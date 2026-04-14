import math
import yfinance as yf
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler
from urllib.parse import urlparse, parse_qs


def _safe_float(v):
    """Convert to float, return 0 for NaN/None."""
    try:
        f = float(v)
        return 0.0 if math.isnan(f) else f
    except (TypeError, ValueError):
        return 0.0


class handler(BaseHandler):
    def do_GET(self):
        qs     = parse_qs(urlparse(self.path).query)
        ticker = (qs.get("ticker") or qs.get("symbol") or [""])[0].upper().strip()
        if not ticker:
            return self._err("ticker required", 400)
        try:
            t = yf.Ticker(ticker)
            try:
                df = t.insider_transactions
            except Exception:
                df = None

            rows       = []
            buy_value  = 0.0
            sell_value = 0.0
            buy_count  = 0
            sell_count = 0

            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    # yfinance columns: Text, Transaction, Insider, Position, Shares, Value, Start Date
                    text = str(row.get("Text", "") or "")
                    txn  = str(row.get("Transaction", "") or "")
                    desc = text or txn  # Text has the description, Transaction is often empty

                    shares = int(_safe_float(row.get("Shares", 0)))
                    value  = _safe_float(row.get("Value", 0))

                    is_buy = any(k in desc.lower() for k in ("purchase", "buy", "acquisition", "exercise"))
                    is_gift = "gift" in desc.lower()

                    if is_buy:
                        buy_value  += value
                        buy_count  += 1
                    elif not is_gift:
                        sell_value += value
                        sell_count += 1

                    rows.append({
                        "date":        str(row.get("Start Date", ""))[:10],
                        "executive":   str(row.get("Insider", "") or ""),
                        "title":       str(row.get("Position", "") or ""),
                        "transaction": desc or ("Purchase" if is_buy else "Sale" if not is_gift else "Gift"),
                        "shares":      shares,
                        "value":       value,
                    })

            self._ok({
                "symbol":     ticker,
                "buyCount":   buy_count,
                "sellCount":  sell_count,
                "buyValue":   buy_value,
                "sellValue":  sell_value,
                "transactions": rows,
            })
        except Exception as e:
            self._err(str(e))
