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
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QCursor

from logic.dashboard_service import DashboardService


class DashboardWidget(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.master_df: pd.DataFrame = pd.DataFrame()
        self.team_map: Dict[str, str] = {}
        self.color_map: Dict[str, str] = {}

        self._current_eng_dist: Dict[str, Any] = {}
        self._global_req_dist: Dict[str, int] = {}
        self._dynamic_card_widgets: List[QWidget] = []

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
        self.cards_grid = QGridLayout(left_pane)
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        self.cards_grid.setSpacing(15)

        self.card_delivery = self._build_delivery_card()
        self.card_backlog = self._build_backlog_card()

        # Row 0: Global Health
        self.cards_grid.addWidget(self.card_delivery['frame'], 0, 0)
        self.cards_grid.addWidget(self.card_backlog['frame'], 0, 1)

        # Right Column: Interactive Master-Detail Pies
        self.dist_ui = self._build_interactive_chart_panel()

        top_half_layout.addWidget(left_pane, 4)
        top_half_layout.addWidget(self.dist_ui['card'], 6)

        main_layout.addLayout(top_half_layout, 1)

        # --- Bottom Half: Timeline ---
        self.timeline_ui = self._build_timeline_card("Completed Jobs & Active Forecast")
        main_layout.addWidget(self.timeline_ui['card'], 1)

        self.timeline_ui['date_filter'].currentTextChanged.connect(self.render_all)

        # --- Set up the hidden floating tooltip ---
        self.chart_tooltip = QFrame(self)
        self.chart_tooltip.setObjectName("ChartTooltip")
        # THIS IS THE MAGIC LINE that stops the flickering/disappearing!
        self.chart_tooltip.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.chart_tooltip.hide()

        self.tooltip_layout = QVBoxLayout(self.chart_tooltip)
        self.tooltip_layout.setContentsMargins(10, 10, 10, 10)
        self.tooltip_layout.setSpacing(5)

        self.tooltip_header = QLabel("Week --")
        self.tooltip_header.setObjectName("TooltipHeader")
        self.tooltip_layout.addWidget(self.tooltip_header)

        self.tooltip_content = QLabel("")
        self.tooltip_content.setObjectName("TooltipText")
        self.tooltip_layout.addWidget(self.tooltip_content)

    # ---------------------------------------------------------
    # UI Component Builders
    # ---------------------------------------------------------

    def _build_delivery_card(self) -> Dict[str, Any]:
        frame = QFrame()
        frame.setObjectName("DashCard")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("Global Delivery %")
        title.setObjectName("CardTitle")
        layout.addWidget(title, alignment=Qt.AlignTop | Qt.AlignHCenter)

        layout.addSpacing(10)

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
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("Active Backlog")
        title.setObjectName("CardTitle")
        layout.addWidget(title, alignment=Qt.AlignTop | Qt.AlignHCenter)

        layout.addSpacing(10)

        val = QLabel("--")
        val.setObjectName("DashMetric")
        layout.addWidget(val, alignment=Qt.AlignCenter)

        sub = QLabel("Prod: -- | Sub: --")
        sub.setObjectName("FilterLabel")
        layout.addWidget(sub, alignment=Qt.AlignCenter)

        return {'frame': frame, 'val': val, 'sub': sub}

    def _build_vertical_health_card(self, title_text: str) -> Dict[str, Any]:
        frame = QFrame()
        frame.setObjectName("DashCard")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel(title_text)
        title.setObjectName("CardTitle")
        layout.addWidget(title, alignment=Qt.AlignTop | Qt.AlignHCenter)

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

        layout.addSpacing(10)
        layout.addWidget(p_lbl)
        layout.addLayout(p_grid)

        layout.addSpacing(25)

        layout.addWidget(s_lbl)
        layout.addLayout(s_grid)

        return {
            'frame': frame,
            'p_var_cur': p_v_c, 'p_var_ytd': p_v_y, 'p_q_cur': p_q_c, 'p_q_ytd': p_q_y,
            's_var_cur': s_v_c, 's_var_ytd': s_v_y, 's_q_cur': s_q_c, 's_q_ytd': s_q_y
        }

    def _build_flow_card(self, title_text: str) -> Dict[str, Any]:
        frame = QFrame()
        frame.setObjectName("DashCard")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel(title_text)
        title.setObjectName("CardTitle")
        layout.addWidget(title, alignment=Qt.AlignTop | Qt.AlignHCenter)

        layout.addSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(10)

        lbl_in = QLabel("Incoming:"); lbl_in.setObjectName("FilterLabel")
        val_in = QLabel("--"); val_in.setObjectName("KpiBlockValue")
        grid.addWidget(lbl_in, 0, 0); grid.addWidget(val_in, 0, 1, alignment=Qt.AlignCenter)

        lbl_out = QLabel("Outgoing:"); lbl_out.setObjectName("FilterLabel")
        val_out = QLabel("--"); val_out.setObjectName("KpiBlockValue")
        grid.addWidget(lbl_out, 1, 0); grid.addWidget(val_out, 1, 1, alignment=Qt.AlignCenter)

        lbl_net = QLabel("Net Change:"); lbl_net.setObjectName("FilterLabel")
        val_net = QLabel("--"); val_net.setObjectName("KpiBlockValue")
        grid.addWidget(lbl_net, 2, 0); grid.addWidget(val_net, 2, 1, alignment=Qt.AlignCenter)

        layout.addLayout(grid)

        layout.addSpacing(25)

        b_layout = QHBoxLayout()
        b_lbl = QLabel("Total Backlog:"); b_lbl.setObjectName("FilterLabel")
        val_b = QLabel("--"); val_b.setObjectName("KpiBlockValue")
        b_layout.addWidget(b_lbl); b_layout.addStretch(); b_layout.addWidget(val_b)
        layout.addLayout(b_layout)

        return {
            'frame': frame,
            'in': val_in, 'out': val_out, 'net': val_net, 'backlog': val_b
        }

    def _build_interactive_chart_panel(self) -> Dict[str, Any]:
        card = QFrame()
        card.setObjectName("DashCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)

        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)

        # --- FIXED: Changed Title to "Lines by Assignee" ---
        left_title = QLabel("Lines by Assignee")
        left_title.setObjectName("CardTitle")
        left_layout.addWidget(left_title, alignment=Qt.AlignTop | Qt.AlignHCenter)

        self.chart_assignee = QChart()
        self.chart_assignee.setTheme(QChart.ChartThemeDark)
        self.chart_assignee.setBackgroundBrush(Qt.NoBrush)
        self.chart_assignee.layout().setContentsMargins(0, 0, 0, 0)
        self.chart_assignee.legend().hide()

        view_assignee = QChartView(self.chart_assignee)
        view_assignee.setRenderHint(QPainter.Antialiasing)
        left_layout.addWidget(view_assignee, 1)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_req_title = QLabel("Team Requirement Breakdown")
        self.lbl_req_title.setObjectName("CardTitle")
        right_layout.addWidget(self.lbl_req_title, alignment=Qt.AlignTop | Qt.AlignHCenter)

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
        layout.setContentsMargins(15, 15, 15, 15)

        top_bar = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setObjectName("CardTitle")
        top_bar.addWidget(title_lbl, alignment=Qt.AlignVCenter | Qt.AlignLeft)
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

    def _abbr_req(self, req: str) -> str:
        r = str(req).upper().strip()
        if 'PROD' in r: return 'PROD'
        if 'APP' in r: return 'APP'
        if 'SUB' in r: return 'SUB'
        if 'QUOT' in r: return 'QUOT'
        if 'SUPPORT' in r: return 'SUPP'
        if 'DOC' in r: return 'DOC'
        return r[:4]

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

        df['CALC_TEAM'] = df.apply(self._get_team_for_row, axis=1)

        if current_team != "All Teams":
            filtered_df = df[df['CALC_TEAM'] == current_team.strip().upper()].copy()
        else:
            filtered_df = df.copy()

        active_df, comp_df = DashboardService.split_base_data(filtered_df)

        self.render_top_row(active_df, comp_df, df, current_team)
        self.render_interactive_pies(active_df)
        self.render_timeline_row(active_df, comp_df)

    def render_top_row(self, active_df: pd.DataFrame, comp_df: pd.DataFrame, full_df: pd.DataFrame, current_team: str) -> None:
        for widget in self._dynamic_card_widgets:
            self.cards_grid.removeWidget(widget)
            widget.deleteLater()
        self._dynamic_card_widgets.clear()

        kpis = DashboardService.calculate_advanced_kpis(active_df, comp_df, full_df, current_team)

        global_data = kpis['global']
        pct_cur = global_data['delivery_cur']
        self.card_delivery['cur'].setText(f"{pct_cur:.1f}%" if not pd.isna(pct_cur) else "--")
        self.card_delivery['cur'].setStyleSheet("color: #4CAF50;" if pct_cur >= 95.0 else "color: #FF5252;")
        self.card_delivery['ytd'].setText(f"YTD: {global_data['delivery_ytd']:.1f}%" if not pd.isna(global_data['delivery_ytd']) else "YTD: --")

        self.card_backlog['val'].setText(str(global_data['backlog_total']))
        self.card_backlog['sub'].setText(f"Prod: {global_data['backlog_prod']} | Sub: {global_data['backlog_sub']}")

        row_idx = 1
        col_idx = 0

        for card_data in kpis['cards']:
            if kpis['view_type'] == 'health':
                ui_card = self._build_vertical_health_card(card_data['title'])

                p_cur, p_ytd = card_data['prod']['cur']['variance'], card_data['prod']['ytd']['variance']
                ui_card['p_var_cur'].setText(self._format_var(p_cur)); self._set_var_color(ui_card['p_var_cur'], p_cur)
                ui_card['p_var_ytd'].setText(self._format_var(p_ytd)); self._set_var_color(ui_card['p_var_ytd'], p_ytd)
                ui_card['p_q_cur'].setText(self._format_day(card_data['prod']['cur']['queue']))
                ui_card['p_q_ytd'].setText(self._format_day(card_data['prod']['ytd']['queue']))

                s_cur, s_ytd = card_data['sub']['cur']['variance'], card_data['sub']['ytd']['variance']
                ui_card['s_var_cur'].setText(self._format_var(s_cur)); self._set_var_color(ui_card['s_var_cur'], s_cur)
                ui_card['s_var_ytd'].setText(self._format_var(s_ytd)); self._set_var_color(ui_card['s_var_ytd'], s_ytd)
                ui_card['s_q_cur'].setText(self._format_day(card_data['sub']['cur']['queue']))
                ui_card['s_q_ytd'].setText(self._format_day(card_data['sub']['ytd']['queue']))

                frame = ui_card['frame']

            else:
                ui_card = self._build_flow_card(card_data['title'])
                ui_card['in'].setText(str(card_data['incoming']))
                ui_card['out'].setText(str(card_data['outgoing']))

                net = card_data['net']
                ui_card['net'].setText(f"{net:+d}")
                if net > 0: ui_card['net'].setStyleSheet("color: #FF5252;")
                elif net < 0: ui_card['net'].setStyleSheet("color: #4CAF50;")
                else: ui_card['net'].setStyleSheet("color: #FFFFFF;")

                ui_card['backlog'].setText(str(card_data['backlog']))

                frame = ui_card['frame']

            self.cards_grid.addWidget(frame, row_idx, col_idx)
            self._dynamic_card_widgets.append(frame)

            col_idx += 1
            if col_idx > 1:
                col_idx = 0
                row_idx += 1

    # --- Interactive Master-Detail Pie Rendering ---

    def render_interactive_pies(self, active_df: pd.DataFrame) -> None:
        self.chart_assignee.removeAllSeries()

        self._current_eng_dist = DashboardService.get_detailed_donut_data(active_df)
        if not self._current_eng_dist:
            self.chart_req.removeAllSeries()
            return

        global_reqs = {}
        for eng_data in self._current_eng_dist.values():
            for req, count in eng_data['reqs'].items():
                global_reqs[req] = global_reqs.get(req, 0) + count
        self._global_req_dist = dict(sorted(global_reqs.items(), key=lambda item: item[1], reverse=True))

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
            slc.hovered.connect(self._on_slice_hovered)

        self.chart_assignee.addSeries(pie)
        self._render_detail_pie("Team Requirement Breakdown", self._global_req_dist)

    def _on_slice_hovered(self, state: bool) -> None:
        slice_obj = self.sender()
        if not isinstance(slice_obj, QPieSlice): return

        if state:
            eng_name = slice_obj.label().split(' (')[0].strip()
            data = self._current_eng_dist.get(eng_name)

            if data and data['reqs']:
                slice_obj.setExploded(True)
                slice_obj.setExplodeDistanceFactor(0.05)
                self._render_detail_pie(f"{eng_name}'s Backlog", data['reqs'])
        else:
            slice_obj.setExploded(False)
            self._render_detail_pie("Team Requirement Breakdown", self._global_req_dist)

    def _render_detail_pie(self, title: str, req_data: Dict[str, int]) -> None:
        self.lbl_req_title.setText(title)
        self.chart_req.removeAllSeries()

        if not req_data: return

        pie = QPieSeries()
        pie.setHoleSize(0.3)
        font = QFont("Segoe UI", 8)

        for req_name, count in req_data.items():
            short_name = self._abbr_req(req_name)
            slc = pie.append(f"{short_name} ({count})", count)
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
        if range_sel == "Last 30 Days":
            start_date = today - pd.Timedelta(days=30)
        elif range_sel == "Last 90 Days":
            start_date = today - pd.Timedelta(days=90)
        elif range_sel == "Year to Date":
            start_date = pd.Timestamp(year=today.year, month=1, day=1)
        else:
            start_date = pd.Timestamp.min

        weeks, reqs, df = DashboardService.prepare_timeline_data(comp_df, active_df, start_date)
        if df.empty or not weeks: return

        # Store the dataframe so the hover function can read from it!
        self._timeline_df = df
        self._timeline_weeks = weeks

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

                act_data = df[mask_base & (~df['IS_FORECAST'])]['VAR_DAYS']
                act_val = float(act_data.mean()) if not act_data.empty else 0.0
                if pd.isna(act_val): act_val = 0.0

                for_data = df[mask_base & (df['IS_FORECAST'])]['VAR_DAYS']
                for_val = float(for_data.mean()) if not for_data.empty else 0.0
                if pd.isna(for_val): for_val = 0.0

                actual_set.append(act_val)
                forecast_set.append(for_val)
                min_y, max_y = min(min_y, act_val, for_val), max(max_y, act_val, for_val)

            # ---> NEW: Connect the hover signals! <---
            actual_set.hovered.connect(
                lambda status, index, req=r, is_fc=False: self._on_bar_hovered(status, index, req, is_fc))
            forecast_set.hovered.connect(
                lambda status, index, req=r, is_fc=True: self._on_bar_hovered(status, index, req, is_fc))

            bar_series.append(actual_set)
            bar_series.append(forecast_set)

        chart.addSeries(bar_series)

        # --- EXISTING BOTTOM AXIS (Relative Weeks) ---
        axisX = QBarCategoryAxis()
        categories = [self.get_relative_week_label(wk) for wk in weeks]
        axisX.append(categories)
        font = QFont("Segoe UI", 8, QFont.Bold)
        axisX.setLabelsFont(font)
        axisX.setLabelsBrush(QColor("#AAAAAA"))
        chart.addAxis(axisX, Qt.AlignBottom)
        bar_series.attachAxis(axisX)

        # ---> NEW: TOP AXIS (Actual Dates) <---
        axisX_top = QBarCategoryAxis()
        top_categories = []
        for wk in weeks:
            try:
                # %G = ISO year, %V = ISO week, %u = ISO weekday (1=Monday)
                # This grabs the actual Monday date for that specific week
                dt = pd.to_datetime(wk + '-1', format='%G-%V-%u')
                top_categories.append(dt.strftime('%b %d'))
            except Exception:
                top_categories.append(wk)

        axisX_top.append(top_categories)
        font_top = QFont("Segoe UI", 7)
        axisX_top.setLabelsFont(font_top)
        axisX_top.setLabelsBrush(QColor("#777777"))  # Make it slightly dimmer than the bottom axis
        chart.addAxis(axisX_top, Qt.AlignTop)
        bar_series.attachAxis(axisX_top)

        axisY = QValueAxis()

        # --- FIXED: Apply integer format for Y-axis precision ---
        axisY.setLabelFormat("%d")

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

    def _on_bar_hovered(self, status: bool, index: int, req_name: str, is_forecast: bool) -> None:
        """Handles the display, data population, and coordinate mapping of the custom timeline tooltip."""
        if not status:
            self.chart_tooltip.hide()
            return

        try:
            target_week = self._timeline_weeks[index]
            week_label = self.get_relative_week_label(target_week)

            mask = (self._timeline_df['REQUIREMENT'].replace('', 'Uncategorized') == req_name) & \
                   (self._timeline_df['YearWeek'] == target_week) & \
                   (self._timeline_df['IS_FORECAST'] == is_forecast)

            subset = self._timeline_df[mask]

            if subset.empty:
                return

            total_lines = subset['LINE_COUNT'].sum() if 'LINE_COUNT' in subset.columns else len(subset)
            avg_var = subset['VAR_DAYS'].mean()

            title_type = "Forecast" if is_forecast else "Completed"
            self.tooltip_header.setText(f"{req_name} ({title_type}) | {week_label}")

            details = [
                f"<b>Total Lines:</b> {int(total_lines)}",
                f"<b>Avg Variance:</b> {avg_var:+.1f} days",
                "<br><b>Projects:</b>"
            ]

            # --- NEW: Group by Project Name and get average variance per project ---
            # Fallback to PROJECT_ID if 'PROJECT NAME' column doesn't exist
            proj_col = 'PROJECT NAME' if 'PROJECT NAME' in subset.columns else 'PROJECT_ID'

            # Group by the project, average their variance, and sort so the latest (most negative) are at the top
            proj_vars = subset.groupby(proj_col)['VAR_DAYS'].mean().sort_values(ascending=True)

            # Build the list with color-coded HTML text
            projects = list(proj_vars.items())
            for p_name, p_var in projects[:5]:
                color = "#FF5252" if p_var < 0 else "#4CAF50"
                details.append(f"• {p_name}: <span style='color:{color};'>{p_var:+.1f}d</span>")

            if len(projects) > 5:
                details.append(f"<i>...and {len(projects) - 5} more</i>")

            self.tooltip_content.setText("<br>".join(details))

            global_pos = QCursor.pos()
            local_pos = self.mapFromGlobal(global_pos)

            self.chart_tooltip.move(local_pos.x() + 15, local_pos.y() + 15)
            self.chart_tooltip.adjustSize()
            self.chart_tooltip.show()
            self.chart_tooltip.raise_()

        except Exception as e:
            print(f"Tooltip Error: {e}")
            self.chart_tooltip.hide()