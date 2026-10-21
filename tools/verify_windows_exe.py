"""Run both actual windowed-EXE checks with explicit handles and bounded waits."""
from pathlib import Path
import argparse, json, os, subprocess
p=argparse.ArgumentParser()
p.add_argument('exe',type=Path)
p.add_argument('output',type=Path)
p.add_argument('--temp',type=Path)
a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=True)
env=os.environ.copy()
if a.temp:
    a.temp.mkdir(parents=True,exist_ok=True)
    env['TEMP']=env['TMP']=str(a.temp.resolve())
# Prove the EXE locates its own FFmpeg and runtime, not a developer installation.
env['PATH']=str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32')
env.pop('PYTHONHOME',None);env.pop('PYTHONPATH',None);env.pop('FFMPEG_BINARY',None)
for mode,name in [('--self-test','self-test-report.json'),('--gui-smoke-test','gui-smoke-test-report.json')]:
    report=a.output/name
    report.unlink(missing_ok=True)
    run=subprocess.run([str(a.exe.resolve()),mode,'--report',str(report.resolve())],
                       cwd=a.output.resolve(),env=env,stdin=subprocess.DEVNULL,
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
    if run.returncode:
        raise SystemExit(f'{mode} failed ({run.returncode}): '+run.stderr.decode(errors='replace'))
    if not report.is_file():raise SystemExit(f'Missing report: {report}')
    info=json.loads(report.read_text(encoding='utf-8'))
    if not info.get('ok') or not info.get('frozen') or info.get('version')!='1.0.0':
        raise SystemExit(f'Invalid packaged test result: {report}')
    print(f'{mode}: passed ({len(info["results"])} stages, frozen=True)',flush=True)
