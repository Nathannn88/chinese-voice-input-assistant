@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PIP_DISABLE_PIP_VERSION_CHECK=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1

echo ==================================================
echo   中文语音转文字助手 - 环境安装
echo ==================================================
echo.

if exist "venv\Scripts\python.exe" (
    echo [1/4] 检测到现有 venv，继续更新依赖。
) else (
    echo [1/4] 正在创建 Python 3.12.12 虚拟环境...
    where uv >nul 2>nul
    if not errorlevel 1 (
        uv venv --python 3.12.12 --seed venv
    ) else (
        where py >nul 2>nul
        if errorlevel 1 (
            echo [ERROR] 未找到 uv 或 Python Launcher。
            echo 请先安装 uv，或安装 64 位 Python 3.12 后重试。
            exit /b 1
        )
        py -3.12 -m venv venv
    )
    if errorlevel 1 (
        echo [ERROR] 创建虚拟环境失败。
        exit /b 1
    )
)

echo.
echo [2/4] 正在安装固定版本依赖，首次安装需要下载 CUDA 运行库...
"venv\Scripts\python.exe" -m pip install --require-hashes --index-url https://pypi.org/simple -r requirements.txt
if errorlevel 1 exit /b 1

echo.
echo [3/4] 正在检查 Python、依赖与 NVIDIA GPU...
"venv\Scripts\python.exe" verify_environment.py
if errorlevel 1 (
    echo.
    echo [ERROR] 环境检查未通过，请根据上方信息排查。
    exit /b 1
)

echo.
echo [4/4] 正在准备固定版本的 Whisper large-v3 模型...
"venv\Scripts\python.exe" prepare_model.py
if errorlevel 1 (
    echo.
    echo [ERROR] 模型准备失败，请根据上方信息排查网络或 GPU 环境。
    exit /b 1
)

echo.
echo [完成] 环境安装成功。
echo 接下来双击“启动_whisper.bat”。
exit /b 0
