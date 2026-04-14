"""Tests for core/cache.py — SQLite caching layer."""
import os
import json
import threading
import tempfile
import pytest

# Override DB_PATH before importing cache so tests use a temp DB
import core.cache as cache_module

_original_db_dir = cache_module.DB_DIR
_original_db_path = cache_module.DB_PATH


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path):
    """Redirect cache to a temp directory for each test."""
    cache_module.DB_DIR = str(tmp_path)
    cache_module.DB_PATH = os.path.join(str(tmp_path), "cache.db")
    yield
    cache_module.DB_DIR = _original_db_dir
    cache_module.DB_PATH = _original_db_path


from core.cache import (
    _get_conn, get_cached_prices, store_prices,
    get_cached_metric, store_metric,
    get_cached_news, store_news,
    get_cached_factors, store_factors,
    invalidate, clear_expired, db_stats,
)


# ---------------------------------------------------------------------------
# Price cache
# ---------------------------------------------------------------------------

def test_store_and_retrieve_prices():
    rows = [
        {"date": "2024-01-02", "open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000},
        {"date": "2024-01-03", "open": 103, "high": 107, "low": 102, "close": 106, "volume": 1200},
    ]
    store_prices("AAPL", rows)
    cached = get_cached_prices("AAPL")
    assert len(cached) == 2
    assert cached[0]["date"] == "2024-01-02"
    assert cached[0]["close"] == 103
    assert cached[1]["volume"] == 1200


def test_get_cached_prices_with_date_range():
    rows = [
        {"date": "2024-01-02", "open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000},
        {"date": "2024-01-03", "open": 103, "high": 107, "low": 102, "close": 106, "volume": 1200},
        {"date": "2024-01-04", "open": 106, "high": 110, "low": 105, "close": 109, "volume": 1100},
    ]
    store_prices("AAPL", rows)
    cached = get_cached_prices("AAPL", start_date="2024-01-03", end_date="2024-01-03")
    assert len(cached) == 1
    assert cached[0]["date"] == "2024-01-03"


def test_get_cached_prices_empty():
    cached = get_cached_prices("ZZZZ")
    assert cached == []


# ---------------------------------------------------------------------------
# Metrics cache
# ---------------------------------------------------------------------------

def test_store_and_retrieve_metric():
    data = {"sharpe": 1.5, "beta": 0.9, "tickers": ["AAPL", "MSFT"]}
    store_metric("portfolio:abc", data, ttl_hours=24)
    result = get_cached_metric("portfolio:abc")
    assert result == data
    assert result["sharpe"] == 1.5
    assert result["tickers"] == ["AAPL", "MSFT"]


def test_metric_ttl_expiration():
    """Store with ttl_hours=0, verify get_cached_metric returns None."""
    store_metric("test:expired", {"value": 42}, ttl_hours=0)
    result = get_cached_metric("test:expired")
    assert result is None


def test_metric_not_found():
    result = get_cached_metric("nonexistent:key")
    assert result is None


# ---------------------------------------------------------------------------
# News cache
# ---------------------------------------------------------------------------

def test_store_and_retrieve_news():
    articles = [
        {
            "id": "news1",
            "headline": "Apple hits all-time high",
            "source": "Reuters",
            "category": "technology",
            "sentiment": 0.8,
            "tickers": ["AAPL"],
            "impact_scores": {"AAPL": 0.9},
            "published_at": "2024-12-20 10:00:00",
        },
        {
            "id": "news2",
            "headline": "Fed holds rates steady",
            "source": "Bloomberg",
            "category": "macro",
            "sentiment": 0.1,
            "tickers": [],
            "impact_scores": {},
            "published_at": "2024-12-20 09:00:00",
        },
    ]
    store_news(articles)
    cached = get_cached_news(max_age_hours=1.0)
    assert len(cached) == 2
    assert cached[0]["headline"] in ("Apple hits all-time high", "Fed holds rates steady")


def test_news_auto_id():
    """Articles without 'id' get an auto-generated one from headline hash."""
    articles = [{"headline": "Test article", "source": "Test"}]
    store_news(articles)
    stats = db_stats()
    assert stats["news_cache"] == 1


# ---------------------------------------------------------------------------
# Factor cache
# ---------------------------------------------------------------------------

def test_store_and_retrieve_factors():
    rows = [
        {"date": "2024-01-02", "mkt_rf": 0.01, "smb": -0.005, "hml": 0.003, "rmw": 0.002, "cma": -0.001, "rf": 0.0002},
        {"date": "2024-01-03", "mkt_rf": -0.02, "smb": 0.008, "hml": -0.004, "rmw": 0.001, "cma": 0.002, "rf": 0.0002},
    ]
    store_factors(rows)
    cached = get_cached_factors()
    assert len(cached) == 2
    assert cached[0]["mkt_rf"] == 0.01


# ---------------------------------------------------------------------------
# Invalidation & maintenance
# ---------------------------------------------------------------------------

def test_invalidate_by_table():
    store_prices("AAPL", [{"date": "2024-01-02", "open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000}])
    store_prices("MSFT", [{"date": "2024-01-02", "open": 200, "high": 210, "low": 198, "close": 205, "volume": 2000}])
    deleted = invalidate("price_cache", "AAPL")
    assert deleted == 1
    assert len(get_cached_prices("AAPL")) == 0
    assert len(get_cached_prices("MSFT")) == 1


def test_invalidate_whole_table():
    store_prices("AAPL", [{"date": "2024-01-02", "open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000}])
    store_prices("MSFT", [{"date": "2024-01-02", "open": 200, "high": 210, "low": 198, "close": 205, "volume": 2000}])
    deleted = invalidate("price_cache")
    assert deleted == 2


def test_clear_expired():
    store_metric("fresh", {"a": 1}, ttl_hours=24)
    store_metric("expired", {"b": 2}, ttl_hours=0)
    removed = clear_expired()
    assert removed >= 1
    assert get_cached_metric("fresh") is not None


def test_db_stats():
    store_prices("AAPL", [
        {"date": "2024-01-02", "open": 100, "high": 105, "low": 99, "close": 103, "volume": 1000},
        {"date": "2024-01-03", "open": 103, "high": 107, "low": 102, "close": 106, "volume": 1200},
    ])
    store_metric("test:stat", {"val": 1})
    stats = db_stats()
    assert stats["price_cache"] == 2
    assert stats["metrics_cache"] == 1
    assert stats["news_cache"] == 0
    assert stats["factor_cache"] == 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_missing_db_directory(tmp_path):
    """Should auto-create data/ directory if missing."""
    new_dir = os.path.join(str(tmp_path), "subdir", "nested")
    cache_module.DB_DIR = new_dir
    cache_module.DB_PATH = os.path.join(new_dir, "cache.db")
    store_metric("test:autocreate", {"v": 1})
    assert os.path.exists(new_dir)
    result = get_cached_metric("test:autocreate")
    assert result == {"v": 1}


def test_concurrent_access():
    """Store from two threads without errors."""
    errors = []

    def writer(ticker, n):
        try:
            rows = [{"date": f"2024-01-{i+1:02d}", "open": i, "high": i+1, "low": i-1, "close": i, "volume": i*100}
                    for i in range(1, n+1)]
            store_prices(ticker, rows)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=writer, args=("AAPL", 10))
    t2 = threading.Thread(target=writer, args=("MSFT", 10))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(errors) == 0
    assert len(get_cached_prices("AAPL")) == 10
    assert len(get_cached_prices("MSFT")) == 10


def test_corrupted_db_recovery(tmp_path):
    """Write garbage to cache.db, verify recreation."""
    # First create a valid DB and store something
    store_metric("before", {"x": 1})

    # Corrupt the DB file
    db_path = cache_module.DB_PATH
    with open(db_path, "wb") as f:
        f.write(b"this is not a valid sqlite database!!! garbage data")

    # Should recover by deleting and recreating
    store_metric("after", {"y": 2})
    result = get_cached_metric("after")
    assert result == {"y": 2}
