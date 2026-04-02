import os
from PySide6.QtWidgets import (QMainWindow, QPushButton, QTableWidget,
                               QVBoxLayout, QHBoxLayout, QWidget, QMessageBox,
                               QTableWidgetItem, QHeaderView, QStackedWidget, QLabel,
                               QFrame, QFormLayout, QLineEdit, QAbstractItemView,
                               QGraphicsView, QGraphicsScene)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QPainter


class MyGanttWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyGantt")
        self.resize(1500, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # --- THE WELL (Slim Side Tray) ---
        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("sidebarFrame")
        self.sidebar_frame.setFixedWidth(70)
        self.sidebar_layout = QVBoxLayout(self.sidebar_frame)
        self.sidebar_layout.setAlignment(Qt.AlignTop)
        self.sidebar_layout.setContentsMargins(10, 20, 10, 10)
        self.sidebar_layout.setSpacing(15)

        base_path = os.path.dirname(__file__)

        self.nav_data_btn = QPushButton("")
        self.nav_data_btn.setIcon(QIcon(os.path.join(base_path, "resources", "data.svg")))
        self.nav_data_btn.setToolTip("Raw Data")

        self.nav_gantt_btn = QPushButton("")
        self.nav_gantt_btn.setIcon(QIcon(os.path.join(base_path, "resources", "gantt.svg")))
        self.nav_gantt_btn.setToolTip("Planning Board")

        self.nav_dash_btn = QPushButton("")
        self.nav_dash_btn.setIcon(QIcon(os.path.join(base_path, "resources", "dashboard.svg")))
        self.nav_dash_btn.setToolTip("Dashboard")

        for btn in [self.nav_data_btn, self.nav_gantt_btn, self.nav_dash_btn]:
            btn.setObjectName("NavButton")
            btn.setFixedSize(50, 50)
            btn.setIconSize(QSize(24, 24))
            self.sidebar_layout.addWidget(btn)

        # --- THE CARD (Main Content Container) ---
        self.main_card_frame = QFrame()
        self.main_card_frame.setObjectName("mainCardFrame")
        self.card_layout = QVBoxLayout(self.main_card_frame)
        self.card_layout.setContentsMargins(20, 20, 20, 20)

        self.stacked_widget = QStackedWidget()
        self.card_layout.addWidget(self.stacked_widget)

        # ==========================================
        # CARD 1: RAW DATA SCREEN (Full Table)
        # ==========================================
        self.data_screen = QWidget()
        data_main_layout = QVBoxLayout(self.data_screen)
        data_main_layout.setContentsMargins(0, 0, 0, 0)

        header_lbl = QLabel("Engineering Workload Data")
        header_lbl.setObjectName("Header")
        data_main_layout.addWidget(header_lbl)

        self.raw_table_well = QFrame()
        self.raw_table_well.setObjectName("TableWell")
        raw_well_layout = QVBoxLayout(self.raw_table_well)
        raw_well_layout.setContentsMargins(2, 2, 2, 2)

        self.raw_table = QTableWidget()
        self.raw_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.raw_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.raw_table.setShowGrid(False)
        self.raw_table.verticalHeader().setVisible(False)
        raw_well_layout.addWidget(self.raw_table)
        data_main_layout.addWidget(self.raw_table_well)

        # Sync Button sits on the Raw Data Page
        bottom_bar = QHBoxLayout()
        self.sync_btn = QPushButton("Sync Workload")
        self.sync_btn.setObjectName("PrimaryButton")
        bottom_bar.addWidget(self.sync_btn)
        bottom_bar.addStretch()
        data_main_layout.addLayout(bottom_bar)

        # ==========================================
        # CARD 2: PLANNING BOARD (Backlog + Gantt + KPI)
        # ==========================================
        self.gantt_screen = QWidget()
        gantt_main_layout = QHBoxLayout(self.gantt_screen)
        gantt_main_layout.setContentsMargins(0, 0, 0, 0)
        gantt_main_layout.setSpacing(15)

        # --- PANE 1: THE BACKLOG (Slim Entry List) ---
        backlog_container = QWidget()
        backlog_container.setFixedWidth(280)
        backlog_layout = QVBoxLayout(backlog_container)
        backlog_layout.setContentsMargins(0, 0, 0, 0)

        backlog_header = QLabel("Unscheduled Backlog")
        backlog_header.setObjectName("Header")
        backlog_layout.addWidget(backlog_header)

        self.backlog_well = QFrame()
        self.backlog_well.setObjectName("TableWell")
        b_well_layout = QVBoxLayout(self.backlog_well)
        b_well_layout.setContentsMargins(2, 2, 2, 2)

        # We keep a tiny table just for picking jobs to estimate
        self.backlog_table = QTableWidget()
        self.backlog_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.backlog_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.backlog_table.setShowGrid(False)
        self.backlog_table.verticalHeader().setVisible(False)
        b_well_layout.addWidget(self.backlog_table)
        backlog_layout.addWidget(self.backlog_well)

        gantt_main_layout.addWidget(backlog_container)

        # --- PANE 2: THE GANTT CANVAS (The Digital Whiteboard) ---
        canvas_container = QWidget()
        canvas_layout = QVBoxLayout(canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)

        canvas_header = QLabel("Interactive Schedule")
        canvas_header.setObjectName("Header")
        canvas_layout.addWidget(canvas_header)

        self.canvas_well = QFrame()
        self.canvas_well.setObjectName("TableWell")
        c_well_layout = QVBoxLayout(self.canvas_well)
        c_well_layout.setContentsMargins(2, 2, 2, 2)

        # This is the 2D Engine where we will draw the timeline, lanes, and draggable blocks!
        self.gantt_scene = QGraphicsScene()
        self.gantt_view = QGraphicsView(self.gantt_scene)
        self.gantt_view.setRenderHint(QPainter.RenderHint.Antialiasing)  # Smooth lines
        self.gantt_view.setStyleSheet("background: transparent; border: none;")

        c_well_layout.addWidget(self.gantt_view)
        canvas_layout.addWidget(self.canvas_well)

        gantt_main_layout.addWidget(canvas_container, 1)  # Gets the majority of the screen space

        # --- PANE 3: THE KPI INSPECTOR (Right Side) ---
        self.kpi_panel = QFrame()
        self.kpi_panel.setObjectName("TableWell")
        self.kpi_panel.setFixedWidth(300)

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

        # Input fields for quick estimating
        self.inp_est_days = QLineEdit()
        self.inp_assignee = QLineEdit()

        # Read-Only KPI Fields
        self.kpi_due_date = QLabel("--")
        self.kpi_esd = QLabel("--")
        self.kpi_eng_var = QLabel("--")
        self.kpi_esd_var = QLabel("--")

        # Styling the KPI text to stand out
        kpi_style = "color: #4DB8FF; font-weight: bold; font-size: 14px;"
        self.kpi_due_date.setStyleSheet(kpi_style)
        self.kpi_esd.setStyleSheet(kpi_style)
        self.kpi_eng_var.setStyleSheet(kpi_style)
        self.kpi_esd_var.setStyleSheet(kpi_style)

        form_layout.addRow("Est. Days:", self.inp_est_days)
        form_layout.addRow("Assign To:", self.inp_assignee)

        # Add a visual separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #3E3E42;")
        form_layout.addRow(line)

        form_layout.addRow("Eng Due Date:", self.kpi_due_date)
        form_layout.addRow("Eng Variance:", self.kpi_eng_var)
        form_layout.addRow("Project ESD:", self.kpi_esd)
        form_layout.addRow("ESD Variance:", self.kpi_esd_var)

        kpi_layout.addLayout(form_layout)

        self.save_edit_btn = QPushButton("Save Estimate")
        self.save_edit_btn.setObjectName("PrimaryButton")
        kpi_layout.addWidget(self.save_edit_btn)
        kpi_layout.addStretch()

        gantt_main_layout.addWidget(self.kpi_panel)

        # Add Screens to Deck
        self.dash_screen = QWidget()
        self.stacked_widget.addWidget(self.data_screen)
        self.stacked_widget.addWidget(self.gantt_screen)
        self.stacked_widget.addWidget(self.dash_screen)

        main_layout.addWidget(self.sidebar_frame)
        main_layout.addWidget(self.main_card_frame, 1)

        # Connect Navigation
        self.nav_data_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        self.nav_gantt_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        self.nav_dash_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(2))

    def display_dataframe(self, table_widget, df):
        """A generic function to paint any Pandas DataFrame onto a given QTableWidget."""
        table_widget.clear()
        if df.empty:
            table_widget.setRowCount(0)
            table_widget.setColumnCount(0)
            return

        table_widget.setColumnCount(df.shape[1])
        table_widget.setRowCount(df.shape[0])
        table_widget.setHorizontalHeaderLabels(list(df.columns))

        # Style headers
        table_widget.horizontalHeader().setMinimumHeight(35)
        table_widget.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        for row in range(df.shape[0]):
            for col in range(df.shape[1]):
                cell_value = str(df.iat[row, col])
                item = QTableWidgetItem(cell_value)
                table_widget.setItem(row, col, item)

        table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

    def show_warning(self, title, message):
        QMessageBox.warning(self, title, message)