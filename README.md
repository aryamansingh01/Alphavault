# AlphaVault — Institutional-Grade Portfolio Intelligence

A full-stack portfolio analytics dashboard that brings institutional-quality tools to retail investors. Real-time portfolio tracking, risk management, options pricing, and advanced financial modeling — all in a sleek, professional interface.

**Live:** Deployed on Render

## Features

### Portfolio Management
- Add/edit/delete positions with ticker, shares, and average cost
- Preset portfolios (S&P Core, Tech Heavy, Dividend, Crypto, Bogleheads)
- CSV import/export, real-time NAV and day P&L tracking

### Portfolio Analytics
- **Risk metrics:** Sharpe, Sortino, Treynor, Calmar ratios
- **Market sensitivity:** Beta, Alpha (CAPM)
- **Tail risk:** VaR (95%/99%), CVaR, max drawdown
- **Correlation matrix** heatmap across all holdings

### Risk Management
- Drawdown analysis per security with recovery tracking
- Stress testing against 8 scenarios (2008 crisis, COVID crash, dot-com bust, rate hikes, sector selloffs)
- Beta-adjusted impact estimates

### Efficient Frontier
- Markowitz mean-variance optimization with Ledoit-Wolf covariance shrinkage
- Min-volatility and max-Sharpe portfolios
- Analytical solver + random sampling (no scipy dependency)

### Monte Carlo Simulation
- 1,000–3,000 path projections with percentile bands
- Monthly contributions with inflation adjustment
- Probability of success metric

### Options & Derivatives
- **Black-Scholes pricer** for European calls and puts
- **Full Greeks:** Delta, Gamma, Theta, Vega, Rho with interpretations
- **Implied volatility solver** (Newton-Raphson)
- **Payoff diagrams** for long/short positions
- **Strategy builder:** Straddle, Bull Call Spread, Iron Condor, Protective Put, Covered Call
- **Put-call parity** verification on every price

### Market Research
- Live quotes, analyst consensus, insider transactions
- News feeds, macro dashboard (VIX, yields, CPI, Fed rate, gold, oil)
- ETF holdings look-through and sector breakdown

### Additional Tools
- Benchmark comparison (SPY, QQQ, DIA)
- What-If calculator, DCA vs Lump Sum analysis
- Goal projection, watchlist, PDF export, dark/light theme

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Vanilla JS, Chart.js 4.4, HTML5, CSS3 |
| Backend | Python 3.11+, Flask |
| Computation | NumPy, Pandas |
| Data Sources | Financial Modeling Prep, yfinance, FRED, Finnhub |
| Deployment | Render (backend), Vercel (static frontend) |

## Project Structure

```
aladin-pro/
├── index.html                 Main app shell
├── app.js                     Core app logic (~3,000 lines)
├── style.css                  Design system
├── dev_server.py              Flask dev server with dynamic API routing
├── requirements.txt           Python dependencies
├── api/
│   ├── _base.py               HTTP handler abstraction
│   ├── _fmp.py                FMP API client
│   ├── quote.py               Stock quotes + fundamentals
│   ├── history.py             Price history + benchmark comparison
│   ├── research.py            Analyst grades + insider transactions
│   ├── portfolio_analytics.py Risk metrics (Sharpe, Beta, VaR, etc.)
│   ├── efficient_frontier.py  Portfolio optimization
│   ├── montecarlo.py          Monte Carlo simulations
│   ├── risk.py                Drawdown + stress testing
│   ├── correlation.py         Correlation matrix
│   ├── options.py             Options pricing API
│   ├── news.py, macro.py, dividends.py, etf_holdings.py, etf_sectors.py
│   └── ...
├── core/
│   ├── analytics.py           Pure computation functions (portfolio metrics)
│   └── options.py             Black-Scholes engine, Greeks, IV, payoffs
└── tests/
    ├── test_analytics.py      65 tests — portfolio analytics
    └── test_options.py        63 tests — options pricing
```

## Getting Started

### Prerequisites
- Python 3.11+
- API keys in `.env`: `FMP_API_KEY`, `FINNHUB_API_KEY` (optional fallbacks: `FRED_API_KEY`, `ALPHA_VANTAGE_API_KEY`)

### Run Locally
```bash
cd aladin-pro
python3 -m venv venv
./venv/bin/pip install flask python-dotenv yfinance pandas numpy requests pytest
./venv/bin/python dev_server.py
```
Open `http://localhost:3000`

### Run Tests
```bash
./venv/bin/python -m pytest tests/ -v
```
128 tests covering:
- Portfolio risk/return metrics (Sharpe, Sortino, Beta, Alpha, VaR, CVaR)
- Efficient frontier optimization (weight constraints, singular matrix fallback)
- Monte Carlo simulation (distribution properties, contribution effects)
- Stress testing (scenario coverage, beta sensitivity)
- Black-Scholes pricing (verified against known reference values)
- Put-call parity (parametrized across 5 input sets)
- All 5 Greeks (analytical + numerical finite-difference validation)
- Implied volatility (recovery across σ = 10%–80%)
- Options strategy payoffs (bounded profit/loss verification)

## Financial Accuracy

All computations use proper institutional formulas:

| Metric | Formula |
|--------|---------|
| Sharpe | (R_p - R_f) / σ_p |
| Sortino | (R_p - R_f) / σ_downside |
| Beta | Cov(R_p, R_m) / Var(R_m) |
| Alpha | R_p - R_f - β(R_m - R_f) |
| VaR 95% | 5th percentile of daily returns |
| CVaR | E[R \| R ≤ VaR] |
| Black-Scholes | S·N(d₁) - K·e^(-rT)·N(d₂) |
| Greeks | Analytical closed-form (not finite difference) |
| Implied Vol | Newton-Raphson on vega |
| Efficient Frontier | Analytical Lagrangian with long-only projection |
