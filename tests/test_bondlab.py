"""Tests for core/bondlab.py — Fixed Income Analytics."""
import os
import math
import numpy as np
import pytest

import core.cache as cache_module

_orig_dir = cache_module.DB_DIR
_orig_path = cache_module.DB_PATH


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path):
    cache_module.DB_DIR = str(tmp_path)
    cache_module.DB_PATH = os.path.join(str(tmp_path), "cache.db")
    yield
    cache_module.DB_DIR = _orig_dir
    cache_module.DB_PATH = _orig_path


from core.bondlab import (
    price_bond, macaulay_duration, modified_duration, convexity,
    price_change_estimate, full_bond_analysis,
    get_yield_curve, interpolate_yield, yield_curve_slope,
)


# ---------------------------------------------------------------------------
# Bond Pricing
# ---------------------------------------------------------------------------

def test_par_bond():
    """coupon_rate == ytm -> price == face."""
    result = price_bond(face=1000, coupon_rate=0.05, ytm=0.05, years=10, frequency=2)
    assert abs(result["price"] - 1000) < 0.01


def test_premium_bond():
    """coupon_rate > ytm -> price > face."""
    result = price_bond(face=1000, coupon_rate=0.06, ytm=0.04, years=10, frequency=2)
    assert result["price"] > 1000
    assert result["premium_discount"] == "Premium"


def test_discount_bond():
    """coupon_rate < ytm -> price < face."""
    result = price_bond(face=1000, coupon_rate=0.03, ytm=0.05, years=10, frequency=2)
    assert result["price"] < 1000
    assert result["premium_discount"] == "Discount"


def test_zero_coupon():
    """coupon=0 -> price = face / (1+r)^n."""
    result = price_bond(face=1000, coupon_rate=0.0, ytm=0.05, years=10, frequency=2)
    expected = 1000 / (1.025 ** 20)
    assert abs(result["price"] - expected) < 0.01


def test_known_textbook_price():
    """face=1000, coupon=5%, ytm=4%, 10yr semi-annual.
    C=25, r=0.02, n=20. Price = 25*annuity(0.02,20) + 1000/(1.02)^20"""
    r = 0.02
    n = 20
    annuity = (1 - (1 + r) ** -n) / r
    expected = 25 * annuity + 1000 / (1 + r) ** n
    result = price_bond(1000, 0.05, 0.04, 10, 2)
    assert abs(result["price"] - expected) < 0.01


def test_current_yield():
    result = price_bond(1000, 0.05, 0.04, 10, 2)
    expected_cy = 50.0 / result["price"]
    assert abs(result["current_yield"] - expected_cy) < 0.0001


def test_price_bond_annual():
    """Annual frequency should work."""
    result = price_bond(1000, 0.05, 0.05, 5, 1)
    assert abs(result["price"] - 1000) < 0.01


def test_price_bond_quarterly():
    """Quarterly frequency."""
    result = price_bond(1000, 0.06, 0.06, 5, 4)
    assert abs(result["price"] - 1000) < 0.01


# ---------------------------------------------------------------------------
# Duration
# ---------------------------------------------------------------------------

def test_zero_coupon_duration():
    """Zero-coupon Macaulay duration = years to maturity."""
    dur = macaulay_duration(1000, 0.0, 0.05, 5, 2)
    assert abs(dur - 5.0) < 0.01


def test_duration_less_than_maturity():
    """Coupon-bearing bond duration < maturity."""
    dur = macaulay_duration(1000, 0.05, 0.04, 10, 2)
    assert dur < 10.0


def test_higher_coupon_lower_duration():
    dur_low = macaulay_duration(1000, 0.02, 0.04, 10, 2)
    dur_high = macaulay_duration(1000, 0.08, 0.04, 10, 2)
    assert dur_high < dur_low


def test_longer_maturity_higher_duration():
    dur_5 = macaulay_duration(1000, 0.05, 0.04, 5, 2)
    dur_20 = macaulay_duration(1000, 0.05, 0.04, 20, 2)
    assert dur_20 > dur_5


def test_modified_less_than_macaulay():
    mac = macaulay_duration(1000, 0.05, 0.04, 10, 2)
    mod = modified_duration(1000, 0.05, 0.04, 10, 2)
    assert mod < mac


def test_modified_duration_formula():
    mac = macaulay_duration(1000, 0.05, 0.04, 10, 2)
    mod = modified_duration(1000, 0.05, 0.04, 10, 2)
    expected = mac / (1 + 0.04 / 2)
    assert abs(mod - expected) < 0.001


def test_duration_known_value():
    """Verify duration for a simple 2-year annual bond."""
    # face=1000, coupon=10%, ytm=10%, 2yr annual
    # CF: year1=100, year2=1100
    # PV1 = 100/1.10 = 90.909, PV2 = 1100/1.21 = 909.091
    # Price = 1000 (par bond)
    # Mac Dur = (1*90.909 + 2*909.091) / 1000 = 1909.091/1000 = 1.909
    dur = macaulay_duration(1000, 0.10, 0.10, 2, 1)
    assert abs(dur - 1.909) < 0.01


# ---------------------------------------------------------------------------
# Convexity
# ---------------------------------------------------------------------------

def test_convexity_positive():
    conv = convexity(1000, 0.05, 0.04, 10, 2)
    assert conv > 0


def test_higher_maturity_higher_convexity():
    c5 = convexity(1000, 0.05, 0.04, 5, 2)
    c20 = convexity(1000, 0.05, 0.04, 20, 2)
    assert c20 > c5


def test_zero_coupon_highest_convexity():
    """Zero-coupon should have highest convexity for given maturity."""
    c_zero = convexity(1000, 0.0, 0.04, 10, 2)
    c_coupon = convexity(1000, 0.05, 0.04, 10, 2)
    assert c_zero > c_coupon


# ---------------------------------------------------------------------------
# Price Change Estimate
# ---------------------------------------------------------------------------

def test_price_change_duration_only():
    """Small yield change: duration estimate should be close to actual."""
    mod = modified_duration(1000, 0.05, 0.04, 10, 2)
    conv = convexity(1000, 0.05, 0.04, 10, 2)

    # Actual prices
    p0 = price_bond(1000, 0.05, 0.04, 10, 2)["price"]
    p1 = price_bond(1000, 0.05, 0.0401, 10, 2)["price"]
    actual_pct = (p1 - p0) / p0 * 100

    est = price_change_estimate(mod, conv, 0.0001)
    # Should be close for 1bp change
    assert abs(est["total_change_pct"] - actual_pct) < 0.01


def test_convexity_effect_always_positive():
    mod = 7.0
    conv = 60.0
    est_up = price_change_estimate(mod, conv, 0.01)
    est_down = price_change_estimate(mod, conv, -0.01)
    assert est_up["convexity_effect"] > 0
    assert est_down["convexity_effect"] > 0


def test_symmetric_duration_effect():
    """Duration effects should be opposite sign for +/- yield changes."""
    mod = 7.0
    conv = 60.0
    est_up = price_change_estimate(mod, conv, 0.01)
    est_down = price_change_estimate(mod, conv, -0.01)
    assert abs(est_up["duration_effect"] + est_down["duration_effect"]) < 0.001


def test_yield_change_bps_conversion():
    est = price_change_estimate(7.0, 60.0, 0.01)
    assert est["yield_change_bps"] == 100.0


# ---------------------------------------------------------------------------
# Full Bond Analysis
# ---------------------------------------------------------------------------

def test_full_analysis_keys():
    result = full_bond_analysis(1000, 0.05, 0.04, 10, 2)
    assert "price" in result
    assert "macaulay_duration" in result
    assert "modified_duration" in result
    assert "convexity" in result
    assert "dollar_duration" in result
    assert "scenarios" in result
    assert "-100bps" in result["scenarios"]
    assert "+100bps" in result["scenarios"]


def test_full_analysis_scenarios_direction():
    result = full_bond_analysis(1000, 0.05, 0.04, 10, 2)
    # Yield down -> price up
    assert result["scenarios"]["-100bps"]["price_change_pct"] > 0
    # Yield up -> price down
    assert result["scenarios"]["+100bps"]["price_change_pct"] < 0


# ---------------------------------------------------------------------------
# Yield Curve
# ---------------------------------------------------------------------------

def test_yield_curve_keys():
    curve = get_yield_curve()
    assert "maturities" in curve
    assert "yields" in curve
    assert "labels" in curve
    assert "slope_2s10s" in curve
    assert "inverted" in curve
    assert "source" in curve


def test_yield_curve_lengths_match():
    curve = get_yield_curve()
    assert len(curve["maturities"]) == len(curve["yields"])
    assert len(curve["maturities"]) == len(curve["labels"])


def test_yield_curve_reasonable_values():
    """Yields should be in a reasonable range (0-15%)."""
    curve = get_yield_curve()
    for y in curve["yields"]:
        assert 0 <= y <= 0.15


def test_yield_curve_slope():
    curve = get_yield_curve()
    y2_idx = curve["labels"].index("2Y")
    y10_idx = curve["labels"].index("10Y")
    expected_slope = curve["yields"][y10_idx] - curve["yields"][y2_idx]
    assert abs(curve["slope_2s10s"] - expected_slope) < 0.0001


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------

def test_interpolate_at_known_maturity():
    maturities = [1, 2, 5, 10]
    yields = [0.03, 0.035, 0.04, 0.045]
    result = interpolate_yield(maturities, yields, 5)
    assert abs(result - 0.04) < 1e-9


def test_interpolate_between_maturities():
    maturities = [1, 2, 5, 10]
    yields = [0.03, 0.035, 0.04, 0.045]
    result = interpolate_yield(maturities, yields, 3)
    # Between 2Y (3.5%) and 5Y (4%)
    assert 0.035 < result < 0.04


def test_interpolate_monotonic():
    """If curve is normal, interpolated yields increase with maturity."""
    maturities = [1, 2, 5, 10, 30]
    yields = [0.03, 0.035, 0.04, 0.045, 0.05]
    y3 = interpolate_yield(maturities, yields, 3)
    y7 = interpolate_yield(maturities, yields, 7)
    y15 = interpolate_yield(maturities, yields, 15)
    assert y3 < y7 < y15


# ---------------------------------------------------------------------------
# Yield Curve Slope
# ---------------------------------------------------------------------------

def test_yield_curve_slope_function():
    result = yield_curve_slope()
    assert "slope_2s10s" in result
    assert "interpretation" in result
    assert isinstance(result["interpretation"], str)


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

def test_very_short_maturity():
    result = price_bond(1000, 0.05, 0.04, 0.25, 2)
    assert result["price"] > 0


def test_very_long_maturity():
    result = price_bond(1000, 0.05, 0.04, 50, 2)
    assert result["price"] > 0


def test_ytm_zero():
    """ytm=0 -> no discounting, price = sum of all cash flows."""
    result = price_bond(1000, 0.05, 0.0, 10, 2)
    expected = 25 * 20 + 1000  # 20 coupons of 25 + face
    assert abs(result["price"] - expected) < 0.01


def test_very_high_ytm():
    """Very high yield -> price approaches 0."""
    result = price_bond(1000, 0.05, 1.0, 10, 2)
    assert result["price"] < 100
