import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler
try:
    from api._fmp import fmp
except ImportError:
    from _fmp import fmp


def _ticker_div_fmp(ticker, shares):
    """Try FMP for dividend data."""
    dh  = fmp(f"/api/v3/historical-price-full/stock_dividend/{ticker}")
    if not dh:
        return None
    hist = dh.get("historical", []) if isinstance(dh, dict) else []
    if not hist:
        return None
    hist_sorted = sorted(hist, key=lambda x: x.get("date",""), reverse=True)

    last4 = hist_sorted[:4]
    ann_dps = sum(float(h.get("adjDividend") or h.get("dividend") or 0) for h in last4)
    if ann_dps == 0:
        return None

    dgr = 0.0
    if len(hist_sorted) >= 8:
        cutoff = (datetime.datetime.today() - datetime.timedelta(days=365*4)).strftime("%Y-%m-%d")
        old4   = [h for h in hist_sorted if h.get("date","") <= cutoff][:4]
        old4v  = [float(h.get("adjDividend") or h.get("dividend") or 0) for h in old4]
        ann_o  = sum(old4v)
        if ann_o > 0 and ann_dps > 0:
            dgr = round(((ann_dps/ann_o)**0.25 - 1)*100, 2)

    q     = fmp(f"/api/v3/quote-short/{ticker}")
    price = float((q or [{}])[0].get("price") or 0)
    yield_pct = round(ann_dps/price*100, 2) if price and ann_dps else 0.0

    next_pay = (hist_sorted[0].get("paymentDate") or hist_sorted[0].get("date",""))[:10] if hist_sorted else ""

    return {
        "ticker":       ticker,
        "shares":       shares,
        "annualdps":    round(ann_dps, 4),
        "yieldpct":     yield_pct,
        "dgr":          dgr,
        "nextpayment":  next_pay,
        "annualincome": round(ann_dps * shares, 2),
    }


def _ticker_div_yf(ticker, shares):
    """yfinance fallback for dividend data."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}

        # Get dividend history
        divs = t.dividends
        if divs is None or divs.empty:
            return {
                "ticker": ticker, "shares": shares,
                "annualdps": 0, "yieldpct": 0, "dgr": 0,
                "nextpayment": "", "annualincome": 0,
            }

        # Last 4 dividends for annual DPS
        recent = divs.tail(4)
        ann_dps = float(recent.sum())

        # DGR: compare last 4 vs 4 from ~4 years ago
        dgr = 0.0
        if len(divs) >= 8:
            cutoff = datetime.datetime.today() - datetime.timedelta(days=365*4)
            old = divs[divs.index < cutoff.strftime("%Y-%m-%d")].tail(4)
            old_sum = float(old.sum())
            if old_sum > 0 and ann_dps > 0:
                dgr = round(((ann_dps/old_sum)**0.25 - 1)*100, 2)

        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        yield_pct = round(ann_dps/price*100, 2) if price and ann_dps else 0.0

        # Next ex-dividend date
        next_pay = ""
        ex_date = info.get("exDividendDate")
        if ex_date:
            try:
                next_pay = datetime.datetime.fromtimestamp(ex_date).strftime("%Y-%m-%d")
            except Exception:
                pass

        return {
            "ticker":       ticker,
            "shares":       shares,
            "annualdps":    round(ann_dps, 4),
            "yieldpct":     yield_pct,
            "dgr":          dgr,
            "nextpayment":  next_pay,
            "annualincome": round(ann_dps * shares, 2),
        }
    except Exception as e:
        return {
            "ticker": ticker, "shares": shares,
            "annualdps": 0, "yieldpct": 0, "dgr": 0,
            "nextpayment": "", "annualincome": 0, "_err": str(e),
        }


def _ticker_div(ticker, shares):
    """Try FMP first, fall back to yfinance."""
    try:
        result = _ticker_div_fmp(ticker, shares)
        if result:
            return result
    except Exception:
        pass
    return _ticker_div_yf(ticker, shares)


class handler(BaseHandler):
    def do_POST(self):
        try:
            payload  = self._body()
            holdings = payload if isinstance(payload, list) else payload.get("holdings",[])
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(_ticker_div, h["ticker"], h["shares"]): h["ticker"]
                        for h in holdings}
                results = [fut.result() for fut in as_completed(futs)]
            results.sort(key=lambda r: -r["annualincome"])
            monthly = {}
            for r in results:
                mo = round(r["annualincome"]/12, 2)
                for i in range(12):
                    monthly[i+1] = round(monthly.get(i+1,0)+mo, 2)
            self._ok({"results": results, "monthlyincome": monthly})
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
