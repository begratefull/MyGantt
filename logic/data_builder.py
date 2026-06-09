"""
Contains utility classes for transforming flat database records
into hierarchical, visually-ready data structures for the UI.
"""

import re
import logging
from typing import Dict, Any, List, Set, Optional
import pandas as pd
from logic.constants import AppConstants
from logic.calendar_engine import CalendarEngine

logger = logging.getLogger(__name__)


class GanttDataBuilder:
    """
    Utility class for building visual hierarchies and formatting data
    for the Gantt chart UI.
    """

    @staticmethod
    def clean_requirement_text(req_text: Any) -> str:
        """
        Cleans the requirement text by removing the word 'drawing' (case-insensitive)
        and stripping whitespace.

        Args:
            req_text (Any): The raw requirement string.

        Returns:
            str: The cleaned requirement string.
        """
        try:
            return re.sub(r'(?i)drawing', '', str(req_text)).strip()
        except Exception as e:
            logger.error(f"Error cleaning requirement text '{req_text}': {e}")
            return str(req_text).strip()

    @staticmethod
    def build_visual_hierarchy(
            df: pd.DataFrame,
            expanded_projects: Set[str],
            color_map: Dict[str, str],
            pto_dict: Optional[Dict[str, List[str]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Builds a hierarchical list of dictionaries representing parent and child
        Gantt chart rows from a flat DataFrame. Applies date calculations and formatting.

        Args:
            df (pd.DataFrame): The flat database records.
            expanded_projects (Set[str]): Project IDs that are expanded in the UI.
            color_map (Dict[str, str]): Mapping of assignee names to hex colors.
            pto_dict (Optional[Dict[str, List[str]]]): Dictionary mapping assignee to PTO dates.

        Returns:
            List[Dict[str, Any]]: Formatted rows ready for visual rendering.
        """
        visual_rows: List[Dict[str, Any]] = []
        if df.empty:
            return visual_rows

        try:
            grouped = df.groupby('PROJECT_ID', sort=False)
        except Exception as e:
            logger.error(f"Error grouping DataFrame by PROJECT_ID: {e}")
            return visual_rows

        for project_id, group in grouped:
            try:
                # Maintain index alignment for combine_first by not dropping NA immediately
                real_starts = pd.to_datetime(group['ENG START DATE'].replace('', None), errors='coerce')
                real_ends = pd.to_datetime(group['COMPLETE DATE'].replace('', None), errors='coerce')
                est_starts = pd.to_datetime(group['EST START DATE'].replace('', None), errors='coerce')

                est_ends = pd.Series(index=group.index, dtype='datetime64[ns]')
                valid_idx = est_starts.dropna().index

                if not valid_idx.empty:
                    est_days = pd.to_numeric(group.loc[valid_idx, 'EST DAYS'], errors='coerce').fillna(AppConstants.DEFAULT_EST_DAYS).astype(int)

                    assignee_series = group.loc[valid_idx, 'ASSIGNED TO']
                    end_strings = CalendarEngine.calculate_end_dates_vectorized(
                        group.loc[valid_idx, 'EST START DATE'], est_days, assignee_series, pto_dict
                    )
                    est_ends.loc[valid_idx] = pd.to_datetime(end_strings, errors='coerce')

                    group.loc[valid_idx, 'EST END DATE'] = end_strings

                # Combine dates row-by-row. Actual dates override estimated dates.
                effective_starts = real_starts.combine_first(est_starts)
                effective_ends = real_ends.combine_first(est_ends)

                # Phase 1 Debug Logging for Parent Task Bug
                logger.debug(f"--- Debugging Project: {project_id} ---")
                logger.debug(f"Real Starts: {real_starts.dt.strftime('%Y-%m-%d').tolist()}")
                logger.debug(f"Est Starts:  {est_starts.dt.strftime('%Y-%m-%d').tolist()}")
                logger.debug(f"Real Ends:   {real_ends.dt.strftime('%Y-%m-%d').tolist()}")
                logger.debug(f"Est Ends:    {est_ends.dt.strftime('%Y-%m-%d').tolist()}")
                logger.debug(f"Effective Starts: {effective_starts.dt.strftime('%Y-%m-%d').tolist()}")
                logger.debug(f"Effective Ends:   {effective_ends.dt.strftime('%Y-%m-%d').tolist()}")
                logger.debug(f"---------------------------------------")

                # Drop NaT elements before finding absolute min and max bounds for the parent
                valid_effective_starts = effective_starts.dropna()
                valid_effective_ends = effective_ends.dropna()
                valid_real_starts = real_starts.dropna()
                valid_real_ends = real_ends.dropna()

                min_start = valid_effective_starts.min() if not valid_effective_starts.empty else pd.NaT
                max_end = valid_effective_ends.max() if not valid_effective_ends.empty else pd.NaT

                parent_days = AppConstants.DEFAULT_EST_DAYS
                parent_visual_days = AppConstants.DEFAULT_EST_DAYS
                if pd.notna(min_start) and pd.notna(max_end):
                    parent_days = max(1, CalendarEngine.get_working_days_duration(min_start, max_end))
                    parent_visual_days = max(1, CalendarEngine.get_visual_grid_span(min_start, max_end))

                parent_eng_start = valid_real_starts.min() if not valid_real_starts.empty else pd.NaT
                parent_comp_date = valid_real_ends.max() if not valid_real_ends.empty else pd.NaT

                first_row = group.iloc[0]
                all_complete = all(group['STATUS'].str.strip().str.upper() == 'COMPLETE')
                parent_status = 'COMPLETE' if all_complete else 'ACTIVE'

                assignees = [str(x).strip().upper() for x in group['ASSIGNED TO'].unique() if
                             str(x).strip().upper() not in ('', AppConstants.UNASSIGNED_LABEL, 'NAN')]
                parent_assignee = assignees[0] if len(assignees) == 1 else "MULTIPLE" if len(assignees) > 1 else AppConstants.UNASSIGNED_LABEL

                all_colors = [color_map.get(a, "#555555") for a in assignees] if assignees else ["#555555"]

                parent_color = color_map.get(parent_assignee, "#555555")
                if parent_assignee == "MULTIPLE": parent_color = "#888888"
                if parent_assignee in [AppConstants.UNASSIGNED_LABEL, "TBD", "NAN", ""]: parent_color = "#555555"

                reqs = group['REQUIREMENT'].unique()
                raw_req = reqs[0] if len(reqs) == 1 else "Multiple"

                due_dates = pd.to_datetime(group['ENG DUE DATE'].replace('', None), errors='coerce').dropna()
                max_due = due_dates.max() if not due_dates.empty else pd.NaT

                esd_dates = pd.to_datetime(group['ESD'].replace('', None), errors='coerce').dropna()
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
                    'ALL_ASSIGNEES': assignees,
                    'ALL_COLORS': all_colors,

                    'ENG START DATE': parent_eng_start.strftime('%m/%d/%Y') if pd.notna(parent_eng_start) else "",
                    'COMPLETE DATE': parent_comp_date.strftime('%m/%d/%Y') if pd.notna(parent_comp_date) else "",

                    'EST START DATE': min_start.strftime('%m/%d/%Y') if pd.notna(min_start) else "",
                    'EST END DATE': max_end.strftime('%m/%d/%Y') if pd.notna(max_end) else "",
                    'EST DAYS': str(parent_days),
                    'VISUAL_DAYS': parent_visual_days,
                    'ENG DUE DATE': max_due.strftime('%m/%d/%Y') if pd.notna(max_due) else "",
                    'ESD': min_esd.strftime('%m/%d/%Y') if pd.notna(min_esd) else "",
                    'EST ENG VARIANCE': parent_eng_var,
                    'EST ESD VARIANCE': parent_esd_var
                }
                visual_rows.append(parent_row)

                if project_id in expanded_projects:
                    for idx, row in group.iterrows():
                        try:
                            child_row: Dict[str, Any] = {str(k): v for k, v in row.items()}

                            child_row['IS_PARENT'] = False
                            child_row['REQUIREMENT'] = GanttDataBuilder.clean_requirement_text(child_row.get('REQUIREMENT', ''))

                            c_start = pd.to_datetime(child_row.get('EST START DATE', ''), errors='coerce')
                            c_end = pd.to_datetime(child_row.get('EST END DATE', ''), errors='coerce')

                            if pd.notna(c_start) and pd.notna(c_end):
                                child_row['VISUAL_DAYS'] = max(1, CalendarEngine.get_visual_grid_span(c_start, c_end))
                            else:
                                est_fallback = child_row.get('EST DAYS', AppConstants.DEFAULT_EST_DAYS)
                                child_row['VISUAL_DAYS'] = int(est_fallback) if str(est_fallback).isdigit() else 5

                            child_assignee = str(child_row.get('ASSIGNED TO', '')).strip().upper()

                            if child_assignee in ["", AppConstants.UNASSIGNED_LABEL, "NAN", "TBD"]:
                                child_color = "#555555"
                            else:
                                child_color = color_map.get(child_assignee, "#555555")

                            if str(child_row.get('STATUS', '')).strip().upper() == 'COMPLETE':
                                child_row['REQUIREMENT'] = f"✓ {child_row['REQUIREMENT']}"

                                if child_color.startswith("#") and len(child_color) == 7:
                                    try:
                                        r, g, b = int(child_color[1:3], 16), int(child_color[3:5], 16), int(child_color[5:7], 16)
                                        bg_r, bg_g, bg_b = 0x1E, 0x1E, 0x1E
                                        alpha = 0.3

                                        r = int(r * alpha + bg_r * (1 - alpha))
                                        g = int(g * alpha + bg_g * (1 - alpha))
                                        b = int(b * alpha + bg_b * (1 - alpha))
                                        child_color = f"#{r:02X}{g:02X}{b:02X}"
                                    except ValueError:
                                        pass

                            child_row['HEX_COLOR'] = child_color
                            child_row['ALL_ASSIGNEES'] = [child_assignee] if child_assignee else []
                            child_row['ALL_COLORS'] = [child_color]

                            visual_rows.append(child_row)

                        except Exception as e:
                            logger.error(f"Error processing child row for project {project_id}: {e}")

            except Exception as e:
                logger.error(f"Error processing project {project_id} group: {e}")

        return visual_rows