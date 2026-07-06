"""Shared static-asset copy for the page builders.

`theme.js` ships a `/*__SUPABASE_CFG__*/null` placeholder that MUST be replaced
with the public Supabase config (`config.yml -> watchlist.supabase`) at copy
time, so `window.SUPABASE_CFG` — and therefore the site-wide account system
(sign-in modal + cookie session) — is live on EVERY page.

Why this module exists: every page builder copies `theme.js` from `templates/`
into its `site/` output with its own little loop. `build_site.py` used to be the
only one that baked the token; the ~11 other builders (china/hk/canada/intl/
mastermind/aibrief/ai-desk/china-*) copied it RAW. Because those builders run
after `build_site.py` in the nightly pipeline, whichever ran last clobbered the
baked copy with the unresolved placeholder — leaving `window.SUPABASE_CFG` null
and the account UI silently disabled (`auth-disabled`) on the whole live site.

Route every `theme.js` copy through `copy_asset()` so the bake can never be lost
to copy ordering again. The publishable (anon) key is PUBLIC by design;
per-user isolation is enforced by RLS. See `ACCOUNTS_SETUP.md`.
"""
from __future__ import annotations

import json
from pathlib import Path

from lib import config

# The literal token emitted by templates/theme.js; kept in sync with that file.
SUPABASE_TOKEN = "/*__SUPABASE_CFG__*/null"


def supabase_cfg_json() -> str:
    """Single source of truth for the inline Supabase config injected into pages.

    Returns the ``{"url", "anonKey"}`` config as a JSON object literal, or the
    string ``"null"`` when Supabase is not configured (so the placeholder still
    resolves to a valid ``window.SUPABASE_CFG = ... || null`` expression and the
    account system cleanly reports itself disabled).

    Used by :func:`bake_theme_js` (for ``theme.js``) and directly by the
    watchlist and committee page builders in ``scripts/build_site.py``.
    """
    sup = (config.load().get("watchlist", {}).get("supabase") or {})
    cfg = (
        {"url": sup["url"], "anonKey": sup["anon_key"]}
        if sup.get("url") and sup.get("anon_key")
        else None
    )
    return json.dumps(cfg)


def bake_theme_js(text: str) -> str:
    """Replace the Supabase-config placeholder in theme.js source with live config."""
    return text.replace(SUPABASE_TOKEN, supabase_cfg_json())


def copy_asset(asset: str, src: Path, dst_dir: Path) -> None:
    """Copy one template asset into a site dir, baking theme.js's Supabase config.

    ``src`` is the full source path (``templates/<asset>``); ``dst_dir`` is the
    site output directory. For every asset except ``theme.js`` this is a plain
    byte-for-byte copy — identical to the ``(dst_dir / asset).write_text(
    src.read_text())`` the builders used before.
    """
    text = src.read_text()
    if asset == "theme.js":
        text = bake_theme_js(text)
    (dst_dir / asset).write_text(text)
