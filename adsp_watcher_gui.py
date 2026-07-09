from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from dataclasses import dataclass
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

BG = "#f7f9fc"
SURFACE = "#ffffff"
TEXT = "#191f28"
MUTED = "#6b7684"
LINE = "#e5e8eb"
BLUE = "#3182f6"
BLUE_DARK = "#1b64da"
GREEN = "#00a878"
RED = "#e03131"


@dataclass
class FieldSpec:
    label: str
    variable: tk.StringVar
    helper: str
    secret: bool = False


class WatcherGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1120x760")
        self.minsize(1040, 700)
        self.configure(bg=BG)

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
        self.telegram_status_var = tk.StringVar(value="Telegram 미확인")
        self.command_var = tk.StringVar(value="")

        self._configure_style()
        self._build_ui()
        self._refresh_command_preview()
        self._refresh_summary()
        self.after(150, self._drain_output_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background=BG, foreground=TEXT)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=SURFACE)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Card.TLabel", background=SURFACE, foreground=TEXT)
        style.configure("CardMuted.TLabel", background=SURFACE, foreground=MUTED)
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"), background=BG, foreground=TEXT)
        style.configure("Section.TLabel", font=("Segoe UI", 13, "bold"), background=SURFACE, foreground=TEXT)
        style.configure("Primary.TButton", padding=(18, 10), background=BLUE, foreground="#ffffff", borderwidth=0)
        style.map("Primary.TButton", background=[("active", BLUE_DARK), ("disabled", "#b0c8f8")])
        style.configure("Secondary.TButton", padding=(16, 9), background="#eef4ff", foreground=BLUE, borderwidth=0)
        style.map("Secondary.TButton", background=[("active", "#dcebff")])
        style.configure("Danger.TButton", padding=(16, 9), background="#fff0f0", foreground=RED, borderwidth=0)
        style.configure("TEntry", padding=(10, 7), bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
        style.configure("TCheckbutton", background=SURFACE, foreground=TEXT)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        shell = ttk.Frame(self, padding=24)
        shell.grid(row=0, column=0, rowspan=2, sticky="nsew")
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(2, weight=1)

        hero = ttk.Frame(shell)
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        hero.columnconfigure(0, weight=1)
        ttk.Label(hero, text="ADsP Seat Watcher", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            hero,
            text="수동으로 열어둔 DataQ 고사장 팝업을 OCR로 읽고, 잔여좌석 가능성을 Telegram으로 알려줍니다.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        self.status_badge = tk.Label(
            hero,
            textvariable=self.status_var,
            bg="#eef4ff",
            fg=BLUE,
            padx=16,
            pady=8,
            font=("Segoe UI", 10, "bold"),
        )
        self.status_badge.grid(row=0, column=1, sticky="e")

        cards = ttk.Frame(shell)
        cards.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        for col in range(3):
            cards.columnconfigure(col, weight=1)
        self.telegram_card_value = tk.StringVar()
        self.scan_card_value = tk.StringVar()
        self.ocr_card_value = tk.StringVar()
        self._summary_card(cards, 0, "알림", self.telegram_card_value, "Telegram 테스트 후 실행")
        self._summary_card(cards, 1, "스캔", self.scan_card_value, "주기와 목록 범위")
        self._summary_card(cards, 2, "OCR", self.ocr_card_value, "화면 영역과 좌석 열")

        body = ttk.Frame(shell)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        left = self._card(body, padding=18)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, 18))
        left.columnconfigure(0, weight=1)
        self._build_action_panel(left)

        right = self._card(body, padding=16)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        self._build_log_panel(right)

    def _card(self, parent: tk.Widget, padding: int = 14) -> ttk.Frame:
        return ttk.Frame(parent, style="Card.TFrame", padding=padding)

    def _summary_card(self, parent: ttk.Frame, column: int, title: str, value: tk.StringVar, helper: str) -> None:
        card = self._card(parent, padding=16)
        card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0 if column == 2 else 8))
        ttk.Label(card, text=title, style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, textvariable=value, style="Section.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Label(card, text=helper, style="CardMuted.TLabel").grid(row=2, column=0, sticky="w", pady=(6, 0))

    def _build_action_panel(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="실행 준비", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(parent, text="설정은 단계별 창에서 하나씩 조정합니다.", style="CardMuted.TLabel", wraplength=280).grid(row=1, column=0, sticky="w", pady=(6, 18))
        ttk.Button(parent, text="초기 설정", style="Secondary.TButton", command=self._open_setup_wizard).grid(row=2, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(parent, text="DataQ 열기", style="Secondary.TButton", command=lambda: webbrowser.open(DATAQ_ACCEPT_URL)).grid(row=3, column=0, sticky="ew", pady=(0, 10))
        ttk.Button(parent, text="Telegram 테스트", style="Secondary.TButton", command=self._test_telegram).grid(row=4, column=0, sticky="ew", pady=(0, 18))
        self.start_button = ttk.Button(parent, text="감시 시작", style="Primary.TButton", command=self._start_watcher)
        self.start_button.grid(row=5, column=0, sticky="ew", pady=(0, 10))
        self.stop_button = ttk.Button(parent, text="중지", style="Danger.TButton", command=self._stop_watcher, state="disabled")
        self.stop_button.grid(row=6, column=0, sticky="ew", pady=(0, 20))
        ttk.Label(parent, text="정책 경계", style="Section.TLabel").grid(row=7, column=0, sticky="w", pady=(8, 6))
        ttk.Label(parent, text="자동 로그인, 자동 접수, 자동 결제, 캡차 우회, 감지 우회는 수행하지 않습니다.", style="CardMuted.TLabel", wraplength=280).grid(row=8, column=0, sticky="w")

    def _build_log_panel(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="Card.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="실시간 로그", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="명령 복사", style="Secondary.TButton", command=self._copy_command).grid(row=0, column=1, sticky="e")
        ttk.Entry(parent, textvariable=self.command_var, state="readonly").grid(row=1, column=0, sticky="ew", pady=(12, 12))
        text_frame = ttk.Frame(parent, style="Card.TFrame")
        text_frame.grid(row=2, column=0, sticky="nsew")
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)
        self.output_text = tk.Text(text_frame, wrap="word", height=24, font=("Consolas", 10), bg="#111827", fg="#e5e7eb", insertbackground="#e5e7eb", relief="flat", padx=14, pady=14)
        self.output_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=self.output_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.output_text.configure(yscrollcommand=scrollbar.set)

    def _refresh_summary(self) -> None:
        self.telegram_card_value.set("설정됨" if self.token_var.get().strip() and self.chat_id_var.get().strip() else "미설정")
        self.scan_card_value.set(f"{self.interval_var.get().strip() or DEFAULT_INTERVAL}초 / {self.pages_var.get().strip() or DEFAULT_PAGES}화면")
        seat = "보조 OCR 켬" if self.seat_column_var.get() else "보조 OCR 끔"
        self.ocr_card_value.set(f"{self.bbox_var.get().strip() or DEFAULT_BBOX} | {seat}")

    def _open_setup_wizard(self) -> None:
        self._open_step(0)

    def _open_step(self, index: int) -> None:
        steps = [
            ("Telegram 알림", "휴대폰으로 받을 Bot token과 Chat ID를 입력합니다.", self._telegram_step),
            ("화면 준비", "DataQ 팝업을 열고 앞으로 배치한 뒤 포커스 좌표를 확인합니다.", self._browser_step),
            ("OCR 영역", "표 전체와 잔여좌석 열을 읽을 화면 영역을 설정합니다.", self._ocr_step),
            ("감시 동작", "새로고침, 주기, 스크롤, 절전 방지 옵션을 정합니다.", self._behavior_step),
        ]
        if index >= len(steps):
            self._refresh_all()
            messagebox.showinfo("설정 완료", "초기 설정이 완료되었습니다. 이제 감시를 시작할 수 있습니다.")
            return
        title, subtitle, builder = steps[index]
        window = tk.Toplevel(self)
        window.title(f"{APP_TITLE} - {title}")
        window.geometry("560x520")
        window.configure(bg=BG)
        window.transient(self)
        window.grab_set()
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        header = ttk.Frame(window, padding=(24, 22, 24, 12))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text=f"{index + 1}/4", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=title, font=("Segoe UI", 20, "bold"), background=BG, foreground=TEXT).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, text=subtitle, style="Muted.TLabel", wraplength=500).grid(row=2, column=0, sticky="w", pady=(8, 0))
        content = self._card(window, padding=22)
        content.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        content.columnconfigure(0, weight=1)
        builder(content)
        footer = ttk.Frame(window, padding=(24, 0, 24, 22))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)
        if index > 0:
            ttk.Button(footer, text="이전", style="Secondary.TButton", command=lambda: self._go_step(window, index - 1)).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="다음" if index < len(steps) - 1 else "완료", style="Primary.TButton", command=lambda: self._go_step(window, index + 1)).grid(row=0, column=2, sticky="e")

    def _go_step(self, window: tk.Toplevel, index: int) -> None:
        self._refresh_all()
        window.grab_release()
        window.destroy()
        self.after(80, lambda: self._open_step(index))

    def _telegram_step(self, parent: ttk.Frame) -> None:
        self._field(parent, 0, FieldSpec("Bot token", self.token_var, "BotFather에서 받은 토큰입니다. 파일에 저장하지 않습니다.", True))
        self._field(parent, 1, FieldSpec("Chat ID", self.chat_id_var, "getUpdates 결과의 chat.id 숫자입니다."))
        ttk.Button(parent, text="테스트 전송", style="Secondary.TButton", command=self._test_telegram).grid(row=2, column=0, sticky="e", pady=(18, 0))

    def _browser_step(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="1. DataQ 접수 화면을 열고 직접 로그인합니다.", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Label(parent, text="2. ADsP 고사장 목록 팝업을 열고 화면 맨 앞으로 둡니다.", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Label(parent, text="3. 새로고침 후 스크롤 포커스를 받을 본문 좌표를 둡니다.", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Button(parent, text="DataQ 접수 화면 열기", style="Secondary.TButton", command=lambda: webbrowser.open(DATAQ_ACCEPT_URL)).grid(row=3, column=0, sticky="ew", pady=(20, 18))
        self._field(parent, 4, FieldSpec("포커스 클릭 좌표", self.focus_click_var, "기본값 900,500. 팝업 본문 중앙 근처가 좋습니다."))

    def _ocr_step(self, parent: ttk.Frame) -> None:
        self._field(parent, 0, FieldSpec("전체 OCR 영역", self.bbox_var, "팝업 표 전체 영역입니다. 예: 0,90,1845,980"))
        self._field(parent, 1, FieldSpec("잔여좌석 열 영역", self.seat_bbox_var, "좌석 숫자 열만 좁게 잡습니다. 예: 1535,90,1645,980"))
        ttk.Checkbutton(parent, text="잔여좌석 열 보조 OCR 사용", variable=self.seat_column_var, command=self._refresh_all).grid(row=2, column=0, sticky="w", pady=(12, 0))
        self._field(parent, 3, FieldSpec("OCR 원문 저장 파일", self.save_text_var, "디버깅용 텍스트 파일명입니다. git에는 포함하지 않습니다."))

    def _behavior_step(self, parent: ttk.Frame) -> None:
        self._field(parent, 0, FieldSpec("확인 주기(초)", self.interval_var, "한 사이클 후 대기 시간입니다. 권장: 40"))
        self._field(parent, 1, FieldSpec("스캔 화면 수", self.pages_var, "목록을 훑을 화면 수입니다. 권장: 15"))
        self._field(parent, 2, FieldSpec("휠 칸 수", self.wheel_notches_var, "한 번에 내릴 스크롤 양입니다. 권장: 9"))
        checks = ttk.Frame(parent, style="Card.TFrame")
        checks.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        for row, (label, var) in enumerate([("새로고침 사용", self.refresh_var), ("양식 다시 제출 확인 처리", self.confirm_resubmit_var), ("절전 방지", self.keep_awake_var), ("시작 시 Telegram 테스트", self.telegram_test_on_start_var), ("Windows 메시지박스 사용", self.message_box_var)]):
            ttk.Checkbutton(checks, text=label, variable=var, command=self._refresh_all).grid(row=row, column=0, sticky="w", pady=3)

    def _field(self, parent: ttk.Frame, row: int, spec: FieldSpec) -> None:
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=spec.label, style="Card.TLabel", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=spec.variable, show="*" if spec.secret else "").grid(row=1, column=0, sticky="ew", pady=(6, 4))
        ttk.Label(frame, text=spec.helper, style="CardMuted.TLabel", wraplength=480).grid(row=2, column=0, sticky="w")
        spec.variable.trace_add("write", lambda *_args: self._refresh_all())

    def _refresh_all(self) -> None:
        self._refresh_command_preview()
        self._refresh_summary()

    def _build_command(self) -> list[str]:
        cmd = [sys.executable, "adsp_popup_ocr_watcher.py", "--interval", self.interval_var.get().strip() or DEFAULT_INTERVAL, "--pages", self.pages_var.get().strip() or DEFAULT_PAGES, "--scroll-method", "wheel", "--wheel-notches", self.wheel_notches_var.get().strip() or DEFAULT_WHEEL_NOTCHES, "--focus-click", self.focus_click_var.get().strip() or DEFAULT_FOCUS_CLICK, "--bbox", self.bbox_var.get().strip() or DEFAULT_BBOX, "--save-text", self.save_text_var.get().strip() or DEFAULT_SAVE_TEXT]
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
        self.telegram_status_var.set("전송 중")

        def worker() -> None:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            ok = send_telegram(token, chat_id, f"ADsP watcher GUI test\n시간: {now}")
            self.telegram_status_var.set("테스트 성공" if ok else "테스트 실패")
            self.output_queue.put("Telegram 테스트 전송 완료\n" if ok else "Telegram 테스트 전송 실패\n")
            self.output_queue.put("__SUMMARY_REFRESH__")

        threading.Thread(target=worker, daemon=True).start()

    def _start_watcher(self) -> None:
        if self.process and self.process.poll() is None:
            return
        token = self.token_var.get().strip()
        chat_id = self.chat_id_var.get().strip()
        if not token or not chat_id:
            if not messagebox.askyesno("Telegram 미설정", "Telegram 없이 실행할까요?"):
                return
        self._refresh_all()
        env = os.environ.copy()
        if token:
            env["TELEGRAM_BOT_TOKEN"] = token
        if chat_id:
            env["TELEGRAM_CHAT_ID"] = chat_id
        cmd = self._build_command()
        self.output_text.delete("1.0", "end")
        self._append_output("실행 시작\n")
        self._append_output(self.command_var.get() + "\n\n")
        self.process = subprocess.Popen(cmd, cwd=Path(__file__).resolve().parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env)
        self.status_var.set("실행 중")
        self.status_badge.configure(bg="#e6f8f1", fg=GREEN)
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
                    self.status_badge.configure(bg="#eef4ff", fg=BLUE)
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                elif item == "__SUMMARY_REFRESH__":
                    self._refresh_summary()
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
