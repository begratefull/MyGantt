from PySide6.QtWidgets import QGraphicsObject, QGraphicsItem, QMenu
from PySide6.QtGui import QBrush, QColor, QPen, QPainter, QFontMetrics
from PySide6.QtCore import Qt, QRectF, Signal, QTimer


class GanttBlock(QGraphicsObject):
    block_dropped = Signal(str, float, float)
    assignee_changed = Signal(str, str)

    def __init__(self, project_data, x, y, width, height, day_width, due_x_offset=-1):
        super().__init__()
        self.setPos(x, y)
        self.data = project_data

        self.day_width = day_width
        self.rect = QRectF(0, 0, width, height)
        self.due_x_offset = due_x_offset

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.ItemIsSelectable)

        assignee = str(self.data.get('ASSIGNED TO', '')).strip().upper()
        status = str(self.data.get('STATUS', '')).strip().upper()
        raw_start = str(self.data.get('ENG START DATE', '')).strip()
        est_start = str(self.data.get('EST START DATE', '')).strip()
        est_days = str(self.data.get('EST DAYS', '')).strip()

        # Reverted to rich, bold solids and fixed the fuzzy matching
        if 'ADAM' in assignee:
            self.base_color = QColor("#2E7D32")  # Bold Green
        elif 'DAVID' in assignee or 'DAVE' in assignee:
            self.base_color = QColor("#C62828")  # Bold Red
        elif 'ANDY' in assignee:
            self.base_color = QColor("#1565C0")  # Bold Blue
        elif 'MATT' in assignee:
            self.base_color = QColor("#EF6C00")  # True Orange
        else:
            self.base_color = QColor("#888888")  # Grey

        # With heavy transparency over a dark canvas, white text is required for contrast
        self.text_color = QColor("#FFFFFF")

        self.can_move = True
        self.can_resize = True

        # --- TRANSPARENCY TIERS ---

        # 1. Actuals (Alpha 180 - The old 'Planned' look)
        actual_color = QColor(self.base_color)
        actual_color.setAlpha(180)

        # 2. Planned (Alpha 90 - Highly transparent)
        planned_color = QColor(self.base_color)
        planned_color.setAlpha(120)

        # 3. Ghost/Queue (Alpha 30 - Barely visible)
        ghost_color = QColor(self.base_color)
        ghost_color.setAlpha(120)

        # Apply the tiers based on rules
        if status == 'RELEASED FOR PRODUCTION' or status == 'COMPLETE':
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

    def boundingRect(self):
        return self.rect.adjusted(-2, -2, 2, 2)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(self.brush)

        if self.isSelected():
            painter.setPen(QPen(QColor("#FFFFFF"), 2))
        else:
            painter.setPen(Qt.NoPen)

        painter.drawRoundedRect(self.rect, 4, 4)

        if self.due_x_offset >= 0:
            # Reverted to a striking red line
            due_pen = QPen(QColor("#FF5252"), 3)
            painter.setPen(due_pen)

            # Draw the line inside the block bounds
            marker_x = min(max(0, self.due_x_offset), self.rect.width())
            painter.drawLine(int(marker_x), 0, int(marker_x), int(self.rect.height()))

        assignee = str(self.data.get('ASSIGNED TO', '')).strip()
        if assignee:
            painter.setPen(QPen(self.text_color))
            font = painter.font()
            font.setFamily("Segoe UI")
            font.setPointSize(8)
            font.setBold(True)
            painter.setFont(font)

            metrics = QFontMetrics(font)
            elided_text = metrics.elidedText(assignee, Qt.ElideRight, int(self.rect.width() - 8))

            text_rect = QRectF(self.rect.x() + 4, self.rect.y(), self.rect.width() - 8, self.rect.height())
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided_text)

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu { background-color: #252526; color: white; border: 1px solid #3E3E42; }
            QMenu::item:selected { background-color: #007ACC; }
        """)

        assign_menu = menu.addMenu("Assign To...")

        engineers = ["Adam T", "David M", "Andy C", "Matt M", "Unassigned"]
        for eng in engineers:
            action = assign_menu.addAction(eng)
            action.triggered.connect(lambda checked=False, e=eng: self.change_assignee(e))

        menu.exec(event.screenPos())

    def change_assignee(self, eng_name):
        smart_id = str(self.data.get('SMART_ID', ''))
        if smart_id:
            val = "" if eng_name == "Unassigned" else eng_name
            self.assignee_changed.emit(smart_id, val)

    def hoverMoveEvent(self, event):
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
            smart_id = str(self.data.get('SMART_ID', ''))
            if smart_id:
                QTimer.singleShot(0, lambda: self.block_dropped.emit(smart_id, self.x(), self.rect.width()))