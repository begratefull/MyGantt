from PySide6.QtGui import QGuiApplication, QPen, QColor, QFont
from PySide6.QtWidgets import QTableWidgetItem
from PySide6.QtCore import Qt, QTimer
import pandas as pd
from ui.gantt_components import GanttBlock


class AppController:
    def __init__(self, view, model):
        self.view = view
        self.model = model

        self.excel_path = r"C:\Users\fgibil1a\OneDrive - Legrand France\Development\Engineering Workload_Data\Engineering_Workload_Sync.xlsx"

        self.day_width = 25
        self.row_height = 28
        self.current_plan_df = pd.DataFrame()

        # Prevents snapping back to today every time you sync or filter!
        self.initial_scroll_done = False

        self.refresh_tables()

        self.view.sync_btn.clicked.connect(self.handle_sync)
        self.view.filter_req.currentTextChanged.connect(self.refresh_tables)
        self.view.filter_status.currentTextChanged.connect(self.refresh_tables)

        self.view.gantt_scene.selectionChanged.connect(self.handle_block_selection)
        self.view.info_table.itemSelectionChanged.connect(self.handle_table_selection)
        self.view.save_edit_btn.clicked.connect(self.handle_save_edit)

        # NEW: Listen for clicks on the empty void of the Gantt chart!
        self.view.gantt_view.empty_clicked.connect(self.clear_all_selections)

    def refresh_tables(self):
        raw_df = self.model.get_raw_data()
        self.view.display_dataframe(self.view.raw_table, raw_df)

        plan_df = self.model.get_planning_data()
        if plan_df.empty: return

        req_filter = self.view.filter_req.currentText()
        if req_filter != "All Reqs":
            plan_df = plan_df[plan_df['REQUIRMENT'].str.contains(req_filter, case=False, na=False)]

        status_filter = self.view.filter_status.currentText()
        if status_filter == "Active":
            plan_df = plan_df[plan_df['STATUS'].str.upper() != 'COMPLETE']
        elif status_filter == "Complete":
            plan_df = plan_df[plan_df['STATUS'].str.upper() == 'COMPLETE']

        plan_df['SORT_DATE'] = pd.to_datetime(plan_df['ENG START DATE'].replace('', pd.NaT)).combine_first(
            pd.to_datetime(plan_df['EST START DATE'].replace('', pd.NaT))).combine_first(
            pd.to_datetime(plan_df['ENG DUE DATE'].replace('', pd.NaT)))

        plan_df = plan_df.sort_values(by=['STATUS', 'SORT_DATE'], ascending=[True, True])
        plan_df = plan_df.drop(columns=['SORT_DATE'])

        self.current_plan_df = plan_df.reset_index(drop=True)

        self.view.info_table.blockSignals(True)
        self.populate_left_table(self.current_plan_df)
        self.view.info_table.blockSignals(False)

        self.draw_gantt_canvas(self.current_plan_df)
        self.view.kpi_panel.hide()

    def populate_left_table(self, df):
        table = self.view.info_table
        table.setRowCount(df.shape[0])
        for row_idx, row in df.iterrows():
            table.setItem(row_idx, 0, QTableWidgetItem(str(row.get('REQUIRMENT', ''))))
            table.setItem(row_idx, 1, QTableWidgetItem(str(row.get('QUOTE NO', ''))))
            table.setItem(row_idx, 2, QTableWidgetItem(str(row.get('PROJECT NAME', ''))))
            table.setItem(row_idx, 3, QTableWidgetItem(str(row.get('ESD', ''))))
            table.setItem(row_idx, 4, QTableWidgetItem(str(row.get('STATUS', ''))))
        table.resizeColumnsToContents()

    def get_business_day_offset(self, start_date, target_date):
        if pd.isna(target_date) or pd.isna(start_date): return 0
        days = pd.bdate_range(start=start_date, end=target_date)
        return len(days) - 1 if len(days) > 0 else 0

    def draw_gantt_canvas(self, df):
        self.view.header_scene.clear()
        self.view.gantt_scene.clear()

        all_starts = pd.to_datetime(df['ENG START DATE'].replace('', pd.NaT)).combine_first(
            pd.to_datetime(df['EST START DATE'].replace('', pd.NaT)))
        day_zero = all_starts.min() if not all_starts.isna().all() else pd.Timestamp.today().normalize()
        day_zero = day_zero - pd.Timedelta(days=day_zero.weekday())

        total_business_days = 120
        total_width = total_business_days * self.day_width
        total_height = max(len(df) * self.row_height, 800)  # Ensures lines draw all the way down

        self.view.header_scene.setSceneRect(0, 0, total_width, 45)
        self.view.gantt_scene.setSceneRect(0, 0, total_width, total_height)

        font_month = QFont("Segoe UI", 9, QFont.Bold)
        font_day = QFont("Segoe UI", 8)

        current_x = 0
        current_month = -1

        today = pd.Timestamp.today().normalize()
        today_x = -1

        for i in range(total_business_days):
            current_date = day_zero + pd.tseries.offsets.BusinessDay(i)

            # HIGHLIGHT TODAY!
            if current_date == today:
                h_highlight = self.view.header_scene.addRect(current_x, 0, self.day_width, 45, QPen(Qt.NoPen),
                                                             QColor(255, 255, 255, 15))
                h_highlight.setZValue(-1)

                g_highlight = self.view.gantt_scene.addRect(current_x, 0, self.day_width, total_height, QPen(Qt.NoPen),
                                                            QColor(255, 255, 255, 15))
                g_highlight.setZValue(-1)
                today_x = current_x

            if current_date.month != current_month:
                current_month = current_date.month
                m_text = self.view.header_scene.addText(current_date.strftime("%B %Y"))
                m_text.setDefaultTextColor(QColor("#CCCCCC"))
                m_text.setFont(font_month)
                m_text.setPos(current_x + 2, 0)

            if current_date.weekday() == 0:
                week_pen = QPen(QColor("#666666"), 2)
                self.view.header_scene.addLine(current_x, 25, current_x, 45, week_pen)
                self.view.gantt_scene.addLine(current_x, 0, current_x, total_height, week_pen)
            else:
                dot_pen = QPen(QColor("#3E3E42"))
                dot_pen.setStyle(Qt.DotLine)
                self.view.gantt_scene.addLine(current_x, 0, current_x, total_height, dot_pen)

            d_text = self.view.header_scene.addText(str(current_date.day))
            d_text.setDefaultTextColor(QColor("#888888"))
            d_text.setFont(font_day)
            d_text.setPos(current_x + 2, 20)

            current_x += self.day_width

        for index, row in df.iterrows():
            y = index * self.row_height
            self.view.gantt_scene.addLine(0, y + self.row_height, current_x, y + self.row_height,
                                          QPen(QColor("#252526")))

            raw_start = str(row.get('ENG START DATE', '')).strip()
            est_start = str(row.get('EST START DATE', '')).strip()
            start_str = raw_start if raw_start else est_start
            start_dt = pd.to_datetime(start_str) if start_str else pd.NaT

            est_days_str = str(row.get('EST DAYS', '')).strip()
            days = float(est_days_str) if est_days_str else 3
            width = days * self.day_width

            if pd.notna(start_dt):
                offset = self.get_business_day_offset(day_zero, start_dt)
                x = offset * self.day_width
                block = GanttBlock(row.to_dict(), x, y + 4, width, self.row_height - 8)
                self.view.gantt_scene.addItem(block)

        # SCROLL TO TODAY (Only on initial launch!)
        if not self.initial_scroll_done and today_x >= 0:
            # TWEAK: Calculate exactly how far into the week we are and step back to Monday
            days_from_monday = today.weekday()
            monday_x = today_x - (days_from_monday * self.day_width)

            # Step back 1 more day (25px) as a visual padding buffer
            scroll_x = max(0, monday_x - self.day_width)

            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.view.gantt_view.horizontalScrollBar().setValue(scroll_x))
            self.initial_scroll_done = True


    def populate_kpi_inspector(self, data):
        self.view.inp_smart_id.setText(str(data.get('SMART_ID', '')))
        project_name = str(data.get('PROJECT NAME', 'Unknown'))
        self.view.kpi_title.setText(f"Job: {project_name[:15]}...")
        self.view.kpi_req.setText(str(data.get('REQUIRMENT', '--')))
        self.view.inp_assignee.setText(str(data.get('ASSIGNED TO', '')))
        self.view.inp_est_days.setText(str(data.get('EST DAYS', '')))
        self.view.kpi_eng_due.setText(str(data.get('ENG DUE DATE', '--')))
        self.view.kpi_esd.setText(str(data.get('ESD', '--')))
        self.view.kpi_eng_var.setText(str(data.get('EST ENG VARIANCE', '--')))
        self.view.kpi_esd_var.setText(str(data.get('EST ESD VARIANCE', '--')))

    def clear_all_selections(self):
        """Called when clicking the empty background of the Gantt chart."""
        self.view.info_table.blockSignals(True)
        self.view.info_table.clearSelection()
        self.view.info_table.blockSignals(False)

        self.view.gantt_scene.blockSignals(True)
        self.view.gantt_scene.clearSelection()
        self.view.gantt_scene.blockSignals(False)

        self.view.kpi_panel.hide()

    def handle_block_selection(self):
        selected_items = self.view.gantt_scene.selectedItems()
        if not selected_items:
            self.view.kpi_panel.hide()
            return

        self.view.info_table.blockSignals(True)
        self.view.info_table.clearSelection()
        self.view.info_table.blockSignals(False)

        self.populate_kpi_inspector(selected_items[0].data)
        self.view.kpi_panel.show()

    def handle_table_selection(self):
        selected_rows = self.view.info_table.selectionModel().selectedRows()
        if not selected_rows or self.current_plan_df.empty:
            self.view.kpi_panel.hide()
            return

        self.view.gantt_scene.blockSignals(True)
        self.view.gantt_scene.clearSelection()
        self.view.gantt_scene.blockSignals(False)

        row_idx = selected_rows[0].row()
        row_data = self.current_plan_df.iloc[row_idx].to_dict()
        self.populate_kpi_inspector(row_data)
        self.view.kpi_panel.show()

    def handle_sync(self):
        self.view.sync_btn.setText("Syncing Data...")
        self.view.sync_btn.setEnabled(False)
        QGuiApplication.processEvents()
        success, error_msg = self.model.sync_from_excel(self.excel_path)
        if not success:
            self.view.show_warning("Sync Error", f"Could not sync data:\n\n{error_msg}")
        else:
            self.refresh_tables()
        self.view.sync_btn.setText("Sync Workload")
        self.view.sync_btn.setEnabled(True)

    def handle_save_edit(self):
        smart_id = self.view.inp_smart_id.text()
        assignee = self.view.inp_assignee.text()
        est_days = self.view.inp_est_days.text()

        current_start_date = ""
        if not self.current_plan_df.empty:
            match = self.current_plan_df[self.current_plan_df['SMART_ID'] == smart_id]
            if not match.empty:
                current_start_date = match.iloc[0]['EST START DATE']

        self.model.update_job_details(smart_id, assignee, est_days, current_start_date)
        self.refresh_tables()