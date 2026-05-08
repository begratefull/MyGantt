"""
Provides the TeamManagementWidget, a dedicated interface for assigning
engineers to specific teams, configuring their Gantt chart colors, and
viewing their individual workload analytics.
"""

from typing import Dict, List, Tuple, Optional, Any

import pandas as pd
from PySide6.QtCharts import (
    QChart, QChartView, QPolarChart, QLineSeries, QBarSeries, QBarSet, QBarCategoryAxis,
    QAreaSeries, QCategoryAxis, QValueAxis
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QFrame, QComboBox,
    QPushButton, QAbstractItemView, QGridLayout, QFormLayout, QProgressBar
)


class TeamManagementWidget(QWidget):
    """
    The main widget for the Team Management screen.
    Handles engineer configurations (Team/Color) and displays workload analytics.
    """
    save_engineer_requested = Signal(str, str, str)
    engineer_selected = Signal(str)

    def __init__(self) -> None:
        super().__init__()

        self.palette: List[str] = [
            "#D32F2F", "#F44336", "#FF5252", "#E91E63", "#C2185B",
            "#7B1FA2", "#9C27B0", "#673AB7", "#512DA8", "#3F51B5",
            "#1976D2", "#2196F3", "#03A9F4", "#00BCD4", "#0097A7",
            "#00796B", "#009688", "#4CAF50", "#388E3C", "#8BC34A",
            "#AFB42B", "#FBC02D", "#FF9800", "#F57C00", "#FF5722"
        ]

        self.swatch_buttons: List[Tuple[QPushButton, str]] = []
        self._current_selected_color: str = self.palette[11]
        self.roster_data: Optional[pd.DataFrame] = None

        # Store animations so PySide6's garbage collector doesn't destroy them
        self.progress_animations = []

        self._setup_ui()

    def _get_empty_dark_chart(self) -> QChart:
        chart = QChart()
        chart.setTheme(QChart.ChartThemeDark)
        chart.setBackgroundBrush(Qt.NoBrush)
        chart.layout().setContentsMargins(10, 10, 10, 10)
        chart.legend().hide()
        return chart

    def _safe_set_chart(self, chart_view: QChartView, new_chart: QChart) -> None:
        old_chart = chart_view.chart()
        chart_view.setChart(new_chart)
        if old_chart:
            old_chart.deleteLater()

    def _setup_ui(self) -> None:
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(15)

        # ==========================================
        # LEFT COLUMN: Roster & Config
        # ==========================================
        left_layout = QVBoxLayout()
        left_layout.setSpacing(15)

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
        self.roster_table.itemSelectionChanged.connect(self._on_roster_selection)

        self.roster_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.roster_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.roster_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.roster_table.setColumnWidth(2, 60)

        roster_layout.addWidget(self.roster_table)
        left_layout.addWidget(roster_frame, 3)

        config_frame = QFrame()
        config_frame.setObjectName("TableWell")
        config_layout = QVBoxLayout(config_frame)
        config_layout.setContentsMargins(20, 20, 20, 20)
        config_layout.setSpacing(15)

        config_title = QLabel("Configure Engineer")
        config_title.setObjectName("Header")
        config_layout.addWidget(config_title)

        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(15)

        self.inp_name = QComboBox()
        self.inp_name.setEditable(True)
        form_layout.addRow("Engineer Name:", self.inp_name)

        self.inp_team = QComboBox()
        self.inp_team.setEditable(True)
        self.inp_team.addItems(["Custom Team", "Standard Team", "NPD Team"])
        form_layout.addRow("Team Assignment:", self.inp_team)

        swatch_container = QWidget()
        swatch_layout = QGridLayout(swatch_container)
        swatch_layout.setContentsMargins(0, 0, 0, 0)
        swatch_layout.setSpacing(8)
        swatch_layout.setAlignment(Qt.AlignLeft)

        for index, color in enumerate(self.palette):
            btn = QPushButton()
            btn.setFixedSize(24, 24)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, c=color: self.set_selected_color(c))
            self.swatch_buttons.append((btn, color))
            row = index // 5
            col = index % 5
            swatch_layout.addWidget(btn, row, col)

        form_layout.addRow("Theme Color:", swatch_container)
        config_layout.addLayout(form_layout)
        config_layout.addStretch()

        self.btn_save = QPushButton("Save / Update Engineer")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setMinimumHeight(35)
        self.btn_save.clicked.connect(self.emit_save_request)
        config_layout.addWidget(self.btn_save)

        left_layout.addWidget(config_frame, 2)
        main_layout.addLayout(left_layout, 1)

        # ==========================================
        # RIGHT COLUMN: Analytics Dashboard
        # ==========================================
        analytics_frame = QFrame()
        analytics_frame.setObjectName("TableWell")
        analytics_layout = QVBoxLayout(analytics_frame)
        analytics_layout.setContentsMargins(20, 20, 20, 20)
        analytics_layout.setSpacing(20)

        # Main Title Header - Bumped up font size!
        self.lbl_analytics_title = QLabel("Workload Analytics: Select an Engineer")
        self.lbl_analytics_title.setStyleSheet("color: #FFFFFF; font-size: 24px; font-weight: bold;")
        analytics_layout.addWidget(self.lbl_analytics_title)

        # Dashboard Body Split (Left Sidebar / Right Main Stage)
        dashboard_body_layout = QHBoxLayout()
        dashboard_body_layout.setSpacing(20)

        # --- DASHBOARD LEFT SIDEBAR (KPIs, List, Circle) ---
        dash_left_layout = QVBoxLayout()
        dash_left_layout.setSpacing(15)

        # Custom Progress Bar Leaderboard (With KPIs merged into header)
        projects_frame = QFrame()
        projects_frame.setObjectName("DashCard")
        projects_layout = QVBoxLayout(projects_frame)

        # 1. Cleaned up KPIs - no inner borders, pure data
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(20)

        prod_layout = QVBoxLayout()
        prod_title = QLabel("TOTAL PROD LINES")
        prod_title.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
        self.kpi_prod_lbl = QLabel("0")
        self.kpi_prod_lbl.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: bold;")
        prod_layout.addWidget(prod_title)
        prod_layout.addWidget(self.kpi_prod_lbl)

        sub_layout = QVBoxLayout()
        sub_title = QLabel("TOTAL SUB LINES")
        sub_title.setStyleSheet("color: #888888; font-size: 11px; font-weight: bold;")
        self.kpi_sub_lbl = QLabel("0")
        self.kpi_sub_lbl.setStyleSheet("color: #FFFFFF; font-size: 28px; font-weight: bold;")
        sub_layout.addWidget(sub_title)
        sub_layout.addWidget(self.kpi_sub_lbl)

        kpi_layout.addLayout(prod_layout)
        kpi_layout.addLayout(sub_layout)

        projects_layout.addLayout(kpi_layout)

        # Sleek Divider
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #2E2E32;")
        projects_layout.addWidget(sep)

        projects_title = QLabel("Top High-Value Projects")
        projects_title.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: bold; margin-top: 5px;")
        projects_layout.addWidget(projects_title)

        self.projects_container = QWidget()
        self.projects_vbox = QVBoxLayout(self.projects_container)
        self.projects_vbox.setAlignment(Qt.AlignTop)
        self.projects_vbox.setContentsMargins(0, 10, 0, 0)
        self.projects_vbox.setSpacing(15)

        projects_layout.addWidget(self.projects_container, 1)
        dash_left_layout.addWidget(projects_frame, 1)

        # 3. Radar Chart
        radar_frame = QFrame()
        radar_frame.setObjectName("DashCard")
        radar_layout = QVBoxLayout(radar_frame)
        radar_title = QLabel("Top Fixture Families")
        radar_title.setObjectName("CardTitle")
        radar_layout.addWidget(radar_title)

        empty_polar = QPolarChart()
        empty_polar.setTheme(QChart.ChartThemeDark)
        empty_polar.setBackgroundBrush(Qt.NoBrush)
        empty_polar.layout().setContentsMargins(5, 5, 5, 5)

        self.radar_view = QChartView(empty_polar)
        self.radar_view.setRenderHint(QPainter.Antialiasing)
        self.radar_view.setStyleSheet("background: transparent;")
        radar_layout.addWidget(self.radar_view, 1)

        dash_left_layout.addWidget(radar_frame, 1)

        dashboard_body_layout.addLayout(dash_left_layout, 1)


        # --- DASHBOARD RIGHT MAIN STAGE (Wide Charts) ---
        dash_right_layout = QVBoxLayout()
        dash_right_layout.setSpacing(15)

        # 1. Production Throughput Chart (Top)
        self.prod_card = QFrame()
        self.prod_card.setObjectName("DashCard")
        self.prod_layout = QVBoxLayout(self.prod_card)
        prod_title = QLabel("YTD Production Throughput")
        prod_title.setObjectName("CardTitle")
        self.prod_layout.addWidget(prod_title)

        self.prod_chart_view = QChartView(self._get_empty_dark_chart())
        self.prod_chart_view.setRenderHint(QPainter.Antialiasing)
        self.prod_chart_view.setStyleSheet("background: transparent;")
        self.prod_layout.addWidget(self.prod_chart_view, 1)

        dash_right_layout.addWidget(self.prod_card, 1)

        # 2. Submittal Throughput Chart (Bottom)
        self.sub_card = QFrame()
        self.sub_card.setObjectName("DashCard")
        self.sub_layout = QVBoxLayout(self.sub_card)
        sub_title = QLabel("YTD Submittal Throughput")
        sub_title.setObjectName("CardTitle")
        self.sub_layout.addWidget(sub_title)

        self.sub_chart_view = QChartView(self._get_empty_dark_chart())
        self.sub_chart_view.setRenderHint(QPainter.Antialiasing)
        self.sub_chart_view.setStyleSheet("background: transparent;")
        self.sub_layout.addWidget(self.sub_chart_view, 1)

        dash_right_layout.addWidget(self.sub_card, 1)

        dashboard_body_layout.addLayout(dash_right_layout, 2)

        analytics_layout.addLayout(dashboard_body_layout, 1)
        main_layout.addWidget(analytics_frame, 3)

        self.set_selected_color(self._current_selected_color)

    def set_selected_color(self, color_hex: str) -> None:
        self._current_selected_color = color_hex.upper()
        for btn, btn_color in self.swatch_buttons:
            if btn_color.upper() == self._current_selected_color:
                btn.setStyleSheet(f"background-color: {btn_color}; border-radius: 12px; border: 3px solid #FFFFFF;")
            else:
                btn.setStyleSheet(f"background-color: {btn_color}; border-radius: 12px; border: 2px solid #1E1E20;")

    def _on_roster_selection(self) -> None:
        selected_rows = self.roster_table.selectionModel().selectedRows()
        if not selected_rows: return

        row_idx = selected_rows[0].row()
        name = self.roster_table.item(row_idx, 0).text()

        if self.roster_data is not None and not self.roster_data.empty:
            match = self.roster_data[self.roster_data['name'].str.upper() == name.upper()]
            if not match.empty:
                team = match.iloc[0].get('team_name', '')
                color = match.iloc[0].get('hex_color', self.palette[11])
                self.inp_name.setCurrentText(name)
                self.inp_team.setCurrentText(team)
                if color.upper() in [c.upper() for c in self.palette]:
                    self.set_selected_color(color)

        self.engineer_selected.emit(name)

    def emit_save_request(self) -> None:
        name = self.inp_name.currentText().strip().upper()
        team = self.inp_team.currentText().strip()
        if name and team:
            self.save_engineer_requested.emit(name, team, self._current_selected_color)

    def populate_roster(self, df: pd.DataFrame) -> None:
        self.roster_table.setRowCount(0)
        if df.empty:
            self.roster_data = df
            return

        team_order = ["Custom Team", "Standard Team", "NPD Team"]
        df_sorted = df.copy()
        df_sorted['team_name'] = pd.Categorical(df_sorted['team_name'], categories=team_order, ordered=True)
        df_sorted = df_sorted.sort_values(['team_name', 'name'], na_position='last').reset_index(drop=True)

        self.roster_data = df_sorted
        self.roster_table.setRowCount(len(df_sorted))

        for row_idx, row in df_sorted.iterrows():
            name = str(row.get('name', ''))
            team = str(row.get('team_name', ''))
            color = str(row.get('hex_color', '#888888'))

            self.roster_table.setItem(row_idx, 0, QTableWidgetItem(name))
            self.roster_table.setItem(row_idx, 1, QTableWidgetItem(team))

            color_widget = QWidget()
            color_layout = QHBoxLayout(color_widget)
            color_layout.setContentsMargins(0, 0, 0, 0)
            color_layout.setAlignment(Qt.AlignCenter)

            color_badge = QFrame()
            color_badge.setFixedSize(16, 16)
            color_badge.setStyleSheet(f"background-color: {color}; border-radius: 8px; border: 1px solid #1E1E20;")

            color_layout.addWidget(color_badge)
            self.roster_table.setCellWidget(row_idx, 2, color_widget)

    # ===============================================
    # VISUAL CHART GENERATORS
    # ===============================================

    def _populate_throughput(self, chart_view: QChartView, data_dict: Dict[str, Dict[str, float]], primary_color: str) -> None:
        new_chart = self._get_empty_dark_chart()
        new_chart.setAnimationOptions(QChart.SeriesAnimations) # Retain animation for bars

        if not data_dict:
            self._safe_set_chart(chart_view, new_chart)
            return

        bar_series = QBarSeries()
        bar_set = QBarSet("Total Lines")
        fill_color = QColor(primary_color)
        fill_color.setAlpha(200)
        bar_set.setColor(fill_color)
        bar_set.setBorderColor(QColor(primary_color))

        speed_series = QLineSeries()
        speed_series.setName("Avg Days")
        speed_pen = QPen(QColor("#FFFFFF"), 3)
        speed_series.setPen(speed_pen)

        categories = []
        max_lines = 0
        max_days = 0.0

        for i, (l_type, stats) in enumerate(data_dict.items()):
            lines = stats['lines']
            days = stats['avg_days']
            categories.append(l_type)

            bar_set.append(lines)
            speed_series.append(i, days)

            if lines > max_lines: max_lines = lines
            if days > max_days: max_days = days

        bar_series.append(bar_set)

        new_chart.addSeries(bar_series)
        new_chart.addSeries(speed_series)

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_x.setLabelsBrush(QColor("#AAAAAA"))
        axis_x.setGridLineVisible(False)
        new_chart.addAxis(axis_x, Qt.AlignBottom)
        bar_series.attachAxis(axis_x)
        speed_series.attachAxis(axis_x)

        axis_y_left = QValueAxis()
        axis_y_left.setLabelFormat("%d")
        axis_y_left.setTitleText("Total Lines")
        axis_y_left.setTitleBrush(QColor("#AAAAAA"))
        axis_y_left.setRange(0, max_lines + (max_lines * 0.2) + 1)
        axis_y_left.setLabelsBrush(QColor(primary_color))
        axis_y_left.setGridLineColor(QColor("#333333"))
        new_chart.addAxis(axis_y_left, Qt.AlignLeft)
        bar_series.attachAxis(axis_y_left)

        axis_y_right = QValueAxis()
        axis_y_right.setLabelFormat("%.1f")
        axis_y_right.setTitleText("Avg Days")
        axis_y_right.setTitleBrush(QColor("#AAAAAA"))
        axis_y_right.setRange(0, max_days + (max_days * 0.2) + 1)
        axis_y_right.setLabelsBrush(QColor("#FFFFFF"))
        axis_y_right.setGridLineVisible(False)
        new_chart.addAxis(axis_y_right, Qt.AlignRight)
        speed_series.attachAxis(axis_y_right)

        bar_series.setLabelsVisible(True)
        bar_set.setLabelColor(QColor("#FFFFFF"))

        new_chart.legend().show()
        new_chart.legend().setAlignment(Qt.AlignBottom)
        new_chart.legend().setLabelBrush(QColor("#FFFFFF"))

        self._safe_set_chart(chart_view, new_chart)

    def _populate_top_projects(self, projects_list: List[Dict[str, Any]], primary_color: str) -> None:
        self.progress_animations.clear() # Clear out old animations

        while self.projects_vbox.count():
            child = self.projects_vbox.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not projects_list:
            empty_label = QLabel("No high-value projects found.")
            empty_label.setStyleSheet("color: #666666; font-style: italic;")
            self.projects_vbox.addWidget(empty_label)
            return

        max_val = max([float(p.get('total_sell', 0.0)) for p in projects_list])
        if max_val == 0: max_val = 1

        for index, proj in enumerate(projects_list):
            val = float(proj.get('total_sell', 0.0))
            name = str(proj.get('FUZZY_PROJ', 'Unknown Project'))

            row_container = QWidget()
            row_layout = QVBoxLayout(row_container)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(4)

            text_layout = QHBoxLayout()

            lbl_name = QLabel(f"#{index + 1}  {name}")
            lbl_name.setStyleSheet("color: #E0E0E0; font-size: 12px; font-weight: bold;")

            lbl_val = QLabel(f"${val:,.0f}")
            lbl_val.setStyleSheet("color: #AAAAAA; font-size: 12px;")

            text_layout.addWidget(lbl_name)
            text_layout.addStretch()
            text_layout.addWidget(lbl_val)

            row_layout.addLayout(text_layout)

            bar = QProgressBar()
            bar.setFixedHeight(6)
            bar.setTextVisible(False)
            bar.setRange(0, int(max_val))
            bar.setValue(0) # Start at 0 for animation

            bar.setStyleSheet(f"""
                QProgressBar {{
                    background-color: #2A2A2E;
                    border: none;
                    border-radius: 3px;
                }}
                QProgressBar::chunk {{
                    background-color: {primary_color};
                    border-radius: 3px;
                }}
            """)

            row_layout.addWidget(bar)
            self.projects_vbox.addWidget(row_container)

            # Create a smooth animation for each bar sliding in!
            anim = QPropertyAnimation(bar, b"value")
            anim.setDuration(800) # milliseconds
            anim.setStartValue(0)
            anim.setEndValue(int(val))
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self.progress_animations.append(anim)
            anim.start()

    def _populate_radar(self, radar_data: Dict[str, Any], primary_color: str) -> None:
        new_chart = QPolarChart()
        new_chart.setTheme(QChart.ChartThemeDark)
        new_chart.setBackgroundBrush(Qt.NoBrush)
        new_chart.layout().setContentsMargins(5, 5, 5, 5)

        # Explicitly NO animations added here to respect request

        categories = radar_data.get('categories', [])
        prod_vals = radar_data.get('prod', [])

        if not categories:
            self._safe_set_chart(self.radar_view, new_chart)
            return

        series_prod = QLineSeries()
        series_prod.setName("Production Lines")
        color_prod = QColor(primary_color)
        series_prod.setPen(QPen(color_prod, 3))

        series_zero = QLineSeries()

        max_val = 0
        for i, cat in enumerate(categories):
            p_val = prod_vals[i] if i < len(prod_vals) else 0

            series_prod.append(i, p_val)
            series_zero.append(i, 0)
            max_val = max(max_val, p_val)

        if categories:
            series_prod.append(len(categories), series_prod.at(0).y())
            series_zero.append(len(categories), 0)

        area_prod = QAreaSeries(series_prod, series_zero)
        area_prod.setName("Production Lines")
        area_prod._series_prod_ref = series_prod
        area_prod._series_zero_ref = series_zero

        fill_color = QColor(primary_color)
        fill_color.setAlpha(80)
        area_prod.setBrush(fill_color)
        area_prod.setPen(QPen(color_prod, 2))

        new_chart.addSeries(area_prod)

        angular_axis = QCategoryAxis()
        angular_axis.setLabelsBrush(QColor("#AAAAAA"))
        angular_axis.setLabelsPosition(QCategoryAxis.AxisLabelsPositionOnValue)

        for i, cat in enumerate(categories):
            angular_axis.append(cat, i)

        angular_axis.append("\u200B", len(categories))
        angular_axis.setRange(0, len(categories))

        new_chart.addAxis(angular_axis, QPolarChart.PolarOrientationAngular)
        area_prod.attachAxis(angular_axis)

        radial_axis = QValueAxis()
        radial_axis.setLabelsBrush(QColor("#AAAAAA"))
        radial_axis.setLabelFormat("%d")
        radial_axis.setRange(0, max_val + (max_val * 0.2) + 1)
        radial_axis.setTickCount(4)

        new_chart.addAxis(radial_axis, QPolarChart.PolarOrientationRadial)
        area_prod.attachAxis(radial_axis)

        new_chart.legend().setAlignment(Qt.AlignBottom)
        new_chart.legend().setLabelBrush(QColor("#FFFFFF"))

        self._safe_set_chart(self.radar_view, new_chart)

    def update_analytics(self, engineer_name: str, analytics_payload: Dict[str, Any], primary_color: str = "#007ACC") -> None:
        self.lbl_analytics_title.setText(f"Workload Analytics: {engineer_name}")

        kpis = analytics_payload.get('kpis', {'total_prod': 0, 'total_sub': 0})
        self.kpi_prod_lbl.setText(str(kpis['total_prod']))
        self.kpi_sub_lbl.setText(str(kpis['total_sub']))

        self._populate_throughput(self.prod_chart_view, analytics_payload['throughput'].get('prod', {}), primary_color)
        self._populate_throughput(self.sub_chart_view, analytics_payload['throughput'].get('sub', {}), primary_color)

        self._populate_top_projects(analytics_payload.get('projects', []), primary_color)
        self._populate_radar(analytics_payload.get('radar', {}), primary_color)