@echo off
rem ClaimGuard-KR: start the app and open the browser (double-click).
cd /d "%~dp0"
set PORT=8501

if not exist ".venv\Scripts\streamlit.exe" (
    echo [ERROR] .venv not found. Install first - see the Run section of README.md
    pause
    exit /b 1
)

rem Already running: just open the browser
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue) { exit 1 }"
if errorlevel 1 (
    echo Already running: http://localhost:%PORT%
    if not "%~1"=="--no-browser" start "" http://localhost:%PORT%
    exit /b 0
)

echo Starting ClaimGuard-KR...
start "ClaimGuard-KR" /min ".venv\Scripts\streamlit.exe" run app.py --server.headless true --server.port %PORT%

rem Wait up to 60 seconds until the app answers
powershell -NoProfile -Command "for ($i = 0; $i -lt 60; $i++) { try { Invoke-WebRequest -UseBasicParsing http://localhost:%PORT%/_stcore/health -TimeoutSec 2 | Out-Null; exit 0 } catch { Start-Sleep -Seconds 1 } }; exit 1"
if errorlevel 1 (
    echo [ERROR] App did not start within 60 seconds. Check the minimized "ClaimGuard-KR" window.
    pause
    exit /b 1
)

echo Running: http://localhost:%PORT%   (run stop_app.cmd to stop)
if not "%~1"=="--no-browser" start "" http://localhost:%PORT%
