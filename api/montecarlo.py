import numpy as np
import yfinance as yf
import pandas as pd
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler


class handler(BaseHandler):
    def do_POST(self):
        try:
            p        = self._body()
            holdings = p.get("holdings", [])
            tickers  = [h["ticker"] for h in holdings]
            weights  = np.array([float(h.get("weight", 1/max(1, len(tickers)))) for h in holdings])
            if weights.sum() > 0: weights /= weights.sum()
            n_sims   = min(int(p.get("simulations", 1000)), 3000)
            years    = int(p.get("years", 20))
            nav      = float(p.get("nav", 10000))
            monthly  = float(p.get("monthlyContrib", 500))
            inflation= float(p.get("inflation", 0.03))
            mu_ann   = float(p.get("expectedReturn", 0.08))
            vol_ann  = float(p.get("volatility", 0.15))

            if tickers:
                try:
                    raw = yf.download(tickers, period="5y", interval="1d",
                                       auto_adjust=True, progress=False)["Close"]
                    if isinstance(raw, pd.Series): raw = raw.to_frame(tickers[0])
                    r   = (raw.pct_change().dropna() * weights[:len(raw.columns)]).sum(axis=1)
                    mu_ann  = float(r.mean() * 252)
                    vol_ann = float(r.std()  * 252**0.5)
                except: pass

            steps = years * 12
            mu_m  = mu_ann / 12
            sig_m = vol_ann / 12**0.5
            paths = np.zeros((n_sims, steps + 1))
            paths[:, 0] = nav
            for t in range(1, steps + 1):
                z    = np.random.normal(0, 1, n_sims)
                cont = monthly * (1 + inflation)**(t / 12)
                paths[:, t] = paths[:, t-1] * (1 + mu_m + sig_m * z) + cont

            final       = paths[:, -1]
            percentiles = {str(q): round(float(np.percentile(final, q)), 2)
                           for q in [5, 10, 25, 50, 75, 90, 95]}
            stride = max(1, steps // 60)
            sample = [[round(float(v), 2) for v in paths[i, ::stride]]
                      for i in range(0, n_sims, max(1, n_sims // 20))][:20]
            self._ok({"percentiles": percentiles, "samplePaths": sample,
                      "mu": round(mu_ann, 4), "vol": round(vol_ann, 4),
                      "prob_positive": round(float((final > nav).mean() * 100), 1)})
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
