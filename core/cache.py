"""
SQLite caching layer for price data, computed metrics, news, and factor data.
Uses Python's built-in sqlite3 — no new dependencies.
"""
import sqlite3
import json
import os
import hashlib
from datetime import datetime, timedelta

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "cache.db")

_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS price_cache (
        ticker TEXT NOT NULL,
        date TEXT NOT NULL,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume INTEGER,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (ticker, date)
    )""",
    """CREATE TABLE IF NOT EXISTS metrics_cache (
        key TEXT PRIMARY KEY,
        value TEXT,
        computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ttl_hours INTEGER DEFAULT 24
    )""",
    """CREATE TABLE IF NOT EXISTS news_cache (
        id TEXT PRIMARY KEY,
        headline TEXT,
        source TEXT,
        category TEXT,
        sentiment REAL,
        tickers TEXT,
        impact_scores TEXT,
        published_at TIMESTAMP,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    """CREATE TABLE IF NOT EXISTS factor_cache (
        date TEXT PRIMARY KEY,
        mkt_rf REAL,
        smb REAL,
        hml REAL,
        rmw REAL,
        cma REAL,
        rf REAL,
        fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
]


def _get_conn():
    """Get SQLite connection. Create DB dir and tables if needed.
    Uses check_same_thread=False for thread safety.
    Handles corrupted DB by deleting and recreating."""
    os.makedirs(DB_DIR, exist_ok=True)
    try:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        for stmt in _SCHEMA:
            conn.execute(stmt)
        conn.commit()
        return conn
    except sqlite3.DatabaseError:
        # Corrupted DB — delete and recreate
        try:
            os.remove(DB_PATH)
        except OSError:
            pass
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        for stmt in _SCHEMA:
            conn.execute(stmt)
        conn.commit()
        return conn


def _now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Price cache
# ---------------------------------------------------------------------------

def get_cached_prices(ticker: str, start_date: str = None, end_date: str = None) -> list:
    """Fetch cached OHLCV rows for a ticker within date range.
    Returns list of dicts with keys: date, open, high, low, close, volume.
    Returns empty list if nothing cached."""
    conn = _get_conn()
    try:
        query = "SELECT date, open, high, low, close, volume FROM price_cache WHERE ticker = ?"
        params = [ticker.upper()]
        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def store_prices(ticker: str, rows: list) -> None:
    """Store OHLCV data. rows is list of dicts with keys: date, open, high, low, close, volume.
    Uses INSERT OR REPLACE to handle duplicates."""
    if not rows:
        return
    conn = _get_conn()
    try:
        now = _now_iso()
        ticker_upper = ticker.upper()
        conn.executemany(
            "INSERT OR REPLACE INTO price_cache (ticker, date, open, high, low, close, volume, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (ticker_upper, r["date"], r.get("open"), r.get("high"),
                 r.get("low"), r.get("close"), r.get("volume"), now)
                for r in rows
            ]
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Metrics cache
# ---------------------------------------------------------------------------

def get_cached_metric(key: str):
    """Fetch a cached computed metric by key.
    Returns None if not found or if TTL has expired.
    Value is stored as JSON string — deserialize before returning."""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT value, computed_at, ttl_hours FROM metrics_cache WHERE key = ?",
            (key,)
        ).fetchone()
        if row is None:
            return None
        computed_at = datetime.strptime(row["computed_at"], "%Y-%m-%d %H:%M:%S")
        ttl = timedelta(hours=row["ttl_hours"])
        if datetime.utcnow() - computed_at > ttl:
            return None
        return json.loads(row["value"])
    except Exception:
        return None
    finally:
        conn.close()


def store_metric(key: str, value: object, ttl_hours: int = 24) -> None:
    """Store a JSON-serializable value with a TTL.
    Serializes value to JSON string before storing."""
    conn = _get_conn()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO metrics_cache (key, value, computed_at, ttl_hours) VALUES (?, ?, ?, ?)",
            (key, json.dumps(value, default=str), _now_iso(), ttl_hours)
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# News cache
# ---------------------------------------------------------------------------

def get_cached_news(max_age_hours: float = 1.0) -> list:
    """Fetch all cached news articles younger than max_age_hours.
    Returns list of dicts. Returns empty list if nothing fresh."""
    conn = _get_conn()
    try:
        cutoff = (datetime.utcnow() - timedelta(hours=max_age_hours)).strftime("%Y-%m-%d %H:%M:%S")
        rows = conn.execute(
            "SELECT * FROM news_cache WHERE fetched_at >= ? ORDER BY published_at DESC",
            (cutoff,)
        ).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            # Deserialize JSON fields
            if d.get("tickers"):
                try:
                    d["tickers"] = json.loads(d["tickers"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if d.get("impact_scores"):
                try:
                    d["impact_scores"] = json.loads(d["impact_scores"])
                except (json.JSONDecodeError, TypeError):
                    pass
            results.append(d)
        return results
    except Exception:
        return []
    finally:
        conn.close()


def store_news(articles: list) -> None:
    """Store news articles. Each article dict must have 'id' (or generate one from headline hash).
    Uses INSERT OR REPLACE."""
    if not articles:
        return
    conn = _get_conn()
    try:
        now = _now_iso()
        for a in articles:
            article_id = a.get("id") or hashlib.md5(
                a.get("headline", "").encode()
            ).hexdigest()
            tickers = json.dumps(a.get("tickers", [])) if isinstance(a.get("tickers"), (list, tuple)) else a.get("tickers", "[]")
            impact = json.dumps(a.get("impact_scores", {})) if isinstance(a.get("impact_scores"), (dict, list)) else a.get("impact_scores", "{}")
            conn.execute(
                "INSERT OR REPLACE INTO news_cache "
                "(id, headline, source, category, sentiment, tickers, impact_scores, published_at, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    article_id,
                    a.get("headline", ""),
                    a.get("source", ""),
                    a.get("category", ""),
                    a.get("sentiment", 0.0),
                    tickers,
                    impact,
                    a.get("published_at", now),
                    now,
                )
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Factor cache
# ---------------------------------------------------------------------------

def get_cached_factors(start_date: str = None, end_date: str = None) -> list:
    """Fetch cached Fama-French factor data within date range.
    Returns list of dicts with keys: date, mkt_rf, smb, hml, rmw, cma, rf."""
    conn = _get_conn()
    try:
        query = "SELECT date, mkt_rf, smb, hml, rmw, cma, rf FROM factor_cache"
        params = []
        conditions = []
        if start_date:
            conditions.append("date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("date <= ?")
            params.append(end_date)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY date"
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


def store_factors(rows: list) -> None:
    """Store Fama-French factor rows. Uses INSERT OR REPLACE."""
    if not rows:
        return
    conn = _get_conn()
    try:
        now = _now_iso()
        conn.executemany(
            "INSERT OR REPLACE INTO factor_cache (date, mkt_rf, smb, hml, rmw, cma, rf, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (r["date"], r.get("mkt_rf"), r.get("smb"), r.get("hml"),
                 r.get("rmw"), r.get("cma"), r.get("rf"), now)
                for r in rows
            ]
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

def invalidate(table: str, pattern: str = None) -> int:
    """Delete entries from a table. If pattern provided, delete where key LIKE pattern.
    For price_cache, pattern matches against ticker.
    Returns number of rows deleted."""
    allowed = {"price_cache", "metrics_cache", "news_cache", "factor_cache"}
    if table not in allowed:
        return 0
    conn = _get_conn()
    try:
        if pattern:
            if table == "price_cache":
                cur = conn.execute(f"DELETE FROM {table} WHERE ticker LIKE ?", (pattern,))
            elif table == "metrics_cache":
                cur = conn.execute(f"DELETE FROM {table} WHERE key LIKE ?", (pattern,))
            elif table == "news_cache":
                cur = conn.execute(f"DELETE FROM {table} WHERE id LIKE ?", (pattern,))
            elif table == "factor_cache":
                cur = conn.execute(f"DELETE FROM {table} WHERE date LIKE ?", (pattern,))
            else:
                cur = conn.execute(f"DELETE FROM {table}")
        else:
            cur = conn.execute(f"DELETE FROM {table}")
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def clear_expired() -> int:
    """Delete all metrics_cache entries where TTL has expired.
    Returns number of rows deleted."""
    conn = _get_conn()
    try:
        now = _now_iso()
        cur = conn.execute(
            "DELETE FROM metrics_cache WHERE datetime(computed_at, '+' || ttl_hours || ' hours') <= datetime(?)",
            (now,)
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def db_stats() -> dict:
    """Return row counts for each table. Useful for debugging.
    Returns: {"price_cache": int, "metrics_cache": int, "news_cache": int, "factor_cache": int}"""
    conn = _get_conn()
    try:
        stats = {}
        for table in ["price_cache", "metrics_cache", "news_cache", "factor_cache"]:
            row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
            stats[table] = row["cnt"]
        return stats
    finally:
        conn.close()
