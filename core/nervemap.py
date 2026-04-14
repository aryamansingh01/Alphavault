"""
Rules-based market impact scoring engine.
Maps news headlines to impact scores across markets, sectors, and asset classes.
Uses sentiment scores + category-based weight maps.
Zero-cost alternative to LLM-powered analysis.
"""
import numpy as np
import re
from core.sanitize import safe_divide

# ---------------------------------------------------------------------------
# Impact Weight Configuration
# ---------------------------------------------------------------------------

SENSITIVITY_SCALE = 5.0  # max impact magnitude

IMPACT_WEIGHTS = {
    "monetary_policy": {
        "markets": {"US": 0.9, "India": 0.6, "China": 0.5, "EU": 0.7, "Japan": 0.5, "UK": 0.6, "EM": 0.7, "Middle_East": 0.3},
        "sectors": {"Banking": 0.9, "Technology": 0.5, "Pharma": 0.2, "Energy": 0.4, "Metals": 0.3, "Real_Estate": 0.8, "FMCG": 0.2, "Auto": 0.5, "Telecom": 0.3, "Infrastructure": 0.6},
        "assets": {"Equities": 0.8, "Bonds": 0.95, "Gold": 0.6, "Crude_Oil": 0.4, "USD_Index": 0.85, "Crypto": 0.5, "INR_USD": 0.6, "VIX": 0.7},
    },
    "earnings": {
        "markets": {"US": 0.7, "India": 0.3, "China": 0.3, "EU": 0.4, "Japan": 0.3, "UK": 0.3, "EM": 0.2, "Middle_East": 0.1},
        "sectors": {"Banking": 0.5, "Technology": 0.8, "Pharma": 0.6, "Energy": 0.5, "Metals": 0.3, "Real_Estate": 0.3, "FMCG": 0.5, "Auto": 0.5, "Telecom": 0.4, "Infrastructure": 0.3},
        "assets": {"Equities": 0.9, "Bonds": 0.2, "Gold": 0.1, "Crude_Oil": 0.1, "USD_Index": 0.2, "Crypto": 0.1, "INR_USD": 0.1, "VIX": 0.4},
    },
    "geopolitical": {
        "markets": {"US": 0.6, "India": 0.5, "China": 0.6, "EU": 0.7, "Japan": 0.4, "UK": 0.5, "EM": 0.8, "Middle_East": 0.9},
        "sectors": {"Banking": 0.5, "Technology": 0.4, "Pharma": 0.3, "Energy": 0.8, "Metals": 0.6, "Real_Estate": 0.3, "FMCG": 0.4, "Auto": 0.4, "Telecom": 0.3, "Infrastructure": 0.5},
        "assets": {"Equities": 0.6, "Bonds": 0.5, "Gold": 0.9, "Crude_Oil": 0.85, "USD_Index": 0.5, "Crypto": 0.4, "INR_USD": 0.5, "VIX": 0.8},
    },
    "commodity_shock": {
        "markets": {"US": 0.5, "India": 0.7, "China": 0.7, "EU": 0.6, "Japan": 0.6, "UK": 0.4, "EM": 0.8, "Middle_East": 0.9},
        "sectors": {"Banking": 0.2, "Technology": 0.2, "Pharma": 0.3, "Energy": 0.95, "Metals": 0.9, "Real_Estate": 0.2, "FMCG": 0.5, "Auto": 0.6, "Telecom": 0.1, "Infrastructure": 0.5},
        "assets": {"Equities": 0.5, "Bonds": 0.3, "Gold": 0.8, "Crude_Oil": 0.95, "USD_Index": 0.4, "Crypto": 0.3, "INR_USD": 0.6, "VIX": 0.5},
    },
    "trade_policy": {
        "markets": {"US": 0.8, "India": 0.6, "China": 0.9, "EU": 0.7, "Japan": 0.5, "UK": 0.5, "EM": 0.7, "Middle_East": 0.3},
        "sectors": {"Banking": 0.3, "Technology": 0.7, "Pharma": 0.4, "Energy": 0.4, "Metals": 0.6, "Real_Estate": 0.2, "FMCG": 0.5, "Auto": 0.8, "Telecom": 0.3, "Infrastructure": 0.4},
        "assets": {"Equities": 0.7, "Bonds": 0.3, "Gold": 0.4, "Crude_Oil": 0.4, "USD_Index": 0.7, "Crypto": 0.3, "INR_USD": 0.5, "VIX": 0.5},
    },
    "regulatory": {
        "markets": {"US": 0.7, "India": 0.5, "China": 0.6, "EU": 0.7, "Japan": 0.4, "UK": 0.5, "EM": 0.4, "Middle_East": 0.3},
        "sectors": {"Banking": 0.8, "Technology": 0.7, "Pharma": 0.7, "Energy": 0.5, "Metals": 0.3, "Real_Estate": 0.4, "FMCG": 0.3, "Auto": 0.4, "Telecom": 0.5, "Infrastructure": 0.4},
        "assets": {"Equities": 0.6, "Bonds": 0.3, "Gold": 0.2, "Crude_Oil": 0.3, "USD_Index": 0.3, "Crypto": 0.8, "INR_USD": 0.2, "VIX": 0.4},
    },
    "tech_disruption": {
        "markets": {"US": 0.8, "India": 0.5, "China": 0.7, "EU": 0.5, "Japan": 0.5, "UK": 0.4, "EM": 0.4, "Middle_East": 0.2},
        "sectors": {"Banking": 0.4, "Technology": 0.95, "Pharma": 0.3, "Energy": 0.3, "Metals": 0.2, "Real_Estate": 0.2, "FMCG": 0.3, "Auto": 0.6, "Telecom": 0.5, "Infrastructure": 0.3},
        "assets": {"Equities": 0.7, "Bonds": 0.2, "Gold": 0.1, "Crude_Oil": 0.2, "USD_Index": 0.3, "Crypto": 0.6, "INR_USD": 0.2, "VIX": 0.4},
    },
    "currency": {
        "markets": {"US": 0.7, "India": 0.8, "China": 0.6, "EU": 0.7, "Japan": 0.7, "UK": 0.6, "EM": 0.8, "Middle_East": 0.4},
        "sectors": {"Banking": 0.6, "Technology": 0.4, "Pharma": 0.5, "Energy": 0.4, "Metals": 0.4, "Real_Estate": 0.3, "FMCG": 0.4, "Auto": 0.5, "Telecom": 0.3, "Infrastructure": 0.3},
        "assets": {"Equities": 0.5, "Bonds": 0.5, "Gold": 0.7, "Crude_Oil": 0.5, "USD_Index": 0.95, "Crypto": 0.4, "INR_USD": 0.9, "VIX": 0.4},
    },
    "general": {
        "markets": {"US": 0.3, "India": 0.2, "China": 0.2, "EU": 0.2, "Japan": 0.2, "UK": 0.2, "EM": 0.2, "Middle_East": 0.1},
        "sectors": {"Banking": 0.2, "Technology": 0.2, "Pharma": 0.2, "Energy": 0.2, "Metals": 0.2, "Real_Estate": 0.2, "FMCG": 0.2, "Auto": 0.2, "Telecom": 0.2, "Infrastructure": 0.2},
        "assets": {"Equities": 0.3, "Bonds": 0.2, "Gold": 0.1, "Crude_Oil": 0.1, "USD_Index": 0.1, "Crypto": 0.1, "INR_USD": 0.1, "VIX": 0.2},
    },
}

# ---------------------------------------------------------------------------
# Ticker-to-Sector Map
# ---------------------------------------------------------------------------

TICKER_SECTOR_MAP = {
    "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology", "GOOG": "Technology",
    "META": "Technology", "NVDA": "Technology", "AMD": "Technology", "INTC": "Technology",
    "CRM": "Technology", "ADBE": "Technology", "ORCL": "Technology", "CSCO": "Technology",
    "AMZN": "Technology", "TSLA": "Auto", "NFLX": "Technology",
    "JPM": "Banking", "BAC": "Banking", "GS": "Banking", "MS": "Banking", "WFC": "Banking", "C": "Banking",
    "JNJ": "Pharma", "PFE": "Pharma", "UNH": "Pharma", "MRK": "Pharma", "ABBV": "Pharma", "LLY": "Pharma",
    "XOM": "Energy", "CVX": "Energy", "COP": "Energy", "SLB": "Energy", "EOG": "Energy",
    "CAT": "Infrastructure", "DE": "Infrastructure", "HON": "Infrastructure",
    "PG": "FMCG", "KO": "FMCG", "PEP": "FMCG", "WMT": "FMCG", "COST": "FMCG",
    "HD": "Real_Estate", "LOW": "Real_Estate",
    "T": "Telecom", "VZ": "Telecom", "TMUS": "Telecom",
    "F": "Auto", "GM": "Auto", "TM": "Auto",
    "NEM": "Metals", "FCX": "Metals", "AA": "Metals",
    "DIS": "Technology", "V": "Banking", "MA": "Banking",
    "SPY": "Diversified", "QQQ": "Technology", "DIA": "Diversified", "VTI": "Diversified",
    "GLD": "Metals", "SLV": "Metals", "USO": "Energy",
    "BND": "Bonds", "TLT": "Bonds", "AGG": "Bonds", "IBIT": "Crypto", "BTC-USD": "Crypto", "ETH-USD": "Crypto",
    "SCHD": "Diversified", "VYM": "Diversified", "VXUS": "Diversified", "VEA": "Diversified",
    "JEPI": "Diversified", "IWM": "Diversified", "EFA": "Diversified", "ETHA": "Crypto",
    "O": "Real_Estate", "AMT": "Real_Estate",
}

# ---------------------------------------------------------------------------
# Category Classification
# ---------------------------------------------------------------------------

CATEGORY_KEYWORDS = {
    "monetary_policy": ["fed", "federal reserve", "interest rate", "rate hike", "rate cut",
                        "monetary policy", "fomc", "central bank", "rbi", "ecb", "boj",
                        "quantitative", "taper", "dovish", "hawkish", "basis points", "inflation target"],
    "earnings": ["earnings", "revenue", "profit", "eps", "quarterly results", "beat estimates",
                 "missed estimates", "guidance", "forecast", "q1", "q2", "q3", "q4",
                 "annual report", "fiscal year"],
    "geopolitical": ["war", "conflict", "sanctions", "military", "geopolitical", "tension",
                     "invasion", "treaty", "nuclear", "missile", "nato", "defense", "coup",
                     "protest", "uprising"],
    "commodity_shock": ["oil price", "crude oil", "opec", "natural gas", "commodity",
                        "supply shock", "shortage", "surplus", "barrel", "mining", "crop",
                        "wheat", "corn", "lithium", "copper price"],
    "trade_policy": ["tariff", "trade war", "trade deal", "import duty", "export ban",
                     "trade deficit", "trade surplus", "wto", "free trade", "trade agreement",
                     "customs", "trade restriction"],
    "regulatory": ["regulation", "sec", "compliance", "antitrust", "lawsuit", "fine",
                   "penalty", "ban", "approve", "fda", "epa", "ftc", "legislation",
                   "bill passed", "executive order"],
    "tech_disruption": ["ai ", "artificial intelligence", "breakthrough", "innovation",
                        "disruption", "autonomous", "quantum", "robotics", "machine learning",
                        "blockchain", "patent", "launch", "new product"],
    "currency": ["dollar", "forex", "exchange rate", "currency", "depreciation",
                 "appreciation", "yen", "euro", "rupee", "yuan", "sterling", "devaluation",
                 "forex reserve"],
}


def classify_category(headline: str, source: str = "") -> str:
    """Classify a news headline into a category using keyword matching.
    Case-insensitive. Returns the category with the most keyword matches.
    If no keywords match, returns 'general'.
    If tied, prefer the first match in CATEGORY_KEYWORDS order."""
    if not headline:
        return "general"

    text = (headline + " " + source).lower()
    best_cat = "general"
    best_count = 0

    for category, keywords in CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text)
        if count > best_count:
            best_count = count
            best_cat = category

    return best_cat


# ---------------------------------------------------------------------------
# Keyword-based sentiment estimation
# ---------------------------------------------------------------------------

_POSITIVE_WORDS = [
    "surge", "surges", "rally", "rallies", "gain", "gains", "jump", "jumps",
    "soar", "soars", "rise", "rises", "beat", "beats", "record", "high",
    "boost", "upgrade", "upgrades", "bullish", "optimism", "recovery",
    "profit", "growth", "strong", "outperform", "positive", "green",
    "approval", "approves", "deal", "breakthrough", "innovation", "launch",
    "dividend", "buyback", "expansion", "exceed", "exceeds", "boom",
    "upbeat", "robust", "momentum", "accelerate", "rebound", "up",
]

_NEGATIVE_WORDS = [
    "crash", "crashes", "plunge", "plunges", "drop", "drops", "fall", "falls",
    "decline", "declines", "loss", "losses", "miss", "misses", "low",
    "slump", "cut", "cuts", "downgrade", "downgrades", "bearish", "fear",
    "recession", "crisis", "default", "bankruptcy", "layoff", "layoffs",
    "weak", "underperform", "negative", "red", "sell-off", "selloff",
    "warning", "warns", "risk", "threat", "tariff", "sanctions", "war",
    "inflation", "collapse", "sink", "sinks", "tumble", "down", "worst",
    "penalty", "fine", "lawsuit", "investigation", "probe",
]


def estimate_sentiment(headline: str) -> float:
    """Estimate sentiment from headline keywords. Returns float in [-1.0, +1.0]."""
    if not headline:
        return 0.0
    text = headline.lower()
    pos = sum(1 for w in _POSITIVE_WORDS if w in text)
    neg = sum(1 for w in _NEGATIVE_WORDS if w in text)
    total = pos + neg
    if total == 0:
        return 0.0
    raw = (pos - neg) / total  # range [-1, 1]
    # Scale by confidence: more keyword matches = more confident
    confidence = min(total / 3.0, 1.0)
    return round(raw * confidence, 3)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _clip(val: float, lo: float = -5.0, hi: float = 5.0) -> float:
    return max(lo, min(hi, val))


def score_headline(headline: str, source: str, sentiment: float, tickers: list = None) -> dict:
    """Score a single headline's impact across all dimensions.
    sentiment: float from -1.0 to +1.0. NaN treated as 0.
    If sentiment is 0.0 (default/missing), estimate from headline keywords."""
    if sentiment is None or (isinstance(sentiment, float) and sentiment != sentiment):
        sentiment = 0.0

    # If no sentiment provided, estimate from keywords
    if sentiment == 0.0 and headline:
        sentiment = estimate_sentiment(headline)

    category = classify_category(headline, source)
    weights = IMPACT_WEIGHTS.get(category, IMPACT_WEIGHTS["general"])

    impacts = {}
    magnitude = 0.0

    for dimension in ("markets", "sectors", "assets"):
        dim_weights = weights.get(dimension, {})
        dim_scores = {}
        for entity, w in dim_weights.items():
            score = _clip(sentiment * w * SENSITIVITY_SCALE)
            dim_scores[entity] = round(score, 4)
            magnitude += abs(score)
        impacts[dimension] = dim_scores

    # Ticker boost: amplify the relevant sector by 1.5x
    affected_tickers = []
    if tickers:
        boosted_sectors = set()
        for t in tickers:
            t_upper = t.upper()
            affected_tickers.append(t_upper)
            sector = TICKER_SECTOR_MAP.get(t_upper)
            if sector and sector in impacts.get("sectors", {}) and sector not in boosted_sectors:
                old = impacts["sectors"][sector]
                impacts["sectors"][sector] = _clip(old * 1.5)
                magnitude += abs(impacts["sectors"][sector]) - abs(old)
                boosted_sectors.add(sector)

    return {
        "headline": headline,
        "source": source,
        "category": category,
        "sentiment": sentiment,
        "impacts": impacts,
        "magnitude": round(magnitude, 4),
        "affected_tickers": affected_tickers,
    }


def aggregate_scores(scored_headlines: list) -> dict:
    """Aggregate impact scores across multiple headlines.
    Sums scores per entity, clips to [-5, +5], determines overall sentiment."""
    if not scored_headlines:
        return {
            "net_impact": {"markets": {}, "sectors": {}, "assets": {}},
            "sentiment": "NEUTRAL",
            "sentiment_score": 0.0,
            "story_count": 0,
            "top_stories": [],
        }

    net = {"markets": {}, "sectors": {}, "assets": {}}

    for sh in scored_headlines:
        for dimension in ("markets", "sectors", "assets"):
            for entity, score in sh.get("impacts", {}).get(dimension, {}).items():
                net[dimension][entity] = net[dimension].get(entity, 0.0) + score

    # Clip aggregated scores
    for dimension in net:
        for entity in net[dimension]:
            net[dimension][entity] = _clip(net[dimension][entity])

    # Overall sentiment score
    total = sum(v for dim in net.values() for v in dim.values())

    if total > 0.01:
        sentiment = "RISK-ON"
    elif total < -0.01:
        sentiment = "RISK-OFF"
    else:
        sentiment = "NEUTRAL"

    # Sort by magnitude descending
    top_stories = sorted(scored_headlines, key=lambda s: s.get("magnitude", 0), reverse=True)

    return {
        "net_impact": net,
        "sentiment": sentiment,
        "sentiment_score": round(total, 4),
        "story_count": len(scored_headlines),
        "top_stories": top_stories,
    }


def _get_sector_score(ticker: str, sector_impacts: dict) -> float:
    """Get the impact score for a ticker's sector.
    For diversified/broad-market ETFs, use the average of all sector scores.
    For bonds, use a low sensitivity proxy."""
    sector = TICKER_SECTOR_MAP.get(ticker, "Other")
    # Direct match
    if sector in sector_impacts:
        return sector_impacts[sector]
    # Diversified ETFs (SPY, VTI, DIA) or unknown — use average of all sector impacts
    if sector in ("Diversified", "Other"):
        vals = [v for v in sector_impacts.values() if v != 0]
        return sum(vals) / len(vals) if vals else 0.0
    # Bonds — low equity sensitivity, use ~20% of average market impact
    if sector == "Bonds":
        vals = [v for v in sector_impacts.values() if v != 0]
        return (sum(vals) / len(vals) * 0.2) if vals else 0.0
    # Crypto — use Technology as closest proxy
    if sector == "Crypto":
        return sector_impacts.get("Technology", 0.0) * 0.8
    return 0.0


def portfolio_impact(scored_headlines: list, holdings: list) -> dict:
    """Cross-reference news impact with user's actual portfolio.
    holdings: list of dicts with at least {'ticker': str, 'weight': float}"""
    if not holdings or not scored_headlines:
        return {
            "portfolio_impact_score": 0.0,
            "holdings_impact": [],
            "most_affected": None,
            "least_affected": None,
        }

    agg = aggregate_scores(scored_headlines)
    sector_impacts = agg["net_impact"].get("sectors", {})

    holdings_impact = []
    for h in holdings:
        ticker = h.get("ticker", "").upper()
        weight = h.get("weight", 0.0)
        sector = TICKER_SECTOR_MAP.get(ticker, "Other")
        sector_score = _get_sector_score(ticker, sector_impacts)
        contribution = weight * sector_score

        holdings_impact.append({
            "ticker": ticker,
            "sector": sector,
            "sector_impact": round(sector_score, 4),
            "portfolio_contribution": round(contribution, 4),
        })

    total_impact = sum(h["portfolio_contribution"] for h in holdings_impact)

    most = max(holdings_impact, key=lambda x: abs(x["portfolio_contribution"]))
    least = min(holdings_impact, key=lambda x: abs(x["portfolio_contribution"]))

    return {
        "portfolio_impact_score": round(total_impact, 4),
        "holdings_impact": holdings_impact,
        "most_affected": {"ticker": most["ticker"], "impact": most["portfolio_contribution"]},
        "least_affected": {"ticker": least["ticker"], "impact": least["portfolio_contribution"]},
    }
