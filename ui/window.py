"""
The main QMainWindow for the MyGantt application.
Responsible for assembling the layout, sidebar navigation,
and linking the Controller to the UI components.
"""

import os
from PySide6.QtWidgets import (QMainWindow, QPushButton, QVBoxLayout, QHBoxLayout,
                               QWidget, QMessageBox, QTableWidgetItem, QHeaderView, QStackedWidget, QFrame, QPlainTextEdit)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from ui.views.dashboard import DashboardWidget
from ui.views.data_view import DataViewWidget
from ui.views.gantt_view import GanttScreenWidget
from ui.views.team_view import TeamManagementWidget


class MyGanttWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MyGantt")
        self.resize(1500, 1000)

        base_path = os.path.dirname(__file__)
        self.setWindowIcon(QIcon(os.path.join(base_path, "resources", "app_icon.svg")))

        self.statusBar().showMessage("Ready")
        self.statusBar().setStyleSheet("color: #AAAAAA; background-color: #1E1E1E; border-top: 1px solid #3E3E42;")

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
        self.nav_dash_btn = QPushButton("")
        self.nav_dash_btn.setIcon(QIcon(os.path.join(base_path, "resources", "dashboard.svg")))

        self.nav_gantt_btn = QPushButton("")
        self.nav_gantt_btn.setIcon(QIcon(os.path.join(base_path, "resources", "gantt.svg")))

        self.nav_team_btn = QPushButton("")
        self.nav_team_btn.setIcon(QIcon(os.path.join(base_path, "resources", "team.svg")))

        self.nav_data_btn = QPushButton("")
        self.nav_data_btn.setIcon(QIcon(os.path.join(base_path, "resources", "data.svg")))

        self.nav_sync_btn = QPushButton("")
        self.nav_sync_btn.setIcon(QIcon(os.path.join(base_path, "resources", "refresh.svg")))
        self.nav_sync_btn.setToolTip("Sync Workload from Excel")

        # --- ADD NEW LOG BUTTON ---
        self.nav_log_btn = QPushButton("")
        self.nav_log_btn.setIcon(QIcon(os.path.join(base_path, "resources", "log.svg")))
        self.nav_log_btn.setToolTip("Toggle Application Logs")

        for btn in [self.nav_dash_btn, self.nav_gantt_btn, self.nav_team_btn, self.nav_data_btn, self.nav_sync_btn, self.nav_log_btn]:
            btn.setObjectName("NavButton")
            btn.setFixedSize(50, 50)
            btn.setIconSize(QSize(24, 24))

        # Make the navigation buttons checkable so they can be highlighted
        self.nav_dash_btn.setCheckable(True)
        self.nav_gantt_btn.setCheckable(True)
        self.nav_team_btn.setCheckable(True)
        self.nav_data_btn.setCheckable(True)
        self.nav_log_btn.setCheckable(True) # Make log button checkable for toggle state

        # Layout the sidebar in the exact order requested
        self.sidebar_layout.addWidget(self.nav_dash_btn)
        self.sidebar_layout.addWidget(self.nav_gantt_btn)
        self.sidebar_layout.addWidget(self.nav_team_btn)
        self.sidebar_layout.addStretch()
        self.sidebar_layout.addWidget(self.nav_log_btn)
        self.sidebar_layout.addWidget(self.nav_data_btn)
        self.sidebar_layout.addWidget(self.nav_sync_btn)

        # --- RESTRUCTURED MAIN VIEW AREA ---
        # Container for the right side (Main Screens + Log Console)
        self.right_container = QWidget()
        self.right_layout = QVBoxLayout(self.right_container)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(10)

        self.main_card_frame = QFrame()
        self.main_card_frame.setObjectName("mainCardFrame")
        self.card_layout = QVBoxLayout(self.main_card_frame)
        self.card_layout.setContentsMargins(20, 20, 20, 20)

        self.stacked_widget = QStackedWidget()
        self.card_layout.addWidget(self.stacked_widget)

        self.dash_screen = DashboardWidget()
        self.gantt_screen = GanttScreenWidget()
        self.team_screen = TeamManagementWidget()
        self.data_screen = DataViewWidget()

        self.stacked_widget.addWidget(self.dash_screen)
        self.stacked_widget.addWidget(self.gantt_screen)
        self.stacked_widget.addWidget(self.team_screen)
        self.stacked_widget.addWidget(self.data_screen)

        # Add main card to the top of the right container
        self.right_layout.addWidget(self.main_card_frame, 1)

        # --- BUILD THE LOG CONSOLE ---
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setFixedHeight(250)
        self.log_console.hide() # Hide it by default
        self.log_console.setStyleSheet("""
            QPlainTextEdit {
                background-color: #151515;
                color: #A9A9A9;
                font-family: Consolas, 'Courier New', monospace;
                border-radius: 8px;
                padding: 10px;
                border: 1px solid #3E3E42;
            }
        """)
        # Add log console to the bottom of the right container
        self.right_layout.addWidget(self.log_console, 0)

        # Assemble the final root layout
        main_layout.addWidget(self.sidebar_frame)
        main_layout.addWidget(self.right_container, 1)

        # Connect navigation clicks
        self.nav_dash_btn.clicked.connect(lambda: self.switch_view(0))
        self.nav_gantt_btn.clicked.connect(lambda: self.switch_view(1))
        self.nav_team_btn.clicked.connect(lambda: self.switch_view(2))
        self.nav_data_btn.clicked.connect(lambda: self.switch_view(3))

        # Connect log toggle button
        self.nav_log_btn.clicked.connect(self.toggle_log_console)

        # Map child widget variables for the controller to use
        self.raw_table = self.data_screen.raw_table
        self.filter_team = self.gantt_screen.filter_team
        self.filter_req = self.gantt_screen.filter_req
        self.filter_status = self.gantt_screen.filter_status

        self.gantt_scene = self.gantt_screen.gantt_scene
        self.gantt_view = self.gantt_screen.gantt_view
        self.header_scene = self.gantt_screen.header_scene
        self.header_view = self.gantt_screen.header_view
        self.info_table = self.gantt_screen.info_table

        self.kpi_panel = self.gantt_screen.kpi_panel
        self.kpi_title = self.gantt_screen.kpi_title
        self.inp_smart_id = self.gantt_screen.inp_smart_id
        self.inp_est_days = self.gantt_screen.inp_est_days
        self.inp_assignee = self.gantt_screen.inp_assignee

        self.kpi_order = self.gantt_screen.kpi_order
        self.kpi_quote = self.gantt_screen.kpi_quote
        self.kpi_req = self.gantt_screen.kpi_req
        self.kpi_esd = self.gantt_screen.kpi_esd
        self.kpi_eng_due = self.gantt_screen.kpi_eng_due
        self.kpi_eng_var = self.gantt_screen.kpi_eng_var
        self.kpi_esd_var = self.gantt_screen.kpi_esd_var

        # Set the initial view and highlight state
        self.switch_view(0)

    def switch_view(self, index: int):
        """Updates the stacked widget and handles nav button highlighting."""
        self.stacked_widget.setCurrentIndex(index)
        self.nav_dash_btn.setChecked(index == 0)
        self.nav_gantt_btn.setChecked(index == 1)
        self.nav_team_btn.setChecked(index == 2)
        self.nav_data_btn.setChecked(index == 3)

    def toggle_log_console(self):
        """Shows or hides the bottom log console panel."""
        if self.nav_log_btn.isChecked():
            self.log_console.show()
        else:
            self.log_console.hide()

    def append_log_message(self, message: str):
        """Safely appends a new message to the UI log console and auto-scrolls."""
        self.log_console.appendPlainText(message)
        # Scroll to the bottom automatically
        scrollbar = self.log_console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def show_status(self, message: str, timeout: int = 4000):
        self.statusBar().showMessage(message, timeout)

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
        table_widget.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        for row in range(df.shape[0]):
            for col in range(df.shape[1]):
                cell_value = str(df.iat[row, col])
                item = QTableWidgetItem(cell_value)
                table_widget.setItem(row, col, item)
        table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

    def show_warning(self, title: str, message: str):
        QMessageBox.warning(self, title, message)