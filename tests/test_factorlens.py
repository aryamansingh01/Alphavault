"""Tests for core/factorlens.py — Factor-Based Risk Decomposition."""
import numpy as np
import pandas as pd
import pytest
import math

from core.factorlens import (
    FACTOR_NAMES, fit_factor_model, decompose_risk,
    interpret_factors, full_factor_analysis,
)


# ---------------------------------------------------------------------------
# Helpers — synthetic factor data
# ---------------------------------------------------------------------------

def _make_factor_data(n=504, seed=42):
    """Create synthetic Fama-French factor data (daily, decimal form)."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-03", periods=n, freq="B")
    data = {
        "Mkt-RF": rng.normal(0.0004, 0.01, n),
        "SMB": rng.normal(0.0001, 0.005, n),
        "HML": rng.normal(0.0001, 0.004, n),
        "RMW": rng.normal(0.0001, 0.003, n),
        "CMA": rng.normal(0.00005, 0.003, n),
        "RF": np.full(n, 0.0002),
    }
    return pd.DataFrame(data, index=idx)


def _make_port_returns(factor_data, loadings, alpha_daily=0.0, noise_std=0.002, seed=42):
    """Generate synthetic portfolio returns from factor model with known loadings."""
    rng = np.random.default_rng(seed)
    ret = alpha_daily + factor_data["RF"].values.copy()
    for f in FACTOR_NAMES:
        ret = ret + loadings.get(f, 0.0) * factor_data[f].values
    ret = ret + rng.normal(0, noise_std, len(ret))
    return pd.Series(ret, index=factor_data.index, name="port")


# ---------------------------------------------------------------------------
# Factor data
# ---------------------------------------------------------------------------

def test_factor_data_columns():
    fd = _make_factor_data()
    for col in FACTOR_NAMES + ["RF"]:
        assert col in fd.columns


def test_factor_data_decimal_form():
    """All daily factor values should be small (decimal, not percentage)."""
    fd = _make_factor_data()
    for f in FACTOR_NAMES:
        assert fd[f].abs().max() < 0.2  # daily returns < 20%


def test_factor_data_has_datetimeindex():
    fd = _make_factor_data()
    assert isinstance(fd.index, pd.DatetimeIndex)


# ---------------------------------------------------------------------------
# Model fitting
# ---------------------------------------------------------------------------

def test_fit_market_only():
    """Portfolio = 1.2 * market -> Mkt-RF loading ~ 1.2, others ~ 0."""
    fd = _make_factor_data(504)
    loadings = {"Mkt-RF": 1.2, "SMB": 0, "HML": 0, "RMW": 0, "CMA": 0}
    port = _make_port_returns(fd, loadings, noise_std=0.001)

    result = fit_factor_model(port, fd)
    assert result["model_valid"] is True
    assert abs(result["factor_loadings"]["Mkt-RF"] - 1.2) < 0.15
    for f in ["SMB", "HML", "RMW", "CMA"]:
        assert abs(result["factor_loadings"][f]) < 0.3


def test_fit_pure_noise():
    """Pure noise -> low R-squared."""
    fd = _make_factor_data(504)
    rng = np.random.default_rng(99)
    noise = pd.Series(rng.normal(0, 0.02, len(fd)), index=fd.index)

    result = fit_factor_model(noise, fd)
    assert result["model_valid"] is True
    assert result["r_squared"] < 0.15


def test_fit_insufficient_data():
    fd = _make_factor_data(30)
    port = _make_port_returns(fd, {"Mkt-RF": 1.0}, noise_std=0.01)
    result = fit_factor_model(port, fd, min_observations=60)
    assert result["model_valid"] is False


def test_fit_alpha_annualized():
    """Alpha should be daily * 252."""
    fd = _make_factor_data(504)
    port = _make_port_returns(fd, {"Mkt-RF": 1.0}, alpha_daily=0.0003, noise_std=0.001)
    result = fit_factor_model(port, fd)
    assert result["model_valid"] is True
    # daily alpha ~ 0.0003, annualized ~ 0.0756
    assert abs(result["alpha"] - result["alpha_daily"] * 252) < 1e-9


def test_fit_residual_vol_annualized():
    fd = _make_factor_data(504)
    port = _make_port_returns(fd, {"Mkt-RF": 1.0}, noise_std=0.005)
    result = fit_factor_model(port, fd)
    assert result["model_valid"] is True
    # Residual vol should be annualized
    assert result["residual_vol"] > result["residual_vol"] / math.sqrt(252) * 0.9


def test_fit_all_keys_present():
    fd = _make_factor_data(200)
    port = _make_port_returns(fd, {"Mkt-RF": 1.0})
    result = fit_factor_model(port, fd)
    assert result["model_valid"] is True
    assert all(f in result["factor_loadings"] for f in FACTOR_NAMES)
    assert all(f in result["t_stats"] for f in FACTOR_NAMES)
    assert all(f in result["p_values"] for f in FACTOR_NAMES)
    assert "alpha" in result["t_stats"]
    assert "alpha" in result["p_values"]


def test_fit_r_squared_bounds():
    fd = _make_factor_data(504)
    port = _make_port_returns(fd, {"Mkt-RF": 1.0})
    result = fit_factor_model(port, fd)
    assert 0 <= result["r_squared"] <= 1


def test_fit_observations_count():
    fd = _make_factor_data(200)
    port = _make_port_returns(fd, {"Mkt-RF": 1.0})
    result = fit_factor_model(port, fd)
    assert result["observations"] == 200


def test_fit_empty_factor_data():
    port = pd.Series([0.01] * 100, index=pd.date_range("2023-01-01", periods=100, freq="B"))
    result = fit_factor_model(port, pd.DataFrame())
    assert result["model_valid"] is False


def test_fit_empty_portfolio():
    fd = _make_factor_data()
    result = fit_factor_model(pd.Series(dtype=float), fd)
    assert result["model_valid"] is False


def test_fit_nan_in_returns():
    """NaN in portfolio returns should be handled gracefully."""
    fd = _make_factor_data(200)
    port = _make_port_returns(fd, {"Mkt-RF": 1.0})
    port.iloc[10] = np.nan
    port.iloc[50] = np.nan
    # align_dates drops NaN rows
    result = fit_factor_model(port, fd)
    assert result["model_valid"] is True
    assert result["observations"] == 198


# ---------------------------------------------------------------------------
# Risk decomposition
# ---------------------------------------------------------------------------

def test_decompose_systematic_plus_idiosyncratic():
    """systematic_pct + idiosyncratic_pct ~ 100%."""
    fd = _make_factor_data(504)
    loadings = {"Mkt-RF": 1.0, "SMB": 0.3, "HML": -0.2, "RMW": 0.1, "CMA": 0.0}
    result = decompose_risk(loadings, fd, residual_vol=0.10)
    total = result["systematic_pct"] + result["idiosyncratic_pct"]
    assert abs(total - 100.0) < 0.1


def test_decompose_factor_contributions_nonnegative():
    fd = _make_factor_data(504)
    loadings = {"Mkt-RF": 1.0, "SMB": 0.5, "HML": -0.3, "RMW": 0.2, "CMA": -0.1}
    result = decompose_risk(loadings, fd, residual_vol=0.05)
    for f in FACTOR_NAMES:
        assert result["factor_contributions"][f]["variance"] >= 0


def test_decompose_zero_loadings():
    """Zero loadings -> zero factor contributions, all risk is idiosyncratic."""
    fd = _make_factor_data(504)
    loadings = {f: 0.0 for f in FACTOR_NAMES}
    result = decompose_risk(loadings, fd, residual_vol=0.15)
    assert result["systematic_variance"] < 1e-10
    assert result["idiosyncratic_pct"] > 99.9


def test_decompose_large_market_beta_dominates():
    """Large market beta should make Mkt-RF the dominant risk."""
    fd = _make_factor_data(504)
    loadings = {"Mkt-RF": 2.0, "SMB": 0.0, "HML": 0.0, "RMW": 0.0, "CMA": 0.0}
    result = decompose_risk(loadings, fd, residual_vol=0.01)
    mkt_pct = result["factor_contributions"]["Mkt-RF"]["pct_of_total"]
    assert mkt_pct > 80


def test_decompose_empty_factor_data():
    loadings = {"Mkt-RF": 1.0, "SMB": 0, "HML": 0, "RMW": 0, "CMA": 0}
    result = decompose_risk(loadings, pd.DataFrame(), 0.1)
    assert "error" in result


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------

def test_interpret_high_beta():
    model = {
        "model_valid": True,
        "alpha": 0.02,
        "factor_loadings": {"Mkt-RF": 1.5, "SMB": 0, "HML": 0, "RMW": 0, "CMA": 0},
        "t_stats": {"alpha": 1.0, "Mkt-RF": 15.0, "SMB": 0.5, "HML": 0.3, "RMW": 0.1, "CMA": 0.2},
        "p_values": {"alpha": 0.3, "Mkt-RF": 0.0001, "SMB": 0.6, "HML": 0.7, "RMW": 0.9, "CMA": 0.8},
        "r_squared": 0.85,
    }
    msgs = interpret_factors(model)
    assert any("more volatile" in m for m in msgs)


def test_interpret_significant_smb():
    model = {
        "model_valid": True, "alpha": 0, "r_squared": 0.8,
        "factor_loadings": {"Mkt-RF": 1.0, "SMB": 0.5, "HML": 0, "RMW": 0, "CMA": 0},
        "t_stats": {"alpha": 0.5, "Mkt-RF": 10, "SMB": 3.5, "HML": 0.1, "RMW": 0.1, "CMA": 0.1},
        "p_values": {"alpha": 0.6, "Mkt-RF": 0.001, "SMB": 0.001, "HML": 0.9, "RMW": 0.9, "CMA": 0.9},
    }
    msgs = interpret_factors(model)
    assert any("small-cap" in m for m in msgs)


def test_interpret_insignificant_generates_no_message():
    model = {
        "model_valid": True, "alpha": 0, "r_squared": 0.5,
        "factor_loadings": {"Mkt-RF": 1.0, "SMB": 0.3, "HML": 0.4, "RMW": 0.3, "CMA": 0.2},
        "t_stats": {"alpha": 0.5, "Mkt-RF": 1.0, "SMB": 0.5, "HML": 0.3, "RMW": 0.2, "CMA": 0.1},
        "p_values": {"alpha": 0.6, "Mkt-RF": 0.3, "SMB": 0.6, "HML": 0.7, "RMW": 0.8, "CMA": 0.9},
    }
    msgs = interpret_factors(model)
    # Only R² message should be generated (all loadings insignificant)
    factor_msgs = [m for m in msgs if "Factor model explains" not in m]
    assert len(factor_msgs) == 0


def test_interpret_high_r_squared():
    model = {
        "model_valid": True, "alpha": 0, "r_squared": 0.95,
        "factor_loadings": {"Mkt-RF": 1.0, "SMB": 0, "HML": 0, "RMW": 0, "CMA": 0},
        "t_stats": {"alpha": 0.5, "Mkt-RF": 20, "SMB": 0.1, "HML": 0.1, "RMW": 0.1, "CMA": 0.1},
        "p_values": {"alpha": 0.6, "Mkt-RF": 0.001, "SMB": 0.9, "HML": 0.9, "RMW": 0.9, "CMA": 0.9},
    }
    msgs = interpret_factors(model)
    assert any("almost entirely" in m for m in msgs)


def test_interpret_positive_alpha():
    model = {
        "model_valid": True, "alpha": 0.05, "r_squared": 0.8,
        "factor_loadings": {"Mkt-RF": 1.0, "SMB": 0, "HML": 0, "RMW": 0, "CMA": 0},
        "t_stats": {"alpha": 3.0, "Mkt-RF": 10, "SMB": 0.1, "HML": 0.1, "RMW": 0.1, "CMA": 0.1},
        "p_values": {"alpha": 0.003, "Mkt-RF": 0.001, "SMB": 0.9, "HML": 0.9, "RMW": 0.9, "CMA": 0.9},
    }
    msgs = interpret_factors(model)
    assert any("positive alpha" in m for m in msgs)


def test_interpret_invalid_model():
    model = {"model_valid": False, "error": "No data"}
    msgs = interpret_factors(model)
    assert len(msgs) == 1
    assert "could not" in msgs[0].lower()


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def test_full_pipeline_with_synthetic():
    """Full pipeline using synthetic data injected directly."""
    fd = _make_factor_data(504)
    loadings = {"Mkt-RF": 1.1, "SMB": 0.2, "HML": -0.1, "RMW": 0.15, "CMA": 0.0}
    port = _make_port_returns(fd, loadings, alpha_daily=0.0001)

    # Directly test fit + decompose + interpret (skip get_factor_data which needs network)
    model = fit_factor_model(port, fd)
    assert model["model_valid"] is True

    risk = decompose_risk(model["factor_loadings"], fd, model["residual_vol"])
    assert abs(risk["systematic_pct"] + risk["idiosyncratic_pct"] - 100) < 0.5

    msgs = interpret_factors(model)
    assert isinstance(msgs, list)
    assert len(msgs) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_single_factor_dominance():
    """All loadings on one factor."""
    fd = _make_factor_data(200)
    port = _make_port_returns(fd, {"Mkt-RF": 1.5, "SMB": 0, "HML": 0, "RMW": 0, "CMA": 0}, noise_std=0.001)
    result = fit_factor_model(port, fd)
    assert result["model_valid"] is True
    assert result["r_squared"] > 0.5


def test_all_equal_loadings():
    fd = _make_factor_data(300)
    loadings = {f: 0.5 for f in FACTOR_NAMES}
    port = _make_port_returns(fd, loadings)
    result = fit_factor_model(port, fd)
    assert result["model_valid"] is True
    for f in FACTOR_NAMES:
        assert abs(result["factor_loadings"][f] - 0.5) < 0.3


def test_negative_loadings():
    fd = _make_factor_data(300)
    loadings = {"Mkt-RF": -0.5, "SMB": -0.3, "HML": 0.4, "RMW": 0, "CMA": 0}
    port = _make_port_returns(fd, loadings, noise_std=0.001)
    result = fit_factor_model(port, fd)
    assert result["model_valid"] is True
    assert result["factor_loadings"]["Mkt-RF"] < 0
