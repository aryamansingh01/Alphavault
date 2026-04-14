"""Tests for core/sectorscan.py — Multi-Factor Stock Screener."""
import os
import pytest
from unittest.mock import patch, MagicMock

import core.cache as cache_module

_orig_dir = cache_module.DB_DIR
_orig_path = cache_module.DB_PATH


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path):
    cache_module.DB_DIR = str(tmp_path)
    cache_module.DB_PATH = os.path.join(str(tmp_path), "cache.db")
    yield
    cache_module.DB_DIR = _orig_dir
    cache_module.DB_PATH = _orig_path


from core.sectorscan import (
    get_fundamentals, get_fundamentals_batch, screen_stocks,
    rank_by_metric, composite_score, rank_with_composite,
    preset_screens, _passes_filters, DEFAULT_UNIVERSE,
)


# ---------------------------------------------------------------------------
# Synthetic stock data for testing
# ---------------------------------------------------------------------------

def _make_stocks():
    return [
        {"ticker": "AAPL", "name": "Apple", "sector": "Technology", "pe": 28, "pb": 35,
         "roe": 0.60, "profit_margin": 0.25, "dividend_yield": 0.005, "debt_equity": 1.5,
         "revenue_growth": 0.08, "fcf_yield": 0.04, "market_cap": 3e12, "beta": 1.2},
        {"ticker": "JPM", "name": "JPMorgan", "sector": "Financials", "pe": 12, "pb": 1.8,
         "roe": 0.15, "profit_margin": 0.30, "dividend_yield": 0.025, "debt_equity": 2.0,
         "revenue_growth": 0.05, "fcf_yield": 0.06, "market_cap": 500e9, "beta": 1.0},
        {"ticker": "KO", "name": "Coca-Cola", "sector": "Consumer Staples", "pe": 22, "pb": 10,
         "roe": 0.40, "profit_margin": 0.22, "dividend_yield": 0.03, "debt_equity": 1.8,
         "revenue_growth": 0.03, "fcf_yield": 0.03, "market_cap": 250e9, "beta": 0.6},
        {"ticker": "XOM", "name": "Exxon", "sector": "Energy", "pe": 10, "pb": 1.5,
         "roe": 0.20, "profit_margin": 0.10, "dividend_yield": 0.035, "debt_equity": 0.3,
         "revenue_growth": -0.05, "fcf_yield": 0.08, "market_cap": 400e9, "beta": 0.8},
        {"ticker": "NVDA", "name": "NVIDIA", "sector": "Technology", "pe": 50, "pb": 40,
         "roe": 0.80, "profit_margin": 0.55, "dividend_yield": 0.001, "debt_equity": 0.4,
         "revenue_growth": 1.20, "fcf_yield": 0.02, "market_cap": 2e12, "beta": 1.8},
    ]


# ---------------------------------------------------------------------------
# get_fundamentals (mocked)
# ---------------------------------------------------------------------------

@patch("core.sectorscan.yf")
def test_get_fundamentals_returns_expected_keys(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.info = {
        "shortName": "Apple Inc", "sector": "Technology", "industry": "Consumer Electronics",
        "currentPrice": 195, "marketCap": 3e12, "trailingPE": 28, "forwardPE": 25,
        "priceToBook": 35, "returnOnEquity": 0.6, "beta": 1.2, "dividendYield": 0.005,
        "profitMargins": 0.25, "debtToEquity": 150, "trailingEps": 6.5,
    }
    mock_yf.Ticker.return_value = mock_ticker

    result = get_fundamentals("AAPL")
    assert result["ticker"] == "AAPL"
    assert "pe" in result
    assert "roe" in result
    assert "sector" in result
    assert result["debt_equity"] == 1.5  # normalized from 150


@patch("core.sectorscan.yf")
def test_get_fundamentals_error_on_failure(mock_yf):
    mock_yf.Ticker.side_effect = Exception("Network error")
    result = get_fundamentals("ZZZZ")
    assert "error" in result


@patch("core.sectorscan.yf")
def test_get_fundamentals_cached(mock_yf):
    mock_ticker = MagicMock()
    mock_ticker.info = {"shortName": "Test", "currentPrice": 100, "marketCap": 1e9}
    mock_yf.Ticker.return_value = mock_ticker

    get_fundamentals("TEST")
    # Second call should hit cache
    get_fundamentals("TEST")
    # yf.Ticker should only be called once (second is cached)
    assert mock_yf.Ticker.call_count == 1


# ---------------------------------------------------------------------------
# get_fundamentals_batch
# ---------------------------------------------------------------------------

@patch("core.sectorscan.get_fundamentals")
def test_batch_returns_list(mock_get):
    mock_get.side_effect = lambda t: {"ticker": t, "pe": 15}
    results = get_fundamentals_batch(["AAPL", "MSFT", "GOOGL"])
    assert len(results) == 3


@patch("core.sectorscan.get_fundamentals")
def test_batch_skips_failures(mock_get):
    def _side(t):
        if t == "BAD":
            return {"ticker": "BAD", "error": "fail"}
        return {"ticker": t, "pe": 15}
    mock_get.side_effect = _side
    results = get_fundamentals_batch(["AAPL", "BAD", "MSFT"])
    assert len(results) == 2


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------

def test_screen_no_filters():
    stocks = _make_stocks()
    with patch("core.sectorscan.get_fundamentals_batch", return_value=stocks):
        result = screen_stocks(["AAPL", "JPM"], filters=None)
    assert len(result) == 5  # returns all from batch


def test_screen_pe_max():
    stocks = _make_stocks()
    with patch("core.sectorscan.get_fundamentals_batch", return_value=stocks):
        result = screen_stocks(["AAPL"], filters={"pe_max": 15})
    # Only JPM (12) and XOM (10) pass
    assert all(s["pe"] <= 15 for s in result)
    assert len(result) == 2


def test_screen_sector_filter():
    stocks = _make_stocks()
    with patch("core.sectorscan.get_fundamentals_batch", return_value=stocks):
        result = screen_stocks(["AAPL"], filters={"sector": "Technology"})
    assert all(s["sector"] == "Technology" for s in result)
    assert len(result) == 2  # AAPL and NVDA


def test_screen_impossible_filters():
    stocks = _make_stocks()
    with patch("core.sectorscan.get_fundamentals_batch", return_value=stocks):
        result = screen_stocks(["AAPL"], filters={"pe_max": 1})
    assert len(result) == 0


def test_screen_range_filter():
    stocks = _make_stocks()
    with patch("core.sectorscan.get_fundamentals_batch", return_value=stocks):
        result = screen_stocks(["AAPL"], filters={"pe_min": 10, "pe_max": 25})
    for s in result:
        assert 10 <= s["pe"] <= 25


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def test_rank_ascending():
    stocks = _make_stocks()
    ranked = rank_by_metric(stocks, "pe", ascending=True)
    pes = [s["pe"] for s in ranked if s.get("pe") is not None]
    assert pes == sorted(pes)
    assert ranked[0]["rank"] == 1


def test_rank_descending():
    stocks = _make_stocks()
    ranked = rank_by_metric(stocks, "roe", ascending=False)
    roes = [s["roe"] for s in ranked if s.get("roe") is not None]
    assert roes == sorted(roes, reverse=True)


def test_rank_none_values_to_end():
    stocks = [
        {"ticker": "A", "pe": 10},
        {"ticker": "B", "pe": None},
        {"ticker": "C", "pe": 5},
    ]
    ranked = rank_by_metric(stocks, "pe", ascending=True)
    assert ranked[-1]["ticker"] == "B"


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

def test_composite_score_returns_float():
    stocks = _make_stocks()
    score = composite_score(stocks[0], stocks)
    assert isinstance(score, float)
    assert 0 <= score <= 1


def test_rank_with_composite_adds_rank():
    stocks = _make_stocks()
    ranked = rank_with_composite(stocks)
    assert ranked[0]["composite_rank"] == 1
    assert "composite_score" in ranked[0]
    # Scores should be descending
    scores = [s["composite_score"] for s in ranked]
    assert scores == sorted(scores, reverse=True)


def test_rank_with_composite_empty():
    assert rank_with_composite([]) == []


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def test_preset_screens_all_present():
    presets = preset_screens()
    assert "value" in presets
    assert "growth" in presets
    assert "dividend" in presets
    assert "quality" in presets
    assert "low_vol" in presets


def test_preset_has_valid_structure():
    presets = preset_screens()
    for name, p in presets.items():
        assert "name" in p
        assert "filters" in p
        assert "sort_by" in p
        assert isinstance(p["filters"], dict)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_empty_universe():
    with patch("core.sectorscan.get_fundamentals_batch", return_value=[]):
        result = screen_stocks([], filters=None)
    assert result == []


def test_single_stock():
    stocks = [_make_stocks()[0]]
    with patch("core.sectorscan.get_fundamentals_batch", return_value=stocks):
        result = screen_stocks(["AAPL"])
    assert len(result) == 1


def test_passes_filters_with_none_value():
    """Stock with None for a filtered metric should pass (skip that filter)."""
    stock = {"ticker": "TEST", "pe": None, "roe": 0.20}
    assert _passes_filters(stock, {"pe_max": 15}) is True  # None -> skip
    assert _passes_filters(stock, {"roe_min": 0.15}) is True
