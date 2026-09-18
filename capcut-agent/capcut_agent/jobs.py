"""업로드 -> 무음 분석 -> 드래프트 생성 파이프라인을 SSE 이벤트로 중계

Stage 2에서는 upload/silence/draft 세 단계만 실제로 동작한다.
Stage 3(asr)/Stage 4(filler)는 silence와 draft 사이에 끼워넣을 예정이며,
그 때도 이 파일의 _run/_emit 구조는 그대로 재사용한다.

⚠️ 업로드 파일은 임시로 버리는 사본이 아니라 CapCut 드래프트가 직접 참조하는
   '진짜 소스'다 (build_draft.VideoMaterial.path가 이 파일을 가리킴). 그래서
   OS 임시 폴더가 아니라 영속 디렉토리(UPLOAD_DIR)에 저장하고, 파이프라인이
   끝나도 삭제하지 않는다 - 지우면 CapCut에서 "미디어 오프라인"이 된다.

⚠️ ASR(Stage 3+)은 asyncio.Lock으로 직렬화해야 한다 (mlx/numba 계열은 동시
   호출에 안전하지 않아 segfault 위험). 여기 정의된 _ASR_LOCK을 그 때 사용한다.
"""

import asyncio
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .build_draft import BuildResult, build_jumpcut_draft
from .ffmpeg_utils import probe_duration
from .silence_detect import KeepSegment, analyze

MIN_STAGE_SECONDS = 0.5
"""단계당 최소 지연. 캐시 hit 등으로 순간 끝나도 UI 애니메이션이 보이도록 강제."""

UPLOAD_DIR = Path.home() / ".capcut-agent" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Stage 3(ASR)에서 실제로 사용할 락. 미리 정의해두어 나중에 import 경로가 안 바뀌게 한다.
ASR_LOCK = asyncio.Lock()


@dataclass
class Job:
    id: str
    video_path: Path
    draft_name: str
    draft_folder: str
    noise: str
    min_silence: float
    padding: float
    min_speech: float
    allow_replace: bool
    queue: "asyncio.Queue[Optional[Dict[str, Any]]]" = field(default_factory=asyncio.Queue)
    done: bool = False
    error: Optional[str] = None


_jobs: Dict[str, Job] = {}


def new_job_id() -> str:
    return uuid.uuid4().hex[:12]


def register_job(job: Job) -> None:
    _jobs[job.id] = job


def get_job(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)


def upload_dest(job_id: str, original_filename: str) -> Path:
    """업로드 사본의 저장 경로. 파일명은 Path().name으로 정리해 경로 조작을 막는다."""
    safe_name = Path(original_filename).name
    return UPLOAD_DIR / f"{job_id}_{safe_name}"


async def _emit(job: Job, stage: str, status: str, **payload: Any) -> None:
    await job.queue.put({"stage": stage, "status": status, **payload})


async def _run(job: Job, stage: str, fn, *args, **kwargs):
    """블로킹 함수를 스레드에서 실행하고, 최소 지연을 보장한 뒤 결과를 반환.

    'done' 이벤트는 호출부에서 JSON-safe한 요약 데이터로 직접 emit한다
    (KeepSegment/BuildResult 같은 파이썬 객체를 그대로 큐에 넣지 않기 위해).
    """
    await _emit(job, stage, "start")
    t0 = time.monotonic()
    try:
        result = await asyncio.to_thread(fn, *args, **kwargs)
    except Exception as e:
        await _emit(job, stage, "error", message=str(e))
        raise
    elapsed = time.monotonic() - t0
    if elapsed < MIN_STAGE_SECONDS:
        await asyncio.sleep(MIN_STAGE_SECONDS - elapsed)
    return result


def _upload_stage(video_path: str) -> int:
    return os.path.getsize(video_path)


def _silence_stage(video_path: str, noise: str, min_silence: float,
                    padding: float, min_speech: float):
    duration = probe_duration(video_path)
    keep_segments = analyze(
        video_path, noise=noise, min_silence=min_silence,
        padding=padding, min_speech=min_speech,
    )
    return duration, keep_segments


async def run_pipeline(job: Job) -> None:
    try:
        size_bytes = await _run(job, "upload", _upload_stage, str(job.video_path))
        await _emit(job, "upload", "done", data={"size_mb": round(size_bytes / 1_000_000, 1)})

        duration, keep_segments = await _run(
            job, "silence", _silence_stage, str(job.video_path),
            job.noise, job.min_silence, job.padding, job.min_speech,
        )
        keep_segments: List[KeepSegment]
        kept = sum(s.duration for s in keep_segments)
        await _emit(job, "silence", "done", data={
            "segments": len(keep_segments),
            "kept_seconds": round(kept, 2),
            "kept_ratio": round(kept / duration, 3) if duration else 0.0,
        })

        build_result: BuildResult = await _run(
            job, "draft", build_jumpcut_draft, str(job.video_path), keep_segments,
            draft_folder=job.draft_folder, draft_name=job.draft_name,
            allow_replace=job.allow_replace,
        )
        await _emit(job, "draft", "done", data={
            "draft_path": build_result.draft_path,
            "original_duration": round(build_result.original_duration, 2),
            "final_duration": round(build_result.final_duration, 2),
            "cut_count": build_result.cut_count,
        })

        await _emit(job, "complete", "done", data={
            "draft_name": job.draft_name,
            "draft_path": build_result.draft_path,
        })
    except Exception as e:
        job.error = str(e)
        await _emit(job, "complete", "error", message=str(e))
    finally:
        job.done = True
        await job.queue.put(None)  # SSE 스트림 종료 신호
