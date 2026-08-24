from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import nvidia_runtime


class NvidiaRuntimeTests(unittest.TestCase):
    def _create_runtime_dirs(self, root: Path) -> list[str]:
        paths = []
        for relative in nvidia_runtime.NVIDIA_DLL_PACKAGES:
            path = root / "Lib" / "site-packages" / Path(relative)
            path.mkdir(parents=True)
            paths.append(str(path.resolve()))
        return paths

    def test_configure_prepends_paths_and_returns_live_handles(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dll_paths = self._create_runtime_dirs(root)
            handles = [object(), object(), object()]
            old_path = os.pathsep.join(["C:\\Windows", dll_paths[1]])

            with (
                mock.patch.dict(os.environ, {"PATH": old_path}, clear=True),
                mock.patch.object(
                    nvidia_runtime.os,
                    "add_dll_directory",
                    side_effect=handles,
                ) as add_directory,
            ):
                result = nvidia_runtime.configure_nvidia_dll_search(root)
                path_entries = os.environ["PATH"].split(os.pathsep)

            self.assertEqual(result, handles)
            self.assertEqual(path_entries[:3], dll_paths)
            self.assertEqual(path_entries.count(dll_paths[1]), 1)
            self.assertEqual(
                [call.args[0] for call in add_directory.call_args_list],
                dll_paths,
            )

    def test_missing_directory_fails_before_mutating_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = "C:\\Windows"
            with (
                mock.patch.dict(os.environ, {"PATH": original_path}, clear=True),
                mock.patch.object(nvidia_runtime.os, "add_dll_directory") as add_directory,
                self.assertRaisesRegex(FileNotFoundError, "缺少 NVIDIA 运行库目录"),
            ):
                nvidia_runtime.configure_nvidia_dll_search(Path(temp_dir))
                self.assertEqual(os.environ.get("PATH"), original_path)

            add_directory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
