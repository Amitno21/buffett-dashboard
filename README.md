# Amit Dashboard

A daily value-investing dashboard built entirely from public filings. It applies
Buffett's published criteria to ten years of SEC data, estimates what each
business is worth, and tells you what changed in the last 24 hours.

**It is not investment advice.** It reports numbers and shows its working. Every
score decomposes into the figures that produced it, and every valuation exposes
its assumptions so you can disagree with them.

---

## What is on it

| Panel | What it answers |
| --- | --- |
| **Market Weather** | What regime am I operating in? Buffett Indicator, the 10-year Treasury, S&P 500, VIX. |
| **Today** | What changed in 24 hours? Price shocks, valuation crossings, new filings, 52-week lows, Berkshire trades. |
| **Companies** | Is this a good business, and is it cheap? Quality score out of 100, owner earnings, intrinsic value, margin of safety. |
| **S&P 500 screen** | What else should I look at? A coarse return-on-equity screen over all 500 constituents. |
| **Berkshire** | What is Buffett actually doing? Latest 13F holdings and quarter-on-quarter changes. |
| **My positions** | Does my thesis still hold? Your holdings re-checked against the same criteria. |
| **Israel** | Tel Aviv indices, the shekel, Israeli money-market and hedge funds. |
| **Learn** | One principle a day, with the letter it comes from. |
| **Glossary** | Every term on the page, explained for someone new to investing. |

Click any company row for the full scoring breakdown, a ten-year history, and a
**discounted cash flow with sliders** — move the growth and discount assumptions
and watch the answer move. That sensitivity is the point: it shows how much of
any valuation is assumption rather than fact.

---

## The scoring

Seven components, 100 points. Nothing is hidden; each one reports the raw figure
it was computed from.

| Component | Points | Full marks at |
| --- | --- | --- |
| Return on equity | 20 | 18%+ average over ten years |
| ROE consistency | 10 | Every year above 15% |
| Margin stability (moat proxy) | 15 | Gross margin varying under 3% |
| Debt burden | 15 | Long-term debt under 1x owner earnings |
| Owner-earnings growth | 15 | 12% a year |
| Earnings consistency | 15 | No year with a fall over 10% |
| One-dollar premise | 10 | Each $1 retained creating $1.50 of market value |

**Owner earnings** follow Buffett's 1986 definition: net income, plus
depreciation and other non-cash charges including impairments, less the capital
expenditure needed to maintain the business. Maintenance capex is never
disclosed, so it uses the standard `min(capex, depreciation)` proxy — an
estimate, and labelled as one throughout.

Two automatic caveats are raised where the criteria do not transfer:

- **Banks and insurers** have no gross margin or maintenance capex, so two
  components score zero for reasons unrelated to quality.
- **Companies with negative book equity** from years of buybacks get return on
  invested capital scored instead of return on equity, which would otherwise
  print meaningless figures like Mastercard's 193%.

---

## Data sources

All free, none needing an API key.

| Source | Used for |
| --- | --- |
| `data.sec.gov` company facts | Ten years of financials per company |
| `data.sec.gov` XBRL frames | The S&P 500 screen — one request covers every filer |
| `sec.gov` 13F filings | Berkshire's holdings |
| Yahoo Finance chart API | Daily prices, moving averages, RSI |
| FRED (`fredgraph.csv`) | 10-year Treasury, Buffett Indicator inputs |
| `datasets/s-and-p-500-companies` | Index constituents |
| `funder.co.il` | Israeli money-market and hedge funds (digest, full lists linked) |
| Yahoo Finance | TA-125, TA-35 and the shekel rate |

### A note on the Israeli data

`funder.co.il` embeds each table as JSON in the page, so `scripts/israel.py`
reads that directly rather than parsing markup. Two things shaped it:

- **Index levels are never in the served HTML.** The page fills them from a live
  feed after JavaScript runs; the static copy carries zeros and `"miss"`
  placeholders. Levels therefore come from Yahoo, which agrees with funder to
  the decimal on TA-125.
- **Only a digest of each table is stored**, not the whole database. The twelve
  largest money-market funds and twelve best-performing hedge funds are kept,
  with every panel linking back to the full list on funder.co.il.

None of the Buffett scoring applies to these instruments — they are funds, not
operating businesses, with no accounts to read and no owner earnings to value.
The interface says so on the panel itself.

Two quirks worth knowing, both handled in `scripts/common.py`: FRED stalls on a
browser-style `User-Agent` and needs a curl-like minimal header set, while Yahoo
returns 429 without one. Hence the per-source header profiles.

---

## Setup

### 1. Create the repository

```bash
gh repo create buffett-dashboard --public --source=. --remote=origin --push
```

Pages serves a private repository only on a paid plan, which is why this is
public. The repository holds no personal data as shipped — but if you add real
holdings to `positions` in `watchlist.json`, they become public too. Keep that
section empty, or move to a private repo and view the dashboard locally.

### 2. Turn on GitHub Pages

Settings → Pages → Source: **Deploy from a branch** → branch `main`, folder
`/docs`. The dashboard appears at `https://<you>.github.io/buffett-dashboard/`.

### 3. Identify yourself to the SEC

The SEC asks for a contact address in the `User-Agent`:

```bash
gh secret set SEC_CONTACT --body "you@example.com"
```

A secret rather than a variable, so the address stays out of the build logs,
which are public on a public repository. Without it the build still runs, using
a placeholder address.

### 4. Let it run

The workflow runs at **07:10 UTC daily**, and can be triggered by hand from the
Actions tab. It commits the refreshed `docs/data/latest.json` back to the repo,
which is what updates the live page.

---

## Running it locally

```bash
python scripts/build.py
```

No dependencies — the standard library only. Useful flags:

```bash
python scripts/build.py --limit 5      # only the first five companies
python scripts/build.py --force        # ignore the fundamentals cache
python scripts/build.py --skip-screen  # skip the S&P 500 screen
```

Then serve the page:

```bash
python -m http.server 8731 --directory docs
```

Run the tests:

```bash
python scripts/test_pipeline.py
```

---

## Configuring it

Everything lives in `watchlist.json`.

```jsonc
{
  "watchlist": ["AAPL", "KO", "MSFT"],     // deep ten-year analysis on each
  "positions": [
    { "ticker": "AAPL", "shares": 100, "cost_basis": 175.50 }
  ],
  "settings": {
    "margin_of_safety_pct": 30,   // discount you demand below estimated value
    "discount_rate_pct": 10.0,    // DCF hurdle rate
    "terminal_growth_pct": 2.5,   // growth assumed in perpetuity
    "big_move_pct": 5.0,          // daily move that raises a signal
    "max_berkshire_holdings": 25  // how many of Berkshire's positions to analyse
  },
  "shares_override": {
    "V": 1950000000               // see below
  }
}
```

The universe is your watchlist **plus** Berkshire's largest holdings,
deduplicated by company so share classes like GOOGL and GOOG are not analysed
twice.

### Why `shares_override` exists

The SEC's companyfacts API returns only undimensioned facts. Companies that
report share counts per share class — Visa is the common example — therefore
expose no single total, and the only figure that survives is a stale cover-page
number from 2009. Rather than value a company off a share count a sixth of its
real size, the pipeline rejects any count more than three years old and marks
the valuation unavailable. Supplying the diluted count here fixes it.

---

## Limitations

Worth being honest about:

- **The circle of competence cannot be automated.** Whether you understand a
  business is the one filter no dashboard can apply for you, and Buffett treats
  it as the one that matters most.
- **Maintenance capex is estimated**, not reported.
- **A 13F is delayed** by up to 45 days and covers US-listed equities only.
- **The screen is single-year and coarse.** It generates a shortlist; anything
  interesting needs the full ten-year workup.
- **Terminal value is typically half or more** of any DCF result, which means
  most of the "value" rests on an assumption about the distant future. The
  drawer shows that share explicitly.
- **Quality and cheapness are different questions.** A score of 98 says nothing
  about whether the price is sensible.

---

## Layout

```
scripts/
  common.py         config, HTTP with per-source header profiles, helpers
  edgar.py          SEC company facts, XBRL frames, 13F parsing
  market.py         Yahoo prices, FRED macro, market weather
  metrics.py        owner earnings, quality scoring, DCF
  principles.py     the rotating daily principle
  build.py          orchestrator, caching, signals -> docs/data/latest.json
  test_pipeline.py  38 tests, standard library only
docs/               the published site (GitHub Pages root)
  index.html  app.js  styles.css  data/latest.json
watchlist.json      everything you configure
```
