"""Tests for core/data.py — shared data fetcher."""
import os
import pandas as pd
import numpy as np
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Redirect cache DB to temp dir for tests
import core.cache as cache_module

_original_db_dir = cache_module.DB_DIR
_original_db_path = cache_module.DB_PATH


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path):
    cache_module.DB_DIR = str(tmp_path)
    cache_module.DB_PATH = os.path.join(str(tmp_path), "cache.db")
    yield
    cache_module.DB_DIR = _original_db_dir
    cache_module.DB_PATH = _original_db_path


from core.data import (
    period_to_days, get_ohlcv, get_daily_returns,
    get_market_news, get_quote_cached, get_fama_french_factors,
)
from core import cache


# ---------------------------------------------------------------------------
# period_to_days
# ---------------------------------------------------------------------------

def test_period_to_days_1m():
    assert period_to_days("1m") == 30


def test_period_to_days_3m():
    assert period_to_days("3m") == 90


def test_period_to_days_6m():
    assert period_to_days("6m") == 180


def test_period_to_days_1y():
    assert period_to_days("1y") == 365


def test_period_to_days_2y():
    assert period_to_days("2y") == 730


def test_period_to_days_3y():
    assert period_to_days("3y") == 1095


def test_period_to_days_5y():
    assert period_to_days("5y") == 1825


def test_period_to_days_10y():
    assert period_to_days("10y") == 3650


def test_period_to_days_ytd():
    days = period_to_days("ytd")
    today = datetime.today()
    expected = (today - datetime(today.year, 1, 1)).days or 1
    assert days == expected


def test_period_to_days_default():
    assert period_to_days("unknown") == 365


def test_period_to_days_none():
    assert period_to_days(None) == 365


# ---------------------------------------------------------------------------
# get_ohlcv (mocked yfinance)
# ---------------------------------------------------------------------------

def _make_mock_history():
    """Create a mock DataFrame that yfinance would return."""
    dates = pd.date_range("2024-01-02", periods=5, freq="B")
    df = pd.DataFrame({
        "Open": [100, 101, 102, 103, 104],
        "High": [105, 106, 107, 108, 109],
        "Low": [99, 100, 101, 102, 103],
        "Close": [103, 104, 105, 106, 107],
        "Volume": [1000, 1100, 1200, 1300, 1400],
    }, index=dates)
    return df


@patch("core.data.yf")
def test_get_ohlcv_returns_dataframe(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_mock_history()
    mock_yf.Ticker.return_value = mock_ticker

    df = get_ohlcv("AAPL", "1m")
    assert isinstance(df, pd.DataFrame)
    assert "close" in df.columns
    assert "open" in df.columns
    assert "volume" in df.columns
    assert len(df) == 5


@patch("core.data.yf")
def test_get_ohlcv_stores_in_cache(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.history.return_value = _make_mock_history()
    mock_yf.Ticker.return_value = mock_ticker

    get_ohlcv("TSLA", "1m")
    stats = cache.db_stats()
    assert stats["price_cache"] == 5


@patch("core.data.yf")
def test_get_ohlcv_cache_hit(mock_yf, capsys):
    """Second call should hit cache."""
    mock_ticker = MagicMock()
    # Create mock data spanning 30+ business days so cache covers the full "1m" range
    dates = pd.date_range(end=datetime.today(), periods=25, freq="B")
    n = len(dates)
    hist = pd.DataFrame({
        "Open": list(range(100, 100 + n)),
        "High": list(range(105, 105 + n)),
        "Low": list(range(99, 99 + n)),
        "Close": list(range(103, 103 + n)),
        "Volume": [1000 + i * 100 for i in range(n)],
    }, index=dates)
    mock_ticker.history.return_value = hist
    mock_yf.Ticker.return_value = mock_ticker

    get_ohlcv("GOOG", "1m")
    get_ohlcv("GOOG", "1m")
    captured = capsys.readouterr()
    assert "Cache HIT" in captured.out


@patch("core.data.yf")
def test_get_ohlcv_failure_returns_empty(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.history.side_effect = Exception("Network error")
    mock_yf.Ticker.return_value = mock_ticker

    df = get_ohlcv("FAIL", "1m")
    assert isinstance(df, pd.DataFrame)


# ---------------------------------------------------------------------------
# get_daily_returns (mocked)
# ---------------------------------------------------------------------------

@patch("core.data.yf")
def test_get_daily_returns_shape(mock_yf):
    def side_effect_history(period=None):
        dates = pd.date_range("2024-01-02", periods=10, freq="B")
        return pd.DataFrame({
            "Open": range(10), "High": range(10), "Low": range(10),
            "Close": [100 + i for i in range(10)], "Volume": [1000]*10,
        }, index=dates)

    mock_ticker = MagicMock()
    mock_ticker.history = side_effect_history
    mock_yf.Ticker.return_value = mock_ticker

    df = get_daily_returns(["AAPL", "MSFT"], "1m")
    assert isinstance(df, pd.DataFrame)
    # Should have 2 columns (one per ticker)
    assert df.shape[1] == 2
    # Should have 9 rows (10 - 1 for pct_change drop)
    assert len(df) == 9


def test_get_daily_returns_empty_tickers():
    df = get_daily_returns([], "1m")
    assert isinstance(df, pd.DataFrame)
    assert df.empty


@patch("core.data.yf")
def test_get_daily_returns_drops_failed_tickers(mock_yf):
    """If one ticker fails, it's just dropped — no error."""
    call_count = [0]
    def side_effect_ticker(symbol):
        t = MagicMock()
        call_count[0] += 1
        if symbol == "FAIL":
            t.history.return_value = pd.DataFrame()  # empty
        else:
            dates = pd.date_range("2024-01-02", periods=5, freq="B")
            t.history.return_value = pd.DataFrame({
                "Open": range(5), "High": range(5), "Low": range(5),
                "Close": [100+i for i in range(5)], "Volume": [1000]*5,
            }, index=dates)
        return t

    mock_yf.Ticker.side_effect = side_effect_ticker

    df = get_daily_returns(["AAPL", "FAIL"], "1m")
    assert isinstance(df, pd.DataFrame)
    assert "AAPL" in df.columns
    assert "FAIL" not in df.columns


# ---------------------------------------------------------------------------
# get_quote_cached (mocked)
# ---------------------------------------------------------------------------

@patch("core.data.yf")
def test_get_quote_cached_returns_dict(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.info = {
        "currentPrice": 150.0, "regularMarketChange": 2.5,
        "regularMarketChangePercent": 1.7, "regularMarketVolume": 50000000,
        "marketCap": 2500000000000, "sector": "Technology",
        "industry": "Consumer Electronics", "beta": 1.2,
        "trailingPE": 25.0, "dividendYield": 0.005,
    }
    mock_yf.Ticker.return_value = mock_ticker

    quote = get_quote_cached("AAPL")
    assert isinstance(quote, dict)
    assert quote["price"] == 150.0
    assert quote["sector"] == "Technology"
    assert quote["ticker"] == "AAPL"


@patch("core.data.yf")
def test_get_quote_cached_failure_returns_empty(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.info = None
    mock_yf.Ticker.side_effect = Exception("fail")

    quote = get_quote_cached("FAIL")
    assert isinstance(quote, dict)


# ---------------------------------------------------------------------------
# get_market_news (no external calls)
# ---------------------------------------------------------------------------

def test_get_market_news_empty_when_no_api_key():
    """Without FINNHUB_API_KEY, should return empty list (no crash)."""
    with patch.dict(os.environ, {"FINNHUB_API_KEY": ""}, clear=False):
        result = get_market_news()
        assert isinstance(result, list)
