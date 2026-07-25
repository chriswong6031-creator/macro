"""The Special Situations tier gate — the split IS the boundary.

Two layers, deliberately:

* the SPLIT LOGIC is proven hermetically (fake rows, real templates), so the
  contract holds even before a render lane has rebaked the desk;
* the SHIPPED BYTES are then checked against the same invariant — no row that
  the paid payload carries may also sit in the free shell.

The second layer skips (loudly) until the desk has been rebaked in the gated
shape, because the baked page on main lags a template change by one render.
See docs/TIER_PREVIEW_PATTERN.md.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "site" / "special_situations.html"
PAYLOAD = ROOT / "site" / "premiumdata" / "special_situations.json"
TICKER_RE = re.compile(r'data-ticker="([^"]+)"')


def _env():
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    env.globals.update(td=lambda en: en, tr=lambda en: en)
    return env


# The page reads only these palette keys; a literal stand-in keeps this test
# hermetic (importing scripts.build_vector would drag pandas into the lane).
C_STUB = {k: "#333333" for k in
          ("amber", "bg", "blue", "card", "faint", "grid", "indigo", "ink", "muted", "red", "text")}


def _row(ticker: str, n: int) -> dict:
    return {
        "ticker": ticker, "company": f"{ticker} Corp", "cat": "Acquisitions",
        "cat_zh": "收购", "cat_color": "#3b82f6", "stage": "announced", "stage_zh": "已宣布",
        "summary_short": f"{ticker} filed an 8-K announcing a merger agreement.",
        "summary": "", "grade": "A", "grade_word": "Strong setup", "grade_word_zh": "布局成熟",
        "mc": "$1.2B", "mc_bucket": "large", "sector": "Financials", "themes": [],
        "age_days": n, "tech_tokens": [], "score": 100 - n, "date": f"2026-07-{20 - n:02d}",
        "cross_border": False, "live": True, "url": "https://sec.gov/x", "form": "8-K",
        "why": [], "why_zh": [], "tier": None, "tier_word": None, "tier_word_zh": None,
        "oversold": False, "momentum_state": None, "sector_stance": None, "standout": None,
        "low_conf": False, "n_amend": 0, "prior": None, "prior_plain": None,
        "prior_plain_zh": None, "arb": None, "source_lane": "edgar", "confidence": "high",
        "needs": False,
    }


# ---------------------------------------------------------------- policy shape


def _policy() -> dict:
    return yaml.safe_load((ROOT / "config" / "site_access.yml").read_text())


def test_payload_prefix_is_enforced_ahead_of_the_launch_switch():
    early = _policy()["premium"]["enforced_early"]
    assert "/premiumdata/" in early["prefixes"], (
        "the paid payload lane must be gated regardless of PAYWALL_ENABLED — "
        "otherwise the desk is open to every registered account"
    )


def test_preview_shell_is_free_registered_not_premium():
    """The page URL must stay reachable for Free, or there is no preview at all."""
    assert "/special_situations.html" in _policy()["free_registered"]["exact"]


def test_payload_prefix_is_not_public():
    pol = _policy()
    assert "/premiumdata/" not in pol["public"]["prefixes"]
    assert not any(p.startswith("/premiumdata/") for p in pol["public"]["exact"])


def test_gate_switch_and_preview_size_are_config_driven():
    cfg = yaml.safe_load((ROOT / "config.yml").read_text())["special_situations"]
    assert cfg["gated"] is True
    assert isinstance(cfg["preview_rows"], int) and 1 <= cfg["preview_rows"] <= 10


# ------------------------------------------------------------- split mechanics


def test_row_partial_renders_only_the_rows_it_is_handed():
    html = _env().get_template("_special_situations_rows.html.j2").render(
        rows=[_row("AAA", 1), _row("BBB", 2)])
    assert set(TICKER_RE.findall(html)) == {"aaa", "bbb"}
    assert "CCC" not in html


def test_gated_shell_omits_locked_rows_and_the_setup_strip():
    env = _env()
    preview, locked = [_row("AAA", 1)], [_row("BBB", 2), _row("CCC", 3)]
    shell = env.get_template("special_situations.html.j2").render(
        rows=preview, groups=[], cat_chips=[], cat_chips_more=[], sector_opts=[],
        theme_opts=[], total=3, n_cats=1, counts={}, coverage={}, built="2026-07-25 00:00 UTC",
        top_setups=[], grade_a=1, new_today=0, intel_cov={},
        gate={"tier": "insider", "payload": "/premiumdata/special_situations.json",
              "preview": 1, "locked": 2},
        C=C_STUB)
    assert set(TICKER_RE.findall(shell)) == {"aaa"}
    for locked_row in locked:
        assert locked_row["summary_short"] not in shell
    # the wall, the inert filter bar and the skeleton strip are all present…
    assert 'id="ss-tier-wall"' in shell
    assert 'class="filter-bar gated"' in shell
    assert 'class="setup-chip setup-ghost"' in shell   # markup, not the CSS selector
    # …and the shell asks the server for the rest rather than deciding locally
    assert "/premiumdata/special_situations.json" in shell
    assert "plans.html" in shell


def test_ungated_shell_keeps_every_row_and_no_wall():
    env = _env()
    shell = env.get_template("special_situations.html.j2").render(
        rows=[_row("AAA", 1), _row("BBB", 2)], groups=[], cat_chips=[], cat_chips_more=[],
        sector_opts=[], theme_opts=[], total=2, n_cats=1, counts={}, coverage={},
        built="2026-07-25 00:00 UTC", top_setups=[], grade_a=0, new_today=0, intel_cov={},
        gate=None, C=C_STUB)
    assert set(TICKER_RE.findall(shell)) == {"aaa", "bbb"}
    assert 'id="ss-tier-wall"' not in shell
    assert 'class="setup-chip setup-ghost"' not in shell
    assert "var GATE = null" in shell


# ------------------------------------------------------------- shipped artifacts


def test_shipped_shell_leaks_no_paid_row():
    if not PAYLOAD.exists():
        pytest.skip("desk not yet rebaked in the gated shape "
                    "(render.yml scope=sits / nightly emits site/premiumdata/)")
    payload = json.loads(PAYLOAD.read_text())
    if not payload.get("gated"):
        pytest.skip("desk is running ungated (config.yml special_situations.gated=false)")
    shell = SHELL.read_text(encoding="utf-8")
    locked = {t for t in TICKER_RE.findall(payload["rows_html"]) if t and t != "—"}
    assert locked, "a gated payload with no rows is a vacuous pass"
    leaked = sorted(t for t in locked if f'data-ticker="{t}"' in shell)
    assert leaked == [], f"paid rows readable in the free shell: {leaked[:8]}"
    assert len(TICKER_RE.findall(shell)) <= payload["preview"] + 1


def test_shipped_payload_declares_the_required_tier():
    if not PAYLOAD.exists():
        pytest.skip("desk not yet rebaked in the gated shape")
    payload = json.loads(PAYLOAD.read_text())
    assert payload["schema"] == "tier_payload.v1"
    if payload.get("gated"):
        assert payload["required_tier"] == "insider"
        assert payload["locked"] > 0
