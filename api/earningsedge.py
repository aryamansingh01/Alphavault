try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

try:
    from core.earningsedge import (
        get_earnings_calendar, get_earnings_history,
        calculate_surprise_stats, get_post_earnings_moves,
        estimate_expected_move, portfolio_earnings_summary,
    )
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.earningsedge import (
        get_earnings_calendar, get_earnings_history,
        calculate_surprise_stats, get_post_earnings_moves,
        estimate_expected_move, portfolio_earnings_summary,
    )


class handler(BaseHandler):
    def do_GET(self):
        qs = self._qs()
        ticker = qs.get("ticker", "").upper()
        if not ticker:
            return self._err("ticker required", 400)

        try:
            upcoming = get_earnings_calendar(ticker)
            history = get_earnings_history(ticker)
            stats = calculate_surprise_stats(history)
            moves = get_post_earnings_moves(ticker, history)
            expected = estimate_expected_move(moves)

            self._ok({
                "ticker": ticker,
                "upcoming": upcoming,
                "history": history,
                "surprise_stats": stats,
                "expected_move": expected,
                "price_moves": moves,
            })
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))

    def do_POST(self):
        try:
            body = self._body()
            holdings = body.get("holdings", [])
            weeks_ahead = body.get("weeks_ahead", 4)

            if not holdings:
                return self._err("holdings required", 400)

            result = portfolio_earnings_summary(holdings, weeks_ahead)
            self._ok(result)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
