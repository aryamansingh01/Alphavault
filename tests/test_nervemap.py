"""Tests for core/nervemap.py — Rules-based news impact engine."""
import numpy as np
import pytest

from core.nervemap import (
    classify_category, score_headline, aggregate_scores, portfolio_impact,
    TICKER_SECTOR_MAP, IMPACT_WEIGHTS, SENSITIVITY_SCALE,
)


# ---------------------------------------------------------------------------
# classify_category
# ---------------------------------------------------------------------------

def test_classify_fed_rates():
    assert classify_category("Fed raises interest rates by 25 basis points") == "monetary_policy"


def test_classify_earnings():
    assert classify_category("Apple beats earnings estimates for Q3") == "earnings"


def test_classify_commodity():
    assert classify_category("Oil prices surge after OPEC production cut") == "commodity_shock"


def test_classify_geopolitical():
    assert classify_category("Military conflict escalates with new sanctions") == "geopolitical"


def test_classify_trade():
    assert classify_category("US announces new tariff on Chinese imports") == "trade_policy"


def test_classify_regulatory():
    assert classify_category("SEC launches antitrust investigation into tech giant") == "regulatory"


def test_classify_tech():
    assert classify_category("New AI breakthrough in autonomous robotics") == "tech_disruption"


def test_classify_currency():
    assert classify_category("Dollar strengthens as forex reserves climb") == "currency"


def test_classify_general():
    assert classify_category("random unrelated headline about nothing specific") == "general"


def test_classify_multiple_categories_picks_strongest():
    """When headline matches multiple categories, picks the one with most keyword hits."""
    headline = "Fed rate cut boosts earnings forecast as interest rate drops"
    cat = classify_category(headline)
    # "interest rate", "rate cut", "fed" -> monetary_policy (3)
    # "earnings", "forecast" -> earnings (2)
    assert cat == "monetary_policy"


def test_classify_empty():
    assert classify_category("") == "general"


# ---------------------------------------------------------------------------
# score_headline
# ---------------------------------------------------------------------------

def test_score_positive_sentiment():
    result = score_headline("Fed cuts rates", "Reuters", 0.8)
    # Positive sentiment -> most scores should be positive
    us_score = result["impacts"]["markets"]["US"]
    assert us_score > 0


def test_score_negative_sentiment():
    result = score_headline("Fed raises rates sharply", "Bloomberg", -0.7)
    us_score = result["impacts"]["markets"]["US"]
    assert us_score < 0


def test_score_zero_sentiment():
    result = score_headline("Nothing happened", "AP", 0.0)
    for dim in result["impacts"].values():
        for score in dim.values():
            assert score == 0.0


def test_score_within_bounds():
    """All scores must be within [-5, +5]."""
    result = score_headline("Massive rate hike by Fed", "Reuters", 1.0)
    for dim in result["impacts"].values():
        for score in dim.values():
            assert -5.0 <= score <= 5.0

    result2 = score_headline("Massive rate hike by Fed", "Reuters", -1.0)
    for dim in result2["impacts"].values():
        for score in dim.values():
            assert -5.0 <= score <= 5.0


def test_score_ticker_boost():
    """Ticker boost should amplify the relevant sector score by 1.5x."""
    base = score_headline("Tech earnings beat", "Reuters", 0.5)
    boosted = score_headline("Tech earnings beat", "Reuters", 0.5, tickers=["AAPL"])
    # AAPL -> Technology sector, should be boosted
    assert abs(boosted["impacts"]["sectors"]["Technology"]) >= abs(base["impacts"]["sectors"]["Technology"])


def test_score_magnitude_positive():
    result = score_headline("Major event", "Reuters", 0.5)
    assert result["magnitude"] > 0


def test_score_magnitude_is_sum_of_abs():
    result = score_headline("Fed cuts rates", "Reuters", 0.5)
    total = 0
    for dim in result["impacts"].values():
        for score in dim.values():
            total += abs(score)
    assert abs(result["magnitude"] - total) < 0.01


def test_score_nan_sentiment():
    """NaN sentiment should be treated as 0."""
    result = score_headline("Test headline", "Source", float('nan'))
    for dim in result["impacts"].values():
        for score in dim.values():
            assert score == 0.0


def test_score_returns_all_keys():
    result = score_headline("Test", "Source", 0.5)
    assert "headline" in result
    assert "source" in result
    assert "category" in result
    assert "sentiment" in result
    assert "impacts" in result
    assert "magnitude" in result
    assert "affected_tickers" in result


# ---------------------------------------------------------------------------
# aggregate_scores
# ---------------------------------------------------------------------------

def test_aggregate_single_story():
    scored = [score_headline("Fed cuts rates", "Reuters", 0.5)]
    agg = aggregate_scores(scored)
    assert agg["story_count"] == 1
    assert agg["net_impact"]["markets"]["US"] == scored[0]["impacts"]["markets"]["US"]


def test_aggregate_opposing_stories():
    """Two stories with opposite sentiment should partially cancel."""
    pos = score_headline("Fed cuts rates", "Reuters", 0.8)
    neg = score_headline("Fed raises rates", "Bloomberg", -0.8)
    agg = aggregate_scores([pos, neg])
    # Scores should be close to zero since they cancel
    us_score = agg["net_impact"]["markets"]["US"]
    assert abs(us_score) < 1.0


def test_aggregate_risk_on():
    scored = [score_headline("Great earnings across the board", "Reuters", 0.9)]
    agg = aggregate_scores(scored)
    assert agg["sentiment"] == "RISK-ON"
    assert agg["sentiment_score"] > 0


def test_aggregate_risk_off():
    scored = [score_headline("War escalates with new sanctions", "Reuters", -0.9)]
    agg = aggregate_scores(scored)
    assert agg["sentiment"] == "RISK-OFF"
    assert agg["sentiment_score"] < 0


def test_aggregate_top_stories_sorted():
    s1 = score_headline("Minor news", "AP", 0.1)
    s2 = score_headline("Fed raises rates massively", "Reuters", -0.9)
    s3 = score_headline("Moderate earnings beat", "Bloomberg", 0.5)
    agg = aggregate_scores([s1, s2, s3])
    mags = [s["magnitude"] for s in agg["top_stories"]]
    assert mags == sorted(mags, reverse=True)


def test_aggregate_empty():
    agg = aggregate_scores([])
    assert agg["sentiment"] == "NEUTRAL"
    assert agg["story_count"] == 0
    assert agg["sentiment_score"] == 0.0


# ---------------------------------------------------------------------------
# portfolio_impact
# ---------------------------------------------------------------------------

def test_portfolio_impact_single_holding():
    scored = [score_headline("Tech earnings beat estimates", "Reuters", 0.8, tickers=["AAPL"])]
    holdings = [{"ticker": "AAPL", "weight": 1.0}]
    result = portfolio_impact(scored, holdings)
    assert result["portfolio_impact_score"] != 0
    assert result["holdings_impact"][0]["ticker"] == "AAPL"
    assert result["holdings_impact"][0]["sector"] == "Technology"


def test_portfolio_impact_most_least_affected():
    scored = [score_headline("Tech innovation breakthrough", "Reuters", 0.8)]
    holdings = [
        {"ticker": "AAPL", "weight": 0.5},  # Technology
        {"ticker": "XOM", "weight": 0.5},    # Energy
    ]
    result = portfolio_impact(scored, holdings)
    assert result["most_affected"] is not None
    assert result["least_affected"] is not None
    assert abs(result["most_affected"]["impact"]) >= abs(result["least_affected"]["impact"])


def test_portfolio_impact_empty_holdings():
    scored = [score_headline("News", "Reuters", 0.5)]
    result = portfolio_impact(scored, [])
    assert result["portfolio_impact_score"] == 0.0


def test_portfolio_impact_empty_headlines():
    holdings = [{"ticker": "AAPL", "weight": 1.0}]
    result = portfolio_impact([], holdings)
    assert result["portfolio_impact_score"] == 0.0


# ---------------------------------------------------------------------------
# TICKER_SECTOR_MAP
# ---------------------------------------------------------------------------

def test_known_tickers():
    assert TICKER_SECTOR_MAP["AAPL"] == "Technology"
    assert TICKER_SECTOR_MAP["JPM"] == "Banking"
    assert TICKER_SECTOR_MAP["XOM"] == "Energy"
    assert TICKER_SECTOR_MAP["TSLA"] == "Auto"


def test_unknown_ticker_defaults():
    """Unknown ticker not in map should get 'Other' from portfolio_impact."""
    scored = [score_headline("News", "Reuters", 0.5)]
    holdings = [{"ticker": "ZZZZ", "weight": 1.0}]
    result = portfolio_impact(scored, holdings)
    assert result["holdings_impact"][0]["sector"] == "Other"
