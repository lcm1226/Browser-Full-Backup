from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from browser_detection import BrowserInstall


LOGGER = logging.getLogger(__name__)


IGNORE_DIRECTORIES = {
    "Crashpad",
    "ShaderCache",
    "CertificateRevocation",
    "FileTypePolicies",
    "GrShaderCache",
    "MEIPreload",
    "PKIMetadata",
    "SafetyTips",
    "SwReporter",
    "WidevineCdm",
    "component_crx_cache",
}


@dataclass(slots=True)
class BrowserProfile:
    browser_key: str
    browser_name: str
    profile_dir_name: str
    profile_name: str
    path: Path


def discover_profiles(browser: BrowserInstall) -> list[BrowserProfile]:
    user_data = browser.user_data_dir
    if not user_data.exists():
        return []

    friendly_names = _load_profile_names_from_local_state(user_data)
    profiles: list[BrowserProfile] = []

    for child in sorted(user_data.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir():
            continue
        if child.name in IGNORE_DIRECTORIES:
            continue
        if not _looks_like_profile_dir(child):
            continue

        profile_name = friendly_names.get(child.name) or _profile_name_from_preferences(child)
        profiles.append(
            BrowserProfile(
                browser_key=browser.key,
                browser_name=browser.display_name,
                profile_dir_name=child.name,
                profile_name=profile_name or child.name,
                path=child,
            )
        )

    return profiles


def _looks_like_profile_dir(path: Path) -> bool:
    name = path.name
    if name == "Default" or name.startswith("Profile "):
        return True
    if name in {"Guest Profile", "System Profile"}:
        return True
    if (path / "Preferences").exists():
        return True
    return False


def _load_profile_names_from_local_state(user_data_dir: Path) -> dict[str, str]:
    local_state = user_data_dir / "Local State"
    if not local_state.exists():
        return {}

    try:
        payload = json.loads(local_state.read_text(encoding="utf-8"))
        info_cache = payload.get("profile", {}).get("info_cache", {})
        result: dict[str, str] = {}
        for profile_dir, details in info_cache.items():
            if isinstance(details, dict):
                display_name = details.get("name")
                if isinstance(display_name, str) and display_name.strip():
                    result[profile_dir] = display_name.strip()
        return result
    except (json.JSONDecodeError, OSError) as exc:
        LOGGER.debug("Could not parse Local State in %s: %s", user_data_dir, exc)
        return {}


def _profile_name_from_preferences(profile_dir: Path) -> str | None:
    preferences = profile_dir / "Preferences"
    if not preferences.exists():
        return None

    try:
        payload = json.loads(preferences.read_text(encoding="utf-8"))
        profile = payload.get("profile", {})
        display_name = profile.get("name")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.strip()
    except (json.JSONDecodeError, OSError) as exc:
        LOGGER.debug("Could not parse Preferences in %s: %s", profile_dir, exc)

    return None
