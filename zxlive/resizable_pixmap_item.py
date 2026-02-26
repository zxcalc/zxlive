from __future__ import annotations

from enum import Enum
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QStyleOptionGraphicsItem, QWidget


class _Corner(Enum):
    NONE = 0
    TOP_LEFT = 1
    TOP_RIGHT = 2
    BOTTOM_LEFT = 3
    BOTTOM_RIGHT = 4


class ResizablePixmapItem(QGraphicsPixmapItem):
    """A movable pixmap item with always-visible 4-corner resize handles."""

    def __init__(self, parent: Optional[QGraphicsItem] = None) -> None:
        super().__init__(parent)
        self._source_pixmap = QPixmap()
        self._handle_size = 6.0
        self._active_corner = _Corner.NONE
        self._drag_opposite_corner_parent = QPointF()
        self._target_size: Optional[tuple[int, int]] = None
        self._user_positioned = False

        self._dragging_body = False
        self._press_scene_pos = QPointF()
        self._item_start_pos = QPointF()
        self._resize_start_mouse_parent = QPointF()
        self._resize_start_size = QPointF()
        self._resize_start_display_size = QPointF()

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)

    def set_source_pixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = pixmap
        if self._target_size is None:
            self.setPixmap(pixmap)
            return

        w, h = self._target_size
        self.setPixmap(self._scaled_from_source(float(w), float(h)))

    def should_auto_center(self, text: str, last_text: Optional[str]) -> bool:
        return (not self._user_positioned) or (text != last_text)

    def mark_programmatic_recenter(self) -> None:
        self._user_positioned = False


    def _scaled_from_source(self, display_w: float, display_h: float) -> QPixmap:
        dpr = max(1.0, self._source_pixmap.devicePixelRatio())
        pixel_w = max(16, int(round(display_w * dpr)))
        pixel_h = max(16, int(round(display_h * dpr)))
        scaled = self._source_pixmap.scaled(
            pixel_w,
            pixel_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        scaled.setDevicePixelRatio(dpr)
        return scaled

    def _pixel_rect(self) -> QRectF:
        return super().boundingRect()

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        rect = self._pixel_rect()
        half = self._handle_size / 2.0
        return rect.adjusted(-half, -half, half, half)

    def shape(self) -> QPainterPath:  # type: ignore[override]
        path = QPainterPath()
        path.addRect(self.boundingRect())
        return path

    def _corner_rects(self) -> dict[_Corner, QRectF]:
        rect = self._pixel_rect()
        s = self._handle_size
        half = s / 2.0
        return {
            _Corner.TOP_LEFT: QRectF(rect.left() - half, rect.top() - half, s, s),
            _Corner.TOP_RIGHT: QRectF(rect.right() - half, rect.top() - half, s, s),
            _Corner.BOTTOM_LEFT: QRectF(rect.left() - half, rect.bottom() - half, s, s),
            _Corner.BOTTOM_RIGHT: QRectF(rect.right() - half, rect.bottom() - half, s, s),
        }

    def _corner_at(self, pos: QPointF) -> _Corner:
        for corner, crect in self._corner_rects().items():
            if crect.contains(pos):
                return corner
        return _Corner.NONE

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None) -> None:
        super().paint(painter, option, widget)
        if self.pixmap().isNull():
            return

        if not self.isSelected():
            return

        painter.save()
        outline = QColor("#2f80ed")
        painter.setPen(QPen(outline, 1, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self._pixel_rect())

        painter.setPen(QPen(QColor("#2f80ed"), 1))
        painter.setBrush(QBrush(QColor("#ffffff")))
        for crect in self._corner_rects().values():
            painter.drawRect(crect)
        painter.restore()

    def hoverMoveEvent(self, event) -> None:  # type: ignore[override]
        corner = self._corner_at(event.pos())
        if corner in (_Corner.TOP_LEFT, _Corner.BOTTOM_RIGHT):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif corner in (_Corner.TOP_RIGHT, _Corner.BOTTOM_LEFT):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(event)

    def _scene_delta_in_parent(self, scene_now: QPointF) -> QPointF:
        parent = self.parentItem()
        if parent is None:
            return scene_now - self._press_scene_pos
        return parent.mapFromScene(scene_now) - parent.mapFromScene(self._press_scene_pos)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.setSelected(True)
        self.setFocus()

        self._press_scene_pos = event.scenePos()
        self._item_start_pos = self.pos()

        corner = self._corner_at(event.pos())
        self._active_corner = corner

        if corner != _Corner.NONE:
            rect = self._pixel_rect()
            if corner == _Corner.TOP_LEFT:
                opposite = QPointF(rect.right(), rect.bottom())
            elif corner == _Corner.TOP_RIGHT:
                opposite = QPointF(rect.left(), rect.bottom())
            elif corner == _Corner.BOTTOM_LEFT:
                opposite = QPointF(rect.right(), rect.top())
            else:
                opposite = QPointF(rect.left(), rect.top())
            self._drag_opposite_corner_parent = self.mapToParent(opposite)
            self._resize_start_mouse_parent = self.mapToParent(event.pos())
            start_rect = self._pixel_rect()
            self._resize_start_size = QPointF(start_rect.width(), start_rect.height())
            self._resize_start_display_size = QPointF(start_rect.width(), start_rect.height())
            self.grabMouse()
            event.accept()
            return

        self._dragging_body = True
        self.grabMouse()
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._active_corner != _Corner.NONE and not self._source_pixmap.isNull():
            # Use scene-space delta (mapped to parent coordinates) to avoid feedback
            # loops from local-coordinate changes while the item is being resized.
            delta = self._scene_delta_in_parent(event.scenePos())

            # Ignore tiny initial jitter so click-and-hold doesn't immediately
            # shrink the item before an intentional drag starts.
            if abs(delta.x()) < 2.0 and abs(delta.y()) < 2.0:
                event.accept()
                return

            sx = -1.0 if self._active_corner in (_Corner.TOP_LEFT, _Corner.BOTTOM_LEFT) else 1.0
            sy = -1.0 if self._active_corner in (_Corner.TOP_LEFT, _Corner.TOP_RIGHT) else 1.0

            # Signed movement along the selected corner's outward diagonal.
            diag_drag = (sx * delta.x() + sy * delta.y()) / 2.0
            base = max(1.0, max(self._resize_start_size.x(), self._resize_start_size.y()))
            # Allow shrinking and enlarging from the original rendered size, while
            # preventing collapse to near-zero dimensions.
            scale_factor = max(0.2, 1.0 + diag_drag / base)

            target_w = max(16.0, self._resize_start_display_size.x() * scale_factor)
            target_h = max(16.0, self._resize_start_display_size.y() * scale_factor)

            self.setPixmap(self._scaled_from_source(target_w, target_h))
            self._target_size = (self.pixmap().width(), self.pixmap().height())
            self._user_positioned = True

            rect = self._pixel_rect()
            if self._active_corner == _Corner.TOP_LEFT:
                self.setPos(
                    QPointF(
                        self._drag_opposite_corner_parent.x() - rect.width(),
                        self._drag_opposite_corner_parent.y() - rect.height(),
                    )
                )
            elif self._active_corner == _Corner.TOP_RIGHT:
                self.setPos(
                    QPointF(
                        self._drag_opposite_corner_parent.x(),
                        self._drag_opposite_corner_parent.y() - rect.height(),
                    )
                )
            elif self._active_corner == _Corner.BOTTOM_LEFT:
                self.setPos(
                    QPointF(
                        self._drag_opposite_corner_parent.x() - rect.width(),
                        self._drag_opposite_corner_parent.y(),
                    )
                )
            else:
                self.setPos(self._drag_opposite_corner_parent)

            event.accept()
            return

        if self._dragging_body:
            delta = self._scene_delta_in_parent(event.scenePos())
            self.setPos(self._item_start_pos + delta)
            self._user_positioned = True
            event.accept()
            return

        event.ignore()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._active_corner = _Corner.NONE
        self._dragging_body = False
        self.ungrabMouse()
        event.accept()
