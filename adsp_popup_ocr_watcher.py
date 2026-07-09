from __future__ import annotations

import argparse
import ctypes
import os
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from PIL import ImageEnhance, ImageGrab, ImageOps
import pytesseract

from adsp_seat_parser import TARGET_EXAM, SeatHit, parse_table_like_hits


DEFAULT_INTERVAL_SECONDS = 60
DEFAULT_REFRESH_WAIT_SECONDS = 2
DEFAULT_TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
DEFAULT_LANG = "kor+eng"
DEFAULT_FOCUS_CLICK = "900,500"
DEFAULT_SEAT_BBOX = "1535,90,1645,980"

VK_F5 = 0x74
VK_HOME = 0x24
VK_NEXT = 0x22
VK_CONTROL = 0x11
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120
ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

STOP_KEYWORDS = [
    "개발자 도구",
    "자동화",
    "captcha",
    "CAPTCHA",
    "보안문자",
    "비밀번호",
    "로그인",
]


def configure_tesseract(path: str | None) -> None:
    candidates = [path, DEFAULT_TESSERACT_PATH, shutil.which("tesseract")]
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


def parse_point(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("좌표는 x,y 형식이어야 합니다.")
    try:
        x, y = [int(part) for part in parts]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("좌표는 정수여야 합니다.") from exc
    return x, y


def press_key(vk: int) -> None:
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def press_ctrl_home() -> None:
    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
    press_key(VK_HOME)
    ctypes.windll.user32.keybd_event(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)


def click_point(point: tuple[int, int] | None) -> None:
    if point is None:
        return
    x, y = point
    ctypes.windll.user32.SetCursorPos(x, y)
    time.sleep(0.03)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    time.sleep(0.05)


def scroll_wheel(notches: int) -> None:
    ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, notches * WHEEL_DELTA, 0)


def alert(message: str, show_message_box: bool = False) -> None:
    print(message, flush=True)
    try:
        import winsound

        winsound.Beep(1200, 700)
        winsound.Beep(1500, 700)
    except Exception:
        pass

    if show_message_box:
        def show_message() -> None:
            try:
                ctypes.windll.user32.MessageBoxW(None, message, "ADsP 잔여좌석 알림", 0x40)
            except Exception:
                pass

        threading.Thread(target=show_message, daemon=True).start()


def send_telegram(token: str | None, chat_id: str | None, message: str) -> bool:
    if not token or not chat_id:
        print("Telegram 알림 건너뜀: TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID가 없습니다.", flush=True)
        return False

    data = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message[:3500],
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as response:
            response.read()
        print("Telegram 알림 전송 완료", flush=True)
        return True
    except Exception as exc:
        print(f"Telegram 알림 실패: {exc}", flush=True)
        return False


def keep_awake(enable: bool) -> None:
    if not enable:
        return
    ctypes.windll.kernel32.SetThreadExecutionState(
        ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
    )


def screenshot_text(
    bbox: tuple[int, int, int, int] | None,
    lang: str,
    scale: float,
    contrast: float,
) -> str:
    image = ImageGrab.grab(bbox=bbox)
    image = ImageOps.grayscale(image)
    if scale and scale != 1:
        width, height = image.size
        image = image.resize((int(width * scale), int(height * scale)))
    if contrast and contrast != 1:
        image = ImageEnhance.Contrast(image).enhance(contrast)
    text_psm6 = pytesseract.image_to_string(image, lang=lang, config="--oem 3 --psm 6")
    text_psm11 = pytesseract.image_to_string(image, lang=lang, config="--oem 3 --psm 11")
    return text_psm6 + "\n" + text_psm11


def screenshot_digits(
    bbox: tuple[int, int, int, int],
    scale: float,
    contrast: float,
) -> str:
    image = ImageGrab.grab(bbox=bbox)
    image = ImageOps.grayscale(image)
    if scale and scale != 1:
        width, height = image.size
        image = image.resize((int(width * scale), int(height * scale)))
    if contrast and contrast != 1:
        image = ImageEnhance.Contrast(image).enhance(contrast)
    config = "--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789"
    return pytesseract.image_to_string(image, lang="eng", config=config)


def append_log(path: str | None, message: str) -> None:
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as file:
        file.write(message.rstrip() + "\n")


def contains_stop_keyword(text: str) -> str | None:
    for keyword in STOP_KEYWORDS:
        if keyword in text:
            return keyword
    return None


def parse_seat_column_hits(text: str, page_number: int) -> list[SeatHit]:
    hits: list[SeatHit] = []
    seen: set[int] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        compact = re.sub(r"\s+", "", line)
        if not re.fullmatch(r"\d{1,3}", compact):
            continue
        seats = int(compact)
        if seats == 0 or seats in seen:
            continue
        seen.add(seats)
        hits.append(
            SeatHit(
                region=f"OCR seat column page {page_number}",
                seats=seats,
                line=f"seat-column OCR: {line}",
                priority=999,
            )
        )
    return hits




def scan_pages(
    bbox: tuple[int, int, int, int] | None,
    lang: str,
    pages: int,
    page_wait: float,
    focus_click: tuple[int, int] | None,
    scroll_method: str,
    wheel_notches: int,
    ocr_scale: float,
    ocr_contrast: float,
    seat_bbox: tuple[int, int, int, int] | None,
    on_page=None,
) -> tuple[str, list]:
    texts: list[str] = []
    hits = []

    click_point(focus_click)

    if pages > 1:
        press_ctrl_home()
        time.sleep(page_wait)
        click_point(focus_click)

    for page in range(max(1, pages)):
        text = screenshot_text(bbox, lang, ocr_scale, ocr_contrast)
        texts.append(text)
        page_hits = parse_table_like_hits(text)
        if seat_bbox is not None:
            seat_text = screenshot_digits(seat_bbox, ocr_scale, ocr_contrast)
            texts.append(seat_text)
            page_hits.extend(parse_seat_column_hits(seat_text, page + 1))
        hits.extend(page_hits)
        if on_page:
            on_page(text, page_hits, page + 1)

        if page + 1 < pages:
            click_point(focus_click)
            if scroll_method == "pagedown":
                press_key(VK_NEXT)
            else:
                scroll_wheel(-abs(wheel_notches))
            time.sleep(page_wait)

    if pages > 1:
        click_point(focus_click)
        press_ctrl_home()
        time.sleep(page_wait)

    unique = {(hit.region, hit.seats, hit.line): hit for hit in hits}
    sorted_hits = sorted(unique.values(), key=lambda hit: (hit.priority, -hit.seats, hit.line))
    return "\n".join(texts), sorted_hits


def main() -> int:
    parser = argparse.ArgumentParser(
        description="사용자가 열어둔 DataQ 고사장 팝업을 보수적으로 새로고침하고 OCR로 확인합니다."
    )
    parser.add_argument("--refresh", action="store_true", help="활성 창에 F5를 보내 새로고침합니다.")
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"확인 주기(초). 기본값: {DEFAULT_INTERVAL_SECONDS}",
    )
    parser.add_argument(
        "--refresh-wait",
        type=int,
        default=DEFAULT_REFRESH_WAIT_SECONDS,
        help=f"새로고침 후 OCR 전 대기 시간(초). 기본값: {DEFAULT_REFRESH_WAIT_SECONDS}",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=1,
        help="PageDown으로 훑을 화면 수. 기본값: 1",
    )
    parser.add_argument(
        "--page-wait",
        type=float,
        default=0.35,
        help="페이지 이동 후 OCR 전 대기 시간(초). 기본값: 0.35",
    )
    parser.add_argument("--bbox", type=parse_bbox, default=None, help="OCR 영역. 예: 0,110,1845,1010")
    parser.add_argument("--seat-bbox", type=parse_bbox, default=parse_bbox(DEFAULT_SEAT_BBOX), help=f"잔여좌석 열 OCR 영역. 기본값: {DEFAULT_SEAT_BBOX}")
    parser.add_argument("--disable-seat-column-check", action="store_true", help="잔여좌석 열 전용 OCR 보조 검사를 끕니다.")
    parser.add_argument("--message-box", action="store_true", help="알림 시 Windows 메시지박스를 띄웁니다. 기본값은 꺼짐입니다.")
    parser.add_argument("--focus-click", type=parse_point, default=parse_point(DEFAULT_FOCUS_CLICK), help=f"포커스 복구용 본문 클릭 좌표. 기본값: {DEFAULT_FOCUS_CLICK}")
    parser.add_argument("--scroll-method", choices=["wheel", "pagedown"], default="wheel", help="스크롤 방식. 기본값: wheel")
    parser.add_argument("--wheel-notches", type=int, default=7, help="wheel 방식에서 한 번에 내릴 휠 칸 수. 기본값: 7")
    parser.add_argument("--ocr-scale", type=float, default=2.0, help="OCR 전 이미지 확대 배율. 기본값: 2.0")
    parser.add_argument("--ocr-contrast", type=float, default=1.8, help="OCR 전 이미지 대비 강화. 기본값: 1.8")
    parser.add_argument("--lang", default=DEFAULT_LANG, help=f"OCR 언어. 기본값: {DEFAULT_LANG}")
    parser.add_argument("--tesseract", default=None, help="tesseract.exe 경로")
    parser.add_argument("--save-text", default=None, help="마지막 OCR 텍스트 저장 파일")
    parser.add_argument("--log-file", default="adsp_popup_hits.log", help="알림 로그 파일")
    parser.add_argument("--keep-awake", action="store_true", help="실행 중 Windows 절전/화면 꺼짐을 방지합니다.")
    parser.add_argument(
        "--confirm-resubmit",
        action="store_true",
        help="새로고침 후 브라우저의 양식 다시 제출 확인 창에서 Enter를 눌러 계속합니다.",
    )
    parser.add_argument(
        "--confirm-retries",
        type=int,
        default=4,
        help="양식 다시 제출 확인 창에 보낼 Enter 횟수. 기본값: 4",
    )
    parser.add_argument(
        "--confirm-wait",
        type=float,
        default=0.35,
        help="확인 Enter 사이 대기 시간(초). 기본값: 0.35",
    )
    parser.add_argument("--telegram-token", default=None, help="Telegram Bot token")
    parser.add_argument("--telegram-chat-id", default=None, help="Telegram chat_id")
    parser.add_argument("--telegram-test", action="store_true", help="시작 시 Telegram 테스트 메시지를 1회 전송합니다.")
    args = parser.parse_args()

    if not args.telegram_token:
        args.telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not args.telegram_chat_id:
        args.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")

    configure_tesseract(args.tesseract)
    keep_awake(args.keep_awake)

    print(f"대상 시험: {TARGET_EXAM}")
    print("Chrome의 DataQ 고사장 팝업을 맨 앞에 둔 상태로 실행하세요.")
    print("자동 접수/결제/로그인/캡차 처리/감지 우회는 하지 않습니다.")
    print(f"새로고침: {'사용' if args.refresh else '사용 안 함'}")
    print(f"확인 주기: {args.interval}초")
    print(f"스캔 화면 수: {max(1, args.pages)}")
    print(f"OCR 영역: {args.bbox or '전체 화면'}")
    telegram_ready = bool(args.telegram_token and args.telegram_chat_id)
    print(f"Telegram 알림: {'사용' if telegram_ready else '미설정'}")
    if args.telegram_test:
        test_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        send_telegram(args.telegram_token, args.telegram_chat_id, f"ADsP watcher Telegram test\n시간: {test_now}")

    last_alert_key = ""
    cycle_alert_sent = False

    def handle_page_alerts(_page_text, page_hits, _page_number):
        nonlocal last_alert_key, cycle_alert_sent
        page_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if page_hits and not cycle_alert_sent:
            lines = [f"{hit.region} 잔여좌석 {hit.seats}석 - {hit.line}" for hit in page_hits]
            alert_key = "\n".join(lines)
            if alert_key != last_alert_key:
                message = "ADsP 잔여좌석 발견\n\n" + "\n".join(lines[:10])
                append_log(args.log_file, f"[{page_now}]\n{message}\n")
                alert(message, args.message_box)
                send_telegram(args.telegram_token, args.telegram_chat_id, message)
                last_alert_key = alert_key
            cycle_alert_sent = True

    while True:
        cycle_alert_sent = False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if args.refresh:
            print(f"[{now}] 활성 창 새로고침")
            press_key(VK_F5)
            if args.confirm_resubmit:
                for _ in range(max(1, args.confirm_retries)):
                    time.sleep(max(0.2, args.confirm_wait))
                    press_key(VK_RETURN)
            time.sleep(max(1, args.refresh_wait))
            click_point(args.focus_click)

        try:
            text, hits = scan_pages(
                args.bbox,
                args.lang,
                args.pages,
                args.page_wait,
                args.focus_click,
                args.scroll_method,
                args.wheel_notches,
                args.ocr_scale,
                args.ocr_contrast,
                None if args.disable_seat_column_check else args.seat_bbox,
                handle_page_alerts,
            )
        except Exception as exc:
            print(f"[{now}] OCR 실패: {exc}")
            time.sleep(max(10, args.interval))
            continue

        if args.save_text:
            Path(args.save_text).write_text(text, encoding="utf-8")

        stop_keyword = contains_stop_keyword(text)
        if stop_keyword:
            message = f"[{now}] 중단 키워드 감지: {stop_keyword}. 자동 새로고침을 중단합니다."
            print(message)
            append_log(args.log_file, message)
            alert(message, args.message_box)
            send_telegram(args.telegram_token, args.telegram_chat_id, message)
            return 2

        print(f"[{now}] 팝업 OCR 확인: {len(hits)}건")

        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())



















