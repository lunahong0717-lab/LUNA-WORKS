"""보존 구간(KeepSegment) 목록으로 CapCut 점프컷 드래프트를 생성

핵심 함정 메모 (pycapcut 기준):
- 시간 단위는 전부 마이크로초(1s = pycapcut.SEC = 1_000_000).
  ⚠️ tim()/trange()는 문자열("1.5s")만 SEC 배율로 변환하고, int/float를 넘기면
  "이미 마이크로초"로 간주해 그대로 반올림한다. 즉 trange(3.2, 1.0)은 3.2초가 아니라
  3.2마이크로초짜리 구간이 되어버린다. 이 함정을 피하기 위해 초 단위 float는 반드시
  `to_us()`로 명시 변환 후 `Timerange`를 직접 생성한다.
- 메인 비디오 트랙(가장 아래 비디오 트랙)의 첫 세그먼트는 반드시 0에서 시작해야 함.
  그렇지 않으면 CapCut이 강제로 0s로 정렬해버려 이후 모든 컷의 싱크가 깨진다.
- 같은 트랙 위의 세그먼트는 서로 겹칠 수 없다(SegmentOverlap) → target_timerange를
  cursor 기준으로 빈틈없이 이어붙여야 한다.
- 비디오 세그먼트는 오디오를 함께 포함하므로(volume 필드로 제어) 별도 오디오 트랙을
  추가할 필요가 없다 - Stage 1은 비디오 트랙 하나로 충분하다.
- VideoMaterial 생성에는 pymediainfo(→ libmediainfo)가 필요. Mac: brew install mediainfo
"""

import os
from dataclasses import dataclass
from typing import List, Optional

from pycapcut import SEC, DraftFolder, ScriptFile, Timerange, TrackType, VideoMaterial, VideoSegment

from .ffmpeg_utils import probe_fps
from .silence_detect import KeepSegment


def to_us(seconds: float) -> int:
    """초(float) -> 마이크로초(int). tim()/trange()의 숫자-그대로-대입 함정을 피하기 위해 명시 변환."""
    return int(round(seconds * SEC))


@dataclass
class BuildResult:
    draft_name: str
    draft_path: str
    original_duration: float
    final_duration: float
    cut_count: int
    """제거된(=보존되지 않은) 구간 수"""


def build_jumpcut_draft(
    video_path: str,
    keep_segments: List[KeepSegment],
    *,
    draft_folder: str,
    draft_name: str,
    allow_replace: bool = False,
    fps: Optional[int] = None,
) -> BuildResult:
    """무음/NG 구간이 빠진 점프컷 CapCut 드래프트를 생성하고 저장

    Args:
        video_path: 원본 mp4/mov 파일 경로
        keep_segments: 보존할 구간 목록(시간순 정렬되어 있어야 함)
        draft_folder: CapCut 드래프트 루트 폴더 (예: ~/Movies/CapCut/User Data/Projects/com.lveditor.draft)
        draft_name: 생성할 드래프트 이름 (해당 폴더 하위에 같은 이름 폴더가 생김)
        allow_replace: 동일 이름의 드래프트가 있을 때 덮어쓸지 여부
        fps: 강제 지정할 프레임레이트. 지정하지 않으면 원본에서 자동 추출.

    Raises:
        ValueError: keep_segments가 비어있음
    """
    if not keep_segments:
        raise ValueError("keep_segments가 비어 있습니다 - 보존할 구간이 없습니다")

    video_path = os.path.abspath(video_path)
    material = VideoMaterial(video_path)
    detected_fps = fps if fps is not None else probe_fps(video_path)

    folder = DraftFolder(draft_folder)
    try:
        script: ScriptFile = folder.create_draft(
            draft_name, material.width, material.height, detected_fps,
            allow_replace=allow_replace,
        )
    except FileExistsError:
        # pycapcut은 중국어 원문 예외 메시지를 던진다 (예: "草稿文件夹 ... 已存在...").
        # 한국어 사용자에게 그대로 노출하지 않도록 여기서 번역해 다시 던진다.
        raise FileExistsError(
            f"이미 '{draft_name}' 이름의 드래프트가 존재합니다. "
            f"다른 이름을 쓰거나 덮어쓰기를 허용해주세요."
        )
    script.add_track(TrackType.video)

    cursor_us = 0
    for seg in keep_segments:
        source_range = Timerange(to_us(seg.start), to_us(seg.duration))
        if source_range.end > material.duration:
            # 부동소수점 반올림으로 소스 끝이 소재 길이를 살짝 넘는 경우 클램프
            source_range = Timerange(source_range.start, material.duration - source_range.start)
        target_range = Timerange(cursor_us, source_range.duration)

        video_segment = VideoSegment(material, target_range, source_timerange=source_range)
        script.add_segment(video_segment)

        cursor_us += source_range.duration

    script.save()

    original_duration = material.duration / SEC
    draft_path = os.path.join(draft_folder, draft_name)

    return BuildResult(
        draft_name=draft_name,
        draft_path=draft_path,
        original_duration=original_duration,
        final_duration=cursor_us / SEC,
        cut_count=max(0, len(keep_segments) - 1),
    )
