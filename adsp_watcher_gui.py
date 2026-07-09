from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk

from adsp_popup_ocr_watcher import DEFAULT_FOCUS_CLICK, DEFAULT_SEAT_BBOX, send_telegram
from adsp_seat_parser import TARGET_EXAM


APP_TITLE = "ADsP Seat Watcher"
DATAQ_ACCEPT_URL = "https://www.dataq.or.kr/www/accept/list.do"
DEFAULT_BBOX = "0,90,1845,980"
DEFAULT_INTERVAL = "40"
DEFAULT_PAGES = "15"
DEFAULT_WHEEL_NOTCHES = "9"
DEFAULT_SAVE_TEXT = "ocr_debug.txt"


class WatcherGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1040x760")
        self.minsize(980, 680)

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()

        self.interval_var = tk.StringVar(value=DEFAULT_INTERVAL)
        self.pages_var = tk.StringVar(value=DEFAULT_PAGES)
        self.wheel_notches_var = tk.StringVar(value=DEFAULT_WHEEL_NOTCHES)
        self.bbox_var = tk.StringVar(value=DEFAULT_BBOX)
        self.seat_bbox_var = tk.StringVar(value=DEFAULT_SEAT_BBOX)
        self.focus_click_var = tk.StringVar(value=DEFAULT_FOCUS_CLICK)
        self.save_text_var = tk.StringVar(value=DEFAULT_SAVE_TEXT)
        self.token_var = tk.StringVar(value=os.environ.get("TELEGRAM_BOT_TOKEN", ""))
        self.chat_id_var = tk.StringVar(value=os.environ.get("TELEGRAM_CHAT_ID", ""))

        self.refresh_var = tk.BooleanVar(value=True)
        self.confirm_resubmit_var = tk.BooleanVar(value=True)
        self.keep_awake_var = tk.BooleanVar(value=True)
        self.seat_column_var = tk.BooleanVar(value=True)
        self.telegram_test_on_start_var = tk.BooleanVar(value=False)
        self.message_box_var = tk.BooleanVar(value=False)

        self.status_var = tk.StringVar(value="대기 중")
        self.command_var = tk.StringVar(value="")

        self._build_ui()
        self._refresh_command_preview()
        self.after(150, self._drain_output_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(16, 14, 16, 10))
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text=APP_TITLE, font=("Segoe UI", 18, "bold"))
        title.grid(row=0, column=0, sticky="w")
        subtitle = ttk.Label(
            header,
            text=f"{TARGET_EXAM} | 사용자가 직접 열어둔 DataQ 고사장 팝업을 OCR로 감시",
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, textvariable=self.status_var).grid(row=0, column=1, sticky="e")

        controls = ttk.Frame(self, padding=(16, 0, 10, 16))
        controls.grid(row=1, column=0, sticky="nsew")
        controls.columnconfigure(0, weight=1)

        log_area = ttk.Frame(self, padding=(6, 0, 16, 16))
        log_area.grid(row=1, column=1, sticky="nsew")
        log_area.rowconfigure(1, weight=1)
        log_area.columnconfigure(0, weight=1)

        self._build_controls(controls)
        self._build_log_area(log_area)

    def _build_controls(self, parent: ttk.Frame) -> None:
        guide = ttk.LabelFrame(parent, text="준비", padding=10)
        guide.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        guide.columnconfigure(0, weight=1)
        ttk.Label(
            guide,
            text="1. 일반 Chrome에서 DataQ 접수 화면에 직접 로그인\n"
            "2. ADsP 고사장 목록 팝업을 열고 맨 앞으로 배치\n"
            "3. Telegram 테스트 후 시작",
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(guide, text="DataQ 열기", command=lambda: webbrowser.open(DATAQ_ACCEPT_URL)).grid(
            row=0, column=1, padx=(10, 0), sticky="e"
        )

        telegram = ttk.LabelFrame(parent, text="Telegram", padding=10)
        telegram.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        telegram.columnconfigure(1, weight=1)
        ttk.Label(telegram, text="Bot token").grid(row=0, column=0, sticky="w", pady=3)
        token_entry = ttk.Entry(telegram, textvariable=self.token_var, show="*")
        token_entry.grid(row=0, column=1, sticky="ew", pady=3)
        ttk.Label(telegram, text="Chat ID").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(telegram, textvariable=self.chat_id_var).grid(row=1, column=1, sticky="ew", pady=3)
        ttk.Button(telegram, text="테스트 전송", command=self._test_telegram).grid(
            row=2, column=1, sticky="e", pady=(8, 0)
        )

        options = ttk.LabelFrame(parent, text="감시 설정", padding=10)
        options.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        for idx in range(2):
            options.columnconfigure(idx * 2 + 1, weight=1)

        self._entry_row(options, 0, "주기(초)", self.interval_var, "스캔 후 대기")
        self._entry_row(options, 1, "스캔 화면 수", self.pages_var, "긴 목록 페이지 수")
        self._entry_row(options, 2, "휠 칸 수", self.wheel_notches_var, "한 번에 내릴 양")
        self._entry_row(options, 3, "OCR 영역", self.bbox_var, "left,top,right,bottom")
        self._entry_row(options, 4, "좌석 열 영역", self.seat_bbox_var, "잔여좌석 열")
        self._entry_row(options, 5, "포커스 클릭", self.focus_click_var, "x,y")
        self._entry_row(options, 6, "OCR 저장", self.save_text_var, "디버그 텍스트")

        checks = ttk.LabelFrame(parent, text="동작", padding=10)
        checks.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        ttk.Checkbutton(checks, text="새로고침", variable=self.refresh_var, command=self._refresh_command_preview).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Checkbutton(
            checks,
            text="양식 재제출 확인 처리",
            variable=self.confirm_resubmit_var,
            command=self._refresh_command_preview,
        ).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(checks, text="절전 방지", variable=self.keep_awake_var, command=self._refresh_command_preview).grid(
            row=2, column=0, sticky="w"
        )
        ttk.Checkbutton(
            checks,
            text="잔여좌석 열 보조 OCR",
            variable=self.seat_column_var,
            command=self._refresh_command_preview,
        ).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(
            checks,
            text="시작 시 Telegram 테스트",
            variable=self.telegram_test_on_start_var,
            command=self._refresh_command_preview,
        ).grid(row=4, column=0, sticky="w")
        ttk.Checkbutton(
            checks,
            text="Windows 메시지박스",
            variable=self.message_box_var,
            command=self._refresh_command_preview,
        ).grid(row=5, column=0, sticky="w")

        actions = ttk.Frame(parent)
        actions.grid(row=4, column=0, sticky="ew")
        actions.columnconfigure((0, 1), weight=1)
        self.start_button = ttk.Button(actions, text="시작", command=self._start_watcher)
        self.start_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.stop_button = ttk.Button(actions, text="중지", command=self._stop_watcher, state="disabled")
        self.stop_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        ttk.Button(actions, text="명령 복사", command=self._copy_command).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

    def _build_log_area(self, parent: ttk.Frame) -> None:
        command_frame = ttk.LabelFrame(parent, text="실행 명령", padding=8)
        command_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        command_frame.columnconfigure(0, weight=1)
        command_entry = ttk.Entry(command_frame, textvariable=self.command_var, state="readonly")
        command_entry.grid(row=0, column=0, sticky="ew")

        output_frame = ttk.LabelFrame(parent, text="로그", padding=8)
        output_frame.grid(row=1, column=0, sticky="nsew")
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)
        self.output_text = tk.Text(output_frame, wrap="word", height=24, font=("Consolas", 10))
        self.output_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(output_frame, orient="vertical", command=self.output_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.output_text.configure(yscrollcommand=scrollbar.set)

    def _entry_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, hint: str) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=3)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=3)
        ttk.Label(parent, text=hint).grid(row=row, column=2, sticky="w", pady=3)
        variable.trace_add("write", lambda *_args: self._refresh_command_preview())

    def _build_command(self) -> list[str]:
        cmd = [
            sys.executable,
            "adsp_popup_ocr_watcher.py",
            "--interval",
            self.interval_var.get().strip() or DEFAULT_INTERVAL,
            "--pages",
            self.pages_var.get().strip() or DEFAULT_PAGES,
            "--scroll-method",
            "wheel",
            "--wheel-notches",
            self.wheel_notches_var.get().strip() or DEFAULT_WHEEL_NOTCHES,
            "--focus-click",
            self.focus_click_var.get().strip() or DEFAULT_FOCUS_CLICK,
            "--bbox",
            self.bbox_var.get().strip() or DEFAULT_BBOX,
            "--save-text",
            self.save_text_var.get().strip() or DEFAULT_SAVE_TEXT,
        ]
        if self.refresh_var.get():
            cmd.append("--refresh")
        if self.confirm_resubmit_var.get():
            cmd.append("--confirm-resubmit")
        if self.keep_awake_var.get():
            cmd.append("--keep-awake")
        if self.telegram_test_on_start_var.get():
            cmd.append("--telegram-test")
        if self.message_box_var.get():
            cmd.append("--message-box")
        if self.seat_column_var.get():
            cmd.extend(["--seat-bbox", self.seat_bbox_var.get().strip() or DEFAULT_SEAT_BBOX])
        else:
            cmd.append("--disable-seat-column-check")
        return cmd

    def _refresh_command_preview(self) -> None:
        cmd = self._build_command()
        display = " ".join(f'"{part}"' if " " in part else part for part in cmd)
        self.command_var.set(display)

    def _append_output(self, text: str) -> None:
        self.output_text.insert("end", text)
        self.output_text.see("end")

    def _test_telegram(self) -> None:
        token = self.token_var.get().strip()
        chat_id = self.chat_id_var.get().strip()
        if not token or not chat_id:
            messagebox.showwarning("Telegram", "Bot token과 Chat ID를 입력하세요.")
            return

        def worker() -> None:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            ok = send_telegram(token, chat_id, f"ADsP watcher GUI test\n시간: {now}")
            self.output_queue.put("Telegram 테스트 전송 완료\n" if ok else "Telegram 테스트 전송 실패\n")

        threading.Thread(target=worker, daemon=True).start()

    def _start_watcher(self) -> None:
        if self.process and self.process.poll() is None:
            return

        token = self.token_var.get().strip()
        chat_id = self.chat_id_var.get().strip()
        if not token or not chat_id:
            if not messagebox.askyesno("Telegram 미설정", "Telegram 없이 실행할까요?"):
                return

        self._refresh_command_preview()
        env = os.environ.copy()
        if token:
            env["TELEGRAM_BOT_TOKEN"] = token
        if chat_id:
            env["TELEGRAM_CHAT_ID"] = chat_id

        cmd = self._build_command()
        self.output_text.delete("1.0", "end")
        self._append_output("실행 시작\n")
        self._append_output(self.command_var.get() + "\n\n")

        self.process = subprocess.Popen(
            cmd,
            cwd=Path(__file__).resolve().parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        self.status_var.set("실행 중")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        threading.Thread(target=self._read_process_output, daemon=True).start()

    def _read_process_output(self) -> None:
        assert self.process is not None
        assert self.process.stdout is not None
        for line in self.process.stdout:
            self.output_queue.put(line)
        code = self.process.wait()
        self.output_queue.put(f"\n프로세스 종료: {code}\n")
        self.output_queue.put("__PROCESS_EXIT__")

    def _stop_watcher(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        self.status_var.set("중지 중")
        self.process.terminate()

    def _drain_output_queue(self) -> None:
        try:
            while True:
                item = self.output_queue.get_nowait()
                if item == "__PROCESS_EXIT__":
                    self.status_var.set("대기 중")
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                else:
                    self._append_output(item)
        except queue.Empty:
            pass
        self.after(150, self._drain_output_queue)

    def _copy_command(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.command_var.get())
        self.status_var.set("명령 복사됨")

    def _on_close(self) -> None:
        if self.process and self.process.poll() is None:
            if not messagebox.askyesno("종료", "감시가 실행 중입니다. 중지하고 종료할까요?"):
                return
            self.process.terminate()
        self.destroy()


def main() -> int:
    app = WatcherGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
