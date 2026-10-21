from pathlib import Path
import ctypes
import hashlib
import os
import shutil
import sys

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets'
DATA = ROOT / 'data'
OUTPUT = ROOT / '완성본'


def setup_fonts():
    """Install only the bundled open fonts for this user; no administrator needed."""
    if os.name != 'nt':
        return
    import winreg
    dest = Path(os.environ['LOCALAPPDATA']) / 'Microsoft/Windows/Fonts'
    dest.mkdir(parents=True, exist_ok=True)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows NT\CurrentVersion\Fonts') as key:
        for src in (ASSETS / 'fonts').glob('*'):
            target = dest / src.name
            if not target.exists():
                shutil.copy2(src, target)
            # Preserve an existing font, rather than overwriting another installation.
            winreg.SetValueEx(key, src.stem + ' (Thumbnail Studio)', 0, winreg.REG_SZ, str(target))
            ctypes.windll.gdi32.AddFontResourceExW(str(target), 0, 0)


def ensure_dirs():
    for p in (DATA, OUTPUT, ROOT / '캡처'):
        p.mkdir(parents=True, exist_ok=True)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()
