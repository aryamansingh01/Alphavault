"""
Strategy Backtesting Framework.
Event-driven backtester with pluggable strategies, transaction cost modeling,
and comprehensive performance analytics.

CRITICAL: No look-ahead bias. Strategies see only data up to current bar.
"""
import math
import numpy as np
import pandas as pd
from core.sanitize import safe_divide, sanitize_returns
from core.calendar import annualization_factor


# ---------------------------------------------------------------------------
# Strategy Base Class
# ---------------------------------------------------------------------------

class Strategy:
    """Base class for all trading strategies."""

    def __init__(self, name: str = "BaseStrategy", params: dict = None):
        self.name = name
        self.params = params or {}

    def generate_signal(self, data: pd.DataFrame, current_index: int) -> str:
        """Return 'BUY', 'SELL', or 'HOLD'. Only use data.iloc[:current_index+1]."""
        raise NotImplementedError

    def __repr__(self):
        return f"{self.name}({self.params})"


# ---------------------------------------------------------------------------
# Built-in Strategies
# ---------------------------------------------------------------------------

class BuyAndHold(Strategy):
    def __init__(self):
        super().__init__("Buy & Hold", {})

    def generate_signal(self, data, current_index):
        return "BUY" if current_index == 0 else "HOLD"


class MACrossover(Strategy):
    def __init__(self, fast: int = 50, slow: int = 200):
        super().__init__("MA Crossover", {"fast": fast, "slow": slow})
        self.fast = fast
        self.slow = slow

    def generate_signal(self, data, current_index):
        if current_index < self.slow:
            return "HOLD"
        visible = data.iloc[:current_index + 1]["close"]
        fast_now = visible.iloc[-self.fast:].mean()
        fast_prev = visible.iloc[-self.fast - 1:-1].mean()
        slow_now = visible.iloc[-self.slow:].mean()
        slow_prev = visible.iloc[-self.slow - 1:-1].mean()
        if fast_prev <= slow_prev and fast_now > slow_now:
            return "BUY"
        elif fast_prev >= slow_prev and fast_now < slow_now:
            return "SELL"
        return "HOLD"


class RSIMeanReversion(Strategy):
    def __init__(self, period: int = 14, oversold: int = 30, overbought: int = 70):
        super().__init__("RSI Mean Reversion", {"period": period, "oversold": oversold, "overbought": overbought})
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signal(self, data, current_index):
        if current_index < self.period + 1:
            return "HOLD"
        visible = data.iloc[:current_index + 1]["close"]
        rsi_val = self._compute_rsi(visible)
        if rsi_val is None or np.isnan(rsi_val):
            return "HOLD"
        if rsi_val < self.oversold:
            return "BUY"
        if rsi_val > self.overbought:
            return "SELL"
        return "HOLD"

    def _compute_rsi(self, prices: pd.Series) -> float:
        delta = prices.diff()
        gains = delta.clip(lower=0)
        losses = (-delta).clip(lower=0)
        period = self.period
        if len(gains) < period + 1:
            return None
        avg_gain = gains.iloc[1:period + 1].mean()
        avg_loss = losses.iloc[1:period + 1].mean()
        for i in range(period + 1, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains.iloc[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses.iloc[i]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))


class MonthlyRebalance(Strategy):
    """Monthly rebalance: sell at end of month, buy at start of next month.
    This creates a sell-rebuy cycle each month, incurring transaction costs
    and producing different results from Buy & Hold."""

    def __init__(self):
        super().__init__("Monthly Rebalance", {})

    def generate_signal(self, data, current_index):
        if current_index == 0:
            return "BUY"
        current_date = data.index[current_index]
        prev_date = data.index[current_index - 1]

        # BUY on the first trading day of a new month (when we're FLAT after last month's sell)
        if current_date.month != prev_date.month:
            return "BUY"

        # SELL on the last trading day of the month
        # (check if next trading day is a new month — this is calendar knowledge, not price look-ahead)
        if current_index < len(data) - 1:
            next_date = data.index[current_index + 1]
            if next_date.month != current_date.month:
                return "SELL"

        return "HOLD"


class BollingerBandMean(Strategy):
    def __init__(self, window: int = 20, num_std: float = 2.0):
        super().__init__("Bollinger Band Mean Reversion", {"window": window, "num_std": num_std})
        self.window = window
        self.num_std = num_std

    def generate_signal(self, data, current_index):
        if current_index < self.window:
            return "HOLD"
        visible = data.iloc[:current_index + 1]["close"]
        rolling = visible.iloc[-self.window:]
        middle = rolling.mean()
        std = rolling.std()
        if std == 0:
            return "HOLD"
        upper = middle + self.num_std * std
        lower = middle - self.num_std * std
        price = visible.iloc[-1]
        if price < lower:
            return "BUY"
        elif price > upper:
            return "SELL"
        return "HOLD"


# ---------------------------------------------------------------------------
# Strategy Registry
# ---------------------------------------------------------------------------

STRATEGIES = {
    "buy_and_hold": BuyAndHold,
    "ma_crossover": MACrossover,
    "rsi_mean_reversion": RSIMeanReversion,
    "monthly_rebalance": MonthlyRebalance,
    "bollinger_mean_reversion": BollingerBandMean,
}


def get_strategy(name: str, params: dict = None) -> Strategy:
    cls = STRATEGIES.get(name)
    if cls is None:
        raise ValueError(f"Unknown strategy: {name}. Available: {list(STRATEGIES.keys())}")
    if params:
        return cls(**params)
    return cls()


def list_strategies() -> list:
    return [
        {"name": "buy_and_hold", "description": "Buy on first day, hold forever", "params": {}},
        {"name": "ma_crossover", "description": "Moving Average Crossover", "params": {"fast": 50, "slow": 200}},
        {"name": "rsi_mean_reversion", "description": "RSI Mean Reversion", "params": {"period": 14, "oversold": 30, "overbought": 70}},
        {"name": "monthly_rebalance", "description": "Buy on first trading day of each month", "params": {}},
        {"name": "bollinger_mean_reversion", "description": "Bollinger Band Mean Reversion", "params": {"window": 20, "num_std": 2.0}},
    ]


# ---------------------------------------------------------------------------
# Backtest Engine
# ---------------------------------------------------------------------------

class Backtest:
    def __init__(self, strategy: Strategy, data: pd.DataFrame,
                 initial_capital: float = 100000.0, commission_bps: float = 10.0,
                 slippage_bps: float = 5.0, position_size: float = 1.0, seed: int = 42):
        self.strategy = strategy
        self.data = data
        self.initial_capital = initial_capital
        self.commission_rate = commission_bps / 10000
        self.slippage_bps = slippage_bps
        self.position_size = min(max(position_size, 0.0), 1.0)
        self.rng = np.random.default_rng(seed)
        self.cash = initial_capital
        self.shares = 0
        self.position = "FLAT"
        self.equity_curve = []
        self.trade_log = []
        self.daily_returns = []

    def _apply_slippage(self, price: float, direction: str) -> float:
        slip = self.rng.uniform(0, self.slippage_bps) / 10000
        return price * (1 + slip) if direction == "BUY" else price * (1 - slip)

    def _execute_buy(self, price, bar_date):
        exec_price = self._apply_slippage(price, "BUY")
        available = self.cash * self.position_size
        commission = available * self.commission_rate
        investable = available - commission
        shares = int(investable / exec_price)
        if shares <= 0:
            return None
        cost = shares * exec_price
        actual_commission = cost * self.commission_rate
        self.cash -= (cost + actual_commission)
        self.shares += shares
        self.position = "LONG"
        trade = {
            "date": str(bar_date)[:10], "action": "BUY", "price": round(exec_price, 4),
            "shares": shares, "cost": round(cost, 2), "commission": round(actual_commission, 2),
            "cash_after": round(self.cash, 2),
            "portfolio_value": round(self.cash + self.shares * price, 2),
        }
        self.trade_log.append(trade)
        return trade

    def _execute_sell(self, price, bar_date):
        if self.shares <= 0:
            return None
        exec_price = self._apply_slippage(price, "SELL")
        proceeds = self.shares * exec_price
        commission = proceeds * self.commission_rate
        net = proceeds - commission
        trade = {
            "date": str(bar_date)[:10], "action": "SELL", "price": round(exec_price, 4),
            "shares": self.shares, "proceeds": round(proceeds, 2),
            "commission": round(commission, 2),
            "cash_after": round(self.cash + net, 2),
            "portfolio_value": round(self.cash + net, 2),
        }
        self.cash += net
        self.shares = 0
        self.position = "FLAT"
        self.trade_log.append(trade)
        return trade

    def run(self) -> dict:
        if self.data is None or len(self.data) < 2:
            return {"error": "Insufficient data for backtest", "valid": False}

        self.cash = self.initial_capital
        self.shares = 0
        self.position = "FLAT"
        self.equity_curve = []
        self.trade_log = []
        self.daily_returns = []

        for i in range(len(self.data)):
            price = self.data.iloc[i]["close"]
            bar_date = self.data.index[i]
            pv = self.cash + self.shares * price
            self.equity_curve.append(pv)
            if i > 0:
                prev = self.equity_curve[-2]
                self.daily_returns.append((pv - prev) / prev if prev > 0 else 0)

            signal = self.strategy.generate_signal(self.data, i)
            if signal == "BUY" and self.position == "FLAT":
                self._execute_buy(price, bar_date)
            elif signal == "SELL" and self.position == "LONG":
                self._execute_sell(price, bar_date)

        if self.position == "LONG":
            self._execute_sell(self.data.iloc[-1]["close"], self.data.index[-1])

        return self._compute_results()

    def _compute_results(self) -> dict:
        ec = np.array(self.equity_curve)
        dr = np.array(self.daily_returns)
        n_days = len(ec)
        final = ec[-1] if len(ec) > 0 else self.initial_capital

        total_return = safe_divide(final - self.initial_capital, self.initial_capital)

        if n_days > 1:
            ann_return = (1 + total_return) ** (252 / n_days) - 1
        else:
            ann_return = 0.0

        # Benchmark: buy and hold
        first_price = self.data.iloc[0]["close"]
        last_price = self.data.iloc[-1]["close"]
        bench_return = safe_divide(last_price - first_price, first_price)

        vol = float(np.std(dr, ddof=1) * math.sqrt(252)) if len(dr) > 1 else 0.0
        sharpe = safe_divide(ann_return - 0.052, vol)

        # Sortino
        neg = dr[dr < 0]
        downside_vol = float(np.std(neg, ddof=1) * math.sqrt(252)) if len(neg) > 0 else 0.0
        sortino = safe_divide(ann_return - 0.052, downside_vol)

        # Drawdown
        peak = np.maximum.accumulate(ec)
        dd = (ec - peak) / np.where(peak > 0, peak, 1)
        max_dd = float(np.min(dd))
        calmar = safe_divide(ann_return, abs(max_dd))

        # Trade analysis
        buys = [t for t in self.trade_log if t["action"] == "BUY"]
        sells = [t for t in self.trade_log if t["action"] == "SELL"]
        n_roundtrips = min(len(buys), len(sells))
        total_commissions = sum(t.get("commission", 0) for t in self.trade_log)

        wins, losses = [], []
        for j in range(n_roundtrips):
            buy_cost = buys[j]["price"] * buys[j]["shares"]
            sell_proceeds = sells[j]["price"] * sells[j]["shares"]
            pnl = sell_proceeds - buy_cost
            if pnl > 0:
                wins.append(pnl / buy_cost)
            else:
                losses.append(pnl / buy_cost)

        gross_profit = sum(w for w in wins) if wins else 0
        gross_loss = abs(sum(l for l in losses)) if losses else 0

        # Trade durations
        durations = []
        for j in range(n_roundtrips):
            try:
                bd = pd.Timestamp(buys[j]["date"])
                sd = pd.Timestamp(sells[j]["date"])
                durations.append((sd - bd).days)
            except Exception:
                pass

        dates = [d.strftime("%Y-%m-%d") for d in self.data.index]

        return {
            "valid": True,
            "strategy": self.strategy.name,
            "strategy_params": self.strategy.params,
            "period": {"start": dates[0], "end": dates[-1], "trading_days": n_days},
            "total_return": round(total_return, 6),
            "annualized_return": round(ann_return, 6),
            "benchmark_return": round(bench_return, 6),
            "excess_return": round(total_return - bench_return, 6),
            "volatility": round(vol, 6),
            "sharpe": round(sharpe, 4),
            "sortino": round(sortino, 4),
            "max_drawdown": round(max_dd, 6),
            "calmar": round(calmar, 4),
            "total_trades": len(self.trade_log),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": round(safe_divide(len(wins), n_roundtrips), 4) if n_roundtrips > 0 else 0,
            "avg_win": round(float(np.mean(wins)), 6) if wins else 0,
            "avg_loss": round(float(np.mean(losses)), 6) if losses else 0,
            "profit_factor": round(safe_divide(gross_profit, gross_loss), 4) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0,
            "avg_trade_duration": round(float(np.mean(durations)), 1) if durations else 0,
            "largest_win": round(max(wins), 6) if wins else 0,
            "largest_loss": round(min(losses), 6) if losses else 0,
            "equity_curve": [round(v, 2) for v in ec.tolist()],
            "drawdown_curve": [round(v, 6) for v in dd.tolist()],
            "dates": dates,
            "trade_log": self.trade_log,
            "total_commissions": round(total_commissions, 2),
            "commission_drag": round(safe_divide(total_commissions, self.initial_capital), 6),
            "initial_capital": self.initial_capital,
            "final_value": round(final, 2),
        }


# ---------------------------------------------------------------------------
# Convenience Functions
# ---------------------------------------------------------------------------

def run_backtest(ticker: str, strategy_name: str, params: dict = None,
                 period: str = "5y", initial_capital: float = 100000,
                 commission_bps: float = 10, slippage_bps: float = 5) -> dict:
    try:
        from core.data import get_ohlcv
        df = get_ohlcv(ticker, period)
        if df.empty:
            return {"valid": False, "error": f"No data for {ticker}"}
        strategy = get_strategy(strategy_name, params)
        bt = Backtest(strategy, df, initial_capital, commission_bps, slippage_bps)
        return bt.run()
    except Exception as e:
        return {"valid": False, "error": str(e)}


def compare_strategies(ticker: str, strategy_configs: list, period: str = "5y",
                       initial_capital: float = 100000) -> dict:
    try:
        from core.data import get_ohlcv
        df = get_ohlcv(ticker, period)
        if df.empty:
            return {"error": f"No data for {ticker}"}

        results = []
        for cfg in strategy_configs:
            name = cfg.get("name", "buy_and_hold")
            params = cfg.get("params")
            strategy = get_strategy(name, params)
            bt = Backtest(strategy, df, initial_capital)
            r = bt.run()
            if r.get("valid"):
                results.append({
                    "strategy": r["strategy"],
                    "total_return": r["total_return"],
                    "annualized_return": r["annualized_return"],
                    "sharpe": r["sharpe"],
                    "max_drawdown": r["max_drawdown"],
                    "total_trades": r["total_trades"],
                    "win_rate": r["win_rate"],
                })

        results.sort(key=lambda x: x["sharpe"], reverse=True)

        best_sharpe = results[0]["strategy"] if results else ""
        best_return = max(results, key=lambda x: x["total_return"])["strategy"] if results else ""
        best_dd = max(results, key=lambda x: x["max_drawdown"])["strategy"] if results else ""

        return {
            "ticker": ticker, "period": period,
            "comparison": results,
            "best_strategy": best_sharpe,
            "best_by": {"sharpe": best_sharpe, "return": best_return, "drawdown": best_dd},
        }
    except Exception as e:
        return {"error": str(e)}
