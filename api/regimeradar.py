try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

try:
    from core.regimeradar import (
        get_regime_history, portfolio_regime_performance, interpret_regime,
    )
    from core.data import get_daily_returns
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.regimeradar import (
        get_regime_history, portfolio_regime_performance, interpret_regime,
    )
    from core.data import get_daily_returns

import numpy as np
import pandas as pd


class handler(BaseHandler):
    def do_GET(self):
        qs = self._qs()
        period = qs.get("period", "5y")
        method = qs.get("method", "rule_based")

        try:
            history = get_regime_history(period, method)
            if "error" in history and not history.get("dates"):
                return self._err(history["error"], 500)

            msgs = interpret_regime(history)

            self._ok({
                "current_regime": history.get("current_regime", ""),
                "confidence": None,
                "metrics": None,
                "history": {
                    "dates": history.get("dates", []),
                    "regimes": history.get("regimes", []),
                    "regime_summary": history.get("regime_summary", {}),
                },
                "interpretations": msgs,
            })
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))

    def do_POST(self):
        try:
            body = self._body()
            holdings = body.get("holdings", [])
            period = body.get("period", "5y")
            method = body.get("method", "rule_based")

            history = get_regime_history(period, method)
            if "error" in history and not history.get("dates"):
                return self._err(history["error"], 500)

            result = {
                "current_regime": history.get("current_regime", ""),
                "history": {
                    "dates": history.get("dates", []),
                    "regimes": history.get("regimes", []),
                    "regime_summary": history.get("regime_summary", {}),
                },
            }

            portfolio_perf = None
            if holdings:
                tickers = [h["ticker"] for h in holdings]
                weights = np.array([h["weight"] for h in holdings])
                weights = weights / weights.sum()

                returns_df = get_daily_returns(tickers, period)
                if not returns_df.empty:
                    available = [t for t in tickers if t.upper() in returns_df.columns]
                    if available:
                        w = np.array([weights[i] for i, t in enumerate(tickers) if t.upper() in returns_df.columns])
                        w = w / w.sum()
                        port_returns = (returns_df[available] * w).sum(axis=1)
                        portfolio_perf = portfolio_regime_performance(port_returns, history)
                        # Clean numpy types
                        result["portfolio_performance"] = _clean(portfolio_perf)

            msgs = interpret_regime(history, portfolio_perf)
            result["interpretations"] = msgs

            self._ok(result)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))


def _clean(obj):
    if isinstance(obj, (np.floating, np.float64)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    return obj
