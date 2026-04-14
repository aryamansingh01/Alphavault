try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

try:
    from core.driftguard import (
        calculate_drift, generate_trades, estimate_tax_impact,
        rebalance_needed, suggest_target_weights,
    )
except ImportError:
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from core.driftguard import (
        calculate_drift, generate_trades, estimate_tax_impact,
        rebalance_needed, suggest_target_weights,
    )


class handler(BaseHandler):
    def do_POST(self):
        try:
            body = self._body()
            holdings = body.get("holdings", [])
            targets = body.get("targets", None)
            portfolio_value = body.get("portfolio_value", None)
            tolerance = body.get("tolerance", 0.05)

            if not holdings:
                return self._err("holdings required", 400)

            # Compute current weights from holdings
            if portfolio_value is None:
                portfolio_value = sum(
                    h.get("shares", 0) * h.get("current_price", 0)
                    for h in holdings
                )

            if portfolio_value <= 0:
                return self._err("portfolio_value must be positive", 400)

            current_weights = {}
            current_prices = {}
            cost_basis = {}
            holding_periods = {}

            for h in holdings:
                ticker = h.get("ticker", "").upper()
                shares = h.get("shares", 0)
                price = h.get("current_price", 0)
                current_weights[ticker] = (shares * price) / portfolio_value
                current_prices[ticker] = price
                if "avg_cost" in h:
                    cost_basis[ticker] = h["avg_cost"]
                if "days_held" in h:
                    holding_periods[ticker] = h["days_held"]

            # Use provided targets or generate equal-weight
            if targets is None:
                tickers = list(current_weights.keys())
                suggested = suggest_target_weights(tickers)
                targets = suggested["weights"]

            # Calculate drift
            drift_table = calculate_drift(current_weights, targets)

            # Check if rebalance needed
            rb = rebalance_needed(current_weights, targets, tolerance)

            # Generate trades
            trades = generate_trades(drift_table, portfolio_value, current_prices)

            # Tax impact
            tax = estimate_tax_impact(
                trades,
                cost_basis if cost_basis else None,
                holding_periods if holding_periods else None,
            )

            # Summary
            total_buy = sum(t["dollar_amount"] for t in trades if t["action"] == "BUY")
            total_sell = sum(t["dollar_amount"] for t in trades if t["action"] == "SELL")

            self._ok({
                "rebalance_needed": rb["rebalance_needed"],
                "max_drift": rb["max_drift"],
                "max_drift_ticker": rb["max_drift_ticker"],
                "drift_table": drift_table,
                "suggested_trades": trades,
                "tax_impact": tax,
                "summary": {
                    "total_buy_amount": round(total_buy, 2),
                    "total_sell_amount": round(total_sell, 2),
                    "net_cash_flow": round(total_sell - total_buy, 2),
                    "num_trades": len(trades),
                },
            })
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))
