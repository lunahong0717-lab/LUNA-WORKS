"""Stage 1 CLI: 무음/잔말 구간을 잘라낸 CapCut 점프컷 드래프트를 생성

사용 예:
    python -m capcut_agent.cli \\
        --input /path/to/talk.mp4 \\
        --draft-folder "$HOME/Movies/CapCut/User Data/Projects/com.lveditor.draft" \\
        --draft-name my_talk_jumpcut

먼저 --dry-run 으로 보존 구간을 미리 확인한 뒤 실제 드래프트를 생성하는 것을 권장한다.
"""

import argparse
import sys

from .build_draft import build_jumpcut_draft
from .ffmpeg_utils import ToolNotFound, probe_duration
from .silence_detect import analyze


def _default_draft_folder_hint() -> str:
    if sys.platform == "darwin":
        return "~/Movies/CapCut/User Data/Projects/com.lveditor.draft"
    if sys.platform == "win32":
        return r"%APPDATA%\..\Local\CapCut\User Data\Projects\com.lveditor.draft"
    return "(CapCut 드래프트 폴더 경로를 --draft-folder로 직접 지정하세요)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="capcut-agent",
        description="무음/잔말 구간을 잘라낸 CapCut 점프컷 드래프트 생성 (Stage 1)",
    )
    parser.add_argument("--input", required=True, help="입력 mp4/mov 파일 경로")
    parser.add_argument("--draft-name", required=True, help="생성할 CapCut 드래프트 이름")
    parser.add_argument(
        "--draft-folder", default=None,
        help=f"CapCut 드래프트 루트 폴더. 기본 추정 경로: {_default_draft_folder_hint()}",
    )
    parser.add_argument("--noise", default="-30dB", help="무음 판정 음량 임계값 (기본 -30dB)")
    parser.add_argument("--min-silence", type=float, default=0.6, help="무음으로 판정할 최소 길이(초, 기본 0.6)")
    parser.add_argument("--padding", type=float, default=0.12, help="발화 구간 양쪽 여유 시간(초, 기본 0.12)")
    parser.add_argument("--min-speech", type=float, default=0.15, help="이보다 짧은 발화는 노이즈로 간주해 제거 (초, 기본 0.15)")
    parser.add_argument("--allow-replace", action="store_true", help="같은 이름의 드래프트를 덮어쓸지 여부")
    parser.add_argument("--dry-run", action="store_true", help="드래프트를 생성하지 않고 보존 구간만 출력")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        duration = probe_duration(args.input)
        keep_segments = analyze(
            args.input,
            noise=args.noise,
            min_silence=args.min_silence,
            padding=args.padding,
            min_speech=args.min_speech,
        )
    except ToolNotFound as e:
        print(f"[오류] {e}", file=sys.stderr)
        return 1

    kept_total = sum(s.duration for s in keep_segments)
    print(f"원본 길이: {duration:.2f}s / 보존 구간 {len(keep_segments)}개 / 보존 길이: {kept_total:.2f}s "
          f"({kept_total / duration * 100:.1f}%)")
    for i, seg in enumerate(keep_segments):
        print(f"  [{i:03d}] {seg.start:7.2f}s -> {seg.end:7.2f}s  ({seg.duration:.2f}s)")

    if args.dry_run:
        print("\n--dry-run 모드: 드래프트를 생성하지 않았습니다.")
        return 0

    if not args.draft_folder:
        print("[오류] --draft-folder 를 지정해주세요. "
              f"(추정 경로: {_default_draft_folder_hint()})", file=sys.stderr)
        return 1

    try:
        result = build_jumpcut_draft(
            args.input, keep_segments,
            draft_folder=args.draft_folder,
            draft_name=args.draft_name,
            allow_replace=args.allow_replace,
        )
    except FileExistsError as e:
        print(f"[오류] {e}", file=sys.stderr)
        return 1

    print(f"\n드래프트 생성 완료: {result.draft_path}")
    print(f"  원본 {result.original_duration:.2f}s -> 최종 {result.final_duration:.2f}s "
          f"(컷 {result.cut_count}개)")
    print("\n⚠️ 검증은 여기서 끝나지 않습니다. CapCut 앱을 열어 "
          f"'{result.draft_name}' 드래프트를 직접 재생해 확인해주세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
