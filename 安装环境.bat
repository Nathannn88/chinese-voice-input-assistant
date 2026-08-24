@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "PROJECT_DIR=%CD%"
set "PROJECT_RUNTIME_DIR=%PROJECT_DIR%\.runtime"
set "RUNTIME_UV_DIR=%PROJECT_RUNTIME_DIR%\uv"
set "UV_EXE=%RUNTIME_UV_DIR%\uv.exe"
set "UV_VERSION=0.12.5"
set "UV_PYTHON_INSTALL_DIR=%PROJECT_RUNTIME_DIR%\python"
set "PROJECT_CACHE_DIR=%PROJECT_DIR%\.cache"
set "UV_CACHE_DIR=%PROJECT_CACHE_DIR%\uv"
set "TEMP=%PROJECT_CACHE_DIR%\tmp"
set "TMP=%TEMP%"
set "HF_HOME=%PROJECT_CACHE_DIR%\huggingface"
set "CUDA_CACHE_PATH=%PROJECT_CACHE_DIR%\cuda"
set "UV_NO_MODIFY_PATH=1"
set "UV_MANAGED_PYTHON=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_CACHE_DIR=%PROJECT_CACHE_DIR%\pip"
set "PIP_NO_CACHE_DIR=1"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"

echo ==================================================
echo   中文语音转文字助手 - 项目内环境安装
echo ==================================================
echo.

echo [1/6] 检查项目内 uv %UV_VERSION%...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%\bootstrap_runtime.ps1" -ProjectDir "%PROJECT_DIR%"
if errorlevel 1 goto uv_install_failed

"%UV_EXE%" --version
if errorlevel 1 goto uv_run_failed

echo.
echo [2/6] 检查项目内 Python 3.12.12 与 venv...
if not exist "venv\Scripts\python.exe" goto create_venv
"venv\Scripts\python.exe" -c "import os,pathlib,sys; root=pathlib.Path(os.environ['UV_PYTHON_INSTALL_DIR']).resolve(); base=pathlib.Path(sys.base_prefix).resolve(); raise SystemExit(0 if base == root or root in base.parents else 1)" >nul 2>nul
if errorlevel 1 goto create_venv
echo 检测到有效的项目内 venv，继续校验依赖。
goto venv_ready

:create_venv
if exist "venv" echo 检测到失效或非项目内 venv，正在安全重建...
if exist "venv" rmdir /s /q "%PROJECT_DIR%\venv"
"%UV_EXE%" venv --python 3.12.12 --seed "venv"
if errorlevel 1 goto venv_failed

:venv_ready

echo.
echo [3/6] 安装哈希锁定的构建工具与运行依赖...
"venv\Scripts\python.exe" -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.build.txt
if errorlevel 1 exit /b 1
"venv\Scripts\python.exe" -m pip install --no-cache-dir --require-hashes --no-build-isolation -r requirements.txt
if errorlevel 1 exit /b 1

echo.
echo [4/6] 检查 Python、依赖、NVIDIA GPU 与麦克风...
"venv\Scripts\python.exe" verify_environment.py
if errorlevel 1 (
    echo.
    echo [ERROR] 环境检查未通过，请根据上方信息排查。
    exit /b 1
)

echo.
echo [5/6] 准备固定版本的 Whisper large-v3 模型...
"venv\Scripts\python.exe" prepare_model.py
if errorlevel 1 (
    echo.
    echo [ERROR] 模型准备失败，请根据上方信息排查网络或 GPU 环境。
    exit /b 1
)

echo.
echo [6/6] 验证项目内自包含布局...
"venv\Scripts\python.exe" verify_local_install.py
if errorlevel 1 (
    echo.
    echo [ERROR] 项目内布局验证失败。
    exit /b 1
)

"%UV_EXE%" cache clean >nul 2>nul
if errorlevel 1 goto cleanup_failed
if exist "%TEMP%" rmdir /s /q "%TEMP%"
if exist "%TEMP%" goto cleanup_failed
mkdir "%TEMP%" >nul 2>nul
if errorlevel 1 goto cleanup_failed

echo.
echo [完成] 环境安装成功，Python、依赖、模型和缓存均位于项目目录。
echo 接下来双击“启动_whisper.bat”。
exit /b 0

:uv_install_failed
echo [ERROR] 项目内 uv 安装失败。
exit /b 1

:uv_run_failed
echo [ERROR] 项目内 uv 无法运行：%UV_EXE%
exit /b 1

:venv_failed
echo [ERROR] 项目内 Python 3.12.12 或 venv 创建失败。
exit /b 1

:cleanup_failed
echo [ERROR] 项目缓存或临时目录清理失败，未报告安装成功。
exit /b 1
