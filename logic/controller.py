import json
import os

import pandas as pd
import numpy as np
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
            raw_df = self.model.get_raw_df()
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
        self.current_visual_rows = []  # NEW: Tracks the hierarchy for rendering
        self.expanded_projects = set()  # NEW: Remembers which parents are open

        self.initial_scroll_done = False
        self.last_hovered_block = None
        self.refresh_worker = None

        self.setup_shortcuts()
        self.refresh_tables()

        if hasattr(self.view, 'nav_sync_btn'):
            self.view.nav_sync_btn.clicked.connect(self.handle_sync)

        self.view.filter_req.currentTextChanged.connect(lambda text: self.refresh_tables(maintain_state=False))
        self.view.filter_status.currentTextChanged.connect(lambda text: self.refresh_tables(maintain_state=False))

        self.view.gantt_scene.selectionChanged.connect(self.handle_block_selection)
        self.view.info_table.itemSelectionChanged.connect(self.handle_table_selection)
        self.view.gantt_view.empty_clicked.connect(self.clear_all_selections)

        # NEW: Double clicking the left table expands/collapses the order!
        self.view.info_table.cellDoubleClicked.connect(self.handle_table_double_click)

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
            if hasattr(self.view, 'show_status'):
                self.view.show_status("Undo successful. Press Ctrl+S to save.", 3000)

    def handle_redo(self):
        if self.history.redo():
            self.refresh_tables(maintain_state=True)
            if hasattr(self.view, 'show_status'):
                self.view.show_status("Redo successful. Press Ctrl+S to save.", 3000)

    def handle_global_save(self):
        if self.history.has_changes():
            self.model.commit_overrides(self.history.get_staged_edits())
            self.history.clear()
            self.refresh_tables(maintain_state=True)
            if hasattr(self.view, 'show_status'):
                self.view.show_status("All changes saved successfully.", 4000)
        else:
            if hasattr(self.view, 'show_status'):
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

    def update_dynamic_dropdowns(self, df):
        if df.empty: return

        current_req = self.view.filter_req.currentText()
        unique_reqs = ["All Reqs"] + sorted([str(x) for x in df['REQUIREMENT'].replace('', 'Uncategorized').unique() if
                                             str(x).strip() and str(x).strip() != 'Uncategorized'])
        self.view.filter_req.blockSignals(True)
        self.view.filter_req.clear()
        self.view.filter_req.addItems(unique_reqs)
        if current_req in unique_reqs: self.view.filter_req.setCurrentText(current_req)
        self.view.filter_req.blockSignals(False)

        current_assignee = self.view.inp_assignee.currentText()
        unique_assignees = ["Unassigned"] + sorted([str(x) for x in df['ASSIGNED TO'].unique() if str(x).strip()])
        self.view.inp_assignee.blockSignals(True)
        self.view.inp_assignee.clear()
        self.view.inp_assignee.addItems(unique_assignees)
        if current_assignee in unique_assignees: self.view.inp_assignee.setCurrentText(current_assignee)
        self.view.inp_assignee.blockSignals(False)

    # =========================================================================
    # NEW: CORE HIERARCHY BUILDER
    # =========================================================================
    def build_visual_hierarchy(self, df):
        """Flattens the grouped data based on expansion state."""
        visual_rows = []
        if df.empty: return visual_rows

        grouped = df.groupby('PROJECT_ID', sort=False)

        for project_id, group in grouped:
            # 1. Calculate Parent bounds from children
            starts = pd.to_datetime(group['ENG START DATE'].replace('', pd.NaT)).combine_first(
                pd.to_datetime(group['EST START DATE'].replace('', pd.NaT)))
            ends = pd.to_datetime(group['EST END DATE'].replace('', pd.NaT)).combine_first(
                pd.to_datetime(group['COMPLETE DATE'].replace('', pd.NaT)))

            min_start = starts.min() if not starts.isna().all() else pd.NaT
            max_end = ends.max() if not ends.isna().all() else pd.NaT

            # Simple business days calculation for parent bar
            parent_days = 5
            if pd.notna(min_start) and pd.notna(max_end):
                days = np.busday_count(min_start.date(), max_end.date())
                parent_days = max(1, int(days))

            # Grab shared project info from the first line
            first_row = group.iloc[0]

            # Check status (If all complete, parent is complete)
            all_complete = all(group['STATUS'].str.strip().str.upper() == 'COMPLETE')
            parent_status = 'COMPLETE' if all_complete else 'ACTIVE'

            # Identify multiple assignees or reqs
            reqs = group['REQUIREMENT'].unique()
            req_label = reqs[0] if len(reqs) == 1 else "Multiple"

            parent_row = {
                'IS_PARENT': True,
                'PROJECT_ID': project_id,
                'SMART_ID': project_id,  # Fallback ID
                'REQUIREMENT': req_label,
                'QUOTE NO': first_row.get('QUOTE NO', ''),
                'PROJECT NAME': first_row.get('PROJECT NAME', ''),
                'STATUS': parent_status,
                'EST START DATE': min_start.strftime('%m/%d/%Y') if pd.notna(min_start) else "",
                'EST END DATE': max_end.strftime('%m/%d/%Y') if pd.notna(max_end) else "",
                'EST DAYS': str(parent_days),
                'ESD': first_row.get('ESD', '')  # Usually shared across project
            }
            visual_rows.append(parent_row)

            # 2. Append children if expanded
            if project_id in self.expanded_projects:
                for idx, row in group.iterrows():
                    child_row = row.to_dict()
                    child_row['IS_PARENT'] = False
                    visual_rows.append(child_row)

        return visual_rows

    def on_data_refreshed(self, raw_df, plan_df, full_dashboard_df):
        if hasattr(self.view, 'display_dataframe') and hasattr(self.view, 'raw_table'):
            self.view.display_dataframe(self.view.raw_table, raw_df)

        if full_dashboard_df.empty: return
        self.update_dynamic_dropdowns(full_dashboard_df)

        if plan_df.empty: return
        self.current_plan_df = plan_df

        # Build our new visual rows
        self.current_visual_rows = self.build_visual_hierarchy(plan_df)

        self.view.info_table.blockSignals(True)
        self.populate_left_table(self.current_visual_rows)
        self.view.info_table.blockSignals(False)

        self.draw_gantt_canvas(self.current_visual_rows)

        if hasattr(self.view, 'dash_screen'):
            self.view.dash_screen.update_dashboard(full_dashboard_df)

        if self.is_maintaining_state and self.selected_id_to_restore:
            self.restore_selection(self.selected_id_to_restore)
        else:
            self.view.kpi_panel.hide()

    def handle_table_double_click(self, row, col):
        """Toggles the expansion state of a parent order instantly."""
        if row < len(self.current_visual_rows):
            row_data = self.current_visual_rows[row]
            if row_data.get('IS_PARENT', False):
                project_id = row_data['PROJECT_ID']

                # Toggle the state
                if project_id in self.expanded_projects:
                    self.expanded_projects.remove(project_id)
                else:
                    self.expanded_projects.add(project_id)

                # FAST REDRAW: Bypass the DB and use the data already in memory
                if not self.current_plan_df.empty:
                    self.current_visual_rows = self.build_visual_hierarchy(self.current_plan_df)

                    self.view.info_table.blockSignals(True)
                    self.populate_left_table(self.current_visual_rows)
                    self.view.info_table.blockSignals(False)

                    self.draw_gantt_canvas(self.current_visual_rows)

    def restore_selection(self, target_id):
        try:
            # Find row in visual hierarchy
            row_idx = next(i for i, r in enumerate(self.current_visual_rows) if
                           r.get('SMART_ID') == target_id or r.get('PROJECT_ID') == target_id)
            self.view.info_table.blockSignals(True)
            self.view.info_table.selectRow(row_idx)
            self.view.info_table.blockSignals(False)
        except StopIteration:
            pass

        self.view.gantt_scene.blockSignals(True)
        for item in self.view.gantt_scene.items():
            if isinstance(item, GanttBlock):
                if (item.is_parent and item.data.get('PROJECT_ID') == target_id) or \
                        (not item.is_parent and item.data.get('SMART_ID') == target_id):
                    item.setSelected(True)
                    break
        self.view.gantt_scene.blockSignals(False)
        self.view.kpi_panel.show()

    def populate_left_table(self, visual_rows):
        table = self.view.info_table
        table.setRowCount(len(visual_rows))

        font_parent = QFont("Segoe UI", 9, QFont.Bold)
        font_child = QFont("Segoe UI", 9)

        for row_idx, row in enumerate(visual_rows):
            is_parent = row.get('IS_PARENT', False)
            prefix = "▼ " if is_parent and row.get(
                'PROJECT_ID') in self.expanded_projects else "▶ " if is_parent else "    "

            items = [
                QTableWidgetItem(f"{prefix}{str(row.get('REQUIREMENT', ''))}"),
                QTableWidgetItem(str(row.get('QUOTE NO', ''))),
                QTableWidgetItem(str(row.get('PROJECT NAME', ''))),
                QTableWidgetItem(str(row.get('ESD', ''))),
                QTableWidgetItem(str(row.get('STATUS', '')))
            ]

            for col, item in enumerate(items):
                item.setFont(font_parent if is_parent else font_child)
                # The green text override has been removed from here!
                table.setItem(row_idx, col, item)

        table.resizeColumnsToContents()

    def get_business_day_offset(self, start_date, target_date):
        if pd.isna(target_date) or pd.isna(start_date): return 0
        days = pd.bdate_range(start=start_date, end=target_date)
        return len(days) - 1 if len(days) > 0 else 0

    def draw_gantt_canvas(self, visual_rows):
        self.view.header_scene.clear()
        self.view.gantt_scene.clear()

        if not visual_rows: return

        # Find day zero for canvas bounds
        all_starts = [r.get('ENG START DATE') or r.get('EST START DATE') for r in visual_rows if
                      r.get('ENG START DATE') or r.get('EST START DATE')]
        if all_starts:
            start_series = pd.to_datetime(all_starts)
            day_zero = start_series.min()
        else:
            day_zero = pd.Timestamp.today().normalize()

        day_zero = day_zero - pd.Timedelta(days=day_zero.weekday())
        self.day_zero = day_zero

        total_business_days = 120
        total_width = total_business_days * self.day_width
        total_height = max(len(visual_rows) * self.row_height, 800)

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

        # We pass our dynamically captured assignees to the blocks
        dynamic_engineers = [self.view.inp_assignee.itemText(i) for i in range(self.view.inp_assignee.count())]

        for index, row in enumerate(visual_rows):
            y = index * self.row_height
            is_parent = row.get('IS_PARENT', False)

            start_str = str(row.get('ENG START DATE') or row.get('EST START DATE')).strip()
            est_days_str = str(row.get('EST DAYS', '')).strip()

            days = float(est_days_str) if est_days_str else 5
            start_dt = pd.to_datetime(start_str) if start_str else pd.NaT

            width = days * self.day_width
            x = self.get_business_day_offset(day_zero, start_dt) * self.day_width if pd.notna(start_dt) else 0

            block = GanttBlock(
                project_data=row,
                x=x, y=y + 4, width=width, height=self.row_height - 8,
                day_width=self.day_width,
                dynamic_engineers=dynamic_engineers,
                is_parent=is_parent
            )
            block.block_dropped.connect(self.handle_block_dropped)
            block.assignee_changed.connect(self.handle_right_click_assign)
            self.view.gantt_scene.addItem(block)

            # Draw Due Date Markers only for children
            if not is_parent:
                due_dt = pd.to_datetime(row.get('ENG DUE DATE', '')) if str(row.get('ENG DUE DATE', '')) else pd.NaT
                if pd.notna(due_dt):
                    due_offset = self.get_business_day_offset(day_zero, due_dt)
                    due_x = due_offset * self.day_width
                    if due_x >= 0:
                        self.view.gantt_scene.addItem(DueDateMarker(due_x, y, self.row_height))

        if not self.initial_scroll_done and today_x >= 0:
            scroll_x = max(0, today_x - (today.weekday() * self.day_width) - self.day_width)
            QTimer.singleShot(0, lambda: self.view.gantt_view.horizontalScrollBar().setValue(scroll_x))
            self.initial_scroll_done = True

    def handle_right_click_assign(self, target_id, new_assignee):
        # We only assign children, so target_id is SMART_ID
        self.history.stage_edit(target_id, {'MAN_ASSIGNED': new_assignee})
        self.refresh_tables(maintain_state=True)
        if hasattr(self.view, 'show_status'):
            self.view.show_status("Assignee updated. Press Ctrl+S to save.", 3000)

    def handle_block_dropped(self, target_id, new_x, new_width, is_parent):
        if is_parent: return  # For now, we only allow dragging child lines

        new_date = self.day_zero + pd.tseries.offsets.BusinessDay(int(new_x / self.day_width))
        self.history.stage_edit(target_id, {
            'MAN_START_DATE': f"{new_date.month}/{new_date.day}/{new_date.year}",
            'MAN_EST_DAYS': str(int(new_width / self.day_width))
        })
        self.refresh_tables(maintain_state=True)
        if hasattr(self.view, 'show_status'):
            self.view.show_status("Schedule adjusted. Press Ctrl+S to save.", 3000)

    def populate_kpi_inspector(self, data):
        self.view.inp_smart_id.setText(str(data.get('SMART_ID', '')))

        is_parent = data.get('IS_PARENT', False)
        prefix = "Order: " if is_parent else "Line: "

        self.view.kpi_title.setText(f"{prefix}{str(data.get('PROJECT NAME', 'Unknown'))[:15]}...")
        self.view.kpi_order.setText(str(data.get('PROJECT_ID', '--')))
        self.view.kpi_quote.setText(str(data.get('QUOTE NO', '--')))
        self.view.kpi_req.setText(str(data.get('REQUIREMENT', '--')))

        assignee = str(data.get('ASSIGNED TO', '')).strip()
        self.view.inp_assignee.blockSignals(True)
        self.view.inp_assignee.setCurrentText(assignee)
        self.view.inp_assignee.setEnabled(not is_parent)  # Disable changing assignee for whole orders
        self.view.inp_assignee.blockSignals(False)

        self.view.inp_est_days.blockSignals(True)
        self.view.inp_est_days.setText(str(data.get('EST DAYS', '')))
        self.view.inp_est_days.setEnabled(not is_parent)  # Disable changing days for whole orders
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
        if not selected or not self.current_visual_rows:
            self.view.kpi_panel.hide()
            return

        self.view.gantt_scene.blockSignals(True)
        self.view.gantt_scene.clearSelection()
        self.view.gantt_scene.blockSignals(False)

        row_idx = selected[0].row()
        if row_idx < len(self.current_visual_rows):
            self.populate_kpi_inspector(self.current_visual_rows[row_idx])
            self.view.kpi_panel.show()

    def handle_sync(self):
        if not self.excel_path or not os.path.exists(self.excel_path):
            self.excel_path = self.prompt_for_excel()

        if not self.excel_path or not os.path.exists(self.excel_path):
            if hasattr(self.view, 'show_warning'):
                self.view.show_warning("Sync Aborted", "No valid Excel file was selected.")
            return

        if hasattr(self.view, 'nav_sync_btn'):
            self.view.nav_sync_btn.setEnabled(False)

        if hasattr(self.view, 'show_status'):
            self.view.show_status("Syncing workload data from Excel...", 0)

        self.sync_worker = SyncWorker(self.model, self.excel_path)
        self.sync_worker.finished.connect(self.on_sync_finished)
        self.sync_worker.start()

    def on_sync_finished(self, success, error_msg):
        if hasattr(self.view, 'nav_sync_btn'):
            self.view.nav_sync_btn.setEnabled(True)

        if not success:
            if hasattr(self.view, 'show_status'): self.view.show_status("Sync failed.", 5000)
            if hasattr(self.view, 'show_warning'): self.view.show_warning("Sync Error",
                                                                          f"Could not sync data:\n\n{error_msg}")
        else:
            if hasattr(self.view, 'show_status'): self.view.show_status("Sync complete!", 4000)
            self.refresh_tables(maintain_state=False)

    def handle_stage_edit(self):
        smart_id = self.view.inp_smart_id.text()
        assignee = self.view.inp_assignee.currentText()
        est_days = self.view.inp_est_days.text()

        self.history.stage_edit(smart_id, {'MAN_ASSIGNED': assignee, 'MAN_EST_DAYS': est_days})
        self.refresh_tables(maintain_state=True)
        if hasattr(self.view, 'show_status'):
            self.view.show_status("Edit staged. Press Ctrl+S to save.", 3000)