"""무음 구간을 바탕으로 '보존할' 발화 구간(keep segments)을 계산

전체 대본(단어 단위 X) 원칙과 별개로, Stage 1은 오디오 레벨만으로
점프컷을 만드는 가장 단순한 단계다. NG/잔말 판단은 Stage 4에서
전체 스크립트를 기반으로 추가된다.
"""

from dataclasses import dataclass
from typing import List, Tuple

from .ffmpeg_utils import detect_silence, probe_duration


@dataclass
class KeepSegment:
    start: float
    """구간 시작 (초)"""
    end: float
    """구간 끝 (초)"""

    @property
    def duration(self) -> float:
        return self.end - self.start


def _merge(intervals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """겹치거나 맞닿은 구간을 병합"""
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def compute_keep_segments(
    duration: float,
    silences: List[Tuple[float, float]],
    *,
    padding: float = 0.12,
    min_speech: float = 0.15,
) -> List[KeepSegment]:
    """무음 구간의 여집합으로 발화 구간을 구하고, 패딩을 적용해 최종 보존 구간을 계산

    Args:
        duration: 전체 미디어 길이(초)
        silences: [(start, end), ...] 무음 구간 목록(초)
        padding: 발화 구간 양쪽에 덧붙일 여유 시간(초). 단어 앞뒤가 잘리는 것을 방지.
        min_speech: 이보다 짧은 발화 구간(잡음/클릭 등으로 추정)은 무시하고 잘라냄.
    """
    merged_silences = _merge(silences)

    # 무음 구간의 여집합 = 발화 구간
    speech: List[Tuple[float, float]] = []
    cursor = 0.0
    for s, e in merged_silences:
        s = max(0.0, min(s, duration))
        e = max(0.0, min(e, duration))
        if s > cursor:
            speech.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration:
        speech.append((cursor, duration))

    # 너무 짧은 발화 구간(노이즈로 추정) 제거
    speech = [(s, e) for s, e in speech if (e - s) >= min_speech]

    if not speech:
        # 전부 무음으로 판정된 경우, 안전하게 원본 전체를 보존
        return [KeepSegment(0.0, duration)]

    # 패딩 적용 후 다시 병합 (패딩으로 인접 구간과 겹칠 수 있음)
    padded = [(max(0.0, s - padding), min(duration, e + padding)) for s, e in speech]
    padded = _merge(padded)

    return [KeepSegment(s, e) for s, e in padded]


def analyze(
    path: str,
    *,
    noise: str = "-30dB",
    min_silence: float = 0.6,
    padding: float = 0.12,
    min_speech: float = 0.15,
) -> List[KeepSegment]:
    """입력 파일에 대해 무음 탐지 후 보존 구간 목록을 계산"""
    duration = probe_duration(path)
    silences = detect_silence(path, noise=noise, min_silence=min_silence)
    return compute_keep_segments(
        duration, silences, padding=padding, min_speech=min_speech
    )
