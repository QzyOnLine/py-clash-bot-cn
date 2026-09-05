from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
import tkinter.filedialog
import webbrowser
from collections.abc import Callable
from pathlib import Path
from tkinter import messagebox
from typing import TYPE_CHECKING

import ttkbootstrap as ttk
from ttkbootstrap.constants import LEFT, READONLY, YES, X
from ttkbootstrap.style import Colors
from ttkbootstrap.widgets import ToolTip

from pyclashbot.emulators import EmulatorType, get_available_emulators
from pyclashbot.interface.config import (
    BLUESTACKS_DEVICE_CONFIG,
    BLUESTACKS_SETTINGS,
    GOOGLE_PLAY_DEVICE_CONFIG,
    GOOGLE_PLAY_SETTINGS,
    JOBS,
    MEMU_SETTINGS,
    ComboConfig,
    JobConfig,
)
from pyclashbot.interface.enums import (
    BATTLE_STAT_FIELDS,
    BATTLE_STAT_LABELS,
    BOT_STAT_FIELDS,
    BOT_STAT_LABELS,
    COLLECTION_STAT_FIELDS,
    COLLECTION_STAT_LABELS,
    WIN_RATE_STAT_FIELDS,
    WIN_RATE_STAT_LABELS,
    BotStatField,
    DerivedStatField,
    StatField,
    UIField,
    has_start_ready_job,
)
from pyclashbot.interface.widgets import DualRingGauge
from pyclashbot.utils.platform import (
    LOW_DISK_SPACE_BYTES,
    clear_recordings,
    get_recordings_dir,
    is_windows,
    recordings_drive_free_bytes,
    recordings_total_bytes_all_locations,
    validate_recordings_path,
)

if TYPE_CHECKING:
    from collections.abc import Callable


# Common MuMu install roots whose <root>\shell dir holds adb.exe/MuMuManager.exe.
# Kept in this list so the UI's ADB device scan/name lookup works even when the
# GUI is launched without 启动bot.bat (which normally adds the dir to PATH).
_MUMU_INSTALL_ROOTS = (
    r"D:\Program Files\Netease\MuMu Player 12",
    r"C:\Program Files\Netease\MuMu Player 12",
    r"D:\Program Files\Netease\MuMu Player 6",
    r"C:\Program Files\Netease\MuMu Player 6",
    r"C:\Program Files\Netease\MuMu Player",
)


def _ensure_mumu_on_path() -> None:
    """Prepend the MuMu shell dir (adb.exe/MuMuManager.exe) to PATH if found.

    Runs once at UI startup so both "adb" (used by AdbController.discover_devices
    and the refresh scan) and "MuMuManager" (device-name lookup) resolve without
    relying on the launcher batch file.
    """
    for root in _MUMU_INSTALL_ROOTS:
        shell = os.path.join(root, "shell")
        if os.path.isfile(os.path.join(shell, "adb.exe")):
            path_entries = os.environ.get("PATH", "").split(os.pathsep)
            if shell not in path_entries:
                os.environ["PATH"] = shell + os.pathsep + os.environ.get("PATH", "")
            return


class _AdbUiLogger:
    """Minimal no-op logger so AdbController helpers can run from the UI thread."""
    @staticmethod
    def change_status(*_args, **_kwargs):
        pass

    @staticmethod
    def log(*_args, **_kwargs):
        pass


# Jobs tab layout (display only — JOBS in config.py keeps bot state-machine order).
# Two columns of section groups to fit the Jobs tab at default height.
_JOB_TAB_COLUMNS: tuple[tuple[tuple[str, tuple[UIField, ...]], ...], ...] = (
    (
        (
            "对战",
            (
                UIField.CLASSIC_1V1_USER_TOGGLE,
                UIField.CLASSIC_2V2_USER_TOGGLE,
                UIField.TROPHY_ROAD_USER_TOGGLE,
                UIField.WAR_USER_TOGGLE,
            ),
        ),
        (
            "收藏",
            (
                UIField.CARD_UPGRADE_USER_TOGGLE,
                UIField.UPGRADE_PRINCESS_USER_TOGGLE,
                UIField.CARD_MASTERY_USER_TOGGLE,
                UIField.SHOP_DAILY_OFFER_USER_TOGGLE,
            ),
        ),
        ("账号", (UIField.SWITCH_ACCOUNTS_USER_TOGGLE,)),
    ),
    (
        (
            "部落聊天",
            (
                UIField.CLAN_DONATE_USER_TOGGLE,
                UIField.CLAN_REQUEST_CARDS_USER_TOGGLE,
                UIField.CLAN_CLAIM_GIFTS_USER_TOGGLE,
            ),
        ),
        (
            "卡组",
            (
                UIField.RANDOM_DECKS_USER_TOGGLE,
                UIField.CYCLE_DECKS_USER_TOGGLE,
                UIField.RANDOM_PLAYS_USER_TOGGLE,
            ),
        ),
        ("选项", (UIField.DISABLE_WIN_TRACK_TOGGLE,)),
    ),
)

# Stored disable_win_track_toggle is inverted in the UI — see _job_toggle_default().
_WIN_TRACK_UI_FIELD = UIField.DISABLE_WIN_TRACK_TOGGLE
_JOB_SPINBOX_LABELS: dict[UIField, str] = {
    UIField.DECK_NUMBER_SELECTION: "卡组槽位：",
    UIField.MAX_DECK_SELECTION: "卡组数：",
    UIField.MAX_ACCOUNT_SELECTION: "账号数：",
}
_JOB_TOGGLE_ON_STYLE = "round-toggle"
_JOB_TOGGLE_OFF_STYLE = "secondary-round-toggle"
_TAB_SECTION_STYLE = "TabSection.TLabelframe"
_TAB_SECTION_PADDING = (8, 6)
_TAB_CONTAINER_PADDING = (10, 8)
_NOTEBOOK_STYLE = "App.TNotebook"
_NOTEBOOK_TAB_STYLE = "App.TNotebook.Tab"
_NOTEBOOK_TAB_COUNT = 4
_NOTEBOOK_TAB_WIDTH_DIVISOR = 6  # Tcl tab width units vs notebook pixels (approx.)
_IDLE_STATUS = "空闲"
_START_BLOCKED_MESSAGE = "请至少启用一个对战、部落聊天或收藏任务才能启动。"

# ttkbootstrap built-in theme names -> Chinese display labels. The underlying
# theme value (English) is what gets persisted to settings, so only the combo
# shows the Chinese label while the variable keeps the English name.
_THEME_LABELS = {
    "cerculean": "天青",
    "cosmo": "宇宙",
    "cyborg": "赛博",
    "darkly": "暗黑",
    "flatly": "扁平",
    "journal": "报刊",
    "litera": "文学",
    "lumen": "流明",
    "minty": "薄荷",
    "morph": "形态",
    "pulse": "脉搏",
    "sandstone": "砂岩",
    "simplex": "简约",
    "solar": "日光",
    "superhero": "超级英雄",
    "united": "联合",
    "vapor": "蒸汽波",
    "yeti": "雪人",
}
_ACTION_BUTTON_IPAD = (18, 2)
_WIN_GAUGE_DIAMETER = 58
_WIN_GAUGE_THICKNESS = 8
_APP_ICON_NAME = "pixel-pycb.ico"
_DISCORD_INVITE_URL = "https://pyclashbot.app/discord/invite"
_GITHUB_PROJECT_URL = "https://github.com/pyclashbot/py-clash-bot"
_UPLOAD_RECORDINGS_URL = "https://www.royaletrainer.com/upload"
# How often the "recordings using N GB" note recomputes folder size (ms).
_RECORDINGS_SIZE_REFRESH_MS = 3 * 60 * 1000  # 3 minutes
_DISCORD_BRAND = "#5865F2"
_GITHUB_BRAND = "#238636"
_DISCORD_BUTTON_STYLE = "App.Discord.TButton"
_GITHUB_BUTTON_STYLE = "App.GitHub.TButton"


def no_jobs_popup() -> None:
    messagebox.showerror("无法启动", _START_BLOCKED_MESSAGE)


class PyClashBotUI(ttk.Window):
    DEFAULT_THEME = "darkly"
    DEFAULT_WIDTH = 520
    DEFAULT_HEIGHT = 540
    MIN_WIDTH = 520
    MIN_HEIGHT = 540

    def __init__(self) -> None:
        super().__init__(themename=self.DEFAULT_THEME)
        self.title("py-clash-bot")
        self._set_window_icon()
        self.geometry(f"{self.DEFAULT_WIDTH}x{self.DEFAULT_HEIGHT}")
        self.resizable(True, True)
        self.minsize(self.MIN_WIDTH, self.MIN_HEIGHT)

        # Make adb/MuMuManager resolvable even if the GUI wasn't launched via
        # 启动bot.bat (device scan + name lookup depend on them).
        _ensure_mumu_on_path()

        self._style = ttk.Style()
        current_theme = self._style.theme_use()
        if not current_theme:
            current_theme = self.DEFAULT_THEME
        self.theme_var = ttk.StringVar(value=current_theme)
        self.discord_rpc_var = ttk.BooleanVar(value=False)
        self.record_fights_var = ttk.BooleanVar(value=False)
        # Show the resolved default location in the box until the user picks a custom one.
        self.recording_folder_path_var = ttk.StringVar(value=get_recordings_dir())
        self.advanced_settings_var = ttk.BooleanVar(value=False)
        self._config_callback: Callable[[dict[str, object]], None] | None = None
        self._open_logs_callback: Callable[[], None] | None = None
        self._open_recordings_callback: Callable[[], None] | None = None
        self._config_widgets: dict[str, tk.Widget] = {}
        self._job_toggle_checkbuttons: dict[UIField, ttk.Checkbutton] = {}
        self._job_row_extras: dict[UIField, list[tk.Widget]] = {}
        self._job_extra_spinboxes: dict[UIField, ttk.Spinbox] = {}
        self._theme_labels: list[tk.Widget] = []
        self._muted_labels: list[tk.Widget] = []
        self._stat_accent_labels: list[tk.Widget] = []
        self._traces: list[tuple[tk.Variable, str]] = []
        self._suspend_traces = 0
        self._button_state = "idle"
        self.deck_var: ttk.StringVar | None = None
        self.max_deck_var: ttk.StringVar | None = None
        self.max_account_var: ttk.StringVar | None = None

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)  # Tab area absorbs extra height
        self.rowconfigure(1, weight=0)  # Status log + Start stay compact

        self._build_tabs()
        self._build_bottom_row()
        self._sync_brand_button_styles()
        self._refresh_theme_colours()

    def register_config_callback(self, callback: Callable[[dict[str, object]], None]) -> None:
        self._config_callback = callback

    def register_open_logs_callback(self, callback: Callable[[], None]) -> None:
        self._open_logs_callback = callback

    def register_open_recordings_callback(self, callback: Callable[[], None]) -> None:
        self._open_recordings_callback = callback

    def get_all_values(self) -> dict[str, object]:
        values: dict[str, object] = {}
        for field, var in self.jobs_vars.items():
            stored = bool(var.get())
            if field == _WIN_TRACK_UI_FIELD:
                stored = not stored
            values[field.value] = stored

        values[UIField.DECK_NUMBER_SELECTION.value] = self._safe_int(
            self.deck_var.get() if self.deck_var is not None else "2", fallback=2
        )
        values[UIField.CYCLE_DECKS_USER_TOGGLE.value] = bool(self.jobs_vars[UIField.CYCLE_DECKS_USER_TOGGLE].get())
        values[UIField.MAX_DECK_SELECTION.value] = self._safe_int(
            self.max_deck_var.get() if self.max_deck_var is not None else "2", fallback=2
        )
        values[UIField.SWITCH_ACCOUNTS_USER_TOGGLE.value] = bool(
            self.jobs_vars[UIField.SWITCH_ACCOUNTS_USER_TOGGLE].get()
        )
        values[UIField.MAX_ACCOUNT_SELECTION.value] = self._safe_int(
            self.max_account_var.get() if self.max_account_var is not None else "2", fallback=2
        )
        emulator_choice = self.emulator_var.get()
        values[UIField.MEMU_EMULATOR_TOGGLE.value] = emulator_choice == EmulatorType.MEMU
        values[UIField.GOOGLE_PLAY_EMULATOR_TOGGLE.value] = emulator_choice == EmulatorType.GOOGLE_PLAY
        values[UIField.BLUESTACKS_EMULATOR_TOGGLE.value] = emulator_choice == EmulatorType.BLUESTACKS
        values[UIField.ADB_TOGGLE.value] = emulator_choice == EmulatorType.ADB

        memu_render = self.memu_render_var.get()
        values[UIField.DIRECTX_TOGGLE.value] = memu_render == "DirectX"
        values[UIField.OPENGL_TOGGLE.value] = memu_render == "OpenGL"

        bs_render = self.bs_render_var.get()
        values[UIField.BS_RENDERER_DX.value] = bs_render == "DirectX"
        values[UIField.BS_RENDERER_GL.value] = bs_render == "OpenGL"
        values[UIField.BS_RENDERER_VK.value] = bs_render == "Vulkan"

        for field, var in self.gp_vars.items():
            values[field.value] = var.get()

        values[UIField.ADB_SERIAL.value] = self.adb_serial_var.get()
        values[UIField.GP_DEVICE_SERIAL.value] = self.gp_device_serial_var.get()
        values[UIField.BS_DEVICE_SERIAL.value] = self.bs_device_serial_var.get()

        values[UIField.THEME_NAME.value] = self.theme_var.get() or self.DEFAULT_THEME
        values[UIField.DISCORD_RPC_TOGGLE.value] = bool(self.discord_rpc_var.get())
        values[UIField.RECORD_FIGHTS_TOGGLE.value] = bool(self.record_fights_var.get())
        values[UIField.RECORDING_FOLDER_PATH.value] = self.recording_folder_path_var.get() or ""
        return values

    def set_all_values(self, values: dict[str, object]) -> None:
        theme_value: str | None = None
        self._suspend_traces += 1
        try:
            for field, var in self.jobs_vars.items():
                if field.value in values:
                    ui_value = bool(values[field.value])
                    if field == _WIN_TRACK_UI_FIELD:
                        ui_value = not ui_value
                    var.set(ui_value)

            if UIField.DECK_NUMBER_SELECTION.value in values and self.deck_var is not None:
                self.deck_var.set(str(values[UIField.DECK_NUMBER_SELECTION.value]))
            if UIField.MAX_DECK_SELECTION.value in values and self.max_deck_var is not None:
                self.max_deck_var.set(str(values[UIField.MAX_DECK_SELECTION.value]))
            if UIField.MAX_ACCOUNT_SELECTION.value in values and self.max_account_var is not None:
                self.max_account_var.set(str(values[UIField.MAX_ACCOUNT_SELECTION.value]))
            if UIField.THEME_NAME.value in values:
                theme_value = str(values[UIField.THEME_NAME.value])

            # Determine saved emulator choice; default to current selection if no data provided
            saved_emulator = self.emulator_var.get()
            emulator_keys = {
                UIField.GOOGLE_PLAY_EMULATOR_TOGGLE.value,
                UIField.BLUESTACKS_EMULATOR_TOGGLE.value,
                UIField.ADB_TOGGLE.value,
                UIField.MEMU_EMULATOR_TOGGLE.value,
            }
            if emulator_keys & values.keys():
                if values.get(UIField.GOOGLE_PLAY_EMULATOR_TOGGLE.value):
                    saved_emulator = EmulatorType.GOOGLE_PLAY
                elif values.get(UIField.BLUESTACKS_EMULATOR_TOGGLE.value):
                    saved_emulator = EmulatorType.BLUESTACKS
                elif values.get(UIField.ADB_TOGGLE.value):
                    saved_emulator = EmulatorType.ADB
                elif values.get(UIField.MEMU_EMULATOR_TOGGLE.value):
                    saved_emulator = EmulatorType.MEMU
            # Use saved choice if available on this platform, otherwise fallback
            available = get_available_emulators()
            if saved_emulator in available:
                self.emulator_var.set(saved_emulator)
            elif available:
                self.emulator_var.set(available[0])

            if values.get(UIField.DIRECTX_TOGGLE.value):
                self.memu_render_var.set("DirectX")
            elif values.get(UIField.OPENGL_TOGGLE.value):
                self.memu_render_var.set("OpenGL")

            if values.get(UIField.BS_RENDERER_VK.value):
                self.bs_render_var.set("Vulkan")
            elif values.get(UIField.BS_RENDERER_DX.value):
                self.bs_render_var.set("DirectX")
            elif values.get(UIField.BS_RENDERER_GL.value):
                self.bs_render_var.set("OpenGL")

            for field, var in self.gp_vars.items():
                config = next((c for c in GOOGLE_PLAY_SETTINGS if c.key == field), None)
                if field.value in values and values[field.value] is not None:
                    var.set(str(values[field.value]))
                elif config:
                    var.set(str(config.default))

            if UIField.ADB_SERIAL.value in values:
                self.adb_serial_var.set(str(values[UIField.ADB_SERIAL.value]))
                self._adb_serial_display_var.set(
                    self._adb_serial_labels.get(self.adb_serial_var.get(), self.adb_serial_var.get())
                )
            if UIField.GP_DEVICE_SERIAL.value in values:
                self.gp_device_serial_var.set(str(values[UIField.GP_DEVICE_SERIAL.value]))
            if UIField.BS_DEVICE_SERIAL.value in values:
                self.bs_device_serial_var.set(str(values[UIField.BS_DEVICE_SERIAL.value]))

            self._update_google_play_comboboxes()

        finally:
            self._suspend_traces -= 1

        if theme_value is not None:
            # Defer theme apply so combobox popdown widgets exist (avoids TclError on macOS).
            self.after_idle(lambda t=theme_value: self._apply_theme(t))

        if self._job_extra_spinboxes:
            self._sync_job_extra_spinboxes()
        if self._job_toggle_checkbuttons:
            self._sync_all_job_toggle_appearances()
        if self._button_state == "idle":
            self._sync_start_button_readiness()

        if UIField.DISCORD_RPC_TOGGLE.value in values:
            self.discord_rpc_var.set(bool(values[UIField.DISCORD_RPC_TOGGLE.value]))

        if UIField.RECORD_FIGHTS_TOGGLE.value in values:
            self.record_fights_var.set(bool(values[UIField.RECORD_FIGHTS_TOGGLE.value]))

        if UIField.RECORDING_FOLDER_PATH.value in values:
            saved_path = str(values[UIField.RECORDING_FOLDER_PATH.value])
            # An empty saved value means "default" -- show the resolved default path.
            self.recording_folder_path_var.set(saved_path or get_recordings_dir())

        self._show_current_emulator_settings()

    def set_button_state(self, state: str) -> None:
        """Set the main button state: 'idle' or 'running'."""
        self._button_state = state
        if state == "idle":
            self._sync_start_button_readiness()
        elif state == "running":
            self.main_btn.configure(text="停止", bootstyle="danger", state=tk.NORMAL)

        # Disable/enable config widgets based on running state
        running = state == "running"
        for key, widget in self._config_widgets.items():
            if key == "main_btn":
                continue
            try:
                if isinstance(widget, ttk.Combobox):
                    if key == "emulator_combobox":
                        widget.configure(state=tk.DISABLED if running else READONLY)
                    elif widget in (
                        self.adb_serial_combo,
                        self.gp_device_serial_combo,
                        self.bs_device_serial_combo,
                    ):
                        widget.configure(state=tk.DISABLED if running else tk.NORMAL)
                    else:
                        widget.configure(state=tk.DISABLED if running else READONLY)
                elif isinstance(widget, ttk.Spinbox):
                    if widget in self._job_extra_spinboxes.values():
                        continue
                    widget.configure(state=tk.DISABLED if running else READONLY)
                elif isinstance(widget, ttk.Radiobutton) and key in [
                    UIField.DIRECTX_TOGGLE.value,
                    UIField.OPENGL_TOGGLE.value,
                    UIField.BS_RENDERER_DX.value,
                    UIField.BS_RENDERER_GL.value,
                    UIField.BS_RENDERER_VK.value,
                ]:
                    widget.configure(state=tk.DISABLED if running else tk.NORMAL)
                elif widget in [
                    self.adb_connect_btn,
                    self.adb_refresh_btn,
                    self.adb_restart_btn,
                    self.adb_set_size_btn,
                    self.adb_reset_size_btn,
                ]:
                    widget.configure(state=tk.DISABLED if running else tk.NORMAL)
                elif isinstance(widget, ttk.Checkbutton):
                    widget.configure(state=tk.DISABLED if running else tk.NORMAL)
                elif isinstance(widget, ttk.Button):
                    widget.configure(state=tk.DISABLED if running else tk.NORMAL)

            except tk.TclError:
                continue
        self._sync_job_extra_spinboxes()
        if self._job_toggle_checkbuttons:
            self._sync_all_job_toggle_appearances()

    def get_button_state(self) -> str:
        """Get the current button state: 'idle' or 'running'."""
        return self._button_state

    def append_log(self, message: str) -> None:
        self.event_log.configure(state="normal")
        self.event_log.delete("1.0", "end")
        self.event_log.insert("end", message)
        self.event_log.configure(state="disabled")
        self.event_log.see("end")

    def set_status(self, text: str) -> None:
        self._status_text = text

    def update_stats(self, stats: dict[str, object] | None) -> None:
        if not stats:
            return

        def as_string(field: StatField, default: str = "0") -> str:
            value = stats.get(field.value, default)
            return str(value)

        def as_int(field: StatField) -> int:
            value = stats.get(field.value)
            try:
                return int(str(value))
            except (TypeError, ValueError):
                return 0

        for field, var in self.stat_labels.items():
            var.set(as_string(field))

        runtime = stats.get(BotStatField.TIME_SINCE_START.value)
        if runtime is not None:
            self.bot_labels[BotStatField.TIME_SINCE_START].set(str(runtime))
        failures = stats.get(BotStatField.RESTARTS_AFTER_FAILURE.value)
        if failures is not None:
            self.bot_labels[BotStatField.RESTARTS_AFTER_FAILURE].set(str(failures))

        winrate_raw = stats.get(DerivedStatField.WINRATE.value)
        wins = as_int(StatField.WINS)
        losses = as_int(StatField.LOSSES)
        parsed_winrate = self._parse_winrate_value(winrate_raw)
        winrate = parsed_winrate if parsed_winrate is not None else self._calculate_winrate_percentage(wins, losses)
        gauge_fg, gauge_bg, gauge_text, _canvas_bg = self._gauge_theme_colours()
        self.win_gauge.animate_to(winrate, fg_colour=gauge_fg, text_colour=gauge_text)

        # Update win streak stats
        current_streak = stats.get(DerivedStatField.CURRENT_WIN_STREAK.value, 0)
        best_streak = stats.get(DerivedStatField.BEST_WIN_STREAK.value, 0)
        if hasattr(self, "current_streak_var"):
            self.current_streak_var.set(str(current_streak))
        if hasattr(self, "best_streak_var"):
            self.best_streak_var.set(str(best_streak))

    def _build_tabs(self) -> None:
        self._style.configure(f"{_TAB_SECTION_STYLE}.Label", anchor="center")
        self._init_notebook_style()

        self.notebook = ttk.Notebook(self, style=_NOTEBOOK_STYLE)
        self.notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))
        self.notebook.bind("<Configure>", self._sync_notebook_tab_widths, add="+")

        self.jobs_tab = ttk.Frame(self.notebook)
        self.emulator_tab = ttk.Frame(self.notebook)
        self.stats_tab = ttk.Frame(self.notebook)
        self.misc_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.jobs_tab, text="任务")
        self.notebook.add(self.emulator_tab, text="模拟器")
        self.notebook.add(self.stats_tab, text="统计")
        self.notebook.add(self.misc_tab, text="其他")

        self._create_jobs_tab()
        self._create_emulator_tab()
        self._create_stats_tab()
        self._create_misc_tab()
        self.after_idle(self._sync_notebook_tab_widths)

    def _init_notebook_style(self) -> None:
        """Equal-width, centered top tabs shared across the app."""
        self._style.layout(_NOTEBOOK_STYLE, self._style.layout("TNotebook"))
        self._style.configure(_NOTEBOOK_STYLE, tabmargins=(2, 4, 2, 0))
        self._style.configure(
            _NOTEBOOK_TAB_STYLE,
            padding=(10, 6),
            anchor="center",
        )

    def _sync_notebook_tab_widths(self, event: tk.Event | None = None) -> None:
        if event is not None and event.widget is not self.notebook:
            return
        try:
            width = self.notebook.winfo_width()
        except tk.TclError:
            return
        if width <= 1:
            return
        tab_width = max(10, width // (_NOTEBOOK_TAB_COUNT * _NOTEBOOK_TAB_WIDTH_DIVISOR))
        try:
            self._style.configure(_NOTEBOOK_TAB_STYLE, width=tab_width)
        except tk.TclError:
            return

    def _section_labelframe(self, parent: tk.Misc, title: str) -> ttk.Labelframe:
        """Section box with a centered title — same look across tabs."""
        return ttk.Labelframe(
            parent,
            text=title,
            labelanchor="n",
            style=_TAB_SECTION_STYLE,
            padding=_TAB_SECTION_PADDING,
        )

    def _compact_action_button_row(
        self,
        parent: tk.Misc,
        *buttons: dict[str, object],
    ) -> tuple[ttk.Button, ...]:
        row = ttk.Frame(parent)
        row.pack(fill=X)
        cluster = ttk.Frame(row)
        cluster.pack(anchor="center")
        created: list[ttk.Button] = []
        last_index = len(buttons) - 1
        for index, config in enumerate(buttons):
            text = str(config["text"])
            command = config["command"]
            style = config.get("style")
            bootstyle = config.get("bootstyle")
            pady_raw = config.get("pady", (0, 0))
            if isinstance(pady_raw, int):
                pady: tuple[int, int] | int = pady_raw
            elif isinstance(pady_raw, tuple) and len(pady_raw) == 2:
                a, b = pady_raw
                pady = (int(str(a)), int(str(b)))
            else:
                pady = (0, 0)
            if style is not None and bootstyle is not None:
                button = ttk.Button(cluster, text=text, command=command, style=str(style), bootstyle=str(bootstyle))
            elif style is not None:
                button = ttk.Button(cluster, text=text, command=command, style=str(style))
            elif bootstyle is not None:
                button = ttk.Button(cluster, text=text, command=command, bootstyle=str(bootstyle))
            else:
                button = ttk.Button(cluster, text=text, command=command)
            padx = (0, 10) if index < last_index else (0, 0)
            button.pack(side=LEFT, ipadx=12, ipady=1, padx=padx, pady=pady)
            created.append(button)
        return tuple(created)

    def _app_icon_path(self) -> Path | None:
        relative = Path("assets") / _APP_ICON_NAME
        candidates: list[Path] = []
        if getattr(sys, "frozen", False):
            bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
            candidates.extend((bundle_root / relative, Path(sys.executable).parent / relative))
        candidates.append(Path(__file__).resolve().parents[2] / relative)
        return next((path for path in candidates if path.is_file()), None)

    def _set_window_icon(self) -> None:
        icon_path = self._app_icon_path()
        if icon_path is None:
            return
        if is_windows():
            try:
                self.iconbitmap(str(icon_path))
            except tk.TclError:
                return
            return
        try:
            from PIL import Image, ImageTk

            with Image.open(icon_path) as source:
                resized = source.resize((64, 64), Image.Resampling.LANCZOS)
                self._window_icon = ImageTk.PhotoImage(resized)
            # PIL ImageTk.PhotoImage is _PhotoImageLike-compatible but not in tkinter stubs.
            self.iconphoto(True, self._window_icon)  # ty: ignore[invalid-argument-type]
        except (ImportError, OSError, tk.TclError):
            return

    def _prepare_tab_page(self, tab: ttk.Frame) -> ttk.Frame:
        """Fill the tab page; extra height opens below the content, not under Start."""
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)
        page = ttk.Frame(tab, padding=_TAB_CONTAINER_PADDING)
        page.pack(fill="both", expand=YES)
        content = ttk.Frame(page)
        content.pack(fill=X, anchor="n")
        content.columnconfigure(0, weight=1)
        return content

    def _picker_combobox(self, parent: tk.Misc, **kwargs) -> ttk.Combobox:
        """Combobox with consistent TCombobox styling across the app."""
        kwargs.setdefault("state", READONLY)
        kwargs.setdefault("style", "TCombobox")
        return ttk.Combobox(parent, **kwargs)

    def _build_bottom_row(self) -> None:
        bottom = ttk.Frame(self)
        bottom.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        bottom.columnconfigure(0, weight=1)

        status_frame = self._section_labelframe(bottom, "状态")
        status_frame.grid(row=0, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)

        self.event_log = tk.Text(status_frame, height=1, wrap="word")
        self.event_log.grid(row=0, column=0, sticky="ew")
        self.event_log.configure(state="disabled")
        self._status_text = "空闲"
        self._style_status_log()

        self._main_btn_row = ttk.Frame(bottom)
        self._main_btn_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self._main_btn_row.columnconfigure(0, weight=1)
        self._main_btn_row.columnconfigure(1, weight=0)
        self._main_btn_row.columnconfigure(2, weight=1)
        ipadx, ipady = _ACTION_BUTTON_IPAD

        self.main_btn = ttk.Button(self._main_btn_row, text="启动", bootstyle="success")
        self.main_btn.grid(row=0, column=1, ipadx=ipadx, ipady=ipady)
        self._register_config_widget("main_btn", self.main_btn)

    def _create_jobs_tab(self) -> None:
        content = self._prepare_tab_page(self.jobs_tab)

        columns_frame = ttk.Frame(content)
        columns_frame.pack(fill=X)
        columns_frame.columnconfigure(0, weight=1, uniform="jobs_cols")
        columns_frame.columnconfigure(1, weight=1, uniform="jobs_cols")

        job_defaults = {job.key: job.default for job in JOBS}
        jobs_by_key = {job.key: job for job in JOBS}
        self.jobs_vars: dict[UIField, ttk.BooleanVar] = {}

        def place_extras_controls(
            parent: tk.Misc, combo_config: ComboConfig, combo_field: UIField, job: JobConfig
        ) -> None:
            short_label = _JOB_SPINBOX_LABELS.get(combo_field, combo_config.label)
            label = ttk.Label(parent, text=short_label)
            label.pack(side=LEFT, padx=(0, 4))
            self._job_row_extras.setdefault(job.key, []).append(label)

            spin_var = ttk.StringVar(value=str(combo_config.default))
            spinbox = ttk.Spinbox(
                parent,
                from_=int(min(combo_config.values)),
                to=int(max(combo_config.values)),
                width=3,
                textvariable=spin_var,
                command=self._notify_config_change,
                state=READONLY,
            )
            spinbox.pack(side=LEFT)
            self._trace_variable(spin_var)
            self._register_config_widget(combo_field.value, spinbox)
            self._job_extra_spinboxes[job.key] = spinbox
            self._job_row_extras.setdefault(job.key, []).append(spinbox)

            if combo_config.tooltip:
                info_label = ttk.Label(parent, text="ⓘ", bootstyle="info")
                info_label.pack(side=LEFT, padx=(4, 0))
                ToolTip(info_label, combo_config.tooltip)
                self._job_row_extras.setdefault(job.key, []).append(info_label)

            if combo_field == UIField.DECK_NUMBER_SELECTION:
                self.deck_var = spin_var
            elif combo_field == UIField.MAX_DECK_SELECTION:
                self.max_deck_var = spin_var
            elif combo_field == UIField.MAX_ACCOUNT_SELECTION:
                self.max_account_var = spin_var

        def place_job_toggle(
            parent: tk.Misc,
            *,
            field: UIField,
            text: str,
            tooltip: str = "",
            row_index: int | None = None,
            command: Callable[[], None] | None = None,
        ) -> ttk.Checkbutton:
            var = ttk.BooleanVar(value=self._job_toggle_default(field, job_defaults))

            def on_toggle() -> None:
                self._sync_job_toggle_appearance(field)
                if command:
                    command()
                else:
                    self._notify_config_change()

            checkbox = ttk.Checkbutton(
                parent,
                text=text,
                variable=var,
                bootstyle=_JOB_TOGGLE_ON_STYLE,
                command=on_toggle,
            )
            if row_index is None:
                checkbox.pack(side=LEFT)
            else:
                checkbox.grid(row=row_index, column=0, sticky="w", pady=2)
            if tooltip:
                ToolTip(checkbox, tooltip)
            self.jobs_vars[field] = var
            self._job_toggle_checkbuttons[field] = checkbox
            self._trace_variable(var)
            self._register_config_widget(field.value, checkbox)
            self._sync_job_toggle_appearance(field)
            return checkbox

        def add_job_row(section_frame: ttk.Labelframe, job: JobConfig, row_index: int) -> int:
            """Place one job row; returns the next free row index."""
            if job.extras:
                # Toggle on row 1; number picker indented below (fits narrow columns).
                combo_config = next(iter(job.extras.values()))
                combo_field = combo_config.key
                place_job_toggle(
                    section_frame,
                    field=job.key,
                    text=job.title,
                    tooltip=job.tooltip,
                    row_index=row_index,
                    command=lambda j=job.key: self._on_job_with_extra_toggle(j),
                )

                extras = ttk.Frame(section_frame)
                extras.grid(
                    row=row_index + 1,
                    column=0,
                    sticky="w",
                    padx=(22, 0),
                    pady=(0, 4),
                )
                place_extras_controls(extras, combo_config, combo_field, job)
                self._sync_job_extra_spinboxes()
                return row_index + 2

            place_job_toggle(
                section_frame,
                field=job.key,
                text=job.title,
                tooltip=job.tooltip,
                row_index=row_index,
            )
            return row_index + 1

        column_padx = ((0, 5), (5, 0))
        for column_index, sections in enumerate(_JOB_TAB_COLUMNS):
            column_frame = ttk.Frame(columns_frame)
            column_frame.grid(row=0, column=column_index, sticky="nsew", padx=column_padx[column_index])
            column_frame.columnconfigure(0, weight=1)

            for section_title, job_keys in sections:
                section_frame = self._section_labelframe(column_frame, section_title)
                section_frame.pack(fill=X, pady=(0, 6))

                grid_row = 0
                for job_key in job_keys:
                    job = jobs_by_key[job_key]
                    grid_row = add_job_row(section_frame, job, grid_row)

        self._sync_all_job_toggle_appearances()

    def can_start(self) -> bool:
        """True when at least one battle, clan chat, or collection job is enabled."""
        return has_start_ready_job(self.get_all_values())

    def _sync_start_button_readiness(self) -> None:
        """Enable Start only when at least one Battles, Clan chat, or Collection job is selected."""
        if self._button_state != "idle":
            return
        if self.can_start():
            self.main_btn.configure(text="启动", bootstyle="success", state=tk.NORMAL)
            self.append_log(_IDLE_STATUS)
        else:
            self.main_btn.configure(text="启动", bootstyle="secondary", state=tk.DISABLED)
            self.append_log(_START_BLOCKED_MESSAGE)

    def _on_job_with_extra_toggle(self, job_key: UIField) -> None:
        self._sync_job_toggle_appearance(job_key)
        self._sync_job_extra_spinboxes()
        self._notify_config_change()

    def _sync_job_extra_spinboxes(self) -> None:
        bot_running = self._button_state == "running"
        for job_key, spinbox in self._job_extra_spinboxes.items():
            job_on = bool(self.jobs_vars[job_key].get())
            if bot_running or not job_on:
                spinbox.configure(state=tk.DISABLED)
            else:
                spinbox.configure(state=READONLY)

    def _muted_foreground(self) -> str:
        try:
            colour = self._style.lookup("secondary.TLabel", "foreground")
            return colour or "#888888"
        except tk.TclError:
            return "#888888"

    def _sync_job_toggle_appearance(self, field: UIField) -> None:
        """Dim job toggles (and their extras) when turned off."""
        checkbox = self._job_toggle_checkbuttons.get(field)
        var = self.jobs_vars.get(field)
        if not checkbox or not var:
            return

        job_on = bool(var.get())
        normal = self._label_foreground()
        muted = self._muted_foreground()
        try:
            checkbox.configure(bootstyle=_JOB_TOGGLE_ON_STYLE if job_on else _JOB_TOGGLE_OFF_STYLE)
        except tk.TclError:
            pass

        for widget in self._job_row_extras.get(field, []):
            try:
                widget.configure(foreground=normal if job_on else muted)
            except tk.TclError:
                continue

    def _sync_all_job_toggle_appearances(self) -> None:
        for field in self._job_toggle_checkbuttons:
            self._sync_job_toggle_appearance(field)

    @staticmethod
    def _job_toggle_default(field: UIField, job_defaults: dict[UIField, bool]) -> bool:
        """Map stored job defaults to what the Jobs tab toggle should show."""
        stored = job_defaults.get(field, False)
        if field == _WIN_TRACK_UI_FIELD:
            return not stored
        return stored

    def _create_emulator_tab(self) -> None:
        content = self._prepare_tab_page(self.emulator_tab)

        connection_section = self._section_labelframe(content, "模拟器")
        connection_section.pack(fill=X, pady=(0, 6))
        selection_frame = ttk.Frame(connection_section)
        selection_frame.pack(fill=X)
        ttk.Label(selection_frame, text="类型：").pack(side=LEFT, padx=(0, 5))

        available_emulators = get_available_emulators()
        default_emulator = available_emulators[0] if available_emulators else EmulatorType.ADB
        self.emulator_var = ttk.StringVar(value=default_emulator)
        self.emulator_combo = self._picker_combobox(
            selection_frame,
            textvariable=self.emulator_var,
            values=available_emulators,
            width=20,
        )
        self.emulator_combo.pack(side=LEFT, fill=X, expand=True)
        self.emulator_combo.bind("<<ComboboxSelected>>", self._on_emulator_changed)
        self._register_config_widget("emulator_combobox", self.emulator_combo)

        ttk.Checkbutton(
            selection_frame,
            text="高级设置",
            variable=self.advanced_settings_var,
            bootstyle="round-toggle",
            command=self._on_advanced_settings_toggled,
        ).pack(side=LEFT, padx=(8, 0))

        self.settings_container = ttk.Frame(content)
        self.settings_container.pack_forget()
        self.google_play_frame = ttk.Frame(self.settings_container)
        self.memu_frame = ttk.Frame(self.settings_container)
        self.bluestacks_frame = ttk.Frame(self.settings_container)
        self.adb_frame = ttk.Frame(self.settings_container)

        # Store frames in a dictionary for easy access
        self.emulator_settings_frames = {
            EmulatorType.MEMU: self.memu_frame,
            EmulatorType.GOOGLE_PLAY: self.google_play_frame,
            EmulatorType.BLUESTACKS: self.bluestacks_frame,
            EmulatorType.ADB: self.adb_frame,
        }

        # Populate the settings frames
        self.gp_vars: dict[UIField, ttk.StringVar] = {}
        self._create_google_play_settings(self.google_play_frame)
        self._create_memu_settings(self.memu_frame)
        self._create_bluestacks_settings(self.bluestacks_frame)
        self._create_adb_tab(self.adb_frame)

        # Show the initial settings based on the default value
        self._show_current_emulator_settings()
        self._update_advanced_settings_visibility(self.emulator_var.get())

    def _create_google_play_settings(self, parent_frame: ttk.Frame) -> None:
        device_frame = self._section_labelframe(parent_frame, "设备")
        device_frame.pack(fill=X, pady=(0, 6))

        # Device serial row
        device_row = ttk.Frame(device_frame)
        device_row.pack(fill="x", pady=(0, 5))
        device_row.columnconfigure(1, weight=1)

        ttk.Label(device_row, text="设备：").grid(row=0, column=0, padx=(0, 5), sticky="w")

        self.gp_device_serial_var = ttk.StringVar(value=str(GOOGLE_PLAY_DEVICE_CONFIG.default))
        self.gp_device_serial_combo = self._picker_combobox(
            device_row,
            textvariable=self.gp_device_serial_var,
            state=tk.NORMAL,
        )
        self.gp_device_serial_combo.grid(row=0, column=1, padx=5, sticky="ew")
        self._register_config_widget(UIField.GP_DEVICE_SERIAL.value, self.gp_device_serial_combo)
        self._trace_variable(self.gp_device_serial_var)

        frame = self._section_labelframe(parent_frame, "Google Play Games")
        frame.pack(fill=X, pady=(0, 6))

        left_keys = GOOGLE_PLAY_SETTINGS[:4]
        right_keys = GOOGLE_PLAY_SETTINGS[4:]

        for row, config in enumerate(left_keys):
            self._add_google_play_row(frame, row, 0, config)

        for row, config in enumerate(right_keys):
            self._add_google_play_row(frame, row, 3, config)

    def _create_memu_settings(self, parent_frame: ttk.Frame) -> None:
        self.memu_advanced_frame = self._section_labelframe(parent_frame, "渲染模式")
        self.memu_advanced_frame.pack_forget()

        self.memu_render_var = ttk.StringVar(value="DirectX")
        for config in MEMU_SETTINGS:
            text = "DirectX" if config.key == UIField.DIRECTX_TOGGLE else "OpenGL"
            rb = ttk.Radiobutton(
                self.memu_advanced_frame,
                text=text,
                variable=self.memu_render_var,
                value=text,
                command=self._notify_config_change,
            )
            rb.pack(anchor="w")
            self._register_config_widget(config.key.value, rb)

    def _create_bluestacks_settings(self, parent_frame: ttk.Frame) -> None:
        device_frame = self._section_labelframe(parent_frame, "设备")
        device_frame.pack(fill=X, pady=(0, 6))

        # Device serial row
        device_row = ttk.Frame(device_frame)
        device_row.pack(fill="x", pady=(0, 5))
        device_row.columnconfigure(1, weight=1)

        ttk.Label(device_row, text="设备：").grid(row=0, column=0, padx=(0, 5), sticky="w")

        self.bs_device_serial_var = ttk.StringVar(value=str(BLUESTACKS_DEVICE_CONFIG.default))
        self.bs_device_serial_combo = self._picker_combobox(
            device_row,
            textvariable=self.bs_device_serial_var,
            state=tk.NORMAL,
        )
        self.bs_device_serial_combo.grid(row=0, column=1, padx=5, sticky="ew")
        self._register_config_widget(UIField.BS_DEVICE_SERIAL.value, self.bs_device_serial_combo)
        self._trace_variable(self.bs_device_serial_var)

        # Note about auto-discovery
        note_label = ttk.Label(
            device_frame,
            text="留空将自动从 BlueStacks 配置中检测",
            font=("TkDefaultFont", 8),
            foreground=self._muted_foreground(),
        )
        note_label.pack(anchor="w")
        self._muted_labels.append(note_label)

        self.bluestacks_advanced_frame = self._section_labelframe(parent_frame, "渲染模式")
        self.bluestacks_advanced_frame.pack_forget()

        self.bs_render_var = ttk.StringVar(value="DirectX")
        for config in BLUESTACKS_SETTINGS:
            if config.key == UIField.BS_RENDERER_DX:
                value = "DirectX"
            elif config.key == UIField.BS_RENDERER_VK:
                value = "Vulkan"
            else:
                value = "OpenGL"
            rb = ttk.Radiobutton(
                self.bluestacks_advanced_frame,
                text=value,
                variable=self.bs_render_var,
                value=value,
                command=self._notify_config_change,
            )
            rb.pack(anchor="w")
            self._register_config_widget(config.key.value, rb)

    def _create_adb_tab(self, parent_frame: ttk.Frame) -> None:
        """Create the widgets for the ADB Device settings tab."""
        frame = self._section_labelframe(parent_frame, "ADB 设备")
        frame.pack(fill=X, pady=(0, 6))

        # --- Row 1: Serial Input ---
        row1 = ttk.Frame(frame)
        row1.pack(fill="x", pady=(0, 5))
        row1.columnconfigure(1, weight=1)

        ttk.Label(row1, text="设备序列号：").grid(row=0, column=0, padx=(0, 5), sticky="w")

        self.adb_serial_var = ttk.StringVar(value="")
        # The dropdown shows friendly device names (e.g. "MuMuPlayer (127.0.0.1:16448)")
        # while adb_serial_var keeps the raw serial so the persisted config
        # round-trips as a valid address for the worker.
        self._adb_serial_labels: dict[str, str] = {}
        self._adb_serial_display_var = ttk.StringVar(value="")
        self.adb_serial_combo = self._picker_combobox(
            row1,
            textvariable=self._adb_serial_display_var,
            state=tk.NORMAL,
        )
        self.adb_serial_combo.grid(row=0, column=1, padx=5, sticky="ew")
        self._register_config_widget(UIField.ADB_SERIAL.value, self.adb_serial_combo)
        self._trace_variable(self.adb_serial_var)
        self._adb_serial_display_var.trace_add("write", self._on_adb_serial_display_changed)

        # --- Row 2: Connect/Refresh Buttons ---
        row_buttons_connect = ttk.Frame(frame)
        row_buttons_connect.pack(fill="x", pady=(0, 8))
        row_buttons_connect.columnconfigure(0, weight=1)
        row_buttons_connect.columnconfigure(1, weight=1)

        self.adb_connect_btn = ttk.Button(
            row_buttons_connect, text="连接", style="success.TButton", command=self._on_adb_connect
        )
        self.adb_connect_btn.grid(row=0, column=0, padx=(0, 3), sticky="ew")
        self._register_config_widget("adb_connect_btn", self.adb_connect_btn)

        self.adb_refresh_btn = ttk.Button(row_buttons_connect, text="刷新", command=self._on_adb_refresh)
        self.adb_refresh_btn.grid(row=0, column=1, padx=(3, 0), sticky="ew")
        # 真实鼠标点击: 高 DPI 缩放下 release 可能落在按钮外导致 ttk command 不触发,
        # 改为按下即触发; _on_adb_refresh 的防重入兜底重复调用.
        self.adb_refresh_btn.bind("<Button-1>", lambda _e: self._on_adb_refresh())
        self._register_config_widget("adb_refresh_btn", self.adb_refresh_btn)

        # --- Row 3: Action Buttons (Stacked Vertically) ---
        row_buttons_action = ttk.Frame(frame)
        row_buttons_action.pack(fill="x")

        self.adb_restart_btn = ttk.Button(row_buttons_action, text="重启 ADB", command=self._on_adb_restart)
        self.adb_restart_btn.pack(fill=X, pady=(0, 3))
        self._register_config_widget("adb_restart_btn", self.adb_restart_btn)

        self.adb_set_size_btn = ttk.Button(row_buttons_action, text="设置尺寸和密度")
        self.adb_set_size_btn.pack(fill=X, pady=3)
        self._register_config_widget("adb_set_size_btn", self.adb_set_size_btn)

        self.adb_reset_size_btn = ttk.Button(row_buttons_action, text="重置尺寸和密度")
        self.adb_reset_size_btn.pack(fill=X, pady=(3, 0))
        self._register_config_widget("adb_reset_size_btn", self.adb_reset_size_btn)

        ToolTip(self.adb_set_size_btn, "将模拟器屏幕设置为 419x633，密度设置为 160。")
        ToolTip(self.adb_reset_size_btn, "将模拟器屏幕尺寸和密度重置为设备默认值。")

        # Auto-discover available ADB devices once the UI is up.
        self.after(300, lambda: self._on_adb_refresh(auto=True))

    # Common local emulator ADB ports (MuMu, LDPlayer, BlueStacks, etc.) probed
    # by _scan_adb_devices when a device isn't already in `adb devices`.
    _ADB_PROBE_PORTS = (16448, 16384, 21503, 5555, 7555, 5554)

    def _scan_adb_devices(self) -> list[str]:
        """List online ADB devices, probing common emulator ports in parallel."""
        import subprocess
        from concurrent.futures import ThreadPoolExecutor

        from pyclashbot.emulators.adb import AdbController

        devices = AdbController.discover_devices()

        # Probe any missing common ports concurrently (adb connect to a dead
        # port returns fast, but issuing them serially still adds seconds).
        to_probe = [
            f"127.0.0.1:{port}" for port in self._ADB_PROBE_PORTS if f"127.0.0.1:{port}" not in devices
        ]
        if to_probe:

            def _connect(addr: str) -> None:
                try:
                    subprocess.run(
                        f'"adb" connect {addr}',
                        shell=True,
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=2,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    pass

            with ThreadPoolExecutor(max_workers=len(to_probe)) as ex:
                list(ex.map(_connect, to_probe))

        return AdbController.discover_devices()

    _ADB_DEBUG_LOG = r"d:\workwork\trae\皇室战争\_refresh_debug.log"

    def _adb_debug(self, msg: str) -> None:
        try:
            import datetime
            with open(self._ADB_DEBUG_LOG, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now():%H:%M:%S.%f}] {msg}\n")
        except Exception:
            pass

    def _on_adb_refresh(self, auto: bool = False) -> None:
        """Scan for ADB devices in a worker thread so the UI never freezes.

        adb connect probes and the MuMuManager name lookup can take seconds; the
        window must not freeze and the combobox must keep showing names while a
        manual refresh runs. So manual refreshes first re-apply the last known
        labels immediately, then swap in the fresh scan result when it's ready.
        """
        self._adb_debug(
            f"ENTER auto={auto} cache={'Y' if getattr(self, '_adb_cached_devices', None) else 'N'} "
            f"running={getattr(self, '_adb_scan_in_progress', False)}"
        )
        # Manual refresh: immediately re-apply the previous scan so the dropdown
        # keeps its friendly names instead of going blank during the scan.
        if not auto and getattr(self, "_adb_cached_devices", None):
            self._apply_adb_labels(self._adb_cached_devices, self._adb_cached_labels)

        if getattr(self, "_adb_scan_in_progress", False):
            return
        self._adb_scan_in_progress = True

        def _worker() -> None:
            try:
                devices = self._scan_adb_devices()
                labels = self._adb_device_labels()
                self._adb_cached_devices = devices
                self._adb_cached_labels = labels
            except Exception:  # noqa: BLE001 - keep UI responsive; show nothing
                self._adb_scan_in_progress = False
                return
            self.after(0, lambda: self._adb_finish_refresh(devices, labels))

        threading.Thread(target=_worker, daemon=True).start()

    def _adb_finish_refresh(self, devices: list[str], labels: dict[str, str]) -> None:
        """Main-thread half of _on_adb_refresh: update the dropdown, no popups."""
        self._adb_scan_in_progress = False
        self._adb_cached_devices = devices
        self._adb_cached_labels = labels
        self._adb_debug(f"FINISH devices={devices} labels={labels}")
        self._apply_adb_labels(devices, labels)

    def _apply_adb_labels(self, devices: list[str], labels: dict[str, str]) -> None:
        """Fill the ADB serial dropdown from a (devices, labels) scan result."""
        self._adb_serial_labels = {
            serial: self._format_adb_label(serial, labels.get(serial, "")) for serial in devices
        }
        displays = [self._adb_serial_labels[s] for s in devices]
        self._adb_debug(f"APPLY displays={displays}")
        self.adb_serial_combo.configure(values=displays)

        if devices:
            if self.adb_serial_var.get() not in devices:
                self.adb_serial_var.set(devices[0])
            self._adb_serial_display_var.set(
                self._adb_serial_labels.get(self.adb_serial_var.get(), self.adb_serial_var.get())
            )
        else:
            self.adb_serial_var.set("")
            self._adb_serial_display_var.set("")

    def _adb_device_labels(self) -> dict[str, str]:
        """Map each online ADB serial to a friendly device name.

        Prefers the MuMu instance name (e.g. "皇室战争" for 127.0.0.1:16448),
        falling back to the model reported by `adb devices -l`.
        """
        labels = self._mumu_instance_names()

        import subprocess

        try:
            res = subprocess.run(
                '"adb" devices -l',
                shell=True,
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return labels
        for line in res.stdout.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2 or parts[1] != "device":
                continue
            serial = parts[0]
            if serial in labels:
                continue
            model = next(
                (kv.split(":", 1)[1] for kv in parts[2:] if kv.startswith("model:")),
                "",
            )
            if model:
                labels[serial] = model
        return labels

    def _mumu_instance_names(self) -> dict[str, str]:
        """Map 127.0.0.1:<adb_port> -> MuMu instance name via `MuMuManager info -v all`."""
        import json
        import shutil
        import subprocess

        exe = shutil.which("MuMuManager") or shutil.which("MuMuManager.exe")
        if not exe:
            # Fallback to a known install root if it isn't on PATH (GUI launched
            # without 启动bot.bat and _ensure_mumu_on_path didn't find one).
            for root in _MUMU_INSTALL_ROOTS:
                cand = os.path.join(root, "shell", "MuMuManager.exe")
                if os.path.isfile(cand):
                    exe = cand
                    break
        if not exe:
            return {}
        raw: bytes | None = None
        for _attempt in range(2):  # MuMuManager can occasionally start slowly
            try:
                res = subprocess.run(
                    f'"{exe}" info -v all',
                    shell=True,
                    capture_output=True,
                    check=False,
                    timeout=10,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if res.returncode == 0 and res.stdout:
                raw = res.stdout
                break
        if not raw:
            return {}
        data: object = None
        for enc in ("utf-8-sig", "utf-8", "gbk"):
            try:
                data = json.loads(raw.decode(enc))
                break
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                continue
        if not isinstance(data, dict):
            return {}
        names: dict[str, str] = {}
        for inst in data.values():
            if not isinstance(inst, dict):
                continue
            port = inst.get("adb_port")
            name = inst.get("name", "")
            if port and name:
                names[f"{inst.get('adb_host_ip', '127.0.0.1')}:{port}"] = name
        return names

    def _format_adb_label(self, serial: str, model: str) -> str:
        """Friendly dropdown text for a device serial (model + serial)."""
        if model and model != serial:
            return f"{model} ({serial})"
        return serial

    def _on_adb_serial_display_changed(self, *_args) -> None:
        """Sync the raw serial when the user picks or types a device in the dropdown."""
        display = self._adb_serial_display_var.get()
        serial = next((s for s, d in self._adb_serial_labels.items() if d == display), None)
        if serial is None:
            serial = display  # manual input: treat it as a raw serial
        if serial != self.adb_serial_var.get():
            self.adb_serial_var.set(serial)

    def _on_adb_connect(self) -> None:
        from pyclashbot.emulators.adb import AdbController

        serial = self.adb_serial_var.get().strip()
        if not serial:
            messagebox.showwarning("ADB 连接", "请先填写或扫描设备序列号。")
            return
        ok = AdbController.connect_device(_AdbUiLogger(), serial)
        if ok:
            messagebox.showinfo("ADB 连接", f"设备 {serial} 连接成功。")
        else:
            messagebox.showerror("ADB 连接", f"设备 {serial} 连接失败。")

    def _on_adb_restart(self) -> None:
        from pyclashbot.emulators.adb import AdbController

        ok = AdbController.restart_adb(_AdbUiLogger())
        if not ok:
            messagebox.showerror("重启 ADB", "ADB 服务器重启失败。")
            return
        messagebox.showinfo("重启 ADB", "ADB 服务器已重启。")
        self._on_adb_refresh(auto=True)

    def _create_stats_tab(self) -> None:
        content = self._prepare_tab_page(self.stats_tab)
        content.columnconfigure(0, weight=1, uniform="stats_cols")
        content.columnconfigure(1, weight=1, uniform="stats_cols")

        self.stat_labels: dict[StatField, ttk.StringVar] = {}

        left = ttk.Frame(content)
        left.grid(row=0, column=0, sticky="new", padx=(0, 5))
        left.columnconfigure(0, weight=1)

        gauge_frame = self._section_labelframe(left, "胜率")
        gauge_frame.grid(row=0, column=0, sticky="ew")
        gauge_frame.columnconfigure(0, weight=1)

        _gauge_kw = self._initial_gauge_kwargs()
        self.win_gauge = DualRingGauge(
            gauge_frame,
            diameter=_WIN_GAUGE_DIAMETER,
            thickness=_WIN_GAUGE_THICKNESS,
            fg=_gauge_kw["fg"],
            bg=_gauge_kw["bg"],
            text_color=_gauge_kw["text_color"],
            canvas_bg=_gauge_kw["canvas_bg"],
        )
        self.win_gauge.grid(row=0, column=0, pady=(0, 6))

        win_loss_frame = ttk.Frame(gauge_frame)
        win_loss_frame.grid(row=1, column=0, sticky="ew")
        win_loss_frame.columnconfigure(1, weight=1)
        for row, field in enumerate(WIN_RATE_STAT_FIELDS):
            title = WIN_RATE_STAT_LABELS[field]
            label = ttk.Label(win_loss_frame, text=f"{title}:")
            label.grid(row=row, column=0, sticky="w")
            self._theme_labels.append(label)
            var = ttk.StringVar(value="0")
            value_label = ttk.Label(win_loss_frame, textvariable=var, foreground=self._stat_accent_foreground())
            value_label.grid(row=row, column=1, sticky="e")
            self._stat_accent_labels.append(value_label)
            self.stat_labels[field] = var

        battle_frame = self._section_labelframe(left, "对战统计")
        battle_frame.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        battle_frame.columnconfigure(1, weight=1)

        for row, field in enumerate(BATTLE_STAT_FIELDS):
            title = BATTLE_STAT_LABELS[field]
            label = ttk.Label(battle_frame, text=title)
            label.grid(row=row, column=0, sticky="w")
            self._theme_labels.append(label)
            var = ttk.StringVar(value="0")
            value_label = ttk.Label(battle_frame, textvariable=var, foreground=self._stat_accent_foreground())
            value_label.grid(row=row, column=1, sticky="e")
            self._stat_accent_labels.append(value_label)
            self.stat_labels[field] = var

        streak_row = len(BATTLE_STAT_FIELDS)
        ttk.Separator(battle_frame, orient="horizontal").grid(
            row=streak_row, column=0, columnspan=2, sticky="ew", pady=(8, 4)
        )
        ttk.Label(battle_frame, text="当前连胜：").grid(row=streak_row + 1, column=0, sticky="w")
        self.current_streak_var = ttk.StringVar(value="0")
        current_streak_label = ttk.Label(
            battle_frame,
            textvariable=self.current_streak_var,
            foreground=self._stat_accent_foreground(),
        )
        current_streak_label.grid(row=streak_row + 1, column=1, sticky="e")
        self._stat_accent_labels.append(current_streak_label)
        ttk.Label(battle_frame, text="最佳连胜：").grid(row=streak_row + 2, column=0, sticky="w")
        self.best_streak_var = ttk.StringVar(value="0")
        best_streak_label = ttk.Label(
            battle_frame,
            textvariable=self.best_streak_var,
            foreground=self._stat_accent_foreground(),
        )
        best_streak_label.grid(row=streak_row + 2, column=1, sticky="e")
        self._stat_accent_labels.append(best_streak_label)

        right = ttk.Frame(content)
        right.grid(row=0, column=1, sticky="new", padx=(5, 0))
        right.columnconfigure(0, weight=1)

        collection_frame = self._section_labelframe(right, "收藏统计")
        collection_frame.grid(row=0, column=0, sticky="ew")
        collection_frame.columnconfigure(1, weight=1)
        for row, field in enumerate(COLLECTION_STAT_FIELDS):
            title = COLLECTION_STAT_LABELS[field]
            label = ttk.Label(collection_frame, text=title)
            label.grid(row=row, column=0, sticky="w")
            self._theme_labels.append(label)
            var = ttk.StringVar(value="0")
            value_label = ttk.Label(collection_frame, textvariable=var, foreground=self._stat_accent_foreground())
            value_label.grid(row=row, column=1, sticky="e")
            self._stat_accent_labels.append(value_label)
            self.stat_labels[field] = var

        bot_frame = self._section_labelframe(right, "机器人统计")
        bot_frame.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        bot_frame.columnconfigure(1, weight=1)
        self.bot_labels = {
            BotStatField.RESTARTS_AFTER_FAILURE: ttk.StringVar(value="0"),
            BotStatField.TIME_SINCE_START: ttk.StringVar(value="00:00:00"),
        }
        for row, field in enumerate(BOT_STAT_FIELDS):
            title = BOT_STAT_LABELS[field]
            label = ttk.Label(bot_frame, text=title)
            label.grid(row=row, column=0, sticky="w")
            self._theme_labels.append(label)
            value_label = ttk.Label(
                bot_frame,
                textvariable=self.bot_labels[field],
                foreground=self._stat_accent_foreground(),
            )
            value_label.grid(row=row, column=1, sticky="e")
            self._stat_accent_labels.append(value_label)

    def _create_misc_tab(self) -> None:
        content = self._prepare_tab_page(self.misc_tab)

        appearance = self._section_labelframe(content, "外观")
        appearance.pack(fill=X, pady=(0, 6))

        ttk.Label(appearance, text="主题：").pack(anchor="w", pady=(0, 4))
        # Combo displays Chinese labels; theme_var keeps the English theme name.
        self.theme_display_var = ttk.StringVar(
            value=_THEME_LABELS.get(self.theme_var.get(), self.theme_var.get())
        )
        self.theme_combo = self._picker_combobox(
            appearance,
            values=list(_THEME_LABELS.values()),
            width=25,
            textvariable=self.theme_display_var,
        )
        self.theme_combo.pack(anchor="w")
        self.theme_combo.bind("<<ComboboxSelected>>", self._on_theme_change)
        self._trace_variable(self.theme_var)
        self._register_config_widget(UIField.THEME_NAME.value, self.theme_combo)

        data_frame = self._section_labelframe(content, "数据")
        data_frame.pack(fill=X, pady=(0, 6))

        discord_checkbox = ttk.Checkbutton(
            data_frame,
            text="Discord 在线状态",
            variable=self.discord_rpc_var,
            bootstyle="round-toggle",
            command=self._notify_config_change,
        )
        discord_checkbox.pack(anchor="w", pady=(0, 6))
        self._trace_variable(self.discord_rpc_var)
        self._register_config_widget(UIField.DISCORD_RPC_TOGGLE.value, discord_checkbox)

        record_fights_checkbox = ttk.Checkbutton(
            data_frame,
            text="录制我的 1v1 对战作为训练数据",
            variable=self.record_fights_var,
            bootstyle="round-toggle",
            command=self._notify_config_change,
        )
        record_fights_checkbox.pack(anchor="w", pady=(0, 6))
        self._trace_variable(self.record_fights_var)
        self._register_config_widget(UIField.RECORD_FIGHTS_TOGGLE.value, record_fights_checkbox)

        # Recording folder path picker
        recording_folder_frame = ttk.Frame(data_frame)
        recording_folder_frame.pack(fill=X, pady=(0, 2))

        ttk.Label(
            recording_folder_frame,
            text="录制文件夹：",
            font=("TkDefaultFont", 9),
        ).pack(side=LEFT, padx=(0, 5))

        recording_folder_entry = ttk.Entry(
            recording_folder_frame,
            textvariable=self.recording_folder_path_var,
            width=40,
        )
        recording_folder_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 5))

        browse_folder_btn = ttk.Button(
            recording_folder_frame,
            text="浏览...",
            width=10,
            command=self._on_browse_recording_folder,
        )
        browse_folder_btn.pack(side=LEFT)
        self._trace_variable(self.recording_folder_path_var)
        self._register_config_widget(UIField.RECORDING_FOLDER_PATH.value, recording_folder_entry)

        # Live validation feedback for the recording folder path.
        self.recording_folder_feedback = ttk.Label(
            data_frame,
            text="",
            font=("TkDefaultFont", 8),
            bootstyle="secondary",
        )
        self.recording_folder_feedback.pack(anchor="w", pady=(0, 0))
        feedback_trace = self.recording_folder_path_var.trace_add("write", self._update_recording_folder_feedback)
        self._traces.append((self.recording_folder_path_var, feedback_trace))
        self._update_recording_folder_feedback()

        self.open_logs_btn, self.open_recordings_btn = self._compact_action_button_row(
            data_frame,
            {
                "text": "查看日志",
                "bootstyle": "secondary",
                "command": self._on_open_logs_clicked,
            },
            {
                "text": "查看录制",
                "bootstyle": "secondary",
                "command": self._on_open_recordings_clicked,
            },
        )

        self.clear_recordings_btn, self.upload_recordings_btn = self._compact_action_button_row(
            data_frame,
            {
                "text": "清除录制",
                "bootstyle": "danger",
                "command": self._on_clear_recordings_clicked,
                "pady": (6, 0),
            },
            {
                "text": "上传录制",
                "bootstyle": "info",
                "command": lambda: webbrowser.open(_UPLOAD_RECORDINGS_URL),
                "pady": (6, 0),
            },
        )

        # Small auto-updating note showing total disk used by recordings.
        self.recordings_size_label = ttk.Label(
            data_frame,
            text="录制占用：正在计算...",
            font=("TkDefaultFont", 8),
            bootstyle="secondary",
        )
        self.recordings_size_label.pack(anchor="center", pady=(6, 0))
        self._schedule_recordings_size_refresh()

        links_frame = self._section_labelframe(content, "链接")
        links_frame.pack(fill=X)

        self._compact_action_button_row(
            links_frame,
            {
                "text": "Discord",
                "style": _DISCORD_BUTTON_STYLE,
                "command": lambda: webbrowser.open(_DISCORD_INVITE_URL),
            },
            {
                "text": "GitHub",
                "style": _GITHUB_BUTTON_STYLE,
                "command": lambda: webbrowser.open(_GITHUB_PROJECT_URL),
            },
        )

    def _register_config_widget(self, key: str, widget: tk.Widget) -> None:
        self._config_widgets[key] = widget

    def _notify_config_change(self, *_: object) -> None:
        if self._suspend_traces > 0 or self._config_callback is None:
            return
        if self._button_state == "idle":
            self._sync_start_button_readiness()
        callback = self._config_callback
        self.after_idle(lambda: callback(self.get_all_values()))

    def _trace_variable(self, var: tk.Variable) -> None:
        trace_id = var.trace_add("write", self._notify_config_change)
        self._traces.append((var, trace_id))

    def _add_google_play_row(
        self,
        frame: ttk.Labelframe,
        row: int,
        column_offset: int,
        config: ComboConfig,
    ) -> None:
        ttk.Label(frame, text=config.label).grid(row=row, column=column_offset, sticky="w", padx=5, pady=2)
        var = ttk.StringVar(value=str(config.default))
        combo = self._picker_combobox(
            frame,
            values=[str(option) for option in config.values],
            width=12,
            textvariable=var,
        )
        combo.grid(row=row, column=column_offset + 1, sticky="w")
        combo.bind("<<ComboboxSelected>>", self._notify_config_change_event)
        field = config.key
        self.gp_vars[field] = var
        self._trace_variable(var)
        self._register_config_widget(field.value, combo)

    def _notify_config_change_event(self, _event: object) -> None:
        self._notify_config_change()

    def _update_google_play_comboboxes(self) -> None:
        for field, var in self.gp_vars.items():
            widget = self._config_widgets.get(field.value)
            if not widget:
                continue
            values = [str(option) for option in widget.cget("values")]
            if var.get() not in values and values:
                var.set(values[0])

    def _reapply_custom_styles(self) -> None:
        """Restore app-specific ttk styles after theme_use resets them."""
        self._style.configure(f"{_TAB_SECTION_STYLE}.Label", anchor="center")
        self._sync_brand_button_styles()
        self._init_notebook_style()

    def _register_brand_button_style(self, style_name: str, background: str) -> None:
        colors = self._style.colors
        foreground = Colors.get_foreground(colors, background)
        pressed = Colors.make_transparent(0.80, background, colors.bg)
        hover = Colors.make_transparent(0.90, background, colors.bg)
        disabled_bg = Colors.make_transparent(0.10, colors.fg, colors.bg)
        disabled_fg = Colors.make_transparent(0.30, colors.fg, colors.bg)
        self._style.configure(
            style_name,
            foreground=foreground,
            background=background,
            bordercolor=background,
            darkcolor=background,
            lightcolor=background,
            focusthickness=0,
            focuscolor=foreground,
            padding=(10, 5),
            anchor="center",
        )
        self._style.layout(style_name, self._style.layout("success.TButton"))
        self._style.map(
            style_name,
            foreground=[("disabled", disabled_fg)],
            background=[
                ("disabled", disabled_bg),
                ("pressed !disabled", pressed),
                ("hover !disabled", hover),
            ],
            bordercolor=[("disabled", disabled_bg)],
            darkcolor=[
                ("disabled", disabled_bg),
                ("pressed !disabled", pressed),
                ("hover !disabled", hover),
            ],
            lightcolor=[
                ("disabled", disabled_bg),
                ("pressed !disabled", pressed),
                ("hover !disabled", hover),
            ],
        )

    def _sync_brand_button_styles(self) -> None:
        self._register_brand_button_style(_DISCORD_BUTTON_STYLE, _DISCORD_BRAND)
        self._register_brand_button_style(_GITHUB_BUTTON_STYLE, _GITHUB_BRAND)

    def _apply_theme(self, theme_name: str, skip_variable_update: bool = False) -> None:
        available = tuple(self._style.theme_names())
        selected = theme_name if theme_name in available else self.DEFAULT_THEME
        if selected not in available and available:
            selected = available[0]
        if not skip_variable_update or self.theme_var.get() != selected:
            self._suspend_traces += 1
            try:
                self.theme_var.set(selected)
            finally:
                self._suspend_traces -= 1
        # Keep the combo's Chinese label in sync with the English theme value.
        display_var = getattr(self, "theme_display_var", None)
        if display_var is not None:
            display_var.set(_THEME_LABELS.get(selected, selected))
        try:
            self._style.theme_use(selected)
        except tk.TclError:
            # Popdown widget may be mid-close on macOS; still resync colours below.
            pass
        self._reapply_custom_styles()
        self._refresh_theme_colours()
        if self._button_state == "idle":
            self._sync_start_button_readiness()
        self.after_idle(self._sync_notebook_tab_widths)

    def _label_foreground(self) -> str:
        try:
            colour = self._style.lookup("TLabel", "foreground")
            return colour or "#202020"
        except tk.TclError:
            return "#202020"

    def _stat_accent_foreground(self) -> str:
        colors = getattr(self._style, "colors", None)
        if colors is not None:
            accent = getattr(colors, "info", "")
            if accent:
                return accent
        return self._label_foreground()

    def _panel_background(self) -> str:
        try:
            background = self._style.lookup("TLabelframe", "background")
            if background:
                return background
        except tk.TclError:
            pass
        colors = getattr(self._style, "colors", None)
        if colors is not None:
            return getattr(colors, "bg", "") or self._label_foreground()
        return self._label_foreground()

    def _gauge_theme_colours(self) -> tuple[str, str, str, str]:
        colors = getattr(self._style, "colors", None)
        gauge_fg = getattr(colors, "success", "#2ecc71") if colors is not None else "#2ecc71"
        gauge_bg = getattr(colors, "danger", "#e74c3c") if colors is not None else "#e74c3c"
        return gauge_fg, gauge_bg, self._label_foreground(), self._panel_background()

    def _initial_gauge_kwargs(self) -> dict[str, str]:
        gauge_fg, gauge_bg, gauge_text, canvas_bg = self._gauge_theme_colours()
        return {
            "fg": gauge_fg,
            "bg": gauge_bg,
            "text_color": gauge_text,
            "canvas_bg": canvas_bg,
        }

    def _style_status_log(self) -> None:
        try:
            background = self._style.lookup("TEntry", "fieldbackground")
            foreground = self._style.lookup("TEntry", "foreground")
        except tk.TclError:
            return

        colors = getattr(self._style, "colors", None)
        if not background and colors is not None:
            background = getattr(colors, "input", "") or getattr(colors, "bg", "")
        if not foreground and colors is not None:
            foreground = getattr(colors, "fg", "")

        if not background or not foreground:
            return

        self.event_log.configure(
            background=background,
            foreground=foreground,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            insertbackground=foreground,
        )

    def _refresh_theme_colours(self) -> None:
        foreground = self._label_foreground()
        for label in self._theme_labels:
            try:
                label.configure(foreground=foreground)
            except tk.TclError:
                continue
        muted = self._muted_foreground()
        for label in self._muted_labels:
            try:
                label.configure(foreground=muted)
            except tk.TclError:
                continue
        if hasattr(self, "event_log"):
            self._style_status_log()
        accent = self._stat_accent_foreground()
        for label in self._stat_accent_labels:
            try:
                label.configure(foreground=accent)
            except tk.TclError:
                continue
        if hasattr(self, "win_gauge"):
            gauge_fg, gauge_bg, gauge_text, canvas_bg = self._gauge_theme_colours()
            self.win_gauge.set_colours(gauge_fg, gauge_bg, gauge_text, canvas_bg=canvas_bg)
        if self._job_toggle_checkbuttons:
            self._sync_all_job_toggle_appearances()

    def _on_theme_change(self, _event: object | None = None) -> None:
        display = self.theme_display_var.get()
        english = next((k for k, v in _THEME_LABELS.items() if v == display), display)
        self._apply_theme(english, skip_variable_update=True)
        self._notify_config_change()

    def _on_emulator_changed(self, _event: object = None) -> None:
        if self.emulator_var.get() == EmulatorType.ADB:
            # Re-scan on every return to the ADB tab so the dropdown always
            # shows friendly device names (switching emulator types can leave
            # the display pointing at the bare serial).
            self._on_adb_refresh(auto=True)
        self._show_current_emulator_settings()
        self._notify_config_change()

    def _show_current_emulator_settings(self) -> None:
        """Hides all emulator settings frames and shows the one selected in the combobox."""
        selected_emulator = self.emulator_var.get()
        show_advanced = bool(self.advanced_settings_var.get())

        for frame in self.emulator_settings_frames.values():
            frame.pack_forget()

        frame_to_show = self.emulator_settings_frames.get(selected_emulator)
        should_show = True
        if selected_emulator in {EmulatorType.MEMU, EmulatorType.BLUESTACKS, EmulatorType.GOOGLE_PLAY}:
            should_show = show_advanced

        if frame_to_show and should_show:
            self.settings_container.pack(fill=X, anchor="n", pady=(0, 6))
            frame_to_show.pack(fill=X, anchor="n")
        else:
            self.settings_container.pack_forget()

        self._update_advanced_settings_visibility(selected_emulator)
        self.settings_container.update_idletasks()

    def _on_open_logs_clicked(self) -> None:
        if self._open_logs_callback:
            self._open_logs_callback()

    def _on_open_recordings_clicked(self) -> None:
        if self._open_recordings_callback:
            self._open_recordings_callback()

    def _on_browse_recording_folder(self) -> None:
        folder = tkinter.filedialog.askdirectory(
            title="选择录制文件夹",
            initialdir=self.recording_folder_path_var.get() or None,
        )
        if folder:
            self.recording_folder_path_var.set(folder)

    def _schedule_recordings_size_refresh(self) -> None:
        """Refresh the recordings-size note now and re-arm the next refresh."""
        self._refresh_recordings_size()
        self.after(_RECORDINGS_SIZE_REFRESH_MS, self._schedule_recordings_size_refresh)

    def _refresh_recordings_size(self) -> None:
        """Compute total recordings size off the UI thread, then update the note."""
        # Read the tk variable on the main thread; it isn't thread-safe.
        custom_path = self.recording_folder_path_var.get() or None

        def worker() -> None:
            try:
                total = recordings_total_bytes_all_locations(custom_path=custom_path)
            except OSError:
                return
            gb = total / (1024**3)
            self.after(0, lambda: self._set_recordings_size_text(gb))

        threading.Thread(target=worker, daemon=True).start()

    def _set_recordings_size_text(self, gb: float) -> None:
        label = getattr(self, "recordings_size_label", None)
        if label is None:
            return
        try:
            label.configure(text=f"录制占用 {gb:.2f} GB")
        except tk.TclError:
            pass  # window was closed before this callback ran

    def _update_recording_folder_feedback(self, *_: object) -> None:
        """Show path-validity and low-disk-space feedback under the folder field."""
        label = getattr(self, "recording_folder_feedback", None)
        if label is None:
            return
        custom_path = self.recording_folder_path_var.get() or None

        ok, message = validate_recordings_path(custom_path)
        if not ok:
            label.configure(text=message, bootstyle="danger")
            return

        free = recordings_drive_free_bytes(custom_path)
        if free is not None and free <= LOW_DISK_SPACE_BYTES:
            label.configure(
                text="警告：磁盘空间不足。请清理或导出部分录制。",
                bootstyle="danger",
            )
            return

        # No note when the path is valid -- only surface problems.
        label.configure(text="")

    def _on_clear_recordings_clicked(self) -> None:
        if not messagebox.askyesno(
            "清除录制",
            "删除所有录制的对战数据包？此操作无法撤销。",
        ):
            return
        removed, freed = clear_recordings(custom_path=self.recording_folder_path_var.get() or None)
        messagebox.showinfo(
            "录制已清除",
            f"已删除 {removed} 个录制，释放 {freed / (1024**3):.2f} GB。",
        )

    def _update_advanced_settings_visibility(self, emulator_choice: str) -> None:
        show_advanced = bool(self.advanced_settings_var.get())

        def _toggle_frame(frame: ttk.Frame | None, should_show: bool) -> None:
            if not frame:
                return
            try:
                frame.pack_forget()
                if should_show:
                    frame.pack(fill=X, pady=(0, 6))
            except tk.TclError:
                return

        is_memu = emulator_choice == EmulatorType.MEMU
        is_bluestacks = emulator_choice == EmulatorType.BLUESTACKS

        _toggle_frame(getattr(self, "memu_advanced_frame", None), show_advanced and is_memu)
        _toggle_frame(getattr(self, "bluestacks_advanced_frame", None), show_advanced and is_bluestacks)

    def _on_advanced_settings_toggled(self) -> None:
        # Re-evaluate which emulator settings should be visible when the toggle changes
        self._show_current_emulator_settings()

    @staticmethod
    def _safe_int(value: object, fallback: int = 0) -> int:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _parse_winrate_value(raw: object) -> float | None:
        if isinstance(raw, str):
            stripped = raw.strip()
            if stripped.endswith("%"):
                stripped = stripped[:-1]
            try:
                return float(stripped)
            except ValueError:
                return None
        if isinstance(raw, int | float):
            return float(raw)
        return None

    @staticmethod
    def _calculate_winrate_percentage(wins: int, losses: int) -> float:
        total = wins + losses
        if total <= 0:
            return 0.0
        return wins / total * 100
