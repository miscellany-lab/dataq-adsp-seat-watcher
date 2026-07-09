# DataQ Seat Watcher

DataQ 자격검정 고사장 목록 팝업을 사용자가 직접 열어둔 상태에서, 화면 OCR과 클립보드 텍스트를 함께 사용해 잔여좌석을 알려주는 Windows 로컬 보조 도구입니다.

처음에는 ADsP 접수 화면을 기준으로 검증했지만, DataQ의 고사장 목록 팝업 구조가 동일한 자격검정이라면 같은 방식으로 사용할 수 있도록 프로젝트 범위를 DataQ 전체 자격검정으로 넓혔습니다.

## 원칙

- 자동 접수 프로그램이 아닙니다.
- 자동 결제, 자동 로그인, 캡차 우회 기능을 만들지 않습니다.
- 비밀번호나 Telegram 토큰을 파일에 저장하지 않습니다.
- DataQ 사이트의 자동화/개발자도구 감지를 우회하지 않습니다.
- 실제 접수와 결제는 사용자가 DataQ 사이트에서 직접 진행합니다.

## 작동 방식

1. 사용자가 일반 Chrome에서 DataQ에 직접 로그인합니다.
2. 응시할 자격검정의 `시험 고사장 목록` 팝업을 직접 엽니다.
3. 앱은 활성 팝업을 새로고침하고, 화면을 스크롤하며 OCR로 좌석 열을 확인합니다.
4. 동시에 화면 텍스트를 클립보드로 복사해 OCR이 깨뜨린 한글 고사장명과 주소를 보정합니다.
5. 잔여좌석이 1석 이상인 행만 정형화해서 GUI 결과 카드와 선택적 Telegram 알림으로 보여줍니다.

이 도구는 화면과 클립보드에 보이는 정보를 읽을 뿐, 접수 절차를 대신 수행하지 않습니다.

## GUI 실행

일반 사용자용 실행 파일은 `dataq_desktop_app.py`입니다.

```powershell
python -m pip install -r requirements.txt
python dataq_desktop_app.py
```

GUI 흐름:

1. 처음 설정 안내
2. 선택 사항: Telegram Bot token / Chat ID 입력 및 테스트
3. DataQ 팝업 준비 안내
4. 감시 설정 확인
5. 실행 화면에서 감시 시작/중지 및 결과 확인

Telegram을 연결하지 않아도 GUI 결과창만으로 사용할 수 있습니다.

## DataQ 화면 준비

1. 일반 Chrome에서 DataQ 접수 페이지에 접속합니다.
2. 사용자가 직접 로그인합니다.
3. 원하는 DataQ 자격검정 접수 화면으로 이동합니다.
4. `시험 고사장 목록` 팝업을 엽니다.
5. 팝업 창을 화면 맨 앞으로 둡니다.
6. GUI에서 `감시 시작`을 누릅니다.

## CLI 실행

개발자/검증용 CLI는 기존 파일명을 유지합니다. 새 별칭으로도 실행할 수 있습니다.

```powershell
python dataq_popup_ocr_watcher.py --refresh --confirm-resubmit --interval 40 --pages 15 --scroll-method wheel --wheel-notches 9 --focus-click 900,500 --keep-awake --bbox 0,90,1845,980 --seat-bbox 1535,90,1645,980 --save-text ocr_debug.txt
```

기존 명령도 호환됩니다.

```powershell
python adsp_popup_ocr_watcher.py --refresh --confirm-resubmit --interval 40 --pages 15 --scroll-method wheel --wheel-notches 9 --focus-click 900,500 --keep-awake --bbox 0,90,1845,980 --seat-bbox 1535,90,1645,980 --save-text ocr_debug.txt
```

## Telegram 알림

Telegram은 선택 사항입니다. 휴대폰 알림이 필요할 때만 연결합니다.

1. Telegram에서 `@BotFather`에게 `/newbot`을 보내 봇을 만듭니다.
2. 발급된 Bot token을 보관합니다.
3. 만든 봇에게 `/start` 메시지를 보냅니다.
4. 아래 주소에서 `chat.id` 값을 확인합니다.

```text
https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
```

PowerShell에서 환경변수로 설정할 수도 있습니다.

```powershell
$env:TELEGRAM_BOT_TOKEN="1234567890:ABC..."
$env:TELEGRAM_CHAT_ID="123456789"
```

GUI에 입력한 값은 파일로 저장하지 않습니다.

## 검증 기록

ADsP 접수 기간 중 실제 DataQ 팝업을 기준으로 다음을 검증했습니다.

- 전체 잔여좌석이 0석일 때 알림이 발생하지 않음
- 실제 잔여좌석이 생긴 행을 감지하고 GUI/Telegram으로 전달
- OCR 한글 깨짐을 클립보드 텍스트로 보정
- 행번호 기준 오름차순 결과 정렬
- 특정 지역 제외 같은 개인 조건 필터 제거

자세한 테스트와 디버깅 기록은 [TESTING_AND_DEBUGGING.md](TESTING_AND_DEBUGGING.md)에 분리했습니다.

### 검증 이미지

0석 상태에서 알림이 발생하지 않는 터미널 로그입니다.

![0석 상태에서 알림이 발생하지 않는 터미널 로그](docs/images/zero-seat-no-alert.png)

실제 잔여좌석을 감지한 터미널 로그입니다.

![잔여좌석 감지 터미널 로그](docs/images/seat-detected-terminal.png)

Telegram으로 전달된 휴대폰 알림 예시입니다.

![Telegram 좌석 알림](docs/images/telegram-seat-alert.png)

## 파일 구성

- `dataq_desktop_app.py`: 일반 사용자용 GUI 실행 별칭
- `dataq_popup_ocr_watcher.py`: DataQ 팝업 OCR 감시 CLI 별칭
- `adsp_desktop_app.py`: GUI 본체, 기존 호환 파일명 유지
- `adsp_popup_ocr_watcher.py`: 팝업 OCR 감시 엔진, 기존 호환 파일명 유지
- `adsp_seat_parser.py`: DataQ 고사장 목록 좌석 파싱 로직
- `adsp_manual_clipboard_watcher.py`: 수동 클립보드 감시 도구
- `adsp_ocr_watcher.py`: 일반 화면 OCR 감시 도구
- `ui/`: pywebview GUI의 HTML/CSS/JS
- `tests/`: ADsP 검증 사례와 DataQ 범용 파서 회귀 테스트

## 배포 전 체크리스트

GitHub에 올리기 전 다음 파일이 포함되지 않도록 확인하세요.

- Telegram bot token 또는 chat_id가 들어간 파일
- `ocr_debug.txt`, `ocr_debug_zero_case.txt`
- `dataq_popup_hits.log`, `adsp_popup_hits.log`
- 브라우저 프로필
- `.vscode/`, `.codex/`, `__pycache__/`

## 한계

- OCR 기반이라 화면 배율, 해상도, 브라우저 크기, DataQ UI 변경에 영향을 받습니다.
- DataQ 팝업 구조가 크게 바뀌면 좌표와 파싱 로직을 조정해야 합니다.
- 잔여좌석이 보인다고 실제 접수 성공을 보장하지 않습니다.
- 접수와 결제는 반드시 사용자가 직접 진행해야 합니다.
