/* Thesis Gate - model, gating engine and store.
   Implements README-thesis-gate.md. No DOM in this file, so the whole of the
   logic is testable from thesis-gate-tests.html.

   The framework is GATED, NOT WEIGHTED. There is deliberately no overall score
   anywhere in here: a single number is the shortcut the gating structure exists
   to prevent (spec section 8). Anyone tempted to add one should read section 1
   first. */

(function (global) {
  'use strict';

  const STAGE_IDS = ['origin', 'wave', 'regulatory', 'operator', 'insiders',
                     'informationEdge', 'numbers', 'killAttempt', 'portfolio'];

  const STAGE_TITLES = [
    'Origin', 'The wave', 'Regulatory and political', 'Operator and capital',
    'Insider signals', 'Information edge', 'Numbers', 'Kill attempt',
    'Portfolio placement',
  ];

  const uid = () => 'th_' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
  const nowIso = () => new Date().toISOString();

  /* ------------------------------------------------------------- model */

  function newThesis(overrides) {
    const t = {
      id: uid(),
      createdAt: nowIso(),
      updatedAt: nowIso(),
      status: 'draft',
      currentStage: 0,
      highestStageCompleted: -1,
      derivedFrom: null,
      staleStages: [],
      killedReason: null,
      subject: { name: '', ticker: '', oneLine: '' },
      stages: {
        origin: { source: '', sourceDetail: '', anomaly: '' },
        wave: { trendStatement: '', survivesProductFailure: 'unknown',
                horizonYears: null, wavePosition: '' },
        regulatory: { harmTest: 'unknown', displacementTest: 'unknown',
                      changeVisibility: '', regulator: '', pendingLegal: '' },
        operator: { companyStage: '', founderTrackRecord: '', builderOrFinancier: '',
                    isOwnCustomer: false, evidenceOfCourseCorrection: '',
                    commitmentLevel: '', capitalUse: [], allocationFitsStage: 'unknown',
                    hedgedBothWays: false, acquisitionInDna: false },
        insiders: { holderMoves: [], debtSignal: '', insiderBuying: '',
                    circularityCheck: 'unknown' },
        informationEdge: { analystCoverage: null, obscurityReason: [], edgeStatement: '' },
        numbers: { marketCap: null, currentRevenue: null, growthRate: null,
                   projectedRevenue5y: null, impliedValuation5y: null,
                   cashPosition: null, runwayMonths: null },
        killAttempt: { failureReasons: [], haloTest: '', singlePointOfFailure: '',
                       challengerName: '', challengerObjection: '' },
        portfolio: { positionSizePct: null, totalLossTolerable: 'unknown',
                     holdingPeriodYears: null, sellDiscipline: '', riskProfileNote: '' },
      },
      breakConditions: [],
      reviews: [],
      journal: [],
    };
    return Object.assign(t, overrides || {});
  }

  function sourcedNumber(value, source, asOf, note) {
    return { value: Number(value), source: source, asOf: asOf || nowIso().slice(0, 10),
             note: note || '' };
  }

  /* --------------------------------------------------------- validation */

  /* A break condition describes thesis invalidation, not price movement.
     The hard part is rejecting "drops 25%" while accepting a legitimate
     business trigger that happens to contain a number, such as "revenue falls
     below 100m for two consecutive quarters". Two narrow rules do that:
     an explicit reference to price with a number, or a very short phrase that
     is nothing but a movement and a figure. */
  const PRICE_WORDS = /\b(share price|stock price|price|valuation|market cap|market capitalisation|share|stock)\b/i;
  const MOVEMENT = /\b(drops?|dropped|falls?|fell|declines?|declined|rises?|rose|gains?|climbs?|below|under|above|over|halves?|doubles?)\b/i;
  const HAS_FIGURE = /\d+\s*%|[$€£₪]\s*\d|\d+\s*(usd|ils|eur|gbp)\b/i;

  function validateBreakCondition(statement) {
    const text = String(statement || '').trim();
    if (!text) {
      return { valid: false, message: 'Write the event that would prove the reasoning wrong.' };
    }
    const words = text.split(/\s+/).length;
    const priceRef = PRICE_WORDS.test(text) && (HAS_FIGURE.test(text) || MOVEMENT.test(text));
    const bareMove = words <= 6 && MOVEMENT.test(text) && HAS_FIGURE.test(text);
    if (priceRef || bareMove) {
      return {
        valid: false,
        message: 'A price drop is not a break condition. What event would prove the reasoning wrong?',
      };
    }
    return { valid: true, message: '' };
  }

  /* The trend must stand on its own, without the company in it. */
  function validateTrendStatement(statement, subject) {
    const text = String(statement || '').trim();
    if (!text) return { valid: false, message: 'Describe the trend.' };
    const needles = [subject && subject.name, subject && subject.ticker]
      .filter(function (s) { return s && String(s).trim().length >= 2; });
    for (const needle of needles) {
      const re = new RegExp('\\b' + String(needle).trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b', 'i');
      if (re.test(text)) {
        return {
          valid: false,
          message: 'Describe the trend without naming the company. If the trend cannot be '
                 + 'stated without it, you are describing a product, not a wave.',
        };
      }
    }
    return { valid: true, message: '' };
  }

  const GENERIC_EDGE = /^(it('s| is)? (cheap|undervalued|good|great)|good company|strong company|undervalued|cheap|growth|potential|the market is wrong)\.?$/i;

  function validateEdgeStatement(statement) {
    const text = String(statement || '').trim();
    if (!text) return { valid: false, message: 'State what you understand that the market has not priced in.' };
    if (text.length > 200) return { valid: false, message: 'Keep it to one sentence, 200 characters at most.' };
    if (GENERIC_EDGE.test(text) || text.split(/\s+/).length < 4) {
      return { valid: false, message: 'That is a conclusion, not an edge. What specifically do you know?' };
    }
    return { valid: true, message: '' };
  }

  /* ---------------------------------------------------- stage completion */

  const filled = v => v !== null && v !== undefined && String(v).trim() !== '';
  const answered = v => v === 'pass' || v === 'fail';

  const STAGE_COMPLETE = {
    origin: s => filled(s.source) && String(s.anomaly || '').trim().length >= 20,
    wave: (s, t) => filled(s.trendStatement)
                 && validateTrendStatement(s.trendStatement, t.subject).valid
                 && answered(s.survivesProductFailure),
    regulatory: s => answered(s.harmTest) && answered(s.displacementTest),
    operator: function (s) {
      if (s.companyStage === 'young') {
        return filled(s.founderTrackRecord) && filled(s.commitmentLevel);
      }
      if (s.companyStage === 'mature') return answered(s.allocationFitsStage);
      return false;
    },
    insiders: s => answered(s.circularityCheck) && filled(s.insiderBuying),
    informationEdge: s => validateEdgeStatement(s.edgeStatement).valid,
    numbers: s => !!(s.marketCap && s.impliedValuation5y),
    killAttempt: (s, t) => (s.failureReasons || []).filter(filled).length >= 3
                        && filled(s.haloTest) && (t.breakConditions || []).length >= 1,
    portfolio: s => answered(s.totalLossTolerable) && Number(s.holdingPeriodYears) > 0,
  };

  function isStageComplete(thesis, index) {
    const id = STAGE_IDS[index];
    return !!STAGE_COMPLETE[id](thesis.stages[id], thesis);
  }

  /* -------------------------------------------------------- hard gates */

  /* Each gate reports pass / fail / unknown. `unknown` never blocks movement
     but does prevent the thesis reaching `active` (spec section 4 rule 2). */
  const HARD_GATES = [
    { id: 'wave.survivesProductFailure', stage: 1,
      read: t => t.stages.wave.survivesProductFailure,
      message: 'You are betting on a single product, not a trend. That is a different, '
             + 'riskier bet - reframe the thesis or park it.' },
    { id: 'regulatory.harmTest', stage: 2,
      read: t => t.stages.regulatory.harmTest,
      message: 'If one incident stops the whole category, the regulatory risk sits above '
             + 'the company and no amount of execution fixes it.' },
    { id: 'regulatory.displacementTest', stage: 2,
      read: t => t.stages.regulatory.displacementTest,
      message: 'Displacing an organised, politically visible workforce invites rules '
             + 'written specifically against you.' },
    { id: 'operator.allocationFitsStage', stage: 3,
      read: t => (t.stages.operator.companyStage === 'mature'
                  ? t.stages.operator.allocationFitsStage : 'pass'),
      message: 'Returning cash is discipline for a stable cash machine and avoidance for a '
             + 'stagnating one. Decide which this is.' },
    { id: 'informationEdge.edgeStatement', stage: 5,
      read: t => (validateEdgeStatement(t.stages.informationEdge.edgeStatement).valid
                  ? 'pass' : 'fail'),
      message: 'Without a specific edge you are paying the same price as everyone else for '
             + 'the same information.' },
    { id: 'killAttempt.failureReasons', stage: 7,
      read: t => ((t.stages.killAttempt.failureReasons || []).filter(filled).length >= 3
                  ? 'pass' : 'fail'),
      message: 'Fewer than three means you have not dug deep enough.' },
    { id: 'killAttempt.breakConditions', stage: 7,
      read: t => ((t.breakConditions || []).length >= 1 ? 'pass' : 'fail'),
      message: 'Without a written break condition there is nothing to hold you to later.' },
    { id: 'portfolio.totalLossTolerable', stage: 8,
      read: t => t.stages.portfolio.totalLossTolerable,
      message: 'If a total loss on this position would change your behaviour, the position '
             + 'is too large for this framework.' },
  ];

  function gateResults(thesis) {
    return HARD_GATES.map(function (g) {
      return { id: g.id, stage: g.stage, answer: g.read(thesis), message: g.message };
    });
  }

  /* ---------------------------------------------------------- warnings */

  function warningsFor(thesis, allTheses) {
    const w = [];
    const s = thesis.stages;
    const add = (id, level, text) => w.push({ id, level, text });

    if (['tip-or-recommendation', 'mainstream-coverage', 'social-trend'].indexOf(s.origin.source) >= 0) {
      add('origin.channel', 'warning',
          'This idea arrived through a channel everyone else also sees. You will need an '
        + 'unusually strong answer in Stage 5.');
    }

    const horizon = Number(s.wave.horizonYears);
    const holding = Number(s.portfolio.holdingPeriodYears);
    if (horizon > 0 && holding > 0 && horizon < holding) {
      add('wave.horizonMismatch', 'warning',
          'The trend is expected to run ' + horizon + ' years but you intend to hold for '
        + holding + '. One of the two numbers is wrong.');
    }

    if (s.insiders.circularityCheck === 'fail') {
      add('insiders.circularity', 'badge',
          'Circular funding: a large backer is also a supplier funding its own customer. An '
        + 'apparent vote of confidence may be revenue recycling.');
    }

    const coverage = Number(s.informationEdge.analystCoverage);
    const obscurity = s.informationEdge.obscurityReason || [];
    const noObscurity = obscurity.length === 0 || (obscurity.length === 1 && obscurity[0] === 'none');
    if (noObscurity && coverage > 10) {
      add('edge.wellCovered', 'warning',
          'This is a well-covered name. Your edge claim needs to be unusually specific.');
    }
    if (coverage >= 0 && coverage <= 2 && filled(s.informationEdge.analystCoverage)) {
      add('edge.noCoverage', 'warning',
          'No coverage is both your opportunity and your exposure. Nobody else is checking '
        + "the company's claims either.");
    }

    const upside = upsideMultiple(thesis);
    if (upside !== null && upside < 5) {
      add('numbers.upside', 'warning',
          'Below the 5x / 5-year bar this framework is built around. At this upside the '
        + 'risk-reward does not justify the volatility of a small position.');
    }

    const reliance = guidanceReliance(thesis);
    if (reliance !== null && reliance > 0.5) {
      add('numbers.guidance', 'badge',
          "Most of this thesis rests on management's own forecasts. Management is "
        + 'incentivised to be optimistic, and forecasts are not audited.');
    }

    const runway = Number(s.numbers.runwayMonths);
    if (runway > 0 && runway < 18) {
      add('numbers.runway', 'warning',
          'Under 18 months of runway. A forced raise at a bad price dilutes you.');
    }

    if (allTheses) w.push.apply(w, portfolioWarnings(thesis, allTheses));
    return w;
  }

  function upsideMultiple(thesis) {
    const n = thesis.stages.numbers;
    if (!n.marketCap || !n.impliedValuation5y) return null;
    const cap = Number(n.marketCap.value), implied = Number(n.impliedValuation5y.value);
    if (!cap || cap <= 0) return null;
    return implied / cap;
  }

  const NUMERIC_FIELDS = ['marketCap', 'currentRevenue', 'growthRate',
                          'projectedRevenue5y', 'impliedValuation5y', 'cashPosition'];

  function guidanceReliance(thesis) {
    const n = thesis.stages.numbers;
    const present = NUMERIC_FIELDS.map(k => n[k]).filter(Boolean);
    if (!present.length) return null;
    const guided = present.filter(v => v.source === 'company-guidance').length;
    return guided / present.length;
  }

  function portfolioWarnings(thesis, allTheses) {
    const out = [];
    const active = (allTheses || []).filter(t => t.status === 'active');
    if (active.length && active.length < 5) {
      out.push({ id: 'portfolio.count', level: 'warning',
        text: 'This framework assumes roughly ten comparable positions, on the explicit '
            + 'expectation that several go to zero. With ' + active.length + ', you are '
            + 'running a concentrated bet - a different and less forgiving model.' });
    }
    const sizes = active.map(t => Number(t.stages.portfolio.positionSizePct))
                        .filter(v => v > 0);
    if (sizes.length > 1) {
      const mean = sizes.reduce((a, b) => a + b, 0) / sizes.length;
      const mine = Number(thesis.stages.portfolio.positionSizePct);
      if (mine > mean * 2) {
        out.push({ id: 'portfolio.dominant', level: 'warning',
          text: 'One position dominates. Power-law logic requires comparable sizing at entry.' });
      }
    }
    const holding = Number(thesis.stages.portfolio.holdingPeriodYears);
    if (holding > 0 && holding < 5) {
      out.push({ id: 'portfolio.horizon', level: 'warning',
        text: 'The framework assumes five years or more.' });
    }
    return out;
  }

  /* ----------------------------------------------------- gating engine */

  function evaluate(thesis, allTheses) {
    const gates = gateResults(thesis);
    const failed = gates.filter(g => g.answer === 'fail');
    const unknown = gates.filter(g => g.answer === 'unknown');

    const stages = STAGE_IDS.map(function (id, i) {
      const gatesHere = gates.filter(g => g.stage === i);
      const blockedHere = gatesHere.filter(g => g.answer === 'fail');
      const earlierFail = failed.filter(g => g.stage < i).length > 0;
      const priorComplete = STAGE_IDS.slice(0, i).every((_, j) => isStageComplete(thesis, j));
      return {
        index: i,
        id: id,
        title: STAGE_TITLES[i],
        complete: isStageComplete(thesis, i),
        gates: gatesHere,
        blocked: blockedHere.length > 0,
        blockedBy: blockedHere.map(g => g.id),
        stale: (thesis.staleStages || []).indexOf(i) >= 0,
        reachable: i === 0 || (priorComplete && !earlierFail),
      };
    });

    const allComplete = stages.every(s => s.complete);
    const canBeActive = allComplete && failed.length === 0 && unknown.length === 0
                     && (thesis.breakConditions || []).length >= 1;

    return {
      stages: stages,
      gates: gates,
      failedGates: failed,
      unknownGates: unknown,
      warnings: warningsFor(thesis, allTheses),
      allComplete: allComplete,
      canBeActive: canBeActive,
      upsideMultiple: upsideMultiple(thesis),
      guidanceReliance: guidanceReliance(thesis),
    };
  }

  function canAdvance(thesis, fromStage) {
    const ev = evaluate(thesis);
    const here = ev.stages[fromStage];
    const blockedBy = ev.failedGates.filter(g => g.stage <= fromStage).map(g => g.id);
    return {
      allowed: !!here && here.complete && blockedBy.length === 0 && fromStage < 8,
      blockedBy: blockedBy,
      warnings: ev.warnings,
    };
  }

  /* Section 4 rule 3: editing an earlier stage re-runs every gate. A gate that
     now fails drops the thesis to `blocked` and marks the later stages stale -
     visible, never deleted. */
  function reconcile(thesis, allTheses) {
    const ev = evaluate(thesis, allTheses);
    const firstFail = ev.failedGates.length
      ? Math.min.apply(null, ev.failedGates.map(g => g.stage)) : null;

    if (firstFail !== null) {
      const stale = [];
      for (let i = firstFail + 1; i <= thesis.highestStageCompleted; i++) stale.push(i);
      thesis.staleStages = stale;
      if (thesis.status !== 'killed') thesis.status = 'blocked';
    } else {
      thesis.staleStages = [];
      if (thesis.status === 'blocked') {
        thesis.status = ev.canBeActive ? 'active' : 'draft';
      } else if (thesis.status === 'draft' && ev.canBeActive) {
        thesis.status = 'active';
      }
    }
    return thesis;
  }

  /* ----------------------------------------------------------- journal */

  function getPath(obj, path) {
    return path.split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
  }

  function setPath(obj, path, value) {
    const keys = path.split('.');
    const last = keys.pop();
    const target = keys.reduce(function (o, k) {
      if (o[k] === null || typeof o[k] !== 'object') o[k] = {};
      return o[k];
    }, obj);
    target[last] = value;
  }

  /* Every change is appended, never overwritten. This is what makes hindsight
     bias visible: the review screen reads the ORIGINAL wording back out of
     here, not the current text. */
  function applyChange(thesis, path, value, note) {
    const from = getPath(thesis, path);
    if (JSON.stringify(from) === JSON.stringify(value)) return thesis;
    thesis.journal.push({
      id: uid(), at: nowIso(), field: path, from: from, to: value, note: note || '',
    });
    setPath(thesis, path, value);
    thesis.updatedAt = nowIso();
    return thesis;
  }

  /* The earliest value ever recorded for a field, for the review screen. */
  function originalValue(thesis, path) {
    const first = (thesis.journal || []).filter(e => e.field === path)[0];
    return first ? first.from : getPath(thesis, path);
  }

  /* --------------------------------------------------------- reframing */

  /* Spec section 2: on a regulatory block, the trend was right and the vehicle
     was wrong. Carrying the trend statement into a fresh draft is described as
     the most valuable interaction in the module. */
  function reframe(thesis) {
    const draft = newThesis();
    draft.derivedFrom = thesis.id;
    draft.stages.wave.trendStatement = thesis.stages.wave.trendStatement;
    draft.stages.wave.horizonYears = thesis.stages.wave.horizonYears;
    draft.stages.wave.wavePosition = thesis.stages.wave.wavePosition;
    draft.journal.push({
      id: uid(), at: nowIso(), field: 'derivedFrom', from: null, to: thesis.id,
      note: 'Reframed after a regulatory block on ' + (thesis.subject.name || 'the original thesis'),
    });
    return draft;
  }

  /* ------------------------------------------------------------- store */

  /* The interface the spec defines. The host app supplies an implementation;
     this one keeps everything in the browser, which is also why none of it can
     reach the public repository. */
  function createLocalStore(key) {
    const KEY = key || 'thesis-gate-v1';

    function readAll() {
      try {
        return JSON.parse(global.localStorage.getItem(KEY) || '[]');
      } catch (e) {
        return [];
      }
    }

    function writeAll(rows) {
      // A silent failure in a tool whose value is the record is worse than an
      // error, so this throws rather than swallowing (spec section 5).
      global.localStorage.setItem(KEY, JSON.stringify(rows));
    }

    return {
      list: function () { return Promise.resolve(readAll()); },
      get: function (id) {
        return Promise.resolve(readAll().filter(t => t.id === id)[0] || null);
      },
      create: function (t) {
        const rows = readAll();
        const record = Object.assign(newThesis(), t, { id: uid(), createdAt: nowIso(), updatedAt: nowIso() });
        rows.push(record);
        writeAll(rows);
        return Promise.resolve(record);
      },
      save: function (thesis) {
        const rows = readAll();
        const i = rows.findIndex(r => r.id === thesis.id);
        thesis.updatedAt = nowIso();
        if (i >= 0) rows[i] = thesis; else rows.push(thesis);
        writeAll(rows);
        return Promise.resolve(thesis);
      },
      update: function (id, patch) {
        const rows = readAll();
        const i = rows.findIndex(r => r.id === id);
        if (i < 0) return Promise.reject(new Error('No thesis ' + id));
        rows[i] = Object.assign({}, rows[i], patch, { updatedAt: nowIso() });
        writeAll(rows);
        return Promise.resolve(rows[i]);
      },
      // Never a hard delete. The record of what was rejected and why is the point.
      archive: function (id, reason) {
        const rows = readAll();
        const i = rows.findIndex(r => r.id === id);
        if (i < 0) return Promise.reject(new Error('No thesis ' + id));
        rows[i].status = 'killed';
        rows[i].killedReason = reason;
        rows[i].updatedAt = nowIso();
        rows[i].journal.push({ id: uid(), at: nowIso(), field: 'status',
                               from: 'active', to: 'killed', note: reason });
        writeAll(rows);
        return Promise.resolve();
      },
    };
  }

  /* -------------------------------------------------------------- review */

  const REVIEW_DAYS = 90;

  function daysSinceReview(thesis) {
    const last = (thesis.reviews || []).slice(-1)[0];
    const from = last ? last.date : thesis.createdAt;
    return Math.floor((Date.now() - new Date(from).getTime()) / 86400000);
  }

  function reviewDue(thesis, days) {
    return thesis.status === 'active' && daysSinceReview(thesis) >= (days || REVIEW_DAYS);
  }

  global.ThesisGateCore = {
    STAGE_IDS, STAGE_TITLES, HARD_GATES, REVIEW_DAYS,
    newThesis, sourcedNumber, uid,
    validateBreakCondition, validateTrendStatement, validateEdgeStatement,
    isStageComplete, evaluate, canAdvance, reconcile,
    applyChange, originalValue, getPath, setPath,
    reframe, createLocalStore,
    upsideMultiple, guidanceReliance, portfolioWarnings,
    daysSinceReview, reviewDue,
  };
})(typeof window !== 'undefined' ? window : globalThis);
