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
            payload = self._body()
            tickers = payload if isinstance(payload, list) else payload.get("tickers", [])
            raw = yf.download(tickers, period="5y", interval="1d",
                               auto_adjust=True, progress=False)["Close"]
            if isinstance(raw, pd.Series):
                raw = raw.to_frame(tickers[0])
            results = []
            for t in tickers:
                if t not in raw.columns: continue
                p = raw[t].dropna()
                if len(p) < 10: continue
                peak  = p.cummax()
                dd    = (p - peak) / peak
                md    = float(dd.min())
                dur   = int((dd < -0.001).sum())

                min_ts = dd.idxmin()
                rec    = int((p.index[-1] - min_ts).days) if pd.notna(min_ts) else 0

                ann   = float((p.iloc[-1]/p.iloc[0])**(252/len(p)) - 1) if len(p) > 1 else 0
                calmar = ann / abs(md) if md != 0 else 0
                results.append({
                    "ticker":      t,
                    "maxdrawdown": round(md, 4),
                    "duration":    dur,
                    "recovery":    rec,
                    "calmar":      round(calmar, 3),
                })
            results.sort(key=lambda x: x["maxdrawdown"])
            self._ok({"results": results})
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
