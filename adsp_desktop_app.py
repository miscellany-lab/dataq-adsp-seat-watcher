"""CSS-based desktop shell for the DataQ seat watcher.

This app keeps the proven watcher engine in Python and moves the general-user
experience to a small HTML/CSS interface rendered by pywebview.
"""
from __future__ import annotations

import os
import json
import queue
import re
import signal
import subprocess
import sys
import threading
import webbrowser
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

try:
    import webview
except ImportError:  # pragma: no cover - user-facing dependency guard
    webview = None

from adsp_popup_ocr_watcher import DEFAULT_FOCUS_CLICK, DEFAULT_SEAT_BBOX, send_telegram


BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR / "ui"
DATAQ_ACCEPT_URL = "https://www.dataq.or.kr/www/accept/list.do"


@dataclass
class WatcherConfig:
    telegram_token: str = ""
    telegram_chat_id: str = ""
    interval: int = 40
    pages: int = 15
    wheel_notches: int = 9
    focus_click: str = DEFAULT_FOCUS_CLICK
    bbox: str = "0,90,1845,980"
    seat_bbox: str = DEFAULT_SEAT_BBOX
    save_text: str = "ocr_debug.txt"
    refresh: bool = True
    confirm_resubmit: bool = True
    keep_awake: bool = True
    message_box: bool = False
    telegram_test_on_start: bool = False
    seat_column: bool = True
    clipboard_assist: bool = True



def _result_sort_key(item: dict[str, str]) -> tuple[int, str]:
    try:
        row_number = int(item.get("no") or 999999)
    except (TypeError, ValueError):
        row_number = 999999
    return row_number, str(item.get("site") or "")

class WatcherApi:
    def __init__(self) -> None:
        self.process: subprocess.Popen[str] | None = None
        self.events: queue.Queue[dict[str, str]] = queue.Queue()
        self.results: list[dict[str, str]] = []
        self.log_lines: list[str] = []
        self.last_started_at = ""
        self._pending_result: dict[str, str] | None = None

    def get_default_config(self) -> dict:
        return asdict(WatcherConfig())

    def open_dataq(self, _payload: dict | None = None) -> dict:
        webbrowser.open(DATAQ_ACCEPT_URL)
        return {"ok": True, "message": "DataQ 접수 화면을 열었습니다."}

    def test_telegram(self, config: dict) -> dict:
        cfg = self._coerce_config(config)
        if not cfg.telegram_token or not cfg.telegram_chat_id:
            return {"ok": False, "message": "Bot token과 Chat ID를 모두 입력해야 테스트할 수 있습니다."}
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            send_telegram(cfg.telegram_token, cfg.telegram_chat_id, f"DataQ Seat Watcher 테스트 알림\n시간: {now}")
        except Exception as exc:  # pragma: no cover - network/runtime path
            return {"ok": False, "message": f"Telegram 전송 실패: {exc}"}
        return {"ok": True, "message": "휴대폰으로 테스트 알림을 보냈습니다."}

    def start_watcher(self, config: dict) -> dict:
        if self.process and self.process.poll() is None:
            return {"ok": False, "message": "이미 감시가 실행 중입니다."}

        cfg = self._coerce_config(config)
        command = self._build_command(cfg)
        env = os.environ.copy()
        if cfg.telegram_token and cfg.telegram_chat_id:
            env["TELEGRAM_BOT_TOKEN"] = cfg.telegram_token
            env["TELEGRAM_CHAT_ID"] = cfg.telegram_chat_id
        else:
            env.pop("TELEGRAM_BOT_TOKEN", None)
            env.pop("TELEGRAM_CHAT_ID", None)

        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(BASE_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except Exception as exc:
            return {"ok": False, "message": f"실행 실패: {exc}"}

        self.last_started_at = datetime.now().strftime("%H:%M:%S")
        self._pending_result = None
        self._emit("status", "감시를 시작했습니다.")
        threading.Thread(target=self._read_process_output, daemon=True).start()
        return {"ok": True, "message": "감시를 시작했습니다.", "command": " ".join(command)}

    def stop_watcher(self, _payload: dict | None = None) -> dict:
        if not self.process or self.process.poll() is not None:
            self.process = None
            return {"ok": True, "message": "실행 중인 감시가 없습니다."}

        process = self.process
        stopped = False
        if os.name == "nt":
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
                process.wait(timeout=2)
                stopped = True
            except Exception:
                stopped = False

        if not stopped and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
                stopped = True
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
                stopped = True

        self.process = None
        self._pending_result = None
        self._emit("status", "감시를 중지했습니다.")
        return {"ok": True, "message": "감시를 중지했습니다."}

    def poll(self) -> dict:
        items = []
        while True:
            try:
                items.append(self.events.get_nowait())
            except queue.Empty:
                break
        self._sync_results_from_log()
        running = bool(self.process and self.process.poll() is None)
        if self.process and not running:
            self.process = None
        return {
            "running": running,
            "startedAt": self.last_started_at,
            "events": items,
            "results": sorted(self.results[-120:], key=_result_sort_key),
            "log": "".join(self.log_lines[-500:]),
        }

    def _build_command(self, cfg: WatcherConfig) -> list[str]:
        cmd = [
            sys.executable,
            "adsp_popup_ocr_watcher.py",
            "--interval",
            str(max(10, int(cfg.interval))),
            "--pages",
            str(max(1, int(cfg.pages))),
            "--scroll-method",
            "wheel",
            "--wheel-notches",
            str(max(1, int(cfg.wheel_notches))),
            "--focus-click",
            cfg.focus_click,
            "--bbox",
            cfg.bbox,
            "--save-text",
            cfg.save_text,
            "--gui-events",
        ]
        if cfg.refresh:
            cmd.append("--refresh")
        if cfg.confirm_resubmit:
            cmd.append("--confirm-resubmit")
        if cfg.keep_awake:
            cmd.append("--keep-awake")
        if cfg.message_box:
            cmd.append("--message-box")
        if cfg.telegram_test_on_start and cfg.telegram_token and cfg.telegram_chat_id:
            cmd.append("--telegram-test")
        if cfg.seat_column:
            cmd.extend(["--seat-bbox", cfg.seat_bbox])
        if cfg.clipboard_assist:
            cmd.extend(["--clipboard-assist", "--auto-copy-clipboard"])
        return cmd

    def _read_process_output(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            self.log_lines.append(line)
            self._classify_line(line.rstrip())
        self._flush_pending_result()
        code = process.poll()
        self._emit("status", f"감시 프로세스가 종료되었습니다. code={code}")

    def _classify_line(self, line: str) -> None:
        if not line:
            return
        if line.startswith("ADSP_WATCHER_RESULT_JSON "):
            self._consume_json_event(line)
            return
        self._consume_result_line(line)

        kind = "log"
        if "잔여좌석 발견" in line:
            kind = "summary"
        elif line.startswith("No.") and "|" in line and "석" in line:
            kind = "hit"
        elif "팝업 OCR 확인" in line:
            kind = "check"
        elif "새로고침" in line:
            kind = "refresh"
        elif "Telegram" in line:
            kind = "telegram"
        self._emit(kind, line)

    def _consume_json_event(self, line: str) -> None:
        raw_payload = line.removeprefix("ADSP_WATCHER_RESULT_JSON ").strip()
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError as exc:
            self._emit("error", f"GUI 결과 이벤트 파싱 실패: {exc}")
            return
        if payload.get("type") != "seat_hits":
            return
        known = {
            (item.get("no"), item.get("seats"), item.get("site"), item.get("address"))
            for item in self.results
        }
        event_time = payload.get("time") or datetime.now().strftime("%H:%M:%S")
        added = 0
        for hit in payload.get("hits", []):
            item = self._result_from_hit_payload(hit, event_time)
            key = (item["no"], item["seats"], item["site"], item["address"])
            if key in known:
                continue
            known.add(key)
            self.results.append(item)
            added += 1
        self.results = self.results[-200:]
        self._emit("result", f"잔여좌석 결과 {added}건 반영")

    def _result_from_hit_payload(self, hit: dict, event_time: str) -> dict[str, str]:
        line = str(hit.get("line") or "")
        site = str(hit.get("site") or "").strip()
        address = str(hit.get("address") or "").strip()
        if not site and " - " in line:
            parts = [part.strip() for part in line.split(" - ")]
            if len(parts) >= 3:
                site = parts[2]
            if len(parts) >= 4:
                address = parts[3]
        return {
            "time": str(event_time).split()[-1],
            "no": "" if hit.get("no") is None else str(hit.get("no")),
            "region": str(hit.get("region") or ""),
            "seats": str(hit.get("seats") or ""),
            "site": site or line,
            "address": address,
        }
    def _consume_result_line(self, line: str) -> None:
        if line.startswith("DataQ 잔여좌석 발견") or line.startswith("ADsP 잔여좌석 발견"):
            self._flush_pending_result()
            return

        if line.startswith("No.") and "|" in line and "석" in line:
            self._flush_pending_result()
            parts = [part.strip() for part in line.split("|")]
            if len(parts) >= 3:
                self._pending_result = {
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "no": parts[0].replace("No.", "").strip(),
                    "region": parts[1],
                    "seats": parts[2].replace("석", "").strip(),
                    "site": "",
                    "address": "",
                }
            return

        if self._pending_result is None:
            return
        if not self._pending_result["site"]:
            self._pending_result["site"] = line
            return
        if not self._pending_result["address"]:
            self._pending_result["address"] = line
            self._flush_pending_result()

    def _flush_pending_result(self) -> None:
        if self._pending_result is None:
            return
        result = self._pending_result
        self._pending_result = None
        if not result.get("site"):
            return
        self.results.append(result)
        self.results = self.results[-200:]
        self._emit("result", f"No.{result['no']} {result['region']} {result['seats']}석")


    def _sync_results_from_log(self) -> None:
        text = "".join(self.log_lines)
        if not text:
            return
        pattern = re.compile(
            r"^No\.(?P<no>\d+)\s*\|\s*(?P<region>[^|]+)\|\s*(?P<seats>\d+)석\s*\n"
            r"(?P<site>[^\n]+)\n"
            r"(?P<address>[^\n]+)",
            re.MULTILINE,
        )
        known = {
            (item.get("no"), item.get("seats"), item.get("site"), item.get("address"))
            for item in self.results
        }
        for match in pattern.finditer(text):
            item = {
                "time": datetime.now().strftime("%H:%M:%S"),
                "no": match.group("no").strip(),
                "region": match.group("region").strip(),
                "seats": match.group("seats").strip(),
                "site": match.group("site").strip(),
                "address": match.group("address").strip(),
            }
            key = (item["no"], item["seats"], item["site"], item["address"])
            if key in known:
                continue
            known.add(key)
            self.results.append(item)
            self._emit("result", f"No.{item['no']} {item['region']} {item['seats']}석")
        self.results = self.results[-200:]
    def _emit(self, kind: str, message: str) -> None:
        self.events.put({"kind": kind, "message": message, "time": datetime.now().strftime("%H:%M:%S")})

    def _coerce_config(self, raw: dict) -> WatcherConfig:
        base = asdict(WatcherConfig())
        base.update(raw or {})
        for key in ("interval", "pages", "wheel_notches"):
            try:
                base[key] = int(base[key])
            except (TypeError, ValueError):
                base[key] = getattr(WatcherConfig(), key)
        return WatcherConfig(**base)


def main() -> int:
    if webview is None:
        print("pywebview가 설치되어 있지 않습니다. `python -m pip install -r requirements.txt`를 먼저 실행하세요.")
        return 1
    index = UI_DIR / "index.html"
    api = WatcherApi()
    webview.create_window(
        "DataQ Seat Watcher",
        str(index),
        js_api=api,
        width=1180,
        height=760,
        min_size=(980, 680),
        text_select=True,
    )
    webview.start(debug=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
