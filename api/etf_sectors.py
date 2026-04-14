# ============================================================
# api/etf_sectors.py — ETF Sector + Geography + Cap Breakdown
# GET /api/etf_sectors?ticker=SPY
#
# Returns: sectors{}, geography{}, market_cap{}
#          (weight % for each bucket)
#
# Data priority: FMP → yfinance → static fallback
# Powers the Exposure tab donuts
# ============================================================

import json
import os
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import requests

FMP_KEY   = os.environ.get("FMP_API_KEY", "")
CACHE: dict = {}
CACHE_TTL = 86400   # 24-hour cache

# ── Static sector profiles for major ETFs ───────────────────

STATIC_SECTORS = {
    "SPY": {
        "sectors": {
            "Technology": 31.2, "Financials": 13.1, "Healthcare": 11.8,
            "Consumer Discretionary": 10.6, "Industrials": 8.9,
            "Communication Services": 8.6, "Consumer Staples": 5.9,
            "Energy": 3.8, "Real Estate": 2.4, "Materials": 2.2, "Utilities": 1.5,
        },
        "geography": {
            "United States": 100.0,
        },
        "market_cap": {
            "Mega Cap (>$200B)": 52.1, "Large Cap ($10-200B)": 37.4,
            "Mid Cap ($2-10B)": 9.2, "Small Cap (<$2B)": 1.3,
        },
    },
    "QQQ": {
        "sectors": {
            "Technology": 51.8, "Communication Services": 16.2,
            "Consumer Discretionary": 13.4, "Healthcare": 6.5,
            "Industrials": 4.8, "Consumer Staples": 4.1,
            "Financials": 2.2, "Energy": 0.6, "Utilities": 0.4,
        },
        "geography": {"United States": 100.0},
        "market_cap": {
            "Mega Cap (>$200B)": 65.3, "Large Cap ($10-200B)": 28.4,
            "Mid Cap ($2-10B)": 6.1, "Small Cap (<$2B)": 0.2,
        },
    },
    "VTI": {
        "sectors": {
            "Technology": 29.8, "Financials": 13.5, "Healthcare": 12.1,
            "Consumer Discretionary": 10.2, "Industrials": 9.4,
            "Communication Services": 7.8, "Consumer Staples": 5.6,
            "Energy": 4.1, "Real Estate": 3.2, "Materials": 2.5, "Utilities": 1.8,
        },
        "geography": {"United States": 100.0},
        "market_cap": {
            "Mega Cap (>$200B)": 42.3, "Large Cap ($10-200B)": 35.6,
            "Mid Cap ($2-10B)": 16.2, "Small Cap (<$2B)": 5.9,
        },
    },
    "VXUS": {
        "sectors": {
            "Financials": 21.4, "Industrials": 14.8, "Technology": 12.6,
            "Consumer Discretionary": 11.2, "Healthcare": 9.6,
            "Consumer Staples": 8.1, "Materials": 6.9, "Energy": 5.8,
            "Communication Services": 5.2, "Utilities": 2.6, "Real Estate": 1.8,
        },
        "geography": {
            "Japan": 15.3, "United Kingdom": 9.8, "France": 7.6,
            "China": 7.1, "Canada": 6.4, "Switzerland": 5.9,
            "Germany": 5.7, "Australia": 4.8, "India": 4.2, "Other": 33.2,
        },
        "market_cap": {
            "Mega Cap (>$200B)": 28.4, "Large Cap ($10-200B)": 42.1,
            "Mid Cap ($2-10B)": 22.6, "Small Cap (<$2B)": 6.9,
        },
    },
    "IWM": {
        "sectors": {
            "Financials": 18.6, "Healthcare": 16.2, "Industrials": 15.8,
            "Technology": 14.4, "Consumer Discretionary": 10.2,
            "Energy": 7.4, "Real Estate": 6.8, "Materials": 4.9,
            "Consumer Staples": 3.2, "Communication Services": 1.8, "Utilities": 0.7,
        },
        "geography": {"United States": 100.0},
        "market_cap": {
            "Mega Cap (>$200B)": 0.0, "Large Cap ($10-200B)": 5.4,
            "Mid Cap ($2-10B)": 38.2, "Small Cap (<$2B)": 56.4,
        },
    },
    "GLD": {
        "sectors": {"Commodities": 99.8, "Cash": 0.2},
        "geography": {"Global": 100.0},
        "market_cap": {"Commodity": 100.0},
    },
    "BND": {
        "sectors": {
            "Government": 42.3, "Mortgage-Backed": 18.1,
            "Corporate": 15.2, "Agency": 9.4,
            "International": 8.6, "Municipal": 3.8, "TIPS": 2.6,
        },
        "geography": {"United States": 91.4, "International": 8.6},
        "market_cap": {
            "Short-Term (< 1Y)": 5.2, "Medium-Term (1-5Y)": 38.6,
            "Long-Term (5-10Y)": 34.8, "Ultra Long (>10Y)": 21.4,
        },
    },
    "SCHD": {
        "sectors": {
            "Financials": 22.3, "Industrials": 18.6, "Consumer Staples": 14.8,
            "Healthcare": 12.4, "Technology": 11.6, "Energy": 8.9,
            "Materials": 5.2, "Consumer Discretionary": 4.1, "Utilities": 2.1,
        },
        "geography": {"United States": 100.0},
        "market_cap": {
            "Mega Cap (>$200B)": 38.6, "Large Cap ($10-200B)": 52.4,
            "Mid Cap ($2-10B)": 9.0, "Small Cap (<$2B)": 0.0,
        },
    },
    "VYM": {
        "sectors": {
            "Financials": 21.6, "Healthcare": 14.8, "Consumer Staples": 13.2,
            "Industrials": 12.4, "Energy": 9.8, "Technology": 8.6,
            "Real Estate": 5.4, "Utilities": 5.2, "Materials": 4.8,
            "Communication Services": 2.6, "Consumer Discretionary": 1.6,
        },
        "geography": {"United States": 100.0},
        "market_cap": {
            "Mega Cap (>$200B)": 35.8, "Large Cap ($10-200B)": 55.6,
            "Mid Cap ($2-10B)": 8.6, "Small Cap (<$2B)": 0.0,
        },
    },
    "JEPI": {
        "sectors": {
            "Healthcare": 18.4, "Financials": 14.6, "Industrials": 13.2,
            "Technology": 12.8, "Consumer Staples": 11.6, "Energy": 9.4,
            "Consumer Discretionary": 7.8, "Utilities": 6.2,
            "Communication Services": 3.8, "Materials": 1.8, "Real Estate": 0.4,
        },
        "geography": {"United States": 100.0},
        "market_cap": {
            "Mega Cap (>$200B)": 36.2, "Large Cap ($10-200B)": 51.8,
            "Mid Cap ($2-10B)": 12.0, "Small Cap (<$2B)": 0.0,
        },
    },
    "IBIT": {
        "sectors": {"Cryptocurrency": 100.0},
        "geography": {"Global": 100.0},
        "market_cap": {"Crypto Asset": 100.0},
    },
}

# ── Helpers ───────────────────────────────────────────────────

def _safe(val, default=None):
    try:
        if val is None:
            return default
        import math
        if isinstance(val, float) and math.isnan(val):
            return default
        return val
    except Exception:
        return default

# ── FMP Fetch ─────────────────────────────────────────────────

def fetch_fmp(ticker: str) -> dict:
    if not FMP_KEY:
        raise ValueError("FMP_API_KEY not set")

    r = requests.get(
        f"https://financialmodelingprep.com/api/v3/etf-sector-weightings/{ticker}",
        params={"apikey": FMP_KEY},
        timeout=8,
    )
    r.raise_for_status()
    raw = r.json() or []

    if not raw:
        raise ValueError(f"No FMP sector data for {ticker}")

    sectors = {}
    for item in raw:
        name = _safe(item.get("sector"), "Other")
        pct  = float(_safe(item.get("weightPercentage"), "0").replace("%", "") or 0)
        if name and pct > 0:
            sectors[name] = round(pct, 2)

    # FMP doesn't have geo/cap for ETFs — use static overlay
    static = STATIC_SECTORS.get(ticker.upper(), {})

    return {
        "ticker":     ticker,
        "sectors":    sectors or static.get("sectors", {}),
        "geography":  static.get("geography", {"United States": 100.0}),
        "market_cap": static.get("market_cap", {}),
        "_source":    "fmp",
    }

# ── yFinance Fallback ─────────────────────────────────────────

def fetch_yfinance_sectors(ticker: str) -> dict:
    import yfinance as yf

    t    = yf.Ticker(ticker)
    info = t.info or {}

    # yfinance fund_sector_weightings
    sectors = {}
    try:
        sw = getattr(t, "fund_sector_weightings", None)
        if sw is not None and not sw.empty:
            for idx, row in sw.iterrows():
                pct = float(row.get("realestate", row.iloc[0] if len(row) else 0) or 0)
                if idx and pct > 0:
                    sectors[str(idx)] = round(pct * 100, 2)
    except Exception:
        pass

    if not sectors:
        raise ValueError("yfinance has no sector data")

    static = STATIC_SECTORS.get(ticker.upper(), {})
    return {
        "ticker":     ticker,
        "sectors":    sectors,
        "geography":  static.get("geography", {"United States": 100.0}),
        "market_cap": static.get("market_cap", {}),
        "_source":    "yfinance",
    }

# ── Static Fallback ───────────────────────────────────────────

def fetch_static_sectors(ticker: str) -> dict:
    data = STATIC_SECTORS.get(ticker.upper())
    if not data:
        raise ValueError(f"No static sector data for {ticker}")
    return {
        "ticker":     ticker,
        "sectors":    data.get("sectors",    {}),
        "geography":  data.get("geography",  {}),
        "market_cap": data.get("market_cap", {}),
        "_source":    "static",
    }

# ── Main ──────────────────────────────────────────────────────

def get_etf_sectors(ticker: str) -> dict:
    ticker = ticker.upper().strip()

    if ticker in CACHE:
        ts, data = CACHE[ticker]
        if time.time() - ts < CACHE_TTL:
            return data

    result = None
    errors = []

    for fn in [fetch_fmp, fetch_yfinance_sectors, fetch_static_sectors]:
        try:
            result = fn(ticker)
            if result and result.get("sectors"):
                break
        except Exception as e:
            errors.append(str(e))

    if result is None:
        result = {
            "ticker":     ticker,
            "sectors":    {},
            "geography":  {},
            "market_cap": {},
            "errors":     errors,
        }

    CACHE[ticker] = (time.time(), result)
    return result

# ── Vercel Handler ────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        ticker = (params.get("ticker") or params.get("symbol") or [""])[0].strip()

        if not ticker:
            self._respond(400, {"error": "ticker param required"})
            return

        self._respond(200, get_etf_sectors(ticker))

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors_headers()
        self.end_headers()

    def _respond(self, status: int, payload: dict):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self._cors_headers()
        self.send_header("Content-Type",   "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, *args):
        pass
