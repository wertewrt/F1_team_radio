"""Collect license texts from the actual Windows build environment."""
from importlib.metadata import distribution
from pathlib import Path
import shutil, subprocess, sys, tkinter, urllib.request
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'LICENSES'
DEST.mkdir(exist_ok=True)
components=[]
for name in ('numpy','Pillow','imageio-ffmpeg','pyinstaller'):
    package=distribution(name)
    count=0
    for item in package.files or []:
        if not any(word in str(item).lower() for word in ('license','copying','copyright')):
            continue
        source=Path(package.locate_file(item))
        if not source.is_file(): continue
        # Keep the wheel's directory structure to preserve third-party notices.
        target=DEST/name/Path(str(item))
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
        count+=1
    if not count: raise RuntimeError('No license found for '+name)
    components.append((name,package.version))
python_license=Path(sys.base_prefix)/'LICENSE.txt'
shutil.copyfile(python_license,DEST/'Python-LICENSE.txt')
shutil.copyfile(ROOT/'assets/fonts/LICENSE_DEJAVU.txt',DEST/'DejaVu-LICENSE.txt')
shutil.copyfile(ROOT/'assets/ASSET_NOTES.md',DEST/'ASSET_NOTES.md')
tcl=tkinter.Tcl()
tcl_version=tcl.eval('info patchlevel')
for component in ('tcl','tk'):
    url=f'https://raw.githubusercontent.com/tcltk/{component}/core-{tcl_version.replace(".","-")}/license.terms'
    with urllib.request.urlopen(url,timeout=60) as response:
        (DEST/(component+'-license.terms')).write_bytes(response.read())
ffmpeg=DEST/'FFmpeg'
ffmpeg.mkdir(exist_ok=True)
for name in ('COPYING.GPLv3','LICENSE.md','COPYING.LGPLv3'):
    target=ffmpeg/name
    if not target.exists():
        with urllib.request.urlopen('https://raw.githubusercontent.com/FFmpeg/FFmpeg/n7.1/'+name,timeout=60) as response:
            target.write_bytes(response.read())
import imageio_ffmpeg
build_info=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), '-version'], capture_output=True, text=True, check=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
(ffmpeg/'BUILD-CONFIGURATION.txt').write_text(build_info.stdout + build_info.stderr, encoding='utf-8')
lines=['F1 Team Radio Studio v1.0.1 — Third-party notices',
       '================================================',
       'These notices cover bundled third-party components, not a new license grant for project code.',
       '',f'Python {sys.version.split()[0]} — Python Software Foundation License (see Python-LICENSE.txt).',
       f'Tcl/Tk {tcl_version} — BSD-style licenses (see tcl-license.terms and tk-license.terms).']
for name,version in components:
    lines.append(f'{name} {version} — complete wheel license texts are under LICENSES/{name}/.')
lines += ['', 'Pillow includes FreeType and other native libraries; their complete notices are included in its LICENSE.',
          'Portions of this software are copyright The FreeType Project (https://freetype.org). All rights reserved.',
          'NumPy wheel notices include OpenBLAS and its bundled native components.',
          'PyInstaller bootloader redistribution is covered by the special exception in its COPYING.txt.',
          '', 'FFmpeg 7.1-essentials_build-www.gyan.dev (unmodified imageio-ffmpeg 0.6.0 Windows binary)',
          'Copyright (c) 2000-2024 the FFmpeg developers.',
          'License: GNU GPL version 3 or later; this is distinct from the imageio-ffmpeg wrapper BSD license.',
          'The application invokes FFmpeg as a separate executable. No FFmpeg libraries are linked into Python.',
          'Full GPL text and FFmpeg license details: LICENSES/FFmpeg/.',
          'Build configuration and upstream component links: LICENSES/FFmpeg/BUILD-AND-SOURCES.txt.',
          'FFmpeg core source archive is provided alongside this release as ffmpeg-7.1.tar.xz.',
          'Upstream release source: https://ffmpeg.org/releases/ffmpeg-7.1.tar.xz',
          'Binary builder: https://www.gyan.dev/ffmpeg/builds/',
          'Binary mirror: https://github.com/GyanD/codexffmpeg/releases/tag/7.1',
          'Bundled binary distributor: https://github.com/imageio/imageio-ffmpeg/tree/v0.6.0',
          '', 'Formula 1 Bold / Regular fonts — supplied by the user as Formula1-Bold_web_0.ttf and Formula1-Regular_web_0.ttf.',
          'These fonts are not covered by the DejaVu license; this project grants no additional rights to them.',
          'DejaVu fonts — Bitstream Vera/DejaVu terms: LICENSES/DejaVu-LICENSE.txt.',
          'Microsoft YaHei is loaded from Windows when available and is not redistributed.',
          'Team names/logos belong to their respective rights holders; asset provenance is documented in LICENSES/ASSET_NOTES.md.',
          '', 'Permission texts are also embedded in the executable and included in the release licenses ZIP.',
          'No warranty is provided by the third-party components beyond their respective license terms.', '']
(ROOT/'THIRD-PARTY-NOTICES.txt').write_text('\n'.join(lines),encoding='utf-8')
print('Collected licenses for',components,'Tcl/Tk',tcl_version)
