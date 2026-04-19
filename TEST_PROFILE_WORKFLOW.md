# Test Profile Workflow

This checklist is intentionally limited to the current safe validation scope on this machine.

Allowed profiles:

- Chrome `Profile 2` named `test`
- Chrome `Profile 98` as the restore target cloned from `test`

Do not use:

- Chrome `Default`
- Chrome `Profile 1`
- Chrome `System Profile`
- Any Brave profile
- Any Edge profile

## Safe Validation Steps

1. Close Chrome completely before backup or restore.
2. Launch the app from the project folder:

```powershell
& "C:\Users\user\Desktop\Chromium 프로파일 백업&복원 도구\dist\ChromiumProfileBackupTool.exe"
```

3. In the `Backup` tab:
   - Select `Google Chrome`
   - Select `Profile 2 | test`
   - Choose a destination folder
   - Keep sensitive exclusion enabled unless you intentionally want session state
   - Run `Preview Backup` first

4. In the `Restore` tab:
   - Use a backup created from `Profile 2 | test`
   - Select `Google Chrome`
   - Restore only into `Profile 98` or another explicitly-created test-only destination
   - Run `Preview Restore` first

5. To inspect the restored profile directly in Chrome:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --profile-directory="Profile 98"
```

## Recommended Visual Checks

- A bookmark added in `test`
- A homepage or startup-page setting changed in `test`
- A harmless extension present in `test`

These are easier to validate than cookies or login state because the current test backup excluded sensitive session data.

## Verification Artifacts Created So Far

- Backup archive:
  [chrome_Profile_2_20260419-000411.zip](</C:/Users/user/Desktop/Chromium 프로파일 백업&복원 도구/verification_output/chrome_Profile_2_20260419-000411/chrome_Profile_2_20260419-000411.zip>)
- Manifest:
  [manifest.json](</C:/Users/user/Desktop/Chromium 프로파일 백업&복원 도구/verification_output/chrome_Profile_2_20260419-000411/manifest.json>)

## Cleanup Options

Keep:

- `Profile 98` if you want a persistent restore target for future tests
- `verification_output` if you want to keep the test archive

Remove later if no longer needed:

- `Profile 98`
- `verification_output`
