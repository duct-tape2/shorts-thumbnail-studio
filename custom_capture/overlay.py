from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget


class SelectionOverlay(QWidget):
    selection_made = Signal(QRect)
    cancelled = Signal()

    def __init__(self, min_selection_size: int = 3) -> None:
        super().__init__(None)
        self._min_selection_size = min_selection_size
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._virtual_origin = QPoint(0, 0)
        self._snapshot_parts: list[tuple[QRect, QImage]] = []

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))
        self.setMouseTracking(True)

    def begin(self, snapshot=None) -> None:
        virtual = QApplication.primaryScreen().virtualGeometry()
        self._virtual_origin = virtual.topLeft()
        self._origin = None
        self._current = None
        self._set_snapshot(snapshot)
        self.setGeometry(virtual)
        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self.cancelled.emit()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._origin = event.position().toPoint()
        self._current = self._origin
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._origin is None:
            return
        self._current = event.position().toPoint()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return

        self._current = event.position().toPoint()
        local_rect = self._selection_rect()
        self._origin = None
        self._current = None

        if (
            local_rect.width() < self._min_selection_size
            or local_rect.height() < self._min_selection_size
        ):
            self.hide()
            self.cancelled.emit()
            return

        logical_global_rect = QRect(
            local_rect.left() + self._virtual_origin.x(),
            local_rect.top() + self._virtual_origin.y(),
            local_rect.width(),
            local_rect.height(),
        )
        physical_global_rect = self._logical_to_physical_rect(logical_global_rect)

        self.hide()
        self.selection_made.emit(physical_global_rect)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._snapshot_parts:
            self._draw_snapshot(painter)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))

        rect = self._selection_rect()
        if not rect.isNull():
            if self._snapshot_parts:
                painter.save()
                painter.setClipRect(rect)
                self._draw_snapshot(painter)
                painter.restore()
            else:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                painter.fillRect(rect, Qt.GlobalColor.transparent)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(255, 255, 255), 2))
            painter.drawRect(rect.adjusted(0, 0, -1, -1))
            painter.setPen(QPen(QColor(0, 120, 215), 1))
            painter.drawRect(rect.adjusted(2, 2, -3, -3))

    def _selection_rect(self) -> QRect:
        if self._origin is None or self._current is None:
            return QRect()
        return QRect(self._origin, self._current).normalized()

    def _logical_to_physical_rect(self, logical_rect: QRect) -> QRect:
        physical: QRect | None = None

        for screen in QApplication.screens():
            screen_rect = screen.geometry()
            intersection = logical_rect.intersected(screen_rect)
            if intersection.isNull() or intersection.width() <= 0 or intersection.height() <= 0:
                continue

            scale = float(screen.devicePixelRatio())
            physical_left = int(round(screen_rect.left() + (intersection.left() - screen_rect.left()) * scale))
            physical_top = int(round(screen_rect.top() + (intersection.top() - screen_rect.top()) * scale))
            physical_right = int(round(screen_rect.left() + (intersection.left() + intersection.width() - screen_rect.left()) * scale))
            physical_bottom = int(round(screen_rect.top() + (intersection.top() + intersection.height() - screen_rect.top()) * scale))

            part = QRect(
                physical_left,
                physical_top,
                max(1, physical_right - physical_left),
                max(1, physical_bottom - physical_top),
            )
            physical = part if physical is None else physical.united(part)

        if physical is not None:
            return physical

        scale = float(QApplication.primaryScreen().devicePixelRatio())
        return QRect(
            int(round(logical_rect.x() * scale)),
            int(round(logical_rect.y() * scale)),
            max(1, int(round(logical_rect.width() * scale))),
            max(1, int(round(logical_rect.height() * scale))),
        )

    def _set_snapshot(self, snapshot) -> None:
        self._snapshot_parts = []
        if snapshot is None:
            return

        for screen in QApplication.screens():
            screen_rect = screen.geometry()
            scale = float(screen.devicePixelRatio())
            physical_left = int(screen_rect.left())
            physical_top = int(screen_rect.top())
            physical_width = max(1, int(round(screen_rect.width() * scale)))
            physical_height = max(1, int(round(screen_rect.height() * scale)))

            crop_box = (
                physical_left - int(snapshot.left),
                physical_top - int(snapshot.top),
                physical_left + physical_width - int(snapshot.left),
                physical_top + physical_height - int(snapshot.top),
            )
            image = snapshot.image.crop(crop_box).convert("RGB")
            qimage = QImage(
                image.tobytes(),
                image.width,
                image.height,
                image.width * 3,
                QImage.Format.Format_RGB888,
            ).copy()
            local_rect = QRect(screen_rect)
            local_rect.translate(-self._virtual_origin)
            self._snapshot_parts.append((local_rect, qimage))

    def _draw_snapshot(self, painter: QPainter) -> None:
        for local_rect, qimage in self._snapshot_parts:
            painter.drawImage(local_rect, qimage)
