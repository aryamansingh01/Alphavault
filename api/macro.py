import os
import json
import traceback
import urllib.request
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler
try:
    from api._fmp import fmp
except ImportError:
    from _fmp import fmp

FRED_KEY = os.environ.get("FRED_API_KEY", "")


def _yf_price(symbol):
    try:
        import yfinance as yf
        return yf.Ticker(symbol).fast_info.last_price
    except Exception:
        return None


def _yf_change_pct(symbol):
    try:
        import yfinance as yf
        fi = yf.Ticker(symbol).fast_info
        if fi.last_price and fi.previous_close:
            return round((fi.last_price - fi.previous_close) / fi.previous_close * 100, 2)
    except Exception:
        pass
    return None


def _fred_latest(series_id):
    """Fetch latest value from FRED API (free)."""
    if not FRED_KEY:
        return None
    try:
        url = (f"https://api.stlouisfed.org/fred/series/observations"
               f"?series_id={series_id}&api_key={FRED_KEY}"
               f"&file_type=json&sort_order=desc&limit=1")
        req = urllib.request.Request(url, headers={"User-Agent": "AlphaVault/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
            obs = data.get("observations", [])
            if obs and obs[0].get("value") != ".":
                return float(obs[0]["value"])
    except Exception:
        pass
    return None


def _latest(arr):
    if not arr:
        return None
    return sorted(arr, key=lambda x: x.get("date", ""))[-1].get("value")


class handler(BaseHandler):
    def do_GET(self):
        today  = datetime.today().strftime("%Y-%m-%d")
        from6m = (datetime.today() - timedelta(days=200)).strftime("%Y-%m-%d")
        from1y = (datetime.today() - timedelta(days=400)).strftime("%Y-%m-%d")

        try:
            calls = {
                # FMP calls (may return None on free tier)
                "fmp_treasury": lambda: fmp("/api/v4/treasury", **{"from": from6m, "to": today}),
                "fmp_fed":      lambda: fmp("/api/v4/economic", name="federalFunds", **{"from": from6m, "to": today}),
                "fmp_cpi":      lambda: fmp("/api/v4/economic", name="CPI", **{"from": from1y, "to": today}),
                "fmp_gdp":      lambda: fmp("/api/v4/economic", name="realGDP", **{"from": "2023-01-01", "to": today}),
                "fmp_unemp":    lambda: fmp("/api/v4/economic", name="unemploymentRate", **{"from": from6m, "to": today}),
                "fmp_vix":      lambda: fmp("/api/v3/quote/%5EVIX"),
                "fmp_gold":     lambda: fmp("/api/v3/quote/GCUSD"),
                "fmp_oil":      lambda: fmp("/api/v3/quote/CLUSD"),
                "fmp_dxy":      lambda: fmp("/api/v3/quote/DX-Y.NYB"),

                # yfinance fallbacks (always free)
                "yf_vix":       lambda: _yf_price("^VIX"),
                "yf_vix_chg":   lambda: _yf_change_pct("^VIX"),
                "yf_gold":      lambda: _yf_price("GC=F"),
                "yf_oil":       lambda: _yf_price("CL=F"),
                "yf_dxy":       lambda: _yf_price("DX-Y.NYB"),
                "yf_t10y":      lambda: _yf_price("^TNX"),
                "yf_t2y":       lambda: _yf_price("^IRX"),

                # FRED fallbacks (free with API key)
                "fred_fedfunds": lambda: _fred_latest("FEDFUNDS"),
                "fred_cpi":      lambda: _fred_latest("CPIAUCSL"),
                "fred_unrate":   lambda: _fred_latest("UNRATE"),
                "fred_gdp":      lambda: _fred_latest("A191RL1Q225SBEA"),
                "fred_m2":       lambda: _fred_latest("M2SL"),
                "fred_hy":       lambda: _fred_latest("BAMLH0A0HYM2"),
            }

            results = {}
            with ThreadPoolExecutor(max_workers=20) as ex:
                futs = {ex.submit(v): k for k, v in calls.items()}
                for fut in as_completed(futs):
                    k = futs[fut]
                    try:
                        results[k] = fut.result()
                    except Exception:
                        results[k] = None

            # ── Treasury yields ──
            treas = sorted(results.get("fmp_treasury") or [], key=lambda x: x.get("date", ""))
            treas_latest = treas[-1] if treas else {}
            t10y = treas_latest.get("year10") or results.get("yf_t10y")
            t2y  = treas_latest.get("year2") or results.get("yf_t2y")
            yc   = round(t10y - t2y, 4) if (t10y and t2y) else None

            # ── Economic data: FMP → FRED fallback ──
            fed_funds = _latest(results.get("fmp_fed") or []) or results.get("fred_fedfunds")

            # CPI: FRED returns index level (e.g. 327), compute YoY% would need 2 obs
            # For now just show the FRED value if available, or FMP
            fmp_cpi = _latest(results.get("fmp_cpi") or [])
            fred_cpi_raw = results.get("fred_cpi")
            cpi_val = fmp_cpi  # FMP already gives YoY%
            # If no FMP data, we can't easily compute YoY from a single FRED observation
            # So we'll show FRED raw CPI index if nothing else
            if cpi_val is None and fred_cpi_raw:
                cpi_val = fred_cpi_raw  # This will be the index level, not YoY%

            unemp = _latest(results.get("fmp_unemp") or []) or results.get("fred_unrate")

            # GDP
            fmp_gdp = results.get("fmp_gdp") or []
            gdp_arr = sorted(fmp_gdp, key=lambda x: x.get("date", "")) if fmp_gdp else []
            gdp_growth = None
            if len(gdp_arr) >= 2:
                prev = gdp_arr[-2].get("value", 0) or 1
                curr = gdp_arr[-1].get("value", 0) or 0
                gdp_growth = round((curr - prev) / prev * 100, 2) if prev else None
            if gdp_growth is None:
                gdp_growth = results.get("fred_gdp")  # FRED gives annualized QoQ directly

            # M2
            m2_raw = results.get("fred_m2")
            m2 = round(m2_raw / 1000, 2) if m2_raw else None  # Convert billions to trillions

            # HY Credit Spread
            hy_spread = results.get("fred_hy")

            # ── Market quotes: FMP → yfinance ──
            def _fmp_quote_val(key, field="price"):
                data = results.get(key) or [{}]
                q = data[0] if isinstance(data, list) and data else {}
                return q.get(field)

            vix  = _fmp_quote_val("fmp_vix") or results.get("yf_vix")
            vix_chg = _fmp_quote_val("fmp_vix", "changesPercentage") or results.get("yf_vix_chg")
            gold = _fmp_quote_val("fmp_gold") or results.get("yf_gold")
            oil  = _fmp_quote_val("fmp_oil") or results.get("yf_oil")
            dxy  = _fmp_quote_val("fmp_dxy") or results.get("yf_dxy")

            source = "FMP" if _fmp_quote_val("fmp_vix") else "yfinance+FRED"

            self._ok({
                "vix":            vix,
                "vixChange":      vix_chg,
                "t10y":           t10y,
                "t2y":            t2y,
                "yieldCurve":     yc,
                "gold":           gold,
                "oil":            oil,
                "dxy":            dxy,
                "fedFundsRate":   fed_funds,
                "cpi":            cpi_val,
                "coreCpi":        None,
                "gdpGrowth":      gdp_growth,
                "unemployment":   unemp,
                "m2":             m2,
                "hyCreditSpread": hy_spread,
                "_note": f"Source: {source} | {today}",
            })
        except Exception as e:
            traceback.print_exc()
            self._err(str(e))
