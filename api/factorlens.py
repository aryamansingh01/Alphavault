try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

try:
    from core.data import get_daily_returns
    from core.factorlens import full_factor_analysis
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.data import get_daily_returns
    from core.factorlens import full_factor_analysis

import numpy as np
import pandas as pd


class handler(BaseHandler):
    def do_POST(self):
        try:
            body = self._body()
            holdings = body.get("holdings", [])
            period = body.get("period", "3y")

            if not holdings:
                return self._err("holdings required", 400)

            tickers = [h["ticker"] for h in holdings]
            weights = np.array([h["weight"] for h in holdings])
            weights = weights / weights.sum()

            returns_df = get_daily_returns(tickers, period)
            if returns_df.empty:
                return self._err("Could not fetch return data for tickers", 404)

            # Compute weighted portfolio returns
            available = [t for t in tickers if t.upper() in returns_df.columns]
            if not available:
                return self._err("No valid return data found", 404)

            w = np.array([weights[i] for i, t in enumerate(tickers) if t.upper() in returns_df.columns])
            w = w / w.sum()
            port_returns = (returns_df[available] * w).sum(axis=1)

            result = full_factor_analysis(port_returns, period)

            # Make JSON-serializable
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

            self._ok(_clean(result))
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
