"""配置项目内 NVIDIA DLL，使 CTranslate2 可跨线程延迟加载。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

NVIDIA_DLL_PACKAGES = (
    "nvidia/cublas/bin",
    "nvidia/cudnn/bin",
    "nvidia/cuda_nvrtc/bin",
)


def _path_key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def configure_nvidia_dll_search(prefix: str | Path | None = None) -> list[object]:
    """将 venv 内 NVIDIA DLL 目录加入当前进程并返回需保活的句柄。"""
    site_packages = Path(prefix or sys.prefix) / "Lib" / "site-packages"
    dll_dirs = [site_packages / Path(relative) for relative in NVIDIA_DLL_PACKAGES]
    missing = [str(path) for path in dll_dirs if not path.is_dir()]
    if missing:
        raise FileNotFoundError("缺少 NVIDIA 运行库目录：\n  " + "\n  ".join(missing))

    dll_paths = [str(path.resolve()) for path in dll_dirs]
    dll_keys = {_path_key(path) for path in dll_paths}
    existing_paths = [path for path in os.environ.get("PATH", "").split(os.pathsep) if path]
    remaining_paths = [path for path in existing_paths if _path_key(path) not in dll_keys]
    os.environ["PATH"] = os.pathsep.join([*dll_paths, *remaining_paths])

    return [os.add_dll_directory(path) for path in dll_paths]
