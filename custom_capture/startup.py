from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .config import APP_NAME


def startup_dir() -> Path:
    appdata = Path(os.environ.get("APPDATA", str(Path.home())))
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def shortcut_path() -> Path:
    return startup_dir() / f"{APP_NAME}.lnk"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def executable_target() -> tuple[Path, str, Path]:
    if is_frozen():
        exe = Path(sys.executable)
        return exe, "", exe.parent

    exe = Path(sys.executable)
    cwd = Path(__file__).resolve().parents[1]
    return exe, "-m custom_capture", cwd


def _ps_single_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def install_startup() -> Path:
    target, arguments, working_dir = executable_target()
    link = shortcut_path()
    link.parent.mkdir(parents=True, exist_ok=True)

    script = "\n".join(
        [
            "$shell = New-Object -ComObject WScript.Shell",
            f"$shortcut = $shell.CreateShortcut({_ps_single_quote(str(link))})",
            f"$shortcut.TargetPath = {_ps_single_quote(str(target))}",
            f"$shortcut.Arguments = {_ps_single_quote(arguments)}",
            f"$shortcut.WorkingDirectory = {_ps_single_quote(str(working_dir))}",
            "$shortcut.WindowStyle = 7",
            f"$shortcut.IconLocation = {_ps_single_quote(str(target) + ',0')}",
            "$shortcut.Save()",
        ]
    )

    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return link


def remove_startup() -> Path:
    link = shortcut_path()
    if link.exists():
        link.unlink()
    return link


def is_startup_installed() -> bool:
    return shortcut_path().exists()
