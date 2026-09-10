"""Cache-busting for the page's own scripts and stylesheet.

The data file was already fetched with a timestamp query, so it always
refreshed. The scripts and the stylesheet were not, which meant a returning
visitor could run yesterday's JavaScript against today's data until they
happened to force a reload. That is why every change needed a "hard refresh"
to appear.

This stamps a short content hash onto each asset reference in index.html:

    <script src="app.js?v=9f3c1a2b">

The hash changes only when the file changes, so browsers cache aggressively
until the moment there is something new to fetch, and never a moment longer.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

# Only local assets. A CDN reference or a data: URI must be left alone.
ASSET_PATTERN = re.compile(
    r'(?P<attr>src|href)="(?P<file>[A-Za-z0-9_\-./]+\.(?:js|css))(?:\?v=[a-f0-9]+)?"'
)


def content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:8]


def stamp(html_path: Path) -> dict[str, str]:
    """Rewrite asset references in `html_path` with current content hashes."""
    html = html_path.read_text(encoding="utf-8")
    root = html_path.parent
    stamped: dict[str, str] = {}

    def replace(match: re.Match) -> str:
        name = match.group("file")
        target = root / name
        if not target.is_file():
            return match.group(0)
        digest = content_hash(target)
        stamped[name] = digest
        return f'{match.group("attr")}="{name}?v={digest}"'

    updated = ASSET_PATTERN.sub(replace, html)
    if updated != html:
        html_path.write_text(updated, encoding="utf-8")
    return stamped
