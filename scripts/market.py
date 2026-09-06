"""Market data: daily prices from Yahoo, macro series from FRED.

Both are keyless. FRED's graph CSV endpoint serves full history without an API
key, which keeps the whole pipeline free of secrets.
"""
from __future__ import annotations

import csv
import io
from datetime import date

from common import FetchError, fetch, fetch_json, safe_div

YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={rng}&interval=1d"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"


# --------------------------------------------------------------------------- #
# Prices
# --------------------------------------------------------------------------- #

def price_history(symbol: str, rng: str = "2y") -> dict:
    """Daily closes for a symbol, plus derived trend statistics.

    Returns {} when the symbol cannot be fetched, so one bad ticker never takes
    down the whole run.
    """
    try:
        payload = fetch_json(YAHOO_CHART.format(symbol=symbol, rng=rng))
    except FetchError:
        return {}

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return {}
    node = result[0]
    meta = node.get("meta", {})
    stamps = node.get("timestamp") or []
    quote = (node.get("indicators", {}).get("quote") or [{}])[0]
    closes_raw = quote.get("close") or []

    series: list[tuple[str, float]] = []
    for ts, close in zip(stamps, closes_raw):
        if close is None:
            continue
        series.append((date.fromtimestamp(ts).isoformat(), round(float(close), 4)))
    if not series:
        return {}

    closes = [c for _, c in series]
    last = closes[-1]
    prev = closes[-2] if len(closes) > 1 else last
    window_52w = closes[-252:] if len(closes) >= 252 else closes

    return {
        "symbol": symbol,
        "currency": meta.get("currency", "USD"),
        "price": round(float(meta.get("regularMarketPrice") or last), 4),
        "previous_close": prev,
        "change_pct": round((last / prev - 1) * 100, 2) if prev else None,
        "high_52w": max(window_52w),
        "low_52w": min(window_52w),
        "from_high_pct": round((last / max(window_52w) - 1) * 100, 2),
        "from_low_pct": round((last / min(window_52w) - 1) * 100, 2),
        "sma50": sma(closes, 50),
        "sma200": sma(closes, 200),
        "rsi14": rsi(closes, 14),
        "atr_pct": atr_pct(closes, 14),
        "as_of": series[-1][0],
        # The oldest point of the requested range, kept as its own field. The
        # sparkline below is downsampled and truncated, so it must never be used
        # to read a historical price.
        "first_close": closes[0],
        "first_date": series[0][0],
        # Weekly sample keeps the payload small while still drawing a clean line.
        "sparkline": [c for _, c in series[::5]][-120:],
    }


def sma(closes: list[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    return round(sum(closes[-window:]) / window, 4)


def rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's RSI. Above 70 is conventionally overbought, below 30 oversold."""
    if len(closes) < period + 1:
        return None
    gains, losses = 0.0, 0.0
    for i in range(-period, 0):
        delta = closes[i] - closes[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain, avg_loss = gains / period, losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def atr_pct(closes: list[float], period: int = 14) -> float | None:
    """Average absolute daily move as a percentage of price.

    A true ATR needs intraday high/low; close-to-close is the honest
    approximation available from this feed and is fine for sizing context.
    """
    if len(closes) < period + 1:
        return None
    moves = [abs(closes[i] - closes[i - 1]) for i in range(-period, 0)]
    avg = sum(moves) / period
    return round(safe_div(avg, closes[-1]) * 100, 2) if closes[-1] else None


# --------------------------------------------------------------------------- #
# Macro
# --------------------------------------------------------------------------- #

def fred_series(series_id: str) -> list[tuple[str, float]]:
    """(date, value) pairs from FRED. Missing observations are marked '.'."""
    try:
        raw = fetch(FRED_CSV.format(series=series_id), profile="minimal").decode("utf-8", "replace")
    except FetchError:
        return []
    rows: list[tuple[str, float]] = []
    for row in csv.DictReader(io.StringIO(raw)):
        keys = list(row.keys())
        if len(keys) < 2:
            continue
        stamp, value = row[keys[0]], row[keys[1]]
        if value in (".", "", None):
            continue
        try:
            rows.append((stamp, float(value)))
        except ValueError:
            continue
    return rows


def fred_latest(series_id: str) -> dict:
    rows = fred_series(series_id)
    if not rows:
        return {}
    stamp, value = rows[-1]
    year_ago = rows[-253] if len(rows) > 253 else rows[0]
    return {"date": stamp, "value": value, "prior_year": year_ago[1]}


def market_weather() -> dict:
    """The macro regime a value buyer is operating in.

    Every number here is sourced, not modelled:
      * DGS10  - 10-year Treasury, Buffett's "gravity" on all asset prices
      * NCBEILQ027S / GDP - the Buffett Indicator, from the Fed's Z.1 accounts
      * ^GSPC, ^VIX - index level and implied volatility
    """
    out: dict = {"sources": {
        "treasury_10y": "FRED DGS10",
        "buffett_indicator": "FRED NCBEILQ027S / GDP (Fed Z.1)",
        "index": "Yahoo Finance ^GSPC, ^VIX",
    }}

    ten_year = fred_latest("DGS10")
    if ten_year:
        out["treasury_10y"] = ten_year

    # Buffett Indicator: total value of corporate equities relative to the size
    # of the economy. Equities are reported in $M, GDP in $B.
    equities = dict(fred_series("NCBEILQ027S"))
    gdp = dict(fred_series("GDP"))
    if equities and gdp:
        # The two series publish on different lags, so compare the most recent
        # quarter present in both rather than each series' own last point.
        common = sorted(set(equities) & set(gdp))
        if common:
            quarter = common[-1]
            equities_bn = equities[quarter] / 1000.0  # Z.1 reports $M, GDP $B
            gdp_bn = gdp[quarter]
            ratio = safe_div(equities_bn, gdp_bn)
            if ratio:
                out["buffett_indicator"] = {
                    "value": round(ratio * 100, 1),
                    "as_of": quarter,
                    "equities_usd_bn": round(equities_bn, 1),
                    "gdp_usd_bn": round(gdp_bn, 1),
                }

    for key, symbol in (("sp500", "%5EGSPC"), ("vix", "%5EVIX")):
        snap = price_history(symbol, rng="1y")
        if snap:
            out[key] = {
                "price": snap["price"],
                "change_pct": snap["change_pct"],
                "from_high_pct": snap["from_high_pct"],
                "high_52w": snap["high_52w"],
                "low_52w": snap["low_52w"],
            }
    return out
