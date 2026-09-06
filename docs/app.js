/* Buffett Dashboard - client rendering.
   The payload is produced nightly by scripts/build.py. Everything here is
   presentation, with one exception: the discounted cash flow is recomputed in
   the browser so the assumption sliders respond instantly. That JavaScript
   implementation deliberately mirrors metrics.discounted_owner_earnings. */

const state = { data: null, tab: 'signals', sort: { key: 'score', dir: -1 }, drawer: null };

/* ----------------------------------------------------------- formatting */

const nf = (n, d = 0) => n === null || n === undefined || Number.isNaN(n)
  ? '--' : n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });

function money(n, d = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return '--';
  return '$' + nf(n, d);
}

function compact(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return '--';
  const abs = Math.abs(n);
  if (abs >= 1e12) return '$' + (n / 1e12).toFixed(2) + 'T';
  if (abs >= 1e9) return '$' + (n / 1e9).toFixed(1) + 'B';
  if (abs >= 1e6) return '$' + (n / 1e6).toFixed(1) + 'M';
  return '$' + nf(n, 0);
}

function pct(n, d = 1) {
  if (n === null || n === undefined || Number.isNaN(n)) return '--';
  return n.toFixed(d) + '%';
}

function signed(n, d = 1) {
  if (n === null || n === undefined || Number.isNaN(n)) return '--';
  return (n > 0 ? '+' : '') + n.toFixed(d) + '%';
}

const cls = n => (n === null || n === undefined) ? '' : (n > 0 ? 'pos' : n < 0 ? 'neg' : '');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function bandPill(band) {
  if (!band) return '<span class="pill pill-rich">no valuation</span>';
  const map = {
    'Below margin of safety': 'pill-buy',
    'Near fair value': 'pill-fair',
    'Above estimated value': 'pill-rich',
  };
  return `<span class="pill ${map[band] || 'pill-rich'}">${esc(band)}</span>`;
}

function timeAgo(iso) {
  if (!iso) return 'unknown';
  const hours = (Date.now() - new Date(iso).getTime()) / 36e5;
  if (hours < 1) return 'just now';
  if (hours < 24) return `${Math.round(hours)}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

/* ---------------------------------------------------------------- charts */

function lineChart(series, { format = 'compact', height = 62 } = {}) {
  const years = Object.keys(series).sort();
  if (years.length < 2) return '<div class="range">Not enough history</div>';
  const values = years.map(y => series[y]);
  const min = Math.min(...values, 0);
  const max = Math.max(...values);
  const span = (max - min) || 1;
  const W = 240, H = height, pad = 3;
  const x = i => (i / (years.length - 1)) * (W - pad * 2) + pad;
  const y = v => H - pad - ((v - min) / span) * (H - pad * 2);

  const path = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const area = `${path} L${x(values.length - 1).toFixed(1)},${H - pad} L${x(0).toFixed(1)},${H - pad} Z`;
  const zeroLine = min < 0
    ? `<line x1="${pad}" y1="${y(0).toFixed(1)}" x2="${W - pad}" y2="${y(0).toFixed(1)}"
             stroke="var(--rule-2)" stroke-width="1" stroke-dasharray="2 2"/>` : '';

  const fmt = format === 'pct' ? v => pct(v * 100) : compact;
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img"
     aria-label="${esc(years[0])} ${esc(fmt(values[0]))} to ${esc(years.at(-1))} ${esc(fmt(values.at(-1)))}">
    <path d="${area}" fill="var(--accent-sub)"/>
    ${zeroLine}
    <path d="${path}" fill="none" stroke="var(--accent)" stroke-width="1.8"
          stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${x(values.length - 1).toFixed(1)}" cy="${y(values.at(-1)).toFixed(1)}" r="2.6" fill="var(--accent)"/>
  </svg>`;
}

function chartCard(title, series, format) {
  const years = Object.keys(series || {}).sort();
  if (!years.length) return '';
  const first = series[years[0]], last = series[years.at(-1)];
  const fmt = format === 'pct' ? v => pct(v * 100) : compact;
  return `<div class="chart">
    <div class="title">${esc(title)}</div>
    <div class="range">${years[0]} ${esc(fmt(first))} &rarr; ${years.at(-1)} ${esc(fmt(last))}</div>
    ${lineChart(series, { format })}
  </div>`;
}

/* ------------------------------------------------------------------ DCF */

/* Mirror of metrics.discounted_owner_earnings: ten explicit years, then a
   Gordon terminal value, with net cash added back. */
function dcf({ base, shares, g1, g2, discount, terminal, netCash }) {
  if (!base || base <= 0 || !shares || shares <= 0 || discount <= terminal) return null;
  let flow = base, pv = 0;
  for (let year = 1; year <= 10; year++) {
    flow *= 1 + (year <= 5 ? g1 : g2);
    pv += flow / Math.pow(1 + discount, year);
  }
  const terminalValue = (flow * (1 + terminal)) / (discount - terminal);
  const terminalPv = terminalValue / Math.pow(1 + discount, 10);
  const equity = pv + terminalPv + (netCash || 0);
  return {
    perShare: equity / shares,
    terminalShare: equity ? terminalPv / equity : 0,
  };
}

/* ------------------------------------------------------------- rendering */

function renderWeather() {
  const w = state.data.weather || {};
  const tiles = [];

  if (w.buffett_indicator) {
    const v = w.buffett_indicator.value;
    const tone = v > 150 ? 'neg' : v < 100 ? 'pos' : 'warn';
    tiles.push(`<div class="stat">
      <div class="stat-label">Buffett Indicator</div>
      <div class="stat-value">${pct(v, 0)}</div>
      <div class="stat-note ${tone}">of GDP &middot; ${esc(w.buffett_indicator.as_of)}</div>
    </div>`);
  }
  if (w.treasury_10y) {
    const t = w.treasury_10y;
    const delta = t.value - t.prior_year;
    tiles.push(`<div class="stat">
      <div class="stat-label">10-Year Treasury</div>
      <div class="stat-value">${pct(t.value, 2)}</div>
      <div class="stat-note ${cls(delta)}">${signed(delta, 2)} vs a year ago</div>
    </div>`);
  }
  if (w.sp500) {
    tiles.push(`<div class="stat">
      <div class="stat-label">S&amp;P 500</div>
      <div class="stat-value">${nf(w.sp500.price, 0)}</div>
      <div class="stat-note ${cls(w.sp500.change_pct)}">${signed(w.sp500.change_pct)} &middot; ${signed(w.sp500.from_high_pct)} from high</div>
    </div>`);
  }
  if (w.vix) {
    const v = w.vix.price;
    tiles.push(`<div class="stat">
      <div class="stat-label">VIX</div>
      <div class="stat-value">${nf(v, 1)}</div>
      <div class="stat-note ${v > 25 ? 'neg' : v < 15 ? 'warn' : ''}">${v > 25 ? 'elevated fear' : v < 15 ? 'complacent' : 'ordinary'}</div>
    </div>`);
  }

  const cheap = state.data.companies.filter(
    c => (c.valuation || {}).band === 'Below margin of safety').length;
  tiles.push(`<div class="stat">
    <div class="stat-label">Below margin of safety</div>
    <div class="stat-value">${cheap}</div>
    <div class="stat-note">of ${state.data.companies.length} tracked</div>
  </div>`);

  document.getElementById('weather').innerHTML = tiles.join('');
  document.getElementById('regime').innerHTML = regimeNote(w);
}

/* A description of the current regime, stated as fact. It does not tell the
   reader what to do; it says what the numbers are and what they have
   historically implied. */
function regimeNote(w) {
  const parts = [];
  if (w.buffett_indicator) {
    const v = w.buffett_indicator.value;
    parts.push(v > 150
      ? `Total US equity value sits at <b>${pct(v, 0)} of GDP</b>, far above the long-run average. Buffett has described readings near these levels as playing with fire.`
      : v < 100
      ? `Total US equity value is <b>${pct(v, 0)} of GDP</b>, historically the range where broad returns have been most generous.`
      : `Total US equity value is <b>${pct(v, 0)} of GDP</b>, around its long-run average.`);
  }
  if (w.treasury_10y) {
    parts.push(`The 10-year Treasury pays <b>${pct(w.treasury_10y.value, 2)}</b>, which is the hurdle every equity must clear; a business earning less than that on your purchase price is worse than a bond.`);
  }
  return parts.join(' ');
}

function renderSignals() {
  const signals = state.data.signals || [];
  const el = document.getElementById('tab-signals');
  if (!signals.length) {
    el.innerHTML = `<div class="card"><div class="empty">
      <div class="big">Nothing moved today</div>
      <div>No price shocks, valuation crossings or new filings since the last run.
      A quiet day is the normal state of a portfolio you intend to hold.</div>
    </div></div>`;
    return;
  }
  el.innerHTML = `<h2 class="section">What changed in the last 24 hours</h2>
    <p class="lede">Compared against the previous run${state.data.previous_generated_at
      ? ' from ' + timeAgo(state.data.previous_generated_at) : ''}.</p>
    <div class="card">${signals.map(s => `
      <div class="signal">
        <span class="sig-tag sev-${esc(s.severity)}">${esc(s.severity)}</span>
        <div>
          <div class="sig-head">${esc(s.headline)}</div>
          <div class="sig-detail">${esc(s.detail)}
            ${s.url ? ` <a href="${esc(s.url)}" target="_blank" rel="noopener">source</a>` : ''}</div>
        </div>
      </div>`).join('')}</div>`;
}

const COLUMNS = [
  { key: 'ticker', label: 'Company', num: false },
  { key: 'price', label: 'Price', num: true },
  { key: 'change', label: '1d', num: true },
  { key: 'ret', label: 'Return', num: true },
  { key: 'margin', label: 'Gross margin', num: true },
  { key: 'growth', label: 'OE growth', num: true },
  { key: 'yield', label: 'OE yield', num: true },
  { key: 'value', label: 'Est. value', num: true },
  { key: 'gap', label: 'vs price', num: true },
  { key: 'band', label: 'Verdict', num: false },
  { key: 'score', label: 'Quality', num: true },
];

function rowValues(c) {
  const v = c.valuation || {}, q = c.quality || {}, p = c.price || {};
  const growth = (q.components || []).find(x => x.key === 'earnings_growth');
  return {
    ticker: c.ticker,
    price: p.price ?? null,
    change: p.change_pct ?? null,
    ret: (c.latest || {}).return_pct ?? null,
    retBasis: (c.latest || {}).return_basis || 'ROE',
    margin: (c.latest || {}).gross_margin_pct ?? null,
    growth: growth ? growth.value : null,
    yield: v.owner_earnings_yield_pct ?? null,
    value: v.base_value ?? null,
    gap: v.discount_to_value_pct ?? null,
    band: v.band ?? null,
    score: q.score ?? null,
  };
}

function renderCompanies() {
  const rows = state.data.companies.map(c => ({ c, v: rowValues(c) }));
  const { key, dir } = state.sort;
  rows.sort((a, b) => {
    const x = a.v[key], y = b.v[key];
    if (x === null || x === undefined) return 1;
    if (y === null || y === undefined) return -1;
    return typeof x === 'string' ? x.localeCompare(y) * dir : (x - y) * dir;
  });

  const head = COLUMNS.map(col => `
    <th class="sortable ${col.num ? 'num' : ''}" data-key="${col.key}">
      ${esc(col.label)}${key === col.key ? ` <span class="arrow">${dir === 1 ? '▲' : '▼'}</span>` : ''}
    </th>`).join('');

  const body = rows.map(({ c, v }) => `
    <tr class="clickable" data-ticker="${esc(c.ticker)}">
      <td><span class="ticker">${esc(c.ticker)}</span><br><span class="co-name">${esc(c.name)}</span></td>
      <td class="num">${money(v.price)}</td>
      <td class="num ${cls(v.change)}">${signed(v.change)}</td>
      <td class="num">${pct(v.ret)}<br><span class="co-name">${esc(v.retBasis)}</span></td>
      <td class="num">${pct(v.margin)}</td>
      <td class="num">${v.growth === null ? '--' : pct(v.growth)}</td>
      <td class="num">${pct(v.yield, 2)}</td>
      <td class="num">${money(v.value)}</td>
      <td class="num ${cls(v.gap)}">${signed(v.gap)}</td>
      <td>${bandPill(v.band)}</td>
      <td class="num"><div class="score-cell">
        <span class="score-bar"><span style="width:${Math.max(0, Math.min(100, v.score || 0))}%"></span></span>
        <span class="score-num">${v.score === null ? '--' : v.score.toFixed(0)}</span>
      </div></td>
    </tr>`).join('');

  document.getElementById('tab-companies').innerHTML = `
    <h2 class="section">Quality and valuation</h2>
    <p class="lede">Every figure comes from ten years of SEC filings. Click any row for the
      full scoring breakdown, the ten-year history, and a discounted cash flow you can adjust yourself.
      "Return" is return on equity, or return on invested capital where buybacks have driven book equity
      near zero and ROE would be meaningless. "vs price" is how far today's price sits below the estimated
      value: positive means cheaper than the estimate.</p>
    <div class="card"><div class="table-wrap"><table>
      <thead><tr>${head}</tr></thead><tbody>${body}</tbody>
    </table></div></div>`;

  document.querySelectorAll('#tab-companies th.sortable').forEach(th => {
    th.onclick = () => {
      const k = th.dataset.key;
      state.sort = { key: k, dir: state.sort.key === k ? -state.sort.dir : (k === 'ticker' ? 1 : -1) };
      renderCompanies();
    };
  });
  document.querySelectorAll('#tab-companies tr.clickable').forEach(tr => {
    tr.onclick = () => openDrawer(tr.dataset.ticker);
  });
}

/* ---------------------------------------------------------------- drawer */

function openDrawer(ticker) {
  const c = state.data.companies.find(x => x.ticker === ticker);
  if (!c) return;
  state.drawer = c;

  const q = c.quality || {}, v = c.valuation || {}, p = c.price || {};
  const components = (q.components || []).map(comp => `
    <div class="comp">
      <div class="comp-top">
        <span class="comp-label">${esc(comp.label)}</span>
        <span class="comp-pts">${comp.points} / ${comp.max}</span>
      </div>
      <div class="comp-track"><span style="width:${(comp.points / comp.max) * 100}%"></span></div>
      <div class="comp-note">${esc(comp.note)}</div>
      ${comp.detail ? `<div class="comp-detail">${esc(comp.detail)}</div>` : ''}
    </div>`).join('');

  const charts = [
    chartCard('Owner earnings', c.series.owner_earnings),
    chartCard('Revenue', c.series.revenue),
    chartCard('Return on equity', c.series.roe, 'pct'),
    chartCard('Gross margin', c.series.gross_margin, 'pct'),
  ].filter(Boolean).join('');

  const filings = (c.filings || []).slice(0, 5).map(f => `
    <tr><td>${esc(f.form)}</td><td>${esc(f.filed)}</td>
    <td><a href="${esc(f.url)}" target="_blank" rel="noopener">open</a></td></tr>`).join('');

  document.getElementById('drawer-root').innerHTML = `
    <div class="backdrop" id="backdrop">
      <div class="drawer" role="dialog" aria-label="${esc(c.name)} detail">
        <div class="drawer-head">
          <div>
            <div style="font-family:var(--serif);font-size:23px;font-weight:600">
              ${esc(c.ticker)} <span style="color:var(--muted);font-size:15px">${esc(c.name)}</span>
            </div>
            <div style="font-size:13px;color:var(--muted);margin-top:2px">
              ${money(p.price)} &middot; <span class="${cls(p.change_pct)}">${signed(p.change_pct)}</span>
              &middot; ${signed(p.from_high_pct)} from 52-week high
              &middot; quality ${q.score ?? '--'} (${esc(q.grade || '')})
            </div>
          </div>
          <button class="close-x" id="close-drawer" aria-label="Close">&times;</button>
        </div>
        <div class="drawer-body">
          ${(q.caveats || []).map(t => `<div class="caveat">${esc(t)}</div>`).join('')}

          <h3>Quality score: ${q.score ?? '--'} / 100</h3>
          ${components}

          <h3>Ten-year record</h3>
          <div class="chart-grid">${charts || '<p class="lede">No history available.</p>'}</div>

          <h3>What it is worth</h3>
          <div id="dcf-panel"></div>

          <h3>Recent filings</h3>
          <div class="table-wrap"><table>
            <thead><tr><th>Form</th><th>Filed</th><th>Link</th></tr></thead>
            <tbody>${filings || '<tr><td colspan="3">None found</td></tr>'}</tbody>
          </table></div>
          <p class="lede" style="margin-top:10px">
            Share count: ${c.shares ? nf(c.shares / 1e6, 1) + 'M' : '--'}
            <span style="opacity:.7">(${esc(c.shares_source)})</span>.
            <a href="${esc(c.edgar_url)}" target="_blank" rel="noopener">All EDGAR filings</a>.
          </p>
        </div>
      </div>
    </div>`;

  document.getElementById('close-drawer').onclick = closeDrawer;
  document.getElementById('backdrop').onclick = e => {
    if (e.target.id === 'backdrop') closeDrawer();
  };
  renderDcf(c, v);
  document.body.style.overflow = 'hidden';
}

function closeDrawer() {
  document.getElementById('drawer-root').innerHTML = '';
  document.body.style.overflow = '';
  state.drawer = null;
}

function renderDcf(c, v) {
  const panel = document.getElementById('dcf-panel');
  if (!v.available) {
    panel.innerHTML = `<p class="lede">No intrinsic value estimate: ${esc(v.reason || 'insufficient data')}.
      A discounted cash flow needs positive, reasonably steady owner earnings; when a business does not
      have them, the honest answer is that this method cannot value it.</p>`;
    return;
  }

  const settings = state.data.settings || {};
  const ctrls = {
    growth: v.assumed_growth_pct,
    discount: v.discount_rate_pct,
    terminal: v.terminal_growth_pct,
    mos: settings.margin_of_safety_pct ?? 30,
  };

  panel.innerHTML = `
    <p class="lede">Ten years of projected owner earnings discounted to today, plus a terminal value.
      The starting point is the ${esc(v.base_method || 'median')} (${compact(v.base_owner_earnings)}),
      which grew ${pct(v.historic_growth_pct)} a year historically. Move the assumptions and watch the
      answer change: that sensitivity is the honest lesson of any valuation.</p>
    <div class="controls">
      <div class="control"><label>Growth, years 1-5 <span class="val" id="l-growth"></span></label>
        <input type="range" id="s-growth" min="-5" max="25" step="0.5"></div>
      <div class="control"><label>Discount rate <span class="val" id="l-discount"></span></label>
        <input type="range" id="s-discount" min="5" max="18" step="0.5"></div>
      <div class="control"><label>Terminal growth <span class="val" id="l-terminal"></span></label>
        <input type="range" id="s-terminal" min="0" max="4" step="0.1"></div>
      <div class="control"><label>Margin of safety <span class="val" id="l-mos"></span></label>
        <input type="range" id="s-mos" min="0" max="60" step="5"></div>
    </div>
    <div class="scenarios" id="scenarios"></div>
    <p class="lede" id="dcf-summary" style="margin-top:14px"></p>`;

  const inputs = {
    growth: document.getElementById('s-growth'),
    discount: document.getElementById('s-discount'),
    terminal: document.getElementById('s-terminal'),
    mos: document.getElementById('s-mos'),
  };
  Object.entries(inputs).forEach(([k, el]) => {
    el.value = ctrls[k];
    el.oninput = () => { ctrls[k] = parseFloat(el.value); update(); };
  });

  function update() {
    document.getElementById('l-growth').textContent = pct(ctrls.growth);
    document.getElementById('l-discount').textContent = pct(ctrls.discount);
    document.getElementById('l-terminal').textContent = pct(ctrls.terminal);
    document.getElementById('l-mos').textContent = pct(ctrls.mos, 0);

    const price = (c.price || {}).price;
    const shapes = {
      bear: [ctrls.growth / 100 - 0.05, ctrls.growth / 100 - 0.07],
      base: [ctrls.growth / 100, ctrls.growth / 100 - 0.03],
      bull: [ctrls.growth / 100 + 0.04, ctrls.growth / 100],
    };
    let baseValue = null;
    const cards = Object.entries(shapes).map(([name, [g1, g2]]) => {
      const out = dcf({
        base: v.base_owner_earnings, shares: v.shares,
        g1: Math.max(-0.5, g1), g2: Math.max(-0.5, g2),
        discount: ctrls.discount / 100, terminal: ctrls.terminal / 100,
        netCash: v.net_cash,
      });
      if (!out) return `<div class="scenario ${name}"><div class="name">${name}</div>
        <div class="price">--</div><div class="delta">discount must exceed terminal growth</div></div>`;
      if (name === 'base') baseValue = out.perShare;
      const upside = price ? (out.perShare / price - 1) * 100 : null;
      return `<div class="scenario ${name}">
        <div class="name">${name}</div>
        <div class="price">${money(out.perShare)}</div>
        <div class="delta ${cls(upside)}">${signed(upside)} vs price</div>
        <div style="font-size:11px;color:var(--muted);margin-top:4px">
          terminal value is ${pct(out.terminalShare * 100, 0)} of the total</div>
      </div>`;
    }).join('');
    document.getElementById('scenarios').innerHTML = cards;

    const summary = document.getElementById('dcf-summary');
    if (baseValue && price) {
      const buyBelow = baseValue * (1 - ctrls.mos / 100);
      const gap = (baseValue - price) / baseValue * 100;
      const verdict = price <= buyBelow ? 'Below margin of safety'
        : price <= baseValue * 1.1 ? 'Near fair value' : 'Above estimated value';
      summary.innerHTML = `On these assumptions the base case is <b>${money(baseValue)}</b> a share against
        a market price of <b>${money(price)}</b> (${signed(gap)}). With a ${pct(ctrls.mos, 0)} margin of
        safety you would want to pay under <b>${money(buyBelow)}</b>. Verdict: ${bandPill(verdict)}`;
    } else {
      summary.textContent = '';
    }
  }
  update();
}

/* ----------------------------------------------------------------- other */

function renderScreen() {
  const s = state.data.screen || {};
  const el = document.getElementById('tab-screen');
  if (!s.available) {
    el.innerHTML = `<div class="card"><div class="empty"><div class="big">Screen unavailable</div>
      <div>${esc(s.reason || 'No data')}</div></div></div>`;
    return;
  }
  const rows = s.top.map(r => `
    <tr><td><span class="ticker">${esc(r.ticker)}</span><br><span class="co-name">${esc(r.name)}</span></td>
      <td>${esc(r.sector)}</td>
      <td class="num">${pct(r.roe_pct)}</td>
      <td class="num">${compact(r.net_income)}</td>
      <td class="num">${r.debt_to_earnings === null ? '--' : r.debt_to_earnings + 'x'}</td>
      <td class="num">${nf(r.screen_score, 1)}</td></tr>`).join('');
  el.innerHTML = `<h2 class="section">S&amp;P 500 screen &middot; ${esc(s.period)}</h2>
    <p class="lede">${esc(s.note)} Ranked on return on equity with a penalty for leverage,
      across ${s.scored} of the ${s.universe} constituents that reported comparable figures.</p>
    <div class="card"><div class="table-wrap"><table>
      <thead><tr><th>Company</th><th>Sector</th><th class="num">ROE</th>
        <th class="num">Net income</th><th class="num">Debt / earnings</th><th class="num">Score</th></tr></thead>
      <tbody>${rows}</tbody></table></div></div>`;
}

function renderBerkshire() {
  const b = state.data.berkshire || {};
  const el = document.getElementById('tab-berkshire');
  if (!b.available) {
    el.innerHTML = `<div class="card"><div class="empty"><div class="big">13F unavailable</div></div></div>`;
    return;
  }
  const changeTags = { new: 'pill-new', exited: 'pill-exit', added: 'pill-buy', trimmed: 'pill-fair' };
  const changes = (b.changes || []).map(ch => `
    <div class="signal">
      <span class="sig-tag ${ch.kind === 'exited' ? 'sev-high' : 'sev-low'}">${esc(ch.kind)}</span>
      <div><div class="sig-head">${esc(ch.issuer)}${ch.ticker ? ` (${esc(ch.ticker)})` : ''}</div>
      <div class="sig-detail">${ch.change_pct !== undefined ? signed(ch.change_pct) + ' in share count' : ''}
        ${ch.value ? ' &middot; position worth ' + compact(ch.value) : ''}</div></div>
    </div>`).join('');

  const holdings = (b.holdings || []).map(h => `
    <tr><td><span class="ticker">${esc(h.ticker || '')}</span><br><span class="co-name">${esc(h.issuer)}</span></td>
      <td class="num">${compact(h.value)}</td>
      <td class="num">${pct(h.weight_pct)}</td>
      <td class="num">${nf(h.shares / 1e6, 1)}M</td>
      <td>${h.change && h.change !== 'held'
        ? `<span class="pill ${changeTags[h.change] || 'pill-rich'}">${esc(h.change)}${h.change_pct ? ' ' + signed(h.change_pct) : ''}</span>`
        : '<span style="color:var(--muted);font-size:12px">held</span>'}</td></tr>`).join('');

  el.innerHTML = `<h2 class="section">What Berkshire actually owns</h2>
    <p class="lede">From the 13F for ${esc(b.period)}, filed ${esc(b.filed)}: ${b.position_count} positions
      worth ${compact(b.total_value)}. A 13F is filed up to 45 days after quarter end and covers US-listed
      equities only, so it is a delayed and partial view, not a live portfolio.
      <a href="${esc(b.source)}" target="_blank" rel="noopener">Source filings</a>.</p>
    ${changes ? `<h2 class="section" style="font-size:16px;margin-top:20px">Changes since ${esc(b.previous_period || 'the prior quarter')}</h2>
      <div class="card">${changes}</div>` : ''}
    <div class="card"><div class="table-wrap"><table>
      <thead><tr><th>Holding</th><th class="num">Value</th><th class="num">Weight</th>
        <th class="num">Shares</th><th>Change</th></tr></thead>
      <tbody>${holdings}</tbody></table></div></div>`;
}

function renderPositions() {
  const p = state.data.positions || { rows: [] };
  const el = document.getElementById('tab-positions');
  if (!p.rows.length) {
    el.innerHTML = `<div class="card"><div class="empty">
      <div class="big">No positions recorded</div>
      <div>Add them to <code>watchlist.json</code> under <code>positions</code>, with a ticker,
      share count and cost basis. They will then be valued here and checked against the same criteria.</div>
    </div></div>`;
    return;
  }
  const rows = p.rows.map(r => `
    <tr><td><span class="ticker">${esc(r.ticker)}</span><br><span class="co-name">${esc(r.name)}</span></td>
      <td class="num">${nf(r.shares)}</td>
      <td class="num">${money(r.cost_basis)}</td>
      <td class="num">${money(r.price)}</td>
      <td class="num">${money(r.value)}</td>
      <td class="num ${cls(r.gain)}">${r.gain === null ? '--' : money(r.gain)}</td>
      <td class="num ${cls(r.gain_pct)}">${signed(r.gain_pct)}</td>
      <td class="num">${r.quality_score ?? '--'}</td>
      <td>${bandPill(r.band)}</td></tr>`).join('');
  el.innerHTML = `<h2 class="section">Your positions</h2>
    <p class="lede">Worth ${money(p.total_value)} against ${money(p.total_cost)} invested:
      <span class="${cls(p.total_gain)}">${money(p.total_gain)} (${signed(p.total_gain_pct)})</span>.
      The quality and verdict columns re-run the same tests on what you already hold, which is the
      harder discipline: deciding whether a thesis still holds.</p>
    <div class="card"><div class="table-wrap"><table>
      <thead><tr><th>Position</th><th class="num">Shares</th><th class="num">Cost</th><th class="num">Price</th>
        <th class="num">Value</th><th class="num">Gain</th><th class="num">%</th>
        <th class="num">Quality</th><th>Verdict</th></tr></thead>
      <tbody>${rows}</tbody></table></div></div>`;
}

function renderLearn() {
  const p = state.data.principle || {};
  document.getElementById('tab-learn').innerHTML = `
    <h2 class="section">Principle of the day</h2>
    <p class="lede">One of ${p.total || 20}, rotating daily.</p>
    <div class="principle">
      <h3>${esc(p.title)}</h3>
      <p>${esc(p.body)}</p>
      <div class="src">${esc(p.source)}</div>
    </div>
    <div class="framework">
      <h2 class="section">How this dashboard reads a business</h2>
      <p class="lede">Buffett's method is a sequence of filters, applied in order. A company has to
        pass each one before the next is worth asking.</p>
      <ol>
        <li><b>Do I understand it?</b> The circle of competence. This is the one filter no dashboard
          can apply for you, and the one Buffett treats as non-negotiable.</li>
        <li><b>Does it have a moat?</b> Measured here through margin stability and sustained high
          returns on equity. A business holding its margins for a decade is being protected by something.</li>
        <li><b>Is management rational with capital?</b> Approximated by the debt burden and the
          one-dollar premise: every dollar retained should create at least a dollar of market value.</li>
        <li><b>Is the price sensible?</b> Only asked last. Owner earnings are discounted to a present
          value, and a margin of safety is demanded on top, because every estimate can be wrong.</li>
      </ol>
      <p class="lede">The short-term panel on the companies table exists for timing and context only.
        Momentum and RSI say nothing about what a business is worth, and mixing the two disciplines
        is how people end up doing neither well.</p>
    </div>`;
}

/* ------------------------------------------------------------------ shell */

function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll('nav.tabs button').forEach(b =>
    b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
  document.querySelectorAll('main section').forEach(s => { s.hidden = s.id !== `tab-${tab}`; });
  try { localStorage.setItem('bd-tab', tab); } catch (e) { /* private mode */ }
}

function applyTheme(theme) {
  if (theme) document.documentElement.setAttribute('data-theme', theme);
  else document.documentElement.removeAttribute('data-theme');
  try { theme ? localStorage.setItem('bd-theme', theme) : localStorage.removeItem('bd-theme'); }
  catch (e) { /* private mode */ }
}

async function init() {
  try { applyTheme(localStorage.getItem('bd-theme')); } catch (e) { /* private mode */ }

  document.getElementById('theme-toggle').onclick = () => {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark'
      || (!document.documentElement.hasAttribute('data-theme')
          && matchMedia('(prefers-color-scheme: dark)').matches);
    applyTheme(dark ? 'light' : 'dark');
  };

  let data;
  try {
    const res = await fetch(`data/latest.json?t=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    data = await res.json();
  } catch (err) {
    document.getElementById('app').innerHTML = `<div class="card"><div class="empty">
      <div class="big">Could not load the data file</div>
      <div>Expected <code>docs/data/latest.json</code>. Run <code>python scripts/build.py</code>
      to generate it, or wait for the nightly workflow.<br><br>
      <span style="color:var(--neg)">${esc(err.message)}</span></div></div></div>`;
    return;
  }
  state.data = data;

  const stale = (Date.now() - new Date(data.generated_at).getTime()) / 36e5 > 36;
  document.getElementById('updated').innerHTML =
    `<span class="dot ${stale ? 'stale' : ''}"></span> Updated ${timeAgo(data.generated_at)}
     <span style="opacity:.6">(${esc(data.generated_at.replace('T', ' ').replace('+00:00', ' UTC'))})</span>`;

  document.getElementById('app').hidden = false;
  document.getElementById('loading').hidden = true;

  renderWeather();
  renderSignals();
  renderCompanies();
  renderScreen();
  renderBerkshire();
  renderPositions();
  renderLearn();

  document.getElementById('c-signals').textContent = (data.signals || []).length;
  document.getElementById('c-companies').textContent = data.companies.length;
  document.getElementById('disclaimer-text').textContent = data.disclaimer;

  document.querySelectorAll('nav.tabs button').forEach(b => {
    b.onclick = () => switchTab(b.dataset.tab);
  });
  let saved = 'signals';
  try { saved = localStorage.getItem('bd-tab') || 'signals'; } catch (e) { /* private mode */ }
  switchTab(document.querySelector(`nav.tabs button[data-tab="${saved}"]`) ? saved : 'signals');

  document.addEventListener('keydown', e => { if (e.key === 'Escape' && state.drawer) closeDrawer(); });
}

init();
