"""Regression tests for lib/site_assets.py — Supabase bake integrity.

Guards against the original bug where ~11 builders copied theme.js RAW via
`write_text(src.read_text())`, clobbering the baked token and leaving
`window.SUPABASE_CFG = null` (auth silently dead) on every page.

No network, no full render — all tests are deterministic and fast.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Ensure the repo root is on the path regardless of how pytest is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, site_assets  # noqa: E402

WORKTREE = Path(__file__).resolve().parent.parent
TEMPLATES = WORKTREE / "templates"
SCRIPTS = WORKTREE / "scripts"

# The literal placeholder token that must NEVER survive into the deployed file.
TOKEN = "/*__SUPABASE_CFG__*/null"

# Regex: "theme.js" appearing inside an ASSETS tuple/list or a `for asset in (...)`
# loop — the copy-context patterns.  Excludes HTML src= attribute strings which are
# NOT copy paths (e.g. build_vector.py embeds '<script src="theme.js">').
_ASSETS_RE = re.compile(
    r'ASSETS\s*=\s*\([^)]*"theme\.js"'          # ASSETS = ("theme.css", "theme.js", ...)
    r'|for\s+\w+\s+in\s+\([^)]*"theme\.js"',    # for asset in ("theme.css", "theme.js", ...)
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# 1. copy_asset bakes theme.js — token gone, real config present
# ---------------------------------------------------------------------------

def test_copy_asset_bakes_theme_js(tmp_path: Path) -> None:
    """copy_asset('theme.js', ...) must replace the placeholder with live config."""
    src = TEMPLATES / "theme.js"
    assert src.exists(), "templates/theme.js must exist"

    site_assets.copy_asset("theme.js", src, tmp_path)
    out = (tmp_path / "theme.js").read_text()

    # Token must be gone.
    assert TOKEN not in out, (
        "copy_asset() left the raw SUPABASE_CFG placeholder in theme.js — "
        "auth will be silently dead on every page."
    )

    # With config.yml populated the baked JS must contain the real Supabase URL.
    sup = (config.load().get("watchlist", {}).get("supabase") or {})
    if sup.get("url") and sup.get("anon_key"):
        assert "supabase.co" in out, (
            "Expected baked theme.js to contain 'supabase.co' from config.yml."
        )
        assert "anonKey" in out, (
            "Expected baked theme.js to contain 'anonKey' JSON key."
        )


# ---------------------------------------------------------------------------
# 2. copy_asset is byte-parity for non-theme assets
# ---------------------------------------------------------------------------

def test_copy_asset_plain_copy_for_non_theme(tmp_path: Path) -> None:
    """copy_asset must copy non-theme.js assets byte-for-byte without modification."""
    src = TEMPLATES / "theme.css"
    assert src.exists(), "templates/theme.css must exist"

    site_assets.copy_asset("theme.css", src, tmp_path)
    out = (tmp_path / "theme.css").read_text()
    assert out == src.read_text(), (
        "copy_asset() modified theme.css — only theme.js should be baked."
    )


# ---------------------------------------------------------------------------
# 3. bake_theme_js is no-op on already-baked text
# ---------------------------------------------------------------------------

def test_bake_theme_js_idempotent_on_already_baked_text() -> None:
    """bake_theme_js() on text with no token must return the text unchanged."""
    already_baked = 'window.SUPABASE_CFG = window.SUPABASE_CFG || {"url":"https://x.supabase.co","anonKey":"abc"};'
    result = site_assets.bake_theme_js(already_baked)
    assert result == already_baked, (
        "bake_theme_js() must be a no-op when the token is absent."
    )


# ---------------------------------------------------------------------------
# 4. Sole-carrier guard: only theme.js carries the raw token in templates/
# ---------------------------------------------------------------------------

def test_sole_token_carrier_is_theme_js() -> None:
    """templates/theme.js must be the ONLY file under templates/ carrying the token.

    If another template file is accidentally given the placeholder, this test
    fails CI — alerting the author before a silent auth regression ships.
    """
    carriers = [
        f for f in TEMPLATES.rglob("*")
        if f.is_file() and TOKEN in f.read_text(errors="replace")
    ]
    assert len(carriers) == 1, (
        f"Expected exactly 1 file under templates/ to carry {TOKEN!r}; "
        f"found {len(carriers)}: {[str(c) for c in carriers]}"
    )
    assert carriers[0].name == "theme.js", (
        f"The sole carrier of {TOKEN!r} should be theme.js, got {carriers[0].name}"
    )


# ---------------------------------------------------------------------------
# 5. Anti-recurrence guard: no build_*.py writes theme.js raw
# ---------------------------------------------------------------------------

def test_no_builder_writes_theme_js_raw() -> None:
    """Every build_*.py that ships theme.js must route through site_assets.copy_asset.

    The original bug: builders used  `(site / a).write_text(src.read_text())`
    which bypassed the Supabase bake.  This test catches any regression.

    Checks two invariants for each builder whose source mentions '"theme.js"':
      a) Its source does NOT contain the raw-write anti-pattern.
      b) Its source DOES contain 'site_assets.copy_asset'.
    """
    # Patterns that indicate a raw, un-baked copy.
    raw_patterns = [
        "write_text(src.read_text())",
        "write_text(srcf.read_text())",
    ]

    # Only include builders that actively copy theme.js (i.e. it appears in an ASSETS
    # tuple or a `for asset in (...)` copy loop). Builders that merely reference
    # "theme.js" inside HTML src= attributes (e.g. build_vector.py) are excluded —
    # those are not copy paths and the test assertion does not apply to them.
    builders_with_theme = [
        f for f in SCRIPTS.glob("build_*.py")
        if _ASSETS_RE.search(f.read_text())
    ]
    assert builders_with_theme, "Expected at least one build_*.py to ship 'theme.js' via ASSETS"

    failures: list[str] = []
    for bf in sorted(builders_with_theme):
        src_text = bf.read_text()

        # (a) Must NOT contain raw-write patterns.
        for pat in raw_patterns:
            if pat in src_text:
                failures.append(
                    f"{bf.name}: contains raw-write pattern {pat!r} "
                    "(bypasses Supabase bake)"
                )

        # (b) Must contain the copy_asset call.
        if "site_assets.copy_asset" not in src_text:
            failures.append(
                f"{bf.name}: references 'theme.js' but does not call "
                "site_assets.copy_asset — bake may be bypassed"
            )

    if failures:
        msg = "\n".join(failures)
        raise AssertionError(
            f"Builder(s) found that may copy theme.js without baking:\n{msg}"
        )
