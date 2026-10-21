"""Build the portable distribution. Run with a Python 3.12 Windows x64 environment."""
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys

root=Path(__file__).resolve().parent
public='--public' in sys.argv
args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
      '--name','ThumbnailStudio','--collect-all','rapidocr','--collect-all','kiwipiepy_model',
      '--collect-all','kiwipiepy','--collect-all','onnxruntime','--hidden-import','_kiwipiepy',
      '--hidden-import','dxcam','--collect-all','comtypes','--exclude-module','PySide6.QtWebEngineCore',
      '--exclude-module','PySide6.QtWebEngineWidgets','--exclude-module','PySide6.QtPdf',
      '--exclude-module','PySide6.QtQuick','--exclude-module','PySide6.QtQml','main.py']
subprocess.run(args,cwd=root,check=True)
dest=root/'dist/ThumbnailStudio'
# Qt uses Windows' unversioned ICU API. The build host's Python runtime also
# carries an ICU DLL with version-suffixed exports, which is incompatible.
# Do not shadow the Windows system DLL in the frozen executable's search path.
for filename in ('icuuc.dll','icudt78.dll'):
    (dest/'_internal'/filename).unlink(missing_ok=True)
for name in ('assets','vendor','licenses'):
    shutil.copytree(root/name,dest/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('template.psd') if public and name=='assets' else None)
for name in ('시작.bat','사용법.txt','README.md','LICENSE'):
    shutil.copy2(root/name,dest/name)
source=dest/'소스코드';source.mkdir(exist_ok=True)
for name in ('studio','custom_capture','tests','scripts'):
    shutil.copytree(root/name,source/name,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
for name in ('main.py','build.py','requirements-lock.txt','DESIGN.md'):
    shutil.copy2(root/name,source/name)
third=dest/'licenses/python-packages';third.mkdir(parents=True,exist_ok=True)
inventory=[]
for d in importlib.metadata.distributions():
    name=d.metadata['Name'];version=d.version
    inventory.append({'name':name,'version':version,'license':d.metadata.get('License-Expression') or d.metadata.get('License','')})
    for f in d.files or []:
        if any(k in str(f).lower() for k in ('license','copying','notice')) and '.dist-info' in str(f):
            src=Path(d.locate_file(f))
            if src.is_file():
                relative=Path(*Path(str(f)).parts[1:])
                target=third/name/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
(dest/'licenses/dependencies.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
print(dest)
