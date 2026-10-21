"""Real FFmpeg integration tests; no ffprobe or downloaded fixtures required.

Run: python -m unittest discover -s tests -p test_media.py -v
"""
from __future__ import annotations

from io import BytesIO
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock
import wave
import zipfile

import numpy as np
from PIL import Image

from teamradio.media import AudioAnalyzer, CancelledError, export_video, ffmpeg_exe


def write_wave(path, samples, rate=16000):
    samples = np.asarray(samples)
    channels = 1 if samples.ndim == 1 else samples.shape[1]
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(2)
        stream.setframerate(rate)
        stream.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())


def ffmpeg_call(*args):
    result = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", *map(str, args)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=40)
    if result.returncode:
        raise AssertionError(result.stderr.decode("utf-8", "replace"))
    return result.stdout


class FFmpegResolutionTests(unittest.TestCase):
    def test_explicit_invalid_binary_has_useful_error(self):
        with mock.patch.dict(os.environ, {"FFMPEG_BINARY": "a_missing_ffmpeg_executable_23891"}):
            with self.assertRaisesRegex(FileNotFoundError, "FFMPEG_BINARY"):
                ffmpeg_exe()


class AudioAnalyzerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            ffmpeg_exe()
        except RuntimeError as exc:
            raise unittest.SkipTest(str(exc))

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_silence_tone_duration_central_group_and_cleanup(self):
        rate = 16000
        t = np.arange(rate // 2) / rate
        audio = np.concatenate([np.zeros(rate // 2), .25 * np.sin(2 * np.pi * 440 * t),
                                np.zeros(rate // 2)])
        source = self.root / "silence-tone.wav"
        write_wave(source, audio)
        with AudioAnalyzer(source, fps=30) as analyzer:
            temporary = Path(analyzer._temp.name)
            self.assertAlmostEqual(analyzer.duration, 1.5, places=4)
            np.testing.assert_array_equal(analyzer.levels_at(.2), np.zeros(9))
            np.testing.assert_array_equal(analyzer.levels_at(1.3), np.zeros(9))
            levels = analyzer.levels_at(.75)
            self.assertEqual(levels.shape, (9,))
            self.assertEqual(levels.dtype, np.float32)
            self.assertTrue(np.isfinite(levels).all())
            self.assertTrue(np.all(levels>0))
            self.assertIn(int(np.argmax(levels)),(3,4,5))
            self.assertLess(float(levels[[0,-1]].max()),float(levels[3:6].max())*.08)
            self.assertTrue(np.all(analyzer.levels_at(.55)>0))
            self.assertLessEqual(float(levels.max()), 1)
            self.assertGreater(float(levels.std()), .005)
            original = levels.copy()
            levels[:] = 0
            np.testing.assert_array_equal(analyzer.levels_at(.75), original)
            np.testing.assert_array_equal(analyzer.levels_at(-1), np.zeros(9))
            np.testing.assert_array_equal(analyzer.levels_at(2), np.zeros(9))
        self.assertFalse(temporary.exists())
        analyzer.close()
        with self.assertRaises(RuntimeError):
            analyzer.levels_at(.3)

    def test_group_pulses_in_place_with_small_live_edges(self):
        rate = 16000
        signal = np.zeros(rate)
        # A brief syllable must appear in every block at the same time, rather
        # than enter at the right edge and migrate through a history display.
        start,end = round(.25*rate),round(.32*rate)
        t = np.arange(end-start)/rate
        signal[start:end] = .25*np.sin(2*np.pi*440*t)
        source = self.root/'stationary-burst.wav'
        write_wave(source,signal)
        for fps in (30,60):
            with self.subTest(fps=fps), AudioAnalyzer(source,fps=fps) as analyzer:
                sequence=np.array([analyzer.levels_at(i/fps) for i in range(fps)])
                onsets=[np.flatnonzero(sequence[:,i]>1e-5)[0] for i in range(9)]
                self.assertEqual(len(set(onsets)),1)
                active=sequence[sequence.max(axis=1)>.005]
                self.assertTrue(np.isin(np.argmax(active,axis=1),[3,4,5]).all())
                self.assertTrue((active[:,[0,-1]]>0).all())
                self.assertTrue((active[:,[0,-1]].max(axis=1)<active[:,3:6].max(axis=1)*.08).all())
                np.testing.assert_array_equal(analyzer.levels_at(.6),np.zeros(9))

    def test_current_spectrum_changes_central_contour_without_horizontal_flow(self):
        rate=16000
        contours=[]
        for frequency in (180,500,850,1400,3800):
            source=self.root/f'current-{frequency}.wav'
            write_wave(source,.2*np.sin(2*np.pi*frequency*np.arange(rate)/rate))
            with AudioAnalyzer(source) as analyzer:
                a=analyzer.levels_at(.35)
                b=analyzer.levels_at(.65)
                self.assertIn(int(np.argmax(a)),(3,4,5))
                self.assertTrue(np.all(a>0))
                # The two shoulders must not collapse into a mirrored outline.
                self.assertGreater(float(np.max(np.abs(a[:4]-a[:4:-1]))),float(a.max())*.05)
                self.assertGreater(float(a[3:6].mean()),float(a[[0,1,7,8]].mean())*5)
                np.testing.assert_allclose(a/a.max(),b/b.max(),atol=.015)
                contours.append(a/a.max())
        self.assertGreater(float(np.max(np.ptp(np.array(contours),axis=0))),.1)

    def test_gain_and_silence(self):
        source = self.root / "tone.wav"
        write_wave(source, .02 * np.sin(2 * np.pi * 240 * np.arange(8000) / 16000))
        with AudioAnalyzer(source, gain=.25) as quiet, AudioAnalyzer(source, gain=2) as loud:
            self.assertGreater(float(loud.levels_at(.25).mean()), float(quiet.levels_at(.25).mean()))
        with AudioAnalyzer(source, gain=0) as muted:
            np.testing.assert_array_equal(muted.levels_at(.25), np.zeros(9))

    def test_invalid_empty_and_missing_audio(self):
        with self.assertRaises(FileNotFoundError):
            AudioAnalyzer(self.root / "missing.wav")
        source = self.root / "bad.wav"
        source.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "empty"):
            AudioAnalyzer(source)
        source.write_bytes(b"this is not audio")
        with self.assertRaisesRegex(RuntimeError, "FFmpeg"):
            AudioAnalyzer(source)
        write_wave(source, np.zeros(0))
        with self.assertRaises((ValueError, RuntimeError)):
            AudioAnalyzer(source)

    def test_cancellation_before_and_during_analysis(self):
        source = self.root / "audio.wav"
        write_wave(source, np.ones(16000) * .1)
        event = threading.Event()
        event.set()
        with self.assertRaises(CancelledError):
            AudioAnalyzer(source, cancel=event)
        event.clear()
        original = AudioAnalyzer._analyze
        def cancel_after_decode(analyzer, cancel):
            cancel.set()
            original(analyzer, cancel)
        with mock.patch.object(AudioAnalyzer, "_analyze", cancel_after_decode):
            with self.assertRaises(CancelledError):
                AudioAnalyzer(source, cancel=event)


class ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            ffmpeg_exe()
            from teamradio.renderer import RenderConfig
        except (RuntimeError, ImportError) as exc:
            raise unittest.SkipTest(str(exc))
        cls.RenderConfig = RenderConfig

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.rate = 44100
        t = np.arange(round(self.rate * .4)) / self.rate
        self.samples = np.stack([.3 * np.sin(2 * np.pi * 440 * t),
                                 .2 * np.sin(2 * np.pi * 880 * t)], axis=1)
        self.source = self.root / "original.wav"
        write_wave(self.source, self.samples, self.rate)
        self.config = self.RenderConfig(width=480, height=270, fps=10, entrance=.1,
                                       start_delay=.1, hold=.1, fade_out=.1,
                                       background="transparent")
        self.audio_start = .2
        self.total = .8

    def test_zip_alpha_metadata_and_original_stereo_delayed_soundtrack(self):
        output = self.root / "sequence.zip"
        progress = []
        result = export_video(self.source, output, self.config,
                              progress=lambda value, message: progress.append((value, message)))
        self.assertEqual(result, output.resolve())
        self.assertEqual(progress[-1][0], 1)
        self.assertEqual([value for value, _ in progress], sorted(value for value, _ in progress))
        self.assertEqual(sum(value == 1 for value, _ in progress), 1)
        with zipfile.ZipFile(output) as archive:
            metadata = json.loads(archive.read("metadata.json"))
            self.assertAlmostEqual(metadata["audio_start"], self.audio_start)
            self.assertAlmostEqual(metadata["duration"], self.total)
            names = [name for name in archive.namelist() if name.endswith(".png")]
            self.assertEqual(len(names), math.ceil(self.total * self.config.fps))
            image = Image.open(BytesIO(archive.read(names[3])))
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getpixel((0, 0))[3], 0)
            self.assertGreater(image.getchannel("A").getextrema()[1], 200)
            with wave.open(BytesIO(archive.read("soundtrack.wav")), "rb") as audio:
                self.assertEqual(audio.getnchannels(), 2)
                self.assertEqual(audio.getframerate(), self.rate)
                decoded = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").reshape(-1, 2)
        delay = round(self.audio_start * self.rate)
        np.testing.assert_array_equal(decoded[:delay], 0)
        expected = (self.samples * 32767).astype("<i2")
        np.testing.assert_allclose(decoded[delay:delay + len(expected)], expected, atol=1)
        self.assertGreaterEqual(len(decoded), round(self.total * self.rate) - 1)

    def test_all_video_containers_decode_and_alpha_survives(self):
        for extension in (".mp4", ".mov", ".webm", ".mkv", ".avi", ".gif"):
            with self.subTest(extension=extension):
                output = self.root / ("clip" + extension)
                export_video(self.source, output, self.config)
                self.assertGreater(output.stat().st_size, 100)
                frame = self.root / ("frame" + extension + ".png")
                decoder = ["-c:v", "libvpx-vp9"] if extension == ".webm" else []
                ffmpeg_call(*decoder, "-i", output, "-ss", "0.3", "-frames:v", "1", "-pix_fmt", "rgba", frame)
                with Image.open(frame) as image:
                    self.assertEqual(image.size, (480, 270))
                    if extension in (".mov", ".webm", ".gif"):
                        self.assertEqual(image.getpixel((0, 0))[3], 0)
                        self.assertGreater(image.getchannel("A").getextrema()[1], 200)
                    else:
                        self.assertEqual(image.getpixel((0, 0))[3], 255)
                        np.testing.assert_allclose(image.getpixel((0, 0))[:3], [16, 18, 26], atol=5)
                if extension != ".gif":
                    decoded_audio = self.root / ("sound" + extension + ".wav")
                    ffmpeg_call("-i", output, "-vn", "-c:a", "pcm_s16le", decoded_audio)
                    with wave.open(str(decoded_audio), "rb") as audio:
                        duration = audio.getnframes() / audio.getframerate()
                        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2")
                        channels = audio.getnchannels()
                        rate = audio.getframerate()
                    self.assertAlmostEqual(duration, self.total, delta=.12)
                    samples = samples.reshape(-1, channels)
                    before = samples[:round(.15 * rate)]
                    during = samples[round(.3 * rate):round(.5 * rate)]
                    self.assertLess(float(np.abs(before.astype(float)).mean()), 70)
                    self.assertGreater(float(np.abs(during.astype(float)).mean()), 1000)

    def test_cancel_and_encoder_failure_preserve_destination_and_cleanup(self):
        output = self.root / "existing.mp4"
        output.write_bytes(b"keep original destination")
        event = threading.Event()
        progress = []
        def cancel_during_frames(value, message):
            progress.append(value)
            if message.startswith("Rendering frame"):
                event.set()
        with self.assertRaises(CancelledError):
            export_video(self.source, output, self.config, cancel_during_frames, event)
        self.assertEqual(output.read_bytes(), b"keep original destination")
        self.assertNotIn(1., progress)
        self.assertFalse(list(self.root.glob(".teamradio-*")))
        from teamradio import media
        real_stream = media._stream_frames
        def fail_encoder(args, frames, cancel):
            args = list(args)
            args[args.index("libx264")] = "missing_encoder_23891"
            return real_stream(args, frames, cancel)
        with mock.patch.object(media, "_stream_frames", fail_encoder):
            with self.assertRaisesRegex(RuntimeError, "FFmpeg"):
                export_video(self.source, output, self.config)
        self.assertEqual(output.read_bytes(), b"keep original destination")
        self.assertFalse(list(self.root.glob(".teamradio-*")))

    def test_cancel_interrupts_encoder_that_does_not_read_pipe(self):
        from teamradio.media import _stream_frames
        event = threading.Event()
        timer = threading.Timer(.2, event.set)
        timer.start()
        try:
            with self.assertRaises(CancelledError):
                _stream_frames([sys.executable, "-c", "import time; time.sleep(20)"],
                               iter([Image.new("RGB", (960, 540))]), event)
        finally:
            timer.cancel()
            timer.join()

    def test_rejects_source_overwrite_and_unknown_format(self):
        original = self.source.read_bytes()
        # A supported output suffix must still be rejected when it aliases the
        # source; FFmpeg identifies the WAV contents independently of its name.
        supported_source = self.root / "source.mp4"
        supported_source.write_bytes(original)
        with self.assertRaisesRegex(ValueError, "source audio"):
            export_video(supported_source, supported_source, self.config)
        self.assertEqual(supported_source.read_bytes(), original)
        logo = self.root / "custom.gif"
        Image.new("RGBA", (8, 8), "red").save(logo)
        self.config.logo_path = str(logo)
        logo_original = logo.read_bytes()
        with self.assertRaisesRegex(ValueError, "logo asset"):
            export_video(self.source, logo, self.config)
        self.assertEqual(logo.read_bytes(), logo_original)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            export_video(self.source, self.root / "out.xyz", self.config)


if __name__ == "__main__":
    unittest.main()
