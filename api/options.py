"""Options pricing API endpoint.
POST /api/options  body: {"S":100,"K":100,"T":1,"r":0.05,"sigma":0.20,"type":"call"}
Also supports: implied_vol, payoff, greeks, strategy
"""
import json, math, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from api._base import BaseHandler
except ImportError:
    from _base import BaseHandler

from core.options import (
    black_scholes_call, black_scholes_put, put_call_parity_check,
    all_greeks, implied_volatility,
    call_payoff, put_payoff, straddle_payoff, bull_call_spread_payoff,
    iron_condor_payoff, protective_put_payoff, covered_call_payoff,
)
import numpy as np


class handler(BaseHandler):
    def do_POST(self):
        try:
            body = self._body()
            action = body.get("action", "price")

            if action == "price":
                return self._price(body)
            elif action == "greeks":
                return self._greeks(body)
            elif action == "implied_vol":
                return self._implied_vol(body)
            elif action == "payoff":
                return self._payoff(body)
            elif action == "strategy":
                return self._strategy(body)
            else:
                return self._err(f"Unknown action: {action}", 400)

        except ValueError as e:
            self._err(str(e), 400)
        except Exception as e:
            import traceback; traceback.print_exc()
            self._err(str(e))

    def _price(self, body):
        S = float(body["S"])
        K = float(body["K"])
        T = float(body["T"])
        r = float(body.get("r", 0.05))
        sigma = float(body["sigma"])
        opt_type = body.get("type", "call")

        call = black_scholes_call(S, K, T, r, sigma)
        put = black_scholes_put(S, K, T, r, sigma)
        parity = put_call_parity_check(call, put, S, K, T, r)
        greeks = all_greeks(S, K, T, r, sigma, opt_type)

        self._ok({
            "call": round(call, 4),
            "put": round(put, 4),
            "selected": round(call if opt_type == "call" else put, 4),
            "type": opt_type,
            "parityResidual": round(parity, 8),
            "greeks": {k: round(v, 6) for k, v in greeks.items()},
            "inputs": {"S": S, "K": K, "T": T, "r": r, "sigma": sigma},
        })

    def _greeks(self, body):
        S = float(body["S"])
        K = float(body["K"])
        T = float(body["T"])
        r = float(body.get("r", 0.05))
        sigma = float(body["sigma"])

        call_g = all_greeks(S, K, T, r, sigma, "call")
        put_g = all_greeks(S, K, T, r, sigma, "put")

        # Greeks surface: vary S from 0.5K to 1.5K
        spots = np.linspace(S * 0.7, S * 1.3, 50)
        delta_curve = []
        gamma_curve = []
        for s in spots:
            try:
                g = all_greeks(s, K, T, r, sigma, body.get("type", "call"))
                delta_curve.append({"S": round(float(s), 2), "delta": round(g["delta"], 4)})
                gamma_curve.append({"S": round(float(s), 2), "gamma": round(g["gamma"], 6)})
            except ValueError:
                pass

        self._ok({
            "call": {k: round(v, 6) for k, v in call_g.items()},
            "put": {k: round(v, 6) for k, v in put_g.items()},
            "deltaCurve": delta_curve,
            "gammaCurve": gamma_curve,
        })

    def _implied_vol(self, body):
        S = float(body["S"])
        K = float(body["K"])
        T = float(body["T"])
        r = float(body.get("r", 0.05))
        market_price = float(body["marketPrice"])
        opt_type = body.get("type", "call")

        iv = implied_volatility(market_price, S, K, T, r, opt_type)

        # Compute theoretical price at solved IV
        if opt_type == "call":
            theo = black_scholes_call(S, K, T, r, iv)
        else:
            theo = black_scholes_put(S, K, T, r, iv)

        self._ok({
            "impliedVol": round(iv, 6),
            "impliedVolPct": round(iv * 100, 2),
            "theoreticalPrice": round(theo, 4),
            "marketPrice": market_price,
            "priceDiff": round(abs(theo - market_price), 6),
        })

    def _payoff(self, body):
        S = float(body["S"])
        K = float(body["K"])
        T = float(body.get("T", 0.5))
        r = float(body.get("r", 0.05))
        sigma = float(body.get("sigma", 0.20))
        opt_type = body.get("type", "call")
        position = body.get("position", "long")

        if opt_type == "call":
            premium = black_scholes_call(S, K, T, r, sigma)
        else:
            premium = black_scholes_put(S, K, T, r, sigma)

        S_range = np.linspace(S * 0.5, S * 1.5, 100)

        if opt_type == "call":
            pnl = call_payoff(S_range, K, premium, position)
        else:
            pnl = put_payoff(S_range, K, premium, position)

        breakeven = K + premium if opt_type == "call" else K - premium
        max_profit = float("inf") if opt_type == "call" and position == "long" else float(np.max(pnl))
        max_loss = float(-premium) if position == "long" else float(np.min(pnl))

        self._ok({
            "premium": round(premium, 4),
            "breakeven": round(breakeven, 4),
            "maxProfit": round(max_profit, 4) if max_profit != float("inf") else "unlimited",
            "maxLoss": round(max_loss, 4),
            "chart": {
                "prices": [round(float(s), 2) for s in S_range],
                "pnl": [round(float(p), 2) for p in pnl],
                "zero": [0] * len(S_range),
            },
        })

    def _strategy(self, body):
        strategy = body.get("strategy", "straddle")
        S = float(body["S"])
        r = float(body.get("r", 0.05))
        T = float(body.get("T", 0.5))
        sigma = float(body.get("sigma", 0.20))
        S_range = np.linspace(S * 0.5, S * 1.5, 100)

        if strategy == "straddle":
            K = float(body.get("K", S))
            cp = black_scholes_call(S, K, T, r, sigma)
            pp = black_scholes_put(S, K, T, r, sigma)
            pnl = straddle_payoff(S_range, K, cp, pp)
            cost = cp + pp
            info = {"cost": round(cost, 4), "upperBE": round(K + cost, 2), "lowerBE": round(K - cost, 2)}

        elif strategy == "bull_call_spread":
            K1 = float(body.get("K1", S * 0.95))
            K2 = float(body.get("K2", S * 1.05))
            p1 = black_scholes_call(S, K1, T, r, sigma)
            p2 = black_scholes_call(S, K2, T, r, sigma)
            pnl = bull_call_spread_payoff(S_range, K1, K2, p1, p2)
            net_cost = p1 - p2
            info = {"cost": round(net_cost, 4), "maxProfit": round(K2 - K1 - net_cost, 4),
                    "maxLoss": round(-net_cost, 4), "breakeven": round(K1 + net_cost, 2)}

        elif strategy == "iron_condor":
            K1 = float(body.get("K1", S * 0.85))
            K2 = float(body.get("K2", S * 0.95))
            K3 = float(body.get("K3", S * 1.05))
            K4 = float(body.get("K4", S * 1.15))
            p1 = black_scholes_put(S, K1, T, r, sigma)
            p2 = black_scholes_put(S, K2, T, r, sigma)
            p3 = black_scholes_call(S, K3, T, r, sigma)
            p4 = black_scholes_call(S, K4, T, r, sigma)
            pnl = iron_condor_payoff(S_range, K1, K2, K3, K4, p1, p2, p3, p4)
            net_credit = (p2 - p1) + (p3 - p4)
            info = {"credit": round(net_credit, 4),
                    "maxProfit": round(net_credit, 4),
                    "maxLoss": round(min(K2 - K1, K4 - K3) - net_credit, 4)}

        elif strategy == "protective_put":
            K = float(body.get("K", S * 0.95))
            pp = black_scholes_put(S, K, T, r, sigma)
            pnl = protective_put_payoff(S_range, S, K, pp)
            info = {"putCost": round(pp, 4), "maxLoss": round(-(S - K + pp), 4),
                    "breakeven": round(S + pp, 2)}

        elif strategy == "covered_call":
            K = float(body.get("K", S * 1.05))
            cp = black_scholes_call(S, K, T, r, sigma)
            pnl = covered_call_payoff(S_range, S, K, cp)
            info = {"premium": round(cp, 4), "maxProfit": round(K - S + cp, 4),
                    "breakeven": round(S - cp, 2)}
        else:
            return self._err(f"Unknown strategy: {strategy}", 400)

        self._ok({
            "strategy": strategy,
            "info": info,
            "chart": {
                "prices": [round(float(s), 2) for s in S_range],
                "pnl": [round(float(p), 2) for p in pnl],
                "zero": [0] * len(S_range),
            },
        })
