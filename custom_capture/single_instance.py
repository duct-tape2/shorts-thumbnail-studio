from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from .config import SETTINGS_DIR


ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Local\\CustomCapture_SingleInstance"

_mutex_handle: int | None = None
_lock_file = None


def acquire_single_instance() -> bool:
    return _acquire_file_lock() and _acquire_mutex()


def _acquire_file_lock() -> bool:
    global _lock_file

    try:
        import msvcrt
    except ImportError:
        return True

    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        lock_path = Path(SETTINGS_DIR) / "CustomCapture.lock"
        handle = open(lock_path, "a+b")
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()).encode("ascii"))
        handle.flush()
        _lock_file = handle
        return True
    except OSError:
        try:
            handle.close()
        except Exception:
            pass
        return False


def _acquire_mutex() -> bool:
    global _mutex_handle

    if not hasattr(ctypes, "windll"):
        return True

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    kernel32.GetLastError.argtypes = []
    kernel32.GetLastError.restype = wintypes.DWORD

    handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    if not handle:
        return True

    _mutex_handle = handle
    return kernel32.GetLastError() != ERROR_ALREADY_EXISTS
