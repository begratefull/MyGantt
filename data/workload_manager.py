import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple, Optional
import re
import logging

from data.database import DatabaseManager
from data.excel_parser import ExcelParser
from logic.constants import AppConstants
from logic.calendar_engine import CalendarEngine

logger = logging.getLogger(__name__)


class WorkloadManager:
    """
    Manages the processing, synthesis, and synchronization of raw Excel data
    with manual application overrides and side-work tasks.
    """

    def __init__(self) -> None:
        self.db = DatabaseManager()
        self.parser = ExcelParser()
        self.db.init_db(self.parser.unique_expected_cols)

    def sync_from_excel(self, file_path: str) -> Tuple[bool, str]:
        """
        Passes the file to the parser, then saves the result to the DB.

        Args:
            file_path (str): The absolute path to the synced Excel file.

        Returns:
            Tuple[bool, str]: Success boolean and an error message if applicable.
        """
        try:
            df, holidays, error_msg = self.parser.parse_file(file_path)
            if df is None:
                return False, error_msg

            self.db.replace_raw_workload(df, self.parser.unique_expected_cols, list(df.columns))
            self.db.replace_holidays(holidays)

            return True, ""
        except Exception as e:
            logger.exception(f"Unexpected error during Excel synchronization: {e}")
            return False, str(e)

    def commit_overrides(self, staged_edits_dict: Dict[str, Dict[str, Any]]) -> None:
        """
        Passes manual user edits down to the database layer.

        Args:
            staged_edits_dict (Dict[str, Dict[str, Any]]): Dictionary mapping SMART_IDs to modified attributes.
        """
        try:
            self.db.save_overrides(staged_edits_dict)
        except Exception as e:
            logger.exception(f"Failed to commit overrides to the database: {e}")

    def get_raw_df(self) -> pd.DataFrame:
        """Returns the unmodified raw synced data from the database."""
        return self.db.get_raw_df()

    def get_application_data(self, staged_edits: Optional[Dict[str, Any]] = None,
                             ignore_overrides: bool = False) -> pd.DataFrame:
        """
        Builds the final DataFrame for the app by appending manual tasks
        and injecting user overrides line by line using fast vectorized operations.

        Args:
            staged_edits (Optional[Dict]): Dictionary of unsaved edits active in the session.
            ignore_overrides (bool): If true, strips out manually assigned states (used for base analytics).

        Returns:
            pd.DataFrame: The fully enriched and processed application dataset.
        """
        try:
            raw_df = self.db.get_raw_df()
            manual_df = self.db.get_manual_tasks_df()

            # Safely combine raw Excel workload with manually created side-work tasks
            if not manual_df.empty:
                if not raw_df.empty:
                    combined_df = pd.concat([raw_df, manual_df], ignore_index=True).fillna("")
                else:
                    combined_df = manual_df.copy()
            else:
                combined_df = raw_df.copy()

            if combined_df.empty:
                return combined_df

            # Evaluate overrides and staged edits
            if ignore_overrides:
                df = combined_df.copy()
                df['MAN_ASSIGNED'] = ""
                df['MAN_START_DATE'] = ""
                df['MAN_EST_DAYS'] = ""
                df['MAN_STATUS'] = ""
            else:
                over_df = self.db.get_saved_overrides_df()
                if not over_df.empty:
                    df = pd.merge(combined_df, over_df, on="SMART_ID", how="left").fillna("")
                else:
                    df = combined_df.copy()
                    df['MAN_ASSIGNED'] = ""
                    df['MAN_EST_DAYS'] = ""
                    df['MAN_START_DATE'] = ""
                    df['MAN_STATUS'] = ""

                if staged_edits:
                    staged_df = pd.DataFrame.from_dict(staged_edits, orient='index')
                    staged_df.index.name = 'SMART_ID'
                    staged_df = staged_df.reset_index()

                    df = df.set_index('SMART_ID')
                    staged_df = staged_df.set_index('SMART_ID')
                    df.update(staged_df)
                    df = df.reset_index()

            # Handle Custom Overrides mapping securely
            df['ASSIGNED TO'] = df.apply(
                lambda r: r.get('MAN_ASSIGNED') if str(r.get('MAN_ASSIGNED', '')).strip()
                else (r.get('RAW_ASSIGNED') if str(r.get('RAW_ASSIGNED', '')).strip() else r.get('ASSIGNED TO', '')),
                axis=1
            )

            # Prioritize MAN_STATUS to allow manual completion overrides on any line
            if 'STATUS' not in df.columns:
                df['STATUS'] = ""

            df['STATUS'] = df.apply(
                lambda r: r.get('MAN_STATUS') if str(r.get('MAN_STATUS', '')).strip() else r.get('STATUS', ''),
                axis=1
            )

            df['ENG START DATE'] = df.get('RAW_START_DATE', '')

            # Calculate fallback starts and days
            due_dates_dt = pd.to_datetime(df.get('ENG DUE DATE', pd.Series(dtype=str)), errors='coerce')
            calc_starts = (due_dates_dt - pd.tseries.offsets.BusinessDay(1)).dt.strftime('%m/%d/%Y').fillna('')

            req_col = df.get('REQUIREMENT', pd.Series('', index=df.index, dtype=str))
            if not isinstance(req_col, pd.Series):
                req_col = pd.Series(req_col, index=df.index, dtype=str)

            is_quote_app = req_col.str.contains(AppConstants.QUOTE_REQ_PATTERN, case=False, na=False)
            cond_quote = (is_quote_app & due_dates_dt.notna()).to_numpy(dtype=bool)
            calc_starts_np = calc_starts.to_numpy(dtype=object)

            raw_start_col = df.get('RAW_START_DATE', pd.Series('', index=df.index, dtype=str))
            if not isinstance(raw_start_col, pd.Series):
                raw_start_col = pd.Series(raw_start_col, index=df.index, dtype=str)
            raw_starts_np = raw_start_col.to_numpy(dtype=object)

            fallback_start_dates = np.where(cond_quote, calc_starts_np, raw_starts_np).tolist()
            is_quote_bool_np = is_quote_app.to_numpy(dtype=bool)
            fallback_days = np.where(is_quote_bool_np, str(AppConstants.DEFAULT_QUOTE_DAYS),
                                     str(AppConstants.DEFAULT_EST_DAYS)).tolist()

            cond_man_start = (df['MAN_START_DATE'].str.strip() != '').to_numpy(dtype=bool)
            man_starts_np = df['MAN_START_DATE'].to_numpy(dtype=object)

            df['EST START DATE'] = np.where(cond_man_start, man_starts_np, fallback_start_dates).tolist()

            cond_man_est = (df['MAN_EST_DAYS'].str.strip() != '').to_numpy(dtype=bool)
            man_est_np = df['MAN_EST_DAYS'].to_numpy(dtype=object)

            df['EST DAYS'] = np.where(cond_man_est, man_est_np, fallback_days).tolist()

            # Resolve Project Grouping Identifiers
            df['PROJECT_ID'] = df.apply(
                lambda x: str(x.get('ORDER NUMBER', '')).strip() if str(x.get('ORDER NUMBER', '')).strip() else str(
                    x.get('QUOTE NO', '')).strip(),
                axis=1)
            df['PROJECT_ID'] = df.apply(lambda x: x['PROJECT_ID'] if x['PROJECT_ID'] else x.get('SMART_ID', ''), axis=1)
            df['LINE_COUNT'] = 1

            # Execute Vectorized End Date Generation
            starts_dt = pd.to_datetime(df['EST START DATE'], errors='coerce')
            esd_dt = pd.to_datetime(df.get('ESD', pd.Series(dtype=str)), errors='coerce')
            eng_due_dt = pd.to_datetime(df.get('ENG DUE DATE', pd.Series(dtype=str)), errors='coerce')
            comp_date_dt = pd.to_datetime(df.get('COMPLETE DATE', pd.Series(dtype=str)), errors='coerce')
            date_to_eng_dt = pd.to_datetime(df.get('DATE TO ENG', pd.Series(dtype=str)), errors='coerce')

            df['EST END DATE'] = CalendarEngine.calculate_end_dates_vectorized(df['EST START DATE'], df['EST DAYS'])
            ends_dt = pd.to_datetime(df['EST END DATE'], errors='coerce')

            def calc_var_formatted(s1: pd.Series, s2: pd.Series) -> list:
                raw_vars = CalendarEngine.calculate_variance_vectorized(s1, s2)
                return [f"{int(d)} days" if pd.notna(d) else "" for d in raw_vars]

            df['EST ESD VARIANCE'] = calc_var_formatted(ends_dt, esd_dt)
            df['EST ENG VARIANCE'] = calc_var_formatted(ends_dt, eng_due_dt)
            df['COMPLETION VARIANCE'] = calc_var_formatted(comp_date_dt, eng_due_dt)
            df['QUEUE_DAYS'] = calc_var_formatted(date_to_eng_dt, starts_dt)

            comp_or_est_end_dt = comp_date_dt.combine_first(ends_dt)
            df['PROCESS_DAYS'] = calc_var_formatted(starts_dt, comp_or_est_end_dt)

            lum_col = 'LUMINARIE SPECIFICATION'

            def extract_family_robust(lum_str: Any) -> str:
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

        except Exception as e:
            logger.exception(f"Critical error building application data matrix: {e}")
            return pd.DataFrame()