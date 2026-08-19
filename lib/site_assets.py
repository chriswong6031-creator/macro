"""Shared static-asset copy for the page builders.

`theme.js` ships a `/*__SUPABASE_CFG__*/null` placeholder that MUST be replaced
with the public Supabase config (`config.yml -> watchlist.supabase`) at copy
time, so `window.SUPABASE_CFG` — and therefore the site-wide account system
(sign-in modal + cookie session) — is live on EVERY page. The emitted file also
bundles `terminal_overlay.js`: the production access wall already exposes
`theme.js` as a public static asset, while newly named standalone assets are
authenticated until their edge policy is updated.

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

import hashlib
import json
from pathlib import Path

from lib import config

# The literal tokens emitted by templates/theme.js; kept in sync with that file.
# Both are comment-prefixed literals, so an UNBAKED theme.js is still valid JS
# that degrades to a disabled account system / an unversioned bundle request
# rather than a syntax error taking the whole shared script down.
SUPABASE_TOKEN = "/*__SUPABASE_CFG__*/null"
MM_BRAIN_VER_TOKEN = "/*__MM_BRAIN_VER__*/''"


def project_ref(url: str) -> str:
    """The Supabase project ref — the first label of the project hostname.

    This is the identity of the PROJECT, never of the host the browser happens to
    talk to. It keys the session cookie (``sb-<ref>-auth-token``, written by
    theme.js COOKIE_STORAGE and read server-side by ``app.main._sb_storage_key``),
    so it must be derived from the project URL even when the browser is pointed at
    a proxy origin — see :func:`supabase_cfg_json`.
    """
    try:
        return url.split("://", 1)[-1].split(".", 1)[0]
    except Exception:  # noqa: BLE001
        return ""


def supabase_cfg_json() -> str:
    """Single source of truth for the inline Supabase config injected into pages.

    Returns the ``{"url", "anonKey", "ref"}`` config as a JSON object literal, or
    the string ``"null"`` when Supabase is not configured (so the placeholder still
    resolves to a valid ``window.SUPABASE_CFG = ... || null`` expression and the
    account system cleanly reports itself disabled).

    ``url`` is the origin the BROWSER calls: ``watchlist.supabase.browser_url`` when
    set (the GFW proxy — see config.yml), else the project URL itself.

    ``ref`` is ALWAYS the project ref, and is the reason this function exists rather
    than a dict literal at each call site. Both browser SDK clients derive their
    session storage key from the URL they were handed
    (``theme.js._storageKey``; supabase-js's own default in ``account.js``). Point
    them at ``https://www.mastermind-x.com`` without pinning the key and the browser
    starts writing ``sb-www-auth-token`` while ``app.main`` keeps reading
    ``sb-fsldfzlxyavsuwqbceod-auth-token`` — every existing session orphaned (every
    user silently logged out) and the server never sees a session again. Shipping
    ``ref`` lets both clients pin the key to the PROJECT, so the browser-facing
    origin becomes a routing detail instead of an identity change.

    Used by :func:`bake_theme_js` (for ``theme.js``) and directly by the
    watchlist and committee page builders in ``scripts/build_site.py``.
    """
    sup = (config.load().get("watchlist", {}).get("supabase") or {})
    if not (sup.get("url") and sup.get("anon_key")):
        return json.dumps(None)
    browser_url = str(sup.get("browser_url") or "").strip().rstrip("/")
    cfg = {
        "url": browser_url or sup["url"],
        "anonKey": sup["anon_key"],
        "ref": project_ref(sup["url"]),      # the PROJECT, never the proxy host
    }
    return json.dumps(cfg)


def bake_theme_js(text: str) -> str:
    """Replace the Supabase-config placeholder in theme.js source with live config."""
    return text.replace(SUPABASE_TOKEN, supabase_cfg_json())


def mm_brain_version(src: Path) -> str:
    """The content hash ``theme.js`` must use when it requests ``mm_brain.js``.

    ``src`` is any path in ``templates/``; the bundle is read as its sibling.

    This is deliberately the SAME function ``scripts.optimize_assets`` applies to
    every ``.js``/``.css`` reference it stamps into HTML — ``sha256(bytes)[:8]``.
    Sharing the derivation is the whole point: the ~3,500 pages that carry a
    page-authored ``<script src="../../mm_brain.js?v=…">`` and the pages whose
    launcher requests the bundle dynamically must land on ONE cache key, or a
    reader who crosses between them pays for the same 232 KB twice — and once
    ``mm_brain.js`` moves onto the edge's immutable matcher, a URL that disagreed
    with the stamped one would pin that reader to stale bytes for a year.

    Returns ``""`` when the bundle cannot be read, which leaves theme.js's
    placeholder at its unbaked ``''`` and makes the request unversioned: correct,
    just uncached. A missing sibling is a local/custom build, never production.
    """
    try:
        return hashlib.sha256(src.with_name("mm_brain.js").read_bytes()).hexdigest()[:8]
    except OSError:
        return ""


def emit_theme_js(src: Path) -> str:
    """Build the exact ``theme.js`` bytes served by production."""
    text = bake_theme_js(src.read_text())
    text = text.replace(MM_BRAIN_VER_TOKEN, json.dumps(mm_brain_version(src)))
    overlay_src = src.with_name("terminal_overlay.js")
    if overlay_src.exists():
        text = f"{text.rstrip()}\n\n{overlay_src.read_text().lstrip()}"
    return text


def copy_asset(asset: str, src: Path, dst_dir: Path) -> None:
    """Copy one template asset into a site dir, baking the production theme.

    ``src`` is the full source path (``templates/<asset>``); ``dst_dir`` is the
    site output directory. For every asset except ``theme.js`` this is a plain
    byte-for-byte copy — identical to the ``(dst_dir / asset).write_text(
    src.read_text())`` the builders used before. The emitted ``theme.js`` gets
    its Supabase config plus the separately maintained Terminal overlay source.
    """
    text = emit_theme_js(src) if asset == "theme.js" else src.read_text()
    (dst_dir / asset).write_text(text)
