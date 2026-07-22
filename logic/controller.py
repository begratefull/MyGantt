"""
The central nervous system of the MyGantt application.
Responsible for bridging the UI views with the underlying data model,
routing background signals, and managing application state.
"""

import json
import logging
import os
import uuid
from typing import Any, Optional

import pandas as pd
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import QFileDialog

from logic.calendar_engine import CalendarEngine
from logic.constants import AppConstants
from logic.dashboard_service import DashboardService
from logic.data_builder import GanttDataBuilder
from logic.history import HistoryManager
from logic.pto_parser import PTOParser
from logic.web_publisher import WebPublisher
from logic.workers import SyncWorker, DataRefreshWorker
from ui.components.gantt_components import GanttBlock

try:
    from ui.dialogs.task_dialog import TaskDialog  # pyrefly: ignore[missing-import]
except ImportError:
    TaskDialog = None

logger = logging.getLogger(__name__)


class AppController:
    """
    Manages the flow of data between the UI components and the SQLite/Excel backend.
    Handles user inputs, triggers threaded workers, and maintains undo/redo history.
    """
    def __init__(self, view: Any, model: Any) -> None:
        """
        Initializes the controller, binds view signals, and starts the initial data load.

        Args:
            view (Any): The main QMainWindow reference.
            model (Any): The WorkloadManager data model reference.
        """
        self.view = view
        self.model = model
        self.history = HistoryManager()

        # Declares all instance attributes upfront for strict typing.
        self.shortcut_undo: Optional[QShortcut] = None
        self.shortcut_redo: Optional[QShortcut] = None
        self.shortcut_save: Optional[QShortcut] = None

        # Upgraded to list for multi-select state restoration.
        self.selected_ids_to_restore: list[str] = []
        self.is_maintaining_state: bool = False
        self.sync_worker: Optional[SyncWorker] = None

        self.config_file = AppConstants.get_config_path()
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
        self._old_workers: list[DataRefreshWorker] = []

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

        # Cross-component selection syncing signals.
        self.view.gantt_scene.selectionChanged.connect(self.handle_block_selection)
        self.view.info_table.itemSelectionChanged.connect(self.handle_table_selection)
        self.view.gantt_view.empty_clicked.connect(self.clear_all_selections)
        self.view.info_table.cellDoubleClicked.connect(self.handle_table_double_click)

        # Threaded bulk dispatch signal from view to controller.
        self.view.gantt_screen.bulk_kpi_update_signal.connect(self.handle_bulk_kpi_update)
        self.view.gantt_screen.block_dropped_signal.connect(self.handle_block_dropped)

        # Manual side-work task signal.
        if hasattr(self.view, 'btn_create_task'):
            self.view.btn_create_task.clicked.connect(self.handle_create_task)

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
        """Loads user preferences and file paths from the JSON config."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        return {}

    def save_config(self) -> None:
        """Saves current user preferences and file paths to the JSON config."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config_data, f, indent=4)
        except OSError as e:
            logger.error("Failed to save config: %s", e)

    def save_preferences(self) -> None:
        """Captures the current state of UI filters and saves them."""
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
        """Triggered when dashboard filters change to auto-save preferences."""
        self.save_preferences()

    def on_gantt_filter_changed(self) -> None:
        """Triggered when Gantt filters change to auto-save preferences and update the view."""
        self.save_preferences()
        self.refresh_tables(maintain_state=False)

    def prompt_for_excel(self) -> str:
        """Prompts the user to select the master engineering Excel file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.view, "Select Engineering Workload Excel File", "", "Excel Files (*.xlsx *.xls)"
        )
        if file_path:
            self.config_data['excel_path'] = file_path
            self.save_config()
            return file_path
        return ""

    def prompt_for_pto(self) -> str:
        """Prompts the user to select the Power Automate PTO CSV."""
        file_path, _ = QFileDialog.getOpenFileName(
            self.view, "Select Power Automate PTO CSV", "", "CSV Files (*.csv)"
        )
        if file_path:
            self.config_data['pto_path'] = file_path
            self.save_config()
            return file_path
        return ""

    def _set_combo_box_value(self, combo_box: Any, value: str) -> None:
        """Safely updates a combo box value without triggering active state signals."""
        combo_box.blockSignals(True)
        if combo_box.findText(value) == -1:
            combo_box.addItem(value)
        combo_box.setCurrentText(value)
        combo_box.blockSignals(False)

    def inject_startup_defaults(self) -> None:
        """Applies saved filter states to the UI dropdowns upon boot."""
        prefs = self.config_data.get('filters', {})
        gantt_team_pref = prefs.get('gantt_team', 'Custom Team')
        dash_team_pref = prefs.get('dash_team', 'Custom Team')

        req_pref = prefs.get('req', 'All Reqs')
        status_pref = prefs.get('status', 'Active')
        sort_pref = prefs.get('sort', 'Start Date')

        if hasattr(self.view, 'dash_screen'):
            self._set_combo_box_value(self.view.dash_screen.filter_team, dash_team_pref)

        if hasattr(self.view, 'filter_team'):
            self._set_combo_box_value(self.view.filter_team, gantt_team_pref)

        if hasattr(self.view, 'filter_req'):
            self._set_combo_box_value(self.view.filter_req, req_pref)

        if hasattr(self.view, 'filter_status'):
            self._set_combo_box_value(self.view.filter_status, status_pref)

        if hasattr(self.view, 'gantt_screen') and hasattr(self.view.gantt_screen, 'sort_by'):
            self._set_combo_box_value(self.view.gantt_screen.sort_by, sort_pref)

        self.refresh_tables()

    # ---------------------------------------------------------
    # CORE ROUTING & SHORTCUTS
    # ---------------------------------------------------------

    def setup_shortcuts(self) -> None:
        """Binds global keyboard shortcuts for Undo, Redo, and Save."""
        self.shortcut_undo = QShortcut(QKeySequence("Ctrl+Z"), self.view)
        self.shortcut_undo.activated.connect(self.handle_undo)

        self.shortcut_redo = QShortcut(QKeySequence("Ctrl+Y"), self.view)
        self.shortcut_redo.activated.connect(self.handle_redo)

        self.shortcut_save = QShortcut(QKeySequence("Ctrl+S"), self.view)
        self.shortcut_save.activated.connect(self.handle_global_save)

    def _execute_history_action(self, action_type: str) -> None:
        """Executes an undo or redo action and redraws the UI dynamically."""
        success = self.history.undo() if action_type == 'undo' else self.history.redo()
        if success:
            self.refresh_tables(maintain_state=True)
            if hasattr(self.view, 'show_status'):
                self.view.show_status(f"{action_type.capitalize()} successful. Press Ctrl+S to save.", 3000)

    def handle_undo(self) -> None:
        """Executes an undo action and redraws the UI."""
        self._execute_history_action('undo')

    def handle_redo(self) -> None:
        """Executes a redo action and redraws the UI."""
        self._execute_history_action('redo')

    def handle_global_save(self) -> None:
        """Commits all staged edits to the database and attempts to publish to the web portal."""
        if self.history.has_changes():
            self.model.commit_overrides(self.history.get_staged_edits())
            self.history.clear()

            web_df = self.model.get_application_data()

            if not web_df.empty:
                web_df = web_df[web_df['STATUS'].str.strip().str.upper() != 'COMPLETE'].copy()

                assignee_series = web_df['ASSIGNED TO']
                pto = getattr(self, 'pto_dict', None)
                web_df['EST END DATE'] = CalendarEngine.calculate_end_dates_vectorized(
                    web_df['EST START DATE'], web_df['EST DAYS'], assignee_series, pto
                )

                if hasattr(self.view, 'show_status'):
                    self.view.show_status("Saving locally and publishing to live web schedule...", 0)

                success = WebPublisher.publish_schedule(web_df, self.config_data)

                if success and hasattr(self.view, 'show_status'):
                    self.view.show_status("All changes saved locally and published live.", 4000)
                elif hasattr(self.view, 'show_status'):
                    self.view.show_status("Saved locally, but web publish failed. Check log file.", 5000)
            else:
                if hasattr(self.view, 'show_status'):
                    self.view.show_status("All changes saved successfully.", 4000)

            self.refresh_tables(maintain_state=True)
        else:
            if hasattr(self.view, 'show_status'):
                self.view.show_status("No unsaved changes.", 3000)

    def refresh_tables(self, maintain_state: bool = False) -> None:
        """Kicks off the threaded worker. Dynamically captures all selected item IDs to restore state upon finish."""
        if maintain_state and not self.view.kpi_panel.isHidden():
            self.selected_ids_to_restore = []
            for item in self.view.gantt_scene.selectedItems():
                if isinstance(item, GanttBlock):
                    tid = item.data.get('PROJECT_ID') if item.is_parent else item.data.get('SMART_ID')
                    if tid: self.selected_ids_to_restore.append(tid)
        else:
            self.selected_ids_to_restore = []

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

        self.refresh_worker = DataRefreshWorker(self.model, staged_edits, gantt_team_filter, req_filter, status_filter,
                                                sort_by, maintain_ids, self.pto_dict)
        self.refresh_worker.data_ready.connect(self.on_data_refreshed)
        self.refresh_worker.start()

    def _replace_combo_items(self, combo_box: Any, items: list[str], current_value: str) -> None:
        """Clears and replaces items in a combo box while preserving the active selection."""
        combo_box.blockSignals(True)
        combo_box.clear()
        combo_box.addItems(items)
        if current_value in items:
            combo_box.setCurrentText(current_value)
        combo_box.blockSignals(False)

    def update_dynamic_dropdowns(self, df: pd.DataFrame) -> None:
        """Updates filter dropdowns to only show options relevant to the current dataset."""
        if df.empty:
            return

        eng_df = self.model.db.get_engineers_df()
        unique_teams = ["All Teams"]
        team_map = {}
        color_map = {}

        if not eng_df.empty:
            team_names: list[str] = [str(x) for x in eng_df['team_name'].unique() if str(x).strip()]
            unique_teams += sorted(team_names)

            team_map = {str(k).strip().upper(): str(v).strip().upper() for k, v in zip(eng_df['name'], eng_df['team_name'])}
            color_map = {str(k).strip().upper(): str(v).strip().upper() for k, v in zip(eng_df['name'], eng_df['hex_color'])}

        if hasattr(self.view, 'dash_screen'):
            self.view.dash_screen.team_map = team_map
            self.view.dash_screen.color_map = color_map
            self._replace_combo_items(self.view.dash_screen.filter_team, unique_teams, self.view.dash_screen.filter_team.currentText())

        if hasattr(self.view, 'filter_team'):
            self._replace_combo_items(self.view.filter_team, unique_teams, self.view.filter_team.currentText())

        current_req = self.view.filter_req.currentText()
        req_names: list[str] = [str(x) for x in df['REQUIREMENT'].replace('', 'Uncategorized').unique() if str(x).strip() and str(x).strip() != 'Uncategorized']
        unique_reqs = ["All Reqs"] + sorted(req_names)
        self._replace_combo_items(self.view.filter_req, unique_reqs, current_req)

        current_assignee = self.view.inp_assignee.currentText()
        assignee_names: list[str] = [str(x) for x in df['ASSIGNED TO'].unique() if str(x).strip()]
        unique_assignees = ["Unassigned"] + sorted(assignee_names)
        self._replace_combo_items(self.view.inp_assignee, unique_assignees, current_assignee)

    def is_target_parent(self, target_id: str) -> bool:
        """Determines if a given ID corresponds to a parent project group."""
        for row in self.current_visual_rows:
            if row.get('IS_PARENT') and row.get('PROJECT_ID') == target_id:
                return True
        return False

    def _rebuild_and_render_canvas(self, target_ids_to_restore: Optional[list[str]] = None) -> None:
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

        self.restore_selection(target_ids_to_restore)

    def on_data_refreshed(self, raw_df: pd.DataFrame, plan_df: pd.DataFrame, actual_df: pd.DataFrame, full_plan_df: pd.DataFrame) -> None:
        """Callback triggered when the DataRefreshWorker completes its background calculations."""
        if hasattr(self.view, 'display_dataframe') and hasattr(self.view, 'raw_table'):
            self.view.display_dataframe(self.view.raw_table, raw_df)

        if actual_df.empty:
            return

        self.update_dynamic_dropdowns(actual_df)

        self.actual_df = actual_df
        self.full_plan_df = full_plan_df

        if plan_df.empty:
            return
        self.current_plan_df = plan_df

        targets = self.selected_ids_to_restore if self.is_maintaining_state else None
        self._rebuild_and_render_canvas(targets)

        if hasattr(self.view, 'dash_screen'):
            self.view.dash_screen.update_dashboard(actual_df, full_plan_df)

        if not (self.is_maintaining_state and self.selected_ids_to_restore):
            self.view.kpi_panel.hide()

    def handle_table_double_click(self, row: int, _col: int) -> None:
        """Toggles the expanded/collapsed state of a project group."""
        if row < len(self.current_visual_rows):
            row_data = self.current_visual_rows[row]
            if row_data.get('IS_PARENT', False):
                project_id = row_data['PROJECT_ID']

                if project_id in self.expanded_projects:
                    self.expanded_projects.remove(project_id)
                else:
                    self.expanded_projects.add(project_id)

                if not self.current_plan_df.empty:
                    self._rebuild_and_render_canvas(self.selected_ids_to_restore)

    def restore_selection(self, target_ids: Optional[list[str]]) -> None:
        """Iterates through all known selected IDs and reapplies highlight to Table and Canvas without infinite loops."""
        if not target_ids:
            return

        try:
            self.view.info_table.blockSignals(True)
            self.view.gantt_scene.blockSignals(True)

            selected_data = []

            # 1. Restores table highlights.
            for row_idx, r in enumerate(self.current_visual_rows):
                tid = r.get('SMART_ID') if not r.get('IS_PARENT') else r.get('PROJECT_ID')
                if tid in target_ids:
                    self.view.info_table.selectRow(row_idx)

            # 2. Restores canvas highlights.
            if self.view.isVisible():
                for item in self.view.gantt_scene.items():
                    if isinstance(item, GanttBlock):
                        item_tid = item.data.get('PROJECT_ID') if item.is_parent else item.data.get('SMART_ID')
                        if item_tid in target_ids:
                            item.setSelected(True)
                            selected_data.append(item.data)

            self.view.info_table.blockSignals(False)
            self.view.gantt_scene.blockSignals(False)

            # 3. Restores KPI panel data context.
            if selected_data:
                self.view.gantt_screen.populate_kpi_inspector(selected_data)
                self.view.kpi_panel.show()

        except RuntimeError:
            pass

    def clear_all_selections(self) -> None:
        """Safely clears highlights from both the table and the canvas."""
        try:
            if not self.view.isVisible():
                return
            self.view.info_table.blockSignals(True)
            self.view.info_table.clearSelection()
            self.view.info_table.blockSignals(False)

            self.view.gantt_scene.blockSignals(True)
            self.view.gantt_scene.clearSelection()
            self.view.gantt_scene.blockSignals(False)

            self.view.kpi_panel.hide()
            self.selected_ids_to_restore = []
        except RuntimeError:
             pass

    def handle_block_selection(self) -> None:
        """Triggers when the canvas is dragged. Programmatically selects the matching table rows."""
        try:
            if not self.view.isVisible():
                return
            selected_items = self.view.gantt_scene.selectedItems()

            self.view.info_table.blockSignals(True)
            self.view.info_table.clearSelection()

            if not selected_items:
                self.view.info_table.blockSignals(False)
                self.view.kpi_panel.hide()
                return

            selected_data = []
            for item in selected_items:
                if hasattr(item, 'data'):
                    data = item.data
                    selected_data.append(data)

                    tid = data.get('SMART_ID') if not data.get('IS_PARENT') else data.get('PROJECT_ID')
                    for row_idx, r in enumerate(self.current_visual_rows):
                        r_tid = r.get('SMART_ID') if not r.get('IS_PARENT') else r.get('PROJECT_ID')
                        if r_tid == tid:
                            self.view.info_table.selectRow(row_idx)
                            break

            self.view.info_table.blockSignals(False)

            if selected_data:
                self.view.gantt_screen.populate_kpi_inspector(selected_data)
                self.view.kpi_panel.show()
        except RuntimeError:
            pass

    def handle_table_selection(self) -> None:
        """Triggers when the table is dragged. Programmatically selects the matching canvas blocks."""
        try:
            if not self.view.isVisible():
                return
            selected_rows = self.view.info_table.selectionModel().selectedRows()

            self.view.gantt_scene.blockSignals(True)
            self.view.gantt_scene.clearSelection()

            if not selected_rows or not self.current_visual_rows:
                self.view.gantt_scene.blockSignals(False)
                self.view.kpi_panel.hide()
                return

            selected_data = []
            for model_index in selected_rows:
                row_idx = model_index.row()
                if row_idx < len(self.current_visual_rows):
                    data = self.current_visual_rows[row_idx]
                    selected_data.append(data)

                    tid = data.get('SMART_ID') if not data.get('IS_PARENT') else data.get('PROJECT_ID')

                    for item in self.view.gantt_scene.items():
                        if isinstance(item, GanttBlock):
                            item_tid = item.data.get('SMART_ID') if not item.is_parent else item.data.get('PROJECT_ID')
                            if item_tid == tid:
                                item.setSelected(True)
                                break

            self.view.gantt_scene.blockSignals(False)

            if selected_data:
                self.view.gantt_screen.populate_kpi_inspector(selected_data)
                self.view.kpi_panel.show()
        except RuntimeError:
            pass

    def handle_bulk_kpi_update(self, target_ids: list[str], field_name: str, new_value: Any) -> None:
        """Dispatches data changes, applies local vectorized math safely, and redraws UI."""
        try:
            bulk_edits = {}
            if field_name == 'EST DAYS':
                history_key = 'MAN_EST_DAYS'
            elif field_name == 'STATUS':
                history_key = 'MAN_STATUS'
            elif field_name == 'ASSIGNED TO':
                history_key = 'MAN_ASSIGNED'
            else:
                history_key = 'UNKNOWN'

            for tid in target_ids:
                if self.is_target_parent(tid):
                    mask = self.current_plan_df['PROJECT_ID'] == tid
                    for child_id in self.current_plan_df[mask]['SMART_ID'].tolist():
                        bulk_edits[child_id] = {history_key: new_value}
                        c_mask = self.current_plan_df['SMART_ID'] == child_id
                        self.current_plan_df.loc[c_mask, field_name] = new_value
                else:
                    bulk_edits[tid] = {history_key: new_value}
                    mask = self.current_plan_df['SMART_ID'] == tid
                    self.current_plan_df.loc[mask, field_name] = new_value

            if bulk_edits:
                self.history.stage_bulk_edits(bulk_edits)

            # Fast path: Vectorized math in memory.
            if field_name == 'EST DAYS' or field_name == 'ASSIGNED TO':
                affected_mask = self.current_plan_df['SMART_ID'].isin(bulk_edits.keys())

                valid_starts = pd.to_datetime(self.current_plan_df.loc[affected_mask, 'EST START DATE'],
                                              errors='coerce')
                valid_mask = affected_mask & valid_starts.notna()

                if valid_mask.any():
                    assignee_series = self.current_plan_df.loc[valid_mask, 'ASSIGNED TO']
                    pto = getattr(self, 'pto_dict', None)

                    self.current_plan_df.loc[
                        valid_mask, 'EST END DATE'] = CalendarEngine.calculate_end_dates_vectorized(
                        self.current_plan_df.loc[valid_mask, 'EST START DATE'],
                        self.current_plan_df.loc[valid_mask, 'EST DAYS'],
                        assignee_series,
                        pto
                    )

            # Passes the target_ids list directly to maintain selection instead of reading the empty fallback variable.
            self._rebuild_and_render_canvas(target_ids)

            if hasattr(self.view, 'show_status'):
                self.view.show_status(f"Unsaved Bulk Edit ({len(target_ids)} items). Press Ctrl+S to Calculate & Save.",
                                      5000)

        except Exception as e:  # pyrefly: ignore[broad-except]
            logger.error(f"Error handling bulk KPI update: {e}")

    def handle_create_task(self) -> None:
        """Launches the dialog to create a new manual side-work task and saves it to the database."""
        try:
            if TaskDialog is None:
                if hasattr(self.view, 'show_warning'):
                    self.view.show_warning("Not Implemented", "TaskDialog module is missing. Please implement the dialog file.")
                return

            eng_df = self.model.db.get_engineers_df()
            # Stop uppercasing names here so they match exactly what is in the database.
            configured_names = [str(x).strip() for x in eng_df['name'].unique()] if not eng_df.empty else []

            dialog = TaskDialog(self.view, configured_names)
            if dialog.exec():
                task_data = dialog.get_task_data()

                # Generates unique identifiers.
                short_hash = uuid.uuid4().hex[:6].upper()
                smart_id = f"{AppConstants.MANUAL_TASK_PREFIX}{short_hash}"
                project_id = f"SW-{short_hash}"

                # Enriches payload with backend defaults.
                task_data['SMART_ID'] = smart_id
                task_data['PROJECT_ID'] = project_id
                task_data['REQUIREMENT'] = 'SIDE WORK'
                task_data['TYPE'] = 'CUS'
                task_data['STATUS'] = 'ACTIVE'

                # Saves directly to persistence layer.
                success = self.model.db.upsert_manual_task(task_data)

                if success:
                    if hasattr(self.view, 'show_status'):
                        self.view.show_status(f"Task '{task_data.get('PROJECT NAME')}' created successfully.", 4000)
                    # Triggers a hard refresh to pull the new database rows.
                    self.refresh_tables(maintain_state=True)
                else:
                    if hasattr(self.view, 'show_warning'):
                        self.view.show_warning("Error", "Failed to create manual task in the database.")
        except Exception as e:  # pyrefly: ignore[broad-except]
            logger.exception(f"Error handling task creation: {e}")
            if hasattr(self.view, 'show_warning'):
                self.view.show_warning("Error", f"An unexpected error occurred while creating the task: {e}")

    def handle_sync(self) -> None:
        """Triggers the Excel parsing worker to update the database."""
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
        """Callback for when the Excel sync worker completes."""
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
        """Updates the roster and assignments available in the Team Management screen."""
        try:
            eng_df = self.model.db.get_engineers_df()
            self.view.team_screen.populate_roster(eng_df)

            raw_df = self.model.get_raw_df()
            if not raw_df.empty and 'RAW_ASSIGNED' in raw_df.columns:
                raw_names: set[str] = {str(x).strip().upper() for x in raw_df['RAW_ASSIGNED'].unique() if
                                       str(x).strip().upper() not in ('', 'UNASSIGNED', 'NAN')}

                configured_names: set[str] = {str(x).strip().upper() for x in
                                              eng_df['name'].unique()} if not eng_df.empty else set()

                unconfigured: list[str] = sorted(list(raw_names - configured_names))
                configured_list: list[str] = sorted(list(configured_names))

                combo = self.view.team_screen.inp_name
                combo.blockSignals(True)
                combo.clear()
                combo.addItems(unconfigured + configured_list)
                combo.blockSignals(False)
        except Exception as e:  # pyrefly: ignore[broad-except]
            logger.exception(f"CRITICAL ERROR in refresh_team_view: {e}")

    def handle_save_engineer(self, name: str, team: str, color: str) -> None:
        """Saves engineer configurations from the Team Management screen."""
        self.model.db.upsert_team(team, 0.0)
        self.model.db.upsert_engineer(name, team, color)
        if hasattr(self.view, 'show_status'): self.view.show_status(f"Saved configuration for {name}.", 3000)
        self.refresh_team_view()

    def handle_engineer_selected(self, engineer_name: str) -> None:
        """Generates analytics for a specifically selected engineer."""
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

    def update_kpi_variances_locally(self, start_x: float, est_days_str: str, pto_dates: Optional[list[str]] = None) -> None:
        """Locally updates the KPI panel text during a visual drag event."""
        day_zero = self.view.gantt_screen.day_zero
        if not day_zero:
            return

        start_date_raw = day_zero + pd.tseries.offsets.BusinessDay(round(start_x / self.day_width))
        days = int(est_days_str) if est_days_str.isdigit() else 5

        adjusted_days = days - 1 if days > 0 else days
        end_date = CalendarEngine.shift_date(start_date_raw, adjusted_days, pto_dates)

        if end_date is None:
            return

        due_date_str = self.view.kpi_eng_due.text()
        if due_date_str and due_date_str != '--':
            try:
                var = CalendarEngine.get_working_days_variance(end_date, pd.to_datetime(due_date_str), pto_dates)
                self.view.kpi_eng_var.setText(f"{var} days")
            except ValueError:
                pass

        esd_str = self.view.kpi_esd.text()
        if esd_str and esd_str != '--':
            try:
                var_esd = CalendarEngine.get_working_days_variance(end_date, pd.to_datetime(esd_str), pto_dates)
                self.view.kpi_esd_var.setText(f"{var_esd} days")
            except ValueError:
                pass

    def handle_block_dropped(self, target_id: str, new_x: float, new_width: float, is_parent: bool,
                             delta_x: float = 0.0, delta_w: float = 0.0) -> None:
        """Processes logic for when a Gantt block finishes being visually dragged."""
        day_zero = self.view.gantt_screen.day_zero
        if not day_zero:
            return
        day_width = self.view.gantt_screen.day_width

        # Captures the multi-selection from the scene to prevent dropping it on redraw.
        restore_ids = [target_id]
        try:
            if self.view.gantt_scene:
                scene_selected = [
                    item.data.get('PROJECT_ID') if item.is_parent else item.data.get('SMART_ID')
                    for item in self.view.gantt_scene.selectedItems() if isinstance(item, GanttBlock)
                ]
                scene_selected = [tid for tid in scene_selected if tid and str(tid).lower() != 'nan']
                if scene_selected:
                    restore_ids = list(set(scene_selected + [target_id]))
        except Exception:  # pyrefly: ignore[broad-except]
            pass

        mask = self.current_plan_df['SMART_ID'] == target_id
        assignee = self.current_plan_df.loc[mask, 'ASSIGNED TO'].values[0] if not is_parent else ""
        safe_assignee = str(assignee).strip().title()
        pto_dates = self.pto_dict.get(safe_assignee, []) if hasattr(self, 'pto_dict') and self.pto_dict else []

        if not is_parent:
            new_date_raw = day_zero + pd.tseries.offsets.BusinessDay(round(new_x / day_width))
            new_start_pd = CalendarEngine.shift_date(new_date_raw, 0, pto_dates)

            if new_start_pd is None:
                self._rebuild_and_render_canvas(restore_ids)
                return

            start_date_str = f"{new_start_pd.month}/{new_start_pd.day}/{new_start_pd.year}"

            self.current_plan_df.loc[mask, 'EST START DATE'] = start_date_str
            self.history.stage_edit(target_id, {'MAN_START_DATE': start_date_str})

            est_days_str = str(self.current_plan_df.loc[mask, 'EST DAYS'].values[0])
            days_val = int(est_days_str) if est_days_str.isdigit() else 5
            adjusted_days = days_val - 1 if days_val > 0 else days_val

            new_end_pd = CalendarEngine.shift_date(new_start_pd, adjusted_days, pto_dates)

            if new_end_pd is not None:
                self.current_plan_df.loc[
                    mask, 'EST END DATE'] = f"{new_end_pd.month}/{new_end_pd.day}/{new_end_pd.year}"

            if abs(delta_w) > 0.1:
                visual_days = max(1, round(new_width / day_width))
                end_date_raw = new_date_raw + pd.tseries.offsets.BusinessDay(visual_days - 1)

                raw_work_days = CalendarEngine.get_working_days_duration(new_start_pd, end_date_raw, pto_dates)
                new_days_str = str(max(1, raw_work_days))

                self.current_plan_df.loc[mask, 'EST DAYS'] = new_days_str
                self.history.stage_edit(target_id, {'MAN_EST_DAYS': new_days_str})

                if hasattr(self, 'update_kpi_variances_locally'):
                    self.update_kpi_variances_locally(new_x, new_days_str, pto_dates)

        else:
            if abs(delta_x) < 0.1:
                self._rebuild_and_render_canvas(restore_ids)
                return

            mask = self.current_plan_df['PROJECT_ID'] == target_id
            children = self.current_plan_df[mask]

            delta_days_visual = round(delta_x / day_width)

            parent_starts = pd.to_datetime(children['EST START DATE'], errors='coerce').dropna()
            if parent_starts.empty:
                self._rebuild_and_render_canvas(restore_ids)
                return

            old_parent_start = parent_starts.min()

            new_parent_start_safe = CalendarEngine.shift_date(old_parent_start, delta_days_visual)

            if new_parent_start_safe is None:
                self._rebuild_and_render_canvas(restore_ids)
                return

            shift_working_days = CalendarEngine.get_working_days_variance(old_parent_start, new_parent_start_safe)

            if shift_working_days == 0:
                self._rebuild_and_render_canvas(restore_ids)
                return

            bulk_edits = {}
            for _, child in children.iterrows():
                child_smart_id = child['SMART_ID']

                if str(child.get('ENG START DATE', '')).strip():
                    continue

                old_child_start = pd.to_datetime(child.get('EST START DATE', pd.NaT))
                if pd.isna(old_child_start):
                    continue

                new_child_pd = CalendarEngine.shift_date(old_child_start, shift_working_days)

                if new_child_pd is None:
                    continue

                start_date_str = f"{new_child_pd.month}/{new_child_pd.day}/{new_child_pd.year}"

                bulk_edits[child_smart_id] = {'MAN_START_DATE': start_date_str}
                c_mask = self.current_plan_df['SMART_ID'] == child_smart_id
                self.current_plan_df.loc[c_mask, 'EST START DATE'] = start_date_str

            if bulk_edits:
                self.history.stage_bulk_edits(bulk_edits)

        # Restores the group selection after the math calculates.
        self._rebuild_and_render_canvas(restore_ids)

        if hasattr(self.view, 'show_status'):
            self.view.show_status("Unsaved Schedule edit. Press Ctrl+S to Calculate & Save.", 5000)