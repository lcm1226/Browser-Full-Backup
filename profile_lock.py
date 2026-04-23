from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import subprocess
from dataclasses import dataclass
from pathlib import Path

from browser_detection import BrowserInstall
from profile_discovery import BrowserProfile


LOGGER = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 310_000
PASSWORD_HASH_NAME = "sha256"
LOCK_FILE_VERSION = 1


@dataclass(slots=True)
class ProfileLockRecord:
    browser_key: str
    profile_dir_name: str
    salt: str
    password_hash: str
    iterations: int
    hash_name: str


class ProfileLockStore:
    """Local password gate for launching profiles through this app only.

    This is intentionally not a Chromium security boundary. The records only decide
    whether this app will launch a selected browser profile after password entry.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._records = self._load_records()

    def is_locked(self, browser_key: str, profile_dir_name: str) -> bool:
        return self._lock_key(browser_key, profile_dir_name) in self._records

    def set_password(self, browser_key: str, profile_dir_name: str, password: str) -> None:
        self._validate_password(password)
        salt_bytes = secrets.token_bytes(16)
        password_hash = self._hash_password(password, salt_bytes, PBKDF2_ITERATIONS)
        record = ProfileLockRecord(
            browser_key=browser_key,
            profile_dir_name=profile_dir_name,
            salt=base64.b64encode(salt_bytes).decode("ascii"),
            password_hash=base64.b64encode(password_hash).decode("ascii"),
            iterations=PBKDF2_ITERATIONS,
            hash_name=PASSWORD_HASH_NAME,
        )
        self._records[self._lock_key(browser_key, profile_dir_name)] = record
        self._save_records()

    def verify_password(self, browser_key: str, profile_dir_name: str, password: str) -> bool:
        record = self._records.get(self._lock_key(browser_key, profile_dir_name))
        if record is None:
            return True
        try:
            salt = base64.b64decode(record.salt.encode("ascii"))
            expected = base64.b64decode(record.password_hash.encode("ascii"))
        except ValueError:
            LOGGER.warning("Ignoring corrupt profile lock record for %s", profile_dir_name)
            return False
        actual = self._hash_password(password, salt, record.iterations)
        return hmac.compare_digest(actual, expected)

    def remove_lock(self, browser_key: str, profile_dir_name: str) -> None:
        self._records.pop(self._lock_key(browser_key, profile_dir_name), None)
        self._save_records()

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 6:
            raise ValueError("Profile lock passwords must be at least 6 characters long.")

    @staticmethod
    def _hash_password(password: str, salt: bytes, iterations: int) -> bytes:
        return hashlib.pbkdf2_hmac(
            PASSWORD_HASH_NAME,
            password.encode("utf-8"),
            salt,
            iterations,
        )

    @staticmethod
    def _lock_key(browser_key: str, profile_dir_name: str) -> str:
        return f"{browser_key}:{profile_dir_name}"

    def _load_records(self) -> dict[str, ProfileLockRecord]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            LOGGER.warning("Could not load profile lock file: %s", exc)
            return {}

        records: dict[str, ProfileLockRecord] = {}
        if not isinstance(payload, dict):
            return records
        raw_records = payload.get("locks", {})
        if not isinstance(raw_records, dict):
            return records

        for key, value in raw_records.items():
            if not isinstance(key, str) or not isinstance(value, dict):
                continue
            try:
                records[key] = ProfileLockRecord(
                    browser_key=str(value["browser_key"]),
                    profile_dir_name=str(value["profile_dir_name"]),
                    salt=str(value["salt"]),
                    password_hash=str(value["password_hash"]),
                    iterations=int(value.get("iterations", PBKDF2_ITERATIONS)),
                    hash_name=str(value.get("hash_name", PASSWORD_HASH_NAME)),
                )
            except (KeyError, TypeError, ValueError):
                LOGGER.warning("Skipping invalid profile lock record: %s", key)
        return records

    def _save_records(self) -> None:
        payload = {
            "version": LOCK_FILE_VERSION,
            "description": "Local app launcher password gates. Not a Chromium security boundary.",
            "locks": {
                key: {
                    "browser_key": record.browser_key,
                    "profile_dir_name": record.profile_dir_name,
                    "salt": record.salt,
                    "password_hash": record.password_hash,
                    "iterations": record.iterations,
                    "hash_name": record.hash_name,
                }
                for key, record in sorted(self._records.items())
            },
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def launch_profile(browser: BrowserInstall, profile: BrowserProfile) -> None:
    if browser.executable_path is None or not browser.executable_path.exists():
        raise RuntimeError(f"{browser.display_name} executable could not be found.")
    if not profile.path.exists():
        raise RuntimeError(f"The selected profile folder no longer exists: {profile.path}")

    subprocess.Popen(
        [str(browser.executable_path), f"--profile-directory={profile.profile_dir_name}"],
        close_fds=True,
    )
