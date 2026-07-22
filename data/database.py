import sqlite3
import os
import logging
import contextlib
import pandas as pd
from typing import Dict, Any, List
from logic.constants import AppConstants

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages SQLite database connections, schema initializations, migrations,
    and data read/write operations for the MyGantt application.
    """

    def __init__(self, db_path: str = "") -> None:
        # If no path is provided, dynamically use smart data directory from AppConstants
        if not db_path:
            db_path = os.path.join(AppConstants.get_data_dir(), 'gantt_data.db')

        self.db_path = db_path
        self._ensure_static_tables()

    def get_connection(self) -> sqlite3.Connection:
        """Returns a new SQLite connection."""
        return sqlite3.connect(self.db_path)

    def _ensure_static_tables(self) -> None:
        """Silently creates teams, engineers, holidays, and manual task tables on startup if they don't exist."""
        try:
            # Using contextlib.closing ensures the connection is actually CLOSED
            # and released back to OneDrive so it can sync safely without locking.
            with contextlib.closing(self.get_connection()) as conn:
                with conn:  # This inner context manages the transaction (commit/rollback)
                    cursor = conn.cursor()
                    cursor.execute('''
                                   CREATE TABLE IF NOT EXISTS teams
                                   (
                                       "team_name"
                                       TEXT
                                       PRIMARY
                                       KEY,
                                       "hourly_rate"
                                       REAL
                                   )
                                   ''')
                    cursor.execute('''
                                   CREATE TABLE IF NOT EXISTS engineers
                                   (
                                       "name"
                                       TEXT
                                       PRIMARY
                                       KEY,
                                       "team_name"
                                       TEXT,
                                       "hex_color"
                                       TEXT,
                                       FOREIGN
                                       KEY
                                   (
                                       "team_name"
                                   ) REFERENCES teams
                                   (
                                       "team_name"
                                   )
                                       )
                                   ''')
                    cursor.execute('''
                                   CREATE TABLE IF NOT EXISTS company_holidays
                                   (
                                       "holiday_date"
                                       TEXT
                                       PRIMARY
                                       KEY
                                   )
                                   ''')
                    cursor.execute('''
                                   CREATE TABLE IF NOT EXISTS manual_tasks
                                   (
                                       "SMART_ID"
                                       TEXT
                                       PRIMARY
                                       KEY,
                                       "PROJECT_ID"
                                       TEXT,
                                       "PROJECT NAME"
                                       TEXT,
                                       "ASSIGNED TO"
                                       TEXT,
                                       "EST START DATE"
                                       TEXT,
                                       "EST DAYS"
                                       TEXT,
                                       "REQUIREMENT"
                                       TEXT,
                                       "TYPE"
                                       TEXT,
                                       "STATUS"
                                       TEXT
                                   )
                                   ''')
        except sqlite3.Error as e:
            logger.error(f"Database Initialization Error: Could not verify static tables. ({e})")

    def init_db(self, unique_cols: List[str]) -> None:
        """Creates the raw_workload table dynamically during an Excel sync and migrates overrides schema."""
        self._ensure_static_tables()
        try:
            with contextlib.closing(self.get_connection()) as conn:
                with conn:
                    cursor = conn.cursor()
                    raw_cols = ", ".join([f'"{h}" TEXT' for h in unique_cols])

                    cursor.execute(f'''
                        CREATE TABLE IF NOT EXISTS raw_workload (
                            "SMART_ID" TEXT PRIMARY KEY,
                            {raw_cols}
                        )
                    ''')

                    cursor.execute('''
                                   CREATE TABLE IF NOT EXISTS user_overrides
                                   (
                                       "SMART_ID"
                                       TEXT
                                       PRIMARY
                                       KEY,
                                       "MAN_ASSIGNED"
                                       TEXT,
                                       "MAN_EST_DAYS"
                                       TEXT,
                                       "MAN_START_DATE"
                                       TEXT,
                                       "MAN_STATUS"
                                       TEXT
                                   )
                                   ''')

                    # Safe schema migration: Add MAN_STATUS to older database files if it is missing
                    cursor.execute("PRAGMA table_info(user_overrides)")
                    columns = [info[1] for info in cursor.fetchall()]
                    if "MAN_STATUS" not in columns:
                        cursor.execute('ALTER TABLE user_overrides ADD COLUMN "MAN_STATUS" TEXT')
                        logger.info("Migrated existing user_overrides schema to include MAN_STATUS.")

                    logger.info("Database schemas initialized successfully.")
        except sqlite3.Error as e:
            logger.error(f"Database Error: Failed to initialize sync tables. ({e})")

    def get_raw_df(self) -> pd.DataFrame:
        """Retrieves the raw workload data from the database as a Pandas DataFrame."""
        try:
            with contextlib.closing(self.get_connection()) as conn:
                return pd.read_sql_query('SELECT * FROM raw_workload', conn).fillna("")
        except sqlite3.Error as e:
            logger.warning(f"Failed to load raw workload data: {e}")
            return pd.DataFrame()

    def get_saved_overrides_df(self) -> pd.DataFrame:
        """Retrieves user overrides from the database as a Pandas DataFrame."""
        try:
            with contextlib.closing(self.get_connection()) as conn:
                return pd.read_sql_query('SELECT * FROM user_overrides', conn).fillna("")
        except sqlite3.Error as e:
            logger.warning(f"Failed to load user overrides: {e}")
            return pd.DataFrame()

    def get_manual_tasks_df(self) -> pd.DataFrame:
        """Retrieves all manually created side-work tasks as a Pandas DataFrame."""
        try:
            with contextlib.closing(self.get_connection()) as conn:
                return pd.read_sql_query('SELECT * FROM manual_tasks', conn).fillna("")
        except sqlite3.Error as e:
            logger.warning(f"Failed to load manual tasks: {e}")
            return pd.DataFrame()

    def get_engineers_df(self) -> pd.DataFrame:
        """Fetches engineers with a safety net if the table is empty or missing."""
        try:
            with contextlib.closing(self.get_connection()) as conn:
                return pd.read_sql_query('SELECT * FROM engineers', conn).fillna("")
        except sqlite3.Error as e:
            logger.warning(f"Failed to load engineer roster: {e}")
            return pd.DataFrame(columns=["name", "team_name", "hex_color"])

    def get_teams_df(self) -> pd.DataFrame:
        """Fetches the team roster and associated hourly rates."""
        try:
            with contextlib.closing(self.get_connection()) as conn:
                return pd.read_sql_query('SELECT * FROM teams', conn).fillna("")
        except sqlite3.Error as e:
            logger.warning(f"Failed to load teams: {e}")
            return pd.DataFrame(columns=["team_name", "hourly_rate"])

    def save_overrides(self, staged_edits_dict: Dict[str, Dict[str, Any]]) -> None:
        """Commits dictionary of staged UI edits (Assignee, Dates, Durations, Status) into the database."""
        if not staged_edits_dict or not isinstance(staged_edits_dict, dict):
            return

        try:
            with contextlib.closing(self.get_connection()) as conn:
                with conn:
                    cursor = conn.cursor()
                    for smart_id, edit_data in staged_edits_dict.items():
                        assignee = edit_data.get('MAN_ASSIGNED', '')
                        est_days = edit_data.get('MAN_EST_DAYS', '')
                        start_date = edit_data.get('MAN_START_DATE', '')
                        man_status = edit_data.get('MAN_STATUS', '')

                        cursor.execute('''
                                       INSERT INTO user_overrides ("SMART_ID", "MAN_ASSIGNED", "MAN_EST_DAYS",
                                                                   "MAN_START_DATE", "MAN_STATUS")
                                       VALUES (?, ?, ?, ?, ?) ON CONFLICT("SMART_ID") DO
                                       UPDATE SET
                                           "MAN_ASSIGNED" = CASE WHEN excluded."MAN_ASSIGNED" != '' THEN excluded."MAN_ASSIGNED" ELSE user_overrides."MAN_ASSIGNED" END,
                                           "MAN_EST_DAYS" = CASE WHEN excluded."MAN_EST_DAYS" != '' THEN excluded."MAN_EST_DAYS" ELSE user_overrides."MAN_EST_DAYS"
                                       END,
                                "MAN_START_DATE" = CASE WHEN excluded."MAN_START_DATE" != '' THEN excluded."MAN_START_DATE" ELSE user_overrides."MAN_START_DATE"
                                       END,
                                "MAN_STATUS" = CASE WHEN excluded."MAN_STATUS" != '' THEN excluded."MAN_STATUS" ELSE user_overrides."MAN_STATUS"
                                       END
                                       ''', (smart_id, assignee, est_days, start_date, man_status))
                    logger.info(f"Successfully saved {len(staged_edits_dict)} edits to the database.")
        except sqlite3.Error as e:
            logger.error(f"Failed to save manual edits: {e}")

    def upsert_manual_task(self, task_data: Dict[str, Any]) -> bool:
        """Inserts or updates a manually created side-work task in the persistence table."""
        self._ensure_static_tables()
        try:
            with contextlib.closing(self.get_connection()) as conn:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                                   INSERT INTO manual_tasks ("SMART_ID", "PROJECT_ID", "PROJECT NAME", "ASSIGNED TO",
                                                             "EST START DATE", "EST DAYS", "REQUIREMENT", "TYPE",
                                                             "STATUS")
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT("SMART_ID") DO
                                   UPDATE SET
                                       "PROJECT NAME" = excluded."PROJECT NAME",
                                       "ASSIGNED TO" = excluded."ASSIGNED TO",
                                       "EST START DATE" = excluded."EST START DATE",
                                       "EST DAYS" = excluded."EST DAYS",
                                       "STATUS" = excluded."STATUS"
                                   ''', (
                                       task_data.get('SMART_ID', ''),
                                       task_data.get('PROJECT_ID', ''),
                                       task_data.get('PROJECT NAME', ''),
                                       task_data.get('ASSIGNED TO', ''),
                                       task_data.get('EST START DATE', ''),
                                       task_data.get('EST DAYS', ''),
                                       task_data.get('REQUIREMENT', 'SIDE WORK'),
                                       task_data.get('TYPE', 'CUS'),
                                       task_data.get('STATUS', 'ACTIVE')
                                   ))
                    logger.info(f"Manual task {task_data.get('SMART_ID')} saved successfully.")
                    return True
        except sqlite3.Error as e:
            logger.error(f"Failed to upsert manual task: {e}")
            return False

    def delete_manual_task(self, smart_id: str) -> bool:
        """Deletes a manual side-work task from the persistence table based on its SMART_ID."""
        try:
            with contextlib.closing(self.get_connection()) as conn:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM manual_tasks WHERE "SMART_ID" = ?', (smart_id,))
                    logger.info(f"Manual task {smart_id} deleted successfully.")
                    return True
        except sqlite3.Error as e:
            logger.error(f"Failed to delete manual task {smart_id}: {e}")
            return False

    def upsert_engineer(self, name: str, team_name: str, hex_color: str) -> None:
        """Updates or inserts an engineer configuration record."""
        self._ensure_static_tables()
        try:
            with contextlib.closing(self.get_connection()) as conn:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                                   INSERT INTO engineers ("name", "team_name", "hex_color")
                                   VALUES (?, ?, ?) ON CONFLICT("name") DO
                                   UPDATE SET
                                       "team_name" = excluded."team_name",
                                       "hex_color" = excluded."hex_color"
                                   ''', (name, team_name, hex_color))
                    logger.info(f"Engineer '{name}' saved successfully.")
        except sqlite3.Error as e:
            logger.error(f"Failed to save engineer '{name}': {e}")

    def upsert_team(self, team_name: str, hourly_rate: float) -> None:
        """Updates or inserts a team configuration record."""
        self._ensure_static_tables()
        try:
            with contextlib.closing(self.get_connection()) as conn:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute('''
                                   INSERT INTO teams ("team_name", "hourly_rate")
                                   VALUES (?, ?) ON CONFLICT("team_name") DO
                                   UPDATE SET
                                       "hourly_rate" = excluded."hourly_rate"
                                   ''', (team_name, hourly_rate))
        except sqlite3.Error as e:
            logger.error(f"Failed to save team '{team_name}': {e}")

    def replace_raw_workload(self, df: pd.DataFrame, expected_cols: List[str], final_cols: List[str]) -> None:
        """Replaces the entire raw_workload table with freshly parsed Excel data."""
        try:
            with contextlib.closing(self.get_connection()) as conn:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute('DROP TABLE IF EXISTS raw_workload')

                    raw_cols_def = ", ".join([f'"{h}" TEXT' for h in expected_cols])
                    cursor.execute(f'''CREATE TABLE raw_workload ("SMART_ID" TEXT PRIMARY KEY, {raw_cols_def})''')

                    col_names_str = ", ".join([f'"{c}"' for c in final_cols])
                    placeholders = ", ".join(["?"] * len(final_cols))

                    records = list(df.itertuples(index=False, name=None))
                    if records:
                        cursor.executemany(f"INSERT INTO raw_workload ({col_names_str}) VALUES ({placeholders})",
                                           records)
                    logger.info(f"Database sync complete: {len(records)} raw workload rows inserted.")
        except sqlite3.Error as e:
            logger.error(f"Critical Database Error during sync: {e}")

    def replace_holidays(self, dates: list) -> None:
        """Wipes the old holidays and saves the newly synced ones."""
        try:
            with contextlib.closing(self.get_connection()) as conn:
                with conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM company_holidays')
                    if dates:
                        records = [(d,) for d in dates]
                        cursor.executemany('INSERT INTO company_holidays ("holiday_date") VALUES (?)', records)
        except sqlite3.Error as e:
            logger.error(f"Failed to save holidays: {e}")

    def get_holidays(self) -> list:
        """Returns a list of holiday date strings."""
        try:
            with contextlib.closing(self.get_connection()) as conn:
                df = pd.read_sql_query('SELECT holiday_date FROM company_holidays', conn)
                return df['holiday_date'].tolist()
        except sqlite3.Error as e:
            logger.warning(f"Failed to load holidays: {e}")
            return []