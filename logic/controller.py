import json
import os

import pandas as pd
from PySide6.QtCore import Qt, QTimer, QThread, Signal
from PySide6.QtGui import QPen, QColor, QFont, QShortcut, QKeySequence
from PySide6.QtWidgets import QTableWidgetItem, QFileDialog

from logic.history import HistoryManager
from ui.gantt_components import GanttBlock, DueDateMarker


class SyncWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, model, excel_path):
        super().__init__()
        self.model = model
        self.excel_path = excel_path

    def run(self):
        success, error_msg = self.model.sync_from_excel(self.excel_path)
        self.finished.emit(success, error_msg)


class DataRefreshWorker(QThread):
    data_ready = Signal(object, object, object)

    def __init__(self, model, staged_edits, req_filter, status_filter, maintain_ids):
        super().__init__()
        self.model = model
        self.staged_edits = staged_edits
        self.req_filter = req_filter
        self.status_filter = status_filter
        self.maintain_ids = maintain_ids

    def run(self):
        try:
            raw_df = self.model._get_raw_df()
            plan_df = self.model.get_application_data(self.staged_edits)

            if plan_df.empty:
                self.data_ready.emit(raw_df, plan_df, plan_df)
                return

            full_dashboard_df = plan_df.copy()

            if self.req_filter != "All Reqs":
                plan_df = plan_df[plan_df['REQUIREMENT'].str.contains(self.req_filter, case=False, na=False)]

            if self.status_filter == "Active":
                plan_df = plan_df[plan_df['STATUS'].str.strip().str.upper() != 'COMPLETE']
            elif self.status_filter == "Complete":
                plan_df = plan_df[plan_df['STATUS'].str.strip().str.upper() == 'COMPLETE']

            if self.maintain_ids is not None:
                current_ids = self.maintain_ids
                plan_df = plan_df.set_index('SMART_ID')
                valid_ids = [uid for uid in current_ids if uid in plan_df.index]
                new_ids = [uid for uid in plan_df.index if uid not in current_ids]
                plan_df = plan_df.loc[valid_ids + new_ids].reset_index()
            else:
                plan_df['SORT_DATE'] = pd.to_datetime(plan_df['ENG START DATE'].replace('', pd.NaT)).combine_first(
                    pd.to_datetime(plan_df['EST START DATE'].replace('', pd.NaT))).combine_first(
                    pd.to_datetime(plan_df['ENG DUE DATE'].replace('', pd.NaT)))

                plan_df = plan_df.sort_values(by=['STATUS', 'SORT_DATE'], ascending=[True, True])
                plan_df = plan_df.drop(columns=['SORT_DATE'])

            self.data_ready.emit(raw_df, plan_df.reset_index(drop=True), full_dashboard_df)

        except Exception as e:
            import traceback
            print(f"Worker Error: {e}\n{traceback.format_exc()}")


class AppController:
    def __init__(self, view, model):
        self.view = view
        self.model = model
        self.history = HistoryManager()

        self.config_file = "app_config.json"
        self.excel_path = self.load_excel_path()

        self.day_width = 25
        self.row_height = 36
        self.current_plan_df = pd.DataFrame()
        self.initial_scroll_done = False
        self.last_hovered_block = None

        self.refresh_worker = None

        self.setup_shortcuts()
        self.refresh_tables()

        # Wire up the new Sidebar Sync button!
        self.view.nav_sync_btn.clicked.connect(self.handle_sync)

        self.view.filter_req.currentTextChanged.connect(lambda text: self.refresh_tables(maintain_state=False))
        self.view.filter_status.currentTextChanged.connect(lambda text: self.refresh_tables(maintain_state=False))

        self.view.gantt_scene.selectionChanged.connect(self.handle_block_selection)
        self.view.info_table.itemSelectionChanged.connect(self.handle_table_selection)
        self.view.gantt_view.empty_clicked.connect(self.clear_all_selections)

        self.view.inp_est_days.editingFinished.connect(self.handle_stage_edit)
        self.view.inp_assignee.activated.connect(self.handle_stage_edit)

    def load_excel_path(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                path = config.get('excel_path', '')
                if os.path.exists(path): return path
        return self.prompt_for_excel()

    def prompt_for_excel(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self.view, "Select Engineering Workload Excel File", "", "Excel Files (*.xlsx *.xls)"
        )
        if file_path:
            with open(self.config_file, 'w') as f: json.dump({'excel_path': file_path}, f)
            return file_path
        return ""

    def setup_shortcuts(self):
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self.view)
        self.shortcut_undo.activated.connect(self.handle_undo)
        self.shortcut_redo = QShortcut(QKeySequence("Ctrl+Y"), self.view)
        self.shortcut_redo.activated.connect(self.handle_redo)
        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self.view)
        self.shortcut_save.activated.connect(self.handle_global_save)

    def handle_undo(self):
        if self.history.undo():
            self.refresh_tables(maintain_state=True)
            self.view.show_status("Undo successful. Press Ctrl+S to save.", 3000)

    def handle_redo(self):
        if self.history.redo():
            self.refresh_tables(maintain_state=True)
            self.view.show_status("Redo successful. Press Ctrl+S to save.", 3000)

    def handle_global_save(self):
        if self.history.has_changes():
            self.model.commit_overrides(self.history.get_staged_edits())
            self.history.clear()
            self.refresh_tables(maintain_state=True)
            self.view.show_status("All changes saved successfully.", 4000)
        else:
            self.view.show_status("No unsaved changes.", 3000)

    def refresh_tables(self, maintain_state=False):
        self.selected_id_to_restore = self.view.inp_smart_id.text() if maintain_state and not self.view.kpi_panel.isHidden() else None
        self.is_maintaining_state = maintain_state

        req_filter = self.view.filter_req.currentText()
        status_filter = self.view.filter_status.currentText()
        staged_edits = self.history.get_staged_edits()
        maintain_ids = self.current_plan_df[
            'SMART_ID'].tolist() if maintain_state and not self.current_plan_df.empty else None

        if self.refresh_worker and self.refresh_worker.isRunning():
            self.refresh_worker.data_ready.disconnect()

        self.refresh_worker = DataRefreshWorker(self.model, staged_edits, req_filter, status_filter, maintain_ids)
        self.refresh_worker.data_ready.connect(self.on_data_refreshed)
        self.refresh_worker.start()

    def on_data_refreshed(self, raw_df, plan_df, full_dashboard_df):
        self.view.display_dataframe(self.view.raw_table, raw_df)
        if plan_df.empty: return
        self.current_plan_df = plan_df

        self.view.info_table.blockSignals(True)
        self.populate_left_table(self.current_plan_df)
        self.view.info_table.blockSignals(False)

        self.draw_gantt_canvas(self.current_plan_df)
        self.view.dash_screen.update_dashboard(full_dashboard_df)

        if self.is_maintaining_state and self.selected_id_to_restore:
            self.restore_selection(self.selected_id_to_restore)
        else:
            self.view.kpi_panel.hide()

    def restore_selection(self, smart_id):
        try:
            row_idx = self.current_plan_df[self.current_plan_df['SMART_ID'] == smart_id].index[0]
            self.view.info_table.blockSignals(True)
            self.view.info_table.selectRow(row_idx)
            self.view.info_table.blockSignals(False)
        except IndexError:
            pass

        self.view.gantt_scene.blockSignals(True)
        for item in self.view.gantt_scene.items():
            if isinstance(item, GanttBlock) and item.data.get('SMART_ID') == smart_id:
                item.setSelected(True)
                break
        self.view.gantt_scene.blockSignals(False)
        self.view.kpi_panel.show()

    def populate_left_table(self, df):
        table = self.view.info_table
        table.setRowCount(df.shape[0])
        for row_idx, row in df.iterrows():
            table.setItem(row_idx, 0, QTableWidgetItem(str(row.get('REQUIREMENT', ''))))
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
        self.day_zero = day_zero

        total_business_days = 120
        total_width = total_business_days * self.day_width
        total_height = max(len(df) * self.row_height, 800)

        self.view.header_scene.setSceneRect(0, 0, total_width, 45)
        self.view.gantt_scene.setSceneRect(0, 0, total_width, total_height)

        font_month = QFont("Segoe UI", 9, QFont.Bold)
        font_day = QFont("Segoe UI", 8)
        current_x, current_month, today_x = 0, -1, -1
        today = pd.Timestamp.today().normalize()

        for i in range(total_business_days):
            current_date = day_zero + pd.tseries.offsets.BusinessDay(i)
            if current_date == today:
                self.view.gantt_scene.addRect(current_x, 0, self.day_width, total_height + 2000, QPen(Qt.NoPen),
                                              QColor(255, 255, 255, 25))
                today_x = current_x

            if current_date.month != current_month:
                current_month = current_date.month
                m_text = self.view.header_scene.addText(current_date.strftime("%B %Y"))
                m_text.setDefaultTextColor(QColor("#CCCCCC"))
                m_text.setFont(font_month)
                m_text.setPos(current_x + 2, 0)

            if current_date.weekday() == 0:
                self.view.header_scene.addLine(current_x, 25, current_x, 45, QPen(QColor("#666666"), 2))

            d_text = self.view.header_scene.addText(str(current_date.day))
            d_text.setDefaultTextColor(QColor("#888888"))
            d_text.setFont(font_day)
            d_text.setPos(current_x + 2, 20)
            current_x += self.day_width

        for index, row in df.iterrows():
            y = index * self.row_height
            status = str(row.get('STATUS', '')).strip().upper()
            raw_start = str(row.get('ENG START DATE', '')).strip()
            est_start = str(row.get('EST START DATE', '')).strip()
            comp_date = str(row.get('COMPLETE DATE', '')).strip()
            est_days_str = str(row.get('EST DAYS', '')).strip()

            start_str = raw_start if raw_start else est_start
            if status == 'COMPLETE':
                start_dt = pd.to_datetime(start_str) if start_str else pd.NaT
                end_dt = pd.to_datetime(comp_date) if comp_date else pd.NaT
                if pd.notna(start_dt) and pd.notna(end_dt):
                    days = max(1, self.get_business_day_offset(start_dt, end_dt))
                else:
                    days = 1
            else:
                days = float(est_days_str) if est_days_str else 5

            start_dt = pd.to_datetime(start_str) if start_str else pd.NaT
            due_dt = pd.to_datetime(row.get('ENG DUE DATE', '')) if str(row.get('ENG DUE DATE', '')) else pd.NaT

            width = days * self.day_width
            x = self.get_business_day_offset(day_zero, start_dt) * self.day_width if pd.notna(start_dt) else 0

            block = GanttBlock(row.to_dict(), x, y + 4, width, self.row_height - 8, self.day_width)
            block.block_dropped.connect(self.handle_block_dropped)
            block.assignee_changed.connect(self.handle_right_click_assign)
            self.view.gantt_scene.addItem(block)

            if pd.notna(due_dt):
                due_offset = self.get_business_day_offset(day_zero, due_dt)
                due_x = due_offset * self.day_width
                if due_x >= 0:
                    self.view.gantt_scene.addItem(DueDateMarker(due_x, y, self.row_height))

        if not self.initial_scroll_done and today_x >= 0:
            scroll_x = max(0, today_x - (today.weekday() * self.day_width) - self.day_width)
            QTimer.singleShot(0, lambda: self.view.gantt_view.horizontalScrollBar().setValue(scroll_x))
            self.initial_scroll_done = True

    def handle_right_click_assign(self, smart_id, new_assignee):
        self.history.stage_edit(smart_id, {'MAN_ASSIGNED': new_assignee})
        self.refresh_tables(maintain_state=True)
        self.view.show_status("Assignee updated. Press Ctrl+S to save.", 3000)

    def handle_block_dropped(self, smart_id, new_x, new_width):
        new_date = self.day_zero + pd.tseries.offsets.BusinessDay(int(new_x / self.day_width))
        self.history.stage_edit(smart_id, {'MAN_START_DATE': f"{new_date.month}/{new_date.day}/{new_date.year}",
                                           'MAN_EST_DAYS': str(int(new_width / self.day_width))})
        self.refresh_tables(maintain_state=True)
        self.view.show_status("Schedule adjusted. Press Ctrl+S to save.", 3000)

    def populate_kpi_inspector(self, data):
        self.view.inp_smart_id.setText(str(data.get('SMART_ID', '')))
        self.view.kpi_title.setText(f"Job: {str(data.get('PROJECT NAME', 'Unknown'))[:15]}...")
        self.view.kpi_order.setText(str(data.get('ORDER NUMBER', '--')))
        self.view.kpi_quote.setText(str(data.get('QUOTE NO', '--')))
        self.view.kpi_req.setText(str(data.get('REQUIREMENT', '--')))

        assignee = str(data.get('ASSIGNED TO', '')).strip()
        self.view.inp_assignee.blockSignals(True)
        self.view.inp_assignee.setCurrentText(assignee)
        self.view.inp_assignee.blockSignals(False)

        self.view.inp_est_days.blockSignals(True)
        self.view.inp_est_days.setText(str(data.get('EST DAYS', '')))
        self.view.inp_est_days.blockSignals(False)

        self.view.kpi_eng_due.setText(str(data.get('ENG DUE DATE', '--')))
        self.view.kpi_esd.setText(str(data.get('ESD', '--')))
        self.view.kpi_eng_var.setText(str(data.get('EST ENG VARIANCE', '--')))
        self.view.kpi_esd_var.setText(str(data.get('EST ESD VARIANCE', '--')))

    def clear_all_selections(self):
        self.view.info_table.blockSignals(True)
        self.view.info_table.clearSelection()
        self.view.info_table.blockSignals(False)
        self.view.gantt_scene.blockSignals(True)
        self.view.gantt_scene.clearSelection()
        self.view.gantt_scene.blockSignals(False)
        self.view.kpi_panel.hide()

    def handle_block_selection(self):
        selected = self.view.gantt_scene.selectedItems()
        if not selected:
            self.view.kpi_panel.hide()
            return
        self.view.info_table.blockSignals(True)
        self.view.info_table.clearSelection()
        self.view.info_table.blockSignals(False)
        if hasattr(selected[0], 'data'):
            self.populate_kpi_inspector(selected[0].data)
            self.view.kpi_panel.show()

    def handle_table_selection(self):
        selected = self.view.info_table.selectionModel().selectedRows()
        if not selected or self.current_plan_df.empty:
            self.view.kpi_panel.hide()
            return
        self.view.gantt_scene.blockSignals(True)
        self.view.gantt_scene.clearSelection()
        self.view.gantt_scene.blockSignals(False)
        self.populate_kpi_inspector(self.current_plan_df.iloc[selected[0].row()].to_dict())
        self.view.kpi_panel.show()

    def handle_sync(self):
        if not self.excel_path or not os.path.exists(self.excel_path):
            self.excel_path = self.prompt_for_excel()

        if not self.excel_path or not os.path.exists(self.excel_path):
            self.view.show_warning("Sync Aborted", "No valid Excel file was selected.")
            return

        self.view.nav_sync_btn.setEnabled(False)
        self.view.show_status("Syncing workload data from Excel...", 0)

        self.sync_worker = SyncWorker(self.model, self.excel_path)
        self.sync_worker.finished.connect(self.on_sync_finished)
        self.sync_worker.start()

    def on_sync_finished(self, success, error_msg):
        self.view.nav_sync_btn.setEnabled(True)
        if not success:
            self.view.show_status("Sync failed.", 5000)
            self.view.show_warning("Sync Error", f"Could not sync data:\n\n{error_msg}")
        else:
            self.view.show_status("Sync complete!", 4000)
            self.refresh_tables(maintain_state=False)

    def handle_stage_edit(self):
        smart_id = self.view.inp_smart_id.text()
        assignee = self.view.inp_assignee.currentText()
        est_days = self.view.inp_est_days.text()

        self.history.stage_edit(smart_id, {'MAN_ASSIGNED': assignee, 'MAN_EST_DAYS': est_days})
        self.refresh_tables(maintain_state=True)
        self.view.show_status("Edit staged. Press Ctrl+S to save.", 3000)

    def handle_table_cell_entered(self, row, col):
        if self.last_hovered_block:
            self.last_hovered_block.set_external_hover(False)
            self.last_hovered_block = None

        if not self.current_plan_df.empty and row < len(self.current_plan_df):
            smart_id = self.current_plan_df.iloc[row]['SMART_ID']
            for item in self.view.gantt_scene.items():
                if isinstance(item, GanttBlock) and item.data.get('SMART_ID') == smart_id:
                    item.set_external_hover(True)
                    self.last_hovered_block = item
                    break

    def handle_block_hover_in(self, smart_id):
        if self.current_plan_df.empty: return
        idx = self.current_plan_df.index[self.current_plan_df['SMART_ID'] == smart_id].tolist()
        if idx:
            row = idx[0]
            selected_rows = [r.row() for r in self.view.info_table.selectionModel().selectedRows()]
            if row in selected_rows: return
            for col in range(self.view.info_table.columnCount()):
                item = self.view.info_table.item(row, col)
                if item: item.setBackground(QColor("#3E3E42"))

    def handle_block_hover_out(self, smart_id):
        if self.current_plan_df.empty: return
        idx = self.current_plan_df.index[self.current_plan_df['SMART_ID'] == smart_id].tolist()
        if idx:
            row = idx[0]
            selected_rows = [r.row() for r in self.view.info_table.selectionModel().selectedRows()]
            if row in selected_rows: return
            for col in range(self.view.info_table.columnCount()):
                item = self.view.info_table.item(row, col)
                if item: item.setBackground(QColor(0, 0, 0, 0))