@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PROJECT_DIR=%CD%"
set "UV_PYTHON_INSTALL_DIR=%PROJECT_DIR%\.runtime\python"
set "PROJECT_CACHE_DIR=%PROJECT_DIR%\.cache"
set "UV_CACHE_DIR=%PROJECT_CACHE_DIR%\uv"
set "TEMP=%PROJECT_CACHE_DIR%\tmp"
set "TMP=%TEMP%"
set "HF_HOME=%PROJECT_CACHE_DIR%\huggingface"
set "CUDA_CACHE_PATH=%PROJECT_CACHE_DIR%\cuda"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

if not exist "%TEMP%" mkdir "%TEMP%"
if not exist "%HF_HOME%" mkdir "%HF_HOME%"
if not exist "%CUDA_CACHE_PATH%" mkdir "%CUDA_CACHE_PATH%"

if not exist "venv\Scripts\python.exe" goto install_environment
"venv\Scripts\python.exe" -c "import os,pathlib,sys; root=pathlib.Path(os.environ['UV_PYTHON_INSTALL_DIR']).resolve(); base=pathlib.Path(sys.base_prefix).resolve(); raise SystemExit(0 if base == root or root in base.parents else 1)" >nul 2>nul
if errorlevel 1 goto install_environment
goto run_assistant

:install_environment
echo [首次运行] 未检测到有效的项目内运行环境，开始自动安装...
call "%~dp0安装环境.bat"
if errorlevel 1 goto install_failed

:run_assistant

"venv\Scripts\python.exe" main.py
set "APP_EXIT=%ERRORLEVEL%"
if not "%APP_EXIT%"=="0" (
    echo.
    echo [ERROR] exitcode: %APP_EXIT%
)
pause
exit /b %APP_EXIT%

:install_failed
echo.
echo [ERROR] 环境安装失败，请查看上方提示。
pause
exit /b 1
