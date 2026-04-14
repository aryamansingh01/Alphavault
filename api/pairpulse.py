try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

try:
    from core.pairpulse import analyze_pair, analyze_portfolio_pairs
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.pairpulse import analyze_pair, analyze_portfolio_pairs

import numpy as np


class handler(BaseHandler):
    def do_GET(self):
        qs = self._qs()
        ticker_a = qs.get("ticker_a", "").upper()
        ticker_b = qs.get("ticker_b", "").upper()
        period = qs.get("period", "2y")

        if not ticker_a or not ticker_b:
            return self._err("ticker_a and ticker_b required", 400)

        try:
            result = analyze_pair(ticker_a, ticker_b, period)
            self._ok(_clean(result))
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))

    def do_POST(self):
        try:
            body = self._body()
            tickers = body.get("tickers", [])
            period = body.get("period", "2y")
            significance = body.get("significance", 0.05)

            if not tickers or len(tickers) < 2:
                return self._err("At least 2 tickers required", 400)

            result = analyze_portfolio_pairs(tickers, period, significance)
            self._ok(_clean(result))
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))


def _clean(obj):
    if isinstance(obj, (np.floating, np.float64)):
        v = float(obj)
        return None if (v != v) else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and obj != obj:
        return None
    return obj
