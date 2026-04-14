"""
Shared data fetcher — single entry point for all data across the project.
Checks cache first, fetches from API only if stale, stores result in cache.
"""
import os
import json
import urllib.request
import urllib.parse
import hashlib
from datetime import datetime, timedelta

import pandas as pd
import numpy as np
import yfinance as yf

from core import cache


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def period_to_days(period: str) -> int:
    """Convert period string to number of calendar days.
    '1m'->30, '3m'->90, '6m'->180, 'ytd'->days since Jan 1, '1y'->365, '2y'->730,
    '3y'->1095, '5y'->1825, '10y'->3650. Default: 365"""
    period = (period or "1y").lower().strip()
    mapping = {
        "1m": 30, "3m": 90, "6m": 180,
        "1y": 365, "2y": 730, "3y": 1095,
        "5y": 1825, "10y": 3650,
    }
    if period in mapping:
        return mapping[period]
    if period == "ytd":
        today = datetime.today()
        jan1 = datetime(today.year, 1, 1)
        return (today - jan1).days or 1
    return 365


def _is_fresh(cached_rows: list, start_date: str) -> bool:
    """Check if cached data is fresh enough: covers start_date and has recent data."""
    if not cached_rows:
        return False
    # Check coverage
    if cached_rows[0]["date"] > start_date:
        return False
    # Check recency: most recent cached date within 3 calendar days of today
    last_date = datetime.strptime(cached_rows[-1]["date"], "%Y-%m-%d").date()
    today = datetime.today().date()
    return (today - last_date).days <= 3


# ---------------------------------------------------------------------------
# OHLCV data
# ---------------------------------------------------------------------------

def get_ohlcv(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Fetch OHLCV price data for a single ticker.
    Checks cache first, fetches from yfinance if stale.
    Returns DataFrame with columns: open, high, low, close, volume.
    Index: DatetimeIndex. Returns empty DataFrame on failure — never raises."""
    try:
        ticker = ticker.upper().strip()
        days = period_to_days(period)
        start_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = datetime.today().strftime("%Y-%m-%d")

        # Check cache
        cached = cache.get_cached_prices(ticker, start_date, end_date)
        if _is_fresh(cached, start_date):
            print(f"[DATA] Cache HIT for {ticker} prices")
            df = pd.DataFrame(cached)
            df.index = pd.to_datetime(df["date"])
            df = df.drop(columns=["date"])
            df.index.name = None
            return df

        # Cache miss — fetch from yfinance
        print(f"[DATA] Cache MISS for {ticker}, fetching...")
        try:
            yticker = yf.Ticker(ticker)
            df = yticker.history(period=period)
        except Exception:
            # yfinance failed — return stale cache if available
            if cached:
                print(f"[DATA] yfinance failed, returning stale cache for {ticker}")
                df = pd.DataFrame(cached)
                df.index = pd.to_datetime(df["date"])
                df = df.drop(columns=["date"])
                df.index.name = None
                return df
            return pd.DataFrame()

        if df is None or df.empty:
            if cached:
                df = pd.DataFrame(cached)
                df.index = pd.to_datetime(df["date"])
                df = df.drop(columns=["date"])
                df.index.name = None
                return df
            return pd.DataFrame()

        # Handle MultiIndex columns (yfinance quirk with single ticker)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Strip timezone from index (yfinance returns tz-aware)
        if hasattr(df.index, 'tz') and df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        # Normalize column names to lowercase
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]

        # Keep only OHLCV columns
        keep = []
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                keep.append(col)
        df = df[keep]

        # Store in cache
        rows = []
        for idx, row in df.iterrows():
            rows.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": float(row.get("open", 0)) if pd.notna(row.get("open")) else None,
                "high": float(row.get("high", 0)) if pd.notna(row.get("high")) else None,
                "low": float(row.get("low", 0)) if pd.notna(row.get("low")) else None,
                "close": float(row.get("close", 0)) if pd.notna(row.get("close")) else None,
                "volume": int(row.get("volume", 0)) if pd.notna(row.get("volume")) else None,
            })
        if rows:
            cache.store_prices(ticker, rows)

        df.index.name = None
        return df

    except Exception:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Daily returns
# ---------------------------------------------------------------------------

def get_daily_returns(tickers: list, period: str = "1y") -> pd.DataFrame:
    """Fetch daily returns for multiple tickers.
    Returns DataFrame with one column per ticker, DatetimeIndex.
    Drops tickers that returned no data."""
    if not tickers:
        return pd.DataFrame()

    closes = {}
    for ticker in tickers:
        df = get_ohlcv(ticker, period)
        if df.empty or "close" not in df.columns:
            continue
        closes[ticker.upper()] = df["close"]

    if not closes:
        return pd.DataFrame()

    prices = pd.DataFrame(closes)
    returns = prices.pct_change().iloc[1:]  # drop first NaN row
    returns = returns.ffill()  # forward-fill misaligned trading days
    return returns


# ---------------------------------------------------------------------------
# Market news
# ---------------------------------------------------------------------------

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")


def get_market_news(tickers: list = None, max_age_hours: float = 1.0) -> list:
    """Fetch market news, optionally filtered by tickers.
    Checks cache first, fetches from Finnhub if stale.
    Never raises — returns empty list on failure."""
    try:
        # Check cache
        cached = cache.get_cached_news(max_age_hours)
        if cached:
            print(f"[DATA] Cache HIT for news ({len(cached)} articles)")
            if tickers:
                tickers_upper = {t.upper() for t in tickers}
                filtered = [a for a in cached if _article_matches_tickers(a, tickers_upper)]
                # If ticker filter removes everything, return general news instead of nothing
                return filtered if filtered else cached
            return cached

        print("[DATA] Cache MISS for news, fetching...")
        articles = []

        # Always fetch general news first (works without specific tickers)
        articles.extend(_fetch_finnhub_general_news())

        # Also fetch company-specific news if tickers provided
        if tickers:
            for ticker in tickers[:5]:  # limit to 5 to avoid rate limits
                articles.extend(_fetch_finnhub_company_news(ticker.upper()))

        # Deduplicate by id
        seen = set()
        unique = []
        for a in articles:
            aid = a.get("id", "")
            if aid not in seen:
                seen.add(aid)
                unique.append(a)
        articles = unique

        # Store in cache
        if articles:
            cache.store_news(articles)

        return articles

    except Exception:
        return []


def _article_matches_tickers(article: dict, tickers_upper: set) -> bool:
    """Check if article is relevant to any of the given tickers.
    General news (empty tickers list) is always considered relevant."""
    art_tickers = article.get("tickers", [])
    if isinstance(art_tickers, str):
        try:
            art_tickers = json.loads(art_tickers)
        except (json.JSONDecodeError, TypeError):
            art_tickers = [art_tickers]
    # General news (no specific tickers) is always relevant
    if not art_tickers:
        return True
    if isinstance(art_tickers, list):
        for t in art_tickers:
            if str(t).upper() in tickers_upper:
                return True
    return False


def _fetch_finnhub_company_news(ticker: str) -> list:
    """Fetch company news from Finnhub."""
    if not FINNHUB_KEY:
        return []
    try:
        today = datetime.today().strftime("%Y-%m-%d")
        week_ago = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")
        url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from={week_ago}&to={today}&token={FINNHUB_KEY}"
        req = urllib.request.Request(url, headers={"User-Agent": "AlphaVault/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = json.loads(r.read())
        return [_normalize_finnhub_article(item, [ticker]) for item in (raw or [])[:20]]
    except Exception:
        return []


def _fetch_finnhub_general_news() -> list:
    """Fetch general market news from Finnhub."""
    if not FINNHUB_KEY:
        return []
    try:
        url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_KEY}"
        req = urllib.request.Request(url, headers={"User-Agent": "AlphaVault/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = json.loads(r.read())
        return [_normalize_finnhub_article(item, []) for item in (raw or [])[:20]]
    except Exception:
        return []


def _normalize_finnhub_article(item: dict, tickers: list) -> dict:
    """Normalize a Finnhub article to our standard format."""
    ts = item.get("datetime", 0)
    pub = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S") if ts else ""
    return {
        "id": hashlib.md5(item.get("headline", "").encode()).hexdigest(),
        "headline": item.get("headline", ""),
        "source": item.get("source", ""),
        "category": item.get("category", ""),
        "sentiment": 0.0,
        "tickers": tickers,
        "impact_scores": {},
        "published_at": pub,
        "url": item.get("url", ""),
        "summary": (item.get("summary", "") or "")[:300],
    }


# ---------------------------------------------------------------------------
# Quote (cached)
# ---------------------------------------------------------------------------

def get_quote_cached(ticker: str, max_age_minutes: float = 5.0) -> dict:
    """Fetch a stock quote with short-lived cache.
    Returns dict with quote fields. Returns empty dict on failure."""
    try:
        ticker = ticker.upper().strip()
        cache_key = f"quote:{ticker}"

        # Check metrics cache
        cached = cache.get_cached_metric(cache_key)
        if cached:
            print(f"[DATA] Cache HIT for {ticker} quote")
            return cached

        # Fetch from yfinance
        print(f"[DATA] Cache MISS for {ticker} quote, fetching...")
        try:
            t = yf.Ticker(ticker)
            info = t.info or {}
        except Exception:
            return {}

        quote = {
            "ticker": ticker,
            "price": info.get("currentPrice") or info.get("regularMarketPrice", 0),
            "change": info.get("regularMarketChange", 0),
            "change_pct": info.get("regularMarketChangePercent", 0),
            "volume": info.get("regularMarketVolume") or info.get("volume", 0),
            "market_cap": info.get("marketCap", 0),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "beta": info.get("beta", 0),
            "pe": info.get("trailingPE") or info.get("forwardPE", 0),
            "dividend_yield": info.get("dividendYield", 0),
        }

        cache.store_metric(cache_key, quote, ttl_hours=1)
        return quote

    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Fama-French factors
# ---------------------------------------------------------------------------

def get_fama_french_factors(period: str = "3y") -> pd.DataFrame:
    """Fetch Fama-French 5-factor data.
    Checks cache first, downloads from Ken French data library if missing.
    Returns DataFrame with columns: Mkt-RF, SMB, HML, RMW, CMA, RF. Index: DatetimeIndex.
    Returns empty DataFrame on failure."""
    try:
        days = period_to_days(period)
        start_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = datetime.today().strftime("%Y-%m-%d")

        # Check cache
        cached = cache.get_cached_factors(start_date, end_date)
        if cached and len(cached) > days * 0.5:  # reasonable coverage
            print(f"[DATA] Cache HIT for Fama-French factors ({len(cached)} rows)")
            df = pd.DataFrame(cached)
            df.index = pd.to_datetime(df["date"])
            df = df.drop(columns=["date"])
            df.columns = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]
            df.index.name = None
            return df

        # Try pandas_datareader
        print("[DATA] Cache MISS for Fama-French factors, fetching...")
        df = _download_ff_factors()

        if df is not None and not df.empty:
            # Filter to period
            cutoff = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
            df = df[df.index >= cutoff]

            # Store in cache
            rows = []
            for idx, row in df.iterrows():
                rows.append({
                    "date": idx.strftime("%Y-%m-%d"),
                    "mkt_rf": float(row.get("Mkt-RF", 0)),
                    "smb": float(row.get("SMB", 0)),
                    "hml": float(row.get("HML", 0)),
                    "rmw": float(row.get("RMW", 0)),
                    "cma": float(row.get("CMA", 0)),
                    "rf": float(row.get("RF", 0)),
                })
            if rows:
                cache.store_factors(rows)

            df.index.name = None
            return df

        # Fallback to stale cache
        if cached:
            df = pd.DataFrame(cached)
            df.index = pd.to_datetime(df["date"])
            df = df.drop(columns=["date"])
            df.columns = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"]
            df.index.name = None
            return df

        return pd.DataFrame()

    except Exception:
        return pd.DataFrame()


def _download_ff_factors() -> pd.DataFrame:
    """Download Fama-French 5-factor daily data from Ken French library."""
    try:
        import io
        import zipfile

        url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
        req = urllib.request.Request(url, headers={"User-Agent": "AlphaVault/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            zip_data = r.read()

        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            csv_name = zf.namelist()[0]
            with zf.open(csv_name) as f:
                lines = f.read().decode("utf-8").split("\n")

        # Find header row (contains "Mkt-RF")
        header_idx = None
        for i, line in enumerate(lines):
            if "Mkt-RF" in line:
                header_idx = i
                break

        if header_idx is None:
            return pd.DataFrame()

        # Parse data
        headers = [h.strip() for h in lines[header_idx].split(",")]
        data_rows = []
        for line in lines[header_idx + 1:]:
            parts = line.strip().split(",")
            if len(parts) < 6:
                continue
            date_str = parts[0].strip()
            if len(date_str) != 8 or not date_str.isdigit():
                continue
            try:
                dt = datetime.strptime(date_str, "%Y%m%d")
                vals = [float(v.strip()) / 100.0 for v in parts[1:6]]
                rf = float(parts[6].strip()) / 100.0 if len(parts) > 6 else 0.0
                data_rows.append([dt] + vals + [rf])
            except (ValueError, IndexError):
                continue

        if not data_rows:
            return pd.DataFrame()

        df = pd.DataFrame(data_rows, columns=["date", "Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"])
        df.index = pd.to_datetime(df["date"])
        df = df.drop(columns=["date"])
        return df

    except Exception:
        return pd.DataFrame()
