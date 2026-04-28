"""
Extracts Pandas dataframe math, KPI aggregations, and data formatting
away from the Dashboard UI, keeping the View strictly focused on rendering.
"""

from typing import Dict, Any, Tuple, List

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
    def _apply_mask(df: pd.DataFrame, col: str, search_terms: str) -> pd.DataFrame:
        if df.empty or col not in df.columns: return pd.DataFrame(columns=df.columns)
        mask = df[col].str.contains(search_terms, case=False, na=False)
        return df[mask]

    @staticmethod
    def calculate_advanced_kpis(active_df: pd.DataFrame, comp_df: pd.DataFrame) -> Dict[str, Any]:
        today = pd.Timestamp.today().normalize()
        ytd_start = pd.Timestamp(year=today.year, month=1, day=1)
        cur_start = today - pd.Timedelta(days=7)

        curr_active_df = DashboardService._get_current_backlog(active_df)
        comp_ytd = DashboardService._filter_completed_by_date(comp_df, ytd_start)
        comp_cur = DashboardService._filter_completed_by_date(comp_df, cur_start)

        type_col = 'TYPE' if 'TYPE' in curr_active_df.columns else 'REQUIREMENT'

        mod_act = DashboardService._apply_mask(curr_active_df, type_col, 'MOD')
        cus_act = DashboardService._apply_mask(curr_active_df, type_col, 'CUS')
        mod_ytd = DashboardService._apply_mask(comp_ytd, type_col, 'MOD')
        cus_ytd = DashboardService._apply_mask(comp_ytd, type_col, 'CUS')
        mod_cur = DashboardService._apply_mask(comp_cur, type_col, 'MOD')
        cus_cur = DashboardService._apply_mask(comp_cur, type_col, 'CUS')

        sub_regex = 'APP|SUB|QUOT|QUOTE|APPROVAL|SUBMITTAL'

        mod_prod_act = DashboardService._apply_mask(mod_act, 'REQUIREMENT', 'PROD')
        mod_sub_act = DashboardService._apply_mask(mod_act, 'REQUIREMENT', sub_regex)
        mod_prod_ytd, mod_sub_ytd = DashboardService._apply_mask(mod_ytd, 'REQUIREMENT', 'PROD'), DashboardService._apply_mask(mod_ytd, 'REQUIREMENT', sub_regex)
        mod_prod_cur, mod_sub_cur = DashboardService._apply_mask(mod_cur, 'REQUIREMENT', 'PROD'), DashboardService._apply_mask(mod_cur, 'REQUIREMENT', sub_regex)

        cus_prod_act = DashboardService._apply_mask(cus_act, 'REQUIREMENT', 'PROD')
        cus_sub_act = DashboardService._apply_mask(cus_act, 'REQUIREMENT', sub_regex)
        cus_prod_ytd, cus_sub_ytd = DashboardService._apply_mask(cus_ytd, 'REQUIREMENT', 'PROD'), DashboardService._apply_mask(cus_ytd, 'REQUIREMENT', sub_regex)
        cus_prod_cur, cus_sub_cur = DashboardService._apply_mask(cus_cur, 'REQUIREMENT', 'PROD'), DashboardService._apply_mask(cus_cur, 'REQUIREMENT', sub_regex)

        global_ytd = DashboardService._calc_subset_metrics(curr_active_df, comp_ytd)
        global_cur = DashboardService._calc_subset_metrics(curr_active_df, comp_cur)

        return {
            'global': {
                'backlog': int(curr_active_df['LINE_COUNT'].sum()) if 'LINE_COUNT' in curr_active_df.columns else 0,
                'delivery_ytd': global_ytd['on_time'],
                'delivery_cur': global_cur['on_time']
            },
            'mod': {
                'prod': {'ytd': DashboardService._calc_subset_metrics(mod_prod_act, mod_prod_ytd), 'cur': DashboardService._calc_subset_metrics(mod_prod_act, mod_prod_cur)},
                'sub': {'ytd': DashboardService._calc_subset_metrics(mod_sub_act, mod_sub_ytd), 'cur': DashboardService._calc_subset_metrics(mod_sub_act, mod_sub_cur)}
            },
            'cus': {
                'prod': {'ytd': DashboardService._calc_subset_metrics(cus_prod_act, cus_prod_ytd), 'cur': DashboardService._calc_subset_metrics(cus_prod_act, cus_prod_cur)},
                'sub': {'ytd': DashboardService._calc_subset_metrics(cus_sub_act, cus_sub_ytd), 'cur': DashboardService._calc_subset_metrics(cus_sub_act, cus_sub_cur)}
            }
        }

    @staticmethod
    def get_detailed_donut_data(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
        """Prepares detailed hierarchical data for the interactive hover charts."""
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