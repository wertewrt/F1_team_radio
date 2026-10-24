# -*- mode: python ; coding: utf-8 -*-
"""Windows x64 one-file build. Run through tools/build_windows.ps1."""
from pathlib import Path
import struct
import sys

import imageio_ffmpeg

ROOT = Path(SPECPATH).resolve().parent
NAME = "F1-Team-Radio-Studio-v1.0.2-windows-x64"
if sys.platform != "win32" or struct.calcsize("P") != 8:
    raise RuntimeError("Build with 64-bit Windows Python.")

# Explicit inputs keep reference media, examples and the development environment out.
required = [ROOT / "assets", ROOT / "LICENSES",
            ROOT / "THIRD-PARTY-NOTICES.txt", ROOT / "packaging" / "app.ico"]
for path in required:
    if not path.exists():
        raise FileNotFoundError(f"Required release input is missing: {path}")
datas = [
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "LICENSES"), "LICENSES"),
    (str(ROOT / "THIRD-PARTY-NOTICES.txt"), "."),
]
ffmpeg_dir = Path(imageio_ffmpeg.__file__).resolve().parent / "binaries"
ffmpeg_binaries = sorted(ffmpeg_dir.glob("ffmpeg*.exe"))
if len(ffmpeg_binaries) != 1:
    raise RuntimeError(f"Expected one bundled Windows FFmpeg binary in {ffmpeg_dir}")

a = Analysis(
    [str(ROOT / "launch_gui.py")],
    pathex=[str(ROOT)],
    binaries=[(str(ffmpeg_binaries[0]), "imageio_ffmpeg/binaries")],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["cv2", "fontTools", "pytest", "IPython", "matplotlib", "scipy", "pandas"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name=NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    version=str(ROOT / "packaging" / "windows-version-info.txt"),
    icon=str(ROOT / "packaging" / "app.ico"),
)
