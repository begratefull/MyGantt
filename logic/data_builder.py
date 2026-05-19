"""
Contains utility classes for transforming flat database records
into hierarchical, visually-ready data structures for the UI.
"""

import re
from typing import Dict, Any, List, Set
from logic.constants import AppConstants
import pandas as pd
from logic.calendar_engine import CalendarEngine

class GanttDataBuilder:

    @staticmethod
    def clean_requirement_text(req_text: Any) -> str:
        return re.sub(r'(?i)drawing', '', str(req_text)).strip()

    @staticmethod
    def build_visual_hierarchy(df: pd.DataFrame, expanded_projects: Set[str], color_map: Dict[str, str]) -> List[Dict[str, Any]]:
        visual_rows: List[Dict[str, Any]] = []
        if df.empty:
            return visual_rows

        grouped = df.groupby('PROJECT_ID', sort=False)

        for project_id, group in grouped:

            real_starts = pd.to_datetime(group['ENG START DATE'].replace('', None)).dropna()
            real_ends = pd.to_datetime(group['COMPLETE DATE'].replace('', None)).dropna()
            est_starts = pd.to_datetime(group['EST START DATE'].replace('', None)).dropna()

            est_ends = pd.Series(dtype='datetime64[ns]')
            if not est_starts.empty:
                valid_idx = est_starts.index
                est_days = pd.to_numeric(group.loc[valid_idx, 'EST DAYS'], errors='coerce').fillna(AppConstants.DEFAULT_EST_DAYS).astype(int)

                # --- Routed through Central Engine ---
                end_strings = CalendarEngine.calculate_end_dates_vectorized(est_starts, est_days)
                est_ends = pd.to_datetime(end_strings, errors='coerce')

            all_starts = pd.concat([real_starts, est_starts])
            all_ends = pd.concat([real_ends, est_ends])

            min_start = all_starts.min() if not all_starts.empty else pd.NaT
            max_end = all_ends.max() if not all_ends.empty else pd.NaT

            parent_days = AppConstants.DEFAULT_EST_DAYS
            if pd.notna(min_start) and pd.notna(max_end):
                parent_days = max(1, CalendarEngine.get_working_days_duration(min_start, max_end))

            parent_eng_start = real_starts.min() if not real_starts.empty else pd.NaT
            parent_comp_date = real_ends.max() if not real_ends.empty else pd.NaT

            first_row = group.iloc[0]
            all_complete = all(group['STATUS'].str.strip().str.upper() == 'COMPLETE')
            parent_status = 'COMPLETE' if all_complete else 'ACTIVE'

            assignees = [str(x).strip().upper() for x in group['ASSIGNED TO'].unique() if
                         str(x).strip().upper() not in ('', AppConstants.UNASSIGNED_LABEL, 'NAN')]
            parent_assignee = assignees[0] if len(assignees) == 1 else "MULTIPLE" if len(assignees) > 1 else AppConstants.UNASSIGNED_LABEL

            parent_color = color_map.get(parent_assignee, "#555555")
            if parent_assignee == "MULTIPLE": parent_color = "#888888"
            if parent_assignee in [AppConstants.UNASSIGNED_LABEL, "TBD", "NAN", ""]: parent_color = "#555555"

            reqs = group['REQUIREMENT'].unique()
            raw_req = reqs[0] if len(reqs) == 1 else "Multiple"

            due_dates = pd.to_datetime(group['ENG DUE DATE'].replace('', None)).dropna()
            max_due = due_dates.max() if not due_dates.empty else pd.NaT

            esd_dates = pd.to_datetime(group['ESD'].replace('', None)).dropna()
            min_esd = esd_dates.min() if not esd_dates.empty else pd.NaT

            parent_eng_var = ""
            if pd.notna(max_end) and pd.notna(max_due):
                var = CalendarEngine.get_working_days_variance(max_end, max_due)
                parent_eng_var = f"{var} days"

            parent_esd_var = ""
            if pd.notna(max_end) and pd.notna(min_esd):
                var = CalendarEngine.get_working_days_variance(max_end, min_esd)
                parent_esd_var = f"{var} days"

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

                'ENG START DATE': parent_eng_start.strftime('%m/%d/%Y') if pd.notna(parent_eng_start) else "",
                'COMPLETE DATE': parent_comp_date.strftime('%m/%d/%Y') if pd.notna(parent_comp_date) else "",

                'EST START DATE': min_start.strftime('%m/%d/%Y') if pd.notna(min_start) else "",
                'EST END DATE': max_end.strftime('%m/%d/%Y') if pd.notna(max_end) else "",
                'EST DAYS': str(parent_days),
                'ENG DUE DATE': max_due.strftime('%m/%d/%Y') if pd.notna(max_due) else "",
                'ESD': min_esd.strftime('%m/%d/%Y') if pd.notna(min_esd) else "",
                'EST ENG VARIANCE': parent_eng_var,
                'EST ESD VARIANCE': parent_esd_var
            }
            visual_rows.append(parent_row)

            if project_id in expanded_projects:
                for idx, row in group.iterrows():
                    child_row = row.to_dict()
                    child_row['IS_PARENT'] = False
                    child_row['REQUIREMENT'] = GanttDataBuilder.clean_requirement_text(child_row.get('REQUIREMENT', ''))

                    child_assignee = str(child_row.get('ASSIGNED TO', '')).strip().upper()

                    if child_assignee in ["", AppConstants.UNASSIGNED_LABEL, "NAN", "TBD"]:
                        child_color = "#555555"
                    else:
                        child_color = color_map.get(child_assignee, "#555555")

                    # Unindented to apply to all children properly!
                    child_row['HEX_COLOR'] = child_color

                    visual_rows.append(child_row)

        return visual_rows