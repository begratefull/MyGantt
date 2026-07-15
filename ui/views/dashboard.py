"""
Contains the DashboardWidget which displays high-level KPIs,
detailed performance grids, queue distributions, and timeline forecasting.
"""

import logging
import re
import json
import os
from typing import Dict, Any, List, Set

import pandas as pd
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox, QGridLayout, QSizePolicy
)
from PySide6.QtCharts import (
    QChart, QChartView, QPieSeries, QPieSlice,
    QBarCategoryAxis, QValueAxis, QLineSeries, QAreaSeries,
    QSplineSeries, QScatterSeries, QLegendMarker
)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QCursor, QBrush

from logic.dashboard_service import DashboardService
from logic.constants import AppConstants

logger = logging.getLogger(__name__)


class DashboardWidget(QWidget):
    """
    Main widget for the Engineering Dashboard.
    Renders high-level KPIs, charts, and forecasts based on workload data.
    """
    def __init__(self) -> None:
        super().__init__()
        self.actual_df: pd.DataFrame = pd.DataFrame()
        self.forecast_df: pd.DataFrame = pd.DataFrame()

        self.team_map: Dict[str, str] = {}
        self.color_map: Dict[str, str] = {}

        self._current_eng_dist: Dict[str, Any] = {}
        self._global_req_dist: Dict[str, int] = {}
        self._dynamic_card_widgets: List[QWidget] = []

        self._timeline_df: pd.DataFrame = pd.DataFrame()
        self._timeline_weeks: List[str] = []

        # Maps requirement category to its active QtSeries for interactive toggling
        self.series_map: Dict[str, Dict[str, Any]] = {}
        self.hidden_series: Set[str] = self._load_hidden_series()

        self.dynamic_color_map: Dict[str, str] = {}
        self.chart_palette: List[str] = [
            "#2196F3", "#F44336", "#4CAF50", "#FF9800",
            "#9C27B0", "#00BCD4", "#795548", "#E91E63"
        ]
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Initializes and layouts the main UI components for the dashboard."""
        try:
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(0, 0, 0, 0)
            main_layout.setSpacing(15)

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

            # --- Top Half Split (Left:Right = 1:2) ---
            top_half_layout = QHBoxLayout()
            top_half_layout.setSpacing(15)

            left_pane = QWidget()
            self.cards_grid = QGridLayout(left_pane)
            self.cards_grid.setContentsMargins(0, 0, 0, 0)
            self.cards_grid.setSpacing(15)

            self.card_delivery = self._build_delivery_card()
            self.card_backlog = self._build_backlog_card()

            self.cards_grid.addWidget(self.card_delivery['frame'], 0, 0)
            self.cards_grid.addWidget(self.card_backlog['frame'], 0, 1)

            self.dist_ui = self._build_interactive_chart_panel()

            top_half_layout.addWidget(left_pane, 1)
            top_half_layout.addWidget(self.dist_ui['card'], 2)

            main_layout.addLayout(top_half_layout, 1)

            # --- Bottom Half Split (Left:Right = 1:2) ---
            bottom_half_layout = QHBoxLayout()
            bottom_half_layout.setSpacing(15)

            self.family_ui = self._build_family_card()

            bottom_half_layout.addWidget(self.family_ui['card'], 1)

            self.timeline_ui = self._build_timeline_card("Completed Jobs & Active Forecast")
            bottom_half_layout.addWidget(self.timeline_ui['card'], 2)

            main_layout.addLayout(bottom_half_layout, 1)

            self.timeline_ui['date_filter'].currentTextChanged.connect(self.render_all)

            # --- Tooltip Setup ---
            self.chart_tooltip = QFrame(self)
            self.chart_tooltip.setObjectName("ChartTooltip")
            self.chart_tooltip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
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
        except Exception as e:
            logger.error(f"Failed to setup dashboard UI: {e}")

    # ---------------------------------------------------------
    # Configuration & Persistence
    # ---------------------------------------------------------

    def _load_hidden_series(self) -> Set[str]:
        """Loads the user's hidden dashboard categories from the configuration file."""
        try:
            config_path = AppConstants.get_config_path()
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return set(data.get('hidden_dashboard_series', []))
        except Exception as e:
            logger.warning(f"Could not load hidden series config, defaulting to empty: {e}")
        return set()

    def _save_hidden_series(self) -> None:
        """Saves the user's hidden dashboard categories to the configuration file."""
        try:
            config_path = AppConstants.get_config_path()
            data = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

            data['hidden_dashboard_series'] = list(self.hidden_series)

            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save hidden series config: {e}")

    # ---------------------------------------------------------
    # UI Component Builders
    # ---------------------------------------------------------

    @staticmethod
    def _build_delivery_card() -> Dict[str, Any]:
        """Builds the global delivery percentage card."""
        frame = QFrame()
        frame.setObjectName("DashCard")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("Global Delivery %")
        title.setObjectName("CardTitle")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        layout.addSpacing(10)

        val_cur = QLabel("--")
        val_cur.setObjectName("DashMetric")
        layout.addWidget(val_cur, alignment=Qt.AlignmentFlag.AlignCenter)

        val_ytd = QLabel("YTD: --")
        val_ytd.setObjectName("FilterLabel")
        layout.addWidget(val_ytd, alignment=Qt.AlignmentFlag.AlignCenter)

        return {'frame': frame, 'cur': val_cur, 'ytd': val_ytd}

    @staticmethod
    def _build_backlog_card() -> Dict[str, Any]:
        """Builds the active backlog line count card."""
        frame = QFrame()
        frame.setObjectName("DashCard")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("Active Backlog")
        title.setObjectName("CardTitle")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        layout.addSpacing(10)

        val = QLabel("--")
        val.setObjectName("DashMetric")
        layout.addWidget(val, alignment=Qt.AlignmentFlag.AlignCenter)

        sub = QLabel("Prod: -- | Sub: --")
        sub.setObjectName("FilterLabel")
        layout.addWidget(sub, alignment=Qt.AlignmentFlag.AlignCenter)

        return {'frame': frame, 'val': val, 'sub': sub}

    @staticmethod
    def _build_vertical_health_card(title_text: str) -> Dict[str, Any]:
        """Builds a health card showing productivity and variance metrics."""
        frame = QFrame()
        frame.setObjectName("DashCard")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel(title_text)
        title.setObjectName("CardTitle")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        def build_sub_section(header_text: str):
            lbl = QLabel(header_text)
            lbl.setObjectName("SubHeader")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

            grid = QGridLayout()
            grid.addWidget(QLabel("Current"), 0, 1, alignment=Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(QLabel("YTD"), 0, 2, alignment=Qt.AlignmentFlag.AlignCenter)

            p_c, p_y = QLabel("--"), QLabel("--")
            v_c, v_y = QLabel("--"), QLabel("--")

            for l in [p_c, p_y, v_c, v_y]: l.setObjectName("KpiBlockValue")

            lbl_p = QLabel("Days in Eng:")
            lbl_p.setObjectName("FilterLabel")
            grid.addWidget(lbl_p, 1, 0)
            grid.addWidget(p_c, 1, 1, alignment=Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(p_y, 1, 2, alignment=Qt.AlignmentFlag.AlignCenter)

            lbl_v = QLabel("Var to Due:")
            lbl_v.setObjectName("FilterLabel")
            grid.addWidget(lbl_v, 2, 0)
            grid.addWidget(v_c, 2, 1, alignment=Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(v_y, 2, 2, alignment=Qt.AlignmentFlag.AlignCenter)

            return lbl, grid, p_c, p_y, v_c, v_y

        p_lbl, p_grid, p_p_c, p_p_y, p_v_c, p_v_y = build_sub_section("Production")
        s_lbl, s_grid, s_p_c, s_p_y, s_v_c, s_v_y = build_sub_section("Submittals")

        layout.addSpacing(10)
        layout.addWidget(p_lbl)
        layout.addLayout(p_grid)

        layout.addSpacing(25)

        layout.addWidget(s_lbl)
        layout.addLayout(s_grid)

        return {
            'frame': frame,
            'p_prod_cur': p_p_c, 'p_prod_ytd': p_p_y,
            'p_var_cur': p_v_c, 'p_var_ytd': p_v_y,
            's_prod_cur': s_p_c, 's_prod_ytd': s_p_y,
            's_var_cur': s_v_c, 's_var_ytd': s_v_y,
        }

    @staticmethod
    def _build_flow_card(title_text: str) -> Dict[str, Any]:
        """Builds a flow card showing incoming vs outgoing workload."""
        frame = QFrame()
        frame.setObjectName("DashCard")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel(title_text)
        title.setObjectName("CardTitle")
        layout.addWidget(title, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        layout.addSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(10)

        lbl_in = QLabel("Incoming:"); lbl_in.setObjectName("FilterLabel")
        val_in = QLabel("--"); val_in.setObjectName("KpiBlockValue")
        grid.addWidget(lbl_in, 0, 0); grid.addWidget(val_in, 0, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        lbl_out = QLabel("Outgoing:"); lbl_out.setObjectName("FilterLabel")
        val_out = QLabel("--"); val_out.setObjectName("KpiBlockValue")
        grid.addWidget(lbl_out, 1, 0); grid.addWidget(val_out, 1, 1, alignment=Qt.AlignmentFlag.AlignCenter)

        lbl_net = QLabel("Net Change:"); lbl_net.setObjectName("FilterLabel")
        val_net = QLabel("--"); val_net.setObjectName("KpiBlockValue")
        grid.addWidget(lbl_net, 2, 0); grid.addWidget(val_net, 2, 1, alignment=Qt.AlignmentFlag.AlignCenter)

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
        """Builds the container for the interactive pie charts."""
        card = QFrame()
        card.setObjectName("DashCard")
        layout = QHBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)

        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_title = QLabel("Lines by Assignee")
        left_title.setObjectName("CardTitle")
        left_layout.addWidget(left_title, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.chart_assignee = QChart()
        self.chart_assignee.setTheme(QChart.ChartTheme.ChartThemeDark)
        self.chart_assignee.setBackgroundBrush(Qt.BrushStyle.NoBrush)
        self.chart_assignee.layout().setContentsMargins(0, 0, 0, 0)
        self.chart_assignee.legend().hide()

        view_assignee = QChartView(self.chart_assignee)
        view_assignee.setRenderHint(QPainter.RenderHint.Antialiasing)
        left_layout.addWidget(view_assignee, 1)

        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.lbl_req_title = QLabel("Team Requirement Breakdown")
        self.lbl_req_title.setObjectName("CardTitle")
        right_layout.addWidget(self.lbl_req_title, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.chart_req = QChart()
        self.chart_req.setTheme(QChart.ChartTheme.ChartThemeDark)
        self.chart_req.setBackgroundBrush(Qt.BrushStyle.NoBrush)
        self.chart_req.layout().setContentsMargins(0, 0, 0, 0)
        self.chart_req.legend().hide()

        view_req = QChartView(self.chart_req)
        view_req.setRenderHint(QPainter.RenderHint.Antialiasing)
        right_layout.addWidget(view_req, 1)

        layout.addLayout(left_layout, 1)
        layout.addLayout(right_layout, 1)

        return {'card': card}

    @staticmethod
    def _build_family_card() -> Dict[str, Any]:
        """Builds the grid for the top 10 fixture families."""
        card = QFrame()
        card.setObjectName("DashCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)

        title = QLabel("Top 10 Prod Fixture Families")
        title.setObjectName("CardTitle")
        layout.addWidget(title)

        container = QWidget()
        grid = QGridLayout(container)
        grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        grid.setContentsMargins(0, 5, 0, 0)
        grid.setSpacing(12)

        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(4, 2)

        h_fam = QLabel("FAMILY")
        h_lines = QLabel("LINES")
        h_lead = QLabel("AVG DAYS\nIN ENG")
        h_proc = QLabel("AVG DAYS\nIN PROCESS")
        h_sell = QLabel("TOTAL $")

        for h in [h_fam, h_lines, h_lead, h_proc, h_sell]:
            h.setStyleSheet("color: #888888; font-weight: bold; font-size: 10px;")

        grid.addWidget(h_fam, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        grid.addWidget(h_lines, 0, 1, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom)
        grid.addWidget(h_lead, 0, 2, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom)
        grid.addWidget(h_proc, 0, 3, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom)
        grid.addWidget(h_sell, 0, 4, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("background-color: #2E2E32;")
        grid.addWidget(sep, 1, 0, 1, 5)

        layout.addWidget(container, 1)

        return {'card': card, 'grid': grid}

    @staticmethod
    def _build_timeline_card(title: str) -> Dict[str, Any]:
        """Builds the trendline chart container."""
        card = QFrame()
        card.setObjectName("DashCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(15, 15, 15, 15)

        top_bar = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setObjectName("CardTitle")
        top_bar.addWidget(title_lbl, alignment=Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        top_bar.addStretch()

        date_filter = QComboBox()
        date_filter.addItems(["Last 4 Weeks", "Last 8 Weeks", "Year to Date", "All Time"])
        date_filter.setCurrentText("Last 8 Weeks")
        date_filter.setMaximumHeight(24)

        top_bar.addWidget(date_filter)
        layout.addLayout(top_bar)

        chart = QChart()
        chart.setTheme(QChart.ChartTheme.ChartThemeDark)
        chart.setBackgroundBrush(Qt.BrushStyle.NoBrush)
        chart.layout().setContentsMargins(0, 0, 0, 0)

        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(chart_view, 1)

        return {'card': card, 'date_filter': date_filter, 'chart': chart, 'chart_view': chart_view}

    # ---------------------------------------------------------
    # Utilities & Rendering
    # ---------------------------------------------------------

    def get_dynamic_color(self, name: str) -> str:
        """Retrieves or assigns a consistent color for an engineer."""
        name = name.strip().upper()
        if not name or name == "UNASSIGNED": return "#888888"
        if hasattr(self, 'color_map') and name in self.color_map: return self.color_map[name]
        if name not in self.dynamic_color_map:
            color_idx = len(self.dynamic_color_map) % len(self.chart_palette)
            self.dynamic_color_map[name] = self.chart_palette[color_idx]
        return self.dynamic_color_map[name]

    def get_req_color(self, req_name: str) -> str:
        """Determines the UI color for a given requirement string."""
        try:
            req_upper = req_name.upper().strip()
            # Explicit category routing to guarantee correct mapping before generic pattern
            if 'RE-WORK' in req_upper or 'REWORK' in req_upper: return "#9C27B0" # Purple
            if 'NEW PRODUCT' in req_upper: return "#8BC34A" # Light Green
            if 'QUOTE' in req_upper or 'QUOT' in req_upper: return "#2196F3" # Blue
            if 'APPROVAL' in req_upper or 'APP' in req_upper: return "#FF9800" # Orange
            if 'REVISION' in req_upper or 'REV' in req_upper: return "#FFB300" # Amber
            if 'PRE-WORK' in req_upper or 'PRE' in req_upper: return "#00BCD4" # Cyan
            if 'SUPPORT' in req_upper or 'DOC' in req_upper: return "#F44336" # Red
            if 'JDE' in req_upper: return "#795548" # Brown
            if 'PRODUCTION' in req_upper or re.search(AppConstants.PROD_REQ_PATTERN, req_upper): return "#4CAF50" # Green

            return self.get_dynamic_color(req_upper)
        except Exception as e:
            logger.error(f"Error determining requirement color for {req_name}: {e}")
            return "#888888"

    @staticmethod
    def _abbr_req(req: str) -> str:
        """Abbreviates requirement strings for pie chart labels."""
        try:
            r = req.upper().strip()
            if 'RE-WORK' in r or 'REWORK' in r: return 'RWK'
            if 'NEW PRODUCT' in r: return 'NEW'
            if 'PRODUCTION' in r or re.search(AppConstants.PROD_REQ_PATTERN, r): return 'PROD'
            if 'REVISION' in r or 'REV' in r: return 'REV'
            if 'PRE-WORK' in r or 'PRE' in r: return 'PRE'
            if 'JDE' in r: return 'JDE'
            if 'APP' in r: return 'APP'
            if 'SUB' in r: return 'SUB'
            if 'QUOT' in r: return 'QUOT'
            if 'SUPPORT' in r: return 'SUPP'
            if 'DOC' in r: return 'DOC'
            return r[:4]
        except Exception as e:
            logger.error(f"Error abbreviating requirement '{req}': {e}")
            return str(req)[:4]

    @staticmethod
    def get_relative_week_label(year_week_str: str) -> str:
        """Converts an ISO week string into a relative label (e.g. 'Current Wk', '-1 Wk')."""
        try:
            target_year, target_week = map(int, year_week_str.split('-'))
            today = pd.Timestamp.today()
            curr_year, curr_week, _ = today.isocalendar()
            diff = (target_year - curr_year) * 52 + (target_week - curr_week)
            if diff == 0: return "Current Wk"
            elif diff > 0: return f"+{diff} Wk"
            else: return f"{diff} Wk"
        except (ValueError, TypeError, AttributeError):
            return year_week_str

    def _get_team_for_row(self, row: pd.Series) -> str:
        """Resolves the team name for a specific dataframe row based on assignments or line types."""
        name = str(row.get('ASSIGNED TO', '')).strip().upper()
        if name and name not in [AppConstants.UNASSIGNED_LABEL, 'NAN', '']:
            return self.team_map.get(name, AppConstants.UNASSIGNED_LABEL)

        line_type = str(row.get('TYPE', '')).strip().upper()

        if line_type in AppConstants.STANDARD_LINE_TYPES:
            return AppConstants.STANDARD_TEAM_LABEL

        elif line_type in AppConstants.CUSTOM_LINE_TYPES:
            return AppConstants.CUSTOM_TEAM_LABEL

        return AppConstants.UNASSIGNED_LABEL

    @staticmethod
    def _format_var(val: float) -> str:
        """Formats a variance float into a signed string (e.g., '+1.0d')."""
        if pd.isna(val) or val == 0.0 and type(val) is not float: return "--"
        return f"{val:+.1f}d"

    @staticmethod
    def _format_day(val: float) -> str:
        """Formats a day float into a standardized string (e.g., '1.0d')."""
        if pd.isna(val) or val == 0.0 and type(val) is not float: return "--"
        return f"{val:.1f}d"

    @staticmethod
    def _set_var_color(label: QLabel, val: float) -> None:
        """Sets the label color based on variance (green for positive/neutral, red for negative)."""
        if pd.isna(val): label.setStyleSheet("color: #FFFFFF;")
        else: label.setStyleSheet("color: #4CAF50;" if val >= 0 else "color: #FF5252;")

    @staticmethod
    def _apply_goal_color(label: QLabel, val: float, goal: float, lower_is_better: bool = True) -> None:
        """Colors a label based on performance against a target goal."""
        if pd.isna(val):
            label.setStyleSheet("color: #FFFFFF;")
        else:
            if lower_is_better:
                label.setStyleSheet("color: #4CAF50;" if val <= goal else "color: #FF5252;")
            else:
                label.setStyleSheet("color: #4CAF50;" if val >= goal else "color: #FF5252;")

    def update_dashboard(self, actual_df: pd.DataFrame, forecast_df: pd.DataFrame) -> None:
        """Primary endpoint for controller to supply fresh data to the dashboard."""
        if actual_df.empty: return
        self.actual_df = actual_df.copy()
        self.forecast_df = forecast_df.copy()
        self.render_all()

    def render_all(self) -> None:
        """Triggers a complete redraw of all dashboard elements based on current filters."""
        try:
            if not hasattr(self, 'actual_df') or self.actual_df.empty: return

            df = self.actual_df.copy()
            f_df = self.forecast_df.copy()

            current_team = self.filter_team.currentText()

            df['CALC_TEAM'] = df.apply(self._get_team_for_row, axis=1)
            f_df['CALC_TEAM'] = f_df.apply(self._get_team_for_row, axis=1)

            if current_team != "All Teams":
                filtered_df = df[df['CALC_TEAM'] == current_team.strip().upper()].copy()
                filtered_f_df = f_df[f_df['CALC_TEAM'] == current_team.strip().upper()].copy()
            else:
                filtered_df = df.copy()
                filtered_f_df = f_df.copy()

            active_df, comp_df = DashboardService.split_base_data(filtered_df)
            f_active_df, _ = DashboardService.split_base_data(filtered_f_df)

            self.render_top_row(active_df, comp_df, df, current_team)
            self.render_interactive_pies(active_df)
            self.render_family_card(filtered_df)
            self.render_timeline_row(f_active_df, comp_df)
        except Exception as e:
            logger.error(f"Error rendering dashboard: {e}")

    def render_top_row(self, active_df: pd.DataFrame, comp_df: pd.DataFrame, full_df: pd.DataFrame, current_team: str) -> None:
        """Renders the top KPI cards."""
        try:
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

                    title_text = card_data['title'].upper()
                    if "MOD" in title_text:
                        prod_goal = 15.0
                    elif "CUS" in title_text:
                        prod_goal = 20.0
                    else:
                        prod_goal = 15.0

                    var_goal = 0.0

                    p_prod_cur, p_prod_ytd = card_data['prod']['cur']['productivity'], card_data['prod']['ytd']['productivity']
                    ui_card['p_prod_cur'].setText(self._format_day(p_prod_cur))
                    self._apply_goal_color(ui_card['p_prod_cur'], p_prod_cur, prod_goal, lower_is_better=True)

                    ui_card['p_prod_ytd'].setText(self._format_day(p_prod_ytd))
                    self._apply_goal_color(ui_card['p_prod_ytd'], p_prod_ytd, prod_goal, lower_is_better=True)

                    p_cur, p_ytd = card_data['prod']['cur']['variance'], card_data['prod']['ytd']['variance']
                    ui_card['p_var_cur'].setText(self._format_var(p_cur))
                    self._apply_goal_color(ui_card['p_var_cur'], p_cur, var_goal, lower_is_better=False)

                    ui_card['p_var_ytd'].setText(self._format_var(p_ytd))
                    self._apply_goal_color(ui_card['p_var_ytd'], p_ytd, var_goal, lower_is_better=False)

                    s_prod_cur, s_prod_ytd = card_data['sub']['cur']['productivity'], card_data['sub']['ytd']['productivity']
                    ui_card['s_prod_cur'].setText(self._format_day(s_prod_cur))
                    ui_card['s_prod_cur'].setStyleSheet("color: #FFFFFF;")

                    ui_card['s_prod_ytd'].setText(self._format_day(s_prod_ytd))
                    ui_card['s_prod_ytd'].setStyleSheet("color: #FFFFFF;")

                    s_cur, s_ytd = card_data['sub']['cur']['variance'], card_data['sub']['ytd']['variance']
                    ui_card['s_var_cur'].setText(self._format_var(s_cur))
                    ui_card['s_var_cur'].setStyleSheet("color: #FFFFFF;")

                    ui_card['s_var_ytd'].setText(self._format_var(s_ytd))
                    ui_card['s_var_ytd'].setStyleSheet("color: #FFFFFF;")

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
        except Exception as e:
            logger.error(f"Error rendering top row cards: {e}")

    def render_family_card(self, filtered_df: pd.DataFrame) -> None:
        """Renders the top family statistics block."""
        try:
            grid = self.family_ui['grid']

            for i in reversed(range(grid.count())):
                item = grid.itemAt(i)
                widget = item.widget()
                if widget:
                    row, col, rowspan, colspan = grid.getItemPosition(i)
                    if row > 1:
                        grid.removeWidget(widget)
                        widget.deleteLater()

            stats = DashboardService.get_dashboard_family_stats(filtered_df)

            if not stats:
                empty_lbl = QLabel("No production lines found for this team.")
                empty_lbl.setStyleSheet("color: #666666; font-style: italic;")
                grid.addWidget(empty_lbl, 2, 0, 1, 5)
                return

            row_idx = 2
            for i, stat in enumerate(stats):
                lbl_fam = QLabel(f"#{i+1}  {stat['family']}")
                lbl_fam.setStyleSheet("color: #E0E0E0; font-size: 13px; font-weight: bold;")

                lbl_lines = QLabel(str(stat['lines']))
                lbl_lines.setStyleSheet("color: #E0E0E0; font-size: 13px;")

                lbl_lead = QLabel(f"{stat['avg_lead']:.1f}" if pd.notna(stat['avg_lead']) else "--")
                lbl_lead.setStyleSheet("color: #E0E0E0; font-size: 13px;")

                lbl_proc = QLabel(f"{stat['avg_proc']:.1f}" if pd.notna(stat['avg_proc']) else "--")
                lbl_proc.setStyleSheet("color: #E0E0E0; font-size: 13px;")

                sell_val = stat['total_sell']
                if sell_val > 1000:
                    sell_str = f"${sell_val/1000:.1f}k"
                else:
                    sell_str = f"${sell_val:.0f}"

                lbl_sell = QLabel(sell_str)
                lbl_sell.setStyleSheet("color: #4CAF50; font-size: 13px;")

                grid.addWidget(lbl_fam, row_idx, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(lbl_lines, row_idx, 1, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(lbl_lead, row_idx, 2, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(lbl_proc, row_idx, 3, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(lbl_sell, row_idx, 4, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

                row_idx += 1
        except Exception as e:
            logger.error(f"Error rendering family card: {e}")

    def render_interactive_pies(self, active_df: pd.DataFrame) -> None:
        """Renders the assignee and requirement breakdown pie charts."""
        try:
            self.chart_assignee.removeAllSeries()
            self.chart_req.removeAllSeries()

            dist = DashboardService.get_detailed_donut_data(active_df)

            if not dist:
                self.lbl_req_title.setText("No active lines found.")
                return

            self._current_eng_dist = dist

            series_eng = QPieSeries()
            series_eng.setHoleSize(0.5)

            for eng_name, data in dist.items():
                val = data['total']
                slice_obj = QPieSlice(eng_name, val)
                slice_obj.setBrush(QColor(self.get_dynamic_color(eng_name)))
                slice_obj.setLabelVisible(True)
                slice_obj.setLabel(f"{eng_name} ({val})")
                slice_obj.hovered.connect(lambda state, slc=slice_obj, e=eng_name: self._on_eng_slice_hovered(state, e, slc)) # type: ignore
                series_eng.append(slice_obj)

            self.chart_assignee.addSeries(series_eng)

            self._global_req_dist = {}
            for eng_data in dist.values():
                for r_name, r_val in eng_data['reqs'].items():
                    self._global_req_dist[r_name] = self._global_req_dist.get(r_name, 0) + r_val

            self._render_req_pie(self._global_req_dist, "Team Requirement Breakdown")
        except Exception as e:
            logger.error(f"Error rendering interactive pie charts: {e}")

    def _on_eng_slice_hovered(self, state: bool, eng_name: str, slice_obj: QPieSlice) -> None:
        """Handles mouse hover events on the engineer pie chart to filter the req chart."""
        try:
            if state:
                slice_obj.setExploded(True)
                slice_obj.setLabelFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                eng_data = self._current_eng_dist.get(eng_name, {})
                self._render_req_pie(eng_data.get('reqs', {}), f"{eng_name}'s Open Lines")
            else:
                slice_obj.setExploded(False)
                slice_obj.setLabelFont(QFont("Segoe UI", 9))
                self._render_req_pie(self._global_req_dist, "Team Requirement Breakdown")
        except Exception as e:
            logger.error(f"Error on engineer slice hover: {e}")

    def _render_req_pie(self, req_data: Dict[str, int], title: str) -> None:
        """Draws the requirements pie chart."""
        try:
            self.chart_req.removeAllSeries()
            self.lbl_req_title.setText(title)

            if not req_data: return

            series = QPieSeries()
            series.setHoleSize(0.5)

            sorted_reqs = sorted(req_data.items(), key=lambda x: x[1], reverse=True)

            for req_name, val in sorted_reqs:
                slice_obj = QPieSlice(req_name, val)
                slice_obj.setBrush(QColor(self.get_req_color(req_name)))
                slice_obj.setLabelVisible(True)
                slice_obj.setLabel(f"{self._abbr_req(req_name)} ({val})")
                series.append(slice_obj)

            self.chart_req.addSeries(series)
        except Exception as e:
            logger.error(f"Error rendering req pie: {e}")

    def render_timeline_row(self, active_df: pd.DataFrame, comp_df: pd.DataFrame) -> None:
        """Renders the timeline forecast as an interactive Spline/Scatter chart with Viewport Zooming."""
        try:
            chart = self.timeline_ui['chart']
            chart.removeAllSeries()
            for ax in chart.axes(): chart.removeAxis(ax)
            self.series_map.clear()

            date_filter_val = self.timeline_ui['date_filter'].currentText()
            today = pd.Timestamp.today().normalize()

            # Define the viewport target date
            if date_filter_val == "Last 4 Weeks":
                target_start_date = today - pd.Timedelta(weeks=4)
            elif date_filter_val == "Last 8 Weeks":
                target_start_date = today - pd.Timedelta(weeks=8)
            elif date_filter_val == "Year to Date":
                target_start_date = pd.Timestamp(year=today.year, month=1, day=1)
            else:
                target_start_date = pd.Timestamp(year=2000, month=1, day=1)

            # Backend ignores target_start_date and provides up to a 52-week buffer to anchor splines
            weeks, reqs, df = DashboardService.prepare_timeline_data(comp_df, active_df, target_start_date)

            if not weeks or df.empty:
                return

            self._timeline_df = df
            self._timeline_weeks = weeks

            # Calculate Viewport bounds based on target_start_date
            target_year, target_week, _ = target_start_date.isocalendar()
            target_yw = f"{target_year}-{target_week:02d}"

            start_idx = 0
            for i, w in enumerate(weeks):
                if w >= target_yw:
                    start_idx = i
                    break
            end_idx = len(weeks) - 1

            # --- Configure X-Axis (Category Labels) ---
            axis_x = QBarCategoryAxis()
            display_weeks = [self.get_relative_week_label(w) for w in weeks]
            axis_x.append(display_weeks)
            axis_x.setLabelsColor(QColor("#AAAAAA"))
            axis_x.setLinePenColor(QColor("#454548"))
            chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)

            # Restrict visual bounds for Viewport Zooming
            if display_weeks and start_idx <= end_idx:
                axis_x.setRange(display_weeks[start_idx], display_weeks[end_idx])

            # --- Configure Y-Axis (Variance Values) ---
            axis_y = QValueAxis()
            axis_y.setLabelsColor(QColor("#AAAAAA"))
            axis_y.setLinePenColor(QColor("#454548"))
            axis_y.setGridLineColor(QColor("#2E2E32"))
            chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)

            # --- Configure Hidden Numerical X-Axis (For Spline/Scatter Mapping) ---
            axis_x_line = QValueAxis()
            axis_x_line.setRange(start_idx - 0.5, end_idx + 0.5)
            axis_x_line.setVisible(False)
            chart.addAxis(axis_x_line, Qt.AlignmentFlag.AlignBottom)

            min_val = 0.0
            max_val = 0.0
            series_list = []

            # Loop over categories to build smooth lines and hover nodes
            for req in reqs:
                req_color = QColor(self.get_req_color(req))
                is_hidden = req in self.hidden_series

                # Completed Data (Solid Spline + Opaque Nodes)
                comp_spline = QSplineSeries()
                comp_spline.setName(req)
                comp_spline.setPen(QPen(req_color, 2, Qt.PenStyle.SolidLine))
                comp_spline.setVisible(not is_hidden)

                comp_scatter = QScatterSeries()
                comp_scatter.setName(f"{req} Nodes")
                comp_scatter.setMarkerSize(10)
                comp_scatter.setColor(req_color)
                comp_scatter.setBorderColor(QColor("#FFFFFF"))
                comp_scatter.setVisible(not is_hidden)

                # Forecast Data (Dashed Spline + Transparent Nodes)
                fcst_color = QColor(req_color)
                fcst_color.setAlpha(150)

                fcst_spline = QSplineSeries()
                fcst_spline.setName(f"{req} (Forecast)")
                fcst_spline.setPen(QPen(fcst_color, 2, Qt.PenStyle.DashLine))
                fcst_spline.setVisible(not is_hidden)

                fcst_scatter = QScatterSeries()
                fcst_scatter.setName(f"{req} (Forecast Nodes)")
                fcst_scatter.setMarkerSize(10)
                fcst_scatter.setColor(fcst_color)
                fcst_scatter.setBorderColor(QColor("#AAAAAA"))
                fcst_scatter.setVisible(not is_hidden)

                self.series_map[req] = {
                    'comp_spline': comp_spline,
                    'comp_scatter': comp_scatter,
                    'fcst_spline': fcst_spline,
                    'fcst_scatter': fcst_scatter
                }

                has_comp_data = False
                has_fcst_data = False

                for w_idx, w in enumerate(weeks):
                    mask_c = (df['REQUIREMENT'].replace('', 'Uncategorized') == req) & (df['YearWeek'] == w) & (df['IS_FORECAST'] == False)
                    mask_f = (df['REQUIREMENT'].replace('', 'Uncategorized') == req) & (df['YearWeek'] == w) & (df['IS_FORECAST'] == True)

                    subset_c = df[mask_c]
                    subset_f = df[mask_f]

                    # Note: We safely append to the series using the integer index of the week
                    if not subset_c.empty:
                        c_val = float(subset_c['VAR_DAYS'].mean())
                        comp_spline.append(w_idx, c_val)
                        comp_scatter.append(w_idx, c_val)
                        has_comp_data = True
                        if w_idx >= start_idx:
                            max_val = max(max_val, c_val)
                            min_val = min(min_val, c_val)

                    if not subset_f.empty:
                        f_val = float(subset_f['VAR_DAYS'].mean())
                        fcst_spline.append(w_idx, f_val)
                        fcst_scatter.append(w_idx, f_val)
                        has_fcst_data = True
                        if w_idx >= start_idx:
                            max_val = max(max_val, f_val)
                            min_val = min(min_val, f_val)

                if has_comp_data:
                    comp_scatter.hovered.connect(lambda point, state, r=req: self._on_node_hovered(point, state, r, False)) # type: ignore
                    series_list.extend([comp_spline, comp_scatter])

                if has_fcst_data:
                    fcst_scatter.hovered.connect(lambda point, state, r=req: self._on_node_hovered(point, state, r, True)) # type: ignore
                    series_list.extend([fcst_spline, fcst_scatter])

            # Attach all populated series to the shared axes
            for s in series_list:
                chart.addSeries(s)
                s.attachAxis(axis_x_line)
                s.attachAxis(axis_y)

            y_padding = max(abs(max_val), abs(min_val)) * 0.2
            if y_padding == 0: y_padding = 2
            axis_y.setRange(min_val - y_padding - 1, max_val + y_padding + 1)
            axis_y.applyNiceNumbers()

            today_year, today_week, _ = today.isocalendar()
            curr_year_week = f"{today_year}-{today_week:02d}"

            # Future area highlighting
            if curr_year_week in weeks:
                curr_idx = weeks.index(curr_year_week)

                future_area = QAreaSeries()
                future_area.setName("Future Highlight")

                lower = QLineSeries()
                lower.append(curr_idx - 0.5, axis_y.min())
                lower.append(len(weeks) - 0.5, axis_y.min())
                upper = QLineSeries()
                upper.append(curr_idx - 0.5, axis_y.max())
                upper.append(len(weeks) - 0.5, axis_y.max())

                future_area.setLowerSeries(lower)
                future_area.setUpperSeries(upper)

                highlight = QColor("#007ACC")
                highlight.setAlpha(20)
                future_area.setBrush(highlight)
                future_area.setPen(Qt.PenStyle.NoPen)
                chart.addSeries(future_area)
                future_area.attachAxis(axis_x_line)
                future_area.attachAxis(axis_y)

            # Target / Zero Line
            zero_line = QLineSeries()
            zero_line.setName("Target")
            zero_line.append(-0.5, 0)
            zero_line.append(len(weeks) - 0.5, 0)
            zero_line.setPen(QPen(QColor("#FFFFFF"), 3, Qt.PenStyle.SolidLine))
            chart.addSeries(zero_line)
            zero_line.attachAxis(axis_x_line)
            zero_line.attachAxis(axis_y)

            # Legend interactive cleanup
            chart.legend().show()
            chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
            for marker in chart.legend().markers():
                label = marker.label()
                if "(Forecast)" in label or "Nodes" in label or label == "Target" or label == "Future Highlight":
                    marker.setVisible(False)
                else:
                    req_name = label
                    is_hidden = req_name in self.hidden_series

                    # Force the marker to stay visible so we can toggle it back on
                    marker.setVisible(True)

                    brush = marker.labelBrush()
                    brush.setColor(QColor("#666666") if is_hidden else QColor("#FFFFFF"))
                    marker.setLabelBrush(brush)

                    marker.clicked.connect(lambda checked=False, m=marker, r=req_name: self._on_legend_marker_clicked(m, r))
                    marker.hovered.connect(self._on_legend_hovered)

        except Exception as e:
            logger.error(f"Error rendering timeline row: {e}")

    def _on_legend_hovered(self, state: bool) -> None:
        """Changes the mouse cursor to a pointing hand when hovering over legend items."""
        try:
            if state:
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            else:
                self.unsetCursor()
        except Exception as e:
            logger.error(f"Error handling legend hover: {e}")

    def _on_legend_marker_clicked(self, marker: QLegendMarker, req_name: str) -> None:
        """Handles toggling series visibility, saving user preference, and cleaning up auto-generated markers."""
        try:
            if req_name in self.hidden_series:
                self.hidden_series.remove(req_name)
                is_hidden = False
            else:
                self.hidden_series.add(req_name)
                is_hidden = True

            self._save_hidden_series()

            if req_name in self.series_map:
                s_dict = self.series_map[req_name]
                for s in s_dict.values():
                    if s: s.setVisible(not is_hidden)

            # Force the marker to remain visible after hiding its linked series
            marker.setVisible(True)

            brush = marker.labelBrush()
            brush.setColor(QColor("#666666") if is_hidden else QColor("#FFFFFF"))
            marker.setLabelBrush(brush)

            # --- NEW FIX: Re-hide the sub-markers that Qt auto-unhides ---
            chart = self.timeline_ui['chart']
            for m in chart.legend().markers():
                label = m.label()
                if "(Forecast)" in label or "Nodes" in label or label == "Target" or label == "Future Highlight":
                    m.setVisible(False)

        except Exception as e:
            logger.error(f"Error toggling legend marker: {e}")

    def _on_node_hovered(self, point: QPointF, state: bool, req_name: str, is_forecast: bool) -> None:
        """Handles tooltip rendering with dynamic window bounds clamping."""
        if not state:
            self.chart_tooltip.hide()
            return

        try:
            # Map the point's exact X coordinate back to the list index integer
            index = int(round(point.x()))
            if index < 0 or index >= len(self._timeline_weeks):
                return

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

            # Explicit, readable variance translations
            trend_text = "Behind by" if avg_var < 0 else "Ahead by"
            trend_color = "#FF5252" if avg_var < 0 else "#4CAF50"

            details = [
                f"<b>Total Lines:</b> {int(total_lines)}",
                f"<b>Avg Variance:</b> <span style='color:{trend_color};'>{trend_text} {abs(avg_var):.1f} days</span>",
                "<br><b>Projects:</b>"
            ]

            proj_col = 'PROJECT NAME' if 'PROJECT NAME' in subset.columns else 'PROJECT_ID'
            proj_vars = subset.groupby(proj_col)['VAR_DAYS'].mean().sort_values(ascending=True)

            projects = list(proj_vars.items())
            for p_name, p_var in projects[:5]:
                p_color = "#FF5252" if p_var < 0 else "#4CAF50"
                p_trend = "Behind" if p_var < 0 else "Ahead"
                details.append(f"• {str(p_name)[:30]}: <span style='color:{p_color};'>{abs(p_var):.1f}d {p_trend}</span>")

            if len(projects) > 5:
                details.append(f"<i>...and {len(projects) - 5} more</i>")

            self.tooltip_content.setText("<br>".join(details))

            # Recalculate physical size before moving to ensure accurate math
            self.chart_tooltip.adjustSize()

            global_pos = QCursor.pos()
            local_pos = self.mapFromGlobal(global_pos)

            # --- Tooltip Bounds Clamping Logic ---
            tt_width = self.chart_tooltip.width()
            tt_height = self.chart_tooltip.height()

            # Default placement (bottom-right of cursor)
            target_x = local_pos.x() + 15
            target_y = local_pos.y() + 15

            # Clamp to left edge if colliding with right window border
            if target_x + tt_width > self.width():
                target_x = local_pos.x() - tt_width - 15

            # Clamp to top edge if colliding with bottom window border
            if target_y + tt_height > self.height():
                target_y = local_pos.y() - tt_height - 15

            # Ensure the inversion didn't push it off the left/top edges
            target_x = max(0, target_x)
            target_y = max(0, target_y)

            self.chart_tooltip.move(target_x, target_y)
            self.chart_tooltip.show()
            self.chart_tooltip.raise_()

        except Exception as e: # type: ignore # noqa
            logger.exception("Tooltip Error: %s", e)
            self.chart_tooltip.hide()