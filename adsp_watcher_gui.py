"""
[Codex AI Rules for adsp_watcher_gui.py]
1. This is the general-user GUI. Keep OCR internals, raw parsing details, and developer diagnostics out of the main screen.
2. Prefer DESIGN_TOKENS for colors, typography, spacing, component sizes, and state colors.
3. Add or extend token categories first when a new visual variable is needed.
4. Map reusable ttk components through init_theme_system() instead of one-off ttk styling.
5. Keep detailed logs and generated CLI commands inside the troubleshooting drawer only.
"""
from __future__ import annotations

import os
import queue
import re
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
        "accent_disabled": "#8FB1FF",
        "on_accent": "#FFFFFF",
    },
    "palette": {
        "light": {
            "bg": "#F6F8FC",
            "sidebar": "#FFFFFF",
            "surface": "#FFFFFF",
            "surface2": "#EEF4FF",
            "text": "#191F28",
            "muted": "#6B7684",
            "line": "#E5E8EB",
            "good": "#00A878",
            "warning": "#F59F00",
            "danger": "#E03131",
            "status_bg": "#EAF2FF",
            "status_fg": ACCENT,
            "running_bg": "#E6F8F1",
            "running_fg": "#008F6B",
            "log_bg": "#111827",
            "log_fg": "#E5E7EB",
        },
        "dark": {
            "bg": "#0B1020",
            "sidebar": "#080D1A",
            "surface": "#121A2B",
            "surface2": "#172033",
            "text": "#F8FAFC",
            "muted": "#94A3B8",
            "line": "#26344D",
            "good": "#2DD4BF",
            "warning": "#FBBF24",
            "danger": "#FB7185",
            "status_bg": "#102A5C",
            "status_fg": "#B9D2FF",
            "running_bg": "#063B2F",
            "running_fg": "#9FF4DF",
            "log_bg": "#050816",
            "log_fg": "#E5E7EB",
        },
    },
    "typography": {
        "family": "Pretendard",
        "mono": "Consolas",
        "hero": ("Pretendard", 28, "bold"),
        "title": ("Pretendard", 21, "bold"),
        "modal_title": ("Pretendard", 18, "bold"),
        "section": ("Pretendard", 13, "bold"),
        "metric": ("Pretendard", 22, "bold"),
        "body": ("Pretendard", 10),
        "body_bold": ("Pretendard", 10, "bold"),
        "caption": ("Pretendard", 9),
        "sidebar_title": ("Pretendard", 18, "bold"),
        "log": ("Consolas", 10),
    },
    "space": {
        "xxs": 2,
        "xs": 4,
        "sm": 6,
        "md": 10,
        "lg": 14,
        "xl": 20,
        "xxl": 28,
    },
    "layout": {
        "window": "1080x720",
        "window_min": (980, 650),
        "modal": "560x520",
        "debug": "760x520",
        "sidebar_pad": (20, 24),
        "main_pad": (28, 24, 28, 28),
        "card_pad": 20,
        "modal_card_pad": 22,
        "status_pad_x": 14,
        "status_pad_y": 8,
        "log_height": 22,
    },
    "component": {
        "hero_min_h": 172,
        "step_card_min_h": 128,
        "status_card_min_h": 104,
        "toast_width": 420,
        "toast_height": 64,
        "toast_duration_ms": 3200,
        "toast_pad": 16,
        "toast_offset": 24,
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
    style.configure("Hero.TFrame", background=palette["surface2"])

    style.configure("TLabel", background=palette["bg"], foreground=palette["text"])
    style.configure("Muted.TLabel", background=palette["bg"], foreground=palette["muted"])
    style.configure("Side.TLabel", background=palette["sidebar"], foreground=palette["text"])
    style.configure("SideMuted.TLabel", background=palette["sidebar"], foreground=palette["muted"])
    style.configure("Card.TLabel", background=palette["surface"], foreground=palette["text"])
    style.configure("CardMuted.TLabel", background=palette["surface"], foreground=palette["muted"])
    style.configure("Soft.TLabel", background=palette["surface2"], foreground=palette["text"])
    style.configure("SoftMuted.TLabel", background=palette["surface2"], foreground=palette["muted"])
    style.configure("Hero.TLabel", font=typo["hero"], background=palette["surface2"], foreground=palette["text"])
    style.configure("Title.TLabel", font=typo["title"], background=palette["bg"], foreground=palette["text"])
    style.configure("Section.TLabel", font=typo["section"], background=palette["surface"], foreground=palette["text"])
    style.configure("SoftSection.TLabel", font=typo["section"], background=palette["surface2"], foreground=palette["text"])
    style.configure("Metric.TLabel", font=typo["metric"], background=palette["surface"], foreground=palette["text"])

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

class StepCard(ttk.Frame):
    def __init__(self, parent: tk.Misc, number: int, title: str, body: str, palette: dict[str, str], done: bool = False) -> None:
        super().__init__(parent, style="Card.TFrame", padding=token("layout", "card_pad"))
        self.configure(height=token("component", "step_card_min_h"))
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)
        badge_text = "완료" if done else "필요"
        badge_color = palette["good"] if done else palette["warning"]
        ttk.Label(self, text=f"{number}. {title}", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        tk.Label(
            self,
            text=badge_text,
            bg=badge_color,
            fg=token("brand", "on_accent"),
            padx=10,
            pady=4,
            font=token("typography", "caption"),
        ).grid(row=0, column=1, sticky="e")
        ttk.Label(self, text=body, style="CardMuted.TLabel", wraplength=260).grid(row=1, column=0, columnspan=2, sticky="w", pady=(space("md"), 0))


class StatusCard(ttk.Frame):
    def __init__(self, parent: tk.Misc, title: str, value: tk.StringVar, caption: tk.StringVar) -> None:
        super().__init__(parent, style="Card.TFrame", padding=token("layout", "card_pad"))
        self.configure(height=token("component", "status_card_min_h"))
        self.grid_propagate(False)
        self.columnconfigure(0, weight=1)
        ttk.Label(self, text=title, style="CardMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(self, textvariable=value, style="Metric.TLabel").grid(row=1, column=0, sticky="w", pady=(space("sm"), 0))
        ttk.Label(self, textvariable=caption, style="CardMuted.TLabel").grid(row=2, column=0, sticky="w", pady=(space("sm"), 0))


class ToastBanner(tk.Toplevel):
    def __init__(self, parent: tk.Tk, message: str, palette: dict[str, str], danger: bool = False) -> None:
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        bg_color = palette["danger"] if danger else token("brand", "accent")
        self.configure(bg=bg_color)
        parent.update_idletasks()
        width = token("component", "toast_width")
        height = token("component", "toast_height")
        offset = token("component", "toast_offset")
        x = parent.winfo_rootx() + max(0, parent.winfo_width() - width - offset)
        y = parent.winfo_rooty() + offset
        self.geometry(f"{width}x{height}+{x}+{y}")
        tk.Label(
            self,
            text=message,
            bg=bg_color,
            fg=token("brand", "on_accent"),
            font=token("typography", "body_bold"),
            padx=token("component", "toast_pad"),
            pady=token("component", "toast_pad"),
            anchor="w",
            justify="left",
        ).pack(fill="both", expand=True)
        self.after(token("component", "toast_duration_ms"), self.destroy)


class WatcherGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(token("layout", "window"))
        self.minsize(*token("layout", "window_min"))

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[str] = queue.Queue()
        self.debug_lines: list[str] = []
        self.debug_window: tk.Toplevel | None = None
        self.debug_text: tk.Text | None = None
        self.scan_count = 0
        self.hit_count = 0
        self.telegram_count = 0
        self.telegram_test_ok = False

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
        self.dark_mode_var = tk.BooleanVar(value=False)

        self.status_var = tk.StringVar(value="대기 중")
        self.primary_message_var = tk.StringVar(value="아래 순서대로 준비한 뒤 감시 시작을 누르세요.")
        self.telegram_value_var = tk.StringVar(value="미설정")
        self.telegram_caption_var = tk.StringVar(value="Bot token과 Chat ID를 입력하세요")
        self.popup_value_var = tk.StringVar(value="직접 준비")
        self.popup_caption_var = tk.StringVar(value="Chrome에서 DataQ 팝업을 맨 앞에 둡니다")
        self.last_check_var = tk.StringVar(value="아직 없음")
        self.last_check_caption_var = tk.StringVar(value="시작 후 자동으로 갱신됩니다")
        self.hit_value_var = tk.StringVar(value="0")
        self.hit_caption_var = tk.StringVar(value="잔여좌석 알림 대기")
        self.command_var = tk.StringVar(value="")

        self.palette: dict[str, str] = {}
        self._apply_palette()
        self._configure_style()
        self._build_ui()
        self._refresh_all()
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
        self._build_hero(self.main)
        self._build_steps(self.main)
        self._build_status(self.main)
        self._build_controls(self.main)
    def _build_sidebar(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="ADsP", style="Side.TLabel", font=token("typography", "sidebar_title")).grid(row=0, column=0, sticky="w")
        ttk.Label(parent, text="Seat Watcher", style="SideMuted.TLabel").grid(row=1, column=0, sticky="w", pady=(space("xs"), space("xxl")))
        actions = [
            ("시작 준비", self._open_setup_wizard),
            ("Telegram 테스트", self._test_telegram),
            ("DataQ 열기", lambda: webbrowser.open(DATAQ_ACCEPT_URL)),
            ("문제 해결 로그", self._open_debug_log),
        ]
        for row, (label, command) in enumerate(actions, start=2):
            ttk.Button(parent, text=label, style="Ghost.TButton", command=command).grid(row=row, column=0, sticky="ew", pady=space("xs"))
        ttk.Checkbutton(parent, text="Dark mode", variable=self.dark_mode_var, command=self._toggle_theme).grid(row=9, column=0, sticky="w", pady=(space("xxl"), space("md")))
        ttk.Label(parent, text="자동 로그인 없음\n자동 접수 없음\n자동 결제 없음", style="SideMuted.TLabel", justify="left").grid(row=10, column=0, sticky="w", pady=(space("md"), 0))

    def _build_hero(self, parent: ttk.Frame) -> None:
        hero = ttk.Frame(parent, style="Hero.TFrame", padding=token("layout", "card_pad"))
        hero.grid(row=0, column=0, sticky="ew", pady=(0, space("xl")))
        hero.columnconfigure(0, weight=1)
        hero.configure(height=token("component", "hero_min_h"))
        ttk.Label(hero, text="ADsP 잔여좌석 알림 도우미", style="Hero.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            hero,
            text=f"{TARGET_EXAM} 고사장 팝업을 직접 열어두면 화면에 보이는 잔여좌석을 읽고 휴대폰으로 알려줍니다.",
            style="SoftMuted.TLabel",
            wraplength=720,
        ).grid(row=1, column=0, sticky="w", pady=(space("md"), 0))
        self.status_badge = tk.Label(
            hero,
            textvariable=self.status_var,
            bg=self.palette["status_bg"],
            fg=self.palette["status_fg"],
            padx=token("layout", "status_pad_x"),
            pady=token("layout", "status_pad_y"),
            font=token("typography", "body_bold"),
        )
        self.status_badge.grid(row=0, column=1, sticky="ne")
        ttk.Button(hero, text="감시 시작", style="Primary.TButton", command=self._start_watcher).grid(row=2, column=0, sticky="w", pady=(space("xl"), 0))
        ttk.Button(hero, text="설정 확인", style="Secondary.TButton", command=self._open_setup_wizard).grid(row=2, column=0, sticky="w", padx=(140, 0), pady=(space("xl"), 0))

    def _build_steps(self, parent: ttk.Frame) -> None:
        steps = ttk.Frame(parent, style="Root.TFrame")
        steps.grid(row=1, column=0, sticky="ew", pady=(0, space("xl")))
        for col in range(3):
            steps.columnconfigure(col, weight=1)
        telegram_ready = self._telegram_ready()
        running = self._is_running()
        StepCard(steps, 1, "휴대폰 알림", "Telegram 정보를 입력하고 테스트 메시지를 받아봅니다.", self.palette, done=self.telegram_test_ok).grid(row=0, column=0, sticky="ew", padx=(0, space("md")))
        StepCard(steps, 2, "DataQ 화면", "일반 Chrome에서 직접 로그인하고 고사장 팝업을 맨 앞에 둡니다.", self.palette, done=False).grid(row=0, column=1, sticky="ew", padx=(space("sm"), space("sm")))
        StepCard(steps, 3, "감시 시작", "준비가 끝나면 시작 버튼만 누릅니다. 실제 접수와 결제는 직접 합니다.", self.palette, done=running and telegram_ready).grid(row=0, column=2, sticky="ew", padx=(space("md"), 0))

    def _build_status(self, parent: ttk.Frame) -> None:
        cards = ttk.Frame(parent, style="Root.TFrame")
        cards.grid(row=2, column=0, sticky="ew", pady=(0, space("xl")))
        for col in range(4):
            cards.columnconfigure(col, weight=1)
        StatusCard(cards, "Telegram", self.telegram_value_var, self.telegram_caption_var).grid(row=0, column=0, sticky="ew", padx=(0, space("md")))
        StatusCard(cards, "DataQ 팝업", self.popup_value_var, self.popup_caption_var).grid(row=0, column=1, sticky="ew", padx=(space("sm"), space("sm")))
        StatusCard(cards, "마지막 확인", self.last_check_var, self.last_check_caption_var).grid(row=0, column=2, sticky="ew", padx=(space("sm"), space("sm")))
        StatusCard(cards, "좌석 알림", self.hit_value_var, self.hit_caption_var).grid(row=0, column=3, sticky="ew", padx=(space("md"), 0))

    def _build_controls(self, parent: ttk.Frame) -> None:
        panel = ttk.Frame(parent, style="Card.TFrame", padding=token("layout", "card_pad"))
        panel.grid(row=3, column=0, sticky="nsew")
        panel.columnconfigure(0, weight=1)
        ttk.Label(panel, text="실행", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(panel, textvariable=self.primary_message_var, style="CardMuted.TLabel", wraplength=780).grid(row=1, column=0, sticky="w", pady=(space("sm"), space("xl")))
        actions = ttk.Frame(panel, style="Card.TFrame")
        actions.grid(row=2, column=0, sticky="ew")
        self.start_button = ttk.Button(actions, text="감시 시작", style="Primary.TButton", command=self._start_watcher)
        self.start_button.grid(row=0, column=0, sticky="w")
        self.stop_button = ttk.Button(actions, text="중지", style="Danger.TButton", command=self._stop_watcher, state="disabled")
        self.stop_button.grid(row=0, column=1, sticky="w", padx=(space("md"), 0))
        ttk.Button(actions, text="초기 설정", style="Secondary.TButton", command=self._open_setup_wizard).grid(row=0, column=2, sticky="w", padx=(space("md"), 0))
        ttk.Button(actions, text="Telegram 테스트", style="Secondary.TButton", command=self._test_telegram).grid(row=0, column=3, sticky="w", padx=(space("md"), 0))
        ttk.Label(
            panel,
            text="이 도구는 화면 감시와 알림만 수행합니다. 로그인, 접수, 결제, 캡차 처리는 사용자가 직접 합니다.",
            style="CardMuted.TLabel",
            wraplength=780,
        ).grid(row=3, column=0, sticky="w", pady=(space("xxl"), 0))

    def _toggle_theme(self) -> None:
        self._apply_palette()
        self._configure_style()
        for child in self.winfo_children():
            child.destroy()
        self._build_ui()
        self._refresh_all()

    def _show_toast(self, message: str, danger: bool = False) -> None:
        ToastBanner(self, message, self.palette, danger=danger)

    def _telegram_ready(self) -> bool:
        return bool(self.token_var.get().strip() and self.chat_id_var.get().strip())

    def _is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def _refresh_all(self) -> None:
        self._refresh_command_preview()
        if self._telegram_ready():
            self.telegram_value_var.set("준비됨")
            if self.telegram_caption_var.get() in {"Bot token과 Chat ID를 입력하세요", "알림 대기"}:
                self.telegram_caption_var.set("테스트 전송을 해보세요")
        else:
            self.telegram_value_var.set("미설정")
            self.telegram_caption_var.set("Bot token과 Chat ID를 입력하세요")
        self.hit_value_var.set(str(self.hit_count))
        if self._is_running():
            self.status_var.set("감시 중")
            self.primary_message_var.set("감시 중입니다. 잔여좌석 가능성이 감지되면 휴대폰으로 알려드립니다.")
            if hasattr(self, "status_badge"):
                self.status_badge.configure(bg=self.palette["running_bg"], fg=self.palette["running_fg"])
        else:
            self.status_var.set("대기 중")
            if hasattr(self, "status_badge"):
                self.status_badge.configure(bg=self.palette["status_bg"], fg=self.palette["status_fg"])
    def _open_setup_wizard(self) -> None:
        self._open_step(0)

    def _open_step(self, index: int) -> None:
        steps = [
            ("Telegram 알림", "휴대폰으로 받을 Bot token과 Chat ID를 입력합니다.", self._telegram_step),
            ("DataQ 화면 준비", "일반 Chrome에서 직접 로그인하고 고사장 팝업을 맨 앞으로 둡니다.", self._browser_step),
            ("감시 방식", "대부분의 사용자는 기본값 그대로 사용하면 됩니다.", self._behavior_step),
            ("고급 OCR", "화면 영역이 맞지 않을 때만 조정합니다.", self._ocr_step),
        ]
        if index >= len(steps):
            self._refresh_all()
            self._rebuild_main()
            messagebox.showinfo("설정 완료", "설정이 완료되었습니다. 이제 감시 시작을 누르세요.")
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
        ttk.Label(header, text=f"{index + 1}/{len(steps)}", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=title, font=token("typography", "modal_title"), background=self.palette["bg"], foreground=self.palette["text"]).grid(row=1, column=0, sticky="w", pady=(space("xs"), 0))
        ttk.Label(header, text=subtitle, style="Muted.TLabel", wraplength=500).grid(row=2, column=0, sticky="w", pady=(space("md"), 0))
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
        for row, text in enumerate(["DataQ 접수 화면을 엽니다.", "사용자가 직접 로그인합니다.", "ADsP 고사장 목록 팝업을 열고 화면 맨 앞으로 둡니다."]):
            ttk.Label(parent, text=f"{row + 1}. {text}", style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=space("sm"))
        ttk.Button(parent, text="DataQ 접수 화면 열기", style="Secondary.TButton", command=lambda: webbrowser.open(DATAQ_ACCEPT_URL)).grid(row=3, column=0, sticky="ew", pady=(20, 18))
        self._field(parent, 4, FieldSpec("포커스 클릭 좌표", self.focus_click_var, "기본값 900,500. 스크롤이 움직이지 않을 때만 조정하세요."))

    def _behavior_step(self, parent: ttk.Frame) -> None:
        self._field(parent, 0, FieldSpec("확인 주기(초)", self.interval_var, "권장값은 40초입니다."))
        self._field(parent, 1, FieldSpec("스캔 화면 수", self.pages_var, "목록 전체를 훑기 위한 화면 수입니다. 권장값은 15입니다."))
        self._field(parent, 2, FieldSpec("휠 칸 수", self.wheel_notches_var, "한 번에 내릴 스크롤 양입니다. 권장값은 9입니다."))
        checks = ttk.Frame(parent, style="Card.TFrame")
        checks.grid(row=3, column=0, sticky="ew", pady=(16, 0))
        for row, (label, var) in enumerate([("새로고침 사용", self.refresh_var), ("양식 다시 제출 확인 처리", self.confirm_resubmit_var), ("절전 방지", self.keep_awake_var), ("시작 시 Telegram 테스트", self.telegram_test_on_start_var), ("Windows 메시지박스 사용", self.message_box_var)]):
            ttk.Checkbutton(checks, text=label, variable=var, command=self._refresh_all).grid(row=row, column=0, sticky="w", pady=space("xs"))

    def _ocr_step(self, parent: ttk.Frame) -> None:
        self._field(parent, 0, FieldSpec("전체 OCR 영역", self.bbox_var, "기본값: 0,90,1845,980"))
        self._field(parent, 1, FieldSpec("잔여좌석 열 영역", self.seat_bbox_var, "기본값: 1535,90,1645,980"))
        ttk.Checkbutton(parent, text="잔여좌석 열 보조 OCR 사용", variable=self.seat_column_var, command=self._refresh_all).grid(row=2, column=0, sticky="w", pady=(12, 0))
        self._field(parent, 3, FieldSpec("OCR 원문 저장 파일", self.save_text_var, "문제 해결용 텍스트 파일명입니다."))

    def _field(self, parent: ttk.Frame, row: int, spec: FieldSpec) -> None:
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=spec.label, style="Card.TLabel", font=token("typography", "body_bold")).grid(row=0, column=0, sticky="w")
        ttk.Entry(frame, textvariable=spec.variable, show="*" if spec.secret else "").grid(row=1, column=0, sticky="ew", pady=(6, 4))
        ttk.Label(frame, text=spec.helper, style="CardMuted.TLabel", wraplength=480).grid(row=2, column=0, sticky="w")
        spec.variable.trace_add("write", lambda *_args: self._refresh_all())

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
        self._refresh_all()
    def _parse_runtime_event(self, text: str) -> None:
        if "팝업 OCR 확인" in text:
            self.scan_count += 1
            self.last_check_var.set(time.strftime("%H:%M:%S"))
            match = re.search(r"팝업 OCR 확인:\s*(\d+)건", text)
            self.last_check_caption_var.set("좌석 후보 확인 중" if match and int(match.group(1)) > 0 else "잔여좌석 없음")

        seat_match = re.search(r"OCR No\.(\d+)\s+잔여좌석\s+(\d+)석", text)
        if seat_match:
            no, seats = seat_match.groups()
            self.hit_count += 1
            self.hit_value_var.set(str(self.hit_count))
            self.hit_caption_var.set(f"No.{no} 고사장 / {seats}석")
            self.primary_message_var.set("잔여좌석 가능성이 감지되었습니다. 휴대폰 알림과 DataQ 화면을 확인하세요.")
            self._show_toast(f"잔여좌석 가능성 감지\nNo.{no} / {seats}석")

        if "ADsP 잔여좌석 발견" in text and not seat_match:
            self.hit_count += 1
            self.hit_value_var.set(str(self.hit_count))
            self.primary_message_var.set("잔여좌석 가능성이 감지되었습니다. 휴대폰 알림과 DataQ 화면을 확인하세요.")

        if "Telegram 알림 전송 완료" in text:
            self.telegram_count += 1
            self.telegram_caption_var.set("알림 전송 완료")
            self._show_toast("휴대폰 알림을 보냈습니다")

        if "Telegram 테스트 전송 완료" in text:
            self.telegram_test_ok = True
            self.telegram_value_var.set("준비됨")
            self.telegram_caption_var.set("테스트 성공")
            self._show_toast("Telegram 테스트 전송 완료")
            self._rebuild_main()

        if "Telegram 알림 실패" in text or "Telegram 테스트 전송 실패" in text:
            self.telegram_caption_var.set("전송 실패")
            self._show_toast("Telegram 전송에 실패했습니다", danger=True)

    def _test_telegram(self) -> None:
        token_value = self.token_var.get().strip()
        chat_id = self.chat_id_var.get().strip()
        if not token_value or not chat_id:
            messagebox.showwarning("Telegram", "Bot token과 Chat ID를 입력하세요.")
            return
        self.telegram_caption_var.set("테스트 전송 중")

        def worker() -> None:
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            ok = send_telegram(token_value, chat_id, f"ADsP watcher GUI test\n시간: {now}")
            self.output_queue.put("Telegram 테스트 전송 완료\n" if ok else "Telegram 테스트 전송 실패\n")
            self.output_queue.put("__SUMMARY_REFRESH__")

        threading.Thread(target=worker, daemon=True).start()

    def _start_watcher(self) -> None:
        if self._is_running():
            return
        token_value = self.token_var.get().strip()
        chat_id = self.chat_id_var.get().strip()
        if not token_value or not chat_id:
            if not messagebox.askyesno("Telegram 미설정", "Telegram 없이 실행할까요?"):
                return
        self._refresh_all()
        env = os.environ.copy()
        if token_value:
            env["TELEGRAM_BOT_TOKEN"] = token_value
        if chat_id:
            env["TELEGRAM_CHAT_ID"] = chat_id
        self.debug_lines.clear()
        self._append_output("실행 시작\n")
        self._append_output(self.command_var.get() + "\n\n")
        self.process = subprocess.Popen(self._build_command(), cwd=Path(__file__).resolve().parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env)
        self.status_var.set("감시 중")
        self.primary_message_var.set("감시 중입니다. 잔여좌석 가능성이 감지되면 휴대폰으로 알려드립니다.")
        self.status_badge.configure(bg=self.palette["running_bg"], fg=self.palette["running_fg"])
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self._show_toast("감시를 시작했습니다")
        self._rebuild_main()
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
        if not self._is_running():
            return
        self.status_var.set("중지 중")
        assert self.process is not None
        self.process.terminate()

    def _drain_output_queue(self) -> None:
        try:
            while True:
                item = self.output_queue.get_nowait()
                if item == "__PROCESS_EXIT__":
                    self.status_var.set("대기 중")
                    self.primary_message_var.set("감시가 중지되었습니다. 다시 시작할 수 있습니다.")
                    self.status_badge.configure(bg=self.palette["status_bg"], fg=self.palette["status_fg"])
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self._rebuild_main()
                elif item == "__SUMMARY_REFRESH__":
                    self._refresh_all()
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
        window.geometry(token("layout", "debug"))
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
        self._show_toast("실행 명령을 복사했습니다")

    def _rebuild_main(self) -> None:
        if not hasattr(self, "main"):
            return
        for child in self.main.winfo_children():
            child.destroy()
        self._build_hero(self.main)
        self._build_steps(self.main)
        self._build_status(self.main)
        self._build_controls(self.main)
        self._refresh_all()

    def _on_close(self) -> None:
        if self._is_running():
            if not messagebox.askyesno("종료", "감시가 실행 중입니다. 중지하고 종료할까요?"):
                return
            assert self.process is not None
            self.process.terminate()
        self.destroy()


def main() -> int:
    app = WatcherGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())