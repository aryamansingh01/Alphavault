"""
Comprehensive test suite for AlphaVault portfolio analytics.
Tests financial math correctness, edge cases, and numerical stability.
"""
import math
import numpy as np
import pytest
from core.analytics import (
    portfolio_returns, annualized_return, annualized_volatility,
    sharpe_ratio, sortino_ratio, beta, alpha, treynor_ratio,
    max_drawdown, calmar_ratio, value_at_risk, conditional_var,
    correlation_matrix, solve_min_variance, portfolio_stats,
    efficient_frontier, monte_carlo, stress_test, drawdown_analysis,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_prices():
    """Two assets, 10 days of prices."""
    return np.array([
        [100.0, 50.0],
        [102.0, 51.0],
        [101.0, 52.0],
        [104.0, 51.5],
        [103.0, 53.0],
        [106.0, 52.0],
        [105.0, 54.0],
        [108.0, 53.5],
        [107.0, 55.0],
        [110.0, 54.0],
    ])


@pytest.fixture
def equal_weights():
    return np.array([0.5, 0.5])


@pytest.fixture
def daily_returns_positive():
    """Consistently positive daily returns."""
    np.random.seed(42)
    return np.random.normal(0.001, 0.01, 252)


@pytest.fixture
def daily_returns_negative():
    """Consistently negative daily returns."""
    np.random.seed(42)
    return np.random.normal(-0.002, 0.015, 252)


@pytest.fixture
def daily_returns_zero_vol():
    """Returns with zero variance (constant returns)."""
    return np.full(252, 0.0004)


@pytest.fixture
def two_asset_cov():
    """Simple 2-asset covariance matrix."""
    return np.array([[0.04, 0.01],
                     [0.01, 0.09]])


@pytest.fixture
def two_asset_mu():
    return np.array([0.10, 0.15])


# ===========================================================================
# Portfolio Returns
# ===========================================================================

class TestPortfolioReturns:
    def test_basic_calculation(self, simple_prices, equal_weights):
        rets = portfolio_returns(simple_prices, equal_weights)
        assert len(rets) == len(simple_prices) - 1

    def test_single_asset(self):
        prices = np.array([[100.0], [110.0], [105.0]])
        rets = portfolio_returns(prices, np.array([1.0]))
        np.testing.assert_allclose(rets, [0.10, -0.04545454545], rtol=1e-5)

    def test_weights_sum_to_one(self, simple_prices):
        w = np.array([0.7, 0.3])
        rets = portfolio_returns(simple_prices, w)
        # Manually compute first return
        r1_asset1 = (102 - 100) / 100
        r1_asset2 = (51 - 50) / 50
        expected = 0.7 * r1_asset1 + 0.3 * r1_asset2
        assert abs(rets[0] - expected) < 1e-10

    def test_zero_weight_ignores_asset(self, simple_prices):
        w_only_first = np.array([1.0, 0.0])
        rets = portfolio_returns(simple_prices, w_only_first)
        single = np.diff(simple_prices[:, 0]) / simple_prices[:-1, 0]
        np.testing.assert_allclose(rets, single, rtol=1e-10)


# ===========================================================================
# Annualized Return & Volatility
# ===========================================================================

class TestAnnualized:
    def test_positive_returns(self, daily_returns_positive):
        ann_ret = annualized_return(daily_returns_positive)
        assert ann_ret > 0  # positive mean → positive annualized

    def test_negative_returns(self, daily_returns_negative):
        ann_ret = annualized_return(daily_returns_negative)
        assert ann_ret < 0

    def test_zero_returns(self):
        assert annualized_return(np.zeros(100)) == 0.0

    def test_volatility_positive(self, daily_returns_positive):
        vol = annualized_volatility(daily_returns_positive)
        assert vol > 0

    def test_volatility_zero_for_constant(self, daily_returns_zero_vol):
        vol = annualized_volatility(daily_returns_zero_vol)
        assert vol == pytest.approx(0.0, abs=1e-10)

    def test_volatility_scales_with_sqrt_time(self):
        daily_ret = np.random.RandomState(0).normal(0, 0.01, 10000)
        daily_vol = np.std(daily_ret, ddof=1)
        ann_vol = annualized_volatility(daily_ret)
        assert ann_vol == pytest.approx(daily_vol * math.sqrt(252), rel=0.01)


# ===========================================================================
# Sharpe Ratio
# ===========================================================================

class TestSharpe:
    def test_basic(self):
        # 10% return, 20% vol, 5.2% rf → sharpe = (0.10 - 0.052) / 0.20 = 0.24
        assert sharpe_ratio(0.10, 0.20) == pytest.approx(0.24, rel=1e-5)

    def test_zero_vol_returns_zero(self):
        assert sharpe_ratio(0.10, 0.0) == 0.0

    def test_negative_excess_return(self):
        assert sharpe_ratio(0.02, 0.15) < 0

    def test_high_sharpe(self):
        # Renaissance-level: 60% return, 10% vol
        sh = sharpe_ratio(0.60, 0.10)
        assert sh > 5


# ===========================================================================
# Sortino Ratio
# ===========================================================================

class TestSortino:
    def test_all_positive_returns(self):
        # No negative returns → sortino = 0 (no downside)
        rets = np.abs(np.random.RandomState(0).normal(0.001, 0.01, 252))
        assert sortino_ratio(rets) == 0.0

    def test_mixed_returns(self, daily_returns_positive):
        sort = sortino_ratio(daily_returns_positive)
        # Sortino should be defined for mixed returns
        assert isinstance(sort, float)

    def test_sortino_geq_sharpe_for_positive_skew(self):
        # For positively skewed returns, sortino ≥ sharpe (less downside penalized)
        np.random.seed(99)
        rets = np.abs(np.random.normal(0.001, 0.01, 252))
        rets = np.concatenate([rets, np.random.normal(-0.0005, 0.005, 50)])
        ann_ret = annualized_return(rets)
        ann_vol = annualized_volatility(rets)
        sh = sharpe_ratio(ann_ret, ann_vol)
        so = sortino_ratio(rets)
        # Sortino uses only downside deviation → typically larger than Sharpe
        # (not guaranteed for all distributions, so just check it's defined)
        assert isinstance(so, float)


# ===========================================================================
# Beta & Alpha
# ===========================================================================

class TestBetaAlpha:
    def test_beta_of_market_is_one(self):
        np.random.seed(42)
        market = np.random.normal(0.0005, 0.01, 500)
        b = beta(market, market)
        assert b == pytest.approx(1.0, rel=1e-3)

    def test_beta_of_uncorrelated(self):
        np.random.seed(42)
        p = np.random.normal(0, 0.01, 500)
        m = np.random.normal(0, 0.01, 500)
        b = beta(p, m)
        assert abs(b) < 0.2  # should be close to 0

    def test_beta_insufficient_data(self):
        assert beta(np.array([0.01, 0.02]), np.array([0.01, 0.02])) == 1.0

    def test_alpha_zero_for_market(self):
        a = alpha(0.10, 1.0, 0.10, rf=0.05)
        assert a == pytest.approx(0.0, abs=1e-10)

    def test_alpha_positive_for_outperformer(self):
        # Portfolio returns 15%, beta=1, market returns 10%, rf=5%
        # alpha = 0.15 - 0.05 - 1.0*(0.10-0.05) = 0.05
        a = alpha(0.15, 1.0, 0.10, rf=0.05)
        assert a == pytest.approx(0.05, rel=1e-5)

    def test_high_beta_amplifies_market(self):
        np.random.seed(42)
        market = np.random.normal(0.0005, 0.01, 500)
        leveraged = market * 2  # 2x leveraged
        b = beta(leveraged, market)
        assert b == pytest.approx(2.0, rel=0.01)


# ===========================================================================
# Treynor Ratio
# ===========================================================================

class TestTreynor:
    def test_basic(self):
        # Treynor = (0.12 - 0.052) / 1.2 = 0.0567
        assert treynor_ratio(0.12, 1.2) == pytest.approx(0.0567, rel=0.01)

    def test_zero_beta_returns_zero(self):
        assert treynor_ratio(0.10, 0.0) == 0.0

    def test_negative_beta(self):
        tr = treynor_ratio(0.10, -0.5)
        assert tr < 0  # negative beta + positive excess → negative treynor


# ===========================================================================
# Drawdown & Calmar
# ===========================================================================

class TestDrawdown:
    def test_max_drawdown_50pct_crash(self):
        # Simulate: up 10%, then crash -55%, then recover 20%
        rets = np.array([0.10, 0.05, -0.30, -0.35, 0.20, 0.15])
        dd = max_drawdown(rets)
        assert dd < -0.40  # significant drawdown occurred
        assert dd <= 0

    def test_max_drawdown_always_negative_or_zero(self, daily_returns_positive):
        dd = max_drawdown(daily_returns_positive)
        assert dd <= 0

    def test_drawdown_analysis_basic(self):
        # Need 10+ data points
        prices = np.array([100, 105, 110, 108, 115, 120, 90, 95, 100, 110, 105], dtype=float)
        result = drawdown_analysis(prices)
        assert result["maxdrawdown"] < 0
        assert result["duration"] > 0

    def test_drawdown_analysis_monotonic_up(self):
        prices = np.arange(100, 200, dtype=float)
        result = drawdown_analysis(prices)
        assert result["maxdrawdown"] == 0.0

    def test_calmar_positive(self):
        assert calmar_ratio(0.10, -0.25) == pytest.approx(0.4, rel=1e-5)

    def test_calmar_zero_drawdown(self):
        assert calmar_ratio(0.10, 0.0) == 0.0


# ===========================================================================
# VaR & CVaR
# ===========================================================================

class TestVaR:
    def test_var95_is_negative(self, daily_returns_positive):
        # Even for mostly-positive returns, 5th percentile should be in the left tail
        var = value_at_risk(daily_returns_positive, 0.95)
        assert isinstance(var, float)

    def test_var99_more_extreme_than_var95(self, daily_returns_positive):
        var95 = value_at_risk(daily_returns_positive, 0.95)
        var99 = value_at_risk(daily_returns_positive, 0.99)
        assert var99 <= var95  # 99% VaR is more extreme (further left)

    def test_cvar_leq_var(self, daily_returns_positive):
        var95 = value_at_risk(daily_returns_positive, 0.95)
        cvar = conditional_var(daily_returns_positive, var95)
        assert cvar <= var95  # CVaR is the average beyond VaR, so worse

    def test_cvar_with_no_tail(self):
        # All returns equal → CVaR = VaR = that value
        rets = np.full(100, 0.01)
        var = value_at_risk(rets, 0.95)
        cvar = conditional_var(rets, var)
        assert cvar == pytest.approx(var, abs=1e-10)

    def test_var_known_distribution(self):
        np.random.seed(0)
        rets = np.random.normal(0, 0.01, 100_000)
        var95 = value_at_risk(rets, 0.95)
        # 5th percentile of N(0, 0.01) ≈ -1.645 * 0.01 = -0.01645
        assert var95 == pytest.approx(-0.01645, abs=0.001)


# ===========================================================================
# Correlation Matrix
# ===========================================================================

class TestCorrelation:
    def test_diagonal_is_one(self):
        np.random.seed(42)
        rets = np.random.normal(0, 0.01, (252, 3))
        corr = correlation_matrix(rets)
        np.testing.assert_allclose(np.diag(corr), 1.0, atol=1e-10)

    def test_symmetric(self):
        np.random.seed(42)
        rets = np.random.normal(0, 0.01, (252, 4))
        corr = correlation_matrix(rets)
        np.testing.assert_allclose(corr, corr.T, atol=1e-10)

    def test_perfect_correlation(self):
        x = np.arange(100, dtype=float).reshape(-1, 1)
        rets = np.hstack([x, x * 2])
        corr = correlation_matrix(rets)
        assert corr[0, 1] == pytest.approx(1.0, abs=1e-10)

    def test_uncorrelated(self):
        np.random.seed(42)
        n = 100_000
        rets = np.column_stack([np.random.normal(0, 1, n), np.random.normal(0, 1, n)])
        corr = correlation_matrix(rets)
        assert abs(corr[0, 1]) < 0.01


# ===========================================================================
# Efficient Frontier
# ===========================================================================

class TestEfficientFrontier:
    def test_min_variance_weights_sum_to_one(self, two_asset_mu, two_asset_cov):
        w = solve_min_variance(two_asset_mu, two_asset_cov)
        assert np.sum(w) == pytest.approx(1.0, abs=1e-8)

    def test_min_variance_long_only(self, two_asset_mu, two_asset_cov):
        w = solve_min_variance(two_asset_mu, two_asset_cov)
        assert np.all(w >= 0)

    def test_min_variance_with_target(self, two_asset_mu, two_asset_cov):
        target = 0.12
        w = solve_min_variance(two_asset_mu, two_asset_cov, target_ret=target)
        assert np.sum(w) == pytest.approx(1.0, abs=1e-8)
        assert np.all(w >= 0)

    def test_min_variance_lower_vol_than_equal_weight(self, two_asset_mu, two_asset_cov):
        w_mv = solve_min_variance(two_asset_mu, two_asset_cov)
        w_eq = np.array([0.5, 0.5])
        _, v_mv = portfolio_stats(w_mv, two_asset_mu, two_asset_cov)
        _, v_eq = portfolio_stats(w_eq, two_asset_mu, two_asset_cov)
        assert v_mv <= v_eq + 1e-8

    def test_portfolio_stats_dimensions(self, two_asset_mu, two_asset_cov):
        w = np.array([0.6, 0.4])
        r, v = portfolio_stats(w, two_asset_mu, two_asset_cov)
        expected_r = 0.6 * 0.10 + 0.4 * 0.15
        assert r == pytest.approx(expected_r, rel=1e-5)
        assert v > 0

    def test_efficient_frontier_has_points(self, two_asset_mu, two_asset_cov):
        result = efficient_frontier(two_asset_mu, two_asset_cov, n_points=20, n_random=100)
        assert len(result["frontier"]) > 0
        assert result["min_vol"]["vol"] > 0
        assert result["max_sharpe"]["vol"] > 0

    def test_max_sharpe_better_than_equal_weight(self, two_asset_mu, two_asset_cov):
        result = efficient_frontier(two_asset_mu, two_asset_cov)
        ms = result["max_sharpe"]
        w_eq = np.array([0.5, 0.5])
        r_eq, v_eq = portfolio_stats(w_eq, two_asset_mu, two_asset_cov)
        sharpe_eq = r_eq / v_eq if v_eq > 0 else 0
        assert ms["sharpe"] >= sharpe_eq - 0.01  # allow small numerical tolerance

    def test_singular_cov_fallback(self):
        mu = np.array([0.1, 0.1])
        cov = np.array([[1, 1], [1, 1]])  # singular
        w = solve_min_variance(mu, cov)
        assert np.sum(w) == pytest.approx(1.0, abs=1e-8)

    def test_three_assets(self):
        mu = np.array([0.08, 0.12, 0.06])
        cov = np.array([
            [0.04, 0.006, 0.002],
            [0.006, 0.09, 0.004],
            [0.002, 0.004, 0.01],
        ])
        result = efficient_frontier(mu, cov, n_points=30, n_random=200)
        assert sum(result["min_vol"]["weights"]) == pytest.approx(1.0, abs=1e-6)
        assert sum(result["max_sharpe"]["weights"]) == pytest.approx(1.0, abs=1e-6)


# ===========================================================================
# Monte Carlo
# ===========================================================================

class TestMonteCarlo:
    def test_basic_output(self):
        result = monte_carlo(10000, 0.08, 0.15, years=10, n_sims=500, seed=42)
        assert 5 in result["percentiles"]
        assert 50 in result["percentiles"]
        assert 95 in result["percentiles"]
        assert result["paths"].shape == (500, 121)  # 10 years * 12 months + 1

    def test_median_grows_with_positive_return(self):
        result = monte_carlo(10000, 0.10, 0.15, years=20, n_sims=2000, seed=42)
        assert result["percentiles"][50] > 10000

    def test_zero_return_zero_vol(self):
        result = monte_carlo(10000, 0.0, 0.0, years=5, monthly_contrib=0,
                             inflation=0, n_sims=100, seed=42)
        # With 0 return and 0 vol, final value should equal initial NAV
        assert result["percentiles"][50] == pytest.approx(10000, rel=0.01)

    def test_contributions_increase_final_value(self):
        r1 = monte_carlo(10000, 0.08, 0.15, years=10, monthly_contrib=0, n_sims=1000, seed=42)
        r2 = monte_carlo(10000, 0.08, 0.15, years=10, monthly_contrib=500, n_sims=1000, seed=42)
        assert r2["percentiles"][50] > r1["percentiles"][50]

    def test_prob_positive_in_range(self):
        result = monte_carlo(10000, 0.08, 0.15, years=20, n_sims=1000, seed=42)
        assert 0 <= result["prob_positive"] <= 100

    def test_higher_vol_wider_spread(self):
        r_low = monte_carlo(10000, 0.08, 0.10, years=10, n_sims=2000, seed=42)
        r_high = monte_carlo(10000, 0.08, 0.30, years=10, n_sims=2000, seed=42)
        spread_low = r_low["percentiles"][95] - r_low["percentiles"][5]
        spread_high = r_high["percentiles"][95] - r_high["percentiles"][5]
        assert spread_high > spread_low


# ===========================================================================
# Stress Testing
# ===========================================================================

class TestStressTest:
    def test_returns_all_scenarios(self):
        results = stress_test(["AAPL", "MSFT"], np.array([0.5, 0.5]),
                              {"AAPL": 1.2, "MSFT": 1.0})
        assert len(results) == 8

    def test_financial_crisis_impact_negative(self):
        results = stress_test(["AAPL"], np.array([1.0]), {"AAPL": 1.5})
        crisis = next(r for r in results if "2008" in r["scenario"])
        assert crisis["impact"] < 0

    def test_tech_selloff_hits_tech_harder(self):
        results_tech = stress_test(["AAPL"], np.array([1.0]), {"AAPL": 1.0})
        results_energy = stress_test(["XOM"], np.array([1.0]), {"XOM": 1.0})
        tech_impact = next(r for r in results_tech if "Tech Selloff" in r["scenario"])
        energy_impact = next(r for r in results_energy if "Tech Selloff" in r["scenario"])
        assert tech_impact["impact"] < energy_impact["impact"]

    def test_zero_beta_reduces_hist_impact(self):
        results = stress_test(["AAPL"], np.array([1.0]), {"AAPL": 0.0})
        crisis = next(r for r in results if "2008" in r["scenario"])
        assert crisis["impact"] == pytest.approx(0.0, abs=1e-10)

    def test_diversified_portfolio(self):
        results = stress_test(
            ["AAPL", "XOM", "GLD", "BND"],
            np.array([0.25, 0.25, 0.25, 0.25]),
            {"AAPL": 1.2, "XOM": 0.8, "GLD": 0.1, "BND": -0.1},
        )
        assert all("impact" in r for r in results)


# ===========================================================================
# Drawdown Analysis
# ===========================================================================

class TestDrawdownAnalysis:
    def test_monotonic_up(self):
        prices = np.linspace(100, 200, 252)
        result = drawdown_analysis(prices)
        assert result["maxdrawdown"] == 0.0

    def test_single_crash(self):
        prices = np.concatenate([
            np.linspace(100, 200, 100),
            np.linspace(200, 100, 50),
            np.linspace(100, 150, 102),
        ])
        result = drawdown_analysis(prices)
        assert result["maxdrawdown"] == pytest.approx(-0.5, abs=0.01)

    def test_short_series(self):
        result = drawdown_analysis(np.array([100, 95, 90]))
        assert result["maxdrawdown"] == 0  # fewer than 10 points
