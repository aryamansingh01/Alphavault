try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

try:
    from core.data import get_market_news
    from core.nervemap import score_headline, aggregate_scores, portfolio_impact
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.data import get_market_news
    from core.nervemap import score_headline, aggregate_scores, portfolio_impact


class handler(BaseHandler):
    def do_GET(self):
        qs = self._qs()
        tickers_str = qs.get("tickers", "")
        tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()] if tickers_str else None

        try:
            articles = get_market_news(tickers=tickers)
            scored = [
                score_headline(
                    a.get("headline", ""),
                    a.get("source", ""),
                    a.get("sentiment", 0.0),
                    tickers=a.get("tickers", []),
                )
                for a in articles
            ]
            agg = aggregate_scores(scored)
            self._ok(agg)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))

    def do_POST(self):
        try:
            body = self._body()
            holdings = body.get("holdings", [])
            tickers = [h.get("ticker", "").upper() for h in holdings if h.get("ticker")]

            articles = get_market_news(tickers=tickers or None)
            scored = [
                score_headline(
                    a.get("headline", ""),
                    a.get("source", ""),
                    a.get("sentiment", 0.0),
                    tickers=a.get("tickers", []),
                )
                for a in articles
            ]
            agg = aggregate_scores(scored)

            if holdings:
                pi = portfolio_impact(scored, holdings)
                agg["portfolio_impact"] = pi

            self._ok(agg)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
