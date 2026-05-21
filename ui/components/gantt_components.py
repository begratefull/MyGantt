"""
Contains custom QGraphicsItems used for rendering the interactive Gantt chart.
These components handle their own mathematical drawing via QPainter, hover states,
and complex drag-and-drop timeline interactions.
"""

from typing import Dict, Any, List, Optional

from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsItem, QMenu, QWidget
)
from PySide6.QtGui import (
    QBrush, QColor, QPen, QPainter, QFontMetrics, QPolygonF, QPainterPath
)
from PySide6.QtCore import Qt, QRectF, Signal, QTimer, QPointF


class DueDateMarker(QGraphicsItem):
    """Draws a small yellow triangle to indicate a project's target due date."""
    def __init__(self, x: float, y: float, _height: float) -> None:
        super().__init__()
        self.setPos(x, y)
        self.rect: QRectF = QRectF(-10, -5, 20, 20)
        self.setZValue(5)

    def boundingRect(self) -> QRectF:
        return self.rect

    def paint(self, painter: QPainter, option: Any, widget: Optional[QWidget] = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(QColor("#FFD54F")))
        painter.setPen(QPen(QColor("#252526"), 1))

        triangle = QPolygonF([
            QPointF(-6, 0),
            QPointF(6, 0),
            QPointF(0, 12)
        ])
        painter.drawPolygon(triangle)


class GanttBlock(QGraphicsObject):
    block_dropped = Signal(str, float, float, bool, float, float) # type: ignore
    assignee_changed = Signal(str, str) # type: ignore

    def __init__(self, project_data: Dict[str, Any], x: float, y: float, width: float,
                 height: float, day_width: float, dynamic_engineers: Optional[List[str]] = None,
                 is_parent: bool = False, due_x_offset: float = -1) -> None:
        super().__init__()
        self.setPos(x, y)

        self.block_data: Dict[str, Any] = project_data
        self.day_width: float = day_width
        self.rect: QRectF = QRectF(0, 0, width, height)

        self.is_parent: bool = is_parent
        self.dynamic_engineers: List[str] = dynamic_engineers if dynamic_engineers else []
        self.due_x_offset: float = due_x_offset

        self.base_color: QColor = QColor()
        self.text_color: QColor = QColor()
        self.brush: QBrush = QBrush()

        self.is_resizing_hover: bool = False
        self.is_resizing: bool = False
        self.is_moving: bool = False

        self.start_pos: QPointF = QPointF()
        self.start_scene_pos: QPointF = QPointF()
        self.start_rect: QRectF = QRectF()

        self.can_move: bool = True
        self.can_resize: bool = True
        self.is_started: bool = False

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

        self.refresh_visuals()

    @property
    def data(self) -> Dict[str, Any]: # type: ignore # noqa
        """Allows controller.py to access the payload via item.data without breaking Qt's native C++ methods."""
        return self.block_data

    def refresh_visuals(self) -> None:
        assignee = str(self.block_data.get('ASSIGNED TO', '')).strip().upper()
        status = str(self.block_data.get('STATUS', '')).strip().upper()
        raw_start = str(self.block_data.get('ENG START DATE', '')).strip()
        est_start = str(self.block_data.get('EST START DATE', '')).strip()
        est_days = str(self.block_data.get('EST DAYS', '')).strip()
        req = str(self.block_data.get('REQUIREMENT', '')).strip().upper()

        self.is_started = bool(raw_start)
        hex_color = str(self.block_data.get('HEX_COLOR', '#007ACC')).strip()

        self.base_color = QColor(hex_color)
        self.text_color = QColor("#FFFFFF")

        actual_color = QColor(self.base_color)
        planned_color = QColor(self.base_color)
        ghost_color = QColor(self.base_color)

        is_prod = 'PROD' in req

        if not is_prod:
            actual_color.setAlpha(90)
            planned_color.setAlpha(50)
            ghost_color.setAlpha(40)
            self.text_color = QColor("#AAAAAA")
        else:
            actual_color.setAlpha(180)
            planned_color.setAlpha(120)
            ghost_color.setAlpha(120)

        if self.is_parent:
            self.text_color = QColor("#E0E0E0") if is_prod else QColor("#888888")

            if assignee == "MULTIPLE":
                self.brush = QBrush(Qt.BrushStyle.NoBrush)
            elif assignee and assignee != "UNASSIGNED":
                self.brush = QBrush(actual_color)
            else:
                self.brush = QBrush(QColor("#454548"))
        elif status in ('RELEASED FOR PRODUCTION', 'COMPLETE'):
            self.brush = QBrush(actual_color)
        elif raw_start:
            self.brush = QBrush(actual_color)
        elif est_start and est_days:
            self.brush = QBrush(planned_color)
        else:
            self.brush = QBrush(ghost_color)

        self.can_move = True
        self.can_resize = not self.is_parent

        if status in ('RELEASED FOR PRODUCTION', 'COMPLETE'):
            self.can_move = False
            self.can_resize = False
        elif self.is_started:
            self.can_move = False

        self.update()

    def boundingRect(self) -> QRectF:
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter: QPainter, option: Any, widget: Optional[QWidget] = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Let _draw_shape handle both the fill and the background clipping
        painter.setBrush(self.brush)
        if self.isSelected():
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
        else:
            painter.setPen(Qt.PenStyle.NoPen)

        self._draw_shape(painter)

        if self.is_started:
            painter.setPen(QPen(QColor("#A0A0A0"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap))
            y_offset = 2 if not self.is_parent else 0
            painter.drawLine(
                QPointF(self.rect.x() + 2, self.rect.y() + y_offset),
                QPointF(self.rect.x() + 2, self.rect.y() + self.rect.height() - y_offset)
            )

        if self.is_parent:
            label_text = str(self.block_data.get('PROJECT NAME', 'Unknown Project')).strip()
        else:
            label_text = str(self.block_data.get('ASSIGNED TO', '')).strip()

        if label_text:
            painter.setPen(QPen(self.text_color))
            font = painter.font()
            font.setFamily("Segoe UI")
            font.setPointSize(8)
            font.setBold(True if self.is_parent else False)
            painter.setFont(font)

            metrics = QFontMetrics(font)
            text_x_offset = 8 if self.is_started else 4
            elided_text = metrics.elidedText(label_text, Qt.TextElideMode.ElideRight, int(self.rect.width() - text_x_offset - 4))

            text_rect = QRectF(
                self.rect.x() + text_x_offset,
                self.rect.y(),
                self.rect.width() - text_x_offset - 4,
                self.rect.height() if not self.is_parent else self.rect.height() - 8
            )
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_text)

    def _draw_shape(self, painter: QPainter) -> None:
        # 1. Define the outline shape of the block
        path = QPainterPath()
        if self.is_parent:
            poly = QPolygonF([
                QPointF(0, 0),
                QPointF(self.rect.width(), 0),
                QPointF(self.rect.width(), self.rect.height()),
                QPointF(self.rect.width() - 8, self.rect.height() - 8),
                QPointF(8, self.rect.height() - 8),
                QPointF(0, self.rect.height())
            ])
            path.addPolygon(poly)
        else:
            path.addRoundedRect(self.rect, 4.0, 4.0)

        assignee = str(self.block_data.get('ASSIGNED TO', '')).strip().upper()
        all_colors = self.block_data.get('ALL_COLORS', [])

        if self.is_parent and assignee == "MULTIPLE" and len(all_colors) > 1:
            # 2. Save state and clip to the parent's chamfered outline
            painter.save()
            painter.setClipPath(path)

            req = str(self.block_data.get('REQUIREMENT', '')).strip().upper()
            alpha = 120 if 'PROD' in req else 60

            w = self.rect.width()
            h = self.rect.height()
            step = w / len(all_colors)

            painter.setPen(Qt.PenStyle.NoPen)
            for i, c_hex in enumerate(all_colors):
                qc = QColor(c_hex)
                qc.setAlpha(alpha)
                painter.setBrush(QBrush(qc))

                # 3. Draw solid 45-degree slanted blocks!
                slice_poly = QPolygonF([
                    QPointF(i * step, 0),
                    QPointF((i + 1) * step, 0),
                    QPointF((i + 1) * step - h, h),
                    QPointF(i * step - h, h)
                ])
                painter.drawPolygon(slice_poly)

            painter.restore()

            # 4. Redraw the border cleanly over the clipped slices
            if self.isSelected():
                painter.setPen(QPen(QColor("#FFFFFF"), 2))
            else:
                painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        else:
            # Normal single-color fill
            painter.drawPath(path)

    def contextMenuEvent(self, event: Any) -> None:
        menu = QMenu()
        assign_menu = menu.addMenu("Assign To...")

        for eng in self.dynamic_engineers:
            action = assign_menu.addAction(eng)
            action.triggered.connect(lambda checked=False, e=eng: self.change_assignee(e)) # type: ignore

        menu.exec(event.screenPos())

    def change_assignee(self, eng_name: str) -> None:
        target_id = str(self.block_data.get('PROJECT_ID', '')) if self.is_parent else str(self.block_data.get('SMART_ID', ''))
        if target_id:
            val = "" if eng_name == "Unassigned" else eng_name
            def safe_emit() -> None:
                try:
                    self.assignee_changed.emit(target_id, val)
                except RuntimeError:
                    pass
            QTimer.singleShot(0, safe_emit)

    def hoverMoveEvent(self, event: Any) -> None:
        if not self.can_resize and not self.can_move:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if self.can_resize and event.pos().x() >= self.rect.width() - 15:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            self.is_resizing_hover = True
        else:
            self.setCursor(Qt.CursorShape.OpenHandCursor if self.can_move else Qt.CursorShape.ArrowCursor)
            self.is_resizing_hover = False

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.start_pos = event.scenePos()
            self.start_rect = QRectF(self.rect)
            self.start_scene_pos = self.scenePos()

            if self.is_resizing_hover:
                self.is_resizing = True
                self.is_moving = False
                event.accept()
            elif self.can_move:
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.is_moving = True
                self.is_resizing = False
                event.accept()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:
        if self.is_resizing:
            delta = event.scenePos().x() - self.start_pos.x()
            snapped_delta = round(delta / self.day_width) * self.day_width
            new_width = max(self.day_width, self.start_rect.width() + snapped_delta)

            self.prepareGeometryChange()
            self.rect.setWidth(new_width)
            self.update()

        elif self.is_moving:
            delta = event.scenePos().x() - self.start_pos.x()
            snapped_delta = round(delta / self.day_width) * self.day_width
            new_x = max(0.0, self.start_scene_pos.x() + snapped_delta)

            self.setPos(new_x, self.start_scene_pos.y())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        self.setCursor(Qt.CursorShape.OpenHandCursor if self.can_move else Qt.CursorShape.ArrowCursor)

        was_resizing = self.is_resizing
        was_moving = self.is_moving

        self.is_resizing = False
        self.is_moving = False

        super().mouseReleaseEvent(event)

        if was_resizing or was_moving:
            target_id = str(self.block_data.get('PROJECT_ID', '')) if self.is_parent else str(self.block_data.get('SMART_ID', ''))

            if target_id:
                cx = self.x()
                cw = self.rect.width()
                ip = self.is_parent
                delta_x = cx - self.start_scene_pos.x()
                delta_w = cw - self.start_rect.width()

                def safe_emit() -> None:
                    try:
                        self.block_dropped.emit(target_id, cx, cw, ip, delta_x, delta_w)
                    except RuntimeError:
                        pass
                QTimer.singleShot(0, safe_emit)