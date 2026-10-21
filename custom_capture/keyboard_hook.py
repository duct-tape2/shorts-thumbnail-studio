from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable


WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

VK_S = 0x53
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_SHIFT = 0x10
VK_LWIN = 0x5B
VK_RWIN = 0x5C

LLKHF_INJECTED = 0x10


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    wintypes.LPARAM,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class WinShiftSKeyboardHook:
    def __init__(self, on_hotkey: Callable[[], None]) -> None:
        self._on_hotkey = on_hotkey
        self._thread: threading.Thread | None = None
        self._hook_handle = None
        self._thread_id = 0
        self._callback = LowLevelKeyboardProc(self._hook_proc)
        self._lock = threading.Lock()
        self._pressed: set[int] = set()
        self._running = threading.Event()

        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

        self._user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int,
            LowLevelKeyboardProc,
            wintypes.HINSTANCE,
            wintypes.DWORD,
        ]
        self._user32.SetWindowsHookExW.restype = wintypes.HHOOK
        self._user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        self._user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        self._user32.CallNextHookEx.argtypes = [
            wintypes.HHOOK,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self._user32.CallNextHookEx.restype = wintypes.LPARAM
        self._user32.GetMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG),
            wintypes.HWND,
            wintypes.UINT,
            wintypes.UINT,
        ]
        self._user32.GetMessageW.restype = wintypes.BOOL
        self._user32.PostThreadMessageW.argtypes = [
            wintypes.DWORD,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        self._user32.PostThreadMessageW.restype = wintypes.BOOL
        self._kernel32.GetCurrentThreadId.argtypes = []
        self._kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self._kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self._kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._running.clear()
        self._thread = threading.Thread(
            target=self._message_loop,
            name="CustomCaptureKeyboardHook",
            daemon=True,
        )
        self._thread.start()
        if not self._running.wait(timeout=3):
            raise RuntimeError("Keyboard hook thread did not start")
        if not self._hook_handle:
            raise RuntimeError("SetWindowsHookExW failed")

    def stop(self) -> None:
        if self._thread_id:
            self._user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None

    def _message_loop(self) -> None:
        self._thread_id = self._kernel32.GetCurrentThreadId()
        module_handle = self._kernel32.GetModuleHandleW(None)
        self._hook_handle = self._user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._callback,
            module_handle,
            0,
        )
        self._running.set()

        if not self._hook_handle:
            return

        msg = wintypes.MSG()
        while self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass

        if self._hook_handle:
            self._user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = None

    def _hook_proc(self, n_code: int, w_param: int, l_param: int) -> int:
        if n_code < 0:
            return self._user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)

        event = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk_code = int(event.vkCode)
        flags = int(event.flags)
        is_key_down = w_param in (WM_KEYDOWN, WM_SYSKEYDOWN)
        is_key_up = w_param in (WM_KEYUP, WM_SYSKEYUP)

        if flags & LLKHF_INJECTED:
            return self._user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)

        should_block = False
        should_fire = False

        with self._lock:
            if is_key_down:
                self._pressed.add(vk_code)
            elif is_key_up:
                self._pressed.discard(vk_code)

            win_down = VK_LWIN in self._pressed or VK_RWIN in self._pressed
            shift_down = (
                VK_SHIFT in self._pressed
                or VK_LSHIFT in self._pressed
                or VK_RSHIFT in self._pressed
            )

            if is_key_down and vk_code == VK_S and win_down and shift_down:
                should_block = True
                should_fire = True
            elif vk_code == VK_S and win_down and shift_down:
                should_block = True

        if should_fire:
            threading.Thread(
                target=self._on_hotkey,
                name="CustomCaptureHotkeyDispatch",
                daemon=True,
            ).start()

        if should_block:
            return 1

        return self._user32.CallNextHookEx(self._hook_handle, n_code, w_param, l_param)
