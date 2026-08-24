from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_DIR / "bootstrap_runtime.ps1"
POWERSHELL = Path(
    shutil.which("powershell.exe") or "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
)


def ps_quote(path: Path) -> str:
    return str(path).replace("'", "''")


class BootstrapRuntimeTests(unittest.TestCase):
    def make_project(self):
        base = PROJECT_DIR / ".cache" / "bootstrap-tests"
        base.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(prefix="case-", dir=base)

    def run_bootstrap(self, project: Path, archive: Path | None = None):
        command = [
            str(POWERSHELL),
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPT),
            "-ProjectDir",
            str(project),
        ]
        if archive is not None:
            command.extend(("-UvArchivePath", str(archive)))
        return subprocess.run(
            command, check=False, capture_output=True, text=True, encoding="utf-8"
        )

    def run_layout_check(self, archive: Path):
        command = (
            f". '{ps_quote(SCRIPT)}' -FunctionsOnly; "
            f"Assert-UvArchiveLayout -ArchivePath '{ps_quote(archive)}'"
        )
        return subprocess.run(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                command,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_script_has_utf8_bom_and_runs_from_disk_in_powershell_51(self):
        self.assertEqual(SCRIPT.read_bytes()[:3], b"\xef\xbb\xbf")
        result = subprocess.run(
            [
                str(POWERSHELL),
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-FunctionsOnly",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_existing_uv_is_revalidated_without_download(self):
        result = self.run_bootstrap(PROJECT_DIR)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("已通过版本、哈希和清单检查", result.stdout)
        self.assertNotIn("[下载]", result.stdout)

    def test_bad_archive_hash_preserves_existing_uv(self):
        with self.make_project() as temp:
            project = Path(temp)
            uv_dir = project / ".runtime" / "uv"
            uv_dir.mkdir(parents=True)
            old_uv = uv_dir / "uv.exe"
            old_uv.write_bytes(b"old uv must survive")
            archive = project / "bad.zip"
            with zipfile.ZipFile(archive, "w") as file:
                file.writestr("uv.exe", b"bad")

            result = self.run_bootstrap(project, archive)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(old_uv.read_bytes(), b"old uv must survive")
            self.assertIn("SHA-256", result.stderr + result.stdout)

    def test_archive_rejects_extra_absolute_and_traversal_entries(self):
        with self.make_project() as temp:
            root = Path(temp)
            cases = {
                "extra.zip": ("uv.exe", "uvw.exe", "uvx.exe", "extra.txt"),
                "absolute.zip": ("C:/uv.exe", "uvw.exe", "uvx.exe"),
                "traversal.zip": ("../uv.exe", "uvw.exe", "uvx.exe"),
            }
            for name, entries in cases.items():
                archive = root / name
                with zipfile.ZipFile(archive, "w") as file:
                    for entry in entries:
                        file.writestr(entry, b"x")
                with self.subTest(name=name):
                    result = self.run_layout_check(archive)
                    self.assertNotEqual(result.returncode, 0)

    def test_invalid_cache_target_fails_before_download(self):
        with self.make_project() as temp:
            project = Path(temp)
            (project / ".runtime").mkdir()
            (project / ".cache").write_text("not a directory", encoding="utf-8")

            result = self.run_bootstrap(project)

            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("[下载]", result.stdout)

    def test_reparse_runtime_target_is_rejected(self):
        with self.make_project() as temp:
            project = Path(temp)
            outside = project / "outside"
            outside.mkdir()
            runtime = project / ".runtime"
            command = (
                f"New-Item -ItemType Junction -Path '{ps_quote(runtime)}' "
                f"-Target '{ps_quote(outside)}' | Out-Null"
            )
            created = subprocess.run(
                [str(POWERSHELL), "-NoProfile", "-Command", command],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            if created.returncode != 0:
                self.skipTest(f"无法创建测试 junction：{created.stderr}")

            result = self.run_bootstrap(project)

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("reparse point", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
