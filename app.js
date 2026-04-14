/* ============================================================
   ALPHAVAULT — APP.JS  (Part 1 of 2)
   Core Engine: State, Navigation, Portfolio, Charts
   ============================================================ */

'use strict';

/* ============================================================
   1. GLOBAL STATE
   ============================================================ */
const STATE = {
  portfolio: [],       // Array of position objects
  watchlist: [],       // Array of ticker strings
  activeTab: 'portfolio',
  theme: 'dark',
  charts: {},          // Chart.js instances — destroyed before re-render
  quotes: {},          // Cache: { TICKER: { price, change, changePct, ... } }
  lastQuoteTime: null,
  analyticsData: null,
  macroData: null,
  macroLastFetch: null,
  researchTicker: null,
};

/* ============================================================
   2. CONSTANTS
   ============================================================ */
const PRESET_PORTFOLIOS = {
  sp500core: [
    { ticker: 'SPY',  shares: 50,  avgCost: 420 },
    { ticker: 'VTI',  shares: 30,  avgCost: 210 },
    { ticker: 'SCHD', shares: 40,  avgCost: 78  },
  ],
  techheavy: [
    { ticker: 'AAPL', shares: 20,  avgCost: 170 },
    { ticker: 'MSFT', shares: 15,  avgCost: 310 },
    { ticker: 'NVDA', shares: 10,  avgCost: 480 },
    { ticker: 'GOOGL',shares: 8,   avgCost: 140 },
    { ticker: 'META', shares: 12,  avgCost: 320 },
    { ticker: 'QQQ',  shares: 25,  avgCost: 380 },
  ],
  dividend: [
    { ticker: 'SCHD', shares: 100, avgCost: 75  },
    { ticker: 'VYM',  shares: 60,  avgCost: 108 },
    { ticker: 'JEPI', shares: 80,  avgCost: 54  },
    { ticker: 'O',    shares: 50,  avgCost: 55  },
    { ticker: 'JNJ',  shares: 20,  avgCost: 155 },
  ],
  crypto: [
    { ticker: 'IBIT', shares: 40,  avgCost: 35  },
    { ticker: 'ETHA', shares: 30,  avgCost: 22  },
    { ticker: 'SPY',  shares: 20,  avgCost: 430 },
    { ticker: 'GLD',  shares: 15,  avgCost: 185 },
  ],
  bogleheads: [
    { ticker: 'VTI',  shares: 60,  avgCost: 215 },
    { ticker: 'VXUS', shares: 40,  avgCost: 58  },
    { ticker: 'BND',  shares: 30,  avgCost: 72  },
  ],
};

const ASSET_TYPES = {
  SPY:'ETF', QQQ:'ETF', VTI:'ETF', VEA:'ETF', GLD:'ETF', IBIT:'ETF',
  TQQQ:'ETF', IWM:'ETF', EFA:'ETF', AGG:'ETF', BND:'ETF', VXUS:'ETF',
  SCHD:'ETF', VYM:'ETF', JEPI:'ETF', ETHA:'ETF', IAU:'ETF', SLV:'ETF',
  'BTC-USD':'Crypto','ETH-USD':'Crypto','SOL-USD':'Crypto','BNB-USD':'Crypto',
};

const SECTOR_MAP = {
  AAPL:'Technology', MSFT:'Technology', NVDA:'Technology', GOOGL:'Technology',
  META:'Technology', AMZN:'Consumer Cyclical', TSLA:'Consumer Cyclical',
  JNJ:'Healthcare', UNH:'Healthcare', PFE:'Healthcare', ABBV:'Healthcare',
  JPM:'Financials', BAC:'Financials', GS:'Financials', V:'Financials',
  XOM:'Energy', CVX:'Energy', O:'Real Estate', AMT:'Real Estate',
  SPY:'Diversified', QQQ:'Technology', VTI:'Diversified', BND:'Bonds',
  GLD:'Commodities', IBIT:'Crypto', SCHD:'Diversified', VYM:'Diversified',
};

const CHART_COLORS = [
  '#4a8eff','#3dbc72','#5ba8d4','#d4a03d','#d44a4a',
  '#9b7ed8','#5cc4a0','#c87a3d','#6ba3d4','#c45a8a',
  '#7ec45a','#a87ed8',
];

/* ============================================================
   3. INITIALIZATION
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {
  loadFromStorage();
  initClock();
  initTheme();
  initNavigation();
  initPortfolioBuilderEvents();
  initCSVUpload();
  renderPortfolio();
  initExportPDF();
  startAutoRefresh();
  // Part 2 initializers
  initResearchSearch();
  initSimulateTab();
  initCompareTab();
  initWatchlistTab();
  initStressTestScenarios();
  initOptionsTab();
});

/* ============================================================
   4. LOCAL STORAGE
   ============================================================ */
function loadFromStorage() {
  try {
    const saved = localStorage.getItem('av_portfolio');
    if (saved) STATE.portfolio = JSON.parse(saved);
    const wl = localStorage.getItem('av_watchlist');
    if (wl) STATE.watchlist = JSON.parse(wl);
    const theme = localStorage.getItem('av_theme');
    if (theme) STATE.theme = theme;
  } catch(e) { console.warn('Storage load error:', e); }
}

function saveToStorage() {
  try {
    localStorage.setItem('av_portfolio', JSON.stringify(STATE.portfolio));
    localStorage.setItem('av_watchlist', JSON.stringify(STATE.watchlist));
    localStorage.setItem('av_theme', STATE.theme);
  } catch(e) { console.warn('Storage save error:', e); }
}

/* ============================================================
   5. LIVE CLOCK
   ============================================================ */
function initClock() {
  const el = document.getElementById('liveClock');
  function tick() {
    const now = new Date();
    el.textContent = now.toLocaleTimeString('en-US', { hour12: false });
  }
  tick();
  setInterval(tick, 1000);
}

/* ============================================================
   6. THEME TOGGLE
   ============================================================ */
function initTheme() {
  applyTheme(STATE.theme);
  document.getElementById('themeToggle').addEventListener('click', () => {
    STATE.theme = STATE.theme === 'dark' ? 'light' : 'dark';
    applyTheme(STATE.theme);
    saveToStorage();
  });
}

function applyTheme(theme) {
  const body = document.body;
  const btn  = document.getElementById('themeToggle');
  if (theme === 'light') {
    body.classList.add('light');
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/>
      <line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
      <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/>
      <line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
      <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`;
  } else {
    body.classList.remove('light');
    btn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
  }
}

/* ============================================================
   7. NAVIGATION / TAB SWITCHING
   ============================================================ */
function initNavigation() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      const tab = item.dataset.tab;
      switchTab(tab);
    });
  });

  // Inner tab switching (research, simulate)
  document.querySelectorAll('[data-inner-tab]').forEach(btn => {
    btn.addEventListener('click', () => {
      const panelId = btn.dataset.innerTab;
      const parent  = btn.closest('.inner-tabs');
      parent.querySelectorAll('.inner-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const allPanels = btn.closest('.tab-page').querySelectorAll('.inner-tab-panel');
      allPanels.forEach(p => p.classList.remove('active'));
      const target = document.getElementById(`panel-${panelId}`);
      if (target) target.classList.add('active');
    });
  });
}

function switchTab(tabName) {
  STATE.activeTab = tabName;
  document.querySelectorAll('.nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.tab === tabName);
  });
  document.querySelectorAll('.tab-page').forEach(p => {
    p.classList.toggle('active', p.id === `tab-${tabName}`);
  });
  // Lazy-load tab content
  onTabActivated(tabName);
}

function onTabActivated(tab) {
  switch(tab) {
    case 'exposure':  renderExposureTab();  break;
    case 'risk':      renderRiskTab();      break;
    case 'macro':     loadMacroTab();       break;
    case 'compare':   renderCompareTab();   break;
    case 'watchlist': renderWatchlistTab(); break;
    case 'simulate':  initSimulateTab();    break;
    case 'technical':    if(typeof renderTechnicalTab==='function') renderTechnicalTab(); break;
    case 'nervemap':     if(typeof renderNerveMapTab==='function') renderNerveMapTab(); break;
    case 'rebalance':    if(typeof renderRebalanceTab==='function') renderRebalanceTab(); break;
    case 'factors':      if(typeof renderFactorsTab==='function') renderFactorsTab(); break;
    case 'attribution':  if(typeof renderAttributionTab==='function') renderAttributionTab(); break;
    case 'regime':       if(typeof renderRegimeTab==='function') renderRegimeTab(); break;
    case 'screener':     if(typeof renderScreenerTab==='function') renderScreenerTab(); break;
    case 'earnings':     if(typeof renderEarningsTab==='function') renderEarningsTab(); break;
    case 'bonds':        if(typeof renderBondsTab==='function') renderBondsTab(); break;
    case 'pairs':        if(typeof renderPairsTab==='function') renderPairsTab(); break;
    case 'backtest':     if(typeof renderBacktestTab==='function') renderBacktestTab(); break;
  }
}

/* ============================================================
   8. API HELPER
   ============================================================ */
async function apiFetch(url, options = {}) {
  try {
    const res = await fetch(url, options);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch(e) {
    console.error(`API Error [${url}]:`, e);
    throw e;
  }
}

/* ============================================================
   9. QUOTE FETCHING
   ============================================================ */
async function fetchQuote(ticker) {
  if (STATE.quotes[ticker] && STATE.lastQuoteTime &&
      (Date.now() - STATE.lastQuoteTime) < 30000) {
    return STATE.quotes[ticker];
  }
  try {
    const data = await apiFetch(`/api/quote?ticker=${encodeURIComponent(ticker)}`);
    STATE.quotes[ticker] = data;
    STATE.lastQuoteTime = Date.now();
    return data;
  } catch(e) {
    // Return last cached value if available
    return STATE.quotes[ticker] || null;
  }
}

async function refreshAllQuotes() {
  const tickers = STATE.portfolio.map(p => p.ticker);
  if (!tickers.length) return;
  document.getElementById('lastUpdated').textContent = 'Refreshing…';
  try {
    await Promise.all(tickers.map(t => fetchQuote(t)));
    document.getElementById('lastUpdated').textContent =
      `Updated ${new Date().toLocaleTimeString()}`;
    renderHoldingsTable();
    updateHeaderStats();
    calculateAndRenderGrade();
  } catch(e) {
    document.getElementById('lastUpdated').textContent = 'Refresh failed';
  }
}

function startAutoRefresh() {
  // Refresh quotes every 60 seconds while page is visible
  setInterval(() => {
    if (!document.hidden && STATE.portfolio.length > 0) refreshAllQuotes();
  }, 60000);
}

/* ============================================================
   10. PORTFOLIO BUILDER — EVENTS
   ============================================================ */
function initPortfolioBuilderEvents() {
  // Add position button
  document.getElementById('addPositionBtn').addEventListener('click', addPositionFromForm);

  // Enter key on ticker/shares
  ['inputTicker','inputShares','inputAvgCost'].forEach(id => {
    document.getElementById(id).addEventListener('keydown', e => {
      if (e.key === 'Enter') addPositionFromForm();
    });
  });

  // Preset templates
  document.querySelectorAll('.preset-chip[data-preset]').forEach(chip => {
    chip.addEventListener('click', () => loadPreset(chip.dataset.preset));
  });

  // Refresh quotes button
  document.getElementById('refreshQuotesBtn').addEventListener('click', refreshAllQuotes);
}

function addPositionFromForm() {
  const ticker  = document.getElementById('inputTicker').value.trim().toUpperCase();
  const shares  = parseFloat(document.getElementById('inputShares').value);
  const avgCost = parseFloat(document.getElementById('inputAvgCost').value) || 0;

  if (!ticker || isNaN(shares) || shares <= 0) {
    flashInput('inputTicker');
    return;
  }

  addPosition({ ticker, shares, avgCost });

  // Clear form
  document.getElementById('inputTicker').value  = '';
  document.getElementById('inputShares').value  = '';
  document.getElementById('inputAvgCost').value = '';
  document.getElementById('inputTicker').focus();
}

function flashInput(id) {
  const el = document.getElementById(id);
  el.style.borderColor = 'var(--red)';
  setTimeout(() => el.style.borderColor = '', 1000);
}

function addPosition(pos) {
  // If ticker already exists, merge shares
  const existing = STATE.portfolio.find(p => p.ticker === pos.ticker);
  if (existing) {
    const totalCost = (existing.avgCost * existing.shares) + (pos.avgCost * pos.shares);
    existing.shares   += pos.shares;
    existing.avgCost   = pos.avgCost > 0 ? totalCost / existing.shares : existing.avgCost;
  } else {
    STATE.portfolio.push({
      ticker:  pos.ticker,
      shares:  pos.shares,
      avgCost: pos.avgCost || 0,
      type:    ASSET_TYPES[pos.ticker] || 'Stock',
      addedAt: Date.now(),
    });
  }
  saveToStorage();
  renderPortfolio();
  fetchQuote(pos.ticker).then(() => {
    renderHoldingsTable();
    updateHeaderStats();
    calculateAndRenderGrade();
  });
}

function removePosition(ticker) {
  STATE.portfolio = STATE.portfolio.filter(p => p.ticker !== ticker);
  delete STATE.quotes[ticker];
  saveToStorage();
  renderPortfolio();
  updateHeaderStats();
  calculateAndRenderGrade();
}

function loadPreset(presetKey) {
  const positions = PRESET_PORTFOLIOS[presetKey];
  if (!positions) return;
  STATE.portfolio = [];
  positions.forEach(p => STATE.portfolio.push({
    ...p,
    type: ASSET_TYPES[p.ticker] || 'Stock',
    addedAt: Date.now(),
  }));
  saveToStorage();
  renderPortfolio();
  refreshAllQuotes();
}

/* ============================================================
   11. CSV UPLOAD
   ============================================================ */
function initCSVUpload() {
  document.getElementById('csvUpload').addEventListener('change', e => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
      const rows = ev.target.result.split('\n').slice(1); // skip header
      let added = 0;
      rows.forEach(row => {
        const cols = row.split(',').map(c => c.trim().replace(/"/g,''));
        if (cols.length >= 2 && cols[0]) {
          const ticker  = cols[0].toUpperCase();
          const shares  = parseFloat(cols[1]) || 0;
          const avgCost = parseFloat(cols[2]) || 0;
          if (ticker && shares > 0) {
            STATE.portfolio.push({
              ticker, shares, avgCost,
              type: ASSET_TYPES[ticker] || 'Stock',
              addedAt: Date.now(),
            });
            added++;
          }
        }
      });
      saveToStorage();
      renderPortfolio();
      if (added > 0) refreshAllQuotes();
    };
    reader.readAsText(file);
    e.target.value = ''; // reset input
  });
}

/* ============================================================
   12. RENDER PORTFOLIO (Main function)
   ============================================================ */
function renderPortfolio() {
  renderPositionsList();
  renderHoldingsTable();
  renderAllocationDonut();
}

/* ============================================================
   13. POSITIONS LIST (Quick-Build panel)
   ============================================================ */
function renderPositionsList() {
  const container = document.getElementById('positionsList');
  const empty     = document.getElementById('positionsEmpty');

  if (STATE.portfolio.length === 0) {
    empty.classList.remove('hidden');
    return;
  }
  empty.classList.add('hidden');

  // Build list of added tickers
  const existing = container.querySelectorAll('.position-row');
  const rendered = new Set([...existing].map(r => r.dataset.ticker));
  const current  = new Set(STATE.portfolio.map(p => p.ticker));

  // Remove deleted rows
  existing.forEach(row => {
    if (!current.has(row.dataset.ticker)) row.remove();
  });

  // Add new rows
  STATE.portfolio.forEach(pos => {
    if (rendered.has(pos.ticker)) return;
    const row = document.createElement('div');
    row.className = 'position-row flex items-center justify-between gap-2 mb-2';
    row.dataset.ticker = pos.ticker;
    row.style.cssText = 'padding:8px 10px;background:var(--bg2);border-radius:var(--radius-row);border:1px solid var(--border);';
    row.innerHTML = `
      <span class="mono font-bold" style="color:var(--white);min-width:55px;">${pos.ticker}</span>
      <span class="text-muted text-sm">${pos.shares} shares</span>
      <span class="mono text-sm" style="color:var(--text3);">@ $${pos.avgCost > 0 ? pos.avgCost.toFixed(2) : '—'}</span>
      <span class="badge ${getBadgeClass(pos.type)}">${pos.type}</span>
      <button class="btn btn-sm btn-danger" onclick="removePosition('${pos.ticker}')">✕</button>
    `;
    container.appendChild(row);
  });
}

function getBadgeClass(type) {
  if (type === 'ETF')    return 'badge-etf';
  if (type === 'Crypto') return 'badge-crypto';
  return 'badge-stock';
}

/* ============================================================
   14. HOLDINGS TABLE
   ============================================================ */
function renderHoldingsTable() {
  const tbody = document.getElementById('holdingsBody');
  if (STATE.portfolio.length === 0) {
    tbody.innerHTML = `<tr><td colspan="12">
      <div class="empty-state">
        <div class="empty-state-icon">◈</div>
        <div class="empty-state-title">Portfolio is empty</div>
        <div class="empty-state-msg">Add positions using the Quick Build panel above</div>
      </div></td></tr>`;
    return;
  }

  // Calculate total market value
  let totalValue = 0;
  STATE.portfolio.forEach(pos => {
    const q = STATE.quotes[pos.ticker];
    const price = q ? q.price : pos.avgCost;
    totalValue += price * pos.shares;
  });

  tbody.innerHTML = STATE.portfolio.map(pos => {
    const q = STATE.quotes[pos.ticker];
    const price      = q ? q.price     : pos.avgCost;
    const change     = q ? q.change    : 0;
    const changePct  = q ? q.changePct : 0;
    const value      = price * pos.shares;
    const cost       = pos.avgCost * pos.shares;
    const pnl        = pos.avgCost > 0 ? value - cost : 0;
    const pnlPct     = pos.avgCost > 0 && cost > 0 ? (pnl / cost) * 100 : 0;
    const weight     = totalValue > 0 ? (value / totalValue) * 100 : 0;
    const isLoading  = !q;

    const pnlClass    = pnl >= 0    ? 'positive' : 'negative';
    const changeClass = change >= 0 ? 'positive' : 'negative';

    return `<tr data-ticker="${pos.ticker}">
      <td><span class="mono font-bold" style="color:var(--white);">${pos.ticker}</span></td>
      <td class="truncate" style="max-width:120px;">${getTickerName(pos.ticker)}</td>
      <td><span class="badge ${getBadgeClass(pos.type)}">${pos.type}</span></td>
      <td class="mono">${fmtNum(pos.shares)}</td>
      <td class="mono">${pos.avgCost > 0 ? fmtCurrency(pos.avgCost) : '—'}</td>
      <td class="mono ${isLoading ? '' : ''}">${isLoading ? skeletonCell() : fmtCurrency(price)}</td>
      <td class="mono">${isLoading ? skeletonCell() : fmtCurrency(value)}</td>
      <td class="mono ${pnlClass}">${pos.avgCost > 0 ? (pnl >= 0 ? '+' : '') + fmtCurrency(pnl) : '—'}</td>
      <td class="mono ${pnlClass}">${pos.avgCost > 0 ? (pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%' : '—'}</td>
      <td class="mono ${changeClass}">${isLoading ? skeletonCell() : (change >= 0 ? '+' : '') + fmtCurrency(change) + ' (' + (changePct >= 0 ? '+' : '') + changePct.toFixed(2) + '%)'}</td>
      <td class="mono">${weight.toFixed(1)}%</td>
      <td><button class="btn btn-sm btn-danger btn-icon" onclick="removePosition('${pos.ticker}')" title="Remove">✕</button></td>
    </tr>`;
  }).join('');
}

function skeletonCell() {
  return `<span class="skeleton skeleton-text w-60" style="display:inline-block;height:10px;"></span>`;
}

/* ============================================================
   15. ALLOCATION DONUT
   ============================================================ */
function renderAllocationDonut() {
  const canvas = document.getElementById('allocationDonut');
  const empty  = document.getElementById('donutEmpty');
  const legend = document.getElementById('donutLegend');

  if (STATE.portfolio.length === 0) {
    empty.classList.remove('hidden');
    if (STATE.charts.allocationDonut) {
      STATE.charts.allocationDonut.destroy();
      delete STATE.charts.allocationDonut;
    }
    legend.innerHTML = '';
    return;
  }
  empty.classList.add('hidden');

  // Calculate values
  let totalValue = 0;
  const positions = STATE.portfolio.map(pos => {
    const q = STATE.quotes[pos.ticker];
    const price = q ? q.price : (pos.avgCost || 1);
    const value = price * pos.shares;
    totalValue += value;
    return { ticker: pos.ticker, value };
  });

  // Sort by value, top 8 + Others
  positions.sort((a, b) => b.value - a.value);
  const top8  = positions.slice(0, 8);
  const rest  = positions.slice(8);
  const otherVal = rest.reduce((s, p) => s + p.value, 0);
  if (otherVal > 0) top8.push({ ticker: 'Other', value: otherVal });

  const labels = top8.map(p => p.ticker);
  const data   = top8.map(p => p.value);
  const colors = top8.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);

  destroyChart('allocationDonut');

  STATE.charts.allocationDonut = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data, backgroundColor: colors, borderColor: 'var(--bg1)', borderWidth: 2, hoverOffset: 8 }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${fmtCurrency(ctx.raw)} (${((ctx.raw/totalValue)*100).toFixed(1)}%)`
          }
        }
      }
    }
  });

  // Legend
  legend.innerHTML = top8.map((p, i) => `
    <div class="flex items-center gap-2 mb-1" style="cursor:pointer;" onclick="highlightHoldingRow('${p.ticker}')">
      <span style="width:8px;height:8px;border-radius:50%;background:${colors[i]};flex-shrink:0;display:inline-block;"></span>
      <span class="text-sm mono" style="color:var(--text2);">${p.ticker}</span>
      <span class="text-xs" style="color:var(--text3);margin-left:auto;">${((p.value/totalValue)*100).toFixed(1)}%</span>
    </div>`).join('');
}

function highlightHoldingRow(ticker) {
  document.querySelectorAll('#holdingsBody tr').forEach(row => {
    row.style.background = row.dataset.ticker === ticker ? 'var(--bg3)' : '';
  });
}

/* ============================================================
   16. HEADER STATS UPDATE
   ============================================================ */
function updateHeaderStats() {
  if (STATE.portfolio.length === 0) {
    ['hNavValue','hDayPnl','hBeta','hSharpe'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = '—';
    });
    updatePortfolioStatBoxes(0, 0, 0, 0);
    return;
  }

  let totalValue = 0, totalCost = 0, totalDayChange = 0;
  STATE.portfolio.forEach(pos => {
    const q = STATE.quotes[pos.ticker];
    const price  = q ? q.price  : (pos.avgCost || 0);
    const change = q ? q.change : 0;
    totalValue     += price * pos.shares;
    totalCost      += (pos.avgCost || 0) * pos.shares;
    totalDayChange += change * pos.shares;
  });

  const totalReturn = totalCost > 0 ? totalValue - totalCost : 0;
  const returnPct   = totalCost > 0 ? (totalReturn / totalCost) * 100 : 0;

  const navEl = document.getElementById('hNavValue');
  const pnlEl = document.getElementById('hDayPnl');
  if (navEl) navEl.textContent = fmtCurrency(totalValue);
  if (pnlEl) {
    pnlEl.textContent = (totalDayChange >= 0 ? '+' : '') + fmtCurrency(totalDayChange);
    pnlEl.className = `header-stat-value mono ${totalDayChange >= 0 ? 'positive' : 'negative'}`;
  }

  updatePortfolioStatBoxes(totalValue, totalReturn, returnPct, STATE.portfolio.length);
}

function updatePortfolioStatBoxes(nav, ret, retPct, count) {
  const el = (id) => document.getElementById(id);

  animateNumber(el('statNav'),     nav,    fmtCurrency);
  animateNumber(el('statReturn'),  ret,    v => (v >= 0 ? '+' : '') + fmtCurrency(v));
  if (el('statReturnPct')) {
    el('statReturnPct').textContent = (retPct >= 0 ? '+' : '') + retPct.toFixed(2) + '%';
    el('statReturnPct').className   = `stat-sub ${retPct >= 0 ? 'text-green' : 'text-red'}`;
  }
  if (el('statPositions')) el('statPositions').textContent = count;

  const statNav    = el('statNav');
  const statReturn = el('statReturn');
  if (statNav)    statNav.className    = 'stat-value mono';
  if (statReturn) statReturn.className = `stat-value mono ${ret >= 0 ? 'positive' : 'negative'}`;
}

/* ============================================================
   17. PORTFOLIO GRADE CALCULATOR
   ============================================================ */
function calculateAndRenderGrade() {
  if (STATE.portfolio.length === 0) {
    document.getElementById('gradeLetter').textContent = '—';
    return;
  }

  let totalValue = 0;
  const positions = STATE.portfolio.map(pos => {
    const q = STATE.quotes[pos.ticker];
    const price = q ? q.price : (pos.avgCost || 1);
    const value = price * pos.shares;
    totalValue += value;
    return { ...pos, value, type: pos.type || ASSET_TYPES[pos.ticker] || 'Stock' };
  });

  const weights = positions.map(p => p.value / totalValue);

  // 1. Diversification (number of positions, 0–100)
  const n = positions.length;
  const divScore = Math.min(100, n <= 1 ? 10 : n <= 3 ? 35 : n <= 6 ? 60 : n <= 10 ? 80 : 100);

  // 2. Concentration Risk (top position weight)
  const maxWeight = Math.max(...weights) * 100;
  const concScore = maxWeight > 50 ? 20 : maxWeight > 35 ? 45 : maxWeight > 25 ? 65 : maxWeight > 15 ? 80 : 100;

  // 3. Sector Balance (unique sectors)
  const sectors = new Set(positions.map(p => SECTOR_MAP[p.ticker] || 'Other'));
  const sectorScore = Math.min(100, sectors.size * 14);

  // 4. Geographic Spread (penalize >80% domestic)
  const intlWeight = positions
    .filter(p => ['VXUS','VEA','EFA','VWO','EEM'].includes(p.ticker))
    .reduce((s, p, i) => s + (weights[positions.indexOf(p)] || 0), 0) * 100;
  const geoScore = intlWeight > 20 ? 100 : intlWeight > 10 ? 75 : intlWeight > 5 ? 55 : 35;

  // 5. Volatility (penalize crypto and leveraged ETFs)
  const cryptoWeight = positions
    .filter(p => p.type === 'Crypto')
    .reduce((s, p) => s + (p.value / totalValue), 0) * 100;
  const leveragedWeight = positions
    .filter(p => ['TQQQ','SQQQ','UPRO','SPXU'].includes(p.ticker))
    .reduce((s, p) => s + (p.value / totalValue), 0) * 100;
  const volScore = Math.max(0, 100 - (cryptoWeight * 1.5) - (leveragedWeight * 2));

  // Composite
  const composite = (divScore * 0.25 + concScore * 0.25 + sectorScore * 0.2 + geoScore * 0.15 + volScore * 0.15);
  const grade = composite >= 85 ? 'A' : composite >= 70 ? 'B' : composite >= 55 ? 'C' : composite >= 40 ? 'D' : 'F';

  const gradeEl = document.getElementById('gradeLetter');
  gradeEl.textContent = grade;
  gradeEl.className   = `grade-letter ${grade}`;

  // Sub-scores
  const subscores = [
    { label: 'Diversification',     score: divScore,    color: 'blue'  },
    { label: 'Concentration Risk',  score: concScore,   color: 'sky'   },
    { label: 'Sector Balance',      score: sectorScore, color: 'green' },
    { label: 'Geographic Spread',   score: geoScore,    color: 'amber' },
    { label: 'Volatility Level',    score: volScore,    color: 'blue'  },
  ];

  document.getElementById('gradeSubscores').innerHTML = subscores.map(s => `
    <div class="subscore-row">
      <span class="subscore-label">${s.label}</span>
      <div class="subscore-bar">
        <div class="progress-bar-fill ${s.color}" style="width:${s.score}%"></div>
      </div>
      <span class="subscore-score">${Math.round(s.score)}</span>
    </div>`).join('');
}

/* ============================================================
   18. EXPOSURE TAB
   ============================================================ */
function renderExposureTab() {
  renderSectorDonut();
  renderGeoDonut();
  renderCapDonut();
  renderRebalanceSuggester();
  loadEtfLookThrough();
}

function renderSectorDonut() {
  if (STATE.portfolio.length === 0) return;
  const sectorWeights = {};
  let totalValue = 0;
  STATE.portfolio.forEach(pos => {
    const q = STATE.quotes[pos.ticker];
    const price = q ? q.price : (pos.avgCost || 1);
    const value = price * pos.shares;
    totalValue += value;
    const sector = SECTOR_MAP[pos.ticker] || 'Other';
    sectorWeights[sector] = (sectorWeights[sector] || 0) + value;
  });
  renderSmallDonut('sectorDonut', sectorWeights, totalValue, 'sectorLegend');
}

function renderGeoDonut() {
  const geoData = {
    'US Domestic': 0, 'Intl Developed': 0, 'Emerging Markets': 0, 'Other': 0
  };
  let totalValue = 0;
  const intlTickers   = ['VXUS','VEA','EFA','VWO'];
  const emergingTickers = ['VWO','EEM'];

  STATE.portfolio.forEach(pos => {
    const q = STATE.quotes[pos.ticker];
    const price = q ? q.price : (pos.avgCost || 1);
    const value = price * pos.shares;
    totalValue += value;
    if (emergingTickers.includes(pos.ticker)) geoData['Emerging Markets'] += value;
    else if (intlTickers.includes(pos.ticker)) geoData['Intl Developed'] += value;
    else if (pos.type === 'Crypto') geoData['Other'] += value;
    else geoData['US Domestic'] += value;
  });
  renderSmallDonut('geoDonut', geoData, totalValue, 'geoLegend');
}

function renderCapDonut() {
  const capData = { 'Mega Cap': 0, 'Large Cap': 0, 'Mid Cap': 0, 'Small Cap': 0 };
  const megaTickers  = ['AAPL','MSFT','NVDA','GOOGL','AMZN','META','TSLA','BERKB'];
  const largeTickers = ['JPM','JNJ','V','UNH','XOM','CVX','BAC','WMT'];
  const midTickers   = ['SNAP','PINS','RBLX','DKNG','PLTR'];
  let totalValue = 0;

  STATE.portfolio.forEach(pos => {
    const q = STATE.quotes[pos.ticker];
    const price = q ? q.price : (pos.avgCost || 1);
    const value = price * pos.shares;
    totalValue += value;
    if (megaTickers.includes(pos.ticker))  capData['Mega Cap']  += value;
    else if (largeTickers.includes(pos.ticker)) capData['Large Cap'] += value;
    else if (midTickers.includes(pos.ticker))   capData['Mid Cap']   += value;
    else if (pos.type === 'ETF') capData['Large Cap'] += value; // ETFs mostly large
    else capData['Mid Cap'] += value;
  });
  renderSmallDonut('capDonut', capData, totalValue, 'capLegend');
}

function renderSmallDonut(canvasId, dataObj, totalValue, legendId) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const entries = Object.entries(dataObj).filter(([,v]) => v > 0);
  const labels  = entries.map(([k]) => k);
  const data    = entries.map(([,v]) => v);
  const colors  = labels.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);

  destroyChart(canvasId);
  STATE.charts[canvasId] = new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{ data, backgroundColor: colors, borderColor: 'var(--bg1)', borderWidth: 2, hoverOffset: 6 }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${((ctx.raw/totalValue)*100).toFixed(1)}%`
          }
        }
      }
    }
  });

  const legendEl = document.getElementById(legendId);
  if (legendEl) {
    legendEl.innerHTML = labels.map((l, i) => `
      <div class="flex items-center gap-2 mb-1">
        <span style="width:7px;height:7px;border-radius:50%;background:${colors[i]};display:inline-block;flex-shrink:0;"></span>
        <span class="text-xs" style="color:var(--text2);">${l}</span>
        <span class="text-xs" style="color:var(--text3);margin-left:auto;">${((data[i]/totalValue)*100).toFixed(1)}%</span>
      </div>`).join('');
  }
}

/* ============================================================
   19. ETF LOOK-THROUGH
   ============================================================ */
async function loadEtfLookThrough() {
  const etfs = STATE.portfolio.filter(p => p.type === 'ETF');
  const container = document.getElementById('etfLookThroughContent');
  if (etfs.length === 0) {
    container.innerHTML = `<div class="empty-state">
      <div class="empty-state-icon">◎</div>
      <div class="empty-state-title">No ETFs in portfolio</div>
      <div class="empty-state-msg">Add ETFs (e.g. SPY, QQQ, VTI) to see look-through holdings</div>
    </div>`;
    return;
  }

  container.innerHTML = `<div class="skeleton skeleton-chart mb-2"></div>
    <div class="skeleton skeleton-text w-80 mb-1"></div>
    <div class="skeleton skeleton-text w-60"></div>`;

  try {
    const results = await Promise.all(
      etfs.map(e => apiFetch(`/api/etf?ticker=${e.ticker}`)
        .then(d => ({ ticker: e.ticker, holdings: d.holdings || [] }))
        .catch(() => ({ ticker: e.ticker, holdings: getFallbackHoldings(e.ticker) }))
      )
    );

    let html = '';
    results.forEach(r => {
      html += `<div class="mb-3">
        <div class="flex items-center gap-2 mb-2">
          <span class="badge badge-etf">${r.ticker}</span>
          <span class="text-sm text-muted">Top 10 Holdings</span>
        </div>
        <div class="table-scroll">
        <table class="data-table">
          <thead><tr><th>Holding</th><th>Name</th><th>Weight %</th><th>Bar</th></tr></thead>
          <tbody>
            ${r.holdings.slice(0, 10).map(h => `
              <tr>
                <td class="mono font-bold">${h.ticker || '—'}</td>
                <td class="text-muted truncate" style="max-width:140px;">${h.name || '—'}</td>
                <td class="mono">${(h.weight || 0).toFixed(2)}%</td>
                <td style="width:100px;">
                  <div class="progress-bar-track"><div class="progress-bar-fill blue" style="width:${Math.min(100,h.weight||0)*3}%"></div></div>
                </td>
              </tr>`).join('')}
          </tbody>
        </table></div></div>`;
    });
    container.innerHTML = html;
  } catch(e) {
    container.innerHTML = renderErrorState('Failed to load ETF holdings', () => loadEtfLookThrough());
  }
}

function getFallbackHoldings(ticker) {
  const fallbacks = {
    SPY: [
      {ticker:'AAPL',name:'Apple Inc',weight:7.1},{ticker:'MSFT',name:'Microsoft',weight:6.5},
      {ticker:'NVDA',name:'NVIDIA',weight:5.9},{ticker:'AMZN',name:'Amazon',weight:3.8},
      {ticker:'META',name:'Meta Platforms',weight:2.7},{ticker:'GOOGL',name:'Alphabet A',weight:2.3},
      {ticker:'GOOG',name:'Alphabet C',weight:2.2},{ticker:'TSLA',name:'Tesla',weight:1.9},
      {ticker:'BRK.B',name:'Berkshire B',weight:1.7},{ticker:'UNH',name:'UnitedHealth',weight:1.4},
    ],
    QQQ: [
      {ticker:'MSFT',name:'Microsoft',weight:8.4},{ticker:'AAPL',name:'Apple Inc',weight:7.9},
      {ticker:'NVDA',name:'NVIDIA',weight:7.5},{ticker:'AMZN',name:'Amazon',weight:5.3},
      {ticker:'META',name:'Meta Platforms',weight:4.9},{ticker:'TSLA',name:'Tesla',weight:3.5},
      {ticker:'GOOGL',name:'Alphabet A',weight:3.1},{ticker:'GOOG',name:'Alphabet C',weight:3.0},
      {ticker:'AVGO',name:'Broadcom',weight:2.8},{ticker:'COST',name:'Costco',weight:2.1},
    ],
    VTI: [
      {ticker:'MSFT',name:'Microsoft',weight:5.8},{ticker:'AAPL',name:'Apple Inc',weight:5.5},
      {ticker:'NVDA',name:'NVIDIA',weight:4.9},{ticker:'AMZN',name:'Amazon',weight:3.2},
      {ticker:'META',name:'Meta Platforms',weight:2.4},{ticker:'GOOGL',name:'Alphabet A',weight:1.9},
      {ticker:'GOOG',name:'Alphabet C',weight:1.8},{ticker:'TSLA',name:'Tesla',weight:1.5},
      {ticker:'BRK.B',name:'Berkshire B',weight:1.4},{ticker:'UNH',name:'UnitedHealth',weight:1.2},
    ],
  };
  return fallbacks[ticker] || [{ticker:'N/A',name:'Fallback not available',weight:0}];
}

/* ============================================================
   20. REBALANCE SUGGESTER
   ============================================================ */
function renderRebalanceSuggester() {
  const container = document.getElementById('rebalanceContent');
  if (STATE.portfolio.length === 0) return;

  let totalValue = 0;
  const positions = STATE.portfolio.map(pos => {
    const q = STATE.quotes[pos.ticker];
    const price = q ? q.price : (pos.avgCost || 1);
    const value = price * pos.shares;
    totalValue += value;
    return { ...pos, value, price };
  });

  const equal = (100 / positions.length).toFixed(1);

  container.innerHTML = `
    <p class="text-sm text-muted mb-3">Set target allocation % for each position (must sum to 100%)</p>
    <div class="table-scroll">
    <table class="data-table" id="rebalanceTable">
      <thead><tr>
        <th>Ticker</th><th>Current Value</th><th>Current %</th>
        <th>Target %</th><th>Drift</th><th>Action</th>
      </tr></thead>
      <tbody>
        ${positions.map((pos, i) => {
          const currentPct = totalValue > 0 ? (pos.value / totalValue) * 100 : 0;
          return `<tr>
            <td class="mono font-bold">${pos.ticker}</td>
            <td class="mono">${fmtCurrency(pos.value)}</td>
            <td class="mono">${currentPct.toFixed(1)}%</td>
            <td><input type="number" class="form-input mono rebalance-target"
                style="width:70px;padding:4px 6px;"
                data-ticker="${pos.ticker}"
                data-price="${pos.price}"
                value="${equal}" min="0" max="100" step="0.1"
                onchange="updateRebalanceRow(this, ${totalValue})" /></td>
            <td class="mono rebalance-drift" id="drift-${pos.ticker}">—</td>
            <td class="rebalance-action" id="action-${pos.ticker}">—</td>
          </tr>`;
        }).join('')}
      </tbody>
    </table></div>
    <div class="flex items-center gap-2 mt-3">
      <span class="text-sm text-muted">Target sum: <span id="targetSum" class="mono">—</span></span>
      <span id="targetSumStatus" class="badge">—</span>
    </div>`;

  // Initialize all rows
  document.querySelectorAll('.rebalance-target').forEach(inp => {
    updateRebalanceRow(inp, totalValue);
  });
}

function updateRebalanceRow(input, totalValue) {
  const ticker  = input.dataset.ticker;
  const price   = parseFloat(input.dataset.price) || 1;
  const target  = parseFloat(input.value) || 0;

  const pos = STATE.portfolio.find(p => p.ticker === ticker);
  if (!pos) return;

  const q = STATE.quotes[ticker];
  const currentPrice = q ? q.price : price;
  const currentValue = currentPrice * pos.shares;
  const currentPct   = totalValue > 0 ? (currentValue / totalValue) * 100 : 0;
  const drift        = target - currentPct;
  const targetValue  = (target / 100) * totalValue;
  const targetShares = targetValue / currentPrice;
  const sharesDiff   = targetShares - pos.shares;

  const driftEl  = document.getElementById(`drift-${ticker}`);
  const actionEl = document.getElementById(`action-${ticker}`);

  if (driftEl) {
    driftEl.textContent  = (drift >= 0 ? '+' : '') + drift.toFixed(1) + '%';
    driftEl.className    = `mono rebalance-drift ${drift > 0 ? 'text-green' : drift < 0 ? 'text-red' : 'text-muted'}`;
  }
  if (actionEl) {
    if (Math.abs(sharesDiff) < 0.01) {
      actionEl.textContent = 'HOLD';
      actionEl.className   = 'rebalance-action hold';
    } else if (sharesDiff > 0) {
      actionEl.textContent = `BUY ${sharesDiff.toFixed(2)} shares`;
      actionEl.className   = 'rebalance-action buy';
    } else {
      actionEl.textContent = `SELL ${Math.abs(sharesDiff).toFixed(2)} shares`;
      actionEl.className   = 'rebalance-action sell';
    }
  }

  // Update sum
  let sum = 0;
  document.querySelectorAll('.rebalance-target').forEach(inp => { sum += parseFloat(inp.value) || 0; });
  const sumEl    = document.getElementById('targetSum');
  const statusEl = document.getElementById('targetSumStatus');
  if (sumEl) sumEl.textContent = sum.toFixed(1) + '%';
  if (statusEl) {
    const diff = Math.abs(sum - 100);
    statusEl.textContent = diff < 0.1 ? '✓ Valid' : `${sum.toFixed(1)}% (needs 100%)`;
    statusEl.className   = `badge ${diff < 0.1 ? 'badge-green' : 'badge-amber'}`;
  }
}

/* ============================================================
   21. RISK TAB
   ============================================================ */
function renderRiskTab() {
  renderRiskGauge();
  document.getElementById('runAnalyticsBtn').addEventListener('click', runPortfolioAnalytics);
  document.getElementById('runCorrelationBtn').addEventListener('click', runCorrelation);
  document.getElementById('runDrawdownBtn').addEventListener('click', runDrawdown);
  document.getElementById('runDividendsBtn').addEventListener('click', runDividends);
  document.getElementById('runFrontierBtn').addEventListener('click', runEfficientFrontier);
}

function renderRiskGauge() {
  if (STATE.portfolio.length === 0) return;

  // Calculate risk score (same logic as grade but inverted)
  let totalValue = 0;
  const positions = STATE.portfolio.map(pos => {
    const q = STATE.quotes[pos.ticker];
    const price = q ? q.price : (pos.avgCost || 1);
    const value = price * pos.shares;
    totalValue += value;
    return { ...pos, value };
  });

  const weights = positions.map(p => p.value / totalValue);
  const maxWeight  = Math.max(...weights) * 100;
  const cryptoPct  = positions.filter(p => p.type === 'Crypto')
    .reduce((s, p, i) => s + (p.value/totalValue*100), 0);
  const leverPct   = positions.filter(p => ['TQQQ','SQQQ','UPRO','SPXU'].includes(p.ticker))
    .reduce((s, p) => s + (p.value/totalValue*100), 0);
  const sectorCount = new Set(positions.map(p => SECTOR_MAP[p.ticker] || 'Other')).size;

  // Beta proxy (simplified)
  const betaProxy = 1.0 + (cryptoPct * 0.03) + (leverPct * 0.05) - (sectorCount * 0.02);

  // Risk score 0–100
  let score = 30; // Base
  score += Math.max(0, maxWeight - 20) * 0.8;       // Concentration
  score += cryptoPct * 0.6;                          // Crypto exposure
  score += leverPct  * 1.2;                          // Leveraged ETFs
  score += Math.max(0, (1.5 - betaProxy)) * -10;    // Low beta = lower risk
  score += Math.max(0, (betaProxy - 1.5)) * 15;     // High beta = higher risk
  score  = Math.min(100, Math.max(0, score));

  const label = score < 30 ? 'Conservative' : score < 60 ? 'Moderate' : score < 85 ? 'Aggressive' : 'Extreme Risk';
  const color = score < 30 ? '#3dbc72' : score < 60 ? '#d4a03d' : score < 85 ? '#c87a3d' : '#d44a4a';

  document.getElementById('gaugeNumber').textContent = Math.round(score);
  document.getElementById('gaugeNumber').style.color = color;
  document.getElementById('gaugeLabel').textContent  = label;
  document.getElementById('gaugeLabel').style.color  = color;

  drawGaugeArc('riskGauge', score, color);

  // Risk factor breakdown
  const factors = [
    { label: 'Concentration',    value: Math.min(100, maxWeight * 1.5),  note: `Top position: ${maxWeight.toFixed(1)}%` },
    { label: 'Crypto Exposure',  value: Math.min(100, cryptoPct * 2),     note: `${cryptoPct.toFixed(1)}% in crypto` },
    { label: 'Leverage',         value: Math.min(100, leverPct * 4),      note: `${leverPct.toFixed(1)}% leveraged ETFs` },
    { label: 'Sector Diversity', value: Math.max(0, 100 - sectorCount*14), note: `${sectorCount} sectors` },
    { label: 'Market Beta',      value: Math.min(100, betaProxy * 50),    note: `Est. β ${betaProxy.toFixed(2)}` },
  ];

  document.getElementById('riskFactors').innerHTML = factors.map(f => `
    <div class="subscore-row mb-2">
      <div class="flex justify-between mb-1">
        <span class="text-sm">${f.label}</span>
        <span class="text-xs text-muted">${f.note}</span>
      </div>
      <div class="progress-bar-track">
        <div class="progress-bar-fill" style="width:${f.value}%;background:${f.value>66?'var(--red)':f.value>33?'var(--amber)':'var(--green)'}"></div>
      </div>
    </div>`).join('');
}

function drawGaugeArc(canvasId, score, activeColor) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const cx = canvas.width / 2, cy = canvas.height - 10;
  const r  = 90;
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Background arc
  ctx.beginPath();
  ctx.arc(cx, cy, r, Math.PI, 0, false);
  ctx.lineWidth = 14;
  ctx.strokeStyle = 'rgba(36,42,56,0.8)';
  ctx.stroke();

  // Colored arc zones
  const zones = [
    { from: 0, to: 30,  color: '#3dbc72' },
    { from: 30, to: 60, color: '#d4a03d' },
    { from: 60, to: 85, color: '#c87a3d' },
    { from: 85, to: 100,color: '#d44a4a' },
  ];
  zones.forEach(z => {
    const startAngle = Math.PI + (z.from / 100) * Math.PI;
    const endAngle   = Math.PI + (z.to   / 100) * Math.PI;
    ctx.beginPath();
    ctx.arc(cx, cy, r, startAngle, endAngle, false);
    ctx.lineWidth = 14;
    ctx.strokeStyle = z.color + '40';
    ctx.stroke();
  });

  // Active progress
  const endAngle = Math.PI + (score / 100) * Math.PI;
  ctx.beginPath();
  ctx.arc(cx, cy, r, Math.PI, endAngle, false);
  ctx.lineWidth = 14;
  ctx.strokeStyle = activeColor;
  ctx.lineCap = 'round';
  ctx.stroke();

  // Needle dot
  const needleAngle = Math.PI + (score / 100) * Math.PI;
  const nx = cx + r * Math.cos(needleAngle);
  const ny = cy + r * Math.sin(needleAngle);
  ctx.beginPath();
  ctx.arc(nx, ny, 7, 0, Math.PI * 2);
  ctx.fillStyle = activeColor;
  ctx.fill();
  ctx.beginPath();
  ctx.arc(nx, ny, 3, 0, Math.PI * 2);
  ctx.fillStyle = '#fff';
  ctx.fill();
}

/* ============================================================
   22. PORTFOLIO ANALYTICS API CALL
   ============================================================ */
async function runPortfolioAnalytics() {
  const btn = document.getElementById('runAnalyticsBtn');
  const container = document.getElementById('analyticsContent');
  if (STATE.portfolio.length === 0) return;

  btn.textContent = 'Running…';
  btn.disabled    = true;
  container.innerHTML = renderSkeletonGrid(8);

  const payload = {
    holdings: STATE.portfolio.map(p => ({ ticker: p.ticker, shares: p.shares, weight: 0 }))
  };

  try {
    const data = await apiFetch('/api/portfolio_analytics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    STATE.analyticsData = data;

    // Update header
    if (data.beta   !== undefined) document.getElementById('hBeta').textContent   = data.beta.toFixed(3);
    if (data.sharpe !== undefined) document.getElementById('hSharpe').textContent = data.sharpe.toFixed(3);

    const metrics = [
      { label: 'Beta (vs SPY)',     value: data.beta,       fmt: v => v.toFixed(3),               tooltip: 'Sensitivity to S&P 500 market moves. Beta > 1 means more volatile than market.' },
      { label: 'Alpha (Annual)',    value: data.alpha,      fmt: v => (v*100).toFixed(2)+'%',      tooltip: "Jensen's Alpha — excess return above CAPM expectation." },
      { label: 'Sharpe Ratio',      value: data.sharpe,     fmt: v => v.toFixed(3),               tooltip: 'Return per unit of total risk (annualized). Higher is better.' },
      { label: 'Sortino Ratio',     value: data.sortino,    fmt: v => v.toFixed(3),               tooltip: 'Return per unit of downside risk only. Penalizes bad volatility more.' },
      { label: 'Treynor Ratio',     value: data.treynor,    fmt: v => v.toFixed(4),               tooltip: 'Excess return per unit of market (systematic) risk.' },
      { label: 'VaR 95% (Daily)',   value: data.var95,      fmt: v => (v*100).toFixed(2)+'%',     tooltip: '95% chance daily loss will not exceed this amount.' },
      { label: 'VaR 99% (Daily)',   value: data.var99,      fmt: v => (v*100).toFixed(2)+'%',     tooltip: '99% chance daily loss will not exceed this amount.' },
      { label: 'CVaR 95%',          value: data.cvar95,     fmt: v => (v*100).toFixed(2)+'%',     tooltip: 'Expected Shortfall — average loss on the worst 5% of days.' },
      { label: 'CVaR 99%',          value: data.cvar99,     fmt: v => (v*100).toFixed(2)+'%',     tooltip: 'Average loss on the worst 1% of days.' },
      { label: 'Calmar Ratio',      value: data.calmar,     fmt: v => v.toFixed(3),               tooltip: 'Annualized return divided by max drawdown. Higher is better.' },
      { label: 'Ann. Return',       value: data.annreturn,  fmt: v => (v*100).toFixed(2)+'%',     tooltip: 'Annualized portfolio return.' },
      { label: 'Ann. Volatility',   value: data.annvol,     fmt: v => (v*100).toFixed(2)+'%',     tooltip: 'Annualized standard deviation of returns.' },
    ];

    container.innerHTML = `<div class="metric-grid">` +
      metrics.filter(m => m.value !== undefined).map(m => `
        <div class="metric-card" data-tooltip="${m.tooltip}">
          <div class="metric-name">${m.label}</div>
          <div class="metric-value mono">${m.fmt(m.value)}</div>
        </div>`).join('') +
      `</div>`;

  } catch(e) {
    container.innerHTML = renderErrorState('Analytics failed', runPortfolioAnalytics);
  } finally {
    btn.textContent = 'Run Analysis';
    btn.disabled    = false;
  }
}

/* ============================================================
   23. CORRELATION MATRIX
   ============================================================ */
async function runCorrelation() {
  const btn = document.getElementById('runCorrelationBtn');
  const container = document.getElementById('correlationContent');
  if (STATE.portfolio.length < 2) {
    container.innerHTML = renderErrorState('Need at least 2 positions', null);
    return;
  }

  btn.textContent = 'Calculating…';
  btn.disabled    = true;
  container.innerHTML = renderSkeletonGrid(4);

  const tickers = STATE.portfolio.map(p => p.ticker);

  try {
    const data = await apiFetch('/api/correlation', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tickers })
    });

    const matrix = data.matrix;
    const labels = data.tickers || tickers;

    // Render heatmap table
    let html = `<div class="heatmap-wrap"><table class="heatmap-table"><thead><tr>
      <th class="heatmap-label"></th>
      ${labels.map(l => `<th class="heatmap-label">${l}</th>`).join('')}
    </tr></thead><tbody>`;

    labels.forEach((rowLabel, i) => {
      html += `<tr><th class="heatmap-label">${rowLabel}</th>`;
      labels.forEach((_, j) => {
        const val = matrix[i][j];
        const bg  = corrToColor(val);
        const txt = Math.abs(val) > 0.5 ? '#fff' : 'var(--text2)';
        html += `<td class="heatmap-cell" style="background:${bg};color:${txt};"
          data-tooltip="${rowLabel} / ${labels[j]}: ${val.toFixed(3)} — ${corrLabel(val)}">
          ${val.toFixed(2)}</td>`;
      });
      html += `</tr>`;
    });

    html += `</tbody></table></div>`;

    // Warning for high correlations
    const warnings = [];
    labels.forEach((l1, i) => {
      labels.forEach((l2, j) => {
        if (i < j && matrix[i][j] > 0.85) {
          warnings.push(`${l1} & ${l2}: ${matrix[i][j].toFixed(2)}`);
        }
      });
    });

    if (warnings.length > 0) {
      html += `<div class="macro-summary-box mt-3" style="border-left:3px solid var(--amber);">
        <strong>⚠ High Correlation Warning:</strong> ${warnings.join(' | ')}
        <br><span class="text-muted text-sm">Pairs above 0.85 provide limited diversification benefit.</span>
      </div>`;
    }

    container.innerHTML = html;

  } catch(e) {
    container.innerHTML = renderErrorState('Correlation failed', runCorrelation);
  } finally {
    btn.textContent = 'Calculate';
    btn.disabled    = false;
  }
}

function corrToColor(val) {
  // -1 = red, 0 = dark navy, +1 = blue
  if (val > 0) {
    const intensity = Math.round(val * 180);
    return `rgb(0, ${Math.round(val*80)}, ${intensity})`;
  } else {
    const intensity = Math.round(Math.abs(val) * 180);
    return `rgb(${intensity}, 0, ${Math.round(Math.abs(val)*30)})`;
  }
}

function corrLabel(v) {
  if (v >  0.85) return 'Strongly Positive';
  if (v >  0.5)  return 'Moderately Positive';
  if (v >  0.2)  return 'Weakly Positive';
  if (v > -0.2)  return 'Near Zero';
  if (v > -0.5)  return 'Weakly Negative';
  if (v > -0.85) return 'Moderately Negative';
  return 'Strongly Negative';
}

/* ============================================================
   24. DRAWDOWN CHART
   ============================================================ */
async function runDrawdown() {
  const btn = document.getElementById('runDrawdownBtn');
  const container = document.getElementById('drawdownContent');
  if (STATE.portfolio.length === 0) return;

  btn.textContent = 'Calculating…';
  btn.disabled    = true;

  const tickers = STATE.portfolio.map(p => p.ticker);

  try {
    const data = await apiFetch('/api/risk', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'drawdown', tickers })
    });

    const results = data.results.sort((a, b) => a.maxdrawdown - b.maxdrawdown);
    const labels  = results.map(r => r.ticker);
    const values  = results.map(r => Math.abs(r.maxdrawdown * 100));
    const colors  = values.map(v => v > 30 ? '#d44a4a' : v > 15 ? '#d4a03d' : '#3dbc72');

    destroyChart('drawdownChart');
    STATE.charts.drawdownChart = new Chart(document.getElementById('drawdownChart'), {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: colors,
          borderColor: colors,
          borderWidth: 1,
          borderRadius: 4,
        }]
      },
      options: {
        indexAxis: 'y',
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => ` Max Drawdown: -${ctx.raw.toFixed(1)}%` } }
        },
        scales: {
          x: {
            grid:  { color: 'rgba(36,42,56,0.5)' },
            ticks: { color: '#8892a6', callback: v => `-${v}%` }
          },
          y: {
            grid:  { display: false },
            ticks: { color: '#8892a6', font: { family: 'IBM Plex Mono', size: 11 } }
          }
        }
      }
    });

    // Table below chart
    const tableHtml = `<div class="table-scroll mt-3"><table class="data-table">
      <thead><tr><th>Ticker</th><th>Max Drawdown</th><th>Duration (days)</th><th>Recovery (days)</th><th>Calmar</th></tr></thead>
      <tbody>${results.map(r => `
        <tr>
          <td class="mono font-bold">${r.ticker}</td>
          <td class="mono ${Math.abs(r.maxdrawdown*100)>30?'negative':Math.abs(r.maxdrawdown*100)>15?'amber':'positive'}">
            -${(Math.abs(r.maxdrawdown)*100).toFixed(1)}%</td>
          <td class="mono">${r.duration || '—'}</td>
          <td class="mono">${r.recovery || '—'}</td>
          <td class="mono">${r.calmar ? r.calmar.toFixed(2) : '—'}</td>
        </tr>`).join('')}
      </tbody></table></div>`;
    container.insertAdjacentHTML('beforeend', tableHtml);

  } catch(e) {
    container.innerHTML = `<div class="chart-wrap" style="height:280px;"><canvas id="drawdownChart"></canvas></div>`;
    container.insertAdjacentHTML('beforeend', renderErrorState('Drawdown failed', runDrawdown));
  } finally {
    btn.textContent = 'Calculate';
    btn.disabled    = false;
  }
}

/* ============================================================
   25. DIVIDENDS
   ============================================================ */
async function runDividends() {
  const btn = document.getElementById('runDividendsBtn');
  const container = document.getElementById('dividendContent');
  if (STATE.portfolio.length === 0) return;

  btn.textContent = 'Loading…';
  btn.disabled    = true;
  container.innerHTML = renderSkeletonGrid(4);

  const holdings = STATE.portfolio.map(p => ({ ticker: p.ticker, shares: p.shares }));

  try {
    const data = await apiFetch('/api/dividends', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ holdings })
    });

    const results = data.results.filter(r => r.annualdps > 0);
    const totalIncome = results.reduce((s, r) => s + r.annualincome, 0);
    const monthlyData = data.monthlyincome || {};

    let html = `<div class="table-scroll mb-3"><table class="data-table">
      <thead><tr>
        <th>Ticker</th><th>Shares</th><th>Annual DPS</th><th>Yield %</th>
        <th>DGR (5Y CAGR)</th><th>Next Payment</th><th>Annual Income</th>
      </tr></thead>
      <tbody>${results.map(r => `
        <tr>
          <td class="mono font-bold">${r.ticker}</td>
          <td class="mono">${fmtNum(r.shares)}</td>
          <td class="mono text-green">${fmtCurrency(r.annualdps)}</td>
          <td class="mono">${r.yieldpct.toFixed(2)}%</td>
          <td class="mono ${r.dgr > 0 ? 'text-green' : 'text-red'}">${r.dgr > 0 ? '+' : ''}${r.dgr.toFixed(1)}%</td>
          <td class="mono text-muted">${r.nextpayment || '—'}</td>
          <td class="mono text-green">${fmtCurrency(r.annualincome)}</td>
        </tr>`).join('')}
      </tbody>
    </table></div>
    <div class="stat-box mb-3">
      <div class="stat-label">Total Annual Dividend Income</div>
      <div class="stat-value mono text-green">${fmtCurrency(totalIncome)}</div>
      <div class="stat-sub">Approx. ${fmtCurrency(totalIncome / 12)} / month</div>
    </div>`;

    // Monthly calendar
    if (Object.keys(monthlyData).length > 0) {
      const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
      html += `<div class="card-header mb-2"><span class="card-title">Monthly Income Calendar</span></div>
        <div class="grid-4">
        ${months.map((m, i) => {
          const income = monthlyData[i+1] || 0;
          return `<div class="stat-box" style="padding:10px;">
            <div class="stat-label">${m}</div>
            <div class="mono" style="font-size:14px;color:${income>0?'var(--green)':'var(--text3)'};">${income > 0 ? fmtCurrency(income) : '—'}</div>
          </div>`;
        }).join('')}
        </div>`;
    }

    container.innerHTML = html;
  } catch(e) {
    container.innerHTML = renderErrorState('Dividend data failed', runDividends);
  } finally {
    btn.textContent = 'Load Dividends';
    btn.disabled    = false;
  }
}

/* ============================================================
   26. EFFICIENT FRONTIER
   ============================================================ */
async function runEfficientFrontier() {
  const btn = document.getElementById('runFrontierBtn');
  if (STATE.portfolio.length < 2) return;

  btn.textContent = 'Optimizing…';
  btn.disabled    = true;

  let totalValue = 0;
  STATE.portfolio.forEach(p => {
    const q = STATE.quotes[p.ticker];
    totalValue += (q ? q.price : p.avgCost || 1) * p.shares;
  });

  const holdings = STATE.portfolio.map(p => {
    const q = STATE.quotes[p.ticker];
    const value = (q ? q.price : p.avgCost || 1) * p.shares;
    return { ticker: p.ticker, weight: totalValue > 0 ? value / totalValue : 1 / STATE.portfolio.length };
  });

  try {
    const data = await apiFetch('/api/efficient_frontier', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ holdings })
    });

    const frontier  = data.frontier;    // [{vol, ret}, ...]
    const maxSharpe = data.maxSharpe;   // {vol, ret, sharpe, weights}
    const minVol    = data.minVol;      // {vol, ret, sharpe, weights}

    // Estimate current portfolio position from holdings weights + expected returns
    let currentVol = 0, currentRet = 0;
    holdings.forEach(h => {
      currentRet += (data.expectedReturns?.[h.ticker] || 0) * h.weight;
      currentVol += (data.volatilities?.[h.ticker] || 0) * h.weight;
    });
    const currentSharpe = currentVol > 0 ? currentRet / currentVol : 0;

    const datasets = [
      {
        label: 'Efficient Frontier',
        data: frontier.map(p => ({ x: p.vol * 100, y: p.ret * 100 })),
        backgroundColor: 'rgba(74,142,255,0.3)',
        borderColor: '#4a8eff',
        pointRadius: 2,
        showLine: true,
        fill: false,
        tension: 0.4,
      },
      {
        label: 'Current Portfolio',
        data: [{ x: currentVol * 100, y: currentRet * 100 }],
        backgroundColor: '#d4a03d',
        borderColor: '#d4a03d',
        pointRadius: 10,
        pointStyle: 'star',
      },
      {
        label: 'Max Sharpe',
        data: [{ x: maxSharpe.vol * 100, y: maxSharpe.ret * 100 }],
        backgroundColor: '#3dbc72',
        borderColor: '#3dbc72',
        pointRadius: 10,
        pointStyle: 'triangle',
      },
      {
        label: 'Min Volatility',
        data: [{ x: minVol.vol * 100, y: minVol.ret * 100 }],
        backgroundColor: '#5ba8d4',
        borderColor: '#5ba8d4',
        pointRadius: 10,
        pointStyle: 'rectRot',
      },
    ];

    destroyChart('frontierChart');
    STATE.charts.frontierChart = new Chart(document.getElementById('frontierChart'), {
      type: 'scatter',
      data: { datasets },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { labels: { color: '#8892a6', font: { size: 11 } } },
          tooltip: { callbacks: {
            label: ctx => `${ctx.dataset.label}: Vol ${ctx.raw.x.toFixed(1)}% / Ret ${ctx.raw.y.toFixed(1)}%`
          }}
        },
        scales: {
          x: {
            title: { display: true, text: 'Annual Volatility (%)', color: '#4e5668' },
            grid:  { color: 'rgba(36,42,56,0.5)' },
            ticks: { color: '#8892a6' },
          },
          y: {
            title: { display: true, text: 'Expected Annual Return (%)', color: '#4e5668' },
            grid:  { color: 'rgba(36,42,56,0.5)' },
            ticks: { color: '#8892a6' },
          }
        }
      }
    });

    document.getElementById('efLegend').innerHTML = `
      <div class="ef-legend-item"><div class="ef-legend-dot" style="background:#d4a03d"></div>Current Portfolio (Sharpe: ${currentSharpe.toFixed(2)})</div>
      <div class="ef-legend-item"><div class="ef-legend-dot" style="background:#3dbc72"></div>Max Sharpe (${maxSharpe.sharpe.toFixed(2)})</div>
      <div class="ef-legend-item"><div class="ef-legend-dot" style="background:#5ba8d4"></div>Min Volatility</div>`;

    // Suggestion
    if (maxSharpe.weights && currentSharpe < maxSharpe.sharpe - 0.05) {
      const suggestionEl = document.getElementById('frontierSuggestion');
      const weightEntries = Object.entries(maxSharpe.weights);
      const diffs = weightEntries.map(([ticker, optW]) => {
        const h = holdings.find(h => h.ticker === ticker);
        const curW = h ? h.weight : 0;
        return { ticker, current: curW * 100, optimal: optW * 100, diff: (optW - curW) * 100 };
      }).sort((a,b) => Math.abs(b.diff) - Math.abs(a.diff));

      const top = diffs[0];
      const bot = diffs[diffs.length - 1];
      suggestionEl.innerHTML = `<strong>Optimization Suggestion:</strong> Shift ${Math.abs(bot.diff).toFixed(1)}% from
        <strong>${bot.ticker}</strong> → <strong>${top.ticker}</strong>
        to improve Sharpe Ratio from <strong>${currentSharpe.toFixed(2)}</strong> to <strong>${maxSharpe.sharpe.toFixed(2)}</strong>`;
      suggestionEl.classList.remove('hidden');
    }

  } catch(e) {
    document.getElementById('frontierSuggestion').innerHTML = 'Optimization failed. Ensure portfolio has sufficient history.';
    document.getElementById('frontierSuggestion').classList.remove('hidden');
  } finally {
    btn.textContent = 'Run Optimization';
    btn.disabled    = false;
  }
}

/* ============================================================
   27. HELPER UTILITIES
   ============================================================ */
function fmtCurrency(n) {
  if (n === null || n === undefined || isNaN(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 1e9) return (n < 0 ? '-' : '') + '$' + (abs / 1e9).toFixed(2) + 'B';
  if (abs >= 1e6) return (n < 0 ? '-' : '') + '$' + (abs / 1e6).toFixed(2) + 'M';
  if (abs >= 1e3) return (n < 0 ? '-' : '') + '$' + (abs / 1e3).toFixed(2) + 'K';
  return (n < 0 ? '-$' : '$') + abs.toFixed(2);
}

function fmtNum(n) {
  if (n === null || n === undefined) return '—';
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: 4 });
}

function getTickerName(ticker) {
  const names = {
    AAPL:'Apple Inc', MSFT:'Microsoft Corp', NVDA:'NVIDIA Corp', GOOGL:'Alphabet Inc',
    AMZN:'Amazon.com', META:'Meta Platforms', TSLA:'Tesla Inc', JPM:'JPMorgan Chase',
    JNJ:'Johnson & Johnson', V:'Visa Inc', UNH:'UnitedHealth', XOM:'Exxon Mobil',
    SPY:'SPDR S&P 500 ETF', QQQ:'Invesco QQQ ETF', VTI:'Vanguard Total Market',
    GLD:'SPDR Gold Shares', IBIT:'iShares Bitcoin ETF', BND:'Vanguard Bond ETF',
    VXUS:'Vanguard Intl Stock', SCHD:'Schwab US Dividend', VYM:'Vanguard High Div',
    JEPI:'JPMorgan Premium Income', O:'Realty Income', AGG:'iShares Core US Bond',
    'BTC-USD':'Bitcoin', 'ETH-USD':'Ethereum', 'SOL-USD':'Solana',
  };
  return names[ticker] || ticker;
}

function destroyChart(id) {
  if (STATE.charts[id]) {
    STATE.charts[id].destroy();
    delete STATE.charts[id];
  }
}

function renderSkeletonGrid(count) {
  return `<div class="metric-grid">${Array(count).fill(0).map(() => `
    <div class="metric-card">
      <div class="skeleton skeleton-text w-60 mb-2"></div>
      <div class="skeleton skeleton-value"></div>
    </div>`).join('')}</div>`;
}

function renderErrorState(msg, retryFn) {
  const retryId = `retry-${Date.now()}`;
  if (retryFn) {
    setTimeout(() => {
      const btn = document.getElementById(retryId);
      if (btn) btn.addEventListener('click', retryFn);
    }, 100);
  }
  return `<div class="error-state">
    <div class="error-state-icon">⚠</div>
    <div class="error-state-msg">${msg}</div>
    ${retryFn ? `<button class="btn btn-sm btn-ghost mt-2" id="${retryId}">↻ Retry</button>` : ''}
  </div>`;
}

function animateNumber(el, targetVal, fmtFn, duration = 800) {
  if (!el) return;
  const startVal = parseFloat(el.dataset.rawVal) || 0;
  el.dataset.rawVal = targetVal;
  const startTime = performance.now();
  function step(now) {
    const progress = Math.min(1, (now - startTime) / duration);
    const eased    = 1 - Math.pow(1 - progress, 3);
    const current  = startVal + (targetVal - startVal) * eased;
    el.textContent = fmtFn(current);
    if (progress < 1) requestAnimationFrame(step);
    else el.textContent = fmtFn(targetVal);
  }
  requestAnimationFrame(step);
}

/* ============================================================
   END OF APP.JS PART 1
   ============================================================ */

/* ============================================================
ALPHAVAULT — APP.JS  (Part 2 of 2)
Research, Macro, Simulate, Compare, Watchlist, PDF Export
============================================================ */

/* ============================================================
   28. RESEARCH TAB — SEARCH
   ============================================================ */


function initResearchSearch() {
  const input = document.getElementById('researchSearch');
  if (!input) return;
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const ticker = input.value.trim().toUpperCase();
      if (ticker) loadResearchTicker(ticker);
    }
  });
}

async function loadResearchTicker(ticker) {
  STATE.researchTicker = ticker;

  // Show content, hide placeholder
  document.getElementById('researchPlaceholder').classList.add('hidden');
  document.getElementById('researchContent').classList.remove('hidden');
  document.getElementById('companyStrip').classList.remove('hidden');

  // Show skeleton in strip
  ['companyName','companyTicker','companySector','companyMktCap',
   'companyPrice','companyDayChange','week52Low','week52High'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = '…';
  });
  document.getElementById('companyLogoInitial').textContent = ticker.charAt(0);

  // Load all panels in parallel
  try {
    const [quoteData] = await Promise.all([
      fetchResearchQuote(ticker),
      loadValuation(ticker),
      loadInsider(ticker),
      loadAnalyst(ticker),
      loadNews(ticker),
    ]);
    renderCompanyStrip(ticker, quoteData);
  } catch(e) {
    console.error('Research load error:', e);
  }
}

async function fetchResearchQuote(ticker) {
  try {
    const data = await apiFetch(`/api/quote?ticker=${encodeURIComponent(ticker)}`);
    STATE.quotes[ticker] = data;
    return data;
  } catch(e) { return null; }
}

function renderCompanyStrip(ticker, q) {
  if (!q) return;
  document.getElementById('companyName').textContent      = q.name        || getTickerName(ticker);
  document.getElementById('companyTicker').textContent    = ticker;
  document.getElementById('companySector').textContent    = q.sector       || SECTOR_MAP[ticker] || '—';
  document.getElementById('companyMktCap').textContent    = q.market_cap   ? fmtCurrency(q.market_cap) : '—';
  document.getElementById('companyPrice').textContent     = q.price        ? fmtCurrency(q.price) : '—';
  document.getElementById('companyLogoInitial').textContent = ticker.charAt(0);

  const changeEl = document.getElementById('companyDayChange');
  if (changeEl && q.change !== undefined) {
    const sign = q.change >= 0 ? '+' : '';
    changeEl.textContent = `${sign}${fmtCurrency(q.change)} (${sign}${(q.changePct||0).toFixed(2)}%)`;
    changeEl.style.color = q.change >= 0 ? 'var(--green)' : 'var(--red)';
  }

  // 52-week range
  if (q.week52Low !== undefined && q.week52High !== undefined) {
    document.getElementById('week52Low').textContent  = fmtCurrency(q.week52Low);
    document.getElementById('week52High').textContent = fmtCurrency(q.week52High);
    const range   = q.week52High - q.week52Low;
    const pos     = range > 0 ? ((q.price - q.week52Low) / range) * 100 : 50;
    document.getElementById('weekRangeFill').style.width = '100%';
    document.getElementById('weekRangeDot').style.left   = `${Math.min(97, Math.max(3, pos))}%`;
  }
}

/* ============================================================
   29. RESEARCH — VALUATION
   ============================================================ */
async function loadValuation(ticker) {
  const container = document.getElementById('valuationMetrics');
  container.innerHTML = renderSkeletonGrid(9);

  // Load price chart alongside valuation data
  loadResearchPriceChart(ticker);

  try {
    const data = await apiFetch(`/api/quote?ticker=${encodeURIComponent(ticker)}`);
    const metrics = [
      { name: 'P/E Ratio',         value: data.pe,          sector: 22, sp: 25,  fmt: v => v.toFixed(1), lower: true  },
      { name: 'Forward P/E',       value: data.forward_pe,  sector: 20, sp: 22,  fmt: v => v.toFixed(1), lower: true  },
      { name: 'P/S Ratio',         value: data.ps,          sector: 4,  sp: 5,   fmt: v => v.toFixed(2), lower: true  },
      { name: 'P/B Ratio',         value: data.pb,          sector: 3,  sp: 4,   fmt: v => v.toFixed(2), lower: true  },
      { name: 'EV/EBITDA',         value: data.ev_ebitda,   sector: 14, sp: 16,  fmt: v => v.toFixed(1), lower: true  },
      { name: 'Debt/Equity',       value: data.debt_equity, sector: 0.8,sp: 1.2, fmt: v => v.toFixed(2), lower: true  },
      { name: 'ROE',               value: data.roe,         sector: 0.15,sp:0.18,fmt: v => (v*100).toFixed(1)+'%', lower: false },
      { name: 'ROA',               value: data.roa,         sector: 0.07,sp:0.09,fmt: v => (v*100).toFixed(1)+'%', lower: false },
      { name: 'FCF Yield',         value: data.fcf_yield,   sector: 0.04,sp:0.05,fmt: v => (v*100).toFixed(1)+'%', lower: false },
    ];

    container.innerHTML = `<div class="metric-grid">` +
      metrics.map(m => {
        if (m.value === undefined || m.value === null) return '';
        const isCheap     = m.lower ? m.value < m.sector  : m.value > m.sector;
        const isExpensive = m.lower ? m.value > m.sp * 1.2: m.value < m.sp * 0.8;
        const verdict     = isCheap ? 'Cheap' : isExpensive ? 'Expensive' : 'Fair';
        const vClass      = isCheap ? 'badge-green' : isExpensive ? 'badge-red' : 'badge-amber';
        return `<div class="metric-card">
          <div class="metric-name">${m.name}</div>
          <div class="metric-value mono">${m.fmt(m.value)}</div>
          <div class="metric-verdict"><span class="badge ${vClass}">${verdict}</span></div>
        </div>`;
      }).join('') + `</div>`;

    // Comparison chart
    const chartMetrics = metrics.filter(m => m.value !== undefined && m.value !== null).slice(0, 6);
    renderValuationCompareChart(ticker, chartMetrics);

  } catch(e) {
    container.innerHTML = renderErrorState('Valuation data unavailable', () => loadValuation(ticker));
  }
}

async function loadResearchPriceChart(ticker) {
  // Insert chart canvas before valuationMetrics if not already there
  let wrap = document.getElementById('researchPriceChartWrap');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.id = 'researchPriceChartWrap';
    wrap.className = 'card mb-3';
    wrap.innerHTML = `<div class="card-header"><span class="card-title">Price History (1Y)</span></div>
      <div class="chart-wrap" style="height:220px;"><canvas id="researchPriceChart"></canvas></div>`;
    const container = document.getElementById('valuationMetrics');
    container.parentNode.insertBefore(wrap, container);
  }

  try {
    const data = await apiFetch(`/api/history?tickers=${ticker}&period=1y`);
    if (data.dates && data.series && data.series[ticker]) {
      destroyChart('researchPriceChart');
      STATE.charts.researchPriceChart = new Chart(document.getElementById('researchPriceChart'), {
        type: 'line',
        data: {
          labels: data.dates,
          datasets: [{
            label: ticker,
            data: data.series[ticker],
            borderColor: '#4a8eff',
            borderWidth: 2,
            pointRadius: 0,
            fill: true,
            backgroundColor: 'rgba(74,142,255,0.08)',
            tension: 0.3,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: false },
            tooltip: { callbacks: { label: ctx => `${ticker}: ${ctx.raw.toFixed(2)}` } } },
          scales: {
            x: { grid: { color: 'rgba(36,42,56,0.3)' }, ticks: { color: '#8892a6', maxTicksLimit: 8, font: { size: 10 } } },
            y: { grid: { color: 'rgba(36,42,56,0.3)' }, ticks: { color: '#8892a6' },
              title: { display: true, text: 'Indexed', color: '#4e5668', font: { size: 10 } } },
          },
        },
      });
    }
  } catch(e) {
    console.warn('Price chart failed:', e);
  }
}

function renderValuationCompareChart(ticker, metrics) {
  const canvas = document.getElementById('valuationCompareChart');
  if (!canvas) return;
  destroyChart('valuationCompareChart');

  const labels  = metrics.map(m => m.name);
  const ticker_vals = metrics.map(m => m.value);
  const sector_vals = metrics.map(m => m.sector);
  const sp_vals     = metrics.map(m => m.sp);

  STATE.charts.valuationCompareChart = new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: ticker, data: ticker_vals, backgroundColor: 'rgba(74,142,255,0.7)', borderColor: '#4a8eff', borderWidth: 1, borderRadius: 3 },
        { label: 'Sector Median', data: sector_vals, backgroundColor: 'rgba(91,168,212,0.4)', borderColor: '#5ba8d4', borderWidth: 1, borderRadius: 3 },
        { label: 'S&P 500 Median', data: sp_vals, backgroundColor: 'rgba(212,160,61,0.4)', borderColor: '#d4a03d', borderWidth: 1, borderRadius: 3 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#8892a6', font: { size: 11 } } } },
      scales: {
        x: { grid: { color: 'rgba(36,42,56,0.5)' }, ticks: { color: '#8892a6', font: { size: 10 } } },
        y: { grid: { color: 'rgba(36,42,56,0.5)' }, ticks: { color: '#8892a6' } }
      }
    }
  });
}

/* ============================================================
   30. RESEARCH — INSIDER ACTIVITY
   ============================================================ */
async function loadInsider(ticker) {
  const tbody = document.getElementById('insiderBody');
  if (!tbody) return;
  tbody.innerHTML = `<tr><td colspan="6">${renderSkeletonGrid(3)}</td></tr>`;

  try {
    const data = await apiFetch(`/api/research?type=insider&ticker=${encodeURIComponent(ticker)}`);
    const txns = data.transactions || [];

    // Summary stats
    const buyCount  = data.buyCount  || 0;
    const sellCount = data.sellCount || 0;
    const buyVal    = data.buyValue  || 0;
    const sellVal   = data.sellValue || 0;

    document.getElementById('insiderBuys').textContent   = `${buyCount} Buys (${fmtCurrency(buyVal)})`;
    document.getElementById('insiderSells').textContent  = `${sellCount} Sells (${fmtCurrency(sellVal)})`;

    const ratio = buyCount / Math.max(1, buyCount + sellCount);
    const badge = document.getElementById('insiderSentimentBadge');
    if (badge) {
      badge.textContent = ratio > 0.6 ? 'Bullish' : ratio < 0.35 ? 'Bearish' : 'Neutral';
      badge.className   = `badge ${ratio > 0.6 ? 'badge-green' : ratio < 0.35 ? 'badge-red' : 'badge-neutral'}`;
    }

    if (txns.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted" style="padding:20px;">No recent insider transactions</td></tr>`;
      return;
    }

    tbody.innerHTML = txns.slice(0, 20).map(t => {
      const isBuy = t.transaction && t.transaction.toLowerCase().includes('purchase');
      const txnType = isBuy ? 'Buy' : 'Sell';
      return `<tr style="background:${isBuy ? 'rgba(61,188,114,0.04)' : 'transparent'}">
        <td class="mono text-muted">${t.date || '—'}</td>
        <td class="font-600">${t.executive || '—'}</td>
        <td class="text-muted text-sm">${t.title || '—'}</td>
        <td><span class="badge ${isBuy ? 'badge-buy' : 'badge-sell'}">${txnType}</span></td>
        <td class="mono">${t.shares ? fmtNum(t.shares) : '—'}</td>
        <td class="mono ${isBuy ? 'positive' : 'negative'}">${t.value ? fmtCurrency(t.value) : '—'}</td>
      </tr>`;
    }).join('');

  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="6">${renderErrorState('Insider data unavailable', () => loadInsider(ticker))}</td></tr>`;
  }
}
/* ============================================================
   APP.JS — PART 2 FIX
   Paste this AFTER line 1896 in app.js
   (replace the bare `try` at line 1897 onwards)
   ============================================================ */

/* ============================================================
   31. RESEARCH — ANALYST RATINGS
   ============================================================ */
   async function loadAnalyst(ticker) {
    const tbody = document.getElementById('analystBody');
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="5">${renderSkeletonGrid(3)}</td></tr>`;
  
    try {
      const data = await apiFetch(`/api/research?type=analyst&ticker=${encodeURIComponent(ticker)}`);
      const ratings = data.ratingChanges || [];

      // Derive consensus from score (1=Strong Buy, 5=Strong Sell)
      const score = data.consensusScore;
      const consensus = !score ? '—' : score <= 1.5 ? 'Strong Buy' : score <= 2.5 ? 'Buy' : score <= 3.5 ? 'Hold' : score <= 4.5 ? 'Sell' : 'Strong Sell';
      const buys  = ratings.filter(r => r.action && r.action.toLowerCase().includes('upgrade')).length;
      const sells = ratings.filter(r => r.action && r.action.toLowerCase().includes('downgrade')).length;
      const holds = Math.max(0, ratings.length - buys - sells);
      const pt    = data.priceTargetAvg;

      // Consensus badge
      const consensusEl = document.getElementById('consensusBadge');
      if (consensusEl) {
        consensusEl.textContent = consensus;
        consensusEl.className = `badge ${
          consensus.toLowerCase().includes('buy')  ? 'badge-green badge-buy'  :
          consensus.toLowerCase().includes('sell') ? 'badge-red badge-sell'   : 'badge-amber'
        }`;
        consensusEl.style.fontSize = '14px';
        consensusEl.style.padding = '6px 18px';
      }

      // Ratings bar
      const barEl = document.getElementById('ratingsBar');
      if (barEl) {
        barEl.innerHTML = `
          <div style="display:flex;height:8px;border-radius:4px;overflow:hidden;gap:2px;margin-bottom:6px">
            <div style="flex:${buys||1};background:var(--green);border-radius:4px 0 0 4px"></div>
            <div style="flex:${holds||1};background:var(--amber)"></div>
            <div style="flex:${sells||1};background:var(--red);border-radius:0 4px 4px 0"></div>
          </div>
          <div style="display:flex;gap:12px;font-size:11px;color:var(--text2)">
            <span style="color:var(--green)">▲ ${buys} Upgrade</span>
            <span style="color:var(--amber)">◆ ${holds} Maintain</span>
            <span style="color:var(--red)">▼ ${sells} Downgrade</span>
          </div>`;
      }

      // Price targets
      const ptLow  = data.priceTargetLow;
      const ptHigh = data.priceTargetHigh;
      const ptCurr = data.priceTargetCurr;
      if (document.getElementById('ptLowVal'))  document.getElementById('ptLowVal').textContent  = ptLow  ? fmtCurrency(ptLow)  : '—';
      if (document.getElementById('ptAvgVal'))   document.getElementById('ptAvgVal').textContent  = pt     ? fmtCurrency(pt)     : '—';
      if (document.getElementById('ptHighVal'))  document.getElementById('ptHighVal').textContent = ptHigh ? fmtCurrency(ptHigh) : '—';

      // Position price target markers
      if (ptLow && ptHigh && ptCurr) {
        const range = ptHigh - ptLow;
        if (range > 0) {
          const pctLow  = 5;
          const pctHigh = 95;
          const pctAvg  = pt ? Math.min(95, Math.max(5, ((pt - ptLow) / range) * 90 + 5)) : 50;
          const pctCurr = Math.min(95, Math.max(5, ((ptCurr - ptLow) / range) * 90 + 5));
          if (document.getElementById('ptLow'))     document.getElementById('ptLow').style.left     = pctLow + '%';
          if (document.getElementById('ptAvg'))      document.getElementById('ptAvg').style.left     = pctAvg + '%';
          if (document.getElementById('ptHigh'))     document.getElementById('ptHigh').style.left    = pctHigh + '%';
          if (document.getElementById('ptCurrent'))  document.getElementById('ptCurrent').style.left = pctCurr + '%';
          if (document.getElementById('ptRangeFill')) {
            document.getElementById('ptRangeFill').style.left  = pctLow + '%';
            document.getElementById('ptRangeFill').style.width = (pctHigh - pctLow) + '%';
          }
        }
      }

      if (!ratings.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted" style="padding:20px">No analyst ratings available</td></tr>`;
        return;
      }

      tbody.innerHTML = ratings.slice(0, 15).map(r => {
        const isUp = r.action && r.action.toLowerCase().includes('upgrade');
        const isDn = r.action && r.action.toLowerCase().includes('downgrade');
        return `<tr>
          <td class="text-muted mono">${r.date || '—'}</td>
          <td class="truncate" style="max-width:140px">${r.firm || '—'}</td>
          <td class="mono text-muted">${r.fromGrade || '—'}</td>
          <td class="mono"><span class="badge ${isUp ? 'badge-green' : isDn ? 'badge-red' : 'badge-amber'}">${r.toGrade || '—'}</span></td>
          <td class="mono text-green">${r.priceTarget ? fmtCurrency(r.priceTarget) : '—'}</td>
        </tr>`;
      }).join('');
    } catch(e) {
      tbody.innerHTML = `<tr><td colspan="5">${renderErrorState('Analyst data unavailable', () => loadAnalyst(ticker))}</td></tr>`;
    }
  }
  
  /* ============================================================
     32. RESEARCH — NEWS
     ============================================================ */
  async function loadNews(ticker) {
    const container = document.getElementById('newsFeed');
    if (!container) return;
    container.innerHTML = renderSkeletonGrid(4);
  
    try {
      const data  = await apiFetch(`/api/news?ticker=${encodeURIComponent(ticker)}`);
      const items = data.articles || [];

      if (!items.length) {
        container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">📰</div><div class="empty-state-title">No recent news</div></div>`;
        return;
      }

      container.innerHTML = items.slice(0, 12).map(n => {
        return `<a class="news-card" href="${n.url || '#'}" target="_blank" rel="noopener noreferrer">
          <div class="news-source">${n.publisher || '—'} · <span class="text-muted">${n.date || ''}</span></div>
          <div class="news-title">${n.title || ''}</div>
          <div class="news-footer">
            <span class="text-muted" style="font-size:11px">${n.summary ? n.summary.substring(0,100)+'…' : ''}</span>
          </div>
        </a>`;
      }).join('');
    } catch(e) {
      container.innerHTML = renderErrorState('News unavailable', () => loadNews(ticker));
    }
  }
  
  /* ============================================================
     33. MACRO TAB
     ============================================================ */
  async function loadMacroTab() {
    // Don't refetch within 5 minutes
    if (STATE.macroData && STATE.macroLastFetch && (Date.now() - STATE.macroLastFetch) < 300000) {
      renderMacroData(STATE.macroData);
      return;
    }

    // Wire refresh button
    const refreshBtn = document.getElementById('refreshMacroBtn');
    if (refreshBtn && !refreshBtn._wired) {
      refreshBtn._wired = true;
      refreshBtn.addEventListener('click', () => { STATE.macroLastFetch = null; loadMacroTab(); });
    }

    try {
      const data = await apiFetch('/api/macro');
      STATE.macroData      = data;
      STATE.macroLastFetch = Date.now();
      renderMacroData(data);
    } catch(e) {
      console.error('Macro fetch failed:', e);
    }
  }

  function renderMacroData(data) {
    // Map API fields to the pre-built HTML card IDs
    const cardMap = {
      'macro-FEDFUNDS':    { value: data.fedFundsRate,  fmt: v => v.toFixed(2) + '%',       note: 'Current target rate' },
      'macro-CPI':         { value: data.cpi,           fmt: v => v > 100 ? v.toFixed(1) : v.toFixed(2) + '%', note: v => v > 100 ? 'CPI Index Level' : 'Consumer Price Index YoY' },
      'macro-UNRATE':      { value: data.unemployment,  fmt: v => v.toFixed(1) + '%',       note: 'U-3 unemployment rate' },
      'macro-GDP':         { value: data.gdpGrowth,     fmt: v => v.toFixed(2) + '%',       note: 'Annualized QoQ' },
      'macro-M2SL':        { value: data.m2,            fmt: v => '$' + v.toFixed(2) + 'T', note: 'M2 money supply' },
      'macro-T10Y2Y':      { value: data.yieldCurve,    fmt: v => (v > 0 ? '+' : '') + (v*100).toFixed(0) + 'bps', note: v => v < 0 ? 'Inverted' : 'Normal spread' },
      'macro-BAMLH0A0HYM2':{ value: data.hyCreditSpread,fmt: v => v.toFixed(2) + '%',      note: 'High yield spread' },
      'macro-DGS10':       { value: data.t10y,          fmt: v => v.toFixed(3) + '%',       note: '10-year yield' },
      'macro-DGS2':        { value: data.t2y,           fmt: v => v.toFixed(3) + '%',       note: '2-year yield' },
      'macro-DTWEXBGS':    { value: data.dxy,           fmt: v => v.toFixed(2),             note: 'US Dollar Index' },
      'macro-GOLD':        { value: data.gold,          fmt: v => fmtCurrency(v),           note: 'Spot price per oz' },
      'macro-WTI':         { value: data.oil,           fmt: v => fmtCurrency(v),           note: 'Per barrel' },
      'macro-VIX':         { value: data.vix,           fmt: v => v.toFixed(2),             note: data.vixChange ? (data.vixChange > 0 ? '+' : '') + data.vixChange.toFixed(1) + '% today' : 'Fear index' },
    };

    Object.entries(cardMap).forEach(([cardId, cfg]) => {
      const card = document.getElementById(cardId);
      if (!card) return;

      card.classList.remove('skeleton-loading');
      const valueEl  = card.querySelector('.macro-value');
      const changeEl = card.querySelector('.macro-change');

      if (cfg.value != null) {
        if (valueEl) {
          valueEl.classList.remove('skeleton', 'skeleton-value');
          valueEl.textContent = cfg.fmt(cfg.value);
        }
        if (changeEl) {
          changeEl.classList.remove('skeleton', 'skeleton-text', 'w-60', 'mt-1');
          const noteText = typeof cfg.note === 'function' ? cfg.note(cfg.value) : cfg.note;
          changeEl.textContent = noteText;
          changeEl.style.color = 'var(--text3)';
        }
      } else {
        if (valueEl) {
          valueEl.classList.remove('skeleton', 'skeleton-value');
          valueEl.textContent = '—';
          valueEl.style.color = 'var(--text3)';
        }
        if (changeEl) {
          changeEl.classList.remove('skeleton', 'skeleton-text', 'w-60', 'mt-1');
          changeEl.textContent = 'Requires paid API tier';
          changeEl.style.color = 'var(--text3)';
          changeEl.style.fontSize = '10px';
        }
      }
    });

    // Summary panel
    const summaryEl = document.getElementById('macroSummary');
    if (summaryEl) {
      const vix = data.vix;
      const yc  = data.yieldCurve;
      const lines = [];
      if (vix != null) lines.push(vix > 30 ? 'VIX elevated — markets stressed' : vix > 20 ? 'VIX moderate — some uncertainty' : 'VIX low — calm markets');
      if (yc != null) lines.push(yc < 0 ? 'Yield curve inverted — recession signal' : 'Yield curve normal (' + (yc*100).toFixed(0) + 'bps spread)');
      if (data.gold) lines.push('Gold at ' + fmtCurrency(data.gold) + '/oz');
      if (data.oil) lines.push('WTI crude at ' + fmtCurrency(data.oil) + '/barrel');
      summaryEl.innerHTML = lines.length
        ? '<strong>Market Snapshot</strong><br>' + lines.join(' · ')
        : '<span class="text-muted">Market data loading…</span>';
    }
  }
  
  /* ============================================================
     34. SIMULATE TAB — MONTE CARLO
     ============================================================ */
  function initSimulateTab() {
    // Monte Carlo — wire sliders to their value labels
    const sliderMap = {
      'mcSims': 'mcSimsVal', 'mcYears': 'mcYearsVal', 'mcReturn': 'mcReturnVal',
      'mcVol': 'mcVolVal', 'mcInfl': 'mcInflVal', 'mcContrib': 'mcContribVal',
    };
    Object.entries(sliderMap).forEach(([sliderId, labelId]) => {
      const slider = document.getElementById(sliderId);
      const label  = document.getElementById(labelId);
      if (slider && label) {
        slider.addEventListener('input', () => label.textContent = slider.value);
      }
    });

    // Monte Carlo run button
    const mcBtn = document.getElementById('runMonteCarloBtn');
    if (mcBtn) mcBtn.addEventListener('click', runMonteCarloSim);

    // Goal Planner
    const goalBtn = document.getElementById('runGoalBtn');
    if (goalBtn) goalBtn.addEventListener('click', runGoalPlanner);

    // DCA Calculator
    const dcaBtn = document.getElementById('runDcaBtn');
    if (dcaBtn) dcaBtn.addEventListener('click', runDcaCalc);

    // Stress Test
    const stressBtn = document.getElementById('runStressBtn');
    if (stressBtn) stressBtn.addEventListener('click', () => runSimStressTest());
    document.querySelectorAll('.scenario-btn[data-scenario]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.scenario-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const isCustom = btn.dataset.scenario === 'custom';
        const customEl = document.getElementById('customScenarioInputs');
        if (customEl) customEl.classList.toggle('hidden', !isCustom);
      });
    });

    // Pre-fill starting value from portfolio
    const startEl = document.getElementById('mcStartValue');
    if (startEl && !startEl.value) {
      let tv = 0;
      STATE.portfolio.forEach(p => {
        const q = STATE.quotes[p.ticker];
        tv += (q ? q.price : (p.avgCost || 1)) * p.shares;
      });
      if (tv > 100) startEl.value = Math.round(tv);
    }
  }

  async function runMonteCarloSim() {
    const btn = document.getElementById('runMonteCarloBtn');
    if (!btn) return;

    const sims    = parseInt(document.getElementById('mcSims')?.value || 1000);
    const years   = parseInt(document.getElementById('mcYears')?.value || 10);
    const contrib = parseFloat(document.getElementById('mcContrib')?.value || 500);
    const infl    = parseFloat(document.getElementById('mcInfl')?.value || 3) / 100;

    // Starting value: from input or portfolio
    let nav = parseFloat(document.getElementById('mcStartValue')?.value || 0);
    if (!nav) {
      STATE.portfolio.forEach(p => {
        const q = STATE.quotes[p.ticker];
        nav += (q ? q.price : (p.avgCost || 1)) * p.shares;
      });
    }
    if (!nav) nav = 50000;

    const holdings = STATE.portfolio.map(p => ({ ticker: p.ticker, shares: p.shares, weight: 0 }));

    btn.textContent = 'Simulating…';
    btn.disabled = true;

    try {
      const data = await apiFetch('/api/montecarlo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          holdings, years, nav, monthlyContrib: contrib,
          inflation: infl, simulations: sims,
          expectedReturn: parseFloat(document.getElementById('mcReturn')?.value || 8) / 100,
          volatility: parseFloat(document.getElementById('mcVol')?.value || 15) / 100,
        }),
      });

      const p = data.percentiles || {};
      const paths = data.samplePaths || [];

      // Fill result cards
      const el = id => document.getElementById(id);
      if (el('mcMedian'))      el('mcMedian').textContent      = fmtCurrency(p['50']);
      if (el('mcP90'))         el('mcP90').textContent          = fmtCurrency(p['90']);
      if (el('mcP10'))         el('mcP10').textContent          = fmtCurrency(p['10']);
      if (el('mcRealMedian'))  el('mcRealMedian').textContent   = fmtCurrency(p['50'] / Math.pow(1 + infl, years));
      if (el('mcDoubleProb'))  el('mcDoubleProb').textContent   = (data.prob_positive || 0).toFixed(1) + '%';
      if (el('mcTotalContrib'))el('mcTotalContrib').textContent = fmtCurrency(nav + contrib * 12 * years);

      // Draw chart
      if (paths.length) {
        const steps   = paths[0].length;
        const stride  = Math.max(1, Math.floor(steps / 48));
        const xLabels = [];
        for (let i = 0; i < steps; i += stride)
          xLabels.push(`Y${((i / (steps - 1)) * years).toFixed(0)}`);

        const downsample = arr => arr.filter((_, i) => i % stride === 0);

        const sampleDS = paths.slice(0, 15).map((path, idx) => ({
          label: idx === 0 ? 'Sample paths' : '',
          data: downsample(path),
          borderColor: 'rgba(74,142,255,0.18)',
          borderWidth: 1, pointRadius: 0, fill: false, tension: 0.3,
        }));

        const refLines = [
          { key: '95', color: '#5cc4a0', label: 'P95', dash: [4,3] },
          { key: '75', color: '#3dbc72', label: 'P75', dash: [4,3] },
          { key: '50', color: '#4a8eff', label: 'P50 Median', dash: [] },
          { key: '25', color: '#d4a03d', label: 'P25', dash: [4,3] },
          { key: '5',  color: '#d44a4a', label: 'P5',  dash: [4,3] },
        ].map(r => ({
          label: r.label,
          data: Array(xLabels.length).fill(p[r.key]),
          borderColor: r.color, borderDash: r.dash,
          borderWidth: 1.5, pointRadius: 0, fill: false,
        }));

        destroyChart('mcCanvas');
        STATE.charts.mcCanvas = new Chart(el('mcCanvas'), {
          type: 'line',
          data: { labels: xLabels, datasets: [...sampleDS, ...refLines] },
          options: {
            responsive: true, maintainAspectRatio: false,
            animation: { duration: 400 },
            plugins: {
              legend: { display: true, labels: {
                filter: item => !item.text?.startsWith('Sample'),
                color: '#8892a6', font: { size: 11 },
              }},
              tooltip: { callbacks: { label: ctx => ctx.dataset.label ? `${ctx.dataset.label}: ${fmtCurrency(ctx.raw)}` : '' }},
            },
            scales: {
              x: { grid: { color: 'rgba(36,42,56,0.4)' }, ticks: { color: '#8892a6', maxTicksLimit: 10 } },
              y: { grid: { color: 'rgba(36,42,56,0.4)' }, ticks: { color: '#8892a6',
                callback: v => '$' + (v >= 1e6 ? (v/1e6).toFixed(1)+'M' : v >= 1e3 ? (v/1e3).toFixed(0)+'K' : v) } },
            },
          },
        });
      }
    } catch(e) {
      console.error('Monte Carlo failed:', e);
    } finally {
      btn.textContent = '▶ Run Simulation';
      btn.disabled = false;
    }
  }

  function runGoalPlanner() {
    const container = document.getElementById('goalResults');
    if (!container) return;

    let current = parseFloat(document.getElementById('gpCurrent')?.value || 0);
    if (!current) {
      STATE.portfolio.forEach(p => {
        const q = STATE.quotes[p.ticker];
        current += (q ? q.price : (p.avgCost || 1)) * p.shares;
      });
    }
    const target  = parseFloat(document.getElementById('gpTarget')?.value || 1000000);
    const year    = parseInt(document.getElementById('gpYear')?.value || 2045);
    const ret     = parseFloat(document.getElementById('gpReturn')?.value || 8) / 100;
    const contrib = parseFloat(document.getElementById('gpContrib')?.value || 500);
    const years   = Math.max(1, year - new Date().getFullYear());

    // Project with monthly compounding
    let balance = current || 10000;
    const monthlyRet = ret / 12;
    const yearlyBalances = [balance];
    for (let m = 1; m <= years * 12; m++) {
      balance = balance * (1 + monthlyRet) + contrib;
      if (m % 12 === 0) yearlyBalances.push(balance);
    }
    const totalContrib = (current || 10000) + contrib * 12 * years;
    const onTrack = balance >= target;
    const neededContrib = target > current ? ((target * monthlyRet) / (Math.pow(1 + monthlyRet, years*12) - 1)) - (current * monthlyRet * Math.pow(1+monthlyRet, years*12)) / (Math.pow(1+monthlyRet, years*12)-1) : 0;

    container.innerHTML = `
      <div class="metric-grid mb-4">
        <div class="metric-card"><div class="metric-name">Projected Value</div>
          <div class="metric-value mono ${onTrack ? 'text-green' : 'text-red'}">${fmtCurrency(balance)}</div></div>
        <div class="metric-card"><div class="metric-name">Target</div>
          <div class="metric-value mono">${fmtCurrency(target)}</div></div>
        <div class="metric-card"><div class="metric-name">Time Horizon</div>
          <div class="metric-value mono">${years} years</div></div>
        <div class="metric-card"><div class="metric-name">Total Contributed</div>
          <div class="metric-value mono">${fmtCurrency(totalContrib)}</div></div>
        <div class="metric-card"><div class="metric-name">Investment Growth</div>
          <div class="metric-value mono text-green">${fmtCurrency(balance - totalContrib)}</div></div>
        <div class="metric-card"><div class="metric-name">Status</div>
          <div class="metric-value mono ${onTrack ? 'text-green' : 'text-red'}">${onTrack ? 'On Track' : 'Behind'}</div></div>
      </div>
      ${!onTrack ? `<div class="macro-summary-box" style="border-left:3px solid var(--amber)">
        <strong>To reach your goal:</strong> Increase monthly contribution to ~${fmtCurrency(Math.max(0,neededContrib))}/mo
      </div>` : ''}`;
  }

  function runDcaCalc() {
    const container = document.querySelector('#panel-dca > div:last-child');
    if (!container) return;

    const start   = parseFloat(document.getElementById('dcaStart')?.value || 10000);
    const contrib = parseFloat(document.getElementById('dcaContrib')?.value || 500);
    const years   = parseInt(document.getElementById('dcaYears')?.value || 20);
    const ret     = parseFloat(document.getElementById('dcaReturn')?.value || 8) / 100;
    const monthlyRet = ret / 12;

    // DCA path
    let dcaBal = start;
    const dcaPath = [start];
    for (let m = 1; m <= years * 12; m++) {
      dcaBal = dcaBal * (1 + monthlyRet) + contrib;
      if (m % 12 === 0) dcaPath.push(dcaBal);
    }

    // Lump sum path (invest all contributions upfront)
    const totalContrib = start + contrib * 12 * years;
    let lumpBal = totalContrib;
    const lumpPath = [totalContrib];
    for (let y = 1; y <= years; y++) {
      lumpBal = lumpBal * (1 + ret);
      lumpPath.push(lumpBal);
    }

    const labels = Array.from({length: years + 1}, (_, i) => `Y${i}`);
    const canvasEl = container.querySelector('canvas') || document.createElement('canvas');
    if (!canvasEl.id) { canvasEl.id = 'dcaChart'; container.innerHTML = ''; container.appendChild(canvasEl); }

    container.innerHTML = `
      <div class="card mb-3">
        <div class="card-header"><span class="card-title">Lump Sum vs DCA</span></div>
        <div style="height:280px;position:relative"><canvas id="dcaChart"></canvas></div>
      </div>
      <div class="metric-grid">
        <div class="metric-card"><div class="metric-name">DCA Final Value</div><div class="metric-value mono text-green">${fmtCurrency(dcaBal)}</div></div>
        <div class="metric-card"><div class="metric-name">Lump Sum Final</div><div class="metric-value mono text-green">${fmtCurrency(lumpBal)}</div></div>
        <div class="metric-card"><div class="metric-name">Total Contributed</div><div class="metric-value mono">${fmtCurrency(totalContrib)}</div></div>
        <div class="metric-card"><div class="metric-name">DCA Growth</div><div class="metric-value mono text-green">${fmtCurrency(dcaBal - totalContrib)}</div></div>
      </div>`;

    destroyChart('dcaChart');
    STATE.charts.dcaChart = new Chart(document.getElementById('dcaChart'), {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'DCA', data: dcaPath, borderColor: '#4a8eff', borderWidth: 2, fill: false, tension: 0.3, pointRadius: 0 },
          { label: 'Lump Sum', data: lumpPath, borderColor: '#3dbc72', borderWidth: 2, borderDash: [6,3], fill: false, tension: 0.3, pointRadius: 0 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#8892a6' } },
          tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${fmtCurrency(ctx.raw)}` } } },
        scales: {
          x: { grid: { color: 'rgba(36,42,56,0.4)' }, ticks: { color: '#8892a6' } },
          y: { grid: { color: 'rgba(36,42,56,0.4)' }, ticks: { color: '#8892a6', callback: v => fmtCurrency(v) } },
        },
      },
    });
  }

  async function runSimStressTest() {
    const container = document.getElementById('stressResults');
    if (!container || !STATE.portfolio.length) return;

    container.innerHTML = renderSkeletonGrid(6);

    let totalValue = 0;
    const holdings = STATE.portfolio.map(p => {
      const q = STATE.quotes[p.ticker];
      const price = q ? q.price : (p.avgCost || 1);
      const value = price * p.shares;
      totalValue += value;
      return { ticker: p.ticker, weight: 0, shares: p.shares, value, price };
    });
    holdings.forEach(h => h.weight = h.value / totalValue);

    try {
      const data = await apiFetch('/api/risk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type: 'stress', holdings: holdings.map(h => ({ ticker: h.ticker, weight: h.weight })) }),
      });

      const results = data.results || [];
      container.innerHTML = `
        <div class="table-scroll">
          <table class="data-table">
            <thead><tr>
              <th>Scenario</th><th>Portfolio Impact</th><th>Est. Loss</th><th>S&P 500 Ref</th><th>Severity</th>
            </tr></thead>
            <tbody>
              ${results.map(r => {
                const impact = r.impact * 100;
                const loss = r.impact * totalValue;
                const severity = Math.abs(impact) > 30 ? 'Extreme' : Math.abs(impact) > 15 ? 'High' : Math.abs(impact) > 5 ? 'Moderate' : 'Low';
                const sevClass = Math.abs(impact) > 30 ? 'text-red' : Math.abs(impact) > 15 ? 'text-amber' : 'text-green';
                return `<tr>
                  <td class="font-600">${r.scenario}</td>
                  <td class="mono text-red">${impact.toFixed(1)}%</td>
                  <td class="mono text-red">${fmtCurrency(loss)}</td>
                  <td class="mono text-muted">${r.spy_ref ? (r.spy_ref * 100).toFixed(1) + '%' : '—'}</td>
                  <td class="${sevClass}">${severity}</td>
                </tr>`;
              }).join('')}
            </tbody>
          </table>
        </div>
        <div class="macro-summary-box mt-3" style="border-left:3px solid var(--amber)">
          <strong>Worst scenario:</strong> ${results.reduce((w, r) => r.impact < w.impact ? r : w, results[0]).scenario}
          — estimated ${fmtCurrency(results.reduce((w, r) => r.impact < w.impact ? r : w, results[0]).impact * totalValue)} loss
        </div>`;
    } catch(e) {
      container.innerHTML = renderErrorState('Stress test failed', runSimStressTest);
    }
  }
  
  /* ============================================================
     35. COMPARE TAB
     ============================================================ */
  function initCompareTab() {
    // Wire timeframe buttons
    document.querySelectorAll('#benchmarkTF .tf-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('#benchmarkTF .tf-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        runBenchmarkCompare(btn.dataset.tf);
      });
    });

    // What If Calculator
    const wiBtn = document.getElementById('runWhatIfBtn');
    if (wiBtn) wiBtn.addEventListener('click', runWhatIf);

    // What If presets
    document.querySelectorAll('#whatIfPresets .preset-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const parts = chip.dataset.whatif.split(',');
        if (parts.length >= 3) {
          const aEl = document.getElementById('whatIfA');
          const bEl = document.getElementById('whatIfB');
          const yEl = document.getElementById('whatIfYear');
          if (aEl) aEl.value = parts[0];
          if (bEl) bEl.value = parts[1];
          if (yEl) yEl.value = parts[2];
          runWhatIf();
        }
      });
    });
  }

  async function runWhatIf() {
    const tickerA = (document.getElementById('whatIfA')?.value || '').trim().toUpperCase();
    const tickerB = (document.getElementById('whatIfB')?.value || '').trim().toUpperCase();
    const startYear = document.getElementById('whatIfYear')?.value || '2020';

    if (!tickerA || !tickerB) return;

    const now = new Date().getFullYear();
    const years = now - parseInt(startYear);
    const periodMap = { 1: '1y', 2: '2y', 3: '3y', 4: '4y', 5: '5y' };
    const period = years <= 5 ? (periodMap[years] || '5y') : '5y';

    try {
      const data = await apiFetch(`/api/history?tickers=${tickerA},${tickerB}&period=${period}`);
      if (!data.series || !data.series[tickerA] || !data.series[tickerB]) {
        return;
      }

      const seriesA = data.series[tickerA];
      const seriesB = data.series[tickerB];
      const dates   = data.dates;

      // Draw chart
      destroyChart('whatIfChart');
      STATE.charts.whatIfChart = new Chart(document.getElementById('whatIfChart'), {
        type: 'line',
        data: {
          labels: dates,
          datasets: [
            { label: tickerA, data: seriesA, borderColor: '#4a8eff', borderWidth: 2, pointRadius: 0, tension: 0.3, fill: false },
            { label: tickerB, data: seriesB, borderColor: '#3dbc72', borderWidth: 2, pointRadius: 0, tension: 0.3, fill: false },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { labels: { color: '#8892a6', font: { size: 11 } } },
            tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.raw.toFixed(1)}` } },
          },
          scales: {
            x: { grid: { color: 'rgba(36,42,56,0.4)' }, ticks: { color: '#8892a6', maxTicksLimit: 8 } },
            y: { grid: { color: 'rgba(36,42,56,0.4)' }, ticks: { color: '#8892a6' },
              title: { display: true, text: 'Indexed (100 = start)', color: '#4e5668' } },
          },
        },
      });

      // Stats
      const finalA = seriesA[seriesA.length - 1];
      const finalB = seriesB[seriesB.length - 1];
      const returnA = finalA - 100;
      const returnB = finalB - 100;
      const invested = 10000;
      const valA = invested * finalA / 100;
      const valB = invested * finalB / 100;
      const annA = years > 0 ? (Math.pow(finalA / 100, 1 / years) - 1) * 100 : returnA;
      const annB = years > 0 ? (Math.pow(finalB / 100, 1 / years) - 1) * 100 : returnB;

      // Show comparison strip
      const compEl = document.getElementById('whatIfComparison');
      if (compEl) {
        compEl.classList.remove('hidden');
        document.getElementById('whatIfLabelA').textContent = `$10K in ${tickerA}`;
        document.getElementById('whatIfValA').textContent   = fmtCurrency(valA);
        document.getElementById('whatIfLabelB').textContent = `$10K in ${tickerB}`;
        document.getElementById('whatIfValB').textContent   = fmtCurrency(valB);
      }

      const statsEl = document.getElementById('whatIfStats');
      if (statsEl) {
        statsEl.classList.remove('hidden');
        const diff = valA - valB;
        document.getElementById('wiDiffDollar').textContent = (diff >= 0 ? '+' : '') + fmtCurrency(diff);
        document.getElementById('wiDiffDollar').style.color = diff >= 0 ? 'var(--green)' : 'var(--red)';
        document.getElementById('wiDiffPct').textContent    = (returnA - returnB >= 0 ? '+' : '') + (returnA - returnB).toFixed(1) + '%';
        document.getElementById('wiDiffPct').style.color    = returnA >= returnB ? 'var(--green)' : 'var(--red)';
        document.getElementById('wiAnnReturn').textContent  = `${annA.toFixed(1)}% vs ${annB.toFixed(1)}%`;
      }
    } catch(e) {
      console.error('What If failed:', e);
    }
  }

  function renderCompareTab() {
    if (!STATE.portfolio.length) return;
    // Auto-run with current active timeframe
    const activeBtn = document.querySelector('#benchmarkTF .tf-btn.active');
    const tf = activeBtn ? activeBtn.dataset.tf : '1Y';
    runBenchmarkCompare(tf);
  }

  async function runBenchmarkCompare(tf) {
    if (!STATE.portfolio.length) return;

    const periodMap = { '1M':'1mo', '3M':'3mo', '6M':'6mo', 'YTD':'ytd', '1Y':'1y', '3Y':'3y', '5Y':'5y' };
    const period = periodMap[tf] || '1y';

    let totalValue = 0;
    const holdings = STATE.portfolio.map(p => {
      const q = STATE.quotes[p.ticker];
      const price = q ? q.price : (p.avgCost || 1);
      const value = price * p.shares;
      totalValue += value;
      return { ticker: p.ticker, weight: 0, value };
    });
    holdings.forEach(h => h.weight = h.value / totalValue);

    try {
      const data = await apiFetch('/api/history', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ holdings, period }),
      });

      // Draw chart
      const chart = data.chart || {};
      if (chart.dates && chart.portfolio) {
        destroyChart('benchmarkChart');
        const datasets = [
          { label: 'Your Portfolio', data: chart.portfolio, borderColor: '#4a8eff', borderWidth: 2.5, pointRadius: 0, tension: 0.3 },
        ];
        if (chart.spy) datasets.push({ label: 'SPY', data: chart.spy, borderColor: '#3dbc72', borderWidth: 1.5, pointRadius: 0, tension: 0.3, borderDash: [4,2] });
        if (chart.qqq) datasets.push({ label: 'QQQ', data: chart.qqq, borderColor: '#5ba8d4', borderWidth: 1.5, pointRadius: 0, tension: 0.3, borderDash: [4,2] });
        if (chart.dia) datasets.push({ label: 'DIA', data: chart.dia, borderColor: '#d4a03d', borderWidth: 1.5, pointRadius: 0, tension: 0.3, borderDash: [4,2] });

        STATE.charts.benchmarkChart = new Chart(document.getElementById('benchmarkChart'), {
          type: 'line',
          data: { labels: chart.dates, datasets },
          options: {
            responsive: true, maintainAspectRatio: false,
            plugins: { legend: { labels: { color: '#8892a6', font: { size: 11 } } },
              tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.raw.toFixed(1)}` } } },
            scales: {
              x: { grid: { color: 'rgba(36,42,56,0.4)' }, ticks: { color: '#8892a6', maxTicksLimit: 10 } },
              y: { grid: { color: 'rgba(36,42,56,0.4)' }, ticks: { color: '#8892a6', callback: v => v.toFixed(0) },
                title: { display: true, text: 'Indexed (100 = start)', color: '#4e5668' } },
            },
          },
        });
      }

      // Fill metrics table
      const tbody = document.getElementById('compareBody');
      if (tbody) {
        const p = data.portfolio || {};
        const s = data.spy || {};
        const q = data.qqq || {};
        const d = data.dia || {};
        const fmtPct = v => v != null ? (v >= 0 ? '+' : '') + (v * 100).toFixed(2) + '%' : '—';
        const fmtR   = v => v != null ? v.toFixed(3) : '—';
        const rows = [
          ['Total Return',      fmtPct(p.total),      fmtPct(s.total),      fmtPct(q.total),      fmtPct(d.total)],
          ['Annualized Return', fmtPct(p.annualized),  fmtPct(s.annualized),  fmtPct(q.annualized),  fmtPct(d.annualized)],
          ['Volatility (Ann.)', fmtPct(p.vol),        fmtPct(s.vol),        fmtPct(q.vol),        fmtPct(d.vol)],
          ['Sharpe Ratio',      fmtR(p.sharpe),       fmtR(s.sharpe),       fmtR(q.sharpe),       fmtR(d.sharpe)],
          ['Max Drawdown',      fmtPct(p.maxdrawdown), fmtPct(s.maxdrawdown), fmtPct(q.maxdrawdown), fmtPct(d.maxdrawdown)],
          ['Best Month',        fmtPct(p.best_month),  fmtPct(s.best_month),  fmtPct(q.best_month),  fmtPct(d.best_month)],
          ['Worst Month',       fmtPct(p.worst_month), fmtPct(s.worst_month), fmtPct(q.worst_month), fmtPct(d.worst_month)],
        ];
        tbody.innerHTML = rows.map(r => `<tr>
          <td class="text-muted">${r[0]}</td>
          <td class="mono">${r[1]}</td><td class="mono">${r[2]}</td>
          <td class="mono">${r[3]}</td><td class="mono">${r[4]}</td>
        </tr>`).join('');
      }
    } catch(e) {
      console.error('Benchmark compare failed:', e);
    }
  }
  
  /* ============================================================
     36. WATCHLIST TAB
     ============================================================ */
  function initWatchlistTab() {
    document.getElementById('addWatchlistBtn')?.addEventListener('click', addToWatchlist);
    document.getElementById('watchlistInput')?.addEventListener('keydown', e => {
      if (e.key === 'Enter') addToWatchlist();
    });
  }
  
  function addToWatchlist() {
    const input  = document.getElementById('watchlistInput');
    const ticker = input?.value.trim().toUpperCase();
    if (!ticker) return;
    if (!STATE.watchlist.includes(ticker)) {
      STATE.watchlist.push(ticker);
      saveToStorage();
    }
    if (input) input.value = '';
    renderWatchlistTab();
  }
  
  function removeFromWatchlist(ticker) {
    STATE.watchlist = STATE.watchlist.filter(t => t !== ticker);
    saveToStorage();
    renderWatchlistTab();
  }
  
  async function renderWatchlistTab() {
    const tbody = document.getElementById('watchlistBody');
    if (!tbody) return;

    if (!STATE.watchlist.length) {
      tbody.innerHTML = `<tr><td colspan="11">
        <div class="watchlist-empty">
          <div class="watchlist-empty-icon">◷</div>
          <div class="empty-state-title">Your watchlist is empty</div>
          <div class="empty-state-msg">Add tickers above to track their performance</div>
        </div></td></tr>`;
      return;
    }

    tbody.innerHTML = `<tr><td colspan="11" class="text-center text-muted" style="padding:20px">Loading quotes...</td></tr>`;

    const results = await Promise.all(
      STATE.watchlist.map(t => apiFetch(`/api/quote?ticker=${encodeURIComponent(t)}`).catch(() => null))
    );

    tbody.innerHTML = STATE.watchlist.map((ticker, i) => {
      const q = results[i];
      const chg    = q?.change    || 0;
      const chgPct = q?.changePct || 0;
      const chgCls = chg >= 0 ? 'positive' : 'negative';
      const price  = q?.price || 0;
      const w52H   = q?.week52High || q?.yearHigh;
      const w52L   = q?.week52Low || q?.yearLow;
      const perf52 = (w52L && price) ? ((price - w52L) / w52L * 100) : null;

      return `<tr>
        <td class="mono font-bold" style="cursor:pointer;color:var(--blue)"
            onclick="document.getElementById('researchSearch').value='${ticker}';loadResearchTicker('${ticker}');switchTab('research')">
          ${ticker}</td>
        <td class="truncate text-muted" style="max-width:120px">${q?.name || getTickerName(ticker)}</td>
        <td class="mono">${price ? fmtCurrency(price) : '—'}</td>
        <td class="mono ${chgCls}">${q ? (chg >= 0 ? '+' : '') + fmtCurrency(chg) : '—'}</td>
        <td class="mono ${chgCls}">${q ? (chgPct >= 0 ? '+' : '') + chgPct.toFixed(2) + '%' : '—'}</td>
        <td class="mono">${w52H ? fmtCurrency(w52H) : '—'}</td>
        <td class="mono">${w52L ? fmtCurrency(w52L) : '—'}</td>
        <td class="mono ${perf52 != null ? (perf52 >= 0 ? 'positive' : 'negative') : ''}">${perf52 != null ? (perf52 >= 0 ? '+' : '') + perf52.toFixed(1) + '%' : '—'}</td>
        <td class="mono">${q?.marketCap ? fmtCurrency(q.marketCap) : '—'}</td>
        <td class="text-muted text-xs">—</td>
        <td><button class="btn btn-sm btn-danger" onclick="removeFromWatchlist('${ticker}')">✕</button></td>
      </tr>`;
    }).join('');
  }
  
  /* ============================================================
     37. STRESS TEST SCENARIOS
     ============================================================ */
  function initStressTestScenarios() {
    // Stress test is now handled in the simulate tab via initSimulateTab
  }
  
  /* ============================================================
     38. PDF / CSV EXPORT
     ============================================================ */
  function initExportPDF() {
    document.getElementById('exportPdfBtn')?.addEventListener('click', exportToPDF);
    document.getElementById('exportCsvBtn')?.addEventListener('click', exportToCSV);
  }
  
  function exportToCSV() {
    if (!STATE.portfolio.length) return;
    const headers = ['Ticker','Shares','Avg Cost','Current Price','Market Value','P&L $','P&L %','Weight %'];
    let totalValue = 0;
    STATE.portfolio.forEach(p => {
      const q = STATE.quotes[p.ticker];
      totalValue += (q?.price || p.avgCost) * p.shares;
    });
  
    const rows = STATE.portfolio.map(p => {
      const q     = STATE.quotes[p.ticker];
      const price = q?.price  || p.avgCost;
      const value = price * p.shares;
      const cost  = p.avgCost * p.shares;
      const pnl   = p.avgCost > 0 ? value - cost : 0;
      const pnlPct= p.avgCost > 0 && cost > 0 ? (pnl / cost * 100).toFixed(2) : '—';
      const weight= totalValue > 0 ? (value / totalValue * 100).toFixed(2) : '0';
      return [p.ticker, p.shares, p.avgCost.toFixed(2), price.toFixed(2), value.toFixed(2), pnl.toFixed(2), pnlPct, weight];
    });
  
    const csv  = [headers, ...rows].map(r => r.join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `alphavault-portfolio-${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }
  
  function exportToPDF() {
    window.print();
  }
  
  /* ============================================================
     39. OPTIONS & DERIVATIVES TAB
     ============================================================ */
  function initOptionsTab() {
    document.getElementById('optPriceBtn')?.addEventListener('click', priceOption);
    document.getElementById('ivSolveBtn')?.addEventListener('click', solveIV);
    document.getElementById('payoffPosition')?.addEventListener('change', priceOption);
    document.getElementById('optType')?.addEventListener('change', priceOption);
    document.getElementById('stratBtn')?.addEventListener('click', runStrategy);
    document.getElementById('strategySelect')?.addEventListener('change', onStrategyChange);
    onStrategyChange();
  }

  function onStrategyChange() {
    const strat = document.getElementById('strategySelect')?.value;
    const row = document.getElementById('stratStrikesRow');
    const k1 = document.getElementById('stratK1Group');
    const k2 = document.getElementById('stratK2Group');
    const k3 = document.getElementById('stratK3Group');
    const k4 = document.getElementById('stratK4Group');
    const S = parseFloat(document.getElementById('stratS')?.value) || 100;

    if (!row) return;
    row.classList.remove('hidden');
    [k2, k3, k4].forEach(el => el?.classList.add('hidden'));

    if (strat === 'straddle' || strat === 'protective_put' || strat === 'covered_call') {
      document.getElementById('stratK1Label').textContent = 'Strike (K)';
      document.getElementById('stratK1').value = S;
    } else if (strat === 'bull_call_spread') {
      document.getElementById('stratK1Label').textContent = 'Lower Strike';
      document.getElementById('stratK1').value = (S * 0.95).toFixed(2);
      k2?.classList.remove('hidden');
      document.getElementById('stratK2').value = (S * 1.05).toFixed(2);
    } else if (strat === 'iron_condor') {
      document.getElementById('stratK1Label').textContent = 'K1 (Put Buy)';
      document.getElementById('stratK1').value = (S * 0.85).toFixed(2);
      [k2, k3, k4].forEach(el => el?.classList.remove('hidden'));
      document.getElementById('stratK2').value = (S * 0.95).toFixed(2);
      document.getElementById('stratK3').value = (S * 1.05).toFixed(2);
      document.getElementById('stratK4').value = (S * 1.15).toFixed(2);
    }
  }

  async function priceOption() {
    const S     = parseFloat(document.getElementById('optS')?.value);
    const K     = parseFloat(document.getElementById('optK')?.value);
    const T     = parseFloat(document.getElementById('optT')?.value);
    const r     = parseFloat(document.getElementById('optR')?.value);
    const sigma = parseFloat(document.getElementById('optSigma')?.value);
    const type  = document.getElementById('optType')?.value || 'call';

    if (!S || !K || !T || !sigma) return;

    try {
      const data = await apiFetch('/api/options', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'price', S, K, T, r, sigma, type }),
      });
      if (data.error) throw new Error(data.error);

      document.getElementById('optCallPrice').textContent = '$' + data.call.toFixed(4);
      document.getElementById('optPutPrice').textContent = '$' + data.put.toFixed(4);
      document.getElementById('optCallPrice').className = 'stat-value mono positive';
      document.getElementById('optPutPrice').className = 'stat-value mono negative';

      const residual = Math.abs(data.parityResidual);
      document.getElementById('optParityCheck').textContent =
        `Put-Call Parity: ${residual < 0.001 ? '✓ Verified' : '△ Residual: ' + residual.toFixed(6)}`;

      const greeks = data.greeks;
      const interp = {
        delta: `Price moves $${Math.abs(greeks.delta).toFixed(3)} per $1 spot move`,
        gamma: `Delta changes ${greeks.gamma.toFixed(4)} per $1 spot move`,
        theta: `Loses $${Math.abs(greeks.theta).toFixed(4)}/day from time decay`,
        vega:  `Price changes $${greeks.vega.toFixed(4)} per 1% vol move`,
        rho:   `Price changes $${greeks.rho.toFixed(4)} per 1% rate move`,
      };
      document.getElementById('greeksBody').innerHTML = Object.entries(greeks).map(([k, v]) =>
        `<tr>
          <td class="mono" style="text-transform:capitalize;font-weight:600;">${k}</td>
          <td class="mono ${k === 'theta' ? 'negative' : ''}">${v.toFixed(6)}</td>
          <td class="text-muted text-xs">${interp[k] || ''}</td>
        </tr>`
      ).join('');

      // Payoff diagram
      const position = document.getElementById('payoffPosition')?.value || 'long';
      const payData = await apiFetch('/api/options', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'payoff', S, K, T, r, sigma, type, position }),
      });
      if (!payData.error) {
        renderPayoffChart(payData);
        document.getElementById('payoffStats')?.classList.remove('hidden');
        document.getElementById('payoffPremium').textContent = '$' + payData.premium.toFixed(2);
        document.getElementById('payoffBreakeven').textContent = '$' + payData.breakeven.toFixed(2);
        document.getElementById('payoffMaxLoss').textContent = '$' + payData.maxLoss.toFixed(2);
        document.getElementById('payoffMaxLoss').className = 'stat-value mono negative';
      }
    } catch (e) {
      console.error('Options pricing error:', e);
    }
  }

  function renderPayoffChart(data) {
    if (STATE.charts.payoff) STATE.charts.payoff.destroy();
    const ctx = document.getElementById('payoffChart')?.getContext('2d');
    if (!ctx) return;

    const colors = data.chart.pnl.map(v => v >= 0 ? '#3dbc72' : '#d44a4a');

    STATE.charts.payoff = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.chart.prices,
        datasets: [
          {
            label: 'P&L at Expiry',
            data: data.chart.pnl,
            borderColor: '#4a8eff',
            backgroundColor: 'transparent',
            borderWidth: 2,
            pointRadius: 0,
            tension: 0,
          },
          {
            label: 'Breakeven',
            data: data.chart.zero,
            borderColor: 'rgba(255,255,255,0.2)',
            borderDash: [5, 5],
            borderWidth: 1,
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: true, labels: { color: '#8a9bb5', boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: ctx => `P&L: $${ctx.parsed.y.toFixed(2)} at S=$${ctx.label}`,
            }
          },
        },
        scales: {
          x: { title: { display: true, text: 'Spot Price at Expiry', color: '#8a9bb5' },
               ticks: { color: '#8a9bb5', maxTicksLimit: 10 }, grid: { color: 'rgba(255,255,255,0.05)' } },
          y: { title: { display: true, text: 'Profit / Loss ($)', color: '#8a9bb5' },
               ticks: { color: '#8a9bb5' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        },
      },
    });
  }

  async function solveIV() {
    const marketPrice = parseFloat(document.getElementById('ivMarketPrice')?.value);
    const S    = parseFloat(document.getElementById('ivS')?.value);
    const K    = parseFloat(document.getElementById('ivK')?.value);
    const T    = parseFloat(document.getElementById('ivT')?.value);
    const type = document.getElementById('ivType')?.value || 'call';

    if (!marketPrice || !S || !K || !T) return;

    try {
      const data = await apiFetch('/api/options', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'implied_vol', S, K, T, r: 0.05, marketPrice, type }),
      });
      if (data.error) throw new Error(data.error);

      document.getElementById('ivResults')?.classList.remove('hidden');
      document.getElementById('ivResult').textContent = data.impliedVolPct.toFixed(2) + '%';
      document.getElementById('ivTheo').textContent = '$' + data.theoreticalPrice.toFixed(4);
      document.getElementById('ivDiff').textContent = '$' + data.priceDiff.toFixed(6);
    } catch (e) {
      console.error('IV solve error:', e);
    }
  }

  async function runStrategy() {
    const strategy = document.getElementById('strategySelect')?.value;
    const S     = parseFloat(document.getElementById('stratS')?.value);
    const sigma = parseFloat(document.getElementById('stratSigma')?.value);
    const T     = parseFloat(document.getElementById('stratT')?.value);
    const K1    = parseFloat(document.getElementById('stratK1')?.value);
    const K2    = parseFloat(document.getElementById('stratK2')?.value);
    const K3    = parseFloat(document.getElementById('stratK3')?.value);
    const K4    = parseFloat(document.getElementById('stratK4')?.value);

    if (!S || !sigma || !T) return;

    const body = { action: 'strategy', strategy, S, sigma, T, r: 0.05 };

    if (strategy === 'straddle') body.K = K1;
    else if (strategy === 'bull_call_spread') { body.K1 = K1; body.K2 = K2; }
    else if (strategy === 'iron_condor') { body.K1 = K1; body.K2 = K2; body.K3 = K3; body.K4 = K4; }
    else if (strategy === 'protective_put') body.K = K1;
    else if (strategy === 'covered_call') body.K = K1;

    try {
      const data = await apiFetch('/api/options', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (data.error) throw new Error(data.error);

      renderStrategyChart(data);

      const stats = document.getElementById('stratStats');
      stats?.classList.remove('hidden');
      const info = data.info;

      const l1 = document.getElementById('stratStat1Label');
      const l2 = document.getElementById('stratStat2Label');
      const l3 = document.getElementById('stratStat3Label');
      const v1 = document.getElementById('stratStat1');
      const v2 = document.getElementById('stratStat2');
      const v3 = document.getElementById('stratStat3');

      if (strategy === 'straddle') {
        l1.textContent = 'Total Cost'; v1.textContent = '$' + info.cost.toFixed(2);
        l2.textContent = 'Upper B/E';  v2.textContent = '$' + info.upperBE.toFixed(2);
        l3.textContent = 'Lower B/E';  v3.textContent = '$' + info.lowerBE.toFixed(2);
      } else if (strategy === 'iron_condor') {
        l1.textContent = 'Net Credit'; v1.textContent = '$' + info.credit.toFixed(2); v1.className = 'stat-value mono positive';
        l2.textContent = 'Max Profit'; v2.textContent = '$' + info.maxProfit.toFixed(2); v2.className = 'stat-value mono positive';
        l3.textContent = 'Max Loss';   v3.textContent = '$' + info.maxLoss.toFixed(2); v3.className = 'stat-value mono negative';
      } else if (strategy === 'bull_call_spread') {
        l1.textContent = 'Net Cost';   v1.textContent = '$' + info.cost.toFixed(2);
        l2.textContent = 'Max Profit'; v2.textContent = '$' + info.maxProfit.toFixed(2); v2.className = 'stat-value mono positive';
        l3.textContent = 'Breakeven';  v3.textContent = '$' + info.breakeven.toFixed(2);
      } else if (strategy === 'protective_put') {
        l1.textContent = 'Put Cost';   v1.textContent = '$' + info.putCost.toFixed(2);
        l2.textContent = 'Max Loss';   v2.textContent = '$' + info.maxLoss.toFixed(2); v2.className = 'stat-value mono negative';
        l3.textContent = 'Breakeven';  v3.textContent = '$' + info.breakeven.toFixed(2);
      } else if (strategy === 'covered_call') {
        l1.textContent = 'Premium';    v1.textContent = '$' + info.premium.toFixed(2); v1.className = 'stat-value mono positive';
        l2.textContent = 'Max Profit'; v2.textContent = '$' + info.maxProfit.toFixed(2); v2.className = 'stat-value mono positive';
        l3.textContent = 'Breakeven';  v3.textContent = '$' + info.breakeven.toFixed(2);
      }
    } catch (e) {
      console.error('Strategy error:', e);
    }
  }

  function renderStrategyChart(data) {
    if (STATE.charts.strategy) STATE.charts.strategy.destroy();
    const ctx = document.getElementById('strategyChart')?.getContext('2d');
    if (!ctx) return;

    STATE.charts.strategy = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.chart.prices,
        datasets: [
          {
            label: data.strategy.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) + ' P&L',
            data: data.chart.pnl,
            borderColor: '#d4a03d',
            backgroundColor: 'transparent',
            borderWidth: 2,
            pointRadius: 0,
            tension: 0,
          },
          {
            label: 'Breakeven',
            data: data.chart.zero,
            borderColor: 'rgba(255,255,255,0.2)',
            borderDash: [5, 5],
            borderWidth: 1,
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: true, labels: { color: '#8a9bb5', boxWidth: 12, font: { size: 11 } } },
          tooltip: {
            callbacks: {
              label: ctx => `P&L: $${ctx.parsed.y.toFixed(2)}`,
            }
          },
        },
        scales: {
          x: { title: { display: true, text: 'Spot Price at Expiry', color: '#8a9bb5' },
               ticks: { color: '#8a9bb5', maxTicksLimit: 10 }, grid: { color: 'rgba(255,255,255,0.05)' } },
          y: { title: { display: true, text: 'Profit / Loss ($)', color: '#8a9bb5' },
               ticks: { color: '#8a9bb5' }, grid: { color: 'rgba(255,255,255,0.05)' } },
        },
      },
    });
  }

  /* ============================================================
     END OF APP.JS PART 2
     ============================================================ */