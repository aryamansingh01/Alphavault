try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

try:
    from core.bondlab import full_bond_analysis, get_yield_curve, yield_curve_slope
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.bondlab import full_bond_analysis, get_yield_curve, yield_curve_slope


class handler(BaseHandler):
    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path.endswith("/curve"):
            return self._handle_curve()
        elif path.endswith("/slope"):
            return self._handle_slope()
        else:
            return self._handle_curve()  # default

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        if path.endswith("/price"):
            return self._handle_price()
        else:
            return self._handle_price()  # default

    def _handle_curve(self):
        try:
            self._ok(get_yield_curve())
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))

    def _handle_slope(self):
        try:
            self._ok(yield_curve_slope())
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))

    def _handle_price(self):
        try:
            body = self._body()
            result = full_bond_analysis(
                face=body.get("face", 1000),
                coupon_rate=body.get("coupon_rate", 0.05),
                ytm=body.get("ytm", 0.04),
                years=body.get("years", 10),
                frequency=body.get("frequency", 2),
            )
            self._ok(result)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
