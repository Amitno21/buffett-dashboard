"""Israeli market data.

Sources, all requested by the dashboard's owner:

  funder.co.il/kaspit     shekel money-market funds  (var kaspitData)
  funder.co.il/gidurList  hedge funds held in trust  (var fundlistData)
  funder.co.il/secDash    market movers and USD/ILS  (var fxPreData)
  funder.co.il/madadim    the Tel Aviv index catalogue

funder.co.il embeds each table as a JSON blob in the page rather than as
markup, so this reads that blob directly instead of parsing HTML. Two caveats
shaped the design:

  * Index *levels* are never in the served HTML. The page fills them from a
    live feed after JavaScript runs, and the static copy carries zeros and
    "miss" placeholders. Levels therefore come from Yahoo instead, which
    agrees with funder to the decimal on TA-125, and the funder index pages
    are linked rather than copied.
  * Only a digest of each table is kept, not the whole database. The full
    lists stay on funder.co.il, which every panel links back to.

None of the Buffett scoring applies to these instruments. They are funds, not
operating businesses: there is no owner earnings figure and nothing to value.
They are reported here as published, and labelled that way in the interface.
"""
from __future__ import annotations

import json
import re

from common import FetchError, fetch

BASE = "https://www.funder.co.il"
PAGES = {
    "money_market": f"{BASE}/kaspit",
    "hedge": f"{BASE}/gidurList",
    "movers": f"{BASE}/secDash",
    "indices": f"{BASE}/madadim",
}

BACKSLASH = chr(92)

# How many rows of each table to keep. A digest, not a copy of the database.
DIGEST_ROWS = 12


# --------------------------------------------------------------------------- #
# Extracting the embedded JSON
# --------------------------------------------------------------------------- #

def _balanced(text: str, start: int, opener: str, closer: str) -> str | None:
    """Return the balanced {...} or [...] literal beginning at `start`."""
    depth, i, in_str, esc = 0, start, False, False
    while i < len(text):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == BACKSLASH:
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
        i += 1
    return None


def embedded_rows(html: str, variable: str) -> list[dict]:
    """Rows from `var <variable> = {"x": [ ... ]}` in a funder.co.il page."""
    match = re.search(rf'var\s+{re.escape(variable)}\s*=\s*(\{{)', html)
    if not match:
        return []
    blob = _balanced(html, match.start(1), "{", "}")
    if not blob:
        return []
    try:
        payload = json.loads(blob)
    except json.JSONDecodeError:
        return []
    rows = payload.get("x")
    return rows if isinstance(rows, list) else []


def _num(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean(text) -> str:
    """Fund names carry stray whitespace and directional marks."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


# --------------------------------------------------------------------------- #
# Money-market funds
# --------------------------------------------------------------------------- #

def money_market_funds() -> dict:
    """Shekel money-market funds, the closest Israeli equivalent to cash."""
    try:
        html = fetch(PAGES["money_market"]).decode("utf-8", "replace")
    except FetchError as exc:
        return {"available": False, "reason": str(exc)}

    rows = embedded_rows(html, "kaspitData")
    if not rows:
        return {"available": False, "reason": "No fund data found in the page"}

    funds = []
    for row in rows:
        funds.append({
            "name": _clean(row.get("fundName")),
            "manager": _clean(row.get("fundMng")),
            "day_pct": _num(row.get("1day")),
            "month_pct": _num(row.get("monthBegin")),
            "ytd_pct": _num(row.get("yearBegin")),
            "year_pct": _num(row.get("1year")),
            "fee_pct": _num(row.get("nihol")),
            "size_musd": _num(row.get("rSize")),      # millions of shekels
            "as_of": row.get("lastUpdate", ""),
            "url": f"{BASE}/fund/{row.get('fundNum')}" if row.get("fundNum") else "",
        })

    with_year = [f["year_pct"] for f in funds if f["year_pct"]]
    fees = [f["fee_pct"] for f in funds if f["fee_pct"] is not None]
    total_size = sum(f["size_musd"] or 0 for f in funds)

    funds.sort(key=lambda f: f["size_musd"] or 0, reverse=True)
    return {
        "available": True,
        "count": len(funds),
        "total_size_mils": round(total_size, 1),
        "median_year_pct": round(sorted(with_year)[len(with_year) // 2], 2) if with_year else None,
        "best_year_pct": round(max(with_year), 2) if with_year else None,
        "median_fee_pct": round(sorted(fees)[len(fees) // 2], 3) if fees else None,
        "as_of": funds[0]["as_of"] if funds else "",
        "rows": funds[:DIGEST_ROWS],
        "source": PAGES["money_market"],
    }


# --------------------------------------------------------------------------- #
# Hedge funds held in trust
# --------------------------------------------------------------------------- #

def hedge_funds() -> dict:
    """Israeli hedge funds sold as trust funds ("קרנות גידור בנאמנות")."""
    try:
        html = fetch(PAGES["hedge"]).decode("utf-8", "replace")
    except FetchError as exc:
        return {"available": False, "reason": str(exc)}

    rows = embedded_rows(html, "fundlistData")
    if not rows:
        return {"available": False, "reason": "No fund data found in the page"}

    funds = []
    for row in rows:
        funds.append({
            "name": _clean(row.get("fundName")),
            "manager": _clean(row.get("mng")),
            "profile": _clean(row.get("fProfile")),
            "month_pct": _num(row.get("MonthlyReturn")),
            "ytd_pct": _num(row.get("YtdReturn")),
            "year_pct": _num(row.get("YearlyReturn")),
            "two_year_pct": _num(row.get("TwoYearsReturn")),
            "three_year_pct": _num(row.get("ThreeYearsReturn")),
            "since_start_pct": _num(row.get("TotalReturn")),
            "fee_pct": _num(row.get("nihul")),
            "performance_fee_pct": _num(row.get("hatzlacha")),
            "size_mils": _num(row.get("dSIze")),
            "url": f"{BASE}/fund/{row.get('fid')}" if row.get("fid") else "",
        })

    with_year = [f["year_pct"] for f in funds if f["year_pct"] is not None]
    perf_fees = [f["performance_fee_pct"] for f in funds if f["performance_fee_pct"]]
    losers = sum(1 for v in with_year if v < 0)

    funds.sort(key=lambda f: f["year_pct"] if f["year_pct"] is not None else -999, reverse=True)
    return {
        "available": True,
        "count": len(funds),
        "with_year_history": len(with_year),
        "median_year_pct": round(sorted(with_year)[len(with_year) // 2], 2) if with_year else None,
        "best_year_pct": round(max(with_year), 2) if with_year else None,
        "worst_year_pct": round(min(with_year), 2) if with_year else None,
        "negative_year_count": losers,
        "typical_performance_fee_pct": round(sorted(perf_fees)[len(perf_fees) // 2], 1) if perf_fees else None,
        "rows": funds[:DIGEST_ROWS],
        "source": PAGES["hedge"],
    }


# --------------------------------------------------------------------------- #
# Indices and the shekel
# --------------------------------------------------------------------------- #

# Yahoo's symbols for the two headline Tel Aviv indices. TA-125 takes a caret
# and TA-35 does not; neither is guessable, so both are pinned here.
TASE_SYMBOLS = [
    ("%5ETA125.TA", "TA-125", "The 125 largest companies on the Tel Aviv exchange"),
    ("TA35.TA", "TA-35", "The 35 largest, Israel's blue-chip index"),
]


def tase_indices(price_history) -> list[dict]:
    """Index levels from Yahoo, since funder serves these only to the browser."""
    out = []
    for symbol, label, description in TASE_SYMBOLS:
        snapshot = price_history(symbol, rng="1y")
        if not snapshot:
            continue
        out.append({
            "label": label,
            "description": description,
            "price": snapshot["price"],
            "change_pct": snapshot["change_pct"],
            "from_high_pct": snapshot["from_high_pct"],
            "high_52w": snapshot["high_52w"],
            "low_52w": snapshot["low_52w"],
            "as_of": snapshot["as_of"],
        })
    return out


def shekel(price_history) -> dict:
    snapshot = price_history("ILS=X", rng="1y")
    if not snapshot:
        return {}
    return {
        "rate": snapshot["price"],
        "change_pct": snapshot["change_pct"],
        "high_52w": snapshot["high_52w"],
        "low_52w": snapshot["low_52w"],
        "as_of": snapshot["as_of"],
    }


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def snapshot(price_history) -> dict:
    """Everything on the Israel panel, with each source recorded."""
    money = money_market_funds()
    hedge = hedge_funds()
    data = {
        "money_market": money,
        "hedge": hedge,
        "indices": tase_indices(price_history),
        "shekel": shekel(price_history),
        "links": [
            {"label": "Market movers and indices", "hebrew": "עולות ויורדות", "url": PAGES["movers"]},
            {"label": "Tel Aviv index list", "hebrew": "מדדי הבורסה", "url": PAGES["indices"]},
            {"label": "Money-market funds", "hebrew": "קרנות כספיות", "url": PAGES["money_market"]},
            {"label": "Hedge funds in trust", "hebrew": "קרנות גידור בנאמנות", "url": PAGES["hedge"]},
        ],
        "attribution": "Fund data from funder.co.il, shown as a digest with the full "
                       "lists linked. Index levels and the shekel rate from Yahoo Finance.",
    }
    data["brief"] = brief(data)
    return data


def brief(data: dict) -> str:
    """A plain-English read of the Israeli panel."""
    parts: list[str] = []
    money = data.get("money_market") or {}
    hedge = data.get("hedge") or {}
    indices = data.get("indices") or []
    fx = data.get("shekel") or {}

    if indices:
        lead = indices[0]
        direction = "up" if (lead["change_pct"] or 0) >= 0 else "down"
        parts.append(
            f"{lead['label']} is {direction} {abs(lead['change_pct']):.2f}% at "
            f"{lead['price']:,.0f}, {abs(lead['from_high_pct']):.1f}% below its "
            f"12-month high.")
    if fx.get("rate"):
        parts.append(f"A dollar buys {fx['rate']:.3f} shekels.")

    if money.get("available") and money.get("median_year_pct"):
        parts.append(
            f"The {money['count']} shekel money-market funds returned a median of "
            f"{money['median_year_pct']:.2f}% over the past year, at a typical management "
            f"fee of {money['median_fee_pct']:.2f}%. These are the closest thing to cash: "
            f"very low risk, no lock-up, and the yield moves with the Bank of Israel's rate.")

    if hedge.get("available") and hedge.get("median_year_pct") is not None:
        parts.append(
            f"Among the {hedge['count']} hedge funds sold in trust, the median one-year "
            f"return was {hedge['median_year_pct']:.1f}%, spread from "
            f"{hedge['worst_year_pct']:.1f}% to {hedge['best_year_pct']:.1f}%"
            + (f", with {hedge['negative_year_count']} of {hedge['with_year_history']} losing money"
               if hedge.get("negative_year_count") else "")
            + f". Most charge a performance fee of around "
              f"{hedge['typical_performance_fee_pct']:.0f}% on top of the management fee, "
              f"so the headline return is not what reaches you.")

    parts.append(
        "None of the Buffett tests on the other tabs apply here. Those measure operating "
        "businesses through their accounts; these are funds, and what matters instead is "
        "the fee, the risk taken to earn the return, and how the return compares with "
        "simply holding cash.")
    return " ".join(parts)
