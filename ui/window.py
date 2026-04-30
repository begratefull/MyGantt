"""
The main QMainWindow for the MyGantt application.
Responsible for assembling the layout, sidebar navigation,
and linking the Controller to the UI components.
"""

import os
from PySide6.QtWidgets import (QMainWindow, QPushButton, QVBoxLayout, QHBoxLayout,
                               QWidget, QMessageBox, QTableWidgetItem, QHeaderView, QStackedWidget, QFrame)
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

        for btn in [self.nav_dash_btn, self.nav_gantt_btn, self.nav_team_btn, self.nav_data_btn, self.nav_sync_btn]:
            btn.setObjectName("NavButton")
            btn.setFixedSize(50, 50)
            btn.setIconSize(QSize(24, 24))

        self.sidebar_layout.addWidget(self.nav_dash_btn)
        self.sidebar_layout.addWidget(self.nav_gantt_btn)
        self.sidebar_layout.addWidget(self.nav_team_btn)
        self.sidebar_layout.addWidget(self.nav_data_btn)
        self.sidebar_layout.addStretch()
        self.sidebar_layout.addWidget(self.nav_sync_btn)

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

        self.nav_dash_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        self.nav_gantt_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        self.nav_team_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(2))
        self.nav_data_btn.clicked.connect(lambda: self.stacked_widget.setCurrentIndex(3))

        main_layout.addWidget(self.sidebar_frame)
        main_layout.addWidget(self.main_card_frame, 1)

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