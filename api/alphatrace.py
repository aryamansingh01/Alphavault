try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

try:
    from core.alphatrace import full_attribution
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.alphatrace import full_attribution


class handler(BaseHandler):
    def do_POST(self):
        try:
            body = self._body()
            holdings = body.get("holdings", [])
            period = body.get("period", "1y")

            if not holdings:
                return self._err("holdings required", 400)

            result = full_attribution(holdings, period)

            if not result.get("available", False):
                return self._err(result.get("error", "Attribution failed"), 500)

            self._ok(result)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
