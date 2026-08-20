"""P-MP1-SHELL §7/§11/§12 item 3 — non-US byte-parity proof.

MP-1-prophet-board.md §7: "Other markets: hk/china/canada/intl keep the legacy
rail via the pv_card parameter default (ruling §10.2) — zero rendered-byte
change on non-US pages, test-pinned." §12 acceptance item 3: "The pv_card
lifecycle parameter defaults to legacy: non-US templates render byte-identical."

The ONLY file this packet's diff shares with hk.html.j2/china.html.j2/
canada.html.j2/intl.html.j2 is templates/_prophet_card.html.j2 (each of those
four does `{% import "_prophet_card.html.j2" as pv %}` then calls
`pv.pv_css()` once and `pv.pv_card(cx)` per row, with NO `lifecycle`/`id`/
`life`/`lane_mark` keys — every existing non-US call site). This suite proves,
against origin/main's pre-migration copy of that file:

  1. The four non-US page templates themselves are byte-identical to
     origin/main (git diff --stat empty) — confirming no OTHER file in this
     packet's diff touches them.
  2. pv_css() — the shared <style> block every one of those four pages
     renders once — is byte-identical. This is the check that caught a real
     defect during this packet's build: the new .pv-life/.pv-newer/.pv-mark
     CSS was first added INSIDE pv_css() (shared), which would have changed
     all four pages' bytes; it now lives in dashboard.html.j2's own <style>
     block instead (US-only, never included by the other four).
  3. pv_card() — the per-row card macro — is byte-identical for representative
     cx dicts shaped exactly like the non-US callers' (no lifecycle/id/life/
     lane_mark keys), across several branches (buy/wait/hold/no-zone/flags/
     marks) so an additive-parameter regression that only shows up on one
     branch cannot hide.

A full whole-page render diff (synthetic VM through hk.html.j2 etc. in full)
is NOT attempted here — building synthetic view-models for four more
templates of this size is out of this suite's scope. Given (1) — no other
touched file — the shared-macro proof above is the complete surface by
construction: nothing else in the diff can reach those four pages' bytes.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import jinja2

ROOT = Path(__file__).resolve().parent.parent
NON_US_TEMPLATES = [
    "templates/hk.html.j2",
    "templates/china.html.j2",
    "templates/canada.html.j2",
    "templates/intl.html.j2",
]


def _origin_main_text(rel_path: str) -> str:
    return subprocess.check_output(
        ["git", "show", f"origin/main:{rel_path}"], cwd=str(ROOT)
    ).decode()


def test_non_us_page_templates_are_untouched():
    """Confirms no file besides _prophet_card.html.j2 in this packet's diff
    can reach hk/china/canada/intl's rendered bytes at all."""
    out = subprocess.check_output(
        ["git", "diff", "--stat", "origin/main", "HEAD", "--", *NON_US_TEMPLATES],
        cwd=str(ROOT),
    ).decode()
    assert out.strip() == "", f"non-US template(s) changed:\n{out}"


def _macros():
    orig_src = _origin_main_text("templates/_prophet_card.html.j2")
    cur_src = (ROOT / "templates" / "_prophet_card.html.j2").read_text()
    env = jinja2.Environment(autoescape=True)
    return env.from_string(orig_src).module, env.from_string(cur_src).module


def test_pv_css_is_byte_identical():
    """The shared <style> block every non-US page renders once via pv.pv_css()."""
    orig, cur = _macros()
    assert str(orig.pv_css()) == str(cur.pv_css())


def _base_cx(**overrides) -> dict:
    cx = {
        "href": "stock.html#0700.HK", "tk": "0700", "mkt": "hk",
        "name": "Tencent", "sec": "Communication Services",
        "price_txt": "$400.00", "show_change": True,
        "verb": "buy", "edge": 72,
        "stage": 3, "spark": None,
        "zone_kind": "active", "zone_lo": "$390.00", "zone_hi": "$410.00",
        "date": "2026-07-04", "flags": [], "triage": False, "featured": False,
        "marks": None,
    }
    cx.update(overrides)
    return cx


CX_VARIANTS = [
    ("buy_featured", _base_cx(verb="buy", featured=True)),
    ("wait_no_zone", _base_cx(verb="wait", zone_kind="none", zone_lo=None, zone_hi=None, stage=0)),
    ("hold_readd", _base_cx(verb="hold", zone_kind="readd")),
    ("avoid_with_flags", _base_cx(
        verb="avoid",
        flags=[("Earnings soon", "财报临近"), ("Extended", "过热")],
    )),
    ("with_marks_and_trigger", _base_cx(
        marks=[{"k": "new", "en": "New", "zh": "新"},
               {"k": "theme", "en": "AI", "zh": "AI"}],
        trigger={"kind": "fired", "tip_en": "Fired.", "tip_zh": "已触发。"},
    )),
    ("triage_no_price", _base_cx(price_txt=None, show_change=False, triage=True)),
]


def test_pv_card_is_byte_identical_across_representative_non_us_calls():
    orig, cur = _macros()
    for label, cx in CX_VARIANTS:
        out_orig = str(orig.pv_card(cx))
        out_cur = str(cur.pv_card(cx))
        assert out_orig == out_cur, f"pv_card diverged for variant {label!r}"
