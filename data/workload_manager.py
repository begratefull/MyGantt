import numpy as np
import pandas as pd
from typing import Dict, Any

from data.database import DatabaseManager
from data.excel_parser import ExcelParser


class WorkloadManager:
    def __init__(self):
        self.db = DatabaseManager()
        self.parser = ExcelParser()

        # Initialize the database with the expected columns from the parser
        self.db.init_db(self.parser.unique_expected_cols)

    def sync_from_excel(self, file_path: str):
        """Passes the file to the parser, then saves the result to the DB."""
        df, error_msg = self.parser.parse_file(file_path)
        if df is None:
            return False, error_msg

        self.db.replace_raw_workload(df, self.parser.unique_expected_cols, list(df.columns))
        return True, ""

    def commit_overrides(self, staged_edits_dict: Dict[str, Dict[str, Any]]):
        """Passes manual user edits down to the database layer."""
        self.db.save_overrides(staged_edits_dict)

    def get_raw_df(self) -> pd.DataFrame:
        return self.db.get_raw_df()

    def get_application_data(self, staged_edits=None):
        """Builds the final DataFrame for the app, line by line."""
        raw_df = self.db.get_raw_df()
        over_df = self.db.get_saved_overrides_df()

        if raw_df.empty:
            return raw_df

        # 1. Merge raw data with saved overrides
        df = pd.merge(raw_df, over_df, on="SMART_ID", how="left").fillna("")

        # 2. Apply any staged (unsaved) edits currently in memory
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
            lambda r: r['MAN_ASSIGNED'] if str(r.get('MAN_ASSIGNED', '')).strip() else r['RAW_ASSIGNED'], axis=1)
        df['ENG START DATE'] = df['RAW_START_DATE']

        # --- UPDATED LOGIC: Automate Quote & Approval Defaults ---
        # Convert due dates to actual datetime objects so we can do math on them
        due_dates_dt = pd.to_datetime(df['ENG DUE DATE'], errors='coerce')

        # Subtract 1 business day so the 1-day task ENDS on the due date
        calc_starts = (due_dates_dt - pd.tseries.offsets.BusinessDay(1)).dt.strftime('%m/%d/%Y').fillna('')

        # Identify lines where the requirement is a Quote or Approval
        is_quote_app = df['REQUIREMENT'].str.contains('QUOT|APP', case=False, na=False)

        # Determine the fallback dates and days
        fallback_start_dates = np.where(is_quote_app & due_dates_dt.notna(), calc_starts, df['RAW_START_DATE'])
        fallback_days = np.where(is_quote_app, '1', '5')

        # Apply manual overrides if present, otherwise use fallbacks
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

        # Create a Parent ID so we know which lines belong to which order/quote
        df['PROJECT_ID'] = df.apply(
            lambda x: str(x['ORDER NUMBER']).strip() if str(x['ORDER NUMBER']).strip() else str(x['QUOTE NO']).strip(),
            axis=1)
        df['PROJECT_ID'] = df.apply(lambda x: x['PROJECT_ID'] if x['PROJECT_ID'] else x['SMART_ID'], axis=1)
        df['LINE_COUNT'] = 1


        # 4. Calculate Business Day Variances (Vectorized for speed)
        starts_dt = pd.to_datetime(df['EST START DATE'], errors='coerce')
        est_days_num = pd.to_numeric(df['EST DAYS'], errors='coerce').fillna(5).astype(int)
        esd_dt = pd.to_datetime(df['ESD'], errors='coerce')
        eng_due_dt = pd.to_datetime(df['ENG DUE DATE'], errors='coerce')
        comp_date_dt = pd.to_datetime(df['COMPLETE DATE'], errors='coerce')
        date_to_eng_dt = pd.to_datetime(df['DATE TO ENG'], errors='coerce')

        df['EST END DATE'] = ""
        valid_starts = starts_dt.notna()
        if valid_starts.any():
            starts_np = starts_dt[valid_starts].values.astype('datetime64[D]')
            days_np = est_days_num[valid_starts].values
            ends_np = np.busday_offset(starts_np, days_np)
            df.loc[valid_starts, 'EST END DATE'] = pd.to_datetime(ends_np).strftime('%m/%d/%Y').tolist()

        ends_dt = pd.to_datetime(df['EST END DATE'], errors='coerce')

        def calc_var_vectorized(start_dates, target_dates):
            result_array = np.full(len(df), "", dtype=object)
            valid = start_dates.notna() & target_dates.notna()
            if valid.any():
                s_np = start_dates[valid].values.astype('datetime64[D]')
                t_np = target_dates[valid].values.astype('datetime64[D]')
                diff = np.busday_count(s_np, t_np)
                result_array[valid] = [f"{int(d)} days" for d in diff]
            return result_array

        df['EST ESD VARIANCE'] = calc_var_vectorized(ends_dt, esd_dt)
        df['EST ENG VARIANCE'] = calc_var_vectorized(ends_dt, eng_due_dt)
        df['COMPLETION VARIANCE'] = calc_var_vectorized(comp_date_dt, eng_due_dt)
        df['QUEUE_DAYS'] = calc_var_vectorized(date_to_eng_dt, starts_dt)

        comp_or_est_end_dt = comp_date_dt.combine_first(ends_dt)
        df['PROCESS_DAYS'] = calc_var_vectorized(starts_dt, comp_or_est_end_dt)

        planning_headers = [
            "PROJECT_ID", "SMART_ID", "TYPE", "REQUIREMENT", "QUOTE NO", "ORDER NUMBER", "PROJECT NAME", "STATUS",
            "ASSIGNED TO", "DATE TO ENG", "ENG START DATE", "EST START DATE", "EST DAYS", "EST END DATE",
            "ESD", "ENG DUE DATE", "COMPLETE DATE",
            "EST ESD VARIANCE", "EST ENG VARIANCE", "COMPLETION VARIANCE",
            "QUEUE_DAYS", "PROCESS_DAYS", "SELL $", "LINE_COUNT",
            "LUMINARIE SPECIFICATION", "PART NUMBER", "FAMILY", "CATALOG CODE", "CATALOG"
        ]

        available_cols = [c for c in planning_headers if c in df.columns]
        return df[available_cols]