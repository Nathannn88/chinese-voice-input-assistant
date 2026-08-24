from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
PYTHON = PROJECT_DIR / "venv" / "Scripts" / "python.exe"


class DependencyLockTests(unittest.TestCase):
    def test_build_lock_has_only_expected_wheels_and_hashes(self):
        lock = (PROJECT_DIR / "requirements.build.txt").read_text(encoding="utf-8")
        requirement_lines = [
            line
            for line in lock.splitlines()
            if line and not line.startswith(("#", "--", " ", "\t"))
        ]
        self.assertEqual(
            requirement_lines,
            ["setuptools==70.2.0 \\", "wheel==0.45.1 \\"],
        )
        self.assertIn(
            "sha256:b8b8060bb426838fbe942479c90296ce976249451118ef566a5a0b7d8b78fb05",
            lock,
        )
        self.assertIn(
            "sha256:708e7481cc80179af0e556bbf0cc00b8444c7321e2700b8d8580231d13017248",
            lock,
        )
        self.assertEqual(lock.count("--hash=sha256:"), 2)

    def test_every_runtime_requirement_block_has_a_sha256_hash(self):
        lock = (PROJECT_DIR / "requirements.txt").read_text(encoding="utf-8")
        blocks = []
        current = []
        for line in lock.splitlines():
            if line and not line.startswith((" ", "#", "--")):
                if current:
                    blocks.append(current)
                current = [line]
            elif current:
                current.append(line)
        if current:
            blocks.append(current)

        self.assertGreater(len(blocks), 40)
        for block in blocks:
            with self.subTest(requirement=block[0]):
                self.assertIn("--hash=sha256:", "\n".join(block))

    def test_install_script_uses_build_lock_before_no_build_isolation(self):
        script = (PROJECT_DIR / "安装环境.bat").read_text(encoding="utf-8")
        build_position = script.index("requirements.build.txt")
        runtime_position = script.index("--no-build-isolation -r requirements.txt")
        self.assertLess(build_position, runtime_position)
        self.assertIn("--require-hashes --only-binary=:all:", script)
        self.assertIn("bootstrap_runtime.ps1", script)
        self.assertNotIn("Invoke-RestMethod", script)
        self.assertNotIn("Invoke-Expression", script)

    def test_pip_rejects_wrong_hash_without_network(self):
        cache_root = PROJECT_DIR / ".cache"
        cache_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="hash-test-", dir=cache_root) as temp:
            temp_dir = Path(temp)
            fake_wheel = temp_dir / "wheel-0.45.1-py3-none-any.whl"
            fake_wheel.write_bytes(b"not the locked wheel")
            requirement = temp_dir / "wrong-hash.txt"
            requirement.write_text(
                "wheel==0.45.1 "
                "--hash=sha256:0000000000000000000000000000000000000000000000000000000000000000\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    str(PYTHON),
                    "-m",
                    "pip",
                    "install",
                    "--force-reinstall",
                    "--no-deps",
                    "--no-index",
                    "--find-links",
                    str(temp_dir),
                    "--require-hashes",
                    "-r",
                    str(requirement),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("THESE PACKAGES DO NOT MATCH THE HASHES", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
