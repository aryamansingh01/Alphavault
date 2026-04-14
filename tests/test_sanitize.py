"""Tests for core/sanitize.py — data cleaning utilities."""
import numpy as np
import pandas as pd
import pytest

from core.sanitize import (
    sanitize_returns, safe_divide, clip_outliers, require_min_length,
    fill_missing_prices, validate_weights, is_valid_ticker, coerce_to_array,
)


# ---------------------------------------------------------------------------
# sanitize_returns
# ---------------------------------------------------------------------------

def test_sanitize_returns_replaces_nan():
    arr = sanitize_returns([1.0, float('nan'), 3.0])
    assert arr[1] == 0.0
    assert arr[0] == 1.0


def test_sanitize_returns_replaces_inf():
    arr = sanitize_returns([1.0, float('inf'), float('-inf')])
    assert arr[1] == 0.0
    assert arr[2] == 0.0


def test_sanitize_returns_clean_data_unchanged():
    data = [0.01, -0.02, 0.03]
    arr = sanitize_returns(data)
    np.testing.assert_array_almost_equal(arr, data)


def test_sanitize_returns_empty():
    arr = sanitize_returns([])
    assert len(arr) == 0


def test_sanitize_returns_none():
    arr = sanitize_returns(None)
    assert len(arr) == 0


def test_sanitize_returns_series():
    s = pd.Series([1.0, float('nan'), 3.0])
    arr = sanitize_returns(s)
    assert arr[1] == 0.0


# ---------------------------------------------------------------------------
# safe_divide
# ---------------------------------------------------------------------------

def test_safe_divide_normal():
    assert safe_divide(10, 2) == 5.0


def test_safe_divide_zero_denom():
    assert safe_divide(10, 0) == 0.0


def test_safe_divide_nan_denom():
    assert safe_divide(10, float('nan')) == 0.0


def test_safe_divide_inf_denom():
    assert safe_divide(10, float('inf')) == 0.0


def test_safe_divide_custom_default():
    assert safe_divide(10, 0, default=-1.0) == -1.0


# ---------------------------------------------------------------------------
# clip_outliers
# ---------------------------------------------------------------------------

def test_clip_outliers_clips_extreme():
    data = [1, 2, 3, 4, 5, 100]
    result = clip_outliers(data, n_std=2.0)
    assert result[-1] < 100


def test_clip_outliers_empty():
    result = clip_outliers([])
    assert len(result) == 0


def test_clip_outliers_single_element():
    result = clip_outliers([5.0])
    assert result[0] == 5.0


# ---------------------------------------------------------------------------
# require_min_length
# ---------------------------------------------------------------------------

def test_require_min_length_passes():
    require_min_length([1, 2, 3], 3)


def test_require_min_length_fails():
    with pytest.raises(ValueError, match="requires at least 5 observations, got 3"):
        require_min_length([1, 2, 3], 5)


# ---------------------------------------------------------------------------
# fill_missing_prices
# ---------------------------------------------------------------------------

def test_fill_missing_prices_ffill():
    df = pd.DataFrame({"close": [1.0, np.nan, np.nan, 4.0]})
    result = fill_missing_prices(df, method="ffill", limit=5)
    assert result["close"].iloc[1] == 1.0
    assert result["close"].iloc[2] == 1.0


def test_fill_missing_prices_interpolate():
    df = pd.DataFrame({"close": [1.0, np.nan, 3.0]})
    result = fill_missing_prices(df, method="interpolate")
    assert abs(result["close"].iloc[1] - 2.0) < 0.01


def test_fill_missing_prices_empty():
    result = fill_missing_prices(pd.DataFrame())
    assert result.empty


# ---------------------------------------------------------------------------
# validate_weights
# ---------------------------------------------------------------------------

def test_validate_weights_normalizes():
    w = validate_weights([2.0, 2.0, 6.0])
    assert abs(w.sum() - 1.0) < 1e-9
    assert abs(w[0] - 0.2) < 1e-9


def test_validate_weights_all_zeros():
    w = validate_weights([0, 0, 0])
    np.testing.assert_array_almost_equal(w, [1/3, 1/3, 1/3])


def test_validate_weights_clips_negatives():
    w = validate_weights([-1, 2, 3])
    assert w[0] == 0.0
    assert abs(w.sum() - 1.0) < 1e-9


def test_validate_weights_nan():
    w = validate_weights([float('nan'), 1.0, 1.0])
    assert w[0] == 0.0
    assert abs(w.sum() - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# is_valid_ticker
# ---------------------------------------------------------------------------

def test_valid_ticker_aapl():
    assert is_valid_ticker("AAPL") is True


def test_valid_ticker_brkb():
    assert is_valid_ticker("BRK.B") is True


def test_valid_ticker_empty():
    assert is_valid_ticker("") is False


def test_valid_ticker_invalid():
    assert is_valid_ticker("not a ticker!!") is False


def test_valid_ticker_lowercase():
    assert is_valid_ticker("aapl") is False


# ---------------------------------------------------------------------------
# coerce_to_array
# ---------------------------------------------------------------------------

def test_coerce_list():
    arr = coerce_to_array([1, 2, 3])
    assert isinstance(arr, np.ndarray)
    assert len(arr) == 3


def test_coerce_series():
    s = pd.Series([1.0, 2.0])
    arr = coerce_to_array(s)
    assert isinstance(arr, np.ndarray)
    assert len(arr) == 2


def test_coerce_single_float():
    arr = coerce_to_array(5.0)
    assert isinstance(arr, np.ndarray)
    assert len(arr) == 1
    assert arr[0] == 5.0


def test_coerce_none():
    arr = coerce_to_array(None)
    assert len(arr) == 0
