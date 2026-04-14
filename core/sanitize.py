"""
Data cleaning and validation utilities.
Used by all analytics modules to ensure clean inputs.
"""
import re
import numpy as np


def sanitize_returns(returns) -> np.ndarray:
    """Clean a returns array: replace NaN and Inf with 0.0.
    Accepts: np.ndarray, list, pd.Series, None.
    Always returns np.ndarray (1-D)."""
    if returns is None:
        return np.array([], dtype=float)
    arr = coerce_to_array(returns)
    if arr.size == 0:
        return arr
    arr = np.where(np.isfinite(arr), arr, 0.0)
    return arr


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division. Returns default if denominator is 0, NaN, or Inf."""
    try:
        if denominator == 0 or not np.isfinite(denominator):
            return default
        result = numerator / denominator
        if not np.isfinite(result):
            return default
        return float(result)
    except (TypeError, ValueError, ZeroDivisionError):
        return default


def clip_outliers(arr, n_std: float = 5.0) -> np.ndarray:
    """Clip values beyond n_std standard deviations from the mean.
    Handles empty array (returns as-is).
    Returns np.ndarray."""
    arr = coerce_to_array(arr)
    if arr.size < 2:
        return arr
    mean = np.mean(arr)
    std = np.std(arr, ddof=1)
    if std == 0 or not np.isfinite(std):
        return arr
    lower = mean - n_std * std
    upper = mean + n_std * std
    return np.clip(arr, lower, upper)


def require_min_length(arr, min_len: int, name: str = "data") -> None:
    """Raise ValueError if arr has fewer than min_len elements.
    Message: f'{name} requires at least {min_len} observations, got {len(arr)}'"""
    length = len(arr) if arr is not None else 0
    if length < min_len:
        raise ValueError(f"{name} requires at least {min_len} observations, got {length}")


def fill_missing_prices(df, method: str = "ffill", limit: int = 5):
    """Fill missing values in a price DataFrame.
    method: 'ffill' (forward fill) or 'interpolate' (linear interpolation).
    limit: max consecutive NaN to fill.
    Import pandas only when called."""
    import pandas as pd
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    if method == "ffill":
        return df.ffill(limit=limit)
    elif method == "interpolate":
        return df.interpolate(method="linear", limit=limit)
    return df


def validate_weights(weights) -> np.ndarray:
    """Validate and normalize portfolio weights.
    - Convert to np.ndarray
    - Replace NaN with 0
    - Clip negatives to 0 (long-only)
    - Normalize to sum to 1.0
    - If all zeros: return equal weights (1/n each)
    Returns np.ndarray."""
    arr = coerce_to_array(weights)
    if arr.size == 0:
        return arr
    arr = np.where(np.isfinite(arr), arr, 0.0)
    arr = np.maximum(arr, 0.0)
    s = arr.sum()
    if s <= 0:
        return np.ones(len(arr)) / len(arr)
    return arr / s


def is_valid_ticker(ticker: str) -> bool:
    """Basic validation: 1-10 uppercase alphanumeric characters, optionally with dots or hyphens.
    Examples: 'AAPL' -> True, 'BRK.B' -> True, '' -> False, 'not a ticker!!' -> False"""
    if not isinstance(ticker, str) or not ticker:
        return False
    return bool(re.match(r'^[A-Z0-9][A-Z0-9.\-]{0,9}$', ticker))


def coerce_to_array(data) -> np.ndarray:
    """Convert various inputs to 1-D np.ndarray.
    Handles: list, tuple, np.ndarray, pd.Series, single float/int.
    Single values become 1-element array."""
    if data is None:
        return np.array([], dtype=float)
    if isinstance(data, np.ndarray):
        return data.flatten().astype(float)
    if isinstance(data, (list, tuple)):
        return np.array(data, dtype=float)
    if isinstance(data, (int, float)):
        return np.array([data], dtype=float)
    # pd.Series or similar
    try:
        return np.asarray(data, dtype=float).flatten()
    except (TypeError, ValueError):
        return np.array([], dtype=float)
