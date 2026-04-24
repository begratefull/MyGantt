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
        """Safely parses variance strings like '-5 days' into floats."""
        if pd.isna(val) or val == "":
            return np.nan
        try:
            return float(str(val).replace('days', '').strip())
        except Exception:
            return np.nan

    @staticmethod
    def split_base_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Splits the master dataframe into active, complete, production, and submittal bases.
        Returns: (active_df, comp_df, prod_base, quote_base)
        """
        if df.empty:
            return df, df, df, df

        if 'LINE_COUNT' not in df.columns:
            df['LINE_COUNT'] = 1

        active_df = df[df['STATUS'].str.strip().str.upper() != 'COMPLETE'].copy()
        comp_df = df[df['STATUS'].str.strip().str.upper() == 'COMPLETE'].copy()

        if not active_df.empty and 'REQUIREMENT' in active_df.columns:
            prod_mask = active_df['REQUIREMENT'].str.contains('PROD', case=False, na=False)
            prod_base = active_df[prod_mask].copy()
            quote_base = active_df[~prod_mask].copy()
        else:
            prod_base = pd.DataFrame(columns=df.columns)
            quote_base = pd.DataFrame(columns=df.columns)

        return active_df, comp_df, prod_base, quote_base

    @staticmethod
    def calculate_kpis(df: pd.DataFrame) -> Dict[str, Any]:
        """Calculates line counts and average day metrics for a given subset."""
        kpis = {'lines': 0, 'avg_var': np.nan, 'avg_queue': np.nan, 'avg_proc': np.nan}
        if df.empty:
            return kpis

        kpis['lines'] = int(df['LINE_COUNT'].sum()) if 'LINE_COUNT' in df.columns else 0

        def get_mean(col_name: str) -> float:
            if col_name in df.columns:
                parsed = df[col_name].apply(DashboardService.parse_variance).dropna()
                if not parsed.empty:
                    return float(parsed.mean())
            return np.nan

        kpis['avg_var'] = get_mean('EST ENG VARIANCE')
        kpis['avg_queue'] = get_mean('QUEUE_DAYS')
        kpis['avg_proc'] = get_mean('PROCESS_DAYS')

        return kpis

    @staticmethod
    def get_donut_distribution(df: pd.DataFrame) -> Dict[str, int]:
        """Aggregates line counts by assignee for pie/donut charts."""
        distribution = {}
        if df.empty or 'ASSIGNED TO' not in df.columns:
            return distribution

        engineers = df['ASSIGNED TO'].unique()
        for eng in engineers:
            eng_name = str(eng).strip().upper()
            if not eng_name:
                continue
            lines = int(df[df['ASSIGNED TO'] == eng]['LINE_COUNT'].sum())
            if lines > 0:
                distribution[eng_name] = lines
        return distribution

    @staticmethod
    def prepare_timeline_data(comp_df: pd.DataFrame, active_df: pd.DataFrame, start_date: pd.Timestamp) -> Tuple[
        List[str], List[str], pd.DataFrame]:
        """
        Merges completed actuals with active forecasts, calculates variances,
        and formats the dataset for the timeline bar chart.
        """
        h_df = comp_df.copy()
        if not h_df.empty:
            h_df['TARGET_DATE'] = pd.to_datetime(h_df.get('COMPLETE DATE', pd.NaT), errors='coerce')
            h_df['VAR_DAYS'] = h_df.get('COMPLETION VARIANCE', pd.Series(dtype=float)).apply(
                DashboardService.parse_variance).fillna(0)
            h_df['IS_FORECAST'] = False

        f_df = active_df.copy()
        if not f_df.empty:
            f_df['TARGET_DATE'] = pd.to_datetime(f_df.get('EST END DATE', pd.NaT), errors='coerce')
            f_df['VAR_DAYS'] = f_df.get('EST ENG VARIANCE', pd.Series(dtype=float)).apply(
                DashboardService.parse_variance).fillna(0)
            f_df['IS_FORECAST'] = True

        if h_df.empty and f_df.empty:
            return [], [], pd.DataFrame()

        df = pd.concat([h_df, f_df], ignore_index=True)
        if 'TARGET_DATE' in df.columns:
            df = df.dropna(subset=['TARGET_DATE'])
            df = df[(df['TARGET_DATE'] >= start_date) | (df['IS_FORECAST'] == True)].copy()

        if df.empty:
            return [], [], pd.DataFrame()

        df['YearWeek'] = df['TARGET_DATE'].dt.strftime('%G-%V')
        weeks = sorted(df['YearWeek'].unique().tolist())
        reqs = df['REQUIREMENT'].replace('', 'Uncategorized').unique().tolist()

        return weeks, reqs, df
