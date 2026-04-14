"""Combined risk endpoint: drawdown + stress_test
   POST /api/risk  body: {"type":"drawdown", "tickers":["AAPL","MSFT"]}
   POST /api/risk  body: {"type":"stress", "holdings":[...]}
"""
import yfinance as yf
import numpy as np
import pandas as pd
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler


SCENARIOS = [
    {"name": "2008 Financial Crisis", "type": "hist", "spy": -0.565},
    {"name": "2020 COVID Crash",       "type": "hist", "spy": -0.340},
    {"name": "2022 Rate Hike Bear",    "type": "hist", "spy": -0.252},
    {"name": "2000 Dot-Com Bust",      "type": "hist", "spy": -0.491},
    {"name": "2018 Q4 Correction",     "type": "hist", "spy": -0.196},
    {"name": "Rising Rates +2%",       "type": "rate",      "shock": 0.02},
    {"name": "Tech Selloff -40%",      "type": "sector",    "shock": -0.40, "sector": "Technology"},
    {"name": "Inflation Spike +5%",    "type": "inflation", "shock": 0.05},
]
SECTORS = {"AAPL":"Technology","MSFT":"Technology","NVDA":"Technology","GOOGL":"Technology",
           "META":"Technology","AMZN":"Consumer","TSLA":"Consumer","JNJ":"Healthcare",
           "UNH":"Healthcare","JPM":"Financials","XOM":"Energy","CVX":"Energy",
           "SPY":"Diversified","QQQ":"Technology","VTI":"Diversified",
           "BND":"Bonds","GLD":"Commodities","IBIT":"Crypto"}


def _do_drawdown(payload):
    tickers = payload if isinstance(payload, list) else payload.get("tickers", [])
    raw = yf.download(tickers, period="5y", interval="1d", auto_adjust=True, progress=False)["Close"]
    if isinstance(raw, pd.Series):
        raw = raw.to_frame(tickers[0])
    results = []
    for t in tickers:
        if t not in raw.columns: continue
        p = raw[t].dropna()
        if len(p) < 10: continue
        peak = p.cummax(); dd = (p - peak) / peak
        md = float(dd.min()); dur = int((dd < -0.001).sum())
        min_ts = dd.idxmin()
        rec = int((p.index[-1] - min_ts).days) if pd.notna(min_ts) else 0
        ann = float((p.iloc[-1]/p.iloc[0])**(252/len(p)) - 1) if len(p) > 1 else 0
        calmar = ann / abs(md) if md != 0 else 0
        results.append({"ticker": t, "maxdrawdown": round(md, 4), "duration": dur,
                        "recovery": rec, "calmar": round(calmar, 3)})
    results.sort(key=lambda x: x["maxdrawdown"])
    return {"results": results}


def _do_stress(payload):
    holdings = payload.get("holdings", []) if isinstance(payload, dict) else []
    tickers = [h["ticker"] for h in holdings]
    weights = np.array([float(h.get("weight", 1/max(1, len(holdings)))) for h in holdings])
    if weights.sum() > 0: weights /= weights.sum()

    betas = {t: 1.0 for t in tickers}
    try:
        all_t = list(set(tickers + ["SPY"]))
        raw = yf.download(all_t, period="1y", interval="1d", auto_adjust=True, progress=False)["Close"]
        if isinstance(raw, pd.Series): raw = raw.to_frame(all_t[0])
        spy_r = raw["SPY"].pct_change().dropna() if "SPY" in raw.columns else None
        for t in tickers:
            if t in raw.columns and spy_r is not None:
                al = pd.concat([raw[t].pct_change(), spy_r], axis=1).dropna()
                if len(al) > 20:
                    c = np.cov(al.iloc[:, 0], al.iloc[:, 1])
                    betas[t] = float(c[0,1] / c[1,1]) if c[1,1] > 0 else 1
    except Exception: pass

    results = []
    for sc in SCENARIOS:
        st = sc["type"]
        if st == "hist":
            imp = sum(w * sc["spy"] * betas.get(tk, 1) for w, tk in zip(weights, tickers))
        elif st == "rate":
            imp = sum(w * (-0.05 * sc["shock"] * betas.get(tk, 1)) for w, tk in zip(weights, tickers))
        elif st == "sector":
            imp = sum(w * (sc["shock"] if SECTORS.get(tk, "Other") == sc["sector"] else -0.02)
                      for w, tk in zip(weights, tickers))
        elif st == "inflation":
            imp = sum(w * (-0.03 * sc["shock"]) for w, tk in zip(weights, tickers))
        else: imp = 0
        results.append({"scenario": sc["name"], "impact": round(float(imp), 4), "spy_ref": sc.get("spy")})
    return {"results": results, "betas": betas}


class handler(BaseHandler):
    def do_POST(self):
        try:
            payload = self._body()
            rtype = payload.get("type", "drawdown") if isinstance(payload, dict) else "drawdown"
            if rtype == "stress":
                self._ok(_do_stress(payload))
            else:
                self._ok(_do_drawdown(payload))
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
