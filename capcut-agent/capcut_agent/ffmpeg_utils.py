"""ffmpeg/ffprobe 래퍼: 미디어 정보 조회 및 무음 구간 탐지"""

import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Tuple


class ToolNotFound(RuntimeError):
    """ffmpeg 또는 ffprobe 실행 파일을 찾지 못했을 때"""


def _require(tool: str) -> str:
    path = shutil.which(tool)
    if path is None:
        raise ToolNotFound(
            f"'{tool}' 를 찾을 수 없습니다. Mac: brew install ffmpeg / "
            f"Windows: winget install ffmpeg 후 다시 실행해주세요."
        )
    return path


def probe_duration(path: str) -> float:
    """미디어 전체 길이(초)를 반환"""
    ffprobe = _require("ffprobe")
    out = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def probe_fps(path: str) -> int:
    """비디오 프레임레이트를 반올림한 정수로 반환. 기본값 30."""
    ffprobe = _require("ffprobe")
    out = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    raw = out.stdout.strip()
    if not raw:
        return 30
    if "/" in raw:
        num, den = raw.split("/")
        den = float(den)
        if den == 0:
            return 30
        return round(float(num) / den)
    return round(float(raw))


_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")


def detect_silence(path: str, noise: str = "-30dB", min_silence: float = 0.6) -> List[Tuple[float, float]]:
    """ffmpeg silencedetect 필터로 무음 구간 리스트 [(start, end), ...] (초 단위) 를 반환

    Args:
        path: 입력 미디어 파일 경로
        noise: 무음으로 간주할 음량 임계값 (예: "-30dB")
        min_silence: 무음으로 간주할 최소 지속시간(초)
    """
    ffmpeg = _require("ffmpeg")
    duration = probe_duration(path)

    proc = subprocess.run(
        [ffmpeg, "-i", path, "-af", f"silencedetect=noise={noise}:d={min_silence}",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    log = proc.stderr

    silences: List[Tuple[float, float]] = []
    pending_start: float = None
    for line in log.splitlines():
        m_start = _SILENCE_START_RE.search(line)
        if m_start:
            pending_start = float(m_start.group(1))
            continue
        m_end = _SILENCE_END_RE.search(line)
        if m_end and pending_start is not None:
            silences.append((pending_start, float(m_end.group(1))))
            pending_start = None

    # 파일이 무음으로 끝나는 경우 silence_end 로그가 없을 수 있음
    if pending_start is not None:
        silences.append((pending_start, duration))

    return silences


@dataclass
class MediaInfo:
    duration: float
    fps: int


def probe(path: str) -> MediaInfo:
    return MediaInfo(duration=probe_duration(path), fps=probe_fps(path))
