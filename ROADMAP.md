# Chromium Profile Backup Tool Roadmap

## Current Status

## Active Guardrail For This Machine

During the current validation phase, only these profiles are allowed to be touched:

- Chrome `Profile 2` named `test`
- Chrome `Profile 98` created as the restore target for `test`

Everything else is out of scope for modification.

- No writes to other Chrome profiles
- No writes to Brave profiles
- No writes to Edge profiles
- No backup or restore actions against non-test profiles
- Read-only inspection of non-test profile metadata must stay minimal and justified

Implemented now:

- Windows-first Tkinter desktop UI
- Chrome, Brave, and Edge profile detection
- Profile discovery from standard Windows user data paths
- Backup scope selection
- Sensitive-data exclusion mode for common cookies, sessions, and login databases
- ZIP archive creation with optional password-based AES encryption
- Embedded and side-by-side `manifest.json`
- Dry-run backup
- Restore preview before overwrite
- Rollback snapshot before restoring into a non-empty profile
- Windows launcher script and exe build helper script
- Verified Windows Python runtime setup
- Verified encrypted backup and restore against a real Chrome test profile
- Verified exe build and launch
- Restored profiles are now registered back into Chrome Local State
- Double-click CMD launcher for local use
- Local Profile Lock tab for password-gated launches through this app

Still pending:

- UI-level end-to-end manual acceptance pass by the user
- Cleanup and refinement of profile naming / mojibake display for some existing profiles
- Broader cross-browser validation for Brave and Edge
- Automated test coverage for backup/restore flows
- Clear user acceptance pass for Profile Lock using only the Chrome `test` profile

## Near-Term Execution Checklist

1. Perform one UI-level backup preview using the latest exe.
2. Perform one UI-level restore preview using the latest exe.
3. Confirm the restored Chrome test profile opens as expected in Chrome.
4. Decide whether to keep or remove the temporary `Profile 98` verification profile.
5. Decide whether to keep or remove the `verification_output` backup artifacts.

## Profile Lock Roadmap

The clarified password feature is not backup-password recovery. It is a local gate
before using a selected browser profile.

Implemented direction:

- Add a `Profile Lock` tab to the desktop app.
- Store a salted password hash locally in `profile_locks.json`.
- Require the password before this app launches the selected profile.
- Keep the feature local-only and avoid browser-secret extraction.

Important security boundary:

- Chrome does not provide a supported way for this app to password-protect the native
  profile picker shown at browser startup.
- The app must not patch Chrome, bypass security boundaries, or install stealth hooks.
- Therefore, Profile Lock is an app-controlled guarded launcher, not a true Chrome
  profile access-control system.

## Next Recommended Work

1. Run a user acceptance pass against Chrome `Profile 2 | test`.
2. Add a small automated test for `ProfileLockStore` password set/verify/remove.
3. Add a clearer first-run explanation if Profile Lock becomes a primary workflow.
4. Consider optional Windows shortcut generation that launches this app directly to the
   locked profile flow.
5. For real protection, document Windows-account separation and disk encryption instead
   of pretending Chrome profile folders can be safely locked from a helper app.
