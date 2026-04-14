import yfinance as yf
import numpy as np
import pandas as pd
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler


class handler(BaseHandler):
    def do_POST(self):
        try:
            payload  = self._body()
            holdings = payload.get("holdings", payload) if isinstance(payload, dict) else payload
            tickers  = [h["ticker"] for h in holdings]
            weights  = np.array([float(h.get("weight") or 1/len(holdings)) for h in holdings])
            weights /= weights.sum()
            rf = 0.052

            all_t = list(set(tickers + ["SPY"]))
            raw   = yf.download(all_t, period="2y", interval="1d",
                                  auto_adjust=True, progress=False)["Close"]
            if isinstance(raw, pd.Series): raw = raw.to_frame(all_t[0])
            raw = raw.dropna(axis=1, how="all").dropna()

            spy_r = raw["SPY"].pct_change().dropna() if "SPY" in raw.columns else None
            pr    = pd.Series(0.0, index=raw.index)
            for i, t in enumerate(tickers):
                if t in raw.columns:
                    pr = pr.add(raw[t].pct_change() * weights[i], fill_value=0)
            pr  = pr.dropna()
            ann = 252
            mu  = float(pr.mean() * ann)
            vol = float(pr.std() * ann**0.5)

            sharpe  = (mu - rf) / vol if vol > 0 else 0
            neg     = pr[pr < 0]
            sortino = (mu - rf) / (neg.std() * ann**0.5) if len(neg) > 0 else 0

            beta, alpha = 1.0, 0.0
            if spy_r is not None:
                aligned = pd.concat([pr, spy_r.rename("s")], axis=1).dropna()
                if len(aligned) > 20:
                    cov   = np.cov(aligned.iloc[:,0], aligned.iloc[:,1])
                    beta  = float(cov[0,1] / cov[1,1]) if cov[1,1] > 0 else 1
                    alpha = float(mu - rf - beta * (spy_r.mean() * ann - rf))

            var95  = float(np.percentile(pr, 5))
            var99  = float(np.percentile(pr, 1))
            cvar95 = float(pr[pr <= var95].mean()) if any(pr <= var95) else var95
            cvar99 = float(pr[pr <= var99].mean()) if any(pr <= var99) else var99
            cum    = (1 + pr).cumprod()
            dd     = (cum - cum.cummax()) / cum.cummax()
            maxdd  = float(dd.min())
            calmar  = mu / abs(maxdd) if maxdd != 0 else 0
            treynor = (mu - rf) / beta if beta != 0 else 0

            self._ok({"beta": round(beta,4), "alpha": round(alpha,6),
                      "sharpe": round(sharpe,4), "sortino": round(sortino,4),
                      "treynor": round(treynor,4),
                      "var95": round(var95,6), "var99": round(var99,6),
                      "cvar95": round(cvar95,6), "cvar99": round(cvar99,6),
                      "calmar": round(calmar,4),
                      "annreturn": round(mu,4), "annvol": round(vol,4),
                      "maxdrawdown": round(maxdd,4)})
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
