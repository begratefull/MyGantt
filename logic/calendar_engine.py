import logging
import numpy as np
import pandas as pd
from typing import Union, Any
from logic.constants import AppConstants

logger = logging.getLogger(__name__)


class CalendarEngine:
    """The central authority for all business-day date math in the application."""

    # --- SCALAR MATH (For UI Drag & Drop) ---
    @staticmethod
    def shift_date(start_date: Union[str, pd.Timestamp], shift_amount: int) -> Any:
        """Strictly shifts a date forward or backward by X working days."""
        if pd.isna(start_date) or shift_amount == 0:
            return pd.to_datetime(start_date)  # type: ignore
        try:
            dt = pd.to_datetime(start_date).date()
            dt_safe = np.busday_offset(dt, 0, holidays=AppConstants.COMPANY_HOLIDAYS, roll='forward')
            shifted = np.busday_offset(dt_safe, shift_amount, holidays=AppConstants.COMPANY_HOLIDAYS, roll='forward')
            return pd.to_datetime(shifted)  # type: ignore
        except ValueError:
            return pd.NaT

    @staticmethod
    def get_working_days_duration(start_date: Union[str, pd.Timestamp], end_date: Union[str, pd.Timestamp]) -> int:
        """Calculates exact INCLUSIVE working days between two dates (For task lengths)."""
        if pd.isna(start_date) or pd.isna(end_date):
            return 0
        try:
            d1_safe = np.busday_offset(pd.to_datetime(start_date).date(), 0, holidays=AppConstants.COMPANY_HOLIDAYS,
                                       roll='forward')
            d2_safe = np.busday_offset(pd.to_datetime(end_date).date(), 0, holidays=AppConstants.COMPANY_HOLIDAYS,
                                       roll='backward')
            raw = np.busday_count(d1_safe, d2_safe, holidays=AppConstants.COMPANY_HOLIDAYS)
            return int(raw + 1 if raw >= 0 else raw - 1)
        except ValueError:
            return 0

    @staticmethod
    def get_working_days_variance(start_date: Union[str, pd.Timestamp], end_date: Union[str, pd.Timestamp]) -> int:
        """Calculates exact EXCLUSIVE working days between two dates (For tracking delays/shifts)."""
        if pd.isna(start_date) or pd.isna(end_date):
            return 0
        try:
            d1_safe = np.busday_offset(pd.to_datetime(start_date).date(), 0, holidays=AppConstants.COMPANY_HOLIDAYS,
                                       roll='forward')
            d2_safe = np.busday_offset(pd.to_datetime(end_date).date(), 0, holidays=AppConstants.COMPANY_HOLIDAYS,
                                       roll='backward')
            return int(np.busday_count(d1_safe, d2_safe, holidays=AppConstants.COMPANY_HOLIDAYS))
        except ValueError:
            return 0

    # --- VECTORIZED MATH (For Lightning Fast Data Refreshes) ---
    @staticmethod
    def calculate_end_dates_vectorized(start_series: pd.Series, days_series: pd.Series) -> pd.Series:
        """Mass-calculates inclusive end dates for thousands of rows instantly."""
        res = pd.Series("", index=start_series.index)
        starts_dt = pd.to_datetime(start_series, errors='coerce')
        valid = starts_dt.notna() & days_series.notna()

        if valid.any():
            # Use to_numpy() to guarantee strict NumPy arrays instead of ambiguous ExtensionArrays
            s_np = starts_dt[valid].to_numpy(dtype='datetime64[D]')
            d_np = pd.to_numeric(days_series[valid], errors='coerce').fillna(AppConstants.DEFAULT_EST_DAYS).to_numpy(
                dtype=int)
            try:
                s_safe = np.busday_offset(s_np, 0, holidays=AppConstants.COMPANY_HOLIDAYS, roll='forward')
                adjusted_days = np.where(d_np > 0, d_np - 1, d_np)  # Inclusive math is now perfectly valid
                ends_np = np.busday_offset(s_safe, adjusted_days, holidays=AppConstants.COMPANY_HOLIDAYS,
                                           roll='forward')
                res.loc[valid] = pd.to_datetime(ends_np).strftime('%m/%d/%Y').tolist()  # type: ignore
            except Exception as e:  # type: ignore # noqa
                logger.exception("Calendar Engine Error: %s", e)
        return res

    @staticmethod
    def calculate_variance_vectorized(start_series: pd.Series, end_series: pd.Series) -> pd.Series:
        """Mass-calculates EXCLUSIVE working day variances."""
        res = pd.Series(np.nan, index=start_series.index, dtype=float)
        s_dt = pd.to_datetime(start_series, errors='coerce')
        e_dt = pd.to_datetime(end_series, errors='coerce')
        valid = s_dt.notna() & e_dt.notna()

        if valid.any():
            s_np = s_dt[valid].to_numpy(dtype='datetime64[D]')
            e_np = e_dt[valid].to_numpy(dtype='datetime64[D]')
            try:
                s_safe = np.busday_offset(s_np, 0, holidays=AppConstants.COMPANY_HOLIDAYS, roll='forward')
                e_safe = np.busday_offset(e_np, 0, holidays=AppConstants.COMPANY_HOLIDAYS, roll='forward')

                raw_diff = np.busday_count(s_safe, e_safe, holidays=AppConstants.COMPANY_HOLIDAYS)
                # pyrefly: ignore [no-matching-overload]
                res.loc[valid] = pd.Series(raw_diff.astype(float), index=res[valid].index)
            except Exception as e:
                logger.exception("Calendar Engine Error: %s", e)
        return res
