from PySide6.QtWidgets import QGraphicsObject, QGraphicsItem
from PySide6.QtGui import QBrush, QColor, QPen, QPainter
from PySide6.QtCore import Qt, QRectF


class GanttBlock(QGraphicsObject):
    """An interactive, rounded task block for the Gantt Canvas."""

    def __init__(self, project_data, x, y, width, height):
        super().__init__()
        self.setPos(x, y)
        self.data = project_data

        # Define the exact size of this specific block
        self.rect = QRectF(0, 0, width, height)

        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)

        # Engineer Color Dictionary
        self.engineer_colors = {
            'ADAM T': QColor("#2E7D32"),  # Green
            'DAVE M': QColor("#C62828"),  # Red
            'ANDY C': QColor("#1565C0"),  # Blue
            'MATT M': QColor("#EF6C00"),  # Orange
        }

        assignee = str(self.data.get('ASSIGNED TO', '')).strip().upper()
        status = str(self.data.get('STATUS', '')).strip().upper()
        raw_start = str(self.data.get('ENG START DATE', '')).strip()
        est_start = str(self.data.get('EST START DATE', '')).strip()

        base_color = self.engineer_colors.get(assignee, QColor("#666666"))

        # Styling Logic
        if status == 'COMPLETE':
            self.brush = QBrush(base_color)
            self.setFlag(QGraphicsItem.ItemIsMovable, False)
        elif raw_start:
            self.brush = QBrush(base_color)
        elif est_start:
            # Semi-transparent for planned tasks
            light_color = QColor(base_color)
            light_color.setAlpha(120)
            self.brush = QBrush(light_color)
        else:
            self.brush = QBrush(QColor(60, 60, 65, 80))

    def boundingRect(self):
        """Required for QGraphicsObject: Tells the engine the clickable area."""
        return self.rect

    def paint(self, painter, option, widget=None):
        """Custom painting for beautiful rounded corners."""
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.brush)
        # Draw a rectangle with a 4px corner radius!
        painter.drawRoundedRect(self.rect, 4, 4)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            pass
        return super().itemChange(change, value)