"""Real Tk integration coverage for the optional dialogue editor."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import patch

from PIL import Image
from teamradio.gui import DIALOGUE_MODES, RESOLUTIONS, TeamRadioApp
from teamradio.renderer import RenderConfig


class GuiDialogueTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Tk display unavailable: {exc}")
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(args)
        self.app = TeamRadioApp(self.root)
        self.root.update()
        self.error_patch = patch("teamradio.gui.messagebox.showerror")
        self.showerror = self.error_patch.start()
        self.addCleanup(self.error_patch.stop)
        self.addCleanup(self.app.close)

    def editor_with_two_paragraphs(self):
        editor = self.app.open_dialogue_editor()
        self.root.update()
        self.assertIsInstance(editor, tk.Toplevel)
        editor.start_var.set("1")
        editor.end_var.set("9")
        editor.role_var.set("车手")
        editor.text.insert("1.0", '"First paragraph."\n"Second paragraph."')
        self.assertTrue(editor.add_message())
        self.root.update()
        return editor

    def test_editor_add_split_update_delete_and_audio_relative_seek(self):
        editor = self.editor_with_two_paragraphs()
        self.assertEqual([(item["start"], item["end"]) for item in self.app.dialogue_messages], [(1, 5), (5, 9)])
        self.assertEqual([item["text"] for item in self.app.dialogue_messages], ['"First paragraph."', '"Second paragraph."'])
        self.assertEqual(len(editor.tree.get_children()), 2)
        editor.tree.selection_set("0")
        editor._selected()
        editor.start_var.set("0")
        editor.end_var.set("4")
        editor.role_var.set("其他人")
        editor.text.delete("1.0", "end")
        editor.text.insert("1.0", '"Updated first paragraph."')
        self.assertTrue(editor.update_message())
        self.assertEqual(self.app.dialogue_messages[0]["speaker"], "other")
        self.app.vars["dialogue_mode"].set(DIALOGUE_MODES[1])
        self.app.vars["start_delay"].set("2")
        self.app._refresh_config()
        editor.tree.selection_set("1")
        editor.jump_to_selected()
        self.assertAlmostEqual(self.app.timeline.get(), self.app.audio_start + 5)
        self.assertTrue(editor.delete_message())
        self.assertEqual(len(self.app.dialogue_messages), 1)
        self.assertEqual(self.errors, [])

    def test_configuration_roundtrip_and_legacy_defaults(self):
        self.assertFalse(self.app.build_config().dialogue_enabled)
        self.assertEqual(self.app.build_config().dialogue_scroll_delay, 1.0)
        editor = self.editor_with_two_paragraphs()
        self.app.vars["dialogue_mode"].set(DIALOGUE_MODES[1])
        self.app.vars["dialogue_expand"].set("0.6")
        self.app.vars["dialogue_scroll"].set("0.8")
        self.app.vars["dialogue_scroll_delay"].set("1.7")
        self.app.vars["dialogue_font_size"].set("28")
        self.app.vars["resolution"].set("1080 × 1920")
        self.app.vars["format"].set("WEBM")
        self.app.vars["fps"].set("20")
        expected = asdict(self.app.build_config())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            self.app.write_config(path)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["dialogue"], expected["dialogue"])
            self.assertIsInstance(saved["dialogue_enabled"], bool)
            self.app.dialogue_messages.clear()
            self.app.read_config(path)
            self.assertEqual(asdict(self.app.build_config()), expected)
            self.assertEqual(self.app.vars["format"].get(), "WEBM")
            self.assertEqual(len(editor.tree.get_children()), 2)
            self.app.vars["dialogue_mode"].set(DIALOGUE_MODES[0])
            disabled = self.app.build_config()
            self.assertFalse(disabled.dialogue_enabled)
            self.assertEqual(disabled.dialogue, expected["dialogue"])
            disabled.dialogue[0]["text"] = '"Snapshot change"'
            self.assertNotEqual(disabled.dialogue, self.app.dialogue_messages)
            legacy = asdict(RenderConfig())
            for key in tuple(legacy):
                if key.startswith("dialogue"):
                    del legacy[key]
            path.write_text(json.dumps(legacy), encoding="utf-8")
            self.app.read_config(path)
            config = self.app.build_config()
            self.assertFalse(config.dialogue_enabled)
            self.assertEqual(config.dialogue, [])
            self.assertEqual(config.dialogue_scroll_delay, 1.0)
            self.assertEqual((config.dialogue_expand, config.dialogue_scroll, config.dialogue_font_size), (.35, .45, 26))
        self.assertIn("720 × 1280", RESOLUTIONS)
        self.assertEqual(self.errors, [])

    def test_invalid_edits_and_import_are_atomic_with_chinese_feedback(self):
        editor = self.editor_with_two_paragraphs()
        expected = deepcopy(self.app.dialogue_messages)
        editor.clear_fields()
        for start, end, text in (("10", "12", "Unquoted text"), ("10", "12", ""),
                                  ("nan", "12", '"Text"'), ("-1", "3", '"Text"'),
                                  ("2", "3", '"Overlapping"')):
            editor.start_var.set(start)
            editor.end_var.set(end)
            editor.text.delete("1.0", "end")
            editor.text.insert("1.0", text)
            self.assertFalse(editor.add_message())
            self.assertEqual(self.app.dialogue_messages, expected)
            self.assertTrue(editor.note.get().startswith("请检查对话："))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"dialogue": "invalid"}', encoding="utf-8")
            self.assertFalse(editor.import_json(path))
            self.assertEqual(self.app.dialogue_messages, expected)
        self.assertGreaterEqual(self.showerror.call_count, 6)
        self.assertEqual(self.errors, [])

    def test_relative_audio_path_is_based_on_config_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            audio=root/'voice.wav';audio.write_bytes(b'placeholder')
            config=asdict(RenderConfig())
            config['_gui']={'audio_path':'voice.wav'}
            path=root/'relative.json';path.write_text(json.dumps(config),encoding='utf-8')
            with patch.object(self.app,'load_audio') as load:
                self.app.read_config(path)
                load.assert_called_once_with(audio.resolve())

    def test_json_list_import_export(self):
        editor = self.editor_with_two_paragraphs()
        expected = deepcopy(self.app.dialogue_messages)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dialogue.json"
            self.assertTrue(editor.export_json(path))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), expected)
            self.app.dialogue_messages = []
            self.assertTrue(editor.import_json(path))
            self.assertEqual(self.app.dialogue_messages, expected)
        self.assertEqual(self.errors, [])

    def test_wheel_scrolls_without_mutating_main_or_editor_values(self):
        editor = self.editor_with_two_paragraphs()
        expected_vars = {key: value.get() for key, value in self.app.vars.items()}
        pending, widgets = [self.app.settings_canvas], []
        while pending:
            widget = pending.pop()
            if isinstance(widget, (ttk.Combobox, ttk.Spinbox)):
                widgets.append(widget)
            pending.extend(widget.winfo_children())
        self.app.settings_canvas.yview_moveto(0)
        before_scroll = self.app.settings_canvas.yview()[0]
        widgets[0].event_generate("<MouseWheel>", delta=-120)
        self.root.update()
        self.assertGreater(self.app.settings_canvas.yview()[0], before_scroll)
        for widget in widgets:
            for delta in (-120, 120):
                widget.event_generate("<MouseWheel>", delta=delta)
                widget.event_generate("<Shift-MouseWheel>", delta=delta)
        self.assertEqual({key: value.get() for key, value in self.app.vars.items()}, expected_vars)
        fields = (editor.start_spin, editor.end_spin, editor.role_combo, *editor.option_spins)
        expected_fields = [widget.get() for widget in fields]
        for widget in fields:
            for delta in (-120, 120):
                widget.event_generate("<MouseWheel>", delta=delta)
                widget.event_generate("<Shift-MouseWheel>", delta=delta)
        self.root.update()
        self.assertEqual([widget.get() for widget in fields], expected_fields)
        self.assertEqual({key: value.get() for key, value in self.app.vars.items()}, expected_vars)
        self.assertEqual(self.errors, [])

    def test_posted_combobox_wheel_keeps_native_scrolling_without_callback_errors(self):
        editor = self.editor_with_two_paragraphs()
        expected = {key: value.get() for key, value in self.app.vars.items()}
        for combo in (self.app.driver_combo, self.app.team_combo, editor.role_combo):
            with self.subTest(combo=str(combo)):
                combo.winfo_toplevel().lift()
                self.root.update()
                self.root.tk.call("ttk::combobox::Post", str(combo))
                try:
                    self.root.update()
                    popdown = str(self.root.tk.call("ttk::combobox::PopdownWindow", str(combo)))
                    listbox = popdown + ".f.l"
                    x = int(self.root.tk.call("winfo", "rootx", listbox)) + 12
                    y = int(self.root.tk.call("winfo", "rooty", listbox)) + 12
                    # This real Tcl widget is deliberately absent from Tkinter's
                    # children map, reproducing the original KeyError: popdown.
                    self.assertEqual(str(self.root.tk.call("winfo", "containing", x, y)), listbox)
                    settings_before = self.app.settings_canvas.yview()
                    selection_before = combo.get()
                    view_before = self.root.tk.call(listbox, "yview")
                    for _ in range(3):
                        self.root.tk.call("event", "generate", listbox, "<MouseWheel>",
                                          "-delta", -120, "-rootx", x, "-rooty", y, "-x", 12, "-y", 12)
                        self.root.update()
                    if combo is self.app.driver_combo:
                        self.assertGreater(float(self.root.tk.call(listbox, "yview")[0]), float(view_before[0]))
                    self.assertEqual(combo.get(), selection_before)
                    self.assertEqual(self.app.settings_canvas.yview(), settings_before)
                    self.assertEqual(self.errors, [])
                finally:
                    self.root.tk.call("ttk::combobox::Unpost", str(combo))
                    self.root.update()
        self.assertEqual({key: value.get() for key, value in self.app.vars.items()}, expected)
        self.showerror.assert_not_called()

    def test_duration_uses_audio_and_only_enabled_messages_extend_output(self):
        self.editor_with_two_paragraphs()
        self.app.audio_duration = 1.25
        self.app.vars["dialogue_mode"].set(DIALOGUE_MODES[1])
        self.app._refresh_config()
        self.assertAlmostEqual(self.app.total_duration, self.app.audio_start + 9 + self.app.config.hold + self.app.config.fade_out)
        calls = []
        class RecordingCard:
            def frame(card, t, audio_start, duration, levels):
                calls.append((t, audio_start, duration, levels))
                return Image.new("RGBA", (32, 32))
        self.app._card = RecordingCard()
        self.app.timeline.set(self.app.audio_start + 8)
        self.app._render_preview()
        self.assertEqual(calls[-1][2], 1.25)
        self.assertTrue(all(value == 0 for value in calls[-1][3]))
        self.assertEqual(self.app.audio_duration, 1.25)
        self.app.analyzer = type("FinishedAudio", (), {"close": lambda _self: None})()
        self.app._playing = self.app._audio_started = True
        self.app._clock_origin = 0
        with patch("teamradio.gui.time.monotonic", return_value=self.app.audio_start + 8), patch.object(self.app, "_stop_sound") as stop:
            self.app._tick()
            stop.assert_called_once()
            self.assertTrue(self.app._playing)  # Dialogue continues after sound ends.
        self.app._pause()
        self.app.analyzer = None
        self.app.vars["dialogue_mode"].set(DIALOGUE_MODES[0])
        self.app._refresh_config()
        self.assertAlmostEqual(self.app.total_duration, self.app.audio_start + 1.25 + self.app.config.hold + self.app.config.fade_out)
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
