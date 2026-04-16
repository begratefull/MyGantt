"""
gantt_components.py

Contains custom QGraphicsItems used for rendering the interactive Gantt chart.
These components handle their own drawing, hover states, and drag/drop interactions.
"""

from PySide6.QtWidgets import QGraphicsObject, QGraphicsItem, QMenu
from PySide6.QtGui import QBrush, QColor, QPen, QPainter, QFontMetrics, QPolygonF
from PySide6.QtCore import Qt, QRectF, Signal, QTimer, QPointF

# We keep this as a color fallback for known engineers to keep the charts pretty!
TEAM_CONFIG = {
    "ADAM": "#2E7D32",
    "DAVID": "#C62828",
    "DAVE": "#C62828",
    "ANDY": "#1565C0",
    "MATT": "#EF6C00",
}


class DueDateMarker(QGraphicsItem):
    """
    A simple yellow triangle graphic used to indicate the Engineering Due Date
    on the Gantt canvas.
    """

    def __init__(self, x: float, y: float, height: float):
        super().__init__()
        self.setPos(x, y)
        # Bounding box for the triangle
        self.rect = QRectF(-6, 0, 12, 12)
        self.setZValue(5)

    def boundingRect(self) -> QRectF:
        """Returns the bounding rectangle required by QGraphicsItem."""
        return self.rect

    def paint(self, painter: QPainter, option, widget=None):
        """Paints the yellow triangle marker."""
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
    """
    The primary interactive block representing a task or order on the Gantt chart.
    Supports dragging, resizing (for children), and right-click context menus.

    Signals:
        block_dropped (str, float, float, bool): Emitted when a block is moved or resized.
            Passes (target_id, new_x, new_width, is_parent).
        assignee_changed (str, str): Emitted when a new assignee is picked from the context menu.
            Passes (target_id, new_assignee_name).
    """
    block_dropped = Signal(str, float, float, bool)
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

        assignee = str(self.data.get('ASSIGNED TO', '')).strip().upper()
        status = str(self.data.get('STATUS', '')).strip().upper()
        raw_start = str(self.data.get('ENG START DATE', '')).strip()
        est_start = str(self.data.get('EST START DATE', '')).strip()
        est_days = str(self.data.get('EST DAYS', '')).strip()

        # Determine base color based on engineer assignment
        self.base_color = QColor("#888888")
        for name, hex_color in TEAM_CONFIG.items():
            if name in assignee:
                self.base_color = QColor(hex_color)
                break

        self.text_color = QColor("#FFFFFF")
        self.can_move = True
        self.can_resize = not self.is_parent  # Prevent resizing parent blocks directly for now

        # --- TRANSPARENCY TIERS ---
        actual_color = QColor(self.base_color)
        actual_color.setAlpha(180)

        planned_color = QColor(self.base_color)
        planned_color.setAlpha(120)

        ghost_color = QColor(self.base_color)
        ghost_color.setAlpha(120)

        # Style logic based on status and dates
        if self.is_parent:
            self.brush = QBrush(QColor("#454548"))  # Distinct grey for parent groups
            self.text_color = QColor("#E0E0E0")
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

    def boundingRect(self) -> QRectF:
        """Returns the bounding rectangle, padded slightly for the selection highlight."""
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter: QPainter, option, widget=None):
        """Paints the block onto the scene based on its state (parent vs child)."""
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(self.brush)

        if self.isSelected():
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
        else:
            painter.setPen(Qt.NoPen)

        # Draw a summary bar shape if it's a parent, otherwise a rounded rect
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

        # Draw Label Text
        label_text = f"Order: {self.data.get('PROJECT_ID', 'Unk')}" if self.is_parent else str(
            self.data.get('ASSIGNED TO', '')).strip()

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

    def contextMenuEvent(self, event):
        """Constructs and displays the right-click menu for reassignment."""
        if self.is_parent:
            return  # Let's disable assigning a whole order to one person for now

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
        """
        Safely triggers the assignment update.
        Uses QTimer to prevent the UI from freezing by allowing the context menu
        to finish closing before the controller triggers a full scene redraw.
        """
        smart_id = str(self.data.get('SMART_ID', ''))
        if smart_id:
            val = "" if eng_name == "Unassigned" else eng_name
            # This single line fixes the crashing/freezing bug!
            QTimer.singleShot(0, lambda: self.assignee_changed.emit(smart_id, val))

    def hoverMoveEvent(self, event):
        """Changes the cursor depending on whether the user is hovering over the resize zone."""
        if not self.can_resize and not self.can_move:
            self.setCursor(Qt.ArrowCursor)
            return

        if self.can_resize and event.pos().x() >= self.rect.width() - 10:
            self.setCursor(Qt.SizeHorCursor)
            self.is_resizing_hover = True
        else:
            self.setCursor(Qt.OpenHandCursor if self.can_move else Qt.ArrowCursor)
            self.is_resizing_hover = False

    def mousePressEvent(self, event):
        """Captures the starting position for drag and drop or resizing operations."""
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
        """Calculates delta position and snaps movement/resizing to the grid."""
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
        """Emits the block_dropped signal if a move or resize actually occurred."""
        self.setCursor(Qt.OpenHandCursor if self.can_move else Qt.ArrowCursor)

        was_resizing = getattr(self, 'is_resizing', False)
        was_moving = getattr(self, 'is_moving', False)

        self.is_resizing = False
        self.is_moving = False

        super().mouseReleaseEvent(event)

        if was_resizing or was_moving:
            target_id = str(self.data.get('PROJECT_ID', '')) if self.is_parent else str(self.data.get('SMART_ID', ''))
            if target_id:
                QTimer.singleShot(0, lambda: self.block_dropped.emit(target_id, self.x(), self.rect.width(),
                                                                     self.is_parent))