from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QComboBox, QGroupBox
from PySide6.QtCharts import (QChart, QChartView, QPieSeries, QBarSeries, QStackedBarSeries,
                              QBarSet, QBarCategoryAxis, QValueAxis, QLineSeries)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QFont
import pandas as pd
import numpy as np


class DashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.master_df = pd.DataFrame()
        self.current_df = pd.DataFrame()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(15)

        # --- Header & Global Filters ---
        header_layout = QHBoxLayout()
        header = QLabel("Engineering Workload Dashboard")
        header.setObjectName("Header")
        header_layout.addWidget(header)
        header_layout.addStretch()

        filter_lbl = QLabel("Global Filters:")
        filter_lbl.setStyleSheet("color: #AAAAAA; font-weight: bold; font-size: 13px;")
        header_layout.addWidget(filter_lbl)

        self.global_eng_filter = QComboBox()
        self.global_eng_filter.addItem("All Engineers")
        self.global_eng_filter.currentTextChanged.connect(self.render_dashboard)
        header_layout.addWidget(self.global_eng_filter)

        self.global_type_filter = QComboBox()
        self.global_type_filter.addItem("All Types")
        self.global_type_filter.currentTextChanged.connect(self.render_dashboard)
        header_layout.addWidget(self.global_type_filter)

        main_layout.addLayout(header_layout)

        # --- Top Row: 3 Independent KPI Windows ---
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(15)

        self.kpi_prod = self.create_kpi_window("Production Queue")
        self.kpi_quote = self.create_kpi_window("Quote / Submittal Queue")
        self.kpi_hist = self.create_kpi_window("Completed Jobs")

        kpi_layout.addWidget(self.kpi_prod['box'])
        kpi_layout.addWidget(self.kpi_quote['box'])
        kpi_layout.addWidget(self.kpi_hist['box'])

        main_layout.addLayout(kpi_layout)

        # --- Middle Row: Donut & Bar Charts ---
        mid_chart_layout = QHBoxLayout()
        mid_chart_layout.setSpacing(20)

        self.workload_chart = QChart()
        self.workload_chart.setTheme(QChart.ChartThemeDark)
        self.workload_chart.setTitle("Workload Distribution")
        self.workload_chart.setBackgroundBrush(QColor("#252526"))
        self.workload_chart.legend().hide()
        self.workload_view = QChartView(self.workload_chart)
        self.workload_view.setRenderHint(QPainter.Antialiasing)
        self.workload_view.setObjectName("DashCard")

        self.type_chart = QChart()
        self.type_chart.setTheme(QChart.ChartThemeDark)
        self.type_chart.setTitle("Active Queue by Type")
        self.type_chart.setBackgroundBrush(QColor("#252526"))
        self.type_view = QChartView(self.type_chart)
        self.type_view.setRenderHint(QPainter.Antialiasing)
        self.type_view.setObjectName("DashCard")

        mid_chart_layout.addWidget(self.workload_view)
        mid_chart_layout.addWidget(self.type_view)
        main_layout.addLayout(mid_chart_layout, 1)

        # --- Bottom Row: Win/Loss Bar Chart ---
        trend_container = QFrame()
        trend_container.setObjectName("DashCard")
        trend_layout = QVBoxLayout(trend_container)
        trend_layout.setContentsMargins(0, 0, 0, 0)

        trend_controls = QHBoxLayout()
        trend_controls.setContentsMargins(15, 10, 15, 0)

        trend_lbl = QLabel("Historical Variance Win/Loss (Weekly)")
        trend_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #FFFFFF;")
        trend_controls.addWidget(trend_lbl)
        trend_controls.addStretch()

        local_filter_lbl = QLabel("Date Range:")
        local_filter_lbl.setStyleSheet("color: #AAAAAA; font-weight: bold;")
        trend_controls.addWidget(local_filter_lbl)

        self.trend_date_filter = QComboBox()
        self.trend_date_filter.addItems(["Last 30 Days", "Last 90 Days", "Year to Date"])
        self.trend_date_filter.setCurrentText("Last 90 Days")
        self.trend_date_filter.currentTextChanged.connect(self.refresh_trend_chart)
        trend_controls.addWidget(self.trend_date_filter)

        trend_layout.addLayout(trend_controls)

        self.trend_chart = QChart()
        self.trend_chart.setTheme(QChart.ChartThemeDark)
        self.trend_chart.setBackgroundBrush(Qt.NoBrush)
        self.trend_chart.legend().show()
        self.trend_chart.legend().setAlignment(Qt.AlignBottom)

        self.trend_view = QChartView(self.trend_chart)
        self.trend_view.setRenderHint(QPainter.Antialiasing)

        trend_layout.addWidget(self.trend_view, 1)
        main_layout.addWidget(trend_container, 1)

    def create_kpi_window(self, title):
        """Creates an independent control panel (window) for targeted KPIs."""
        group = QGroupBox(title)
        group.setStyleSheet("""
            QGroupBox { border: 1px solid #3E3E42; border-radius: 6px; margin-top: 12px; background-color: #252526; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #AAAAAA; font-weight: bold; }
        """)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 15, 10, 10)

        # Local Filter Control
        filter_cb = QComboBox()
        filter_cb.addItem("All Requirements")
        filter_cb.currentTextChanged.connect(self.render_dashboard)
        layout.addWidget(filter_cb)

        # Main KPI Value
        lbl_val = QLabel("0")
        lbl_val.setStyleSheet("font-size: 28px; font-weight: bold; color: #FFFFFF; margin-top: 5px;")
        lbl_val.setAlignment(Qt.AlignCenter)

        # Subtitle KPI Value
        lbl_sub = QLabel("Var: --")
        lbl_sub.setStyleSheet("color: #AAAAAA; font-size: 14px; font-weight: bold;")
        lbl_sub.setAlignment(Qt.AlignCenter)

        layout.addWidget(lbl_val)
        layout.addWidget(lbl_sub)

        return {'box': group, 'val_label': lbl_val, 'sub_label': lbl_sub, 'filter': filter_cb}

    def update_dashboard(self, df):
        if df.empty: return
        self.master_df = df.copy()

        if 'LINE_COUNT' not in self.master_df.columns:
            self.master_df['LINE_COUNT'] = 1

        # Populate Global Filters
        current_eng = self.global_eng_filter.currentText()
        engineers = [str(e) for e in self.master_df['ASSIGNED TO'].unique() if str(e).strip()]
        self.global_eng_filter.blockSignals(True)
        self.global_eng_filter.clear()
        self.global_eng_filter.addItem("All Engineers")
        self.global_eng_filter.addItems(sorted(engineers))
        if current_eng in [self.global_eng_filter.itemText(i) for i in range(self.global_eng_filter.count())]:
            self.global_eng_filter.setCurrentText(current_eng)
        self.global_eng_filter.blockSignals(False)

        current_type = self.global_type_filter.currentText()
        types = [str(t) for t in self.master_df['TYPE'].unique() if str(t).strip()]
        self.global_type_filter.blockSignals(True)
        self.global_type_filter.clear()
        self.global_type_filter.addItem("All Types")
        self.global_type_filter.addItems(sorted(types))
        if current_type in [self.global_type_filter.itemText(i) for i in range(self.global_type_filter.count())]:
            self.global_type_filter.setCurrentText(current_type)
        self.global_type_filter.blockSignals(False)

        # Pre-populate Local Window Filters
        self._populate_local_filter(self.kpi_prod['filter'], self.master_df[
            self.master_df['REQUIREMENT'].str.contains('PROD', case=False, na=False)])
        self._populate_local_filter(self.kpi_quote['filter'], self.master_df[
            self.master_df['REQUIREMENT'].str.contains('QUOT|APP|SUB', case=False, na=False)])
        self._populate_local_filter(self.kpi_hist['filter'], self.master_df)

        self.render_dashboard()

    def _populate_local_filter(self, combo_box, target_df):
        current_val = combo_box.currentText()
        reqs = [str(r) for r in target_df['REQUIREMENT'].replace('', 'Uncategorized').unique() if str(r).strip()]
        combo_box.blockSignals(True)
        combo_box.clear()
        combo_box.addItem("All Requirements")
        combo_box.addItems(sorted(reqs))
        if current_val in [combo_box.itemText(i) for i in range(combo_box.count())]:
            combo_box.setCurrentText(current_val)
        combo_box.blockSignals(False)

    def render_dashboard(self):
        if not hasattr(self, 'master_df') or self.master_df.empty: return

        # 1. Apply Global Filters
        df = self.master_df.copy()
        if self.global_eng_filter.currentText() != "All Engineers":
            df = df[df['ASSIGNED TO'] == self.global_eng_filter.currentText()]
        if self.global_type_filter.currentText() != "All Types":
            df = df[df['TYPE'] == self.global_type_filter.currentText()]

        self.current_df = df

        # Bulletproof float conversion function to prevent Pandas string reduction errors
        def parse_variance(val):
            if pd.isna(val) or val == "": return np.nan
            try:
                return float(str(val).replace('days', '').strip())
            except:
                return np.nan

        active_df = df[df['STATUS'].str.strip().str.upper() != 'COMPLETE']
        comp_df = df[df['STATUS'].str.strip().str.upper() == 'COMPLETE']

        # ---------------------------------------------------------
        # 2. Update KPI Windows with Local Filters Applied
        # ---------------------------------------------------------
        # Production Card
        prod_mask = active_df['REQUIREMENT'].str.contains('PROD', case=False, na=False)
        prod_df = active_df[prod_mask]
        if self.kpi_prod['filter'].currentText() != "All Requirements":
            prod_df = prod_df[prod_df['REQUIREMENT'] == self.kpi_prod['filter'].currentText()]

        self.kpi_prod['val_label'].setText(str(int(prod_df['LINE_COUNT'].sum())))
        prod_var_series = prod_df['EST ENG VARIANCE'].apply(parse_variance).astype(float).dropna()
        prod_var = prod_var_series.mean() if not prod_var_series.empty else np.nan
        self.kpi_prod['sub_label'].setText(f"Est Var: {prod_var:+.1f} days" if not pd.isna(prod_var) else "Est Var: --")
        self.kpi_prod['sub_label'].setStyleSheet(
            f"color: {'#FF5252' if prod_var < 0 else '#4CAF50'}; font-weight: bold; font-size: 14px;")

        # Quote Card
        quote_mask = active_df['REQUIREMENT'].str.contains('QUOT|APP|SUB', case=False, na=False)
        quote_df = active_df[quote_mask]
        if self.kpi_quote['filter'].currentText() != "All Requirements":
            quote_df = quote_df[quote_df['REQUIREMENT'] == self.kpi_quote['filter'].currentText()]

        self.kpi_quote['val_label'].setText(str(int(quote_df['LINE_COUNT'].sum())))
        quote_var_series = quote_df['EST ENG VARIANCE'].apply(parse_variance).astype(float).dropna()
        quote_var = quote_var_series.mean() if not quote_var_series.empty else np.nan
        self.kpi_quote['sub_label'].setText(
            f"Est Var: {quote_var:+.1f} days" if not pd.isna(quote_var) else "Est Var: --")
        self.kpi_quote['sub_label'].setStyleSheet(
            f"color: {'#FF5252' if quote_var < 0 else '#4CAF50'}; font-weight: bold; font-size: 14px;")

        # Historical Card
        hist_df = comp_df.copy()
        if self.kpi_hist['filter'].currentText() != "All Requirements":
            hist_df = hist_df[hist_df['REQUIREMENT'] == self.kpi_hist['filter'].currentText()]

        self.kpi_hist['val_label'].setText(str(int(hist_df['LINE_COUNT'].sum())))
        hist_var_series = hist_df['COMPLETION VARIANCE'].apply(parse_variance).astype(float).dropna()
        hist_var = hist_var_series.mean() if not hist_var_series.empty else np.nan
        self.kpi_hist['sub_label'].setText(f"Avg Var: {hist_var:+.1f} days" if not pd.isna(hist_var) else "Avg Var: --")
        self.kpi_hist['sub_label'].setStyleSheet(
            f"color: {'#FF5252' if hist_var < 0 else '#4CAF50'}; font-weight: bold; font-size: 14px;")

        # ---------------------------------------------------------
        # 3. Update Workload Chart (Combined Labels)
        # ---------------------------------------------------------
        self.workload_chart.removeAllSeries()
        pie_series = QPieSeries()
        pie_series.setHoleSize(0.35)

        color_map = {'ADAM': QColor("#2E7D32"), 'DAVID': QColor("#C62828"), 'ANDY': QColor("#1565C0"),
                     'MATT': QColor("#EF6C00")}
        engineers = active_df['ASSIGNED TO'].unique()

        for eng in engineers:
            eng_name = str(eng).strip().upper()
            if not eng_name: continue

            base_color = QColor("#888888")
            for key, c in color_map.items():
                if key in eng_name:
                    base_color = c
                    break

            eng_df = active_df[active_df['ASSIGNED TO'] == eng]
            total_lines = eng_df['LINE_COUNT'].sum()

            if total_lines > 0:
                req_counts = eng_df.groupby('REQUIREMENT')['LINE_COUNT'].sum()
                breakdown_strs = [f"{str(req)[:4] if req else 'Unk'}: {int(count)}" for req, count in
                                  req_counts.items()]
                slice_label = f"{eng_name}\n({', '.join(breakdown_strs)})"

                pie_slice = pie_series.append(slice_label, total_lines)
                pie_slice.setBrush(base_color)
                pie_slice.setLabelVisible(True)
                pie_slice.setLabelColor(QColor("#FFFFFF"))
                pie_slice.setPen(QPen(QColor("#252526"), 2))

        self.workload_chart.addSeries(pie_series)

        # ---------------------------------------------------------
        # 4. Update Stacked Bar Chart
        # ---------------------------------------------------------
        self.type_chart.removeAllSeries()
        for axis in self.type_chart.axes():
            self.type_chart.removeAxis(axis)

        self.type_chart.legend().show()
        self.type_chart.legend().setAlignment(Qt.AlignBottom)

        stacked_series = QStackedBarSeries()
        stacked_series.setBarWidth(0.7)
        requirements = active_df['REQUIREMENT'].replace('', 'Uncategorized').unique().tolist()
        types = active_df['TYPE'].replace('', 'Unknown').unique().tolist()

        type_colors = ["#1F6AA5", "#FFD54F", "#4CAF50", "#9C27B0"]
        max_stack_val = 0

        for i, t_name in enumerate(types):
            bar_set = QBarSet(str(t_name))
            if i < len(type_colors): bar_set.setBrush(QColor(type_colors[i]))

            for req in requirements:
                req_type_df = active_df[
                    (active_df['TYPE'] == t_name) & (active_df['REQUIREMENT'].replace('', 'Uncategorized') == req)]
                bar_set.append(req_type_df['LINE_COUNT'].sum())

            stacked_series.append(bar_set)

        for req in requirements:
            total_for_req = active_df[active_df['REQUIREMENT'].replace('', 'Uncategorized') == req]['LINE_COUNT'].sum()
            if total_for_req > max_stack_val: max_stack_val = total_for_req

        self.type_chart.addSeries(stacked_series)

        axisX = QBarCategoryAxis()
        axisX.append([str(r)[:10] for r in requirements])
        self.type_chart.addAxis(axisX, Qt.AlignBottom)
        stacked_series.attachAxis(axisX)

        axisY = QValueAxis()
        axisY.setRange(0, max_stack_val + 2)
        axisY.setLabelFormat("%d")
        self.type_chart.addAxis(axisY, Qt.AlignLeft)
        stacked_series.attachAxis(axisY)

        self.refresh_trend_chart()

    def refresh_trend_chart(self):
        """Builds a Win/Loss Bar Chart with thick columns and a spanning Zero line."""
        if self.current_df.empty: return

        self.trend_chart.removeAllSeries()
        for axis in self.trend_chart.axes():
            self.trend_chart.removeAxis(axis)

        comp_df = self.current_df[self.current_df['STATUS'].str.strip().str.upper() == 'COMPLETE'].copy()
        if comp_df.empty: return

        comp_df['COMPLETE DATE'] = pd.to_datetime(comp_df['COMPLETE DATE'], errors='coerce')
        comp_df = comp_df.dropna(subset=['COMPLETE DATE'])

        range_sel = self.trend_date_filter.currentText()
        today = pd.Timestamp.today().normalize()
        if range_sel == "Last 30 Days":
            start_date = today - pd.Timedelta(days=30)
        elif range_sel == "Last 90 Days":
            start_date = today - pd.Timedelta(days=90)
        else:
            start_date = pd.Timestamp(year=today.year, month=1, day=1)

        comp_df = comp_df[comp_df['COMPLETE DATE'] >= start_date].copy()
        if comp_df.empty: return

        comp_df['YearWeek'] = comp_df['COMPLETE DATE'].dt.strftime('%G-%V')
        comp_df['WeekLabel'] = comp_df['COMPLETE DATE'].dt.strftime('Wk %V')

        def parse_variance(val):
            try:
                return float(str(val).replace('days', '').strip())
            except:
                return 0

        comp_df['VAR_DAYS'] = comp_df['COMPLETION VARIANCE'].apply(parse_variance)

        weeks = sorted(comp_df['YearWeek'].unique().tolist())
        reqs = comp_df['REQUIREMENT'].replace('', 'Uncategorized').unique().tolist()

        bar_series = QBarSeries()
        bar_series.setBarWidth(0.9)

        req_colors = ["#1F6AA5", "#FFD54F", "#4CAF50", "#9C27B0", "#E53935", "#00ACC1"]
        min_y, max_y = 0, 0

        for i, req in enumerate(reqs):
            bar_set = QBarSet(str(req))
            if i < len(req_colors):
                bar_set.setBrush(QColor(req_colors[i]))

            for wk in weeks:
                mask = (comp_df['REQUIREMENT'].replace('', 'Uncategorized') == req) & (comp_df['YearWeek'] == wk)
                wk_sum = comp_df.loc[mask, 'VAR_DAYS'].sum()
                bar_set.append(wk_sum)

                if wk_sum < min_y: min_y = wk_sum
                if wk_sum > max_y: max_y = wk_sum

            bar_series.append(bar_set)

        self.trend_chart.addSeries(bar_series)

        # Set up X Axis
        axisX = QBarCategoryAxis()
        label_map = comp_df.drop_duplicates('YearWeek').set_index('YearWeek')['WeekLabel'].to_dict()
        categories = [label_map[wk] for wk in weeks]
        axisX.append(categories)

        font = QFont()
        font.setPointSize(8)
        axisX.setLabelsFont(font)
        self.trend_chart.addAxis(axisX, Qt.AlignBottom)
        bar_series.attachAxis(axisX)

        # Set up Y Axis
        axisY = QValueAxis()
        padding = max(abs(max_y), abs(min_y)) * 0.2
        if padding == 0: padding = 2

        axisY.setRange(min_y - padding, max_y + padding)
        axisY.setTitleText("Total Variance (Days)")
        self.trend_chart.addAxis(axisY, Qt.AlignLeft)
        bar_series.attachAxis(axisY)

        # ---------------------------------------------------------
        # NEW: Spanning Zero Line!
        # By setting the X coordinates from -0.5 to length - 0.5,
        # the line touches the absolute left and right bounds of the graph
        # ---------------------------------------------------------
        zero_line = QLineSeries()
        zero_line.setName("Target (Zero Variance)")

        max_idx = max(0, len(weeks) - 0.5)
        zero_line.append(-0.5, 0)
        zero_line.append(max_idx, 0)

        zero_pen = QPen(QColor("#FFFFFF"), 2, Qt.SolidLine)
        zero_line.setPen(zero_pen)

        self.trend_chart.addSeries(zero_line)
        zero_line.attachAxis(axisX)
        zero_line.attachAxis(axisY)