"""Buffett-style quality scoring and intrinsic value estimation.

Every score here is a transparent function of reported figures. Nothing is a
black box: each component returns the raw value it was computed from, the
points awarded, and a plain-English note, so a reader can disagree with the
scoring and see exactly why.

References for the criteria are Buffett's shareholder letters, in particular
the 1986 appendix defining owner earnings and the recurring insistence on
return on equity without leverage, earnings consistency, and the one-dollar
premise for retained earnings.
"""
from __future__ import annotations

from statistics import mean, median, pstdev

from common import cagr, safe_div

# Component weights sum to 100.
WEIGHTS = {
    "roe_level": 20,
    "roe_consistency": 10,
    "margin_stability": 15,
    "debt_burden": 15,
    "earnings_growth": 15,
    "earnings_consistency": 15,
    "retained_earnings": 10,
}


def ramp(value: float | None, floor: float, target: float, points: float) -> float:
    """Award points on a straight line between `floor` (0) and `target` (full).

    Works in both directions: pass floor > target for metrics where lower is
    better, such as leverage.
    """
    if value is None:
        return 0.0
    if floor == target:
        return points if value >= target else 0.0
    fraction = (value - floor) / (target - floor)
    return round(max(0.0, min(1.0, fraction)) * points, 2)


def _years(series: dict) -> list[int]:
    return sorted(int(y) for y in series)


def get(fin: dict, metric: str, year: int) -> float | None:
    series = fin.get(metric, {})
    for key in (year, str(year)):
        if key in series:
            return float(series[key])
    return None


# --------------------------------------------------------------------------- #
# Derived per-year figures
# --------------------------------------------------------------------------- #

def owner_earnings(fin: dict, year: int) -> float | None:
    """Buffett's owner earnings: reported earnings plus depreciation and other
    non-cash charges, less the capital expenditure the business must make to
    hold its position.

    Maintenance capex is never disclosed separately, so this uses the standard
    proxy of min(capex, depreciation): a company spending less than it is
    depreciating is not growing its asset base, and spending above depreciation
    is treated as growth capex, which owner earnings should not be charged for.
    """
    net_income = get(fin, "net_income", year)
    depreciation = get(fin, "depreciation", year)
    capex = get(fin, "capex", year)
    # Write-downs are non-cash and belong in the add-back, exactly like
    # depreciation. Leaving them out makes a single impairment year look like a
    # collapse in earning power.
    impairment = abs(get(fin, "impairment", year) or 0.0)
    if net_income is None:
        return None
    if depreciation is None or capex is None:
        return net_income + impairment
    maintenance = min(abs(capex), abs(depreciation))
    return net_income + abs(depreciation) + impairment - maintenance


MAX_SHARE_COUNT_AGE = 3  # years


def share_count(fin: dict, reference_year: int | None = None) -> tuple[float | None, str]:
    """Best available diluted share count, with the source recorded.

    Order matters. Diluted weighted-average shares is the correct denominator.
    Deriving it from net income over diluted EPS is self-consistent and is the
    next best thing. CommonStockSharesIssued is the last resort because it
    counts treasury stock and can overstate the real figure by half.

    Any candidate more than MAX_SHARE_COUNT_AGE years old is rejected outright.
    A stale count is worse than none: Visa's only undimensioned cover-page
    figure is from 2009, and using it would value the company off a share count
    a sixth of its real size. Companies whose share data is reported per share
    class do not appear in companyfacts at all, which is why an explicit
    override exists in watchlist.json.
    """
    latest_known = reference_year or max(
        (int(y) for series in ("net_income", "revenue") for y in fin.get(series, {})),
        default=None,
    )

    def fresh(year: int) -> bool:
        return latest_known is None or (latest_known - year) <= MAX_SHARE_COUNT_AGE

    candidates = [
        ("diluted_shares", "diluted weighted average"),
        ("cover_shares", "filing cover page"),
        ("shares_out", "shares issued, may include treasury stock"),
    ]

    diluted = fin.get("diluted_shares", {})
    if diluted:
        year = max(int(y) for y in diluted)
        value = get(fin, "diluted_shares", year)
        if value and value > 0 and fresh(year):
            return value, f"diluted weighted average ({year})"

    ni, eps = fin.get("net_income", {}), fin.get("eps_diluted", {})
    common = {int(y) for y in ni} & {int(y) for y in eps}
    if common:
        year = max(common)
        income, per_share = get(fin, "net_income", year), get(fin, "eps_diluted", year)
        if income and per_share and fresh(year):
            return income / per_share, f"derived from EPS ({year})"

    for key, label in candidates[1:]:
        series = fin.get(key, {})
        if not series:
            continue
        year = max(int(y) for y in series)
        value = get(fin, key, year)
        if value and value > 0 and fresh(year):
            return value, f"{label} ({year})"

    return None, "no share count reported in a usable form"


def free_cash_flow(fin: dict, year: int) -> float | None:
    cfo, capex = get(fin, "cfo", year), get(fin, "capex", year)
    if cfo is None:
        return None
    return cfo - abs(capex) if capex is not None else cfo


def gross_margin(fin: dict, year: int) -> float | None:
    revenue = get(fin, "revenue", year)
    if not revenue:
        return None
    profit = get(fin, "gross_profit", year)
    if profit is None:
        cost = get(fin, "cost_of_revenue", year)
        if cost is None:
            return None
        profit = revenue - cost
    return safe_div(profit, revenue)


def roe(fin: dict, year: int) -> float | None:
    return safe_div(get(fin, "net_income", year), get(fin, "equity", year))


def roic(fin: dict, year: int) -> float | None:
    """Operating income after an assumed 21% tax, over invested capital."""
    operating = get(fin, "operating_income", year)
    equity = get(fin, "equity", year)
    debt = get(fin, "long_term_debt", year) or 0.0
    cash = get(fin, "cash", year) or 0.0
    if operating is None or equity is None:
        return None
    invested = equity + debt - cash
    return safe_div(operating * 0.79, invested) if invested > 0 else None


def build_series(fin: dict) -> dict[str, dict[int, float]]:
    """Per-year derived metrics, ready for both scoring and charting."""
    years = sorted({int(y) for m in ("net_income", "equity", "revenue") for y in fin.get(m, {})})
    out: dict[str, dict[int, float]] = {
        "owner_earnings": {}, "fcf": {}, "roe": {}, "roic": {},
        "gross_margin": {}, "operating_margin": {}, "revenue": {},
        "net_income": {}, "eps": {},
    }
    for year in years:
        for key, value in (
            ("owner_earnings", owner_earnings(fin, year)),
            ("fcf", free_cash_flow(fin, year)),
            ("roe", roe(fin, year)),
            ("roic", roic(fin, year)),
            ("gross_margin", gross_margin(fin, year)),
            ("operating_margin", safe_div(get(fin, "operating_income", year), get(fin, "revenue", year))),
            ("revenue", get(fin, "revenue", year)),
            ("net_income", get(fin, "net_income", year)),
            ("eps", get(fin, "eps_diluted", year)),
        ):
            if value is not None:
                out[key][year] = value
    return {k: v for k, v in out.items() if v}


# --------------------------------------------------------------------------- #
# Quality score
# --------------------------------------------------------------------------- #

def quality_score(fin: dict, derived: dict, market_cap: float | None = None,
                  market_cap_then: float | None = None,
                  value_since: str | None = None) -> dict:
    """Score a business 0-100 on Buffett's published criteria."""
    components: list[dict] = []

    def add(key: str, points: float, value, note: str, detail: str = "",
            label: str | None = None) -> None:
        components.append({
            "key": key,
            "label": label or LABELS[key],
            "points": round(points, 2),
            "max": WEIGHTS[key],
            "value": value,
            "note": note,
            "detail": detail,
        })

    roe_series = derived.get("roe", {})
    roe_values = [v for v in roe_series.values() if v is not None]

    # Heavy buybacks can drive book equity to near zero or below, at which point
    # ROE stops describing profitability and starts describing the capital
    # structure. Mastercard prints 193% and DaVita -166% for this reason. Where
    # that happens, fall back to return on invested capital, which stays
    # meaningful because it includes debt.
    roic_series = derived.get("roic", {})
    latest_equity_year = max(fin.get("equity", {}) or [0], key=lambda y: int(y), default=0)
    latest_equity = get(fin, "equity", int(latest_equity_year)) if latest_equity_year else None
    latest_assets = get(fin, "assets", int(latest_equity_year)) if latest_equity_year else None
    thin_equity = (
        latest_equity is not None and (
            latest_equity <= 0
            or (latest_assets and latest_equity / latest_assets < 0.10)
        )
    )

    # 1. Return on equity. Buffett's stated bar is a consistent 15%+ without
    #    leaning on leverage to get there.
    if thin_equity and roic_series:
        roic_values = [v for v in roic_series.values() if v is not None]
        avg_roic = mean(roic_values) if roic_values else None
        add("roe_level", ramp(avg_roic, 0.06, 0.15, WEIGHTS["roe_level"]),
            None if avg_roic is None else round(avg_roic * 100, 1),
            f"{avg_roic * 100:.1f}% average return on invested capital"
            if avg_roic is not None else "Return on capital unavailable",
            "Book equity is negative or negligible after buybacks, which makes "
            "return on equity meaningless, so return on invested capital is "
            "scored instead. Full marks at 15%+.",
            label="Return on invested capital")
    elif roe_values:
        avg_roe = mean(roe_values)
        add("roe_level", ramp(avg_roe, 0.08, 0.18, WEIGHTS["roe_level"]),
            round(avg_roe * 100, 1),
            f"{avg_roe * 100:.1f}% average ROE over {len(roe_values)} years",
            "Full marks at 18%+, none at or below 8%.")
    else:
        add("roe_level", 0, None, "No return-on-equity data", "")

    # 2. Consistency matters as much as the level: one good year proves nothing.
    if roe_values:
        hits = sum(1 for v in roe_values if v >= 0.15)
        share = hits / len(roe_values)
        add("roe_consistency", round(share * WEIGHTS["roe_consistency"], 2),
            f"{hits}/{len(roe_values)}",
            f"Cleared 15% ROE in {hits} of {len(roe_values)} years",
            "Proportional: every qualifying year earns a share of the points.")
    else:
        add("roe_consistency", 0, None, "No return-on-equity data", "")

    # 3. Margin stability is the closest measurable proxy for a moat: a business
    #    that holds its margin for a decade is being protected by something.
    margins = [v for v in derived.get("gross_margin", {}).values() if v is not None]
    if len(margins) >= 3 and mean(margins) > 0:
        cv = pstdev(margins) / mean(margins)
        add("margin_stability", ramp(cv, 0.25, 0.03, WEIGHTS["margin_stability"]),
            round(cv, 3),
            f"Gross margin averaged {mean(margins) * 100:.1f}% with {cv * 100:.1f}% variation",
            "Lower variation scores higher; full marks below 3%.")
    else:
        add("margin_stability", 0, None, "Not enough margin history", "")

    # 4. Leverage. Buffett's rule of thumb is that long-term debt should be
    #    repayable out of a few years of earnings.
    latest_year = max(derived.get("owner_earnings", {}) or [0])
    oe_latest = derived.get("owner_earnings", {}).get(latest_year)
    debt = get(fin, "long_term_debt", latest_year)
    if oe_latest and oe_latest > 0:
        if not debt:
            add("debt_burden", WEIGHTS["debt_burden"], 0.0,
                "No long-term debt reported", "A debt-free balance sheet scores full marks.")
        else:
            multiple = debt / oe_latest
            add("debt_burden", ramp(multiple, 8.0, 1.0, WEIGHTS["debt_burden"]),
                round(multiple, 2),
                f"Long-term debt is {multiple:.1f}x owner earnings",
                "Full marks at 1x or less, none at 8x or more.")
    else:
        add("debt_burden", 0, None, "Owner earnings not positive, so leverage is unscored", "")

    # 5. Growth in owner earnings, not reported EPS.
    oe = derived.get("owner_earnings", {})
    oe_years = sorted(oe)
    if len(oe_years) >= 4:
        span = oe_years[-1] - oe_years[0]
        growth = cagr(oe[oe_years[0]], oe[oe_years[-1]], span)
        add("earnings_growth", ramp(growth, 0.0, 0.12, WEIGHTS["earnings_growth"]),
            None if growth is None else round(growth * 100, 1),
            "Owner earnings grew {} a year over {} years".format(
                f"{growth * 100:.1f}%" if growth is not None else "an unmeasurable amount", span),
            "Full marks at 12% a year, none at zero or negative.")
    else:
        add("earnings_growth", 0, None, "Not enough owner-earnings history", "")

    # 6. Earnings consistency. Buffett wants a decade without a loss year.
    ni = derived.get("net_income", {})
    ni_years = sorted(ni)
    if len(ni_years) >= 4:
        # Only material setbacks count. Buffett's concern is durable earning
        # power, not whether a business had a mildly softer year, so a drop has
        # to exceed 10% before it is treated as a break in the record.
        material = sum(
            1 for a, b in zip(ni_years, ni_years[1:])
            if ni[a] > 0 and (ni[b] - ni[a]) / abs(ni[a]) < -0.10
        )
        losses = sum(1 for y in ni_years if ni[y] < 0)
        penalty = material + losses * 2  # a loss year counts double
        add("earnings_consistency", ramp(penalty, 4.0, 0.0, WEIGHTS["earnings_consistency"]),
            material,
            f"Earnings dropped more than 10% in {material} of {len(ni_years) - 1} years"
            + (f", with {losses} outright loss year(s)" if losses else ""),
            "Full marks for a decade without a material setback; loss years count double.")
    else:
        add("earnings_consistency", 0, None, "Not enough earnings history", "")

    # 7. The one-dollar premise: every dollar retained should create at least a
    #    dollar of market value.
    retained = fin.get("retained_earnings", {})
    ret_years = sorted(int(y) for y in retained)
    scored = False
    if len(ret_years) >= 5 and market_cap and market_cap_then:
        first, last = ret_years[0], ret_years[-1]
        delta_retained = get(fin, "retained_earnings", last) - get(fin, "retained_earnings", first)
        delta_value = market_cap - market_cap_then
        if delta_retained and delta_retained > 0:
            created = delta_value / delta_retained
            since = value_since or str(first)
            add("retained_earnings", ramp(created, 0.5, 1.5, WEIGHTS["retained_earnings"]),
                round(created, 2),
                f"Each $1 retained since {since} created ${created:.2f} of market value",
                "Buffett's one-dollar premise, comparing the change in retained "
                "earnings with the change in market value over the same window. "
                "Full marks at $1.50, none at $0.50.")
            scored = True
        elif delta_retained is not None and delta_retained <= 0:
            # Companies that return nearly all profit to shareholders, as Apple
            # does through buybacks, retain little or nothing. That is not a
            # failure of the test; the test simply does not apply.
            add("retained_earnings", 0, None,
                "Retained earnings did not grow: the company returns its profits "
                "rather than reinvesting them, so this test does not apply",
                "Excluded rather than failed. Judge capital allocation on the "
                "buyback and dividend record instead.")
            scored = True
    if not scored:
        add("retained_earnings", 0, None,
            "Needs both a decade of retained earnings and a matching price history", "")

    total = sum(c["points"] for c in components)

    # Banks and insurers do not report a gross margin or meaningful capital
    # expenditure, so two of the seven components score zero for reasons that
    # say nothing about business quality. Flag it rather than quietly ranking
    # them last.
    caveats: list[str] = []
    if not derived.get("gross_margin") and not fin.get("capex"):
        caveats.append(
            "This looks like a financial company. Gross margin and maintenance "
            "capital expenditure do not apply to banks and insurers, so the "
            "margin-stability and owner-earnings components understate it. "
            "Judge it on return on equity, consistency and book value instead."
        )
    if thin_equity:
        caveats.append(
            "Book equity is negative or very small, usually the result of years "
            "of buybacks. Return-on-equity figures for such a company are an "
            "artefact of its capital structure rather than a measure of "
            "profitability, so return on invested capital is scored in its place."
        )

    return {
        "score": round(total, 1),
        "grade": grade(total),
        "components": components,
        "caveats": caveats,
        # Which return measure was actually scored, so the summary table can
        # show the same figure rather than a misleading raw ROE.
        "return_basis": "roic" if thin_equity else "roe",
    }


LABELS = {
    "roe_level": "Return on equity",
    "roe_consistency": "ROE consistency",
    "margin_stability": "Margin stability (moat proxy)",
    "debt_burden": "Debt burden",
    "earnings_growth": "Owner-earnings growth",
    "earnings_consistency": "Earnings consistency",
    "retained_earnings": "One-dollar premise",
}


def grade(score: float) -> str:
    if score >= 80:
        return "Exceptional"
    if score >= 65:
        return "Strong"
    if score >= 50:
        return "Adequate"
    if score >= 35:
        return "Weak"
    return "Poor"


# --------------------------------------------------------------------------- #
# Intrinsic value
# --------------------------------------------------------------------------- #

def discounted_owner_earnings(base: float, shares: float, *, growth_1_5: float,
                              growth_6_10: float, discount: float,
                              terminal_growth: float, net_cash: float = 0.0) -> dict | None:
    """Two-stage discounted cash flow on owner earnings.

    Ten years of explicit projection, then a Gordon terminal value. The result
    is per share, with net cash added back.
    """
    if not base or base <= 0 or not shares or shares <= 0:
        return None
    if discount <= terminal_growth:
        return None

    present_value = 0.0
    flow = base
    flows: list[float] = []
    for year in range(1, 11):
        flow *= (1 + (growth_1_5 if year <= 5 else growth_6_10))
        flows.append(flow)
        present_value += flow / ((1 + discount) ** year)

    terminal = flows[-1] * (1 + terminal_growth) / (discount - terminal_growth)
    terminal_pv = terminal / ((1 + discount) ** 10)
    equity_value = present_value + terminal_pv + net_cash

    return {
        "per_share": round(equity_value / shares, 2),
        "equity_value": round(equity_value, 0),
        "explicit_pv": round(present_value, 0),
        "terminal_pv": round(terminal_pv, 0),
        "terminal_share_of_value": round(terminal_pv / equity_value, 3) if equity_value else None,
    }


def valuation(derived: dict, fin: dict, price: float | None, shares: float | None,
              settings: dict) -> dict:
    """Bear / base / bull intrinsic value, and the resulting margin of safety."""
    oe = derived.get("owner_earnings", {})
    years = sorted(oe)
    if not years or not price:
        return {"available": False, "reason": "No owner-earnings history or no market price"}
    if not shares:
        return {"available": False,
                "reason": "No usable share count. Companies that report shares per share "
                          "class do not expose a single total through the SEC companyfacts "
                          "API; add the diluted count to shares_override in watchlist.json "
                          "to value this one"}

    # Median of the last five years, not the mean. A single restructuring or
    # litigation year can drag a mean below zero and make a sound business look
    # unvaluable; the median ignores one bad year without ignoring a trend.
    recent = sorted(oe[y] for y in years[-5:] if oe[y] is not None)
    base = median(recent) if recent else None
    if not base or base <= 0:
        return {"available": False,
                "reason": "Owner earnings are negative in most of the last five years"}

    historic_growth = cagr(oe[years[0]], oe[years[-1]], years[-1] - years[0]) or 0.0
    # Cap the growth carried into a forecast: extrapolating a decade of 30%
    # growth forward is how DCFs produce nonsense.
    base_growth = max(0.0, min(historic_growth, 0.15))

    latest = years[-1]
    net_cash = (get(fin, "cash", latest) or 0.0) - (get(fin, "long_term_debt", latest) or 0.0)

    discount = settings.get("discount_rate_pct", 10.0) / 100.0
    terminal = settings.get("terminal_growth_pct", 2.5) / 100.0

    scenarios = {
        "bear": (max(0.0, base_growth - 0.05), max(0.0, base_growth - 0.07)),
        "base": (base_growth, max(0.0, base_growth - 0.03)),
        "bull": (base_growth + 0.04, base_growth),
    }

    out: dict = {
        "available": True,
        "base_owner_earnings": round(base, 0),
        "base_method": f"median of {len(recent)} years of owner earnings",
        "historic_growth_pct": round(historic_growth * 100, 1),
        "assumed_growth_pct": round(base_growth * 100, 1),
        "net_cash": round(net_cash, 0),
        "shares": shares,
        "discount_rate_pct": round(discount * 100, 1),
        "terminal_growth_pct": round(terminal * 100, 1),
        "scenarios": {},
    }

    for name, (g1, g2) in scenarios.items():
        dcf = discounted_owner_earnings(
            base, shares, growth_1_5=g1, growth_6_10=g2,
            discount=discount, terminal_growth=terminal, net_cash=net_cash,
        )
        if not dcf:
            continue
        value = dcf["per_share"]
        out["scenarios"][name] = {
            **dcf,
            "growth_1_5_pct": round(g1 * 100, 1),
            "growth_6_10_pct": round(g2 * 100, 1),
            "upside_pct": round((value / price - 1) * 100, 1) if price else None,
        }

    base_value = out["scenarios"].get("base", {}).get("per_share")
    if base_value:
        mos_required = settings.get("margin_of_safety_pct", 30) / 100.0
        buy_below = base_value * (1 - mos_required)
        discount_now = (base_value - price) / base_value
        out["base_value"] = base_value
        out["buy_below"] = round(buy_below, 2)
        out["discount_to_value_pct"] = round(discount_now * 100, 1)
        out["band"] = (
            "Below margin of safety" if price <= buy_below
            else "Near fair value" if price <= base_value * 1.1
            else "Above estimated value"
        )

    # Earnings yield against the risk-free rate: Buffett's "gravity" comparison.
    market_cap = price * shares
    out["owner_earnings_yield_pct"] = round(base / market_cap * 100, 2) if market_cap else None
    out["market_cap"] = round(market_cap, 0)
    return out
