"""Small desktop error hooks and a real, headless release smoke test.

Nothing here creates a window, changes hooks or starts a process at import time.
"""
from __future__ import annotations

from datetime import datetime
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
import traceback


def log_directory():
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / "AppData" / "Local") / "F1TeamRadioStudio" / "logs"


def log_exception(exc_type, value, tb):
    directory = log_directory()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"studio-{datetime.now():%Y-%m-%d}-{os.getpid()}.log"
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"\n[{datetime.now().isoformat(timespec='seconds')}] frozen={bool(getattr(sys, 'frozen', False))}\n")
        traceback.print_exception(exc_type, value, tb, file=stream)
    return path


def _notify(title, message, parent=None):
    if parent is not None:
        from tkinter import messagebox
        messagebox.showerror(title, message, parent=parent)
    elif sys.platform == "win32":
        # Startup/import failures may occur before Tk itself can be loaded.
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    elif sys.stderr is not None:
        print(f"{title}: {message}", file=sys.stderr)


def report_exception(exc_type, value, tb, *, title="Team Radio Studio 运行异常", parent=None):
    try:
        path = log_exception(exc_type, value, tb)
        detail = f"详细日志已保存至：\n{path}"
    except OSError as error:
        detail = f"无法写入日志目录 {log_directory()}：{error}"
    if sys.stderr is not None:
        traceback.print_exception(exc_type, value, tb, file=sys.stderr)
    try:
        _notify(title, f"{value}\n\n{detail}", parent)
    except Exception:
        # A broken/destroyed Tk interpreter must not hide the original failure.
        if sys.platform == "win32":
            _notify(title, f"{value}\n\n{detail}")


def install_exception_hooks():
    def uncaught(exc_type, value, tb):
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            if sys.stderr is not None:
                sys.__excepthook__(exc_type, value, tb)
            return
        report_exception(exc_type, value, tb)

    sys.excepthook = uncaught

    def thread_uncaught(args):
        if args.exc_type is not SystemExit:
            uncaught(args.exc_type, args.exc_value, args.exc_traceback)

    threading.excepthook = thread_uncaught


def install_tk_exception_handler(root):
    def callback(exc_type, value, tb):
        report_exception(exc_type, value, tb, title="界面操作发生异常", parent=root)
    root.report_callback_exception = callback


def run_self_test(report_path=None):
    """Exercise bundled assets, analysis, rendering, encoding and full decoding.

    Return a process exit status. Reports survive temporary test-file cleanup.
    This path deliberately never imports gui or initializes Tk.
    """
    from . import __version__

    report = {
        "version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable, "python": sys.version,
        "resource_root": str(Path(__file__).resolve().parent.parent / "assets"),
        "ffmpeg_path": None, "results": {}, "ok": False,
    }
    stage = "imports"
    try:
        import wave
        import numpy as np
        from PIL import Image, ImageFont
        from . import media, presets
        from .renderer import CardRenderer, RenderConfig

        report["results"][stage] = {"ok": True}
        stage = "resources"
        required = ["background/reference_panel.png", "lettering/lettering.json",
                    "numerals/contours.json", "fonts/RadioRounded-Bold.ttf",
                    "fonts/RadioRounded-Radio.ttf", "fonts/DejaVuSans-Bold.ttf"]
        required += [f"logos/{team}_{variant}.png" for team in presets.TEAMS
                     for variant in ("color", "white")]
        files = [{"path": str(presets.ASSETS / name),
                  "ok": (presets.ASSETS / name).is_file()} for name in required]
        report["results"][stage] = {"ok": False, "files": files}
        for item in files:
            if not item["ok"]:
                raise FileNotFoundError(f"Missing bundled resource: {item['path']}")
            path = Path(item["path"])
            if path.suffix == ".png":
                with Image.open(path) as image:
                    image.verify()
            elif path.suffix == ".ttf":
                ImageFont.truetype(str(path), 24)
            else:
                json.loads(path.read_text(encoding="utf-8"))
        report["results"][stage]["ok"] = True

        stage = "ffmpeg"
        report["ffmpeg_path"] = media.ffmpeg_exe()
        media._run([report["ffmpeg_path"], "-version"])
        report["results"][stage] = {"ok": True}
        with tempfile.TemporaryDirectory(prefix="teamradio-self-test-") as temporary:
            root = Path(temporary)
            source = root / "synthetic-voice.wav"
            rate = 16000
            t = np.arange(rate, dtype=np.float64) / rate
            # Deterministic voiced harmonics with changing pitch and syllables;
            # no speech service, network, fixture or optional TTS package.
            pitch = 135 + 25 * np.sin(2 * np.pi * 2 * t)
            phase = 2 * np.pi * np.cumsum(pitch) / rate
            envelope = np.sin(np.pi * t) ** 2 * (.25 + .75 * np.sin(2 * np.pi * 3 * t) ** 2)
            signal = envelope * sum(np.sin(h * phase) / h for h in range(1, 7)) * .25
            with wave.open(str(source), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(rate)
                audio.writeframes((signal * 32767).astype("<i2").tobytes())
            stage = "audio_analysis"
            with media.AudioAnalyzer(source, fps=10) as analyzer:
                levels = analyzer.levels_at(.45)
                if abs(analyzer.duration - 1) > .01 or levels.shape != (9,) or not np.isfinite(levels).all() or levels.max() <= 0:
                    raise RuntimeError("Synthetic voice analysis returned invalid duration or levels")
                report["results"][stage] = {"ok": True, "duration": analyzer.duration, "levels": levels.tolist()}

            stage = "render"
            for driver in presets.DRIVERS:
                config = RenderConfig(driver=driver, width=480, height=270, fps=10,
                                      entrance=.1, fade_out=.1, hold=0)
                frame = CardRenderer(config).frame(.55, .1, 1., levels)
                if frame.size != (480, 270) or not frame.getbbox():
                    raise RuntimeError(f"Invalid rendered frame: {driver}")
            config = RenderConfig(width=480, height=270, fps=10, entrance=.1,
                                  fade_out=.1, hold=0, dialogue_enabled=True,
                                  dialogue=[{"start": 0., "end": 1., "speaker": "driver", "text": '"Radio check."'}])
            CardRenderer(config).frame(.55, .1, 1., levels).save(root / "preview.png")
            report["results"][stage] = {"ok": True, "drivers": len(presets.DRIVERS), "size": [480, 270], "dialogue": True}

            stage = "export_mp4"
            output = media.export_video(source, root / "smoke.mp4", config)
            size = output.stat().st_size
            if size < 1024:
                raise RuntimeError("Export is unexpectedly small")
            report["results"][stage] = {"ok": True, "bytes": size}

            stage = "verify_mp4"
            decoded = root / "decoded.rgb"
            media._run(media._base_ffmpeg() + ["-xerror", "-i", str(output), "-map", "0:v:0",
                       "-an", "-pix_fmt", "rgb24", "-f", "rawvideo", str(decoded)])
            expected = math.ceil(round(config.entrance + 1 + config.fade_out, 9) * config.fps)
            frame_bytes = config.width * config.height * 3
            if decoded.stat().st_size != expected * frame_bytes:
                raise RuntimeError("Decoded MP4 frame count or dimensions differ from the export")
            # AudioAnalyzer decodes the exported AAC track, rather than only
            # inspecting a container header or trusting a nonempty file.
            with media.AudioAnalyzer(output, fps=10) as decoded_audio:
                if abs(decoded_audio.duration - expected / config.fps) > .15 or decoded_audio.levels_at(.55).max() <= 0:
                    raise RuntimeError("Exported MP4 audio is silent or has an incorrect duration")
                duration = decoded_audio.duration
            report["results"][stage] = {"ok": True, "frames": expected, "audio_duration": duration}
        report["ok"] = True
    except Exception as exc:
        report["results"].setdefault(stage, {})["ok"] = False
        report["error"] = f"{type(exc).__name__}: {exc}"
        try:
            report["log_path"] = str(log_exception(type(exc), exc, exc.__traceback__))
        except OSError as log_error:
            report["log_error"] = str(log_error)

    return _write_report(report, report_path, "self-test.json")


def _write_report(report, report_path, default_name):
    try:
        path = Path(report_path).expanduser().resolve() if report_path else log_directory() / default_name
        report["report_path"] = str(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        report["ok"] = False
        report["report_error"] = str(exc)
        try:
            log_exception(type(exc), exc, exc.__traceback__)
        except OSError:
            pass
    if sys.stdout is not None:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["ok"] else 1


def run_gui_smoke_test(report_path=None):
    """Open the real Tk studio/editor, exercise them, then close automatically."""
    from . import __version__
    report = {"version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
              "executable": sys.executable, "mode": "gui-smoke-test",
              "resource_root": str(Path(__file__).resolve().parent.parent / "assets"),
              "ffmpeg_path": None, "results": {}, "ok": False}
    root = app = None
    stage = "gui_startup"
    try:
        from dataclasses import asdict
        from . import gui, media
        gui._enable_high_dpi()
        root = gui.tk.Tk()
        callback_errors = []

        def callback_error(exc_type, value, tb):
            callback_errors.append(value)
            log_exception(exc_type, value, tb)

        root.report_callback_exception = callback_error
        app = gui.TeamRadioApp(root)
        root.update()
        if app._photo is None:
            raise RuntimeError("Studio preview did not render")
        report["results"][stage] = {"ok": True, "tk": str(root.tk.call("info", "patchlevel"))}
        report["ffmpeg_path"] = media.ffmpeg_exe()
        stage = "dialogue_editor"
        editor = app.open_dialogue_editor()
        root.update()
        editor.start_var.set("0")
        editor.end_var.set("1")
        editor.text.insert("1.0", '"Packaged radio check."')
        if not editor.add_message():
            raise RuntimeError("Dialogue editor did not accept a message")
        app.vars["dialogue_mode"].set(gui.DIALOGUE_MODES[1])
        app._refresh_config()
        app.timeline.set(app.audio_start + .5)
        app._render_preview()
        root.update()
        report["results"][stage] = {"ok": True, "messages": len(app.dialogue_messages)}
        stage = "configuration_roundtrip"
        expected = asdict(app.build_config())
        with tempfile.TemporaryDirectory(prefix="teamradio-gui-smoke-") as temporary:
            path = Path(temporary) / "config.json"
            app.write_config(path)
            app.read_config(path)
        if asdict(app.build_config()) != expected:
            raise RuntimeError("GUI configuration did not roundtrip")
        editor.finish()
        root.update()
        if callback_errors:
            raise RuntimeError(f"Tk callback failed: {callback_errors[0]}")
        report["results"][stage] = {"ok": True}
        stage = "gui_close"
        app.close()
        if not app._closed or app._temp_dir.exists():
            raise RuntimeError("GUI did not release preview resources")
        root = app = None
        report["results"][stage] = {"ok": True}
        report["ok"] = True
    except Exception as exc:
        report["results"][stage] = {"ok": False}
        report["error"] = f"{type(exc).__name__}: {exc}"
        try:
            report["log_path"] = str(log_exception(type(exc), exc, exc.__traceback__))
        except OSError as log_error:
            report["log_error"] = str(log_error)
    finally:
        if app is not None:
            app.close()
        elif root is not None:
            root.destroy()
    return _write_report(report, report_path, "gui-smoke-test.json")
