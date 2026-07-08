from __future__ import annotations


NOTICE = """
이 파일은 초기 Playwright 방식의 진입점 이름을 보존하기 위한 안내용 파일입니다.

DataQ 접수 화면에서 Playwright/개발자도구 환경이 감지되어 차단될 수 있으므로,
이 프로젝트는 자동화 우회 코드를 제공하지 않습니다.

권장 실행:
  py -3 adsp_manual_clipboard_watcher.py
  py -3 adsp_ocr_watcher.py

정책:
  - 자동 접수, 자동 결제, 자동 로그인 기능 없음
  - 캡차 우회 기능 없음
  - 비밀번호 저장 기능 없음
  - 자동화/개발자도구 감지 우회 없음
  - 실제 접수와 결제는 사용자가 직접 수행
"""


def main() -> int:
    print(NOTICE.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
