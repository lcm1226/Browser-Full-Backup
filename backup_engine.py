from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from fnmatch import fnmatch
from pathlib import Path

from browser_detection import BrowserInstall, validate_browser_closed
from encryption import create_archive
from manifest import BackupManifest, build_manifest, manifest_to_json, write_manifest
from profile_discovery import BrowserProfile
from recovery import RecoveryEnrollment, create_recovery_enrollment, write_recovery_artifacts


LOGGER = logging.getLogger(__name__)


SCOPE_FULL = "full_profile"
SCOPE_SETTINGS_ONLY = "settings_only"


SENSITIVE_PATTERNS = {
    "cookies": [
        "Cookies",
        "Cookies-journal",
        "Network/Cookies",
        "Network/Cookies-journal",
    ],
    "sessions": [
        "Current Session",
        "Current Tabs",
        "Last Session",
        "Last Tabs",
        "Sessions/*",
        "Session Storage/*",
    ],
    "login_data": [
        "Login Data",
        "Login Data-journal",
        "Login Data For Account",
        "Login Data For Account-journal",
    ],
}


SETTINGS_ONLY_ALLOWLIST = [
    "Preferences",
    "Secure Preferences",
    "Bookmarks",
    "Bookmarks.bak",
    "Favicons",
    "Favicons-journal",
    "Top Sites",
    "Top Sites-journal",
    "Shortcuts",
    "Shortcuts-journal",
    "Extensions/*",
    "Extension Rules/*",
    "Extension Scripts/*",
    "Extension State/*",
    "Local Extension Settings/*",
    "Managed Extension Settings/*",
    "Sync Extension Settings/*",
]


@dataclass(slots=True)
class BackupPlanItem:
    source_path: Path
    relative_path: str


@dataclass(slots=True)
class BackupPlan:
    profile_path: Path
    items: list[BackupPlanItem]
    included_categories: list[str]
    excluded_categories: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BackupOptions:
    browser: BrowserInstall
    profile: BrowserProfile
    destination_dir: Path
    backup_scope: str
    exclude_sensitive_data: bool
    password: str | None = None
    enroll_recovery_material: bool = False
    password_hint: str | None = None
    dry_run: bool = False


@dataclass(slots=True)
class BackupResult:
    archive_path: Path | None
    manifest_path: Path | None
    manifest: BackupManifest
    copied_files: list[str]
    warnings: list[str]
    recovery_key_path: Path | None
    emergency_codes_path: Path | None
    dry_run: bool


def create_backup(options: BackupOptions) -> BackupResult:
    if options.enroll_recovery_material and not options.password:
        raise RuntimeError(
            "Recovery enrollment requires an archive password. Set a backup password first."
        )

    # Do not copy live profile state. Even read-only backups can be inconsistent if Chromium is
    # still writing SQLite or session files during the archive step.
    problems = validate_browser_closed(options.browser, options.profile.path)
    if problems:
        raise RuntimeError(
            "Backup stopped because the browser or profile appears to still be in use:\n- "
            + "\n- ".join(problems)
        )

    plan = build_backup_plan(
        profile_path=options.profile.path,
        backup_scope=options.backup_scope,
        exclude_sensitive_data=options.exclude_sensitive_data,
    )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_name = (
        f"{options.browser.key}_{_sanitize_name(options.profile.profile_dir_name)}_{timestamp}.zip"
    )
    recovery_enrollment: RecoveryEnrollment | None = None
    if options.enroll_recovery_material:
        recovery_enrollment = create_recovery_enrollment()
        plan.warnings.append(
            "Recovery enrollment is enabled. A recovery key file and emergency recovery codes"
            " will be written next to the backup archive. Store them separately from the archive."
        )
    manifest = build_manifest(
        browser_name=options.browser.display_name,
        browser_key=options.browser.key,
        profile_name=options.profile.profile_name,
        profile_dir_name=options.profile.profile_dir_name,
        source_path=options.profile.path,
        backup_scope=options.backup_scope,
        included_categories=plan.included_categories,
        excluded_categories=plan.excluded_categories,
        browser_version=options.browser.version,
        archive_name=archive_name,
        encrypted=bool(options.password),
        notes=plan.warnings,
        recovery_enrolled=bool(recovery_enrollment),
        recovery_artifacts=recovery_enrollment.artifact_names if recovery_enrollment else [],
        password_hint=options.password_hint.strip() if options.password_hint else None,
        recovery_key_sha256=(
            recovery_enrollment.recovery_key_sha256 if recovery_enrollment else None
        ),
        emergency_code_sha256=(
            recovery_enrollment.emergency_code_sha256 if recovery_enrollment else []
        ),
    )

    if options.dry_run:
        LOGGER.info("Dry run complete. %s files would be added to the archive.", len(plan.items))
        return BackupResult(
            archive_path=None,
            manifest_path=None,
            manifest=manifest,
            copied_files=[item.relative_path for item in plan.items],
            warnings=plan.warnings,
            recovery_key_path=None,
            emergency_codes_path=None,
            dry_run=True,
        )

    options.destination_dir.mkdir(parents=True, exist_ok=True)
    archive_container = options.destination_dir / Path(archive_name).stem
    archive_container.mkdir(parents=True, exist_ok=True)
    archive_path = archive_container / archive_name
    manifest_path = archive_container / "manifest.json"

    LOGGER.info("Creating archive %s", archive_path)
    create_archive(
        archive_path=archive_path,
        files=[(item.source_path, item.relative_path) for item in plan.items],
        extra_entries={"manifest.json": manifest_to_json(manifest).encode("utf-8")},
        password=options.password,
    )
    write_manifest(manifest, manifest_path)
    recovery_key_path = None
    emergency_codes_path = None
    if recovery_enrollment:
        recovery_key_path, emergency_codes_path = write_recovery_artifacts(
            output_dir=archive_container,
            archive_name=archive_name,
            browser_name=options.browser.display_name,
            profile_name=options.profile.profile_name,
            password_hint=options.password_hint.strip() if options.password_hint else None,
            enrollment=recovery_enrollment,
        )
    LOGGER.info("Backup finished successfully. Manifest written to %s", manifest_path)

    return BackupResult(
        archive_path=archive_path,
        manifest_path=manifest_path,
        manifest=manifest,
        copied_files=[item.relative_path for item in plan.items],
        warnings=plan.warnings,
        recovery_key_path=recovery_key_path,
        emergency_codes_path=emergency_codes_path,
        dry_run=False,
    )


def build_backup_plan(
    profile_path: Path,
    backup_scope: str,
    exclude_sensitive_data: bool,
) -> BackupPlan:
    if not profile_path.exists():
        raise FileNotFoundError(f"Profile path does not exist: {profile_path}")

    items: list[BackupPlanItem] = []
    excluded_categories = ["locked_live_browser_state"]
    warnings: list[str] = []

    for file_path in sorted(
        (path for path in profile_path.rglob("*") if path.is_file()),
        key=lambda item: str(item).lower(),
    ):
        relative_path = file_path.relative_to(profile_path).as_posix()

        # Settings-only mode is allowlist-based on purpose. A denylist would be easier, but it
        # would also be much easier to accidentally include state the user explicitly wanted left out.
        if backup_scope == SCOPE_SETTINGS_ONLY and not _matches_any(
            relative_path, SETTINGS_ONLY_ALLOWLIST
        ):
            continue

        if exclude_sensitive_data and _is_sensitive(relative_path):
            continue

        items.append(BackupPlanItem(source_path=file_path, relative_path=relative_path))

    if backup_scope == SCOPE_SETTINGS_ONLY:
        included_categories = ["preferences", "bookmarks", "favicons", "extensions"]
        excluded_categories.extend(
            ["history", "cookies", "sessions", "login_data", "site_storage", "cache"]
        )
        warnings.append(
            "Settings-only mode uses a conservative allowlist. Some browser or extension-specific"
            " settings may live in files that are not included."
        )
    else:
        included_categories = ["profile_files"]

    if exclude_sensitive_data:
        excluded_categories.extend(["cookies", "sessions", "login_data"])
        warnings.append(
            "Sensitive exclusion mode removes common cookie, session, and login database files."
            " Chromium storage layouts vary by browser version, so some site-specific data may still"
            " remain in other files."
        )

    if not items:
        raise RuntimeError(
            "No files matched the selected backup scope. Try full profile mode or disable exclusions."
        )

    return BackupPlan(
        profile_path=profile_path,
        items=items,
        included_categories=sorted(set(included_categories)),
        excluded_categories=sorted(set(excluded_categories)),
        warnings=warnings,
    )


def _is_sensitive(relative_path: str) -> bool:
    for patterns in SENSITIVE_PATTERNS.values():
        if _matches_any(relative_path, patterns):
            return True
    return False


def _matches_any(relative_path: str, patterns: list[str]) -> bool:
    return any(fnmatch(relative_path, pattern) for pattern in patterns)


def _sanitize_name(value: str) -> str:
    safe = "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in value
    )
    return safe.strip("_") or "profile"
