# CapCut 에이전트

한국어 토킹 영상 자동 편집기. mp4/mov를 넣으면 무음·잔말·NG 컷과 단어별 자막이
반영된 CapCut 드래프트를 만들어준다. FastAPI + 정적 HTML로 동작하는 로컬 웹
도구로 완성할 예정이며, 지금은 **Stage 2 (FastAPI + 정적 HTML, drag/drop + SSE
스테퍼)** 까지 구현되어 있다. Stage 1의 CLI도 그대로 남아있다.

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

## Stage 2: 로컬 웹 UI (drag/drop + SSE 스테퍼)

Stage 1의 파이프라인을 그대로 감싸는 FastAPI 서버 + 정적 HTML 1장이다.
CLI와 결과가 동일하다 (내부적으로 같은 `silence_detect`/`build_draft` 함수 호출).

```bash
source .venv/bin/activate  # 아직 안 했다면
python -m capcut_agent.server
```

브라우저가 자동으로 `http://127.0.0.1:8420` 을 연다 (안 열리면 직접 접속).

사용 흐름:
1. mp4/mov 파일을 드롭존에 끌어놓거나 클릭해서 선택
2. 드래프트 이름 확인(파일명 기반 자동 채움), 드래프트 폴더는 OS별 추정 경로가
   자동으로 채워진다 (틀렸다면 직접 수정). "고급 설정"에서 CLI와 동일한
   `--noise`/`--min-silence`/`--padding`/`--min-speech` 값을 조정 가능
3. "드래프트 생성 시작" → 업로드 → 무음 분석 → 드래프트 생성 단계가 SSE로
   실시간 표시됨
4. 완료 후 통계(원본/최종 길이, 컷 수)와 드래프트 경로 확인 → **CapCut에서
   직접 재생해 검증** (Stage 1과 동일한 검증 체크리스트 적용)

⚠️ **업로드 사본은 지우면 안 된다.** 드롭한 파일은 서버가 `~/.capcut-agent/uploads/`
에 복사본을 저장하고, 생성된 CapCut 드래프트는 원본이 아니라 **이 복사본의
경로**를 참조한다 (브라우저가 보안상 드래그한 파일의 실제 로컬 경로를 알려주지
않기 때문에 업로드가 불가피함). 이 폴더의 파일을 지우면 CapCut에서 "미디어
오프라인"이 뜬다. 편집이 끝나 최종 렌더링까지 마친 뒤에만 정리할 것.

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
- **웹 업로드 사본이 곧 소스**: 브라우저는 보안상 드래그한 파일의 실제 경로를 주지
  않으므로 서버로 업로드(복사)할 수밖에 없다. 이 복사본이 CapCut 드래프트가
  참조하는 실제 미디어 경로가 되므로, OS 임시 폴더가 아니라 영속 디렉토리
  (`~/.capcut-agent/uploads/`)에 저장하고 자동 삭제하지 않는다 (`jobs.py` 참고).
- **pycapcut 예외는 중국어 원문**: 라이브러리 작성자가 중국어 사용자라 `FileExistsError`
  등의 메시지가 중국어로 온다 (예: `"草稿文件夹 ... 已存在..."`). 사용자에게 그대로
  보여주지 말고 알려진 예외는 경계(`build_draft.py`)에서 한국어로 번역해 다시 던진다.

## 로드맵

- [x] Stage 1: `silence_detect` + `build_draft` → 점프컷 드래프트 (CLI, UI 없음)
- [x] Stage 2: FastAPI + 정적 HTML 1장 (drag/drop 업로드 + SSE 진행 단계 표시)
- [ ] Stage 3: mlx-whisper(Mac) / faster-whisper(fallback) 로 전체 대본(세그먼트+단어)
      추출 → 세그먼트 단위 자막 생성. **전체 대본을 먼저 뽑고, 그걸로 NG/자막을
      판단한다 (단어 단위로 그때그때 판단하지 않음)**. ASR은 `jobs.ASR_LOCK`으로
      직렬화 필요 (mlx/numba 계열 동시 호출 시 segfault 위험), 캐시는 파일 mtime이
      아니라 content hash 기준으로 (매 업로드마다 mtime이 바뀌어 캐시 miss남)
- [ ] Stage 4: 전체 대본 기반 잔말(음/어/그니까 등)·NG 컷 통합, 결과 카드에 transcript 노출
- [ ] Stage 5: 영상 프리뷰 + `[`/`]` 단축키로 보존 구간 수동 마킹

## 디자인 톤

Linear/Vercel/Notion 스타일의 모노스페이스 UI. 다크 `#0a0a0a` + 카드 `#161616`,
액센트는 그린 `#22c55e` 한 가지만 사용 (그라데이션·다색 액센트 없음). 숫자는
`tabular-nums`로 정렬. 상태 표시는 큰 체크마크 대신 6px 점 + 글로우, 통계는
3컬럼 그리드, 구분선은 1px `hr`, 경로/코드 값은 모노스페이스 "코드 칩"으로
표시한다 (`capcut_agent/static/index.html` 참고). 참고 영상의 자막 스타일/폰트는
Stage 3에서 자막 렌더링을 붙일 때 반영 예정.
