# AlphaVault — Institutional-Grade Portfolio Intelligence

A full-stack portfolio analytics dashboard that brings institutional-quality tools to retail investors. Real-time portfolio tracking, risk management, options pricing, factor analysis, backtesting, and advanced financial modeling — all in a sleek, professional interface.

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

### Performance Attribution (AlphaTrace)
- Brinson-Fachler decomposition of portfolio returns
- Allocation, selection, and interaction effects by sector
- Benchmark-relative performance breakdown

### Fixed Income (BondLab)
- Bond pricing with duration and convexity
- Yield curve analysis and slope calculations
- Term structure visualization

### Technical Analysis (ChartBrain)
- OHLCV charting with customizable indicator overlays
- Moving averages (SMA, EMA), RSI, MACD, Bollinger Bands
- Support/resistance detection and signal generation

### Portfolio Rebalancing (DriftGuard)
- Weight drift monitoring against target allocations
- Automated rebalancing trade generation with share counts
- Tax impact estimation on proposed trades

### Earnings Intelligence (EarningsEdge)
- Upcoming earnings calendar
- Historical EPS surprise tracking
- Post-earnings price move analysis

### Factor Analysis (FactorLens)
- Fama-French 5-factor decomposition (Market, SMB, HML, RMW, CMA)
- Factor exposure quantification and significance testing
- Idiosyncratic vs. systematic risk breakdown

### Market Sentiment (NerveMap)
- News headline aggregation and sentiment scoring
- Impact analysis across markets, sectors, and asset classes
- Rules-based sensitivity mapping

### Pair Trading (PairPulse)
- Cointegration detection via Engle-Granger method
- Mean-reversion analysis with Ornstein-Uhlenbeck half-life
- Spread visualization and Z-score signals

### Market Regimes (RegimeRadar)
- Market condition classification (Bull / Bear / Crisis)
- Rule-based and GMM statistical regime detection
- Regime transition monitoring

### Strategy Backtesting (RewindEngine)
- Event-driven backtester with pluggable strategies
- Transaction cost modeling and slippage
- Performance analytics with no look-ahead bias

### Stock Screening (SectorScan)
- Multi-factor fundamental screening across 50-stock universe
- Composite scoring and ranking by customizable criteria
- Sector-level filtering and comparison

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
| Caching | SQLite with TTL management |
| Deployment | Render (backend), Vercel (static frontend) |

## Project Structure

```
alphavault/
├── index.html                 Main app shell
├── app.js                     Core app logic (~3,000 lines)
├── titan.js                   Extended UI modules (11 feature panels)
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
│   ├── alphatrace.py          Performance attribution API
│   ├── bondlab.py             Bond pricing + yield curve API
│   ├── chartbrain.py          Technical indicators API
│   ├── driftguard.py          Rebalancing API
│   ├── earningsedge.py        Earnings calendar API
│   ├── factorlens.py          Factor decomposition API
│   ├── nervemap.py            News sentiment API
│   ├── pairpulse.py           Pair trading API
│   ├── regimeradar.py         Market regime API
│   ├── rewindengine.py        Backtesting API
│   ├── sectorscan.py          Stock screener API
│   └── news.py, macro.py, dividends.py, etf.py, ...
├── core/
│   ├── analytics.py           Portfolio metrics engine
│   ├── options.py             Black-Scholes engine, Greeks, IV, payoffs
│   ├── alphatrace.py          Brinson-Fachler attribution engine
│   ├── bondlab.py             Fixed income analytics
│   ├── cache.py               SQLite caching layer with TTL
│   ├── calendar.py            Trading calendar utilities
│   ├── chartbrain.py          Technical analysis engine
│   ├── data.py                Unified data fetcher (cache-first)
│   ├── driftguard.py          Rebalancing engine
│   ├── earningsedge.py        Earnings analysis engine
│   ├── factorlens.py          Fama-French 5-factor model
│   ├── nervemap.py            Sentiment scoring engine
│   ├── pairpulse.py           Cointegration + mean-reversion
│   ├── regimeradar.py         Regime classification engine
│   ├── rewindengine.py        Event-driven backtester
│   ├── sanitize.py            Data validation utilities
│   └── sectorscan.py          Multi-factor stock screener
└── tests/
    ├── test_analytics.py      Portfolio analytics tests
    ├── test_options.py        Options pricing tests
    ├── test_alphatrace.py     Attribution tests
    ├── test_bondlab.py        Bond pricing tests
    ├── test_cache.py          Caching layer tests
    ├── test_calendar.py       Trading calendar tests
    ├── test_chartbrain.py     Technical analysis tests
    ├── test_data.py           Data fetcher tests
    ├── test_driftguard.py     Rebalancing tests
    ├── test_earningsedge.py   Earnings tests
    ├── test_factorlens.py     Factor model tests
    ├── test_nervemap.py       Sentiment tests
    ├── test_pairpulse.py      Pair trading tests
    ├── test_regimeradar.py    Regime detection tests
    ├── test_rewindengine.py   Backtesting tests
    ├── test_sanitize.py       Validation tests
    └── test_sectorscan.py     Screener tests
```

## Getting Started

### Prerequisites
- Python 3.11+
- API keys in `.env`: `FMP_API_KEY`, `FINNHUB_API_KEY` (optional fallbacks: `FRED_API_KEY`, `ALPHA_VANTAGE_API_KEY`)

### Run Locally
```bash
cd alphavault
python3 -m venv venv
./venv/bin/pip install flask python-dotenv yfinance pandas numpy requests pytest
./venv/bin/python dev_server.py
```
Open `http://localhost:3000`

### Run Tests
```bash
./venv/bin/python -m pytest tests/ -v
```
539 tests covering:
- Portfolio risk/return metrics (Sharpe, Sortino, Beta, Alpha, VaR, CVaR)
- Efficient frontier optimization (weight constraints, singular matrix fallback)
- Monte Carlo simulation (distribution properties, contribution effects)
- Stress testing (scenario coverage, beta sensitivity)
- Black-Scholes pricing (verified against known reference values)
- Put-call parity (parametrized across multiple input sets)
- All 5 Greeks (analytical + numerical finite-difference validation)
- Implied volatility (recovery across a range of volatilities)
- Options strategy payoffs (bounded profit/loss verification)
- Brinson-Fachler attribution (allocation, selection, interaction effects)
- Bond pricing, duration, convexity, and yield curves
- Technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands)
- Rebalancing trade generation and tax estimation
- Fama-French factor decomposition and significance
- Cointegration testing and mean-reversion signals
- Market regime classification (rule-based + statistical)
- Event-driven backtesting with transaction costs
- Stock screening composite scoring
- Caching, calendar, and data validation utilities

## Financial Accuracy

All computations use proper institutional formulas:

| Metric | Formula |
|--------|---------|
| Sharpe | (R_p - R_f) / sigma_p |
| Sortino | (R_p - R_f) / sigma_downside |
| Beta | Cov(R_p, R_m) / Var(R_m) |
| Alpha | R_p - R_f - Beta(R_m - R_f) |
| VaR 95% | 5th percentile of daily returns |
| CVaR | E[R | R <= VaR] |
| Black-Scholes | S * N(d1) - K * e^(-rT) * N(d2) |
| Greeks | Analytical closed-form (not finite difference) |
| Implied Vol | Newton-Raphson on vega |
| Efficient Frontier | Analytical Lagrangian with long-only projection |
| Brinson-Fachler | Allocation + Selection + Interaction decomposition |
| Fama-French | R - Rf = a + b1*MKT + b2*SMB + b3*HML + b4*RMW + b5*CMA + e |
| Bond Price | Sum of discounted cash flows with duration and convexity |
| Cointegration | Engle-Granger two-step with ADF test |
| Half-Life | Ornstein-Uhlenbeck mean-reversion estimate |
