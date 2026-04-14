"""
Fama-French 5-Factor Risk Decomposition Engine.
Decomposes portfolio returns into systematic factor exposures and idiosyncratic risk.

Model: R_p - R_f = alpha + b1(Mkt-RF) + b2(SMB) + b3(HML) + b4(RMW) + b5(CMA) + e
"""
import math
import numpy as np
import pandas as pd
import statsmodels.api as sm
from core.sanitize import sanitize_returns, require_min_length, safe_divide
from core.calendar import align_dates

FACTOR_NAMES = ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]


# ---------------------------------------------------------------------------
# Factor Data Retrieval
# ---------------------------------------------------------------------------

def get_factor_data(period: str = "3y") -> pd.DataFrame:
    """Download or retrieve cached Fama-French 5-factor daily data.
    Values are in decimal form (not percentages).
    Returns DataFrame with columns: Mkt-RF, SMB, HML, RMW, CMA, RF
    Index: DatetimeIndex. Returns empty DataFrame on failure."""
    try:
        from core.data import get_fama_french_factors
        df = get_fama_french_factors(period)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass

    # Fallback: pandas_datareader
    try:
        import pandas_datareader.data as web
        from core.data import period_to_days
        from datetime import datetime, timedelta

        days = period_to_days(period)
        start = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")

        ds = web.DataReader("F-F_Research_Data_5_Factors_2x3_daily", "famafrench", start=start)
        df = ds[0]  # first table is the data
        df = df / 100.0  # convert from percentage to decimal
        df.index = pd.to_datetime(df.index.astype(str), format="%Y%m%d", errors="coerce")
        df = df.dropna(subset=["Mkt-RF"])
        return df
    except Exception:
        pass

    # Fallback: direct download
    try:
        from core.data import _download_ff_factors
        df = _download_ff_factors()
        if df is not None and not df.empty:
            from core.data import period_to_days
            from datetime import datetime, timedelta
            days = period_to_days(period)
            cutoff = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
            return df[df.index >= cutoff]
    except Exception:
        pass

    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Factor Model Fitting
# ---------------------------------------------------------------------------

def fit_factor_model(portfolio_returns: pd.Series, factor_data: pd.DataFrame,
                     min_observations: int = 60) -> dict:
    """Fit Fama-French 5-factor OLS regression.
    R_p - R_f = alpha + b1(Mkt-RF) + b2(SMB) + b3(HML) + b4(RMW) + b5(CMA) + e"""
    if factor_data is None or factor_data.empty:
        return {"model_valid": False, "error": "No factor data available"}

    if portfolio_returns is None or portfolio_returns.empty:
        return {"model_valid": False, "error": "No portfolio returns provided"}

    try:
        # Align dates
        port_df = pd.DataFrame({"port": portfolio_returns})
        aligned_port, aligned_factors = align_dates(port_df, factor_data)

        if len(aligned_port) < min_observations:
            return {
                "model_valid": False,
                "error": f"Insufficient data: {len(aligned_port)} observations, need {min_observations}",
            }

        # Excess returns
        port_excess = aligned_port["port"].values - aligned_factors["RF"].values

        # Factor matrix
        X = aligned_factors[FACTOR_NAMES].values
        X_const = sm.add_constant(X)

        # OLS
        model = sm.OLS(port_excess, X_const).fit()

        # Extract results
        params = model.params
        tvalues = model.tvalues
        pvalues = model.pvalues

        alpha_daily = float(params[0])
        loadings = {f: float(params[i + 1]) for i, f in enumerate(FACTOR_NAMES)}
        t_stats = {"alpha": float(tvalues[0])}
        p_vals = {"alpha": float(pvalues[0])}
        for i, f in enumerate(FACTOR_NAMES):
            t_stats[f] = float(tvalues[i + 1])
            p_vals[f] = float(pvalues[i + 1])

        residual_std_daily = float(np.std(model.resid, ddof=1))

        return {
            "alpha": alpha_daily * 252,
            "alpha_daily": alpha_daily,
            "factor_loadings": loadings,
            "t_stats": t_stats,
            "p_values": p_vals,
            "r_squared": float(model.rsquared),
            "adj_r_squared": float(model.rsquared_adj),
            "residual_vol": residual_std_daily * math.sqrt(252),
            "observations": int(len(aligned_port)),
            "model_valid": True,
        }

    except Exception as e:
        return {"model_valid": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Risk Decomposition
# ---------------------------------------------------------------------------

def decompose_risk(factor_loadings: dict, factor_data: pd.DataFrame,
                   residual_vol: float) -> dict:
    """Decompose total portfolio risk into factor contributions."""
    if factor_data is None or factor_data.empty:
        return {"error": "No factor data for decomposition"}

    try:
        factors_df = factor_data[FACTOR_NAMES]
        cov_daily = factors_df.cov().values
        cov_ann = cov_daily * 252

        betas = np.array([factor_loadings.get(f, 0.0) for f in FACTOR_NAMES])

        systematic_var = float(betas @ cov_ann @ betas)
        idiosyncratic_var = residual_vol ** 2
        total_var = systematic_var + idiosyncratic_var

        if total_var <= 0:
            total_var = 1e-12

        # Individual factor contributions (diagonal terms)
        factor_contribs = {}
        for i, f in enumerate(FACTOR_NAMES):
            fvar = betas[i] ** 2 * cov_ann[i, i]
            factor_contribs[f] = {
                "variance": round(fvar, 8),
                "pct_of_total": round(safe_divide(fvar, total_var) * 100, 2),
            }

        return {
            "total_variance": round(total_var, 8),
            "systematic_variance": round(systematic_var, 8),
            "idiosyncratic_variance": round(idiosyncratic_var, 8),
            "systematic_pct": round(safe_divide(systematic_var, total_var) * 100, 2),
            "idiosyncratic_pct": round(safe_divide(idiosyncratic_var, total_var) * 100, 2),
            "factor_contributions": factor_contribs,
        }

    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------------

def interpret_factors(model_result: dict) -> list:
    """Generate human-readable interpretations of factor exposures."""
    if not model_result.get("model_valid", False):
        return [f"Factor model could not be fitted: {model_result.get('error', 'unknown error')}"]

    insights = []
    loadings = model_result.get("factor_loadings", {})
    t_stats = model_result.get("t_stats", {})
    p_values = model_result.get("p_values", {})
    r2 = model_result.get("r_squared", 0)
    alpha = model_result.get("alpha", 0)

    def _significant(name):
        return abs(t_stats.get(name, 0)) > 2.0 or p_values.get(name, 1.0) < 0.05

    # Market beta
    mkt = loadings.get("Mkt-RF", 1.0)
    if _significant("Mkt-RF"):
        if mkt > 1.2:
            insights.append(f"Portfolio is more volatile than the market (beta = {mkt:.2f}). Expect amplified moves in both directions.")
        elif mkt < 0.8:
            insights.append(f"Portfolio is defensive relative to the market (beta = {mkt:.2f}). Should hold up better in downturns.")
        else:
            insights.append(f"Portfolio tracks the market closely (beta = {mkt:.2f}).")

    # SMB
    smb = loadings.get("SMB", 0)
    if _significant("SMB"):
        if smb > 0.2:
            insights.append("Portfolio tilts toward small-cap stocks, which historically offer higher returns with more volatility.")
        elif smb < -0.2:
            insights.append("Portfolio tilts toward large-cap stocks, typically more stable.")

    # HML
    hml = loadings.get("HML", 0)
    if _significant("HML"):
        if hml > 0.2:
            insights.append("Portfolio has a value bias — overweight in stocks with high book-to-market ratios.")
        elif hml < -0.2:
            insights.append("Portfolio has a growth bias — overweight in growth stocks relative to value.")

    # RMW
    rmw = loadings.get("RMW", 0)
    if _significant("RMW"):
        if rmw > 0.2:
            insights.append("Portfolio favors profitable companies with robust earnings.")
        elif rmw < -0.2:
            insights.append("Portfolio leans toward less profitable or speculative firms.")

    # CMA
    cma = loadings.get("CMA", 0)
    if _significant("CMA"):
        if cma > 0.2:
            insights.append("Portfolio overweights firms with conservative investment strategies (low asset growth).")
        elif cma < -0.2:
            insights.append("Portfolio overweights aggressive growers (high asset growth, more capex).")

    # Alpha
    if _significant("alpha"):
        if alpha > 0:
            insights.append(f"Portfolio generates positive alpha of {alpha:.1%} annualized — outperforming what the factor model predicts.")
        else:
            insights.append(f"Portfolio shows negative alpha of {alpha:.1%} annualized — underperforming factor-adjusted expectations.")

    # R-squared
    if r2 > 0.9:
        insights.append(f"Factor model explains {r2:.0%} of portfolio variance — returns are almost entirely driven by systematic factors.")
    elif r2 > 0.7:
        insights.append(f"Factor model explains {r2:.0%} of variance. Portfolio has moderate idiosyncratic risk.")
    else:
        insights.append(f"Factor model explains only {r2:.0%} of variance — significant stock-specific or unexplained risk.")

    return insights


# ---------------------------------------------------------------------------
# Full Pipeline
# ---------------------------------------------------------------------------

def full_factor_analysis(portfolio_returns: pd.Series, period: str = "3y") -> dict:
    """Run the complete factor analysis pipeline."""
    factor_data = get_factor_data(period)
    if factor_data.empty:
        return {"model_valid": False, "error": "Could not retrieve factor data"}

    model = fit_factor_model(portfolio_returns, factor_data)
    if not model.get("model_valid", False):
        return model

    risk = decompose_risk(model["factor_loadings"], factor_data, model["residual_vol"])
    interpretations = interpret_factors(model)

    return {
        **model,
        "risk_decomposition": risk,
        "interpretations": interpretations,
    }
