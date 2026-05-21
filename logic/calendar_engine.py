import logging
import numpy as np
import pandas as pd
from datetime import date
from typing import Union, Optional, List, Dict
from logic.constants import AppConstants

logger = logging.getLogger(__name__)


class CalendarEngine:
    """The central authority for all business-day date math in the application."""

    # --- SCALAR MATH (For UI Drag & Drop) ---
    @staticmethod
    def shift_date(
            start_date: Union[str, pd.Timestamp],
            shift_amount: int,
            pto_dates: Optional[List[str]] = None
    ) ->Optional[pd.Timestamp]:
        """Strictly shifts a date forward or backward by X working days, skipping holidays and PTO."""
        # Safely handle missing starts
        if pd.isna(start_date):
            return None

        # Handle zero shifts
        if shift_amount == 0:
            return pd.Timestamp(start_date)

        # Merge company holidays with specific PTO dates
        custom_holidays = list(AppConstants.COMPANY_HOLIDAYS)
        if pto_dates:
            custom_holidays.extend(pto_dates)
            custom_holidays = list(set(custom_holidays))

        try:
            dt = pd.to_datetime(start_date).date()
            dt_safe = np.busday_offset(dt, 0, holidays=custom_holidays, roll='forward')
            shifted = np.busday_offset(dt_safe, shift_amount, holidays=custom_holidays, roll='forward')

            raw_result = shifted.item()

            if isinstance(raw_result, date):
                return pd.Timestamp(raw_result)

            return None

        except ValueError:
            return None

    @staticmethod
    def get_working_days_duration(
            start_date: Union[str, pd.Timestamp],
            end_date: Union[str, pd.Timestamp],
            pto_dates: Optional[List[str]] = None
    ) -> int:
        """Calculates exact INCLUSIVE working days between two dates (For task lengths)."""
        if pd.isna(start_date) or pd.isna(end_date):
            return 0

        custom_holidays = list(AppConstants.COMPANY_HOLIDAYS)
        if pto_dates:
            custom_holidays.extend(pto_dates)
            custom_holidays = list(set(custom_holidays))

        try:
            d1_safe = np.busday_offset(pd.to_datetime(start_date).date(), 0, holidays=custom_holidays, roll='forward')
            d2_safe = np.busday_offset(pd.to_datetime(end_date).date(), 0, holidays=custom_holidays, roll='backward')
            raw = np.busday_count(d1_safe, d2_safe, holidays=custom_holidays)
            return int(raw + 1 if raw >= 0 else raw - 1)
        except ValueError:
            return 0

    @staticmethod
    def get_working_days_variance(
            start_date: Union[str, pd.Timestamp],
            end_date: Union[str, pd.Timestamp],
            pto_dates: Optional[List[str]] = None
    ) -> int:
        """Calculates exact EXCLUSIVE working days between two dates (For tracking delays/shifts)."""
        if pd.isna(start_date) or pd.isna(end_date):
            return 0

        custom_holidays = list(AppConstants.COMPANY_HOLIDAYS)
        if pto_dates:
            custom_holidays.extend(pto_dates)
            custom_holidays = list(set(custom_holidays))

        try:
            d1_safe = np.busday_offset(pd.to_datetime(start_date).date(), 0, holidays=custom_holidays, roll='forward')
            d2_safe = np.busday_offset(pd.to_datetime(end_date).date(), 0, holidays=custom_holidays, roll='backward')
            return int(np.busday_count(d1_safe, d2_safe, holidays=custom_holidays))
        except ValueError:
            return 0

    # --- VECTORIZED MATH (For Lightning Fast Data Refreshes) ---
    @staticmethod
    def calculate_end_dates_vectorized(
            start_series: pd.Series,
            days_series: pd.Series,
            assignee_series: Optional[pd.Series] = None,
            pto_dict: Optional[Dict[str, List[str]]] = None
    ) -> pd.Series:
        """Mass-calculates inclusive end dates, applying specific PTO per assignee."""
        res = pd.Series("", index=start_series.index)
        starts_dt = pd.to_datetime(start_series, errors='coerce')
        valid = starts_dt.notna() & days_series.notna()

        if valid.any():
            valid_indices = start_series[valid].index

            # If no PTO dict is provided, pretend everyone is in a single "None" group
            assignees = assignee_series[valid_indices] if assignee_series is not None else pd.Series("None",
                                                                                                     index=valid_indices)

            # Loop through each unique assignee in this batch of rows
            for assignee in assignees.unique():
                assignee_mask = valid & (assignees == assignee)

                s_np = starts_dt[assignee_mask].to_numpy(dtype='datetime64[D]')
                d_np = pd.to_numeric(days_series[assignee_mask], errors='coerce').fillna(
                    AppConstants.DEFAULT_EST_DAYS).to_numpy(dtype=int)

                # Build custom holiday array for this specific assignee
                safe_assignee = str(assignee).strip().title()  # Try to normalize to match dictionary
                custom_holidays = list(AppConstants.COMPANY_HOLIDAYS)

                if pto_dict and safe_assignee in pto_dict:
                    custom_holidays.extend(pto_dict[safe_assignee])

                custom_holidays = list(set(custom_holidays))  # De-duplicate

                try:
                    s_safe = np.busday_offset(s_np, 0, holidays=custom_holidays, roll='forward')
                    adjusted_days = np.where(d_np > 0, d_np - 1, d_np)
                    ends_np = np.busday_offset(s_safe, adjusted_days, holidays=custom_holidays, roll='forward')
                    res.loc[assignee_mask] = pd.to_datetime(ends_np).strftime('%m/%d/%Y').tolist()
                except Exception as e:
                    logger.exception(f"Calendar Engine Error for {assignee}: %s", e)

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

    @staticmethod
    def get_visual_grid_span(start_date: Union[str, pd.Timestamp], end_date: Union[str, pd.Timestamp]) -> int:
        """
        Calculates Standard Business Days (M-F) ignoring holidays.
        This dictates exactly how many columns a block must span visually on the UI.
        """
        if pd.isna(start_date) or pd.isna(end_date):
            return 0
        try:
            # We strictly exclude 'holidays' here to map 1:1 with the UI BusinessDay grid
            d1_safe = pd.to_datetime(start_date).date()
            d2_safe = pd.to_datetime(end_date).date()
            raw = np.busday_count(d1_safe, d2_safe)
            return int(raw + 1 if raw >= 0 else raw - 1)
        except ValueError:
            return 0
