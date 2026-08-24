from __future__ import annotations

import contextlib
import io
import threading
import unittest
from unittest import mock

import numpy as np

import main


class DummyThread:
    def __init__(self, *, target, args=(), daemon=None, fail_start=False):
        self.target = target
        self.args = args
        self.daemon = daemon
        self.fail_start = fail_start
        self.started = False

    def start(self):
        if self.fail_start:
            raise RuntimeError("thread start failed")
        self.started = True


class FakeInputStream:
    def __init__(self, session, frame_count=10):
        self.session = session
        self.frame_count = frame_count
        self.read_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, frame_size):
        self.read_count += 1
        if self.read_count >= self.frame_count:
            self.session.stop_event.set()
        return np.ones((frame_size, 1), dtype=np.float32), False


class RecordingStateTests(unittest.TestCase):
    def setUp(self):
        with main._recording_lock:
            main._active_session = None
        main.model_ready.set()

    def tearDown(self):
        with main._recording_lock:
            main._active_session = None
        main.model_ready.set()

    def test_immediate_stop_before_recording_loop_is_safe(self):
        session = main.RecordingSession()
        session.stop_event.set()
        stream = FakeInputStream(session)
        main._active_session = session

        with mock.patch.object(main.sd, "InputStream", return_value=stream):
            main.record_and_transcribe(session)

        self.assertEqual(stream.read_count, 0)
        self.assertIsNone(main._active_session)

    def test_repeated_start_creates_only_one_session(self):
        created = []

        def factory(**kwargs):
            thread = DummyThread(**kwargs)
            created.append(thread)
            return thread

        with mock.patch.object(main.threading, "Thread", side_effect=factory):
            main._start_recording()
            first = main._active_session
            main._start_recording()

        self.assertIs(first, main._active_session)
        self.assertEqual(len(created), 1)

    def test_stop_is_idempotent_with_or_without_session(self):
        main._stop_recording()
        session = main.RecordingSession()
        main._active_session = session

        main._stop_recording()
        main._stop_recording()

        self.assertTrue(session.stop_event.is_set())
        self.assertIs(session, main._active_session)

    def test_start_is_rejected_while_session_is_processing(self):
        active = main.RecordingSession()
        main._active_session = active

        with (
            mock.patch.object(main.threading, "Thread") as thread_cls,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            main._start_recording()

        thread_cls.assert_not_called()
        self.assertIs(active, main._active_session)
        self.assertIn("仍在处理中", output.getvalue())

    def test_input_stream_failure_releases_session(self):
        session = main.RecordingSession()
        main._active_session = session

        with mock.patch.object(
            main.sd, "InputStream", side_effect=RuntimeError("device failed")
        ):
            main.record_and_transcribe(session)

        self.assertIsNone(main._active_session)

    def test_thread_start_failure_rolls_back_session(self):
        def factory(**kwargs):
            return DummyThread(**kwargs, fail_start=True)

        with (
            mock.patch.object(main.threading, "Thread", side_effect=factory),
            self.assertRaisesRegex(RuntimeError, "thread start failed"),
        ):
            main._start_recording()

        self.assertIsNone(main._active_session)

    def _run_pipeline(self, *, transcribed="测试", patches=()):
        session = main.RecordingSession()
        stream = FakeInputStream(session)
        main._active_session = session
        stack = contextlib.ExitStack()
        with stack:
            stack.enter_context(
                mock.patch.object(main.sd, "InputStream", return_value=stream)
            )
            stack.enter_context(mock.patch.object(main, "_transcribe", return_value=transcribed))
            stack.enter_context(mock.patch.object(main.time, "sleep"))
            stack.enter_context(mock.patch.object(main.pyperclip, "paste", return_value="old"))
            stack.enter_context(mock.patch.object(main.pyperclip, "copy"))
            stack.enter_context(mock.patch.object(main.pyautogui, "hotkey"))
            for patcher in patches:
                stack.enter_context(patcher)
            main.record_and_transcribe(session)
        self.assertIsNone(main._active_session)

    def test_pipeline_failures_always_release_session(self):
        cases = (
            mock.patch.object(main, "_transcribe", side_effect=RuntimeError("whisper")),
            mock.patch.object(main.re, "sub", side_effect=RuntimeError("hotword")),
            mock.patch.object(main.pyperclip, "paste", side_effect=RuntimeError("clipboard")),
            mock.patch.object(main.pyautogui, "hotkey", side_effect=RuntimeError("paste")),
        )
        for patcher in cases:
            with self.subTest(patcher=patcher):
                self._run_pipeline(patches=(patcher,))

    def test_model_not_ready_does_not_create_thread(self):
        main.model_ready.clear()

        with mock.patch.object(main.threading, "Thread") as thread_cls:
            main._start_recording()

        thread_cls.assert_not_called()
        self.assertIsNone(main._active_session)

    def test_many_simultaneous_starts_keep_one_active_session(self):
        real_thread = threading.Thread
        gate = threading.Event()
        callers = [real_thread(target=lambda: (gate.wait(), main._start_recording())) for _ in range(20)]
        created = []

        def factory(**kwargs):
            thread = DummyThread(**kwargs)
            created.append(thread)
            return thread

        for caller in callers:
            caller.start()
        with mock.patch.object(main.threading, "Thread", side_effect=factory):
            gate.set()
            for caller in callers:
                caller.join()

        self.assertEqual(len(created), 1)
        self.assertIsNotNone(main._active_session)

    def test_completed_session_allows_next_recording(self):
        created = []

        def factory(**kwargs):
            thread = DummyThread(**kwargs)
            created.append(thread)
            return thread

        with mock.patch.object(main.threading, "Thread", side_effect=factory):
            main._start_recording()
            first = main._active_session
            main._release_session(first)
            main._start_recording()

        self.assertIsNot(first, main._active_session)
        self.assertEqual(len(created), 2)


class ActionWorkerTests(unittest.TestCase):
    def test_action_failure_and_unknown_action_do_not_kill_worker(self):
        actions = iter(("enter", "unknown", "screenshot"))

        def get_action():
            try:
                return next(actions)
            except StopIteration:
                raise KeyboardInterrupt

        fake_queue = mock.Mock()
        fake_queue.get.side_effect = get_action
        with (
            mock.patch.object(main, "_action_queue", fake_queue),
            mock.patch.object(
                main.pyautogui, "press", side_effect=RuntimeError("enter failed")
            ),
            mock.patch.object(main.pyautogui, "hotkey") as hotkey,
            contextlib.redirect_stdout(io.StringIO()) as output,
            self.assertRaises(KeyboardInterrupt),
        ):
            main._action_worker()

        hotkey.assert_called_once_with("ctrl", "1")
        self.assertIn("enter failed", output.getvalue())
        self.assertIn("未知动作", output.getvalue())


if __name__ == "__main__":
    unittest.main()
