from __future__ import annotations

import argparse
import ctypes
import shutil
import time
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab
import pytesseract

from adsp_seat_parser import TARGET_EXAM, parse_table_like_hits


DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
DEFAULT_LANG = "kor+eng"


def configure_tesseract(path: str | None) -> None:
    candidates = [
        path,
        DEFAULT_TESSERACT_PATH,
        shutil.which("tesseract"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            return


def parse_bbox(value: str | None) -> tuple[int, int, int, int] | None:
    if not value:
        return None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("영역은 left,top,right,bottom 형식이어야 합니다.")
    try:
        left, top, right, bottom = [int(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("영역 좌표는 정수여야 합니다.") from exc
    if right <= left or bottom <= top:
        raise argparse.ArgumentTypeError("right/bottom은 left/top보다 커야 합니다.")
    return left, top, right, bottom


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


def screenshot_text(bbox: tuple[int, int, int, int] | None, lang: str) -> str:
    image = ImageGrab.grab(bbox=bbox)
    return pytesseract.image_to_string(image, lang=lang, config="--psm 6")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="일반 Chrome 화면에 보이는 DataQ 고사장 목록을 OCR로 확인합니다."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"화면 확인 주기(초). 기본값: {DEFAULT_INTERVAL_SECONDS}",
    )
    parser.add_argument(
        "--bbox",
        type=parse_bbox,
        default=None,
        help="OCR 화면 영역. 예: 100,250,1600,950",
    )
    parser.add_argument(
        "--lang",
        default=DEFAULT_LANG,
        help=f"Tesseract OCR 언어. 기본값: {DEFAULT_LANG}",
    )
    parser.add_argument(
        "--tesseract",
        default=None,
        help=f"tesseract.exe 경로. 기본값 후보: {DEFAULT_TESSERACT_PATH}",
    )
    parser.add_argument(
        "--save-text",
        default=None,
        help="디버깅용 OCR 텍스트 저장 파일 경로",
    )
    args = parser.parse_args()

    configure_tesseract(args.tesseract)

    print(f"대상 시험: {TARGET_EXAM}")
    print("일반 Chrome에서 DataQ 고사장 목록 화면을 열어둔 상태로 실행하세요.")
    print("이 도구는 브라우저를 조작하지 않고, 화면에 보이는 텍스트만 OCR로 읽습니다.")
    print("DataQ 화면 갱신 또는 새로고침은 사용자가 직접 해야 합니다.")
    print(f"확인 주기: {args.interval}초")
    print(f"OCR 언어: {args.lang}")
    print(f"OCR 영역: {args.bbox or '전체 화면'}")

    last_alert_key = ""

    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            text = screenshot_text(args.bbox, args.lang)
        except Exception as exc:
            print(f"[{now}] OCR 실패: {exc}")
            time.sleep(max(5, args.interval))
            continue

        if args.save_text:
            Path(args.save_text).write_text(text, encoding="utf-8")

        hits = parse_table_like_hits(text)
        print(f"[{now}] OCR 확인: {len(hits)}건")

        if hits:
            lines = [
                f"{hit.region} 잔여좌석 {hit.seats}석 - {hit.line}"
                for hit in hits
            ]
            alert_key = "\n".join(lines)
            if alert_key != last_alert_key:
                alert("DataQ 잔여좌석 발견\n\n" + "\n".join(lines[:10]))
                last_alert_key = alert_key

        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
