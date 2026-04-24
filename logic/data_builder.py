"""
Contains utility classes for transforming flat database records
into hierarchical, visually-ready data structures for the UI.
"""

import re
from typing import Dict, Any, List, Set

import numpy as np
import pandas as pd


class GanttDataBuilder:
    """
    A utility class responsible for taking flat DataFrames and crunching
    the mathematics required to build parent/child relationships,
    aggregate dates, and assign theme colors for the Gantt View.
    """

    @staticmethod
    def clean_requirement_text(req_text: Any) -> str:
        """Strips out redundant words like 'drawing' to keep UI labels clean."""
        return re.sub(r'(?i)drawing', '', str(req_text)).strip()

    @staticmethod
    def build_visual_hierarchy(df: pd.DataFrame, expanded_projects: Set[str], color_map: Dict[str, str]) -> List[
        Dict[str, Any]]:
        """
        Transforms a raw project DataFrame into a structured list of dictionaries
        representing Parent summary blocks and Child task blocks.
        """
        visual_rows: List[Dict[str, Any]] = []
        if df.empty:
            return visual_rows

        grouped = df.groupby('PROJECT_ID', sort=False)

        for project_id, group in grouped:
            # 1. Calculate Agreggate Start and End Dates
            starts = pd.to_datetime(group['ENG START DATE'].replace('', pd.NaT)).combine_first(
                pd.to_datetime(group['EST START DATE'].replace('', pd.NaT)))
            ends = pd.to_datetime(group['EST END DATE'].replace('', pd.NaT)).combine_first(
                pd.to_datetime(group['COMPLETE DATE'].replace('', pd.NaT)))

            min_start = starts.min() if not starts.isna().all() else pd.NaT
            max_end = ends.max() if not ends.isna().all() else pd.NaT

            # 2. Calculate Total Business Days
            parent_days = 5
            if pd.notna(min_start) and pd.notna(max_end):
                days = np.busday_count(min_start.date(), max_end.date())
                parent_days = max(1, int(days))

            first_row = group.iloc[0]
            all_complete = all(group['STATUS'].str.strip().str.upper() == 'COMPLETE')
            parent_status = 'COMPLETE' if all_complete else 'ACTIVE'

            # 3. Determine Parent Assignee
            assignees = [str(x).strip().upper() for x in group['ASSIGNED TO'].unique() if
                         str(x).strip().upper() not in ('', 'UNASSIGNED')]
            parent_assignee = assignees[0] if len(assignees) == 1 else "MULTIPLE" if len(
                assignees) > 1 else "UNASSIGNED"

            # 4. Determine Parent Block Color
            parent_color = color_map.get(parent_assignee, "#007ACC")  # Default Blue
            if parent_assignee == "MULTIPLE":
                parent_color = "#888888"  # Grey
            if parent_assignee == "UNASSIGNED":
                parent_color = "#555555"  # Dark Grey

            reqs = group['REQUIREMENT'].unique()
            raw_req = reqs[0] if len(reqs) == 1 else "Multiple"

            # 5. Calculate Variances
            due_dates = pd.to_datetime(group['ENG DUE DATE'].replace('', pd.NaT))
            min_due = due_dates.min() if not due_dates.isna().all() else pd.NaT

            esd_dates = pd.to_datetime(group['ESD'].replace('', pd.NaT))
            min_esd = esd_dates.min() if not esd_dates.isna().all() else pd.NaT

            parent_eng_var = ""
            if pd.notna(max_end) and pd.notna(min_due):
                parent_eng_var = f"{int(np.busday_count(max_end.date(), min_due.date()))} days"

            parent_esd_var = ""
            if pd.notna(max_end) and pd.notna(min_esd):
                parent_esd_var = f"{int(np.busday_count(max_end.date(), min_esd.date()))} days"

            # 6. Construct the Parent Row Dictionary
            parent_row = {
                'IS_PARENT': True,
                'PROJECT_ID': project_id,
                'SMART_ID': project_id,
                'REQUIREMENT': GanttDataBuilder.clean_requirement_text(raw_req),
                'QUOTE NO': first_row.get('QUOTE NO', ''),
                'PROJECT NAME': f"{first_row.get('PROJECT NAME', '')} ({len(group)})",
                'STATUS': parent_status,
                'ASSIGNED TO': parent_assignee,
                'HEX_COLOR': parent_color,
                'EST START DATE': min_start.strftime('%m/%d/%Y') if pd.notna(min_start) else "",
                'EST END DATE': max_end.strftime('%m/%d/%Y') if pd.notna(max_end) else "",
                'EST DAYS': str(parent_days),
                'ENG DUE DATE': min_due.strftime('%m/%d/%Y') if pd.notna(min_due) else "",
                'ESD': min_esd.strftime('%m/%d/%Y') if pd.notna(min_esd) else "",
                'EST ENG VARIANCE': parent_eng_var,
                'EST ESD VARIANCE': parent_esd_var
            }
            visual_rows.append(parent_row)

            # 7. Append Children if Parent is Expanded
            if project_id in expanded_projects:
                for idx, row in group.iterrows():
                    child_row = row.to_dict()
                    child_row['IS_PARENT'] = False
                    child_row['REQUIREMENT'] = GanttDataBuilder.clean_requirement_text(child_row.get('REQUIREMENT', ''))

                    child_assignee = str(child_row.get('ASSIGNED TO', '')).strip().upper()
                    child_color = color_map.get(child_assignee, "#007ACC") if child_assignee not in ["", "UNASSIGNED",
                                                                                                     "NAN"] else "#555555"
                    child_row['HEX_COLOR'] = child_color

                    visual_rows.append(child_row)

        return visual_rows
