from __future__ import annotations

import argparse
import ctypes
import hashlib
import time
import tkinter as tk
from datetime import datetime

from adsp_seat_parser import TARGET_EXAM, parse_table_like_hits


DEFAULT_INTERVAL_SECONDS = 60


def read_clipboard_text() -> str:
    root = tk.Tk()
    root.withdraw()
    try:
        return root.clipboard_get()
    except tk.TclError:
        return ""
    finally:
        root.destroy()


def alert(message: str) -> None:
    print(message, flush=True)
    try:
        import winsound

        winsound.Beep(1200, 700)
        winsound.Beep(1500, 700)
    except Exception:
        pass

    try:
        ctypes.windll.user32.MessageBoxW(None, message, "DataQ 잔여좌석 알림", 0x40)
    except Exception:
        pass


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="일반 Chrome에서 직접 복사한 DataQ 고사장 목록 텍스트를 확인합니다."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"클립보드 확인 주기(초). 기본값: {DEFAULT_INTERVAL_SECONDS}",
    )
    args = parser.parse_args()

    print(f"대상 시험: {TARGET_EXAM}")
    print("일반 Chrome에서 고사장 목록 표 또는 option 텍스트를 직접 복사하세요.")
    print("이 도구는 브라우저를 조작하지 않고, 클립보드 텍스트만 읽습니다.")
    print(f"확인 주기: {args.interval}초")

    last_digest = ""
    last_alert_key = ""

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = read_clipboard_text()
        current_digest = digest(text)

        if text and current_digest != last_digest:
            hits = parse_table_like_hits(text)
            print(f"[{now}] 새 클립보드 텍스트 확인: {len(hits)}건")

            if hits:
                lines = [
                    f"{hit.region} 잔여좌석 {hit.seats}석 - {hit.line}"
                    for hit in hits
                ]
                alert_key = "\n".join(lines)
                if alert_key != last_alert_key:
                    alert("DataQ 잔여좌석 발견\n\n" + "\n".join(lines[:10]))
                    last_alert_key = alert_key
            last_digest = current_digest
        else:
            print(f"[{now}] 변경 없음")

        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
