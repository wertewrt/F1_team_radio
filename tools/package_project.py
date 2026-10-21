"""Package the complete portable source project, excluding local caches."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
ROOT=Path(__file__).resolve().parent.parent
TARGET=ROOT/'F1_Team_Radio_Studio.zip'
folders=('teamradio','assets','resource','examples','tests','tools','analysis')
rootfiles=('readme.md','requirements.txt','requirements-dev.txt','start.bat','install.bat','launch_gui.py','.gitignore')
files=[ROOT/name for name in rootfiles]
for folder in folders:
 files.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo'))
with ZipFile(TARGET,'w',ZIP_DEFLATED,compresslevel=6) as z:
 for path in sorted(files): z.write(path,Path('F1_Team_Radio_Studio')/path.relative_to(ROOT))
print(TARGET.name, len(files),'files',TARGET.stat().st_size,'bytes')
with ZipFile(TARGET) as z:
 bad=z.testzip()
 if bad: raise RuntimeError('Corrupt archive member: '+bad)
print('Archive CRC check passed')
