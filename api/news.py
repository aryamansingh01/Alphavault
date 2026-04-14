import os
try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler
try:
    from api._fmp import fmp
except ImportError:
    from _fmp import fmp


FINNHUB_KEY = os.environ.get("FINNHUB_API_KEY", "")


def _fetch_fmp_news(ticker):
    raw = fmp("/api/v3/stock_news", tickers=ticker, limit=20)
    if not raw:
        return None
    articles = []
    for item in raw:
        articles.append({
            "title":     item.get("title",""),
            "summary":   (item.get("text","") or "")[:300],
            "url":       item.get("url",""),
            "publisher": item.get("site") or item.get("publisher",""),
            "date":      (item.get("publishedDate","") or "")[:10],
            "image":     item.get("image",""),
        })
    return articles


def _fetch_finnhub_news(ticker):
    if not FINNHUB_KEY:
        return None
    import json, urllib.request
    from datetime import datetime, timedelta
    today = datetime.today().strftime("%Y-%m-%d")
    week_ago = (datetime.today() - timedelta(days=7)).strftime("%Y-%m-%d")
    url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from={week_ago}&to={today}&token={FINNHUB_KEY}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AlphaVault/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = json.loads(r.read())
        articles = []
        for item in (raw or [])[:20]:
            articles.append({
                "title":     item.get("headline",""),
                "summary":   (item.get("summary","") or "")[:300],
                "url":       item.get("url",""),
                "publisher": item.get("source",""),
                "date":      datetime.fromtimestamp(item.get("datetime",0)).strftime("%Y-%m-%d") if item.get("datetime") else "",
                "image":     item.get("image",""),
            })
        return articles if articles else None
    except Exception:
        return None


def _fetch_yfinance_news(ticker):
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        raw = t.news or []
        articles = []
        for item in raw[:20]:
            articles.append({
                "title":     item.get("title",""),
                "summary":   "",
                "url":       item.get("link",""),
                "publisher": item.get("publisher",""),
                "date":      "",
                "image":     (item.get("thumbnail",{}) or {}).get("resolutions",[{}])[0].get("url","") if item.get("thumbnail") else "",
            })
        return articles if articles else None
    except Exception:
        return None


class handler(BaseHandler):
    def do_GET(self):
        qs     = self._qs()
        ticker = qs.get("ticker","").upper()
        if not ticker: return self._err("ticker required", 400)
        try:
            # Try FMP -> Finnhub -> yfinance
            articles = _fetch_fmp_news(ticker)
            source = "fmp"
            if not articles:
                articles = _fetch_finnhub_news(ticker)
                source = "finnhub"
            if not articles:
                articles = _fetch_yfinance_news(ticker)
                source = "yfinance"
            if not articles:
                articles = []
                source = "none"

            self._ok({"articles": articles, "ticker": ticker, "_source": source})
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
