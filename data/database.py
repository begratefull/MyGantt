import sqlite3
import os
import logging
import pandas as pd
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self):
        # Set up the path to the database file
        base_path = os.path.dirname(__file__)
        self.db_path = os.path.join(base_path, "gantt_data.db")

        # Force the static tables to exist the moment the app boots!
        self._ensure_static_tables()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def _ensure_static_tables(self):
        """Silently creates teams and engineers tables on startup if they don't exist."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS teams (
                        "team_name" TEXT PRIMARY KEY,
                        "hourly_rate" REAL
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS engineers (
                        "name" TEXT PRIMARY KEY,
                        "team_name" TEXT,
                        "hex_color" TEXT,
                        FOREIGN KEY("team_name") REFERENCES teams("team_name")
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS company_holidays (
                        "holiday_date" TEST PRIMARY KEY
                    )
                ''')
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database Initialization Error: Could not verify static tables. ({e})")

    def init_db(self, unique_cols: List[str]):
        """Creates the raw_workload table dynamically during an Excel sync."""
        self._ensure_static_tables()
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
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
                logger.info("Database schemas initialized successfully.")
        except sqlite3.Error as e:
            logger.error(f"Database Error: Failed to initialize sync tables. ({e})")

    def get_raw_df(self) -> pd.DataFrame:
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query('SELECT * FROM raw_workload', conn).fillna("")
        except sqlite3.Error as e:
            logger.warning(f"Failed to load raw workload data: {e}")
            return pd.DataFrame()

    def get_saved_overrides_df(self) -> pd.DataFrame:
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query('SELECT * FROM user_overrides', conn).fillna("")
        except sqlite3.Error as e:
            logger.warning(f"Failed to load user overrides: {e}")
            return pd.DataFrame()

    def get_engineers_df(self) -> pd.DataFrame:
        """Fetches engineers with a safety net if the table is empty or missing."""
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query('SELECT * FROM engineers', conn).fillna("")
        except sqlite3.Error as e:
            logger.warning(f"Failed to load engineer roster: {e}")
            return pd.DataFrame(columns=["name", "team_name", "hex_color"])

    def get_teams_df(self) -> pd.DataFrame:
        try:
            with self.get_connection() as conn:
                return pd.read_sql_query('SELECT * FROM teams', conn).fillna("")
        except sqlite3.Error as e:
            logger.warning(f"Failed to load teams: {e}")
            return pd.DataFrame(columns=["team_name", "hourly_rate"])

    def save_overrides(self, staged_edits_dict: Dict[str, Dict[str, Any]]):
        if not staged_edits_dict or not isinstance(staged_edits_dict, dict):
            return

        try:
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
                logger.info(f"Successfully saved {len(staged_edits_dict)} edits to the database.")
        except sqlite3.Error as e:
            logger.error(f"Failed to save manual edits: {e}")

    def upsert_engineer(self, name: str, team_name: str, hex_color: str):
        self._ensure_static_tables()
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO engineers ("name", "team_name", "hex_color")
                    VALUES (?, ?, ?)
                    ON CONFLICT("name") DO UPDATE SET
                        "team_name" = excluded."team_name",
                        "hex_color" = excluded."hex_color"
                ''', (name, team_name, hex_color))
                conn.commit()
                logger.info(f"Engineer '{name}' saved successfully.")
        except sqlite3.Error as e:
            logger.error(f"Failed to save engineer '{name}': {e}")

    def upsert_team(self, team_name: str, hourly_rate: float):
        self._ensure_static_tables()
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO teams ("team_name", "hourly_rate")
                    VALUES (?, ?)
                    ON CONFLICT("team_name") DO UPDATE SET
                        "hourly_rate" = excluded."hourly_rate"
                ''', (team_name, hourly_rate))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to save team '{team_name}': {e}")

    def replace_raw_workload(self, df: pd.DataFrame, expected_cols: List[str], final_cols: List[str]):
        try:
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
                logger.info(f"Database sync complete: {len(records)} raw workload rows inserted.")
        except sqlite3.Error as e:
            logger.error(f"Critical Database Error during sync: {e}")

    def replace_holidays(self, dates: list):
        """Wipes the old holidays and saves the newly synced ones."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM company_holidays')
                if dates:
                    records = [(d,) for d in dates]
                    cursor.executemany('INSERT INTO company_holidays ("holiday_date") VALUES (?)', records)
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to save holidays: {e}")

    def get_holidays(self) -> list:
        """Returns a list of holiday date strings."""
        try:
            with self.get_connection() as conn:
                df = pd.read_sql_query('SELECT holiday_date FROM company_holidays', conn)
                return df['holiday_date'].tolist()
        except sqlite3.Error as e:
            logger.warning(f"Failed to load holidays: {e}")
            return []
