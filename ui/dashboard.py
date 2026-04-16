from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                               QLabel, QFrame, QComboBox, QToolTip)
from PySide6.QtCharts import (QChart, QChartView, QPieSeries, QBarSeries,
                              QBarSet, QBarCategoryAxis, QValueAxis, QLineSeries, QAreaSeries)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QCursor
import pandas as pd
import numpy as np

# Import our newly separated custom widget!
from ui.custom_widgets import CheckableComboBox


class DashboardWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.master_df = pd.DataFrame()
        self._current_hover = None
        self._chart_refs = []

        self.dynamic_color_map = {}
        self.palette = ["#2196F3", "#F44336", "#4CAF50", "#FF9800", "#9C27B0", "#00BCD4", "#795548", "#E91E63"]

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)

        header_layout = QHBoxLayout()
        header = QLabel("Engineering Workload Dashboard")
        header.setStyleSheet("font-size: 20px; font-weight: bold; color: #FFFFFF;")
        header_layout.addWidget(header)
        header_layout.addStretch()

        filter_lbl = QLabel("Global Type Filter:")
        filter_lbl.setStyleSheet("color: #AAAAAA; font-weight: bold; font-size: 12px;")
        header_layout.addWidget(filter_lbl)

        # Using our custom widget
        self.global_type_filter = CheckableComboBox()
        self.global_type_filter.setMinimumWidth(150)
        self.global_type_filter.selection_changed.connect(self.render_all)
        header_layout.addWidget(self.global_type_filter)

        main_layout.addLayout(header_layout)

        top_cards_layout = QHBoxLayout()
        top_cards_layout.setSpacing(15)

        self.prod_ui = self.create_active_card("Production Queue", show_req_filter=False, show_var=True)
        self.quote_ui = self.create_active_card("Submittal Queue", show_req_filter=True, show_var=False)

        top_cards_layout.addWidget(self.prod_ui['card'])
        top_cards_layout.addWidget(self.quote_ui['card'])

        main_layout.addLayout(top_cards_layout, 1)

        self.hist_ui = self.create_history_card("Completed Jobs & Active Forecast")
        main_layout.addWidget(self.hist_ui['card'], 1)

        if self.prod_ui['req_filter']: self.prod_ui['req_filter'].currentTextChanged.connect(self.render_prod_card)
        self.prod_ui['type_filter'].currentTextChanged.connect(self.render_prod_card)

        if self.quote_ui['req_filter']: self.quote_ui['req_filter'].currentTextChanged.connect(self.render_quote_card)
        self.quote_ui['type_filter'].currentTextChanged.connect(self.render_quote_card)

        self.hist_ui['req_filter'].currentTextChanged.connect(self.render_hist_card)
        self.hist_ui['date_filter'].currentTextChanged.connect(self.render_hist_card)

    def get_dynamic_color(self, name):
        name = str(name).strip().upper()
        if not name or name == "UNASSIGNED": return "#888888"

        if name not in self.dynamic_color_map:
            color_idx = len(self.dynamic_color_map) % len(self.palette)
            self.dynamic_color_map[name] = self.palette[color_idx]

        return self.dynamic_color_map[name]

    def create_active_card(self, title, show_req_filter=True, show_var=True):
        card = QFrame()
        card.setObjectName("DashCard")
        card.setStyleSheet(
            "QFrame#DashCard { background-color: #1E1E20; border: 1px solid #3E3E42; border-radius: 8px; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top_bar = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #E0E0E0;")
        top_bar.addWidget(title_lbl)
        top_bar.addStretch()

        req_filter = None
        if show_req_filter:
            req_filter = QComboBox()
            req_filter.addItem("All Reqs")
            req_filter.setMaximumHeight(24)
            top_bar.addWidget(req_filter)

        type_filter = QComboBox()
        type_filter.addItem("All Types")
        type_filter.setMaximumHeight(24)
        top_bar.addWidget(type_filter)
        layout.addLayout(top_bar)

        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(8)

        kpi_lines = self.create_kpi_block("Total Lines")
        kpi_queue = self.create_kpi_block("Avg Queue Days")
        kpi_proc = self.create_kpi_block("Avg Process Days")

        kpi_layout.addWidget(kpi_lines['frame'])

        kpi_var = None
        if show_var:
            kpi_var = self.create_kpi_block("Avg Target Var")
            kpi_layout.addWidget(kpi_var['frame'])

        kpi_layout.addWidget(kpi_queue['frame'])
        kpi_layout.addWidget(kpi_proc['frame'])
        layout.addLayout(kpi_layout)

        chart = QChart()
        chart.setTheme(QChart.ChartThemeDark)
        chart.setBackgroundBrush(Qt.NoBrush)
        chart.layout().setContentsMargins(0, 0, 0, 0)
        chart.legend().hide()

        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.Antialiasing)
        chart_view.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(chart_view, 1)

        return {
            'card': card, 'req_filter': req_filter, 'type_filter': type_filter,
            'lbl_lines': kpi_lines['val'],
            'lbl_var': kpi_var['val'] if kpi_var else None,
            'lbl_queue': kpi_queue['val'], 'lbl_proc': kpi_proc['val'],
            'chart': chart, 'chart_view': chart_view
        }

    def create_history_card(self, title):
        card = QFrame()
        card.setObjectName("DashCard")
        card.setStyleSheet(
            "QFrame#DashCard { background-color: #1E1E20; border: 1px solid #3E3E42; border-radius: 8px; }")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        top_bar = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #E0E0E0;")
        top_bar.addWidget(title_lbl)
        top_bar.addStretch()

        req_filter = QComboBox()
        req_filter.addItem("All Reqs")
        req_filter.setMaximumHeight(24)
        date_filter = QComboBox()
        date_filter.addItems(["Last 30 Days", "Last 90 Days", "Year to Date", "All Time"])
        date_filter.setCurrentText("Last 90 Days")
        date_filter.setMaximumHeight(24)

        top_bar.addWidget(req_filter)
        top_bar.addWidget(date_filter)
        layout.addLayout(top_bar)

        chart = QChart()
        chart.setTheme(QChart.ChartThemeDark)
        chart.setBackgroundBrush(Qt.NoBrush)
        chart.layout().setContentsMargins(0, 0, 0, 0)

        chart_view = QChartView(chart)
        chart_view.setRenderHint(QPainter.Antialiasing)
        chart_view.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(chart_view, 1)

        return {
            'card': card, 'req_filter': req_filter, 'date_filter': date_filter,
            'chart': chart, 'chart_view': chart_view
        }

    def create_kpi_block(self, title):
        frame = QFrame()
        frame.setStyleSheet("background-color: #2D2D30; border-radius: 4px;")
        frame.setMaximumHeight(50)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(2)

        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #AAAAAA; font-size: 10px; font-weight: bold;")
        lbl_title.setAlignment(Qt.AlignCenter)

        lbl_val = QLabel("0")
        lbl_val.setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")
        lbl_val.setAlignment(Qt.AlignCenter)

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_val)

        return {'frame': frame, 'val': lbl_val}

    @staticmethod
    def parse_variance(val):
        if pd.isna(val) or val == "": return np.nan
        try:
            return float(str(val).replace('days', '').strip())
        except:
            return np.nan

    def update_dashboard(self, df):
        if df.empty: return
        self.master_df = df.copy()

        if 'LINE_COUNT' not in self.master_df.columns:
            self.master_df['LINE_COUNT'] = 1

        current_types = self.global_type_filter.get_checked_items()
        is_first_load = self.global_type_filter.model.rowCount() == 0

        unique_types = sorted(
            [str(x) for x in self.master_df['TYPE'].replace('', 'Unknown').unique() if str(x).strip()])
        default_types = ["MOD", "CUS", "PART-MC"]

        self.global_type_filter.blockSignals(True)
        self.global_type_filter.model.clear()

        for t in unique_types:
            if is_first_load:
                is_checked = t in default_types
            else:
                is_checked = t in current_types
            self.global_type_filter.add_item(t, is_checked)

        self.global_type_filter.update_text()
        self.global_type_filter.blockSignals(False)

        self.active_df = self.master_df[self.master_df['STATUS'].str.strip().str.upper() != 'COMPLETE'].copy()
        self.comp_df = self.master_df[self.master_df['STATUS'].str.strip().str.upper() == 'COMPLETE'].copy()

        prod_mask = self.active_df['REQUIREMENT'].str.contains('PROD', case=False, na=False)
        self.prod_base = self.active_df[prod_mask]
        self.quote_base = self.active_df[~prod_mask]

        if self.prod_ui['req_filter']:
            self.populate_combo(self.prod_ui['req_filter'], self.prod_base['REQUIREMENT'], "All Reqs")
        self.populate_combo(self.prod_ui['type_filter'], self.prod_base['TYPE'], "All Types")

        if self.quote_ui['req_filter']:
            self.populate_combo(self.quote_ui['req_filter'], self.quote_base['REQUIREMENT'], "All Reqs")
        self.populate_combo(self.quote_ui['type_filter'], self.quote_base['TYPE'], "All Types")

        self.populate_combo(self.hist_ui['req_filter'], self.master_df['REQUIREMENT'], "All Reqs")

        self.render_all()

    def populate_combo(self, combo, series, default_text):
        current = combo.currentText()
        items = [str(x) for x in series.replace('', 'Uncategorized').unique() if str(x).strip()]
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(default_text)
        combo.addItems(sorted(items))
        if current in [combo.itemText(i) for i in range(combo.count())]:
            combo.setCurrentText(current)
        combo.blockSignals(False)

    def render_all(self):
        self.render_prod_card()
        self.render_quote_card()
        self.render_hist_card()

    def render_prod_card(self):
        if hasattr(self, 'prod_base'):
            self._apply_active_card_logic(self.prod_base.copy(), self.prod_ui)

    def render_quote_card(self):
        if hasattr(self, 'quote_base'):
            self._apply_active_card_logic(self.quote_base.copy(), self.quote_ui)

    def _apply_active_card_logic(self, df, ui_dict):
        checked_types = self.global_type_filter.get_checked_items()
        if checked_types:
            df = df[df['TYPE'].replace('', 'Unknown').isin(checked_types)]
        else:
            df = df.iloc[0:0]

        if ui_dict['req_filter']:
            req = ui_dict['req_filter'].currentText()
            if req != "All Reqs": df = df[df['REQUIREMENT'].replace('', 'Uncategorized') == req]

        typ = ui_dict['type_filter'].currentText()
        if typ != "All Types": df = df[df['TYPE'].replace('', 'Unknown') == typ]

        ui_dict['lbl_lines'].setText(str(int(df['LINE_COUNT'].sum())))

        if ui_dict.get('lbl_var'):
            var_series = df['EST ENG VARIANCE'].apply(self.parse_variance).dropna()
            avg_var = var_series.mean() if not var_series.empty else np.nan
            ui_dict['lbl_var'].setText(f"{avg_var:+.1f} d" if not pd.isna(avg_var) else "--")
            ui_dict['lbl_var'].setStyleSheet(
                f"color: {'#FF5252' if avg_var < 0 else '#4CAF50'}; font-size: 16px; font-weight: bold;")

        if 'QUEUE_DAYS' in df.columns:
            q_series = df['QUEUE_DAYS'].apply(self.parse_variance).dropna()
            avg_q = q_series.mean() if not q_series.empty else np.nan
            ui_dict['lbl_queue'].setText(f"{avg_q:.1f} d" if not pd.isna(avg_q) else "--")
            ui_dict['lbl_queue'].setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")

        if 'PROCESS_DAYS' in df.columns:
            p_series = df['PROCESS_DAYS'].apply(self.parse_variance).dropna()
            avg_p = p_series.mean() if not p_series.empty else np.nan
            ui_dict['lbl_proc'].setText(f"{avg_p:.1f} d" if not pd.isna(avg_p) else "--")
            ui_dict['lbl_proc'].setStyleSheet("color: #FFFFFF; font-size: 16px; font-weight: bold;")

        self.render_donut_chart(ui_dict['chart'], df, ui_dict['chart_view'])

    def handle_pie_hover(self, state, slice_item, chart_view, eng_name, df):
        if state:
            eng_df = df[df['ASSIGNED TO'] == eng_name]
            if eng_df.empty: return

            tooltip_html = f"<b>{eng_name.upper()} | Active Queue</b><hr/>"

            for _, row in eng_df.head(15).iterrows():
                proj = str(row.get('PROJECT NAME', 'Unknown'))[:20]
                quote = str(row.get('QUOTE NO', '--'))
                req = str(row.get('REQUIREMENT', ''))
                req_short = req[:4] if req else "Unk"

                sell = str(row.get('SELL $', ''))
                sell_str = f" | <span style='color: #4CAF50;'>${sell}</span>" if sell and sell.strip().lower() not in [
                    "", "nan", "0", "0.0"] else ""

                tooltip_html += f"• <span style='color: #AAAAAA;'>{quote} ({req_short})</span> - {proj}{sell_str}<br/>"

            if len(eng_df) > 15:
                tooltip_html += f"<br/><i>...and {len(eng_df) - 15} more lines.</i>"

            pos = QCursor.pos()
            offset_pos = QPoint(pos.x() + 15, pos.y() + 15)
            QToolTip.showText(offset_pos, tooltip_html, chart_view, chart_view.rect(), 30000)
        else:
            QToolTip.hideText()

    def render_donut_chart(self, chart, df, chart_view):
        chart.removeAllSeries()
        pie = QPieSeries()
        pie.setHoleSize(0.4)

        if df.empty:
            chart.addSeries(pie)
            return

        engineers = df['ASSIGNED TO'].unique()

        for eng in engineers:
            eng_name = str(eng).strip().upper()
            if not eng_name: continue

            lines = df[df['ASSIGNED TO'] == eng]['LINE_COUNT'].sum()
            if lines > 0:
                slc = pie.append(f"{eng_name}\n({int(lines)})", lines)
                slc.setLabelVisible(True)
                slc.setLabelColor(QColor("#FFFFFF"))

                c = self.get_dynamic_color(eng_name)

                slc.setBrush(QColor(c))
                slc.setPen(QPen(QColor("#1E1E20"), 2))

                slc.hovered.connect(
                    lambda state, item=slc, e_name=eng, data=df: self.handle_pie_hover(state, item, chart_view, e_name,
                                                                                       data))

        chart.addSeries(pie)

    def handle_bar_hover(self, status, index, req, weeks, df, is_forecast):
        hover_id = f"{req}_{index}_{is_forecast}"
        if status:
            if self._current_hover == hover_id: return
            self._current_hover = hover_id
            try:
                wk = weeks[index]
                mask = (df['REQUIREMENT'].replace('', 'Uncategorized') == req) & (df['YearWeek'] == wk) & (
                        df['IS_FORECAST'] == is_forecast)
                bar_df = df[mask]

                if bar_df.empty: return

                prefix = "🔮 Forecast" if is_forecast else "✅ Actual"
                tooltip_html = f"<b>{prefix} | {req} | {self.get_relative_week_label(wk)}</b><hr/>"

                for _, row in bar_df.head(15).iterrows():
                    proj = str(row.get('PROJECT NAME', 'Unknown'))[:20]
                    quote = str(row.get('QUOTE NO', '--'))
                    var = row.get('VAR_DAYS', 0)
                    color = "#FF5252" if var < 0 else "#4CAF50"
                    tooltip_html += f"• <span style='color: #AAAAAA;'>{quote}</span> - {proj}: <b style='color: {color};'>{var:+.1f}d</b><br/>"

                if len(bar_df) > 15: tooltip_html += f"<br/><i>...and {len(bar_df) - 15} more.</i>"

                pos = QCursor.pos()
                offset_pos = QPoint(pos.x() + 15, pos.y() + 15)
                QToolTip.showText(offset_pos, tooltip_html, self.hist_ui['chart_view'],
                                  self.hist_ui['chart_view'].rect(), 30000)
            except Exception:
                pass
        else:
            self._current_hover = None
            QToolTip.hideText()

    def get_relative_week_label(self, year_week_str):
        try:
            target_year, target_week = map(int, year_week_str.split('-'))
            today = pd.Timestamp.today()
            curr_year, curr_week, _ = today.isocalendar()

            diff = (target_year - curr_year) * 52 + (target_week - curr_week)
            if diff == 0:
                return "Current Wk"
            elif diff > 0:
                return f"+{diff} Wk"
            else:
                return f"{diff} Wk"
        except:
            return year_week_str

    def get_req_color(self, req_name):
        req_upper = str(req_name).upper()
        if 'PROD' in req_upper: return "#4CAF50"
        if 'SUPPORT' in req_upper or 'DOC' in req_upper: return "#F44336"
        if 'QUOT' in req_upper: return "#2196F3"
        if 'APP' in req_upper: return "#FF9800"
        if 'SUB' in req_upper: return "#9C27B0"
        return self.get_dynamic_color(req_upper)

    def render_hist_card(self):
        if not hasattr(self, 'comp_df') or not hasattr(self, 'active_df'): return

        h_df = self.comp_df.copy()
        h_df['TARGET_DATE'] = pd.to_datetime(h_df['COMPLETE DATE'], errors='coerce')
        h_df['VAR_DAYS'] = h_df['COMPLETION VARIANCE'].apply(self.parse_variance).fillna(0)
        h_df['IS_FORECAST'] = False

        f_df = self.active_df.copy()
        f_df['TARGET_DATE'] = pd.to_datetime(f_df['EST END DATE'], errors='coerce')
        f_df['VAR_DAYS'] = f_df['EST ENG VARIANCE'].apply(self.parse_variance).fillna(0)
        f_df['IS_FORECAST'] = True

        df = pd.concat([h_df, f_df], ignore_index=True)
        df = df.dropna(subset=['TARGET_DATE'])

        checked_types = self.global_type_filter.get_checked_items()
        if checked_types:
            df = df[df['TYPE'].replace('', 'Unknown').isin(checked_types)]
        else:
            df = df.iloc[0:0]

        req = self.hist_ui['req_filter'].currentText()
        if req != "All Reqs": df = df[df['REQUIREMENT'].replace('', 'Uncategorized') == req]

        range_sel = self.hist_ui['date_filter'].currentText()
        today = pd.Timestamp.today().normalize()

        if range_sel == "Last 30 Days":
            start_date = today - pd.Timedelta(days=30)
        elif range_sel == "Last 90 Days":
            start_date = today - pd.Timedelta(days=90)
        elif range_sel == "Year to Date":
            start_date = pd.Timestamp(year=today.year, month=1, day=1)
        else:
            start_date = pd.Timestamp.min

        df = df[(df['TARGET_DATE'] >= start_date) | (df['IS_FORECAST'] == True)].copy()

        chart = self.hist_ui['chart']
        chart.removeAllSeries()
        for axis in chart.axes(): chart.removeAxis(axis)

        self._chart_refs = []

        if df.empty: return

        df['YearWeek'] = df['TARGET_DATE'].dt.strftime('%G-%V')

        weeks = sorted(df['YearWeek'].unique().tolist())
        reqs = df['REQUIREMENT'].replace('', 'Uncategorized').unique().tolist()

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

                min_y = min(min_y, act_sum, for_sum)
                max_y = max(max_y, act_sum, for_sum)

            actual_set.hovered.connect(
                lambda status, index, req_type=r: self.handle_bar_hover(status, index, req_type, weeks, df, False))
            forecast_set.hovered.connect(
                lambda status, index, req_type=r: self.handle_bar_hover(status, index, req_type, weeks, df, True))

            bar_series.append(actual_set)
            bar_series.append(forecast_set)

        chart.addSeries(bar_series)

        axisX = QBarCategoryAxis()
        categories = [self.get_relative_week_label(wk) for wk in weeks]
        axisX.append(categories)

        font = QFont("Segoe UI", 8, QFont.Bold)
        axisX.setLabelsFont(font)
        chart.addAxis(axisX, Qt.AlignBottom)
        bar_series.attachAxis(axisX)

        axisY = QValueAxis()
        padding = max(abs(max_y), abs(min_y)) * 0.2 + 2
        y_min = min_y - padding
        y_max = max_y + padding
        axisY.setRange(y_min, y_max)

        # RESTORED MISSING CODE: Attaching the Y Axis to the chart
        chart.addAxis(axisY, Qt.AlignLeft)
        bar_series.attachAxis(axisY)

        axisX_line = QValueAxis()
        axisX_line.setRange(-0.5, len(weeks) - 0.5)
        axisX_line.setVisible(False)
        chart.addAxis(axisX_line, Qt.AlignBottom)

        # RESTORED MISSING CODE: The Future Area Highlights and Target Line
        curr_idx = next((i for i, c in enumerate(categories) if "+" in c or "Current" in c), None)
        if curr_idx is not None:
            future_upper = QLineSeries()
            future_lower = QLineSeries()

            start_x = curr_idx - 0.5
            max_x = len(weeks) - 0.5

            future_upper.append(start_x, y_max)
            future_upper.append(max_x, y_max)
            future_lower.append(start_x, y_min)
            future_lower.append(max_x, y_min)

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
        zero_line.append(-0.5, 0)
        zero_line.append(len(weeks) - 0.5, 0)
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