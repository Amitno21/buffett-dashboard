"""Nightly build: fetch everything, score it, and write the dashboard payload.

Run with `python scripts/build.py`. Writes docs/data/latest.json, rotating the
previous run to docs/data/previous.json so the signals feed can diff the two.

The expensive call is companyfacts, which runs to several megabytes per filer.
It is therefore cached under cache/fundamentals and only refetched when the
company's submissions feed shows a filing we have not already processed.
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import traceback
from datetime import datetime, timezone

import edgar
import market
import metrics
from common import (CACHE, DATA, FUND, FetchError, fetch, load_config,
                    read_json, safe_div, write_json)
from principles import principle_of_the_day

SP500_URL = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"


def log(message: str) -> None:
    print(f"  {message}", flush=True)


# --------------------------------------------------------------------------- #
# Per-company analysis
# --------------------------------------------------------------------------- #

def load_fundamentals(ticker: str, cik: int, force: bool = False) -> tuple[dict, list[dict], bool]:
    """Return (financials, recent_filings, refreshed).

    Uses the submissions feed as a cheap change detector: it is roughly 40x
    smaller than companyfacts, so most nights we download only that.
    """
    cache_path = FUND / f"{ticker}.json"
    cached = read_json(cache_path, {}) or {}

    try:
        subs = edgar.submissions(cik)
    except FetchError:
        return cached.get("financials", {}), cached.get("filings", []), False

    filings = edgar.latest_filings(subs, ("10-K", "10-Q", "8-K", "4"), limit=12)
    reports = [f for f in filings if f["form"].startswith(("10-K", "10-Q"))]
    latest_accession = reports[0]["accession"] if reports else ""

    if not force and cached.get("accession") == latest_accession and cached.get("financials"):
        return cached["financials"], filings, False

    try:
        financials = edgar.extract_financials(edgar.company_facts(cik))
    except FetchError:
        return cached.get("financials", {}), filings, False

    write_json(cache_path, {
        "ticker": ticker,
        "cik": cik,
        "accession": latest_accession,
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "financials": financials,
        "filings": filings,
    })
    return financials, filings, True


def analyse(ticker: str, info: dict, settings: dict, force: bool = False,
            overrides: dict | None = None) -> dict | None:
    """Full Buffett workup for one company."""
    cik = info["cik"]
    financials, filings, refreshed = load_fundamentals(ticker, cik, force=force)
    if not financials:
        log(f"{ticker}: no financial data, skipped")
        return None

    derived = metrics.build_series(financials)
    prices = market.price_history(ticker, rng="10y")
    shares, shares_source = metrics.share_count(financials)

    # A manually supplied count wins: it is the only way to value multi-class
    # filers whose share data never reaches the companyfacts API.
    override = (overrides or {}).get(ticker)
    if isinstance(override, (int, float)) and override > 0:
        shares, shares_source = float(override), "manual override in watchlist.json"

    price = prices.get("price")

    market_cap = price * shares if price and shares else None
    market_cap_then = prices.get("first_close") * shares if prices.get("first_close") and shares else None

    quality = metrics.quality_score(
        financials, derived, market_cap, market_cap_then,
        value_since=prices.get("first_date"),
    )
    value = metrics.valuation(derived, financials, price, shares, settings)

    latest_year = max(derived.get("roe", {}) or [0])
    # Report whichever return measure was actually scored. A company with book
    # equity near zero prints an ROE that describes its buyback history rather
    # than its profitability, so the table should show return on capital there.
    basis = quality.get("return_basis", "roe")
    return_series = derived.get(basis if basis == "roic" else "roe", {})
    return_pct = (round(return_series.get(latest_year) * 100, 1)
                  if return_series.get(latest_year) is not None else None)

    return {
        "ticker": ticker,
        "name": info.get("title", ticker),
        "cik": cik,
        "refreshed_fundamentals": refreshed,
        "shares": shares,
        "shares_source": shares_source,
        "price": prices or {},
        "quality": quality,
        "valuation": value,
        "series": {k: {str(y): round(v, 6) if abs(v) < 1000 else round(v, 0)
                       for y, v in series.items()}
                   for k, series in derived.items()},
        "latest": {
            "year": latest_year or None,
            "return_pct": return_pct,
            "return_basis": basis.upper(),
            "roe_pct": round(derived.get("roe", {}).get(latest_year, 0) * 100, 1) if latest_year else None,
            "roic_pct": round(derived.get("roic", {}).get(latest_year, 0) * 100, 1)
                        if derived.get("roic", {}).get(latest_year) else None,
            "gross_margin_pct": round(derived.get("gross_margin", {}).get(latest_year, 0) * 100, 1)
                                if derived.get("gross_margin", {}).get(latest_year) else None,
        },
        "filings": filings[:8],
        "edgar_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=10-K&dateb=&owner=include&count=10",
    }


# --------------------------------------------------------------------------- #
# Berkshire 13F
# --------------------------------------------------------------------------- #

def summarise_13f(filings: list[dict], name_index: dict[str, str]) -> dict:
    """Latest Berkshire equity book, with quarter-on-quarter changes."""
    if not filings:
        return {"available": False}

    current = filings[0]
    previous = filings[1] if len(filings) > 1 else None
    prior = {h["cusip"]: h for h in previous["holdings"]} if previous else {}

    holdings, changes = [], []
    for h in current["holdings"]:
        ticker = name_index.get(edgar.normalise_name(h["issuer"]), "")
        row = {
            "issuer": h["issuer"],
            "ticker": ticker,
            "class": h.get("class", ""),
            "value": h["value"],
            "shares": h["shares"],
            "weight_pct": round(h["value"] / current["total_value"] * 100, 2)
                          if current["total_value"] else None,
        }
        before = prior.get(h["cusip"])
        if previous:
            if not before:
                row["change"] = "new"
                changes.append({"kind": "new", "issuer": h["issuer"], "ticker": ticker,
                                "shares": h["shares"], "value": h["value"]})
            elif before["shares"] > 0:
                delta = (h["shares"] - before["shares"]) / before["shares"]
                if abs(delta) >= 0.02:
                    row["change"] = "added" if delta > 0 else "trimmed"
                    row["change_pct"] = round(delta * 100, 1)
                    changes.append({"kind": row["change"], "issuer": h["issuer"], "ticker": ticker,
                                    "change_pct": round(delta * 100, 1), "value": h["value"]})
                else:
                    row["change"] = "held"
        holdings.append(row)

    if previous:
        held = {h["cusip"] for h in current["holdings"]}
        for h in previous["holdings"]:
            if h["cusip"] not in held:
                changes.append({"kind": "exited", "issuer": h["issuer"],
                                "ticker": name_index.get(edgar.normalise_name(h["issuer"]), ""),
                                "value": h["value"]})

    return {
        "available": True,
        "period": current["period"],
        "filed": current["filed"],
        "previous_period": previous["period"] if previous else None,
        "total_value": current["total_value"],
        "position_count": len(holdings),
        "holdings": holdings,
        "changes": sorted(changes, key=lambda c: c.get("value", 0), reverse=True),
        "source": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={edgar.BERKSHIRE_CIK}&type=13F-HR",
    }


# --------------------------------------------------------------------------- #
# Broad S&P 500 screen
# --------------------------------------------------------------------------- #

def sp500_constituents() -> list[dict]:
    try:
        raw = fetch(SP500_URL).decode("utf-8", "replace")
    except FetchError:
        return read_json(CACHE / "sp500.json", []) or []
    rows = []
    for row in csv.DictReader(io.StringIO(raw)):
        cik = row.get("CIK", "").strip()
        if not cik.isdigit():
            continue
        rows.append({"ticker": row["Symbol"].strip(), "name": row.get("Security", "").strip(),
                     "sector": row.get("GICS Sector", "").strip(), "cik": int(cik)})
    if rows:
        write_json(CACHE / "sp500.json", rows)
    return rows


def broad_screen(limit: int = 40) -> dict:
    """Rank the S&P 500 on return on equity and leverage using XBRL frames.

    One frames request returns a concept for every filer at once, which is what
    makes screening 500 companies affordable. This is deliberately coarse: it
    is a shortlist generator, and anything interesting should then be pulled
    into the watchlist for the full ten-year workup.
    """
    constituents = sp500_constituents()
    if not constituents:
        return {"available": False, "reason": "Constituent list unavailable"}

    year = datetime.now(timezone.utc).year
    net_income: dict[int, float] = {}
    equity: dict[int, float] = {}
    period_used = None

    # Walk back until a period has broad coverage; the most recent calendar year
    # is sparse until filers have reported.
    for candidate in (year - 1, year - 2):
        net_income = edgar.frame("NetIncomeLoss", f"CY{candidate}")
        equity = edgar.frame("StockholdersEquity", f"CY{candidate}Q4I")
        if len(net_income) > 2000 and len(equity) > 2000:
            period_used = candidate
            break
    if not period_used:
        return {"available": False, "reason": "No populated XBRL frame found"}

    revenue = edgar.frame_with_fallback(
        ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"], f"CY{period_used}")
    debt = edgar.frame_with_fallback(
        ["LongTermDebtNoncurrent", "LongTermDebt"], f"CY{period_used}Q4I")

    rows = []
    for company in constituents:
        cik = company["cik"]
        ni, eq = net_income.get(cik), equity.get(cik)
        if ni is None or not eq or eq <= 0:
            continue
        roe = ni / eq
        leverage = safe_div(debt.get(cik, 0.0), ni) if ni > 0 else None
        rows.append({
            **company,
            "roe_pct": round(roe * 100, 1),
            "net_income": ni,
            "equity": eq,
            "revenue": revenue.get(cik),
            "debt_to_earnings": round(leverage, 1) if leverage is not None else None,
            # Coarse rank: reward return on equity, penalise heavy leverage.
            "screen_score": round(min(roe, 0.60) * 100 - min(max(leverage or 0, 0), 15) * 1.5, 1),
        })

    rows.sort(key=lambda r: r["screen_score"], reverse=True)
    return {
        "available": True,
        "period": f"FY{period_used}",
        "universe": len(constituents),
        "scored": len(rows),
        "note": "Single-year screen from XBRL frames. A shortlist, not a verdict: "
                "add anything promising to the watchlist for the full ten-year analysis.",
        "top": rows[:limit],
    }


# --------------------------------------------------------------------------- #
# Signals: what changed in the last 24 hours
# --------------------------------------------------------------------------- #

def compute_signals(companies: list[dict], previous: dict, berkshire: dict, settings: dict) -> list[dict]:
    prior = {c["ticker"]: c for c in previous.get("companies", [])}
    prior_13f = previous.get("berkshire", {}).get("period")
    big_move = settings.get("big_move_pct", 5.0)
    signals: list[dict] = []

    def emit(severity: str, ticker: str, kind: str, headline: str, detail: str = "", url: str = "") -> None:
        signals.append({"severity": severity, "ticker": ticker, "kind": kind,
                        "headline": headline, "detail": detail, "url": url})

    for c in companies:
        ticker = c["ticker"]
        price = c.get("price") or {}
        before = prior.get(ticker, {})
        change = price.get("change_pct")

        if change is not None and abs(change) >= big_move:
            emit("high" if abs(change) >= big_move * 2 else "medium", ticker, "price",
                 f"{ticker} moved {change:+.1f}%",
                 f"Now ${price.get('price')}, {price.get('from_high_pct')}% from its 52-week high.")

        band = (c.get("valuation") or {}).get("band")
        band_before = (before.get("valuation") or {}).get("band")
        if band and band_before and band != band_before:
            emit("high" if band == "Below margin of safety" else "medium", ticker, "valuation",
                 f"{ticker} moved from '{band_before}' to '{band}'",
                 f"Estimated value ${(c.get('valuation') or {}).get('base_value')}, "
                 f"margin-of-safety price ${(c.get('valuation') or {}).get('buy_below')}.")

        score = (c.get("quality") or {}).get("score")
        score_before = (before.get("quality") or {}).get("score")
        if score is not None and score_before is not None and abs(score - score_before) >= 3:
            emit("medium", ticker, "quality",
                 f"{ticker} quality score moved {score - score_before:+.1f} to {score}",
                 "A change this size usually means a fresh annual report was filed.")

        if c.get("refreshed_fundamentals"):
            newest = next((f for f in c.get("filings", []) if f["form"].startswith(("10-K", "10-Q"))), None)
            if newest:
                emit("high", ticker, "filing",
                     f"{ticker} filed a new {newest['form']}",
                     f"Filed {newest['filed']}. The scores below already reflect it.",
                     newest.get("url", ""))

        from_low = price.get("from_low_pct")
        if from_low is not None and from_low <= 1.0:
            emit("high", ticker, "price", f"{ticker} is at a 52-week low",
                 f"${price.get('price')} against a 52-week low of ${price.get('low_52w')}.")

        rsi = price.get("rsi14")
        if rsi is not None and rsi <= 30:
            emit("low", ticker, "technical", f"{ticker} RSI is {rsi}",
                 "Conventionally oversold. A short-term signal, not a valuation one.")

    if berkshire.get("available") and berkshire.get("period") != prior_13f and prior_13f is not None:
        for change in berkshire.get("changes", [])[:10]:
            label = {"new": "opened", "exited": "exited", "added": "added to", "trimmed": "trimmed"}
            emit("high", change.get("ticker", ""), "berkshire",
                 f"Berkshire {label.get(change['kind'], change['kind'])} {change['issuer'].title()}",
                 f"From the 13F for {berkshire.get('period')}.", berkshire.get("source", ""))

    order = {"high": 0, "medium": 1, "low": 2}
    signals.sort(key=lambda s: order.get(s["severity"], 3))
    return signals


# --------------------------------------------------------------------------- #
# Positions
# --------------------------------------------------------------------------- #

def value_positions(positions: list[dict], companies: list[dict]) -> dict:
    index = {c["ticker"]: c for c in companies}
    rows, total_value, total_cost = [], 0.0, 0.0
    for position in positions:
        ticker = str(position.get("ticker", "")).upper()
        shares = float(position.get("shares") or 0)
        cost = float(position.get("cost_basis") or 0)
        if not ticker or shares <= 0:
            continue
        company = index.get(ticker)
        price = ((company or {}).get("price") or {}).get("price")
        value = price * shares if price else None
        book = cost * shares
        total_value += value or 0.0
        total_cost += book
        rows.append({
            "ticker": ticker,
            "name": (company or {}).get("name", ticker),
            "shares": shares,
            "cost_basis": cost,
            "price": price,
            "value": round(value, 2) if value else None,
            "cost_total": round(book, 2),
            "gain": round(value - book, 2) if value else None,
            "gain_pct": round((value / book - 1) * 100, 1) if value and book else None,
            "quality_score": ((company or {}).get("quality") or {}).get("score"),
            "band": ((company or {}).get("valuation") or {}).get("band"),
            "tracked": company is not None,
        })
    rows.sort(key=lambda r: r.get("value") or 0, reverse=True)
    return {
        "rows": rows,
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_gain": round(total_value - total_cost, 2),
        "total_gain_pct": round((total_value / total_cost - 1) * 100, 1) if total_cost else None,
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #

def build(limit: int | None = None, force: bool = False, skip_screen: bool = False) -> dict:
    started = datetime.now(timezone.utc)
    config = load_config()
    settings = config["settings"]
    overrides = {k: v for k, v in (config.get("shares_override") or {}).items()
                 if not k.startswith("_")}

    print("[1/6] Ticker map", flush=True)
    tmap = edgar.ticker_map()
    name_index = edgar.build_name_index(tmap)
    log(f"{len(tmap)} tickers")

    print("[2/6] Berkshire 13F", flush=True)
    try:
        berkshire = summarise_13f(edgar.fetch_13f(back=2), name_index)
        if berkshire.get("available"):
            log(f"{berkshire['position_count']} positions, ${berkshire['total_value'] / 1e9:.1f}bn, "
                f"{len(berkshire['changes'])} changes")
    except FetchError as exc:
        log(f"unavailable: {exc}")
        berkshire = {"available": False}

    print("[3/6] Building universe", flush=True)
    watchlist = [t.upper() for t in config["watchlist"]]
    brk_tickers = [
        h["ticker"] for h in berkshire.get("holdings", [])[:settings["max_berkshire_holdings"]]
        if h.get("ticker")
    ]
    # Deduplicate on CIK, not ticker: GOOGL and GOOG are share classes of one
    # company and would otherwise be analysed and ranked twice.
    universe: list[str] = []
    seen_ciks: set[int] = set()
    for ticker in watchlist + brk_tickers:
        info = tmap.get(ticker)
        if not info or info["cik"] in seen_ciks:
            continue
        seen_ciks.add(info["cik"])
        universe.append(ticker)
    if limit:
        universe = universe[:limit]
    log(f"{len(universe)} companies ({len(watchlist)} watchlist, {len(brk_tickers)} from Berkshire)")

    print(f"[4/6] Analysing {len(universe)} companies", flush=True)
    companies = []
    for i, ticker in enumerate(universe, 1):
        try:
            result = analyse(ticker, tmap[ticker], settings, force=force, overrides=overrides)
        except Exception as exc:  # noqa: BLE001 - one bad filer must not kill the run
            log(f"{ticker}: {type(exc).__name__}: {exc}")
            continue
        if result:
            companies.append(result)
            flag = "*" if result["refreshed_fundamentals"] else " "
            log(f"[{i:>3}/{len(universe)}] {flag} {ticker:<6} score {result['quality']['score']:>5} "
                f"{(result['valuation'] or {}).get('band', 'no valuation')}")
    companies.sort(key=lambda c: c["quality"]["score"], reverse=True)

    print("[5/6] Market weather and screen", flush=True)
    weather = market.market_weather()
    screen = {"available": False, "reason": "skipped"} if skip_screen else broad_screen()
    if screen.get("available"):
        log(f"screened {screen['scored']} of {screen['universe']} S&P 500 names for {screen['period']}")

    print("[6/6] Signals", flush=True)
    previous = read_json(DATA / "latest.json", {}) or {}
    signals = compute_signals(companies, previous, berkshire, settings)
    log(f"{len(signals)} signals")

    payload = {
        "generated_at": started.isoformat(timespec="seconds"),
        "build_seconds": round((datetime.now(timezone.utc) - started).total_seconds(), 1),
        "settings": settings,
        "weather": weather,
        "companies": companies,
        "berkshire": berkshire,
        "screen": screen,
        "signals": signals,
        "positions": value_positions(config["positions"], companies),
        "principle": principle_of_the_day(),
        "previous_generated_at": previous.get("generated_at"),
        "disclaimer": (
            "This dashboard reports public filings and applies published screening criteria. "
            "It is not investment advice, does not know your circumstances, and makes no "
            "recommendation to buy or sell anything. Every estimate here depends on assumptions "
            "that are shown alongside it and that you should judge for yourself."
        ),
    }

    if previous:
        write_json(DATA / "previous.json", previous)
    write_json(DATA / "latest.json", payload)
    return payload


def main() -> int:
    # The repository can live under a non-Latin path, and Windows consoles
    # default to cp1252. Without this a successful build dies on its own
    # closing log line.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="Build the Buffett dashboard dataset")
    parser.add_argument("--limit", type=int, help="only analyse the first N companies")
    parser.add_argument("--force", action="store_true", help="ignore the fundamentals cache")
    parser.add_argument("--skip-screen", action="store_true", help="skip the S&P 500 screen")
    args = parser.parse_args()

    try:
        payload = build(limit=args.limit, force=args.force, skip_screen=args.skip_screen)
    except Exception:  # noqa: BLE001 - surface the whole traceback in CI logs
        traceback.print_exc()
        return 1

    print(f"\nDone in {payload['build_seconds']}s: "
          f"{len(payload['companies'])} companies, {len(payload['signals'])} signals "
          f"-> docs/data/latest.json", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
