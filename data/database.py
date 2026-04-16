import sqlite3
import os
import pandas as pd
from typing import Dict, Any, List


class DatabaseManager:
    def __init__(self):
        # Set up the path to the database file in the same directory as this script
        base_path = os.path.dirname(__file__)
        self.db_path = os.path.join(base_path, "gantt_data.db")

    def get_connection(self):
        """Helper to quickly get a database connection."""
        return sqlite3.connect(self.db_path)

    def init_db(self, unique_cols: List[str]):
        """Creates the necessary tables if they don't already exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Format the column names for the SQL CREATE statement
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

    def get_raw_df(self) -> pd.DataFrame:
        """Fetches the raw synced data as a Pandas DataFrame."""
        with self.get_connection() as conn:
            return pd.read_sql_query('SELECT * FROM raw_workload', conn).fillna("")

    def get_saved_overrides_df(self) -> pd.DataFrame:
        """Fetches the manual user overrides as a Pandas DataFrame."""
        with self.get_connection() as conn:
            return pd.read_sql_query('SELECT * FROM user_overrides', conn).fillna("")

    def save_overrides(self, staged_edits_dict: Dict[str, Dict[str, Any]]):
        """Commits user overrides (assignees, dates, days) to the database."""
        if not staged_edits_dict or not isinstance(staged_edits_dict, dict):
            return

        with self.get_connection() as conn:
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

    def replace_raw_workload(self, df: pd.DataFrame, expected_cols: List[str], final_cols: List[str]):
        """Drops the old raw_workload table and inserts the freshly synced Excel data."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DROP TABLE IF EXISTS raw_workload')

            raw_cols_def = ", ".join([f'"{h}" TEXT' for h in expected_cols])
            cursor.execute(f'''CREATE TABLE raw_workload ("SMART_ID" TEXT PRIMARY KEY, {raw_cols_def})''')

            col_names_str = ", ".join([f'"{c}"' for c in final_cols])
            placeholders = ", ".join(["?"] * len(final_cols))

            records = list(df.itertuples(index=False, name=None))
            if records:
                cursor.executemany(f"INSERT INTO raw_workload ({col_names_str}) VALUES ({placeholders})", records)
            conn.commit()