from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


RECOVERY_KEY_FILE_NAME = "recovery_key.json"
EMERGENCY_CODES_FILE_NAME = "emergency_codes.txt"
_RECOVERY_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


@dataclass(slots=True)
class RecoveryEnrollment:
    recovery_key: str
    recovery_key_sha256: str
    emergency_codes: list[str]
    emergency_code_sha256: list[str]
    artifact_names: list[str]


def create_recovery_enrollment(code_count: int = 8) -> RecoveryEnrollment:
    recovery_key = secrets.token_urlsafe(24)
    emergency_codes = [_generate_recovery_code() for _ in range(code_count)]
    return RecoveryEnrollment(
        recovery_key=recovery_key,
        recovery_key_sha256=_sha256(recovery_key),
        emergency_codes=emergency_codes,
        emergency_code_sha256=[_sha256(code) for code in emergency_codes],
        artifact_names=[RECOVERY_KEY_FILE_NAME, EMERGENCY_CODES_FILE_NAME],
    )


def write_recovery_artifacts(
    *,
    output_dir: Path,
    archive_name: str,
    browser_name: str,
    profile_name: str,
    password_hint: str | None,
    enrollment: RecoveryEnrollment,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    recovery_key_path = output_dir / RECOVERY_KEY_FILE_NAME
    emergency_codes_path = output_dir / EMERGENCY_CODES_FILE_NAME

    recovery_key_payload = {
        "schema_version": 1,
        "archive_name": archive_name,
        "browser_name": browser_name,
        "profile_name": profile_name,
        "created_timestamp": datetime.now(timezone.utc).isoformat(),
        "recovery_key": enrollment.recovery_key,
        "instructions": (
            "Store this file separately from the backup archive. It is intended for future local"
            " password reset or recovery features."
        ),
    }
    if password_hint:
        recovery_key_payload["password_hint"] = password_hint

    recovery_key_path.write_text(
        json.dumps(recovery_key_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    lines = [
        "Chromium Profile Backup Emergency Recovery Codes",
        "",
        f"Archive: {archive_name}",
        f"Browser: {browser_name}",
        f"Profile: {profile_name}",
        "",
        "Store these codes offline and separately from the encrypted backup archive.",
        "Each code is intended for future local recovery or password reset features.",
        "",
        "Recovery codes:",
    ]
    lines.extend(f"- {code}" for code in enrollment.emergency_codes)
    if password_hint:
        lines.extend(["", f"Password hint: {password_hint}"])

    emergency_codes_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return recovery_key_path, emergency_codes_path


def _generate_recovery_code() -> str:
    raw = "".join(secrets.choice(_RECOVERY_CODE_ALPHABET) for _ in range(12))
    return f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
