"""
Multi-factor stock screener.
Filters and ranks stocks by fundamental metrics.
Supports composite scoring with customizable weights.
"""
import numpy as np
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
from core.sanitize import safe_divide
from core.cache import get_cached_metric, store_metric

# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK-B", "JPM", "JNJ",
    "V", "UNH", "HD", "PG", "MA", "DIS", "BAC", "XOM", "ADBE", "CRM",
    "CSCO", "PFE", "NFLX", "KO", "PEP", "TMO", "ABT", "COST", "MRK", "CVX",
    "WMT", "ABBV", "LLY", "AVGO", "ACN", "MCD", "ORCL", "AMD", "INTC", "T",
    "VZ", "NKE", "LOW", "UNP", "CAT", "GS", "MS", "C", "WFC", "DE",
]

# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------

def get_fundamentals(ticker: str) -> dict:
    """Fetch fundamental data for a single ticker. Cached 24h."""
    cache_key = f"fundamentals:{ticker.upper()}"
    cached = get_cached_metric(cache_key)
    if cached and "ticker" in cached:
        return cached

    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
    except Exception as e:
        return {"ticker": ticker.upper(), "error": str(e)}

    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        return {"ticker": ticker.upper(), "error": "No data available"}

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    market_cap = info.get("marketCap")
    fcf = info.get("freeCashflow")

    result = {
        "ticker": ticker.upper(),
        "name": info.get("shortName") or info.get("longName", ""),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "market_cap": market_cap,
        "price": price,
        "pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "pb": info.get("priceToBook"),
        "ps": info.get("priceToSalesTrailing12Months"),
        "peg": info.get("pegRatio"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "dividend_yield": info.get("dividendYield"),
        "eps": info.get("trailingEps"),
        "eps_growth": info.get("earningsGrowth"),
        "revenue_growth": info.get("revenueGrowth"),
        "roe": info.get("returnOnEquity"),
        "roa": info.get("returnOnAssets"),
        "debt_equity": info.get("debtToEquity"),
        "current_ratio": info.get("currentRatio"),
        "profit_margin": info.get("profitMargins"),
        "operating_margin": info.get("operatingMargins"),
        "beta": info.get("beta"),
        "fifty_day_avg": info.get("fiftyDayAverage"),
        "two_hundred_day_avg": info.get("twoHundredDayAverage"),
        "week52_high": info.get("fiftyTwoWeekHigh"),
        "week52_low": info.get("fiftyTwoWeekLow"),
        "avg_volume": info.get("averageVolume"),
        "free_cash_flow": fcf,
        "fcf_yield": safe_divide(fcf, market_cap) if fcf and market_cap else None,
    }

    # Normalize debt_equity from percentage (yfinance returns 150 for 1.5x)
    if result["debt_equity"] is not None and result["debt_equity"] > 10:
        result["debt_equity"] = result["debt_equity"] / 100

    store_metric(cache_key, result, ttl_hours=24)
    return result


def get_fundamentals_batch(tickers: list, max_concurrent: int = 5) -> list:
    """Fetch fundamentals for multiple tickers in parallel."""
    if not tickers:
        return []

    results = []
    done = [0]

    def _fetch(t):
        r = get_fundamentals(t)
        done[0] += 1
        if done[0] % 10 == 0 or done[0] == len(tickers):
            print(f"[SCAN] Fetched {done[0]}/{len(tickers)} tickers...")
        return r

    with ThreadPoolExecutor(max_workers=max_concurrent) as pool:
        futures = [pool.submit(_fetch, t) for t in tickers]
        for f in futures:
            try:
                r = f.result(timeout=30)
                if "error" not in r:
                    results.append(r)
            except Exception:
                pass

    return results


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------

def screen_stocks(universe: list = None, filters: dict = None) -> list:
    """Screen stocks by fundamental criteria."""
    if universe is None:
        universe = DEFAULT_UNIVERSE
    if not universe:
        return []

    stocks = get_fundamentals_batch(universe)
    if not filters:
        return stocks

    passing = []
    for s in stocks:
        if not _passes_filters(s, filters):
            continue
        passing.append(s)

    return passing


def _passes_filters(stock: dict, filters: dict) -> bool:
    """Check if a stock passes all filter criteria."""
    for key, threshold in filters.items():
        if key == "sector":
            if stock.get("sector", "").lower() != threshold.lower():
                return False
            continue

        # Parse metric name and direction from key
        if key.endswith("_min"):
            metric = key[:-4]
            val = stock.get(metric)
            if val is None:
                continue  # skip filter if value missing
            if val < threshold:
                return False
        elif key.endswith("_max"):
            metric = key[:-4]
            val = stock.get(metric)
            if val is None:
                continue
            if val > threshold:
                return False

    return True


# ---------------------------------------------------------------------------
# Ranking & Scoring
# ---------------------------------------------------------------------------

def rank_by_metric(stocks: list, metric: str, ascending: bool = True) -> list:
    """Sort stocks by a single metric. None values go to end."""
    has_val = [s for s in stocks if s.get(metric) is not None]
    no_val = [s for s in stocks if s.get(metric) is None]

    has_val.sort(key=lambda s: s[metric], reverse=not ascending)

    ranked = has_val + no_val
    for i, s in enumerate(ranked):
        s["rank"] = i + 1
    return ranked


_DEFAULT_WEIGHTS = {
    "pe": -0.15,
    "pb": -0.10,
    "roe": 0.20,
    "profit_margin": 0.15,
    "dividend_yield": 0.10,
    "debt_equity": -0.10,
    "revenue_growth": 0.10,
    "fcf_yield": 0.10,
}


def composite_score(stock: dict, all_stocks: list, weights: dict = None) -> float:
    """Compute rank-based composite score for a stock."""
    if weights is None:
        weights = _DEFAULT_WEIGHTS

    score = 0.0
    total_weight = 0.0

    for metric, w in weights.items():
        val = stock.get(metric)
        if val is None:
            continue

        # Get all values for this metric
        vals = [s.get(metric) for s in all_stocks if s.get(metric) is not None]
        if not vals:
            continue

        # Percentile rank (0 to 1)
        rank = sum(1 for v in vals if v <= val) / len(vals)

        # For negative weights, invert the rank (lower is better)
        if w < 0:
            rank = 1 - rank

        score += rank * abs(w)
        total_weight += abs(w)

    return safe_divide(score, total_weight) if total_weight > 0 else 0.0


def rank_with_composite(stocks: list, weights: dict = None) -> list:
    """Score all stocks with composite metric and sort descending."""
    if not stocks:
        return []

    for s in stocks:
        s["composite_score"] = round(composite_score(s, stocks, weights), 4)

    stocks.sort(key=lambda s: s["composite_score"], reverse=True)

    for i, s in enumerate(stocks):
        s["composite_rank"] = i + 1

    return stocks


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------

def preset_screens() -> dict:
    """Return available preset screening strategies."""
    return {
        "value": {
            "name": "Value Stocks",
            "description": "Low P/E, low P/B, high dividend yield",
            "filters": {"pe_max": 15, "pb_max": 2, "dividend_yield_min": 0.02, "market_cap_min": 10e9},
            "sort_by": "pe",
            "ascending": True,
        },
        "growth": {
            "name": "Growth Stocks",
            "description": "High revenue growth, strong margins",
            "filters": {"revenue_growth_min": 0.15, "profit_margin_min": 0.10, "market_cap_min": 5e9},
            "sort_by": "revenue_growth",
            "ascending": False,
        },
        "dividend": {
            "name": "Dividend Champions",
            "description": "High yield, sustainable payout",
            "filters": {"dividend_yield_min": 0.03, "pe_max": 25, "debt_equity_max": 1.5},
            "sort_by": "dividend_yield",
            "ascending": False,
        },
        "quality": {
            "name": "Quality Compounders",
            "description": "High ROE, strong margins, low debt",
            "filters": {"roe_min": 0.15, "profit_margin_min": 0.15, "debt_equity_max": 1.0},
            "sort_by": "roe",
            "ascending": False,
        },
        "low_vol": {
            "name": "Low Volatility",
            "description": "Low beta, stable large-caps",
            "filters": {"beta_max": 0.8, "market_cap_min": 50e9},
            "sort_by": "beta",
            "ascending": True,
        },
    }
