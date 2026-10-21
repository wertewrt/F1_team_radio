"""Runtime coverage for console-free releases; existing tests stay unchanged."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

import launch_gui
from teamradio import media, runtime


class RuntimeErrorsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        environment = mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        old_sys, old_thread = sys.excepthook, threading.excepthook
        self.addCleanup(setattr, sys, "excepthook", old_sys)
        self.addCleanup(setattr, threading, "excepthook", old_thread)

    def test_windowed_startup_failure_logs_traceback_and_reports_location(self):
        with mock.patch("teamradio.gui.main", side_effect=RuntimeError("startup test")), mock.patch.object(runtime, "_notify") as notify, mock.patch.object(sys, "stderr", None):
            self.assertEqual(launch_gui.main([]), 1)
        logs = list((self.root / "F1TeamRadioStudio" / "logs").glob("*.log"))
        self.assertEqual(len(logs), 1)
        text = logs[0].read_text(encoding="utf-8")
        self.assertIn("Traceback", text)
        self.assertIn("RuntimeError: startup test", text)
        self.assertIn(str(logs[0]), notify.call_args.args[1])

    def test_real_tk_callback_logs_and_keeps_event_loop_alive(self):
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        root.withdraw()
        self.addCleanup(root.destroy)
        runtime.install_tk_exception_handler(root)

        def fail():
            raise ValueError("callback test")

        with mock.patch("tkinter.messagebox.showerror") as showerror, mock.patch.object(sys, "stderr", None):
            root.after(0, fail)
            root.update()
        log = next(runtime.log_directory().glob("*.log"))
        self.assertIn("ValueError: callback test", log.read_text(encoding="utf-8"))
        self.assertIn(str(log), showerror.call_args.args[1])
        self.assertIs(showerror.call_args.kwargs["parent"], root)

    def test_uncaught_thread_exception_is_logged_without_console(self):
        runtime.install_exception_hooks()

        def fail():
            raise RuntimeError("worker test")

        with mock.patch.object(runtime, "_notify") as notify, mock.patch.object(sys, "stderr", None):
            thread = threading.Thread(target=fail)
            thread.start()
            thread.join()
        log = next(runtime.log_directory().glob("*.log"))
        self.assertIn("RuntimeError: worker test", log.read_text(encoding="utf-8"))
        self.assertIn(str(log), notify.call_args.args[1])

    def test_double_click_with_no_arguments_still_launches_gui(self):
        with mock.patch("teamradio.gui.main") as gui:
            self.assertEqual(launch_gui.main([]), 0)
        gui.assert_called_once_with()


class BundledFFmpegTests(unittest.TestCase):
    def test_explicit_override_wins_over_bundle_and_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ffmpeg").mkdir()
            (root / "ffmpeg" / "ffmpeg.exe").write_bytes(b"bundle")
            override = root / "custom.exe"
            override.write_bytes(b"explicit")
            with mock.patch.object(sys, "_MEIPASS", str(root), create=True), mock.patch.dict(os.environ, {"FFMPEG_BINARY": str(override)}):
                self.assertEqual(Path(media.ffmpeg_exe()), override.resolve())

    def test_bundle_wins_over_path_and_imageio_in_frozen_app(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ffmpeg").mkdir()
            binary = root / "ffmpeg" / "ffmpeg.exe"
            binary.write_bytes(b"bundle")
            with mock.patch.object(sys, "_MEIPASS", str(root), create=True), mock.patch.object(sys, "frozen", True, create=True), mock.patch.dict(os.environ, {"FFMPEG_BINARY": ""}), mock.patch.object(media.shutil, "which", return_value="PATH-ffmpeg") as which:
                self.assertEqual(Path(media.ffmpeg_exe()), binary.resolve())
            which.assert_not_called()

    def test_both_encoding_process_paths_hide_windows_console(self):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        fake = mock.MagicMock()
        fake.wait.return_value = 0
        fake.stdin.closed = True
        with mock.patch.object(media.subprocess, "Popen", return_value=fake) as popen:
            media._run(["ffmpeg", "-version"])
            media._stream_frames(["ffmpeg", "-version"], [], None)
        self.assertEqual(popen.call_count, 2)
        for call in popen.call_args_list:
            self.assertEqual(call.kwargs["creationflags"], flags)


class SelfTestTests(unittest.TestCase):
    def test_real_headless_self_test_report_without_tk_or_gui_import(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "中文报告" / "report.json"
            # A child interpreter also proves no preexisting GUI import masks
            # an accidental dependency of the headless entry point.
            command = [sys.executable, "-c",
                       "import sys; import launch_gui; code = launch_gui.main(sys.argv[1:]); "
                       "assert 'tkinter' not in sys.modules; "
                       "assert 'teamradio.gui' not in sys.modules; raise SystemExit(code)",
                       "--self-test", "--report", str(path)]
            result = subprocess.run(command, capture_output=True, timeout=90,
                                    **media.ffmpeg_process_options())
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace") + result.stdout.decode("utf-8", "replace"))
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertFalse(report["frozen"])
            self.assertEqual(report["version"], "1.0.0")
            self.assertTrue(Path(report["ffmpeg_path"]).is_file())
            self.assertTrue(all(item["ok"] for item in report["results"].values()))
            self.assertGreater(report["results"]["verify_mp4"]["frames"], 1)

    def test_failure_writes_json_and_log_with_nonzero_status_and_no_popup(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "failure.json"
            with mock.patch.dict(os.environ, {"LOCALAPPDATA": temporary, "FFMPEG_BINARY": "missing-release-ffmpeg-9898"}), mock.patch.object(runtime, "_notify") as notify, mock.patch.object(sys, "stdout", None):
                self.assertEqual(runtime.run_self_test(path), 1)
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse(report["ok"])
            self.assertFalse(report["results"]["ffmpeg"]["ok"])
            self.assertIn("FFMPEG_BINARY", report["error"])
            self.assertTrue(Path(report["log_path"]).is_file())
            notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
