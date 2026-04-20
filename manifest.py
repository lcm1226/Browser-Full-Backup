from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass(slots=True)
class BackupManifest:
    browser_name: str
    browser_key: str
    profile_name: str
    profile_dir_name: str
    source_path: str
    creation_timestamp: str
    backup_scope: str
    included_categories: list[str]
    excluded_categories: list[str]
    browser_version: str | None
    archive_name: str
    encrypted: bool
    notes: list[str]
    recovery_enrolled: bool = False
    recovery_artifacts: list[str] = field(default_factory=list)
    password_hint: str | None = None
    recovery_key_sha256: str | None = None
    emergency_code_sha256: list[str] = field(default_factory=list)


def build_manifest(
    *,
    browser_name: str,
    browser_key: str,
    profile_name: str,
    profile_dir_name: str,
    source_path: Path,
    backup_scope: str,
    included_categories: list[str],
    excluded_categories: list[str],
    browser_version: str | None,
    archive_name: str,
    encrypted: bool,
    notes: list[str] | None = None,
    recovery_enrolled: bool = False,
    recovery_artifacts: list[str] | None = None,
    password_hint: str | None = None,
    recovery_key_sha256: str | None = None,
    emergency_code_sha256: list[str] | None = None,
) -> BackupManifest:
    return BackupManifest(
        browser_name=browser_name,
        browser_key=browser_key,
        profile_name=profile_name,
        profile_dir_name=profile_dir_name,
        source_path=str(source_path),
        creation_timestamp=datetime.now(timezone.utc).isoformat(),
        backup_scope=backup_scope,
        included_categories=sorted(included_categories),
        excluded_categories=sorted(excluded_categories),
        browser_version=browser_version,
        archive_name=archive_name,
        encrypted=encrypted,
        notes=notes or [],
        recovery_enrolled=recovery_enrolled,
        recovery_artifacts=recovery_artifacts or [],
        password_hint=password_hint,
        recovery_key_sha256=recovery_key_sha256,
        emergency_code_sha256=emergency_code_sha256 or [],
    )


def manifest_to_json(manifest: BackupManifest) -> str:
    return json.dumps(asdict(manifest), indent=2, ensure_ascii=False)


def write_manifest(manifest: BackupManifest, destination: Path) -> None:
    destination.write_text(manifest_to_json(manifest), encoding="utf-8")


def load_manifest(path: Path) -> BackupManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return BackupManifest(**payload)


def manifest_from_json(text: str) -> BackupManifest:
    payload = json.loads(text)
    return BackupManifest(**payload)
