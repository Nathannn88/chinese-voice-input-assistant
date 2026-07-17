@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

if not exist "venv\Scripts\python.exe" (
    echo [首次运行] 尚未安装运行环境，开始自动安装...
    call "%~dp0安装环境.bat"
    if errorlevel 1 (
        echo.
        echo [ERROR] 环境安装失败，请查看上方提示。
        pause
        exit /b 1
    )
)

"venv\Scripts\python.exe" main.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] exitcode: %errorlevel%
)
pause
endlocal
