"""
Provides the Interactive Gantt Chart interface.
This view coordinates the left-hand information table, the scrollable
interactive Gantt canvas, and the dynamic KPI Job Inspector panel.
"""

from typing import Optional, List, Dict, Any

import pandas as pd
from PySide6.QtCore import Qt, Signal, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QMouseEvent, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QComboBox, QSplitter, QTableWidget, QAbstractItemView,
    QGraphicsView, QGraphicsScene, QFormLayout, QLineEdit,
    QTableWidgetItem, QHeaderView
)

from ui.components.gantt_components import GanttBlock, DueDateMarker


class GanttView(QGraphicsView):
    """
    Custom QGraphicsView for the Gantt canvas.
    Captures empty clicks to deselect items and hide the KPI panel.
    """
    empty_clicked = Signal()

    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setObjectName("CanvasView")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Emits a signal when the user clicks on an empty area of the canvas."""
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            if not self.itemAt(event.pos()) and self.empty_clicked:
                self.empty_clicked.emit()


class GanttGridScene(QGraphicsScene):
    """
    Custom QGraphicsScene that paints an infinite grid background
    based on the specified day width and row height.
    """

    def __init__(self, day_width: int, row_height: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.day_width = day_width
        self.row_height = row_height

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        """Paints the dark background and the row/column grid lines."""
        painter.fillRect(rect, QColor("#1E1E1E"))

        row_pen = QPen(QColor("#252526"))
        col_pen = QPen(QColor("#3E3E42"))
        col_pen.setStyle(Qt.DotLine)

        top_y = int(rect.top()) - (int(rect.top()) % self.row_height)
        for y in range(top_y, int(rect.bottom()), self.row_height):
            painter.setPen(row_pen)
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)

        left_x = int(rect.left()) - (int(rect.left()) % self.day_width)
        for x in range(left_x, int(rect.right()), self.day_width):
            painter.setPen(col_pen)
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))


class GanttScreenWidget(QWidget):
    """
    The main wrapper widget for the Gantt Screen.
    Contains the filters, the synchronized table/canvas splitter, and the KPI inspector.
    """

    # Emitted up to the controller when blocks are moved or assigned
    block_dropped_signal = Signal(str, float, float, bool, float)
    assignee_changed_signal = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()

        self.day_width: int = 25
        self.row_height: int = 36
        self.initial_scroll_done: bool = False
        self.day_zero: Optional[pd.Timestamp] = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initializes the layout and UI components for the Gantt view."""
        gantt_main_layout = QVBoxLayout(self)
        gantt_main_layout.setContentsMargins(0, 0, 0, 0)

        # ==========================================
        # HEADER & FILTERS
        # ==========================================
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
        gantt_main_layout.addLayout(gantt_header_layout)

        # ==========================================
        # MAIN BODY (Splitter & KPI Panel)
        # ==========================================
        gantt_body_layout = QHBoxLayout()
        gantt_body_layout.setSpacing(15)

        self.unified_gantt_card = QFrame()
        self.unified_gantt_card.setObjectName("TableWell")
        unified_layout = QVBoxLayout(self.unified_gantt_card)
        unified_layout.setContentsMargins(0, 0, 0, 0)
        unified_layout.setSpacing(0)

        self.gantt_splitter = QSplitter(Qt.Horizontal)

        # --- 1. Left Data Table ---
        self.info_table = QTableWidget()
        self.info_table.setObjectName("LeftTable")
        self.info_table.setColumnCount(5)
        self.info_table.setHorizontalHeaderLabels(["Req.", "Quote", "Project", "ESD", "Status"])
        self.info_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.info_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.info_table.setMouseTracking(True)
        self.info_table.viewport().setMouseTracking(True)

        self.info_table.verticalHeader().setDefaultSectionSize(self.row_height)
        self.info_table.verticalHeader().setVisible(False)
        self.info_table.horizontalHeader().setMinimumHeight(45)
        self.info_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self.info_table.setShowGrid(False)
        self.info_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.info_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.info_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.info_table.horizontalHeader().setStretchLastSection(True)
        self.info_table.setMinimumWidth(250)

        # --- 2. Interactive Canvas Container ---
        self.canvas_container = QFrame()
        canvas_layout = QVBoxLayout(self.canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)

        self.header_scene = QGraphicsScene()
        self.header_view = QGraphicsView(self.header_scene)
        self.header_view.setFixedHeight(45)
        self.header_view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.header_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.header_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.header_view.setObjectName("HeaderView")

        self.gantt_scene = GanttGridScene(day_width=self.day_width, row_height=self.row_height)
        self.gantt_view = GanttView(self.gantt_scene)

        # Sync scrolling
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
        self.gantt_splitter.setSizes([350, 800])
        unified_layout.addWidget(self.gantt_splitter)

        # ==========================================
        # KPI INSPECTOR PANEL (Right Sidebar)
        # ==========================================
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
        line.setFrameShape(QFrame.HLine)
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

    # ==========================================
    # DATA RENDERING & CANVAS LOGIC
    # ==========================================

    def populate_kpi_inspector(self, data: Dict[str, Any]) -> None:
        """Fills out the right-hand KPI panel with the selected block's data."""
        self.inp_smart_id.setText(str(data.get('SMART_ID', '')))

        is_parent = data.get('IS_PARENT', False)
        prefix = "Order: " if is_parent else "Line: "

        self.kpi_title.setText(f"{prefix}{str(data.get('PROJECT NAME', 'Unknown'))[:15]}...")
        self.kpi_order.setText(str(data.get('PROJECT_ID', '--')))
        self.kpi_quote.setText(str(data.get('QUOTE NO', '--')))
        self.kpi_req.setText(str(data.get('REQUIREMENT', '--')))

        assignee = str(data.get('ASSIGNED TO', '')).strip()
        self.inp_assignee.blockSignals(True)
        self.inp_assignee.setCurrentText(assignee)
        self.inp_assignee.setEnabled(True)
        self.inp_assignee.blockSignals(False)

        self.inp_est_days.blockSignals(True)
        self.inp_est_days.setText(str(data.get('EST DAYS', '')))
        self.inp_est_days.setEnabled(True)
        self.inp_est_days.blockSignals(False)

        self.kpi_eng_due.setText(str(data.get('ENG DUE DATE', '--')))
        self.kpi_esd.setText(str(data.get('ESD', '--')))
        self.kpi_eng_var.setText(str(data.get('EST ENG VARIANCE', '--')))
        self.kpi_esd_var.setText(str(data.get('EST ESD VARIANCE', '--')))

    def populate_left_table(self, visual_rows: List[Dict[str, Any]], expanded_projects: set) -> None:
        """Fills the left-hand text table with project data."""
        table = self.info_table
        table.setRowCount(len(visual_rows))
        table.setWordWrap(False)

        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        header.setSectionResizeMode(4, QHeaderView.Interactive)

        table.setColumnWidth(0, 85)
        table.setColumnWidth(1, 100)
        table.setColumnWidth(2, 220)
        table.setColumnWidth(3, 80)
        table.setColumnWidth(4, 90)

        font_parent = QFont("Segoe UI", 9, QFont.Bold)
        font_child = QFont("Segoe UI", 9)

        for row_idx, row in enumerate(visual_rows):
            table.setRowHeight(row_idx, self.row_height)

            is_parent = row.get('IS_PARENT', False)
            prefix = "▼ " if is_parent and row.get('PROJECT_ID') in expanded_projects else "▶ " if is_parent else "    "

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
                item.setFont(font_parent if is_parent else font_child)
                table.setItem(row_idx, col, item)

    @staticmethod
    def get_business_day_offset(start_date: pd.Timestamp, target_date: pd.Timestamp) -> int:
        """Calculates the number of business days between two dates."""
        if pd.isna(target_date) or pd.isna(start_date):
            return 0
        days = pd.bdate_range(start=start_date, end=target_date)
        return len(days) - 1 if len(days) > 0 else 0

    def draw_gantt_canvas(self, visual_rows: List[Dict[str, Any]], dynamic_engineers: List[str]) -> None:
        """Plots blocks onto the right-hand canvas using calculated coordinates."""
        self.header_scene.clear()
        self.gantt_scene.clear()

        if not visual_rows:
            return

        all_starts = [r.get('ENG START DATE') or r.get('EST START DATE') for r in visual_rows if
                      r.get('ENG START DATE') or r.get('EST START DATE')]

        if all_starts:
            start_series = pd.to_datetime(all_starts)
            day_zero = start_series.min()
        else:
            day_zero = pd.Timestamp.today().normalize()

        day_zero = day_zero - pd.Timedelta(days=day_zero.weekday())
        self.day_zero = day_zero

        total_business_days = 120
        total_width = total_business_days * self.day_width
        total_height = max(len(visual_rows) * self.row_height, 800)

        self.header_scene.setSceneRect(0, 0, total_width, 45)
        self.gantt_scene.setSceneRect(0, 0, total_width, total_height)

        font_month = QFont("Segoe UI", 9, QFont.Bold)
        font_day = QFont("Segoe UI", 8)
        current_x, current_month, today_x = 0, -1, -1
        today = pd.Timestamp.today().normalize()

        for i in range(total_business_days):
            current_date = day_zero + pd.tseries.offsets.BusinessDay(i)
            if current_date == today:
                self.gantt_scene.addRect(
                    current_x, 0, self.day_width, total_height + 2000,
                    QPen(Qt.NoPen), QColor(255, 255, 255, 25)
                )
                today_x = current_x

            if current_date.month != current_month:
                current_month = current_date.month
                m_text = self.header_scene.addText(current_date.strftime("%B %Y"))
                m_text.setDefaultTextColor(QColor("#CCCCCC"))
                m_text.setFont(font_month)
                m_text.setPos(current_x + 2, 0)

            if current_date.weekday() == 0:
                self.header_scene.addLine(current_x, 25, current_x, 45, QPen(QColor("#666666"), 2))

            d_text = self.header_scene.addText(str(current_date.day))
            d_text.setDefaultTextColor(QColor("#888888"))
            d_text.setFont(font_day)
            d_text.setPos(current_x + 2, 20)
            current_x += self.day_width

        for index, row in enumerate(visual_rows):
            y = index * self.row_height
            is_parent = row.get('IS_PARENT', False)

            start_str = str(row.get('ENG START DATE') or row.get('EST START DATE')).strip()
            est_days_str = str(row.get('EST DAYS', '')).strip()

            days = float(est_days_str) if est_days_str else 5
            start_dt = pd.to_datetime(start_str) if start_str else pd.NaT

            width = days * self.day_width
            x = self.get_business_day_offset(day_zero, start_dt) * self.day_width if pd.notna(start_dt) else 0

            block = GanttBlock(
                project_data=row,
                x=x, y=y + 4, width=width, height=self.row_height - 8,
                day_width=self.day_width,
                dynamic_engineers=dynamic_engineers,
                is_parent=is_parent
            )
            # Pass interactions up via signal
            block.block_dropped.connect(self.block_dropped_signal.emit)
            block.assignee_changed.connect(self.assignee_changed_signal.emit)
            self.gantt_scene.addItem(block)

            if not is_parent:
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

    def render_gantt(self, visual_rows: List[Dict[str, Any]], dynamic_engineers: List[str],
                     expanded_projects: set) -> None:
        """Master method to populate both the data table and drawing canvas simultaneously."""
        self.populate_left_table(visual_rows, expanded_projects)
        self.draw_gantt_canvas(visual_rows, dynamic_engineers)
