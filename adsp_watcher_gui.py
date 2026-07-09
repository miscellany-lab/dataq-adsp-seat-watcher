"""
[Codex AI Rules for adsp_watcher_gui.py]
1. This is the general-user GUI. Keep OCR internals and developer diagnostics out of the main screen.
2. Use CustomTkinter widgets for the main UI. Use tkinter only for variables, message boxes, and minimal platform glue.
3. Prefer DESIGN_TOKENS for layout, typography, state colors, and spacing.
4. Keep detailed logs and generated CLI commands inside the troubleshooting window only.
5. Do not save Telegram tokens or passwords to disk.
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
from tkinter import messagebox

import customtkinter as ctk

from adsp_popup_ocr_watcher import DEFAULT_FOCUS_CLICK, DEFAULT_SEAT_BBOX, send_telegram
from adsp_seat_parser import TARGET_EXAM


APP_TITLE = "ADsP Seat Watcher"
BASE_DIR = Path(__file__).resolve().parent
THEME_PATH = BASE_DIR / "themes" / "adsp_customtkinter_theme.json"
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
        "hero": 28,
        "title": 21,
        "modal_title": 18,
        "section": 14,
        "metric": 22,
        "body": 14,
        "caption": 12,
        "sidebar_title": 19,
        "log": 13,
    },
    "space": {
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
        "sidebar_width": 210,
        "sidebar_pad": 22,
        "main_pad": 28,
        "card_pad": 20,
        "modal_pad": 24,
        "modal_card_pad": 22,
    },
    "component": {
        "hero_height": 178,
        "step_card_height": 134,
        "status_card_height": 112,
        "corner_lg": 22,
        "corner_md": 16,
        "toast_width": 420,
        "toast_height": 64,
        "toast_duration_ms": 3200,
        "toast_pad": 16,
        "toast_offset": 24,
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


def font(name: str, weight: str | None = None) -> ctk.CTkFont:
    return ctk.CTkFont(family=token("typography", "family"), size=token("typography", name), weight=weight)


def init_theme_system() -> None:
    ctk.set_default_color_theme(str(THEME_PATH))
    ctk.set_appearance_mode("light")


@dataclass
class FieldSpec:
    label: str
    variable: tk.StringVar
    helper: str
    secret: bool = False

class StepCard(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, number: int, title: str, body: str, palette: dict[str, str], done: bool = False) -> None:
        super().__init__(parent, fg_color=palette["surface"], corner_radius=token("component", "corner_md"), height=token("component", "step_card_height"))
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        badge_text = "완료" if done else "필요"
        badge_color = palette["good"] if done else palette["warning"]
        ctk.CTkLabel(self, text=f"{number}. {title}", font=font("section", "bold"), text_color=palette["text"]).grid(row=0, column=0, sticky="w", padx=token("layout", "card_pad"), pady=(token("layout", "card_pad"), 0))
        ctk.CTkLabel(self, text=badge_text, fg_color=badge_color, text_color=token("brand", "on_accent"), corner_radius=999, font=font("caption", "bold"), width=48, height=26).grid(row=0, column=1, sticky="e", padx=token("layout", "card_pad"), pady=(token("layout", "card_pad"), 0))
        ctk.CTkLabel(self, text=body, font=font("caption"), text_color=palette["muted"], justify="left", wraplength=250).grid(row=1, column=0, columnspan=2, sticky="nw", padx=token("layout", "card_pad"), pady=(space("md"), 0))


class StatusCard(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass, title: str, value: tk.StringVar, caption: tk.StringVar, palette: dict[str, str]) -> None:
        super().__init__(parent, fg_color=palette["surface"], corner_radius=token("component", "corner_md"), height=token("component", "status_card_height"))
        self.grid_propagate(False)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=title, font=font("caption"), text_color=palette["muted"]).grid(row=0, column=0, sticky="w", padx=token("layout", "card_pad"), pady=(token("layout", "card_pad"), 0))
        ctk.CTkLabel(self, textvariable=value, font=font("metric", "bold"), text_color=palette["text"]).grid(row=1, column=0, sticky="w", padx=token("layout", "card_pad"), pady=(space("sm"), 0))
        ctk.CTkLabel(self, textvariable=caption, font=font("caption"), text_color=palette["muted"]).grid(row=2, column=0, sticky="w", padx=token("layout", "card_pad"), pady=(space("xs"), 0))


class ToastBanner(ctk.CTkToplevel):
    def __init__(self, parent: ctk.CTk, message: str, palette: dict[str, str], danger: bool = False) -> None:
        super().__init__(parent)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        bg_color = palette["danger"] if danger else token("brand", "accent")
        self.configure(fg_color=bg_color)
        parent.update_idletasks()
        width = token("component", "toast_width")
        height = token("component", "toast_height")
        offset = token("component", "toast_offset")
        x = parent.winfo_rootx() + max(0, parent.winfo_width() - width - offset)
        y = parent.winfo_rooty() + offset
        self.geometry(f"{width}x{height}+{x}+{y}")
        ctk.CTkLabel(self, text=message, fg_color=bg_color, text_color=token("brand", "on_accent"), font=font("body", "bold"), justify="left", anchor="w").pack(fill="both", expand=True, padx=token("component", "toast_pad"), pady=token("component", "toast_pad"))
        self.after(token("component", "toast_duration_ms"), self.destroy)


class WatcherGui(ctk.CTk):
    def __init__(self) -> None:
        init_theme_system()
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(token("layout", "window"))
        self.minsize(*token("layout", "window_min"))

        self.process: subprocess.Popen[str] | None = None
        self.output_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.log_buffer: list[str] = []
        self.debug_window: ctk.CTkToplevel | None = None
        self.debug_text: ctk.CTkTextbox | None = None
        self.hit_count = 0
        self.telegram_test_ok = False
        self.setup_completed = False

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
        self.clipboard_assist_var = tk.BooleanVar(value=True)
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
        self._build_ui()
        self._refresh_all()
        self.after(150, self._drain_output_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_palette(self) -> None:
        self.palette = mode_palette(self.dark_mode_var.get())
        ctk.set_appearance_mode(mode_name(self.dark_mode_var.get()))
    def _build_ui(self) -> None:
        self.configure(fg_color=self.palette["bg"])
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)

        self.main = ctk.CTkFrame(self, fg_color=self.palette["bg"], corner_radius=0)
        self.main.grid(row=0, column=0, sticky="nsew", padx=token("layout", "main_pad"), pady=token("layout", "main_pad"))
        self.main.grid_columnconfigure(0, weight=1)
        if self.setup_completed:
            self._build_runtime_view(self.main)
        else:
            self._build_onboarding_view(self.main)

    def _build_onboarding_view(self, parent: ctk.CTkFrame) -> None:
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        panel = ctk.CTkFrame(parent, fg_color=self.palette["surface"], corner_radius=token("component", "corner_lg"))
        panel.grid(row=0, column=0, sticky="", padx=space("xxl"), pady=space("xxl"))
        panel.grid_columnconfigure(0, weight=1)
        pad = token("layout", "card_pad")
        ctk.CTkLabel(panel, text="ADsP Seat Watcher", font=font("hero", "bold"), text_color=self.palette["text"]).grid(row=0, column=0, sticky="w", padx=pad, pady=(pad, 0))
        ctk.CTkLabel(
            panel,
            text="처음 실행하는 사용자를 위해 휴대폰 알림, DataQ 화면 준비, 감시 방식 확인을 한 단계씩 안내합니다.",
            font=font("body"),
            text_color=self.palette["muted"],
            justify="left",
            wraplength=560,
        ).grid(row=1, column=0, sticky="w", padx=pad, pady=(space("md"), space("xl")))
        ctk.CTkButton(panel, text="초기 설정 시작", command=self._open_setup_wizard, height=44).grid(row=2, column=0, sticky="ew", padx=pad, pady=(0, space("md")))
        ctk.CTkButton(
            panel,
            text="이미 설정했습니다",
            command=self._finish_setup,
            fg_color=self.palette["surface2"],
            hover_color=self.palette["line"],
            text_color=token("brand", "accent"),
            height=42,
        ).grid(row=3, column=0, sticky="ew", padx=pad, pady=(0, space("xl")))
        ctk.CTkLabel(
            panel,
            text="자동 로그인, 자동 접수, 자동 결제, 캡차 처리는 하지 않습니다.",
            font=font("caption"),
            text_color=self.palette["muted"],
            justify="left",
        ).grid(row=4, column=0, sticky="w", padx=pad, pady=(0, pad))

    def _build_runtime_view(self, parent: ctk.CTkFrame) -> None:
        parent.grid_rowconfigure(3, weight=1)
        self._build_runtime_hero(parent)
        self._build_status(parent)
        self._build_runtime_controls(parent)

    def _build_runtime_hero(self, parent: ctk.CTkFrame) -> None:
        hero = ctk.CTkFrame(parent, fg_color=self.palette["surface2"], corner_radius=token("component", "corner_lg"), height=token("component", "hero_height"))
        hero.grid(row=0, column=0, sticky="ew", pady=(0, space("xl")))
        hero.grid_propagate(False)
        hero.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hero, text="감시 준비 완료", font=font("hero", "bold"), text_color=self.palette["text"]).grid(row=0, column=0, sticky="w", padx=token("layout", "card_pad"), pady=(token("layout", "card_pad"), 0))
        ctk.CTkLabel(hero, text="DataQ 고사장 팝업을 맨 앞에 둔 뒤 감시를 시작하세요. 좌석 후보가 감지되면 휴대폰으로 알려드립니다.", font=font("body"), text_color=self.palette["muted"], justify="left", wraplength=720).grid(row=1, column=0, sticky="w", padx=token("layout", "card_pad"), pady=(space("md"), 0))
        self.status_badge = ctk.CTkLabel(hero, textvariable=self.status_var, fg_color=self.palette["status_bg"], text_color=self.palette["status_fg"], corner_radius=999, font=font("caption", "bold"), width=78, height=32)
        self.status_badge.grid(row=0, column=1, sticky="ne", padx=token("layout", "card_pad"), pady=token("layout", "card_pad"))
        ctk.CTkButton(hero, text="감시 시작", command=self._start_watcher, width=132, height=42).grid(row=2, column=0, sticky="w", padx=token("layout", "card_pad"), pady=(space("xl"), 0))
        ctk.CTkButton(hero, text="DataQ 열기", command=lambda: webbrowser.open(DATAQ_ACCEPT_URL), fg_color=self.palette["surface"], hover_color=self.palette["line"], text_color=token("brand", "accent"), width=112, height=42).grid(row=2, column=0, sticky="w", padx=(172, 0), pady=(space("xl"), 0))

    def _build_runtime_controls(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color=self.palette["surface"], corner_radius=token("component", "corner_lg"))
        panel.grid(row=3, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        pad = token("layout", "card_pad")
        ctk.CTkLabel(panel, text="실행", font=font("section", "bold"), text_color=self.palette["text"]).grid(row=0, column=0, sticky="w", padx=pad, pady=(pad, 0))
        ctk.CTkLabel(panel, textvariable=self.primary_message_var, font=font("body"), text_color=self.palette["muted"], justify="left", wraplength=780).grid(row=1, column=0, sticky="w", padx=pad, pady=(space("sm"), space("xl")))
        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=pad)
        self.start_button = ctk.CTkButton(actions, text="감시 시작", command=self._start_watcher, width=132, height=42)
        self.start_button.grid(row=0, column=0, sticky="w")
        self.stop_button = ctk.CTkButton(actions, text="중지", command=self._stop_watcher, fg_color=self.palette["danger"], hover_color=self.palette["danger"], state="disabled", width=92, height=42)
        self.stop_button.grid(row=0, column=1, sticky="w", padx=(space("md"), 0))
        ctk.CTkButton(actions, text="설정 다시 보기", command=self._open_setup_wizard, fg_color=self.palette["surface2"], hover_color=self.palette["line"], text_color=token("brand", "accent"), height=42).grid(row=0, column=2, sticky="w", padx=(space("md"), 0))
        ctk.CTkButton(actions, text="문제 해결", command=self._open_debug_log, fg_color=self.palette["surface2"], hover_color=self.palette["line"], text_color=token("brand", "accent"), height=42).grid(row=0, column=3, sticky="w", padx=(space("md"), 0))
        ctk.CTkLabel(panel, text="실제 접수와 결제는 DataQ 화면에서 사용자가 직접 진행합니다.", font=font("caption"), text_color=self.palette["muted"], justify="left", wraplength=780).grid(row=3, column=0, sticky="w", padx=pad, pady=(space("xxl"), pad))
    def _build_sidebar(self, parent: ctk.CTkFrame) -> None:
        pad = token("layout", "sidebar_pad")
        ctk.CTkLabel(parent, text="ADsP", font=font("sidebar_title", "bold"), text_color=self.palette["text"]).grid(row=0, column=0, sticky="w", padx=pad, pady=(pad, 0))
        ctk.CTkLabel(parent, text="Seat Watcher", font=font("caption"), text_color=self.palette["muted"]).grid(row=1, column=0, sticky="w", padx=pad, pady=(space("xs"), space("xxl")))
        actions = [
            ("시작 준비", self._open_setup_wizard),
            ("Telegram 테스트", self._test_telegram),
            ("DataQ 열기", lambda: webbrowser.open(DATAQ_ACCEPT_URL)),
            ("문제 해결 로그", self._open_debug_log),
        ]
        for row, (label, command) in enumerate(actions, start=2):
            ctk.CTkButton(parent, text=label, command=command, fg_color="transparent", hover_color=self.palette["surface2"], text_color=self.palette["muted"], anchor="w").grid(row=row, column=0, sticky="ew", padx=pad, pady=space("xs"))
        ctk.CTkSwitch(parent, text="Dark mode", variable=self.dark_mode_var, command=self._toggle_theme).grid(row=9, column=0, sticky="w", padx=pad, pady=(space("xxl"), space("md")))
        ctk.CTkLabel(parent, text="자동 로그인 없음\n자동 접수 없음\n자동 결제 없음", font=font("caption"), text_color=self.palette["muted"], justify="left").grid(row=10, column=0, sticky="w", padx=pad, pady=(space("md"), 0))

    def _build_hero(self, parent: ctk.CTkFrame) -> None:
        hero = ctk.CTkFrame(parent, fg_color=self.palette["surface2"], corner_radius=token("component", "corner_lg"), height=token("component", "hero_height"))
        hero.grid(row=0, column=0, sticky="ew", pady=(0, space("xl")))
        hero.grid_propagate(False)
        hero.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hero, text="ADsP 잔여좌석 알림 도우미", font=font("hero", "bold"), text_color=self.palette["text"]).grid(row=0, column=0, sticky="w", padx=token("layout", "card_pad"), pady=(token("layout", "card_pad"), 0))
        ctk.CTkLabel(hero, text=f"{TARGET_EXAM} 고사장 팝업을 직접 열어두면 화면에 보이는 잔여좌석을 읽고 휴대폰으로 알려줍니다.", font=font("body"), text_color=self.palette["muted"], justify="left", wraplength=720).grid(row=1, column=0, sticky="w", padx=token("layout", "card_pad"), pady=(space("md"), 0))
        self.status_badge = ctk.CTkLabel(hero, textvariable=self.status_var, fg_color=self.palette["status_bg"], text_color=self.palette["status_fg"], corner_radius=999, font=font("caption", "bold"), width=78, height=32)
        self.status_badge.grid(row=0, column=1, sticky="ne", padx=token("layout", "card_pad"), pady=token("layout", "card_pad"))
        ctk.CTkButton(hero, text="감시 시작", command=self._start_watcher, width=112).grid(row=2, column=0, sticky="w", padx=token("layout", "card_pad"), pady=(space("xl"), 0))
        ctk.CTkButton(hero, text="설정 확인", command=self._open_setup_wizard, fg_color=self.palette["surface"], hover_color=self.palette["line"], text_color=token("brand", "accent"), width=112).grid(row=2, column=0, sticky="w", padx=(150, 0), pady=(space("xl"), 0))

    def _build_steps(self, parent: ctk.CTkFrame) -> None:
        steps = ctk.CTkFrame(parent, fg_color="transparent")
        steps.grid(row=1, column=0, sticky="ew", pady=(0, space("xl")))
        for col in range(3):
            steps.grid_columnconfigure(col, weight=1)
        running = self._is_running()
        telegram_ready = self._telegram_ready()
        StepCard(steps, 1, "휴대폰 알림", "Telegram 정보를 입력하고 테스트 메시지를 받아봅니다.", self.palette, done=self.telegram_test_ok).grid(row=0, column=0, sticky="ew", padx=(0, space("md")))
        StepCard(steps, 2, "DataQ 화면", "일반 Chrome에서 직접 로그인하고 고사장 팝업을 맨 앞에 둡니다.", self.palette, done=False).grid(row=0, column=1, sticky="ew", padx=(space("sm"), space("sm")))
        StepCard(steps, 3, "감시 시작", "준비가 끝나면 시작 버튼만 누릅니다. 실제 접수와 결제는 직접 합니다.", self.palette, done=running and telegram_ready).grid(row=0, column=2, sticky="ew", padx=(space("md"), 0))

    def _build_status(self, parent: ctk.CTkFrame) -> None:
        cards = ctk.CTkFrame(parent, fg_color="transparent")
        cards.grid(row=2, column=0, sticky="ew", pady=(0, space("xl")))
        for col in range(4):
            cards.grid_columnconfigure(col, weight=1)
        StatusCard(cards, "Telegram", self.telegram_value_var, self.telegram_caption_var, self.palette).grid(row=0, column=0, sticky="ew", padx=(0, space("md")))
        StatusCard(cards, "DataQ 팝업", self.popup_value_var, self.popup_caption_var, self.palette).grid(row=0, column=1, sticky="ew", padx=(space("sm"), space("sm")))
        StatusCard(cards, "마지막 확인", self.last_check_var, self.last_check_caption_var, self.palette).grid(row=0, column=2, sticky="ew", padx=(space("sm"), space("sm")))
        StatusCard(cards, "좌석 알림", self.hit_value_var, self.hit_caption_var, self.palette).grid(row=0, column=3, sticky="ew", padx=(space("md"), 0))

    def _build_controls(self, parent: ctk.CTkFrame) -> None:
        panel = ctk.CTkFrame(parent, fg_color=self.palette["surface"], corner_radius=token("component", "corner_lg"))
        panel.grid(row=3, column=0, sticky="nsew")
        panel.grid_columnconfigure(0, weight=1)
        pad = token("layout", "card_pad")
        ctk.CTkLabel(panel, text="실행", font=font("section", "bold"), text_color=self.palette["text"]).grid(row=0, column=0, sticky="w", padx=pad, pady=(pad, 0))
        ctk.CTkLabel(panel, textvariable=self.primary_message_var, font=font("body"), text_color=self.palette["muted"], justify="left", wraplength=780).grid(row=1, column=0, sticky="w", padx=pad, pady=(space("sm"), space("xl")))
        actions = ctk.CTkFrame(panel, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", padx=pad)
        self.start_button = ctk.CTkButton(actions, text="감시 시작", command=self._start_watcher)
        self.start_button.grid(row=0, column=0, sticky="w")
        self.stop_button = ctk.CTkButton(actions, text="중지", command=self._stop_watcher, fg_color=self.palette["danger"], hover_color=self.palette["danger"], state="disabled")
        self.stop_button.grid(row=0, column=1, sticky="w", padx=(space("md"), 0))
        ctk.CTkButton(actions, text="초기 설정", command=self._open_setup_wizard, fg_color=self.palette["surface2"], hover_color=self.palette["line"], text_color=token("brand", "accent")).grid(row=0, column=2, sticky="w", padx=(space("md"), 0))
        ctk.CTkButton(actions, text="Telegram 테스트", command=self._test_telegram, fg_color=self.palette["surface2"], hover_color=self.palette["line"], text_color=token("brand", "accent")).grid(row=0, column=3, sticky="w", padx=(space("md"), 0))
        ctk.CTkLabel(panel, text="이 도구는 화면 감시와 알림만 수행합니다. 로그인, 접수, 결제, 캡차 처리는 사용자가 직접 합니다.", font=font("caption"), text_color=self.palette["muted"], justify="left", wraplength=780).grid(row=3, column=0, sticky="w", padx=pad, pady=(space("xxl"), pad))
    def _toggle_theme(self) -> None:
        self._apply_palette()
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
                self.status_badge.configure(fg_color=self.palette["running_bg"], text_color=self.palette["running_fg"])
        else:
            self.status_var.set("대기 중")
            if hasattr(self, "status_badge"):
                self.status_badge.configure(fg_color=self.palette["status_bg"], text_color=self.palette["status_fg"])

    def _open_setup_wizard(self) -> None:
        self._open_step(0)

    def _finish_setup(self, show_message: bool = False) -> None:
        self.setup_completed = True
        self._refresh_all()
        self._rebuild_main()
        if show_message:
            messagebox.showinfo("설정 완료", "설정이 완료되었습니다. 이제 감시 시작만 누르면 됩니다.")
    def _open_step(self, index: int) -> None:
        steps = [
            ("Telegram 알림", "휴대폰으로 받을 Bot token과 Chat ID를 입력합니다.", self._telegram_step),
            ("DataQ 화면 준비", "일반 Chrome에서 직접 로그인하고 고사장 팝업을 맨 앞으로 둡니다.", self._browser_step),
            ("감시 방식", "대부분의 사용자는 기본값 그대로 사용하면 됩니다.", self._behavior_step),
            ("고급 OCR", "화면 영역이 맞지 않을 때만 조정합니다.", self._ocr_step),
        ]
        if index >= len(steps):
            self._finish_setup(show_message=True)
            return
        title, subtitle, builder = steps[index]
        window = ctk.CTkToplevel(self)
        window.title(f"{APP_TITLE} - {title}")
        window.geometry(token("layout", "modal"))
        window.configure(fg_color=self.palette["bg"])
        window.transient(self)
        window.grab_set()
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        pad = token("layout", "modal_pad")
        header = ctk.CTkFrame(window, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=pad, pady=(pad, space("md")))
        ctk.CTkLabel(header, text=f"{index + 1}/{len(steps)}", font=font("caption"), text_color=self.palette["muted"]).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(header, text=title, font=font("modal_title", "bold"), text_color=self.palette["text"]).grid(row=1, column=0, sticky="w", pady=(space("xs"), 0))
        ctk.CTkLabel(header, text=subtitle, font=font("body"), text_color=self.palette["muted"], wraplength=500, justify="left").grid(row=2, column=0, sticky="w", pady=(space("md"), 0))
        content = ctk.CTkFrame(window, fg_color=self.palette["surface"], corner_radius=token("component", "corner_lg"))
        content.grid(row=1, column=0, sticky="nsew", padx=pad, pady=(0, space("xl")))
        content.grid_columnconfigure(0, weight=1)
        builder(content)
        footer = ctk.CTkFrame(window, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=pad, pady=(0, pad))
        footer.grid_columnconfigure(1, weight=1)
        if index > 0:
            ctk.CTkButton(footer, text="이전", command=lambda: self._go_step(window, index - 1), fg_color=self.palette["surface2"], hover_color=self.palette["line"], text_color=token("brand", "accent")).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(footer, text="다음" if index < len(steps) - 1 else "완료", command=lambda: self._go_step(window, index + 1)).grid(row=0, column=2, sticky="e")

    def _go_step(self, window: ctk.CTkToplevel, index: int) -> None:
        if index == 1:
            if not self._telegram_ready():
                messagebox.showwarning("Telegram 확인", "Bot token과 Chat ID를 입력한 뒤 진행하세요.")
                return
            if not self.telegram_test_ok:
                messagebox.showwarning("Telegram 확인", "테스트 전송을 완료한 뒤 진행하세요.")
                return
        self._refresh_all()
        window.grab_release()
        window.destroy()
        self.after(80, lambda: self._open_step(index))
    def _telegram_step(self, parent: ctk.CTkFrame) -> None:
        self._field(parent, 0, FieldSpec("Bot token", self.token_var, "BotFather에서 받은 토큰입니다. 파일에 저장하지 않습니다.", True))
        self._field(parent, 1, FieldSpec("Chat ID", self.chat_id_var, "getUpdates 결과의 chat.id 숫자입니다."))
        ctk.CTkButton(parent, text="테스트 전송", command=self._test_telegram).grid(row=2, column=0, sticky="e", padx=token("layout", "modal_card_pad"), pady=(space("xl"), token("layout", "modal_card_pad")))

    def _browser_step(self, parent: ctk.CTkFrame) -> None:
        pad = token("layout", "modal_card_pad")
        for row, text in enumerate(["DataQ 접수 화면을 엽니다.", "사용자가 직접 로그인합니다.", "ADsP 고사장 목록 팝업을 열고 고사장 목록 팝업을 화면 맨 앞으로 둡니다."]):
            ctk.CTkLabel(parent, text=f"{row + 1}. {text}", font=font("body"), text_color=self.palette["text"]).grid(row=row, column=0, sticky="w", padx=pad, pady=(pad if row == 0 else space("sm"), 0))
        ctk.CTkButton(parent, text="DataQ 접수 화면 열기", command=lambda: webbrowser.open(DATAQ_ACCEPT_URL)).grid(row=3, column=0, sticky="ew", padx=pad, pady=(space("xl"), space("lg")))
        self._field(parent, 4, FieldSpec("포커스 클릭 좌표", self.focus_click_var, "기본값 900,500. 스크롤이 움직이지 않을 때만 조정하세요."))

    def _behavior_step(self, parent: ctk.CTkFrame) -> None:
        self._field(parent, 0, FieldSpec("확인 주기(초)", self.interval_var, "권장값은 40초입니다."))
        self._field(parent, 1, FieldSpec("스캔 화면 수", self.pages_var, "목록 전체를 훑기 위한 화면 수입니다. 권장값은 15입니다."))
        self._field(parent, 2, FieldSpec("휠 칸 수", self.wheel_notches_var, "한 번에 내릴 스크롤 양입니다. 권장값은 9입니다."))
        checks = ctk.CTkFrame(parent, fg_color="transparent")
        checks.grid(row=3, column=0, sticky="ew", padx=token("layout", "modal_card_pad"), pady=(space("md"), token("layout", "modal_card_pad")))
        for row, (label, var) in enumerate([("새로고침 사용", self.refresh_var), ("양식 다시 제출 확인 처리", self.confirm_resubmit_var), ("절전 방지", self.keep_awake_var), ("표 자동 복사+한글 보정", self.clipboard_assist_var), ("시작 시 Telegram 테스트", self.telegram_test_on_start_var), ("Windows 메시지박스 사용", self.message_box_var)]):
            ctk.CTkCheckBox(checks, text=label, variable=var, command=self._refresh_all).grid(row=row, column=0, sticky="w", pady=space("xs"))

    def _ocr_step(self, parent: ctk.CTkFrame) -> None:
        self._field(parent, 0, FieldSpec("전체 OCR 영역", self.bbox_var, "기본값: 0,90,1845,980"))
        self._field(parent, 1, FieldSpec("잔여좌석 열 영역", self.seat_bbox_var, "기본값: 1535,90,1645,980"))
        ctk.CTkCheckBox(parent, text="잔여좌석 열 보조 OCR 사용", variable=self.seat_column_var, command=self._refresh_all).grid(row=2, column=0, sticky="w", padx=token("layout", "modal_card_pad"), pady=(space("md"), 0))
        self._field(parent, 3, FieldSpec("OCR 원문 저장 파일", self.save_text_var, "문제 해결용 텍스트 파일명입니다."))

    def _field(self, parent: ctk.CTkFrame, row: int, spec: FieldSpec) -> None:
        pad = token("layout", "modal_card_pad")
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=pad, pady=(pad if row == 0 else space("md"), 0))
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=spec.label, font=font("body", "bold"), text_color=self.palette["text"]).grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(frame, textvariable=spec.variable, show="*" if spec.secret else "").grid(row=1, column=0, sticky="ew", pady=(space("sm"), space("xs")))
        ctk.CTkLabel(frame, text=spec.helper, font=font("caption"), text_color=self.palette["muted"], justify="left", wraplength=480).grid(row=2, column=0, sticky="w")
        spec.variable.trace_add("write", lambda *_args: self._refresh_all())
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
        if self.message_box_var.get():
            cmd.append("--message-box")
        if self.telegram_test_on_start_var.get():
            cmd.append("--telegram-test")
        if self.seat_column_var.get():
            cmd.extend(["--seat-bbox", self.seat_bbox_var.get().strip() or DEFAULT_SEAT_BBOX])
        if self.clipboard_assist_var.get():
            cmd.append("--clipboard-assist")
            cmd.append("--auto-copy-clipboard")
        return cmd

    def _refresh_command_preview(self) -> None:
        self.command_var.set(" ".join(self._build_command()))

    def _remember_log(self, text: str) -> None:
        if not text:
            return
        self.log_buffer.append(text)
        if len(self.log_buffer) > 800:
            self.log_buffer = self.log_buffer[-800:]
        if self.debug_text is not None and self.debug_text.winfo_exists():
            self.debug_text.configure(state="normal")
            self.debug_text.insert("end", text)
            self.debug_text.see("end")
            self.debug_text.configure(state="disabled")

    def _append_output(self, text: str) -> None:
        self._remember_log(text)
        self._parse_runtime_event(text)

    def _parse_runtime_event(self, text: str) -> None:
        if "활성 창 새로고침" in text:
            now = time.strftime("%H:%M:%S")
            self.popup_value_var.set("갱신됨")
            self.popup_caption_var.set(f"{now} 새로고침 완료")
        check_match = re.search(r"\[(\d{4}-\d{2}-\d{2} [^\]]+)\]\s+팝업 OCR 확인:\s+(\d+)건", text)
        if check_match:
            self.last_check_var.set(check_match.group(1).split()[-1])
            self.last_check_caption_var.set(f"감지 후보 {check_match.group(2)}건")
        seat_match = re.search(r"OCR No\.(\d+)\s+잔여좌석\s+(\d+)석", text)
        if seat_match is None:
            enriched_match = re.search(r"잔여좌석\s+(\d+)석\s+-\s+No\.(\d+)", text)
            if enriched_match:
                seat_match = re.match(r"(\d+)\|(\d+)", f"{enriched_match.group(2)}|{enriched_match.group(1)}")
        if seat_match:
            self.hit_count += 1
            self.hit_value_var.set(str(self.hit_count))
            self.hit_caption_var.set(f"No.{seat_match.group(1)} / {seat_match.group(2)}석")
            self._show_toast(f"잔여좌석 후보 감지: No.{seat_match.group(1)} {seat_match.group(2)}석")
        self._refresh_all()

    def _test_telegram(self) -> None:
        token_value = self.token_var.get().strip()
        chat_id = self.chat_id_var.get().strip()
        if not token_value or not chat_id:
            self._show_toast("Telegram Bot token과 Chat ID를 먼저 입력하세요.", danger=True)
            return
        threading.Thread(target=self._send_test_telegram, args=(token_value, chat_id), daemon=True).start()

    def _send_test_telegram(self, token_value: str, chat_id: str) -> None:
        try:
            ok = send_telegram(token_value, chat_id, "ADsP Seat Watcher 테스트 알림입니다.")
        except Exception as exc:  # pragma: no cover - network dependent
            self.output_queue.put(("telegram_error", f"Telegram 테스트 실패: {exc}\n"))
            return
        if ok:
            self.output_queue.put(("telegram_ok", "Telegram 테스트 전송 완료\n"))
        else:
            self.output_queue.put(("telegram_error", "Telegram 테스트 실패: token/chat id를 확인하세요.\n"))

    def _start_watcher(self) -> None:
        if self._is_running():
            self._show_toast("이미 감시가 실행 중입니다.")
            return
        if not self._telegram_ready():
            if not messagebox.askyesno("Telegram 미설정", "휴대폰 알림 정보가 없습니다. 그래도 시작할까요?"):
                return
        env = os.environ.copy()
        token_value = self.token_var.get().strip()
        chat_id = self.chat_id_var.get().strip()
        if token_value:
            env["TELEGRAM_BOT_TOKEN"] = token_value
        if chat_id:
            env["TELEGRAM_CHAT_ID"] = chat_id
        cmd = self._build_command()
        self._refresh_command_preview()
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(BASE_DIR),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as exc:
            self._show_toast(f"실행 실패: {exc}", danger=True)
            return
        self._remember_log(f"\n$ {' '.join(cmd)}\n")
        self.reader_thread = threading.Thread(target=self._read_process_output, daemon=True)
        self.reader_thread.start()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self._show_toast("감시를 시작했습니다.")
        self._refresh_all()

    def _read_process_output(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for line in process.stdout:
            self.output_queue.put(("process", line))
        code = process.wait()
        self.output_queue.put(("process_exit", f"\n프로세스가 종료되었습니다. code={code}\n"))

    def _stop_watcher(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            self._show_toast("감시를 중지했습니다.")
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self._refresh_all()

    def _drain_output_queue(self) -> None:
        try:
            while True:
                kind, text = self.output_queue.get_nowait()
                if kind == "process":
                    self._append_output(text)
                elif kind == "process_exit":
                    self._remember_log(text)
                    if hasattr(self, "start_button"):
                        self.start_button.configure(state="normal")
                    if hasattr(self, "stop_button"):
                        self.stop_button.configure(state="disabled")
                    self._refresh_all()
                elif kind == "telegram_ok":
                    self.telegram_test_ok = True
                    self.telegram_value_var.set("테스트 완료")
                    self.telegram_caption_var.set("휴대폰 알림 연결됨")
                    self._remember_log(text)
                    self._show_toast("Telegram 테스트 전송 완료")
                    self._rebuild_main()
                elif kind == "telegram_error":
                    self.telegram_test_ok = False
                    self.telegram_caption_var.set("연결 실패")
                    self._remember_log(text)
                    self._show_toast(text.strip(), danger=True)
        except queue.Empty:
            pass
        self.after(150, self._drain_output_queue)

    def _open_debug_log(self) -> None:
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.focus()
            return
        window = ctk.CTkToplevel(self)
        self.debug_window = window
        window.title(f"{APP_TITLE} - 문제 해결 로그")
        window.geometry(token("layout", "debug"))
        window.configure(fg_color=self.palette["bg"])
        window.grid_columnconfigure(0, weight=1)
        window.grid_rowconfigure(1, weight=1)
        pad = token("layout", "modal_pad")
        ctk.CTkLabel(window, text="문제 해결 로그", font=font("modal_title", "bold"), text_color=self.palette["text"]).grid(row=0, column=0, sticky="w", padx=pad, pady=(pad, space("md")))
        text = ctk.CTkTextbox(window, font=("Consolas", token("typography", "log")), fg_color=self.palette["log_bg"], text_color=self.palette["log_fg"])
        self.debug_text = text
        text.grid(row=1, column=0, sticky="nsew", padx=pad, pady=(0, space("md")))
        text.insert("end", "".join(self.log_buffer) or "아직 로그가 없습니다.\n")
        text.configure(state="disabled")
        footer = ctk.CTkFrame(window, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=pad, pady=(0, pad))
        ctk.CTkButton(footer, text="실행 명령 복사", command=self._copy_command).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(footer, text="닫기", command=self._close_debug_log, fg_color=self.palette["surface2"], hover_color=self.palette["line"], text_color=token("brand", "accent")).grid(row=0, column=1, sticky="w", padx=(space("md"), 0))
        window.protocol("WM_DELETE_WINDOW", self._close_debug_log)

    def _close_debug_log(self) -> None:
        if self.debug_window is not None and self.debug_window.winfo_exists():
            self.debug_window.destroy()
        self.debug_window = None
        self.debug_text = None

    def _copy_command(self) -> None:
        self._refresh_command_preview()
        self.clipboard_clear()
        self.clipboard_append(self.command_var.get())
        self._show_toast("실행 명령을 복사했습니다.")

    def _rebuild_main(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._build_ui()
        if self.setup_completed and self._is_running():
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="normal")
        self._refresh_all()

    def _on_close(self) -> None:
        if self._is_running():
            if not messagebox.askyesno("종료 확인", "감시가 실행 중입니다. 중지하고 종료할까요?"):
                return
            self._stop_watcher()
        self.destroy()


def main() -> None:
    init_theme_system()
    app = WatcherGui()
    app.mainloop()


if __name__ == "__main__":
    main()
