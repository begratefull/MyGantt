"""
gantt_components.py

Contains custom QGraphicsItems used for rendering the interactive Gantt chart.
These components handle their own drawing, hover states, and drag/drop interactions.
"""

from PySide6.QtWidgets import QGraphicsObject, QGraphicsItem, QMenu
from PySide6.QtGui import QBrush, QColor, QPen, QPainter, QFontMetrics, QPolygonF
from PySide6.QtCore import Qt, QRectF, Signal, QTimer, QPointF

TEAM_CONFIG = {
    "ADAM": "#2E7D32",
    "DAVID": "#C62828",
    "DAVE": "#C62828",
    "ANDY": "#1565C0",
    "MATT": "#EF6C00",
}


class DueDateMarker(QGraphicsItem):
    def __init__(self, x: float, y: float, height: float):
        super().__init__()
        self.setPos(x, y)
        self.rect = QRectF(-6, 0, 12, 12)
        self.setZValue(5)

    def boundingRect(self) -> QRectF:
        return self.rect

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor("#FFD54F")))
        painter.setPen(QPen(QColor("#252526"), 1))

        triangle = QPolygonF([
            QPointF(-6, 0),
            QPointF(6, 0),
            QPointF(0, 12)
        ])
        painter.drawPolygon(triangle)


class GanttBlock(QGraphicsObject):
    # Added delta_x (float) to the signal so the controller knows how far to push children!
    block_dropped = Signal(str, float, float, bool, float)
    assignee_changed = Signal(str, str)

    def __init__(self, project_data: dict, x: float, y: float, width: float, height: float,
                 day_width: float, dynamic_engineers: list = None, is_parent: bool = False,
                 due_x_offset: float = -1):
        super().__init__()
        self.setPos(x, y)
        self.data = project_data
        self.day_width = day_width
        self.rect = QRectF(0, 0, width, height)

        self.is_parent = is_parent
        self.dynamic_engineers = dynamic_engineers if dynamic_engineers else []
        self.due_x_offset = due_x_offset

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        self.can_move = True
        self.can_resize = True
        self.refresh_visuals()

    def refresh_visuals(self):
        """Locally recalculates colors and labels instantly without requiring a full scene redraw."""
        assignee = str(self.data.get('ASSIGNED TO', '')).strip().upper()
        status = str(self.data.get('STATUS', '')).strip().upper()
        raw_start = str(self.data.get('ENG START DATE', '')).strip()
        est_start = str(self.data.get('EST START DATE', '')).strip()
        est_days = str(self.data.get('EST DAYS', '')).strip()

        self.base_color = QColor("#888888")
        if assignee == "MULTIPLE":
            self.base_color = QColor("#AAAAAA")
        else:
            for name, hex_color in TEAM_CONFIG.items():
                if name in assignee:
                    self.base_color = QColor(hex_color)
                    break

        self.text_color = QColor("#FFFFFF")

        actual_color = QColor(self.base_color)
        actual_color.setAlpha(180)
        planned_color = QColor(self.base_color)
        planned_color.setAlpha(120)
        ghost_color = QColor(self.base_color)
        ghost_color.setAlpha(120)

        if self.is_parent:
            self.text_color = QColor("#E0E0E0")
            if assignee == "MULTIPLE":
                self.brush = QBrush(self.base_color, Qt.BDiagPattern)
            elif assignee and assignee != "UNASSIGNED":
                self.brush = QBrush(actual_color)
            else:
                self.brush = QBrush(QColor("#454548"))

        elif status == 'RELEASED FOR PRODUCTION' or status == 'COMPLETE':
            self.brush = QBrush(actual_color)
            self.can_move = False
            self.can_resize = False
        elif raw_start:
            self.brush = QBrush(actual_color)
            self.can_move = False
        elif est_start and est_days:
            self.brush = QBrush(planned_color)
        else:
            self.brush = QBrush(ghost_color)

        self.update()

    def boundingRect(self) -> QRectF:
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)

        if self.is_parent and self.brush.style() == Qt.BDiagPattern:
            painter.setBrush(QBrush(QColor("#2D2D30")))
            painter.setPen(Qt.NoPen)
            self._draw_shape(painter)

        painter.setBrush(self.brush)
        if self.isSelected():
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
        else:
            painter.setPen(Qt.NoPen)

        self._draw_shape(painter)

        label_text = f"Order: {self.data.get('PROJECT_ID', 'Unk')}" if self.is_parent else str(self.data.get('ASSIGNED TO', '')).strip()
        if label_text:
            painter.setPen(QPen(self.text_color))
            font = painter.font()
            font.setFamily("Segoe UI")
            font.setPointSize(8)
            font.setBold(True if self.is_parent else False)
            painter.setFont(font)

            metrics = QFontMetrics(font)
            elided_text = metrics.elidedText(label_text, Qt.ElideRight, int(self.rect.width() - 8))

            text_rect = QRectF(self.rect.x() + 4, self.rect.y(), self.rect.width() - 8,
                               self.rect.height() if not self.is_parent else self.rect.height() - 8)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided_text)

    def _draw_shape(self, painter):
        if self.is_parent:
            poly = QPolygonF([
                QPointF(0, 0),
                QPointF(self.rect.width(), 0),
                QPointF(self.rect.width(), self.rect.height()),
                QPointF(self.rect.width() - 8, self.rect.height() - 8),
                QPointF(8, self.rect.height() - 8),
                QPointF(0, self.rect.height())
            ])
            painter.drawPolygon(poly)
        else:
            painter.drawRoundedRect(self.rect, 4, 4)

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #252526; color: white; border: 1px solid #3E3E42; }
            QMenu::item:selected { background-color: #007ACC; }
        """)

        assign_menu = menu.addMenu("Assign To...")

        for eng in self.dynamic_engineers:
            action = assign_menu.addAction(eng)
            action.triggered.connect(lambda checked=False, e=eng: self.change_assignee(e))

        menu.exec(event.screenPos())

    def change_assignee(self, eng_name: str):
        target_id = str(self.data.get('PROJECT_ID', '')) if self.is_parent else str(self.data.get('SMART_ID', ''))
        if target_id:
            val = "" if eng_name == "Unassigned" else eng_name
            def safe_emit():
                try:
                    self.assignee_changed.emit(target_id, val)
                except RuntimeError:
                    pass
            QTimer.singleShot(0, safe_emit)

    def hoverMoveEvent(self, event):
        if not self.can_resize and not self.can_move:
            self.setCursor(Qt.ArrowCursor)
            return

        if self.can_resize and event.pos().x() >= self.rect.width() - 15:
            self.setCursor(Qt.SizeHorCursor)
            self.is_resizing_hover = True
        else:
            self.setCursor(Qt.OpenHandCursor if self.can_move else Qt.ArrowCursor)
            self.is_resizing_hover = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.scenePos()
            self.start_rect = QRectF(self.rect)
            self.start_scene_pos = self.scenePos()

            if getattr(self, 'is_resizing_hover', False):
                self.is_resizing = True
                self.is_moving = False
                event.accept()
            elif self.can_move:
                self.setCursor(Qt.ClosedHandCursor)
                self.is_moving = True
                self.is_resizing = False
                event.accept()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, 'is_resizing', False):
            delta = event.scenePos().x() - self.start_pos.x()
            snapped_delta = round(delta / self.day_width) * self.day_width
            new_width = max(self.day_width, self.start_rect.width() + snapped_delta)

            self.prepareGeometryChange()
            self.rect.setWidth(new_width)
            self.update()

        elif getattr(self, 'is_moving', False):
            delta = event.scenePos().x() - self.start_pos.x()
            snapped_delta = round(delta / self.day_width) * self.day_width
            new_x = max(0, self.start_scene_pos.x() + snapped_delta)
            self.setPos(new_x, self.start_scene_pos.y())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.setCursor(Qt.OpenHandCursor if self.can_move else Qt.ArrowCursor)

        was_resizing = getattr(self, 'is_resizing', False)
        was_moving = getattr(self, 'is_moving', False)

        self.is_resizing = False
        self.is_moving = False

        super().mouseReleaseEvent(event)

        if was_resizing or was_moving:
            target_id = str(self.data.get('PROJECT_ID', '')) if self.is_parent else str(self.data.get('SMART_ID', ''))
            if target_id:
                cx = float(self.x())
                cw = float(self.rect.width())
                ip = bool(self.is_parent)
                delta_x = float(cx - self.start_scene_pos.x())

                def safe_emit():
                    try:
                        self.block_dropped.emit(target_id, cx, cw, ip, delta_x)
                    except RuntimeError:
                        pass
                QTimer.singleShot(0, safe_emit)