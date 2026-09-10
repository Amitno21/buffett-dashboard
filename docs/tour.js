/* Guided tour.

   Two jobs, and the second matters more than the first: explain what each panel
   is, and explain the ORDER to read them in. The dashboard's failure mode for a
   newcomer is landing on a table of numbers and treating the biggest one as the
   most important. The tour exists to say: quality and price are separate
   questions, and the market context comes before either. */

(function (global) {
  'use strict';

  const SEEN_KEY = 'bd-tour-seen';

  const STEPS = [
    {
      tab: null, target: null,
      title: 'What this is',
      body: 'A dashboard that reads company filings and applies Warren Buffett\'s published '
          + 'criteria to them, rebuilt every night. Nothing here is advice. It reports what '
          + 'the filings say and shows its arithmetic, so you can disagree with any of it.\n\n'
          + 'This tour takes about two minutes and explains the order things are best read in.',
    },
    {
      tab: null, target: '#weather',
      title: 'Start here: what kind of market is it?',
      body: 'Before looking at any single company, look at the weather. The Buffett Indicator '
          + 'compares the value of the whole stock market with the size of the economy. Around '
          + '100% is historically normal.\n\nThe 10-year Treasury next to it is the return you '
          + 'can get risk-free. Buffett calls it gravity: every share has to beat it, or you '
          + 'should just buy the bond instead.',
    },
    {
      tab: 'signals', target: null,
      title: 'Today: what actually changed',
      body: 'Your daily stop. Price shocks, new filings, anything that crossed into or out of '
          + 'value territory, and any trades Berkshire made.\n\nMost days this is quiet, and '
          + 'that is the correct result. A portfolio meant to be held for years should not '
          + 'need action every morning.',
    },
    {
      tab: 'companies', target: null,
      title: 'Companies: two separate questions',
      body: 'This is the heart of it, and the one place people misread. Every row answers two '
          + 'independent questions:\n\n'
          + 'QUALITY (0-100) - is this a good business? Costco scores 98.\n'
          + 'VERDICT - is the price sensible right now?\n\n'
          + 'They do not move together. A superb business at a silly price is still a bad '
          + 'purchase, and the table will happily show you one.',
    },
    {
      tab: 'companies', target: '#view-toggle',
      title: 'Not a numbers person? Press this',
      body: 'This swaps the table for plain-English cards - each company described in a '
          + 'sentence or two, cheapest against its estimate first. Same data, no jargon.',
    },
    {
      tab: 'companies', target: 'tbody tr',
      title: 'Click any row for the reasoning',
      body: 'Opens the full breakdown: which of the seven tests the company passed and failed, '
          + 'ten years of history, and a valuation you can argue with.\n\n'
          + 'Inside, drag the sliders. Watching the "worth" of a company swing by hundreds of '
          + 'dollars a share when you change one assumption is the most honest thing on this '
          + 'dashboard.',
    },
    {
      tab: 'etfs', target: null,
      title: 'ETFs: the benchmark that has to be beaten',
      body: 'Buffett instructed that his own estate go 90% into a low-cost S&P 500 index fund. '
          + 'That is the standard everything else here competes with.\n\nIf picking individual '
          + 'companies does not beat simply buying the index - after the effort and the '
          + 'mistakes - then the index was the better answer. This tab keeps that visible '
          + 'rather than buried.',
    },
    {
      tab: 'berkshire', target: null,
      title: 'Berkshire: what he actually did',
      body: 'His real holdings and what changed last quarter, straight from the regulatory '
          + 'filing. Worth reading against the Companies tab.\n\nOne caveat the panel repeats: '
          + 'a 13F filing arrives up to 45 days late and only covers US-listed shares. It is a '
          + 'delayed, partial view, never a live portfolio.',
    },
    {
      tab: 'israel', target: null,
      title: 'Israel: local context',
      body: 'Tel Aviv indices, the shekel, money-market funds and hedge funds.\n\nNote the '
          + 'money-market yield: that is roughly what cash earns you for almost no risk, and '
          + 'it is the number any riskier idea has to beat before it is worth the worry.',
    },
    {
      tab: 'thesis', target: null,
      title: 'Thesis Gate: for your own ideas',
      body: 'The rest of the dashboard analyses companies for you. This does the opposite - it '
          + 'interrogates you.\n\nWrite down an investment idea and walk it through eight '
          + 'stages. Weak reasoning gets stopped early rather than rationalised later, and '
          + 'everything you write is kept so you can see later what you actually thought at '
          + 'the time. It never leaves your browser.',
    },
    {
      tab: null, target: '#glossary',
      title: 'Every term, explained',
      body: 'At the foot of every page. Sixty-plus concepts in plain language, ordered the way '
          + 'the dashboard reasons rather than alphabetically.\n\nIf a word anywhere on this '
          + 'site is unfamiliar, it is defined down here. That is enforced by a test.',
    },
    {
      tab: null, target: null,
      title: 'The order that works',
      body: '1. Weather - is the market expensive?\n'
          + '2. Today - did anything change?\n'
          + '3. Companies - good business, sensible price? Two questions.\n'
          + '4. ETFs - would the index have done this more simply?\n'
          + '5. Thesis Gate - can my own idea survive being attacked?\n\n'
          + 'You can restart this tour any time from the button beside the title.',
    },
  ];

  let index = 0;
  let root = null;

  function el(tag, cls, html) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  }

  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function paragraphs(text) {
    return esc(text).split('\n\n').map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`).join('');
  }

  function start(fromButton) {
    index = 0;
    if (!root) {
      root = el('div', 'tour-root');
      document.body.appendChild(root);
    }
    root.hidden = false;
    show();
    try { localStorage.setItem(SEEN_KEY, '1'); } catch (e) { /* private mode */ }
  }

  function stop() {
    if (root) root.hidden = true;
    clearSpot();
  }

  function clearSpot() {
    document.querySelectorAll('.tour-lit').forEach(n => n.classList.remove('tour-lit'));
  }

  function show() {
    const step = STEPS[index];
    if (!step) return stop();

    if (step.tab) {
      const btn = document.querySelector(`nav.tabs button[data-tab="${step.tab}"]`);
      if (btn) btn.click();
    }

    // Let the tab render before measuring anything.
    setTimeout(function () {
      clearSpot();
      let target = null;
      if (step.target) {
        target = step.tab
          ? document.querySelector(`#tab-${step.tab} ${step.target}`) || document.querySelector(step.target)
          : document.querySelector(step.target);
      }
      if (target) {
        target.classList.add('tour-lit');
        target.scrollIntoView({ block: 'center', behavior: 'smooth' });
      } else {
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }

      root.innerHTML = `
        <div class="tour-backdrop" data-tour-skip></div>
        <div class="tour-box" role="dialog" aria-label="${esc(step.title)}">
          <div class="tour-count">Step ${index + 1} of ${STEPS.length}</div>
          <h3>${esc(step.title)}</h3>
          ${paragraphs(step.body)}
          <div class="tour-nav">
            <button class="icon-btn" data-tour-skip>Skip</button>
            <span class="tour-dots">${STEPS.map((_, i) =>
              `<i class="${i === index ? 'on' : ''}"></i>`).join('')}</span>
            <span style="flex:1"></span>
            <button class="icon-btn" data-tour-prev ${index === 0 ? 'disabled' : ''}>Back</button>
            <button class="icon-btn tg-primary" data-tour-next>${
              index === STEPS.length - 1 ? 'Done' : 'Next'}</button>
          </div>
        </div>`;

      root.querySelectorAll('[data-tour-skip]').forEach(b => { b.onclick = stop; });
      root.querySelector('[data-tour-prev]').onclick = () => { index = Math.max(0, index - 1); show(); };
      root.querySelector('[data-tour-next]').onclick = () => {
        if (index >= STEPS.length - 1) return stop();
        index++; show();
      };
    }, step.tab ? 160 : 0);
  }

  function seen() {
    try { return localStorage.getItem(SEEN_KEY) === '1'; } catch (e) { return true; }
  }

  document.addEventListener('keydown', e => {
    if (!root || root.hidden) return;
    if (e.key === 'Escape') stop();
    if (e.key === 'ArrowRight') { if (index < STEPS.length - 1) { index++; show(); } }
    if (e.key === 'ArrowLeft') { if (index > 0) { index--; show(); } }
  });

  global.Tour = { start, stop, seen, steps: STEPS };
})(window);
