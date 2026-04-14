try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

try:
    from core.data import get_ohlcv
    from core.chartbrain import compute_all_indicators
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.data import get_ohlcv
    from core.chartbrain import compute_all_indicators


class handler(BaseHandler):
    def do_GET(self):
        qs = self._qs()
        ticker = qs.get("ticker", "").upper()
        if not ticker:
            return self._err("ticker required", 400)

        period = qs.get("period", "1y")
        indicators_param = qs.get("indicators", "all")

        try:
            df = get_ohlcv(ticker, period)
            if df.empty:
                return self._err(f"No data found for {ticker}", 404)

            all_ind = compute_all_indicators(df)

            # Filter indicators if specific ones requested
            if indicators_param != "all":
                requested = {i.strip().lower() for i in indicators_param.split(",")}
                filtered = {}
                for key in list(all_ind.keys()):
                    if key in ("signals", "support_resistance"):
                        continue
                    short = key.replace("_", "")
                    if key in requested or short in requested:
                        filtered[key] = all_ind[key]
                indicators = filtered if filtered else all_ind
            else:
                indicators = {k: v for k, v in all_ind.items()
                              if k not in ("signals", "support_resistance")}

            dates = [d.strftime("%Y-%m-%d") for d in df.index]
            ohlcv = {}
            for col in ["open", "high", "low", "close", "volume"]:
                if col in df.columns:
                    ohlcv[col] = [None if (v is None or (isinstance(v, float) and v != v)) else v
                                  for v in df[col].tolist()]

            self._ok({
                "ticker": ticker,
                "period": period,
                "dates": dates,
                "ohlcv": ohlcv,
                "indicators": indicators,
                "signals": all_ind.get("signals", []),
                "support_resistance": all_ind.get("support_resistance", {}),
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            self._err(str(e))
