"""Shared config, HTTP and small utilities. Standard library only."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DATA = DOCS / "data"
# Derived fundamentals are cached outside the published site: they exist to
# avoid re-downloading multi-megabyte company facts, not to be served.
CACHE = ROOT / "cache"
FUND = CACHE / "fundamentals"

# SEC requires a descriptive User-Agent with contact info and caps traffic at
# 10 req/s. We stay well under that. Override via the SEC_USER_AGENT env var.
SEC_UA = os.environ.get("SEC_USER_AGENT", "amit-dashboard/1.0 (contact: dashboard@example.com)")
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"

SEC_MIN_INTERVAL = 0.15  # seconds between SEC calls
_last_sec_call = 0.0


class FetchError(RuntimeError):
    """Raised when a remote source could not be retrieved."""


def _sleep_for_sec_rate_limit() -> None:
    global _last_sec_call
    delta = time.monotonic() - _last_sec_call
    if delta < SEC_MIN_INTERVAL:
        time.sleep(SEC_MIN_INTERVAL - delta)
    _last_sec_call = time.monotonic()


# Header profiles. These are not cosmetic: FRED's CSV endpoint stalls and drops
# the connection when sent a browser-style Chrome User-Agent with a gzip
# Accept-Encoding, but answers a curl-style minimal request in under half a
# second. Yahoo does the reverse and returns 429 with no User-Agent at all.
PROFILES: dict[str, dict[str, str]] = {
    "browser": {
        "User-Agent": BROWSER_UA,
        "Accept-Encoding": "gzip, deflate",
        "Accept": "application/json, text/plain, */*",
    },
    "minimal": {
        "User-Agent": "curl/8.4.0",
        "Accept": "*/*",
    },
}


def fetch(url: str, *, sec: bool = False, profile: str = "browser",
          retries: int = 3, timeout: int = 30) -> bytes:
    """GET a URL with retry and backoff.

    `sec=True` applies SEC rate limiting and the required contact User-Agent.
    `profile` selects a header set for non-SEC hosts (see PROFILES).
    """
    if sec:
        headers = {
            "User-Agent": SEC_UA,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json, */*",
        }
    else:
        headers = dict(PROFILES.get(profile, PROFILES["browser"]))

    last: Exception | None = None
    for attempt in range(retries):
        if sec:
            _sleep_for_sec_rate_limit()
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                return raw
        except urllib.error.HTTPError as exc:
            last = exc
            # 404 means the resource genuinely is not there; do not burn retries.
            if exc.code == 404:
                break
            time.sleep(1.5 * (attempt + 1))
        except Exception as exc:  # noqa: BLE001 - network layer, retry anything
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise FetchError(f"{url} -> {last}")


def fetch_json(url: str, **kw: Any) -> Any:
    return json.loads(fetch(url, **kw))


def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=False), encoding="utf-8")


# Real holdings are deliberately kept out of the repository. watchlist.json is
# committed and this repo is public, so share counts and cost basis there would
# amount to publishing a position-by-position statement of net worth. Holdings
# live in positions.local.json, which .gitignore excludes, and the valued result
# is written to POSITIONS_PRIVATE_OUT rather than into the published payload.
POSITIONS_PRIVATE_IN = ROOT / "positions.local.json"
POSITIONS_PRIVATE_OUT = DATA / "positions.local.json"


def load_positions() -> tuple[list[dict], bool]:
    """Return (positions, is_private).

    Reads positions.local.json when it exists, accepting either a bare list or
    an object with a "positions" key so that a file copied straight from
    positions.local.example.json works unchanged. Falls back to whatever is in
    watchlist.json, which ships empty.
    """
    raw = read_json(POSITIONS_PRIVATE_IN)
    if isinstance(raw, dict):
        raw = raw.get("positions")
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, dict)], True
    return [], False


def load_config() -> dict:
    cfg = read_json(ROOT / "watchlist.json", {}) or {}
    cfg.setdefault("watchlist", [])
    cfg.setdefault("positions", [])
    private, is_private = load_positions()
    if is_private:
        cfg["positions"] = private
    cfg["positions_are_private"] = is_private
    settings = cfg.setdefault("settings", {})
    settings.setdefault("margin_of_safety_pct", 30)
    settings.setdefault("discount_rate_pct", 10.0)
    settings.setdefault("terminal_growth_pct", 2.5)
    settings.setdefault("big_move_pct", 5.0)
    settings.setdefault("max_berkshire_holdings", 25)
    return cfg


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    """Divide, returning None rather than raising on bad or zero input."""
    if numerator is None or denominator in (None, 0):
        return None
    try:
        return numerator / denominator
    except (TypeError, ZeroDivisionError):
        return None


def cagr(first: float | None, last: float | None, years: float) -> float | None:
    """Compound annual growth rate. Undefined if the series starts non-positive."""
    if first is None or last is None or years <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1.0 / years) - 1.0


def pct(value: float | None) -> float | None:
    return None if value is None else round(value * 100, 2)
