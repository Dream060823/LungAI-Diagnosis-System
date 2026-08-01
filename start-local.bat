@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>nul || goto :python_missing
where npm.cmd >nul 2>nul || goto :node_missing

if not exist "backend\.venv\Scripts\python.exe" (
  echo [LungAI] Installing backend dependencies for the first run...
  python -m venv "backend\.venv" || goto :error
  "backend\.venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt" || goto :error
)

if not exist "frontend\node_modules\@cornerstonejs\dicom-image-loader\package.json" goto :install_frontend
if not exist "frontend\node_modules\events\package.json" goto :install_frontend
goto :dependencies_ready

:install_frontend
echo [LungAI] Installing frontend and DICOM decoder dependencies for the first run...
pushd "frontend"
call npm.cmd ci || (popd & goto :error)
popd

:dependencies_ready
powershell -NoProfile -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:5000/health' -TimeoutSec 2; if ($r.status -eq 'ok' -and $r.service -eq 'lung-nodule-backend') { exit 0 } } catch {}; exit 1"
if errorlevel 1 (
  powershell -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort 5000 -ErrorAction SilentlyContinue) { exit 1 }; exit 0"
  if errorlevel 1 goto :backend_port_busy
  echo [LungAI] Starting backend at http://127.0.0.1:5000 ...
  start "LungAI Backend" /D "%CD%\backend" cmd /k ".venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 5000 --no-debugger --no-reload"
) else (
  echo [LungAI] Backend is already running.
)

powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173/' -TimeoutSec 2; if ($r.StatusCode -eq 200 -and $r.Content -match 'LungAI') { exit 0 } } catch {}; exit 1"
if errorlevel 1 (
  powershell -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort 5173 -ErrorAction SilentlyContinue) { exit 1 }; exit 0"
  if errorlevel 1 goto :frontend_port_busy
  echo [LungAI] Starting frontend at http://127.0.0.1:5173 ...
  start "LungAI Frontend" /D "%CD%\frontend" cmd /k "npm.cmd run dev"
) else (
  echo [LungAI] Frontend is already running.
)

echo [LungAI] Waiting for the local system...
powershell -NoProfile -Command "$deadline = (Get-Date).AddSeconds(30); do { try { $r = Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:5173/' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"
if errorlevel 1 goto :startup_timeout

start "" "http://127.0.0.1:5173"
exit /b 0

:python_missing
echo.
echo [LungAI] Python was not found. Install Python 3.10 or newer, then run this file again.
goto :pause_error

:node_missing
echo.
echo [LungAI] Node.js was not found. Install Node.js 20 or newer, then run this file again.
goto :pause_error

:backend_port_busy
echo.
echo [LungAI] Port 5000 is being used by another program. Close that program and try again.
goto :pause_error

:frontend_port_busy
echo.
echo [LungAI] Port 5173 is being used by another program. Close that program and try again.
goto :pause_error

:startup_timeout
echo.
echo [LungAI] The page did not become ready within 30 seconds. Check the LungAI service windows.
goto :pause_error

:error
echo.
echo [LungAI] Setup failed. Check the messages above, then try again.

:pause_error
pause
exit /b 1
