# Progress

## 2026-04-19

- Added Windows system theme detection and Tkinter dark/light palette handling in `ui.py`.
- Improved Windows title bar dark-mode application by retrying `DwmSetWindowAttribute` after window realization and by falling back across the known dark-mode attribute IDs.
- Added a Windows 10 compatibility path that sets the process preferred app mode and allows dark mode on the top-level Tk window before applying DWM title-bar attributes.
- Rebuilt the packaged executable after the UI theme changes.
- Continued validation with the guarded Chrome test profiles only: `Profile 2 | test` and `Profile 98 | test-restored`.
- Verified via captured screenshots that the app body follows the system dark theme, while the standard native title bar still remains light on this Windows 10 environment.
- Replaced the native window chrome with a custom dark title bar on Windows, including drag, minimize, maximize/restore, close, and resize grip behaviors.
- Rebuilt and re-verified the packaged executable with screenshot-based UI inspection after the custom title bar change.
- Added a reusable personal Codex skill for screenshot-based desktop UI self-verification, including a Windows capture helper script under the user skill directory.
- Added basic UI state persistence for the app so recent paths and selection state can be restored on the next launch.
- Added a project-folder shortcut to the personal Codex skills directory for quicker cross-project access.
- Added quick `Open` actions for the backup destination, selected restore archive folder, and the most recently created backup folder.
- Added a recent backup archive picker on the Restore tab so recently used or newly created ZIP files can be reused without browsing again.
- Improved recent backup entries so they show the file name, modified time, and containing folder instead of only the raw ZIP path.
- Started failsafe Phase 1 by adding optional offline recovery enrollment for encrypted backups, including a recovery key file, emergency recovery codes, and password hint metadata.
