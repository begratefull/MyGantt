"""
team_view.py

Provides the TeamManagementWidget, a dedicated interface for assigning
engineers to specific teams, configuring their Gantt chart colors, and
viewing their individual workload analytics.

Phase 3 Updates:
- Expanded the color palette to 25 vibrant, dark-theme optimized colors.
- Upgraded the swatch layout to a QGridLayout for a clean 5x5 presentation.
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QTableWidget, QTableWidgetItem, QHeaderView,
                               QFrame, QComboBox, QPushButton, QAbstractItemView,
                               QGridLayout)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtCharts import (QChart, QChartView, QBarSeries, QBarSet,
                              QBarCategoryAxis, QValueAxis)


class TeamManagementWidget(QWidget):
    """
    The main widget for the Team Management screen.
    Handles engineer configurations (Team/Color) and displays workload analytics.
    """
    # Signals to communicate with the central AppController
    save_engineer_requested = Signal(str, str, str)
    engineer_selected = Signal(str)

    def __init__(self):
        super().__init__()

        # Expanded 25-Color App-Wide Palette (Material Design optimized for Dark UI)
        self.palette = [
            "#D32F2F", "#F44336", "#FF5252", "#E91E63", "#C2185B",  # Reds & Pinks
            "#7B1FA2", "#9C27B0", "#673AB7", "#512DA8", "#3F51B5",  # Purples & Deep Blues
            "#1976D2", "#2196F3", "#03A9F4", "#00BCD4", "#0097A7",  # Blues & Cyans
            "#00796B", "#009688", "#4CAF50", "#388E3C", "#8BC34A",  # Teals & Greens
            "#AFB42B", "#FBC02D", "#FF9800", "#F57C00", "#FF5722"   # Yellows & Oranges
        ]

        self.swatch_buttons = []
        self._current_selected_color = self.palette[11] # Default to a nice MyGantt blue
        self.roster_data = None

        # Main Layout is Vertical
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

        # Emulating the Gold Standard "Raw Data" table styling
        self.roster_table.verticalHeader().setVisible(False)
        self.roster_table.setShowGrid(False)
        self.roster_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.roster_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.roster_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Connect the table selection to our internal handler
        self.roster_table.itemSelectionChanged.connect(self._on_roster_selection)

        # Optimized Column Sizing
        self.roster_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.roster_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.roster_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.roster_table.setColumnWidth(2, 60)

        roster_layout.addWidget(self.roster_table)
        top_layout.addWidget(roster_frame, 1)

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

        # Color Row (Custom 5x5 Grid Palette)
        color_layout = QVBoxLayout()
        color_layout.setSpacing(10)
        color_layout.addWidget(QLabel("Theme Color:"))

        # Use a Grid Layout to display the 25 colors cleanly
        swatch_layout = QGridLayout()
        swatch_layout.setSpacing(8)
        swatch_layout.setAlignment(Qt.AlignLeft)

        for index, color in enumerate(self.palette):
            btn = QPushButton()
            btn.setFixedSize(24, 24) # Slightly smaller to fit grid beautifully
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, c=color: self.set_selected_color(c))
            self.swatch_buttons.append((btn, color))

            # Calculate row and column for 5x5 grid
            row = index // 5
            col = index % 5
            swatch_layout.addWidget(btn, row, col)

        color_layout.addLayout(swatch_layout)
        form_layout.addLayout(color_layout)

        config_layout.addLayout(form_layout)
        config_layout.addStretch()

        self.btn_save = QPushButton("Save / Update Engineer")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setMinimumHeight(35)
        self.btn_save.clicked.connect(self.emit_save_request)
        config_layout.addWidget(self.btn_save)

        top_layout.addWidget(config_frame, 1)
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
        self.chart.setAnimationOptions(QChart.SeriesAnimations)
        self.chart.setBackgroundBrush(Qt.NoBrush)
        self.chart.layout().setContentsMargins(0, 0, 0, 0)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setStyleSheet("background: transparent; border: none;")

        analytics_layout.addWidget(self.chart_view, 1)
        main_layout.addWidget(analytics_frame, 1)

        # Initialize the default selected color styling
        self.set_selected_color(self._current_selected_color)

    def create_kpi_block(self, parent_layout, title):
        """Helper function to create uniform KPI data blocks."""
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

    def set_selected_color(self, color_hex):
        """Updates the selected color and redraws the swatch borders to highlight the active one."""
        self._current_selected_color = color_hex.upper()
        for btn, btn_color in self.swatch_buttons:
            if btn_color.upper() == self._current_selected_color:
                btn.setStyleSheet(f"background-color: {btn_color}; border-radius: 12px; border: 3px solid #FFFFFF;")
            else:
                btn.setStyleSheet(f"background-color: {btn_color}; border-radius: 12px; border: 2px solid #1E1E20;")

    def _on_roster_selection(self):
        """Internal handler fired when a user clicks a row in the roster table."""
        selected_rows = self.roster_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        row_idx = selected_rows[0].row()
        name = self.roster_table.item(row_idx, 0).text()

        # Auto-fill the form with the selected user's data
        if self.roster_data is not None and not self.roster_data.empty:
            match = self.roster_data[self.roster_data['name'].str.upper() == name.upper()]
            if not match.empty:
                team = match.iloc[0].get('team_name', '')
                color = match.iloc[0].get('hex_color', self.palette[11])

                self.inp_name.setCurrentText(name)
                self.inp_team.setCurrentText(team)

                if color.upper() in [c.upper() for c in self.palette]:
                    self.set_selected_color(color)

        # Tell the controller an engineer was clicked so it can calculate analytics
        self.engineer_selected.emit(name)

    def emit_save_request(self):
        """Emits the form data to be saved to the database."""
        name = self.inp_name.currentText().strip().upper()
        team = self.inp_team.currentText().strip()
        if name and team:
            self.save_engineer_requested.emit(name, team, self._current_selected_color)

    def populate_roster(self, df):
        """Clears and populates the engineer roster table from a DataFrame."""
        self.roster_data = df # Cache the DF for auto-filling the form later
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

            # 2. Add Color Badge
            color_widget = QWidget()
            color_layout = QHBoxLayout(color_widget)
            color_layout.setContentsMargins(0, 0, 0, 0)
            color_layout.setAlignment(Qt.AlignCenter)

            color_badge = QFrame()
            color_badge.setFixedSize(16, 16)
            color_badge.setStyleSheet(f"background-color: {color}; border-radius: 8px; border: 1px solid #1E1E20;")

            color_layout.addWidget(color_badge)
            self.roster_table.setCellWidget(row_idx, 2, color_widget)

    def update_analytics(self, engineer_name: str, active_lines: int, avg_days: float,
                         family_counts: dict, primary_color: str = "#007ACC"):
        """
        Updates the UI elements of the Analytics Dashboard for a specific engineer.
        Draws a bar chart showing the frequency of different project 'Families' they work on.
        """
        self.lbl_analytics_title.setText(f"Workload Analytics: {engineer_name}")
        self.lbl_total_lines.setText(str(active_lines))
        self.lbl_avg_days.setText(f"{avg_days:.1f}" if avg_days > 0 else "0.0")

        # 1. Clean up old chart data
        self.chart.removeAllSeries()
        for axis in self.chart.axes():
            self.chart.removeAxis(axis)

        if not family_counts:
            return

        # 2. Build the new Bar Series
        series = QBarSeries()
        bar_set = QBarSet("Projects")
        bar_set.setColor(QColor(primary_color))

        categories = []
        max_val = 0
        for family, count in family_counts.items():
            bar_set.append(count)
            categories.append(str(family))
            if count > max_val:
                max_val = count

        series.append(bar_set)
        self.chart.addSeries(series)

        # 3. Attach X Axis (Categories)
        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsBrush(QColor("#AAAAAA"))
        self.chart.addAxis(axis_x, Qt.AlignBottom)
        series.attachAxis(axis_x)

        # 4. Attach Y Axis (Values)
        axis_y = QValueAxis()
        axis_y.setRange(0, max_val + (max_val * 0.2))  # Give 20% headroom at the top
        axis_y.setLabelFormat("%d")                    # Whole numbers only
        axis_y.setLabelsBrush(QColor("#AAAAAA"))
        self.chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_y)

        self.chart.legend().hide()