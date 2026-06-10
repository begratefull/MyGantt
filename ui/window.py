"""
The main QMainWindow for the MyGantt application.
Responsible for assembling the layout, sidebar navigation,
and linking the Controller to the UI components.
"""

import os
from typing import Any
from PySide6.QtWidgets import (QMainWindow, QPushButton, QVBoxLayout, QHBoxLayout,
                               QWidget, QMessageBox, QTableWidgetItem, QHeaderView,
                               QStackedWidget, QFrame, QPlainTextEdit, QTableWidget, QLabel)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon

from logic.constants import AppConstants
from ui.views.dashboard import DashboardWidget
from ui.views.data_view import DataViewWidget
from ui.views.gantt_view import GanttScreenWidget
from ui.views.team_view import TeamManagementWidget
import pandas as pd


class MyGanttWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MyGantt")
        self.resize(1500, 1000)

        base_path = os.path.dirname(__file__)
        self.setWindowIcon(QIcon(os.path.join(base_path, "resources", "app_icon.ico")))

        self.statusBar().showMessage("Ready")
        self.statusBar().setStyleSheet("color: #AAAAAA; background-color: #1E1E1E; border-top: 1px solid #3E3E42;")

        # Version Number to far right of Status Bar
        self.version_label = QLabel(AppConstants.APP_VERSION)
        self.version_label.setObjectName("VersionLabel")
        self.version_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self.statusBar().addPermanentWidget(self.version_label)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        self.sidebar_frame = QFrame()
        self.sidebar_frame.setObjectName("sidebarFrame")
        self.sidebar_frame.setFixedWidth(70)
        self.sidebar_layout = QVBoxLayout(self.sidebar_frame)
        self.sidebar_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.sidebar_layout.setContentsMargins(10, 20, 10, 10)
        self.sidebar_layout.setSpacing(15)

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

        self.nav_log_btn = QPushButton("")
        self.nav_log_btn.setIcon(QIcon(os.path.join(base_path, "resources", "log.svg")))
        self.nav_log_btn.setToolTip("Toggle Application Logs")

        for btn in [self.nav_dash_btn, self.nav_gantt_btn, self.nav_team_btn, self.nav_data_btn, self.nav_sync_btn, self.nav_log_btn]:
            btn.setObjectName("NavButton")
            btn.setFixedSize(50, 50)
            btn.setIconSize(QSize(24, 24))

        self.nav_dash_btn.setCheckable(True)
        self.nav_gantt_btn.setCheckable(True)
        self.nav_team_btn.setCheckable(True)
        self.nav_data_btn.setCheckable(True)
        self.nav_log_btn.setCheckable(True)

        self.sidebar_layout.addWidget(self.nav_dash_btn)
        self.sidebar_layout.addWidget(self.nav_gantt_btn)
        self.sidebar_layout.addWidget(self.nav_team_btn)
        self.sidebar_layout.addStretch()
        self.sidebar_layout.addWidget(self.nav_log_btn)
        self.sidebar_layout.addWidget(self.nav_data_btn)
        self.sidebar_layout.addWidget(self.nav_sync_btn)

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

        self.right_layout.addWidget(self.main_card_frame, 1)

        self.log_console = QPlainTextEdit(self.right_container)
        self.log_console.setReadOnly(True)
        self.log_console.hide()

        self.log_console.setStyleSheet("""
            QPlainTextEdit {
                background-color: rgba(18, 18, 18, 0.95); 
                color: #A9A9A9;
                font-family: Consolas, 'Courier New', monospace;
                border-radius: 12px;
                padding: 15px;
                border: 2px solid #555555;
            }
        """)

        main_layout.addWidget(self.sidebar_frame)
        main_layout.addWidget(self.right_container, 1)

        self.nav_dash_btn.clicked.connect(lambda: self.switch_view(0))
        self.nav_gantt_btn.clicked.connect(lambda: self.switch_view(1))
        self.nav_team_btn.clicked.connect(lambda: self.switch_view(2))
        self.nav_data_btn.clicked.connect(lambda: self.switch_view(3))

        self.nav_log_btn.clicked.connect(self.toggle_log_console)

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

        self.switch_view(0)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self.reposition_logger()

    def reposition_logger(self) -> None:
        if hasattr(self, 'log_console') and not self.log_console.isHidden():
            logger_width = 800
            logger_height = 500

            container_w = self.right_container.width()
            container_h = self.right_container.height()

            x = (container_w - logger_width) // 2
            y = (container_h - logger_height) // 2

            self.log_console.setGeometry(x, y, logger_width, logger_height)
            self.log_console.raise_()

    def switch_view(self, index: int) -> None:
        self.stacked_widget.setCurrentIndex(index)
        self.nav_dash_btn.setChecked(index == 0)
        self.nav_gantt_btn.setChecked(index == 1)
        self.nav_team_btn.setChecked(index == 2)
        self.nav_data_btn.setChecked(index == 3)

    def toggle_log_console(self) -> None:
        if self.nav_log_btn.isChecked():
            self.log_console.show()
            self.reposition_logger()
        else:
            self.log_console.hide()

    def append_log_message(self, message: str) -> None:
        self.log_console.appendPlainText(message)
        scrollbar = self.log_console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def show_status(self, message: str, timeout: int = 4000) -> None:
        self.statusBar().showMessage(message, timeout)

    @staticmethod
    def display_dataframe(table_widget: QTableWidget, df: pd.DataFrame) -> None:
        table_widget.clear()
        if df.empty:
            table_widget.setRowCount(0)
            table_widget.setColumnCount(0)
            return
        table_widget.setColumnCount(df.shape[1])
        table_widget.setRowCount(df.shape[0])
        table_widget.setHorizontalHeaderLabels(list(df.columns))
        table_widget.horizontalHeader().setMinimumHeight(35)
        table_widget.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for row in range(df.shape[0]):
            for col in range(df.shape[1]):
                cell_value = str(df.iat[row, col])
                item = QTableWidgetItem(cell_value)
                table_widget.setItem(row, col, item)
        table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

    def show_warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)