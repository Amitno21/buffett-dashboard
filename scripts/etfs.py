"""Exchange-traded funds, US and Israeli.

This panel exists because of something Buffett actually instructed rather than
merely said. In the 2013 shareholder letter he set out the terms of his own
estate: 10% in short-term government bonds and 90% in a very low-cost S&P 500
index fund, with the explicit note that he expects it to beat most investors
who hire expensive managers. A dashboard built on his method that never
mentions this would be misrepresenting him.

Two sources:
  * US funds - prices from Yahoo, expense ratios published by the issuers and
    pinned in this file (see EXPENSE_RATIOS for why, and how to check them).
  * Israeli funds - the 502 "קרנות סל" from funder.co.il/etfList, which embeds
    them as JSON the same way its other pages do.

Returns here are PRICE returns: they exclude dividends, so a fund paying 1.5%
a year has really done about 1.5% a year better than the figure shown. That is
stated on the panel rather than quietly corrected, because the correction
depends on when dividends were paid and reinvested.
"""
from __future__ import annotations

from statistics import median

from common import FetchError, fetch, safe_div
from israel import embedded_rows

ETF_LIST_URL = "https://www.funder.co.il/etfList"

# Annual cost, as published by each issuer. These are pinned rather than
# fetched because no free feed carries them reliably, and they change perhaps
# once every few years. Verify against the issuer's own factsheet before acting
# on a small difference; the figure shown on the panel says where it came from.
EXPENSE_RATIOS = {
    "VOO": 0.03, "IVV": 0.03, "SPY": 0.0945, "VTI": 0.03, "QQQ": 0.20,
    "VXUS": 0.05, "VT": 0.06, "AGG": 0.03, "SCHD": 0.06, "VYM": 0.06,
}

# A deliberately short list. The point of the panel is that a handful of broad,
# cheap funds covers almost everything most people need, so listing hundreds
# would argue against itself.
US_ETFS = [
    ("VOO", "Vanguard S&P 500", "The 500 largest US companies. The fund Buffett named for his estate."),
    ("SPY", "SPDR S&P 500", "The same index, older and dearer, but the most heavily traded."),
    ("VTI", "Vanguard Total US Market", "Every listed US company, not just the largest 500."),
    ("QQQ", "Invesco Nasdaq 100", "The 100 largest Nasdaq companies. Heavily weighted to technology."),
    ("VXUS", "Vanguard World ex-US", "Developed and emerging markets outside America."),
    ("VT", "Vanguard Total World", "The whole investable world in one fund."),
    ("SCHD", "Schwab US Dividend", "US companies with a long record of paying dividends."),
    ("AGG", "iShares US Bonds", "US investment-grade bonds, held as ballast rather than for growth."),
]

BENCHMARK = "VOO"


# --------------------------------------------------------------------------- #
# US
# --------------------------------------------------------------------------- #

def _range_return(snapshot: dict) -> float | None:
    """Price return across whatever range was fetched."""
    first, last = snapshot.get("first_close"), snapshot.get("price")
    if not first or not last:
        return None
    return round((last / first - 1) * 100, 1)


def us_etfs(price_history) -> list[dict]:
    rows = []
    for symbol, name, description in US_ETFS:
        one_year = price_history(symbol, rng="1y")
        if not one_year:
            continue
        five_year = price_history(symbol, rng="5y")
        fee = EXPENSE_RATIOS.get(symbol)
        annual_1y = _range_return(one_year)
        rows.append({
            "symbol": symbol,
            "name": name,
            "description": description,
            "price": one_year["price"],
            "change_pct": one_year["change_pct"],
            "year_pct": annual_1y,
            "five_year_pct": _range_return(five_year) if five_year else None,
            "from_high_pct": one_year["from_high_pct"],
            "fee_pct": fee,
            # What the fee actually costs on a real holding, which is easier to
            # judge than a decimal: £/$ per year on ten thousand invested.
            "fee_per_10k": round(fee * 100, 2) if fee is not None else None,
            "as_of": one_year["as_of"],
        })
    rows.sort(key=lambda r: (r["fee_pct"] if r["fee_pct"] is not None else 99))
    return rows


# --------------------------------------------------------------------------- #
# Israel
# --------------------------------------------------------------------------- #

DIGEST_ROWS = 12


def israeli_etfs() -> dict:
    """The Israeli ETF universe, summarised by asset class."""
    try:
        html = fetch(ETF_LIST_URL).decode("utf-8", "replace")
    except FetchError as exc:
        return {"available": False, "reason": str(exc)}

    raw = embedded_rows(html, "fundlistData")
    if not raw:
        return {"available": False, "reason": "No fund data found in the page"}

    funds = []
    for row in raw:
        ytd = row.get("yyb")
        funds.append({
            "name": str(row.get("fundLongName", "")).strip(),
            "manager": str(row.get("fndMng", "")).strip(),
            "category": str(row.get("ClassificationMajorVal", "")).strip(),
            "sub_category": str(row.get("ClassificationSecondaryVal", "")).strip(),
            "day_pct": row.get("y1d"),
            "month_pct": row.get("ymb"),
            "ytd_pct": ytd,
            "url": f"https://www.funder.co.il/etf/{row.get('secId')}" if row.get("secId") else "",
        })

    # Group by asset class so 502 funds become a readable dozen lines.
    groups: dict[str, list[float]] = {}
    for fund in funds:
        if fund["category"] and fund["ytd_pct"] is not None:
            groups.setdefault(fund["category"], []).append(fund["ytd_pct"])
    categories = sorted(
        ({"category": name,
          "count": len(values),
          "median_ytd_pct": round(median(values), 2),
          "best_ytd_pct": round(max(values), 1),
          "worst_ytd_pct": round(min(values), 1)}
         for name, values in groups.items()),
        key=lambda c: c["count"], reverse=True,
    )

    ranked = sorted((f for f in funds if f["ytd_pct"] is not None),
                    key=lambda f: f["ytd_pct"], reverse=True)
    all_ytd = [f["ytd_pct"] for f in ranked]

    return {
        "available": True,
        "count": len(funds),
        "median_ytd_pct": round(median(all_ytd), 2) if all_ytd else None,
        "categories": categories[:10],
        "rows": ranked[:DIGEST_ROWS],
        "source": ETF_LIST_URL,
    }


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def snapshot(price_history, companies: list[dict] | None = None) -> dict:
    us = us_etfs(price_history)
    israeli = israeli_etfs()
    data = {
        "us": us,
        "israel": israeli,
        "benchmark": BENCHMARK,
        "attribution": "US prices from Yahoo Finance; expense ratios as published by the "
                       "issuers and pinned in scripts/etfs.py. Israeli funds from "
                       "funder.co.il, shown as a digest with the full list linked.",
        "returns_note": "All returns here are price returns and exclude dividends, so a fund "
                        "paying income has done better than the figure shown.",
    }
    data["brief"] = brief(data, companies or [])
    return data


def brief(data: dict, companies: list[dict]) -> str:
    parts: list[str] = []
    us = data.get("us") or []
    israeli = data.get("israel") or {}

    benchmark = next((r for r in us if r["symbol"] == data.get("benchmark")), None)
    if benchmark and benchmark.get("year_pct") is not None:
        parts.append(
            f"Buying the whole S&P 500 through {benchmark['symbol']} returned "
            f"{benchmark['year_pct']:.1f}% over the past year, before dividends, for a fee of "
            f"{benchmark['fee_pct']:.2f}% a year — about "
            f"${benchmark['fee_per_10k']:.0f} annually on every $10,000 invested.")

    cheapest = min((r for r in us if r["fee_pct"] is not None),
                   key=lambda r: r["fee_pct"], default=None)
    dearest = max((r for r in us if r["fee_pct"] is not None),
                  key=lambda r: r["fee_pct"], default=None)
    if cheapest and dearest and dearest["fee_pct"] > cheapest["fee_pct"]:
        parts.append(
            f"Fees across this list run from {cheapest['fee_pct']:.2f}% to "
            f"{dearest['fee_pct']:.2f}%. That gap sounds trivial and is not: it is deducted "
            f"every year, on the whole balance, whether the fund rises or falls.")

    # The honest comparison: this is what the stock-picking on the other tabs
    # has to beat, and saying so is the point of the panel.
    if companies:
        cheap = [c for c in companies
                 if (c.get("valuation") or {}).get("band") == "Below margin of safety"]
        parts.append(
            f"This is the benchmark the rest of the dashboard has to beat. Picking individual "
            f"companies only makes sense if it does better than simply buying the index, after "
            f"the effort and the mistakes — and today the screen finds {len(cheap)} of "
            f"{len(companies)} tracked companies trading below their estimated value.")

    if israeli.get("available"):
        parts.append(
            f"On the Tel Aviv side there are {israeli['count']} exchange-traded funds, with a "
            f"median return of {israeli['median_ytd_pct']:.1f}% so far this year.")

    parts.append(
        "Buffett's own instruction for his estate was 90% in a low-cost S&P 500 fund and 10% in "
        "short-term government bonds. He has been explicit that most people, including his own "
        "family, should not try to pick stocks at all.")
    return " ".join(parts)
