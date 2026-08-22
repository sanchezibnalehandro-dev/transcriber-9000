@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Local Python was not found:
    echo %~dp0.venv\Scripts\python.exe
    echo.
    echo Check that the .venv folder is next to this file.
    echo For a fresh GitHub clone, follow SETUP.md first.
    pause
    exit /b 1
)

if not exist "topgun_minimal_app.py" (
    echo GUI script was not found:
    echo %~dp0topgun_minimal_app.py
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -X utf8 -c "import customtkinter, tkinterdnd2" >nul 2>nul
if errorlevel 1 (
    echo GUI dependencies are not installed.
    echo.
    echo Run:
    echo .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -X utf8 "%~dp0topgun_minimal_app.py"
) else (
    start "" ".venv\Scripts\python.exe" -X utf8 "%~dp0topgun_minimal_app.py"
)
