#!/usr/bin/env python3
"""Download the pinned Whisper model and verify CUDA float16 loading.

This script does not record audio, install global hooks, change the clipboard,
or send keys. It is safe for Codex to run while preparing a cloned project.
"""

from __future__ import annotations

import os

import numpy as np

from audio_settings import AUDIO_DTYPE, SAMPLE_RATE
from model_settings import (
    MODEL_DIR,
    MODEL_REPOSITORY,
    MODEL_REVISION,
    MODEL_SIZE,
)
from nvidia_runtime import configure_nvidia_dll_search


def fail(message: str) -> None:
    print(f"[失败] {message}")
    raise SystemExit(1)


def main() -> None:
    if os.name != "nt":
        fail("本工具仅支持 Windows。")

    try:
        dll_handles = configure_nvidia_dll_search()
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
        smoke_audio = np.zeros(SAMPLE_RATE, dtype=AUDIO_DTYPE)
        segments, _ = model.transcribe(
            smoke_audio,
            language="zh",
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        list(segments)
    except Exception as exc:  # noqa: BLE001 - download/CUDA backends use varied exceptions
        fail(f"下载、GPU 加载或推理失败：{exc}")

    device = model.model.device
    compute_type = model.model.compute_type
    print(f"[模型] device={device}, compute_type={compute_type}")
    if device != "cuda" or compute_type != "float16":
        fail("模型没有按要求加载到 CUDA float16。")

    print("[GPU] 已完成 1 秒静音的真实推理冒烟测试。")
    # Keep DLL directory handles alive until inference has finished.
    _ = dll_handles
    print("[通过] 固定版本模型已下载并通过 GPU 加载、推理验证。")


if __name__ == "__main__":
    main()
