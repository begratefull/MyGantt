import hashlib
import os
import re
import shutil
import sqlite3
import logging
import numpy as np
from typing import Dict, Any

import pandas as pd

logging.basicConfig(
    filename='mygantt_errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


class DataManager:
    def __init__(self):
        base_path = os.path.dirname(__file__)
        self.db_path = os.path.join(base_path, "gantt_data.db")

        # --- BULLETPROOF HEADER MAPPING ---
        self.raw_header_mapping = {
            "ORDERNUMBER": "ORDER NUMBER",
            "LINEITEM": "LINE ITEM",
            "PRIORITY": "PRIORITY",
            "DATETOENG": "DATE TO ENG",
            "SHIPTONUMBERPROJECT": "PROJECT NAME",
            "INTERGRATIONREFERENCENUMBERQUOTE": "QUOTE NO",
            "INTEGRATIONREFERENCENUMBERQUOTE": "QUOTE NO",
            "SALESCONTACT": "SALES CONTACT",
            "TYPE": "TYPE",
            "CONFIGUREDSTRINGLUMINARIESPECIFICATION": "LUMINARIE SPECIFICATION",
            "SELL": "SELL $",
            "ASSIGNEDTO": "RAW_ASSIGNED",
            "ENGSTARTDATE": "RAW_START_DATE",
            "DUEDATE": "ENG DUE DATE",
            "COMPLETEDATE": "COMPLETE DATE",
            "SHIPDATE": "ESD",
            "REQUIREMENT": "REQUIREMENT",
            "REQUIRMENT": "REQUIREMENT",
            "STATUS": "STATUS"
        }

        self.valid_types = ['MOD', 'CUS', 'PART-MC']
        self.init_db()

    def init_db(self):
        """Initializes the strict two-layer database architecture."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            unique_cols = list(dict.fromkeys(self.raw_header_mapping.values()))
            raw_cols = ", ".join([f'"{h}" TEXT' for h in unique_cols])

            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS raw_workload (
                    "SMART_ID" TEXT PRIMARY KEY,
                    {raw_cols}
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_overrides (
                    "SMART_ID" TEXT PRIMARY KEY,
                    "MAN_ASSIGNED" TEXT,
                    "MAN_EST_DAYS" TEXT,
                    "MAN_START_DATE" TEXT
                )
            ''')
            conn.commit()

    @staticmethod
    def generate_smart_id(row):
        """Generates a crash-proof unique ID for every line item."""
        order = str(row.get('ORDER NUMBER', '')).strip()
        quote = str(row.get('QUOTE NO', '')).strip()
        line = str(row.get('LINE ITEM', '')).strip()

        if order and order.upper() not in ['NAN', '']:
            base = order
        elif quote and quote.upper() not in ['NAN', '']:
            base = quote
        else:
            project = str(row.get('PROJECT NAME', '')).strip()
            req = str(row.get('REQUIREMENT', '')).strip()
            fallback_str = f"{project}-{req}"

            short_hash = hashlib.md5(fallback_str.encode('utf-8')).hexdigest()[:6].upper()
            base = f"UNK-{short_hash}"

        if line and line.upper() not in ['NAN', '']:
            return f"{base}-{line}"
        return base

    def _get_raw_df(self):
        with sqlite3.connect(self.db_path) as conn:
            return pd.read_sql_query('SELECT * FROM raw_workload', conn).fillna("")

    def _get_saved_overrides_df(self):
        with sqlite3.connect(self.db_path) as conn:
            return pd.read_sql_query('SELECT * FROM user_overrides', conn).fillna("")

    def get_application_data(self, staged_edits=None):
        """
        The Master Data Compiler.
        Blends Layer 1 (Raw), Layer 2 (Saved DB), and Layer 2.5 (Unsaved Staged Edits).
        """
        raw_df = self._get_raw_df()
        over_df = self._get_saved_overrides_df()

        if raw_df.empty:
            return raw_df

        df = pd.merge(raw_df, over_df, on="SMART_ID", how="left").fillna("")

        if staged_edits:
            staged_df = pd.DataFrame.from_dict(staged_edits, orient='index')
            staged_df.index.name = 'SMART_ID'
            staged_df = staged_df.reset_index()

            df = df.set_index('SMART_ID')
            staged_df = staged_df.set_index('SMART_ID')
            df.update(staged_df)
            df = df.reset_index()

        df['ASSIGNED TO'] = df.apply(
            lambda r: r['MAN_ASSIGNED'] if str(r.get('MAN_ASSIGNED', '')).strip() else r['RAW_ASSIGNED'], axis=1)

        df['ENG START DATE'] = df['RAW_START_DATE']
        df['EST START DATE'] = df.apply(
            lambda r: r['MAN_START_DATE'] if str(r.get('MAN_START_DATE', '')).strip() else r['RAW_START_DATE'], axis=1)

        df['EST DAYS'] = df['MAN_EST_DAYS'].replace('', '5')

        df['PROJECT_ID'] = df.apply(lambda x: x['ORDER NUMBER'] if x['ORDER NUMBER'] else x['QUOTE NO'], axis=1)

        df['LINE_COUNT'] = 1

        agg_funcs = {
            'SMART_ID': 'first', 'TYPE': 'first', 'REQUIREMENT': 'first', 'PROJECT NAME': 'first',
            'QUOTE NO': 'first', 'ORDER NUMBER': 'first', 'STATUS': 'first', 'ESD': 'first',
            'ENG DUE DATE': 'first', 'COMPLETE DATE': 'first', 'ASSIGNED TO': 'first',
            'ENG START DATE': 'first', 'EST START DATE': 'first', 'EST DAYS': 'first',
            'LINE_COUNT': 'sum'
        }
        df = df.groupby('PROJECT_ID', as_index=False).agg(agg_funcs)

        # =========================================================
        # FIXED: VECTORIZED DATE & VARIANCE CALCULATIONS
        # By formatting and converting the numpy arrays to pure lists,
        # we completely sidestep Pandas' index-alignment bugs!
        # =========================================================

        starts_dt = pd.to_datetime(df['EST START DATE'], errors='coerce')
        est_days_num = pd.to_numeric(df['EST DAYS'], errors='coerce').fillna(5).astype(int)

        esd_dt = pd.to_datetime(df['ESD'], errors='coerce')
        eng_due_dt = pd.to_datetime(df['ENG DUE DATE'], errors='coerce')
        comp_date_dt = pd.to_datetime(df['COMPLETE DATE'], errors='coerce')

        # 1. Calculate EST END DATE
        df['EST END DATE'] = ""
        valid_starts = starts_dt.notna()
        if valid_starts.any():
            starts_np = starts_dt[valid_starts].values.astype('datetime64[D]')
            days_np = est_days_num[valid_starts].values
            ends_np = np.busday_offset(starts_np, days_np)

            # Convert to a pure list of strings so pandas just places them in order
            formatted_ends = pd.to_datetime(ends_np).strftime('%m/%d/%Y').tolist()
            df.loc[valid_starts, 'EST END DATE'] = formatted_ends

        # 2. Bulletproof Vectorized Variance Helper
        def calc_var_vectorized(start_dates, target_dates):
            # Create a full array of empty strings matching the exact size of df
            result_array = np.full(len(df), "", dtype=object)

            valid = start_dates.notna() & target_dates.notna()
            if valid.any():
                s_np = start_dates[valid].values.astype('datetime64[D]')
                t_np = target_dates[valid].values.astype('datetime64[D]')

                # busday_count(start, target): target > start is early (+), target < start is late (-)
                diff = np.busday_count(s_np, t_np)

                # Format into a pure list and insert via the boolean mask
                formatted_diff = [f"{int(d)} days" for d in diff]
                result_array[valid] = formatted_diff

            return result_array

        ends_dt = pd.to_datetime(df['EST END DATE'], errors='coerce')

        # 3. Apply variances instantly!
        df['EST ESD VARIANCE'] = calc_var_vectorized(ends_dt, esd_dt)
        df['EST ENG VARIANCE'] = calc_var_vectorized(ends_dt, eng_due_dt)
        df['COMPLETION VARIANCE'] = calc_var_vectorized(comp_date_dt, eng_due_dt)

        # =========================================================

        planning_headers = [
            "PROJECT_ID", "SMART_ID", "TYPE", "REQUIREMENT", "QUOTE NO", "ORDER NUMBER", "PROJECT NAME", "STATUS",
            "ASSIGNED TO", "ENG START DATE", "EST START DATE", "EST DAYS", "EST END DATE",
            "ESD", "ENG DUE DATE", "COMPLETE DATE",
            "EST ESD VARIANCE", "EST ENG VARIANCE", "COMPLETION VARIANCE", "LINE_COUNT"
        ]
        return df[planning_headers]

    def commit_overrides(self, staged_edits_dict: Dict[str, Dict[str, Any]]):
        if not staged_edits_dict or not isinstance(staged_edits_dict, dict):
            return

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for smart_id, edit_data in staged_edits_dict.items():
                assignee = edit_data.get('MAN_ASSIGNED', '')
                est_days = edit_data.get('MAN_EST_DAYS', '')
                start_date = edit_data.get('MAN_START_DATE', '')

                cursor.execute('''
                    INSERT INTO user_overrides ("SMART_ID", "MAN_ASSIGNED", "MAN_EST_DAYS", "MAN_START_DATE")
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT("SMART_ID") DO UPDATE SET
                        "MAN_ASSIGNED" = CASE WHEN excluded."MAN_ASSIGNED" != '' THEN excluded."MAN_ASSIGNED" ELSE user_overrides."MAN_ASSIGNED" END,
                        "MAN_EST_DAYS" = CASE WHEN excluded."MAN_EST_DAYS" != '' THEN excluded."MAN_EST_DAYS" ELSE user_overrides."MAN_EST_DAYS" END,
                        "MAN_START_DATE" = CASE WHEN excluded."MAN_START_DATE" != '' THEN excluded."MAN_START_DATE" ELSE user_overrides."MAN_START_DATE" END
                ''', (smart_id, assignee, est_days, start_date))
            conn.commit()

    def sync_from_excel(self, file_path):
        temp_path = "temp_sync_shadow.xlsx"
        step = "Initializing sync"
        try:
            if not os.path.exists(file_path): return False, f"Could not find the synced file at:\n{file_path}"
            shutil.copy2(file_path, temp_path)

            df = pd.read_excel(temp_path, sheet_name='ENG WORKLOAD MASTER 2026', header=None, engine='openpyxl')

            def clean_cell(val):
                if pd.isna(val): return ""
                if isinstance(val, float) and val.is_integer(): return str(int(val))
                return str(val).strip()

            for col in list(df.columns):
                df[col] = df[col].map(clean_cell)

            header_idx = -1
            for idx, row in df.head(50).iterrows():
                if "ORDER NUMBER" in [str(cell).upper() for cell in row]:
                    header_idx = idx
                    break

            if header_idx == -1: return False, "Could not find 'ORDER NUMBER' header row."

            df.columns = [str(c).strip() for c in df.iloc[header_idx]]
            df = df.iloc[header_idx + 1:].reset_index(drop=True)

            actual_cols = list(df.columns)
            rename_dict = {}

            for actual_col in actual_cols:
                norm_col = re.sub(r'[\W_]+', '', str(actual_col).upper())
                if norm_col in self.raw_header_mapping:
                    rename_dict[actual_col] = self.raw_header_mapping[norm_col]

            df = df.rename(columns=rename_dict)

            end_idx = -1
            for idx, row in df.iterrows():
                if "END OF LINE" in [str(cell).upper() for cell in row]:
                    end_idx = idx
                    break
            if end_idx != -1: df = df.iloc[:end_idx]

            unique_expected_cols = list(dict.fromkeys(self.raw_header_mapping.values()))
            columns_to_keep = [c for c in df.columns if c in unique_expected_cols]
            df = df[columns_to_keep]

            if 'TYPE' in df.columns:
                df = df[df['TYPE'].isin(self.valid_types)]

            df['SMART_ID'] = df.apply(self.generate_smart_id, axis=1)
            counts = df.groupby('SMART_ID').cumcount()
            df['SMART_ID'] = df['SMART_ID'] + counts.apply(lambda x: f"_{x}" if x > 0 else "")

            for col in ["DATE TO ENG", "RAW_START_DATE", "ENG DUE DATE", "COMPLETE DATE", "ESD"]:
                if col in df.columns: df[col] = df[col].apply(self.format_date)

            for expected_col in unique_expected_cols:
                if expected_col not in df.columns: df[expected_col] = ""

            final_cols = ["SMART_ID"] + unique_expected_cols
            df = df[final_cols]

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DROP TABLE IF EXISTS raw_workload')

                raw_cols_def = ", ".join([f'"{h}" TEXT' for h in unique_expected_cols])
                cursor.execute(f'''
                    CREATE TABLE raw_workload (
                        "SMART_ID" TEXT PRIMARY KEY,
                        {raw_cols_def}
                    )
                ''')

                col_names_str = ", ".join([f'"{c}"' for c in final_cols])
                placeholders = ", ".join(["?"] * len(final_cols))

                records = list(df.itertuples(index=False, name=None))
                if records:
                    cursor.executemany(f"INSERT INTO raw_workload ({col_names_str}) VALUES ({placeholders})", records)
                conn.commit()
            return True, ""

        except Exception as e:
            import traceback
            error_str = f"Error at {step}: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
            logging.error(error_str)
            return False, "Sync failed! Check error log."
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    @staticmethod
    def format_date(value):
        if pd.isna(value) or str(value).strip() in ["", "nan"]: return ""
        try:
            dt = pd.to_datetime(value)
            return f"{dt.month}/{dt.day}/{dt.year}"
        except Exception:
            return str(value)