@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0dist\ChromiumProfileBackupTool.exe" (
    start "" "%~dp0dist\ChromiumProfileBackupTool.exe"
    exit /b 0
)

if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
    powershell -ExecutionPolicy Bypass -File "%~dp0run_windows.ps1" -PythonPath "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    exit /b %ERRORLEVEL%
)

powershell -ExecutionPolicy Bypass -File "%~dp0run_windows.ps1"
exit /b %ERRORLEVEL%
