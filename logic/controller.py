"""
The central nervous system of the MyGantt application.
Responsible for bridging the UI views with the underlying data model,
routing background signals, and managing application state.
"""

import json
import os
import logging
from typing import Any, Optional, List, Set

import pandas as pd

from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QFileDialog

from logic.constants import AppConstants
from logic.dashboard_service import DashboardService
from logic.history import HistoryManager
from logic.workers import SyncWorker, DataRefreshWorker
from logic.data_builder import GanttDataBuilder
from logic.calendar_engine import CalendarEngine
from logic.pto_parser import PTOParser
from ui.components.gantt_components import GanttBlock

logger = logging.getLogger(__name__)

class AppController:
    """
    Manages the flow of data between the UI components and the SQLite/Excel backend.
    """
    def __init__(self, view: Any, model: Any) -> None:
        self.view = view
        self.model = model
        self.history = HistoryManager()

        # Declare all instance attributes upfront for strict typing
        self.shortcut_undo: Optional[QShortcut] = None
        self.shortcut_redo: Optional[QShortcut] = None
        self.shortcut_save: Optional[QShortcut] = None
        self.selected_id_to_restore: Optional[str] = None
        self.is_maintaining_state: bool = False
        self.sync_worker: Optional[SyncWorker] = None

        self.config_file = "app_config.json"
        self.config_data = self.load_config()
        self.excel_path = self.config_data.get('excel_path', '')

        if not self.excel_path or not os.path.exists(self.excel_path):
            self.excel_path = self.prompt_for_excel()

        self.day_width = 25
        self.row_height = 36

        self.current_plan_df = pd.DataFrame()
        self.full_plan_df = pd.DataFrame()
        self.actual_df = pd.DataFrame()
        self.current_visual_rows = []
        self.expanded_projects = set()

        self.initial_scroll_done = False
        self.refresh_worker: Optional[DataRefreshWorker] = None
        self._old_workers: List[DataRefreshWorker] = []

        self.pto_path = self.config_data.get('pto_path', '')
        if not self.pto_path or not os.path.exists(self.pto_path):
            self.pto_path = self.prompt_for_pto()

        self.pto_dict = PTOParser.load_pto_data(self.pto_path) if self.pto_path else {}

        self.setup_shortcuts()

        self.view.team_screen.save_engineer_requested.connect(self.handle_save_engineer)
        self.view.team_screen.engineer_selected.connect(self.handle_engineer_selected)
        self.refresh_team_view()

        if hasattr(self.view, 'dash_screen'):
            self.view.dash_screen.filter_team.currentTextChanged.connect(lambda text: self.on_dash_filter_changed())

        if hasattr(self.view, 'filter_team'):
            self.view.filter_team.currentTextChanged.connect(lambda text: self.on_gantt_filter_changed())

        self.view.filter_req.currentTextChanged.connect(lambda text: self.on_gantt_filter_changed())
        self.view.filter_status.currentTextChanged.connect(lambda text: self.on_gantt_filter_changed())
        self.view.gantt_screen.sort_by.currentTextChanged.connect(lambda text: self.on_gantt_filter_changed())

        self.view.gantt_scene.selectionChanged.connect(self.handle_block_selection)
        self.view.info_table.itemSelectionChanged.connect(self.handle_table_selection)
        self.view.gantt_view.empty_clicked.connect(self.clear_all_selections)
        self.view.info_table.cellDoubleClicked.connect(self.handle_table_double_click)

        self.view.inp_est_days.editingFinished.connect(self.handle_stage_edit)
        self.view.inp_assignee.activated.connect(self.handle_stage_edit)

        self.view.gantt_screen.block_dropped_signal.connect(self.handle_block_dropped)
        self.view.gantt_screen.assignee_changed_signal.connect(self.handle_right_click_assign)

        self.inject_startup_defaults()

        db_holidays = self.model.db.get_holidays()
        if db_holidays:
            AppConstants.COMPANY_HOLIDAYS = db_holidays

        if hasattr(self.view, 'nav_sync_btn'):
            self.view.nav_sync_btn.clicked.connect(self.handle_sync)

    # ---------------------------------------------------------
    # STATE MANAGEMENT & CONFIGURATION
    # ---------------------------------------------------------

    def load_config(self) -> dict:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        return {}

    def save_config(self) -> None:
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config_data, f, indent=4)
        except OSError as e:
            logger.error("Failed to save config: %s", e)

    def save_preferences(self) -> None:
        prefs = {
            'gantt_team': self.view.filter_team.currentText() if hasattr(self.view, 'filter_team') else "All Teams",
            'dash_team': self.view.dash_screen.filter_team.currentText() if hasattr(self.view, 'dash_screen') else "All Teams",
            'req': self.view.filter_req.currentText() if hasattr(self.view, 'filter_req') else "All Reqs",
            'status': self.view.filter_status.currentText() if hasattr(self.view, 'filter_status') else "Active",
            'sort': self.view.gantt_screen.sort_by.currentText() if hasattr(self.view.gantt_screen, 'sort_by') else "Start Date"
        }
        self.config_data['filters'] = prefs
        self.save_config()

    def on_dash_filter_changed(self) -> None:
        self.save_preferences()

    def on_gantt_filter_changed(self) -> None:
        self.save_preferences()
        self.refresh_tables(maintain_state=False)

    def prompt_for_excel(self) -> str:
        file_path, _ = QFileDialog.getOpenFileName(
            self.view, "Select Engineering Workload Excel File", "", "Excel Files (*.xlsx *.xls)"
        )
        if file_path:
            self.config_data['excel_path'] = file_path
            self.save_config()
            return file_path
        return ""

    def prompt_for_pto(self) -> str:
        file_path, _ = QFileDialog.getOpenFileName(
            self.view, "Select Power Automate PTO CSV", "", "CSV Files (*.csv)"
        )
        if file_path:
            self.config_data['pto_path'] = file_path
            self.save_config()
            return file_path
        return ""

    def inject_startup_defaults(self) -> None:
        prefs = self.config_data.get('filters', {})
        gantt_team_pref = prefs.get('gantt_team', 'Custom Team')
        dash_team_pref = prefs.get('dash_team', 'Custom Team')

        req_pref = prefs.get('req', 'All Reqs')
        status_pref = prefs.get('status', 'Active')
        sort_pref = prefs.get('sort', 'Start Date')

        if hasattr(self.view, 'dash_screen'):
            self.view.dash_screen.filter_team.blockSignals(True)
            if self.view.dash_screen.filter_team.findText(dash_team_pref) == -1:
                self.view.dash_screen.filter_team.addItem(dash_team_pref)
            self.view.dash_screen.filter_team.setCurrentText(dash_team_pref)
            self.view.dash_screen.filter_team.blockSignals(False)

        if hasattr(self.view, 'filter_team'):
            self.view.filter_team.blockSignals(True)
            if self.view.filter_team.findText(gantt_team_pref) == -1:
                self.view.filter_team.addItem(gantt_team_pref)
            self.view.filter_team.setCurrentText(gantt_team_pref)
            self.view.filter_team.blockSignals(False)

        if hasattr(self.view, 'filter_req'):
            self.view.filter_req.blockSignals(True)
            if self.view.filter_req.findText(req_pref) == -1:
                self.view.filter_req.addItem(req_pref)
            self.view.filter_req.setCurrentText(req_pref)
            self.view.filter_req.blockSignals(False)

        if hasattr(self.view, 'filter_status'):
            self.view.filter_status.blockSignals(True)
            if self.view.filter_status.findText(status_pref) == -1:
                self.view.filter_status.addItem(status_pref)
            self.view.filter_status.setCurrentText(status_pref)
            self.view.filter_status.blockSignals(False)

        if hasattr(self.view, 'gantt_screen') and hasattr(self.view.gantt_screen, 'sort_by'):
            self.view.gantt_screen.sort_by.blockSignals(True)
            if self.view.gantt_screen.sort_by.findText(sort_pref) == -1:
                self.view.gantt_screen.sort_by.addItem(sort_pref)
            self.view.gantt_screen.sort_by.setCurrentText(sort_pref)
            self.view.gantt_screen.sort_by.blockSignals(False)

        self.refresh_tables()

    # ---------------------------------------------------------
    # CORE ROUTING & SHORTCUTS
    # ---------------------------------------------------------

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
        self.selected_id_to_restore = self.view.inp_smart_id.text() if maintain_state and not self.view.kpi_panel.isHidden() else None
        self.is_maintaining_state = maintain_state

        gantt_team_filter = self.view.filter_team.currentText() if hasattr(self.view, 'filter_team') else "All Teams"
        req_filter = self.view.filter_req.currentText()
        status_filter = self.view.filter_status.currentText()
        sort_by = self.view.gantt_screen.sort_by.currentText()

        staged_edits = self.history.get_staged_edits()
        maintain_ids = self.current_plan_df['SMART_ID'].tolist() if maintain_state and not self.current_plan_df.empty else None

        if self.refresh_worker and self.refresh_worker.isRunning():
            self.refresh_worker.data_ready.disconnect()
            self._old_workers.append(self.refresh_worker)

        self._old_workers = [w for w in self._old_workers if w.isRunning()]

        self.refresh_worker = DataRefreshWorker(self.model, staged_edits, gantt_team_filter, req_filter, status_filter, sort_by, maintain_ids)
        self.refresh_worker.data_ready.connect(self.on_data_refreshed)
        self.refresh_worker.start()

    def update_dynamic_dropdowns(self, df: pd.DataFrame) -> None:
        if df.empty: return

        eng_df = self.model.db.get_engineers_df()
        unique_teams = ["All Teams"]
        team_map = {}
        color_map = {}

        if not eng_df.empty:
            # Explicitly type the list for the linter before sorting
            team_names: List[str] = [str(x) for x in eng_df['team_name'].unique() if str(x).strip()]
            unique_teams += sorted(team_names)

            team_map = {str(k).strip().upper(): str(v).strip().upper() for k, v in zip(eng_df['name'], eng_df['team_name'])}
            color_map = {str(k).strip().upper(): str(v).strip().upper() for k, v in zip(eng_df['name'], eng_df['hex_color'])}

        if hasattr(self.view, 'dash_screen'):
            self.view.dash_screen.team_map = team_map
            self.view.dash_screen.color_map = color_map
            dash_combo = self.view.dash_screen.filter_team
            current_dash_team = dash_combo.currentText()

            dash_combo.blockSignals(True)
            dash_combo.clear()
            dash_combo.addItems(unique_teams)
            if current_dash_team in unique_teams: dash_combo.setCurrentText(current_dash_team)
            dash_combo.blockSignals(False)

        if hasattr(self.view, 'filter_team'):
            current_gantt_team = self.view.filter_team.currentText()
            self.view.filter_team.blockSignals(True)
            self.view.filter_team.clear()
            self.view.filter_team.addItems(unique_teams)
            if current_gantt_team in unique_teams: self.view.filter_team.setCurrentText(current_gantt_team)
            self.view.filter_team.blockSignals(False)

        current_req = self.view.filter_req.currentText()
        req_names: List[str] = [str(x) for x in df['REQUIREMENT'].replace('', 'Uncategorized').unique() if str(x).strip() and str(x).strip() != 'Uncategorized']
        unique_reqs = ["All Reqs"] + sorted(req_names)

        self.view.filter_req.blockSignals(True)
        self.view.filter_req.clear()
        self.view.filter_req.addItems(unique_reqs)
        if current_req in unique_reqs: self.view.filter_req.setCurrentText(current_req)
        self.view.filter_req.blockSignals(False)

        current_assignee = self.view.inp_assignee.currentText()
        assignee_names: List[str] = [str(x) for x in df['ASSIGNED TO'].unique() if str(x).strip()]
        unique_assignees = ["Unassigned"] + sorted(assignee_names)

        self.view.inp_assignee.blockSignals(True)
        self.view.inp_assignee.clear()
        self.view.inp_assignee.addItems(unique_assignees)
        if current_assignee in unique_assignees: self.view.inp_assignee.setCurrentText(current_assignee)
        self.view.inp_assignee.blockSignals(False)

    def is_target_parent(self, target_id: str) -> bool:
        for row in self.current_visual_rows:
            if row.get('IS_PARENT') and row.get('PROJECT_ID') == target_id:
                return True
        return False

    def _rebuild_and_render_canvas(self, target_id_to_restore: Optional[str]) -> None:
        """Forces a pure recalculation of the visual hierarchy to prevent UI feedback loops."""
        eng_df = self.model.db.get_engineers_df()
        color_map = {str(k).strip().upper(): str(v).strip().upper() for k, v in
                     zip(eng_df['name'], eng_df['hex_color'])} if not eng_df.empty else {}


        self.current_visual_rows = GanttDataBuilder.build_visual_hierarchy(
            self.current_plan_df, self.expanded_projects, color_map, self.pto_dict
        )

        dynamic_engineers = [self.view.inp_assignee.itemText(i)
                             for i in range(self.view.inp_assignee.count())]

        self.view.gantt_screen.render_gantt(
            self.current_visual_rows, dynamic_engineers, self.expanded_projects, color_map, self.pto_dict
        )

        self.restore_selection(target_id_to_restore)

    def on_data_refreshed(self, raw_df: pd.DataFrame, plan_df: pd.DataFrame, actual_df: pd.DataFrame, full_plan_df: pd.DataFrame) -> None:
        if hasattr(self.view, 'display_dataframe') and hasattr(self.view, 'raw_table'):
            self.view.display_dataframe(self.view.raw_table, raw_df)

        if actual_df.empty: return

        self.update_dynamic_dropdowns(actual_df)

        self.actual_df = actual_df
        self.full_plan_df = full_plan_df

        if plan_df.empty: return
        self.current_plan_df = plan_df

        target = self.selected_id_to_restore if self.is_maintaining_state else None
        self._rebuild_and_render_canvas(target)

        if hasattr(self.view, 'dash_screen'):
            self.view.dash_screen.update_dashboard(actual_df, full_plan_df)

        if not (self.is_maintaining_state and self.selected_id_to_restore):
            self.view.kpi_panel.hide()

    def handle_table_double_click(self, row: int, _col: int) -> None:
        if row < len(self.current_visual_rows):
            row_data = self.current_visual_rows[row]
            if row_data.get('IS_PARENT', False):
                project_id = row_data['PROJECT_ID']

                if project_id in self.expanded_projects:
                    self.expanded_projects.remove(project_id)
                else:
                    self.expanded_projects.add(project_id)

                if not self.current_plan_df.empty:
                    self._rebuild_and_render_canvas(None)

    def restore_selection(self, target_id: Optional[str]) -> None:
        if not target_id: return

        try:
            row_idx = next(i for i, r in enumerate(self.current_visual_rows) if
                           r.get('SMART_ID') == target_id or r.get('PROJECT_ID') == target_id)
            self.view.info_table.blockSignals(True)
            self.view.info_table.selectRow(row_idx)
            self.view.info_table.blockSignals(False)
        except StopIteration:
            pass

        try:
            if not self.view.isVisible(): return
            self.view.gantt_scene.blockSignals(True)
            for item in self.view.gantt_scene.items():
                if isinstance(item, GanttBlock):
                    if (item.is_parent and item.data.get('PROJECT_ID') == target_id) or \
                            (not item.is_parent and item.data.get('SMART_ID') == target_id):
                        item.setSelected(True)
                        self.view.gantt_screen.populate_kpi_inspector(item.data)
                        break
            self.view.gantt_scene.blockSignals(False)
            self.view.kpi_panel.show()
        except RuntimeError:
            pass

    def clear_all_selections(self) -> None:
        try:
            if not self.view.isVisible(): return
            self.view.info_table.blockSignals(True)
            self.view.info_table.clearSelection()
            self.view.info_table.blockSignals(False)

            self.view.gantt_scene.blockSignals(True)
            self.view.gantt_scene.clearSelection()
            self.view.gantt_scene.blockSignals(False)

            self.view.kpi_panel.hide()
        except RuntimeError:
             pass

    def handle_block_selection(self) -> None:
        try:
            if not self.view.isVisible(): return
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
        except RuntimeError:
            pass

    def handle_table_selection(self) -> None:
        try:
            if not self.view.isVisible(): return
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
        except RuntimeError:
            pass

    def handle_sync(self) -> None:
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
            if hasattr(self.view, 'show_status'): self.view.show_status("Sync failed.", 5000)
            if hasattr(self.view, 'show_warning'): self.view.show_warning("Sync Error",
                                                                           f"Could not sync data:\n\n{error_msg}")
        else:
            if hasattr(self.view, 'show_status'): self.view.show_status("Sync complete!", 4000)

            db_holidays = self.model.db.get_holidays()
            if db_holidays:
                AppConstants.COMPANY_HOLIDAYS = db_holidays

            if hasattr(self, 'pto_path') and self.pto_path:
                self.pto_path = PTOParser.load_pto_data(self.pto_path)

            self.refresh_tables(maintain_state=False)

    def refresh_team_view(self) -> None:
        try:
            eng_df = self.model.db.get_engineers_df()
            self.view.team_screen.populate_roster(eng_df)

            raw_df = self.model.get_raw_df()
            if not raw_df.empty and 'RAW_ASSIGNED' in raw_df.columns:
                # Explicitly tell the linter these are Sets of strings
                raw_names: Set[str] = {str(x).strip().upper() for x in raw_df['RAW_ASSIGNED'].unique() if
                                       str(x).strip().upper() not in ('', 'UNASSIGNED', 'NAN')}

                configured_names: Set[str] = {str(x).strip().upper() for x in
                                              eng_df['name'].unique()} if not eng_df.empty else set()

                # Explicitly tell the linter these are Lists of strings before sorting
                unconfigured: List[str] = sorted(list(raw_names - configured_names))
                configured_list: List[str] = sorted(list(configured_names))

                combo = self.view.team_screen.inp_name
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(unconfigured + configured_list)
                combo.blockSignals(False)
        except Exception as e:
            logger.exception("CRITICAL ERROR in refresh_team_view: %s", e)

    def handle_save_engineer(self, name: str, team: str, color: str) -> None:
        self.model.db.upsert_team(team, 0.0)
        self.model.db.upsert_engineer(name, team, color)
        if hasattr(self.view, 'show_status'): self.view.show_status(f"Saved configuration for {name}.", 3000)
        self.refresh_team_view()

    def handle_engineer_selected(self, engineer_name: str) -> None:
        if not hasattr(self, 'actual_df') or self.actual_df.empty:
            return

        analytics_payload = DashboardService.get_engineer_performance(self.actual_df, engineer_name)

        eng_db_df = self.model.db.get_engineers_df()
        primary_color = "#007ACC"
        if not eng_db_df.empty:
            color_match = eng_db_df[eng_db_df['name'].str.upper() == engineer_name.upper()]
            if not color_match.empty:
                primary_color = color_match.iloc[0].get('hex_color', '#007ACC')

        self.view.team_screen.update_analytics(
            engineer_name=engineer_name,
            analytics_payload=analytics_payload,
            primary_color=primary_color
        )

    def update_kpi_variances_locally(self, start_x: float, est_days_str: str, pto_dates: Optional[List[str]] = None) -> None:
        day_zero = self.view.gantt_screen.day_zero
        if not day_zero: return

        start_date_raw = day_zero + pd.tseries.offsets.BusinessDay(round(start_x / self.day_width))
        days = int(est_days_str) if est_days_str.isdigit() else 5

        adjusted_days = days - 1 if days > 0 else days
        end_date = CalendarEngine.shift_date(start_date_raw, adjusted_days, pto_dates) # <-- PASS PTO

        if end_date is None:
            return

        due_date_str = self.view.kpi_eng_due.text()
        if due_date_str and due_date_str != '--':
            try:
                var = CalendarEngine.get_working_days_variance(end_date, pd.to_datetime(due_date_str), pto_dates)
                self.view.kpi_eng_var.setText(f"{var} days")
            except ValueError: pass

        esd_str = self.view.kpi_esd.text()
        if esd_str and esd_str != '--':
            try:
                var_esd = CalendarEngine.get_working_days_variance(end_date, pd.to_datetime(esd_str), pto_dates)
                self.view.kpi_esd_var.setText(f"{var_esd} days")
            except ValueError: pass

    def handle_block_dropped(self, target_id: str, new_x: float, new_width: float, is_parent: bool,
                             delta_x: float = 0.0, delta_w: float = 0.0) -> None:
        day_zero = self.view.gantt_screen.day_zero
        if not day_zero: return
        day_width = self.view.gantt_screen.day_width

        # --- NEW: Grab the Assignee's PTO dates to fuel the drag math ---
        mask = self.current_plan_df['SMART_ID'] == target_id
        assignee = self.current_plan_df.loc[mask, 'ASSIGNED TO'].values[0] if not is_parent else ""
        safe_assignee = str(assignee).strip().title()
        pto_dates = self.pto_dict.get(safe_assignee, []) if hasattr(self, 'pto_dict') and self.pto_dict else []
        # ----------------------------------------------------------------

        if not is_parent:
            # 1. Map visual drop location to a physical date via the Engine
            new_date_raw = day_zero + pd.tseries.offsets.BusinessDay(round(new_x / day_width))
            new_start_pd = CalendarEngine.shift_date(new_date_raw, 0, pto_dates)  # <-- PASS PTO

            if new_start_pd is None:
                return

            start_date_str = f"{new_start_pd.month}/{new_start_pd.day}/{new_start_pd.year}"

            # 2. INSTANT CACHE UPDATE
            self.current_plan_df.loc[mask, 'EST START DATE'] = start_date_str
            self.history.stage_edit(target_id, {'MAN_START_DATE': start_date_str})

            est_days_str = str(self.current_plan_df.loc[mask, 'EST DAYS'].values[0])
            days_val = int(est_days_str) if est_days_str.isdigit() else 5
            adjusted_days = days_val - 1 if days_val > 0 else days_val

            new_end_pd = CalendarEngine.shift_date(new_start_pd, adjusted_days, pto_dates)

            if new_end_pd is not None:
                self.current_plan_df.loc[
                    mask, 'EST END DATE'] = f"{new_end_pd.month}/{new_end_pd.day}/{new_end_pd.year}"

            # 3. Handle Resizing
            if abs(delta_w) > 0.1:
                visual_days = max(1, round(new_width / day_width))
                end_date_raw = new_date_raw + pd.tseries.offsets.BusinessDay(visual_days - 1)

                # Use Engine's exact inclusive duration math!
                raw_work_days = CalendarEngine.get_working_days_duration(new_start_pd, end_date_raw,
                                                                         pto_dates)
                new_days_str = str(max(1, raw_work_days))

                self.current_plan_df.loc[mask, 'EST DAYS'] = new_days_str
                self.history.stage_edit(target_id, {'MAN_EST_DAYS': new_days_str})

                if hasattr(self, 'update_kpi_variances_locally'):
                    self.update_kpi_variances_locally(new_x, new_days_str, pto_dates)

        else:
            # 4. GHOST PARENT DRAGGING
            if abs(delta_x) < 0.1:
                self._rebuild_and_render_canvas(target_id)
                return

            mask = self.current_plan_df['PROJECT_ID'] == target_id
            children = self.current_plan_df[mask]

            delta_days_visual = round(delta_x / day_width)

            parent_starts = pd.to_datetime(children['EST START DATE'], errors='coerce').dropna()
            if parent_starts.empty:
                self._rebuild_and_render_canvas(target_id)
                return

            old_parent_start = parent_starts.min()

            # Find exact shift working days using the Engine
            new_parent_start_safe = CalendarEngine.shift_date(old_parent_start, delta_days_visual)

            if new_parent_start_safe is None:
                self._rebuild_and_render_canvas(target_id)
                return

            shift_working_days = CalendarEngine.get_working_days_variance(old_parent_start, new_parent_start_safe)

            if shift_working_days == 0:
                self._rebuild_and_render_canvas(target_id)
                return

            # Shift every un-started child instantly
            bulk_edits = {}
            for _, child in children.iterrows():
                child_smart_id = child['SMART_ID']

                if str(child.get('ENG START DATE', '')).strip():
                    continue

                old_child_start = pd.to_datetime(child.get('EST START DATE', pd.NaT))
                if pd.isna(old_child_start): continue

                new_child_pd = CalendarEngine.shift_date(old_child_start, shift_working_days)

                if new_child_pd is None:
                    continue

                start_date_str = f"{new_child_pd.month}/{new_child_pd.day}/{new_child_pd.year}"

                bulk_edits[child_smart_id] = {'MAN_START_DATE': start_date_str}
                c_mask = self.current_plan_df['SMART_ID'] == child_smart_id
                self.current_plan_df.loc[c_mask, 'EST START DATE'] = start_date_str

            # ---> Apply the perfect bulk-edit fix here! <---
            if bulk_edits:
                self.history.stage_bulk_edits(bulk_edits)

        # 5. INSTANT UI REDRAW
        self._rebuild_and_render_canvas(target_id)

        if hasattr(self.view, 'show_status'):
            self.view.show_status("Unsaved Schedule edit. Press Ctrl+S to Calculate & Save.", 5000)

    def handle_right_click_assign(self, target_id: str, new_assignee: str) -> None:
        if self.is_target_parent(target_id):
            mask = self.current_plan_df['PROJECT_ID'] == target_id
            bulk_edits = {}
            for child_id in self.current_plan_df[mask]['SMART_ID'].tolist():
                bulk_edits[child_id] = {'MAN_ASSIGNED': new_assignee}
                c_mask = self.current_plan_df['SMART_ID'] == child_id
                self.current_plan_df.loc[c_mask, 'ASSIGNED TO'] = new_assignee

            self.history.stage_bulk_edits(bulk_edits)
        else:
            self.history.stage_edit(target_id, {'MAN_ASSIGNED': new_assignee})
            mask = self.current_plan_df['SMART_ID'] == target_id
            self.current_plan_df.loc[mask, 'ASSIGNED TO'] = new_assignee

        self._rebuild_and_render_canvas(target_id)

        if hasattr(self.view, 'show_status'):
            self.view.show_status("Unsaved Assignee edit. Press Ctrl+S to Calculate & Save.", 5000)

    def handle_stage_edit(self) -> None:
        smart_id = self.view.inp_smart_id.text()
        assignee = self.view.inp_assignee.currentText()
        est_days_str = self.view.inp_est_days.text()

        if not est_days_str.isdigit(): est_days_str = "5"

        if self.is_target_parent(smart_id):
            mask = self.current_plan_df['PROJECT_ID'] == smart_id
            bulk_edits = {}
            for child_id in self.current_plan_df[mask]['SMART_ID'].tolist():
                bulk_edits[child_id] = {'MAN_ASSIGNED': assignee}
                c_mask = self.current_plan_df['SMART_ID'] == child_id
                self.current_plan_df.loc[c_mask, 'ASSIGNED TO'] = assignee

            self.history.stage_bulk_edits(bulk_edits)
        else:
            self.history.stage_edit(smart_id, {'MAN_ASSIGNED': assignee, 'MAN_EST_DAYS': est_days_str})
            mask = self.current_plan_df['SMART_ID'] == smart_id
            self.current_plan_df.loc[mask, 'ASSIGNED TO'] = assignee
            self.current_plan_df.loc[mask, 'EST DAYS'] = est_days_str

        self._rebuild_and_render_canvas(smart_id)

        if hasattr(self.view, 'show_status'):
            self.view.show_status("Unsaved Edit. Press Ctrl+S to Calculate & Save.", 5000)