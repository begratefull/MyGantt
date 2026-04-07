from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                               QComboBox, QSplitter, QTableWidget, QAbstractItemView,
                               QGraphicsView, QGraphicsScene, QFormLayout, QLineEdit)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QColor, QPen


class GanttView(QGraphicsView):
    empty_clicked = Signal()

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setObjectName("CanvasView")

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            if not self.itemAt(event.pos()) and self.empty_clicked:
                self.empty_clicked.emit()


class GanttGridScene(QGraphicsScene):
    def __init__(self, day_width, row_height, parent=None):
        super().__init__(parent)
        self.day_width = day_width
        self.row_height = row_height

    def drawBackground(self, painter, rect):
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
    def __init__(self):
        super().__init__()

        gantt_main_layout = QVBoxLayout(self)
        gantt_main_layout.setContentsMargins(0, 0, 0, 0)

        # --- Header & Filters ---
        gantt_header_layout = QHBoxLayout()
        gantt_header_layout.setContentsMargins(0, 0, 0, 10)

        gantt_header = QLabel("Interactive Gantt Chart")
        gantt_header.setObjectName("Header")
        gantt_header_layout.addWidget(gantt_header)
        gantt_header_layout.addStretch()

        filter_lbl = QLabel("Filters:")
        filter_lbl.setStyleSheet("color: #AAAAAA; font-weight: bold; margin-right: 5px;")
        gantt_header_layout.addWidget(filter_lbl)

        self.filter_req = QComboBox()
        self.filter_req.addItems(["All Reqs", "Production", "Approval", "Quote"])
        self.filter_req.setCurrentText("All Reqs")

        self.filter_status = QComboBox()
        self.filter_status.addItems(["All Status", "Active", "Complete"])
        self.filter_status.setCurrentText("Active")

        gantt_header_layout.addWidget(self.filter_req)
        gantt_header_layout.addWidget(self.filter_status)
        gantt_main_layout.addLayout(gantt_header_layout)

        # --- Body ---
        gantt_body_layout = QHBoxLayout()
        gantt_body_layout.setSpacing(15)

        self.unified_gantt_card = QFrame()
        self.unified_gantt_card.setObjectName("TableWell")
        unified_layout = QVBoxLayout(self.unified_gantt_card)
        unified_layout.setContentsMargins(0, 0, 0, 0)
        unified_layout.setSpacing(0)

        self.gantt_splitter = QSplitter(Qt.Horizontal)

        # 1. Left Table
        self.info_table = QTableWidget()
        self.info_table.setObjectName("LeftTable")
        self.info_table.setColumnCount(5)
        self.info_table.setHorizontalHeaderLabels(["Req.", "Quote", "Project", "ESD", "Status"])
        self.info_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.info_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.info_table.setMouseTracking(True)
        self.info_table.viewport().setMouseTracking(True)
        self.info_table.verticalHeader().setDefaultSectionSize(36)
        self.info_table.verticalHeader().setVisible(False)
        self.info_table.horizontalHeader().setMinimumHeight(45)
        self.info_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self.info_table.setShowGrid(False)
        self.info_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.info_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.info_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.info_table.horizontalHeader().setStretchLastSection(True)
        self.info_table.setMinimumWidth(250)

        # 2. Canvas
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

        self.gantt_scene = GanttGridScene(day_width=25, row_height=36)
        self.gantt_view = GanttView(self.gantt_scene)

        # Sync scrollbars
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

        # 3. KPI Panel
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
        self.inp_assignee.addItems(["", "Adam T", "David M", "Andy C", "Matt M"])

        # New Labels!
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

        # Added to layout
        form_layout.addRow("Order No:", self.kpi_order)
        form_layout.addRow("Quote No:", self.kpi_quote)
        form_layout.addRow("Requirement:", self.kpi_req)
        form_layout.addRow("Est. Days:", self.inp_est_days)
        form_layout.addRow("Assign To:", self.inp_assignee)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #3E3E42;")
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