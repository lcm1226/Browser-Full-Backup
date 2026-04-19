from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from browser_detection import BrowserInstall, detect_installed_browsers, validate_browser_closed
from encryption import create_archive, extract_archive, list_entries, read_text_entry
from manifest import BackupManifest, manifest_from_json


LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RestorePreview:
    manifest: BackupManifest
    archive_entries: list[str]
    files_to_add: list[str]
    files_to_overwrite: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RestoreOptions:
    browser: BrowserInstall
    archive_path: Path
    destination_profile_path: Path
    overwrite_existing: bool
    password: str | None = None
    dry_run: bool = False


@dataclass(slots=True)
class RestoreResult:
    preview: RestorePreview
    rollback_snapshot: Path | None
    restored_files: list[str]
    dry_run: bool


def load_manifest_from_archive(
    archive_path: Path,
    password: str | None = None,
) -> BackupManifest:
    text = read_text_entry(archive_path, "manifest.json", password=password)
    return manifest_from_json(text)


def preview_restore(
    archive_path: Path,
    destination_profile_path: Path,
    password: str | None = None,
) -> RestorePreview:
    manifest = load_manifest_from_archive(archive_path, password=password)
    archive_entries = [
        entry for entry in list_entries(archive_path, password=password) if entry != "manifest.json"
    ]

    files_to_add: list[str] = []
    files_to_overwrite: list[str] = []

    for entry in archive_entries:
        destination = destination_profile_path / Path(entry)
        if destination.exists():
            files_to_overwrite.append(entry)
        else:
            files_to_add.append(entry)

    warnings = _build_restore_warnings(manifest, destination_profile_path)

    return RestorePreview(
        manifest=manifest,
        archive_entries=archive_entries,
        files_to_add=files_to_add,
        files_to_overwrite=files_to_overwrite,
        warnings=warnings,
    )


def restore_backup(options: RestoreOptions) -> RestoreResult:
    problems = validate_browser_closed(options.browser, options.destination_profile_path)
    if problems:
        raise RuntimeError(
            "Restore stopped because the destination browser/profile appears to still be in use:\n- "
            + "\n- ".join(problems)
        )

    preview = preview_restore(
        options.archive_path,
        options.destination_profile_path,
        password=options.password,
    )

    if preview.files_to_overwrite and not options.overwrite_existing:
        raise RuntimeError(
            "Restore preview detected existing files in the destination profile. Enable overwrite"
            " only after reviewing the preview."
        )

    if options.dry_run:
        LOGGER.info(
            "Dry run complete. %s files would be restored into %s.",
            len(preview.archive_entries),
            options.destination_profile_path,
        )
        return RestoreResult(
            preview=preview,
            rollback_snapshot=None,
            restored_files=preview.archive_entries,
            dry_run=True,
        )

    rollback_snapshot = None
    if options.destination_profile_path.exists() and any(options.destination_profile_path.iterdir()):
        rollback_snapshot = create_pre_restore_snapshot(
            destination_profile_path=options.destination_profile_path,
            archive_path=options.archive_path,
        )
        LOGGER.info("Created rollback snapshot at %s", rollback_snapshot)

    options.destination_profile_path.mkdir(parents=True, exist_ok=True)

    # Extracting into a temporary directory keeps restore logic simple and prevents half-written
    # profile state if extraction fails in the middle.
    with tempfile.TemporaryDirectory(prefix="chromium-profile-restore-") as temp_dir:
        temp_path = Path(temp_dir)
        extract_archive(
            archive_path=options.archive_path,
            destination=temp_path,
            password=options.password,
        )
        manifest_path = temp_path / "manifest.json"
        if manifest_path.exists():
            manifest_path.unlink()

        for source_file in sorted(
            (path for path in temp_path.rglob("*") if path.is_file()),
            key=lambda item: str(item).lower(),
        ):
            relative_path = source_file.relative_to(temp_path)
            destination_file = options.destination_profile_path / relative_path
            destination_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, destination_file)

    LOGGER.info(
        "Restore finished successfully. %s files restored into %s.",
        len(preview.archive_entries),
        options.destination_profile_path,
    )
    _register_restored_profile(options.browser, options.destination_profile_path, preview.manifest)
    return RestoreResult(
        preview=preview,
        rollback_snapshot=rollback_snapshot,
        restored_files=preview.archive_entries,
        dry_run=False,
    )


def create_pre_restore_snapshot(destination_profile_path: Path, archive_path: Path) -> Path:
    snapshot_root = archive_path.parent / "rollback_snapshots"
    snapshot_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snapshot_name = f"{destination_profile_path.name}_pre_restore_{timestamp}.zip"
    snapshot_path = snapshot_root / snapshot_name

    files = [
        (path, path.relative_to(destination_profile_path).as_posix())
        for path in sorted(
            (entry for entry in destination_profile_path.rglob("*") if entry.is_file()),
            key=lambda item: str(item).lower(),
        )
    ]
    metadata = {
        "snapshot_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_path": str(destination_profile_path),
        "created_for_restore_archive": str(archive_path),
    }
    create_archive(
        archive_path=snapshot_path,
        files=files,
        extra_entries={"snapshot_manifest.json": json.dumps(metadata, indent=2).encode("utf-8")},
        password=None,
    )
    return snapshot_path


def _build_restore_warnings(manifest: BackupManifest, destination_profile_path: Path) -> list[str]:
    warnings: list[str] = []

    destination_browser = _match_destination_browser(destination_profile_path)
    if destination_browser and destination_browser.key != manifest.browser_key:
        warnings.append(
            f"This backup came from {manifest.browser_name} but the destination path belongs to"
            f" {destination_browser.display_name}. Cross-browser restores can be incompatible."
        )

    if destination_browser and destination_browser.version and manifest.browser_version:
        source_major = manifest.browser_version.split(".")[0]
        destination_major = destination_browser.version.split(".")[0]
        if source_major != destination_major:
            warnings.append(
                "Browser version mismatch detected. Restoring across major Chromium versions can"
                " cause profile incompatibilities or data loss."
            )

    if destination_profile_path.exists() and any(destination_profile_path.iterdir()):
        warnings.append(
            "The destination profile already contains files. Review the overwrite list carefully"
            " before restoring."
        )

    return warnings


def _match_destination_browser(destination_profile_path: Path) -> BrowserInstall | None:
    for browser in detect_installed_browsers():
        try:
            destination_profile_path.relative_to(browser.user_data_dir)
            return browser
        except ValueError:
            continue
    return None


def _register_restored_profile(
    browser: BrowserInstall,
    destination_profile_path: Path,
    manifest: BackupManifest,
) -> None:
    try:
        profile_dir_name = destination_profile_path.relative_to(browser.user_data_dir).parts[0]
    except ValueError:
        return

    if profile_dir_name in {"Default", "System Profile", "Guest Profile"}:
        return

    local_state_path = browser.user_data_dir / "Local State"
    payload: dict[str, object]
    if local_state_path.exists():
        try:
            payload = json.loads(local_state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            LOGGER.warning("Could not update Local State at %s: %s", local_state_path, exc)
            return
    else:
        payload = {}

    profile_root = payload.setdefault("profile", {})
    if not isinstance(profile_root, dict):
        profile_root = {}
        payload["profile"] = profile_root

    info_cache = profile_root.setdefault("info_cache", {})
    if not isinstance(info_cache, dict):
        info_cache = {}
        profile_root["info_cache"] = info_cache

    existing_entry = info_cache.get(profile_dir_name)
    if not isinstance(existing_entry, dict):
        existing_entry = {}
        info_cache[profile_dir_name] = existing_entry

    existing_entry.setdefault("avatar_icon", "chrome://theme/IDR_PROFILE_AVATAR_26")
    existing_entry.setdefault("background_apps", False)
    existing_entry.setdefault("is_ephemeral", False)
    existing_entry.setdefault("is_managed", 0)
    existing_entry.setdefault("is_using_default_avatar", True)
    existing_entry["name"] = manifest.profile_name
    existing_entry["shortcut_name"] = manifest.profile_name
    existing_entry["active_time"] = time.time()

    profiles_order = profile_root.setdefault("profiles_order", [])
    if not isinstance(profiles_order, list):
        profiles_order = []
        profile_root["profiles_order"] = profiles_order
    if profile_dir_name not in profiles_order:
        profiles_order.append(profile_dir_name)

    metrics = profile_root.setdefault("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
        profile_root["metrics"] = metrics
    next_bucket_index = metrics.get("next_bucket_index", 1)
    if not isinstance(next_bucket_index, int):
        next_bucket_index = 1
    existing_entry.setdefault("metrics_bucket_index", next_bucket_index)
    metrics["next_bucket_index"] = max(next_bucket_index + 1, 1)

    try:
        local_state_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        LOGGER.info(
            "Registered restored profile %s in Local State for %s.",
            profile_dir_name,
            browser.display_name,
        )
    except OSError as exc:
        LOGGER.warning("Could not write updated Local State at %s: %s", local_state_path, exc)
