import json
import yfinance as yf
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler
from urllib.parse import urlparse, parse_qs


class handler(BaseHandler):
    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        ticker = (qs.get("ticker") or qs.get("symbol") or [""])[0].upper().strip()
        if not ticker:
            return self._err("ticker required", 400)
        try:
            t = yf.Ticker(ticker)
            info = t.info
            fi   = t.fast_info

            price      = (info.get("currentPrice")
                          or info.get("regularMarketPrice")
                          or fi.last_price or 0)
            prev       = (info.get("previousClose")
                          or info.get("regularMarketPreviousClose")
                          or fi.previous_close or 0)
            chg        = price - prev if price and prev else 0
            chg_pct    = (chg / prev * 100) if prev else 0

            mktcap = info.get("marketCap")
            self._ok({
                "symbol":            ticker,
                "name":              info.get("longName") or info.get("shortName") or ticker,
                "price":             price,
                "change":            chg,
                "changesPercentage": chg_pct,
                "changePct":         chg_pct,
                "dayLow":            info.get("dayLow") or info.get("regularMarketDayLow"),
                "dayHigh":           info.get("dayHigh") or info.get("regularMarketDayHigh"),
                "yearHigh":          info.get("fiftyTwoWeekHigh"),
                "yearLow":           info.get("fiftyTwoWeekLow"),
                "week52High":        info.get("fiftyTwoWeekHigh"),
                "week52Low":         info.get("fiftyTwoWeekLow"),
                "marketCap":         mktcap,
                "market_cap":        mktcap,
                "volume":            info.get("volume") or info.get("regularMarketVolume"),
                "avgVolume":         info.get("averageVolume"),
                "open":              info.get("open") or info.get("regularMarketOpen"),
                "previousClose":     prev,
                "eps":               info.get("trailingEps"),
                "pe":                info.get("trailingPE"),
                "forwardPe":         info.get("forwardPE"),
                "forward_pe":        info.get("forwardPE"),
                "ps":                info.get("priceToSalesTrailing12Months"),
                "pb":                info.get("priceToBook"),
                "priceToBook":       info.get("priceToBook"),
                "evEbitda":          info.get("enterpriseToEbitda"),
                "ev_ebitda":         info.get("enterpriseToEbitda"),
                "debtEquity":        info.get("debtToEquity"),
                "debt_equity":       (info.get("debtToEquity") or 0) / 100 if info.get("debtToEquity") else None,
                "roe":               info.get("returnOnEquity"),
                "roa":               info.get("returnOnAssets"),
                "fcf_yield":         info.get("freeCashflow") / mktcap if info.get("freeCashflow") and mktcap else None,
                "exchange":          info.get("exchange"),
                "currency":          info.get("currency", "USD"),
                "sector":            info.get("sector"),
                "industry":          info.get("industry"),
                "description":       info.get("longBusinessSummary", ""),
                "website":           info.get("website", ""),
                "employees":         info.get("fullTimeEmployees"),
                "beta":              info.get("beta"),
                "forwardPE":         info.get("forwardPE"),
                "dividendYield":     info.get("dividendYield"),
                "fiftyDayAvg":       info.get("fiftyDayAverage"),
                "twoHundredDayAvg":  info.get("twoHundredDayAverage"),
            })
        except Exception as e:
            self._err(str(e))
