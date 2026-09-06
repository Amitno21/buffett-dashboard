"""SEC EDGAR access: company facts, XBRL frames, and 13F holdings.

Everything here comes from data.sec.gov / www.sec.gov, which is free, keyless
and authoritative. We honour the SEC fair-access policy via common.fetch.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Iterable

from common import CACHE, FetchError, fetch, fetch_json, read_json, write_json

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
BERKSHIRE_CIK = 1067983

# Concept fallback chains. Filers tag the same economic idea with different
# us-gaap elements, so each metric tries several tags in order of preference.
CONCEPTS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold"],
    "operating_income": ["OperatingIncomeLoss"],
    "cfo": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalImprovements",
    ],
    "depreciation": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "eps_diluted": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"],
    # Non-cash write-downs. Buffett's owner earnings adds back "other non-cash
    # charges", and a goodwill impairment is exactly that: without this,
    # Kraft Heinz's 2025 write-down alone turns its owner earnings negative.
    "impairment": [
        "GoodwillImpairmentLoss",
        "AssetImpairmentCharges",
        "ImpairmentOfIntangibleAssetsExcludingGoodwill",
        "GoodwillAndIntangibleAssetImpairment",
    ],
    "dividends_paid": ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "buybacks": ["PaymentsForRepurchaseOfCommonStock"],
    # Instant (balance-sheet) concepts
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
    "long_term_debt": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "retained_earnings": ["RetainedEarningsAccumulatedDeficit"],
    # Diluted weighted-average shares is the correct per-share denominator.
    # CommonStockSharesIssued is NOT a substitute: it includes treasury stock,
    # which overstates Coca-Cola's count by 63% (7.04bn issued vs 4.31bn real).
    "diluted_shares": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ],
    "shares_out": ["CommonStockSharesOutstanding", "CommonStockSharesIssued"],
}

INSTANT_METRICS = {
    "equity", "assets", "liabilities", "long_term_debt",
    "cash", "retained_earnings", "shares_out",
}

_DURATION_FRAME = re.compile(r"^CY(\d{4})$")
_INSTANT_FRAME = re.compile(r"^CY(\d{4})Q4I$")


# --------------------------------------------------------------------------- #
# Ticker / CIK
# --------------------------------------------------------------------------- #

def ticker_map(refresh: bool = True) -> dict[str, dict]:
    """Map upper-case ticker -> {cik, title}. Cached on disk as a fallback."""
    cache = CACHE / "ticker_map.json"
    if refresh:
        try:
            raw = fetch_json(TICKERS_URL, sec=True)
            out = {
                str(row["ticker"]).upper(): {"cik": int(row["cik_str"]), "title": row["title"]}
                for row in raw.values()
            }
            write_json(cache, out)
            return out
        except FetchError:
            pass
    return read_json(cache, {}) or {}


def cik_str(cik: int) -> str:
    return f"CIK{cik:010d}"


# --------------------------------------------------------------------------- #
# Filings
# --------------------------------------------------------------------------- #

def submissions(cik: int) -> dict:
    return fetch_json(f"https://data.sec.gov/submissions/{cik_str(cik)}.json", sec=True)


def latest_filings(subs: dict, forms: Iterable[str], limit: int = 5) -> list[dict]:
    """Most recent filings whose form starts with any entry in `forms`."""
    recent = subs.get("filings", {}).get("recent", {})
    wanted = tuple(forms)
    cik = int(subs.get("cik", 0))
    out: list[dict] = []
    for i, form in enumerate(recent.get("form", [])):
        if not form.startswith(wanted):
            continue
        accession = recent["accessionNumber"][i]
        document = recent["primaryDocument"][i]
        out.append({
            "form": form,
            "filed": recent["filingDate"][i],
            "report_date": recent.get("reportDate", [""] * (i + 1))[i],
            "accession": accession,
            "document": document,
            "url": filing_url(cik, accession, document),
        })
        if len(out) >= limit:
            break
    return out


def filing_url(cik: int | str, accession: str, document: str) -> str:
    nodash = str(accession).replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{nodash}/{document}"


# --------------------------------------------------------------------------- #
# Company facts -> annual series
# --------------------------------------------------------------------------- #

def _series_from_frames(entries: list[dict], instant: bool) -> dict[int, float]:
    """Prefer entries carrying a `frame`: the SEC marks exactly one canonical,
    non-overlapping fact per calendar period that way."""
    pattern = _INSTANT_FRAME if instant else _DURATION_FRAME
    out: dict[int, float] = {}
    for e in entries:
        frame_id = e.get("frame")
        if not frame_id:
            continue
        m = pattern.match(frame_id)
        if m and e.get("val") is not None:
            out[int(m.group(1))] = float(e["val"])
    return out


def _series_from_annual_reports(entries: list[dict], instant: bool) -> dict[int, float]:
    """Fallback for filers whose fiscal year does not align to calendar frames.
    Uses 10-K figures, keeping the most recently filed value per fiscal year."""
    best: dict[int, tuple[str, float]] = {}
    for e in entries:
        if not str(e.get("form", "")).startswith("10-K"):
            continue
        if not instant and e.get("fp") != "FY":
            continue
        fy, val, filed = e.get("fy"), e.get("val"), e.get("filed", "")
        if fy is None or val is None:
            continue
        fy = int(fy)
        if fy not in best or filed > best[fy][0]:
            best[fy] = (filed, float(val))
    return {fy: v for fy, (_, v) in best.items()}


def annual_series(facts: dict, metric: str) -> dict[int, float]:
    """Resolve one metric to {calendar_year: value} using the tag fallback chain.

    Tags are merged rather than first-match-wins: accounting standards change
    (ASC 606 replaced SalesRevenueNet with RevenueFromContractWithCustomer in
    2018, for example), so a single tag rarely spans a full decade. Earlier tags
    in the chain are preferred where two of them cover the same year.
    """
    instant = metric in INSTANT_METRICS
    gaap = facts.get("facts", {}).get("us-gaap", {})
    merged: dict[int, float] = {}
    for tag in reversed(CONCEPTS[metric]):  # reversed so preferred tags land last
        node = gaap.get(tag)
        if not node:
            continue
        for unit_key in ("USD", "USD/shares", "shares"):
            entries = node.get("units", {}).get(unit_key)
            if not entries:
                continue
            framed = _series_from_frames(entries, instant)
            fallback = _series_from_annual_reports(entries, instant)
            # Frames are cleaner but sparse for off-calendar filers; merge them
            # over the 10-K fallback so framed values win where both exist.
            merged.update({**fallback, **framed})
            break  # one unit per tag is enough
    return dict(sorted(merged.items()))


def company_facts(cik: int) -> dict:
    return fetch_json(f"https://data.sec.gov/api/xbrl/companyfacts/{cik_str(cik)}.json", sec=True)


def cover_page_shares(facts: dict) -> dict[int, float]:
    """Shares outstanding from the filing cover page (dei taxonomy).

    This is the backstop for companies whose us-gaap share tags are split
    across share classes and therefore never resolve to a single total, which
    is the case for Visa and other multi-class issuers.
    """
    node = facts.get("facts", {}).get("dei", {}).get("EntityCommonStockSharesOutstanding")
    if not node:
        return {}
    out: dict[int, float] = {}
    for entries in node.get("units", {}).values():
        for e in entries:
            end, val = e.get("end"), e.get("val")
            if not end or val is None:
                continue
            year = int(end[:4])
            # Multi-class filers report one row per class for the same date;
            # summing them gives the total share count.
            if e.get("fy") and str(e.get("form", "")).startswith("10-K"):
                out[year] = out.get(year, 0.0) + float(val)
    return dict(sorted(out.items()))


def extract_financials(facts: dict, years: int = 11) -> dict[str, dict[int, float]]:
    """Pull every configured metric, trimmed to the most recent `years`."""
    out: dict[str, dict[int, float]] = {}
    for metric in CONCEPTS:
        series = annual_series(facts, metric)
        if series:
            keep = sorted(series)[-years:]
            out[metric] = {y: series[y] for y in keep}

    cover = cover_page_shares(facts)
    if cover:
        out["cover_shares"] = {y: cover[y] for y in sorted(cover)[-years:]}
    return out


# --------------------------------------------------------------------------- #
# XBRL frames: one concept across every filer, for broad screening
# --------------------------------------------------------------------------- #

def frame(tag: str, period: str, unit: str = "USD") -> dict[int, float]:
    """Return {cik: value} for a us-gaap concept in a given period.

    `period` is e.g. 'CY2024' (duration) or 'CY2024Q4I' (instant). One request
    covers every filer, which is what makes a 500-name screen affordable.
    """
    url = f"https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/{unit}/{period}.json"
    try:
        payload = fetch_json(url, sec=True)
    except FetchError:
        return {}
    return {
        int(row["cik"]): float(row["val"])
        for row in payload.get("data", [])
        if row.get("val") is not None
    }


def frame_with_fallback(tags: list[str], period: str, unit: str = "USD") -> dict[int, float]:
    """Merge several tags for one period, with earlier tags winning."""
    merged: dict[int, float] = {}
    for tag in reversed(tags):
        merged.update(frame(tag, period, unit))
    return merged


# --------------------------------------------------------------------------- #
# 13F holdings
# --------------------------------------------------------------------------- #

def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# The 13F schema casing is inconsistent across filers and versions (the share
# count is `sshPrnamt`, with a lower-case 'a'), so fields are matched on a
# lower-cased tag name rather than an exact spelling.
_INFO_FIELDS = {"nameofissuer", "cusip", "value", "titleofclass", "sshprnamt", "putcall"}


def parse_information_table(xml_bytes: bytes) -> list[dict]:
    """Parse a 13F information table into holding rows."""
    root = ET.fromstring(xml_bytes)
    rows: list[dict] = []
    for node in root.iter():
        if _strip_ns(node.tag).lower() != "infotable":
            continue
        rec: dict[str, str] = {}
        for child in node.iter():
            name = _strip_ns(child.tag).lower()
            if name in _INFO_FIELDS and child.text and child.text.strip():
                rec.setdefault(name, child.text.strip())
        if "nameofissuer" not in rec:
            continue
        try:
            value = float(rec.get("value", 0))
            shares = float(rec.get("sshprnamt", 0))
        except ValueError:
            continue
        rows.append({
            "issuer": rec["nameofissuer"],
            "cusip": rec.get("cusip", ""),
            "class": rec.get("titleofclass", ""),
            "value": value,
            "shares": shares,
            "put_call": rec.get("putcall", ""),
        })
    return rows


def consolidate_holdings(rows: list[dict]) -> list[dict]:
    """13F tables list one row per manager/account; sum them per issuer."""
    merged: dict[str, dict] = {}
    for row in rows:
        if row.get("put_call"):
            continue  # options positions are not share ownership
        key = row["cusip"] or row["issuer"].upper()
        if key not in merged:
            merged[key] = {
                "issuer": row["issuer"],
                "cusip": row["cusip"],
                # Share class matters: Alphabet and Lennar appear as separate
                # CUSIPs and must not be collapsed into one line.
                "class": row.get("class", ""),
                "value": 0.0,
                "shares": 0.0,
            }
        merged[key]["value"] += row["value"]
        merged[key]["shares"] += row["shares"]
    return sorted(merged.values(), key=lambda r: r["value"], reverse=True)


def fetch_13f(cik: int = BERKSHIRE_CIK, back: int = 2) -> list[dict]:
    """Return the `back` most recent 13F-HR filings with consolidated holdings."""
    subs = submissions(cik)
    filings = latest_filings(subs, ("13F-HR",), limit=back + 3)
    results: list[dict] = []
    for f in filings:
        if len(results) >= back:
            break
        if f["form"].startswith("13F-HR/A"):
            continue  # amendments are often partial; use originals
        nodash = f["accession"].replace("-", "")
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{nodash}"
        try:
            index = fetch_json(f"{base}/index.json", sec=True)
        except FetchError:
            continue
        names = [item["name"] for item in index.get("directory", {}).get("item", [])]
        table = next(
            (n for n in names if n.lower().endswith(".xml") and "primary_doc" not in n.lower()),
            None,
        )
        if not table:
            continue
        try:
            rows = parse_information_table(fetch(f"{base}/{table}", sec=True))
        except (FetchError, ET.ParseError):
            continue
        if not rows:
            continue
        holdings = consolidate_holdings(rows)
        # Filings before 2023 report value in thousands of dollars. Berkshire's
        # book is far above $5bn, so a smaller total means thousands.
        total = sum(h["value"] for h in holdings)
        if total and total < 5e9:
            for h in holdings:
                h["value"] *= 1000.0
        results.append({
            "filed": f["filed"],
            "period": f.get("report_date", ""),
            "accession": f["accession"],
            "total_value": sum(h["value"] for h in holdings),
            "holdings": holdings,
        })
    return results


_NAME_NOISE = re.compile(
    r"\b(INC|CORP|CORPORATION|CO|COMPANY|LTD|PLC|HOLDINGS|HLDGS|GROUP|GRP|THE"
    r"|CLASS|CL|COM|NEW|SA|NV|AG|LP|TRUST|INTERNATIONAL|INTL)\b|[^A-Z0-9 ]"
)


def normalise_name(name: str) -> str:
    """Reduce a company name to a comparable core for 13F -> ticker matching."""
    return " ".join(_NAME_NOISE.sub(" ", name.upper()).split())


def build_name_index(tmap: dict[str, dict]) -> dict[str, str]:
    """Normalised company name -> ticker, for mapping 13F issuers to tickers."""
    index: dict[str, str] = {}
    for ticker, info in tmap.items():
        key = normalise_name(info["title"])
        # Prefer the shortest ticker for a name (e.g. GOOG over GOOGL variants).
        if key and (key not in index or len(ticker) < len(index[key])):
            index[key] = ticker
    return index
