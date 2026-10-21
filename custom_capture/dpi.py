import ctypes


def enable_dpi_awareness() -> None:
    """Ask Windows for physical-pixel coordinates before Qt starts."""
    if not hasattr(ctypes, "windll"):
        return

    user32 = ctypes.windll.user32
    shcore = getattr(ctypes.windll, "shcore", None)

    try:
        # Windows 10: DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass

    if shcore is not None:
        try:
            # PROCESS_PER_MONITOR_DPI_AWARE
            shcore.SetProcessDpiAwareness(2)
            return
        except Exception:
            pass

    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass
