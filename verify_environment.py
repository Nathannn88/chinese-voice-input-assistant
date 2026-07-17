#!/usr/bin/env python3
"""安全检查运行环境；不会加载模型、录音、安装钩子或发送按键。"""

from __future__ import annotations

import os
import platform
import sys
from pathlib import Path


EXPECTED_PYTHON = (3, 12)
DLL_PACKAGES = (
    "nvidia/cublas/bin",
    "nvidia/cudnn/bin",
    "nvidia/cuda_nvrtc/bin",
)


def fail(message: str) -> None:
    print(f"[失败] {message}")
    raise SystemExit(1)


def main() -> None:
    print(f"[系统] {platform.platform()}")
    print(f"[Python] {sys.version.split()[0]} ({sys.executable})")

    if os.name != "nt":
        fail("本工具依赖 Win32 全局钩子，仅支持 Windows。")
    if sys.version_info[:2] != EXPECTED_PYTHON:
        fail("需要 64 位 Python 3.12；请重新运行“安装环境.bat”。")
    if platform.architecture()[0] != "64bit":
        fail("需要 64 位 Python。")

    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    dll_handles = []
    missing_dll_dirs = []
    for relative_path in DLL_PACKAGES:
        dll_dir = site_packages / Path(relative_path)
        if dll_dir.is_dir():
            dll_handles.append(os.add_dll_directory(str(dll_dir)))
        else:
            missing_dll_dirs.append(str(dll_dir))

    if missing_dll_dirs:
        fail("缺少 NVIDIA 运行库目录：\n  " + "\n  ".join(missing_dll_dirs))

    try:
        import ctranslate2
        import faster_whisper
        import numpy
        import pyautogui
        import pyperclip
        import sounddevice
    except Exception as exc:
        fail(f"依赖导入失败：{exc}")

    cuda_devices = ctranslate2.get_cuda_device_count()
    print(f"[faster-whisper] {faster_whisper.__version__}")
    print(f"[CTranslate2] {ctranslate2.__version__}")
    print(f"[CUDA] 检测到 {cuda_devices} 个设备")
    if cuda_devices < 1:
        fail("没有检测到 NVIDIA CUDA 设备；本项目禁止回退 CPU。")

    compute_types = ctranslate2.get_supported_compute_types("cuda")
    print(f"[CUDA] 支持的计算类型：{', '.join(sorted(compute_types))}")
    if "float16" not in compute_types:
        fail("当前 GPU/CUDA 环境不支持 float16。")

    try:
        input_devices = [
            device["name"]
            for device in sounddevice.query_devices()
            if device["max_input_channels"] > 0
        ]
    except Exception as exc:
        fail(f"无法查询录音设备：{exc}")

    print(f"[录音] 检测到 {len(input_devices)} 个输入设备")
    if not input_devices:
        fail("没有检测到可用的麦克风输入设备。")

    # 防止静态分析器把导入误判为未使用；这些导入本身就是检查目标。
    _ = (numpy, pyautogui, pyperclip, dll_handles)
    print("[通过] 运行环境满足要求。")


if __name__ == "__main__":
    main()
