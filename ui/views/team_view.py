"""
team_view.py

Provides the TeamManagementWidget, a dedicated interface for assigning
engineers to specific teams, configuring their Gantt chart colors, and
viewing their individual workload analytics.
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QTableWidget, QTableWidgetItem, QHeaderView,
                               QFrame, QComboBox, QPushButton, QColorDialog, QAbstractItemView)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtCharts import QChart, QChartView


class TeamManagementWidget(QWidget):
    save_engineer_requested = Signal(str, str, str)

    def __init__(self):
        super().__init__()
        self._current_selected_color = "#888888"

        # Main Layout is now Vertical!
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(15)

        # ==========================================
        # TOP HALF: Roster (Left) & Config (Right)
        # ==========================================
        top_layout = QHBoxLayout()
        top_layout.setSpacing(15)

        # --- 1. Engineer Roster Table ---
        roster_frame = QFrame()
        roster_frame.setObjectName("TableWell")
        roster_layout = QVBoxLayout(roster_frame)
        roster_layout.setContentsMargins(20, 20, 20, 20)
        roster_layout.setSpacing(15)

        roster_title = QLabel("Engineer Roster")
        roster_title.setObjectName("Header")
        roster_layout.addWidget(roster_title)

        self.roster_table = QTableWidget()
        self.roster_table.setColumnCount(3)
        self.roster_table.setHorizontalHeaderLabels(["Engineer", "Team", "Color"])

        self.roster_table.verticalHeader().setVisible(False)
        self.roster_table.setShowGrid(False)
        self.roster_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.roster_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.roster_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Optimized Column Sizing
        self.roster_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents) # Shrinks to fit name
        self.roster_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch) # Fills the middle space
        self.roster_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed) # Locks the color badge
        self.roster_table.setColumnWidth(2, 60)

        roster_layout.addWidget(self.roster_table)
        top_layout.addWidget(roster_frame, 1) # Takes up 50% of the top width

        # --- 2. Configuration Form ---
        config_frame = QFrame()
        config_frame.setObjectName("TableWell")
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(20, 20, 20, 20)
        config_layout.setSpacing(15)

        config_title = QLabel("Configure Engineer")
        config_title.setObjectName("Header")
        config_layout.addWidget(config_title)

        form_layout = QVBoxLayout()
        form_layout.setSpacing(15)

        # Name Row
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("Engineer Name:"))
        self.inp_name = QComboBox()
        self.inp_name.setEditable(True)
        name_layout.addWidget(self.inp_name, 1)
        form_layout.addLayout(name_layout)

        # Team Row
        team_layout = QHBoxLayout()
        team_layout.addWidget(QLabel("Team Assignment:"))
        self.inp_team = QComboBox()
        self.inp_team.setEditable(True)
        self.inp_team.addItems(["Custom Team", "Standard Team", "NPD Team"])
        team_layout.addWidget(self.inp_team, 1)
        form_layout.addLayout(team_layout)

        # Color Row
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Gantt Block Color:"))
        self.btn_color = QPushButton("Pick Color")
        self.btn_color.setStyleSheet(f"background-color: {self._current_selected_color}; color: white; font-weight: bold; border-radius: 4px;")
        self.btn_color.clicked.connect(self.choose_color)
        color_layout.addWidget(self.btn_color, 1)
        form_layout.addLayout(color_layout)

        config_layout.addLayout(form_layout)
        config_layout.addStretch()

        self.btn_save = QPushButton("Save / Update Engineer")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setMinimumHeight(35)
        self.btn_save.clicked.connect(self.emit_save_request)
        config_layout.addWidget(self.btn_save)

        top_layout.addWidget(config_frame, 1) # Takes up 50% of the top width

        # Add the entire Top Half to the main layout
        main_layout.addLayout(top_layout, 1)

        # ==========================================
        # BOTTOM HALF: Analytics Dashboard
        # ==========================================
        analytics_frame = QFrame()
        analytics_frame.setObjectName("TableWell")
        analytics_layout = QVBoxLayout(analytics_frame)
        analytics_layout.setContentsMargins(20, 20, 20, 20)

        self.lbl_analytics_title = QLabel("Workload Analytics: Select an Engineer")
        self.lbl_analytics_title.setObjectName("DashTitle")
        analytics_layout.addWidget(self.lbl_analytics_title)

        kpi_layout = QHBoxLayout()
        self.lbl_total_lines = self.create_kpi_block(kpi_layout, "Active Lines")
        self.lbl_avg_days = self.create_kpi_block(kpi_layout, "Avg Est Days")
        analytics_layout.addLayout(kpi_layout)

        self.chart = QChart()
        self.chart.setTheme(QChart.ChartThemeDark)
        self.chart.setBackgroundBrush(Qt.NoBrush)
        self.chart.layout().setContentsMargins(0, 0, 0, 0)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setStyleSheet("background: transparent; border: none;")

        analytics_layout.addWidget(self.chart_view, 1)

        # Add the entire Bottom Half to the main layout
        main_layout.addWidget(analytics_frame, 1)

    def create_kpi_block(self, parent_layout, title):
        frame = QFrame()
        frame.setStyleSheet("background-color: #2D2D30; border-radius: 4px;")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(5, 5, 5, 5)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #AAAAAA; font-size: 10px; font-weight: bold;")
        lbl_title.setAlignment(Qt.AlignCenter)

        lbl_val = QLabel("--")
        lbl_val.setStyleSheet("color: #FFFFFF; font-size: 18px; font-weight: bold;")
        lbl_val.setAlignment(Qt.AlignCenter)

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_val)
        parent_layout.addWidget(frame)
        return lbl_val

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self._current_selected_color), self, "Select Gantt Color")
        if color.isValid():
            self._current_selected_color = color.name().upper()
            text_color = "black" if color.lightness() > 150 else "white"
            self.btn_color.setStyleSheet(f"background-color: {self._current_selected_color}; color: {text_color}; font-weight: bold; border-radius: 4px;")

    def emit_save_request(self):
        name = self.inp_name.currentText().strip().upper()
        team = self.inp_team.currentText().strip()
        if name and team:
            self.save_engineer_requested.emit(name, team, self._current_selected_color)

    def populate_roster(self, df):
        self.roster_table.setRowCount(0)
        if df.empty:
            return

        self.roster_table.setRowCount(len(df))
        for row_idx, row in df.iterrows():
            name = str(row.get('name', ''))
            team = str(row.get('team_name', ''))
            color = str(row.get('hex_color', '#888888'))

            # 1. Add Text
            self.roster_table.setItem(row_idx, 0, QTableWidgetItem(name))
            self.roster_table.setItem(row_idx, 1, QTableWidgetItem(team))

            # 2. Add Color Badge (Bypasses PySide6 Stylesheet Bug)
            color_widget = QWidget()
            color_layout = QHBoxLayout(color_widget)
            color_layout.setContentsMargins(0, 0, 0, 0)
            color_layout.setAlignment(Qt.AlignCenter)

            color_badge = QFrame()
            color_badge.setFixedSize(16, 16)
            color_badge.setStyleSheet(f"background-color: {color}; border-radius: 4px; border: 1px solid #1E1E20;")

            color_layout.addWidget(color_badge)
            self.roster_table.setCellWidget(row_idx, 2, color_widget)