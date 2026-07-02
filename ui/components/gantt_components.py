"""
Contains custom QGraphicsItems used for rendering the interactive Gantt chart.
These components handle their own mathematical drawing via QPainter, hover states,
and complex drag-and-drop timeline interactions supporting multi-selection.
"""

import logging
import re
from typing import Dict, Any, List, Optional

from PySide6.QtWidgets import (
    QGraphicsObject, QGraphicsItem, QWidget
)
from PySide6.QtGui import (
    QBrush, QColor, QPen, QPainter, QFontMetrics, QPolygonF, QPainterPath
)
from PySide6.QtCore import Qt, QRectF, Signal, QTimer, QPointF

from logic.constants import AppConstants

logger = logging.getLogger(__name__)


class DueDateMarker(QGraphicsItem):
    """
    Draws a small yellow triangle to indicate a project's target due date
    on the Gantt chart timeline.
    """
    def __init__(self, x: float, y: float, _height: float) -> None:
        """
        Initializes the marker at the specified X and Y coordinates.

        Args:
            x (float): The horizontal position on the scene.
            y (float): The vertical position on the scene.
            _height (float): The height of the row (unused for the marker itself, but kept for signature compatibility).
        """
        super().__init__()
        try:
            self.setPos(x, y)
            self.rect: QRectF = QRectF(-10, -5, 20, 20)
            self.setZValue(5)
        except Exception as e:
            logger.error(f"Error initializing DueDateMarker: {e}")

    def boundingRect(self) -> QRectF:
        """
        Defines the clickable and drawable bounds of the marker.

        Returns:
            QRectF: The bounding rectangle of the marker.
        """
        return self.rect

    def paint(self, painter: QPainter, option: Any, widget: Optional[QWidget] = None) -> None:
        """
        Paints the yellow warning triangle onto the scene.

        Args:
            painter (QPainter): The painter object used for drawing.
            option (Any): Style options for the item.
            widget (Optional[QWidget]): The widget being painted on.
        """
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(QColor("#FFD54F")))
            painter.setPen(QPen(QColor("#252526"), 1))

            triangle = QPolygonF([
                QPointF(-6, 0),
                QPointF(6, 0),
                QPointF(0, 12)
            ])
            painter.drawPolygon(triangle)
        except Exception as e:
            logger.error(f"Error painting DueDateMarker: {e}")


class GanttBlock(QGraphicsObject):
    """
    A custom QGraphicsObject representing a task or project parent on the Gantt grid.
    Handles rendering, drag-to-move, drag-to-resize, and robust bulk operations
    by preserving multi-selection states and bypassing C++ deletion limits during scene redraws.
    """
    block_dropped = Signal(str, float, float, bool, float, float)  # type: ignore
    assignee_changed = Signal(str, str)  # type: ignore

    def __init__(self, project_data: Dict[str, Any], x: float, y: float, width: float,
                 height: float, day_width: float, dynamic_engineers: Optional[List[str]] = None,
                 is_parent: bool = False, due_x_offset: float = -1) -> None:
        """
        Initializes a Gantt block representing either a parent project or a child line item.

        Args:
            project_data (Dict[str, Any]): The payload of data for this specific task.
            x (float): The horizontal start position.
            y (float): The vertical start position.
            width (float): The pixel width of the block.
            height (float): The pixel height of the block.
            day_width (float): The width of a single day column in pixels.
            dynamic_engineers (Optional[List[str]]): List of available engineers for assignments.
            is_parent (bool): Flag indicating if this is a parent aggregate block.
            due_x_offset (float): Offset for drawing due date indicators.
        """
        super().__init__()
        try:
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

            self._selection_state: Dict['GanttBlock', Dict[str, float]] = {}

            self.can_move: bool = True
            self.can_resize: bool = True
            self.is_started: bool = False

            self.setAcceptHoverEvents(True)
            self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)

            self.refresh_visuals()
        except Exception as e:
            logger.error(f"Error initializing GanttBlock: {e}")

    @property
    def data(self) -> Dict[str, Any]:  # type: ignore # noqa
        """
        Allows the controller to access the payload via item.data natively.

        Returns:
            Dict[str, Any]: The block's data dictionary.
        """
        return self.block_data

    def refresh_visuals(self) -> None:
        """
        Updates the colors, opacity, and interaction states of the block based on its data payload.
        Utilizes the centralized PROD_REQ_PATTERN to identify production and re-work items.
        """
        try:
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

            # Evaluate production logic using the centralized pattern
            is_prod = bool(re.search(AppConstants.PROD_REQ_PATTERN, req))

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
        except Exception as e:
            logger.error(f"Error refreshing GanttBlock visuals: {e}")

    def boundingRect(self) -> QRectF:
        """
        Defines the interactable boundaries of the block on the canvas.

        Returns:
            QRectF: The padded bounding rectangle.
        """
        try:
            return self.rect.adjusted(-2, -2, 2, 2)
        except Exception as e:
            logger.error(f"Error calculating bounding rect for GanttBlock: {e}")
            return QRectF()

    def paint(self, painter: QPainter, option: Any, widget: Optional[QWidget] = None) -> None:
        """
        Draws the visual representation of the block, including selection outlines,
        progress bars (started tasks), and text labels.

        Args:
            painter (QPainter): The active painter context.
            option (Any): Style options.
            widget (Optional[QWidget]): The widget being painted on.
        """
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

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
                elided_text = metrics.elidedText(label_text, Qt.TextElideMode.ElideRight,
                                                 int(self.rect.width() - text_x_offset - 4))

                text_rect = QRectF(
                    self.rect.x() + text_x_offset,
                    self.rect.y(),
                    self.rect.width() - text_x_offset - 4,
                    self.rect.height() if not self.is_parent else self.rect.height() - 8
                )
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided_text)
        except Exception as e:
            logger.error(f"Error painting GanttBlock: {e}")

    def _draw_shape(self, painter: QPainter) -> None:
        """
        Constructs and paints the geometric path of the block (polygon for parents, rounded rect for children).
        Handles drawing multi-colored segment slices for parent items with multiple assignees.

        Args:
            painter (QPainter): The active painter context.
        """
        try:
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
                painter.save()
                painter.setClipPath(path)

                req = str(self.block_data.get('REQUIREMENT', '')).strip().upper()

                # Check for PROD pattern to determine opacity
                alpha = 120 if re.search(AppConstants.PROD_REQ_PATTERN, req) else 60

                w = self.rect.width()
                h = self.rect.height()
                step = w / len(all_colors)

                painter.setPen(Qt.PenStyle.NoPen)
                for i, c_hex in enumerate(all_colors):
                    qc = QColor(c_hex)
                    qc.setAlpha(alpha)
                    painter.setBrush(QBrush(qc))

                    slice_poly = QPolygonF([
                        QPointF(i * step, 0),
                        QPointF((i + 1) * step, 0),
                        QPointF((i + 1) * step - h, h),
                        QPointF(i * step - h, h)
                    ])
                    painter.drawPolygon(slice_poly)

                painter.restore()

                if self.isSelected():
                    painter.setPen(QPen(QColor("#FFFFFF"), 2))
                else:
                    painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(path)
            else:
                painter.drawPath(path)
        except Exception as e:
            logger.error(f"Error drawing shape in GanttBlock: {e}")

    def _get_app_signal(self, signal_name: str) -> Any:
        """
        Traverses the UI widget hierarchy to find a specific application-level signal.

        Args:
            signal_name (str): The name of the signal to locate.

        Returns:
            Any: The signal object if found, otherwise None.
        """
        try:
            if not self.scene(): return None
            views = self.scene().views()
            if not views: return None

            parent = views[0].parentWidget()
            while parent:
                if hasattr(parent, signal_name):
                    return getattr(parent, signal_name)
                parent = parent.parentWidget()
        except Exception as e:
            logger.error(f"Error finding app signal {signal_name}: {e}")
        return None

    def hoverMoveEvent(self, event: Any) -> None:
        """
        Updates the cursor icon based on where the mouse is hovering over the block (move vs resize).

        Args:
            event (Any): The hover event object.
        """
        try:
            if not self.can_resize and not self.can_move:
                self.setCursor(Qt.CursorShape.ArrowCursor)
                return

            if self.can_resize and event.pos().x() >= self.rect.width() - 15:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                self.is_resizing_hover = True
            else:
                self.setCursor(Qt.CursorShape.OpenHandCursor if self.can_move else Qt.CursorShape.ArrowCursor)
                self.is_resizing_hover = False
        except Exception as e:
            logger.error(f"Error handling hover move event: {e}")

    def mousePressEvent(self, event: Any) -> None:
        """
        Handles the initiation of a drag or resize action, capturing the current
        multi-selection state if applicable.

        Args:
            event (Any): The mouse press event object.
        """
        try:
            is_multi = self.isSelected() and self.scene() and len(self.scene().selectedItems()) > 1

            if is_multi and event.button() == Qt.MouseButton.LeftButton:
                event.accept()  # Bypasses Qt's default clear selection
            else:
                super().mousePressEvent(event)

            if event.button() == Qt.MouseButton.LeftButton:
                self.start_pos = event.scenePos()
                self.start_scene_pos = self.scenePos()
                self.start_rect = QRectF(self.rect)

                self._selection_state.clear()
                items_to_track = [self]
                if self.isSelected() and self.scene():
                    items_to_track = [item for item in self.scene().selectedItems() if isinstance(item, GanttBlock)]

                for item in items_to_track:
                    self._selection_state[item] = {
                        "start_x": item.scenePos().x(),
                        "start_y": item.scenePos().y(),
                        "start_width": item.rect.width()
                    }

                if self.is_resizing_hover:
                    self.is_resizing = True
                    self.is_moving = False
                    event.accept()
                elif self.can_move:
                    self.setCursor(Qt.CursorShape.ClosedHandCursor)
                    self.is_moving = True
                    self.is_resizing = False
                    event.accept()

        except Exception as e:
            logger.error(f"Error handling mouse press event in GanttBlock: {e}")

    def mouseMoveEvent(self, event: Any) -> None:
        """
        Updates the block's geometry and position dynamically as the mouse is dragged.

        Args:
            event (Any): The mouse move event object.
        """
        try:
            if self.is_resizing:
                delta = event.scenePos().x() - self.start_pos.x()
                snapped_delta = round(delta / self.day_width) * self.day_width

                for item, state in self._selection_state.items():
                    if item.can_resize:
                        new_width = max(item.day_width, state["start_width"] + snapped_delta)
                        item.prepareGeometryChange()
                        item.rect.setWidth(new_width)
                        item.update()

            elif self.is_moving:
                delta = event.scenePos().x() - self.start_pos.x()
                snapped_delta = round(delta / self.day_width) * self.day_width

                for item, state in self._selection_state.items():
                    if item.can_move:
                        new_x = max(0.0, state["start_x"] + snapped_delta)
                        item.setPos(new_x, state["start_y"])
            else:
                super().mouseMoveEvent(event)
        except Exception as e:
            logger.error(f"Error handling mouse move event in GanttBlock: {e}")

    def mouseReleaseEvent(self, event: Any) -> None:
        """
        Completes a drag or resize operation, calculates the final offsets,
        and emits the block_dropped signal to commit changes.

        Args:
            event (Any): The mouse release event object.
        """
        try:
            self.setCursor(Qt.CursorShape.OpenHandCursor if self.can_move else Qt.CursorShape.ArrowCursor)

            was_resizing = self.is_resizing
            was_moving = self.is_moving

            self.is_resizing = False
            self.is_moving = False

            super().mouseReleaseEvent(event)

            if was_resizing or was_moving:
                global_sig = self._get_app_signal('block_dropped_signal')

                # MUST extract all payloads before emitting to prevent C++ Pointer deletion on scene clear
                drop_payloads = []
                for item, state in self._selection_state.items():
                    cx = item.x()
                    cw = item.rect.width()
                    ip = item.is_parent
                    delta_x = cx - state["start_x"]
                    delta_w = cw - state["start_width"]

                    if delta_x != 0 or delta_w != 0:
                        tid = str(item.block_data.get('PROJECT_ID', '')) if ip else str(
                            item.block_data.get('SMART_ID', ''))
                        if tid and tid.lower() != 'nan':
                            drop_payloads.append((tid, cx, cw, ip, delta_x, delta_w))

                self._selection_state.clear()

                for payload in drop_payloads:
                    tid, cx, cw, ip, dx, dw = payload
                    if global_sig:
                        global_sig.emit(tid, cx, cw, ip, dx, dw)
                    else:
                        def safe_emit(t=tid, c_x=cx, c_w=cw, is_p=ip, d_x=dx, d_w=dw):
                            try:
                                self.block_dropped.emit(t, c_x, c_w, is_p, d_x, d_w)
                            except RuntimeError:
                                pass

                        QTimer.singleShot(0, safe_emit)

        except Exception as e:
            logger.error(f"Error handling mouse release event in GanttBlock: {e}")