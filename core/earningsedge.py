"""
Earnings Calendar and Surprise Analysis Engine.
Tracks upcoming earnings dates, historical EPS surprises, and post-earnings price moves.
"""
import os
import json
import hashlib
import urllib.request
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from core.cache import get_cached_metric, store_metric
from core.sanitize import safe_divide

FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")


# ---------------------------------------------------------------------------
# Earnings Calendar
# ---------------------------------------------------------------------------

def get_earnings_calendar_finnhub(ticker: str = None, from_date: str = None,
                                   to_date: str = None) -> list:
    """Fetch earnings calendar from Finnhub."""
    if not FINNHUB_KEY:
        return []

    if not from_date:
        from_date = datetime.today().strftime("%Y-%m-%d")
    if not to_date:
        to_date = (datetime.today() + timedelta(weeks=4)).strftime("%Y-%m-%d")

    cache_key = f"earnings_calendar:{ticker or 'all'}:{from_date}"
    cached = get_cached_metric(cache_key)
    if cached is not None:
        return cached

    try:
        params = f"from={from_date}&to={to_date}&token={FINNHUB_KEY}"
        if ticker:
            params += f"&symbol={ticker.upper()}"
        url = f"https://finnhub.io/api/v1/calendar/earnings?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "AlphaVault/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())

        results = []
        for item in data.get("earningsCalendar", []):
            results.append({
                "ticker": item.get("symbol", ""),
                "date": item.get("date", ""),
                "quarter": f"Q{item.get('quarter', '?')} {item.get('year', '')}".strip(),
                "eps_estimate": item.get("epsEstimate"),
                "eps_actual": item.get("epsActual"),
                "revenue_estimate": item.get("revenueEstimate"),
                "revenue_actual": item.get("revenueActual"),
                "hour": item.get("hour", "unknown"),
            })

        store_metric(cache_key, results, ttl_hours=6)
        return results
    except Exception:
        return []


def get_earnings_calendar_yfinance(ticker: str) -> list:
    """Fallback: get earnings dates from yfinance."""
    try:
        t = yf.Ticker(ticker.upper())

        results = []
        try:
            cal = t.calendar
            if cal is not None:
                if isinstance(cal, dict):
                    ed = cal.get("Earnings Date")
                    if ed:
                        dates = ed if isinstance(ed, list) else [ed]
                        for d in dates:
                            results.append({
                                "ticker": ticker.upper(),
                                "date": str(d)[:10] if d else "",
                                "quarter": "",
                                "eps_estimate": cal.get("Earnings Average"),
                                "eps_actual": None,
                                "revenue_estimate": cal.get("Revenue Average"),
                                "revenue_actual": None,
                                "hour": "unknown",
                            })
        except Exception:
            pass

        if not results:
            try:
                ed = t.earnings_dates
                if ed is not None and not ed.empty:
                    for idx, row in ed.head(8).iterrows():
                        results.append({
                            "ticker": ticker.upper(),
                            "date": str(idx)[:10],
                            "quarter": "",
                            "eps_estimate": row.get("EPS Estimate") if pd.notna(row.get("EPS Estimate")) else None,
                            "eps_actual": row.get("Reported EPS") if pd.notna(row.get("Reported EPS")) else None,
                            "revenue_estimate": None,
                            "revenue_actual": None,
                            "hour": "unknown",
                        })
            except Exception:
                pass

        return results
    except Exception:
        return []


def get_earnings_calendar(ticker: str = None, weeks_ahead: int = 4) -> list:
    """Unified earnings calendar — tries Finnhub then yfinance."""
    from_date = datetime.today().strftime("%Y-%m-%d")
    to_date = (datetime.today() + timedelta(weeks=weeks_ahead)).strftime("%Y-%m-%d")

    results = get_earnings_calendar_finnhub(ticker, from_date, to_date)
    if not results and ticker:
        results = get_earnings_calendar_yfinance(ticker)

    results.sort(key=lambda x: x.get("date", ""))
    return results


# ---------------------------------------------------------------------------
# Historical Surprises
# ---------------------------------------------------------------------------

def get_earnings_history(ticker: str, n_quarters: int = 12) -> list:
    """Fetch historical EPS actuals vs estimates."""
    cache_key = f"earnings_history:{ticker.upper()}"
    cached = get_cached_metric(cache_key)
    if cached is not None:
        return cached[:n_quarters]

    results = _fetch_earnings_history_finnhub(ticker)
    if not results:
        results = _fetch_earnings_history_yfinance(ticker)

    # Process surprises
    for r in results:
        est = r.get("eps_estimate")
        act = r.get("eps_actual")
        if est is not None and act is not None:
            r["surprise"] = round(act - est, 4)
            r["surprise_pct"] = round(safe_divide(act - est, abs(est)) * 100, 2) if est != 0 else 0.0
            r["beat"] = act > est
        else:
            r["surprise"] = None
            r["surprise_pct"] = None
            r["beat"] = None

    results = results[:n_quarters]
    if results:
        store_metric(cache_key, results, ttl_hours=24)
    return results


def _fetch_earnings_history_finnhub(ticker: str) -> list:
    if not FINNHUB_KEY:
        return []
    try:
        url = f"https://finnhub.io/api/v1/stock/earnings?symbol={ticker.upper()}&limit=20&token={FINNHUB_KEY}"
        req = urllib.request.Request(url, headers={"User-Agent": "AlphaVault/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        results = []
        for item in (data if isinstance(data, list) else []):
            results.append({
                "ticker": ticker.upper(),
                "date": item.get("period", ""),
                "quarter": f"Q{item.get('quarter', '?')} {item.get('year', '')}".strip(),
                "eps_estimate": item.get("estimate"),
                "eps_actual": item.get("actual"),
            })
        return results
    except Exception:
        return []


def _fetch_earnings_history_yfinance(ticker: str) -> list:
    try:
        t = yf.Ticker(ticker.upper())
        ed = t.earnings_dates
        if ed is None or ed.empty:
            return []
        results = []
        for idx, row in ed.iterrows():
            act = row.get("Reported EPS")
            est = row.get("EPS Estimate")
            results.append({
                "ticker": ticker.upper(),
                "date": str(idx)[:10],
                "quarter": "",
                "eps_estimate": float(est) if pd.notna(est) else None,
                "eps_actual": float(act) if pd.notna(act) else None,
            })
        return results
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Surprise Stats
# ---------------------------------------------------------------------------

def calculate_surprise_stats(earnings_history: list) -> dict:
    """Compute summary statistics from earnings history."""
    valid = [e for e in earnings_history if e.get("beat") is not None]
    if not valid:
        return {
            "total_quarters": 0, "beats": 0, "misses": 0, "meets": 0,
            "beat_rate": 0, "avg_surprise_pct": 0, "median_surprise_pct": 0,
            "avg_beat_magnitude": 0, "avg_miss_magnitude": 0,
            "streak": 0, "consistency_score": 0,
        }

    total = len(valid)
    beats = sum(1 for e in valid if e["beat"])
    surprises = [e["surprise_pct"] for e in valid if e.get("surprise_pct") is not None]
    meets = sum(1 for s in surprises if abs(s) <= 1.0)
    misses = total - beats

    beat_surprises = [s for e, s in zip(valid, surprises) if e["beat"] and s is not None]
    miss_surprises = [s for e, s in zip(valid, surprises) if not e["beat"] and s is not None]

    # Streak: count from most recent
    streak = 0
    if valid:
        first_beat = valid[0]["beat"]
        for e in valid:
            if e["beat"] == first_beat:
                streak += 1
            else:
                break
        if not first_beat:
            streak = -streak

    # Consistency score
    beat_rate = safe_divide(beats, total) * 100
    std_surprise = float(np.std(surprises)) if surprises else 0
    consistency = (beat_rate / 100) * max(0, 1 - std_surprise / 100)
    consistency = max(0.0, min(1.0, consistency))

    return {
        "total_quarters": total,
        "beats": beats,
        "misses": misses,
        "meets": meets,
        "beat_rate": round(beat_rate, 1),
        "avg_surprise_pct": round(float(np.mean(surprises)), 2) if surprises else 0,
        "median_surprise_pct": round(float(np.median(surprises)), 2) if surprises else 0,
        "avg_beat_magnitude": round(float(np.mean(beat_surprises)), 2) if beat_surprises else 0,
        "avg_miss_magnitude": round(float(np.mean(miss_surprises)), 2) if miss_surprises else 0,
        "streak": streak,
        "consistency_score": round(consistency, 4),
    }


# ---------------------------------------------------------------------------
# Post-Earnings Price Moves
# ---------------------------------------------------------------------------

def get_post_earnings_moves(ticker: str, earnings_dates: list) -> list:
    """Calculate price moves after each earnings date."""
    try:
        from core.data import get_ohlcv
        df = get_ohlcv(ticker, "5y")
        if df.empty or "close" not in df.columns:
            return []
    except Exception:
        return []

    results = []
    for ed in earnings_dates:
        date_str = ed.get("date", "")
        if not date_str:
            continue
        try:
            dt = pd.Timestamp(date_str)
            # Find closest trading day
            mask = df.index >= dt
            if mask.sum() == 0:
                continue
            idx = df.index[mask][0]
            pos = df.index.get_loc(idx)

            price_on = float(df["close"].iloc[pos])
            price_1d = float(df["close"].iloc[pos + 1]) if pos + 1 < len(df) else None
            price_5d = float(df["close"].iloc[pos + 5]) if pos + 5 < len(df) else None

            move_1d = safe_divide(price_1d - price_on, price_on) * 100 if price_1d else None
            move_5d = safe_divide(price_5d - price_on, price_on) * 100 if price_5d else None

            results.append({
                "date": date_str,
                "quarter": ed.get("quarter", ""),
                "beat": ed.get("beat"),
                "surprise_pct": ed.get("surprise_pct"),
                "price_move_1d": round(move_1d, 2) if move_1d is not None else None,
                "price_move_5d": round(move_5d, 2) if move_5d is not None else None,
                "price_on_date": round(price_on, 2),
            })
        except Exception:
            continue

    return results


def estimate_expected_move(price_moves: list) -> dict:
    """Estimate expected post-earnings price move based on history."""
    moves_1d = [m["price_move_1d"] for m in price_moves if m.get("price_move_1d") is not None]
    moves_5d = [m["price_move_5d"] for m in price_moves if m.get("price_move_5d") is not None]

    beat_moves = [m["price_move_1d"] for m in price_moves
                  if m.get("price_move_1d") is not None and m.get("beat") is True]
    miss_moves = [m["price_move_1d"] for m in price_moves
                  if m.get("price_move_1d") is not None and m.get("beat") is False]

    return {
        "avg_abs_move_1d": round(float(np.mean(np.abs(moves_1d))), 2) if moves_1d else 0,
        "avg_abs_move_5d": round(float(np.mean(np.abs(moves_5d))), 2) if moves_5d else 0,
        "avg_move_on_beat_1d": round(float(np.mean(beat_moves)), 2) if beat_moves else 0,
        "avg_move_on_miss_1d": round(float(np.mean(miss_moves)), 2) if miss_moves else 0,
        "max_move_up_1d": round(float(max(moves_1d)), 2) if moves_1d else 0,
        "max_move_down_1d": round(float(min(moves_1d)), 2) if moves_1d else 0,
        "positive_reaction_rate": round(safe_divide(sum(1 for m in moves_1d if m > 0), len(moves_1d)) * 100, 1) if moves_1d else 0,
    }


# ---------------------------------------------------------------------------
# Portfolio Summary
# ---------------------------------------------------------------------------

def portfolio_earnings_summary(holdings: list, weeks_ahead: int = 4) -> dict:
    """Generate earnings summary for portfolio holdings."""
    if not holdings:
        return {"upcoming": [], "no_upcoming": [], "total_portfolio_weight_reporting": 0,
                "highest_impact": None, "earnings_this_week": 0, "earnings_next_week": 0}

    today = datetime.today()
    end_of_week = today + timedelta(days=(6 - today.weekday()))
    end_of_next_week = end_of_week + timedelta(days=7)

    upcoming = []
    no_upcoming = []

    for h in holdings:
        ticker = h.get("ticker", "").upper()
        weight = h.get("weight", 0)

        cal = get_earnings_calendar(ticker, weeks_ahead)
        future = [e for e in cal if e.get("date", "") >= today.strftime("%Y-%m-%d")]

        if not future:
            no_upcoming.append(ticker)
            continue

        hist = get_earnings_history(ticker)
        stats = calculate_surprise_stats(hist)
        moves = get_post_earnings_moves(ticker, hist)
        expected = estimate_expected_move(moves)

        for e in future:
            try:
                days_until = (datetime.strptime(e["date"], "%Y-%m-%d") - today).days
            except (ValueError, TypeError):
                days_until = 0

            upcoming.append({
                "ticker": ticker,
                "date": e["date"],
                "days_until": days_until,
                "portfolio_weight": weight,
                "beat_rate": stats["beat_rate"],
                "avg_abs_move_1d": expected["avg_abs_move_1d"],
                "expected_portfolio_impact": round(weight * expected["avg_abs_move_1d"], 4),
            })

    upcoming.sort(key=lambda x: x.get("date", ""))

    total_weight = sum(u["portfolio_weight"] for u in upcoming)
    highest = max(upcoming, key=lambda x: x["expected_portfolio_impact"]) if upcoming else None

    this_week = sum(1 for u in upcoming if u.get("date", "") <= end_of_week.strftime("%Y-%m-%d"))
    next_week = sum(1 for u in upcoming
                    if end_of_week.strftime("%Y-%m-%d") < u.get("date", "") <= end_of_next_week.strftime("%Y-%m-%d"))

    return {
        "upcoming": upcoming,
        "no_upcoming": no_upcoming,
        "total_portfolio_weight_reporting": round(total_weight, 4),
        "highest_impact": {"ticker": highest["ticker"], "expected_impact": highest["expected_portfolio_impact"]} if highest else None,
        "earnings_this_week": this_week,
        "earnings_next_week": next_week,
    }
