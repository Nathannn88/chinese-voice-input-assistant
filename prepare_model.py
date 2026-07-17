#!/usr/bin/env python3
"""Download the pinned Whisper model and verify CUDA float16 loading.

This script does not record audio, install global hooks, change the clipboard,
or send keys. It is safe for Codex to run while preparing a cloned project.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from model_settings import (
    MODEL_DIR,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    MODEL_SIZE,
)


DLL_PACKAGES = (
    "nvidia/cublas/bin",
    "nvidia/cudnn/bin",
    "nvidia/cuda_nvrtc/bin",
)


def fail(message: str) -> None:
    print(f"[失败] {message}")
    raise SystemExit(1)


def main() -> None:
    if os.name != "nt":
        fail("本工具仅支持 Windows。")

    site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    dll_handles = []
    for relative_path in DLL_PACKAGES:
        dll_dir = site_packages / Path(relative_path)
        if not dll_dir.is_dir():
            fail(f"缺少 NVIDIA 运行库目录：{dll_dir}")
        dll_handles.append(os.add_dll_directory(str(dll_dir)))

    try:
        from faster_whisper import WhisperModel

        print(f"[模型] 仓库：{MODEL_REPOSITORY}")
        print(f"[模型] revision：{MODEL_REVISION}")
        print("[模型] 首次运行需下载约 3 GB，请保持网络连接…")
        model = WhisperModel(
            MODEL_SIZE,
            device="cuda",
            compute_type="float16",
            download_root=MODEL_DIR,
            revision=MODEL_REVISION,
        )
    except Exception as exc:
        fail(f"下载或 GPU 加载失败：{exc}")

    device = model.model.device
    compute_type = model.model.compute_type
    print(f"[模型] device={device}, compute_type={compute_type}")
    if device != "cuda" or compute_type != "float16":
        fail("模型没有按要求加载到 CUDA float16。")

    # Keep DLL directory handles alive until the model has finished loading.
    _ = dll_handles
    print("[通过] 固定版本模型已下载并通过 GPU 加载验证。")


if __name__ == "__main__":
    main()
