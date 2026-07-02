"""
Contains QThread worker classes for background processing.
This offloads heavy I/O operations and Pandas calculations from the main UI thread,
ensuring the application remains highly responsive during data refreshes.
"""

import logging
import re
from typing import Optional, List, Any, Dict

import pandas as pd
from PySide6.QtCore import QThread, Signal

from logic.constants import AppConstants
from logic.calendar_engine import CalendarEngine

logger = logging.getLogger(__name__)


class SyncWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, model: Any, excel_path: str) -> None:
        super().__init__()
        self.model = model
        self.excel_path = excel_path

    def run(self) -> None:
        try:
            success, error_msg = self.model.sync_from_excel(self.excel_path)
            self.finished.emit(success, error_msg)
        except Exception as e:
            logger.exception(f"Critical error encountered during SyncWorker execution: {e}")
            self.finished.emit(False, str(e))


class DataRefreshWorker(QThread):
    data_ready = Signal(object, object, object, object)

    def __init__(self, model: Any, staged_edits: Dict[str, Any], team_filter: str,
                 req_filter: str, status_filter: str, sort_by: str,
                 maintain_ids: Optional[List[str]], pto_dict: Optional[Dict[str, List[str]]] = None) -> None:
        super().__init__()
        self.model = model
        self.staged_edits = staged_edits
        self.team_filter = team_filter
        self.req_filter = req_filter
        self.status_filter = status_filter
        self.sort_by = sort_by
        self.maintain_ids = maintain_ids
        self.pto_dict = pto_dict if pto_dict else {}

    def _apply_actual_start_anchoring(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Locks the estimated days and recalculates the estimated end date
        when an actual engineering start date is populated, factoring in PTO and Holidays.
        """
        if df.empty or 'ENG START DATE' not in df.columns or 'EST DAYS' not in df.columns:
            return df

        try:
            eng_starts = pd.to_datetime(df['ENG START DATE'], errors='coerce')
            active_started_mask = eng_starts.notna() & (df['STATUS'].str.strip().str.upper() != 'COMPLETE')

            if active_started_mask.any():
                # 1. Sync the start date immediately so the block snaps to the actual start
                df.loc[active_started_mask, 'EST START DATE'] = df.loc[active_started_mask, 'ENG START DATE']

                # 2. Use the fast vectorized engine to push the end date forward based on locked EST DAYS
                assignee_series = df.loc[active_started_mask, 'ASSIGNED TO']

                df.loc[active_started_mask, 'EST END DATE'] = CalendarEngine.calculate_end_dates_vectorized(
                    df.loc[active_started_mask, 'EST START DATE'],
                    df.loc[active_started_mask, 'EST DAYS'],
                    assignee_series,
                    self.pto_dict
                )
        except Exception as e:
            logger.warning(f"Error applying start date anchoring: {e}")

        return df

    def run(self) -> None:
        try:
            raw_df = self.model.get_raw_df()

            plan_df = self.model.get_application_data(self.staged_edits)
            plan_df = self._apply_actual_start_anchoring(plan_df)

            actual_df = self.model.get_application_data(ignore_overrides=True)
            actual_df = self._apply_actual_start_anchoring(actual_df)

            if plan_df.empty:
                self.data_ready.emit(raw_df, plan_df, actual_df, plan_df)
                return

            full_plan_df = plan_df.copy()

            if self.team_filter != "All Teams":
                eng_df = self.model.db.get_engineers_df()
                team_map = {}
                if not eng_df.empty:
                    team_map = {str(k).strip().upper(): str(v).strip().upper()
                                for k, v in zip(eng_df['name'], eng_df['team_name'])}

                def get_team(row: pd.Series) -> str:
                    name = str(row.get('ASSIGNED TO', '')).strip().upper()
                    if name and name not in [AppConstants.UNASSIGNED_LABEL, 'NAN', '']:
                        return team_map.get(name, AppConstants.UNASSIGNED_LABEL)

                    line_type = str(row.get('TYPE', '')).strip().upper()

                    if line_type in AppConstants.STANDARD_LINE_TYPES:
                        return AppConstants.STANDARD_TEAM_LABEL
                    elif line_type in AppConstants.CUSTOM_LINE_TYPES:
                        return AppConstants.CUSTOM_TEAM_LABEL

                    return AppConstants.UNASSIGNED_LABEL

                plan_df['CALC_TEAM'] = plan_df.apply(get_team, axis=1)
                plan_df = plan_df[plan_df['CALC_TEAM'] == self.team_filter.strip().upper()].copy()
                plan_df = plan_df.drop(columns=['CALC_TEAM'])

            # --- THE DATA BLEED FIX: Regex Filter interception ---
            if self.req_filter != "All Reqs":
                if re.search(AppConstants.PROD_REQ_PATTERN, self.req_filter, re.IGNORECASE):
                    plan_df = plan_df[plan_df['REQUIREMENT'].str.contains(AppConstants.PROD_REQ_PATTERN, case=False, na=False, regex=True)]
                else:
                    plan_df = plan_df[plan_df['REQUIREMENT'].str.contains(self.req_filter, case=False, na=False)]

            # === Project-Aware Status Filtering ===
            if self.status_filter == "Active":
                active_mask = plan_df['STATUS'].str.strip().str.upper() != 'COMPLETE'
                active_projects = plan_df[active_mask]['PROJECT_ID'].unique()
                plan_df = plan_df[plan_df['PROJECT_ID'].isin(active_projects)]

            elif self.status_filter == "Complete":
                active_mask = plan_df['STATUS'].str.strip().str.upper() != 'COMPLETE'
                active_projects = plan_df[active_mask]['PROJECT_ID'].unique()
                plan_df = plan_df[~plan_df['PROJECT_ID'].isin(active_projects)]

            if self.maintain_ids is not None:
                current_ids = self.maintain_ids
                plan_df = plan_df.set_index('SMART_ID')
                valid_ids = [uid for uid in current_ids if uid in plan_df.index]
                new_ids = [uid for uid in plan_df.index if uid not in current_ids]
                plan_df = plan_df.loc[valid_ids + new_ids].reset_index()
            else:
                if self.sort_by == "Eng Due Date":
                    plan_df['SORT_DATE'] = pd.to_datetime(plan_df['ENG DUE DATE'], errors='coerce')
                elif self.sort_by == "ESD":
                    plan_df['SORT_DATE'] = pd.to_datetime(plan_df['ESD'], errors='coerce')
                else:
                    plan_df['SORT_DATE'] = pd.to_datetime(plan_df['ENG START DATE'], errors='coerce').combine_first(
                        pd.to_datetime(plan_df['EST START DATE'], errors='coerce')).combine_first(
                        pd.to_datetime(plan_df['ENG DUE DATE'], errors='coerce'))

                    plan_df = plan_df.sort_values(
                        by=['SORT_DATE', 'STATUS', 'PROJECT_ID', 'SMART_ID'],
                        ascending=[True, True, True, True]
                    )
                    plan_df = plan_df.drop(columns=['SORT_DATE'])

            self.data_ready.emit(raw_df, plan_df.reset_index(drop=True), actual_df, full_plan_df)

        except Exception as e:
            logger.exception(f"DataRefreshWorker encountered a fatal error during data processing: {e}")