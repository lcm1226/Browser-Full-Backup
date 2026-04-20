from __future__ import annotations

import ctypes
import json
import logging
import os
import tkinter as tk
import winreg
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from backup_engine import SCOPE_FULL, SCOPE_SETTINGS_ONLY, BackupOptions, create_backup
from browser_detection import BrowserInstall, detect_installed_browsers
from profile_discovery import BrowserProfile, discover_profiles
from restore_engine import RestoreOptions, preview_restore, restore_backup


LOGGER = logging.getLogger(__name__)


def _get_windows_theme_mode() -> str:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            apps_use_light_theme, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return "light" if apps_use_light_theme else "dark"
    except OSError:
        return "light"


def _call_uxtheme_ordinal(ordinal: int, restype, argtypes: list[type], *args):
    try:
        uxtheme = ctypes.WinDLL("uxtheme", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetProcAddress.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        kernel32.GetProcAddress.restype = ctypes.c_void_p
        address = kernel32.GetProcAddress(ctypes.c_void_p(uxtheme._handle), ctypes.c_void_p(ordinal))
        if not address:
            return None
        function = ctypes.WINFUNCTYPE(restype, *argtypes)(address)
        return function(*args)
    except Exception:
        return None


def configure_windows_dark_mode_behavior(mode: str) -> None:
    preferred_mode = 1 if mode == "dark" else 0
    _call_uxtheme_ordinal(135, ctypes.c_int, [ctypes.c_int], preferred_mode)


@dataclass(slots=True)
class ThemePalette:
    mode: str
    background: str
    surface: str
    elevated: str
    border: str
    text: str
    muted_text: str
    accent: str
    accent_active: str
    warning: str
    input_background: str
    text_background: str
    text_insert: str


class TextWidgetHandler(logging.Handler):
    def __init__(self, widget: tk.Text) -> None:
        super().__init__()
        self.widget = widget

    def emit(self, record: logging.LogRecord) -> None:
        message = self.format(record)
        self.widget.after(0, self._append, message)

    def _append(self, message: str) -> None:
        self.widget.configure(state="normal")
        self.widget.insert("end", message + "\n")
        self.widget.see("end")
        self.widget.configure(state="disabled")


class ChromiumProfileBackupApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Chromium Profile Backup and Restore")
        self.root.geometry("1100x760")
        self.root.minsize(980, 680)
        self.use_custom_title_bar = self.root.tk.call("tk", "windowingsystem") == "win32"
        self.is_maximized = False
        self.last_normal_geometry = self.root.geometry()
        self._drag_origin_x = 0
        self._drag_origin_y = 0
        self._drag_window_x = 0
        self._drag_window_y = 0
        self._resize_origin_x = 0
        self._resize_origin_y = 0
        self._resize_origin_width = 0
        self._resize_origin_height = 0
        self.state_path = Path(__file__).resolve().parent / "ui_state.json"
        self.loaded_state = self._load_ui_state()
        self.style = ttk.Style(root)
        self.theme_mode = "light"
        self.palette = self._build_palette(self.theme_mode)
        self._apply_theme(force=True)

        self.browsers: list[BrowserInstall] = []
        self.browser_map: dict[str, BrowserInstall] = {}
        self.backup_profiles: list[BrowserProfile] = []
        self.restore_profiles: list[BrowserProfile] = []

        self.backup_browser_var = tk.StringVar()
        self.backup_profile_var = tk.StringVar()
        self.backup_destination_var = tk.StringVar()
        self.backup_password_var = tk.StringVar()
        self.backup_password_hint_var = tk.StringVar()
        self.backup_scope_var = tk.StringVar(value=SCOPE_FULL)
        self.backup_exclude_sensitive_var = tk.BooleanVar(value=True)
        self.backup_recovery_enrollment_var = tk.BooleanVar(value=False)
        self.backup_dry_run_var = tk.BooleanVar(value=False)

        self.restore_archive_var = tk.StringVar()
        self.restore_password_var = tk.StringVar()
        self.restore_browser_var = tk.StringVar()
        self.restore_profile_mode_var = tk.StringVar(value="existing")
        self.restore_existing_profile_var = tk.StringVar()
        self.restore_new_profile_var = tk.StringVar(value="Imported Profile")
        self.restore_dry_run_var = tk.BooleanVar(value=False)
        self.recent_backup_var = tk.StringVar()
        self.last_backup_folder: Path | None = None
        self.recent_backup_archives: list[str] = []
        self.recent_backup_labels: dict[str, str] = {}

        self._build_ui()
        self._apply_theme(force=True)
        self._request_title_bar_theme_refresh()
        self._configure_logging()
        self.refresh_browser_detection()
        self._apply_loaded_ui_state()
        self.root.protocol("WM_DELETE_WINDOW", self._close_window)
        self._schedule_theme_watch()

    def _detect_windows_theme_mode(self) -> str:
        return _get_windows_theme_mode()

    def _build_palette(self, mode: str) -> ThemePalette:
        if mode == "dark":
            return ThemePalette(
                mode="dark",
                background="#1E1E1E",
                surface="#252526",
                elevated="#2D2D30",
                border="#3F3F46",
                text="#F3F4F6",
                muted_text="#D4D4D8",
                accent="#3B82F6",
                accent_active="#2563EB",
                warning="#FCA5A5",
                input_background="#1F2937",
                text_background="#111827",
                text_insert="#F9FAFB",
            )

        return ThemePalette(
            mode="light",
            background="#F5F6F8",
            surface="#FFFFFF",
            elevated="#FAFAFB",
            border="#D6D9DE",
            text="#111827",
            muted_text="#374151",
            accent="#2563EB",
            accent_active="#1D4ED8",
            warning="#9A3412",
            input_background="#FFFFFF",
            text_background="#FFFFFF",
            text_insert="#111827",
        )

    def _apply_theme(self, force: bool = False) -> None:
        mode = self._detect_windows_theme_mode()
        if not force and mode == self.theme_mode:
            return

        self.theme_mode = mode
        self.palette = self._build_palette(mode)
        self.style.theme_use("clam")

        palette = self.palette
        self.root.configure(bg=palette.background)
        self.root.option_add("*TCombobox*Listbox.background", palette.surface)
        self.root.option_add("*TCombobox*Listbox.foreground", palette.text)
        self.root.option_add("*TCombobox*Listbox.selectBackground", palette.accent)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")

        self.style.configure(".", background=palette.background, foreground=palette.text)
        self.style.configure("TFrame", background=palette.background)
        self.style.configure(
            "TLabel",
            background=palette.background,
            foreground=palette.text,
        )
        self.style.configure(
            "Warning.TLabel",
            background=palette.background,
            foreground=palette.warning,
        )
        self.style.configure(
            "TLabelframe",
            background=palette.background,
            foreground=palette.text,
            bordercolor=palette.border,
            relief="solid",
        )
        self.style.configure(
            "TLabelframe.Label",
            background=palette.background,
            foreground=palette.text,
        )
        self.style.configure(
            "TButton",
            background=palette.elevated,
            foreground=palette.text,
            bordercolor=palette.border,
            focusthickness=1,
            focuscolor=palette.accent,
            padding=(10, 6),
        )
        self.style.map(
            "TButton",
            background=[("active", palette.accent_active), ("pressed", palette.accent_active)],
            foreground=[("active", "#FFFFFF"), ("pressed", "#FFFFFF")],
        )
        self.style.configure(
            "TEntry",
            fieldbackground=palette.input_background,
            foreground=palette.text,
            bordercolor=palette.border,
            insertcolor=palette.text_insert,
        )
        self.style.configure(
            "TCombobox",
            fieldbackground=palette.input_background,
            background=palette.input_background,
            foreground=palette.text,
            arrowcolor=palette.text,
            bordercolor=palette.border,
        )
        self.style.map(
            "TCombobox",
            fieldbackground=[("readonly", palette.input_background)],
            foreground=[("readonly", palette.text)],
            selectbackground=[("readonly", palette.input_background)],
            selectforeground=[("readonly", palette.text)],
        )
        self.style.configure(
            "TCheckbutton",
            background=palette.background,
            foreground=palette.text,
        )
        self.style.map(
            "TCheckbutton",
            background=[("active", palette.background)],
            foreground=[("active", palette.text)],
        )
        self.style.configure(
            "TRadiobutton",
            background=palette.background,
            foreground=palette.text,
        )
        self.style.map(
            "TRadiobutton",
            background=[("active", palette.background)],
            foreground=[("active", palette.text)],
        )
        self.style.configure(
            "TNotebook",
            background=palette.background,
            bordercolor=palette.border,
        )
        self.style.configure(
            "TNotebook.Tab",
            background=palette.elevated,
            foreground=palette.muted_text,
            bordercolor=palette.border,
            padding=(12, 6),
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", palette.surface), ("active", palette.elevated)],
            foreground=[("selected", palette.text), ("active", palette.text)],
        )

        self._apply_custom_title_bar_theme()
        self._request_title_bar_theme_refresh()
        self._apply_text_widget_theme()

    def _apply_text_widget_theme(self) -> None:
        palette = self.palette
        for widget_name in ("backup_preview_text", "restore_preview_text", "log_text"):
            widget = getattr(self, widget_name, None)
            if widget is None:
                continue
            widget.configure(
                bg=palette.text_background,
                fg=palette.text,
                insertbackground=palette.text_insert,
                selectbackground=palette.accent,
                selectforeground="#FFFFFF",
                highlightbackground=palette.border,
                highlightcolor=palette.accent,
                relief="solid",
                borderwidth=1,
            )

    def _request_title_bar_theme_refresh(self) -> None:
        if self.use_custom_title_bar:
            return
        for delay_ms in (0, 150, 500):
            self.root.after(delay_ms, self._set_windows_title_bar_theme)

    def _set_windows_title_bar_theme(self) -> None:
        try:
            self.root.update_idletasks()
            hwnd = self.root.winfo_id()
            root_hwnd = ctypes.windll.user32.GetAncestor(hwnd, 2) or hwnd
            _call_uxtheme_ordinal(133, ctypes.c_bool, [ctypes.c_void_p, ctypes.c_bool], root_hwnd, self.theme_mode == "dark")
            value = ctypes.c_int(0 if self.theme_mode == "light" else 1)
            for attribute_id in (20, 19):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    root_hwnd,
                    attribute_id,
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )

            caption_color = ctypes.c_uint(self._hex_to_colorref(self.palette.surface))
            border_color = ctypes.c_uint(self._hex_to_colorref(self.palette.border))
            text_color = ctypes.c_uint(self._hex_to_colorref(self.palette.text))
            for attribute_id, color_value in ((35, caption_color), (34, border_color), (36, text_color)):
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    root_hwnd,
                    attribute_id,
                    ctypes.byref(color_value),
                    ctypes.sizeof(color_value),
                )
        except Exception:
            return

    @staticmethod
    def _hex_to_colorref(value: str) -> int:
        value = value.lstrip("#")
        red = int(value[0:2], 16)
        green = int(value[2:4], 16)
        blue = int(value[4:6], 16)
        return red | (green << 8) | (blue << 16)

    def _schedule_theme_watch(self) -> None:
        self._apply_theme()
        self.root.after(2000, self._schedule_theme_watch)

    def _build_ui(self) -> None:
        content_parent: tk.Misc
        if self.use_custom_title_bar:
            self.root.overrideredirect(True)
            self.root.configure(bg=self.palette.border)
            self.root.bind("<Map>", self._on_window_mapped, add="+")
            self.root.bind("<Alt-F4>", self._close_window, add="+")

            self.window_frame = tk.Frame(self.root, bd=0, highlightthickness=1)
            self.window_frame.pack(fill="both", expand=True, padx=1, pady=1)

            self.title_bar_frame = tk.Frame(self.window_frame, height=38, bd=0, highlightthickness=0)
            self.title_bar_frame.pack(fill="x")
            self.title_bar_frame.pack_propagate(False)

            self.title_label = tk.Label(
                self.title_bar_frame,
                text="Chromium Profile Backup and Restore",
                anchor="w",
                padx=12,
                font=("Segoe UI", 10, "normal"),
            )
            self.title_label.pack(side="left", fill="both", expand=True)

            self.minimize_button = self._create_title_button("_", self._minimize_window)
            self.maximize_button = self._create_title_button("[ ]", self._toggle_maximize)
            self.close_button = self._create_title_button("X", self._close_window)

            self.close_button.pack(side="right", padx=(0, 2), pady=2)
            self.maximize_button.pack(side="right", pady=2)
            self.minimize_button.pack(side="right", pady=2)

            for widget in (self.title_bar_frame, self.title_label):
                widget.bind("<ButtonPress-1>", self._start_window_drag, add="+")
                widget.bind("<B1-Motion>", self._perform_window_drag, add="+")
                widget.bind("<Double-Button-1>", self._toggle_maximize, add="+")

            self.content_frame = tk.Frame(self.window_frame, bd=0, highlightthickness=0)
            self.content_frame.pack(fill="both", expand=True)
            content_parent = self.content_frame

            self.resize_grip = tk.Frame(
                self.window_frame,
                cursor="size_nw_se",
                width=14,
                height=14,
                bd=0,
                highlightthickness=0,
            )
            self.resize_grip.place(relx=1.0, rely=1.0, anchor="se")
            self.resize_grip.bind("<ButtonPress-1>", self._start_resize, add="+")
            self.resize_grip.bind("<B1-Motion>", self._perform_resize, add="+")
        else:
            content_parent = self.root

        warning_banner = ttk.Label(
            content_parent,
            text=(
                "Personal backup and migration tool only. Close Chrome, Brave, or Edge completely"
                " before backing up or restoring. This tool performs local file operations only"
                " and does not upload data anywhere."
            ),
            wraplength=1040,
            justify="left",
            style="Warning.TLabel",
        )
        warning_banner.pack(fill="x", padx=12, pady=(12, 8))

        notebook = ttk.Notebook(content_parent)
        notebook.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        backup_tab = ttk.Frame(notebook, padding=12)
        restore_tab = ttk.Frame(notebook, padding=12)
        notebook.add(backup_tab, text="Backup")
        notebook.add(restore_tab, text="Restore")

        self._build_backup_tab(backup_tab)
        self._build_restore_tab(restore_tab)

        log_frame = ttk.LabelFrame(content_parent, text="Activity Log", padding=8)
        log_frame.pack(fill="both", expand=False, padx=12, pady=(0, 12))
        self.log_text = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True)

    def _apply_custom_title_bar_theme(self) -> None:
        if not self.use_custom_title_bar:
            return

        palette = self.palette
        if hasattr(self, "window_frame"):
            self.root.configure(bg=palette.border)
            self.window_frame.configure(bg=palette.border, highlightbackground=palette.border)
        if hasattr(self, "content_frame"):
            self.content_frame.configure(bg=palette.background)
        if hasattr(self, "title_bar_frame"):
            self.title_bar_frame.configure(bg=palette.surface)
        if hasattr(self, "title_label"):
            self.title_label.configure(bg=palette.surface, fg=palette.text)
        for widget in ("minimize_button", "maximize_button", "close_button"):
            button = getattr(self, widget, None)
            if button is not None:
                button.configure(
                    bg=palette.surface,
                    fg=palette.text,
                    activebackground=palette.elevated if widget != "close_button" else "#B91C1C",
                    activeforeground="#FFFFFF" if widget == "close_button" else palette.text,
                )
        if hasattr(self, "resize_grip"):
            self.resize_grip.configure(bg=palette.surface)

    def _create_title_button(self, text: str, command) -> tk.Label:
        button = tk.Label(
            self.title_bar_frame,
            text=text,
            width=4,
            font=("Segoe UI", 10, "normal"),
            cursor="hand2",
            padx=4,
            pady=6,
        )
        button.bind("<Button-1>", command, add="+")
        button.bind("<Enter>", lambda event, widget=button: self._set_title_button_hover(widget, True), add="+")
        button.bind("<Leave>", lambda event, widget=button: self._set_title_button_hover(widget, False), add="+")
        return button

    def _set_title_button_hover(self, widget: tk.Label, active: bool) -> None:
        if not self.use_custom_title_bar:
            return
        if widget is getattr(self, "close_button", None):
            background = "#B91C1C" if active else self.palette.surface
            foreground = "#FFFFFF" if active else self.palette.text
        else:
            background = self.palette.elevated if active else self.palette.surface
            foreground = self.palette.text
        widget.configure(bg=background, fg=foreground)

    def _start_window_drag(self, event: tk.Event) -> None:
        if not self.use_custom_title_bar or self.is_maximized:
            return
        self._drag_origin_x = event.x_root
        self._drag_origin_y = event.y_root
        self._drag_window_x = self.root.winfo_x()
        self._drag_window_y = self.root.winfo_y()

    def _perform_window_drag(self, event: tk.Event) -> None:
        if not self.use_custom_title_bar or self.is_maximized:
            return
        delta_x = event.x_root - self._drag_origin_x
        delta_y = event.y_root - self._drag_origin_y
        self.root.geometry(f"+{self._drag_window_x + delta_x}+{self._drag_window_y + delta_y}")

    def _toggle_maximize(self, event: tk.Event | None = None) -> None:
        if not self.use_custom_title_bar:
            return
        if self.is_maximized:
            self._restore_window()
            return
        self.last_normal_geometry = self.root.geometry()
        left, top, width, height = self._get_work_area_geometry()
        self.root.geometry(f"{width}x{height}+{left}+{top}")
        self.is_maximized = True
        if hasattr(self, "maximize_button"):
            self.maximize_button.configure(text="O")

    def _restore_window(self) -> None:
        if not self.use_custom_title_bar:
            return
        self.root.geometry(self.last_normal_geometry)
        self.is_maximized = False
        if hasattr(self, "maximize_button"):
            self.maximize_button.configure(text="[ ]")

    def _minimize_window(self, event: tk.Event | None = None) -> None:
        if not self.use_custom_title_bar:
            self.root.iconify()
            return
        self.root.overrideredirect(False)
        self.root.iconify()

    def _close_window(self, event: tk.Event | None = None) -> str | None:
        self._save_ui_state()
        self.root.destroy()
        return "break" if event is not None else None

    def _on_window_mapped(self, event: tk.Event) -> None:
        if not self.use_custom_title_bar or event.widget is not self.root:
            return
        if self.root.state() == "normal":
            self.root.after(10, lambda: self.root.overrideredirect(True))

    def _start_resize(self, event: tk.Event) -> None:
        if not self.use_custom_title_bar:
            return
        self._resize_origin_x = event.x_root
        self._resize_origin_y = event.y_root
        self._resize_origin_width = self.root.winfo_width()
        self._resize_origin_height = self.root.winfo_height()

    def _perform_resize(self, event: tk.Event) -> None:
        if not self.use_custom_title_bar or self.is_maximized:
            return
        width = max(self.root.winfo_reqwidth(), self._resize_origin_width + (event.x_root - self._resize_origin_x))
        height = max(self.root.winfo_reqheight(), self._resize_origin_height + (event.y_root - self._resize_origin_y))
        min_width = 980
        min_height = 680
        self.root.geometry(f"{max(width, min_width)}x{max(height, min_height)}")
        self.last_normal_geometry = self.root.geometry()

    @staticmethod
    def _get_work_area_geometry() -> tuple[int, int, int, int]:
        rect = ctypes.wintypes.RECT()
        SPI_GETWORKAREA = 48
        if ctypes.windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
        width = ctypes.windll.user32.GetSystemMetrics(0)
        height = ctypes.windll.user32.GetSystemMetrics(1)
        return 0, 0, width, height

    def _build_backup_tab(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent)
        controls.pack(fill="both", expand=True)
        controls.columnconfigure(1, weight=1)

        ttk.Button(
            controls, text="Detect Installed Browsers", command=self.refresh_browser_detection
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))

        ttk.Label(controls, text="Browser").grid(row=1, column=0, sticky="w", pady=4)
        self.backup_browser_combo = ttk.Combobox(
            controls,
            textvariable=self.backup_browser_var,
            state="readonly",
            width=40,
        )
        self.backup_browser_combo.grid(row=1, column=1, sticky="ew", pady=4)
        self.backup_browser_combo.bind("<<ComboboxSelected>>", self._on_backup_browser_selected)

        ttk.Label(controls, text="Profile").grid(row=2, column=0, sticky="w", pady=4)
        self.backup_profile_combo = ttk.Combobox(
            controls,
            textvariable=self.backup_profile_var,
            state="readonly",
            width=50,
        )
        self.backup_profile_combo.grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(controls, text="Backup Scope").grid(row=3, column=0, sticky="nw", pady=4)
        scope_frame = ttk.Frame(controls)
        scope_frame.grid(row=3, column=1, sticky="w", pady=4)
        ttk.Radiobutton(
            scope_frame,
            text="Full profile backup",
            variable=self.backup_scope_var,
            value=SCOPE_FULL,
        ).pack(anchor="w")
        ttk.Radiobutton(
            scope_frame,
            text="Settings-only backup",
            variable=self.backup_scope_var,
            value=SCOPE_SETTINGS_ONLY,
        ).pack(anchor="w")
        ttk.Checkbutton(
            scope_frame,
            text="Exclude common cookies, sessions, and login databases",
            variable=self.backup_exclude_sensitive_var,
        ).pack(anchor="w", pady=(6, 0))

        ttk.Label(controls, text="Destination Folder").grid(row=4, column=0, sticky="w", pady=4)
        destination_row = ttk.Frame(controls)
        destination_row.grid(row=4, column=1, sticky="ew", pady=4)
        destination_row.columnconfigure(0, weight=1)
        ttk.Entry(destination_row, textvariable=self.backup_destination_var).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(destination_row, text="Browse", command=self._choose_backup_destination).grid(
            row=0, column=1, padx=(8, 0)
        )
        ttk.Button(destination_row, text="Open", command=self._open_backup_destination_ui).grid(
            row=0, column=2, padx=(8, 0)
        )

        ttk.Label(controls, text="Password (optional)").grid(
            row=5, column=0, sticky="w", pady=4
        )
        ttk.Entry(
            controls,
            textvariable=self.backup_password_var,
            show="*",
        ).grid(row=5, column=1, sticky="ew", pady=4)

        recovery_frame = ttk.Frame(controls)
        recovery_frame.grid(row=6, column=1, sticky="ew", pady=(4, 4))
        recovery_frame.columnconfigure(0, weight=1)
        ttk.Checkbutton(
            recovery_frame,
            text="Create offline recovery key file and emergency codes for this encrypted backup",
            variable=self.backup_recovery_enrollment_var,
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(controls, text="Password Hint (optional)").grid(
            row=7, column=0, sticky="w", pady=4
        )
        ttk.Entry(
            controls,
            textvariable=self.backup_password_hint_var,
        ).grid(row=7, column=1, sticky="ew", pady=4)

        ttk.Checkbutton(
            controls,
            text="Dry run only (show what would be backed up)",
            variable=self.backup_dry_run_var,
        ).grid(row=8, column=1, sticky="w", pady=(8, 8))

        actions = ttk.Frame(controls)
        actions.grid(row=9, column=1, sticky="w")
        ttk.Button(actions, text="Preview Backup", command=self.run_backup_preview).pack(
            side="left"
        )
        ttk.Button(actions, text="Create Backup", command=self.run_backup).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(actions, text="Open Last Backup Folder", command=self._open_last_backup_folder_ui).pack(
            side="left", padx=(8, 0)
        )

        preview_frame = ttk.LabelFrame(parent, text="Backup Preview", padding=8)
        preview_frame.pack(fill="both", expand=True, pady=(12, 0))
        self.backup_preview_text = tk.Text(preview_frame, wrap="word", state="disabled")
        self.backup_preview_text.pack(fill="both", expand=True)

    def _build_restore_tab(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent)
        controls.pack(fill="both", expand=True)
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Backup Archive").grid(row=0, column=0, sticky="w", pady=4)
        archive_row = ttk.Frame(controls)
        archive_row.grid(row=0, column=1, sticky="ew", pady=4)
        archive_row.columnconfigure(0, weight=1)
        ttk.Entry(archive_row, textvariable=self.restore_archive_var).grid(
            row=0, column=0, sticky="ew"
        )
        ttk.Button(archive_row, text="Browse", command=self._choose_restore_archive).grid(
            row=0, column=1, padx=(8, 0)
        )
        ttk.Button(archive_row, text="Open", command=self._open_restore_archive_location_ui).grid(
            row=0, column=2, padx=(8, 0)
        )

        ttk.Label(controls, text="Password (if encrypted)").grid(
            row=1, column=0, sticky="w", pady=4
        )
        ttk.Entry(
            controls,
            textvariable=self.restore_password_var,
            show="*",
        ).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(controls, text="Recent Backups").grid(row=2, column=0, sticky="w", pady=4)
        recent_row = ttk.Frame(controls)
        recent_row.grid(row=2, column=1, sticky="ew", pady=4)
        recent_row.columnconfigure(0, weight=1)
        self.recent_backup_combo = ttk.Combobox(
            recent_row,
            textvariable=self.recent_backup_var,
            state="readonly",
            width=60,
        )
        self.recent_backup_combo.grid(row=0, column=0, sticky="ew")
        ttk.Button(recent_row, text="Use Selected", command=self._use_recent_backup_ui).grid(
            row=0, column=1, padx=(8, 0)
        )
        ttk.Button(recent_row, text="Open Folder", command=self._open_recent_backup_folder_ui).grid(
            row=0, column=2, padx=(8, 0)
        )

        ttk.Label(controls, text="Destination Browser").grid(
            row=3, column=0, sticky="w", pady=4
        )
        self.restore_browser_combo = ttk.Combobox(
            controls,
            textvariable=self.restore_browser_var,
            state="readonly",
            width=40,
        )
        self.restore_browser_combo.grid(row=3, column=1, sticky="ew", pady=4)
        self.restore_browser_combo.bind("<<ComboboxSelected>>", self._on_restore_browser_selected)

        ttk.Label(controls, text="Destination Profile").grid(
            row=4, column=0, sticky="nw", pady=4
        )
        profile_mode_frame = ttk.Frame(controls)
        profile_mode_frame.grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Radiobutton(
            profile_mode_frame,
            text="Existing profile",
            variable=self.restore_profile_mode_var,
            value="existing",
            command=self._toggle_restore_profile_mode,
        ).pack(anchor="w")
        self.restore_existing_combo = ttk.Combobox(
            profile_mode_frame,
            textvariable=self.restore_existing_profile_var,
            state="readonly",
            width=50,
        )
        self.restore_existing_combo.pack(fill="x", pady=(2, 8))
        ttk.Radiobutton(
            profile_mode_frame,
            text="Create / restore into a new profile folder",
            variable=self.restore_profile_mode_var,
            value="new",
            command=self._toggle_restore_profile_mode,
        ).pack(anchor="w")
        self.restore_new_entry = ttk.Entry(
            profile_mode_frame,
            textvariable=self.restore_new_profile_var,
            width=50,
        )
        self.restore_new_entry.pack(fill="x", pady=(2, 0))

        ttk.Checkbutton(
            controls,
            text="Dry run only (show what would be restored)",
            variable=self.restore_dry_run_var,
        ).grid(row=5, column=1, sticky="w", pady=(8, 8))

        actions = ttk.Frame(controls)
        actions.grid(row=6, column=1, sticky="w")
        ttk.Button(actions, text="Preview Restore", command=self.run_restore_preview).pack(
            side="left"
        )
        ttk.Button(actions, text="Run Restore", command=self.run_restore).pack(
            side="left", padx=(8, 0)
        )

        preview_frame = ttk.LabelFrame(parent, text="Restore Preview", padding=8)
        preview_frame.pack(fill="both", expand=True, pady=(12, 0))
        self.restore_preview_text = tk.Text(preview_frame, wrap="word", state="disabled")
        self.restore_preview_text.pack(fill="both", expand=True)

    def _configure_logging(self) -> None:
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        if not any(isinstance(handler, TextWidgetHandler) for handler in root_logger.handlers):
            widget_handler = TextWidgetHandler(self.log_text)
            widget_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
            root_logger.addHandler(widget_handler)

        log_path = Path(__file__).resolve().parent / "chromium_profile_backup.log"
        if not any(
            isinstance(handler, logging.FileHandler)
            and Path(getattr(handler, "baseFilename", "")) == log_path
            for handler in root_logger.handlers
        ):
            file_handler = logging.FileHandler(log_path, encoding="utf-8")
            file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            root_logger.addHandler(file_handler)

    def refresh_browser_detection(self) -> None:
        self.browsers = detect_installed_browsers()
        self.browser_map = {
            self._browser_display_value(browser): browser for browser in self.browsers
        }
        browser_values = list(self.browser_map.keys())

        self.backup_browser_combo["values"] = browser_values
        self.restore_browser_combo["values"] = browser_values

        if browser_values:
            self.backup_browser_var.set(browser_values[0])
            self.restore_browser_var.set(browser_values[0])
            self._on_backup_browser_selected()
            self._on_restore_browser_selected()
            LOGGER.info("Detected %s supported browser installation(s).", len(browser_values))
        else:
            self.backup_browser_var.set("")
            self.restore_browser_var.set("")
            self.backup_profile_combo["values"] = []
            self.restore_existing_combo["values"] = []
            LOGGER.warning(
                "No supported Chromium browsers were detected in the standard Windows locations."
            )

    def _load_ui_state(self) -> dict[str, object]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_ui_state(self) -> None:
        geometry = self._geometry_for_save()
        state = {
            "geometry": geometry,
            "backup": {
                "destination": self.backup_destination_var.get().strip(),
                "browser_key": self._selected_browser_key(self.backup_browser_var.get()),
                "profile_dir_name": self._selected_profile_dir_name(self.backup_profile_var.get()),
                "scope": self.backup_scope_var.get(),
                "exclude_sensitive": bool(self.backup_exclude_sensitive_var.get()),
                "recovery_enrollment": bool(self.backup_recovery_enrollment_var.get()),
                "password_hint": self.backup_password_hint_var.get().strip(),
                "dry_run": bool(self.backup_dry_run_var.get()),
            },
            "restore": {
                "archive": self.restore_archive_var.get().strip(),
                "browser_key": self._selected_browser_key(self.restore_browser_var.get()),
                "mode": self.restore_profile_mode_var.get(),
                "existing_profile_dir_name": self._selected_profile_dir_name(
                    self.restore_existing_profile_var.get()
                ),
                "new_profile_name": self.restore_new_profile_var.get().strip(),
                "dry_run": bool(self.restore_dry_run_var.get()),
            },
            "recent_backups": self.recent_backup_archives[:10],
        }
        try:
            self.state_path.write_text(
                json.dumps(state, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            LOGGER.warning("Could not save UI state: %s", exc)

    def _geometry_for_save(self) -> str:
        if self.is_maximized:
            return self.last_normal_geometry
        current = self.root.geometry()
        try:
            size_part = current.split("+", 1)[0]
            width_text, height_text = size_part.split("x", 1)
            width = int(width_text)
            height = int(height_text)
            if width < 980 or height < 680:
                return self.last_normal_geometry
        except (ValueError, IndexError):
            return self.last_normal_geometry
        return current

    def _apply_loaded_ui_state(self) -> None:
        if not self.loaded_state:
            return

        geometry = self.loaded_state.get("geometry")
        if isinstance(geometry, str) and geometry.strip():
            try:
                self.root.geometry(geometry)
                self.last_normal_geometry = geometry
            except tk.TclError:
                pass

        backup_state = self.loaded_state.get("backup")
        if isinstance(backup_state, dict):
            self.backup_destination_var.set(str(backup_state.get("destination", "")).strip())
            self.backup_scope_var.set(str(backup_state.get("scope", SCOPE_FULL)) or SCOPE_FULL)
            self.backup_exclude_sensitive_var.set(
                bool(backup_state.get("exclude_sensitive", True))
            )
            self.backup_recovery_enrollment_var.set(
                bool(backup_state.get("recovery_enrollment", False))
            )
            self.backup_password_hint_var.set(
                str(backup_state.get("password_hint", "")).strip()
            )
            self.backup_dry_run_var.set(bool(backup_state.get("dry_run", False)))
            self._restore_browser_selection(
                combo_var=self.backup_browser_var,
                browser_key=backup_state.get("browser_key"),
                on_selected=self._on_backup_browser_selected,
            )
            self._restore_profile_selection(
                combo_var=self.backup_profile_var,
                profile_dir_name=backup_state.get("profile_dir_name"),
                profiles=self.backup_profiles,
            )

        restore_state = self.loaded_state.get("restore")
        if isinstance(restore_state, dict):
            self.restore_archive_var.set(str(restore_state.get("archive", "")).strip())
            self.restore_profile_mode_var.set(
                str(restore_state.get("mode", "existing")) or "existing"
            )
            self.restore_new_profile_var.set(
                str(restore_state.get("new_profile_name", "Imported Profile")).strip()
                or "Imported Profile"
            )
            self.restore_dry_run_var.set(bool(restore_state.get("dry_run", False)))
            self._restore_browser_selection(
                combo_var=self.restore_browser_var,
                browser_key=restore_state.get("browser_key"),
                on_selected=self._on_restore_browser_selected,
            )
            self._restore_profile_selection(
                combo_var=self.restore_existing_profile_var,
                profile_dir_name=restore_state.get("existing_profile_dir_name"),
                profiles=self.restore_profiles,
            )
            self._toggle_restore_profile_mode()

        recent_backups = self.loaded_state.get("recent_backups")
        if isinstance(recent_backups, list):
            for entry in recent_backups:
                if isinstance(entry, str):
                    self._add_recent_backup_archive(Path(entry), save_state=False)

    def _restore_browser_selection(self, combo_var: tk.StringVar, browser_key: object, on_selected) -> None:
        if not isinstance(browser_key, str) or not browser_key.strip():
            return
        for display_value, browser in self.browser_map.items():
            if browser.key == browser_key:
                combo_var.set(display_value)
                on_selected()
                return

    @staticmethod
    def _restore_profile_selection(
        combo_var: tk.StringVar,
        profile_dir_name: object,
        profiles: list[BrowserProfile],
    ) -> None:
        if not isinstance(profile_dir_name, str) or not profile_dir_name.strip():
            return
        for profile in profiles:
            if profile.profile_dir_name == profile_dir_name:
                combo_var.set(f"{profile.profile_dir_name} | {profile.profile_name}")
                return

    def _selected_browser_key(self, display_value: str) -> str | None:
        browser = self.browser_map.get(display_value)
        return browser.key if browser else None

    @staticmethod
    def _selected_profile_dir_name(display_value: str) -> str | None:
        selected = display_value.strip()
        if not selected:
            return None
        return selected.split(" | ", 1)[0]

    def _add_recent_backup_archive(self, archive_path: Path, save_state: bool = True) -> None:
        normalized = str(archive_path.resolve())
        self.recent_backup_archives = [
            item for item in self.recent_backup_archives if item != normalized
        ]
        self.recent_backup_archives.insert(0, normalized)
        self.recent_backup_archives = [
            item for item in self.recent_backup_archives[:10] if Path(item).exists()
        ]
        if hasattr(self, "recent_backup_combo"):
            self.recent_backup_labels = {
                item: self._recent_backup_label(Path(item)) for item in self.recent_backup_archives
            }
            labels = [self.recent_backup_labels[item] for item in self.recent_backup_archives]
            self.recent_backup_combo["values"] = labels
            self.recent_backup_var.set(labels[0] if labels else "")
        if save_state:
            self._save_ui_state()

    def _selected_recent_backup_path(self) -> Path:
        selected_label = self.recent_backup_var.get().strip()
        if not selected_label:
            raise RuntimeError("Choose one of the recent backup archives first.")
        for archive_path, label in self.recent_backup_labels.items():
            if label == selected_label:
                path = Path(archive_path)
                if not path.exists():
                    raise RuntimeError("The selected recent backup archive no longer exists.")
                return path
        raise RuntimeError("The selected recent backup archive could not be resolved.")

    @staticmethod
    def _recent_backup_label(archive_path: Path) -> str:
        try:
            modified = datetime.fromtimestamp(archive_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except OSError:
            modified = "unknown time"
        return f"{archive_path.name} | {modified} | {archive_path.parent}"

    def run_backup_preview(self) -> None:
        try:
            result = create_backup(self._build_backup_options(dry_run=True))
            text = self._format_backup_preview(result.manifest, result.copied_files, result.warnings)
            self._set_text(self.backup_preview_text, text)
        except Exception as exc:
            messagebox.showerror("Backup Preview Failed", str(exc))
            LOGGER.exception("Backup preview failed: %s", exc)

    def run_backup(self) -> None:
        try:
            result = create_backup(self._build_backup_options(dry_run=self.backup_dry_run_var.get()))
            preview_text = self._format_backup_preview(
                result.manifest,
                result.copied_files,
                result.warnings,
            )
            self._set_text(self.backup_preview_text, preview_text)

            if result.dry_run:
                messagebox.showinfo(
                    "Dry Run Complete",
                    f"{len(result.copied_files)} files would be backed up. Review the preview pane.",
                )
                return

            messagebox.showinfo(
                "Backup Complete",
                "Backup created successfully.\n\n"
                f"Archive: {result.archive_path}\n"
                f"Manifest: {result.manifest_path}"
                + (
                    f"\nRecovery key: {result.recovery_key_path}\n"
                    f"Emergency codes: {result.emergency_codes_path}"
                    if result.recovery_key_path and result.emergency_codes_path
                    else ""
                ),
            )
            if result.archive_path is not None:
                self.last_backup_folder = result.archive_path.parent
                self._add_recent_backup_archive(result.archive_path)
        except Exception as exc:
            messagebox.showerror("Backup Failed", str(exc))
            LOGGER.exception("Backup failed: %s", exc)

    def run_restore_preview(self) -> None:
        try:
            preview = preview_restore(
                archive_path=Path(self.restore_archive_var.get()),
                destination_profile_path=self._get_restore_destination_path(),
                password=self.restore_password_var.get().strip() or None,
            )
            self._set_text(self.restore_preview_text, self._format_restore_preview(preview))
        except Exception as exc:
            messagebox.showerror("Restore Preview Failed", str(exc))
            LOGGER.exception("Restore preview failed: %s", exc)

    def run_restore(self) -> None:
        try:
            options = self._build_restore_options(dry_run=self.restore_dry_run_var.get())
            preview = preview_restore(
                archive_path=options.archive_path,
                destination_profile_path=options.destination_profile_path,
                password=options.password,
            )
            self._set_text(self.restore_preview_text, self._format_restore_preview(preview))

            if not options.dry_run:
                confirm = messagebox.askyesno(
                    "Confirm Restore",
                    "Review the restore preview carefully before continuing.\n\n"
                    f"Files to add: {len(preview.files_to_add)}\n"
                    f"Files to overwrite: {len(preview.files_to_overwrite)}\n\n"
                    "A rollback snapshot will be created automatically if the destination profile"
                    " already contains files.\n\nProceed with restore?",
                )
                if not confirm:
                    return

            result = restore_backup(options)
            self.refresh_browser_detection()

            if result.dry_run:
                messagebox.showinfo(
                    "Dry Run Complete",
                    f"{len(result.restored_files)} files would be restored. Review the preview pane.",
                )
                return

            snapshot_message = (
                f"\nRollback snapshot: {result.rollback_snapshot}"
                if result.rollback_snapshot
                else "\nRollback snapshot: not needed because the destination profile was empty."
            )
            messagebox.showinfo(
                "Restore Complete",
                "Restore completed successfully."
                f"{snapshot_message}",
            )
        except Exception as exc:
            messagebox.showerror("Restore Failed", str(exc))
            LOGGER.exception("Restore failed: %s", exc)

    def _build_backup_options(self, dry_run: bool) -> BackupOptions:
        browser = self._selected_browser(self.backup_browser_var.get())
        profile = self._selected_backup_profile()
        destination_text = self.backup_destination_var.get().strip()
        if not destination_text:
            raise RuntimeError("Choose a destination folder for the backup archive.")
        destination = Path(destination_text)
        password = self.backup_password_var.get().strip() or None
        password_hint = self.backup_password_hint_var.get().strip() or None
        if self.backup_recovery_enrollment_var.get() and not password:
            raise RuntimeError(
                "Set a backup password before enabling the offline recovery key and emergency codes."
            )
        if password_hint and not password:
            raise RuntimeError("A password hint only makes sense when the backup archive is encrypted.")

        return BackupOptions(
            browser=browser,
            profile=profile,
            destination_dir=destination,
            backup_scope=self.backup_scope_var.get(),
            exclude_sensitive_data=self.backup_exclude_sensitive_var.get(),
            password=password,
            enroll_recovery_material=self.backup_recovery_enrollment_var.get(),
            password_hint=password_hint,
            dry_run=dry_run,
        )

    def _build_restore_options(self, dry_run: bool) -> RestoreOptions:
        archive_text = self.restore_archive_var.get().strip()
        if not archive_text:
            raise RuntimeError("Choose an existing backup archive before restoring.")
        archive_path = Path(archive_text)
        if not archive_path.exists():
            raise RuntimeError("The selected backup archive does not exist.")

        destination_profile_path = self._get_restore_destination_path()
        browser = self._selected_browser(self.restore_browser_var.get())

        overwrite_existing = (
            self.restore_profile_mode_var.get() == "existing"
            and destination_profile_path.exists()
            and any(destination_profile_path.iterdir())
        )

        return RestoreOptions(
            browser=browser,
            archive_path=archive_path,
            destination_profile_path=destination_profile_path,
            overwrite_existing=overwrite_existing,
            password=self.restore_password_var.get().strip() or None,
            dry_run=dry_run,
        )

    def _get_restore_destination_path(self) -> Path:
        browser = self._selected_browser(self.restore_browser_var.get())
        if self.restore_profile_mode_var.get() == "new":
            new_profile_name = self.restore_new_profile_var.get().strip()
            if not new_profile_name:
                raise RuntimeError("Enter a folder name for the new destination profile.")
            return browser.user_data_dir / new_profile_name

        selected = self.restore_existing_profile_var.get().strip()
        if not selected:
            raise RuntimeError("Choose an existing destination profile or switch to new profile mode.")
        folder_name = selected.split(" | ", 1)[0]
        return browser.user_data_dir / folder_name

    def _selected_browser(self, display_value: str) -> BrowserInstall:
        browser = self.browser_map.get(display_value)
        if browser is None:
            raise RuntimeError("Select one of the detected supported browsers.")
        return browser

    def _selected_backup_profile(self) -> BrowserProfile:
        selected = self.backup_profile_var.get().strip()
        if not selected:
            raise RuntimeError("Choose a source profile to back up.")

        profile_dir = selected.split(" | ", 1)[0]
        for profile in self.backup_profiles:
            if profile.profile_dir_name == profile_dir:
                return profile
        raise RuntimeError("The selected source profile could not be resolved.")

    def _on_backup_browser_selected(self, _event=None) -> None:
        browser = self.browser_map.get(self.backup_browser_var.get())
        if browser is None:
            self.backup_profile_combo["values"] = []
            return

        self.backup_profiles = discover_profiles(browser)
        values = [
            f"{profile.profile_dir_name} | {profile.profile_name}"
            for profile in self.backup_profiles
        ]
        self.backup_profile_combo["values"] = values
        self.backup_profile_var.set(values[0] if values else "")

    def _on_restore_browser_selected(self, _event=None) -> None:
        browser = self.browser_map.get(self.restore_browser_var.get())
        if browser is None:
            self.restore_existing_combo["values"] = []
            return

        self.restore_profiles = discover_profiles(browser)
        values = [
            f"{profile.profile_dir_name} | {profile.profile_name}"
            for profile in self.restore_profiles
        ]
        self.restore_existing_combo["values"] = values
        self.restore_existing_profile_var.set(values[0] if values else "")
        self._toggle_restore_profile_mode()

    def _toggle_restore_profile_mode(self) -> None:
        existing_enabled = self.restore_profile_mode_var.get() == "existing"
        self.restore_existing_combo.configure(
            state="readonly" if existing_enabled else "disabled"
        )
        self.restore_new_entry.configure(state="disabled" if existing_enabled else "normal")

    def _choose_backup_destination(self) -> None:
        directory = filedialog.askdirectory(title="Choose Backup Destination Folder")
        if directory:
            self.backup_destination_var.set(directory)

    def _choose_restore_archive(self) -> None:
        filename = filedialog.askopenfilename(
            title="Choose Backup Archive",
            filetypes=[("ZIP archives", "*.zip"), ("All files", "*.*")],
        )
        if filename:
            self.restore_archive_var.set(filename)
            self._add_recent_backup_archive(Path(filename))

    def _open_backup_destination(self) -> None:
        destination_text = self.backup_destination_var.get().strip()
        if not destination_text:
            raise RuntimeError("Choose or enter a backup destination folder first.")
        self._open_path(Path(destination_text))

    def _open_last_backup_folder(self) -> None:
        if self.last_backup_folder is None:
            raise RuntimeError("Create a backup first so there is a recent backup folder to open.")
        self._open_path(self.last_backup_folder)

    def _open_restore_archive_location(self) -> None:
        archive_text = self.restore_archive_var.get().strip()
        if not archive_text:
            raise RuntimeError("Choose a backup archive first.")
        archive_path = Path(archive_text)
        if archive_path.exists():
            self._open_path(archive_path.parent if archive_path.is_file() else archive_path)
            return
        raise RuntimeError("The selected backup archive path does not exist.")

    def _use_recent_backup(self) -> None:
        archive_path = self._selected_recent_backup_path()
        self.restore_archive_var.set(str(archive_path))
        self._add_recent_backup_archive(archive_path)

    def _open_recent_backup_folder(self) -> None:
        archive_path = self._selected_recent_backup_path()
        self._open_path(archive_path.parent)

    def _open_backup_destination_ui(self) -> None:
        self._run_ui_action(self._open_backup_destination, "Open Folder Failed")

    def _open_last_backup_folder_ui(self) -> None:
        self._run_ui_action(self._open_last_backup_folder, "Open Folder Failed")

    def _open_restore_archive_location_ui(self) -> None:
        self._run_ui_action(self._open_restore_archive_location, "Open Folder Failed")

    def _use_recent_backup_ui(self) -> None:
        self._run_ui_action(self._use_recent_backup, "Use Recent Backup Failed")

    def _open_recent_backup_folder_ui(self) -> None:
        self._run_ui_action(self._open_recent_backup_folder, "Open Folder Failed")

    @staticmethod
    def _run_ui_action(action, title: str) -> None:
        try:
            action()
        except Exception as exc:
            messagebox.showerror(title, str(exc))

    @staticmethod
    def _open_path(path: Path) -> None:
        if not path.exists():
            raise RuntimeError(f"The path does not exist: {path}")
        try:
            os.startfile(str(path))
        except OSError as exc:
            raise RuntimeError(f"Could not open the path in File Explorer: {path}") from exc

    @staticmethod
    def _browser_display_value(browser: BrowserInstall) -> str:
        version = f" | {browser.version}" if browser.version else ""
        return f"{browser.display_name} | {browser.user_data_dir}{version}"

    @staticmethod
    def _set_text(widget: tk.Text, value: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    @staticmethod
    def _format_backup_preview(manifest, files: list[str], warnings: list[str]) -> str:
        lines = [
            f"Archive encrypted: {'Yes' if manifest.encrypted else 'No'}",
            f"Recovery enrolled: {'Yes' if manifest.recovery_enrolled else 'No'}",
            f"Password hint stored: {'Yes' if manifest.password_hint else 'No'}",
        ]
        if manifest.recovery_artifacts:
            lines.append("Recovery artifacts to create:")
            lines.extend(f"- {entry}" for entry in manifest.recovery_artifacts)
        lines.extend(
            [
                "",
            f"Files selected: {len(files)}",
            "",
            ]
        )
        if warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in warnings)
            lines.append("")
        lines.append("First 200 archive entries:")
        lines.extend(f"- {file_name}" for file_name in files[:200])
        if len(files) > 200:
            lines.append(f"... {len(files) - 200} more file(s)")
        return "\n".join(lines)

    @staticmethod
    def _format_restore_preview(preview) -> str:
        lines = [
            f"Source browser: {preview.manifest.browser_name}",
            f"Source profile: {preview.manifest.profile_name} ({preview.manifest.profile_dir_name})",
            f"Backup scope: {preview.manifest.backup_scope}",
            f"Files in archive: {len(preview.archive_entries)}",
            f"Files to add: {len(preview.files_to_add)}",
            f"Files to overwrite: {len(preview.files_to_overwrite)}",
            "",
        ]
        if preview.warnings:
            lines.append("Warnings:")
            lines.extend(f"- {warning}" for warning in preview.warnings)
            lines.append("")
        lines.append("First 100 files to overwrite:")
        lines.extend(f"- {file_name}" for file_name in preview.files_to_overwrite[:100])
        if len(preview.files_to_overwrite) > 100:
            lines.append(f"... {len(preview.files_to_overwrite) - 100} more overwrite(s)")
        lines.append("")
        lines.append("First 100 files to add:")
        lines.extend(f"- {file_name}" for file_name in preview.files_to_add[:100])
        if len(preview.files_to_add) > 100:
            lines.append(f"... {len(preview.files_to_add) - 100} more addition(s)")
        return "\n".join(lines)


def run() -> None:
    configure_windows_dark_mode_behavior(_get_windows_theme_mode())
    root = tk.Tk()
    ChromiumProfileBackupApp(root)
    root.mainloop()
