"""Tests for core/calendar.py — trading calendar utilities."""
from datetime import date, datetime
import numpy as np
import pandas as pd
import pytest

from core.calendar import (
    us_market_holidays, is_trading_day, trading_days_between,
    previous_trading_day, next_trading_day, align_dates,
    annualization_factor, parse_date,
)


# ---------------------------------------------------------------------------
# Known holidays
# ---------------------------------------------------------------------------

def test_christmas_2024_not_trading_day():
    """2024-12-25 is Christmas — not a trading day."""
    assert is_trading_day("2024-12-25") is False


def test_christmas_eve_2024_is_trading_day():
    """2024-12-24 (Tuesday) is a trading day (early close, but still counts)."""
    assert is_trading_day("2024-12-24") is True


def test_weekend_not_trading_day():
    """Saturday and Sunday are not trading days."""
    assert is_trading_day("2024-12-21") is False  # Saturday
    assert is_trading_day("2024-12-22") is False  # Sunday


def test_mlk_day_2025():
    """MLK Day 2025: 3rd Monday of January = Jan 20."""
    assert is_trading_day("2025-01-20") is False


def test_good_friday_2025():
    """Good Friday 2025: April 18."""
    assert is_trading_day("2025-04-18") is False


def test_regular_weekday_is_trading_day():
    """A normal Wednesday with no holiday should be a trading day."""
    assert is_trading_day("2024-12-18") is True


def test_new_years_2025_observed():
    """2025-01-01 is Wednesday — New Year's Day, not a trading day."""
    assert is_trading_day("2025-01-01") is False


# ---------------------------------------------------------------------------
# previous/next trading day
# ---------------------------------------------------------------------------

def test_previous_trading_day_from_monday():
    """Previous trading day from a Monday (no holiday) returns previous Friday."""
    # 2024-12-23 is Monday. Previous Friday is 2024-12-20.
    result = previous_trading_day("2024-12-20")
    assert result == date(2024, 12, 20)  # Friday is a trading day, returns itself

    # From Saturday 2024-12-21
    result = previous_trading_day("2024-12-21")
    assert result == date(2024, 12, 20)


def test_previous_trading_day_from_trading_day():
    """Previous trading day from a trading day returns itself."""
    result = previous_trading_day("2024-12-18")
    assert result == date(2024, 12, 18)


def test_next_trading_day_from_weekend():
    """Next trading day from Saturday should be Monday (if not holiday)."""
    result = next_trading_day("2024-12-21")  # Saturday
    assert result == date(2024, 12, 23)  # Monday


# ---------------------------------------------------------------------------
# trading_days_between
# ---------------------------------------------------------------------------

def test_trading_days_between_known_week():
    """Mon-Fri with no holidays = 5 trading days."""
    # 2024-12-16 (Mon) to 2024-12-20 (Fri) — no holidays that week
    days = trading_days_between("2024-12-16", "2024-12-20")
    assert len(days) == 5


def test_trading_days_between_christmas_week():
    """Christmas week 2024: Dec 23 (Mon) to Dec 27 (Fri) — Dec 25 is holiday."""
    days = trading_days_between("2024-12-23", "2024-12-27")
    assert len(days) == 4
    assert date(2024, 12, 25) not in days


# ---------------------------------------------------------------------------
# align_dates
# ---------------------------------------------------------------------------

def test_align_dates_common_only():
    """align_dates returns only common dates."""
    idx1 = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    idx2 = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    df1 = pd.DataFrame({"a": [1, 2, 3]}, index=idx1)
    df2 = pd.DataFrame({"b": [4, 5, 6]}, index=idx2)
    a1, a2 = align_dates(df1, df2)
    assert len(a1) == 2
    assert len(a2) == 2


def test_align_dates_drops_nan():
    """align_dates drops rows where either DataFrame has NaN."""
    idx = pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"])
    df1 = pd.DataFrame({"a": [1, np.nan, 3]}, index=idx)
    df2 = pd.DataFrame({"b": [4, 5, 6]}, index=idx)
    a1, a2 = align_dates(df1, df2)
    assert len(a1) == 2


# ---------------------------------------------------------------------------
# annualization_factor
# ---------------------------------------------------------------------------

def test_annualization_factor_daily():
    assert annualization_factor("daily") == 252


def test_annualization_factor_monthly():
    assert annualization_factor("monthly") == 12


def test_annualization_factor_unknown():
    with pytest.raises(ValueError):
        annualization_factor("hourly")


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------

def test_parse_date_string():
    assert parse_date("2024-06-15") == date(2024, 6, 15)


def test_parse_date_datetime():
    dt = datetime(2024, 6, 15, 10, 30)
    assert parse_date(dt) == date(2024, 6, 15)


def test_parse_date_date_object():
    d = date(2024, 6, 15)
    assert parse_date(d) == d


def test_parse_date_pandas_timestamp():
    ts = pd.Timestamp("2024-06-15")
    assert parse_date(ts) == date(2024, 6, 15)


def test_parse_date_invalid():
    with pytest.raises(ValueError):
        parse_date("not-a-date")
