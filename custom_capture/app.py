from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRect, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .capture import (
    DesktopSnapshot,
    grab_desktop_snapshot,
    grab_region,
    save_region,
    save_region_from_snapshot,
    warm_up_capture_engines,
)
from .clipboard import ClipboardError, copy_image_to_clipboard
from .config import APP_NAME, Settings, load_settings
from .dpi import enable_dpi_awareness
from .keyboard_hook import WinShiftSKeyboardHook
from .overlay import SelectionOverlay
from .single_instance import acquire_single_instance
from .startup import install_startup, is_startup_installed, remove_startup


class CaptureController(QObject):
    hotkey_triggered = Signal()

    def __init__(self, settings: Settings, app: QApplication) -> None:
        super().__init__()
        self._settings = settings
        self._app = app
        self._overlay = SelectionOverlay(settings.min_selection_size)
        self._overlay.selection_made.connect(self._capture_selection)
        self._overlay.cancelled.connect(self._show_cancelled)
        self._tray = self._create_tray()
        self._hook = WinShiftSKeyboardHook(self.hotkey_triggered.emit)
        self._snapshot: DesktopSnapshot | None = None
        self.hotkey_triggered.connect(self.begin_capture)

    def start(self) -> None:
        self._tray.show()
        self._hook.start()
        threading.Thread(
            target=warm_up_capture_engines,
            name="CustomCaptureWarmup",
            daemon=True,
        ).start()

    def stop(self) -> None:
        self._hook.stop()

    @Slot()
    def begin_capture(self) -> None:
        if self._overlay.isVisible():
            return
        warm_up_capture_engines()
        self._snapshot = grab_desktop_snapshot()
        self._overlay.begin(self._snapshot)

    @Slot(object)
    def _capture_selection(self, rect) -> None:
        snapshot = self._snapshot
        self._snapshot = None

        def do_capture() -> None:
            try:
                if snapshot is not None:
                    path, image = save_region_from_snapshot(
                        snapshot,
                        rect,
                        Path(self._settings.save_dir),
                    )
                else:
                    path, image = save_region(rect, Path(self._settings.save_dir))
                copied = False
                if self._settings.copy_to_clipboard:
                    try:
                        copy_image_to_clipboard(image)
                        copied = True
                    except ClipboardError as exc:
                        self._tray.showMessage(
                            APP_NAME,
                            f"Saved to Downloads, but clipboard copy failed: {exc}",
                            QSystemTrayIcon.MessageIcon.Warning,
                            4000,
                        )
                        return

                suffix = " and copied to clipboard" if copied else ""
                self._tray.showMessage(
                    APP_NAME,
                    f"Saved {path.name}{suffix}.",
                    QSystemTrayIcon.MessageIcon.Information,
                    2500,
                )
            except Exception as exc:
                self._tray.showMessage(
                    APP_NAME,
                    f"Capture failed: {exc}",
                    QSystemTrayIcon.MessageIcon.Critical,
                    5000,
                )

        QTimer.singleShot(0 if snapshot is not None else 250, do_capture)

    @Slot()
    def _show_cancelled(self) -> None:
        self._snapshot = None
        self._tray.showMessage(
            APP_NAME,
            "Capture cancelled.",
            QSystemTrayIcon.MessageIcon.Information,
            1200,
        )

    def _create_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(_make_icon(), self._app)
        tray.setToolTip(f"{APP_NAME} - {self._settings.hotkey}")

        menu = QMenu()

        capture_action = QAction("Capture now", menu)
        capture_action.triggered.connect(self.begin_capture)
        menu.addAction(capture_action)

        open_downloads_action = QAction("Open Downloads", menu)
        open_downloads_action.triggered.connect(self._open_downloads)
        menu.addAction(open_downloads_action)

        menu.addSeparator()

        startup_action = QAction("Install startup", menu)
        startup_action.triggered.connect(self._install_startup_from_menu)
        menu.addAction(startup_action)

        remove_startup_action = QAction("Remove startup", menu)
        remove_startup_action.triggered.connect(self._remove_startup_from_menu)
        menu.addAction(remove_startup_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._app.quit)
        menu.addAction(quit_action)

        tray.setContextMenu(menu)
        return tray

    @Slot()
    def _open_downloads(self) -> None:
        os.startfile(self._settings.save_dir)

    @Slot()
    def _install_startup_from_menu(self) -> None:
        try:
            link = install_startup()
            self._tray.showMessage(
                APP_NAME,
                f"Startup installed: {link.name}",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
        except Exception as exc:
            self._tray.showMessage(
                APP_NAME,
                f"Startup install failed: {exc}",
                QSystemTrayIcon.MessageIcon.Critical,
                5000,
            )

    @Slot()
    def _remove_startup_from_menu(self) -> None:
        try:
            remove_startup()
            self._tray.showMessage(
                APP_NAME,
                "Startup removed.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )
        except Exception as exc:
            self._tray.showMessage(
                APP_NAME,
                f"Startup removal failed: {exc}",
                QSystemTrayIcon.MessageIcon.Critical,
                5000,
            )


def _make_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(0, 120, 215))
    painter.setPen(QColor(255, 255, 255))
    painter.drawRoundedRect(8, 10, 48, 38, 6, 6)
    painter.setBrush(QColor(255, 255, 255))
    painter.drawRect(20, 22, 24, 14)
    painter.end()
    return QIcon(pixmap)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=APP_NAME)
    parser.add_argument("--install-startup", action="store_true")
    parser.add_argument("--remove-startup", action="store_true")
    parser.add_argument(
        "--no-auto-startup",
        action="store_true",
        help="Do not create the startup shortcut on normal launch.",
    )
    parser.add_argument(
        "--self-test-capture",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)

    if args.install_startup:
        link = install_startup()
        print(f"Installed startup shortcut: {link}")
        return 0

    if args.remove_startup:
        link = remove_startup()
        print(f"Removed startup shortcut: {link}")
        return 0

    if args.self_test_capture:
        enable_dpi_awareness()
        warm_up_capture_engines()
        snapshot = grab_desktop_snapshot()
        image = snapshot.crop(QRect(0, 0, 500, 350)) if snapshot else grab_region(QRect(0, 0, 500, 350))
        image.save(args.self_test_capture, "PNG")
        return 0

    if not acquire_single_instance():
        return 0

    enable_dpi_awareness()
    settings = load_settings()

    app = QApplication([sys.argv[0]])
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("System tray is not available.", file=sys.stderr)
        return 1

    if not args.no_auto_startup and not is_startup_installed():
        try:
            install_startup()
        except Exception:
            pass

    controller = CaptureController(settings, app)
    app.aboutToQuit.connect(controller.stop)
    controller.start()

    return app.exec()
