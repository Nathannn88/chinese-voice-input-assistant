from __future__ import annotations

import contextlib
import io
import types
import unittest
from unittest import mock

import verify_environment
import verify_local_install


class FakeSoundDevice:
    def __init__(self, *, reject_format=False):
        self.default = types.SimpleNamespace(device=(2, 5))
        self.reject_format = reject_format
        self.checked = None

    def query_devices(self, device=None, kind=None):
        if device is None:
            return [
                {"name": "Speaker", "max_input_channels": 0},
                {"name": "Default microphone", "max_input_channels": 2},
            ]
        self.assert_default_query(device, kind)
        return {"name": "Default microphone", "max_input_channels": 2}

    def assert_default_query(self, device, kind):
        if (device, kind) != (2, "input"):
            raise AssertionError((device, kind))

    def check_input_settings(self, **kwargs):
        self.checked = kwargs
        if self.reject_format:
            raise ValueError("unsupported format")


class EnvironmentValidationTests(unittest.TestCase):
    def test_default_microphone_uses_shared_main_settings(self):
        sounddevice = FakeSoundDevice()

        devices, default_device = verify_environment.verify_default_input(sounddevice)

        self.assertEqual(devices, ["Default microphone"])
        self.assertEqual(default_device["name"], "Default microphone")
        self.assertEqual(
            sounddevice.checked,
            {
                "device": 2,
                "samplerate": 16000,
                "channels": 1,
                "dtype": "float32",
            },
        )

    def test_unsupported_default_microphone_format_fails(self):
        sounddevice = FakeSoundDevice(reject_format=True)

        with (
            contextlib.redirect_stdout(io.StringIO()) as output,
            self.assertRaises(SystemExit),
        ):
            verify_environment.verify_default_input(sounddevice)

        self.assertIn("16000 Hz / 1 channel / float32", output.getvalue())


class LocalInstallValidationTests(unittest.TestCase):
    def test_missing_environment_variable_is_reported(self):
        errors = []
        with mock.patch.dict("os.environ", {}, clear=True):
            verify_local_install.validate_environment_path("TEMP", errors)
        self.assertEqual(errors, ["缺少环境变量 TEMP"])

    def test_project_environment_path_is_accepted(self):
        errors = []
        value = str(verify_local_install.CACHE_DIR / "tmp")
        with mock.patch.dict("os.environ", {"TEMP": value}, clear=True):
            verify_local_install.validate_environment_path("TEMP", errors)
        self.assertEqual(errors, [])

    def test_outside_environment_path_is_rejected(self):
        errors = []
        outside = verify_local_install.PROJECT_DIR.parent
        with mock.patch.dict("os.environ", {"TEMP": str(outside)}, clear=True):
            verify_local_install.validate_environment_path("TEMP", errors)
        self.assertEqual(len(errors), 1)
        self.assertIn("不在项目内", errors[0])

    def test_build_tool_versions_are_exact(self):
        errors = []

        def version(package):
            return {"setuptools": "70.2.0", "wheel": "0.45.1"}[package]

        with mock.patch.object(
            verify_local_install.importlib.metadata, "version", side_effect=version
        ):
            verify_local_install.validate_package_versions(errors)
        self.assertEqual(errors, [])

    def test_wrong_build_tool_version_is_rejected(self):
        errors = []
        with mock.patch.object(
            verify_local_install.importlib.metadata, "version", return_value="0.0"
        ):
            verify_local_install.validate_package_versions(errors)
        self.assertEqual(len(errors), 2)


if __name__ == "__main__":
    unittest.main()
