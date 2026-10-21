"""Check a disposable extracted Windows release, including noninteractive failures.

Usage: python tests/startup_smoke.py <ThumbnailStudio-folder> <report-folder>
The app folder must be a test copy: checks create local data and outputs.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

root=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]).resolve();out.mkdir(parents=True,exist_ok=True)
exe=root/'ThumbnailStudio.exe'
env=dict(os.environ,QT_QPA_PLATFORM='offscreen')
for attempt in range(3):
    report=out/f'startup-{attempt+1}.json'
    result=subprocess.run([str(exe),'--self-check','--report',str(report)],env=env,timeout=60)
    assert result.returncode==0, f'Startup attempt {attempt+1} failed: {root}/data/startup-error.log'
    assert json.loads(report.read_text())['ok']
    assert report.with_suffix('.png').is_file()

# A CLI failure must terminate rather than wait forever behind a modal dialog.
invalid=out/'invalid.json';invalid.write_text('{}',encoding='utf-8')
result=subprocess.run([str(exe),'--design',str(invalid)],env=env,timeout=20)
assert result.returncode==1,'Invalid plan should report failure to the caller'
log=root/'data/startup-error.log';assert log.is_file()
assert 'Traceback' in log.read_text(encoding='utf-8')
print('3 startup checks and noninteractive failure check passed')
