"""Tests for core/alphatrace.py — Brinson Performance Attribution."""
import numpy as np
import pandas as pd
import pytest

from core.alphatrace import (
    classify_holdings, get_benchmark_weights, brinson_attribution,
    compute_sector_returns, interpret_attribution,
    SECTOR_ALIASES, BENCHMARK_SECTOR_WEIGHTS,
)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def test_classify_known_tickers():
    holdings = [
        {"ticker": "AAPL", "weight": 0.5},
        {"ticker": "JPM", "weight": 0.3},
        {"ticker": "XOM", "weight": 0.2},
    ]
    result = classify_holdings(holdings)
    assert "Technology" in result["sector_weights"]
    assert "Financials" in result["sector_weights"]
    assert "Energy" in result["sector_weights"]


def test_classify_unknown_ticker():
    holdings = [{"ticker": "ZZZZ", "weight": 1.0}]
    result = classify_holdings(holdings)
    assert "Other" in result["sector_weights"]
    assert "ZZZZ" in result["unclassified"]


def test_classify_weights_sum():
    holdings = [
        {"ticker": "AAPL", "weight": 0.4},
        {"ticker": "MSFT", "weight": 0.3},
        {"ticker": "JPM", "weight": 0.3},
    ]
    result = classify_holdings(holdings)
    total = sum(result["sector_weights"].values())
    assert abs(total - 1.0) < 0.01


def test_classify_grouping():
    """Multiple tech stocks should be grouped into Technology."""
    holdings = [
        {"ticker": "AAPL", "weight": 0.3},
        {"ticker": "MSFT", "weight": 0.3},
        {"ticker": "GOOGL", "weight": 0.4},
    ]
    result = classify_holdings(holdings)
    assert result["sector_weights"]["Technology"] == 1.0
    assert len(result["holdings_by_sector"]["Technology"]) == 3


def test_classify_empty():
    result = classify_holdings([])
    assert result["sector_weights"] == {}
    assert result["unclassified"] == []


# ---------------------------------------------------------------------------
# Sector aliases
# ---------------------------------------------------------------------------

def test_sector_aliases_cover_nervemap():
    """All NerveMap sectors should have a GICS alias."""
    from core.nervemap import TICKER_SECTOR_MAP
    nervemap_sectors = set(TICKER_SECTOR_MAP.values())
    for s in nervemap_sectors:
        if s in ("Diversified", "Bonds", "Crypto"):
            continue  # these are non-GICS
        assert s in SECTOR_ALIASES, f"Missing alias for {s}"


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------

def test_benchmark_weights_sum():
    bw = get_benchmark_weights()
    total = sum(bw.values())
    assert abs(total - 1.0) < 0.01


def test_benchmark_weights_is_copy():
    """get_benchmark_weights should return a copy, not a reference."""
    bw = get_benchmark_weights()
    bw["Technology"] = 99
    assert BENCHMARK_SECTOR_WEIGHTS["Technology"] != 99


# ---------------------------------------------------------------------------
# Brinson attribution math
# ---------------------------------------------------------------------------

def test_brinson_identity():
    """Portfolio = benchmark -> all effects = 0."""
    weights = {"Tech": 0.6, "Fin": 0.4}
    returns = {"Tech": 0.10, "Fin": 0.05}
    result = brinson_attribution(weights, returns, weights, returns)
    assert abs(result["total_active_return"]) < 1e-9
    assert abs(result["total_allocation_effect"]) < 1e-9
    assert abs(result["total_selection_effect"]) < 1e-9
    assert abs(result["total_interaction_effect"]) < 1e-9


def test_brinson_pure_allocation():
    """Same sector returns, different weights -> selection ~ 0."""
    port_w = {"Tech": 0.8, "Fin": 0.2}
    bench_w = {"Tech": 0.5, "Fin": 0.5}
    returns = {"Tech": 0.15, "Fin": 0.05}

    result = brinson_attribution(port_w, returns, bench_w, returns)
    # Selection should be zero (same returns in both)
    assert abs(result["total_selection_effect"]) < 1e-9
    # But allocation should be nonzero
    assert abs(result["total_allocation_effect"]) > 0.001


def test_brinson_pure_selection():
    """Same weights, different returns -> allocation ~ 0."""
    weights = {"Tech": 0.5, "Fin": 0.5}
    port_ret = {"Tech": 0.20, "Fin": 0.05}
    bench_ret = {"Tech": 0.10, "Fin": 0.08}

    result = brinson_attribution(weights, port_ret, weights, bench_ret)
    # With identical weights, allocation effect should be 0
    assert abs(result["total_allocation_effect"]) < 1e-9
    assert abs(result["total_selection_effect"]) > 0.001


def test_brinson_additivity():
    """allocation + selection + interaction should equal active return."""
    port_w = {"Tech": 0.7, "Fin": 0.3}
    bench_w = {"Tech": 0.4, "Fin": 0.6}
    port_ret = {"Tech": 0.20, "Fin": 0.05}
    bench_ret = {"Tech": 0.12, "Fin": 0.08}

    result = brinson_attribution(port_w, port_ret, bench_w, bench_ret)
    check = (result["total_allocation_effect"] +
             result["total_selection_effect"] +
             result["total_interaction_effect"])
    assert abs(check - result["total_active_return"]) < 0.001


def test_brinson_known_textbook():
    """Simple 2-sector textbook example with known results."""
    # Portfolio: 60% stocks (return 10%), 40% bonds (return 5%)
    # Benchmark: 50% stocks (return 8%), 50% bonds (return 4%)
    port_w = {"Stocks": 0.6, "Bonds": 0.4}
    bench_w = {"Stocks": 0.5, "Bonds": 0.5}
    port_ret = {"Stocks": 0.10, "Bonds": 0.05}
    bench_ret = {"Stocks": 0.08, "Bonds": 0.04}

    result = brinson_attribution(port_w, port_ret, bench_w, bench_ret)

    # R_b = 0.5*0.08 + 0.5*0.04 = 0.06
    assert abs(result["total_benchmark_return"] - 0.06) < 1e-6

    # R_p = 0.6*0.10 + 0.4*0.05 = 0.08
    assert abs(result["total_portfolio_return"] - 0.08) < 1e-6

    # Active return = 0.02
    assert abs(result["total_active_return"] - 0.02) < 1e-6

    # Verify additivity
    assert abs(result["attribution_check"] - result["total_active_return"]) < 1e-6


def test_brinson_single_sector():
    port_w = {"Tech": 1.0}
    bench_w = {"Tech": 0.5, "Fin": 0.5}
    port_ret = {"Tech": 0.15}
    bench_ret = {"Tech": 0.10, "Fin": 0.05}

    result = brinson_attribution(port_w, port_ret, bench_w, bench_ret)
    assert abs(result["attribution_check"] - result["total_active_return"]) < 0.001


def test_brinson_sector_only_in_portfolio():
    """Sector in portfolio but not in benchmark."""
    port_w = {"Tech": 0.5, "Crypto": 0.5}
    bench_w = {"Tech": 1.0}
    port_ret = {"Tech": 0.10, "Crypto": 0.20}
    bench_ret = {"Tech": 0.10}

    result = brinson_attribution(port_w, port_ret, bench_w, bench_ret)
    assert abs(result["attribution_check"] - result["total_active_return"]) < 0.001


def test_brinson_sorted_by_abs_total():
    port_w = {"A": 0.5, "B": 0.3, "C": 0.2}
    bench_w = {"A": 0.33, "B": 0.33, "C": 0.34}
    port_ret = {"A": 0.20, "B": 0.05, "C": 0.01}
    bench_ret = {"A": 0.10, "B": 0.10, "C": 0.10}

    result = brinson_attribution(port_w, port_ret, bench_w, bench_ret)
    totals = [abs(d["total"]) for d in result["sector_detail"]]
    assert totals == sorted(totals, reverse=True)


# ---------------------------------------------------------------------------
# Sector returns
# ---------------------------------------------------------------------------

def test_compute_sector_returns_basic():
    holdings_by_sector = {
        "Technology": [{"ticker": "AAPL", "weight": 0.6}, {"ticker": "MSFT", "weight": 0.4}],
    }
    # Returns data: AAPL returned 10%, MSFT returned 20%
    returns_data = pd.DataFrame({"AAPL": [0.10], "MSFT": [0.20]})
    result = compute_sector_returns(holdings_by_sector, returns_data)
    # Weighted: (0.6/1.0)*0.10 + (0.4/1.0)*0.20 = 0.06 + 0.08 = 0.14
    assert abs(result["Technology"] - 0.14) < 0.001


def test_compute_sector_returns_missing_ticker():
    holdings_by_sector = {
        "Technology": [{"ticker": "ZZZZ", "weight": 1.0}],
    }
    returns_data = pd.DataFrame({"AAPL": [0.10]})
    result = compute_sector_returns(holdings_by_sector, returns_data)
    assert result["Technology"] == 0.0


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------

def test_interpret_outperformance():
    result = {
        "total_active_return": 0.05,
        "total_allocation_effect": 0.03,
        "total_selection_effect": 0.01,
        "total_interaction_effect": 0.01,
        "sector_detail": [],
    }
    msgs = interpret_attribution(result)
    assert any("outperformed" in m for m in msgs)


def test_interpret_allocation_dominated():
    result = {
        "total_active_return": 0.05,
        "total_allocation_effect": 0.04,
        "total_selection_effect": 0.005,
        "total_interaction_effect": 0.005,
        "sector_detail": [],
    }
    msgs = interpret_attribution(result)
    assert any("allocation" in m.lower() for m in msgs)


def test_interpret_selection_dominated():
    result = {
        "total_active_return": 0.05,
        "total_allocation_effect": 0.005,
        "total_selection_effect": 0.04,
        "total_interaction_effect": 0.005,
        "sector_detail": [],
    }
    msgs = interpret_attribution(result)
    assert any("selection" in m.lower() for m in msgs)


def test_interpret_concentration():
    result = {
        "total_active_return": 0.01,
        "total_allocation_effect": 0.005,
        "total_selection_effect": 0.005,
        "total_interaction_effect": 0.0,
        "sector_detail": [
            {"sector": "Technology", "port_weight": 0.8, "bench_weight": 0.3,
             "port_return": 0.1, "bench_return": 0.1,
             "allocation": 0.01, "selection": 0.0, "interaction": 0.0, "total": 0.01},
        ],
    }
    msgs = interpret_attribution(result)
    assert any("concentrated" in m for m in msgs)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_single_holding():
    holdings = [{"ticker": "AAPL", "weight": 1.0}]
    result = classify_holdings(holdings)
    assert result["sector_weights"]["Technology"] == 1.0


def test_all_other_sector():
    holdings = [{"ticker": "ZZZZ", "weight": 0.5}, {"ticker": "YYYY", "weight": 0.5}]
    result = classify_holdings(holdings)
    assert "Other" in result["sector_weights"]
    assert result["sector_weights"]["Other"] == 1.0


def test_brinson_all_zero_returns():
    port_w = {"Tech": 0.5, "Fin": 0.5}
    bench_w = {"Tech": 0.5, "Fin": 0.5}
    zero_ret = {"Tech": 0.0, "Fin": 0.0}
    result = brinson_attribution(port_w, zero_ret, bench_w, zero_ret)
    assert abs(result["total_active_return"]) < 1e-9
