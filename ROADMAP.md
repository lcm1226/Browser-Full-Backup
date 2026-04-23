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

Still pending:

- UI-level end-to-end manual acceptance pass by the user
- Cleanup and refinement of profile naming / mojibake display for some existing profiles
- Broader cross-browser validation for Brave and Edge
- Automated test coverage for backup/restore flows

## Near-Term Execution Checklist

1. Perform one UI-level backup preview using the latest exe.
2. Perform one UI-level restore preview using the latest exe.
3. Confirm the restored Chrome test profile opens as expected in Chrome.
4. Decide whether to keep or remove the temporary `Profile 98` verification profile.
5. Decide whether to keep or remove the `verification_output` backup artifacts.

## Next Feature Roadmap

The next requested feature set is a profile-level failsafe for backup passwords:

- Per-browser-profile backup password
- Password recovery or reset path if the backup password is forgotten
- Recovery using one approved login identifier already present in the user's own profile
- Recovery using the user's Google account or Gmail identity as a fallback concept

Important design note:

- This must stay local-only for the core app.
- Any future recovery flow must not silently transmit profile data or secrets.
- Browser-stored credentials and Google-account identity checks are security-sensitive.
- Recovery should never depend on scraping or bypassing protected browser secrets.
- The safest direction is to recover access to the backup archive through user-owned recovery material that was deliberately set up at backup time, not by trying to extract or decrypt browser secrets later.

## Recommended Product Direction for Password Failsafe

Prefer this model:

1. The user sets a backup password.
2. The app optionally creates one or more recovery methods during backup setup.
3. Recovery methods are explicit, local, and user-controlled.
4. Reset works only if the user proves possession of a recovery factor that was enrolled beforehand.

Recommended recovery factors:

- Recovery key file saved locally by the user
- Printed or saved emergency recovery codes
- A second local password hint or admin passphrase set by the user
- Optional external identity flow only if it is explicitly designed, consented to, and separated from local-only mode

## Why Browser Login Data Is a Bad Primary Recovery Mechanism

Using one of the login entries inside a Chromium profile as a recovery path sounds convenient, but it creates several problems:

- Chromium protects many saved secrets with OS-level encryption.
- The current app intentionally does not try to decrypt browser-protected secrets.
- Saved login structures vary by version and browser.
- Extension-managed account data is even less predictable.
- Basing recovery on live browser secrets increases fragility and security risk.

Recommendation:

- Do not use browser-saved passwords as the primary or default recovery mechanism.
- At most, treat existing account metadata as an optional user hint layer, not as a secret-verification mechanism.

## Why Gmail / Google Account Recovery Needs Care

Using a Google account for password reset is not compatible with a strict local-only promise unless the app deliberately adds a network-connected account-recovery mode.

That means:

- It cannot be part of the current local-only baseline.
- It would require a separate mode, separate consent, separate threat model, and very clear user communication.

Recommendation:

- Keep the current product local-only.
- If cloud identity recovery is ever added, gate it behind an optional advanced mode and document the privacy tradeoff clearly.

## Proposed Implementation Phases for the Failsafe Feature

### Phase 1: Local Recovery Enrollment

Goal:

- Add safe, offline recovery enrollment when the user creates a protected backup.

Todo:

- Add optional "Create recovery key" checkbox in the UI
- Generate a one-time recovery key file during backup creation
- Show recovery codes once and require the user to save them
- Add a password hint field that is stored in manifest metadata
- Document the recovery setup clearly in the README

### Phase 2: Local Password Reset for Backup Archives

Goal:

- Let a user regain access to a backup archive if they forgot the password, using previously enrolled recovery material.

Todo:

- Add a "Forgot backup password?" flow to the restore screen
- Support recovery key verification
- Support emergency code verification
- Re-wrap the archive with a new password after successful recovery
- Log recovery events locally in a readable audit record

### Phase 3: Safer Profile-Level Ownership Signals

Goal:

- Explore whether profile metadata can help the user identify the right archive or recovery method without relying on secret extraction.

Todo:

- Surface non-secret account labels already visible in profile metadata when available
- Add warning labels that this is identification help, not authentication
- Avoid reading or using stored credentials as proof

### Phase 4: Optional Advanced Account Recovery Mode

Goal:

- Decide whether an opt-in connected recovery mode is worth building.

Todo:

- Define a separate privacy model
- Define explicit consent UX
- Decide whether Google identity is even necessary
- Document exactly what network traffic would happen
- Keep the default mode fully local-only

## Detailed Todo List for the Requested Failsafe Feature

UI work:

- Add recovery enrollment options to backup setup
- Add recovery status display in backup preview
- Add forgotten-password recovery entry point on restore
- Add recovery reset confirmation flow

Manifest and metadata work:

- Add recovery enrollment flags
- Add password hint field
- Add archive recovery metadata versioning
- Add local audit trail metadata for resets

Crypto and archive work:

- Define how archive password rotation works
- Ensure password reset never alters backed-up content unexpectedly
- Support archive re-encryption with a new password
- Validate rollback behavior for reset flows

Safety and policy work:

- Keep default operation local-only
- Do not use browser-protected secrets as recovery proofs
- Do not silently contact Google or any other service
- Separate identity hints from authentication factors

Testing work:

- Recovery enrollment success test
- Wrong recovery key test
- Successful password reset test
- Archive re-open test after reset
- Backward compatibility test for older manifests

## Recommendation

The best next implementation step is:

1. Finish Windows runtime validation.
2. Add local recovery enrollment with a recovery key file and emergency codes.
3. Delay any Gmail or Google-account recovery concept until the product explicitly supports an opt-in connected mode.
