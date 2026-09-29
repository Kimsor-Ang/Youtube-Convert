@echo off
title YouTube Downloader Web App
echo ========================================================
echo   Starting YouTube Downloader Web Application...
echo ========================================================
echo.

set PYTHON_CMD=python
where python >nul 2>nul
if %errorlevel% neq 0 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
        set PYTHON_CMD="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    ) else (
        echo [ERROR] Python not found in PATH or standard directory!
        pause
        exit /b 1
    )
)

echo Using Python: %PYTHON_CMD%
echo Opening application in your web browser...
echo.

%PYTHON_CMD% app.py

pause
