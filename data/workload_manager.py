import numpy as np
import pandas as pd
from typing import Dict, Any
import re
import logging

from data.database import DatabaseManager
from data.excel_parser import ExcelParser
from logic.constants import AppConstants
from logic.calendar_engine import CalendarEngine  # <-- New Central Engine Imported Here!

logger = logging.getLogger(__name__)


class WorkloadManager:
    def __init__(self):
        self.db = DatabaseManager()
        self.parser = ExcelParser()

        # Initialize the database with the expected columns from the parser
        self.db.init_db(self.parser.unique_expected_cols)

    def sync_from_excel(self, file_path: str):
        """Passes the file to the parser, then saves the result to the DB."""
        df, holidays, error_msg = self.parser.parse_file(file_path)
        if df is None:
            return False, error_msg

        self.db.replace_raw_workload(df, self.parser.unique_expected_cols, list(df.columns))

        self.db.replace_holidays(holidays)

        return True, ""

    def commit_overrides(self, staged_edits_dict: Dict[str, Dict[str, Any]]):
        """Passes manual user edits down to the database layer."""
        self.db.save_overrides(staged_edits_dict)

    def get_raw_df(self) -> pd.DataFrame:
        return self.db.get_raw_df()

    def get_application_data(self, staged_edits=None, ignore_overrides=False):
        """Builds the final DataFrame for the app, line by line."""
        raw_df = self.db.get_raw_df()
        if raw_df.empty:
            return raw_df

        # --- Generate pure actuals without Gantt ghosts if requested ---
        if ignore_overrides:
            df = raw_df.copy()
            df['MAN_ASSIGNED'] = ""
            df['MAN_START_DATE'] = ""
            df['MAN_EST_DAYS'] = ""
        else:
            over_df = self.db.get_saved_overrides_df()
            df = pd.merge(raw_df, over_df, on="SMART_ID", how="left").fillna("")

            if staged_edits:
                staged_df = pd.DataFrame.from_dict(staged_edits, orient='index')
                staged_df.index.name = 'SMART_ID'
                staged_df = staged_df.reset_index()

                df = df.set_index('SMART_ID')
                staged_df = staged_df.set_index('SMART_ID')
                df.update(staged_df)
                df = df.reset_index()

        # 3. Apply business logic for assignments and dates
        df['ASSIGNED TO'] = df.apply(
            lambda r: r['MAN_ASSIGNED'] if str(r.get('MAN_ASSIGNED', '')).strip() else r.get('RAW_ASSIGNED', ''),
            axis=1)
        df['ENG START DATE'] = df.get('RAW_START_DATE', '')

        due_dates_dt = pd.to_datetime(df.get('ENG DUE DATE', pd.Series(dtype=str)), errors='coerce')
        calc_starts = (due_dates_dt - pd.tseries.offsets.BusinessDay(1)).dt.strftime('%m/%d/%Y').fillna('')

        is_quote_app = df.get('REQUIREMENT', pd.Series(dtype=str)).str.contains(AppConstants.QUOTE_REQ_PATTERN,
                                                                                case=False, na=False)

        fallback_start_dates = np.where(is_quote_app & due_dates_dt.notna(), calc_starts, df.get('RAW_START_DATE', ''))
        fallback_days = np.where(is_quote_app, str(AppConstants.DEFAULT_QUOTE_DAYS), str(AppConstants.DEFAULT_EST_DAYS))

        df['EST START DATE'] = np.where(
            df['MAN_START_DATE'].str.strip() != '',
            df['MAN_START_DATE'],
            fallback_start_dates
        )

        df['EST DAYS'] = np.where(
            df['MAN_EST_DAYS'].str.strip() != '',
            df['MAN_EST_DAYS'],
            fallback_days
        )

        df['PROJECT_ID'] = df.apply(
            lambda x: str(x.get('ORDER NUMBER', '')).strip() if str(x.get('ORDER NUMBER', '')).strip() else str(
                x.get('QUOTE NO', '')).strip(),
            axis=1)
        df['PROJECT_ID'] = df.apply(lambda x: x['PROJECT_ID'] if x['PROJECT_ID'] else x.get('SMART_ID', ''), axis=1)
        df['LINE_COUNT'] = 1

        starts_dt = pd.to_datetime(df['EST START DATE'], errors='coerce')
        esd_dt = pd.to_datetime(df.get('ESD', pd.Series(dtype=str)), errors='coerce')
        eng_due_dt = pd.to_datetime(df.get('ENG DUE DATE', pd.Series(dtype=str)), errors='coerce')
        comp_date_dt = pd.to_datetime(df.get('COMPLETE DATE', pd.Series(dtype=str)), errors='coerce')
        date_to_eng_dt = pd.to_datetime(df.get('DATE TO ENG', pd.Series(dtype=str)), errors='coerce')

        # =========================================================
        # --- NEW CENTRALIZED ENGINE MATH ---
        # No more direct NumPy logic here. We let the CalendarEngine
        # crunch the arrays instantly.
        # =========================================================

        df['EST END DATE'] = CalendarEngine.calculate_end_dates_vectorized(df['EST START DATE'], df['EST DAYS'])

        ends_dt = pd.to_datetime(df['EST END DATE'], errors='coerce')

        def calc_var_formatted(s1, s2):
            raw_vars = CalendarEngine.calculate_variance_vectorized(s1, s2)
            # Format back to "X days" strings for the UI table
            return [f"{int(d)} days" if pd.notna(d) else "" for d in raw_vars]

        df['EST ESD VARIANCE'] = calc_var_formatted(ends_dt, esd_dt)
        df['EST ENG VARIANCE'] = calc_var_formatted(ends_dt, eng_due_dt)
        df['COMPLETION VARIANCE'] = calc_var_formatted(comp_date_dt, eng_due_dt)
        df['QUEUE_DAYS'] = calc_var_formatted(date_to_eng_dt, starts_dt)

        comp_or_est_end_dt = comp_date_dt.combine_first(ends_dt)
        df['PROCESS_DAYS'] = calc_var_formatted(starts_dt, comp_or_est_end_dt)

        # =========================================================

        lum_col = 'LUMINARIE SPECIFICATION'

        def extract_family_robust(lum_str):
            if pd.isna(lum_str) or not str(lum_str).strip():
                return 'UNKNOWN'

            s = str(lum_str).strip().upper()
            s = re.sub(r'^(REVISE|ETO\d*)[\.\u2026\s\-]*', '', s)
            s = re.sub(r'^SK[\.\u2026\s\-]*', '', s)

            family = s.split('-')[0].split(' ')[0].strip()
            return family if family else 'UNKNOWN'

        if lum_col in df.columns:
            df['FAMILY_PREFIX'] = df[lum_col].apply(extract_family_robust)
        else:
            df['FAMILY_PREFIX'] = 'UNKNOWN'

        planning_headers = [
            "PROJECT_ID", "SMART_ID", "TYPE", "REQUIREMENT", "QUOTE NO", "ORDER NUMBER", "PROJECT NAME", "STATUS",
            "ASSIGNED TO", "DATE TO ENG", "ENG START DATE", "EST START DATE", "EST DAYS", "EST END DATE",
            "ESD", "ENG DUE DATE", "COMPLETE DATE",
            "EST ESD VARIANCE", "EST ENG VARIANCE", "COMPLETION VARIANCE",
            "QUEUE_DAYS", "PROCESS_DAYS", "SELL $", "LINE_COUNT",
            "LUMINARIE SPECIFICATION", "PART NUMBER", "FAMILY", "CATALOG CODE", "CATALOG",
            "FAMILY_PREFIX"
        ]

        available_cols = [c for c in planning_headers if c in df.columns]
        return df[available_cols]