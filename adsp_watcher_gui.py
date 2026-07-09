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
ACCENT = "#0052FF"


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
        self.geometry("1180x780")
        self.minsize(1080, 720)

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.event_buckets: list[int] = [0] * 24
        self.scan_count = 0
        self.hit_count = 0
        self.telegram_count = 0

        self.interval_var = tk.StringVar(value=DEFAULT_INTERVAL)
        self.pages_var = tk.StringVar(value=DEFAULT_PAGES)
        self.wheel_notches_var = tk.StringVar(value=DEFAULT_WHEEL_NOTCHES)
        self.bbox_var = tk.StringVar(value=DEFAULT_BBOX)
        self.seat_bbox_var = tk.StringVar(value=DEFAULT_SEAT_BBOX)
        self.focus_click_var = tk.StringVar(value=DEFAULT_FOCUS_CLICK)
        self.save_text_var = tk.StringVar(value=DEFAULT_SAVE_TEXT)
        self.token_var = tk.StringVar(value=os.environ.get("TELEGRAM_BOT_TOKEN", ""))
        self.chat_id_var = tk.StringVar(value=os.environ.get("TELEGRAM_CHAT_ID", ""))
        self.period_var = tk.StringVar(value="현재 세션")

        self.refresh_var = tk.BooleanVar(value=True)
        self.confirm_resubmit_var = tk.BooleanVar(value=True)
        self.keep_awake_var = tk.BooleanVar(value=True)
        self.seat_column_var = tk.BooleanVar(value=True)
        self.telegram_test_on_start_var = tk.BooleanVar(value=False)
        self.message_box_var = tk.BooleanVar(value=False)
        self.dark_mode_var = tk.BooleanVar(value=True)

        self.status_var = tk.StringVar(value="대기 중")
        self.telegram_status_var = tk.StringVar(value="미확인")
        self.command_var = tk.StringVar(value="")
        self.scan_metric_var = tk.StringVar(value="0")
        self.hit_metric_var = tk.StringVar(value="0")
        self.telegram_metric_var = tk.StringVar(value="0")
        self.summary_var = tk.StringVar(value="초기 설정을 완료하고 감시를 시작하세요.")

        self.palette: dict[str, str] = {}
        self._apply_palette()
        self._configure_style()
        self._build_ui()
        self._refresh_command_preview()
        self._refresh_summary()
        self.after(150, self._drain_output_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_palette(self) -> None:
        if self.dark_mode_var.get():
            self.palette = {
                "bg": "#0B1020",
                "sidebar": "#080D1A",
                "surface": "#121A2B",
                "surface2": "#172033",
                "text": "#F8FAFC",
                "muted": "#94A3B8",
                "line": "#243044",
                "log_bg": "#050816",
                "good": "#2DD4BF",
                "danger": "#FB7185",
            }
        else:
            self.palette = {
                "bg": "#F7F9FC",
                "sidebar": "#FFFFFF",
                "surface": "#FFFFFF",
                "surface2": "#F2F6FF",
                "text": "#191F28",
                "muted": "#6B7684",
                "line": "#E5E8EB",
                "log_bg": "#111827",
                "good": "#00A878",
                "danger": "#E03131",
            }

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        p = self.palette
        style.configure(".", font=("Pretendard", 10), background=p["bg"], foreground=p["text"])
        style.configure("Root.TFrame", background=p["bg"])
        style.configure("Sidebar.TFrame", background=p["sidebar"])
        style.configure("Card.TFrame", background=p["surface"])
        style.configure("Soft.TFrame", background=p["surface2"])
        style.configure("TLabel", background=p["bg"], foreground=p["text"])
        style.configure("Muted.TLabel", background=p["bg"], foreground=p["muted"])
        style.configure("Side.TLabel", background=p["sidebar"], foreground=p["text"])
        style.configure("SideMuted.TLabel", background=p["sidebar"], foreground=p["muted"])
        style.configure("Card.TLabel", background=p["surface"], foreground=p["text"])
        style.configure("CardMuted.TLabel", background=p["surface"], foreground=p["muted"])
        style.configure("Soft.TLabel", background=p["surface2"], foreground=p["text"])
        style.configure("Title.TLabel", font=("Pretendard", 24, "bold"), background=p["bg"], foreground=p["text"])
        style.configure("Section.TLabel", font=("Pretendard", 13, "bold"), background=p["surface"], foreground=p["text"])
        style.configure("Metric.TLabel", font=("Pretendard", 26, "bold"), background=p["surface"], foreground=p["text"])
        style.configure("Primary.TButton", padding=(18, 10), background=ACCENT, foreground="#FFFFFF", borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#0042CC"), ("disabled", "#809EF5")])
        style.configure("Secondary.TButton", padding=(16, 9), background=p["surface2"], foreground=ACCENT, borderwidth=0)
        style.configure("Ghost.TButton", padding=(14, 8), background=p["sidebar"], foreground=p["muted"], borderwidth=0)
        style.configure("Danger.TButton", padding=(16, 9), background=p["surface2"], foreground=p["danger"], borderwidth=0)
        style.configure("TEntry", padding=(10, 7), fieldbackground=p["surface2"], foreground=p["text"], bordercolor=p["line"], lightcolor=p["line"], darkcolor=p["line"])
        style.configure("TCombobox", padding=(8, 7), fieldbackground=p["surface2"], foreground=p["text"], bordercolor=p["line"])
        style.configure("TCheckbutton", background=p["surface"], foreground=p["text"])

    def _build_ui(self) -> None:
        self.configure(bg=self.palette["bg"])
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = ttk.Frame(self, style="Sidebar.TFrame", padding=(18, 22))
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.rowconfigure(8, weight=1)
        self._build_sidebar(self.sidebar)

        self.main = ttk.Frame(self, style="Root.TFrame", padding=(24, 20, 24, 24))
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(3, weight=1)
        self._build_topbar(self.main)
        self._build_kpis(self.main)
        self._build_chart(self.main)
        self._build_bottom(self.main)

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="ADsP", style="Side.TLabel", font=("Pretendard", 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(parent, text="Seat Watcher", style="SideMuted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 22))
        for row, label in enumerate(["Dashboard", "Setup", "Telegram", "OCR", "Logs"], start=2):
            command = self._open_setup_wizard if label in {"Setup", "Telegram", "OCR"} else None
            ttk.Button(parent, text=label, style="Ghost.TButton", command=command).grid(row=row, column=0, sticky="ew", pady=3)
        ttk.Checkbutton(parent, text="Dark mode", variable=self.dark_mode_var, command=self._toggle_theme).grid(row=9, column=0, sticky="w", pady=(20, 8))
        ttk.Label(parent, text="No auto login\nNo auto payment\nNo captcha bypass", style="SideMuted.TLabel", justify="left").grid(row=10, column=0, sticky="w", pady=(8, 0))

    def _build_topbar(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent, style="Root.TFrame")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        top.columnconfigure(0, weight=1)
        ttk.Label(top, text="Monitoring Dashboard", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top, text=f"{TARGET_EXAM} | DataQ popup OCR assistant", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        filters = ttk.Frame(top, style="Root.TFrame")
        filters.grid(row=0, column=1, rowspan=2, sticky="e")
        ttk.Label(filters, text="기간", style="Muted.TLabel").grid(row=0, column=0, sticky="e", padx=(0, 8))
        ttk.Combobox(filters, textvariable=self.period_var, values=["현재 세션", "최근 1시간", "오늘"], width=12, state="readonly").grid(row=0, column=1, padx=(0, 10))
        self.status_badge = tk.Label(filters, textvariable=self.status_var, bg="#102A5C", fg="#B9D2FF", padx=14, pady=8, font=("Pretendard", 10, "bold"))
        self.status_badge.grid(row=0, column=2)

    def _build_kpis(self, parent: ttk.Frame) -> None:
        kpis = ttk.Frame(parent, style="Root.TFrame")
        kpis.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        for col in range(3):
            kpis.columnconfigure(col, weight=1)
        self._metric_card(kpis, 0, "OCR scans", self.scan_metric_var, "팝업 스캔 누적")
        self._metric_card(kpis, 1, "Seat signals", self.hit_metric_var, "잔여좌석 후보 감지")
        self._metric_card(kpis, 2, "Telegram sent", self.telegram_metric_var, "휴대폰 알림 전송")

    def _metric_card(self, parent: ttk.Frame, col: int, title: str, value: tk.StringVar, helper: str) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=18)
        card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0 if col == 2 else 8))
        ttk.Label(card, text=title, style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, textvariable=value, style="Metric.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 2))
        ttk.Label(card, text=helper, style="CardMuted.TLabel").grid(row=2, column=0, sticky="w")

    def _build_chart(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=18)
        panel.grid(row=2, column=0, sticky="ew", pady=(0, 18))
        panel.columnconfigure(0, weight=1)
        header = ttk.Frame(panel, style="Card.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="실시간 감지 트래픽", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.summary_var, style="CardMuted.TLabel").grid(row=0, column=1, sticky="e")
        self.chart = tk.Canvas(panel, height=170, bg=self.palette["surface"], highlightthickness=0)
        self.chart.grid(row=1, column=0, sticky="ew")
        self.chart.bind("<Configure>", lambda _event: self._draw_chart())

    def _build_bottom(self, parent: ttk.Frame) -> None:
        bottom = ttk.Frame(parent, style="Root.TFrame")
        bottom.grid(row=3, column=0, sticky="nsew")
        bottom.columnconfigure(0, weight=0)
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(0, weight=1)

        actions = ttk.Frame(bottom, style="Card.TFrame", padding=18)
        actions.grid(row=0, column=0, sticky="nsw", padx=(0, 18))
        ttk.Label(actions, text="Quick actions", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 12))
        ttk.Button(actions, text="초기 설정", style="Secondary.TButton", command=self._open_setup_wizard).grid(row=1, column=0, sticky="ew", pady=5)
        ttk.Button(actions, text="DataQ 열기", style="Secondary.TButton", command=lambda: webbrowser.open(DATAQ_ACCEPT_URL)).grid(row=2, column=0, sticky="ew", pady=5)
        ttk.Button(actions, text="Telegram 테스트", style="Secondary.TButton", command=self._test_telegram).grid(row=3, column=0, sticky="ew", pady=5)
        self.start_button = ttk.Button(actions, text="감시 시작", style="Primary.TButton", command=self._start_watcher)
        self.start_button.grid(row=4, column=0, sticky="ew", pady=(18, 5))
        self.stop_button = ttk.Button(actions, text="중지", style="Danger.TButton", command=self._stop_watcher, state="disabled")
        self.stop_button.grid(row=5, column=0, sticky="ew", pady=5)
        ttk.Label(actions, text="자동 접수/결제 없음", style="CardMuted.TLabel").grid(row=6, column=0, sticky="w", pady=(18, 0))

        logs = ttk.Frame(bottom, style="Card.TFrame", padding=18)
        logs.grid(row=0, column=1, sticky="nsew")
        logs.columnconfigure(0, weight=1)
        logs.rowconfigure(2, weight=1)
        log_header = ttk.Frame(logs, style="Card.TFrame")
        log_header.grid(row=0, column=0, sticky="ew")
        log_header.columnconfigure(0, weight=1)
        ttk.Label(log_header, text="실시간 로그", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(log_header, text="명령 복사", style="Secondary.TButton", command=self._copy_command).grid(row=0, column=1, sticky="e")
        ttk.Entry(logs, textvariable=self.command_var, state="readonly").grid(row=1, column=0, sticky="ew", pady=(12, 12))
        self.output_text = tk.Text(logs, wrap="word", height=14, font=("Consolas", 10), bg=self.palette["log_bg"], fg="#E5E7EB", insertbackground="#E5E7EB", relief="flat", padx=14, pady=14)
        self.output_text.grid(row=2, column=0, sticky="nsew")

    def _toggle_theme(self) -> None:
        self._apply_palette()
        self._configure_style()
        for child in self.winfo_children():
            child.destroy()
        self._build_ui()
        self._refresh_all()
        self._draw_chart()

    def _refresh_summary(self) -> None:
        self.scan_metric_var.set(str(self.scan_count))
        self.hit_metric_var.set(str(self.hit_count))
        self.telegram_metric_var.set(str(self.telegram_count))
        telegram = "Telegram 설정됨" if self.token_var.get().strip() and self.chat_id_var.get().strip() else "Telegram 미설정"
        self.summary_var.set(f"{telegram} | {self.interval_var.get().strip() or DEFAULT_INTERVAL}초 주기 | {self.pages_var.get().strip() or DEFAULT_PAGES}화면")

    def _open_setup_wizard(self) -> None:
        self._open_step(0)

    def _open_step(self, index: int) -> None:
        steps = [("Telegram 알림", "휴대폰으로 받을 Bot token과 Chat ID를 입력합니다.", self._telegram_step), ("화면 준비", "DataQ 팝업을 열고 앞으로 배치한 뒤 포커스 좌표를 확인합니다.", self._browser_step), ("OCR 영역", "표 전체와 잔여좌석 열을 읽을 화면 영역을 설정합니다.", self._ocr_step), ("감시 동작", "새로고침, 주기, 스크롤, 절전 방지 옵션을 정합니다.", self._behavior_step)]
        if index >= len(steps):
            self._refresh_all()
            messagebox.showinfo("설정 완료", "초기 설정이 완료되었습니다. 이제 감시를 시작할 수 있습니다.")
            return
        title, subtitle, builder = steps[index]
        window = tk.Toplevel(self)
        window.title(f"{APP_TITLE} - {title}")
        window.geometry("560x520")
        window.configure(bg=self.palette["bg"])
        window.transient(self)
        window.grab_set()
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        header = ttk.Frame(window, padding=(24, 22, 24, 12))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text=f"{index + 1}/4", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=title, font=("Pretendard", 20, "bold"), background=self.palette["bg"], foreground=self.palette["text"]).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, text=subtitle, style="Muted.TLabel", wraplength=500).grid(row=2, column=0, sticky="w", pady=(8, 0))
        content = ttk.Frame(window, style="Card.TFrame", padding=22)
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
        for row, text in enumerate(["DataQ 접수 화면을 열고 직접 로그인합니다.", "ADsP 고사장 목록 팝업을 열고 화면 맨 앞으로 둡니다.", "새로고침 후 스크롤 포커스를 받을 본문 좌표를 둡니다."]):
            ttk.Label(parent, text=f"{row + 1}. {text}", style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=5)
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
        ttk.Label(frame, text=spec.label, style="Card.TLabel", font=("Pretendard", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=spec.variable, show="*" if spec.secret else "").grid(row=1, column=0, sticky="ew", pady=(6, 4))
        ttk.Label(frame, text=spec.helper, style="CardMuted.TLabel", wraplength=480).grid(row=2, column=0, sticky="w")
        spec.variable.trace_add("write", lambda *_args: self._refresh_all())

    def _refresh_all(self) -> None:
        self._refresh_command_preview()
        self._refresh_summary()
        self._draw_chart()

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
        self.command_var.set(" ".join(f'"{part}"' if " " in part else part for part in cmd))

    def _append_output(self, text: str) -> None:
        self.output_text.insert("end", text)
        self.output_text.see("end")
        if "팝업 OCR 확인" in text:
            self.scan_count += 1
            self._push_chart_value(0)
        if "ADsP 잔여좌석 발견" in text:
            self.hit_count += 1
            self._push_chart_value(1)
        if "Telegram 알림 전송 완료" in text:
            self.telegram_count += 1
        self._refresh_summary()

    def _push_chart_value(self, value: int) -> None:
        self.event_buckets = self.event_buckets[1:] + [value]
        self._draw_chart()

    def _draw_chart(self) -> None:
        if not hasattr(self, "chart"):
            return
        self.chart.delete("all")
        width = max(1, self.chart.winfo_width())
        height = max(1, self.chart.winfo_height())
        p = self.palette
        self.chart.configure(bg=p["surface"])
        pad = 18
        inner_w = width - pad * 2
        inner_h = height - pad * 2
        self.chart.create_line(pad, height - pad, width - pad, height - pad, fill=p["line"])
        self.chart.create_line(pad, pad, pad, height - pad, fill=p["line"])
        max_value = max(1, max(self.event_buckets))
        bar_w = max(4, inner_w / len(self.event_buckets) * 0.56)
        gap = inner_w / len(self.event_buckets)
        for idx, value in enumerate(self.event_buckets):
            x = pad + idx * gap + gap * 0.22
            bar_h = (value / max_value) * (inner_h - 8)
            color = ACCENT if value else p["surface2"]
            self.chart.create_rectangle(x, height - pad - bar_h, x + bar_w, height - pad, fill=color, outline="")
        self.chart.create_text(pad, pad - 2, anchor="nw", text="seat signal timeline", fill=p["muted"], font=("Pretendard", 9))

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
        self.output_text.delete("1.0", "end")
        self._append_output("실행 시작\n")
        self._append_output(self.command_var.get() + "\n\n")
        self.process = subprocess.Popen(self._build_command(), cwd=Path(__file__).resolve().parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env)
        self.status_var.set("실행 중")
        self.status_badge.configure(bg="#063B2F", fg="#9FF4DF")
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
                    self.status_badge.configure(bg="#102A5C", fg="#B9D2FF")
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