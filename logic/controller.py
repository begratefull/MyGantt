"""
The central nervous system of the MyGantt application.
Responsible for bridging the UI views with the underlying data model,
routing background signals, and managing application state.

Phase 4 Restructuring:
- Fixed QThread C++ destruction crash (0xC0000409) by preventing premature garbage collection.
- Added signal blocking during startup injection to prevent redundant I/O queries.
"""

import json
import os
from typing import Any, Optional, List

import pandas as pd
import numpy as np

from PySide6.QtCore import QTimer
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QFileDialog

from logic.history import HistoryManager
from logic.workers import SyncWorker, DataRefreshWorker
from logic.data_builder import GanttDataBuilder
from ui.components.gantt_components import GanttBlock


class AppController:
    """
    Manages the flow of data between the UI components and the SQLite/Excel backend.
    """
    def __init__(self, view: Any, model: Any) -> None:
        self.view = view
        self.model = model
        self.history = HistoryManager()

        self.config_file = "app_config.json"
        self.excel_path = self.load_excel_path()

        # Shared constants for grid snapping math
        self.day_width = 25
        self.row_height = 36

        self.current_plan_df = pd.DataFrame()
        self.current_visual_rows = []
        self.expanded_projects = set()

        self.initial_scroll_done = False
        self.refresh_worker: Optional[DataRefreshWorker] = None

        # ---> THE FIX: Safely holds running threads so Python doesn't delete them while C++ is executing
        self._old_workers: List[DataRefreshWorker] = []

        self.setup_shortcuts()

        # --- Team Management Signals ---
        self.view.team_screen.save_engineer_requested.connect(self.handle_save_engineer)
        self.view.team_screen.engineer_selected.connect(self.handle_engineer_selected)
        self.refresh_team_view()

        # --- Dashboard & Gantt Filter Signals ---
        if hasattr(self.view, 'dash_screen'):
            self.view.dash_screen.filter_team.currentTextChanged.connect(lambda text: self.refresh_tables(maintain_state=False))

        if hasattr(self.view, 'filter_team'):
            self.view.filter_team.currentTextChanged.connect(lambda text: self.refresh_tables(maintain_state=False))

        self.view.filter_req.currentTextChanged.connect(lambda text: self.refresh_tables(maintain_state=False))
        self.view.filter_status.currentTextChanged.connect(lambda text: self.refresh_tables(maintain_state=False))

        # --- Gantt Interaction Signals ---
        self.view.gantt_scene.selectionChanged.connect(self.handle_block_selection)
        self.view.info_table.itemSelectionChanged.connect(self.handle_table_selection)
        self.view.gantt_view.empty_clicked.connect(self.clear_all_selections)
        self.view.info_table.cellDoubleClicked.connect(self.handle_table_double_click)

        self.view.inp_est_days.editingFinished.connect(self.handle_stage_edit)
        self.view.inp_assignee.activated.connect(self.handle_stage_edit)

        # Connect the newly abstracted canvas interaction signals
        self.view.gantt_screen.block_dropped_signal.connect(self.handle_block_dropped)
        self.view.gantt_screen.assignee_changed_signal.connect(self.handle_right_click_assign)

        # Trigger Initial Load
        self.inject_startup_defaults()

        if hasattr(self.view, 'nav_sync_btn'):
            self.view.nav_sync_btn.clicked.connect(self.handle_sync)

    def inject_startup_defaults(self) -> None:
        """Injects default settings on application launch before the first data pull."""

        # ---> THE FIX: Block signals temporarily so we don't rapid-fire the database!
        if hasattr(self.view, 'dash_screen'):
            self.view.dash_screen.filter_team.blockSignals(True)
            if self.view.dash_screen.filter_team.findText("Custom Team") == -1:
                self.view.dash_screen.filter_team.addItem("Custom Team")
            self.view.dash_screen.filter_team.setCurrentText("Custom Team")
            self.view.dash_screen.filter_team.blockSignals(False)

        if hasattr(self.view, 'filter_team'):
            self.view.filter_team.blockSignals(True)
            if self.view.filter_team.findText("Custom Team") == -1:
                self.view.filter_team.addItem("Custom Team")
            self.view.filter_team.setCurrentText("Custom Team")
            self.view.filter_team.blockSignals(False)

        self.refresh_tables()

    def load_excel_path(self) -> str:
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                path = config.get('excel_path', '')
                if os.path.exists(path):
                    return path
        return self.prompt_for_excel()

    def prompt_for_excel(self) -> str:
        file_path, _ = QFileDialog.getOpenFileName(
            self.view, "Select Engineering Workload Excel File", "", "Excel Files (*.xlsx *.xls)"
        )
        if file_path:
            with open(self.config_file, 'w') as f:
                json.dump({'excel_path': file_path}, f)
            return file_path
        return ""

    def setup_shortcuts(self) -> None:
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self.view)
        self.shortcut_undo.activated.connect(self.handle_undo)

        self.shortcut_redo = QShortcut(QKeySequence("Ctrl+Y"), self.view)
        self.shortcut_redo.activated.connect(self.handle_redo)

        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self.view)
        self.shortcut_save.activated.connect(self.handle_global_save)

    def handle_undo(self) -> None:
        if self.history.undo():
            self.refresh_tables(maintain_state=True)
            if hasattr(self.view, 'show_status'):
                self.view.show_status("Undo successful. Press Ctrl+S to save.", 3000)

    def handle_redo(self) -> None:
        if self.history.redo():
            self.refresh_tables(maintain_state=True)
            if hasattr(self.view, 'show_status'):
                self.view.show_status("Redo successful. Press Ctrl+S to save.", 3000)

    def handle_global_save(self) -> None:
        if self.history.has_changes():
            self.model.commit_overrides(self.history.get_staged_edits())
            self.history.clear()
            self.refresh_tables(maintain_state=True)
            if hasattr(self.view, 'show_status'):
                self.view.show_status("All changes saved successfully.", 4000)
        else:
            if hasattr(self.view, 'show_status'):
                self.view.show_status("No unsaved changes.", 3000)

    def refresh_tables(self, maintain_state: bool = False) -> None:
        """Kicks off the background worker to fetch and process data safely."""
        self.selected_id_to_restore = self.view.inp_smart_id.text() if maintain_state and not self.view.kpi_panel.isHidden() else None
        self.is_maintaining_state = maintain_state

        team_filter = self.view.filter_team.currentText() if hasattr(self.view, 'filter_team') else "All Teams"
        req_filter = self.view.filter_req.currentText()
        status_filter = self.view.filter_status.currentText()
        staged_edits = self.history.get_staged_edits()
        maintain_ids = self.current_plan_df['SMART_ID'].tolist() if maintain_state and not self.current_plan_df.empty else None

        if self.refresh_worker and self.refresh_worker.isRunning():
            self.refresh_worker.data_ready.disconnect()
            # ---> THE FIX: Push to array so it isn't garbage collected while C++ is executing
            self._old_workers.append(self.refresh_worker)

        # Clean up any workers that have safely finished to avoid memory leaks
        self._old_workers = [w for w in self._old_workers if w.isRunning()]

        self.refresh_worker = DataRefreshWorker(self.model, staged_edits, team_filter, req_filter, status_filter, maintain_ids)
        self.refresh_worker.data_ready.connect(self.on_data_refreshed)
        self.refresh_worker.start()

    def update_dynamic_dropdowns(self, df: pd.DataFrame) -> None:
        """Populates UI combo boxes with available filters and configurations."""
        if df.empty:
            return

        # 1. Fetch Configured Teams & Colors
        eng_df = self.model.db.get_engineers_df()
        unique_teams = ["All Teams"]
        team_map = {}
        color_map = {}

        if not eng_df.empty:
            unique_teams += sorted([str(x) for x in eng_df['team_name'].unique() if str(x).strip()])
            team_map = {str(k).strip().upper(): str(v).strip().upper() for k, v in zip(eng_df['name'], eng_df['team_name'])}
            color_map = {str(k).strip().upper(): str(v).strip().upper() for k, v in zip(eng_df['name'], eng_df['hex_color'])}

        # Pass data to Dashboard
        if hasattr(self.view, 'dash_screen'):
            self.view.dash_screen.team_map = team_map
            self.view.dash_screen.color_map = color_map
            dash_combo = self.view.dash_screen.filter_team
            current_dash_team = dash_combo.currentText()

            dash_combo.blockSignals(True)
            dash_combo.clear()
            dash_combo.addItems(unique_teams)
            if current_dash_team in unique_teams:
                dash_combo.setCurrentText(current_dash_team)
            elif "Custom Team" in unique_teams:
                dash_combo.setCurrentText("Custom Team")
            dash_combo.blockSignals(False)

        # Update Gantt Filter
        if hasattr(self.view, 'filter_team'):
            current_team = self.view.filter_team.currentText()
            self.view.filter_team.blockSignals(True)
            self.view.filter_team.clear()
            self.view.filter_team.addItems(unique_teams)
            if current_team in unique_teams:
                self.view.filter_team.setCurrentText(current_team)
            elif "Custom Team" in unique_teams:
                self.view.filter_team.setCurrentText("Custom Team")
            self.view.filter_team.blockSignals(False)

        # 2. Update Requirements Dropdown
        current_req = self.view.filter_req.currentText()
        unique_reqs = ["All Reqs"] + sorted([str(x) for x in df['REQUIREMENT'].replace('', 'Uncategorized').unique() if str(x).strip() and str(x).strip() != 'Uncategorized'])

        self.view.filter_req.blockSignals(True)
        self.view.filter_req.clear()
        self.view.filter_req.addItems(unique_reqs)
        if current_req in unique_reqs:
            self.view.filter_req.setCurrentText(current_req)
        self.view.filter_req.blockSignals(False)

        # 3. Update KPI Assignee Dropdown
        current_assignee = self.view.inp_assignee.currentText()
        unique_assignees = ["Unassigned"] + sorted([str(x) for x in df['ASSIGNED TO'].unique() if str(x).strip()])

        self.view.inp_assignee.blockSignals(True)
        self.view.inp_assignee.clear()
        self.view.inp_assignee.addItems(unique_assignees)
        if current_assignee in unique_assignees:
            self.view.inp_assignee.setCurrentText(current_assignee)
        self.view.inp_assignee.blockSignals(False)

    def is_target_parent(self, target_id: str) -> bool:
        """Helper to determine if an ID belongs to a Parent summary block."""
        for row in self.current_visual_rows:
            if row.get('IS_PARENT') and row.get('PROJECT_ID') == target_id:
                return True
        return False

    def on_data_refreshed(self, raw_df: pd.DataFrame, plan_df: pd.DataFrame, full_dashboard_df: pd.DataFrame) -> None:
        """Receives processed data from the background worker and distributes it to the UI."""
        if hasattr(self.view, 'display_dataframe') and hasattr(self.view, 'raw_table'):
            self.view.display_dataframe(self.view.raw_table, raw_df)

        if full_dashboard_df.empty:
            return

        self.update_dynamic_dropdowns(full_dashboard_df)

        if plan_df.empty:
            return

        self.current_plan_df = plan_df

        # Fetch configured colors for the data builder
        eng_df = self.model.db.get_engineers_df()
        color_map = {str(k).strip().upper(): str(v).strip().upper() for k, v in zip(eng_df['name'], eng_df['hex_color'])} if not eng_df.empty else {}

        # Offload the heavy aggregation math to the DataBuilder
        self.current_visual_rows = GanttDataBuilder.build_visual_hierarchy(
            plan_df, self.expanded_projects, color_map
        )

        # Extract engineers list for context menus
        dynamic_engineers = [self.view.inp_assignee.itemText(i) for i in range(self.view.inp_assignee.count())]

        # Command the View to render itself
        self.view.gantt_screen.render_gantt(self.current_visual_rows, dynamic_engineers, self.expanded_projects)

        if hasattr(self.view, 'dash_screen'):
            self.view.dash_screen.update_dashboard(full_dashboard_df)

        if self.is_maintaining_state and self.selected_id_to_restore:
            self.restore_selection(self.selected_id_to_restore)
        else:
            self.view.kpi_panel.hide()

    def handle_table_double_click(self, row: int, col: int) -> None:
        """Expands or collapses a project grouping when a parent row is double-clicked."""
        if row < len(self.current_visual_rows):
            row_data = self.current_visual_rows[row]
            if row_data.get('IS_PARENT', False):
                project_id = row_data['PROJECT_ID']

                if project_id in self.expanded_projects:
                    self.expanded_projects.remove(project_id)
                else:
                    self.expanded_projects.add(project_id)

                if not self.current_plan_df.empty:
                    eng_df = self.model.db.get_engineers_df()
                    color_map = {str(k).strip().upper(): str(v).strip().upper() for k, v in zip(eng_df['name'], eng_df['hex_color'])} if not eng_df.empty else {}

                    self.current_visual_rows = GanttDataBuilder.build_visual_hierarchy(
                        self.current_plan_df, self.expanded_projects, color_map
                    )

                    dynamic_engineers = [self.view.inp_assignee.itemText(i) for i in range(self.view.inp_assignee.count())]
                    self.view.gantt_screen.render_gantt(self.current_visual_rows, dynamic_engineers, self.expanded_projects)

    def restore_selection(self, target_id: str) -> None:
        """Ensures user selections persist across background refreshes."""
        try:
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

    def clear_all_selections(self) -> None:
        """Deselects items and closes the KPI panel when clicking empty space."""
        self.view.info_table.blockSignals(True)
        self.view.info_table.clearSelection()
        self.view.info_table.blockSignals(False)

        self.view.gantt_scene.blockSignals(True)
        self.view.gantt_scene.clearSelection()
        self.view.gantt_scene.blockSignals(False)

        self.view.kpi_panel.hide()

    def handle_block_selection(self) -> None:
        """Triggers the KPI panel update when a block is clicked on the canvas."""
        selected = self.view.gantt_scene.selectedItems()
        if not selected:
            self.view.kpi_panel.hide()
            return

        self.view.info_table.blockSignals(True)
        self.view.info_table.clearSelection()
        self.view.info_table.blockSignals(False)

        if hasattr(selected[0], 'data'):
            self.view.gantt_screen.populate_kpi_inspector(selected[0].data)
            self.view.kpi_panel.show()

    def handle_table_selection(self) -> None:
        """Triggers the KPI panel update when a row is clicked in the data table."""
        selected = self.view.info_table.selectionModel().selectedRows()
        if not selected or not self.current_visual_rows:
            self.view.kpi_panel.hide()
            return

        self.view.gantt_scene.blockSignals(True)
        self.view.gantt_scene.clearSelection()
        self.view.gantt_scene.blockSignals(False)

        row_idx = selected[0].row()
        if row_idx < len(self.current_visual_rows):
            self.view.gantt_screen.populate_kpi_inspector(self.current_visual_rows[row_idx])
            self.view.kpi_panel.show()

    def handle_sync(self) -> None:
        """Kicks off a full Excel to SQLite database sync in the background."""
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

    def on_sync_finished(self, success: bool, error_msg: str) -> None:
        if hasattr(self.view, 'nav_sync_btn'):
            self.view.nav_sync_btn.setEnabled(True)

        if not success:
            if hasattr(self.view, 'show_status'):
                self.view.show_status("Sync failed.", 5000)
            if hasattr(self.view, 'show_warning'):
                self.view.show_warning("Sync Error", f"Could not sync data:\n\n{error_msg}")
        else:
            if hasattr(self.view, 'show_status'):
                self.view.show_status("Sync complete!", 4000)
            self.refresh_tables(maintain_state=False)

    # ---------------------------------------------------------
    # TEAM MANAGEMENT LOGIC
    # ---------------------------------------------------------

    def refresh_team_view(self) -> None:
        """Fetches DB configurations and populates the Team Roster and Dropdowns."""
        try:
            eng_df = self.model.db.get_engineers_df()
            self.view.team_screen.populate_roster(eng_df)

            raw_df = self.model.get_raw_df()
            if not raw_df.empty and 'RAW_ASSIGNED' in raw_df.columns:
                raw_names = set([str(x).strip().upper() for x in raw_df['RAW_ASSIGNED'].unique() if
                                 str(x).strip().upper() not in ('', 'UNASSIGNED', 'NAN')])
                configured_names = set(
                    [str(x).strip().upper() for x in eng_df['name'].unique()]) if not eng_df.empty else set()

                unconfigured = sorted(list(raw_names - configured_names))

                combo = self.view.team_screen.inp_name
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(unconfigured + sorted(list(configured_names)))
                combo.blockSignals(False)
        except Exception as e:
            print(f"CRITICAL ERROR in refresh_team_view: {e}")
            import traceback
            traceback.print_exc()

    def handle_save_engineer(self, name: str, team: str, color: str) -> None:
        """Saves the team and engineer config to the SQLite database."""
        self.model.db.upsert_team(team, 0.0)
        self.model.db.upsert_engineer(name, team, color)

        if hasattr(self.view, 'show_status'):
            self.view.show_status(f"Saved configuration for {name}.", 3000)

        self.refresh_team_view()

    def handle_engineer_selected(self, engineer_name: str) -> None:
        """Calculates KPIs and extracts Fixture Families for the selected engineer."""
        if self.current_plan_df.empty:
            return

        eng_mask = self.current_plan_df['ASSIGNED TO'].str.strip().str.upper() == engineer_name.strip().upper()
        eng_df = self.current_plan_df[eng_mask]

        if eng_df.empty:
            self.view.team_screen.update_analytics(engineer_name, 0, 0.0, {})
            return

        active_mask = eng_df['STATUS'].str.strip().str.upper() != 'COMPLETE'
        active_df = eng_df[active_mask]
        active_lines = int(active_mask.sum())

        avg_days = 0.0
        if not active_df.empty and 'EST DAYS' in active_df.columns:
            days_numeric = pd.to_numeric(active_df['EST DAYS'], errors='coerce')
            avg_days = float(days_numeric.mean())
            if pd.isna(avg_days):
                avg_days = 0.0

        family_counts = {}
        if not active_df.empty:
            target_col = next((col for col in ['FAMILY', 'CATALOG CODE', 'CATALOG', 'REQUIREMENT'] if col in active_df.columns), None)

            if target_col:
                counts = active_df[target_col].value_counts()
                for family, count in counts.head(7).items():
                    family_str = str(family).strip()
                    if not family_str or family_str.lower() == 'nan':
                        family_str = "Uncategorized"
                    family_counts[family_str] = family_counts.get(family_str, 0) + int(count)

        eng_db_df = self.model.db.get_engineers_df()
        primary_color = "#007ACC"
        if not eng_db_df.empty:
            color_match = eng_db_df[eng_db_df['name'].str.upper() == engineer_name.upper()]
            if not color_match.empty:
                primary_color = color_match.iloc[0].get('hex_color', '#007ACC')

        self.view.team_screen.update_analytics(
            engineer_name=engineer_name,
            active_lines=active_lines,
            avg_days=avg_days,
            family_counts=family_counts,
            primary_color=primary_color
        )

    # ---------------------------------------------------------
    # CANVAS INTERACTION & STAGING LOGIC
    # ---------------------------------------------------------

    def update_kpi_variances_locally(self, start_x: float, est_days_str: str) -> None:
        """Locally recalculates variance metrics in the UI prior to a full save."""
        day_zero = self.view.gantt_screen.day_zero
        if not day_zero:
            return

        start_date = day_zero + pd.tseries.offsets.BusinessDay(int(start_x / self.day_width))
        days = int(est_days_str) if est_days_str.isdigit() else 5
        end_date = start_date + pd.tseries.offsets.BusinessDay(days)

        due_date_str = self.view.kpi_eng_due.text()
        if due_date_str and due_date_str != '--':
            try:
                due_dt = pd.to_datetime(due_date_str)
                var = np.busday_count(end_date.date(), due_dt.date())
                self.view.kpi_eng_var.setText(f"{int(var)} days")
            except Exception:
                pass

        esd_str = self.view.kpi_esd.text()
        if esd_str and esd_str != '--':
            try:
                esd_dt = pd.to_datetime(esd_str)
                var_esd = np.busday_count(end_date.date(), esd_dt.date())
                self.view.kpi_esd_var.setText(f"{int(var_esd)} days")
            except Exception:
                pass

    def handle_block_dropped(self, target_id: str, new_x: float, new_width: float, is_parent: bool, delta_x: float = 0.0) -> None:
        """Handles visual and logical staging when a block is dragged/dropped."""
        day_zero = self.view.gantt_screen.day_zero
        if not day_zero:
            return

        new_date = day_zero + pd.tseries.offsets.BusinessDay(int(new_x / self.day_width))
        new_days_str = str(int(new_width / self.day_width))

        if not is_parent:
            self.history.stage_edit(target_id, {
                'MAN_START_DATE': f"{new_date.month}/{new_date.day}/{new_date.year}",
                'MAN_EST_DAYS': new_days_str
            })
        else:
            for item in self.view.gantt_scene.items():
                if isinstance(item, GanttBlock) and not item.is_parent and item.data.get('PROJECT_ID') == target_id:
                    item.setPos(max(0, item.x() + delta_x), item.y())
                    item.prepareGeometryChange()
                    item.rect.setWidth(new_width)
                    item.update()

                    child_date = day_zero + pd.tseries.offsets.BusinessDay(int(item.x() / self.day_width))
                    self.history.stage_edit(item.data.get('SMART_ID'), {
                        'MAN_START_DATE': f"{child_date.month}/{child_date.day}/{child_date.year}",
                        'MAN_EST_DAYS': new_days_str
                    })

        if self.view.inp_smart_id.text() == target_id or (is_parent and self.view.kpi_order.text() == target_id):
            self.view.inp_est_days.blockSignals(True)
            self.view.inp_est_days.setText(new_days_str)
            self.view.inp_est_days.blockSignals(False)

            self.update_kpi_variances_locally(new_x, new_days_str)

        if hasattr(self.view, 'show_status'):
            self.view.show_status("Unsaved Schedule edit. Press Ctrl+S to Calculate & Save.", 5000)

    def handle_right_click_assign(self, target_id: str, new_assignee: str) -> None:
        """Handles visual and logical staging when an assignee is changed via context menu."""
        if self.is_target_parent(target_id):
            mask = self.current_plan_df['PROJECT_ID'] == target_id
            for child_id in self.current_plan_df[mask]['SMART_ID'].tolist():
                self.history.stage_edit(child_id, {'MAN_ASSIGNED': new_assignee})
        else:
            self.history.stage_edit(target_id, {'MAN_ASSIGNED': new_assignee})

        eng_df = self.model.db.get_engineers_df()
        color_map = {str(k).strip().upper(): str(v).strip().upper() for k, v in zip(eng_df['name'], eng_df['hex_color'])} if not eng_df.empty else {}
        new_color = color_map.get(str(new_assignee).strip().upper(), "#007ACC") if str(new_assignee).strip().upper() not in ["", "UNASSIGNED"] else "#555555"

        for item in self.view.gantt_scene.items():
            if isinstance(item, GanttBlock):
                is_match = (item.data.get('SMART_ID') == target_id) or \
                           (self.is_target_parent(target_id) and item.data.get('PROJECT_ID') == target_id)
                if is_match:
                    item.data['ASSIGNED TO'] = new_assignee
                    item.data['HEX_COLOR'] = new_color
                    item.refresh_visuals()

        if self.view.inp_smart_id.text() == target_id or (self.is_target_parent(target_id) and self.view.kpi_order.text() == target_id):
            self.view.inp_assignee.blockSignals(True)
            self.view.inp_assignee.setCurrentText(new_assignee)
            self.view.inp_assignee.blockSignals(False)

        if hasattr(self.view, 'show_status'):
            self.view.show_status("Unsaved Assignee edit. Press Ctrl+S to Calculate & Save.", 5000)

    def handle_stage_edit(self) -> None:
        """Handles visual and logical staging when KPIs are edited manually via the inspector."""
        smart_id = self.view.inp_smart_id.text()
        assignee = self.view.inp_assignee.currentText()
        est_days_str = self.view.inp_est_days.text()

        updates = {'MAN_ASSIGNED': assignee, 'MAN_EST_DAYS': est_days_str}

        if self.is_target_parent(smart_id):
            mask = self.current_plan_df['PROJECT_ID'] == smart_id
            for child_id in self.current_plan_df[mask]['SMART_ID'].tolist():
                self.history.stage_edit(child_id, updates)
        else:
            self.history.stage_edit(smart_id, updates)

        new_width = float(est_days_str) * self.day_width if est_days_str.isdigit() else self.day_width

        eng_df = self.model.db.get_engineers_df()
        color_map = {str(k).strip().upper(): str(v).strip().upper() for k, v in zip(eng_df['name'], eng_df['hex_color'])} if not eng_df.empty else {}
        new_color = color_map.get(str(assignee).strip().upper(), "#007ACC") if str(assignee).strip().upper() not in ["", "UNASSIGNED"] else "#555555"

        updated_kpi = False
        for item in self.view.gantt_scene.items():
            if isinstance(item, GanttBlock):
                is_match = (item.data.get('SMART_ID') == smart_id) or \
                           (self.is_target_parent(smart_id) and item.data.get('PROJECT_ID') == smart_id)
                if is_match:
                    item.data['ASSIGNED TO'] = assignee
                    item.data['EST DAYS'] = est_days_str
                    item.data['HEX_COLOR'] = new_color
                    item.prepareGeometryChange()
                    item.rect.setWidth(new_width)
                    item.refresh_visuals()

                    if not updated_kpi and (self.view.inp_smart_id.text() == smart_id or (self.is_target_parent(smart_id) and self.view.kpi_order.text() == smart_id)):
                         self.update_kpi_variances_locally(item.x(), est_days_str)
                         updated_kpi = True

        if hasattr(self.view, 'show_status'):
            self.view.show_status("Unsaved Edit. Press Ctrl+S to Calculate & Save.", 5000)