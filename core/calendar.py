"""
Trading calendar utilities for US equity markets.
Uses only Python stdlib — no external dependencies at module level.
"""
from datetime import datetime, date, timedelta
import calendar


# ---------------------------------------------------------------------------
# Date parsing helper
# ---------------------------------------------------------------------------

def parse_date(d) -> date:
    """Convert various date inputs to a date object.
    Accepts: date, datetime, 'YYYY-MM-DD' string, pandas Timestamp.
    Raises ValueError for unparseable input."""
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str):
        try:
            return datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"Cannot parse date string: {d!r}. Expected YYYY-MM-DD format.")
    # pandas Timestamp
    try:
        return d.date()
    except AttributeError:
        pass
    raise ValueError(f"Cannot parse date: {d!r}")


# ---------------------------------------------------------------------------
# Easter computation (Anonymous Gregorian algorithm — Meeus/Jones/Butcher)
# ---------------------------------------------------------------------------

def _easter(year: int) -> date:
    """Compute Easter Sunday for a given year using the Anonymous Gregorian algorithm."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


# ---------------------------------------------------------------------------
# Holiday observation rules
# ---------------------------------------------------------------------------

def _observed(d: date) -> date:
    """If holiday falls on Saturday, observed Friday. If Sunday, observed Monday."""
    if d.weekday() == 5:  # Saturday
        return d - timedelta(days=1)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """Return the nth occurrence of a weekday in a given month.
    weekday: 0=Monday, 6=Sunday. n: 1-based."""
    first = date(year, month, 1)
    # Days until the first occurrence of the target weekday
    delta = (weekday - first.weekday()) % 7
    first_occ = first + timedelta(days=delta)
    return first_occ + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    """Return the last occurrence of a weekday in a given month."""
    last_day = date(year, month, calendar.monthrange(year, month)[1])
    delta = (last_day.weekday() - weekday) % 7
    return last_day - timedelta(days=delta)


# ---------------------------------------------------------------------------
# US Market Holidays
# ---------------------------------------------------------------------------

def us_market_holidays(year: int) -> list:
    """Return list of date objects for all US market holidays in given year.
    Handles observed rules (Saturday -> Friday, Sunday -> Monday).
    Computes Easter/Good Friday correctly."""
    holidays = []

    # New Year's Day: Jan 1 (observed)
    holidays.append(_observed(date(year, 1, 1)))

    # MLK Day: 3rd Monday of January
    holidays.append(_nth_weekday(year, 1, 0, 3))

    # Presidents' Day: 3rd Monday of February
    holidays.append(_nth_weekday(year, 2, 0, 3))

    # Good Friday: Friday before Easter Sunday
    easter = _easter(year)
    holidays.append(easter - timedelta(days=2))

    # Memorial Day: last Monday of May
    holidays.append(_last_weekday(year, 5, 0))

    # Juneteenth: June 19 (observed)
    holidays.append(_observed(date(year, 6, 19)))

    # Independence Day: July 4 (observed)
    holidays.append(_observed(date(year, 7, 4)))

    # Labor Day: 1st Monday of September
    holidays.append(_nth_weekday(year, 9, 0, 1))

    # Thanksgiving: 4th Thursday of November
    holidays.append(_nth_weekday(year, 11, 3, 4))

    # Christmas: Dec 25 (observed)
    holidays.append(_observed(date(year, 12, 25)))

    return sorted(holidays)


# ---------------------------------------------------------------------------
# Trading day functions
# ---------------------------------------------------------------------------

def is_trading_day(d) -> bool:
    """Returns True if the given date is a US market trading day.
    A trading day is a weekday that is not a market holiday."""
    d = parse_date(d)
    if d.weekday() >= 5:  # weekend
        return False
    return d not in us_market_holidays(d.year)


def trading_days_between(start, end) -> list:
    """Return list of date objects for all trading days between start and end (inclusive)."""
    start = parse_date(start)
    end = parse_date(end)
    if start > end:
        return []
    holidays = set(us_market_holidays(start.year))
    if end.year != start.year:
        for y in range(start.year, end.year + 1):
            holidays.update(us_market_holidays(y))

    result = []
    current = start
    while current <= end:
        if current.weekday() < 5 and current not in holidays:
            result.append(current)
        current += timedelta(days=1)
    return result


def previous_trading_day(d) -> date:
    """Return the most recent trading day on or before d.
    If d is a trading day, returns d."""
    d = parse_date(d)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def next_trading_day(d) -> date:
    """Return the next trading day on or after d.
    If d is a trading day, returns d."""
    d = parse_date(d)
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def align_dates(df1, df2) -> tuple:
    """Align two DataFrames to their common DatetimeIndex.
    Returns (df1_aligned, df2_aligned) with only dates present in both.
    Drops any rows where either has NaN after alignment.
    Handles tz-aware/tz-naive mismatch by normalizing both to tz-naive."""
    import pandas as pd
    idx1 = df1.index
    idx2 = df2.index
    # Normalize timezone: strip tz from both if either is tz-aware
    if hasattr(idx1, 'tz') and idx1.tz is not None:
        df1 = df1.copy()
        df1.index = idx1.tz_localize(None)
    if hasattr(idx2, 'tz') and idx2.tz is not None:
        df2 = df2.copy()
        df2.index = idx2.tz_localize(None)
    # Normalize to date-level precision (drop time component) to handle mismatched timestamps
    df1 = df1.copy()
    df2 = df2.copy()
    df1.index = pd.to_datetime(df1.index.date)
    df2.index = pd.to_datetime(df2.index.date)
    common = df1.index.intersection(df2.index)
    df1_aligned = df1.loc[common]
    df2_aligned = df2.loc[common]
    # Drop rows where either has NaN
    mask = df1_aligned.notna().all(axis=1) & df2_aligned.notna().all(axis=1)
    return df1_aligned.loc[mask], df2_aligned.loc[mask]


def annualization_factor(frequency: str = "daily") -> int:
    """Return the annualization factor for a given frequency.
    'daily' -> 252, 'weekly' -> 52, 'monthly' -> 12, 'quarterly' -> 4, 'annual' -> 1
    Raises ValueError for unknown frequency."""
    mapping = {
        "daily": 252,
        "weekly": 52,
        "monthly": 12,
        "quarterly": 4,
        "annual": 1,
    }
    freq = frequency.lower()
    if freq not in mapping:
        raise ValueError(f"Unknown frequency: {frequency!r}. Expected one of {list(mapping.keys())}")
    return mapping[freq]
