"""
Brinson-Fachler Performance Attribution Engine.
Decomposes portfolio active return (vs benchmark) into:
  - Allocation Effect: did you overweight the right sectors?
  - Selection Effect: did you pick the right stocks within sectors?
  - Interaction Effect: cross-term between allocation and selection
"""
import numpy as np
import pandas as pd
from core.sanitize import safe_divide
from core.nervemap import TICKER_SECTOR_MAP

# ---------------------------------------------------------------------------
# Sector Classification
# ---------------------------------------------------------------------------

SECTOR_ALIASES = {
    "Technology": "Technology",
    "Banking": "Financials",
    "Pharma": "Healthcare",
    "Energy": "Energy",
    "Metals": "Materials",
    "Real_Estate": "Real Estate",
    "FMCG": "Consumer Staples",
    "Auto": "Consumer Discretionary",
    "Telecom": "Communication Services",
    "Infrastructure": "Industrials",
    "Bonds": "Fixed Income",
    "Crypto": "Alternative",
    "Diversified": "Diversified",
    "Other": "Other",
}

# SPY approximate sector weights (GICS sectors)
BENCHMARK_SECTOR_WEIGHTS = {
    "Technology": 0.31,
    "Healthcare": 0.12,
    "Financials": 0.13,
    "Consumer Discretionary": 0.10,
    "Communication Services": 0.09,
    "Industrials": 0.09,
    "Consumer Staples": 0.06,
    "Energy": 0.04,
    "Real Estate": 0.02,
    "Materials": 0.02,
    "Utilities": 0.02,
}

SECTOR_ETF_PROXIES = {
    "Technology": "XLK",
    "Healthcare": "XLV",
    "Financials": "XLF",
    "Consumer Discretionary": "XLY",
    "Communication Services": "XLC",
    "Industrials": "XLI",
    "Consumer Staples": "XLP",
    "Energy": "XLE",
    "Real Estate": "XLRE",
    "Materials": "XLB",
    "Utilities": "XLU",
}


def classify_holdings(holdings: list) -> dict:
    """Classify portfolio holdings into GICS-compatible sectors.
    holdings: [{"ticker": "AAPL", "weight": 0.3}, ...]"""
    sector_weights = {}
    holdings_by_sector = {}
    unclassified = []

    for h in holdings:
        ticker = h.get("ticker", "").upper()
        weight = h.get("weight", 0.0)
        nervemap_sector = TICKER_SECTOR_MAP.get(ticker)

        if nervemap_sector:
            gics_sector = SECTOR_ALIASES.get(nervemap_sector, "Other")
        else:
            gics_sector = "Other"
            unclassified.append(ticker)

        sector_weights[gics_sector] = sector_weights.get(gics_sector, 0.0) + weight
        if gics_sector not in holdings_by_sector:
            holdings_by_sector[gics_sector] = []
        holdings_by_sector[gics_sector].append({"ticker": ticker, "weight": weight})

    return {
        "sector_weights": sector_weights,
        "holdings_by_sector": holdings_by_sector,
        "unclassified": unclassified,
    }


def get_benchmark_weights() -> dict:
    """Return benchmark (SPY) sector weights."""
    return dict(BENCHMARK_SECTOR_WEIGHTS)


# ---------------------------------------------------------------------------
# Return Computation
# ---------------------------------------------------------------------------

def compute_sector_returns(holdings_by_sector: dict, returns_data: pd.DataFrame,
                           period: str = "1y") -> dict:
    """Compute weighted return for each sector in the portfolio.
    returns_data: DataFrame with one column per ticker, values are total returns for the period."""
    sector_returns = {}

    for sector, holdings in holdings_by_sector.items():
        total_weight = sum(h["weight"] for h in holdings)
        if total_weight <= 0:
            sector_returns[sector] = 0.0
            continue

        weighted_return = 0.0
        for h in holdings:
            ticker = h["ticker"].upper()
            if ticker in returns_data.columns:
                ret = returns_data[ticker].iloc[-1] if len(returns_data) > 0 else 0.0
                weighted_return += (h["weight"] / total_weight) * ret

        sector_returns[sector] = weighted_return

    return sector_returns


def get_benchmark_sector_returns(period: str = "1y") -> dict:
    """Get benchmark sector returns using sector ETF proxies.
    Uses core/data.py for price data. Falls back to SPY for missing sectors."""
    try:
        from core.data import get_ohlcv
    except ImportError:
        return {s: 0.0 for s in BENCHMARK_SECTOR_WEIGHTS}

    # Get SPY return as fallback
    spy_ret = 0.0
    try:
        spy_df = get_ohlcv("SPY", period)
        if not spy_df.empty and "close" in spy_df.columns:
            spy_ret = (spy_df["close"].iloc[-1] / spy_df["close"].iloc[0]) - 1
    except Exception:
        pass

    sector_returns = {}
    for sector, etf in SECTOR_ETF_PROXIES.items():
        try:
            df = get_ohlcv(etf, period)
            if not df.empty and "close" in df.columns and len(df) > 1:
                sector_returns[sector] = (df["close"].iloc[-1] / df["close"].iloc[0]) - 1
            else:
                sector_returns[sector] = spy_ret
        except Exception:
            sector_returns[sector] = spy_ret

    return sector_returns


# ---------------------------------------------------------------------------
# Brinson Attribution
# ---------------------------------------------------------------------------

def brinson_attribution(port_sector_weights: dict, port_sector_returns: dict,
                        bench_sector_weights: dict, bench_sector_returns: dict) -> dict:
    """Brinson-Fachler attribution analysis."""
    # Total benchmark return
    r_b = sum(bench_sector_weights.get(s, 0) * bench_sector_returns.get(s, 0)
              for s in set(list(bench_sector_weights.keys()) + list(bench_sector_returns.keys())))

    # Total portfolio return
    r_p = sum(port_sector_weights.get(s, 0) * port_sector_returns.get(s, 0)
              for s in set(list(port_sector_weights.keys()) + list(port_sector_returns.keys())))

    all_sectors = sorted(set(
        list(port_sector_weights.keys()) +
        list(bench_sector_weights.keys())
    ))

    total_alloc = 0.0
    total_select = 0.0
    total_interact = 0.0
    sector_detail = []

    for sector in all_sectors:
        wp = port_sector_weights.get(sector, 0.0)
        wb = bench_sector_weights.get(sector, 0.0)
        rp = port_sector_returns.get(sector, 0.0)
        rb_i = bench_sector_returns.get(sector, 0.0)

        alloc = (wp - wb) * (rb_i - r_b)
        select = wb * (rp - rb_i)
        interact = (wp - wb) * (rp - rb_i)
        total = alloc + select + interact

        total_alloc += alloc
        total_select += select
        total_interact += interact

        sector_detail.append({
            "sector": sector,
            "port_weight": round(wp, 4),
            "bench_weight": round(wb, 4),
            "port_return": round(rp, 4),
            "bench_return": round(rb_i, 4),
            "allocation": round(alloc, 6),
            "selection": round(select, 6),
            "interaction": round(interact, 6),
            "total": round(total, 6),
        })

    sector_detail.sort(key=lambda x: abs(x["total"]), reverse=True)

    return {
        "total_portfolio_return": round(r_p, 6),
        "total_benchmark_return": round(r_b, 6),
        "total_active_return": round(r_p - r_b, 6),
        "total_allocation_effect": round(total_alloc, 6),
        "total_selection_effect": round(total_select, 6),
        "total_interaction_effect": round(total_interact, 6),
        "attribution_check": round(total_alloc + total_select + total_interact, 6),
        "sector_detail": sector_detail,
    }


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------

def full_attribution(holdings: list, period: str = "1y") -> dict:
    """Run the complete attribution pipeline."""
    if not holdings:
        return {"available": False, "error": "No holdings provided"}

    try:
        from core.data import get_ohlcv

        # 1. Classify holdings
        classification = classify_holdings(holdings)
        port_sector_weights = classification["sector_weights"]
        holdings_by_sector = classification["holdings_by_sector"]

        # 2. Compute portfolio sector returns from actual prices
        # Get total returns per ticker
        ticker_returns = {}
        for h in holdings:
            ticker = h["ticker"].upper()
            df = get_ohlcv(ticker, period)
            if not df.empty and "close" in df.columns and len(df) > 1:
                ticker_returns[ticker] = (df["close"].iloc[-1] / df["close"].iloc[0]) - 1
            else:
                ticker_returns[ticker] = 0.0

        returns_df = pd.DataFrame({"dummy": [0]})
        for t, r in ticker_returns.items():
            returns_df[t] = [r]

        port_sector_returns = compute_sector_returns(holdings_by_sector, returns_df, period)

        # 3. Get benchmark sector returns
        bench_sector_weights = get_benchmark_weights()
        bench_sector_returns = get_benchmark_sector_returns(period)

        # 4. Run Brinson attribution
        result = brinson_attribution(
            port_sector_weights, port_sector_returns,
            bench_sector_weights, bench_sector_returns,
        )

        result["classification"] = classification
        result["interpretations"] = interpret_attribution(result)
        result["available"] = True

        return result

    except Exception as e:
        return {"available": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------

def interpret_attribution(result: dict) -> list:
    """Generate human-readable attribution insights."""
    insights = []

    alloc = abs(result.get("total_allocation_effect", 0))
    select = abs(result.get("total_selection_effect", 0))
    active = result.get("total_active_return", 0)

    if active > 0.001:
        insights.append(f"Portfolio outperformed the benchmark by {active:.1%}.")
    elif active < -0.001:
        insights.append(f"Portfolio underperformed the benchmark by {abs(active):.1%}.")
    else:
        insights.append("Portfolio performed roughly in line with the benchmark.")

    if alloc > select and alloc > 0.001:
        insights.append("Returns were primarily driven by sector allocation decisions, not stock picking.")
    elif select > alloc and select > 0.001:
        insights.append("Stock selection within sectors contributed more to returns than sector allocation.")

    # Highlight biggest contributors
    detail = result.get("sector_detail", [])
    if detail:
        best = max(detail, key=lambda x: x["total"])
        worst = min(detail, key=lambda x: x["total"])
        if best["total"] > 0.005:
            insights.append(f"Biggest positive contributor: {best['sector']} ({best['total']:.2%}).")
        if worst["total"] < -0.005:
            insights.append(f"Biggest negative contributor: {worst['sector']} ({worst['total']:.2%}).")

    # Concentration check
    port_weights = {d["sector"]: d["port_weight"] for d in detail}
    if port_weights:
        max_w = max(port_weights.values())
        if max_w > 0.5:
            sector = max(port_weights, key=port_weights.get)
            insights.append(f"Portfolio is highly concentrated in {sector} ({max_w:.0%}), increasing sector-specific risk.")

    return insights
