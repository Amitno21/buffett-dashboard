/* Amit Dashboard - client rendering.
   The payload is produced nightly by scripts/build.py. Everything here is
   presentation, with one exception: the discounted cash flow is recomputed in
   the browser so the assumption sliders respond instantly. That JavaScript
   implementation deliberately mirrors metrics.discounted_owner_earnings. */

const state = { data: null, tab: 'signals', sort: { key: 'score', dir: -1 },
                drawer: null, view: 'table' };

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
  const brief = state.data.brief
    ? `<div class="brief"><div class="brief-label">The short version</div>
         <p>${esc(state.data.brief)}</p></div>` : '';

  if (!signals.length) {
    el.innerHTML = `${brief}<div class="card"><div class="empty">
      <div class="big">Nothing moved today</div>
      <div>No price shocks, valuation crossings or new filings since the last run.
      A quiet day is the normal state of a portfolio you intend to hold.</div>
    </div></div>`;
    return;
  }
  el.innerHTML = `${brief}<h2 class="section">What changed in the last 24 hours</h2>
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

  if (state.view === 'plain') { renderCompanyCards(); return; }

  document.getElementById('tab-companies').innerHTML = `
    <div class="section-head">
      <h2 class="section">Quality and valuation</h2>
      <button class="icon-btn" id="view-toggle">Read it in plain English</button>
    </div>
    <p class="lede">Every figure comes from ten years of SEC filings. Click any row for the
      full scoring breakdown, the ten-year history, and a discounted cash flow you can adjust yourself.
      "Return" is return on equity, or return on invested capital where buybacks have driven book equity
      near zero and ROE would be meaningless. "vs price" is how far today's price sits below the estimated
      value: positive means cheaper than the estimate.</p>
    <div class="card"><div class="table-wrap"><table>
      <thead><tr>${head}</tr></thead><tbody>${body}</tbody>
    </table></div></div>`;

  document.getElementById('view-toggle').onclick = () => {
    state.view = 'plain'; renderCompanies();
  };
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

/* The same companies as sentences rather than columns, for reading rather
   than comparing. Ordered worst-priced last so anything trading below the
   estimate is at the top, where it will actually be read. */
function renderCompanyCards() {
  const order = { 'Below margin of safety': 0, 'Near fair value': 1, 'Above estimated value': 2 };
  const rows = [...state.data.companies].sort((a, b) => {
    const ka = order[(a.valuation || {}).band] ?? 3;
    const kb = order[(b.valuation || {}).band] ?? 3;
    return ka - kb || (b.quality.score || 0) - (a.quality.score || 0);
  });

  document.getElementById('tab-companies').innerHTML = `
    <div class="section-head">
      <h2 class="section">Quality and valuation</h2>
      <button class="icon-btn" id="view-toggle">Back to the table</button>
    </div>
    <p class="lede">Every company in a sentence or two, cheapest against its estimate first.
      Click any card for the full detail.</p>
    ${rows.map(c => `
      <div class="plain-card" data-ticker="${esc(c.ticker)}">
        <div class="plain-head">
          <span><span class="ticker">${esc(c.ticker)}</span>
            <span class="co-name">${esc(c.name)}</span></span>
          ${bandPill((c.valuation || {}).band)}
        </div>
        <div class="plain-headline">${esc(c.headline || '')}</div>
        <p class="plain-body">${esc(c.summary || '')}</p>
      </div>`).join('')}`;

  document.getElementById('view-toggle').onclick = () => {
    state.view = 'table'; renderCompanies();
  };
  document.querySelectorAll('.plain-card').forEach(card => {
    card.onclick = () => openDrawer(card.dataset.ticker);
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
          ${c.summary ? `<div class="brief"><div class="brief-label">In plain English</div>
            <p>${esc(c.summary)}</p></div>` : ''}
          ${(q.caveats || []).map(t => `<div class="caveat">${esc(t)}</div>`).join('')}

          <h3>Quality score: ${q.score ?? '--'} / 100</h3>
          ${components}

          <h3>Ten-year record</h3>
          <div class="chart-grid">${charts || '<p class="lede">No history available.</p>'}</div>

          <h3>What it is worth</h3>
          <div id="dcf-panel"></div>

          <h3>Momentum and timing</h3>
          ${momentumPanel(p)}

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

/* The short-term panel. Deliberately separated from everything above it and
   labelled as a different discipline: none of these say anything about what a
   business is worth. They are here for timing an entry you have already
   decided on, and for position sizing. */
function momentumPanel(p) {
  if (!p || !p.price) return '<p class="lede">No price history available.</p>';

  const trend = (p.sma50 && p.sma200)
    ? (p.sma50 > p.sma200 ? 'above' : 'below')
    : null;
  const rsiNote = p.rsi14 === null || p.rsi14 === undefined ? ''
    : p.rsi14 >= 70 ? 'conventionally overbought'
    : p.rsi14 <= 30 ? 'conventionally oversold' : 'neither extreme';

  return `
    <p class="lede">A different discipline from everything above. These measure
      what the price has been doing, not what the business is worth, and Buffett
      does not use them to decide what to own. They are useful only for timing a
      purchase you have already justified on value, and for sizing it.</p>
    <div class="kv">
      <div><div class="k">50-day average</div><div class="v">${money(p.sma50)}</div></div>
      <div><div class="k">200-day average</div><div class="v">${money(p.sma200)}</div></div>
      <div><div class="k">RSI (14)</div><div class="v">${p.rsi14 ?? '--'}</div></div>
      <div><div class="k">Daily move (ATR)</div><div class="v">${pct(p.atr_pct)}</div></div>
      <div><div class="k">52-week high</div><div class="v">${money(p.high_52w)}</div></div>
      <div><div class="k">52-week low</div><div class="v">${money(p.low_52w)}</div></div>
    </div>
    <p class="lede" style="margin-top:12px">
      ${trend ? `The 50-day average is <b>${trend}</b> the 200-day, the conventional
        reading of an ${trend === 'above' ? 'uptrend' : 'downtrend'}. ` : ''}
      RSI of ${p.rsi14 ?? '--'} is ${rsiNote}.
      The price sits <b>${signed(p.from_high_pct)}</b> from its 52-week high and
      <b>${signed(p.from_low_pct)}</b> above its low. A typical day moves about
      ${pct(p.atr_pct)}, which is the figure to size a position against if a
      temporary fall would force you to sell.
    </p>`;
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
      <div>Copy <code>positions.local.example.json</code> to <code>positions.local.json</code> and list
      each holding with a ticker, share count and cost basis. That file is git-ignored, so your holdings
      stay on your machine: they are valued and checked against the same criteria here, but never
      published. This tab is therefore always empty on the public site.</div>
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
      <p class="lede">The momentum panel inside each company's detail view exists for timing and context only.
        Momentum and RSI say nothing about what a business is worth, and mixing the two disciplines
        is how people end up doing neither well.</p>
    </div>`;
}



/* ------------------------------------------------------------------ etfs */

function renderEtfs() {
  const d = state.data.etfs || {};
  const el = document.getElementById('tab-etfs');
  const us = d.us || [];
  const isr = d.israel || {};

  const usRows = us.map(f => `
    <tr class="${f.symbol === d.benchmark ? 'etf-benchmark' : ''}">
      <td><span class="ticker">${esc(f.symbol)}</span><br>
        <span class="co-name">${esc(f.name)}</span></td>
      <td class="fund-what">${esc(f.description)}</td>
      <td class="num">${money(f.price)}</td>
      <td class="num ${cls(f.year_pct)}">${signed(f.year_pct)}</td>
      <td class="num ${cls(f.five_year_pct)}">${signed(f.five_year_pct)}</td>
      <td class="num"><b>${f.fee_pct === null ? '--' : f.fee_pct.toFixed(2) + '%'}</b><br>
        <span class="co-name">$${nf(f.fee_per_10k, 2)} / $10k</span></td>
    </tr>`).join('');

  const catRows = (isr.categories || []).map(c => `
    <tr><td dir="auto">${esc(c.category)}</td>
      <td class="num">${c.count}</td>
      <td class="num ${cls(c.median_ytd_pct)}">${signed(c.median_ytd_pct)}</td>
      <td class="num ${cls(c.worst_ytd_pct)}">${signed(c.worst_ytd_pct)}</td>
      <td class="num ${cls(c.best_ytd_pct)}">${signed(c.best_ytd_pct)}</td></tr>`).join('');

  const isrRows = (isr.rows || []).map(f => `
    <tr><td dir="auto">${esc(f.name)}<br><span class="co-name" dir="auto">${esc(f.manager)}</span></td>
      <td dir="auto" class="fund-what">${esc(f.sub_category || f.category)}</td>
      <td class="num ${cls(f.ytd_pct)}">${signed(f.ytd_pct)}</td>
      <td class="num ${cls(f.month_pct)}">${signed(f.month_pct)}</td></tr>`).join('');

  el.innerHTML = `
    <h2 class="section">Index funds and ETFs</h2>
    <p class="lede">The alternative to everything else on this dashboard: buy the whole market
      cheaply and leave it alone. Buffett's instruction for his own estate was 90% in a low-cost
      S&amp;P 500 fund and 10% in short-term government bonds, and he has said plainly that most
      people should not try to pick stocks at all. This tab is here so that advice is visible
      rather than buried.</p>

    ${d.brief ? `<div class="brief"><div class="brief-label">The short version</div>
       <p>${esc(d.brief)}</p></div>` : ''}

    <div class="section-head">
      <h2 class="section" style="font-size:16px">US funds</h2>
      <span class="co-name">sorted by annual cost, cheapest first</span>
    </div>
    <p class="lede">The fee column is the one that matters most, because it is the only number
      here you can know in advance. Everything else is a guess about the future; the fee is
      deducted every year regardless.</p>
    <div class="card"><div class="table-wrap"><table>
      <thead><tr><th>Fund</th><th>What it holds</th><th class="num">Price</th>
        <th class="num">1 year</th><th class="num">5 years</th><th class="num">Annual fee</th></tr></thead>
      <tbody>${usRows}</tbody></table></div></div>

    ${isr.available ? `
      <div class="section-head" style="margin-top:26px">
        <h2 class="section" style="font-size:16px">Israeli ETFs</h2>
        <span class="co-name">${isr.count} funds &middot; median ${signed(isr.median_ytd_pct)} this year</span>
      </div>
      <p class="lede">Grouped by what they hold, because 502 funds is not a list anyone reads.
        Note how wide the range runs inside each group, and especially inside the leveraged
        category &mdash; those multiply the index's daily move in both directions.</p>
      <div class="card"><div class="table-wrap"><table>
        <thead><tr><th>Asset class</th><th class="num">Funds</th><th class="num">Median</th>
          <th class="num">Worst</th><th class="num">Best</th></tr></thead>
        <tbody>${catRows}</tbody></table></div></div>
      <p class="lede" style="margin-top:16px">The ${(isr.rows || []).length} strongest so far this
        year. Read this as survivorship in action rather than a recommendation: a table sorted by
        past return will always look impressive, and says nothing about the next twelve months.</p>
      <div class="card"><div class="table-wrap"><table>
        <thead><tr><th>Fund</th><th>Holds</th><th class="num">This year</th>
          <th class="num">This month</th></tr></thead>
        <tbody>${isrRows}</tbody></table></div></div>`
    : `<div class="card" style="margin-top:26px"><div class="empty">
        <div class="big">Israeli ETFs unavailable</div>
        <div>${esc(isr.reason || 'The source page could not be read on this run.')}</div></div></div>`}

    <h2 class="section" style="font-size:16px;margin-top:26px">Sources</h2>
    <p class="lede">${esc(d.attribution || '')} ${esc(d.returns_note || '')}</p>
    ${isr.source ? `<div class="src-links">
      <a class="src-link" href="${esc(isr.source)}" target="_blank" rel="noopener">
        Full Israeli ETF list <span dir="auto" class="co-name">קרנות סל</span></a></div>` : ''}`;
}

/* ---------------------------------------------------------------- israel */

/* Fund names arrive in Hebrew. dir="auto" lets the browser lay each one out
   right-to-left on its own, without flipping the surrounding English table. */
const heb = s => `<span dir="auto">${esc(s)}</span>`;

function renderIsrael() {
  const d = state.data.israel || {};
  const el = document.getElementById('tab-israel');
  const money = d.money_market || {};
  const hedge = d.hedge || {};

  const tiles = [];
  for (const idx of (d.indices || [])) {
    tiles.push(`<div class="stat">
      <div class="stat-label">${esc(idx.label)}</div>
      <div class="stat-value">${nf(idx.price, 0)}</div>
      <div class="stat-note ${cls(idx.change_pct)}">${signed(idx.change_pct)} &middot; ${signed(idx.from_high_pct)} from high</div>
    </div>`);
  }
  if (d.shekel && d.shekel.rate) {
    tiles.push(`<div class="stat">
      <div class="stat-label">US dollar</div>
      <div class="stat-value">&#8362;${d.shekel.rate.toFixed(3)}</div>
      <div class="stat-note ${cls(d.shekel.change_pct)}">${signed(d.shekel.change_pct)} today</div>
    </div>`);
  }
  if (money.available) {
    tiles.push(`<div class="stat">
      <div class="stat-label">Cash-equivalent yield</div>
      <div class="stat-value">${pct(money.median_year_pct, 2)}</div>
      <div class="stat-note">median money-market fund, 1 year</div>
    </div>`);
  }

  const moneyRows = (money.rows || []).map(f => `
    <tr><td>${heb(f.name)}<br><span class="co-name" dir="auto">${esc(f.manager)}</span></td>
      <td class="num ${cls(f.year_pct)}">${pct(f.year_pct, 2)}</td>
      <td class="num">${pct(f.ytd_pct, 2)}</td>
      <td class="num">${pct(f.month_pct, 2)}</td>
      <td class="num">${pct(f.fee_pct, 2)}</td>
      <td class="num">&#8362;${nf(f.size_musd, 0)}M</td></tr>`).join('');

  const hedgeRows = (hedge.rows || []).map(f => `
    <tr><td>${heb(f.name)}<br><span class="co-name" dir="auto">${esc(f.manager)}</span></td>
      <td class="num">${esc(f.profile || '--')}</td>
      <td class="num ${cls(f.year_pct)}">${pct(f.year_pct)}</td>
      <td class="num ${cls(f.ytd_pct)}">${pct(f.ytd_pct)}</td>
      <td class="num ${cls(f.three_year_pct)}">${f.three_year_pct === null ? '--' : pct(f.three_year_pct)}</td>
      <td class="num">${pct(f.fee_pct, 2)}</td>
      <td class="num">${pct(f.performance_fee_pct, 0)}</td></tr>`).join('');

  const links = (d.links || []).map(l =>
    `<a class="src-link" href="${esc(l.url)}" target="_blank" rel="noopener">
       ${esc(l.label)} <span dir="auto" class="co-name">${esc(l.hebrew)}</span></a>`).join('');

  el.innerHTML = `
    <h2 class="section">Israel</h2>
    <p class="lede">Tel Aviv indices, the shekel, and the two fund categories you asked for.
      These are funds rather than operating businesses, so none of the Buffett scoring on the
      other tabs applies to them &mdash; there are no accounts to read and nothing to value.
      What matters here is the fee, the risk taken, and whether the return beats simply
      holding cash.</p>

    ${d.brief ? `<div class="brief"><div class="brief-label">The short version</div>
       <p>${esc(d.brief)}</p></div>` : ''}

    ${tiles.length ? `<div class="weather" style="margin-bottom:22px">${tiles.join('')}</div>` : ''}

    ${money.available ? `
      <div class="section-head">
        <h2 class="section" style="font-size:16px">Money-market funds</h2>
        <span class="co-name">${money.count} funds &middot; &#8362;${nf(money.total_size_mils, 0)}M in total &middot; as at ${esc(money.as_of)}</span>
      </div>
      <p class="lede">The closest thing to cash: no lock-up, minimal risk, and a yield that
        follows the Bank of Israel's rate. Because the return is small, the management fee
        eats a real share of it &mdash; which is why the fee column is worth as much attention
        as the return. Showing the ${(money.rows || []).length} largest by size.</p>
      <div class="card"><div class="table-wrap"><table>
        <thead><tr><th>Fund</th><th class="num">1 year</th><th class="num">This year</th>
          <th class="num">This month</th><th class="num">Fee</th><th class="num">Size</th></tr></thead>
        <tbody>${moneyRows}</tbody></table></div></div>`
    : `<div class="card"><div class="empty"><div class="big">Money-market funds unavailable</div>
        <div>${esc(money.reason || 'The source page could not be read on this run.')}</div></div></div>`}

    ${hedge.available ? `
      <div class="section-head" style="margin-top:26px">
        <h2 class="section" style="font-size:16px">Hedge funds in trust</h2>
        <span class="co-name">${hedge.count} funds &middot; median 1-year ${pct(hedge.median_year_pct)}</span>
      </div>
      <p class="lede">Funds allowed to bet against shares as well as own them, sold to the public
        in a regulated wrapper. Note the spread: over the past year these ranged from
        ${pct(hedge.worst_year_pct)} to ${pct(hedge.best_year_pct)}, and
        ${hedge.negative_year_count} of ${hedge.with_year_history} lost money. Nearly all charge a
        performance fee &mdash; typically ${pct(hedge.typical_performance_fee_pct, 0)} of the gains
        on top of the annual fee &mdash; so the figures below are not what reaches you.
        Showing the ${(hedge.rows || []).length} best over one year, which is survivorship at work:
        the ones that did badly are further down the source list.</p>
      <div class="card"><div class="table-wrap"><table>
        <thead><tr><th>Fund</th><th class="num">Profile</th><th class="num">1 year</th>
          <th class="num">This year</th><th class="num">3 years</th>
          <th class="num">Fee</th><th class="num">Perf. fee</th></tr></thead>
        <tbody>${hedgeRows}</tbody></table></div></div>`
    : `<div class="card" style="margin-top:26px"><div class="empty"><div class="big">Hedge funds unavailable</div>
        <div>${esc(hedge.reason || 'The source page could not be read on this run.')}</div></div></div>`}

    <h2 class="section" style="font-size:16px;margin-top:26px">Sources</h2>
    <p class="lede">${esc(d.attribution || '')}</p>
    <div class="src-links">${links}</div>`;
}

/* -------------------------------------------------------------- glossary */

function renderGlossary() {
  const groups = state.data.glossary || [];
  if (!groups.length) return;
  const total = groups.reduce((n, g) => n + g.terms.length, 0);

  document.getElementById('glossary').innerHTML = `
    <div class="section-head" style="margin-top:34px">
      <h2 class="section">Every term on this page, explained</h2>
      <button class="icon-btn" id="glossary-all">Expand all</button>
    </div>
    <p class="lede">${total} concepts, in the order the dashboard reasons in, written for
      someone who has not done this before. No term is used in a definition before it has
      been defined.</p>
    ${groups.map((g, i) => `
      <details class="gloss-group"${i === 0 ? ' open' : ''}>
        <summary>
          <span class="gloss-title">${esc(g.group)}</span>
          <span class="gloss-count">${g.terms.length}</span>
        </summary>
        <p class="gloss-blurb">${esc(g.blurb)}</p>
        <dl class="gloss-list">
          ${g.terms.map(t => `
            <dt dir="auto">${esc(t.term)}</dt>
            <dd>${esc(t.definition)}</dd>`).join('')}
        </dl>
      </details>`).join('')}`;

  const button = document.getElementById('glossary-all');
  button.onclick = () => {
    const items = [...document.querySelectorAll('.gloss-group')];
    const expand = items.some(d => !d.open);
    items.forEach(d => { d.open = expand; });
    button.textContent = expand ? 'Collapse all' : 'Expand all';
  };
}

/* ------------------------------------------------------------------ shell */

function switchTab(tab) {
  state.tab = tab;
  document.querySelectorAll('nav.tabs button').forEach(b =>
    b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
  document.querySelectorAll('main section').forEach(s => { s.hidden = s.id !== `tab-${tab}`; });
  try { localStorage.setItem('bd-tab', tab); } catch (e) { /* private mode */ }
}

/* Light unless the reader has explicitly chosen dark. The system setting is
   deliberately not consulted: someone opening this over breakfast should not
   get a black page because their laptop is in dark mode. */
function applyTheme(theme) {
  const dark = theme === 'dark';
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
  const button = document.getElementById('theme-toggle');
  if (button) {
    button.textContent = dark ? 'Light mode' : 'Dark mode';
    button.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
  }
  try { localStorage.setItem('bd-theme', dark ? 'dark' : 'light'); }
  catch (e) { /* private mode */ }
}

function global_ThesisGate() { return window.ThesisGate; }

async function init() {
  let stored = null;
  try { stored = localStorage.getItem('bd-theme'); } catch (e) { /* private mode */ }
  applyTheme(stored === 'dark' ? 'dark' : 'light');

  document.getElementById('theme-toggle').onclick = () => {
    const dark = document.documentElement.getAttribute('data-theme') === 'dark';
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

  // Holdings are private. The build writes them to data/positions.local.json,
  // which .gitignore excludes, so the file exists when the dashboard is opened
  // from a local checkout and is absent on GitHub Pages. A failed fetch is the
  // normal published case, not an error worth showing.
  // Skipped outright on the published site: the file is git-ignored so it can
  // never be there, and probing for it would log a 404 in every visitor's
  // console. Any other host (localhost, a LAN address, file://) still looks.
  if (!location.hostname.endsWith('github.io')) {
    try {
      const pr = await fetch(`data/positions.local.json?t=${Date.now()}`);
      if (pr.ok) {
        const priv = await pr.json();
        if (priv && Array.isArray(priv.rows)) state.data.positions = priv;
      }
    } catch (err) {
      /* no private positions file: the tab keeps its empty state */
    }
  }

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
  renderEtfs();
  renderIsrael();
  renderPositions();
  renderLearn();
  renderGlossary();

  // Thesis Gate keeps its own browser-local state and never reads this payload,
  // which is what keeps prices out of a module the spec forbids them from.
  if (global_ThesisGate()) global_ThesisGate().mount();

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

  const tourButton = document.getElementById('tour-start');
  if (tourButton && window.Tour) {
    tourButton.onclick = () => window.Tour.start();
    // Offer it once, unprompted, to somebody arriving for the first time.
    if (!window.Tour.seen()) setTimeout(() => window.Tour.start(), 700);
  }
}

init();
