import pandas as pd
import re
from typing import Dict, List
from logic.constants import AppConstants


class PTOParser:

    @classmethod
    def normalize_name(cls, raw_name: str) -> str:
        """Cleans up the Outlook Subject line and matches it to an official engineer."""
        if not isinstance(raw_name, str):
            return "Unknown"

        name = raw_name.replace("PTO -", "").replace("PTO", "").replace("Holiday -", "").strip()
        name = re.sub(r'\(.*?\)', '', name).strip()
        name_lower = name.lower()

        # Route through AppConstants
        if name_lower in AppConstants.ALIAS_MAP:
            return AppConstants.ALIAS_MAP[name_lower]

        for official in AppConstants.OFFICIAL_ENGINEERS:
            if official.lower() == name_lower:
                return official

        return name.title()

    @classmethod
    def load_pto_data(cls, csv_filepath: str) -> Dict[str, List[str]]:
        """
        Reads the Power Automate CSV, applies fixes, and returns a dictionary mapping
        engineers to an array of YYYY-MM-DD string dates.
        """
        try:
            df = pd.read_csv(csv_filepath)
        except Exception as e:
            print(f"Could not load PTO CSV: {e}")
            return {}

        # Filter out company holidays from team calendar
        df = df[~df['Engineer'].str.contains('Holiday', case=False, na=False)]

        # Apply Name Normalization
        df['Clean_Name'] = df['Engineer'].apply(cls.normalize_name)

        # Strip time for starts and subtract 1 second from End for 'All Day' format
        df['Start'] = pd.to_datetime(df['Start']).dt.normalize()
        df['End'] = (pd.to_datetime(df['End']) - pd.Timedelta(seconds=1)).dt.normalize()

        pto_dict = {}

        # Loop through the cleaned data and build the dictionary
        for _, row in df.iterrows():
            eng = row['Clean_Name']
            if eng not in pto_dict:
                pto_dict[eng] = set()

            # Create an array of all days between Start and End
            date_range = pd.date_range(start=row['Start'], end=row['End'], freq='D')

            # Add them to the engineer's set (using a set prevents duplicates)
            for d in date_range:
                pto_dict[eng].add(d.strftime('%Y-%m-%d'))

        # Convert the sets back to sorted lists
        return {eng: sorted(list(dates)) for eng, dates in pto_dict.items()}
