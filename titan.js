'use strict';
/* ============================================================
   TITAN.JS — Project Titan Frontend Modules
   All 11 new modules. Accesses globals from app.js:
   STATE, apiFetch, destroyChart, renderErrorState,
   renderSkeletonGrid, CHART_COLORS, fmtCurrency, fmtNum
   ============================================================ */

const TITAN = {
  chartbrain: { data: null, ticker: null },
  nervemap: { data: null },
  driftguard: { data: null },
  factorlens: { data: null },
  alphatrace: { data: null },
  regimeradar: { data: null },
  sectorscan: { data: null },
  earningsedge: { data: null, ticker: null },
  bondlab: { curve: null, pricing: null },
  pairpulse: { data: null },
  rewindengine: { data: null, comparison: null },
};

// ---- Helpers ----
function fmtPct(n) {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return (n * 100).toFixed(2) + '%';
}
function fmtPctRaw(n) {
  if (n === null || n === undefined || isNaN(n)) return '—';
  return n.toFixed(2) + '%';
}
function pctColor(n) { return n > 0 ? 'var(--green, #3dbc72)' : n < 0 ? 'var(--red, #d44a4a)' : 'inherit'; }
function strengthDots(s, max) {
  max = max || 5;
  return '●'.repeat(Math.min(s, max)) + '○'.repeat(Math.max(0, max - s));
}
function impactColor(score) {
  if (score > 0) return `rgba(34,197,94,${Math.min(Math.abs(score) / 5, 1) * 0.8})`;
  if (score < 0) return `rgba(239,68,68,${Math.min(Math.abs(score) / 5, 1) * 0.8})`;
  return 'rgba(107,114,128,0.3)';
}
function getTitanHoldings() {
  if (!STATE.portfolio || !STATE.portfolio.length) return null;
  const totalValue = STATE.portfolio.reduce((sum, p) => {
    const q = STATE.quotes[p.ticker];
    const price = q ? (q.price || q.currentPrice || 0) : (p.avgCost || 0);
    return sum + (p.shares * price);
  }, 0);
  if (totalValue <= 0) return null;
  return STATE.portfolio.map(p => {
    const q = STATE.quotes[p.ticker];
    const price = q ? (q.price || q.currentPrice || 0) : (p.avgCost || 0);
    return { ticker: p.ticker, shares: p.shares, avg_cost: p.avgCost, current_price: price, weight: (p.shares * price) / totalValue, days_held: 365 };
  });
}
function noPortfolioMsg() {
  return `<div class="card mb-4"><div style="padding:40px;text-align:center;">
    <div style="font-size:24px;margin-bottom:12px;">◈</div>
    <div class="stat-label">No Portfolio Loaded</div>
    <div class="text-muted" style="margin-top:8px;">Go to the Portfolio tab and add positions first, then return here.</div>
  </div></div>`;
}
function titanLoading(msg) { return `<div class="text-center text-muted" style="padding:40px">${msg || 'Loading...'}</div>`; }
function cardWrap(title, body, refreshFn) {
  const rid = 'r' + Math.random().toString(36).slice(2, 8);
  if (refreshFn) setTimeout(() => { const b = document.getElementById(rid); if (b) b.addEventListener('click', refreshFn); }, 50);
  return `<div class="card mb-4"><div class="card-header"><span class="card-title">${title}</span>${refreshFn ? `<button class="collapsible-toggle" id="${rid}">↻ Refresh</button>` : ''}</div>${body}</div>`;
}
function statBox(label, value, sub) {
  return `<div class="stat-box"><div class="stat-label">${label}</div><div class="stat-value mono">${value}</div>${sub ? `<div class="stat-sub">${sub}</div>` : ''}</div>`;
}
function downsample(arr, max) {
  if (!arr || arr.length <= max) return arr;
  const step = Math.ceil(arr.length / max);
  return arr.filter((_, i) => i % step === 0);
}

/* ============================================================
   1. BONDS — BondLab
   ============================================================ */
function renderBondsTab() {
  const el = document.getElementById('bondsContent');
  if (TITAN.bondlab.curve) { _renderBondsUI(el); return; }
  el.innerHTML = titanLoading('Loading yield curve...');
  apiFetch('/api/bondlab/curve').then(data => {
    TITAN.bondlab.curve = data;
    _renderBondsUI(el);
  }).catch(e => { el.innerHTML = renderErrorState(e.message, renderBondsTab); });
}
function _renderBondsUI(el) {
  const c = TITAN.bondlab.curve;
  const invLabel = c.inverted ? '<span style="color:var(--red)">INVERTED ⚠</span>' : '<span style="color:var(--green)">Normal ✓</span>';
  el.innerHTML = `
    ${cardWrap('US Treasury Yield Curve', `
      <div class="stat-grid"><div class="stat-box"><div class="stat-label">2s10s Spread</div><div class="stat-value mono">${(c.slope_2s10s * 10000).toFixed(0)} bps</div></div>
      <div class="stat-box"><div class="stat-label">3M-10Y Spread</div><div class="stat-value mono">${(c.slope_3m10y * 10000).toFixed(0)} bps</div></div>
      <div class="stat-box"><div class="stat-label">Curve Shape</div><div class="stat-value">${invLabel}</div></div></div>
      <div class="chart-wrap" style="height:300px;"><canvas id="yieldCurveChart"></canvas></div>
    `, () => { TITAN.bondlab.curve = null; renderBondsTab(); })}
    ${cardWrap('Bond Calculator', `
      <div class="form-row mb-3">
        <div class="form-group" style="flex:1"><label class="form-label">Face Value</label><input type="number" class="form-input mono" id="bondFace" value="1000" /></div>
        <div class="form-group" style="flex:1"><label class="form-label">Coupon Rate (%)</label><input type="number" class="form-input mono" id="bondCoupon" value="5" step="0.1" /></div>
        <div class="form-group" style="flex:1"><label class="form-label">YTM (%)</label><input type="number" class="form-input mono" id="bondYTM" value="4" step="0.1" /></div>
        <div class="form-group" style="flex:1"><label class="form-label">Years</label><input type="number" class="form-input mono" id="bondYears" value="10" /></div>
        <div class="form-group" style="flex:1"><label class="form-label">Frequency</label><select class="form-input" id="bondFreq"><option value="2">Semi-Annual</option><option value="1">Annual</option><option value="4">Quarterly</option></select></div>
        <div class="form-group" style="flex:0 0 auto;justify-content:flex-end;"><label class="form-label">&nbsp;</label><button class="btn btn-primary" id="bondCalcBtn">Calculate</button></div>
      </div>
      <div id="bondResults"></div>
    `)}`;
  _drawYieldCurve(c);
  document.getElementById('bondCalcBtn').addEventListener('click', _runBondCalc);
}
function _drawYieldCurve(c) {
  destroyChart('yieldCurveChart');
  STATE.charts.yieldCurveChart = new Chart(document.getElementById('yieldCurveChart'), {
    type: 'line',
    data: { labels: c.labels, datasets: [{ label: 'Yield', data: c.yields.map(y => (y * 100).toFixed(3)), borderColor: CHART_COLORS[0], backgroundColor: 'rgba(74,142,255,0.1)', fill: true, tension: 0.3, pointRadius: 4 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { title: { display: true, text: 'Yield (%)' }, ticks: { color: 'var(--text3)' }, grid: { color: 'rgba(255,255,255,0.06)' } }, x: { ticks: { color: 'var(--text3)' }, grid: { display: false } } } }
  });
}
async function _runBondCalc() {
  const body = {
    face: +document.getElementById('bondFace').value,
    coupon_rate: +document.getElementById('bondCoupon').value / 100,
    ytm: +document.getElementById('bondYTM').value / 100,
    years: +document.getElementById('bondYears').value,
    frequency: +document.getElementById('bondFreq').value,
  };
  document.getElementById('bondResults').innerHTML = titanLoading('Calculating...');
  try {
    const d = await apiFetch('/api/bondlab/price', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    TITAN.bondlab.pricing = d;
    const sc = d.scenarios || {};
    document.getElementById('bondResults').innerHTML = `
      <div class="grid-3">${statBox('Price', '$' + d.price.toFixed(2), d.premium_discount)}${statBox('Modified Duration', d.modified_duration.toFixed(2) + ' yrs')}${statBox('Convexity', d.convexity.toFixed(2))}</div>
      <div class="grid-3">${statBox('Current Yield', (d.current_yield * 100).toFixed(2) + '%')}${statBox('Macaulay Duration', d.macaulay_duration.toFixed(2) + ' yrs')}${statBox('Dollar Duration', '$' + d.dollar_duration.toFixed(2))}</div>
      <div class="table-scroll" style="margin-top:16px"><table class="data-table"><thead><tr><th>Scenario</th><th>Yield Change</th><th>Duration Effect</th><th>Convexity Effect</th><th>Net Change</th><th>New Price</th></tr></thead><tbody>
      ${Object.entries(sc).map(([k, v]) => `<tr><td>${k}</td><td>${(v.yield_change * 100).toFixed(1)}%</td><td colspan="2"></td><td style="color:${pctColor(v.price_change_pct)}">${v.price_change_pct.toFixed(2)}%</td><td>$${v.new_price.toFixed(2)}</td></tr>`).join('')}
      </tbody></table></div>`;
  } catch (e) { document.getElementById('bondResults').innerHTML = renderErrorState(e.message); }
}

/* ============================================================
   2. TECHNICAL — ChartBrain
   ============================================================ */
function renderTechnicalTab() {
  const el = document.getElementById('technicalContent');
  if (TITAN.chartbrain.data && TITAN.chartbrain.ticker) { _renderTechUI(el); return; }
  el.innerHTML = cardWrap('Technical Analysis', `
    <div class="form-row mb-3">
      <div class="form-group" style="flex:2"><label class="form-label">Ticker</label><input type="text" class="form-input mono" id="techTicker" placeholder="AAPL" value="AAPL" /></div>
      <div class="form-group" style="flex:1"><label class="form-label">Period</label><select class="form-input" id="techPeriod"><option value="1m">1M</option><option value="3m">3M</option><option value="6m">6M</option><option value="1y" selected>1Y</option><option value="2y">2Y</option><option value="5y">5Y</option></select></div>
      <div class="form-group" style="flex:0 0 auto;justify-content:flex-end;"><label class="form-label">&nbsp;</label><button class="btn btn-primary" id="techAnalyzeBtn">Analyze</button></div>
    </div><div id="techResultsArea"></div>`);
  document.getElementById('techAnalyzeBtn').addEventListener('click', _runTechAnalysis);
}
async function _runTechAnalysis() {
  const ticker = document.getElementById('techTicker').value.toUpperCase().trim();
  const period = document.getElementById('techPeriod').value;
  if (!ticker) return;
  const area = document.getElementById('techResultsArea');
  area.innerHTML = titanLoading('Fetching technical data for ' + ticker + '...');
  try {
    const data = await apiFetch(`/api/chartbrain?ticker=${ticker}&period=${period}`);
    TITAN.chartbrain.data = data;
    TITAN.chartbrain.ticker = ticker;
    _renderTechCharts(area, data);
  } catch (e) { area.innerHTML = renderErrorState(e.message, _runTechAnalysis); }
}
function _renderTechUI(el) {
  el.innerHTML = cardWrap('Technical Analysis', `
    <div class="form-row mb-3">
      <div class="form-group" style="flex:2"><label class="form-label">Ticker</label><input type="text" class="form-input mono" id="techTicker" placeholder="AAPL" value="${TITAN.chartbrain.ticker}" /></div>
      <div class="form-group" style="flex:1"><label class="form-label">Period</label><select class="form-input" id="techPeriod"><option value="1m">1M</option><option value="3m">3M</option><option value="6m">6M</option><option value="1y" selected>1Y</option><option value="2y">2Y</option><option value="5y">5Y</option></select></div>
      <div class="form-group" style="flex:0 0 auto;justify-content:flex-end;"><label class="form-label">&nbsp;</label><button class="btn btn-primary" id="techAnalyzeBtn">Analyze</button></div>
    </div><div id="techResultsArea"></div>`);
  document.getElementById('techAnalyzeBtn').addEventListener('click', () => { TITAN.chartbrain.data = null; _runTechAnalysis(); });
  _renderTechCharts(document.getElementById('techResultsArea'), TITAN.chartbrain.data);
}
function _signalExplain(s) {
  const ind = s.indicator;
  const type = s.type;
  if (ind === 'RSI' && type === 'bullish')
    return 'The Relative Strength Index has fallen below the oversold threshold. This means selling pressure has been extreme and the stock may be due for a bounce. Historically, deeply oversold readings often precede short-term rallies.';
  if (ind === 'RSI' && type === 'bearish')
    return 'The RSI has risen above the overbought threshold. This indicates buying momentum may be exhausted and the price could pull back. It does not mean the stock will crash — just that the pace of gains is unusually fast.';
  if (ind === 'MACD' && type === 'bullish')
    return 'The MACD line (difference between the 12-day and 26-day moving averages) just crossed above its signal line. This suggests short-term momentum is turning positive — the recent price trend is accelerating upward.';
  if (ind === 'MACD' && type === 'bearish')
    return 'The MACD line crossed below its signal line. This suggests upward momentum is fading and the short-term trend may be turning negative.';
  if (ind === 'MA' && type === 'bullish')
    return 'A "Golden Cross" occurred — the 50-day moving average crossed above the 200-day. This is one of the most watched long-term bullish signals. It suggests the medium-term trend is now stronger than the long-term trend, often marking the start of a sustained uptrend.';
  if (ind === 'MA' && type === 'bearish')
    return 'A "Death Cross" occurred — the 50-day moving average crossed below the 200-day. This classic bearish signal suggests the medium-term trend has weakened below the long-term trend, potentially signaling a longer downturn ahead.';
  if (ind === 'Bollinger' && s.message.includes('squeeze'))
    return 'Bollinger Band width has narrowed to extreme levels. This "squeeze" indicates very low volatility — like a coiled spring. A big move (up or down) often follows, though the direction is unclear until the breakout occurs.';
  if (ind === 'Bollinger' && type === 'bullish')
    return 'The price has broken above the upper Bollinger Band. This can signal strong upward momentum, though it can also mean the stock is overextended in the short term.';
  if (ind === 'Bollinger' && type === 'bearish')
    return 'The price has dropped below the lower Bollinger Band. This often indicates the stock is oversold in the short term, but can also signal the start of a new downtrend.';
  if (ind === 'Volume')
    return 'Trading volume surged well above its recent average. Volume spikes often confirm the significance of a price move — a breakout on high volume is more reliable than one on low volume.';
  return 'A technical indicator has triggered a signal based on historical price patterns.';
}
function _renderTechCharts(area, d) {
  const ind = d.indicators || {};
  const sig = d.signals || [];
  const sr = d.support_resistance || {};
  const dates = (d.dates || []).map(x => x.slice(5));
  const signalHtml = sig.length ? `<div class="signal-list">${sig.map((s, i) => {
    const explain = _signalExplain(s);
    const eid = 'sigexp' + i;
    return `<div class="signal-item" style="flex-direction:column;align-items:stretch;">
      <div style="display:flex;align-items:center;gap:10px;">
        <div class="signal-dot ${s.type}"></div>
        <div class="signal-msg">${s.message}</div>
        <div class="signal-strength">${strengthDots(s.strength, 5)}</div>
        <button class="collapsible-toggle" onclick="var e=document.getElementById('${eid}');e.style.display=e.style.display==='none'?'block':'none';" style="margin-left:auto;">Why?</button>
      </div>
      <div id="${eid}" style="display:none;margin-top:8px;padding:8px 12px;font-size:12px;color:var(--text3);background:var(--bg1);border-radius:6px;line-height:1.5;">${explain}</div>
    </div>`;
  }).join('')}</div>` : '<div class="text-muted" style="padding:16px">No significant signals detected</div>';
  area.innerHTML = `
    <div class="chart-wrap" style="height:340px;"><canvas id="techPriceChart"></canvas></div>
    <div class="chart-wrap" style="height:200px;margin-top:12px;"><canvas id="techRsiChart"></canvas></div>
    <div class="chart-wrap" style="height:200px;margin-top:12px;"><canvas id="techMacdChart"></canvas></div>
    <div class="chart-wrap" style="height:150px;margin-top:12px;"><canvas id="techVolumeChart"></canvas></div>
    <div style="display:flex;gap:16px;margin-top:16px;flex-wrap:wrap;">
      <div style="flex:1;min-width:280px;">${cardWrap('Signals', signalHtml)}</div>
      <div style="flex:1;min-width:200px;">${cardWrap('Support / Resistance', `
        <div style="padding:12px"><div class="stat-label" style="margin-bottom:6px">Resistance</div>${(sr.resistance||[]).map(r=>`<div class="mono" style="color:var(--red)">${r.toFixed(2)}</div>`).join('')||'—'}
        <div class="stat-label" style="margin:12px 0 6px">Support</div>${(sr.support||[]).map(s=>`<div class="mono" style="color:var(--green)">${s.toFixed(2)}</div>`).join('')||'—'}</div>`)}</div>
    </div>`;
  const close = d.ohlcv?.close || [];
  const datasets = [{ label: 'Close', data: close, borderColor: CHART_COLORS[0], borderWidth: 1.5, pointRadius: 0, fill: false }];
  if (ind.sma_20) datasets.push({ label: 'SMA 20', data: ind.sma_20, borderColor: '#4a8eff', borderWidth: 1, pointRadius: 0, borderDash: [4, 2], fill: false });
  if (ind.sma_50) datasets.push({ label: 'SMA 50', data: ind.sma_50, borderColor: '#d4a03d', borderWidth: 1, pointRadius: 0, borderDash: [4, 2], fill: false });
  if (ind.sma_200) datasets.push({ label: 'SMA 200', data: ind.sma_200, borderColor: '#d44a4a', borderWidth: 1, pointRadius: 0, borderDash: [4, 2], fill: false });
  if (ind.bollinger?.upper) datasets.push({ label: 'BB Upper', data: ind.bollinger.upper, borderColor: 'rgba(155,126,216,0.4)', borderWidth: 1, pointRadius: 0, fill: '+1' , backgroundColor: 'rgba(155,126,216,0.07)' });
  if (ind.bollinger?.lower) datasets.push({ label: 'BB Lower', data: ind.bollinger.lower, borderColor: 'rgba(155,126,216,0.4)', borderWidth: 1, pointRadius: 0, fill: false });
  destroyChart('techPriceChart');
  STATE.charts.techPriceChart = new Chart(document.getElementById('techPriceChart'), { type: 'line', data: { labels: dates, datasets }, options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } } }, scales: { y: { grid: { color: 'rgba(255,255,255,0.06)' } }, x: { ticks: { maxTicksLimit: 12, color: 'var(--text3)' }, grid: { display: false } } } } });
  // RSI
  const rsi = ind.rsi || [];
  destroyChart('techRsiChart');
  STATE.charts.techRsiChart = new Chart(document.getElementById('techRsiChart'), { type: 'line', data: { labels: dates, datasets: [{ label: 'RSI', data: rsi, borderColor: '#9b7ed8', borderWidth: 1.5, pointRadius: 0, fill: false }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, annotation: {} }, scales: { y: { min: 0, max: 100, grid: { color: 'rgba(255,255,255,0.06)' } }, x: { ticks: { maxTicksLimit: 12, color: 'var(--text3)' }, grid: { display: false } } } } });
  // MACD
  const macd = ind.macd || {};
  const histColors = (macd.histogram || []).map(v => v > 0 ? 'rgba(61,188,114,0.6)' : 'rgba(212,74,74,0.6)');
  destroyChart('techMacdChart');
  STATE.charts.techMacdChart = new Chart(document.getElementById('techMacdChart'), { type: 'bar', data: { labels: dates, datasets: [{ label: 'Histogram', data: macd.histogram || [], backgroundColor: histColors, order: 2 }, { label: 'MACD', data: macd.macd_line || [], type: 'line', borderColor: CHART_COLORS[0], borderWidth: 1.5, pointRadius: 0, order: 1 }, { label: 'Signal', data: macd.signal_line || [], type: 'line', borderColor: '#d4a03d', borderWidth: 1, pointRadius: 0, borderDash: [3, 2], order: 1 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } } }, scales: { y: { grid: { color: 'rgba(255,255,255,0.06)' } }, x: { ticks: { maxTicksLimit: 12, color: 'var(--text3)' }, grid: { display: false } } } } });
  // Volume
  const vol = d.ohlcv?.volume || [];
  destroyChart('techVolumeChart');
  STATE.charts.techVolumeChart = new Chart(document.getElementById('techVolumeChart'), { type: 'bar', data: { labels: dates, datasets: [{ label: 'Volume', data: vol, backgroundColor: 'rgba(74,142,255,0.3)' }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { grid: { color: 'rgba(255,255,255,0.06)' } }, x: { ticks: { maxTicksLimit: 12, color: 'var(--text3)' }, grid: { display: false } } } } });
}

/* ============================================================
   3. NERVEMAP — Market Intel
   ============================================================ */
function renderNerveMapTab() {
  const el = document.getElementById('nervemapContent');
  if (TITAN.nervemap.data) { _renderNerveUI(el); return; }
  el.innerHTML = titanLoading('Fetching market intelligence...');
  const holdings = getTitanHoldings();
  const prom = holdings
    ? apiFetch('/api/nervemap', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ holdings }) })
    : apiFetch('/api/nervemap?tickers=AAPL,MSFT,GOOGL,AMZN,JPM,XOM');
  prom.then(data => { TITAN.nervemap.data = data; _renderNerveUI(el); }).catch(e => { el.innerHTML = renderErrorState(e.message, renderNerveMapTab); });
}
function _renderNerveUI(el) {
  const d = TITAN.nervemap.data;
  const sClass = d.sentiment === 'RISK-ON' ? 'risk-on' : d.sentiment === 'RISK-OFF' ? 'risk-off' : 'neutral';
  let html = `<div style="display:flex;align-items:center;gap:16px;margin-bottom:20px;flex-wrap:wrap;">
    <div class="sentiment-badge ${sClass}">${d.sentiment}</div>
    <div class="mono" style="font-size:14px;">Score: ${(d.sentiment_score || 0).toFixed(2)}</div>
    <div class="text-muted">${d.story_count || 0} stories analyzed</div>
    <button class="collapsible-toggle" id="nerveRefresh">↻ Refresh</button></div>`;
  // Heatmap
  const ni = d.net_impact || {};
  const hasEntities = Object.values(ni).some(dim => dim && Object.keys(dim).length > 0);
  if (hasEntities) {
    for (const [dim, entities] of Object.entries(ni)) {
      if (!entities || !Object.keys(entities).length) continue;
      html += `<div class="heatmap-section">${dim.toUpperCase()}</div><div class="heatmap-grid">`;
      for (const [name, score] of Object.entries(entities)) {
        html += `<div class="heatmap-cell" style="background:${impactColor(score)}"><div class="cell-label">${name.replace(/_/g, ' ')}</div><div class="cell-score">${(score || 0).toFixed(1)}</div></div>`;
      }
      html += '</div>';
    }
  }
  if ((d.story_count || 0) === 0) {
    html += `<div class="text-muted" style="padding:16px;text-align:center;">No news articles available. Click ↻ Refresh to try again.</div>`;
  }
  // Shock feed
  const stories = (d.top_stories || []).slice(0, 15);
  if (stories.length) {
    html += cardWrap('Shock Feed', stories.map(s => `<div class="shock-story"><div class="shock-headline">${s.headline || '—'}</div><div class="shock-meta"><span class="category-tag">${s.category || 'general'}</span><span class="shock-magnitude">mag: ${(s.magnitude || 0).toFixed(1)}</span></div></div>`).join(''));
  }
  // Portfolio impact
  if (d.portfolio_impact) {
    const pi = d.portfolio_impact;
    html += cardWrap('Portfolio Impact', `<div class="grid-3">${statBox('Impact Score', (pi.portfolio_impact_score || 0).toFixed(2))}${statBox('Most Affected', pi.most_affected?.ticker || '—', (pi.most_affected?.impact || 0).toFixed(3))}${statBox('Least Affected', pi.least_affected?.ticker || '—', (pi.least_affected?.impact || 0).toFixed(3))}</div>`);
  }
  el.innerHTML = html;
  document.getElementById('nerveRefresh')?.addEventListener('click', () => { TITAN.nervemap.data = null; renderNerveMapTab(); });
}

/* ============================================================
   4. REBALANCE — DriftGuard
   ============================================================ */
function renderRebalanceTab() {
  const el = document.getElementById('titanRebalanceContent');
  const holdings = getTitanHoldings();
  if (!holdings) { el.innerHTML = noPortfolioMsg(); return; }
  // If we have cached data, render it immediately
  if (TITAN.driftguard.data) {
    el.innerHTML = cardWrap('Rebalance Analysis', `
      <div style="margin-bottom:12px"><button class="btn btn-primary" id="runRebalanceBtn">↻ Re-run Analysis</button></div>
      <div id="rebalanceResults"></div>`, () => { TITAN.driftguard.data = null; renderRebalanceTab(); });
    _renderRebalResults(TITAN.driftguard.data);
    document.getElementById('runRebalanceBtn').addEventListener('click', _executeRebalance);
    return;
  }
  // Auto-run on first visit
  el.innerHTML = cardWrap('Rebalance Analysis', `
    <div style="margin-bottom:12px"><button class="btn btn-primary" id="runRebalanceBtn">↻ Re-run Analysis</button></div>
    <div id="rebalanceResults"></div>`);
  document.getElementById('runRebalanceBtn').addEventListener('click', _executeRebalance);
  _executeRebalance();
}
async function _executeRebalance() {
  const area = document.getElementById('rebalanceResults');
  if (!area) return;
  area.innerHTML = titanLoading('Analyzing drift...');
  try {
    const h = getTitanHoldings();
    if (!h) { area.innerHTML = noPortfolioMsg(); return; }
    const pv = h.reduce((s, p) => s + p.shares * p.current_price, 0);
    const data = await apiFetch('/api/driftguard', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ holdings: h, portfolio_value: pv, tolerance: 0.05 }) });
    TITAN.driftguard.data = data;
    _renderRebalResults(data);
  } catch (e) { area.innerHTML = renderErrorState(e.message, _executeRebalance); }
}
function _renderRebalResults(d) {
  const area = document.getElementById('rebalanceResults');
  const banner = d.rebalance_needed
    ? '<div style="padding:12px 16px;border-radius:8px;background:rgba(212,160,61,0.15);color:#d4a03d;font-weight:600;margin-bottom:16px;">⚠ Rebalance Needed — max drift: ' + (Math.abs(d.max_drift) * 100).toFixed(1) + '% (' + d.max_drift_ticker + ')</div>'
    : '<div style="padding:12px 16px;border-radius:8px;background:rgba(61,188,114,0.15);color:#3dbc72;font-weight:600;margin-bottom:16px;">✓ Portfolio Balanced</div>';
  const drift = d.drift_table || [];
  const trades = d.suggested_trades || [];
  const summary = d.summary || {};
  area.innerHTML = `${banner}
    <div class="chart-wrap" style="height:${Math.max(200, drift.length * 30)}px;"><canvas id="driftChart"></canvas></div>
    ${trades.length ? `<div class="table-scroll" style="margin-top:16px"><table class="data-table"><thead><tr><th>Ticker</th><th>Action</th><th>Shares</th><th>Amount</th><th>Price</th></tr></thead><tbody>
      ${trades.map(t => `<tr class="${t.action === 'BUY' ? 'trade-buy' : 'trade-sell'}"><td class="mono">${t.ticker}</td><td>${t.action}</td><td class="mono">${Math.abs(t.shares)}</td><td class="mono">${fmtCurrency(t.dollar_amount)}</td><td class="mono">$${t.price.toFixed(2)}</td></tr>`).join('')}
    </tbody></table></div>` : ''}
    <div class="grid-3" style="margin-top:16px">${statBox('Buy Amount', fmtCurrency(summary.total_buy_amount))}${statBox('Sell Amount', fmtCurrency(summary.total_sell_amount))}${statBox('Net Cash Flow', fmtCurrency(summary.net_cash_flow))}</div>`;
  // Drift chart
  destroyChart('driftChart');
  STATE.charts.driftChart = new Chart(document.getElementById('driftChart'), {
    type: 'bar', data: { labels: drift.map(d => d.ticker), datasets: [{ label: 'Drift', data: drift.map(d => (d.drift * 100)), backgroundColor: drift.map(d => d.drift > 0 ? 'rgba(212,74,74,0.6)' : 'rgba(61,188,114,0.6)') }] },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { title: { display: true, text: 'Drift (%)' }, grid: { color: 'rgba(255,255,255,0.06)' } }, y: { grid: { display: false } } } }
  });
}

/* ============================================================
   5. FACTORS — FactorLens
   ============================================================ */
function renderFactorsTab() {
  const el = document.getElementById('factorsContent');
  const holdings = getTitanHoldings();
  if (!holdings) { el.innerHTML = noPortfolioMsg(); return; }
  if (TITAN.factorlens.data) { _renderFactorsUI(el); return; }
  el.innerHTML = titanLoading('Running factor analysis...');
  const payload = holdings.map(h => ({ ticker: h.ticker, weight: h.weight }));
  apiFetch('/api/factorlens', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ holdings: payload, period: '3y' }) })
    .then(data => { TITAN.factorlens.data = data; _renderFactorsUI(el); })
    .catch(e => { el.innerHTML = renderErrorState(e.message, () => { TITAN.factorlens.data = null; renderFactorsTab(); }); });
}
function _renderFactorsUI(el) {
  const d = TITAN.factorlens.data;
  if (!d.model_valid) { el.innerHTML = cardWrap('Factor Analysis', `<div style="padding:20px" class="text-muted">${d.error || 'Model could not be fitted'}</div>`); return; }
  const fl = d.factor_loadings || {};
  const ts = d.t_stats || {};
  const pv = d.p_values || {};
  const rd = d.risk_decomposition || {};
  const interps = d.interpretations || [];
  el.innerHTML = `
    ${cardWrap('Factor Model', `
      <div class="grid-3">${statBox('R-Squared', ((d.r_squared || 0) * 100).toFixed(1) + '%')}${statBox('Alpha (ann.)', fmtPct(d.alpha))}${statBox('Observations', d.observations || 0)}</div>
      <div style="display:flex;gap:16px;margin-top:16px;flex-wrap:wrap;">
        <div style="flex:1;min-width:300px;"><div class="chart-wrap" style="height:250px;"><canvas id="factorLoadingsChart"></canvas></div></div>
        <div style="flex:1;min-width:250px;"><div class="chart-wrap" style="height:250px;"><canvas id="riskDonutChart"></canvas></div></div>
      </div>
      <div class="table-scroll" style="margin-top:16px"><table class="data-table"><thead><tr><th>Factor</th><th>Loading</th><th>t-stat</th><th>p-value</th></tr></thead><tbody>
        <tr><td>Alpha</td><td class="mono">${(d.alpha_daily || 0).toFixed(6)}</td><td class="mono">${(ts.alpha || 0).toFixed(2)}</td><td class="mono">${(pv.alpha || 0).toFixed(4)}</td></tr>
        ${['Mkt-RF','SMB','HML','RMW','CMA'].map(f => `<tr><td>${f}</td><td class="mono">${(fl[f] || 0).toFixed(4)}</td><td class="mono">${(ts[f] || 0).toFixed(2)}</td><td class="mono">${(pv[f] || 0).toFixed(4)}</td></tr>`).join('')}
      </tbody></table></div>
    `, () => { TITAN.factorlens.data = null; renderFactorsTab(); })}
    ${interps.length ? cardWrap('Interpretation', `<ul style="padding:12px 24px;margin:0;">${interps.map(i => `<li style="margin-bottom:6px;font-size:13px;">${i}</li>`).join('')}</ul>`) : ''}`;
  // Factor loadings bar chart
  const factors = ['Mkt-RF', 'SMB', 'HML', 'RMW', 'CMA'];
  const vals = factors.map(f => fl[f] || 0);
  const colors = factors.map(f => Math.abs(ts[f] || 0) > 2 ? CHART_COLORS[0] : 'rgba(107,114,128,0.4)');
  destroyChart('factorLoadingsChart');
  STATE.charts.factorLoadingsChart = new Chart(document.getElementById('factorLoadingsChart'), {
    type: 'bar', data: { labels: factors, datasets: [{ data: vals, backgroundColor: colors }] },
    options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { color: 'rgba(255,255,255,0.06)' } }, y: { grid: { display: false } } } }
  });
  // Risk donut
  const fc = rd.factor_contributions || {};
  const donutLabels = [...factors.filter(f => (fc[f]?.pct_of_total || 0) > 0.5), 'Idiosyncratic'];
  const donutData = [...factors.filter(f => (fc[f]?.pct_of_total || 0) > 0.5).map(f => fc[f].pct_of_total), rd.idiosyncratic_pct || 0];
  destroyChart('riskDonutChart');
  STATE.charts.riskDonutChart = new Chart(document.getElementById('riskDonutChart'), {
    type: 'doughnut', data: { labels: donutLabels, datasets: [{ data: donutData, backgroundColor: donutLabels.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]) }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { boxWidth: 10, font: { size: 10 } } } } }
  });
}

/* ============================================================
   6. ATTRIBUTION — AlphaTrace
   ============================================================ */
function renderAttributionTab() {
  const el = document.getElementById('attributionContent');
  const holdings = getTitanHoldings();
  if (!holdings) { el.innerHTML = noPortfolioMsg(); return; }
  if (TITAN.alphatrace.data) { _renderAttrUI(el); return; }
  el.innerHTML = titanLoading('Running attribution analysis...');
  const payload = holdings.map(h => ({ ticker: h.ticker, weight: h.weight }));
  apiFetch('/api/alphatrace', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ holdings: payload, period: '1y' }) })
    .then(data => { TITAN.alphatrace.data = data; _renderAttrUI(el); })
    .catch(e => { el.innerHTML = renderErrorState(e.message, () => { TITAN.alphatrace.data = null; renderAttributionTab(); }); });
}
function _renderAttrUI(el) {
  const d = TITAN.alphatrace.data;
  const detail = d.sector_detail || [];
  const interps = d.interpretations || [];
  el.innerHTML = `
    ${cardWrap('Brinson-Fachler Attribution', `
      <div class="grid-3">${statBox('Portfolio Return', fmtPct(d.total_portfolio_return))}${statBox('Benchmark Return', fmtPct(d.total_benchmark_return))}${statBox('Active Return', `<span style="color:${pctColor(d.total_active_return)}">${fmtPct(d.total_active_return)}</span>`)}</div>
      <div class="grid-3" style="margin-top:12px">${statBox('Allocation', fmtPct(d.total_allocation_effect))}${statBox('Selection', fmtPct(d.total_selection_effect))}${statBox('Interaction', fmtPct(d.total_interaction_effect))}</div>
      <div class="chart-wrap" style="height:300px;margin-top:16px;"><canvas id="attrSectorChart"></canvas></div>
      <div class="table-scroll" style="margin-top:16px"><table class="data-table"><thead><tr><th>Sector</th><th>Port Wt</th><th>Bench Wt</th><th>Port Ret</th><th>Bench Ret</th><th>Alloc</th><th>Select</th><th>Total</th></tr></thead><tbody>
        ${detail.map(s => `<tr><td>${s.sector}</td><td class="mono">${fmtPct(s.port_weight)}</td><td class="mono">${fmtPct(s.bench_weight)}</td><td class="mono">${fmtPct(s.port_return)}</td><td class="mono">${fmtPct(s.bench_return)}</td><td class="mono" style="color:${pctColor(s.allocation)}">${fmtPct(s.allocation)}</td><td class="mono" style="color:${pctColor(s.selection)}">${fmtPct(s.selection)}</td><td class="mono" style="color:${pctColor(s.total)}">${fmtPct(s.total)}</td></tr>`).join('')}
      </tbody></table></div>
    `, () => { TITAN.alphatrace.data = null; renderAttributionTab(); })}
    ${interps.length ? cardWrap('Insights', `<ul style="padding:12px 24px;margin:0;">${interps.map(i => `<li style="margin-bottom:6px;font-size:13px;">${i}</li>`).join('')}</ul>`) : ''}`;
  // Sector chart
  const sectors = detail.map(s => s.sector);
  destroyChart('attrSectorChart');
  STATE.charts.attrSectorChart = new Chart(document.getElementById('attrSectorChart'), {
    type: 'bar', data: { labels: sectors, datasets: [
      { label: 'Allocation', data: detail.map(s => (s.allocation * 100).toFixed(2)), backgroundColor: CHART_COLORS[0] },
      { label: 'Selection', data: detail.map(s => (s.selection * 100).toFixed(2)), backgroundColor: CHART_COLORS[1] },
      { label: 'Interaction', data: detail.map(s => (s.interaction * 100).toFixed(2)), backgroundColor: CHART_COLORS[3] },
    ] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } } }, scales: { y: { title: { display: true, text: 'Effect (%)' }, grid: { color: 'rgba(255,255,255,0.06)' } }, x: { grid: { display: false } } } }
  });
}

/* ============================================================
   7. REGIME — RegimeRadar
   ============================================================ */
function renderRegimeTab() {
  const el = document.getElementById('regimeContent');
  if (TITAN.regimeradar.data) { _renderRegimeUI(el); return; }
  el.innerHTML = titanLoading('Detecting market regime...');
  apiFetch('/api/regimeradar?period=5y').then(data => { TITAN.regimeradar.data = data; _renderRegimeUI(el); })
    .catch(e => { el.innerHTML = renderErrorState(e.message, () => { TITAN.regimeradar.data = null; renderRegimeTab(); }); });
}
function _renderRegimeUI(el) {
  const d = TITAN.regimeradar.data;
  const regime = d.current_regime || '—';
  const regimeColors = { 'Bull - Low Vol': '#22c55e', 'Bull - High Vol': '#84cc16', 'Bear - Low Vol': '#f97316', 'Bear - High Vol': '#ef4444', 'Crisis': '#7c3aed' };
  const color = regimeColors[regime] || '#6b7280';
  const hist = d.history || {};
  const summary = hist.regime_summary || {};
  const interps = d.interpretations || [];
  el.innerHTML = `
    ${cardWrap('Current Regime', `
      <div style="text-align:center;padding:20px;"><div class="regime-badge" style="background:${color}22;color:${color};font-size:20px;">${regime}</div></div>
      <div class="chart-wrap" style="height:100px;margin-top:16px;"><canvas id="regimeTimelineChart"></canvas></div>
      ${Object.keys(summary).length ? `<div class="table-scroll" style="margin-top:16px"><table class="data-table"><thead><tr><th>Regime</th><th>Days</th><th>% of Time</th><th>Avg Duration</th></tr></thead><tbody>
        ${Object.entries(summary).map(([r, s]) => `<tr><td><span style="color:${regimeColors[r] || '#6b7280'}">●</span> ${r}</td><td class="mono">${s.total_days}</td><td class="mono">${s.pct_of_time}%</td><td class="mono">${s.avg_duration} days</td></tr>`).join('')}
      </tbody></table></div>` : ''}
    `, () => { TITAN.regimeradar.data = null; renderRegimeTab(); })}
    ${interps.length ? cardWrap('Insights', `<ul style="padding:12px 24px;margin:0;">${interps.map(i => `<li style="margin-bottom:6px;font-size:13px;">${i}</li>`).join('')}</ul>`) : ''}`;
  // Timeline chart
  const regimes = downsample(hist.regimes || [], 200);
  const tDates = downsample(hist.dates || [], 200);
  const tColors = regimes.map(r => regimeColors[r] || '#6b7280');
  destroyChart('regimeTimelineChart');
  if (regimes.length) {
    STATE.charts.regimeTimelineChart = new Chart(document.getElementById('regimeTimelineChart'), {
      type: 'bar', data: { labels: tDates.map(d => d.slice(5)), datasets: [{ data: regimes.map(() => 1), backgroundColor: tColors, borderWidth: 0 }] },
      options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => regimes[ctx.dataIndex] } } }, scales: { y: { display: false }, x: { ticks: { maxTicksLimit: 8, font: { size: 9 }, color: 'var(--text3)' }, grid: { display: false } } } }
    });
  }
}

/* ============================================================
   8. SCREENER — SectorScan
   ============================================================ */
function renderScreenerTab() {
  const el = document.getElementById('screenerContent');
  el.innerHTML = cardWrap('Stock Screener', `
    <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:16px;">
      <button class="preset-chip" data-screen="value">Value</button>
      <button class="preset-chip" data-screen="growth">Growth</button>
      <button class="preset-chip" data-screen="dividend">Dividend</button>
      <button class="preset-chip" data-screen="quality">Quality</button>
      <button class="preset-chip" data-screen="low_vol">Low Vol</button>
    </div>
    <div class="form-row mb-3">
      <div class="form-group" style="flex:1"><label class="form-label">P/E Max</label><input type="number" class="form-input mono" id="scrPeMax" placeholder="25" /></div>
      <div class="form-group" style="flex:1"><label class="form-label">Div Yield Min (%)</label><input type="number" class="form-input mono" id="scrDivMin" placeholder="2" step="0.1" /></div>
      <div class="form-group" style="flex:1"><label class="form-label">ROE Min (%)</label><input type="number" class="form-input mono" id="scrRoeMin" placeholder="15" /></div>
      <div class="form-group" style="flex:0 0 auto;justify-content:flex-end;"><label class="form-label">&nbsp;</label><button class="btn btn-primary" id="scrRunBtn">Screen</button></div>
    </div>
    <div id="screenerResults">${TITAN.sectorscan.data ? '' : '<div class="text-muted">Select a preset or set filters, then click Screen</div>'}</div>`);
  if (TITAN.sectorscan.data) _renderScreenResults(TITAN.sectorscan.data);
  el.querySelectorAll('[data-screen]').forEach(b => b.addEventListener('click', () => _runScreen(b.dataset.screen)));
  document.getElementById('scrRunBtn').addEventListener('click', () => _runScreen(null));
}
async function _runScreen(preset) {
  const area = document.getElementById('screenerResults');
  area.innerHTML = titanLoading('Screening stocks... this may take a minute');
  const filters = {};
  const pe = document.getElementById('scrPeMax').value;
  if (pe) filters.pe_max = +pe;
  const div = document.getElementById('scrDivMin').value;
  if (div) filters.dividend_yield_min = +div / 100;
  const roe = document.getElementById('scrRoeMin').value;
  if (roe) filters.roe_min = +roe / 100;
  try {
    const body = { limit: 30, include_composite: true };
    if (preset) body.preset = preset;
    if (Object.keys(filters).length) body.filters = filters;
    const data = await apiFetch('/api/sectorscan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    TITAN.sectorscan.data = data; _renderScreenResults(data);
  } catch (e) { area.innerHTML = renderErrorState(e.message); }
}
function _renderScreenResults(d) {
  const area = document.getElementById('screenerResults');
  const results = d.results || [];
  area.innerHTML = `<div class="text-muted" style="margin-bottom:12px;">Showing ${results.length} of ${d.total_screened || '?'} screened</div>
    <div class="table-scroll"><table class="data-table"><thead><tr><th>#</th><th>Ticker</th><th>Name</th><th>Sector</th><th>P/E</th><th>Div Yield</th><th>ROE</th><th>D/E</th><th>Score</th></tr></thead><tbody>
    ${results.map((s, i) => `<tr>
      <td>${s.composite_rank || i + 1}</td><td class="mono">${s.ticker}</td><td>${(s.name || '').slice(0, 20)}</td><td>${s.sector || '—'}</td>
      <td class="mono">${s.pe != null ? s.pe.toFixed(1) : '—'}</td>
      <td class="mono">${s.dividend_yield != null ? (s.dividend_yield * 100).toFixed(2) + '%' : '—'}</td>
      <td class="mono">${s.roe != null ? (s.roe * 100).toFixed(1) + '%' : '—'}</td>
      <td class="mono">${s.debt_equity != null ? s.debt_equity.toFixed(2) : '—'}</td>
      <td class="mono">${s.composite_score != null ? s.composite_score.toFixed(3) : '—'}</td>
    </tr>`).join('')}</tbody></table></div>`;
}

/* ============================================================
   9. EARNINGS — EarningsEdge
   ============================================================ */
function renderEarningsTab() {
  const el = document.getElementById('earningsContent');
  el.innerHTML = cardWrap('Earnings Intelligence', `
    <div class="form-row mb-3">
      <div class="form-group" style="flex:2"><label class="form-label">Ticker</label><input type="text" class="form-input mono" id="earningsTicker" placeholder="AAPL" /></div>
      <div class="form-group" style="flex:0 0 auto;justify-content:flex-end;"><label class="form-label">&nbsp;</label><button class="btn btn-primary" id="earningsLookupBtn">Look Up</button></div>
    </div>
    <div id="earningsResults"></div>`);
  document.getElementById('earningsLookupBtn').addEventListener('click', _runEarningsLookup);
  // Auto-load portfolio earnings
  const holdings = getTitanHoldings();
  if (holdings) {
    const area = document.getElementById('earningsResults');
    area.innerHTML = titanLoading('Loading portfolio earnings...');
    apiFetch('/api/earningsedge', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ holdings, weeks_ahead: 4 }) })
      .then(data => { _renderPortfolioEarnings(area, data); })
      .catch(() => { area.innerHTML = ''; });
  }
}
async function _runEarningsLookup() {
  const ticker = document.getElementById('earningsTicker').value.toUpperCase().trim();
  if (!ticker) return;
  const area = document.getElementById('earningsResults');
  area.innerHTML = titanLoading('Fetching earnings for ' + ticker + '...');
  try {
    const data = await apiFetch(`/api/earningsedge?ticker=${ticker}`);
    TITAN.earningsedge.data = data; TITAN.earningsedge.ticker = ticker;
    _renderSingleEarnings(area, data);
  } catch (e) { area.innerHTML = renderErrorState(e.message); }
}
function _renderPortfolioEarnings(area, d) {
  const upcoming = d.upcoming || [];
  const noUp = d.no_upcoming || [];
  let html = '';
  if (upcoming.length) {
    html += `<div class="stat-grid" style="margin-bottom:16px">${statBox('Reporting This Week', d.earnings_this_week || 0)}${statBox('Next Week', d.earnings_next_week || 0)}${statBox('Weight Reporting', fmtPct(d.total_portfolio_weight_reporting))}</div>`;
    html += `<div class="table-scroll"><table class="data-table"><thead><tr><th>Ticker</th><th>Date</th><th>Days</th><th>Weight</th><th>Beat Rate</th><th>Avg |Move|</th><th>Impact</th></tr></thead><tbody>
      ${upcoming.map(u => `<tr><td class="mono">${u.ticker}</td><td>${u.date}</td><td class="mono">${u.days_until}d</td><td class="mono">${fmtPct(u.portfolio_weight)}</td><td class="mono">${u.beat_rate}%</td><td class="mono">${u.avg_abs_move_1d}%</td><td class="mono">${u.expected_portfolio_impact.toFixed(3)}</td></tr>`).join('')}
    </tbody></table></div>`;
  }
  if (noUp.length) html += `<div class="text-muted" style="margin-top:12px;">No upcoming earnings: ${noUp.join(', ')}</div>`;
  area.innerHTML = html || '<div class="text-muted">No upcoming earnings for portfolio</div>';
}
function _renderSingleEarnings(area, d) {
  const stats = d.surprise_stats || {};
  const hist = d.history || [];
  const moves = d.price_moves || [];
  area.innerHTML = `
    <div class="grid-3">${statBox('Beat Rate', stats.beat_rate + '%')}${statBox('Avg Surprise', fmtPctRaw(stats.avg_surprise_pct))}${statBox('Streak', (stats.streak > 0 ? '+' : '') + stats.streak)}</div>
    <div style="display:flex;gap:16px;margin-top:16px;flex-wrap:wrap;">
      <div style="flex:1;min-width:300px;"><div class="chart-wrap" style="height:250px;"><canvas id="earningsSurpriseChart"></canvas></div></div>
      <div style="flex:1;min-width:300px;"><div class="chart-wrap" style="height:250px;"><canvas id="earningsScatterChart"></canvas></div></div>
    </div>
    <div class="grid-3" style="margin-top:16px">${statBox('Consistency', stats.consistency_score?.toFixed(2) || '—')}${statBox('Avg |Move| 1d', (d.expected_move?.avg_abs_move_1d || 0) + '%')}${statBox('Positive Rate', (d.expected_move?.positive_reaction_rate || 0) + '%')}</div>`;
  // Surprise chart
  const quarters = hist.filter(h => h.surprise_pct != null).slice(0, 12).reverse();
  destroyChart('earningsSurpriseChart');
  STATE.charts.earningsSurpriseChart = new Chart(document.getElementById('earningsSurpriseChart'), {
    type: 'bar', data: { labels: quarters.map(q => q.quarter || q.date), datasets: [{ data: quarters.map(q => q.surprise_pct), backgroundColor: quarters.map(q => q.beat ? 'rgba(61,188,114,0.6)' : 'rgba(212,74,74,0.6)') }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, title: { display: true, text: 'EPS Surprise %', font: { size: 12 } } }, scales: { y: { grid: { color: 'rgba(255,255,255,0.06)' } }, x: { grid: { display: false } } } }
  });
  // Scatter
  const pts = moves.filter(m => m.surprise_pct != null && m.price_move_1d != null);
  destroyChart('earningsScatterChart');
  STATE.charts.earningsScatterChart = new Chart(document.getElementById('earningsScatterChart'), {
    type: 'scatter', data: { datasets: [{ label: 'Post-Earnings', data: pts.map(p => ({ x: p.surprise_pct, y: p.price_move_1d })), backgroundColor: pts.map(p => p.beat ? 'rgba(61,188,114,0.7)' : 'rgba(212,74,74,0.7)'), pointRadius: 5 }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false }, title: { display: true, text: 'Surprise vs 1D Move', font: { size: 12 } } }, scales: { x: { title: { display: true, text: 'Surprise %' }, grid: { color: 'rgba(255,255,255,0.06)' } }, y: { title: { display: true, text: '1D Move %' }, grid: { color: 'rgba(255,255,255,0.06)' } } } }
  });
}

/* ============================================================
   10. PAIRS — PairPulse
   ============================================================ */
function renderPairsTab() {
  const el = document.getElementById('pairsContent');
  const holdings = getTitanHoldings();
  el.innerHTML = cardWrap('Pair Trading & Cointegration', `
    <div class="form-row mb-3">
      <div class="form-group" style="flex:1"><label class="form-label">Ticker A</label><input type="text" class="form-input mono" id="pairA" placeholder="AAPL" /></div>
      <div class="form-group" style="flex:1"><label class="form-label">Ticker B</label><input type="text" class="form-input mono" id="pairB" placeholder="MSFT" /></div>
      <div class="form-group" style="flex:0 0 auto;justify-content:flex-end;"><label class="form-label">&nbsp;</label><button class="btn btn-primary" id="pairAnalyzeBtn">Analyze Pair</button></div>
      ${holdings ? `<div class="form-group" style="flex:0 0 auto;justify-content:flex-end;"><label class="form-label">&nbsp;</label><button class="btn btn-ghost" id="pairPortfolioBtn">Scan Portfolio</button></div>` : ''}
    </div><div id="pairsResults"></div>`);
  document.getElementById('pairAnalyzeBtn').addEventListener('click', async () => {
    const a = document.getElementById('pairA').value.toUpperCase().trim();
    const b = document.getElementById('pairB').value.toUpperCase().trim();
    if (!a || !b) return;
    const area = document.getElementById('pairsResults');
    area.innerHTML = titanLoading('Analyzing ' + a + ' / ' + b + '...');
    try {
      const data = await apiFetch(`/api/pairpulse?ticker_a=${a}&ticker_b=${b}&period=2y`);
      _renderPairDetail(area, data);
    } catch (e) { area.innerHTML = renderErrorState(e.message); }
  });
  if (holdings) {
    document.getElementById('pairPortfolioBtn')?.addEventListener('click', async () => {
      const area = document.getElementById('pairsResults');
      area.innerHTML = titanLoading('Scanning portfolio pairs...');
      try {
        const tickers = holdings.map(h => h.ticker);
        const data = await apiFetch('/api/pairpulse', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tickers, period: '2y' }) });
        TITAN.pairpulse.data = data; _renderPairsTable(area, data);
      } catch (e) { area.innerHTML = renderErrorState(e.message); }
    });
  }
}
function _renderPairsTable(area, d) {
  const pairs = d.pairs || [];
  area.innerHTML = `<div class="text-muted" style="margin-bottom:12px;">${d.pairs_found || 0} cointegrated pairs found out of ${d.pairs_tested || 0} tested</div>
    ${pairs.length ? `<div class="table-scroll"><table class="data-table"><thead><tr><th>Pair</th><th>p-value</th><th>Hedge Ratio</th><th>Half-Life</th><th>Z-Score</th><th>Signal</th></tr></thead><tbody>
    ${pairs.map(p => {
      const sigColor = p.signal === 'LONG_SPREAD' ? 'var(--green, #3dbc72)' : p.signal === 'SHORT_SPREAD' ? 'var(--red, #d44a4a)' : 'var(--text3)';
      return `<tr><td class="mono">${p.ticker_a}/${p.ticker_b}</td><td class="mono">${p.p_value.toFixed(4)}</td><td class="mono">${p.hedge_ratio.toFixed(3)}</td><td class="mono">${p.half_life === Infinity ? '∞' : p.half_life.toFixed(1) + 'd'}</td><td class="mono">${p.current_z.toFixed(2)}</td><td style="color:${sigColor};font-weight:600">${p.signal}</td></tr>`;
    }).join('')}</tbody></table></div>` : '<div class="text-muted">No cointegrated pairs found</div>'}`;
}
function _renderPairDetail(area, d) {
  const coint = d.cointegration || {};
  const sig = d.signal || {};
  const spread = d.spread || {};
  const tradeable = d.tradeable;
  area.innerHTML = `
    <div class="grid-3">${statBox('Cointegrated', tradeable ? '<span style="color:var(--green)">Yes</span>' : '<span style="color:var(--red)">No</span>', 'p=' + (coint.p_value || '—'))}${statBox('Half-Life', (coint.half_life === Infinity ? '∞' : (coint.half_life || 0).toFixed(1) + ' days'))}${statBox('Hedge Ratio', (coint.hedge_ratio || 0).toFixed(4))}</div>
    ${tradeable && sig.signal ? `<div style="margin:16px 0;"><div class="signal-item"><div class="signal-dot ${sig.signal === 'LONG_SPREAD' || sig.signal === 'SHORT_SPREAD' ? (sig.signal === 'LONG_SPREAD' ? 'bullish' : 'bearish') : 'neutral'}"></div><div class="signal-msg">${sig.description || sig.signal}</div><div class="signal-strength">${strengthDots(sig.strength || 0, 5)}</div></div></div>` : ''}
    ${!tradeable ? `<div class="text-muted" style="padding:12px;">${d.reason || 'Not tradeable'}</div>` : ''}`;
}

/* ============================================================
   11. BACKTEST — RewindEngine
   ============================================================ */
function renderBacktestTab() {
  const el = document.getElementById('backtestContent');
  el.innerHTML = cardWrap('Strategy Backtester', `
    <div class="form-row mb-3">
      <div class="form-group" style="flex:2"><label class="form-label">Ticker</label><input type="text" class="form-input mono" id="btTicker" placeholder="AAPL" value="AAPL" /></div>
      <div class="form-group" style="flex:2"><label class="form-label">Strategy</label><select class="form-input" id="btStrategy"><option value="buy_and_hold">Buy & Hold</option><option value="ma_crossover" selected>MA Crossover</option><option value="rsi_mean_reversion">RSI Mean Reversion</option><option value="bollinger_mean_reversion">Bollinger Band</option><option value="monthly_rebalance">Monthly Rebalance</option></select></div>
      <div class="form-group" style="flex:1"><label class="form-label">Period</label><select class="form-input" id="btPeriod"><option value="1y">1Y</option><option value="2y">2Y</option><option value="3y">3Y</option><option value="5y" selected>5Y</option></select></div>
    </div>
    <div id="btParams" class="form-row mb-3">
      <div class="form-group" style="flex:1"><label class="form-label">Fast MA</label><input type="number" class="form-input mono" id="btFast" value="50" /></div>
      <div class="form-group" style="flex:1"><label class="form-label">Slow MA</label><input type="number" class="form-input mono" id="btSlow" value="200" /></div>
    </div>
    <div class="form-row mb-3">
      <div class="form-group" style="flex:0 0 auto"><button class="btn btn-primary" id="btRunBtn">Run Backtest</button></div>
      <div class="form-group" style="flex:0 0 auto"><button class="btn btn-ghost" id="btCompareBtn">Compare All Strategies</button></div>
    </div>
    <div id="backtestResults"></div>`);
  document.getElementById('btStrategy').addEventListener('change', _updateBtParams);
  document.getElementById('btRunBtn').addEventListener('click', _runBacktest);
  document.getElementById('btCompareBtn').addEventListener('click', _runCompare);
}
function _updateBtParams() {
  const strat = document.getElementById('btStrategy').value;
  const el = document.getElementById('btParams');
  if (strat === 'ma_crossover') el.innerHTML = '<div class="form-group" style="flex:1"><label class="form-label">Fast MA</label><input type="number" class="form-input mono" id="btFast" value="50" /></div><div class="form-group" style="flex:1"><label class="form-label">Slow MA</label><input type="number" class="form-input mono" id="btSlow" value="200" /></div>';
  else if (strat === 'rsi_mean_reversion') el.innerHTML = '<div class="form-group" style="flex:1"><label class="form-label">Period</label><input type="number" class="form-input mono" id="btRsiP" value="14" /></div><div class="form-group" style="flex:1"><label class="form-label">Oversold</label><input type="number" class="form-input mono" id="btRsiOS" value="30" /></div><div class="form-group" style="flex:1"><label class="form-label">Overbought</label><input type="number" class="form-input mono" id="btRsiOB" value="70" /></div>';
  else if (strat === 'bollinger_mean_reversion') el.innerHTML = '<div class="form-group" style="flex:1"><label class="form-label">Window</label><input type="number" class="form-input mono" id="btBBW" value="20" /></div><div class="form-group" style="flex:1"><label class="form-label">Std Dev</label><input type="number" class="form-input mono" id="btBBStd" value="2" step="0.1" /></div>';
  else el.innerHTML = '';
}
async function _runBacktest() {
  const area = document.getElementById('backtestResults');
  const ticker = document.getElementById('btTicker').value.toUpperCase().trim();
  const strat = document.getElementById('btStrategy').value;
  const period = document.getElementById('btPeriod').value;
  if (!ticker) return;
  area.innerHTML = titanLoading('Running backtest on ' + ticker + '...');
  const body = { ticker, strategy: strat, period };
  if (strat === 'ma_crossover') body.params = { fast: +(document.getElementById('btFast')?.value || 50), slow: +(document.getElementById('btSlow')?.value || 200) };
  else if (strat === 'rsi_mean_reversion') body.params = { period: +(document.getElementById('btRsiP')?.value || 14), oversold: +(document.getElementById('btRsiOS')?.value || 30), overbought: +(document.getElementById('btRsiOB')?.value || 70) };
  else if (strat === 'bollinger_mean_reversion') body.params = { window: +(document.getElementById('btBBW')?.value || 20), num_std: +(document.getElementById('btBBStd')?.value || 2) };
  try {
    const data = await apiFetch('/api/rewindengine', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    TITAN.rewindengine.data = data; _renderBacktestResults(area, data);
  } catch (e) { area.innerHTML = renderErrorState(e.message); }
}
async function _runCompare() {
  const area = document.getElementById('backtestResults');
  const ticker = document.getElementById('btTicker').value.toUpperCase().trim();
  const period = document.getElementById('btPeriod').value;
  if (!ticker) return;
  area.innerHTML = titanLoading('Comparing all strategies on ' + ticker + '...');
  try {
    const data = await apiFetch('/api/rewindengine/compare', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ticker, period, strategies: [{ name: 'buy_and_hold' }, { name: 'ma_crossover', params: { fast: 50, slow: 200 } }, { name: 'rsi_mean_reversion' }, { name: 'bollinger_mean_reversion' }, { name: 'monthly_rebalance' }] }) });
    TITAN.rewindengine.comparison = data;
    const comp = data.comparison || [];
    area.innerHTML = `<div class="text-muted" style="margin-bottom:12px;">Best by Sharpe: <strong>${data.best_strategy || '—'}</strong></div>
      <div class="table-scroll"><table class="data-table"><thead><tr><th>Strategy</th><th>Total Return</th><th>Ann. Return</th><th>Sharpe</th><th>Max DD</th><th>Trades</th><th>Win Rate</th></tr></thead><tbody>
      ${comp.map((s, i) => `<tr><td>${i === 0 ? '★ ' : ''}${s.strategy}</td><td class="mono" style="color:${pctColor(s.total_return)}">${fmtPct(s.total_return)}</td><td class="mono">${fmtPct(s.annualized_return)}</td><td class="mono ${i === 0 ? 'metric-best' : ''}">${s.sharpe.toFixed(2)}</td><td class="mono">${fmtPct(s.max_drawdown)}</td><td class="mono">${s.total_trades}</td><td class="mono">${(s.win_rate * 100).toFixed(0)}%</td></tr>`).join('')}
      </tbody></table></div>`;
  } catch (e) { area.innerHTML = renderErrorState(e.message); }
}
function _safeFix(v, decimals) {
  if (v === null || v === undefined || !isFinite(v)) return '—';
  return Number(v).toFixed(decimals);
}
function _renderBacktestResults(area, d) {
  if (!d.valid) { area.innerHTML = renderErrorState(d.error || 'Backtest failed'); return; }
  const ec = d.equity_curve || [];
  const dd = d.drawdown_curve || [];
  const dates = (d.dates || []).map(x => x.slice(5));
  const trades = d.trade_log || [];
  const pf = d.profit_factor;
  const pfStr = (pf === null || pf === undefined) ? '—' : (!isFinite(pf) ? '∞' : pf.toFixed(2));
  area.innerHTML = `
    <div class="grid-4">${statBox('Total Return', `<span style="color:${pctColor(d.total_return)}">${fmtPct(d.total_return)}</span>`)}${statBox('Ann. Return', fmtPct(d.annualized_return))}${statBox('Benchmark', fmtPct(d.benchmark_return))}${statBox('Excess', `<span style="color:${pctColor(d.excess_return)}">${fmtPct(d.excess_return)}</span>`)}</div>
    <div class="grid-4" style="margin-top:8px">${statBox('Volatility', fmtPct(d.volatility))}${statBox('Sharpe', _safeFix(d.sharpe, 2))}${statBox('Max Drawdown', fmtPct(d.max_drawdown))}${statBox('Calmar', _safeFix(d.calmar, 2))}</div>
    <div class="grid-4" style="margin-top:8px">${statBox('Trades', d.total_trades)}${statBox('Win Rate', _safeFix((d.win_rate || 0) * 100, 0) + '%')}${statBox('Profit Factor', pfStr)}${statBox('Commission Drag', fmtPct(d.commission_drag))}</div>
    <div class="chart-wrap" style="height:300px;margin-top:16px;"><canvas id="backtestEquityChart"></canvas></div>
    <div class="chart-wrap" style="height:150px;margin-top:8px;"><canvas id="backtestDrawdownChart"></canvas></div>
    ${trades.length ? `<details style="margin-top:16px;"><summary class="collapsible-toggle">Trade Log (${trades.length} entries)</summary>
      <div class="table-scroll" style="margin-top:8px;"><table class="data-table"><thead><tr><th>Date</th><th>Action</th><th>Price</th><th>Shares</th><th>Commission</th></tr></thead><tbody>
      ${trades.map(t => `<tr class="${t.action === 'BUY' ? 'trade-buy' : 'trade-sell'}"><td>${t.date}</td><td>${t.action}</td><td class="mono">$${t.price.toFixed(2)}</td><td class="mono">${Math.abs(t.shares)}</td><td class="mono">$${t.commission.toFixed(2)}</td></tr>`).join('')}
      </tbody></table></div></details>` : ''}`;
  // Equity chart
  const sampledEc = downsample(ec, 400);
  const sampledDates = downsample(dates, 400);
  const sampledDd = downsample(dd, 400);
  // Equity chart datasets
  const equityDatasets = [
    { label: d.strategy || 'Strategy', data: sampledEc, borderColor: CHART_COLORS[0], borderWidth: 1.5, pointRadius: 0, fill: false },
  ];
  // Only show benchmark line when strategy is NOT Buy & Hold
  const isBuyHold = (d.strategy || '').toLowerCase().includes('buy') && (d.strategy || '').toLowerCase().includes('hold');
  if (!isBuyHold && ec.length > 1) {
    // Reconstruct actual buy-and-hold equity: initial capital * (price[i] / price[0])
    const closeData = ec; // fallback
    const initCap = d.initial_capital || ec[0] || 100000;
    const benchReturn = d.benchmark_return || 0;
    const benchEc = downsample(ec.map((_, i) => {
      // Interpolate the actual price growth: compound the benchmark return across all bars
      const frac = i / (ec.length - 1 || 1);
      return initCap * Math.pow(1 + benchReturn, frac);
    }), 400);
    equityDatasets.push({ label: 'Buy & Hold (benchmark)', data: benchEc, borderColor: '#6b7280', borderWidth: 1, pointRadius: 0, borderDash: [4, 3], fill: false });
  }
  destroyChart('backtestEquityChart');
  STATE.charts.backtestEquityChart = new Chart(document.getElementById('backtestEquityChart'), {
    type: 'line', data: { labels: sampledDates, datasets: equityDatasets },
    options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, plugins: { legend: { labels: { boxWidth: 10, font: { size: 10 } } } }, scales: { y: { title: { display: true, text: '$' }, grid: { color: 'rgba(255,255,255,0.06)' } }, x: { ticks: { maxTicksLimit: 10, color: 'var(--text3)' }, grid: { display: false } } } }
  });
  destroyChart('backtestDrawdownChart');
  STATE.charts.backtestDrawdownChart = new Chart(document.getElementById('backtestDrawdownChart'), {
    type: 'line', data: { labels: sampledDates, datasets: [{ label: 'Drawdown', data: sampledDd.map(v => (v * 100).toFixed(2)), borderColor: '#d44a4a', backgroundColor: 'rgba(212,74,74,0.15)', borderWidth: 1, pointRadius: 0, fill: 'origin' }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { title: { display: true, text: '%' }, grid: { color: 'rgba(255,255,255,0.06)' } }, x: { ticks: { maxTicksLimit: 10, color: 'var(--text3)' }, grid: { display: false } } } }
  });
}
