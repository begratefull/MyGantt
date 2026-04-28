"""
Contains QThread worker classes for background processing.
This offloads heavy I/O operations and Pandas calculations from the main UI thread,
ensuring the application remains highly responsive during data refreshes.
"""

import traceback
from typing import Optional, List, Any, Dict

import pandas as pd
from PySide6.QtCore import QThread, Signal


class SyncWorker(QThread):
    """
    Handles the background syncing of the Excel file into the SQLite database.
    """
    finished = Signal(bool, str)

    def __init__(self, model: Any, excel_path: str) -> None:
        super().__init__()
        self.model = model
        self.excel_path = excel_path

    def run(self) -> None:
        """Executes the workload manager's sync logic and emits success/error states."""
        success, error_msg = self.model.sync_from_excel(self.excel_path)
        self.finished.emit(success, error_msg)


class DataRefreshWorker(QThread):
    """
    Handles the background querying, filtering, and sorting of data
    for the Gantt chart and Dashboard views.
    """
    # Emits: (raw_df, filtered_plan_df, full_dashboard_df)
    data_ready = Signal(object, object, object)

    def __init__(self, model: Any, staged_edits: Dict[str, Any], team_filter: str,
                 req_filter: str, status_filter: str, sort_by: str, maintain_ids: Optional[List[str]]) -> None:
        super().__init__()
        self.model = model
        self.staged_edits = staged_edits
        self.team_filter = team_filter
        self.req_filter = req_filter
        self.status_filter = status_filter

        # --- ADDED: Capture requested sorting method ---
        self.sort_by = sort_by
        self.maintain_ids = maintain_ids

    def run(self) -> None:
        """Fetches data, applies dynamic routing logic, and emits DataFrames to the View."""
        try:
            raw_df = self.model.get_raw_df()
            plan_df = self.model.get_application_data(self.staged_edits)

            if plan_df.empty:
                self.data_ready.emit(raw_df, plan_df, plan_df)
                return

            # Dashboard gets the full payload to do its own local filtering
            full_dashboard_df = plan_df.copy()

            # --- DYNAMIC TEAM & UNASSIGNED FILTERING FOR GANTT ---
            if self.team_filter != "All Teams":
                eng_df = self.model.db.get_engineers_df()
                team_map = {}
                if not eng_df.empty:
                    team_map = {str(k).strip().upper(): str(v).strip().upper()
                                for k, v in zip(eng_df['name'], eng_df['team_name'])}

                def get_team(row: pd.Series) -> str:
                    name = str(row.get('ASSIGNED TO', '')).strip().upper()
                    if name and name not in ['UNASSIGNED', 'NAN', '']:
                        return team_map.get(name, "UNASSIGNED")

                    line_type = str(row.get('TYPE', '')).strip().upper()
                    if line_type in ['STD', 'STD-M', 'PART']:
                        return "STANDARD TEAM"
                    elif line_type in ['MOD', 'CUS', 'PART-MC']:
                        return "CUSTOM TEAM"

                    return "UNASSIGNED"

                plan_df['CALC_TEAM'] = plan_df.apply(get_team, axis=1)
                plan_df = plan_df[plan_df['CALC_TEAM'] == self.team_filter.strip().upper()].copy()
                plan_df = plan_df.drop(columns=['CALC_TEAM'])

            # --- REQUIREMENT & STATUS FILTERING ---
            if self.req_filter != "All Reqs":
                plan_df = plan_df[plan_df['REQUIREMENT'].str.contains(self.req_filter, case=False, na=False)]

            if self.status_filter == "Active":
                plan_df = plan_df[plan_df['STATUS'].str.strip().str.upper() != 'COMPLETE']
            elif self.status_filter == "Complete":
                plan_df = plan_df[plan_df['STATUS'].str.strip().str.upper() == 'COMPLETE']

            # --- SORTING & ID MAINTENANCE ---
            if self.maintain_ids is not None:
                current_ids = self.maintain_ids
                plan_df = plan_df.set_index('SMART_ID')
                valid_ids = [uid for uid in current_ids if uid in plan_df.index]
                new_ids = [uid for uid in plan_df.index if uid not in current_ids]
                plan_df = plan_df.loc[valid_ids + new_ids].reset_index()
            else:

                # --- NEW: Dynamic Sorting based on UI selection ---
                if self.sort_by == "Eng Due Date":
                    plan_df['SORT_DATE'] = pd.to_datetime(plan_df['ENG DUE DATE'].replace('', pd.NaT))
                elif self.sort_by == "ESD":
                    plan_df['SORT_DATE'] = pd.to_datetime(plan_df['ESD'].replace('', pd.NaT))
                else:
                    # Default: "Start Date"
                    plan_df['SORT_DATE'] = pd.to_datetime(plan_df['ENG START DATE'].replace('', pd.NaT)).combine_first(
                        pd.to_datetime(plan_df['EST START DATE'].replace('', pd.NaT))).combine_first(
                        pd.to_datetime(plan_df['ENG DUE DATE'].replace('', pd.NaT)))

                # Secondary sorts ensure that project groupings always stay physically glued together!
                plan_df = plan_df.sort_values(by=['STATUS', 'SORT_DATE', 'PROJECT_ID', 'SMART_ID'], ascending=[True, True, True, True])
                plan_df = plan_df.drop(columns=['SORT_DATE'])

            self.data_ready.emit(raw_df, plan_df.reset_index(drop=True), full_dashboard_df)

        except Exception as e:
            print(f"Worker Error: {e}\n{traceback.format_exc()}")