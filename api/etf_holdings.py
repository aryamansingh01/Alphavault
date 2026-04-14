# ============================================================
# api/etf_holdings.py — ETF Top Holdings (Look-Through)
# GET /api/etf_holdings?ticker=SPY&limit=25
#
# Returns: holdings[] with ticker, name, weight, shares, value
#          + fund meta (name, aum, expense_ratio, inception)
#
# Data priority: FMP → yfinance fallback
# ============================================================

import json
import os
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import requests

FMP_KEY   = os.environ.get("FMP_API_KEY", "")
CACHE: dict = {}
CACHE_TTL = 86400   # 24-hour cache (ETF holdings change rarely)

# ── Static fallback for major ETFs ───────────────────────────
# Used when APIs fail — top 10 holdings for common ETFs

STATIC_HOLDINGS = {
    "SPY": [
        ("AAPL", "Apple Inc.",           7.2), ("MSFT", "Microsoft Corp.",      6.8),
        ("NVDA", "NVIDIA Corp.",          5.9), ("AMZN", "Amazon.com Inc.",      3.8),
        ("META", "Meta Platforms",        2.5), ("GOOGL","Alphabet Inc. A",      2.1),
        ("GOOG", "Alphabet Inc. C",       1.8), ("BRK.B","Berkshire Hathaway",   1.7),
        ("LLY",  "Eli Lilly & Co.",       1.6), ("AVGO", "Broadcom Inc.",        1.5),
    ],
    "QQQ": [
        ("AAPL", "Apple Inc.",           12.1), ("MSFT", "Microsoft Corp.",     10.2),
        ("NVDA", "NVIDIA Corp.",           8.7), ("AMZN", "Amazon.com Inc.",     5.2),
        ("META", "Meta Platforms",         4.8), ("TSLA", "Tesla Inc.",          3.6),
        ("GOOGL","Alphabet Inc. A",        3.2), ("GOOG", "Alphabet Inc. C",     3.0),
        ("AVGO", "Broadcom Inc.",          2.8), ("COST", "Costco Wholesale",    2.2),
    ],
    "VTI": [
        ("AAPL", "Apple Inc.",            5.8), ("MSFT", "Microsoft Corp.",      5.5),
        ("NVDA", "NVIDIA Corp.",           4.8), ("AMZN", "Amazon.com Inc.",     3.1),
        ("META", "Meta Platforms",         2.1), ("GOOGL","Alphabet Inc. A",     1.7),
        ("BRK.B","Berkshire Hathaway",     1.6), ("LLY",  "Eli Lilly & Co.",     1.5),
        ("AVGO", "Broadcom Inc.",          1.4), ("TSLA", "Tesla Inc.",           1.3),
    ],
    "IWM": [
        ("IRTC", "iRhythm Technologies",  0.6), ("ENSG", "Ensign Group",        0.5),
        ("MMSI", "Merit Medical Systems", 0.5), ("CAVA", "CAVA Group",          0.4),
        ("MOG.A","Moog Inc.",             0.4), ("ITGR", "Integer Holdings",    0.4),
        ("NUVL", "Nuvalent Inc.",         0.4), ("STEP", "StepStone Group",     0.4),
        ("CSWI", "CSW Industrials",       0.4), ("TREX", "Trex Company",        0.3),
    ],
    "GLD": [("GOLD_PHYSICAL", "Gold Bullion", 99.8)],
    "BND": [
        ("UST",  "US Treasury Notes",    42.3), ("MBS",  "Mortgage-Backed Sec.",18.1),
        ("CORP", "Investment Grade Corp",15.2), ("GOV",  "US Agency Bonds",      9.4),
        ("INTL", "International Bonds",   8.6), ("MUNI", "Municipal Bonds",       3.8),
        ("TIPS", "Treasury Inflation",    2.6),
    ],
    "SCHD": [
        ("AVGO", "Broadcom Inc.",         4.9), ("HD",   "Home Depot",           4.8),
        ("HON",  "Honeywell Intl.",       4.7), ("AMGN", "Amgen Inc.",           4.6),
        ("CVX",  "Chevron Corp.",         4.5), ("TXN",  "Texas Instruments",    4.4),
        ("CSCO", "Cisco Systems",         4.3), ("KO",   "Coca-Cola Co.",        4.2),
        ("PEP",  "PepsiCo Inc.",          4.1), ("MRK",  "Merck & Co.",          4.0),
    ],
    "VYM": [
        ("JPM",  "JPMorgan Chase",        5.1), ("BRK.B","Berkshire Hathaway",   4.3),
        ("XOM",  "Exxon Mobil",           3.9), ("JNJ",  "Johnson & Johnson",    3.8),
        ("PG",   "Procter & Gamble",      3.6), ("HD",   "Home Depot",           3.3),
        ("ABBV", "AbbVie Inc.",           3.2), ("MRK",  "Merck & Co.",          2.9),
        ("CVX",  "Chevron Corp.",         2.8), ("KO",   "Coca-Cola Co.",        2.7),
    ],
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

def fetch_fmp(ticker: str, limit: int) -> dict:
    if not FMP_KEY:
        raise ValueError("FMP_API_KEY not set")

    # ETF holdings
    r_hold = requests.get(
        f"https://financialmodelingprep.com/api/v3/etf-holder/{ticker}",
        params={"apikey": FMP_KEY},
        timeout=8,
    )
    r_hold.raise_for_status()
    raw = r_hold.json() or []

    holdings = []
    for item in raw[:limit]:
        holdings.append({
            "ticker":   str(_safe(item.get("asset"),             "—")),
            "name":     str(_safe(item.get("name"),              "—")),
            "weight":   float(_safe(item.get("weightPercentage"), 0) or 0),
            "shares":   _safe(item.get("shares")),
            "value":    _safe(item.get("marketValue")),
        })

    # ETF info
    r_info = requests.get(
        f"https://financialmodelingprep.com/api/v4/etf-info",
        params={"symbol": ticker, "apikey": FMP_KEY},
        timeout=8,
    )
    info_raw = r_info.json() if r_info.ok else []
    info = info_raw[0] if info_raw else {}

    return {
        "ticker":   ticker,
        "name":     _safe(info.get("fundName")),
        "aum":      _safe(info.get("aum")),
        "expense_ratio": _safe(info.get("expenseRatio")),
        "inception":     _safe(info.get("inceptionDate")),
        "holdings": holdings,
        "count":    len(holdings),
        "_source":  "fmp",
    }

# ── yFinance Fallback ─────────────────────────────────────────

def fetch_yfinance_etf(ticker: str, limit: int) -> dict:
    import yfinance as yf

    t    = yf.Ticker(ticker)
    info = t.info or {}

    # Try getting holdings from yfinance
    holdings = []
    try:
        # yfinance doesn't have a direct holdings API for ETFs
        # Use fund_holding_info if available
        fh = getattr(t, "fund_holding_info", None)
        if fh and isinstance(fh, dict):
            equities = fh.get("equityHoldings", {})
            # limited data
    except Exception:
        pass

    # If no holdings from yfinance, fall through to static
    if not holdings:
        raise ValueError("yfinance has no ETF holdings data")

    return {
        "ticker":        ticker,
        "name":          _safe(info.get("longName")),
        "aum":           _safe(info.get("totalAssets")),
        "expense_ratio": _safe(info.get("annualReportExpenseRatio")),
        "inception":     None,
        "holdings":      holdings[:limit],
        "count":         len(holdings[:limit]),
        "_source":       "yfinance",
    }

# ── Static Fallback ───────────────────────────────────────────

def fetch_static(ticker: str, limit: int) -> dict:
    raw = STATIC_HOLDINGS.get(ticker.upper())
    if not raw:
        raise ValueError(f"No static holdings for {ticker}")

    holdings = [
        {"ticker": t, "name": n, "weight": w, "shares": None, "value": None}
        for t, n, w in raw[:limit]
    ]
    return {
        "ticker":        ticker,
        "name":          f"{ticker} ETF",
        "aum":           None,
        "expense_ratio": None,
        "inception":     None,
        "holdings":      holdings,
        "count":         len(holdings),
        "_source":       "static",
    }

# ── Main ──────────────────────────────────────────────────────

def get_etf_holdings(ticker: str, limit: int = 25) -> dict:
    ticker = ticker.upper().strip()
    cache_key = f"{ticker}:{limit}"

    if cache_key in CACHE:
        ts, data = CACHE[cache_key]
        if time.time() - ts < CACHE_TTL:
            return data

    result = None
    errors = []

    for fn in [fetch_fmp, fetch_yfinance_etf, fetch_static]:
        try:
            result = fn(ticker, limit)
            if result and result.get("holdings"):
                break
        except Exception as e:
            errors.append(str(e))

    if result is None:
        result = {
            "ticker":   ticker,
            "holdings": [],
            "count":    0,
            "errors":   errors,
        }

    CACHE[cache_key] = (time.time(), result)
    return result

# ── Vercel Handler ────────────────────────────────────────────

class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        ticker = (params.get("ticker") or params.get("symbol") or [""])[0].strip()
        limit  = int((params.get("limit") or ["25"])[0])

        if not ticker:
            self._respond(400, {"error": "ticker param required"})
            return

        self._respond(200, get_etf_holdings(ticker, min(limit, 50)))

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
