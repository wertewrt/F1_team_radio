"""Bounded-memory audio analysis and transactional FFmpeg exports.

Analysis is deliberately separate from muxing: the 16 kHz mono analysis copy is
never used as the exported soundtrack. All encoders receive the original audio.
"""
from __future__ import annotations

from concurrent.futures import CancelledError as _CancelledError
from io import BytesIO
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile

import numpy as np
from PIL import Image, ImageColor


class CancelledError(_CancelledError):
    """An analysis or export was cancelled; its destination was not replaced."""


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise CancelledError("Operation cancelled")


def ffmpeg_exe() -> str:
    """Find FFmpeg without requiring ffprobe or modifying PATH."""
    configured = os.environ.get("FFMPEG_BINARY", "").strip()
    if configured:
        candidate = shutil.which(configured)
        if candidate:
            return candidate
        path = Path(configured).expanduser()
        if path.is_file():
            return str(path.resolve())
        raise FileNotFoundError(f"FFMPEG_BINARY does not name an executable: {configured}")
    # The release supplies a known binary; never let PATH shadow it.
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    for relative in ("ffmpeg/ffmpeg.exe", "bin/ffmpeg.exe", "ffmpeg.exe"):
        bundled = root / relative
        if bundled.is_file():
            return str(bundled.resolve())
    if getattr(sys, "frozen", False):
        bundled = sorted((root / "imageio_ffmpeg" / "binaries").glob("ffmpeg*.exe"))
        if bundled:
            return str(bundled[0].resolve())
    candidate = shutil.which("ffmpeg")
    if candidate:
        return candidate
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError, OSError) as exc:
        raise RuntimeError("FFmpeg is unavailable. Install imageio-ffmpeg or set FFMPEG_BINARY.") from exc


def ffmpeg_process_options():
    """Keep FFmpeg invisible in Windows GUI builds and normal on other OSes."""
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}


def _error_text(log):
    log.flush()
    log.seek(0, os.SEEK_END)
    size = log.tell()
    log.seek(max(0, size - 16384))
    return log.read().decode("utf-8", "replace").strip()


def _stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _wait(process, log, cancel):
    try:
        while True:
            _check_cancel(cancel)
            try:
                code = process.wait(timeout=0.1)
                break
            except subprocess.TimeoutExpired:
                pass
        _check_cancel(cancel)
        if code:
            raise RuntimeError(f"FFmpeg failed (exit {code}): {_error_text(log)}")
    except BaseException:
        _stop(process)
        raise


def _run(args, cancel=None):
    _check_cancel(cancel)
    with tempfile.TemporaryFile() as log:
        process = subprocess.Popen(args, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=log, **ffmpeg_process_options())
        _wait(process, log, cancel)


def _base_ffmpeg():
    return [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]


class AudioAnalyzer:
    """Audio duration and smoothly animated 9-element float32 bar vectors.

    Decoded PCM and frame features live in temporary files, not Python lists.
    Only the current 80 ms audio window is processed at a time. Call close(), or use a context
    manager, to release the mappings and delete those files (also on Windows).
    """
    sample_rate = 16000
    bands = 9

    def __init__(self, path, fps=30, gain=1, cancel=None):
        self._temp = None
        self._pcm = None
        self._features = None
        self._closed = False
        self.duration = 0.0
        self.path = Path(path).expanduser().resolve()
        self.fps = float(fps)
        self.gain = float(gain)
        if not math.isfinite(self.fps) or self.fps <= 0:
            raise ValueError("fps must be a finite positive number")
        if not math.isfinite(self.gain) or self.gain < 0:
            raise ValueError("gain must be a finite nonnegative number")
        _check_cancel(cancel)
        if not self.path.is_file():
            raise FileNotFoundError(f"Audio file not found: {self.path}")
        if self.path.stat().st_size == 0:
            raise ValueError("Audio file is empty")
        self._temp = tempfile.TemporaryDirectory(prefix="teamradio-audio-")
        try:
            pcm_path = Path(self._temp.name) / "audio.f32"
            _run(_base_ffmpeg() + ["-i", str(self.path), "-map", "0:a:0",
                 "-vn", "-ac", "1", "-ar", str(self.sample_rate),
                 "-c:a", "pcm_f32le", "-f", "f32le", str(pcm_path)], cancel)
            samples = pcm_path.stat().st_size // 4
            if not samples:
                raise ValueError("Audio file contains no decodable audio samples")
            self.duration = samples / self.sample_rate
            self._pcm = np.memmap(pcm_path, dtype="<f4", mode="r", shape=(samples,))
            self._frame_count = max(1, math.ceil(self.duration * self.fps))
            self._features = np.memmap(Path(self._temp.name) / "features.f32",
                                      dtype="float32", mode="w+",
                                      shape=(self._frame_count, self.bands))
            self._analyze(cancel)
        except BaseException:
            self.close()
            raise

    def _analyze(self, cancel):
        # All nine blocks read the SAME current audio window. Their indices are
        # fixed frequency regions, never successive samples of a moving history.
        window_size = round(.080 * self.sample_rate)
        hann = np.hanning(window_size).astype(np.float32)
        frequencies = np.fft.rfftfreq(window_size, 1 / self.sample_rate)
        boundaries = np.array([70, 140, 240, 400, 650, 1050, 1700, 2800, 4500, 7600])
        regions = [(frequencies >= lo) & (frequencies < hi)
                   for lo, hi in zip(boundaries[:-1], boundaries[1:])]
        # A stable central cluster matches the references. Positive edge weights
        # keep small, sound-driven protrusions beneath both outer ends/logos.
        # A broader left shoulder and a quicker right falloff avoid mirrored
        # sides; simultaneous spectrum measurements still drive every block.
        envelope = np.array([.045, .12, .33, .88, 1., .64, .21, .065, .025], dtype=np.float32)
        previous = np.zeros(self.bands, dtype=np.float32)
        attack = 1 - math.exp(-1 / (self.fps * .025))
        release = 1 - math.exp(-1 / (self.fps * .090))
        quiet_seconds = 0.
        for frame in range(self._frame_count):
            _check_cancel(cancel)
            end = min(len(self._pcm), round(frame * self.sample_rate / self.fps))
            start = end - window_size
            data = np.zeros(window_size, dtype=np.float32)
            lo = max(0, start)
            if end > lo:
                data[lo - start:] = self._pcm[lo:end]
            np.nan_to_num(data, copy=False, nan=0, posinf=0, neginf=0)
            rms = float(np.sqrt(np.mean(data ** 2)))
            quiet_seconds = quiet_seconds + 1 / self.fps if rms < 1e-6 else 0.
            strength = math.sqrt(min(1., rms * self.gain * 3.5))
            spectrum = np.abs(np.fft.rfft(data * hann)) ** 2
            powers = np.array([float(np.mean(spectrum[region])) if region.any() else 0.
                               for region in regions], dtype=np.float32)
            peak = float(powers.max())
            detail = np.sqrt(powers / peak) if peak > 1e-12 else np.zeros(self.bands, dtype=np.float32)
            # Loudness moves the whole central group at once; spectrum changes
            # its local contour without making a syllable travel horizontally.
            target = strength * envelope * (.62 + .38 * detail)
            rate = np.where(target > previous, attack, release)
            previous += (target - previous) * rate
            gate = max(0., 1 - quiet_seconds / .160)
            if gate == 0 or self.gain == 0:
                previous.fill(0)
            self._features[frame] = previous * gate
        self._features.flush()

    def levels_at(self, seconds):
        if self._closed:
            raise RuntimeError("AudioAnalyzer is closed")
        seconds = float(seconds)
        if not math.isfinite(seconds) or seconds < 0 or seconds >= self.duration:
            return np.zeros(self.bands, dtype=np.float32)
        position = seconds * self.fps
        left = min(int(position), self._frame_count - 1)
        right = min(left + 1, self._frame_count - 1)
        fraction = position - left
        return np.asarray(self._features[left] * (1 - fraction) +
                          self._features[right] * fraction, dtype=np.float32).copy()

    def close(self):
        if self._closed:
            return
        self._closed = True
        for name in ("_features", "_pcm"):
            mapping = getattr(self, name, None)
            if mapping is not None:
                mapping._mmap.close()
                setattr(self, name, None)
        if self._temp is not None:
            self._temp.cleanup()
            self._temp = None

    def __enter__(self):
        if self._closed:
            raise RuntimeError("AudioAnalyzer is closed")
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


def _same_file(first, second):
    if first == second:
        return True
    try:
        return first.exists() and second.exists() and os.path.samefile(first, second)
    except OSError:
        return False


def _flatten(frame, color):
    canvas = Image.new("RGBA", frame.size, ImageColor.getrgb(color))
    return Image.alpha_composite(canvas, frame).convert("RGB")


def _audio_filter(audio_start, total):
    # Decimal milliseconds avoid rounding an entrance to a whole video frame.
    return (f"asetpts=PTS-STARTPTS,adelay={audio_start * 1000:.6f}:all=1,"
            f"apad,atrim=duration={total:.9f}")


def _stream_frames(args, frames, cancel):
    with tempfile.TemporaryFile() as log:
        _check_cancel(cancel)
        process = subprocess.Popen(args, stdin=subprocess.PIPE,
                                   stdout=subprocess.DEVNULL, stderr=log, **ffmpeg_process_options())
        finished = threading.Event()

        def interrupt_on_cancel():
            # A full OS pipe can block write(); terminate the encoder from a
            # watcher so cancellation still interrupts that blocked write.
            while not finished.wait(.1):
                if cancel.is_set():
                    try:
                        if process.poll() is None:
                            process.terminate()
                    except OSError:
                        pass
                    return

        watcher = None
        if cancel is not None:
            watcher = threading.Thread(target=interrupt_on_cancel, daemon=True)
            watcher.start()
        try:
            for frame in frames:
                _check_cancel(cancel)
                try:
                    process.stdin.write(frame.tobytes())
                except (BrokenPipeError, OSError) as exc:
                    _stop(process)
                    _check_cancel(cancel)
                    raise RuntimeError(f"FFmpeg stopped while receiving frames: {_error_text(log)}") from exc
            try:
                process.stdin.close()
            except (BrokenPipeError, OSError) as exc:
                _stop(process)
                _check_cancel(cancel)
                raise RuntimeError(f"FFmpeg stopped while finishing frames: {_error_text(log)}") from exc
            _wait(process, log, cancel)
        except BaseException:
            _stop(process)
            if not process.stdin.closed:
                try:
                    process.stdin.close()
                except OSError:
                    pass
            raise
        finally:
            finished.set()
            if watcher is not None:
                watcher.join()


def export_video(audio_path, output_path, config, progress=None, cancel=None) -> Path:
    """Render a complete clip; atomically publish only a successful export.

    Supported suffixes: mp4, mov (ProRes 4444), webm (VP9 alpha), mkv,
    avi, gif and zip (RGBA PNGs + delayed PCM soundtrack + timing metadata).
    GIF supports binary transparency and has no soundtrack by format design.
    """
    from .renderer import CardRenderer

    _check_cancel(cancel)
    config.validate()
    source = Path(audio_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    extension = destination.suffix.lower()
    if extension not in {".mp4", ".mov", ".webm", ".mkv", ".avi", ".gif", ".zip"}:
        raise ValueError(f"Unsupported export format: {extension or '(no extension)'}")
    project_root = Path(__file__).resolve().parent.parent
    for folder in ("resource", "assets", "teamradio"):
        if destination.is_relative_to((project_root / folder).resolve()):
            raise ValueError("Output must not overwrite bundled source, reference or logo assets")
    protected = [source]
    if getattr(config, "logo_path", None):
        protected.append(Path(config.logo_path).expanduser().resolve())
    if any(_same_file(destination, item) for item in protected):
        raise ValueError("Output must not overwrite the source audio or logo asset")
    if destination.exists() and not destination.is_file():
        raise ValueError("Output path is not a regular file")
    destination.parent.mkdir(parents=True, exist_ok=True)

    def report(value, message):
        _check_cancel(cancel)
        if progress is not None:
            progress(value, message)

    report(0., "Analyzing audio")
    with AudioAnalyzer(source, fps=config.fps, gain=config.gain, cancel=cancel) as audio:
        audio_start = float(config.start_delay + config.entrance)
        total = audio_start + config.content_duration(audio.duration) + config.hold + config.fade_out
        count = max(1, math.ceil(total * config.fps))
        renderer = CardRenderer(config)
        zeros = np.zeros(9, dtype=np.float32)
        alpha = extension in {".mov", ".webm", ".zip", ".gif"}
        mode = "RGBA" if alpha else "RGB"
        report(.12, "Rendering frames")

        def frames():
            for index in range(count):
                _check_cancel(cancel)
                t = index / config.fps
                relative = t - audio_start
                levels = audio.levels_at(relative) if 0 <= relative < audio.duration else zeros
                image = renderer.frame(t, audio_start, audio.duration, levels).convert("RGBA")
                if image.size != (config.width, config.height):
                    raise ValueError("Renderer returned an incorrect canvas size")
                if not alpha:
                    image = _flatten(image, config.background_color)
                if index % max(1, round(config.fps / 5)) == 0:
                    report(.12 + .76 * index / count, f"Rendering frame {index + 1}/{count}")
                yield image

        with tempfile.TemporaryDirectory(prefix=".teamradio-", dir=destination.parent) as temporary:
            temp = Path(temporary)
            target = temp / ("export" + extension)
            if extension == ".zip":
                soundtrack = temp / "soundtrack.wav"
                report(.12, "Preparing delayed lossless soundtrack")
                _run(_base_ffmpeg() + ["-i", str(source), "-map", "0:a:0", "-vn",
                     "-af", _audio_filter(audio_start, total), "-c:a", "pcm_s16le",
                     "-rf64", "auto", str(soundtrack)], cancel)
                with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
                    for index, image in enumerate(frames()):
                        buffer = BytesIO()
                        image.save(buffer, format="PNG")
                        archive.writestr(f"frames/{index:08d}.png", buffer.getvalue())
                    _check_cancel(cancel)
                    archive.write(soundtrack, "soundtrack.wav")
                    archive.writestr("metadata.json", json.dumps({
                        "version": 1, "fps": config.fps, "width": config.width,
                        "height": config.height, "frame_count": count,
                        "duration": total, "video_duration": count / config.fps,
                        "audio_start": audio_start, "audio_duration": audio.duration,
                        "start_delay": config.start_delay, "entrance": config.entrance,
                        "hold": config.hold, "fade_out": config.fade_out,
                        "frames": "frames/%08d.png", "soundtrack": "soundtrack.wav",
                        "soundtrack_start": 0, "alpha": True,
                        "dialogue_enabled": config.dialogue_enabled,
                        "dialogue": config.dialogue if config.dialogue_enabled else [],
                    }, indent=2))
            else:
                raw = _base_ffmpeg() + ["-f", "rawvideo", "-pix_fmt", mode.lower(),
                       "-s:v", f"{config.width}x{config.height}", "-r", str(config.fps), "-i", "pipe:0"]
                # FFmpeg names packed RGB pixels rgb24, not rgb.
                raw[raw.index("-pix_fmt") + 1] = "rgba" if alpha else "rgb24"
                if extension == ".gif":
                    intermediate = temp / "frames.mkv"
                    _stream_frames(raw + ["-an", "-c:v", "ffv1", "-pix_fmt", "bgra",
                                   "-threads", "2", str(intermediate)], frames(), cancel)
                    report(.9, "Building GIF palette")
                    palette = temp / "palette.png"
                    _run(_base_ffmpeg() + ["-i", str(intermediate), "-vf",
                         "palettegen=reserve_transparent=1:stats_mode=diff", "-frames:v", "1",
                         "-threads", "1", str(palette)], cancel)
                    report(.94, "Encoding GIF")
                    _run(_base_ffmpeg() + ["-i", str(intermediate), "-i", str(palette),
                         "-lavfi", "paletteuse=dither=sierra2_4a:alpha_threshold=128",
                         "-t", f"{total:.9f}", "-loop", "0", str(target)], cancel)
                else:
                    codecs = {
                        ".mp4": ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"],
                        ".mov": ["-c:v", "prores_ks", "-profile:v", "4", "-pix_fmt", "yuva444p10le", "-c:a", "pcm_s16le"],
                        ".webm": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-crf", "25", "-b:v", "0", "-c:a", "libopus", "-b:a", "192k"],
                        ".mkv": ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"],
                        ".avi": ["-c:v", "mpeg4", "-q:v", "3", "-pix_fmt", "yuv420p", "-c:a", "pcm_s16le"],
                    }
                    args = raw + ["-i", str(source), "-map", "0:v:0", "-map", "1:a:0",
                           "-af", _audio_filter(audio_start, total), "-t", f"{total:.9f}",
                           "-threads", "2"] + codecs[extension] + [str(target)]
                    _stream_frames(args, frames(), cancel)
            report(.99, "Finalizing export")
            if not target.is_file() or not target.stat().st_size:
                raise RuntimeError("FFmpeg produced an empty export")
            _check_cancel(cancel)
            os.replace(target, destination)
    # Once committed, a late cancellation cannot undo a completed export.
    if progress is not None:
        progress(1., "Export complete")
    return destination
