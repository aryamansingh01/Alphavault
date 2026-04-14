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
            if len(tickers) < 2:
                return self._err("Need at least 2 tickers", 400)
            raw = yf.download(tickers, period="1y", interval="1d",
                               auto_adjust=True, progress=False)["Close"]
            if isinstance(raw, pd.Series):
                raw = raw.to_frame(tickers[0])
            raw  = raw.dropna(axis=1, how="all").dropna()
            rets = raw.pct_change().dropna()
            cols = list(rets.columns)
            mat  = [[round(float(v), 4) if v == v else 0.0 for v in row]
                    for row in rets.corr().values.tolist()]
            self._ok({"tickers": cols, "matrix": mat})
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
