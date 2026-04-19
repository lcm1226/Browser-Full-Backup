from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pyzipper


def create_archive(
    archive_path: Path,
    files: Iterable[tuple[Path, str]],
    extra_entries: dict[str, bytes] | None = None,
    password: str | None = None,
) -> None:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with pyzipper.AESZipFile(
        archive_path,
        mode="w",
        compression=pyzipper.ZIP_DEFLATED,
        allowZip64=True,
    ) as zip_file:
        if password:
            zip_file.setpassword(password.encode("utf-8"))
            zip_file.setencryption(pyzipper.WZ_AES, nbits=256)

        for source_path, archive_name in files:
            zip_file.write(source_path, arcname=archive_name)

        for archive_name, content in sorted((extra_entries or {}).items()):
            zip_file.writestr(archive_name, content)


def extract_archive(
    archive_path: Path,
    destination: Path,
    password: str | None = None,
    members: list[str] | None = None,
) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with pyzipper.AESZipFile(archive_path) as zip_file:
        if password:
            zip_file.setpassword(password.encode("utf-8"))
        zip_file.extractall(path=destination, members=members)


def read_text_entry(
    archive_path: Path,
    entry_name: str,
    password: str | None = None,
) -> str:
    with pyzipper.AESZipFile(archive_path) as zip_file:
        if password:
            zip_file.setpassword(password.encode("utf-8"))
        return zip_file.read(entry_name).decode("utf-8")


def list_entries(archive_path: Path, password: str | None = None) -> list[str]:
    with pyzipper.AESZipFile(archive_path) as zip_file:
        if password:
            zip_file.setpassword(password.encode("utf-8"))
        return sorted(info.filename for info in zip_file.infolist())
