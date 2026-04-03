# ui/dashboard.py

from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCharts import (QChart, QChartView, QPieSeries, QBarSeries, QStackedBarSeries,
                              QBarSet, QBarCategoryAxis, QValueAxis, QLineSeries)
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPainter, QColor, QPen
import pandas as pd
import numpy as np


class DashboardWidget(QWidget):
    def __init__(self):
        super().__init__()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(20)

        header = QLabel("Engineering Workload Dashboard")
        header.setObjectName("Header")
        main_layout.addWidget(header)

        # --- Top Row: KPI Scorecards ---
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(20)

        self.kpi_active = self.create_kpi_card("Active Jobs in Queue", "0")
        self.kpi_eng_var = self.create_kpi_card("Avg Eng Variance (Days)", "0")
        self.kpi_esd_var = self.create_kpi_card("Avg ESD Variance (Days)", "0")

        kpi_layout.addWidget(self.kpi_active['frame'])
        kpi_layout.addWidget(self.kpi_eng_var['frame'])
        kpi_layout.addWidget(self.kpi_esd_var['frame'])

        main_layout.addLayout(kpi_layout)

        # --- Middle Row: Donut & Bar Charts ---
        mid_chart_layout = QHBoxLayout()
        mid_chart_layout.setSpacing(20)

        # 1. Workload Donut Chart
        self.workload_chart = QChart()
        self.workload_chart.setTheme(QChart.ChartThemeDark)
        self.workload_chart.setTitle("Workload Distribution by Engineer & Requirement")
        self.workload_chart.setBackgroundBrush(QColor("#252526"))
        self.workload_view = QChartView(self.workload_chart)
        self.workload_view.setRenderHint(QPainter.Antialiasing)
        self.workload_view.setObjectName("DashCard")

        # 2. Requirement & Type Stacked Bar Chart
        self.type_chart = QChart()
        self.type_chart.setTheme(QChart.ChartThemeDark)
        self.type_chart.setTitle("Active Jobs by Requirement & Type")
        self.type_chart.setBackgroundBrush(QColor("#252526"))
        self.type_view = QChartView(self.type_chart)
        self.type_view.setRenderHint(QPainter.Antialiasing)
        self.type_view.setObjectName("DashCard")

        mid_chart_layout.addWidget(self.workload_view)
        mid_chart_layout.addWidget(self.type_view)
        main_layout.addLayout(mid_chart_layout, 1)

        # --- Bottom Row: Trend Line Chart ---
        self.trend_chart = QChart()
        self.trend_chart.setTheme(QChart.ChartThemeDark)
        self.trend_chart.setTitle("Historical Variance Trend (Last 15 Completed Jobs)")
        self.trend_chart.setBackgroundBrush(QColor("#252526"))
        self.trend_chart.legend().hide()
        self.trend_view = QChartView(self.trend_chart)
        self.trend_view.setRenderHint(QPainter.Antialiasing)
        self.trend_view.setObjectName("DashCard")

        main_layout.addWidget(self.trend_view, 1)

    def create_kpi_card(self, title, default_val):
        frame = QFrame()
        frame.setObjectName("DashCard")
        layout = QVBoxLayout(frame)
        layout.setAlignment(Qt.AlignCenter)

        lbl_title = QLabel(title)
        lbl_title.setObjectName("DashTitle")
        lbl_title.setAlignment(Qt.AlignCenter)

        lbl_val = QLabel(default_val)
        lbl_val.setObjectName("DashMetric")
        lbl_val.setAlignment(Qt.AlignCenter)

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_val)

        return {'frame': frame, 'val_label': lbl_val}

    def update_dashboard(self, df):
        if df.empty: return

        def parse_variance(val):
            try:
                return float(str(val).replace('days', '').strip())
            except:
                return np.nan

        active_df = df[df['STATUS'].str.strip().str.upper() != 'COMPLETE']

        # ---------------------------------------------------------
        # 1. Update KPI Cards
        # ---------------------------------------------------------
        self.kpi_active['val_label'].setText(str(len(active_df)))

        eng_vars = active_df['EST ENG VARIANCE'].apply(parse_variance).dropna()
        avg_eng = eng_vars.mean() if not eng_vars.empty else 0
        self.kpi_eng_var['val_label'].setText(f"{avg_eng:+.1f}")
        self.kpi_eng_var['val_label'].setStyleSheet(f"color: {'#FF5252' if avg_eng < 0 else '#4CAF50'};")

        esd_vars = active_df['EST ESD VARIANCE'].apply(parse_variance).dropna()
        avg_esd = esd_vars.mean() if not esd_vars.empty else 0
        self.kpi_esd_var['val_label'].setText(f"{avg_esd:+.1f}")
        self.kpi_esd_var['val_label'].setStyleSheet(f"color: {'#FF5252' if avg_esd < 0 else '#4CAF50'};")

        # ---------------------------------------------------------
        # 2. Update Workload Donut Chart (Engineer + Requirement)
        # ---------------------------------------------------------
        self.workload_chart.removeAllSeries()
        pie_series = QPieSeries()
        pie_series.setHoleSize(0.35)

        color_map = {
            'ADAM': QColor("#2E7D32"),  # Green
            'DAVID': QColor("#C62828"),  # Red
            'ANDY': QColor("#1565C0"),  # Blue
            'MATT': QColor("#EF6C00")  # Orange
        }

        # Group by Assignee AND Requirement
        grouped = active_df.groupby(['ASSIGNED TO', 'REQUIRMENT']).size()

        for (eng, req), count in grouped.items():
            if not eng or str(eng).strip() == '': continue

            # Format: "Adam T - Prod (2)"
            req_short = str(req)[:4] if str(req) else "Unk"
            slice_label = f"{eng} - {req_short} ({count})"
            pie_slice = pie_series.append(slice_label, count)
            pie_slice.setLabelVisible(True)

            # Add a dark gap border so slices of the same color are visibly separated
            pie_slice.setPen(QPen(QColor("#252526"), 2))

            # Apply the team's base color
            for key, base_color in color_map.items():
                if key in str(eng).upper():
                    pie_slice.setBrush(base_color)
                    break

        self.workload_chart.addSeries(pie_series)

        # ---------------------------------------------------------
        # 3. Update Requirement & Type Stacked Bar Chart
        # ---------------------------------------------------------
        self.type_chart.removeAllSeries()
        for axis in self.type_chart.axes():
            self.type_chart.removeAxis(axis)

        # Show the legend so we can see the Types mapping!
        self.type_chart.legend().show()
        self.type_chart.legend().setAlignment(Qt.AlignBottom)

        stacked_series = QStackedBarSeries()

        requirements = active_df['REQUIRMENT'].replace('', 'Uncategorized').unique().tolist()
        types = active_df['TYPE'].replace('', 'Unknown').unique().tolist()

        # Build a colored bar segment for each Type across all requirements
        type_colors = ["#1F6AA5", "#FFD54F", "#4CAF50", "#9C27B0"]
        max_stack_val = 0

        for i, t_name in enumerate(types):
            bar_set = QBarSet(str(t_name))
            if i < len(type_colors):
                bar_set.setBrush(QColor(type_colors[i]))

            for req in requirements:
                # Count jobs that match BOTH this Type and this Requirement
                count = len(active_df[(active_df['TYPE'] == t_name) & (active_df['REQUIRMENT'] == req)])
                bar_set.append(count)

            stacked_series.append(bar_set)

        # Find the highest stacked bar to set the Y-axis height
        for req in requirements:
            total_for_req = len(active_df[active_df['REQUIRMENT'] == req])
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

        # ---------------------------------------------------------
        # 4. Update Historical Variance Trend (Line Chart)
        # ---------------------------------------------------------
        self.trend_chart.removeAllSeries()
        for axis in self.trend_chart.axes():
            self.trend_chart.removeAxis(axis)

        comp_df = df[df['STATUS'].str.strip().str.upper() == 'COMPLETE'].copy()

        if not comp_df.empty:
            comp_df['COMPLETE DATE'] = pd.to_datetime(comp_df['COMPLETE DATE'], errors='coerce')
            comp_df = comp_df.dropna(subset=['COMPLETE DATE']).sort_values('COMPLETE DATE').tail(15)

            line_series = QLineSeries()
            line_pen = QPen(QColor("#FFD54F"), 3)
            line_series.setPen(line_pen)

            categories = []
            min_y, max_y = 0, 0

            for i, (idx, row) in enumerate(comp_df.iterrows()):
                val = parse_variance(row['COMPLETION VARIANCE'])
                if np.isnan(val): val = 0

                line_series.append(QPointF(i, val))
                categories.append(str(row['PROJECT NAME'])[:10])

                if val < min_y: min_y = val
                if val > max_y: max_y = val

            self.trend_chart.addSeries(line_series)

            axisX_trend = QBarCategoryAxis()
            axisX_trend.append(categories)
            axisX_trend.setLabelsAngle(-45)
            self.trend_chart.addAxis(axisX_trend, Qt.AlignBottom)
            line_series.attachAxis(axisX_trend)

            axisY_trend = QValueAxis()
            axisY_trend.setRange(min_y - 2, max_y + 2)
            axisY_trend.setTitleText("Days (Late < 0 < Early)")
            self.trend_chart.addAxis(axisY_trend, Qt.AlignLeft)
            line_series.attachAxis(axisY_trend)