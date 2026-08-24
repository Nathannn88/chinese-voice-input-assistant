#!/usr/bin/env python3
"""验证运行时、缓存和工具链都严格位于当前项目。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import os
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

# B404 is suppressed because subprocess only queries the fixed, hashed local uv.exe.

PROJECT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = PROJECT_DIR / ".runtime"
LOCAL_UV_DIR = RUNTIME_DIR / "uv"
LOCAL_UV = LOCAL_UV_DIR / "uv.exe"
LOCAL_PYTHON_ROOT = RUNTIME_DIR / "python"
VENV_DIR = PROJECT_DIR / "venv"
CACHE_DIR = PROJECT_DIR / ".cache"
MODELS_DIR = PROJECT_DIR / "models"

EXPECTED_PYTHON = (3, 12, 12)
EXPECTED_UV_VERSION = "0.12.5"
EXPECTED_UV_SHA256 = (
    "8da6cedef60c27ac997ebf400fbfc6d373c5b0a7ae6a299b9d52be7fe63723fb"
)
EXPECTED_PACKAGES = {
    "setuptools": "70.2.0",
    "wheel": "0.45.1",
}
PROJECT_PATH_ENV = (
    "TEMP",
    "TMP",
    "UV_PYTHON_INSTALL_DIR",
    "UV_CACHE_DIR",
    "PIP_CACHE_DIR",
    "HF_HOME",
    "CUDA_CACHE_PATH",
)


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except (OSError, ValueError):
        return False
    return True


def is_reparse_point(path: Path) -> bool:
    try:
        stat_result = path.lstat()
    except OSError:
        return False
    attributes = getattr(stat_result, "st_file_attributes", 0)
    reparse_flag = getattr(os.stat_result, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def validate_managed_path(
    path: Path,
    label: str,
    errors: list[str],
) -> None:
    if not path.exists():
        errors.append(f"{label}不存在：{path}")
        return
    if is_reparse_point(path):
        errors.append(f"{label}不能是 reparse point：{path}")
        return
    if not path.is_dir():
        errors.append(f"{label}不是目录：{path}")
    if not is_within(path, PROJECT_DIR):
        errors.append(f"{label}解析到项目外：{path.resolve()}")


def validate_environment_path(name: str, errors: list[str]) -> None:
    value = os.environ.get(name)
    if not value:
        errors.append(f"缺少环境变量 {name}")
        return
    path = Path(value)
    if not path.is_absolute():
        errors.append(f"{name} 不是绝对路径：{value}")
        return
    if not is_within(path, PROJECT_DIR):
        errors.append(f"{name} 不在项目内：{path.resolve()}")
        return

    try:
        relative_parts = path.resolve(strict=False).relative_to(PROJECT_DIR).parts
    except ValueError:
        return
    current = PROJECT_DIR
    for part in relative_parts:
        current /= part
        if current.exists() and is_reparse_point(current):
            errors.append(f"{name} 经过 reparse point：{current}")
            return


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_uv(errors: list[str]) -> None:
    if not LOCAL_UV.is_file():
        errors.append(f"项目内 uv 不存在：{LOCAL_UV}")
        return
    if is_reparse_point(LOCAL_UV):
        errors.append(f"uv.exe 不能是 reparse point：{LOCAL_UV}")
        return
    actual_hash = file_sha256(LOCAL_UV)
    if actual_hash != EXPECTED_UV_SHA256:
        errors.append(
            f"uv.exe SHA-256 不匹配：期望 {EXPECTED_UV_SHA256}，实际 {actual_hash}"
        )
    try:
        # Executable and argv are fixed after project-boundary/hash validation.
        result = subprocess.run(  # nosec B603
            [str(LOCAL_UV), "--version"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        errors.append(f"uv.exe 无法运行：{exc}")
        return
    version_output = result.stdout.strip()
    if not (
        version_output == f"uv {EXPECTED_UV_VERSION}"
        or version_output.startswith(f"uv {EXPECTED_UV_VERSION} ")
    ):
        errors.append(
            f"uv 版本不是 {EXPECTED_UV_VERSION}：{version_output or '<空输出>'}"
        )


def validate_package_versions(errors: list[str]) -> None:
    for package, expected in EXPECTED_PACKAGES.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            errors.append(f"缺少构建依赖：{package}=={expected}")
            continue
        if actual != expected:
            errors.append(f"{package} 版本不是 {expected}：{actual}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict-user-cleanup",
        action="store_true",
        help="同时要求恢复期间创建的已知用户级 uv/Python 位置不存在",
    )
    args = parser.parse_args()
    errors: list[str] = []

    if sys.version_info[:3] != EXPECTED_PYTHON:
        errors.append(f"Python 版本不是 3.12.12：{sys.version.split()[0]}")

    if is_reparse_point(PROJECT_DIR):
        errors.append(f"项目目录不能是 reparse point：{PROJECT_DIR}")
    for path, label in (
        (RUNTIME_DIR, ".runtime"),
        (LOCAL_UV_DIR, ".runtime\\uv"),
        (VENV_DIR, "venv"),
        (CACHE_DIR, ".cache"),
        (MODELS_DIR, "models"),
    ):
        validate_managed_path(path, label, errors)

    if not is_within(Path(sys.executable), VENV_DIR):
        errors.append(f"当前解释器不属于项目 venv：{sys.executable}")
    if not is_within(Path(sys.prefix), VENV_DIR):
        errors.append(f"当前 sys.prefix 不属于项目 venv：{sys.prefix}")
    if not is_within(Path(sys.base_prefix), LOCAL_PYTHON_ROOT):
        errors.append(f"venv 的基础 Python 不在项目内：{sys.base_prefix}")

    validate_uv(errors)
    validate_package_versions(errors)
    for variable in PROJECT_PATH_ENV:
        validate_environment_path(variable, errors)

    temp_dir = Path(tempfile.gettempdir())
    if not is_within(temp_dir, PROJECT_DIR):
        errors.append(f"tempfile.gettempdir() 不在项目内：{temp_dir}")

    if args.strict_user_cleanup:
        user_profile = Path(os.environ.get("USERPROFILE", Path.home()))
        global_uv = user_profile / ".local" / "bin" / "uv.exe"
        global_uv_python = user_profile / "AppData" / "Roaming" / "uv" / "python"
        if global_uv.exists():
            errors.append(f"仍存在用户级 uv：{global_uv}")
        if global_uv_python.exists():
            errors.append(f"仍存在用户级 uv Python：{global_uv_python}")

    if errors:
        for error in errors:
            print(f"[失败] {error}")
        raise SystemExit(1)

    print(f"[通过] uv {EXPECTED_UV_VERSION}：{LOCAL_UV}")
    print(f"[通过] Python 3.12.12：{sys.base_prefix}")
    print(f"[通过] venv：{sys.prefix}")
    print("[通过] setuptools 70.2.0 / wheel 0.45.1")
    print(f"[通过] 缓存与临时目录：{CACHE_DIR}")
    print(f"[通过] 模型目录：{MODELS_DIR}")
    print("[通过] 所有运行目录、缓存变量和工具链均受项目边界约束。")


if __name__ == "__main__":
    main()
