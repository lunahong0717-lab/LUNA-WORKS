"""CapCut 에이전트 로컬 웹 서버 (Stage 2: FastAPI + 정적 HTML 1장)

실행: python -m capcut_agent.server
"""

import asyncio
import json
import os
import shutil
import sys
import webbrowser
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import jobs

STATIC_DIR = Path(__file__).parent / "static"


def default_draft_folder() -> str:
    if sys.platform == "darwin":
        return str(Path.home() / "Movies/CapCut/User Data/Projects/com.lveditor.draft")
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        return str(Path(local_appdata) / "CapCut/User Data/Projects/com.lveditor.draft")
    return ""


def track_label() -> str:
    """Step 0의 OS 판정 로직을 웹 UI에도 그대로 노출 (참고용 표시)"""
    machine = os.uname().machine if hasattr(os, "uname") else ""
    if sys.platform == "darwin" and machine == "arm64":
        return "Track A (Mac M칩, mlx-whisper 예정)"
    if sys.platform == "win32":
        return "Track C (faster-whisper 예정)"
    return "fallback (faster-whisper 예정)"


def _validate_draft_name(name: str) -> None:
    """draft_name은 draft_folder 하위 폴더명으로 그대로 쓰이므로 경로 조작 문자를 막는다"""
    if not name or name != Path(name).name or ".." in name:
        raise HTTPException(400, "드래프트 이름에 경로 구분자나 '..'를 사용할 수 없습니다")


app = FastAPI(title="CapCut 에이전트")


@app.get("/api/config")
async def get_config():
    folder = default_draft_folder()
    return {
        "platform": sys.platform,
        "track": track_label(),
        "default_draft_folder": folder,
        "draft_folder_exists": bool(folder) and Path(folder).expanduser().exists(),
    }


@app.post("/api/jobs")
async def create_job(
    video: UploadFile = File(...),
    draft_name: str = Form(...),
    draft_folder: str = Form(...),
    noise: str = Form("-30dB"),
    min_silence: float = Form(0.6),
    padding: float = Form(0.12),
    min_speech: float = Form(0.15),
    allow_replace: bool = Form(False),
):
    if not video.filename or not video.filename.lower().endswith((".mp4", ".mov")):
        raise HTTPException(400, "mp4 또는 mov 파일만 지원합니다")
    _validate_draft_name(draft_name)

    draft_folder_path = Path(draft_folder).expanduser()
    if not draft_folder_path.exists():
        raise HTTPException(400, f"드래프트 폴더가 존재하지 않습니다: {draft_folder}")

    job_id = jobs.new_job_id()
    dest = jobs.upload_dest(job_id, video.filename)
    with dest.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    job = jobs.Job(
        id=job_id,
        video_path=dest,
        draft_name=draft_name,
        draft_folder=str(draft_folder_path),
        noise=noise,
        min_silence=min_silence,
        padding=padding,
        min_speech=min_speech,
        allow_replace=allow_replace,
    )
    jobs.register_job(job)
    asyncio.create_task(jobs.run_pipeline(job))

    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(404, "존재하지 않는 job입니다")

    async def event_stream():
        while True:
            item = await job.queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# 정적 HTML(1장)은 API 라우트 등록 이후 마운트해야 /api/* 가 가로채이지 않는다
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


def main() -> None:
    import uvicorn

    host, port = "127.0.0.1", 8420
    url = f"http://{host}:{port}"
    print(f"CapCut 에이전트 실행 중: {url}")
    print(f"업로드 저장 위치: {jobs.UPLOAD_DIR} (드래프트가 이 파일을 참조하므로 지우지 마세요)")

    try:
        webbrowser.open(url)
    except Exception:
        pass

    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
