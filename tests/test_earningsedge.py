"""Tests for core/earningsedge.py — Earnings Calendar & Surprise Tracker."""
import os
import numpy as np
import pytest
from unittest.mock import patch

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


from core.earningsedge import (
    get_earnings_calendar, get_earnings_history,
    calculate_surprise_stats, estimate_expected_move,
    portfolio_earnings_summary,
)


# ---------------------------------------------------------------------------
# Synthetic earnings data
# ---------------------------------------------------------------------------

def _make_earnings_history(beats=8, misses=4):
    """Create synthetic earnings history."""
    results = []
    for i in range(beats):
        results.append({
            "ticker": "AAPL", "date": f"2024-{(i % 12) + 1:02d}-15",
            "quarter": f"Q{(i % 4) + 1} 2024",
            "eps_estimate": 1.50, "eps_actual": 1.65,
            "surprise": 0.15, "surprise_pct": 10.0, "beat": True,
        })
    for i in range(misses):
        results.append({
            "ticker": "AAPL", "date": f"2023-{(i % 12) + 1:02d}-15",
            "quarter": f"Q{(i % 4) + 1} 2023",
            "eps_estimate": 1.50, "eps_actual": 1.35,
            "surprise": -0.15, "surprise_pct": -10.0, "beat": False,
        })
    return results


def _make_price_moves():
    """Create synthetic post-earnings price moves."""
    return [
        {"date": "2024-10-15", "quarter": "Q4 2024", "beat": True, "surprise_pct": 10.0,
         "price_move_1d": 3.5, "price_move_5d": 5.2, "price_on_date": 195.0},
        {"date": "2024-07-15", "quarter": "Q3 2024", "beat": True, "surprise_pct": 8.0,
         "price_move_1d": 2.1, "price_move_5d": 3.8, "price_on_date": 185.0},
        {"date": "2024-04-15", "quarter": "Q2 2024", "beat": False, "surprise_pct": -5.0,
         "price_move_1d": -4.2, "price_move_5d": -2.5, "price_on_date": 175.0},
        {"date": "2024-01-15", "quarter": "Q1 2024", "beat": True, "surprise_pct": 12.0,
         "price_move_1d": 1.8, "price_move_5d": 4.1, "price_on_date": 165.0},
    ]


# ---------------------------------------------------------------------------
# Earnings Calendar
# ---------------------------------------------------------------------------

def test_earnings_calendar_returns_list():
    """get_earnings_calendar should return a list."""
    with patch("core.earningsedge.get_earnings_calendar_finnhub", return_value=[]):
        with patch("core.earningsedge.get_earnings_calendar_yfinance", return_value=[]):
            result = get_earnings_calendar("AAPL")
    assert isinstance(result, list)


def test_earnings_calendar_sorted_by_date():
    mock_data = [
        {"ticker": "AAPL", "date": "2025-02-15", "quarter": "Q1", "eps_estimate": 2.0,
         "eps_actual": None, "revenue_estimate": None, "revenue_actual": None, "hour": "amc"},
        {"ticker": "AAPL", "date": "2025-01-10", "quarter": "Q4", "eps_estimate": 1.8,
         "eps_actual": None, "revenue_estimate": None, "revenue_actual": None, "hour": "bmo"},
    ]
    with patch("core.earningsedge.get_earnings_calendar_finnhub", return_value=mock_data):
        result = get_earnings_calendar("AAPL")
    dates = [e["date"] for e in result]
    assert dates == sorted(dates)


def test_earnings_calendar_has_expected_keys():
    mock_data = [
        {"ticker": "AAPL", "date": "2025-01-15", "quarter": "Q1", "eps_estimate": 2.0,
         "eps_actual": None, "revenue_estimate": None, "revenue_actual": None, "hour": "amc"},
    ]
    with patch("core.earningsedge.get_earnings_calendar_finnhub", return_value=mock_data):
        result = get_earnings_calendar("AAPL")
    if result:
        e = result[0]
        assert "ticker" in e
        assert "date" in e
        assert "eps_estimate" in e


# ---------------------------------------------------------------------------
# Surprise Stats
# ---------------------------------------------------------------------------

def test_stats_all_beats():
    hist = _make_earnings_history(beats=8, misses=0)
    stats = calculate_surprise_stats(hist)
    assert stats["beat_rate"] == 100.0
    assert stats["beats"] == 8
    assert stats["misses"] == 0


def test_stats_all_misses():
    hist = _make_earnings_history(beats=0, misses=8)
    stats = calculate_surprise_stats(hist)
    assert stats["beat_rate"] == 0.0
    assert stats["misses"] == 8


def test_stats_mixed():
    hist = _make_earnings_history(beats=6, misses=4)
    stats = calculate_surprise_stats(hist)
    assert stats["total_quarters"] == 10
    assert stats["beats"] == 6
    assert stats["misses"] == 4
    assert abs(stats["beat_rate"] - 60.0) < 0.1


def test_stats_streak_beats():
    """First entries are beats -> positive streak."""
    hist = _make_earnings_history(beats=5, misses=3)
    stats = calculate_surprise_stats(hist)
    assert stats["streak"] == 5  # first 5 are beats


def test_stats_streak_misses():
    """First entries are misses -> negative streak."""
    hist = _make_earnings_history(beats=0, misses=4)
    stats = calculate_surprise_stats(hist)
    assert stats["streak"] == -4


def test_stats_consistency_score_bounds():
    hist = _make_earnings_history(beats=8, misses=4)
    stats = calculate_surprise_stats(hist)
    assert 0 <= stats["consistency_score"] <= 1


def test_stats_empty():
    stats = calculate_surprise_stats([])
    assert stats["total_quarters"] == 0
    assert stats["beat_rate"] == 0


def test_stats_avg_beat_magnitude():
    hist = _make_earnings_history(beats=4, misses=0)
    stats = calculate_surprise_stats(hist)
    assert stats["avg_beat_magnitude"] == 10.0  # all have 10% surprise


def test_stats_avg_miss_magnitude():
    hist = _make_earnings_history(beats=0, misses=4)
    stats = calculate_surprise_stats(hist)
    assert stats["avg_miss_magnitude"] == -10.0


# ---------------------------------------------------------------------------
# Expected Move
# ---------------------------------------------------------------------------

def test_expected_move_avg_abs_positive():
    moves = _make_price_moves()
    result = estimate_expected_move(moves)
    assert result["avg_abs_move_1d"] > 0


def test_expected_move_max_up_positive():
    moves = _make_price_moves()
    result = estimate_expected_move(moves)
    assert result["max_move_up_1d"] >= 0


def test_expected_move_max_down_negative():
    moves = _make_price_moves()
    result = estimate_expected_move(moves)
    assert result["max_move_down_1d"] <= 0


def test_expected_move_beat_vs_miss():
    moves = _make_price_moves()
    result = estimate_expected_move(moves)
    # On average, beats should have positive moves, misses negative
    assert result["avg_move_on_beat_1d"] > 0
    assert result["avg_move_on_miss_1d"] < 0


def test_expected_move_empty():
    result = estimate_expected_move([])
    assert result["avg_abs_move_1d"] == 0


# ---------------------------------------------------------------------------
# Portfolio Summary
# ---------------------------------------------------------------------------

def test_portfolio_summary_empty_holdings():
    result = portfolio_earnings_summary([])
    assert result["upcoming"] == []
    assert result["total_portfolio_weight_reporting"] == 0


def test_portfolio_summary_structure():
    """Test that the return structure has all keys."""
    with patch("core.earningsedge.get_earnings_calendar", return_value=[]):
        with patch("core.earningsedge.get_earnings_history", return_value=[]):
            result = portfolio_earnings_summary([{"ticker": "AAPL", "weight": 0.5}])
    assert "upcoming" in result
    assert "no_upcoming" in result
    assert "total_portfolio_weight_reporting" in result
    assert "earnings_this_week" in result
    assert "earnings_next_week" in result


def test_portfolio_summary_no_upcoming():
    """When no upcoming earnings, ticker goes to no_upcoming list."""
    with patch("core.earningsedge.get_earnings_calendar", return_value=[]):
        with patch("core.earningsedge.get_earnings_history", return_value=[]):
            result = portfolio_earnings_summary([{"ticker": "AAPL", "weight": 0.5}])
    assert "AAPL" in result["no_upcoming"]


def test_portfolio_summary_with_upcoming():
    """When there are upcoming earnings, compute impact."""
    from datetime import datetime, timedelta
    future_date = (datetime.today() + timedelta(days=7)).strftime("%Y-%m-%d")
    mock_cal = [{"ticker": "AAPL", "date": future_date, "quarter": "Q1 2025",
                 "eps_estimate": 2.0, "eps_actual": None, "revenue_estimate": None,
                 "revenue_actual": None, "hour": "amc"}]
    mock_hist = _make_earnings_history(4, 0)
    mock_moves = _make_price_moves()

    with patch("core.earningsedge.get_earnings_calendar", return_value=mock_cal):
        with patch("core.earningsedge.get_earnings_history", return_value=mock_hist):
            with patch("core.earningsedge.get_post_earnings_moves", return_value=mock_moves):
                result = portfolio_earnings_summary([{"ticker": "AAPL", "weight": 0.3}])

    assert len(result["upcoming"]) > 0
    u = result["upcoming"][0]
    assert u["ticker"] == "AAPL"
    assert u["portfolio_weight"] == 0.3
    # expected_portfolio_impact = weight * avg_abs_move
    assert u["expected_portfolio_impact"] > 0


def test_portfolio_summary_total_weight():
    from datetime import datetime, timedelta
    future_date = (datetime.today() + timedelta(days=5)).strftime("%Y-%m-%d")
    mock_cal = [{"ticker": "AAPL", "date": future_date, "quarter": "Q1",
                 "eps_estimate": 2.0, "eps_actual": None, "revenue_estimate": None,
                 "revenue_actual": None, "hour": "amc"}]

    with patch("core.earningsedge.get_earnings_calendar", return_value=mock_cal):
        with patch("core.earningsedge.get_earnings_history", return_value=_make_earnings_history(4, 0)):
            with patch("core.earningsedge.get_post_earnings_moves", return_value=_make_price_moves()):
                result = portfolio_earnings_summary([
                    {"ticker": "AAPL", "weight": 0.3},
                ])

    assert result["total_portfolio_weight_reporting"] == 0.3
