import os
from PySide6.QtWidgets import (QMainWindow, QPushButton, QTableWidget,
                               QVBoxLayout, QHBoxLayout, QWidget, QMessageBox,
                               QTableWidgetItem, QHeaderView, QStackedWidget, QLabel,
                               QFrame, QFormLayout, QLineEdit, QAbstractItemView,
                               QGraphicsView, QGraphicsScene, QSplitter, QComboBox)
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QIcon, QPainter


class GanttView(QGraphicsView):
    empty_clicked = Signal() if hasattr(Qt, 'Signal') else None

    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setStyleSheet("background: transparent; border: none;")
        self.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            if not self.itemAt(event.pos()) and self.empty_clicked:
                self.empty_clicked.emit()


GanttView.empty_clicked = Signal()


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
        self.nav_gantt_btn = QPushButton("")
        self.nav_gantt_btn.setIcon(QIcon(os.path.join(base_path, "resources", "gantt.svg")))
        self.nav_dash_btn = QPushButton("")
        self.nav_dash_btn.setIcon(QIcon(os.path.join(base_path, "resources", "dashboard.svg")))

        for btn in [self.nav_data_btn, self.nav_gantt_btn, self.nav_dash_btn]:
            btn.setObjectName("NavButton")
            btn.setFixedSize(50, 50)
            btn.setIconSize(QSize(24, 24))
            self.sidebar_layout.addWidget(btn)

        self.main_card_frame = QFrame()
        self.main_card_frame.setObjectName("mainCardFrame")
        self.card_layout = QVBoxLayout(self.main_card_frame)
        self.card_layout.setContentsMargins(20, 20, 20, 20)

        self.stacked_widget = QStackedWidget()
        self.card_layout.addWidget(self.stacked_widget)

        # ==========================================
        # CARD 1: RAW DATA SCREEN
        # ==========================================
        self.data_screen = QWidget()
        data_main_layout = QVBoxLayout(self.data_screen)
        data_main_layout.setContentsMargins(0, 0, 0, 0)

        header_lbl = QLabel("Raw Synced Excel Data")
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

        bottom_bar_data = QHBoxLayout()
        self.sync_btn = QPushButton("Sync Workload")
        self.sync_btn.setObjectName("PrimaryButton")
        bottom_bar_data.addWidget(self.sync_btn)
        bottom_bar_data.addStretch()
        data_main_layout.addLayout(bottom_bar_data)

        # ==========================================
        # CARD 2: GANTT CHART
        # ==========================================
        self.gantt_screen = QWidget()
        gantt_main_layout = QVBoxLayout(self.gantt_screen)
        gantt_main_layout.setContentsMargins(0, 0, 0, 0)

        gantt_header_layout = QHBoxLayout()
        gantt_header_layout.setContentsMargins(0, 0, 0, 10)

        gantt_header = QLabel("Interactive Gantt Chart")
        gantt_header.setObjectName("Header")
        gantt_header_layout.addWidget(gantt_header)
        gantt_header_layout.addStretch()

        filter_lbl = QLabel("Filters:")
        filter_lbl.setStyleSheet("color: #AAAAAA; font-weight: bold; margin-right: 5px;")
        gantt_header_layout.addWidget(filter_lbl)

        combo_style = """
            QComboBox {
                background-color: #252526; color: white; border: 1px solid #3E3E42;
                padding: 4px 10px; border-radius: 4px; min-width: 120px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox::down-arrow { image: none; border-left: 1px solid #3E3E42; }
            QComboBox QAbstractItemView {
                background-color: #1E1E1E; color: white;
                selection-background-color: #007ACC; border: 1px solid #3E3E42;
            }
        """
        self.filter_req = QComboBox()
        self.filter_req.addItems(["All Reqs", "Production", "Approval", "Quote"])
        self.filter_req.setCurrentText("Production")
        self.filter_req.setStyleSheet(combo_style)

        self.filter_status = QComboBox()
        self.filter_status.addItems(["All Status", "Active", "Complete"])
        self.filter_status.setCurrentText("Active")
        self.filter_status.setStyleSheet(combo_style)

        gantt_header_layout.addWidget(self.filter_req)
        gantt_header_layout.addWidget(self.filter_status)
        gantt_main_layout.addLayout(gantt_header_layout)

        gantt_body_layout = QHBoxLayout()
        gantt_body_layout.setSpacing(15)

        self.unified_gantt_card = QFrame()
        self.unified_gantt_card.setObjectName("TableWell")
        unified_layout = QVBoxLayout(self.unified_gantt_card)
        unified_layout.setContentsMargins(0, 0, 0, 0)
        unified_layout.setSpacing(0)

        self.gantt_splitter = QSplitter(Qt.Horizontal)
        self.gantt_splitter.setStyleSheet("QSplitter::handle { background: #3E3E42; width: 1px; }")

        # 1. LEFT PANE: Info Table
        self.info_table = QTableWidget()
        self.info_table.setColumnCount(5)
        self.info_table.setHorizontalHeaderLabels(["Req.", "Quote", "Project", "ESD", "Status"])
        self.info_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.info_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.info_table.verticalHeader().setDefaultSectionSize(28)
        self.info_table.verticalHeader().setVisible(False)
        self.info_table.horizontalHeader().setMinimumHeight(45)

        # TWEAK: Align Left and Bottom!
        self.info_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignBottom)

        self.info_table.setShowGrid(False)
        self.info_table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # TWEAK: Added 5px padding-bottom to the header section so it aligns beautifully
        self.info_table.setStyleSheet("""
            QTableWidget { 
                background-color: transparent; 
                border: none; 
                border-radius: 0px;
                border-top-left-radius: 8px; 
                border-bottom-left-radius: 8px;
            }
            QTableWidget::item:selected { background-color: #007ACC; color: white; }

            QHeaderView::section:horizontal {
                background-color: transparent;
                color: #CCCCCC;
                font-family: 'Segoe UI';
                font-size: 9pt;
                font-weight: bold;
                border: none;
                border-bottom: 1px solid #3E3E42;
                padding-left: 5px;
                padding-bottom: 5px;
            }
            QHeaderView::section:horizontal:first { border-top-left-radius: 8px; }
        """)

        self.info_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.info_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.info_table.horizontalHeader().setStretchLastSection(True)
        self.info_table.setMinimumWidth(250)

        # 2. CENTER PANE: The Gantt Canvas
        self.canvas_container = QFrame()
        self.canvas_container.setStyleSheet("background: transparent; border: none;")
        canvas_layout = QVBoxLayout(self.canvas_container)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)

        self.header_scene = QGraphicsScene()
        self.header_view = QGraphicsView(self.header_scene)
        self.header_view.setFixedHeight(45)
        self.header_view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.header_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.header_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.header_view.setStyleSheet("""
            QGraphicsView {
                background: transparent; border: none; border-bottom: 1px solid #3E3E42;
                border-radius: 0px; border-top-right-radius: 8px;
            }
        """)

        self.gantt_scene = QGraphicsScene()
        self.gantt_view = GanttView(self.gantt_scene)
        self.gantt_view.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.gantt_view.setStyleSheet("""
            QGraphicsView {
                background: transparent; border: none;
                border-radius: 0px; border-bottom-right-radius: 8px;
            }
        """)

        self.gantt_view.horizontalScrollBar().valueChanged.connect(self.header_view.horizontalScrollBar().setValue)
        self.header_view.horizontalScrollBar().valueChanged.connect(self.gantt_view.horizontalScrollBar().setValue)
        self.info_table.verticalScrollBar().valueChanged.connect(self.gantt_view.verticalScrollBar().setValue)
        self.gantt_view.verticalScrollBar().valueChanged.connect(self.info_table.verticalScrollBar().setValue)

        canvas_layout.addWidget(self.header_view)
        canvas_layout.addWidget(self.gantt_view)

        self.gantt_splitter.addWidget(self.info_table)
        self.gantt_splitter.addWidget(self.canvas_container)

        # TWEAK: Lock the left table's size when resizing happens!
        self.gantt_splitter.setStretchFactor(0, 0)  # Index 0 (Table) takes 0% of extra space
        self.gantt_splitter.setStretchFactor(1, 1)  # Index 1 (Canvas) absorbs 100% of shrinking/growing

        self.gantt_splitter.setSizes([350, 800])
        unified_layout.addWidget(self.gantt_splitter)

        # 3. RIGHT PANE: KPI Inspector
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
        self.inp_assignee = QLineEdit()

        self.inp_assignee = QComboBox()
        self.inp_assignee.addItems(["", "Adam T", "David M", "Andy C", "Matt M"])
        self.inp_assignee.setStyleSheet(combo_style)

        self.kpi_req = QLabel("--")
        self.kpi_esd = QLabel("--")
        self.kpi_eng_due = QLabel("--")
        self.kpi_eng_var = QLabel("--")
        self.kpi_esd_var = QLabel("--")

        kpi_style = "color: #4DB8FF; font-weight: bold; font-size: 14px;"
        self.kpi_req.setStyleSheet("color: #AAAAAA; font-weight: bold;")
        self.kpi_esd.setStyleSheet(kpi_style)
        self.kpi_eng_due.setStyleSheet(kpi_style)
        self.kpi_eng_var.setStyleSheet(kpi_style)
        self.kpi_esd_var.setStyleSheet(kpi_style)

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

        self.save_edit_btn = QPushButton("Save Estimate")
        self.save_edit_btn.setObjectName("PrimaryButton")
        kpi_layout.addWidget(self.save_edit_btn)
        kpi_layout.addStretch()

        gantt_body_layout.addWidget(self.unified_gantt_card, 1)
        gantt_body_layout.addWidget(self.kpi_panel)

        gantt_main_layout.addLayout(gantt_body_layout, 1)

        self.dash_screen = QWidget()
        self.stacked_widget.addWidget(self.data_screen)
        self.stacked_widget.addWidget(self.gantt_screen)
        self.stacked_widget.addWidget(self.dash_screen)

        main_layout.addWidget(self.sidebar_frame)
        main_layout.addWidget(self.main_card_frame, 1)

        self.nav_data_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        self.nav_gantt_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))

    def display_dataframe(self, table_widget, df):
        table_widget.clear()
        if df.empty:
            table_widget.setRowCount(0)
            table_widget.setColumnCount(0)
            return
        table_widget.setColumnCount(df.shape[1])
        table_widget.setRowCount(df.shape[0])
        table_widget.setHorizontalHeaderLabels(list(df.columns))
        table_widget.horizontalHeader().setMinimumHeight(35)
        # Keep the raw data table center aligned
        table_widget.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for row in range(df.shape[0]):
            for col in range(df.shape[1]):
                cell_value = str(df.iat[row, col])
                item = QTableWidgetItem(cell_value)
                table_widget.setItem(row, col, item)
        table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

    def show_warning(self, title, message):
        QMessageBox.warning(self, title, message)