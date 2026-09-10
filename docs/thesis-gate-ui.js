/* Thesis Gate - views. Logic lives in thesis-gate-core.js.

   Two rules from the spec govern everything here:
   - No price, no performance figure, no return, no overall score anywhere in
     this module (section 7 and acceptance criterion 8). It never reads the
     dashboard payload, so it cannot show one by accident.
   - On a block, always offer Park, Kill and Reframe. Never a dead end. */

(function (global) {
  'use strict';

  const C = global.ThesisGateCore;
  const store = C.createLocalStore();

  const state = { view: 'list', theses: [], currentId: null, stage: 0, error: '',
                // Field errors live here, not in the DOM: persist() re-renders the
                // whole stage, which would otherwise wipe the message immediately.
                fieldErrors: {} };

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const current = () => state.theses.find(t => t.id === state.currentId) || null;

  /* ------------------------------------------------------- field schema */

  const GATE_OPTIONS = [['pass', 'Yes / passes'], ['fail', 'No / fails'], ['unknown', "Don't know yet"]];

  const FIELDS = {
    origin: [
      { k: 'source', label: 'Where did this come from?', type: 'select', options: [
        ['own-observation', 'I noticed it myself'], ['obscure-item', 'An obscure item I stumbled on'],
        ['tip-or-recommendation', 'A tip or recommendation'], ['mainstream-coverage', 'Mainstream coverage'],
        ['social-trend', 'Social media / trending']] },
      { k: 'sourceDetail', label: 'How exactly did you encounter it?', type: 'text',
        ph: 'Walked past three depots retrofitting the same rig in one month' },
      { k: 'anomaly', label: 'What looked odd? (required, 20 characters minimum)', type: 'textarea',
        ph: 'The specific thing that did not fit the story everyone else was telling',
        hint: 'If you cannot name an anomaly, there is nothing to investigate yet.' },
    ],
    wave: [
      { k: 'trendStatement', label: 'The trend, without naming the company', type: 'textarea',
        ph: 'Warehouses automate picking as labour costs rise', validate: 'trend' },
      { k: 'survivesProductFailure', label: 'Does demand for this trend exist even if this specific product fails?',
        type: 'gate' },
      { k: 'horizonYears', label: 'How many years should the trend run?', type: 'number', ph: '10' },
      { k: 'wavePosition', label: 'Where are we on the wave?', type: 'select', options: [
        ['early', 'Early'], ['mid', 'Middle'], ['late', 'Late'], ['unsure', 'Unsure']] },
    ],
    regulatory: [
      { k: 'harmTest', label: 'If this product physically harms someone, does the whole category stop?',
        type: 'gate', invert: true, hint: 'Answer "No / fails" if one incident would stop the category.' },
      { k: 'displacementTest', label: 'Does it displace a large, organised, politically visible workforce?',
        type: 'gate', invert: true, hint: 'Answer "No / fails" if it does displace one.' },
      { k: 'changeVisibility', label: 'How does the change arrive?', type: 'select', options: [
        ['abrupt-and-visible', 'Abrupt and visible'], ['gradual-and-unnoticed', 'Gradual and unnoticed']] },
      { k: 'regulator', label: 'Who has authority, and what is their incentive?', type: 'textarea',
        ph: 'Which body, and what makes them act or stay quiet' },
      { k: 'pendingLegal', label: 'Live cases or rulings that could change the rules', type: 'textarea',
        ph: 'Either direction - a ruling that helps counts too' },
    ],
    operator: [
      { k: 'companyStage', label: 'Is this a young company or a mature one?', type: 'select',
        options: [['young', 'Young'], ['mature', 'Mature']] },
      { k: 'founderTrackRecord', label: 'What did the founder build before, and at what scale?',
        type: 'textarea', ph: 'Concrete: what shipped, how big it got', only: 'young' },
      { k: 'builderOrFinancier', label: 'Builder or financier?', type: 'select', only: 'young',
        options: [['builder', 'Builder'], ['financier', 'Financier'], ['unclear', 'Unclear']] },
      { k: 'isOwnCustomer', label: 'Do they use their own product?', type: 'bool', only: 'young' },
      { k: 'evidenceOfCourseCorrection', label: 'A documented instance of admitting error and changing course',
        type: 'textarea', ph: 'When did they publicly kill something that was not working?', only: 'young' },
      { k: 'commitmentLevel', label: 'How committed are they?', type: 'select', only: 'young',
        options: [['all-in', 'All in'], ['partial', 'Partial'], ['unclear', 'Unclear']] },
      { k: 'capitalUse', label: 'Where does the cash go?', type: 'multi', only: 'mature', options: [
        ['buybacks', 'Buybacks'], ['dividends', 'Dividends'], ['acquisitions', 'Acquisitions'],
        ['growth-investment', 'Growth investment'], ['hoarding', 'Hoarding']] },
      { k: 'allocationFitsStage', label: 'Does the capital policy match where the company actually is?',
        type: 'gate', only: 'mature',
        hint: 'Returning cash is discipline for a stable cash machine and avoidance for a stagnating one.' },
      { k: 'hedgedBothWays', label: 'Buying cheap exposure to the shift AND building internal capability?',
        type: 'bool', only: 'mature' },
      { k: 'acquisitionInDna', label: 'Has it successfully integrated acquisitions before?',
        type: 'bool', only: 'mature' },
    ],
    insiders: [
      { k: 'debtSignal', label: 'How did their last debt raise go?', type: 'select', options: [
        ['oversubscribed', 'Oversubscribed'], ['normal', 'Normal'], ['struggled', 'Struggled'],
        ['none-issued', 'None issued']] },
      { k: 'insiderBuying', label: 'What are insiders doing?', type: 'select', options: [
        ['buying-own-money', 'Buying with their own money'], ['options-only', 'Options only'],
        ['net-selling', 'Net selling'], ['unknown', 'Unknown']] },
      { k: 'circularityCheck', label: 'Is a large backer also a supplier funding its own customer?',
        type: 'gate', invert: true,
        hint: 'Answer "No / fails" if the money is circular. This does not block, but it stays on the card.' },
    ],
    informationEdge: [
      { k: 'analystCoverage', label: 'How many analysts cover it?', type: 'number', ph: '0' },
      { k: 'obscurityReason', label: 'Why is it overlooked?', type: 'multi', options: [
        ['unknown-name', 'Unknown name'], ['spinoff', 'Spin-off'], ['secondary-listing', 'Secondary listing'],
        ['troubled-history', 'Troubled history'], ['unfashionable-sector', 'Unfashionable sector'],
        ['recently-listed', 'Recently listed'], ['none', 'It is not overlooked']] },
      { k: 'edgeStatement', label: 'What do you understand that the market has not priced in?',
        type: 'textarea', ph: 'One specific sentence. Not "it is cheap".', validate: 'edge', max: 200 },
    ],
    numbers: [
      { k: 'marketCap', label: 'Market capitalisation', type: 'sourced' },
      { k: 'currentRevenue', label: 'Current revenue', type: 'sourced' },
      { k: 'growthRate', label: 'Growth rate (%)', type: 'sourced' },
      { k: 'projectedRevenue5y', label: 'Projected revenue in 5 years', type: 'sourced' },
      { k: 'impliedValuation5y', label: 'Implied valuation in 5 years', type: 'sourced' },
      { k: 'cashPosition', label: 'Cash position', type: 'sourced' },
      { k: 'runwayMonths', label: 'Runway (months)', type: 'number', ph: '24' },
    ],
    killAttempt: [
      { k: 'failureReasons', label: 'Reasons this could be wrong (three minimum)', type: 'list',
        ph: 'A specific way the reasoning breaks' },
      { k: 'haloTest', label: "Remove the well-known founder's name. Does the thesis still stand?",
        type: 'textarea', ph: 'Explain what is left when the reputation is taken away' },
      { k: 'singlePointOfFailure', label: 'The one event that ends it', type: 'text',
        ph: 'A safety recall in the flagship market' },
      { k: 'challengerName', label: 'Who did you ask to argue against it?', type: 'text', ph: 'A name' },
      { k: 'challengerObjection', label: 'What did they say?', type: 'textarea',
        ph: 'Their strongest objection, in their words' },
    ],
    portfolio: [
      { k: 'positionSizePct', label: 'This position as % of total capital', type: 'number', ph: '5' },
      { k: 'totalLossTolerable', label: 'If this goes to zero, does your behaviour change?',
        type: 'gate', invert: true, hint: 'Answer "No / fails" if it would change your behaviour.' },
      { k: 'holdingPeriodYears', label: 'Holding period in years - actual, not aspirational',
        type: 'number', ph: '7' },
      { k: 'sellDiscipline', label: 'What would make you sell?', type: 'textarea',
        ph: 'Reference a break condition, not a price' },
      { k: 'riskProfileNote', label: 'Your circumstances', type: 'textarea',
        ph: 'Age, horizon, whether this capital is needed soon' },
    ],
  };

  /* ------------------------------------------------------------ helpers */

  async function load() {
    state.theses = await store.list();
  }

  async function persist(thesis) {
    try {
      C.reconcile(thesis, state.theses);
      await store.save(thesis);
      state.error = '';
    } catch (err) {
      // A silent write failure in a tool whose value is the record is worse
      // than an error (spec section 5).
      state.error = 'Could not save: ' + err.message
                  + '. Your browser may be blocking storage, or it may be full.';
    }
    render();
  }

  function statusPill(status) {
    const map = { draft: 'pill-rich', active: 'pill-buy', blocked: 'pill-fair',
                  killed: 'pill-exit', closed: 'pill-rich' };
    return `<span class="pill ${map[status] || 'pill-rich'}">${esc(status)}</span>`;
  }

  /* --------------------------------------------------------- list view */

  function renderList(el) {
    const live = state.theses.filter(t => t.status !== 'killed');
    const killed = state.theses.filter(t => t.status === 'killed');
    const counts = ['draft', 'active', 'blocked', 'closed']
      .map(s => `${state.theses.filter(t => t.status === s).length} ${s}`).join(' &middot; ');

    const portfolio = live.length
      ? C.portfolioWarnings(live[0], state.theses)
          .filter(w => w.id !== 'portfolio.horizon')
      : [];

    el.innerHTML = `
      <div class="section-head">
        <h2 class="section">Thesis Gate</h2>
        <button class="icon-btn" id="tg-new">New thesis</button>
      </div>
      <p class="lede">Eight stages, run in order, with hard gates early. The point is that a weak
        thesis dies at stage 2 instead of being rationalised at stage 8. There is no overall score
        here on purpose: a single number lets a strong answer in one place paper over a fatal flaw
        in another.</p>

      ${state.error ? `<div class="caveat">${esc(state.error)}</div>` : ''}

      ${portfolio.length ? `<div class="brief"><div class="brief-label">Portfolio</div>
        ${portfolio.map(w => `<p style="margin:0 0 6px">${esc(w.text)}</p>`).join('')}</div>` : ''}

      ${live.length ? `<div class="tg-cards">${live.map(cardHtml).join('')}</div>`
        : `<div class="card"><div class="empty">
             <div class="big">No theses yet</div>
             <div>Start one when you notice something odd. The first stage asks only where the
             idea came from and what looked wrong &mdash; before any analysis rewrites the memory of it.</div>
           </div></div>`}

      <div class="section-head" style="margin-top:28px">
        <h2 class="section" style="font-size:16px">Kill log</h2>
        <span class="co-name">${counts}</span>
      </div>
      <p class="lede">Rejected ideas, kept deliberately. Reviewing what you turned down, and why,
        is where the calibration happens &mdash; so this sits here rather than behind a settings page.</p>
      ${killed.length ? `<div class="card">${killed.map(t => `
        <div class="signal">
          <span class="sig-tag sev-high">killed</span>
          <div><div class="sig-head">${esc(t.subject.name || 'Untitled')}</div>
            <div class="sig-detail">${esc(t.killedReason || 'No reason recorded')}
              &middot; ${esc((t.updatedAt || '').slice(0, 10))}
              <a href="#" data-open="${esc(t.id)}">open</a></div></div>
        </div>`).join('')}</div>`
        : `<div class="card"><div class="empty"><div>Nothing killed yet.</div></div></div>`}`;

    el.querySelector('#tg-new').onclick = async () => {
      const t = await store.create(C.newThesis());
      await load();
      state.currentId = t.id; state.stage = 0; state.view = 'stage';
      render();
    };
    el.querySelectorAll('[data-open]').forEach(a => {
      a.onclick = e => { e.preventDefault(); state.currentId = a.dataset.open;
                         state.stage = 0; state.view = 'stage'; render(); };
    });
    el.querySelectorAll('[data-card]').forEach(c => {
      c.onclick = () => { state.currentId = c.dataset.card;
                          state.stage = Math.max(0, c.dataset.stage | 0); state.view = 'stage'; render(); };
    });
    el.querySelectorAll('[data-review]').forEach(b => {
      b.onclick = e => { e.stopPropagation(); state.currentId = b.dataset.review;
                         state.view = 'review'; render(); };
    });
  }

  function cardHtml(t) {
    const ev = C.evaluate(t, state.theses);
    const badges = ev.warnings.filter(w => w.level === 'badge');
    const due = C.reviewDue(t);
    return `
      <div class="plain-card" data-card="${esc(t.id)}" data-stage="${ev.stages.findIndex(s => !s.complete)}">
        <div class="plain-head">
          <span><span class="ticker">${esc(t.subject.name || 'Untitled thesis')}</span>
            ${t.subject.ticker ? `<span class="co-name">${esc(t.subject.ticker)}</span>` : ''}</span>
          ${statusPill(t.status)}
        </div>
        <div class="plain-headline">Stage ${ev.stages.filter(s => s.complete).length} of 9 complete${
          ev.failedGates.length ? ' &middot; blocked at stage ' + Math.min.apply(null, ev.failedGates.map(g => g.stage)) : ''}</div>
        <p class="plain-body">${esc(t.subject.oneLine || 'No one-line thesis yet.')}</p>
        ${badges.map(b => `<div class="tg-badge">${esc(b.text)}</div>`).join('')}
        ${due ? `<button class="icon-btn" data-review="${esc(t.id)}" style="margin-top:10px">Review due</button>` : ''}
      </div>`;
  }

  /* -------------------------------------------------------- stage view */

  function renderStage(el) {
    const t = current();
    if (!t) { state.view = 'list'; return render(); }
    const ev = C.evaluate(t, state.theses);
    const idx = Math.min(8, Math.max(0, state.stage));
    const stage = ev.stages[idx];
    const id = C.STAGE_IDS[idx];

    const rail = ev.stages.map(s => {
      // Reachability is checked first on purpose. A stage the user has not got
      // to yet has empty answers, and an empty answer reads as a failed gate -
      // which painted stages 5 and 7 red before they had been opened. Only a
      // stage you can actually reach is allowed to look blocked.
      const cls = !s.reachable ? 'tg-locked'
                : s.blocked ? 'tg-red'
                : s.stale ? 'tg-amber'
                : s.complete ? 'tg-green' : 'tg-grey';
      return `<button class="tg-step ${cls} ${s.index === idx ? 'tg-current' : ''}"
                data-goto="${s.index}" title="${esc(s.title)}">${s.index}</button>`;
    }).join('');

    const blocked = stage.gates.filter(g => g.answer === 'fail');

    el.innerHTML = `
      <div class="section-head">
        <h2 class="section">${esc(t.subject.name || 'New thesis')}</h2>
        <button class="icon-btn" id="tg-back">All theses</button>
      </div>
      ${state.error ? `<div class="caveat">${esc(state.error)}</div>` : ''}

      <div class="tg-rail">${rail}</div>
      <div class="tg-rail-key">
        <span><i class="tg-dot tg-green"></i>complete</span>
        <span><i class="tg-dot tg-red"></i>blocked</span>
        <span><i class="tg-dot tg-amber"></i>needs re-checking</span>
        <span><i class="tg-dot tg-grey"></i>not done</span>
        <span><i class="tg-dot tg-locked-dot"></i>not yet reachable</span>
      </div>

      ${idx === 0 ? subjectHtml(t) : ''}

      <div class="card"><div class="card-pad">
        <h3 style="margin-top:0">Stage ${idx} &mdash; ${esc(C.STAGE_TITLES[idx])}</h3>
        ${stage.stale ? `<div class="caveat">An earlier stage changed. Re-check this one &mdash;
          nothing was deleted, but the answers below were written under different assumptions.</div>` : ''}
        ${fieldsHtml(t, id)}
        ${idx === 7 ? breakConditionsHtml(t) : ''}
      </div></div>

      ${blocked.length ? `
        <div class="tg-block">
          <div class="tg-block-title">Blocked here</div>
          ${blocked.map(g => `<p>${esc(g.message)}</p>`).join('')}
          <div class="tg-actions">
            <button class="icon-btn" id="tg-park">Park it</button>
            <button class="icon-btn" id="tg-kill">Kill it</button>
            ${idx === 2 ? `<button class="icon-btn tg-primary" id="tg-reframe">Find another entry point</button>` : ''}
          </div>
          ${idx === 2 ? `<p class="tg-hint">The trend may be right and the vehicle wrong. Reframing
            carries your trend statement into a fresh draft and links the two.</p>` : ''}
        </div>` : ''}

      ${ev.warnings.filter(w => w.level !== 'badge' || true).length ? `
        <div class="brief" style="margin-top:18px"><div class="brief-label">Worth noting</div>
          ${ev.warnings.map(w => `<p style="margin:0 0 8px">${esc(w.text)}</p>`).join('') || '<p>Nothing flagged.</p>'}
        </div>` : ''}

      <div class="tg-nav">
        <button class="icon-btn" id="tg-prev" ${idx === 0 ? 'disabled' : ''}>Back</button>
        <span class="co-name">${stage.complete ? 'This stage is complete' : 'Stage incomplete'}</span>
        <button class="icon-btn tg-primary" id="tg-next" ${
          (idx >= 8 || blocked.length || !stage.complete) ? 'disabled' : ''}>Next stage</button>
      </div>`;

    el.querySelector('#tg-back').onclick = () => { state.fieldErrors = {}; state.view = 'list'; render(); };
    el.querySelector('#tg-prev').onclick = () => { state.fieldErrors = {}; state.stage = Math.max(0, idx - 1); render(); };
    el.querySelector('#tg-next').onclick = async () => {
      t.highestStageCompleted = Math.max(t.highestStageCompleted, idx);
      t.currentStage = Math.min(8, idx + 1);
      state.stage = t.currentStage;
      state.fieldErrors = {};
      await persist(t);
    };
    el.querySelectorAll('[data-goto]').forEach(b => {
      b.onclick = () => { state.stage = b.dataset.goto | 0; render(); };
    });

    const park = el.querySelector('#tg-park');
    if (park) park.onclick = async () => { t.status = 'blocked'; await persist(t); };
    const kill = el.querySelector('#tg-kill');
    if (kill) kill.onclick = async () => {
      const reason = global.prompt('Why are you killing this? The record is the point.');
      if (!reason) return;
      await store.archive(t.id, reason);
      await load(); state.view = 'list'; render();
    };
    const reframe = el.querySelector('#tg-reframe');
    if (reframe) reframe.onclick = async () => {
      const draft = await store.create(C.reframe(t));
      t.status = 'blocked';
      await store.save(t);
      await load();
      state.currentId = draft.id; state.stage = 0; render();
    };
    wireFields(el, t, id);
  }

  function subjectHtml(t) {
    return `<div class="card"><div class="card-pad">
      <div class="tg-field"><label>Company or asset</label>
        <input type="text" data-subject="name" value="${esc(t.subject.name)}" placeholder="Acme Robotics"></div>
      <div class="tg-field"><label>Ticker (optional)</label>
        <input type="text" data-subject="ticker" value="${esc(t.subject.ticker)}" placeholder="ACME"></div>
      <div class="tg-field"><label>The thesis in one sentence</label>
        <input type="text" data-subject="oneLine" value="${esc(t.subject.oneLine)}"
          placeholder="Warehouse robots become standard fit and this maker owns the retrofit market">
        <div class="tg-hint">Review will show you this sentence again, exactly as first written.</div></div>
    </div></div>`;
  }

  function fieldsHtml(t, stageId) {
    const s = t.stages[stageId];
    return (FIELDS[stageId] || []).filter(f => !f.only || f.only === s.companyStage)
      .map(f => {
        const v = s[f.k];
        let input = '';
        if (f.type === 'text') {
          input = `<input type="text" data-f="${f.k}" value="${esc(v)}" placeholder="${esc(f.ph || '')}">`;
        } else if (f.type === 'textarea') {
          input = `<textarea data-f="${f.k}" rows="3" placeholder="${esc(f.ph || '')}">${esc(v)}</textarea>`;
        } else if (f.type === 'number') {
          input = `<input type="number" data-f="${f.k}" value="${v == null ? '' : esc(v)}" placeholder="${esc(f.ph || '')}">`;
        } else if (f.type === 'bool') {
          input = `<label class="tg-check"><input type="checkbox" data-f="${f.k}" ${v ? 'checked' : ''}> Yes</label>`;
        } else if (f.type === 'gate' || f.type === 'select') {
          const opts = f.type === 'gate' ? GATE_OPTIONS : f.options;
          input = `<select data-f="${f.k}"><option value="">Choose&hellip;</option>` +
            opts.map(o => `<option value="${o[0]}" ${v === o[0] ? 'selected' : ''}>${esc(o[1])}</option>`).join('') +
            '</select>';
        } else if (f.type === 'multi') {
          input = '<div class="tg-multi">' + f.options.map(o =>
            `<label class="tg-check"><input type="checkbox" data-multi="${f.k}" value="${o[0]}"
              ${(v || []).indexOf(o[0]) >= 0 ? 'checked' : ''}> ${esc(o[1])}</label>`).join('') + '</div>';
        } else if (f.type === 'list') {
          const rows = (v || []).concat(['']);
          input = '<div class="tg-list">' + rows.map((row, i) =>
            `<input type="text" data-list="${f.k}" data-i="${i}" value="${esc(row)}"
              placeholder="${esc(f.ph || '')}">`).join('') + '</div>';
        } else if (f.type === 'sourced') {
          const val = v || {};
          input = `<div class="tg-sourced">
            <input type="number" data-sourced="${f.k}" data-part="value" value="${val.value == null ? '' : esc(val.value)}" placeholder="0">
            <select data-sourced="${f.k}" data-part="source">
              <option value="">Source&hellip;</option>
              ${[['audited-filing', 'Audited filing'], ['third-party', 'Third party'],
                 ['own-estimate', 'My own estimate'], ['company-guidance', "Company's own guidance"]]
                .map(o => `<option value="${o[0]}" ${val.source === o[0] ? 'selected' : ''}>${esc(o[1])}</option>`).join('')}
            </select>
            <input type="date" data-sourced="${f.k}" data-part="asOf" value="${esc(val.asOf || '')}">
          </div>`;
        }
        return `<div class="tg-field"><label>${esc(f.label)}</label>${input}
          ${f.hint ? `<div class="tg-hint">${esc(f.hint)}</div>` : ''}
          <div class="tg-error" data-err="${f.k}">${esc(state.fieldErrors[f.k] || '')}</div></div>`;
      }).join('');
  }

  function breakConditionsHtml(t) {
    return `<div class="tg-field">
      <label>Break conditions &mdash; observable events, not price levels (one minimum)</label>
      ${(t.breakConditions || []).map(b => `
        <div class="tg-bc">
          <label class="tg-check"><input type="checkbox" data-bc-obs="${esc(b.id)}" ${b.observed ? 'checked' : ''}>
            observed</label>
          <span>${esc(b.statement)}</span>
          <button class="tg-x" data-bc-del="${esc(b.id)}">&times;</button>
        </div>`).join('')}
      <div class="tg-sourced">
        <input type="text" id="tg-bc-new" placeholder="Founder leaves, or the retrofit cycle stalls for two quarters">
        <button class="icon-btn" id="tg-bc-add">Add</button>
      </div>
      <div class="tg-error" data-err="breakConditions">${esc(state.fieldErrors.breakConditions || '')}</div>
      <div class="tg-hint">A price drop is not a break condition. Describe what would prove the
        reasoning wrong.</div>
    </div>`;
  }

  function wireFields(el, t, stageId) {
    const path = k => `stages.${stageId}.${k}`;
    const showErr = (k, msg) => {
      if (msg) state.fieldErrors[k] = msg; else delete state.fieldErrors[k];
      const box = el.querySelector(`[data-err="${k}"]`);
      if (box) box.textContent = msg || '';
    };

    el.querySelectorAll('[data-subject]').forEach(inp => {
      inp.onchange = async () => {
        C.applyChange(t, 'subject.' + inp.dataset.subject, inp.value.trim());
        await persist(t);
      };
    });

    el.querySelectorAll('[data-f]').forEach(inp => {
      inp.onchange = async () => {
        const k = inp.dataset.f;
        const field = (FIELDS[stageId] || []).find(f => f.k === k) || {};
        let value = inp.type === 'checkbox' ? inp.checked
                  : inp.type === 'number' ? (inp.value === '' ? null : Number(inp.value))
                  : inp.value;
        if (field.validate === 'trend') {
          const r = C.validateTrendStatement(value, t.subject);
          showErr(k, r.valid ? '' : r.message);
        }
        if (field.validate === 'edge') {
          const r = C.validateEdgeStatement(value);
          showErr(k, r.valid ? '' : r.message);
        }
        C.applyChange(t, path(k), value);
        await persist(t);
      };
    });

    el.querySelectorAll('[data-multi]').forEach(inp => {
      inp.onchange = async () => {
        const k = inp.dataset.multi;
        const chosen = Array.from(el.querySelectorAll(`[data-multi="${k}"]`))
          .filter(x => x.checked).map(x => x.value);
        C.applyChange(t, path(k), chosen);
        await persist(t);
      };
    });

    el.querySelectorAll('[data-list]').forEach(inp => {
      inp.onchange = async () => {
        const k = inp.dataset.list;
        const rows = Array.from(el.querySelectorAll(`[data-list="${k}"]`))
          .map(x => x.value.trim()).filter(Boolean);
        C.applyChange(t, path(k), rows);
        await persist(t);
      };
    });

    el.querySelectorAll('[data-sourced]').forEach(inp => {
      inp.onchange = async () => {
        const k = inp.dataset.sourced;
        const parts = {};
        el.querySelectorAll(`[data-sourced="${k}"]`).forEach(x => { parts[x.dataset.part] = x.value; });
        if (parts.value === '' || parts.value == null) { C.applyChange(t, path(k), null); return persist(t); }
        C.applyChange(t, path(k), C.sourcedNumber(parts.value, parts.source || 'own-estimate', parts.asOf));
        await persist(t);
      };
    });

    const add = el.querySelector('#tg-bc-add');
    if (add) add.onclick = async () => {
      const box = el.querySelector('#tg-bc-new');
      const r = C.validateBreakCondition(box.value);
      if (!r.valid) return showErr('breakConditions', r.message);
      showErr('breakConditions', '');
      t.breakConditions = (t.breakConditions || []).concat(
        [{ id: C.uid(), statement: box.value.trim(), observed: false }]);
      C.applyChange(t, 'breakConditionCount', t.breakConditions.length);
      await persist(t);
    };
    el.querySelectorAll('[data-bc-del]').forEach(b => {
      b.onclick = async () => {
        t.breakConditions = t.breakConditions.filter(x => x.id !== b.dataset.bcDel);
        await persist(t);
      };
    });
    el.querySelectorAll('[data-bc-obs]').forEach(b => {
      b.onchange = async () => {
        const bc = t.breakConditions.find(x => x.id === b.dataset.bcObs);
        bc.observed = b.checked;
        bc.observedAt = b.checked ? new Date().toISOString() : null;
        if (b.checked) {
          global.alert('You defined this as invalidating the thesis. Revisit or close?');
        }
        await persist(t);
      };
    });
  }

  /* ------------------------------------------------------- review view */

  function renderReview(el) {
    const t = current();
    if (!t) { state.view = 'list'; return render(); }
    const originalOneLine = C.originalValue(t, 'subject.oneLine');
    const originalEdge = C.originalValue(t, 'stages.informationEdge.edgeStatement');

    el.innerHTML = `
      <div class="section-head">
        <h2 class="section">Review &mdash; ${esc(t.subject.name || 'Untitled')}</h2>
        <button class="icon-btn" id="tg-back">All theses</button>
      </div>
      <p class="lede">This screen deliberately shows no price and no performance. Judging the
        reasoning against the outcome is exactly the bias the tool exists to counter. What you
        are checking is whether the argument still holds, not whether it worked.</p>

      <div class="card"><div class="card-pad">
        <h3 style="margin-top:0">As you first wrote it</h3>
        <p class="tg-original">${esc(originalOneLine || 'Not recorded')}</p>
        <h3>The edge you claimed</h3>
        <p class="tg-original">${esc(originalEdge || 'Not recorded')}</p>
      </div></div>

      <div class="card"><div class="card-pad">
        <h3 style="margin-top:0">Break conditions</h3>
        ${(t.breakConditions || []).map(b => `
          <div class="tg-bc"><label class="tg-check">
            <input type="checkbox" data-rv-bc="${esc(b.id)}" ${b.observed ? 'checked' : ''}> observed</label>
            <span>${esc(b.statement)}</span></div>`).join('') || '<p>None recorded.</p>'}
        <div class="tg-field" style="margin-top:14px">
          <label>Does the thesis still hold?</label>
          <select id="tg-rv-holds"><option value="yes">Yes</option><option value="no">No</option></select>
        </div>
        <div class="tg-field"><label>Notes</label>
          <textarea id="tg-rv-notes" rows="3" placeholder="What changed, and what you got wrong or right in the reasoning"></textarea></div>
        <button class="icon-btn tg-primary" id="tg-rv-save">Record review</button>
      </div></div>`;

    el.querySelector('#tg-back').onclick = () => { state.view = 'list'; render(); };
    el.querySelectorAll('[data-rv-bc]').forEach(b => {
      b.onchange = async () => {
        const bc = t.breakConditions.find(x => x.id === b.dataset.rvBc);
        bc.observed = b.checked;
        if (b.checked) global.alert('You defined this as invalidating the thesis. Revisit or close?');
        await persist(t);
      };
    });
    el.querySelector('#tg-rv-save').onclick = async () => {
      t.reviews = (t.reviews || []).concat([{
        id: C.uid(), date: new Date().toISOString(),
        stillHolds: el.querySelector('#tg-rv-holds').value === 'yes',
        notes: el.querySelector('#tg-rv-notes').value,
        breakConditionsTriggered: (t.breakConditions || []).filter(b => b.observed).map(b => b.id),
      }]);
      await persist(t);
      state.view = 'list'; render();
    };
  }

  /* ------------------------------------------------------------ render */

  function render() {
    const el = document.getElementById('tab-thesis');
    if (!el) return;
    if (state.view === 'stage') renderStage(el);
    else if (state.view === 'review') renderReview(el);
    else renderList(el);
    el.insertAdjacentHTML('beforeend',
      `<div class="tg-disclaimer">This is a personal research tool. It produces no
       recommendations and no advice. All inputs are your own.</div>`);
  }

  global.ThesisGate = {
    mount: async function () { await load(); render(); },
    render: render,
  };
})(window);
