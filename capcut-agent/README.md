# CapCut 에이전트

한국어 토킹 영상 자동 편집기. mp4/mov를 넣으면 무음·잔말·NG 컷과 단어별 자막이
반영된 CapCut 드래프트를 만들어준다. FastAPI + 정적 HTML로 동작하는 로컬 웹
도구로 완성할 예정이며, 지금은 **Stage 1 (무음 감지 + 점프컷 드래프트 생성,
UI 없음)** 까지 구현되어 있다.

> **검증 = 사용자가 CapCut에서 직접 재생.** 이 스크립트가 에러 없이 끝났다는 것은
> "빌드 성공"일 뿐, "검증 완료"가 아니다. 아래 각 단계를 실행한 뒤 반드시 CapCut
> 앱에서 드래프트를 열어 직접 재생해봐야 한다.

## Step 0: 환경 점검

이 저장소의 코드는 사용자의 **로컬 Mac**에서 실행하는 것을 전제로 한다
(CapCut 드래프트 폴더, 실제 mp4 파일, CapCut 재생 검증이 모두 로컬에서만
가능하기 때문). 아래 명령을 로컬 터미널에서 실행해 환경을 확인한다.

```bash
python3 -c "import platform; print(platform.system(), platform.machine())"
# -> Darwin arm64 면 트랙 A (Apple Silicon, mlx-whisper 예정)
```

필요한 도구가 없다면 설치만 하고 다시 실행:

```bash
# Homebrew가 없다면 먼저 설치: https://brew.sh
brew install python@3.11 ffmpeg mediainfo
```

- **ffmpeg**: 무음 감지(`silencedetect`)와 미디어 정보 조회(`ffprobe`)에 사용
- **mediainfo**: `pycapcut`이 내부적으로 사용하는 `pymediainfo`의 의존 라이브러리
  (pip로 설치되는 `pymediainfo` wheel에 이미 번들되어 있는 경우가 많지만,
  안 될 경우를 대비해 brew로도 설치해둔다)
- **CapCut 드래프트 폴더**: CapCut 앱을 한 번이라도 실행해 최소 1개의 드래프트를
  만들어본 적이 있어야 폴더가 생성된다. 기본 위치(버전에 따라 다를 수 있음):
  `~/Movies/CapCut/User Data/Projects/com.lveditor.draft`
  확실하지 않으면 CapCut 앱 설정에서 "드래프트 저장 위치"를 확인할 것.
- **디스크 5GB 이상 여유 공간**

macOS는 `~/Movies` 접근 시 터미널에 "파일과 폴더 접근 권한"을 요구할 수 있다.
권한 팝업이 뜨면 허용하고, 이미 거부했다면 시스템 설정 > 개인정보 보호 및 보안 >
파일과 폴더에서 터미널(또는 사용 중인 IDE)에 권한을 켜준다.

### 설치

```bash
cd capcut-agent
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Stage 1: 무음 감지 + 점프컷 드래프트

먼저 `--dry-run`으로 보존 구간만 확인해 임계값을 조정한다 (드래프트를
만들지 않으므로 CapCut을 열 필요 없이 빠르게 반복 가능):

```bash
python -m capcut_agent.cli \
  --input /path/to/talk.mp4 \
  --draft-name my_talk_jumpcut \
  --dry-run
```

출력에서 보존 구간이 자연스러운지 확인한다. 너무 잘게 잘린다면
`--min-silence`(무음 최소 길이)를 늘리거나, 단어 끝이 잘리는 것 같다면
`--padding`을 늘린다.

만족스러우면 실제 CapCut 드래프트를 생성:

```bash
python -m capcut_agent.cli \
  --input /path/to/talk.mp4 \
  --draft-name my_talk_jumpcut \
  --draft-folder "$HOME/Movies/CapCut/User Data/Projects/com.lveditor.draft"
```

### 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--noise` | `-30dB` | 이보다 조용하면 무음으로 판정 |
| `--min-silence` | `0.6` | 이보다 짧은 무음은 자연스러운 호흡/쉼표로 보고 자르지 않음 |
| `--padding` | `0.12` | 발화 구간 앞뒤 여유(초). 단어 클리핑 방지 |
| `--min-speech` | `0.15` | 이보다 짧은 발화 블립은 노이즈로 간주해 제거 |
| `--allow-replace` | off | 동일 이름 드래프트 덮어쓰기 |

### ✅ 검증 체크리스트 (필수)

1. CapCut 앱을 연다.
2. 방금 생성된 `my_talk_jumpcut` 드래프트를 연다.
3. 처음부터 끝까지 직접 재생하며 확인:
   - [ ] 컷 경계에서 단어가 잘리지 않는가
   - [ ] 영상과 오디오 싱크가 맞는가 (비디오 세그먼트가 오디오를 함께 담고 있음)
   - [ ] 화질/해상도가 원본과 동일하게 보이는가
   - [ ] 타임라인 총 길이가 CLI 출력의 "최종 길이"와 일치하는가

이 체크리스트를 통과해야 Stage 2(FastAPI + 웹 UI)로 넘어간다.

## 알려진 함정 (pycapcut 기준, 리버스엔지니어링으로 확인)

- **시간 단위**: `draft_content.json`의 모든 timerange는 마이크로초. `pycapcut`의
  `tim()`/`trange()`는 **문자열만** `SEC`(=1,000,000) 배율로 변환하고, `int`/`float`를
  넘기면 "이미 마이크로초"로 간주해 그대로 반올림한다. 초 단위 float를 넘기면
  1/1,000,000로 줄어든 컷이 생긴다 — 반드시 `to_us()`처럼 명시적으로 변환할 것
  (`capcut_agent/build_draft.py` 참고).
- **메인 비디오 트랙 정렬**: 가장 아래 비디오 트랙의 첫 세그먼트는 반드시 0에서
  시작해야 한다. 아니면 CapCut이 강제로 0s 정렬해버려 이후 모든 컷의 싱크가 깨진다.
- **세그먼트 겹침 금지**: 같은 트랙 위 세그먼트는 겹칠 수 없다(`SegmentOverlap`).
  점프컷은 `target_timerange`를 커서 기준으로 빈틈없이 이어붙여야 한다.
- **오디오는 비디오 세그먼트에 내장**: 별도 오디오 트랙 없이도 비디오 세그먼트의
  `volume` 필드로 음량 제어가 된다. Stage 1은 비디오 트랙 하나로 충분.
- **`transform_y`**: CapCut이 자막을 SRT로 가져올 때 기본으로 `-0.8`(화면 하단
  근처)을 사용한다 (`ScriptFile.import_srt`의 기본 `clip_settings`). Stage 3에서
  자막 위치를 잡을 때 참고.
- **draft_meta_info.json 필수**: `draft_content.json`만으로는 CapCut이 드래프트
  목록에 인식하지 못한다. `DraftFolder.create_draft()`가 템플릿에서 자동 복사해주므로
  반드시 `DraftFolder`/`ScriptFile` 조합을 통해서만 드래프트를 생성해야 한다.
- **ASR Lock 주의 (Stage 3+ 예정)**: 이 도구로 만든 드래프트를 CapCut에서 연 뒤
  CapCut 자체의 "자동 자막(음성 인식)" 기능을 실행하면, 우리가 넣은 자막 트랙과
  충돌하거나 덮어써질 수 있다. Stage 3 이후 자막을 넣은 드래프트에서는 CapCut의
  자체 자동 자막 기능을 켜지 않는다.
- **macOS 샌드박스/권한**: 터미널이 `~/Movies` 하위 CapCut 폴더에 쓰기 권한이 없으면
  `PermissionError`가 조용히 나거나 폴더가 안 만들어질 수 있다. Step 0의 권한 안내 참고.

## 로드맵

- [x] Stage 1: `silence_detect` + `build_draft` → 점프컷 드래프트 (본 저장소, UI 없음)
- [ ] Stage 2: FastAPI + 정적 HTML 1장 (drag/drop 업로드 + SSE 진행 단계 표시)
- [ ] Stage 3: mlx-whisper(Mac) / faster-whisper(fallback) 로 전체 대본(세그먼트+단어)
      추출 → 세그먼트 단위 자막 생성. **전체 대본을 먼저 뽑고, 그걸로 NG/자막을
      판단한다 (단어 단위로 그때그때 판단하지 않음)**
- [ ] Stage 4: 전체 대본 기반 잔말(음/어/그니까 등)·NG 컷 통합, 결과 카드에 transcript 노출
- [ ] Stage 5: 영상 프리뷰 + `[`/`]` 단축키로 보존 구간 수동 마킹

## 디자인 톤 (Stage 2+ 예정)

자막 스타일/폰트/무드는 참고 영상(사용자 제공 링크)과 동일하게 맞출 예정.
Stage 2에서 정적 HTML 프리뷰 UI를 만들 때 함께 반영한다.
