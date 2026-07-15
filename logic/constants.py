"""
Centralized configuration for business logic and "magic strings".
Update these values when company processes, line types, or tracking rules change.
"""
import datetime
import os
import logging

logger = logging.getLogger(__name__)

class AppConstants:
    """
    A centralized static class housing all application constants, including
    file paths, routing rules, line type classifications, and regex patterns.
    """

    # --- App Metadata ---
    APP_VERSION = 'v2.2.0'

    # --- Smart Pathing (Single Source of Truth) ---
    @staticmethod
    def get_data_dir() -> str:
        """
        Returns the single source-of-truth data directory located on OneDrive.
        Aggressively checks for Business/Commercial OneDrive environments first.

        Returns:
            str: The absolute path to the MyGantt_Data directory.
        """
        try:
            # Priority 1: Business/Commercial OneDrive (Standard for enterprise Microsoft 365)
            onedrive_path = os.environ.get('OneDriveCommercial')

            # Priority 2: Standard/Personal OneDrive
            if not onedrive_path:
                onedrive_path = os.environ.get('ONEDRIVE')

            # Priority 3: Hard Fallback if PyCharm strips environment variables
            if not onedrive_path:
                logger.warning("OneDrive environment variables missing (PyCharm might be hiding them). Using manual fallback.")
                onedrive_path = os.path.expanduser(os.path.join('~', 'OneDrive'))

            # Construct the specific path for the app's data folder
            data_dir = os.path.join(onedrive_path, 'Development', 'MyGantt_Data')

            # Ensure the directory exists
            os.makedirs(data_dir, exist_ok=True)

            logger.info(f"SUCCESS: Resolving data directory to -> {data_dir}")

            return data_dir

        except Exception as e:
            logger.error(f"Failed to resolve or create OneDrive data directory: {e}")
            local_fallback = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data_fallback')
            os.makedirs(local_fallback, exist_ok=True)
            return local_fallback

    @staticmethod
    def get_config_path() -> str:
        """
        Returns the absolute path to the app_config.json file, utilizing the
        single-source OneDrive directory.

        Returns:
            str: The absolute path to the configuration JSON file.
        """
        try:
            return os.path.join(AppConstants.get_data_dir(), 'app_config.json')
        except Exception as e:
            logger.error(f"Failed to resolve config path: {e}")
            # Absolute worst-case fallback to prevent a total crash
            return 'app_config.json'

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

    # --- Task Estimation Defaults & Chart Classifications ---
    # Regex patterns to identify phase requirements from the 'REQUIREMENT' column

    # Global categories (Used for backend aggregations & KPI groupings)
    QUOTE_REQ_PATTERN = r'QUOT|APP'
    PROD_REQ_PATTERN = r'PROD|RE-?WORK' # Re-work is grouped into production for total KPI counting

    # Specific sub-categories (Used primarily for decoupled dashboard color/chart mapping)
    REWORK_REQ_PATTERN = r'RE-?WORK'
    NEW_PROD_REQ_PATTERN = r'NEW PRODUCT'
    PRE_WORK_REQ_PATTERN = r'PRE-?WORK'
    JDE_REQ_PATTERN = r'JDE'
    SUPPORT_REQ_PATTERN = r'SUPPORT|DOC'
    REVISION_REQ_PATTERN = r'REV'
    APPROVAL_REQ_PATTERN = r'APP|APPROVAL'

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