"""
Provides the Interactive Gantt Chart interface.
"""

from typing import Optional, List, Dict, Any
import pandas as pd
import numpy as np
from logic.constants import AppConstants

from PySide6.QtCore import Qt, Signal, QRectF, QRect, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QMouseEvent, QFont, QWheelEvent, QBrush
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QComboBox, QSplitter, QTableWidget, QAbstractItemView,
    QGraphicsView, QGraphicsScene, QFormLayout, QLineEdit,
    QTableWidgetItem, QHeaderView
)

from ui.components.gantt_components import GanttBlock, DueDateMarker


class GanttView(QGraphicsView):
    empty_clicked = Signal()

    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setObjectName("CanvasView")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.itemAt(event.pos()) and self.empty_clicked:
                self.empty_clicked.emit()

    def wheelEvent(self, event: QWheelEvent) -> None:
        """
        Intercepts mouse wheel scrolling. If Shift is held down,
        translates the vertical wheel movement into horizontal scrolling.
        """
        if event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            h_scrollbar = self.horizontalScrollBar()
            scroll_amount = event.angleDelta().y()
            h_scrollbar.setValue(h_scrollbar.value() - scroll_amount)
            event.accept()
        else:
            super().wheelEvent(event)


class GanttGridScene(QGraphicsScene):
    def __init__(self, day_width: int, row_height: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.day_width = day_width
        self.row_height = row_height

    def drawBackground(self, painter: QPainter, rect: QRect | QRectF) -> None:
        painter.fillRect(rect, QColor("#1E1E1E"))

        row_pen = QPen(QColor("#252526"))
        col_pen = QPen(QColor("#3E3E42"))
        col_pen.setStyle(Qt.PenStyle.DotLine)

        top_y = int(rect.top()) - (int(rect.top()) % self.row_height)
        for y in range(top_y, int(rect.bottom()), self.row_height):
            painter.setPen(row_pen)
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)

        left_x = int(rect.left()) - (int(rect.left()) % self.day_width)
        for x in range(left_x, int(rect.right()), self.day_width):
            painter.setPen(col_pen)
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))


class GanttScreenWidget(QWidget):

    block_dropped_signal = Signal(str, float, float, bool, float, float)
    assignee_changed_signal = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()

        self.day_width: int = 25
        self.row_height: int = 36
        self.initial_scroll_done: bool = False
        self.day_zero: Optional[pd.Timestamp] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        gantt_main_layout = QVBoxLayout(self)
        gantt_main_layout.setContentsMargins(0, 0, 0, 0)

        gantt_header_layout = QHBoxLayout()
        gantt_header_layout.setContentsMargins(0, 0, 0, 10)

        gantt_header = QLabel("Interactive Gantt Chart")
        gantt_header.setObjectName("Header")
        gantt_header_layout.addWidget(gantt_header)
        gantt_header_layout.addStretch()

        filter_lbl = QLabel("Filters:")
        filter_lbl.setObjectName("FilterLabel")
        gantt_header_layout.addWidget(filter_lbl)

        self.filter_team = QComboBox()
        self.filter_team.addItem("All Teams")

        self.filter_req = QComboBox()
        self.filter_req.addItem("All Reqs")

        self.filter_status = QComboBox()
        self.filter_status.addItems(["All Status", "Active", "Complete"])
        self.filter_status.setCurrentText("Active")

        gantt_header_layout.addWidget(self.filter_team)
        gantt_header_layout.addWidget(self.filter_req)
        gantt_header_layout.addWidget(self.filter_status)

        gantt_header_layout.addSpacing(10)
        sort_lbl = QLabel("Sort By:")
        sort_lbl.setObjectName("FilterLabel")
        gantt_header_layout.addWidget(sort_lbl)

        self.sort_by = QComboBox()
        self.sort_by.addItems(["Start Date", "Eng Due Date", "ESD"])
        gantt_header_layout.addWidget(self.sort_by)

        gantt_main_layout.addLayout(gantt_header_layout)

        gantt_body_layout = QHBoxLayout()
        gantt_body_layout.setSpacing(15)

        self.unified_gantt_card = QFrame()
        self.unified_gantt_card.setObjectName("TableWell")
        unified_layout = QVBoxLayout(self.unified_gantt_card)
        unified_layout.setContentsMargins(0, 0, 0, 0)
        unified_layout.setSpacing(0)

        self.gantt_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.info_table = QTableWidget()
        self.info_table.setObjectName("LeftTable")
        self.info_table.setColumnCount(5)
        self.info_table.setHorizontalHeaderLabels(["Req.", "Quote", "Project", "ESD", "Status"])
        self.info_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.info_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.info_table.setMouseTracking(True)
        self.info_table.viewport().setMouseTracking(True)

        self.info_table.verticalHeader().setDefaultSectionSize(self.row_height)
        self.info_table.verticalHeader().setVisible(False)
        self.info_table.horizontalHeader().setMinimumHeight(45)
        self.info_table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.info_table.setShowGrid(False)
        self.info_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.info_table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.info_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.info_table.horizontalHeader().setStretchLastSection(True)
        self.info_table.setMinimumWidth(250)

        self.canvas_container = QFrame()
        canvas_layout = QVBoxLayout(self.canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)

        self.header_scene = QGraphicsScene()
        self.header_view = QGraphicsView(self.header_scene)
        self.header_view.setFixedHeight(45)
        self.header_view.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.header_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.header_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.header_view.setObjectName("HeaderView")

        self.gantt_scene = GanttGridScene(day_width=self.day_width, row_height=self.row_height)
        self.gantt_view = GanttView(self.gantt_scene)

        self.gantt_view.horizontalScrollBar().valueChanged.connect(self.header_view.horizontalScrollBar().setValue)
        self.header_view.horizontalScrollBar().valueChanged.connect(self.gantt_view.horizontalScrollBar().setValue)
        self.info_table.verticalScrollBar().valueChanged.connect(self.gantt_view.verticalScrollBar().setValue)
        self.gantt_view.verticalScrollBar().valueChanged.connect(self.info_table.verticalScrollBar().setValue)

        canvas_layout.addWidget(self.header_view)
        canvas_layout.addWidget(self.gantt_view)

        self.gantt_splitter.addWidget(self.info_table)
        self.gantt_splitter.addWidget(self.canvas_container)
        self.gantt_splitter.setStretchFactor(0, 0)
        self.gantt_splitter.setStretchFactor(1, 1)

        self.gantt_splitter.setSizes([650, 800])
        unified_layout.addWidget(self.gantt_splitter)

        self.kpi_panel = QFrame()
        self.kpi_panel.setObjectName("TableWell")
        self.kpi_panel.setFixedWidth(300)
        self.kpi_panel.hide()

        kpi_layout = QVBoxLayout(self.kpi_panel)
        kpi_layout.setContentsMargins(20, 20, 20, 20)
        kpi_layout.setSpacing(15)

        self.kpi_title = QLabel("Job Inspector")
        self.kpi_title.setObjectName("Header")
        kpi_layout.addWidget(self.kpi_title)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form_layout.setVerticalSpacing(15)

        self.inp_smart_id = QLineEdit()
        self.inp_smart_id.hide()
        self.inp_est_days = QLineEdit()

        self.inp_assignee = QComboBox()
        self.inp_assignee.addItem("Unassigned")

        self.kpi_order = QLabel("--")
        self.kpi_quote = QLabel("--")
        self.kpi_req = QLabel("--")
        self.kpi_esd = QLabel("--")
        self.kpi_eng_due = QLabel("--")
        self.kpi_eng_var = QLabel("--")
        self.kpi_esd_var = QLabel("--")

        self.kpi_order.setObjectName("KpiValue")
        self.kpi_quote.setObjectName("KpiValue")
        self.kpi_req.setObjectName("KpiLabel")
        self.kpi_esd.setObjectName("KpiValue")
        self.kpi_eng_due.setObjectName("KpiValue")
        self.kpi_eng_var.setObjectName("KpiValue")
        self.kpi_esd_var.setObjectName("KpiValue")

        form_layout.addRow("Order No:", self.kpi_order)
        form_layout.addRow("Quote No:", self.kpi_quote)
        form_layout.addRow("Requirement:", self.kpi_req)
        form_layout.addRow("Est. Days:", self.inp_est_days)
        form_layout.addRow("Assign To:", self.inp_assignee)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setObjectName("SeparatorLine")
        form_layout.addRow(line)

        form_layout.addRow("Eng Due Date:", self.kpi_eng_due)
        form_layout.addRow("Eng Variance:", self.kpi_eng_var)
        form_layout.addRow("Project ESD:", self.kpi_esd)
        form_layout.addRow("ESD Variance:", self.kpi_esd_var)

        kpi_layout.addLayout(form_layout)
        kpi_layout.addStretch()

        gantt_body_layout.addWidget(self.unified_gantt_card, 1)
        gantt_body_layout.addWidget(self.kpi_panel)

        gantt_main_layout.addLayout(gantt_body_layout, 1)

    def populate_kpi_inspector(self, data: Dict[str, Any]) -> None:
        self.inp_smart_id.setText(str(data.get('SMART_ID', '')))

        is_parent = data.get('IS_PARENT', False)
        prefix = "Order: " if is_parent else "Line: "

        self.kpi_title.setText(f"{prefix}{str(data.get('PROJECT NAME', 'Unknown'))[:15]}...")
        self.kpi_order.setText(str(data.get('PROJECT_ID', '--')))
        self.kpi_quote.setText(str(data.get('QUOTE NO', '--')))
        self.kpi_req.setText(str(data.get('REQUIREMENT', '--')))

        assignee = str(data.get('ASSIGNED TO', '')).strip().upper()
        if not assignee or assignee == 'NAN':
            assignee = "UNASSIGNED"

        match_idx = 0
        for i in range(self.inp_assignee.count()):
            if self.inp_assignee.itemText(i).strip().upper() == assignee:
                match_idx = i
                break

        self.inp_assignee.blockSignals(True)
        self.inp_assignee.setCurrentIndex(match_idx)
        self.inp_assignee.setEnabled(True)
        self.inp_assignee.blockSignals(False)

        self.inp_est_days.blockSignals(True)
        self.inp_est_days.setText(str(data.get('EST DAYS', '')))

        if is_parent:
            self.inp_est_days.setEnabled(False)
            self.inp_est_days.setToolTip("Parent durations are calculated automatically from their sub-lines. Stretch a sub-line to extend this project.")
        else:
            self.inp_est_days.setEnabled(True)
            self.inp_est_days.setToolTip("Type a number of days to override the duration.")

        self.inp_est_days.blockSignals(False)

        self.kpi_eng_due.setText(str(data.get('ENG DUE DATE', '--')))
        self.kpi_esd.setText(str(data.get('ESD', '--')))
        self.kpi_eng_var.setText(str(data.get('EST ENG VARIANCE', '--')))
        self.kpi_esd_var.setText(str(data.get('EST ESD VARIANCE', '--')))

    def populate_left_table(self, visual_rows: List[Dict[str, Any]], expanded_projects: set) -> None:
        table = self.info_table

        table.clearSpans()
        table.setRowCount(len(visual_rows))
        table.setWordWrap(False)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)

        table.setColumnWidth(0, 110)
        table.setColumnWidth(1, 110)
        table.setColumnWidth(2, 260)
        table.setColumnWidth(3, 85)
        table.setColumnWidth(4, 75)

        font_parent = QFont("Segoe UI", 9, QFont.Weight.Bold)
        font_child = QFont("Segoe UI", 9)

        for row_idx, row in enumerate(visual_rows):
            table.setRowHeight(row_idx, self.row_height)

            is_parent = row.get('IS_PARENT', False)

            if is_parent:
                prefix = "▼ " if row.get('PROJECT_ID') in expanded_projects else "▶ "
                req_text = f"{prefix}{str(row.get('REQUIREMENT', ''))}"
                project_text = str(row.get('PROJECT NAME', ''))

                items = [
                    QTableWidgetItem(req_text),
                    QTableWidgetItem(str(row.get('QUOTE NO', ''))),
                    QTableWidgetItem(project_text),
                    QTableWidgetItem(str(row.get('ESD', ''))),
                    QTableWidgetItem(str(row.get('STATUS', '')))
                ]

                items[0].setToolTip(req_text.strip("▼▶ "))
                items[2].setToolTip(project_text)

                for col, item in enumerate(items):
                    item.setFont(font_parent)
                    table.setItem(row_idx, col, item)
            else:
                part_no = str(row.get('LUMINARIE SPECIFICATION',
                            row.get('CONFIGURED STRING',
                            row.get('PART NUMBER',
                            row.get('CATALOG CODE',
                            row.get('CATALOG',
                            row.get('FAMILY', ''))))))).strip()

                if not part_no or part_no.lower() == 'nan':
                    part_no = "Unknown Specification"

                child_text = f"      {part_no}"

                item = QTableWidgetItem(child_text)
                item.setFont(font_child)
                item.setToolTip(part_no)

                table.setItem(row_idx, 0, item)
                table.setSpan(row_idx, 0, 1, 5)

    @staticmethod
    def get_business_day_offset(start_date: pd.Timestamp, target_date: pd.Timestamp) -> int:
        if pd.isna(target_date) or pd.isna(start_date):
            return 0
        # --- NEW: Use pure M-F columns for visual alignment ---
        return int(np.busday_count(start_date.date(), target_date.date()))

    def draw_gantt_canvas(self, visual_rows: List[Dict[str, Any]], dynamic_engineers: List[str]) -> None:
        self.header_scene.clear()
        self.gantt_scene.clear()

        if not visual_rows:
            return

        all_starts = [r.get('ENG START DATE') or r.get('EST START DATE') for r in visual_rows if
                      r.get('ENG START DATE') or r.get('EST START DATE')]

        if all_starts:
            start_series = pd.to_datetime(pd.Series(all_starts))
            day_zero = min(start_series.min(), pd.Timestamp.today().normalize())
        else:
            day_zero = pd.Timestamp.today().normalize()

        day_zero = day_zero - pd.Timedelta(days=day_zero.weekday())
        self.day_zero = day_zero

        max_offset_days = 120
        for row in visual_rows:
            start_str = str(row.get('ENG START DATE') or row.get('EST START DATE')).strip()
            est_days_str = str(row.get('EST DAYS', '')).strip()
            days = float(est_days_str) if est_days_str else 5
            start_dt = pd.to_datetime(start_str) if start_str else pd.NaT

            if pd.notna(start_dt):
                offset = self.get_business_day_offset(day_zero, start_dt)
                if offset + days > max_offset_days:
                    max_offset_days = int(offset + days)

            due_dt = pd.to_datetime(row.get('ENG DUE DATE', '')) if str(row.get('ENG DUE DATE', '')) else pd.NaT
            if pd.notna(due_dt):
                due_offset = self.get_business_day_offset(day_zero, due_dt)
                if due_offset > max_offset_days:
                    max_offset_days = due_offset

        total_business_days = max_offset_days + 30
        total_width = total_business_days * self.day_width
        total_height = max(len(visual_rows) * self.row_height, 800)

        self.header_scene.setSceneRect(0, 0, total_width, 45)
        self.gantt_scene.setSceneRect(0, 0, total_width, total_height)

        font_month = QFont("Segoe UI", 9, QFont.Weight.Bold)
        font_day = QFont("Segoe UI", 8)
        current_x, today_x = 0, -1
        today = pd.Timestamp.today().normalize()

        month_bounds = []
        temp_start_x = 0
        temp_month_date = day_zero

        for i in range(total_business_days):
            current_date = day_zero + pd.tseries.offsets.BusinessDay(i)

            if i > 0 and current_date.month != temp_month_date.month:
                month_bounds.append((temp_start_x, current_x, temp_month_date))
                temp_start_x = current_x
                temp_month_date = current_date

            # --- NEW: Highlight Holidays in red on the grid! ---
            current_date_str = current_date.strftime('%Y-%m-%d')
            if current_date_str in AppConstants.COMPANY_HOLIDAYS:
                self.gantt_scene.addRect(
                    current_x, 0, self.day_width, total_height + 2000,
                    QPen(Qt.PenStyle.NoPen), QColor(255, 82, 82, 30)
                )
                h_text = self.header_scene.addText("H")
                h_text.setDefaultTextColor(QColor("#FF5252"))
                h_text.setFont(font_day)
                h_w = h_text.boundingRect().width()
                h_text.setPos(current_x + (self.day_width - h_w) / 2, 5)

            if current_date == today:
                self.gantt_scene.addRect(
                    current_x, 0, self.day_width, total_height + 2000,
                    QPen(Qt.PenStyle.NoPen), QColor(255, 255, 255, 25)
                )
                today_x = current_x

            if current_date.weekday() == 0:
                self.header_scene.addLine(current_x, 25, current_x, 45, QPen(QColor("#666666"), 2))

            d_text = self.header_scene.addText(str(current_date.day))
            d_text.setDefaultTextColor(QColor("#888888"))
            d_text.setFont(font_day)
            d_w = d_text.boundingRect().width()
            d_text.setPos(current_x + (self.day_width - d_w) / 2, 20)

            current_x += self.day_width

        month_bounds.append((temp_start_x, current_x, temp_month_date))

        for start_x, end_x, m_date in month_bounds:
            month_width = end_x - start_x
            self.header_scene.addRect(start_x, 0, month_width, 22, QPen(QColor("#333333")), QBrush(QColor("#252526")))

            m_str = m_date.strftime("%B %Y")
            m_text = self.header_scene.addText(m_str)
            m_text.setDefaultTextColor(QColor("#CCCCCC"))
            m_text.setFont(font_month)
            text_w = m_text.boundingRect().width()

            if text_w < month_width:
                m_text.setPos(start_x + (month_width - text_w) / 2, -2)
            else:
                m_text.setPlainText(m_date.strftime("%b"))
                m_text.setPos(start_x + 2, -2)

        for index, row in enumerate(visual_rows):
            y = index * self.row_height
            is_parent = row.get('IS_PARENT', False)

            # --- NEW: Calculate width based on visual spanning, stretching over holidays ---
            start_str = str(row.get('ENG START DATE') or row.get('EST START DATE')).strip()
            end_str = str(row.get('COMPLETE DATE') or row.get('EST END DATE')).strip()

            start_dt = pd.to_datetime(start_str) if start_str else pd.NaT
            end_dt = pd.to_datetime(end_str) if end_str else pd.NaT

            if pd.notna(start_dt):
                x = self.get_business_day_offset(day_zero, start_dt) * self.day_width
                if pd.notna(end_dt):
                    # How many M-F columns to bridge visually
                    visual_days = int(np.busday_count(start_dt.date(), end_dt.date())) + 1
                    width = max(1, visual_days) * self.day_width
                else:
                    est_days = float(str(row.get('EST DAYS', 5)).strip() or 5)
                    width = est_days * self.day_width
            else:
                x = 0
                width = 5 * self.day_width

            block = GanttBlock(
                project_data=row,
                x=x, y=y + 4, width=width, height=self.row_height - 8,
                day_width=self.day_width,
                dynamic_engineers=dynamic_engineers,
                is_parent=is_parent
            )
            block.block_dropped.connect(self.block_dropped_signal.emit)
            block.assignee_changed.connect(self.assignee_changed_signal.emit)
            self.gantt_scene.addItem(block)

            due_dt = pd.to_datetime(row.get('ENG DUE DATE', '')) if str(row.get('ENG DUE DATE', '')) else pd.NaT
            if pd.notna(due_dt):
                due_offset = self.get_business_day_offset(day_zero, due_dt)
                due_x = due_offset * self.day_width
                if due_x >= 0:
                    self.gantt_scene.addItem(DueDateMarker(due_x, y, self.row_height))

        if not self.initial_scroll_done and today_x >= 0:
            scroll_x = max(0, today_x - (today.weekday() * self.day_width) - self.day_width)
            QTimer.singleShot(0, lambda: self.gantt_view.horizontalScrollBar().setValue(scroll_x))
            self.initial_scroll_done = True

    def render_gantt(self, visual_rows: List[Dict[str, Any]], dynamic_engineers: List[str], expanded_projects: set) -> None:
        self.populate_left_table(visual_rows, expanded_projects)
        self.draw_gantt_canvas(visual_rows, dynamic_engineers)