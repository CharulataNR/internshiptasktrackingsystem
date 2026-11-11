@echo off
REM Start for Windows WITHOUT a virtual environment (works on PCs where venv\Scripts\*.exe is blocked by Device Guard).
cd /d "%~dp0"
set PY=python
where python >nul 2>nul || set PY=py
echo Installing packages for the current user...
%PY% -m pip install --user --quiet -r requirements.txt || (echo Package installation failed. & pause & exit /b 1)
echo.
echo Starting InternTrack on http://127.0.0.1:5000  (press Ctrl+C to stop)
start "" http://127.0.0.1:5000
%PY% app.py
pause
