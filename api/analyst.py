import yfinance as yf
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler
from urllib.parse import urlparse, parse_qs


class handler(BaseHandler):
    def do_GET(self):
        qs     = parse_qs(urlparse(self.path).query)
        ticker = (qs.get("ticker") or qs.get("symbol") or [""])[0].upper().strip()
        if not ticker:
            return self._err("ticker required", 400)
        try:
            t = yf.Ticker(ticker)

            # price targets
            try:
                pt = t.analyst_price_targets or {}
            except Exception:
                pt = {}
            low  = pt.get("low")
            avg  = pt.get("mean") or pt.get("median")
            high = pt.get("high")
            curr = pt.get("current")

            # consensus / recommendations
            try:
                rec_df = t.recommendations
            except Exception:
                rec_df = None

            consensus_score = None
            if rec_df is not None and not rec_df.empty:
                latest = rec_df.iloc[-1] if hasattr(rec_df, 'iloc') else {}
                try:
                    sb = int(latest.get("strongBuy",  0))
                    b  = int(latest.get("buy",        0))
                    h  = int(latest.get("hold",       0))
                    s  = int(latest.get("sell",       0))
                    ss = int(latest.get("strongSell", 0))
                    total = sb + b + h + s + ss
                    if total:
                        consensus_score = (sb*1 + b*2 + h*3 + s*4 + ss*5) / total
                except Exception:
                    pass

            # upgrades / downgrades
            try:
                ud_df = t.upgrades_downgrades
            except Exception:
                ud_df = None

            grades = []
            if ud_df is not None and not ud_df.empty:
                ud_df = ud_df.sort_index(ascending=False).head(20)
                for idx, row in ud_df.iterrows():
                    grades.append({
                        "date":        str(idx)[:10] if hasattr(idx, "__str__") else "",
                        "firm":        str(row.get("Firm", "")),
                        "toGrade":     str(row.get("ToGrade", "")),
                        "fromGrade":   str(row.get("FromGrade", "")),
                        "action":      str(row.get("Action", "")),
                        "priceTarget": None,
                    })

            self._ok({
                "symbol":          ticker,
                "priceTargetLow":  low,
                "priceTargetAvg":  avg,
                "priceTargetHigh": high,
                "priceTargetCurr": curr,
                "consensusScore":  consensus_score,
                "ratingChanges":   grades,
            })
        except Exception as e:
            self._err(str(e))
