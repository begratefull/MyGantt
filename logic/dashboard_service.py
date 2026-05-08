"""
Extracts Pandas dataframe math, KPI aggregations, and data formatting
away from the Dashboard UI, keeping the View strictly focused on rendering.
"""

from typing import Dict, Any, Tuple, List
import re

import numpy as np
import pandas as pd


class DashboardService:
    """
    Handles data aggregation, KPI math, and dataset preparation for the Dashboard UI.
    """

    @staticmethod
    def parse_variance(val: Any) -> float:
        if pd.isna(val) or val == "": return np.nan
        try: return float(str(val).replace('days', '').strip())
        except Exception: return np.nan

    @staticmethod
    def split_base_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        if df.empty: return df, df
        if 'LINE_COUNT' not in df.columns: df['LINE_COUNT'] = 1

        active_df = df[df['STATUS'].str.strip().str.upper() != 'COMPLETE'].copy()
        comp_df = df[df['STATUS'].str.strip().str.upper() == 'COMPLETE'].copy()
        return active_df, comp_df

    @staticmethod
    def _get_current_backlog(active_df: pd.DataFrame) -> pd.DataFrame:
        if active_df.empty: return active_df

        is_unassigned = (
            active_df['ASSIGNED TO'].isna() |
            (active_df['ASSIGNED TO'].str.strip() == '') |
            (active_df['ASSIGNED TO'].str.upper() == 'UNASSIGNED')
        )

        today = pd.Timestamp.today().normalize()
        start_dates = pd.to_datetime(active_df.get('EST START DATE', pd.Series(pd.NaT, index=active_df.index)), errors='coerce')
        is_started = start_dates <= today
        no_start_date = start_dates.isna()

        mask = is_unassigned | is_started | no_start_date
        return active_df[mask]

    @staticmethod
    def _filter_completed_by_date(comp_df: pd.DataFrame, start_date: pd.Timestamp) -> pd.DataFrame:
        if comp_df.empty: return comp_df
        df = comp_df.copy()
        dates = pd.to_datetime(df['COMPLETE DATE'].replace('', pd.NaT), errors='coerce')
        return df[dates >= start_date]

    @staticmethod
    def _calc_subset_metrics(active_df: pd.DataFrame, comp_df: pd.DataFrame) -> Dict[str, float]:
        metrics = {'variance': np.nan, 'queue': np.nan, 'productivity': np.nan, 'on_time': 100.0}

        act_var = active_df['EST ENG VARIANCE'].apply(DashboardService.parse_variance).dropna() if 'EST ENG VARIANCE' in active_df.columns else pd.Series(dtype=float)
        comp_var = comp_df['COMPLETION VARIANCE'].apply(DashboardService.parse_variance).dropna() if 'COMPLETION VARIANCE' in comp_df.columns else pd.Series(dtype=float)
        all_var = pd.concat([act_var, comp_var])

        if not all_var.empty:
            metrics['variance'] = float(all_var.mean())
            metrics['on_time'] = (float((all_var >= 0).sum()) / len(all_var)) * 100.0

        act_q = active_df['QUEUE_DAYS'].apply(DashboardService.parse_variance).dropna() if 'QUEUE_DAYS' in active_df.columns else pd.Series(dtype=float)
        comp_q = comp_df['QUEUE_DAYS'].apply(DashboardService.parse_variance).dropna() if 'QUEUE_DAYS' in comp_df.columns else pd.Series(dtype=float)
        all_q = pd.concat([act_q, comp_q])
        if not all_q.empty: metrics['queue'] = float(all_q.mean())

        act_prod = pd.to_numeric(active_df['EST DAYS'], errors='coerce').dropna() if 'EST DAYS' in active_df.columns else pd.Series(dtype=float)
        comp_prod = comp_df['PROCESS_DAYS'].apply(DashboardService.parse_variance).dropna() if 'PROCESS_DAYS' in comp_df.columns else pd.Series(dtype=float)
        all_prod = pd.concat([act_prod, comp_prod])
        if not all_prod.empty: metrics['productivity'] = float(all_prod.mean())

        return metrics

    @staticmethod
    def _apply_exact_mask(df: pd.DataFrame, col: str, exact_val: str) -> pd.DataFrame:
        if df.empty or col not in df.columns: return pd.DataFrame(columns=df.columns)
        mask = df[col].str.strip().str.upper() == exact_val.strip().upper()
        return df[mask]

    @staticmethod
    def _apply_regex_mask(df: pd.DataFrame, col: str, search_terms: str) -> pd.DataFrame:
        if df.empty or col not in df.columns: return pd.DataFrame(columns=df.columns)
        mask = df[col].str.contains(search_terms, case=False, na=False)
        return df[mask]

    @staticmethod
    def calculate_advanced_kpis(active_df: pd.DataFrame, comp_df: pd.DataFrame, full_df: pd.DataFrame, current_team_filter: str) -> Dict[str, Any]:
        """Dynamically calculates KPIs based on the selected team context."""
        today = pd.Timestamp.today().normalize()
        ytd_start = pd.Timestamp(year=today.year, month=1, day=1)
        cur_start = today - pd.Timedelta(days=7)

        curr_active_df = DashboardService._get_current_backlog(active_df)
        comp_ytd = DashboardService._filter_completed_by_date(comp_df, ytd_start)
        comp_cur = DashboardService._filter_completed_by_date(comp_df, cur_start)

        sub_regex = 'APP|SUB|QUOT|QUOTE|APPROVAL|SUBMITTAL'
        is_prod_act = curr_active_df['REQUIREMENT'].str.contains('PROD', case=False, na=False) if 'REQUIREMENT' in curr_active_df.columns else pd.Series(False, index=curr_active_df.index)
        is_sub_act = curr_active_df['REQUIREMENT'].str.contains(sub_regex, case=False, na=False) if 'REQUIREMENT' in curr_active_df.columns else pd.Series(False, index=curr_active_df.index)

        global_ytd = DashboardService._calc_subset_metrics(curr_active_df, comp_ytd)
        global_cur = DashboardService._calc_subset_metrics(curr_active_df, comp_cur)

        kpis = {
            'global': {
                'backlog_total': int(curr_active_df['LINE_COUNT'].sum()) if 'LINE_COUNT' in curr_active_df.columns else 0,
                'backlog_prod': int(curr_active_df[is_prod_act]['LINE_COUNT'].sum()) if 'LINE_COUNT' in curr_active_df.columns else 0,
                'backlog_sub': int(curr_active_df[is_sub_act]['LINE_COUNT'].sum()) if 'LINE_COUNT' in curr_active_df.columns else 0,
                'delivery_ytd': global_ytd['on_time'],
                'delivery_cur': global_cur['on_time']
            },
            'view_type': 'health',
            'cards': []
        }

        team_upper = current_team_filter.strip().upper()
        type_col = 'TYPE' if 'TYPE' in curr_active_df.columns else 'REQUIREMENT'

        if team_upper == "ALL TEAMS":
            kpis['view_type'] = 'flow'
            for t_name in ["CUSTOM TEAM", "STANDARD TEAM"]:
                t_full = full_df[full_df['CALC_TEAM'] == t_name] if 'CALC_TEAM' in full_df.columns else pd.DataFrame()
                t_act = curr_active_df[curr_active_df['CALC_TEAM'] == t_name] if 'CALC_TEAM' in curr_active_df.columns else pd.DataFrame()
                t_comp = comp_cur[comp_cur['CALC_TEAM'] == t_name] if 'CALC_TEAM' in comp_cur.columns else pd.DataFrame()

                dates_in = pd.to_datetime(t_full['DATE TO ENG'].replace('', pd.NaT), errors='coerce') if 'DATE TO ENG' in t_full.columns else pd.Series(dtype=float)
                incoming = int((dates_in >= cur_start).sum())
                outgoing = int(t_comp['LINE_COUNT'].sum()) if 'LINE_COUNT' in t_comp.columns else 0
                backlog = int(t_act['LINE_COUNT'].sum()) if 'LINE_COUNT' in t_act.columns else 0

                kpis['cards'].append({
                    'title': f"{t_name.title()} Flow (Last 7 Days)",
                    'incoming': incoming,
                    'outgoing': outgoing,
                    'net': incoming - outgoing,
                    'backlog': backlog
                })

        else:
            kpis['view_type'] = 'health'
            line_types = []

            if team_upper == "CUSTOM TEAM":
                line_types = ['MOD', 'CUS']
            elif team_upper == "STANDARD TEAM":
                line_types = ['STD', 'STD-M']

            for l_type in line_types:
                t_act = DashboardService._apply_exact_mask(curr_active_df, type_col, l_type)
                t_ytd = DashboardService._apply_exact_mask(comp_ytd, type_col, l_type)
                t_cur = DashboardService._apply_exact_mask(comp_cur, type_col, l_type)

                prod_act = DashboardService._apply_regex_mask(t_act, 'REQUIREMENT', 'PROD')
                sub_act = DashboardService._apply_regex_mask(t_act, 'REQUIREMENT', sub_regex)

                prod_ytd = DashboardService._apply_regex_mask(t_ytd, 'REQUIREMENT', 'PROD')
                sub_ytd = DashboardService._apply_regex_mask(t_ytd, 'REQUIREMENT', sub_regex)

                prod_cur = DashboardService._apply_regex_mask(t_cur, 'REQUIREMENT', 'PROD')
                sub_cur = DashboardService._apply_regex_mask(t_cur, 'REQUIREMENT', sub_regex)

                kpis['cards'].append({
                    'title': f"{l_type} Health",
                    'prod': {
                        'ytd': DashboardService._calc_subset_metrics(prod_act, prod_ytd),
                        'cur': DashboardService._calc_subset_metrics(prod_act, prod_cur)
                    },
                    'sub': {
                        'ytd': DashboardService._calc_subset_metrics(sub_act, sub_ytd),
                        'cur': DashboardService._calc_subset_metrics(sub_act, sub_cur)
                    }
                })

        return kpis

    @staticmethod
    def get_detailed_donut_data(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        distribution = {}
        curr_active_df = DashboardService._get_current_backlog(df)
        if curr_active_df.empty or 'ASSIGNED TO' not in curr_active_df.columns: return distribution

        for eng in curr_active_df['ASSIGNED TO'].unique():
            eng_name = str(eng).strip().upper()
            if not eng_name: continue

            eng_df = curr_active_df[curr_active_df['ASSIGNED TO'] == eng]
            total_lines = int(eng_df['LINE_COUNT'].sum())
            if total_lines == 0: continue

            req_counts = {}
            if 'REQUIREMENT' in eng_df.columns:
                for req in eng_df['REQUIREMENT'].replace('', 'Uncategorized').unique():
                    req_name = str(req).strip()
                    count = int(eng_df[eng_df['REQUIREMENT'].replace('', 'Uncategorized') == req_name]['LINE_COUNT'].sum())
                    if count > 0:
                        req_counts[req_name] = count

            distribution[eng_name] = {
                'total': total_lines,
                'reqs': req_counts
            }

        return dict(sorted(distribution.items(), key=lambda item: item[1]['total'], reverse=True))

    @staticmethod
    def prepare_timeline_data(comp_df: pd.DataFrame, active_df: pd.DataFrame, start_date: pd.Timestamp) -> Tuple[List[str], List[str], pd.DataFrame]:
        h_df = comp_df.copy()
        if not h_df.empty:
            h_df['TARGET_DATE'] = pd.to_datetime(h_df.get('COMPLETE DATE', pd.NaT), errors='coerce')
            h_df['VAR_DAYS'] = h_df.get('COMPLETION VARIANCE', pd.Series(dtype=float)).apply(DashboardService.parse_variance).fillna(0)
            h_df['IS_FORECAST'] = False

        f_df = active_df.copy()
        if not f_df.empty:
            f_df['TARGET_DATE'] = pd.to_datetime(f_df.get('EST END DATE', pd.NaT), errors='coerce')
            f_df['VAR_DAYS'] = f_df.get('EST ENG VARIANCE', pd.Series(dtype=float)).apply(DashboardService.parse_variance).fillna(0)
            f_df['IS_FORECAST'] = True

        if h_df.empty and f_df.empty: return [], [], pd.DataFrame()

        df = pd.concat([h_df, f_df], ignore_index=True)
        if 'TARGET_DATE' in df.columns:
            df = df.dropna(subset=['TARGET_DATE'])
            df = df[(df['TARGET_DATE'] >= start_date) | (df['IS_FORECAST'] == True)].copy()

        if df.empty: return [], [], pd.DataFrame()

        df['YearWeek'] = df['TARGET_DATE'].dt.strftime('%G-%V')
        weeks = sorted(df['YearWeek'].unique().tolist())
        reqs = df['REQUIREMENT'].replace('', 'Uncategorized').unique().tolist()

        return weeks, reqs, df

    @staticmethod
    def get_engineer_performance(full_df: pd.DataFrame, engineer_name: str) -> Dict[str, Any]:
        """
        Crunches YTD throughput, top projects, and top 5 fixture families,
        along with overall KPI totals.
        """
        valid_types = ['STD', 'STD-M', 'MOD', 'CUS', 'PART', 'PART-MC', 'WARRANTY', 'SAMPLE', 'RENOV']
        eng_df = full_df[full_df['ASSIGNED TO'].str.strip().str.upper() == engineer_name.strip().upper()].copy()

        if eng_df.empty:
            return {
                'throughput': {'prod': {}, 'sub': {}},
                'projects': [],
                'radar': {'categories': [], 'prod': []},
                'kpis': {'total_prod': 0, 'total_sub': 0}
            }

        eng_df['CLEAN_TYPE'] = eng_df.get('TYPE', pd.Series(dtype=str)).str.strip().str.upper()
        eng_df = eng_df[eng_df['CLEAN_TYPE'].isin(valid_types)]

        # --- Bulletproof Currency Parser ---
        def parse_sell(val):
            if pd.isna(val) or val == "": return 0.0
            try:
                clean_str = re.sub(r'[^\d.]', '', str(val))
                return float(clean_str) if clean_str else 0.0
            except:
                return 0.0

        eng_df['CLEAN_SELL'] = eng_df.get('SELL $', pd.Series(dtype=float)).apply(parse_sell)

        is_prod = eng_df['REQUIREMENT'].str.contains('PROD', case=False, na=False)
        is_sub = eng_df['REQUIREMENT'].str.contains('APP|SUB|QUOT|QUOTE|APPROVAL|SUBMITTAL', case=False, na=False)

        prod_df = eng_df[is_prod]
        sub_df = eng_df[is_sub]

        # Calculate raw KPI totals
        total_prod = int(prod_df['LINE_COUNT'].sum() if 'LINE_COUNT' in prod_df.columns else len(prod_df))
        total_sub = int(sub_df['LINE_COUNT'].sum() if 'LINE_COUNT' in sub_df.columns else len(sub_df))

        # --- Adjusted Throughput Calculation ---
        def calc_throughput(subset):
            stats = {}
            for l_type in valid_types:
                type_df = subset[subset['CLEAN_TYPE'] == l_type]
                lines = int(type_df['LINE_COUNT'].sum()) if 'LINE_COUNT' in type_df.columns else len(type_df)
                if lines > 0:
                    # UPDATED to use PROCESS_DAYS instead of Queue/EST DAYS
                    if 'PROCESS_DAYS' in type_df.columns:
                        avg_days = type_df['PROCESS_DAYS'].apply(DashboardService.parse_variance).mean()
                    elif 'DAYS IN ENG' in type_df.columns:
                        avg_days = pd.to_numeric(type_df['DAYS IN ENG'], errors='coerce').mean()
                    else:
                        avg_days = pd.to_numeric(type_df['EST DAYS'], errors='coerce').mean()

                    stats[l_type] = {'lines': lines, 'avg_days': float(avg_days) if pd.notna(avg_days) else 0.0}
            return stats

        throughput = {
            'prod': calc_throughput(prod_df),
            'sub': calc_throughput(sub_df)
        }

        # --- Top High-Value Projects ---
        def clean_project(name):
            name = str(name).replace('\n', ' ').strip()
            pattern = r'(?i)\s*(?:-|–|—|\()?\s*(?:REL\b|PHASE\b|PART\b|REORDER\b|REQUOTE\b|REPLACEMENT\b|ARO FLOW).*$'
            cleaned = re.sub(pattern, '', name).strip()
            return re.sub(r'\s*[-–—]\s*$', '', cleaned) if cleaned else name

        proj_col = 'PROJECT NAME' if 'PROJECT NAME' in eng_df.columns else (
            'SHIP TO NUMBER\n(PROJECT)' if 'SHIP TO NUMBER\n(PROJECT)' in eng_df.columns else 'PROJECT_ID')
        eng_df['FUZZY_PROJ'] = eng_df.get(proj_col, pd.Series(dtype=str)).apply(clean_project)

        proj_group = eng_df.groupby('FUZZY_PROJ').agg(
            lines=('LINE_COUNT', 'sum') if 'LINE_COUNT' in eng_df.columns else ('SMART_ID', 'count'),
            total_sell=('CLEAN_SELL', 'sum')
        ).reset_index()

        top_projects = proj_group.sort_values('total_sell', ascending=False).head(5).to_dict('records')

        # --- Radar Chart ---
        fam_col = 'FAMILY_PREFIX'
        if fam_col not in eng_df.columns:
            eng_df[fam_col] = 'UNKNOWN'

        valid_fams = prod_df[prod_df[fam_col] != 'UNKNOWN']
        top_fams = valid_fams[fam_col].value_counts().head(5).index.tolist()

        radar_data = {'categories': [], 'prod': []}

        for fam in top_fams:
            fam_df = prod_df[prod_df[fam_col] == fam]
            p_lines = int(fam_df['LINE_COUNT'].sum() if 'LINE_COUNT' in fam_df.columns else len(fam_df))

            radar_data['categories'].append(fam)
            radar_data['prod'].append(p_lines)

        pad_spaces = 1
        while len(radar_data['categories']) < 5:
            radar_data['categories'].append(" " * pad_spaces)
            radar_data['prod'].append(0)
            pad_spaces += 1

        return {
            'throughput': throughput,
            'projects': top_projects,
            'radar': radar_data,
            'kpis': {
                'total_prod': total_prod,
                'total_sub': total_sub
            }
        }