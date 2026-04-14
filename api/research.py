"""Combined research endpoint: insider + analyst
   GET /api/research?ticker=AAPL&type=insider
   GET /api/research?ticker=AAPL&type=analyst
"""
import math
import yfinance as yf
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler
from urllib.parse import urlparse, parse_qs


def _safe_float(v):
    try:
        f = float(v)
        return 0.0 if math.isnan(f) else f
    except (TypeError, ValueError):
        return 0.0


def _get_insider(ticker):
    t = yf.Ticker(ticker)
    try:
        df = t.insider_transactions
    except Exception:
        df = None

    rows, buy_value, sell_value, buy_count, sell_count = [], 0.0, 0.0, 0, 0

    if df is not None and not df.empty:
        for _, row in df.iterrows():
            text = str(row.get("Text", "") or "")
            txn  = str(row.get("Transaction", "") or "")
            desc = text or txn
            shares = int(_safe_float(row.get("Shares", 0)))
            value  = _safe_float(row.get("Value", 0))
            is_buy = any(k in desc.lower() for k in ("purchase", "buy", "acquisition", "exercise"))
            is_gift = "gift" in desc.lower()
            if is_buy:
                buy_value += value; buy_count += 1
            elif not is_gift:
                sell_value += value; sell_count += 1
            rows.append({
                "date": str(row.get("Start Date", ""))[:10],
                "executive": str(row.get("Insider", "") or ""),
                "title": str(row.get("Position", "") or ""),
                "transaction": desc or ("Purchase" if is_buy else "Sale" if not is_gift else "Gift"),
                "shares": shares, "value": value,
            })

    return {"symbol": ticker, "buyCount": buy_count, "sellCount": sell_count,
            "buyValue": buy_value, "sellValue": sell_value, "transactions": rows}


def _get_analyst(ticker):
    t = yf.Ticker(ticker)
    try:
        pt = t.analyst_price_targets or {}
    except Exception:
        pt = {}

    try:
        rec_df = t.recommendations
    except Exception:
        rec_df = None

    consensus_score = None
    if rec_df is not None and not rec_df.empty:
        latest = rec_df.iloc[-1] if hasattr(rec_df, 'iloc') else {}
        try:
            sb, b, h, s, ss = int(latest.get("strongBuy",0)), int(latest.get("buy",0)), int(latest.get("hold",0)), int(latest.get("sell",0)), int(latest.get("strongSell",0))
            total = sb + b + h + s + ss
            if total: consensus_score = (sb*1 + b*2 + h*3 + s*4 + ss*5) / total
        except Exception:
            pass

    try:
        ud_df = t.upgrades_downgrades
    except Exception:
        ud_df = None

    grades = []
    if ud_df is not None and not ud_df.empty:
        ud_df = ud_df.sort_index(ascending=False).head(20)
        for idx, row in ud_df.iterrows():
            grades.append({
                "date": str(idx)[:10], "firm": str(row.get("Firm", "")),
                "toGrade": str(row.get("ToGrade", "")), "fromGrade": str(row.get("FromGrade", "")),
                "action": str(row.get("Action", "")), "priceTarget": None,
            })

    return {"symbol": ticker, "priceTargetLow": pt.get("low"), "priceTargetAvg": pt.get("mean") or pt.get("median"),
            "priceTargetHigh": pt.get("high"), "priceTargetCurr": pt.get("current"),
            "consensusScore": consensus_score, "ratingChanges": grades}


class handler(BaseHandler):
    def do_GET(self):
        qs     = parse_qs(urlparse(self.path).query)
        ticker = (qs.get("ticker") or qs.get("symbol") or [""])[0].upper().strip()
        rtype  = (qs.get("type") or ["insider"])[0].lower()
        if not ticker:
            return self._err("ticker required", 400)
        try:
            if rtype == "analyst":
                self._ok(_get_analyst(ticker))
            else:
                self._ok(_get_insider(ticker))
        except Exception as e:
            self._err(str(e))
