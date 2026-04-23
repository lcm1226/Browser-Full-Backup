# Chromium Profile Backup and Restore Tool

Local-only Windows desktop utility for backing up and restoring Chromium-based browser profiles for personal migration between your own devices.

This project is designed for:

- Google Chrome
- Brave
- Microsoft Edge

It is designed for personal backup and restore only. It does not send data over email, HTTP, cloud storage, webhooks, or any other network path.

## Current Validation Scope

For the current verification workflow on this machine, only these Chrome profiles are in scope:

- `Profile 2` with the friendly name `test`
- `Profile 98`, which was created as a restore target for `test`

Operational guardrail for the current validation phase:

- Do not modify other Chrome profiles
- Do not modify Brave or Edge profiles
- Do not back up, restore, or copy data from non-test profiles
- Only inspect non-test profile metadata when strictly necessary to keep the app safe and understandable

## Safety Model

- Local-only file operations. No upload, email, remote sync, or API calls.
- Windows-first behavior for standard Chromium user data directories.
- Backup and restore both warn the user to fully close the browser first.
- The app checks for running browser processes and common locked profile files before changing anything.
- Restore includes a preview step so the user can see what would be overwritten.
- If restoring over an existing profile, the app creates a rollback snapshot archive before copying files.
- Optional password-based ZIP encryption is supported for the backup archive.

## Supported Browsers and Standard Paths

- Chrome: `%LOCALAPPDATA%\Google\Chrome\User Data`
- Brave: `%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data`
- Edge: `%LOCALAPPDATA%\Microsoft\Edge\User Data`

The app scans profile folders such as:

- `Default`
- `Profile 1`
- `Profile 2`
- `Guest Profile`
- `System Profile`

## Features

- Detect installed supported browsers
- Enumerate available local browser profiles
- Back up one selected profile at a time
- Choose backup scope:
  - Full profile backup
  - Settings-only backup using a conservative allowlist
  - Optional exclusion of common cookies, sessions, and login databases
- Choose backup destination folder manually
- Create compressed ZIP archives
- Optional password-based AES ZIP encryption
- Create a per-backup folder containing the ZIP archive and `manifest.json`
- Embed `manifest.json` inside the archive too
- Dry-run backup and dry-run restore
- Restore preview before overwrite
- Recent backup archive picker on the Restore tab
- Open the backup destination, restore archive folder, and most recent backup folder directly from the UI
- Remember recent paths and major UI selections between launches
- Restore into:
  - an existing profile folder
  - a new profile folder under the selected browser's user data directory
- Automatic rollback snapshot when restoring over a non-empty destination profile
- Local Profile Lock tab for password-gated launches through this app
- User-readable logging to the window and to `chromium_profile_backup.log`

## Project Structure

- `browser_detection.py`
- `profile_discovery.py`
- `profile_lock.py`
- `backup_engine.py`
- `restore_engine.py`
- `manifest.py`
- `encryption.py`
- `ui.py`
- `main.py`
- `test_profile_lock.py`

## Requirements

- Windows 10 or Windows 11
- Python 3.11 or newer recommended

## Quick Start on Windows

가장 쉬운 실행 방법:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1
```

또는 프로젝트 폴더에서 [Launch Chromium Profile Backup Tool.cmd](</C:/Users/user/Desktop/Chromium 프로파일 백업&복원 도구/Launch Chromium Profile Backup Tool.cmd:1>)를 더블클릭해도 됩니다.

이 스크립트는 다음을 자동으로 처리합니다.

- Windows Python 찾기
- `.venv` 가상환경 생성
- `requirements.txt` 의존성 설치
- `main.py` 실행

옵션:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1 -SkipInstall
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1 -ForceReinstall
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1 -NoLaunch
powershell -ExecutionPolicy Bypass -File .\run_windows.ps1 -PythonPath "C:\full\path\to\python.exe"
```

Install dependencies:

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run the app:

```powershell
py -3 main.py
```

exe 파일로 패키징하려면:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1 -PythonPath "C:\full\path\to\python.exe"
```

성공하면 `dist\ChromiumProfileBackupTool.exe`가 생성됩니다.

## How to Use

### Backup

1. Close the browser fully before starting.
2. Click `Detect Installed Browsers`.
3. Choose a browser and one profile.
4. Choose:
   - full profile backup, or
   - settings-only backup
5. Optionally enable exclusion of common cookies, sessions, and login databases.
6. Choose a destination folder.
7. Optionally enter a password to encrypt the archive.
8. Use `Preview Backup` to dry-run first.
9. Use `Create Backup` when the preview looks right.

### Restore

1. Close the destination browser fully before starting.
2. Choose the backup ZIP archive.
3. Enter the password if the archive is encrypted.
4. Choose the destination browser.
5. Choose either:
   - an existing profile folder, or
   - a new profile folder name
6. Use `Preview Restore` first.
7. Review overwrite warnings carefully.
8. Run restore only after confirming the preview.

### Profile Lock

Use this when you want a local password prompt before launching a selected browser profile
from this tool.

1. Open the `Profile Lock` tab.
2. Choose a browser and profile, for example Chrome `Profile 2 | test`.
3. Enter and confirm a profile-lock password.
4. Click `Set / Change Password`.
5. Later, enter the password and click `Unlock and Launch Profile`.

Important: this is a convenience gate inside this app only. It does not lock Chrome's
native profile picker, direct browser shortcuts, Windows user accounts, or the profile
folder on disk. Use separate Windows accounts or full-disk/profile-folder encryption if
you need a real access-control boundary.

Profile Lock stores local salted password hashes in `profile_locks.json`. When running
from source, that file lives in the project folder. When running the packaged exe, it is
stored next to `ChromiumProfileBackupTool.exe`.

## Manifest Format

Each backup writes:

- `manifest.json` next to the ZIP archive inside that backup's timestamped output folder
- `manifest.json` inside the ZIP archive

The manifest includes:

- browser name
- browser key
- profile name
- profile folder name
- source path
- creation timestamp
- backup scope
- included categories
- excluded categories
- browser version if detected
- archive name
- whether encryption was used
- notes and warnings

## Example UI Layout

The app uses a single desktop window with:

- a top warning banner explaining that the browser must be closed and that the tool is local-only
- a `Backup` tab with browser selection, profile selection, scope controls, destination folder picker, password box, and preview/create buttons
- a `Restore` tab with archive picker, password box, destination browser selector, restore target selector, preview button, and restore button
- a `Profile Lock` tab with browser/profile selection, local password setup, lock removal, and password-gated launch
- a lower activity log pane showing readable progress and errors

## Known Limitations

- Chromium profile internals change over time. A backup from one major version may not restore cleanly into another.
- Cross-browser restore is possible at the file level but may be incompatible because Chrome, Brave, and Edge can diverge in profile behavior.
- `Settings-only` mode uses a conservative allowlist. Some browser settings or extension-specific data may live outside the included files.
- `Exclude cookies / sessions / login tokens` mode excludes common known stores, but exact file names and storage locations vary by Chromium version and by extension.
- Some extensions keep data in storage locations that are not easy to classify safely without making risky assumptions.
- The tool does not decrypt browser-protected secrets and does not attempt to bypass browser security.
- Profile Lock is not a Chromium-native password feature. Chrome's own profile picker can still open profiles unless you separately restrict access at the Windows account or filesystem level.
- The tool expects standard Windows profile locations. Non-standard portable installs are out of scope unless their profile folders are copied manually outside the app.

## Notes for Non-Developers

If you want a simple double-click workflow, you can package this script with PyInstaller later:

```powershell
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed main.py
```

That is optional. The application works directly with Python as-is.
