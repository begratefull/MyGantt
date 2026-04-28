"""
Contains the DashboardWidget which displays high-level KPIs,
detailed performance grids, queue distributions, and timeline forecasting.
"""

from typing import Dict, Any, Optional, List

import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox, QGridLayout, QSizePolicy
)
from PySide6.QtCharts import (
    QChart, QChartView, QPieSeries, QPieSlice, QBarSeries, QBarSet,
    QBarCategoryAxis, QValueAxis, QLineSeries, QAreaSeries
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QFont

from logic.dashboard_service import DashboardService


class DashboardWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.master_df: pd.DataFrame = pd.DataFrame()
        self.team_map: Dict[str, str] = {}
        self.color_map: Dict[str, str] = {}

        self._current_eng_dist: Dict[str, Any] = {}
        self._global_req_dist: Dict[str, int] = {}

        self.dynamic_color_map: Dict[str, str] = {}
        self.palette: List[str] = [
            "#2196F3", "#F44336", "#4CAF50", "#FF9800",
            "#9C27B0", "#00BCD4", "#795548", "#E91E63"
        ]
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(15)

        # --- Header Section ---
        header_layout = QHBoxLayout()
        header = QLabel("Engineering Workload Dashboard")
        header.setObjectName("Header")
        header_layout.addWidget(header)
        header_layout.addStretch()

        filter_lbl = QLabel("Global Team Filter:")
        filter_lbl.setObjectName("FilterLabel")
        header_layout.addWidget(filter_lbl)

        self.filter_team = QComboBox()
        self.filter_team.setMinimumWidth(150)
        self.filter_team.addItem("All Teams")
        self.filter_team.currentTextChanged.connect(self.render_all)
        header_layout.addWidget(self.filter_team)

        main_layout.addLayout(header_layout)

        # --- Top Half Split ---
        top_half_layout = QHBoxLayout()
        top_half_layout.setSpacing(15)

        # Left Column: KPI Grid (Cards)
        left_pane = QWidget()
        cards_grid = QGridLayout(left_pane)
        cards_grid.setContentsMargins(0, 0, 0, 0)
        cards_grid.setSpacing(15)

        self.card_delivery = self._build_delivery_card()
        self.card_backlog = self._build_backlog_card()
        self.card_mod = self._build_vertical_health_card("MOD Health")
        self.card_cus = self._build_vertical_health_card("CUS Health")

        cards_grid.addWidget(self.card_delivery['frame'], 0, 0)
        cards_grid.addWidget(self.card_backlog['frame'], 0, 1)
        cards_grid.addWidget(self.card_mod['frame'], 1, 0)
        cards_grid.addWidget(self.card_cus['frame'], 1, 1)

        # Right Column: Interactive Master-Detail Pies
        self.dist_ui = self._build_interactive_chart_panel()

        top_half_layout.addWidget(left_pane, 4)  # 40% width
        top_half_layout.addWidget(self.dist_ui['card'], 6)  # 60% width

        main_layout.addLayout(top_half_layout, 1)

        # --- Bottom Half: Timeline ---
        self.timeline_ui = self._build_timeline_card("Completed Jobs & Active Forecast")
        main_layout.addWidget(self.timeline_ui['card'], 1)

        self.timeline_ui['date_filter'].currentTextChanged.connect(self.render_all)

    # ---------------------------------------------------------
    # UI Component Builders
    # ---------------------------------------------------------

    def _build_delivery_card(self) -> Dict[str, Any]:
        frame = QFrame()
        frame.setObjectName("DashCard")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("Global Delivery %")
        title.setObjectName("CardTitle")
        layout.addWidget(title, alignment=Qt.AlignCenter)

        val_cur = QLabel("--")
        val_cur.setObjectName("DashMetric")
        layout.addWidget(val_cur, alignment=Qt.AlignCenter)

        val_ytd = QLabel("YTD: --")
        val_ytd.setObjectName("FilterLabel")
        layout.addWidget(val_ytd, alignment=Qt.AlignCenter)

        return {'frame': frame, 'cur': val_cur, 'ytd': val_ytd}

    def _build_backlog_card(self) -> Dict[str, Any]:
        frame = QFrame()
        frame.setObjectName("DashCard")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("Active Backlog")
        title.setObjectName("CardTitle")
        layout.addWidget(title, alignment=Qt.AlignCenter)

        val = QLabel("--")
        val.setObjectName("DashMetric")
        layout.addWidget(val, alignment=Qt.AlignCenter)

        sub = QLabel("Current lines in queue")
        sub.setObjectName("FilterLabel")
        layout.addWidget(sub, alignment=Qt.AlignCenter)

        return {'frame': frame, 'val': val}

    def _build_vertical_health_card(self, title_text: str) -> Dict[str, Any]:
        """Builds a card housing Production on top of Submittals vertically."""
        frame = QFrame()
        frame.setObjectName("DashCard")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel(title_text)
        title.setObjectName("CardTitle")
        layout.addWidget(title, alignment=Qt.AlignCenter)

        def build_sub_section(header_text: str):
            lbl = QLabel(header_text)
            lbl.setObjectName("SubHeader")
            lbl.setAlignment(Qt.AlignCenter)

            grid = QGridLayout()
            grid.addWidget(QLabel("Current"), 0, 1, alignment=Qt.AlignCenter)
            grid.addWidget(QLabel("YTD"), 0, 2, alignment=Qt.AlignCenter)

            v_c, v_y = QLabel("--"), QLabel("--")
            q_c, q_y = QLabel("--"), QLabel("--")
            for l in [v_c, v_y, q_c, q_y]: l.setObjectName("KpiBlockValue")

            lbl_v = QLabel("Var:")
            lbl_v.setObjectName("FilterLabel")
            grid.addWidget(lbl_v, 1, 0)
            grid.addWidget(v_c, 1, 1, alignment=Qt.AlignCenter)
            grid.addWidget(v_y, 1, 2, alignment=Qt.AlignCenter)

            lbl_q = QLabel("Queue:")
            lbl_q.setObjectName("FilterLabel")
            grid.addWidget(lbl_q, 2, 0)
            grid.addWidget(q_c, 2, 1, alignment=Qt.AlignCenter)
            grid.addWidget(q_y, 2, 2, alignment=Qt.AlignCenter)

            return lbl, grid, v_c, v_y, q_c, q_y

        p_lbl, p_grid, p_v_c, p_v_y, p_q_c, p_q_y = build_sub_section("Production")
        s_lbl, s_grid, s_v_c, s_v_y, s_q_c, s_q_y = build_sub_section("Submittals")

        layout.addWidget(p_lbl)
        layout.addLayout(p_grid)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("background-color: #333333; margin: 5px 0px;")
        layout.addWidget(sep)

        layout.addWidget(s_lbl)
        layout.addLayout(s_grid)

        return {
            'frame': frame,
            'p_var_cur': p_v_c, 'p_var_ytd': p_v_y, 'p_q_cur': p_q_c, 'p_q_ytd': p_q_y,
            's_var_cur': s_v_c, 's_var_ytd': s_v_y, 's_q_cur': s_q_c, 's_q_ytd': s_q_y
        }

    def _build_interactive_chart_panel(self) -> Dict[str, Any]:
        """Builds a horizontal panel with two pie charts."""
        card = QFrame()
        card.setObjectName("DashCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)

        # Left Side: Assignee Chart
        left_layout = QVBoxLayout()
        left_title = QLabel("Hover an Assignee:")
        left_title.setObjectName("CardTitle")
        left_layout.addWidget(left_title, alignment=Qt.AlignCenter)

        self.chart_assignee = QChart()
        self.chart_assignee.setTheme(QChart.ChartThemeDark)
        self.chart_assignee.setBackgroundBrush(Qt.NoBrush)
        self.chart_assignee.layout().setContentsMargins(0, 0, 0, 0)
        self.chart_assignee.legend().hide()

        view_assignee = QChartView(self.chart_assignee)
        view_assignee.setRenderHint(QPainter.Antialiasing)
        left_layout.addWidget(view_assignee, 1)

        # Right Side: Requirement Chart
        right_layout = QVBoxLayout()
        self.lbl_req_title = QLabel("Team Requirement Breakdown")
        self.lbl_req_title.setObjectName("CardTitle")
        right_layout.addWidget(self.lbl_req_title, alignment=Qt.AlignCenter)

        self.chart_req = QChart()
        self.chart_req.setTheme(QChart.ChartThemeDark)
        self.chart_req.setBackgroundBrush(Qt.NoBrush)
        self.chart_req.layout().setContentsMargins(0, 0, 0, 0)
        self.chart_req.legend().hide()

        view_req = QChartView(self.chart_req)
        view_req.setRenderHint(QPainter.Antialiasing)
        right_layout.addWidget(view_req, 1)

        layout.addLayout(left_layout, 1)
        layout.addLayout(right_layout, 1)

        return {'card': card}

    def _build_timeline_card(self, title: str) -> Dict[str, Any]:
        card = QFrame()
        card.setObjectName("DashCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)

        top_bar = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setObjectName("CardTitle")
        top_bar.addWidget(title_lbl)
        top_bar.addStretch()

        date_filter = QComboBox()
        date_filter.addItems(["Last 30 Days", "Last 90 Days", "Year to Date", "All Time"])
        date_filter.setCurrentText("Last 90 Days")
        date_filter.setMaximumHeight(24)

        top_bar.addWidget(date_filter)
        layout.addLayout(top_bar)

        chart = QChart()
        chart.setTheme(QChart.ChartThemeDark)
        chart.setBackgroundBrush(Qt.NoBrush)
        chart.layout().setContentsMargins(0, 0, 0, 0)

        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.Antialiasing)
        layout.addWidget(chart_view, 1)

        return {'card': card, 'date_filter': date_filter, 'chart': chart, 'chart_view': chart_view}

    # ---------------------------------------------------------
    # Utilities & Rendering
    # ---------------------------------------------------------

    def get_dynamic_color(self, name: str) -> str:
        name = str(name).strip().upper()
        if not name or name == "UNASSIGNED": return "#888888"
        if hasattr(self, 'color_map') and name in self.color_map: return self.color_map[name]
        if name not in self.dynamic_color_map:
            color_idx = len(self.dynamic_color_map) % len(self.palette)
            self.dynamic_color_map[name] = self.palette[color_idx]
        return self.dynamic_color_map[name]

    def get_req_color(self, req_name: str) -> str:
        req_upper = str(req_name).upper()
        if 'PROD' in req_upper: return "#4CAF50"
        if 'SUPPORT' in req_upper or 'DOC' in req_upper: return "#F44336"
        if 'QUOT' in req_upper: return "#2196F3"
        if 'APP' in req_upper or 'SUB' in req_upper: return "#FF9800"
        return self.get_dynamic_color(req_upper)

    def get_relative_week_label(self, year_week_str: str) -> str:
        try:
            target_year, target_week = map(int, year_week_str.split('-'))
            today = pd.Timestamp.today()
            curr_year, curr_week, _ = today.isocalendar()
            diff = (target_year - curr_year) * 52 + (target_week - curr_week)
            if diff == 0: return "Current Wk"
            elif diff > 0: return f"+{diff} Wk"
            else: return f"{diff} Wk"
        except Exception:
            return year_week_str

    def _get_team_for_row(self, row: pd.Series) -> str:
        name = str(row.get('ASSIGNED TO', '')).strip().upper()
        if name and name not in ['UNASSIGNED', 'NAN', '']: return self.team_map.get(name, "UNASSIGNED")
        line_type = str(row.get('TYPE', '')).strip().upper()
        if line_type in ['STD', 'STD-M', 'PART']: return "STANDARD TEAM"
        elif line_type in ['MOD', 'CUS', 'PART-MC']: return "CUSTOM TEAM"
        return "UNASSIGNED"

    def _format_var(self, val: float) -> str:
        if pd.isna(val): return "--"
        return f"{val:+.1f}d"

    def _format_day(self, val: float) -> str:
        if pd.isna(val): return "--"
        return f"{val:.1f}d"

    def _set_var_color(self, label: QLabel, val: float) -> None:
        if pd.isna(val): label.setStyleSheet("color: #FFFFFF;")
        else: label.setStyleSheet("color: #4CAF50;" if val >= 0 else "color: #FF5252;")

    def update_dashboard(self, df: pd.DataFrame) -> None:
        if df.empty: return
        self.master_df = df.copy()
        self.render_all()

    def render_all(self) -> None:
        if self.master_df.empty: return
        df = self.master_df.copy()
        current_team = self.filter_team.currentText()

        if current_team != "All Teams":
            df['CALC_TEAM'] = df.apply(self._get_team_for_row, axis=1)
            df = df[df['CALC_TEAM'] == current_team.strip().upper()].copy()

        active_df, comp_df = DashboardService.split_base_data(df)

        self.render_top_row(active_df, comp_df)
        self.render_interactive_pies(active_df)
        self.render_timeline_row(active_df, comp_df)

    def render_top_row(self, active_df: pd.DataFrame, comp_df: pd.DataFrame) -> None:
        kpis = DashboardService.calculate_advanced_kpis(active_df, comp_df)

        # Delivery & Backlog
        global_data = kpis['global']
        pct_cur = global_data['delivery_cur']
        self.card_delivery['cur'].setText(f"{pct_cur:.1f}%" if not pd.isna(pct_cur) else "--")
        self.card_delivery['cur'].setStyleSheet("color: #4CAF50;" if pct_cur >= 95.0 else "color: #FF5252;")
        pct_ytd = global_data['delivery_ytd']
        self.card_delivery['ytd'].setText(f"YTD: {pct_ytd:.1f}%" if not pd.isna(pct_ytd) else "YTD: --")
        self.card_backlog['val'].setText(str(global_data['backlog']))

        # Populate Vertical MOD and CUS Cards
        def populate_card(ui: Dict, data_dict: Dict):
            p_cur, p_ytd = data_dict['prod']['cur']['variance'], data_dict['prod']['ytd']['variance']
            ui['p_var_cur'].setText(self._format_var(p_cur)); self._set_var_color(ui['p_var_cur'], p_cur)
            ui['p_var_ytd'].setText(self._format_var(p_ytd)); self._set_var_color(ui['p_var_ytd'], p_ytd)
            ui['p_q_cur'].setText(self._format_day(data_dict['prod']['cur']['queue']))
            ui['p_q_ytd'].setText(self._format_day(data_dict['prod']['ytd']['queue']))

            s_cur, s_ytd = data_dict['sub']['cur']['variance'], data_dict['sub']['ytd']['variance']
            ui['s_var_cur'].setText(self._format_var(s_cur)); self._set_var_color(ui['s_var_cur'], s_cur)
            ui['s_var_ytd'].setText(self._format_var(s_ytd)); self._set_var_color(ui['s_var_ytd'], s_ytd)
            ui['s_q_cur'].setText(self._format_day(data_dict['sub']['cur']['queue']))
            ui['s_q_ytd'].setText(self._format_day(data_dict['sub']['ytd']['queue']))

        populate_card(self.card_mod, kpis['mod'])
        populate_card(self.card_cus, kpis['cus'])

    # --- Interactive Master-Detail Pie Rendering ---

    def render_interactive_pies(self, active_df: pd.DataFrame) -> None:
        """Sets up the Assignee pie chart and pre-calculates the global requirement totals."""
        self.chart_assignee.removeAllSeries()

        self._current_eng_dist = DashboardService.get_detailed_donut_data(active_df)
        if not self._current_eng_dist:
            self.chart_req.removeAllSeries()
            return

        # 1. Calculate Global Requirements for the default view
        global_reqs = {}
        for eng_data in self._current_eng_dist.values():
            for req, count in eng_data['reqs'].items():
                global_reqs[req] = global_reqs.get(req, 0) + count
        self._global_req_dist = dict(sorted(global_reqs.items(), key=lambda item: item[1], reverse=True))

        # 2. Build the Master Pie (Assignees)
        pie = QPieSeries()
        pie.setHoleSize(0.3)
        font = QFont("Segoe UI", 8, QFont.Bold)

        for eng_name, data in self._current_eng_dist.items():
            slc = pie.append(f"{eng_name} ({data['total']})", data['total'])
            slc.setLabelVisible(True)
            slc.setLabelPosition(QPieSlice.LabelOutside)
            slc.setLabelColor(QColor("#FFFFFF"))
            slc.setLabelFont(font)
            slc.setBrush(QColor(self.get_dynamic_color(eng_name)))
            slc.setPen(QPen(QColor("#1E1E20"), 2))

            # Connect the interactive hover signal!
            slc.hovered.connect(self._on_slice_hovered)

        self.chart_assignee.addSeries(pie)

        # 3. Render the initial default global requirement view
        self._render_detail_pie("Team Requirement Breakdown", self._global_req_dist)

    def _on_slice_hovered(self, state: bool) -> None:
        """Fired when user hovers over an engineer. Updates the detail pie chart."""
        slice_obj = self.sender()
        if not isinstance(slice_obj, QPieSlice): return

        if state:
            # Hovered In: Extract the name from "MATT (15)" and show their specific requirements
            eng_name = slice_obj.label().split(' (')[0].strip()
            data = self._current_eng_dist.get(eng_name)

            if data and data['reqs']:
                # Pop out the slice slightly to show it is selected
                slice_obj.setExploded(True)
                slice_obj.setExplodeDistanceFactor(0.05)
                self._render_detail_pie(f"{eng_name}'s Backlog", data['reqs'])
        else:
            # Hovered Out: Reset the explosion and revert back to global team view
            slice_obj.setExploded(False)
            self._render_detail_pie("Team Requirement Breakdown", self._global_req_dist)

    def _render_detail_pie(self, title: str, req_data: Dict[str, int]) -> None:
        """Renders the right-side detail pie chart dynamically."""
        self.lbl_req_title.setText(title)
        self.chart_req.removeAllSeries()

        if not req_data: return

        pie = QPieSeries()
        pie.setHoleSize(0.3)
        font = QFont("Segoe UI", 8)

        for req_name, count in req_data.items():
            slc = pie.append(f"{req_name} ({count})", count)
            slc.setLabelVisible(True)
            slc.setLabelColor(QColor("#CCCCCC"))
            slc.setLabelFont(font)
            slc.setBrush(QColor(self.get_req_color(req_name)))
            slc.setPen(QPen(QColor("#1E1E20"), 2))

        self.chart_req.addSeries(pie)

    # --- Timeline ---
    def render_timeline_row(self, active_df: pd.DataFrame, comp_df: pd.DataFrame) -> None:
        chart = self.timeline_ui['chart']
        chart.removeAllSeries()
        for axis in chart.axes(): chart.removeAxis(axis)
        self._chart_refs = []

        range_sel = self.timeline_ui['date_filter'].currentText()
        today = pd.Timestamp.today().normalize()
        if range_sel == "Last 30 Days": start_date = today - pd.Timedelta(days=30)
        elif range_sel == "Last 90 Days": start_date = today - pd.Timedelta(days=90)
        elif range_sel == "Year to Date": start_date = pd.Timestamp(year=today.year, month=1, day=1)
        else: start_date = pd.Timestamp.min

        weeks, reqs, df = DashboardService.prepare_timeline_data(comp_df, active_df, start_date)
        if df.empty or not weeks: return

        bar_series = QBarSeries()
        bar_series.setBarWidth(0.9)
        min_y, max_y = 0, 0

        for r in reqs:
            actual_set = QBarSet(str(r))
            base_color = QColor(self.get_req_color(r))
            actual_set.setBrush(base_color)

            forecast_set = QBarSet(f"{r} (Forecast)")
            forecast_color = QColor(base_color)
            forecast_color.setAlpha(120)
            forecast_set.setBrush(forecast_color)

            for wk in weeks:
                mask_base = (df['REQUIREMENT'].replace('', 'Uncategorized') == r) & (df['YearWeek'] == wk)
                act_sum = df[mask_base & (~df['IS_FORECAST'])]['VAR_DAYS'].sum()
                for_sum = df[mask_base & (df['IS_FORECAST'])]['VAR_DAYS'].sum()
                actual_set.append(act_sum)
                forecast_set.append(for_sum)
                min_y, max_y = min(min_y, act_sum, for_sum), max(max_y, act_sum, for_sum)

            bar_series.append(actual_set)
            bar_series.append(forecast_set)

        chart.addSeries(bar_series)
        axisX = QBarCategoryAxis()
        categories = [self.get_relative_week_label(wk) for wk in weeks]
        axisX.append(categories)
        font = QFont("Segoe UI", 8, QFont.Bold)
        axisX.setLabelsFont(font)
        axisX.setLabelsBrush(QColor("#AAAAAA"))
        chart.addAxis(axisX, Qt.AlignBottom)
        bar_series.attachAxis(axisX)

        axisY = QValueAxis()
        padding = max(abs(max_y), abs(min_y)) * 0.2 + 2
        y_min, y_max = min_y - padding, max_y + padding
        axisY.setRange(y_min, y_max)
        axisY.setLabelsBrush(QColor("#AAAAAA"))
        chart.addAxis(axisY, Qt.AlignLeft)
        bar_series.attachAxis(axisY)

        axisX_line = QValueAxis()
        axisX_line.setRange(-0.5, len(weeks) - 0.5)
        axisX_line.setVisible(False)
        chart.addAxis(axisX_line, Qt.AlignBottom)

        curr_idx = next((i for i, c in enumerate(categories) if "+" in c or "Current" in c), None)
        if curr_idx is not None:
            future_upper, future_lower = QLineSeries(), QLineSeries()
            start_x, max_x = curr_idx - 0.5, len(weeks) - 0.5
            future_upper.append(start_x, y_max); future_upper.append(max_x, y_max)
            future_lower.append(start_x, y_min); future_lower.append(max_x, y_min)

            future_area = QAreaSeries(future_upper, future_lower)
            future_area.setName("Future Highlight")
            self._chart_refs.extend([future_upper, future_lower, future_area])
            highlight = QColor("#FFFFFF")
            highlight.setAlpha(12)
            future_area.setBrush(highlight)
            future_area.setPen(Qt.NoPen)
            chart.addSeries(future_area)
            future_area.attachAxis(axisX_line)
            future_area.attachAxis(axisY)

        zero_line = QLineSeries()
        zero_line.setName("Target")
        zero_line.append(-0.5, 0); zero_line.append(len(weeks) - 0.5, 0)
        zero_line.setPen(QPen(QColor("#FFFFFF"), 3, Qt.SolidLine))
        chart.addSeries(zero_line)
        zero_line.attachAxis(axisX_line)
        zero_line.attachAxis(axisY)

        chart.legend().show()
        chart.legend().setAlignment(Qt.AlignBottom)
        for marker in chart.legend().markers():
            label = marker.label()
            if "(Forecast)" in label or label == "Target" or label == "Future Highlight":
                marker.setVisible(False)