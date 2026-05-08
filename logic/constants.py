"""
Centralized configuration for business logic and "magic strings".
Update these values when company processes, line types, or tracking rules change.
"""


class AppConstants:
    # --- Team Line Type Classifications ---
    # These determine automatic team routing based on the 'TYPE' column in Excel
    STANDARD_LINE_TYPES = ['STD', 'STD-M', 'PART']
    CUSTOM_LINE_TYPES = ['MOD', 'CUS', 'PART-MC']

    # --- Parsing & Data Sync ---
    # The exact name of the sheet inside the Excel file to read from
    MASTER_SHEET_NAME = 'ENG WORKLOAD MASTER 2026'

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