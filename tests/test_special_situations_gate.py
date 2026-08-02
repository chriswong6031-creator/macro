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

# A row's identity is its whole data-* attribute block, NOT its ticker. This desk
# lists SITUATIONS, and one company routinely carries several: on 2026-07-25 HON
# held a 2026-06-21 spin-off on the paid board while a 2026-07-24 capital return
# sat in the free preview — 80 other tickers had more than one locked row. Same
# company, different rows, so a ticker seen on both sides of the wall is not a
# leak; a shared ROW is. Keying on the ticker also silently exempted every
# ticker-less ("—") row — 12 of them — from the leak check entirely.
CARD_RE = re.compile(r'<div class="ss-row-card"(.*?)>', re.S)


def _row_keys(html: str) -> list[str]:
    """Whitespace-normalised identity of every row card rendered into `html`."""
    return [" ".join(m.group(1).split()) for m in CARD_RE.finditer(html)]


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
        gate={"tier": "essential", "payload": "/premiumdata/special_situations.json",
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


def test_row_identity_separates_two_situations_on_one_ticker():
    """Two situations on one ticker are two rows, and only a repeated ROW leaks.

    Proven against the real partial so the leak check below cannot drift from
    the markup the desk actually ships — and so it can never pass vacuously by
    keying on something the cards no longer carry.
    """
    env = _env()
    partial = env.get_template("_special_situations_rows.html.j2")
    spin, capret = _row("HON", 35), _row("HON", 2)
    spin["cat"], spin["date"] = "Spin-Offs", "2026-06-21"
    capret["cat"], capret["date"] = "Capital Returns", "2026-07-24"

    free, paid = partial.render(rows=[capret]), partial.render(rows=[spin])
    # the same ticker sits on both sides of the wall…
    assert TICKER_RE.findall(free) == TICKER_RE.findall(paid) == ["hon"]
    # …yet they are different rows, so nothing leaked
    assert not set(_row_keys(free)) & set(_row_keys(paid))
    # and the check still bites: the same row on both sides IS caught
    assert set(_row_keys(partial.render(rows=[spin]))) & set(_row_keys(paid))


def test_row_identity_covers_rows_a_ticker_key_would_miss():
    """A ticker-less row is still paid content; identity must not skip it."""
    env = _env()
    partial = env.get_template("_special_situations_rows.html.j2")
    anon = _row("—", 4)
    assert len(_row_keys(partial.render(rows=[anon, _row("AAA", 1)]))) == 2


# ------------------------------------------------------------- shipped artifacts


def test_shipped_shell_leaks_no_paid_row():
    if not PAYLOAD.exists():
        pytest.skip("desk not yet rebaked in the gated shape "
                    "(render.yml scope=sits / nightly emits site/premiumdata/)")
    payload = json.loads(PAYLOAD.read_text())
    if not payload.get("gated"):
        pytest.skip("desk is running ungated (config.yml special_situations.gated=false)")
    shell = SHELL.read_text(encoding="utf-8")
    locked = _row_keys(payload["rows_html"])
    assert locked, "a gated payload with no rows is a vacuous pass"
    assert len(locked) == payload["locked"], (
        "row identities must cover the whole paid board or this check is "
        f"vacuous: keyed {len(locked)} of {payload['locked']} locked rows")
    shell_rows = _row_keys(shell)
    leaked = sorted(set(locked) & set(shell_rows))
    assert leaked == [], ("paid rows readable in the free shell: "
                          f"{[k[:120] for k in leaked[:3]]}")
    assert len(shell_rows) <= payload["preview"] + 1


# ------------------------------------------------- express-lane thinning guard
#
# The guard lives in lib/desk_guard.py (stdlib only) rather than in the builder,
# so this lane can exercise it without importing the page stack (pandas, plotly).


def test_thin_guard_refuses_a_desk_that_lost_a_quarter_of_its_rows():
    """A no-refresh rebake on a machine without the accumulated event store took
    the live desk from 1129 situations to 641 on 2026-07-25. Aging never does
    that in a day, so the guard must refuse instead of shipping a thinner page."""
    from lib import desk_guard

    assert desk_guard.would_thin(641, 1129) is True
    assert desk_guard.would_thin(846, 1129) is True      # just under the floor
    assert desk_guard.would_thin(847, 1129) is False     # ordinary aging passes
    assert desk_guard.would_thin(1200, 1129) is False    # growth always passes


def test_thin_guard_is_inert_without_a_baseline():
    """First build (or an unreadable artifact) must never block itself."""
    from lib import desk_guard

    assert desk_guard.would_thin(1, None) is False
    assert desk_guard.would_thin(1, 0) is False


def test_shipped_count_reads_the_bytes_not_the_snapshot(tmp_path):
    """The count comes from page rows + payload `locked`, because data/'s snapshot
    can be staler than the page it describes — that drift IS the bug, so it
    cannot also be the reference."""
    from lib import desk_guard

    page = tmp_path / "special_situations.html"
    page.write_text('<div class="ss-row-card" data-ticker="a"></div>'
                    '<div class="ss-row-card" data-ticker="b"></div>', encoding="utf-8")
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps({"schema": "tier_payload.v1", "gated": True, "locked": 500}),
                       encoding="utf-8")
    assert desk_guard.shipped_row_count(page, payload) == 502
    # payload absent / ungated -> the page is the whole desk
    assert desk_guard.shipped_row_count(page, tmp_path / "nope.json") == 2
    # no shipped page at all -> no baseline
    assert desk_guard.shipped_row_count(tmp_path / "missing.html") is None


def test_shipped_payload_declares_the_required_tier():
    if not PAYLOAD.exists():
        pytest.skip("desk not yet rebaked in the gated shape")
    payload = json.loads(PAYLOAD.read_text())
    assert payload["schema"] == "tier_payload.v1"
    if payload.get("gated"):
        assert payload["required_tier"] == "essential"
        assert payload["locked"] > 0
