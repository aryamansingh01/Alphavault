import yfinance as yf
import numpy as np
import pandas as pd
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

BENCH = ["SPY", "QQQ", "DIA"]


class handler(BaseHandler):
    def do_POST(self):
        try:
            p        = self._body()
            holdings = p.get("holdings", []) if isinstance(p, dict) else []
            period   = p.get("period", "1y")
            tickers  = [h["ticker"] for h in holdings]
            weights  = np.array([float(h.get("weight", 1/max(1, len(holdings)))) for h in holdings])
            if weights.sum() > 0: weights /= weights.sum()

            all_t = list(set(tickers + BENCH))
            raw   = yf.download(all_t, period=period, interval="1d",
                                  auto_adjust=True, progress=False)["Close"]
            if isinstance(raw, pd.Series): raw = raw.to_frame(all_t[0])
            raw   = raw.dropna(axis=1, how="all").ffill().dropna()

            port = pd.Series(0.0, index=raw.index)
            for i, t in enumerate(tickers):
                if t in raw.columns:
                    port = port.add(raw[t] / raw[t].iloc[0] * weights[i], fill_value=0)

            def _m(s):
                r   = s.pct_change().dropna()
                tot = float(s.iloc[-1] / s.iloc[0] - 1)
                ann = float((1 + tot)**(252 / max(1, len(s))) - 1)
                vol = float(r.std() * 252**0.5)
                sh  = (ann - 0.052) / vol if vol > 0 else 0
                cum = s / s.iloc[0]; dd = (cum - cum.cummax()) / cum.cummax()
                bm  = float(r.resample("ME").sum().max()) if len(r) > 20 else 0
                wm  = float(r.resample("ME").sum().min()) if len(r) > 20 else 0
                return {"total": round(tot,4), "annualized": round(ann,4),
                        "vol": round(vol,4), "sharpe": round(sh,3),
                        "maxdrawdown": round(float(dd.min()),4),
                        "best_month": round(bm,4), "worst_month": round(wm,4)}

            result = {"portfolio": _m(port), "chart": {}}
            for b in BENCH:
                if b in raw.columns:
                    result[b.lower()] = _m(raw[b])

            stride = max(1, len(raw) // 100)
            result["chart"]["dates"] = [str(d.date()) for d in raw.index[::stride]]
            result["chart"]["portfolio"] = [round(float(v),4) for v in (port/port.iloc[0]*100).iloc[::stride]]
            for b in BENCH:
                if b in raw.columns:
                    result["chart"][b.lower()] = [round(float(v),4)
                                                   for v in (raw[b]/raw[b].iloc[0]*100).iloc[::stride]]
            self._ok(result)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
