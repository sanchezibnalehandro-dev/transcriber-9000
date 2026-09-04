@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Не найден локальный Python:
    echo %~dp0.venv\Scripts\python.exe
    echo.
    echo Если это свежая копия с GitHub, сначала выполните инструкции из SETUP.md.
    pause
    exit /b 1
)

if not exist "transcriber_app.py" (
    echo Не найден файл приложения:
    echo %~dp0transcriber_app.py
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -X utf8 -c "import customtkinter, tkinterdnd2" >nul 2>nul
if errorlevel 1 (
    echo Не установлены зависимости интерфейса.
    echo.
    echo Выполните:
    echo .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -X utf8 "%~dp0transcriber_app.py"
) else (
    start "" ".venv\Scripts\python.exe" -X utf8 "%~dp0transcriber_app.py"
)
