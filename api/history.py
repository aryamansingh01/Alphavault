"""Combined history + benchmark endpoint
   GET  /api/history?tickers=AAPL,MSFT&period=1y  — price history
   POST /api/history  body: {"holdings":[...], "period":"1y"}  — benchmark comparison
"""
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler
try:
    from api._fmp import fmp
except ImportError:
    from _fmp import fmp

BENCH = ["SPY", "QQQ", "DIA"]


def _fetch_fmp(ticker, from_date):
    try:
        raw = fmp(f"/api/v3/historical-price-full/{ticker}", serietype="line",
                  **{"from": from_date})
        if not raw or not isinstance(raw, dict): return None
        hist = raw.get("historical", [])
        if not hist: return None
        hist = list(reversed(hist))
        return pd.Series([h["close"] for h in hist], index=pd.to_datetime([h["date"] for h in hist]))
    except Exception:
        return None


def _fetch_yf(ticker, period):
    try:
        df = yf.download(ticker, period=period, interval="1d", auto_adjust=True, progress=False)
        if df is None or df.empty: return None
        closes = df["Close"]
        if hasattr(closes, "columns"): closes = closes.iloc[:, 0]
        return closes.dropna()
    except Exception:
        return None


class handler(BaseHandler):
    def do_GET(self):
        qs      = self._qs()
        raw     = qs.get("tickers", "SPY,QQQ,DIA")
        period  = qs.get("period", "1y")
        tickers = [t.strip().upper() for t in raw.split(",") if t.strip()]
        period_days = {"1m":30,"3m":90,"6m":180,"ytd":180,"1y":365,"3y":1095,"5y":1825}
        days = period_days.get(period, 365)
        from_date = (datetime.today() - timedelta(days=days)).strftime("%Y-%m-%d")
        yf_map = {"1m":"1mo","3m":"3mo","6m":"6mo","ytd":"ytd","1y":"1y","3y":"3y","5y":"5y"}
        yf_period = yf_map.get(period, "1y")

        try:
            series = {}
            def fetch_one(t):
                s = _fetch_fmp(t, from_date)
                if s is None or len(s) < 5: s = _fetch_yf(t, yf_period)
                return t, s

            with ThreadPoolExecutor(max_workers=len(tickers)) as ex:
                futs = {ex.submit(fetch_one, t): t for t in tickers}
                for fut in as_completed(futs):
                    t, s = fut.result()
                    if s is not None and len(s) > 5: series[t] = s

            if not series: return self._err("No price history returned")
            df = pd.DataFrame(series).dropna()
            normed = (df / df.iloc[0] * 100).round(4)
            self._ok({
                "dates":   [str(d.date()) if hasattr(d, 'date') else str(d)[:10] for d in normed.index],
                "series":  {t: normed[t].tolist() for t in normed.columns},
                "tickers": list(normed.columns),
            })
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))

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
                if b in raw.columns: result[b.lower()] = _m(raw[b])

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
