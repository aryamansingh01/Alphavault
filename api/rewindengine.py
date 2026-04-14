try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

try:
    from core.rewindengine import run_backtest, compare_strategies, list_strategies
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.rewindengine import run_backtest, compare_strategies, list_strategies

import numpy as np


class handler(BaseHandler):
    def do_GET(self):
        self._ok({"strategies": list_strategies()})

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path.endswith("/compare"):
            return self._handle_compare()
        return self._handle_backtest()

    def _handle_backtest(self):
        try:
            body = self._body()
            ticker = body.get("ticker", "").upper()
            strategy = body.get("strategy", "buy_and_hold")
            params = body.get("params")
            period = body.get("period", "5y")
            capital = body.get("initial_capital", 100000)
            commission = body.get("commission_bps", 10)
            slippage = body.get("slippage_bps", 5)

            if not ticker:
                return self._err("ticker required", 400)

            result = run_backtest(ticker, strategy, params, period, capital, commission, slippage)

            if not result.get("valid"):
                return self._err(result.get("error", "Backtest failed"), 500)

            # Downsample equity curve if too long
            ec = result.get("equity_curve", [])
            dates = result.get("dates", [])
            dd = result.get("drawdown_curve", [])
            if len(ec) > 500:
                step = len(ec) // 500
                result["equity_curve"] = ec[::step]
                result["dates"] = dates[::step]
                result["drawdown_curve"] = dd[::step]

            self._ok(_clean(result))
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))

    def _handle_compare(self):
        try:
            body = self._body()
            ticker = body.get("ticker", "").upper()
            configs = body.get("strategies", [])
            period = body.get("period", "5y")

            if not ticker:
                return self._err("ticker required", 400)
            if not configs:
                return self._err("strategies list required", 400)

            result = compare_strategies(ticker, configs, period)
            self._ok(_clean(result))
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))


def _clean(obj):
    if isinstance(obj, (np.floating, np.float64)):
        v = float(obj)
        return None if v != v else v
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float):
        if obj != obj:
            return None
        if obj == float("inf") or obj == float("-inf"):
            return None
    return obj
