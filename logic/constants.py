"""
Centralized configuration for business logic and "magic strings".
Update these values when company processes, line types, or tracking rules change.
"""
import datetime
import sys
import os

class AppConstants:
    # --- App Metadata ---
    APP_VERSION = 'v1.0.0'

    # --- Smart Pathing ---
    @staticmethod
    def get_data_dir() -> str:
        """
        If running as a compiled .exe, returns the sibling 'MyGantt_Data' folder.
        If running as a Python script, returns the local 'data' folder.
        :return: data_dir as String
        """
        if getattr(sys, 'frozen', False):
            # Running as an .exe inside OneDrive/Engineering Workload_Data/MyGantt_App
            exe_dir = os.path.dirname(sys.executable)
            parent_dir = os.path.dirname(exe_dir)

            data_dir = os.path.join(parent_dir, 'MyGantt_Data')
            os.makedirs(data_dir, exist_ok=True)
            return data_dir
        else:
            # Running locally in PyCharm (C:\dev\MyGantt)
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)

            data_dir = os.path.join(project_root, 'data')
            os.makedirs(data_dir, exist_ok=True)
            return data_dir

    @staticmethod
    def get_config_path() -> str:
        """Keeps app_config.json in the root locally, but in MyGantt_Data when compiled."""
        if getattr(sys, 'frozen', False):
            # Compiled: Look in the sibling data folder
            return os.path.join(AppConstants.get_data_dir(), 'app_config.json')
        else:
            # Local: Look in the root project folder
            current_dir = os.path.dirname(os.path.abspath(__file__))
            project_root = os.path.dirname(current_dir)
            return os.path.join(project_root, 'app_config.json')

    # --- Company Holidays ---
    # Automatically populated when app runs or data is synced
    COMPANY_HOLIDAYS = []

    # --- Dynamic Year Handling ---
    CURRENT_YEAR = datetime.datetime.now().year

    # --- Team Line Type Classifications ---
    # These determine automatic team routing based on the 'TYPE' column in Excel
    STANDARD_LINE_TYPES = ['STD', 'STD-M', 'PART']
    CUSTOM_LINE_TYPES = ['MOD', 'CUS', 'RENOV', 'PART-MC']

    # --- Line Types for KPIs ---
    KPI_CUSTOM_LINE_TYPES = ['MOD', 'CUS']

    # --- Parsing & Data Sync ---
    # The exact name of the sheet inside the Excel file to read from
    MASTER_SHEET_NAME = f'ENG WORKLOAD MASTER {CURRENT_YEAR}'
    HOLIDAY_SHEET_NAME = f'HOLIDAY DATES {CURRENT_YEAR}'

    # --- Task Estimation Defaults ---
    # Regex pattern to identify Quote or Approval lines from the 'REQUIREMENT' column
    QUOTE_REQ_PATTERN = 'QUOT|APP'

    # Default estimated days to complete standard tasks vs quotes
    DEFAULT_EST_DAYS = 5
    DEFAULT_QUOTE_DAYS = 1

    # --- UI & Display Defaults ---
    UNASSIGNED_LABEL = 'UNASSIGNED'
    STANDARD_TEAM_LABEL = 'STANDARD TEAM'
    CUSTOM_TEAM_LABEL = 'CUSTOM TEAM'

    # --- ENGINEERS LIST ---
    OFFICIAL_ENGINEERS = [
        "Adam T", "Andy C", "David M", "Matt M", "Soree S",
        "Shruti K", "Dinesh S", "Inside Sales", "Josh F",
        "Diana E", "Kathryn K", "Josh D", "Eric J",
        "Jason B", "Frank G"
    ]

    # --- ALIAS MAP FOR TYPOS IN OUTLOOK CALENDAR ---
    ALIAS_MAP = {
        "dave m": "David M",
        "frank": "Frank G",
        "david m.": "David M",  # Example of catching typos
    }