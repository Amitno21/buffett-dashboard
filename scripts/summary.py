"""Plain-English summaries of what the numbers say.

Everything here is description, never recommendation. The sentences report what
the figures are and what the dashboard's own tests concluded; they never tell
the reader to buy, sell or hold anything. Where a number is an estimate, the
wording says so.

Generated in Python rather than the browser so the text is testable and travels
with the data.
"""
from __future__ import annotations

import re

GRADE_PHRASE = {
    "Exceptional": "which makes it an exceptional business by these tests",
    "Strong": "which makes it a strong business by these tests",
    "Adequate": "which makes it a middling business by these tests",
    "Weak": "which makes it a weak business by these tests",
    "Poor": "which makes it a poor business by these tests",
}

# A component has to score most of its points before it is described as a
# strength, and most of them must be missing before it is called a weakness.
# Without these thresholds a company scoring 10/100 gets a flattering opening
# sentence built from whichever component happened to score least badly.
STRENGTH_RATIO = 0.65
WEAKNESS_RATIO = 0.45

# Registrant names arrive from EDGAR shouted, with filing-office suffixes.
_NAME_SUFFIX = re.compile(r"\s*/[A-Z]{2,4}/?\s*$")


def clean_name(name: str) -> str:
    """`BANK OF AMERICA CORP /DE/` -> `Bank of America Corp`."""
    name = _NAME_SUFFIX.sub("", (name or "").strip())
    if name.isupper():
        small = {"of", "and", "the", "for", "de", "a"}
        words = []
        for i, word in enumerate(name.split()):
            lowered = word.lower()
            words.append(lowered if i and lowered in small else word.capitalize())
        name = " ".join(words)
    return name or "This company"


def _money(value: float | None, decimals: int = 2) -> str:
    return "an unknown amount" if value is None else f"${value:,.{decimals}f}"


def _cap(clause: str) -> str:
    return clause[:1].upper() + clause[1:] if clause else clause


def _consistency(value) -> tuple[int, int] | None:
    """The ROE-consistency component reports its value as 'hits/total'."""
    if not isinstance(value, str) or "/" not in value:
        return None
    hits, _, total = value.partition("/")
    try:
        return int(hits), int(total)
    except ValueError:
        return None


def describe(component: dict, positive: bool) -> str | None:
    """A self-contained clause about one component.

    Self-contained matters: these clauses get reordered and dropped, so none of
    them may refer back to another ("it managed that in only 1 of 11 years" is
    meaningless once the sentence it referred to is gone).
    """
    key, value = component.get("key"), component.get("value")
    if value is None:
        return None

    if key == "roe_level":
        if not isinstance(value, (int, float)):
            return None
        if positive and value <= 0:
            return None                      # never sell a loss as a strength
        # The label says which measure was actually scored: companies with book
        # equity near zero are scored on return on invested capital instead.
        basis = ("on all the capital invested in it"
                 if "invested capital" in component.get("label", "").lower()
                 else "on the money shareholders have left in it")
        if value < 0:
            return f"it is losing money {basis}, at a rate of about {abs(value):.0f}% a year"
        return (f"it earns about {value:.0f}% a year {basis}" if positive
                else f"it earns only about {value:.0f}% a year {basis}")

    if key == "roe_consistency":
        parsed = _consistency(value)
        if not parsed:
            return None
        hits, total = parsed
        # Two years out of two proves nothing; require a real track record.
        if total < 5:
            return None
        if positive:
            return (f"it has beaten a 15% return on shareholders' money in "
                    f"{hits} of the last {total} years")
        if hits == 0:
            return f"it has not once beaten a 15% return on shareholders' money in {total} years"
        return (f"it beat a 15% return on shareholders' money in only "
                f"{hits} of the last {total} years")

    if key == "margin_stability":
        return ("its profit margin has barely moved in a decade, which is what a durable "
                "competitive advantage looks like from the outside" if positive else
                "its profit margin swings around a lot, which suggests less protection from "
                "competition than the headline figures imply")

    if key == "debt_burden":
        if not isinstance(value, (int, float)):
            return None
        if positive:
            return ("it carries no long-term debt at all" if value == 0
                    else f"its long-term debt comes to only about {value:.1f} years of earnings")
        return f"it owes about {value:.1f} years of earnings in long-term debt"

    if key == "earnings_growth":
        if not isinstance(value, (int, float)):
            return None
        return (f"the cash it throws off for owners has grown about {value:.0f}% a year"
                if positive else
                f"the cash it throws off for owners has grown only about {value:.0f}% a year"
                if value >= 0 else
                f"the cash it throws off for owners has been shrinking, by about {abs(value):.0f}% a year")

    if key == "earnings_consistency":
        if not isinstance(value, (int, float)):
            return None
        return ("it has gone a decade without a serious drop in profit" if value == 0 else
                f"profit fell sharply in {value:.0f} of the last ten years")

    if key == "retained_earnings":
        if not isinstance(value, (int, float)):
            return None
        return (f"every $1 it held back rather than paying out has become about "
                f"{_money(value)} of market value" if positive else
                f"each $1 it held back has produced only about {_money(value)} of market value")

    return None


def _pick(components: list[dict], positive: bool, limit: int) -> list[str]:
    ratio = (lambda c: c["points"] / c["max"])
    pool = [c for c in components
            if c.get("max") and c.get("value") is not None
            and (ratio(c) >= STRENGTH_RATIO if positive else ratio(c) <= WEAKNESS_RATIO)]
    pool.sort(key=ratio, reverse=positive)
    out: list[str] = []
    for component in pool:
        clause = describe(component, positive)
        if clause:
            out.append(clause)
        if len(out) >= limit:
            break
    return out


def _join(clauses: list[str]) -> str:
    if len(clauses) <= 1:
        return clauses[0] if clauses else ""
    return ", and ".join([", ".join(clauses[:-1]), clauses[-1]]) if len(clauses) > 2 \
        else " and ".join(clauses)


def price_sentence(company: dict) -> str:
    valuation = company.get("valuation") or {}
    price = (company.get("price") or {}).get("price")

    if not valuation.get("available"):
        reason = (valuation.get("reason") or "the data needed is not reported").strip()
        return f"There is no usable estimate of what it is worth, because {reason[0].lower()}{reason[1:]}."

    estimate = valuation.get("base_value")
    gap = valuation.get("discount_to_value_pct")
    band = valuation.get("band")
    buy_below = valuation.get("buy_below")

    opening = (f"On the dashboard's default assumptions its shares work out at around "
               f"{_money(estimate)} each")
    if price is None or gap is None:
        return opening + "."
    if band == "Below margin of safety":
        return (f"{opening}, and they trade at {_money(price)}, about {abs(gap):.0f}% below that "
                f"estimate. That is inside the margin of safety set in the settings, which asks "
                f"for {_money(buy_below)} or less.")
    if band == "Near fair value":
        return (f"{opening}, and they trade at {_money(price)}. That is close enough to the "
                f"estimate to leave little room for the estimate itself to be wrong.")
    return (f"{opening}, against a market price of {_money(price)}. That is roughly "
            f"{abs(gap):.0f}% more than the estimate supports, so it is the price rather than "
            f"the business that stands out.")


def company_summary(company: dict) -> str:
    """Two to four sentences describing a business and how it is priced.

    Good businesses lead with what they do well; poor ones lead with the
    problems. Opening a company that scores 19 out of 100 with its brightest
    statistic would be a fair description of one component and a misleading
    description of the company.
    """
    quality = company.get("quality") or {}
    name = clean_name(company.get("name") or company.get("ticker", ""))
    score = quality.get("score")
    components = quality.get("components", [])

    if score is None:
        return f"{name} could not be scored. " + price_sentence(company)

    grade = GRADE_PHRASE.get(quality.get("grade"), "which is hard to place on these tests")
    strengths = _pick(components, positive=True, limit=2)
    weaknesses = _pick(components, positive=False, limit=2)

    parts = [f"{name} scores {score:g} out of 100, {grade}."]

    if score >= 65:
        if strengths:
            parts.append(_cap(_join(strengths)) + ".")
        if weaknesses:
            parts.append(f"The main mark against it is that {weaknesses[0]}.")
    elif score < 50:
        if weaknesses:
            parts.append(_cap(_join(weaknesses)) + ".")
        if strengths:
            parts.append(f"It does score well on one measure: {strengths[0]}.")
    else:
        if strengths:
            parts.append(_cap(strengths[0]) + ".")
        if weaknesses:
            parts.append(f"Against that, {weaknesses[0]}.")

    parts.append(price_sentence(company))

    caveats = quality.get("caveats") or []
    if caveats:
        parts.append("One caution: " + caveats[0][0].lower() + caveats[0][1:])

    return " ".join(parts)


def quality_headline(company: dict) -> str:
    """A very short label for the card view: what it is, and how it is priced."""
    quality = company.get("quality") or {}
    valuation = company.get("valuation") or {}
    grade = quality.get("grade", "Unscored")
    if not valuation.get("available"):
        return f"{grade} business, no usable price estimate"
    tail = {
        "Below margin of safety": "trading below the estimate",
        "Near fair value": "priced near the estimate",
        "Above estimated value": "priced above the estimate",
    }.get(valuation.get("band"), "price unclear")
    return f"{grade} business, {tail}"


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or singular + "s")


def daily_brief(payload: dict) -> str:
    """A short morning read: the weather, what moved, and where things stand."""
    weather = payload.get("weather") or {}
    companies = payload.get("companies") or []
    signals = payload.get("signals") or []
    sentences: list[str] = []

    indicator = (weather.get("buffett_indicator") or {}).get("value")
    ten_year = (weather.get("treasury_10y") or {}).get("value")
    if indicator is not None:
        if indicator > 150:
            sentences.append(
                f"The US stock market as a whole is worth about {indicator:.0f}% of everything "
                f"the country produces in a year, which is high by any historical standard and "
                f"is the measure Buffett has pointed to as a warning sign.")
        elif indicator < 100:
            sentences.append(
                f"The US stock market as a whole is worth about {indicator:.0f}% of everything "
                f"the country produces in a year, historically the cheaper end of the range.")
        else:
            sentences.append(
                f"The US stock market as a whole is worth about {indicator:.0f}% of everything "
                f"the country produces in a year, roughly its long-run average.")
    if ten_year is not None:
        sentences.append(
            f"Government bonds pay {ten_year:.2f}%, which is the return a share has to beat "
            f"before it is worth taking on the extra risk.")

    if not signals:
        sentences.append(
            "Nothing of note has changed since the last check: no large price moves, no new "
            "company filings, and nothing crossed into or out of value territory. Quiet days "
            "are the normal state of a portfolio meant to be held for years.")
    else:
        high = [s for s in signals if s.get("severity") == "high"]
        headline = (high or signals)[0]
        others = len(signals) - 1
        line = f"Since the last check: {headline.get('headline', 'something changed')}."
        if others > 0:
            line += (f" There {'is' if others == 1 else 'are'} {others} other "
                     f"{_plural(others, 'item')} below.")
        sentences.append(line)

    cheap = [c for c in companies
             if (c.get("valuation") or {}).get("band") == "Below margin of safety"]
    fair = [c for c in companies
            if (c.get("valuation") or {}).get("band") == "Near fair value"]
    if cheap:
        names = ", ".join(c["ticker"] for c in cheap[:6])
        sentences.append(
            f"Of the {len(companies)} companies tracked, {len(cheap)} currently sit below the "
            f"margin of safety set in the settings: {names}. That is this dashboard's arithmetic "
            f"on its default assumptions rather than a recommendation, so open each one and "
            f"judge whether the assumptions behind it look right to you.")
    elif fair:
        sentences.append(
            f"None of the {len(companies)} companies tracked are below the margin of safety "
            f"today, though {len(fair)} sit near the estimate of fair value. Finding nothing "
            f"worth acting on is a normal and useful result.")
    else:
        sentences.append(
            f"None of the {len(companies)} companies tracked look cheap against these estimates "
            f"today. Finding nothing is itself an answer, and the usual one in an expensive "
            f"market.")

    return " ".join(sentences)
