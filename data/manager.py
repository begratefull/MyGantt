import pandas as pd
import sqlite3
import os
import shutil
from pandas.tseries.offsets import BusinessDay


class DataManager:
    def __init__(self):
        base_path = os.path.dirname(__file__)
        self.db_path = os.path.join(base_path, "gantt_data.db")

        # Mapped from Boss's Excel to our Clean Raw Data
        self.raw_header_mapping = {
            "ORDER NUMBER": "ORDER NUMBER",
            "LINE\nITEM": "LINE ITEM",
            "PRIORITY": "PRIORITY",
            "DATE TO ENG": "DATE TO ENG",
            "SHIP TO NUMBER\n(PROJECT)": "PROJECT NAME",
            "INTERGRATION REFERENCE NUMBER\n(QUOTE #)": "QUOTE NO",
            "SALES CONTACT": "SALES CONTACT",
            "TYPE": "TYPE",
            "CONFIGURED STRING\n(LUMINARIE SPECIFICATION)": "LUMINARIE SPECIFICATION",
            "SELL $": "SELL $",
            "ASSIGNED TO": "ASSIGNED TO",  # NEW: Added for Real-World Override
            "ENG START DATE": "ENG START DATE",  # NEW: Added for Real-World Override
            "DUE DATE": "ENG DUE DATE",
            "COMPLETE DATE": "COMPLETE DATE",
            "SHIP DATE": "ESD",
            "REQUIRMENT": "REQUIRMENT",
            "STATUS": "STATUS"
        }

        self.valid_types = ['MOD', 'CUS', 'PART-MC']
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            raw_cols = ", ".join([f'"{h}" TEXT' for h in self.raw_header_mapping.values()])
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS raw_workload (
                    "SMART_ID" TEXT PRIMARY KEY,
                    {raw_cols}
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS my_planning_data (
                    "SMART_ID" TEXT PRIMARY KEY,
                    "ASSIGNED TO" TEXT,
                    "EST DAYS" TEXT,
                    "EST START DATE" TEXT
                )
            ''')
            conn.commit()

    def generate_smart_id(self, row):
        order = str(row.get('ORDER NUMBER', '')).strip()
        quote = str(row.get('QUOTE NO', '')).strip()
        line = str(row.get('LINE ITEM', '')).strip()

        if order and order.upper() != 'NAN':
            base = order
        elif quote and quote.upper() != 'NAN':
            base = quote
        else:
            base = "UNKNOWN"

        return f"{base}-{line}"

    def get_raw_data(self):
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query('SELECT * FROM raw_workload', conn)
            return df.fillna("")

    def get_planning_data(self):
        """Creates the Planning Table by blending Raw Data over Manual Data."""
        with sqlite3.connect(self.db_path) as conn:
            query = '''
                SELECT 
                    r."SMART_ID", r."TYPE", r."ORDER NUMBER", r."QUOTE NO", 
                    r."PROJECT NAME", r."STATUS", r."ESD", r."ENG DUE DATE", r."COMPLETE DATE",
                    r."ASSIGNED TO" AS RAW_ASSIGNED, r."ENG START DATE" AS RAW_START,
                    p."ASSIGNED TO" AS MAN_ASSIGNED, p."EST DAYS", p."EST START DATE" AS MAN_START
                FROM raw_workload r
                LEFT JOIN my_planning_data p ON r."SMART_ID" = p."SMART_ID"
            '''
            df = pd.read_sql_query(query, conn).fillna("")

        if df.empty:
            return df

        # THE OVERRIDE BLEND: If the Boss's sheet has data, use it! Otherwise, use your manual input.
        df['ASSIGNED TO'] = df.apply(
            lambda r: r['RAW_ASSIGNED'] if str(r['RAW_ASSIGNED']).strip() else r['MAN_ASSIGNED'], axis=1)
        df['EST START DATE'] = df.apply(lambda r: r['RAW_START'] if str(r['RAW_START']).strip() else r['MAN_START'],
                                        axis=1)

        # 1. Calculate End Dates
        df['EST END DATE'] = df.apply(self.calc_end_date, axis=1)

        # 2. Calculate Variances
        df['EST ESD VARIANCE'] = df.apply(lambda row: self.calc_variance(row['EST END DATE'], row['ESD']), axis=1)
        df['EST ENG VARIANCE'] = df.apply(lambda row: self.calc_variance(row['EST END DATE'], row['ENG DUE DATE']),
                                          axis=1)

        # NEW: Calculate Actual Completion Variance (Only populates if both dates exist)
        df['COMPLETION VARIANCE'] = df.apply(lambda row: self.calc_variance(row['EST END DATE'], row['COMPLETE DATE']),
                                             axis=1)

        # 3. Reorder Columns (Variances sent to the far right)
        planning_headers = [
            "SMART_ID", "TYPE", "ORDER NUMBER", "QUOTE NO", "PROJECT NAME", "STATUS",
            "ASSIGNED TO", "EST START DATE", "EST DAYS", "EST END DATE",
            "ESD", "ENG DUE DATE", "COMPLETE DATE",
            "EST ESD VARIANCE", "EST ENG VARIANCE", "COMPLETION VARIANCE"
        ]
        return df[planning_headers]

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
                row_vals = [str(cell).upper() for cell in row]
                if "ORDER NUMBER" in row_vals:
                    header_idx = idx
                    break

            if header_idx == -1: return False, "Could not find 'ORDER NUMBER' header row in the Excel sheet."

            df.columns = [str(c).strip() for c in df.iloc[header_idx]]
            df = df.iloc[header_idx + 1:].reset_index(drop=True)

            end_idx = -1
            for idx, row in df.iterrows():
                row_vals = [str(cell).upper() for cell in row]
                if "END OF LINE" in row_vals:
                    end_idx = idx
                    break

            if end_idx != -1: df = df.iloc[:end_idx]

            mapping = getattr(self, 'raw_header_mapping', {}) or {}
            raw_cols = list(df.columns) if hasattr(df, 'columns') and df.columns is not None else []
            columns_to_keep = [col for col in raw_cols if col in mapping]
            df = df[columns_to_keep].rename(columns=mapping)

            valid_teams = getattr(self, 'valid_types', ['MOD', 'CUS', 'PART-MC']) or ['MOD', 'CUS', 'PART-MC']
            if 'TYPE' in df.columns:
                df = df[df['TYPE'].isin(valid_teams)]

            df['SMART_ID'] = df.apply(self.generate_smart_id, axis=1)

            counts = df.groupby('SMART_ID').cumcount()
            df['SMART_ID'] = df['SMART_ID'] + counts.apply(lambda x: f"_{x}" if x > 0 else "")

            # ADDED: ENG START DATE format standardizing
            date_cols = ["DATE TO ENG", "ENG START DATE", "ENG DUE DATE", "COMPLETE DATE", "ESD"]
            for col in date_cols:
                if col in df.columns: df[col] = df[col].apply(self.format_date)

            for expected_col in mapping.values():
                if expected_col not in df.columns: df[expected_col] = ""

            final_cols = ["SMART_ID"] + list(mapping.values())
            df = df[final_cols]

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM raw_workload')
                placeholders = ", ".join(["?"] * len(final_cols))
                records = list(df.itertuples(index=False, name=None))
                if records:
                    cursor.executemany(f"INSERT INTO raw_workload VALUES ({placeholders})", records)
                    cursor.execute('''
                        INSERT OR IGNORE INTO my_planning_data ("SMART_ID", "ASSIGNED TO", "EST DAYS", "EST START DATE")
                        SELECT "SMART_ID", '', '', '' FROM raw_workload
                    ''')
                conn.commit()
            return True, ""

        except Exception as e:
            import traceback
            error_str = f"CRASHED AT STEP:\n>>> {step} <<<\n\nError: {str(e)}\n\nTraceback:\n{traceback.format_exc()}"
            print("\n" + "!" * 60 + "\n🚨 DATABASE SYNC ERROR 🚨\n" + "!" * 60 + f"\n{error_str}\n" + "!" * 60 + "\n")
            return False, "Sync failed! Please check your PyCharm console for the full error text."

        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

    def update_job_details(self, smart_id, assignee, est_days, start_date):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE my_planning_data 
                SET "ASSIGNED TO" = ?, "EST DAYS" = ?, "EST START DATE" = ?
                WHERE "SMART_ID" = ?
            ''', (assignee, est_days, start_date, smart_id))
            conn.commit()

    def format_date(self, value):
        if pd.isna(value) or str(value).strip() in ["", "nan"]: return ""
        try:
            dt = pd.to_datetime(value)
            return f"{dt.month}/{dt.day}/{dt.year}"
        except:
            return str(value)

    def calc_end_date(self, row):
        try:
            start = pd.to_datetime(row['EST START DATE'])
            days = int(float(row['EST DAYS']))
            end = start + BusinessDay(days)
            return f"{end.month}/{end.day}/{end.year}"
        except:
            return ""

    def calc_variance(self, end_date, target_date):
        try:
            if not end_date or not target_date: return ""
            delta = (pd.to_datetime(target_date) - pd.to_datetime(end_date)).days
            return f"{delta} days"
        except:
            return ""