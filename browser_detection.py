from __future__ import annotations

import ctypes
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import psutil


LOGGER = logging.getLogger(__name__)


GENERIC_READ = 0x80000000
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


@dataclass(slots=True)
class BrowserInstall:
    key: str
    display_name: str
    process_names: list[str]
    user_data_dir: Path
    executable_candidates: list[Path]
    executable_path: Path | None = None
    version: str | None = None
    installed: bool = False
    running_processes: list[str] = field(default_factory=list)


def _local_app_data() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA is not available on this Windows system.")
    return Path(local)


def supported_browser_definitions() -> list[BrowserInstall]:
    local = _local_app_data()
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    )

    return [
        BrowserInstall(
            key="chrome",
            display_name="Google Chrome",
            process_names=["chrome.exe"],
            user_data_dir=local / "Google" / "Chrome" / "User Data",
            executable_candidates=[
                program_files / "Google" / "Chrome" / "Application" / "chrome.exe",
                program_files_x86 / "Google" / "Chrome" / "Application" / "chrome.exe",
                local / "Google" / "Chrome" / "Application" / "chrome.exe",
            ],
        ),
        BrowserInstall(
            key="brave",
            display_name="Brave",
            process_names=["brave.exe"],
            user_data_dir=local / "BraveSoftware" / "Brave-Browser" / "User Data",
            executable_candidates=[
                program_files
                / "BraveSoftware"
                / "Brave-Browser"
                / "Application"
                / "brave.exe",
                program_files_x86
                / "BraveSoftware"
                / "Brave-Browser"
                / "Application"
                / "brave.exe",
                local
                / "BraveSoftware"
                / "Brave-Browser"
                / "Application"
                / "brave.exe",
            ],
        ),
        BrowserInstall(
            key="edge",
            display_name="Microsoft Edge",
            process_names=["msedge.exe"],
            user_data_dir=local / "Microsoft" / "Edge" / "User Data",
            executable_candidates=[
                program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                program_files_x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                local / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            ],
        ),
    ]


def detect_installed_browsers() -> list[BrowserInstall]:
    installs = supported_browser_definitions()
    running = _collect_running_process_names()

    for browser in installs:
        browser.executable_path = next(
            (candidate for candidate in browser.executable_candidates if candidate.exists()),
            None,
        )
        browser.installed = browser.user_data_dir.exists() or browser.executable_path is not None
        browser.version = (
            get_file_version(browser.executable_path) if browser.executable_path else None
        )
        browser.running_processes = sorted(
            {name for name in running if name.lower() in set(browser.process_names)}
        )

    return [browser for browser in installs if browser.installed]


def _collect_running_process_names() -> list[str]:
    names: list[str] = []
    for proc in psutil.process_iter(["name"]):
        try:
            name = proc.info.get("name")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if name:
            names.append(name.lower())
    return names


def get_file_version(executable_path: Path) -> str | None:
    if not executable_path.exists():
        return None

    escaped_path = str(executable_path).replace("'", "''")
    command = (
        "$ErrorActionPreference='Stop'; "
        f"(Get-Item -LiteralPath '{escaped_path}').VersionInfo.ProductVersion"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        version = completed.stdout.strip()
        return version or None
    except (subprocess.SubprocessError, OSError) as exc:
        LOGGER.debug("Could not detect browser version for %s: %s", executable_path, exc)
        return None


def validate_browser_closed(
    browser: BrowserInstall,
    profile_path: Path,
    extra_lock_targets: Iterable[str] | None = None,
) -> list[str]:
    problems: list[str] = []

    # We fail closed here: a running process or an exclusive-lock failure is enough to stop
    # backup or restore, because Chromium can mutate profile databases while the user is copying.
    running = _collect_running_process_names()
    active = sorted({name for name in running if name in set(browser.process_names)})
    if active:
        problems.append(
            f"{browser.display_name} appears to still be running ({', '.join(active)})."
        )

    for locked_file in detect_locked_profile_files(profile_path, extra_lock_targets):
        problems.append(f"Locked file detected: {locked_file}")

    return problems


def detect_locked_profile_files(
    profile_path: Path,
    extra_lock_targets: Iterable[str] | None = None,
) -> list[str]:
    lock_candidates = [
        "Preferences",
        "History",
        "Favicons",
        "Login Data",
        "Network/Cookies",
        "Current Session",
        "Current Tabs",
    ]
    if extra_lock_targets:
        lock_candidates.extend(extra_lock_targets)

    locked: list[str] = []
    for relative in lock_candidates:
        candidate = profile_path / relative
        if candidate.exists() and not can_open_exclusive(candidate):
            locked.append(str(candidate))
    return locked


def can_open_exclusive(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return True

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateFileW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    kernel32.CreateFileW.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int

    handle = kernel32.CreateFileW(
        str(path),
        GENERIC_READ,
        0,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )

    if handle == INVALID_HANDLE_VALUE:
        return False

    kernel32.CloseHandle(handle)
    return True
