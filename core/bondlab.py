"""
Fixed Income Analytics Engine.
Bond pricing, duration, convexity, yield curve analysis, and spread metrics.

Key formulas:
  Bond Price = sum [C / (1 + y/f)^t] + [F / (1 + y/f)^n]
  Macaulay Duration = sum [t * PV(CF_t)] / Price
  Modified Duration = Macaulay / (1 + y/f)
  Convexity = sum [t*(t+1) * PV(CF_t)] / (Price * (1+y/f)^2)
"""
import math
import json
import os
import numpy as np
import urllib.request
from datetime import datetime, timedelta
from core.sanitize import safe_divide
from core.cache import get_cached_metric, store_metric


# ---------------------------------------------------------------------------
# Bond Pricing
# ---------------------------------------------------------------------------

def price_bond(face: float = 1000, coupon_rate: float = 0.05, ytm: float = 0.04,
               years: float = 10, frequency: int = 2) -> dict:
    """Price a bond and compute all related metrics."""
    periods = int(years * frequency)
    coupon = face * coupon_rate / frequency
    r = ytm / frequency

    if r == 0:
        pv = coupon * periods + face
    else:
        pv = 0.0
        for t in range(1, periods + 1):
            pv += coupon / (1 + r) ** t
        pv += face / (1 + r) ** periods

    annual_coupon = face * coupon_rate
    current_yield = safe_divide(annual_coupon, pv)

    if abs(pv - face) < 0.01:
        pd_label = "Par"
    elif pv > face:
        pd_label = "Premium"
    else:
        pd_label = "Discount"

    return {
        "price": round(pv, 4),
        "face": face,
        "coupon_rate": coupon_rate,
        "ytm": ytm,
        "years": years,
        "frequency": frequency,
        "coupon_payment": round(coupon, 4),
        "annual_coupon": round(annual_coupon, 4),
        "current_yield": round(current_yield, 6),
        "premium_discount": pd_label,
        "accrued_interest": 0.0,
    }


# ---------------------------------------------------------------------------
# Duration & Convexity
# ---------------------------------------------------------------------------

def macaulay_duration(face: float = 1000, coupon_rate: float = 0.05, ytm: float = 0.04,
                      years: float = 10, frequency: int = 2) -> float:
    """Compute Macaulay Duration in years."""
    periods = int(years * frequency)
    coupon = face * coupon_rate / frequency
    r = ytm / frequency

    if r == 0:
        # Special case: no discounting
        total_pv = coupon * periods + face
        if total_pv == 0:
            return 0.0
        weighted = sum(t * coupon for t in range(1, periods + 1)) + periods * face
        return safe_divide(weighted, total_pv) / frequency

    price = 0.0
    weighted_pv = 0.0
    for t in range(1, periods + 1):
        pv_cf = coupon / (1 + r) ** t
        price += pv_cf
        weighted_pv += t * pv_cf

    pv_face = face / (1 + r) ** periods
    price += pv_face
    weighted_pv += periods * pv_face

    return safe_divide(weighted_pv, price) / frequency


def modified_duration(face: float = 1000, coupon_rate: float = 0.05, ytm: float = 0.04,
                      years: float = 10, frequency: int = 2) -> float:
    """Modified Duration = Macaulay Duration / (1 + ytm/frequency)."""
    mac = macaulay_duration(face, coupon_rate, ytm, years, frequency)
    return safe_divide(mac, 1 + ytm / frequency)


def convexity(face: float = 1000, coupon_rate: float = 0.05, ytm: float = 0.04,
              years: float = 10, frequency: int = 2) -> float:
    """Compute bond convexity in years."""
    periods = int(years * frequency)
    coupon = face * coupon_rate / frequency
    r = ytm / frequency

    bond_info = price_bond(face, coupon_rate, ytm, years, frequency)
    price = bond_info["price"]
    if price == 0:
        return 0.0

    if r == 0:
        # No discounting
        total = sum(t * (t + 1) * coupon for t in range(1, periods + 1))
        total += periods * (periods + 1) * face
        return safe_divide(total, price) / (frequency ** 2)

    total = 0.0
    for t in range(1, periods + 1):
        pv_cf = coupon / (1 + r) ** t
        total += t * (t + 1) * pv_cf

    pv_face = face / (1 + r) ** periods
    total += periods * (periods + 1) * pv_face

    return safe_divide(total, price * (1 + r) ** 2) / (frequency ** 2)


def price_change_estimate(mod_dur: float, convex: float, yield_change: float) -> dict:
    """Estimate bond price change using duration and convexity."""
    dur_effect = -mod_dur * yield_change * 100
    conv_effect = 0.5 * convex * (yield_change ** 2) * 100
    total = dur_effect + conv_effect

    return {
        "duration_effect": round(dur_effect, 4),
        "convexity_effect": round(conv_effect, 4),
        "total_change_pct": round(total, 4),
        "yield_change_bps": round(yield_change * 10000, 1),
    }


def full_bond_analysis(face: float = 1000, coupon_rate: float = 0.05, ytm: float = 0.04,
                       years: float = 10, frequency: int = 2) -> dict:
    """Complete bond analysis."""
    pricing = price_bond(face, coupon_rate, ytm, years, frequency)
    mac_dur = macaulay_duration(face, coupon_rate, ytm, years, frequency)
    mod_dur = modified_duration(face, coupon_rate, ytm, years, frequency)
    conv = convexity(face, coupon_rate, ytm, years, frequency)
    dollar_dur = mod_dur * pricing["price"] / 100

    scenarios = {}
    for bps, label in [(-100, "-100bps"), (-50, "-50bps"), (50, "+50bps"), (100, "+100bps")]:
        dy = bps / 10000
        est = price_change_estimate(mod_dur, conv, dy)
        new_price = pricing["price"] * (1 + est["total_change_pct"] / 100)
        scenarios[label] = {
            "yield_change": dy,
            "price_change_pct": est["total_change_pct"],
            "new_price": round(new_price, 2),
        }

    return {
        **pricing,
        "macaulay_duration": round(mac_dur, 4),
        "modified_duration": round(mod_dur, 4),
        "convexity": round(conv, 4),
        "dollar_duration": round(dollar_dur, 4),
        "scenarios": scenarios,
    }


# ---------------------------------------------------------------------------
# Yield Curve
# ---------------------------------------------------------------------------

FRED_SERIES = {
    "3M": "DGS3MO", "6M": "DGS6MO", "1Y": "DGS1", "2Y": "DGS2",
    "3Y": "DGS3", "5Y": "DGS5", "7Y": "DGS7", "10Y": "DGS10",
    "20Y": "DGS20", "30Y": "DGS30",
}

MATURITY_YEARS = {
    "3M": 0.25, "6M": 0.5, "1Y": 1, "2Y": 2, "3Y": 3,
    "5Y": 5, "7Y": 7, "10Y": 10, "20Y": 20, "30Y": 30,
}

# Fallback yields (reasonable recent approximation)
_FALLBACK_YIELDS = {
    "3M": 0.0435, "6M": 0.0440, "1Y": 0.0420, "2Y": 0.0400,
    "3Y": 0.0395, "5Y": 0.0390, "7Y": 0.0395, "10Y": 0.0400,
    "20Y": 0.0430, "30Y": 0.0430,
}


def get_yield_curve() -> dict:
    """Fetch current US Treasury yield curve."""
    cached = get_cached_metric("yield_curve")
    if cached:
        return cached

    labels = list(FRED_SERIES.keys())
    maturities = [MATURITY_YEARS[l] for l in labels]
    yields_dict = {}
    source = "fallback"

    # Try FRED
    fred_key = os.environ.get("FRED_API_KEY", "")
    if fred_key:
        try:
            yields_dict, source = _fetch_fred_yields(fred_key, labels), "fred"
        except Exception:
            yields_dict = {}

    # Try yfinance
    if not yields_dict:
        try:
            yields_dict, source = _fetch_yf_yields(), "yfinance"
        except Exception:
            yields_dict = {}

    # Fallback
    if not yields_dict:
        yields_dict = dict(_FALLBACK_YIELDS)
        source = "fallback"

    yields = [yields_dict.get(l, _FALLBACK_YIELDS.get(l, 0.04)) for l in labels]

    y2 = yields_dict.get("2Y", yields[labels.index("2Y")] if "2Y" in labels else 0.04)
    y10 = yields_dict.get("10Y", yields[labels.index("10Y")] if "10Y" in labels else 0.04)
    y3m = yields_dict.get("3M", yields[0])
    slope_2s10s = y10 - y2
    slope_3m10y = y10 - y3m

    result = {
        "date": datetime.today().strftime("%Y-%m-%d"),
        "maturities": maturities,
        "yields": [round(y, 6) for y in yields],
        "labels": labels,
        "slope_2s10s": round(slope_2s10s, 6),
        "slope_3m10y": round(slope_3m10y, 6),
        "inverted": y2 > y10,
        "source": source,
    }

    store_metric("yield_curve", result, ttl_hours=4)
    return result


def _fetch_fred_yields(api_key: str, labels: list) -> dict:
    """Fetch yields from FRED API."""
    yields = {}
    for label in labels:
        series_id = FRED_SERIES.get(label)
        if not series_id:
            continue
        try:
            url = (f"https://api.stlouisfed.org/fred/series/observations?"
                   f"series_id={series_id}&api_key={api_key}&file_type=json"
                   f"&sort_order=desc&limit=5")
            req = urllib.request.Request(url, headers={"User-Agent": "AlphaVault/1.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            for obs in data.get("observations", []):
                val = obs.get("value", ".")
                if val != ".":
                    yields[label] = float(val) / 100  # FRED gives percentage
                    break
        except Exception:
            continue
    return yields


def _fetch_yf_yields() -> dict:
    """Fetch yields from yfinance treasury tickers."""
    import yfinance as yf
    mapping = {"10Y": "^TNX", "30Y": "^TYX", "3M": "^IRX", "5Y": "^FVX"}
    yields = {}
    for label, ticker in mapping.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                yields[label] = float(hist["Close"].iloc[-1]) / 100
        except Exception:
            continue
    return yields


def interpolate_yield(maturities: list, yields: list, target_maturity: float) -> float:
    """Interpolate yield for any maturity using linear interpolation."""
    return float(np.interp(target_maturity, maturities, yields))


def get_historical_curves(periods: list = None) -> dict:
    """Fetch yield curves from historical dates. V1: returns current curve only."""
    return {"current": get_yield_curve()}


def yield_curve_slope() -> dict:
    """Compute yield curve slope metrics."""
    curve = get_yield_curve()
    slope = curve.get("slope_2s10s", 0)
    slope_3m10y = curve.get("slope_3m10y", 0)
    inverted = curve.get("inverted", False)

    if inverted:
        interp = "Inverted: historically precedes recessions"
    elif abs(slope) < 0.002:
        interp = "Flat: uncertain outlook, potential slowdown"
    else:
        interp = "Normal: positive slope suggests economic growth expected"

    return {
        "slope_2s10s": slope,
        "slope_3m10y": slope_3m10y,
        "inverted": inverted,
        "interpretation": interp,
    }
