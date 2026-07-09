"""
[Codex AI Rules for adsp_watcher_gui.py]
1. Do not introduce new hardcoded layout/style values when editing this GUI.
2. Prefer DESIGN_TOKENS for colors, typography, spacing, component sizes, and state colors.
3. Add or extend token categories first when a new visual variable is needed.
4. Map reusable ttk components through the theme engine instead of one-off inline styling.
5. Inline tk options are allowed only where ttk cannot style the widget, and must still read from DESIGN_TOKENS.
"""
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

DESIGN_TOKENS = {
    "brand": {
        "accent": ACCENT,
        "accent_hover": "#0042CC",
        "accent_disabled": "#809EF5",
        "on_accent": "#FFFFFF",
    },
    "palette": {
        "dark": {
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
            "status_bg": "#102A5C",
            "status_fg": "#B9D2FF",
            "running_bg": "#063B2F",
            "running_fg": "#9FF4DF",
            "log_fg": "#E5E7EB",
            "table_odd": "#121A2B",
            "table_even": "#172033",
            "table_selected": "#102A5C",
        },
        "light": {
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
            "status_bg": "#EAF2FF",
            "status_fg": ACCENT,
            "running_bg": "#E6F8F1",
            "running_fg": "#008F6B",
            "log_fg": "#E5E7EB",
            "table_odd": "#FFFFFF",
            "table_even": "#F7F9FC",
            "table_selected": "#EAF2FF",
        },
    },
    "typography": {
        "family": "Pretendard",
        "mono": "Consolas",
        "title": ("Pretendard", 24, "bold"),
        "modal_title": ("Pretendard", 20, "bold"),
        "section": ("Pretendard", 13, "bold"),
        "metric": ("Pretendard", 26, "bold"),
        "body": ("Pretendard", 10),
        "body_bold": ("Pretendard", 10, "bold"),
        "caption": ("Pretendard", 9),
        "sidebar_title": ("Pretendard", 18, "bold"),
        "log": ("Consolas", 10),
    },
    "space": {
        "xxs": 2,
        "xs": 3,
        "sm": 5,
        "md": 8,
        "lg": 12,
        "xl": 18,
        "xxl": 24,
    },
    "layout": {
        "window": "1180x780",
        "window_min": (1080, 720),
        "modal": "560x520",
        "sidebar_pad": (18, 22),
        "main_pad": (24, 20, 24, 24),
        "card_pad": 18,
        "modal_card_pad": 22,
        "chart_height": 170,
        "chart_pad": 18,
        "log_height": 14,
        "status_pad_x": 14,
        "status_pad_y": 8,
    },
    "component": {
        "status_card_min_h": 92,
        "status_chip_pad": (10, 5),
    },
    "table": {
        "row_height": 32,
        "heading_height": 36,
        "event_height": 7,
    },
    "toast": {
        "width": 420,
        "height": 64,
        "duration_ms": 3200,
        "pad": 16,
        "offset": 24,
    },
    "effects": {
        "border_width": 0,
        "relief_flat": "flat",
        "highlight_none": 0,
    },
}


def token(*path):
    value = DESIGN_TOKENS
    for key in path:
        value = value[key]
    return value


def space(name: str) -> int:
    return token("space", name)


def mode_name(is_dark: bool) -> str:
    return "dark" if is_dark else "light"


def mode_palette(is_dark: bool) -> dict[str, str]:
    return token("palette", mode_name(is_dark)).copy()


def init_theme_system(root: tk.Misc, palette: dict[str, str]) -> ttk.Style:
    """
    Data-driven ttk style matrix.

    All reusable ttk styles must be derived from DESIGN_TOKENS. When the UI
    needs a new visual state or component variant, extend DESIGN_TOKENS first
    and then map it here.
    """
    style = ttk.Style(root)
    style.theme_use("clam")
    typo = token("typography")
    spacing = token("space")
    effects = token("effects")
    brand = token("brand")

    style.configure(".", font=typo["body"], background=palette["bg"], foreground=palette["text"])
    style.configure("Root.TFrame", background=palette["bg"])
    style.configure("Sidebar.TFrame", background=palette["sidebar"])
    style.configure("Card.TFrame", background=palette["surface"])
    style.configure("Soft.TFrame", background=palette["surface2"])

    style.configure("TLabel", background=palette["bg"], foreground=palette["text"])
    style.configure("Muted.TLabel", background=palette["bg"], foreground=palette["muted"])
    style.configure("Side.TLabel", background=palette["sidebar"], foreground=palette["text"])
    style.configure("SideMuted.TLabel", background=palette["sidebar"], foreground=palette["muted"])
    style.configure("Card.TLabel", background=palette["surface"], foreground=palette["text"])
    style.configure("CardMuted.TLabel", background=palette["surface"], foreground=palette["muted"])
    style.configure("Soft.TLabel", background=palette["surface2"], foreground=palette["text"])
    style.configure("Title.TLabel", font=typo["title"], background=palette["bg"], foreground=palette["text"])
    style.configure("Section.TLabel", font=typo["section"], background=palette["surface"], foreground=palette["text"])
    style.configure("Metric.TLabel", font=typo["metric"], background=palette["surface"], foreground=palette["text"])
    style.configure("StatusCard.TFrame", background=palette["surface"])
    style.configure("StatusValue.TLabel", font=typo["metric"], background=palette["surface"], foreground=palette["text"])
    style.configure("StatusCaption.TLabel", font=typo["caption"], background=palette["surface"], foreground=palette["muted"])

    style.configure(
        "Primary.TButton",
        padding=(spacing["xl"], spacing["lg"]),
        background=brand["accent"],
        foreground=brand["on_accent"],
        borderwidth=effects["border_width"],
    )
    style.map(
        "Primary.TButton",
        background=[("active", brand["accent_hover"]), ("disabled", brand["accent_disabled"])],
        foreground=[("disabled", brand["on_accent"])],
    )
    style.configure(
        "Secondary.TButton",
        padding=(spacing["xl"], spacing["md"] + 1),
        background=palette["surface2"],
        foreground=brand["accent"],
        borderwidth=effects["border_width"],
    )
    style.configure(
        "Ghost.TButton",
        padding=(spacing["lg"], spacing["md"]),
        background=palette["sidebar"],
        foreground=palette["muted"],
        borderwidth=effects["border_width"],
    )
    style.configure(
        "Danger.TButton",
        padding=(spacing["xl"], spacing["md"] + 1),
        background=palette["surface2"],
        foreground=palette["danger"],
        borderwidth=effects["border_width"],
    )

    style.configure(
        "TEntry",
        padding=(spacing["lg"], spacing["md"] - 1),
        fieldbackground=palette["surface2"],
        foreground=palette["text"],
        bordercolor=palette["line"],
        lightcolor=palette["line"],
        darkcolor=palette["line"],
    )
    style.configure(
        "TCombobox",
        padding=(spacing["md"], spacing["md"] - 1),
        fieldbackground=palette["surface2"],
        foreground=palette["text"],
        bordercolor=palette["line"],
    )
    style.configure("TCheckbutton", background=palette["surface"], foreground=palette["text"])
    return style


@dataclass
class FieldSpec:
    label: str
    variable: tk.StringVar
    helper: str
    secret: bool = False


class InfoCard(ttk.Frame):
    def __init__(self, parent: tk.Misc, title: str, body: str, palette: dict[str, str], done: bool = False) -> None:
        super().__init__(parent, style="Card.TFrame", padding=token("layout", "card_pad"))
        self.configure(height=token("component", "status_card_min_h"))
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)
        mark = "완료" if done else "필요"
        color = palette["good"] if done else palette["warning"]
        ttk.Label(self, text=title, style="Section.TLabel").grid(row=0, column=0, sticky="w")
        tk.Label(self, text=mark, bg=color, fg=token("brand", "on_accent"), padx=10, pady=4, font=token("typography", "caption")).grid(row=0, column=1, sticky="e")
        ttk.Label(self, text=body, style="CardMuted.TLabel", wraplength=260).grid(row=1, column=0, columnspan=2, sticky="w", pady=(space("md"), 0))

class WatchStatusCard(ttk.Frame):
    def __init__(self, parent: tk.Misc, title: str, value: tk.StringVar, caption: tk.StringVar) -> None:
        super().__init__(parent, style="StatusCard.TFrame", padding=token("layout", "card_pad"))
        self.configure(height=token("component", "status_card_min_h"))
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text=title, style="StatusCaption.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self, textvariable=value, style="StatusValue.TLabel").grid(row=1, column=0, sticky="w", pady=(space("sm"), 0))
        ttk.Label(self, textvariable=caption, style="StatusCaption.TLabel").grid(row=2, column=0, sticky="w", pady=(space("sm"), 0))


class ToastBanner(tk.Toplevel):
    def __init__(self, parent: tk.Tk, message: str, palette: dict[str, str], danger: bool = False) -> None:
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        bg_color = palette["danger"] if danger else token("brand", "accent")
        self.configure(bg=bg_color)
        parent.update_idletasks()
        width = token("toast", "width")
        height = token("toast", "height")
        offset = token("toast", "offset")
        x = parent.winfo_rootx() + max(0, parent.winfo_width() - width - offset)
        y = parent.winfo_rooty() + offset
        self.geometry(f"{width}x{height}+{x}+{y}")
        label = tk.Label(
            self,
            text=message,
            bg=bg_color,
            fg=token("brand", "on_accent"),
            font=token("typography", "body_bold"),
            padx=token("toast", "pad"),
            pady=token("toast", "pad"),
            anchor="w",
            justify="left",
        )
        label.pack(fill="both", expand=True)
        self.after(token("toast", "duration_ms"), self.destroy)


class WatcherGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(token("layout", "window"))
        self.minsize(*token("layout", "window_min"))

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
        self.scan_caption_var = tk.StringVar(value="아직 스캔 전")
        self.hit_caption_var = tk.StringVar(value="잔여좌석 후보 없음")
        self.telegram_caption_var = tk.StringVar(value="알림 대기")

        self.palette: dict[str, str] = {}
        self._apply_palette()
        self._configure_style()
        self._build_ui()
        self._refresh_command_preview()
        self._refresh_summary()
        self.after(150, self._drain_output_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_palette(self) -> None:
        self.palette = mode_palette(self.dark_mode_var.get())

    def _configure_style(self) -> None:
        self.theme = init_theme_system(self, self.palette)

    def _build_ui(self) -> None:
        self.configure(bg=self.palette["bg"])
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        self.sidebar = ttk.Frame(self, style="Sidebar.TFrame", padding=token("layout", "sidebar_pad"))
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.rowconfigure(8, weight=1)
        self._build_sidebar(self.sidebar)

        self.main = ttk.Frame(self, style="Root.TFrame", padding=token("layout", "main_pad"))
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(3, weight=1)
        self._build_topbar(self.main)
        self._build_readiness(self.main)
        self._build_user_status(self.main)
        self._build_user_controls(self.main)

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="ADsP", style="Side.TLabel", font=token("typography", "sidebar_title")).grid(row=0, column=0, sticky="w")
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
        ttk.Label(top, text="ADsP 잔여좌석 알림 도우미", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(top, text=f"{TARGET_EXAM} | 화면 감시와 휴대폰 알림만 수행합니다", style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))
        filters = ttk.Frame(top, style="Root.TFrame")
        filters.grid(row=0, column=1, rowspan=2, sticky="e")
        self.status_badge = tk.Label(filters, textvariable=self.status_var, bg=self.palette["status_bg"], fg=self.palette["status_fg"], padx=token("layout", "status_pad_x"), pady=token("layout", "status_pad_y"), font=token("typography", "body_bold"))
        self.status_badge.grid(row=0, column=0)

    def _build_readiness(self, parent: ttk.Frame) -> None:
        section = ttk.Frame(parent, style="Root.TFrame")
        section.grid(row=1, column=0, sticky="ew", pady=(0, 18))
        for col in range(3):
            section.columnconfigure(col, weight=1)
        telegram_ready = bool(self.token_var.get().strip() and self.chat_id_var.get().strip())
        InfoCard(section, "1. 휴대폰 알림", "Telegram Bot token과 Chat ID를 입력하고 테스트 전송을 합니다.", self.palette, done=telegram_ready).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        InfoCard(section, "2. DataQ 화면", "일반 Chrome에서 직접 로그인하고 고사장 목록 팝업을 맨 앞에 둡니다.", self.palette, done=False).grid(row=0, column=1, sticky="ew", padx=8)
        running = self.process is not None and self.process.poll() is None
        InfoCard(section, "3. 감시 시작", "준비가 끝나면 시작 버튼만 누릅니다. 실제 접수와 결제는 직접 진행합니다.", self.palette, done=running).grid(row=0, column=2, sticky="ew", padx=(8, 0))

    def _build_user_status(self, parent: ttk.Frame) -> None:
        cards = ttk.Frame(parent, style="Root.TFrame")
        cards.grid(row=2, column=0, sticky="ew", pady=(0, 18))
        for col in range(3):
            cards.columnconfigure(col, weight=1)
        self._metric_card(cards, 0, "Telegram", self.telegram_status_var, self.telegram_caption_var)
        self._metric_card(cards, 1, "마지막 확인", self.scan_metric_var, self.scan_caption_var)
        self._metric_card(cards, 2, "좌석 알림", self.hit_metric_var, self.hit_caption_var)

    def _build_user_controls(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=token("layout", "card_pad"))
        panel.grid(row=3, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text="실행", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(panel, textvariable=self.primary_message_var, style="CardMuted.TLabel", wraplength=760).grid(row=1, column=0, sticky="w", pady=(8, 22))
        actions = ttk.Frame(panel, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="ew")
        self.start_button = ttk.Button(actions, text="감시 시작", style="Primary.TButton", command=self._start_watcher)
        self.start_button.grid(row=0, column=0, sticky="w")
        self.stop_button = ttk.Button(actions, text="중지", style="Danger.TButton", command=self._stop_watcher, state="disabled")
        self.stop_button.grid(row=0, column=1, sticky="w", padx=(12, 0))
        ttk.Button(actions, text="초기 설정", style="Secondary.TButton", command=self._open_setup_wizard).grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Button(actions, text="Telegram 테스트", style="Secondary.TButton", command=self._test_telegram).grid(row=0, column=3, sticky="w", padx=(12, 0))
        ttk.Label(panel, text="이 도구는 화면 감시와 알림만 수행합니다. 접수, 결제, 로그인, 캡차 처리는 사용자가 직접 합니다.", style="CardMuted.TLabel", wraplength=760).grid(row=3, column=0, sticky="w", pady=(28, 0))
    def _metric_card(self, parent: ttk.Frame, col: int, title: str, value: tk.StringVar, caption: tk.StringVar) -> None:
        card = WatchStatusCard(parent, title, value, caption)
        card.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 8, 0 if col == 2 else 8))

    def _toggle_theme(self) -> None:
        self._apply_palette()
        self._configure_style()
        for child in self.winfo_children():
            child.destroy()
        self._build_ui()
        self._refresh_all()

    def _refresh_summary(self) -> None:
        telegram_ready = bool(self.token_var.get().strip() and self.chat_id_var.get().strip())
        self.telegram_status_var.set("준비됨" if telegram_ready else "미설정")
        if telegram_ready and self.telegram_caption_var.get() in {"알림 대기", "Bot token과 Chat ID가 필요합니다"}:
            self.telegram_caption_var.set("테스트 전송을 해보세요")
        elif not telegram_ready:
            self.telegram_caption_var.set("Bot token과 Chat ID가 필요합니다")
        self.scan_metric_var.set(time.strftime("%H:%M:%S") if self.scan_count else "아직 없음")
        self.hit_metric_var.set(str(self.hit_count))
        self.telegram_metric_var.set(str(self.telegram_count))
        telegram = "Telegram 설정됨" if telegram_ready else "Telegram 미설정"
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
        window.geometry(token("layout", "modal"))
        window.configure(bg=self.palette["bg"])
        window.transient(self)
        window.grab_set()
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        header = ttk.Frame(window, padding=(24, 22, 24, 12))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text=f"{index + 1}/4", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=title, font=token("typography", "modal_title"), background=self.palette["bg"], foreground=self.palette["text"]).grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(header, text=subtitle, style="Muted.TLabel", wraplength=500).grid(row=2, column=0, sticky="w", pady=(8, 0))
        content = ttk.Frame(window, style="Card.TFrame", padding=token("layout", "modal_card_pad"))
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
        ttk.Label(frame, text=spec.label, style="Card.TLabel", font=token("typography", "body_bold")).grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=spec.variable, show="*" if spec.secret else "").grid(row=1, column=0, sticky="ew", pady=(6, 4))
        ttk.Label(frame, text=spec.helper, style="CardMuted.TLabel", wraplength=480).grid(row=2, column=0, sticky="w")
        spec.variable.trace_add("write", lambda *_args: self._refresh_all())

    def _refresh_all(self) -> None:
        self._refresh_command_preview()
        self._refresh_summary()

    def _show_toast(self, message: str, danger: bool = False) -> None:
        ToastBanner(self, message, self.palette, danger=danger)

    def _parse_runtime_event(self, text: str) -> None:
        if "팝업 OCR 확인" in text:
            self.scan_count += 1
            self.scan_caption_var.set(time.strftime("마지막 확인 %H:%M:%S"))
            match = re.search(r"팝업 OCR 확인:\s*(\d+)건", text)
            if match and int(match.group(1)) > 0:
                self.scan_caption_var.set("좌석 후보를 확인하는 중")

        seat_match = re.search(r"OCR No\.(\d+)\s+잔여좌석\s+(\d+)석", text)
        if seat_match:
            no, seats = seat_match.groups()
            self.hit_count += 1
            self.hit_metric_var.set(str(self.hit_count))
            self.hit_caption_var.set(f"No.{no} 고사장 / {seats}석")
            self.primary_message_var.set("잔여좌석 가능성이 감지되었습니다. 휴대폰 알림과 DataQ 화면을 확인하세요.")
            self._show_toast(f"잔여좌석 가능성 감지\nNo.{no} / {seats}석")

        if "ADsP 잔여좌석 발견" in text and not seat_match:
            self.hit_count += 1
            self.hit_metric_var.set(str(self.hit_count))
            self.primary_message_var.set("잔여좌석 가능성이 감지되었습니다. 휴대폰 알림과 DataQ 화면을 확인하세요.")

        if "Telegram 알림 전송 완료" in text:
            self.telegram_count += 1
            self.telegram_caption_var.set("알림 전송 완료")
            self._show_toast("휴대폰 알림을 보냈습니다")

        if "Telegram 테스트 전송 완료" in text:
            self.telegram_caption_var.set("테스트 성공")
            self._show_toast("Telegram 테스트 전송 완료")

        if "Telegram 알림 실패" in text or "Telegram 테스트 전송 실패" in text:
            self.telegram_caption_var.set("전송 실패")
            self._show_toast("Telegram 전송에 실패했습니다", danger=True)

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

    def _remember_log(self, text: str) -> None:
        self.debug_lines.append(text)
        if len(self.debug_lines) > 1200:
            self.debug_lines = self.debug_lines[-1200:]
        if self.debug_text is not None and self.debug_text.winfo_exists():
            self.debug_text.insert("end", text)
            self.debug_text.see("end")

    def _append_output(self, text: str) -> None:
        self._remember_log(text)
        self._parse_runtime_event(text)
        self._refresh_summary()

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
        self.debug_lines.clear()
        self._append_output("실행 시작\n")
        self._append_output(self.command_var.get() + "\n\n")
        self.process = subprocess.Popen(self._build_command(), cwd=Path(__file__).resolve().parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env)
        self.status_var.set("실행 중")
        self.status_badge.configure(bg=self.palette["running_bg"], fg=self.palette["running_fg"])
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
                    self.status_badge.configure(bg=self.palette["status_bg"], fg=self.palette["status_fg"])
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                elif item == "__SUMMARY_REFRESH__":
                    self._refresh_summary()
                else:
                    self._append_output(item)
        except queue.Empty:
            pass
        self.after(150, self._drain_output_queue)

    def _open_debug_log(self) -> None:
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.lift()
            return
        window = tk.Toplevel(self)
        self.debug_window = window
        window.title(f"{APP_TITLE} - 문제 해결 로그")
        window.geometry("760x520")
        window.configure(bg=self.palette["bg"])
        window.columnconfigure(0, weight=1)
        window.rowconfigure(1, weight=1)
        header = ttk.Frame(window, style="Root.TFrame", padding=(18, 16, 18, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="문제 해결 로그", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(header, text="명령 복사", style="Secondary.TButton", command=self._copy_command).grid(row=0, column=1, sticky="e")
        text = tk.Text(window, wrap="word", height=token("layout", "log_height"), font=token("typography", "log"), bg=self.palette["log_bg"], fg=self.palette["log_fg"], insertbackground=self.palette["log_fg"], relief=token("effects", "relief_flat"), padx=14, pady=14)
        text.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.debug_text = text
        text.insert("end", "".join(self.debug_lines) or "아직 로그가 없습니다.\n")
        text.see("end")
        window.protocol("WM_DELETE_WINDOW", self._close_debug_log)

    def _close_debug_log(self) -> None:
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.destroy()
        self.debug_window = None
        self.debug_text = None
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