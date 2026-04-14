import json, math
import numpy as np
import yfinance as yf
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler


def _solve_min_vol(mu, cov, n, target_ret=None):
    """Analytical min-variance with optional return constraint (long-only approx via projection)."""
    try:
        inv_cov = np.linalg.inv(cov)
    except np.linalg.LinAlgError:
        return np.ones(n) / n

    ones = np.ones(n)

    if target_ret is None:
        # Global min variance: w = inv(C) * 1 / (1' inv(C) 1)
        w = inv_cov @ ones
        w = w / w.sum()
    else:
        # Min variance subject to w'mu = target
        A = ones @ inv_cov @ ones
        B = ones @ inv_cov @ mu
        C = mu @ inv_cov @ mu
        det = A * C - B * B
        if abs(det) < 1e-12:
            w = inv_cov @ ones / (ones @ inv_cov @ ones)
        else:
            lam1 = (C - target_ret * B) / det
            lam2 = (target_ret * A - B) / det
            w = inv_cov @ (lam1 * ones + lam2 * mu)

    # Project to long-only: clip negatives, renormalize
    w = np.maximum(w, 0)
    s = w.sum()
    return w / s if s > 0 else np.ones(n) / n


class handler(BaseHandler):
    def do_POST(self):
        try:
            body = self._body()
        except Exception as e:
            return self._err(f"Bad JSON body: {e}", 400)

        tickers = body.get("tickers") or []
        weights = body.get("weights") or {}

        if not tickers and weights:
            tickers = list(weights.keys())
        if not tickers and body.get("holdings"):
            tickers = [p.get("ticker") or p.get("symbol") for p in body["holdings"] if p.get("ticker") or p.get("symbol")]
        if not tickers and body.get("positions"):
            tickers = [p.get("ticker") or p.get("symbol") for p in body["positions"] if p.get("ticker") or p.get("symbol")]

        tickers = [t.upper().strip() for t in tickers if t]
        if len(tickers) < 2:
            return self._err("At least 2 tickers required", 400)

        period = body.get("period", "1y")

        try:
            raw_df = yf.download(tickers, period=period, auto_adjust=True, progress=False, group_by="column")
            if raw_df is None or raw_df.empty:
                return self._err("No price data returned")

            if len(tickers) == 1:
                prices = raw_df[["Close"]] if "Close" in raw_df.columns else raw_df
                prices.columns = tickers
            else:
                try:
                    prices = raw_df["Close"]
                except KeyError:
                    prices = raw_df.xs("Close", axis=1, level=0)

            prices = prices[[c for c in tickers if c in prices.columns]]
            prices = prices.dropna(axis=1, how="all").dropna(axis=0)
            valid = list(prices.columns)
            if len(valid) < 2:
                return self._err("Insufficient data for: " + str(tickers))

            rets = prices.pct_change().dropna()
            if len(rets) < 30:
                return self._err("Need 30+ trading days of history")

            mu  = rets.mean().values * 252
            cov = rets.cov().values * 252
            cov += np.eye(len(valid)) * 1e-8
            n   = len(valid)

            def port_stats(w):
                r = float(w @ mu)
                v = float(math.sqrt(max(w @ cov @ w, 0)))
                return r, v

            # Min-Vol portfolio (analytical)
            w_mv = _solve_min_vol(mu, cov, n)
            r_mv, v_mv = port_stats(w_mv)

            # Max-Sharpe: try analytical, fallback to sampling
            # Analytical: w* = inv(C) * mu (tangent portfolio)
            try:
                inv_cov = np.linalg.inv(cov)
                w_s = inv_cov @ mu
                w_s = np.maximum(w_s, 0)
                s = w_s.sum()
                w_s = w_s / s if s > 0 else np.ones(n) / n
            except Exception:
                w_s = np.ones(n) / n
            r_s, v_s = port_stats(w_s)

            # If max-sharpe is worse than equal weight, use sampling
            w_eq = np.ones(n) / n
            r_eq, v_eq = port_stats(w_eq)
            sharpe_s  = r_s / v_s if v_s > 1e-9 else 0
            sharpe_eq = r_eq / v_eq if v_eq > 1e-9 else 0

            # Generate frontier via random sampling + analytical sweep
            rng = np.random.default_rng(42)
            frontier = []
            best_sharpe = sharpe_s
            best_w = w_s

            # Analytical sweep
            r_lo = float(mu.min()) * 0.8
            r_hi = float(mu.max()) * 1.2
            for target in np.linspace(r_lo, r_hi, 40):
                w = _solve_min_vol(mu, cov, n, target_ret=target)
                r, v = port_stats(w)
                if v > 0:
                    frontier.append({"vol": round(v, 6), "ret": round(r, 6)})
                    sh = r / v
                    if sh > best_sharpe:
                        best_sharpe = sh
                        best_w = w.copy()

            # Random portfolios to fill gaps
            for _ in range(500):
                w = rng.dirichlet(np.ones(n))
                r, v = port_stats(w)
                frontier.append({"vol": round(v, 6), "ret": round(r, 6)})
                sh = r / v if v > 1e-9 else 0
                if sh > best_sharpe:
                    best_sharpe = sh
                    best_w = w.copy()

            w_s = best_w
            r_s, v_s = port_stats(w_s)

            # Deduplicate + sort
            seen, clean = set(), []
            for pt in sorted(frontier, key=lambda x: x["vol"]):
                k = (round(pt["vol"], 4), round(pt["ret"], 4))
                if k not in seen:
                    seen.add(k)
                    clean.append(pt)

            def fmt_w(wts):
                return {t: round(float(w), 4) for t, w in zip(valid, wts)}

            self._ok({
                "tickers":  valid,
                "frontier": clean,
                "maxSharpe": {
                    "weights": fmt_w(w_s),
                    "ret":     round(r_s, 6),
                    "vol":     round(v_s, 6),
                    "sharpe":  round(r_s / v_s, 4) if v_s > 1e-9 else 0,
                },
                "minVol": {
                    "weights": fmt_w(w_mv),
                    "ret":     round(r_mv, 6),
                    "vol":     round(v_mv, 6),
                    "sharpe":  round(r_mv / v_mv, 4) if v_mv > 1e-9 else 0,
                },
                "expectedReturns": {t: round(float(r), 6) for t, r in zip(valid, mu)},
                "volatilities":    {t: round(float(math.sqrt(cov[i, i])), 6)
                                    for i, t in enumerate(valid)},
            })

        except Exception as e:
            import traceback
            self._err(str(e))
