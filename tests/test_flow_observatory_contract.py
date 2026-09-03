"""Flow Observatory V2 W1 — the trust strip, changed-today read, and absolute-vs-relative
truth on flow_velocity.html (research/flow_observatory/W1_SPEC.md).

Written FIRST and failing per the frozen spec's §0 gate. The pure-contract tests (1-3, 6-8,
10, 13-15) exercise ``engine/flow_observatory/{contract,changes}.py`` directly; the
template-integration tests (4, 5, 9, 11, 12) render ``templates/flow_velocity.html.j2``
against fixtures and would fail on the pre-W1 template (no trust strip / quadrant board /
changed-today section) even once the engine math is right — that gap is the whole point:
correct numbers behind an unconflated LABEL is the thing the live page was missing.

The motivating defect (mission brief): the live page showed Autos vel +2.58σ as an
inflow-colored +1.9% while raw 4-week flow was -0.9%, and Southbound "accelerating out"
beside a +¥7.1B absolute figure. The Autos/Southbound fixtures below are the real shapes
measured off the current build (`site/flowdata/desk.json`, 2026-09-02) — not invented
numbers — so the quadrant math is pinned against the actual defect, not a toy case.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from engine import i18n
from engine.cn_theme_tape import build_cn_theme_tape
from engine.flow_observatory import changes as fo_changes
from engine.flow_observatory.contract import (
    QUADRANT_LABELS,
    STATUS_WORD,
    ContractError,
    build_sources,
    build_v2,
    direction_from_value,
    market_read,
    quadrant,
    rel_direction,
    validate,
)
from scripts.build_vector import C

ROOT = Path(__file__).resolve().parent.parent
TMPL = ROOT / "templates"

# banned-vocabulary list — masterplan §6 language law, exact
BANNED = ["big money", "institutions are buying", "institutional accumulation",
         "smart money", "大资金", "机构买入"]
OLD_VOCAB = ["accelerating in", "inflow cooling", "accelerating out", "outflow easing"]


# ── fixtures: the real Autos/Southbound shapes measured off the live desk ─────────────
def _autos_row(**over):
    row = {"id": "cn_autos", "name": "Autos & NEV Makers", "name_zh": "汽车整车",
          "category": "New Energy & Autos", "n_members": 16,
          "vel": 2.58, "accel": -0.009, "rate_now": 2.9, "rate_4wk": -0.9,
          "rate_norm": -2.8, "rate_rel": 1.9,
          "state": "above norm, cooling", "state_zh": "高于常态·降温",
          "spark": None, "members": [], "inst_attention": 0}
    row.update(over)
    return row


def _gold_row(**over):
    row = {"id": "cn_gold", "name": "Gold Miners", "name_zh": "黄金",
          "category": "Materials", "n_members": 6,
          "vel": 1.1, "accel": 0.02, "rate_now": 1.0, "rate_4wk": 1.2,
          "rate_norm": -0.5, "rate_rel": 1.7,
          "state": "above norm, rising", "state_zh": "高于常态·升温",
          "spark": None, "members": [], "inst_attention": 0}
    row.update(over)
    return row


def _member(**over):
    """A shared-kinetics-map member record (engine.flow_velocity._name_kinetics_map shape)
    — the same dict shape ``ashare_sector_velocity`` puts in a theme row's ``members[]``.
    Ships abs (rate_4wk) and rel (rate_rel) DIFFERENT on purpose (B2): a fixture where they
    happened to be equal could pass a broken template that swapped the two columns."""
    m = {"ticker": "600104.SS", "name": "SAIC Motor", "vel": 2.58, "accel": -0.009,
        "rate_now": 2.9, "rate_4wk": -0.9, "rate_norm": -2.8, "rate_rel": 1.9,
        "state": "above norm, cooling", "state_zh": "高于常态·降温"}
    m.update(over)
    return m


def _snap(**over):
    snap = {
        "as_of": "2026-09-01",
        "aggregate": [
            {"key": "southbound", "label": "Southbound — mainland money into HK",
             "label_zh": "南向 · 内地资金入港", "live": True, "as_of": "2026-09-01",
             "spark": None, "flow_1m_b": 7.1, "pos_days_20": 12,
             "vel": {"1w": -1.0, "1m": -1.52, "3m": -0.8}, "accel": -0.05,
             "vel_primary": -1.52, "primary": "1m",
             "state": "below norm, worsening", "state_zh": "低于常态·加剧"},
            {"key": "northbound", "label": "Northbound — foreign money into A-shares",
             "label_zh": "北向 · 外资入A股", "live": False, "as_of": None,
             "spark": None, "frozen_since": "2024-08-16",
             "note": "Aggregate northbound net disclosure ended 2024-08-16 (Stock Connect "
                     "home-market rule) — historical only, no live velocity.",
             "note_zh": "北向资金净额披露于2024-08-16停止（互联互通本地市场规则）——仅历史，无实时流速。"},
        ],
        "ashare_names": {
            "cadence": "daily", "as_of": "2026-09-01", "n": 10, "n_unscored": 3,
            "primary": "4wk", "note": "note", "note_zh": "note_zh",
            "market_read": market_read(
                [{"vel": 1.0, "rate_4wk": 0.5, "state": "above norm, rising"}] * 10, unscored=3),
            "inflow": [], "outflow": [],
        },
        "ashare_sectors": {
            "cadence": "daily", "as_of": "2026-09-01", "n": 2, "n_unscored": 0,
            "primary": "4wk", "note": "sector note", "note_zh": "板块说明",
            "rows": [_autos_row(), _gold_row()],
        },
        "hk_names": {
            "as_of": "2026-08-31", "n": 400, "n_sized": 380,
            "note": "hk note", "buying": [], "selling": [],
            "depth": 40, "vel_ready": True, "basis": "net-share flow velocity",
            "basis_zh": "净持股流速",
        },
        "seats_by_ticker": {"600104.SS": {"inst_net_yi": 1.2, "n_buy": 3, "n_sell": 1, "dir": "buy"}},
        "seats_as_of": "2026-08-30",
        "sb_vel_primary": -1.52,
        "confluence": None, "momentum": None,
        "pulse": {"breadth": {"names_in": 0, "names_out": 0, "n_names": 0,
                              "sectors_in": 1, "sectors_out": 1, "n_sectors": 2,
                              "tilt": 0, "state": "mixed", "state_zh": "分化"},
                 "dominant_in": None, "dominant_out": None,
                 "sb": {"vel": -1.52, "state": "below norm, worsening", "state_zh": "低于常态·加剧"},
                 "inst": {"agree": 0, "diverge": 0}},
        "note": "Display-only positioning lens — flow is never scored into an allocation signal.",
    }
    snap.update(over)
    return snap


def _v2(log_rows=None, market_session="2026-09-01", **over):
    return build_v2(_snap(**over), log_rows=log_rows or [], market_session=market_session,
                    generated_at="2026-09-01T12:00:00+00:00", seats_as_of="2026-08-30")


def _render(v2, built="test"):
    env = Environment(loader=FileSystemLoader(str(TMPL)), autoescape=True)
    env.globals.update(td=i18n.td, tr=i18n.tr, quadrant_labels=QUADRANT_LABELS,
                       status_word=STATUS_WORD)
    return env.get_template("flow_velocity.html.j2").render(C=C, snap=v2, built=built)


def _visible_only(html: str) -> str:
    """Strip data-tip-en/zh attribute VALUES so a figure that appears only inside a
    tooltip does not satisfy an "on screen at rest" assertion (spec §2.4/§0.4: abs and
    rel must be visible without hover, mutation check M2)."""
    return re.sub(r'data-tip-(?:en|zh)="[^"]*"', "", html)


# ── 1-3: quadrant axis logic (pure) ────────────────────────────────────────────────
def test_absolute_negative_relative_positive_is_improving_but_still_selling():
    """The Autos defect itself: abs -0.9% (still selling) + rel +2.58σ (pressure easing
    vs its own norm) must NOT collapse into a single inflow-colored number."""
    ad, rd = direction_from_value(-0.9, "pct_rate"), rel_direction(2.58)
    assert (ad, rd) == ("negative", "positive")
    assert quadrant(ad, rd) == "improving_but_still_selling"
    en, zh = QUADRANT_LABELS["improving_but_still_selling"]
    assert en == "still selling, pressure easing"
    assert zh == "仍净流出·压力改善"


def test_absolute_positive_relative_negative_is_weakening_but_still_buying():
    """The Southbound defect: abs +¥7.1B (still bought) + rel -1.52σ (below its own norm,
    fading) — never rendered as a bare "accelerating out"."""
    ad, rd = direction_from_value(7.1, "cny_b"), rel_direction(-1.52)
    assert (ad, rd) == ("positive", "negative")
    assert quadrant(ad, rd) == "weakening_but_still_buying"
    en, zh = QUADRANT_LABELS["weakening_but_still_buying"]
    assert en == "still buying, pace fading"
    assert zh == "仍净流入·动能转弱"


def test_quadrant_insufficient_or_unknown_is_neutral():
    assert quadrant("positive", "positive", sufficient=False) == "neutral_or_unknown"
    for bad_abs, bad_rel in [("unknown", "positive"), ("positive", "unknown"),
                             ("neutral", "positive"), ("positive", "neutral")]:
        assert quadrant(bad_abs, bad_rel) == "neutral_or_unknown"
    # de-minimis bands feed the SAME neutral verdict
    assert direction_from_value(0.05, "pct_rate") == "neutral"
    assert direction_from_value(0.3, "cny_b") == "neutral"
    assert rel_direction(0.2) == "neutral"
    assert direction_from_value(None, "pct_rate") == "unknown"
    assert rel_direction(None) == "unknown"


# ── 4-5: template integration — the anti-conflation device on screen ──────────────
def test_autos_fixture_cannot_render_unqualified_inflow():
    v2 = _v2()
    autos = next(r for r in v2["ashare_sectors"]["rows"] if r["id"] == "cn_autos")
    assert autos["quadrant"] == "improving_but_still_selling"
    html = _render(v2)
    assert "still selling, pressure easing" in html
    assert "仍净流出·压力改善" in html
    for bad in OLD_VOCAB:
        assert bad not in html, f"old vocabulary {bad!r} leaked into the rendered page"
    for bad in BANNED:
        assert bad not in html, f"banned unqualified vocabulary {bad!r} in the rendered page"
    # gate #2 (§0.2): abs -0.9% AND rel +2.58σ must both be figures at rest, not
    # tooltip-only — the exact "single inflow-colored number" defect the mission cites.
    visible = _visible_only(html)
    assert "0.9" in visible, "the raw abs 4wk figure must be visible at rest"
    assert "2.58" in visible or "2.6" in visible, "the rel (velocity σ) figure must be visible at rest"


def test_southbound_fixture_keeps_absolute_and_relative_visible():
    v2 = _v2()
    sb = next(c for c in v2["aggregate"] if c["key"] == "southbound")
    assert sb["quadrant"] == "weakening_but_still_buying"
    visible = _visible_only(_render(v2))
    assert "7.1" in visible, "the absolute ¥B figure must be visible at rest, not tooltip-only"
    # scope to the Southbound card itself — the quadrant board's own section header for this
    # SAME enum string is always present, so a whole-page substring search would pass even
    # if the card's own abs×rel chip were dropped (that is the exact M2 failure mode to catch).
    idx = visible.find("Southbound — mainland money into HK")
    assert idx != -1, "southbound card not found"
    card_window = visible[idx:idx + 800]
    assert "still buying, pace fading" in card_window, (
        "the abs×rel quadrant label must be visible at rest ON THE CARD, not tooltip-only — "
        "this is the exact anti-conflation device (spec §2.6/mutation M2)")


# ── 6: market_read denominators / neutral / unscored ───────────────────────────────
def test_market_read_counts_include_neutral_and_unscored():
    rows = [
        {"vel": 1.2, "rate_4wk": 2.0, "state": "above norm, rising"},
        {"vel": -1.2, "rate_4wk": -2.0, "state": "below norm, worsening"},
        {"vel": 0.1, "rate_4wk": 0.02, "state": "near its norm"},   # neutral both axes
        {"vel": None, "rate_4wk": None, "state": "no data"},         # unknown both axes
    ]
    mr = market_read(rows, unscored=5)
    assert mr["absolute_breadth"]["denominator"] == 9
    assert mr["relative_breadth"]["denominator"] == 9
    assert mr["acceleration_breadth"]["denominator"] == 9
    assert mr["absolute_breadth"]["positive"] == 1
    assert mr["absolute_breadth"]["negative"] == 1
    assert mr["absolute_breadth"]["neutral"] == 1
    assert mr["absolute_breadth"]["missing"] == 5 + 1        # unscored + the unknown row
    assert mr["relative_breadth"]["missing"] == 5 + 1
    assert mr["acceleration_breadth"]["strengthening"] == 1
    assert mr["acceleration_breadth"]["worsening"] == 1
    assert mr["acceleration_breadth"]["neutral_or_unknown"] == 5 + 2   # unscored + near-norm + no-data


# ── 7-8: rank/state history vs the previous VALID snapshot only ───────────────────
def test_rank_and_state_changes_compare_previous_valid_snapshot_only():
    """A lane that skipped a session (no line logged for it) must not manufacture a
    transition across the gap it never observed — comparison walks back to the NEWEST
    logged session strictly before today, whatever the calendar gap."""
    log_rows = [
        {"session": "2026-08-28", "written_at": "x", "aggregate": {}, "market_read": {},
         "themes": {"cn_autos": {"quadrant": "true_distribution", "state": "s", "vel": -2.0,
                                 "rank": 5, "abs": -3.0}}},
        # 2026-08-29/30/31 deliberately absent (skipped sessions)
    ]
    v2 = _v2(log_rows=log_rows, market_session="2026-09-01")
    autos = next(r for r in v2["ashare_sectors"]["rows"] if r["id"] == "cn_autos")
    assert autos["prior_state"] == "true_distribution"
    assert autos["state_started"] == "2026-09-01"       # quadrant changed vs 08-28 -> fresh state
    assert autos["state_age_sessions"] == 1
    assert autos["rank_change"] == autos["rank"] - 5


def test_missing_previous_snapshot_yields_null_not_zero():
    """Empty log -> NULL/"first tracked session", never a manufactured zero-change claim
    (missing != zero, §4 law)."""
    v2 = _v2(log_rows=[])
    autos = next(r for r in v2["ashare_sectors"]["rows"] if r["id"] == "cn_autos")
    assert autos["state_started"] is None
    assert autos["state_age_sessions"] is None
    assert autos["prior_state"] is None
    assert autos["state_note"] == "first tracked session"
    assert autos["rank_change"] is None

    cs = fo_changes.compute_changes({"session": "2026-09-01", "themes": {}}, [])
    assert cs["material_change"] is None
    assert cs["previous_valid_session"] is None
    assert cs["reason"] == "no_previous_snapshot"


# ── 9: the quiet "what changed today" state, rendered ───────────────────────────────
def test_no_material_transition_yields_quiet_message():
    log_rows = [
        {"session": "2026-08-31", "written_at": "x", "aggregate": {}, "market_read": {},
         "themes": {"cn_autos": {"quadrant": "improving_but_still_selling", "state": "s",
                                 "vel": 2.5, "rank": 1, "abs": -0.8},
                    "cn_gold": {"quadrant": "true_accumulation", "state": "s",
                               "vel": 1.0, "rank": 2, "abs": 1.0}}},
    ]
    v2 = _v2(log_rows=log_rows, market_session="2026-09-01")
    current_themes = {r["id"]: {"quadrant": r["quadrant"], "state": r.get("state"),
                                "vel": r.get("vel"), "rank": r.get("rank"),
                                "abs": (r.get("abs") or {}).get("value")}
                      for r in v2["ashare_sectors"]["rows"]}
    v2["change_summary"] = fo_changes.compute_changes(
        {"session": "2026-09-01", "themes": current_themes}, log_rows)
    assert v2["change_summary"]["material_change"] is False
    out = _render(v2)
    assert ("No material flow-state transition since the previous valid market session "
            "(2026-08-31)." in out)
    assert "自上一有效交易日（2026-08-31）以来，资金状态无重大变化。" in out


# ── 10: source legs keep distinct dates ────────────────────────────────────────────
def test_source_leg_dates_stay_distinct():
    v2 = _v2()
    sources = build_sources(v2, newest_session="2026-09-01", seats_as_of="2026-08-30")
    by_id = {s["source_id"]: s for s in sources}
    assert by_id["hk_sb_holdings"]["effective_date"] == "2026-08-31"
    assert by_id["cn_large_order_proxy"]["effective_date"] == "2026-09-01"
    assert by_id["lhb_inst_seats"]["effective_date"] == "2026-08-30"
    dates = {s["effective_date"] for s in sources if s["effective_date"]}
    assert len(dates) > 1, "every leg collapsed onto one shared date"
    assert by_id["nb_aggregate"]["status"] == "HISTORICAL_ONLY"
    assert by_id["nb_aggregate"]["effective_date"] != by_id["cn_large_order_proxy"]["effective_date"]


# ── 11: proxy disclosure copy, rendered ────────────────────────────────────────────
def test_order_size_copy_carries_proxy_disclosure():
    out = _render(_v2())
    assert "order-size classification" in out or "order-size proxy" in out
    assert "not identified investors" in out or "非机构身份识别" in out
    for bad in BANNED:
        assert bad not in out, f"banned unqualified vocabulary {bad!r} in the rendered page"


def test_real_build_output_carries_v2_vocabulary_and_no_old_vocab_or_banned_terms():
    """Integration proof through the REAL engine (not a synthetic fixture): builds off
    committed `data/`, so this is the test that actually EXERCISES `flow_velocity._classify`
    end to end — the fixture-based tests above pin the CONTRACT logic but hardcode their own
    state strings and would not notice `_classify` itself reverting to the old vocabulary.
    Mutation check M1 (PR body): reverting `_classify` to the pre-W1 strings must fail this
    test (and test_flow_velocity.py's demeaning test) via the real data path.
    """
    from engine.flow_velocity import snapshot as real_snapshot
    snap = real_snapshot()
    if not snap or not (snap.get("ashare_sectors") or {}).get("rows"):
        pytest.skip("committed China flow data unavailable in this checkout")
    v2 = build_v2(snap, log_rows=[], market_session=snap.get("as_of"),
                 generated_at="2026-09-01T12:00:00+00:00", seats_as_of=snap.get("seats_as_of"))
    out = _render(v2)
    for bad in OLD_VOCAB:
        assert bad not in out, (
            f"old vocabulary {bad!r} reached the REAL rendered page — _classify has reverted "
            "or a consumer is bypassing the v2 vocabulary")
    for bad in BANNED:
        assert bad not in out, f"banned unqualified vocabulary {bad!r} in the real rendered page"


# ── 12: EN/ZH parity for every new label ───────────────────────────────────────────
def test_en_zh_parity_for_new_labels():
    out = _render(_v2())
    pairs = [
        ("still selling, pressure easing", "仍净流出·压力改善"),
        ("still buying, pace fading", "仍净流入·动能转弱"),
        ("real inflow, above norm", "真实流入·高于常态"),
        ("real outflow, below norm", "真实流出·低于常态"),
    ]
    for en, zh in pairs:
        assert en in out, f"EN label {en!r} missing"
        assert zh in out, f"ZH twin {zh!r} missing for EN label {en!r}"


# ── 13: state_log idempotence ──────────────────────────────────────────────────────
def test_state_log_append_is_idempotent_per_session(tmp_path):
    data_root = tmp_path
    e1 = {"themes": {"cn_autos": {"quadrant": "true_accumulation", "state": "s", "vel": 1.0,
                                  "rank": 1, "abs": 1.0}}, "aggregate": {}, "market_read": {}}
    r1 = fo_changes.append_state_log("2026-09-01", e1, data_root, require_lane=False)
    assert r1["written"] and r1["rows"] == 1

    other_day = {"themes": {"cn_autos": {"quadrant": "true_accumulation", "state": "s",
                                         "vel": 0.9, "rank": 2, "abs": 0.8}},
                "aggregate": {}, "market_read": {}}
    fo_changes.append_state_log("2026-08-31", other_day, data_root, require_lane=False)
    before = fo_changes.state_log_path(data_root).read_text()

    e1b = {"themes": {"cn_autos": {"quadrant": "true_distribution", "state": "s2", "vel": -2.0,
                                   "rank": 5, "abs": -3.0}}, "aggregate": {}, "market_read": {}}
    r2 = fo_changes.append_state_log("2026-09-01", e1b, data_root, require_lane=False)
    assert r2["written"] and r2["rows"] == 2, "re-running the SAME session must replace, not duplicate"

    rows = fo_changes.read_state_log(data_root)
    assert len(rows) == 2
    sept1 = next(r for r in rows if r["session"] == "2026-09-01")
    assert sept1["themes"]["cn_autos"]["quadrant"] == "true_distribution"
    aug31 = next(r for r in rows if r["session"] == "2026-08-31")
    assert aug31["themes"]["cn_autos"]["rank"] == 2, "an untouched session's line must stay byte-stable"
    after_text = fo_changes.state_log_path(data_root).read_text()
    before_line = next(l for l in before.splitlines() if '"2026-08-31"' in l)
    assert before_line in after_text.splitlines()


def test_state_log_advance_is_lane_gated(tmp_path, monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)
    monkeypatch.delenv("CN_LANE", raising=False)
    e1 = {"themes": {}, "aggregate": {}, "market_read": {}}
    r = fo_changes.append_state_log("2026-09-01", e1, tmp_path)   # require_lane defaults True
    assert r["written"] is False and r["reason"] == "off_ledger_lane"
    assert not fo_changes.state_log_path(tmp_path).exists()


# ── 14: additive keys don't break the known consumer (cn_theme_tape) ──────────────
def test_added_top_level_keys_do_not_break_known_consumers():
    v2 = _v2()
    membership = {"baskets": {"cn_autos": {
        "name": "Autos & NEV Makers", "name_zh": "汽车整车", "etf_proxy": None,
        "members": [{"ticker": "600104.SS", "name_zh": "上汽集团"}],
    }}}
    import pandas as pd
    cycles = pd.DataFrame([{"date": "2026-09-01", "id": "b-cn_autos", "kind": "basket",
                           "phase": "Recovery", "osc_slope": 4.0, "pos": 10.0}])
    candidates = pd.DataFrame([{"stamp_date": "2026-09-01", "ticker": "600104.SS",
                               "lane": "featured", "entry_status": "partial",
                               "gate_reason": None}])
    import datetime as _dt
    tape = build_cn_theme_tape(membership=membership, cycles=cycles, candidates=candidates,
                               flow=v2, today=_dt.date(2026, 9, 1))
    assert tape is not None
    row = next(r for r in tape["rows"] if r["key"] == "cn_autos")
    assert row["flow_en"] == "above norm, cooling"
    assert row["flow_zh"] == "高于常态·降温"


# ── 15: validate() catches a quadrant/axis mismatch ────────────────────────────────
def test_validate_rejects_quadrant_axis_mismatch():
    v2 = _v2()
    v2["ashare_sectors"]["rows"][0]["quadrant"] = "true_distribution"   # was improving_but_still_selling
    with pytest.raises(ContractError):
        validate(v2)


def test_validate_passes_a_consistent_payload():
    validate(_v2())   # must not raise


def test_validate_rejects_a_missing_denominator():
    v2 = _v2()
    del v2["market_read"]["themes"]["absolute_breadth"]["denominator"]
    with pytest.raises(ContractError):
        validate(v2)


# ══════════════════════════════════════════════════════════════════════════════════════
# W1 repair round — independent-review findings (research/flow_observatory/W1_SPEC.md
# repair commission). B1/B2/B3 = FAIL findings; S4-S9/NIT12 = should-fix findings.
# ══════════════════════════════════════════════════════════════════════════════════════

# ── B1: the t() macro must never be called inside an HTML attribute value ─────────────
def test_no_attribute_breakout_leak_from_the_t_macro():
    """The committed site previously shipped `aria-label="<span class="l-en">Data
    sources</span>..."` — the t() macro's span markup broke out of the attribute value
    and leaked the literal text `Data sources">` onto the page. Every attribute value in
    the rendered page must be free of the t() macro's own markup."""
    html = _render(_v2())
    assert 'Data sources">' not in html, "the aria-label attribute-breakout leak reproduced"
    # a fully general guard: no attribute value anywhere may contain the t() macro's own
    # inner markup — that would mean a t() call landed inside an attribute again.
    assert re.search(r'="[^"]*<span class="l-en"', html) is None, (
        "a t() call landed inside an HTML attribute value (breaks out of the quote)")


# ── B2: member drill-down rows must align column-for-column with the sectortbl header ──
_TD_RE = re.compile(r"<td([^>]*)>(.*?)</td>", re.S)
_TH_RE = re.compile(r"<th([^>]*)>(.*?)</th>", re.S)
_TR_RE = re.compile(r'<tr\b[^>]*>.*?</tr>', re.S)
_COLSPAN_RE = re.compile(r'colspan="(\d+)"')


def _sectortbl_html(html: str) -> str:
    m = re.search(r'<table class="board" id="sectortbl">.*?</table>', html, re.S)
    assert m, "sectortbl not found in rendered page"
    return m.group(0)


def _row_colspan_total(row_html: str, cell_re) -> int:
    total = 0
    for attrs, _inner in cell_re.findall(row_html):
        cs = _COLSPAN_RE.search(attrs)
        total += int(cs.group(1)) if cs else 1
    return total


def test_sectortbl_row_td_counts_match_the_header_th_count():
    """Every body row's <td> colspans must sum to the same total as the header's <th>
    colspans — the structural check for B2's defect (memberrow shipped 5 <td> against an
    8-column header, so a member's numbers silently shifted under the wrong headers)."""
    member = _member()
    v2 = _v2()
    v2["ashare_sectors"]["rows"][0] = dict(v2["ashare_sectors"]["rows"][0], members=[member])
    table_html = _sectortbl_html(_render(v2))
    rows = _TR_RE.findall(table_html)
    assert rows, "no <tr> parsed from sectortbl"
    header_total = _row_colspan_total(rows[0], _TH_RE)
    assert header_total == 8, f"header itself unexpectedly has {header_total} columns"
    body_rows = rows[1:]
    assert body_rows, "no body rows parsed"
    mismatches = [(i, _row_colspan_total(r, _TD_RE)) for i, r in enumerate(body_rows)
                 if _row_colspan_total(r, _TD_RE) != header_total]
    assert not mismatches, (
        f"{len(mismatches)} row(s) have a <td> colspan total != the header's {header_total}: "
        f"{mismatches}")


def test_member_row_shows_raw_abs_under_abs_header_never_the_relative_figure():
    """The Autos defect, relocated: a member's RELATIVE rate_rel used to land under the
    'abs 4wk' header. abs 4wk must show the member's own RAW rate_4wk; 'vs norm' must show
    rate_rel; the two must never collide (they differ in this fixture on purpose)."""
    member = _member(rate_4wk=-0.9, rate_rel=1.9)
    v2 = _v2()
    v2["ashare_sectors"]["rows"][0] = dict(v2["ashare_sectors"]["rows"][0], members=[member])
    table_html = _sectortbl_html(_render(v2))
    row_html = next(r for r in _TR_RE.findall(table_html) if member["ticker"] in r)
    cells = [(int(m.group(1)) if (m := _COLSPAN_RE.search(attrs)) else 1, inner)
            for attrs, inner in _TD_RE.findall(row_html)]
    assert sum(c for c, _ in cells) == 8
    assert len(cells) == 6, f"expected 6 <td> elements (name, seat, abs, rel, vel, dash-3), got {len(cells)}"
    name_cell, seat_cell, abs_cell, rel_cell, vel_cell, tail_cell = cells
    assert name_cell[0] == 1 and seat_cell[0] == 1
    assert "SAIC Motor" in name_cell[1]
    assert "🏛" in seat_cell[1], "seat badge must render in its own cell"
    assert abs_cell[0] == 1 and rel_cell[0] == 1 and vel_cell[0] == 1
    # scope to the VISIBLE figure in each cell — the rel cell's own LENS tooltip legitimately
    # quotes the raw rate_4wk as its receipt ("...ran -0.9% of turnover...") without that
    # being the abs/rel conflation this test guards against (spec §2.4: tooltip receipts are
    # allowed to name both numbers; only the AT-REST figure must not collide).
    abs_visible, rel_visible = _visible_only(abs_cell[1]), _visible_only(rel_cell[1])
    assert "-0.9%" in abs_visible, "abs 4wk cell must show the member's raw rate_4wk at rest"
    assert "+1.9%" not in abs_visible, "the relative figure must never appear in the abs cell at rest"
    assert "+1.9%" in rel_visible, "vs norm cell must show rate_rel at rest"
    assert "-0.9%" not in rel_visible, "the raw abs figure must never appear in the vs-norm cell at rest"
    assert "above norm, cooling" in vel_cell[1], "velocity cell must carry the state word"
    assert tail_cell[0] == 3, "the Quadrant/rank-Δ/trend columns collapse to one colspan-3 dash"


def test_member_row_abs_cell_is_an_em_dash_when_the_member_has_no_scored_rate():
    """A member too short-lived to score gets an em-dash in the abs cell, never a bare
    relative figure and never a fabricated zero. Mirrors the real _rate_read() shape: when
    a series is too short/empty ALL four rate fields come back None together (never just
    rate_4wk alone), so that is the realistic fixture."""
    member = _member(rate_4wk=None, rate_norm=None, rate_rel=None, rate_now=None)
    v2 = _v2()
    v2["ashare_sectors"]["rows"][0] = dict(v2["ashare_sectors"]["rows"][0], members=[member])
    table_html = _sectortbl_html(_render(v2))
    row_html = next(r for r in _TR_RE.findall(table_html) if member["ticker"] in r)
    cells = [(int(m.group(1)) if (m := _COLSPAN_RE.search(attrs)) else 1, inner)
            for attrs, inner in _TD_RE.findall(row_html)]
    abs_cell = cells[2][1]   # name(0), seat(1), abs 4wk(2)
    assert "—" in abs_cell, "a missing member rate must render an em-dash"


# ── B3: market_read.themes must count the REAL unscored themes, not a hardcoded 0 ─────
def test_market_read_themes_denominator_includes_real_unscored_themes():
    """contract.build_v2 used to hardcode unscored=0 for the theme lens while
    flow_velocity.ashare_sector_velocity already computed the real drop count in
    ashare_sectors.n_unscored (themes with <3 members or an unscoreable kinetics read) —
    silently dropping them from the denominator, the exact missing-!=-zero gap the
    contract law exists to close."""
    snap = _snap()
    snap["ashare_sectors"] = {**snap["ashare_sectors"], "n_unscored": 4}
    v2 = build_v2(snap, log_rows=[], market_session="2026-09-01",
                 generated_at="2026-09-01T12:00:00+00:00", seats_as_of="2026-08-30")
    themes_mr = v2["market_read"]["themes"]
    n_scored = len(v2["ashare_sectors"]["rows"])
    assert themes_mr["absolute_breadth"]["missing"] >= 4
    assert themes_mr["absolute_breadth"]["denominator"] == n_scored + 4
    assert themes_mr["relative_breadth"]["denominator"] == n_scored + 4
    assert themes_mr["relative_breadth"]["missing"] >= 4


# ── S4(a): hero thesis pinned all-net-seller sentence when absolute-positive is zero ───
def test_hero_thesis_uses_the_pinned_all_net_seller_sentence_when_absolute_positive_is_zero():
    snap = _snap()
    rows = [_autos_row(rate_4wk=-0.9, vel=1.9, rate_rel=1.9),
           _gold_row(rate_4wk=-1.2, vel=1.7, rate_rel=1.7)]   # both abs negative -> abspos=0
    snap["ashare_sectors"] = {**snap["ashare_sectors"], "rows": rows}
    v2 = build_v2(snap, log_rows=[], market_session="2026-09-01",
                 generated_at="2026-09-01T12:00:00+00:00", seats_as_of="2026-08-30")
    mrt = v2["market_read"]["themes"]
    assert mrt["absolute_breadth"]["positive"] == 0
    n = mrt["relative_breadth"]["denominator"]
    html = _render(v2)
    assert (f"Main-force flow was a net seller in all {n} themes — normal for this "
            "order-size proxy; the signal is pressure vs norm.") in html
    assert f"主力资金在全部{n}个主题均为净卖出——该口径的常态；关键信号是相对常态的压力。" in html
    # the >0 sentence must NOT also be present
    assert "saw positive absolute 4-week flow" not in html.split('id="sources"')[0]


def test_hero_thesis_keeps_the_original_sentence_when_absolute_positive_is_nonzero():
    v2 = _v2()   # default fixture: Autos abs<0, Gold abs>0 -> abspos == 1
    mrt = v2["market_read"]["themes"]
    assert mrt["absolute_breadth"]["positive"] > 0
    html = _render(v2)
    assert "saw positive absolute 4-week flow" in html
    assert "Main-force flow was a net seller in all" not in html


# ── S4(b): designed quiet empty states in the quadrant board + LENS tip on its h2 ─────
def test_quadrant_empty_cells_use_designed_quiet_copy_not_bare_none():
    snap = _snap()
    rows = [_autos_row(rate_4wk=-0.9, vel=1.9, rate_rel=1.9),      # -> improving_but_still_selling
           _gold_row(rate_4wk=-1.2, vel=-1.7, rate_rel=-1.7)]      # -> true_distribution
    snap["ashare_sectors"] = {**snap["ashare_sectors"], "rows": rows}
    v2 = build_v2(snap, log_rows=[], market_session="2026-09-01",
                 generated_at="2026-09-01T12:00:00+00:00", seats_as_of="2026-08-30")
    html = _render(v2)
    # true_accumulation and weakening_but_still_buying are both empty in this fixture
    assert "none today — rare for this proxy; exceptional when a theme appears here" in html
    assert "今日无——该口径下罕见，出现即为异常信号" in html
    assert "none today" in html
    assert "今日无" in html
    assert "structurally a net seller" in html, "quadrant h2 must carry a LENS tip explaining emptiness"


# ── S5: the relative-breadth line must reach its own stated denominator on screen ─────
def test_relative_breadth_line_shows_its_missing_term_and_reaches_the_denominator():
    snap = _snap()
    snap["ashare_sectors"] = {**snap["ashare_sectors"], "n_unscored": 3}
    v2 = build_v2(snap, log_rows=[], market_session="2026-09-01",
                 generated_at="2026-09-01T12:00:00+00:00", seats_as_of="2026-08-30")
    rb = v2["market_read"]["themes"]["relative_breadth"]
    assert rb["missing"] >= 3
    assert rb["positive"] + rb["neutral"] + rb["negative"] + rb["missing"] == rb["denominator"]
    html = _render(v2)
    assert f"— {rb['missing']} unscored" in html
    assert f"— {rb['missing']}个未评分" in html


# ── S6: validate() must reject a build instant substituted for a leg's effective_date ──
def test_validate_rejects_a_build_instant_substituted_for_a_leg_date():
    """The OLD check compared generated_at (always a full ISO instant, e.g.
    "2026-09-01T12:00:00+00:00") byte-for-byte against effective_date (always a plain
    10-char YYYY-MM-DD panel date) — two values that can never be equal by construction,
    so the check was dead code no mutation could ever reach. This mutation (a leg's
    effective_date literally replaced by the build instant) must be caught."""
    v2 = _v2()
    v2["sources"][0]["effective_date"] = v2["generated_at"]
    with pytest.raises(ContractError):
        validate(v2)


def test_validate_still_passes_a_legitimate_same_day_t0_leg():
    """Guard against over-correcting S6: a T+0 leg whose panel date legitimately equals
    today's calendar date (a real, common case — asia-close runs shortly after CN close)
    must NOT be rejected. Only a build-INSTANT shape (has a time component) is rejected."""
    v2 = _v2()
    v2["generated_at"] = "2026-09-01T07:30:00+00:00"    # same UTC calendar day as the legs
    validate(v2)   # must not raise


# ── S7: sources[] always emits all five W1 legs, even with a panel outage ─────────────
def test_sources_always_emit_all_five_legs_even_when_a_panel_is_absent():
    v2 = _v2()
    v2["aggregate"] = [c for c in v2["aggregate"] if c.get("key") != "southbound"]   # sb=None
    sources = build_sources(v2, newest_session="2026-09-01", seats_as_of="2026-08-30")
    assert len(sources) == 5
    by_id = {s["source_id"]: s for s in sources}
    assert set(by_id) == {"cn_large_order_proxy", "sb_aggregate", "hk_sb_holdings",
                          "nb_aggregate", "lhb_inst_seats"}
    sb = by_id["sb_aggregate"]
    assert sb["effective_date"] is None
    assert sb["ui_state"] == "unavailable"
    assert sb["state_word_en"] == "unavailable" and sb["state_word_zh"] == "不可用"
    assert sb["coverage"]["n_observed"] is None
    # the page still renders cleanly with a panel outage, chip date shows an em-dash
    v2["sources"] = sources
    html = _render(v2)
    assert "unavailable" in html or "不可用" in html


def test_hero_vital_shows_a_true_denominator_of_current_legs_out_of_five():
    v2 = _v2()
    present = sum(1 for s in v2["sources"] if s["ui_state"] == "current")
    html = _render(v2)
    assert re.search(rf'<span class="tnum">{present}</span> of 5 legs current', html)
    assert re.search(rf'5条数据源·<span class="tnum">{present}</span>条最新', html)


# ── S9: bare "institutions"/bare "机构" must never appear in at-rest copy ─────────────
def test_at_rest_copy_never_uses_bare_institutions_or_bare_jigou():
    """S9: 'N inst'/'N机构' at rest is qualified to 'N inst seats'/'N机构席位' — extend the
    BANNED at-rest list with a bare word-boundary check. data-tip attribute contents stay
    exempt (LENS receipts are allowed more latitude than glance-tier copy). Scoped to the
    flow_velocity page's OWN content — the shared `_site_nav` include is a separate,
    out-of-scope governed component (nav bar copy is not this program's vocabulary law)."""
    v2 = _v2()
    v2["ashare_sectors"]["rows"][0] = dict(v2["ashare_sectors"]["rows"][0], inst_attention=3)
    html = _render(v2)
    page_html = html.split('<div class="wrap">', 1)[1]
    visible = _visible_only(page_html)
    assert not re.search(r"\binstitutions\b", visible, re.I), (
        "bare word-boundary 'institutions' leaked into at-rest copy")
    bad = [m.group(0) for m in re.finditer(r"机构(?!席位|专用)", visible)]
    assert not bad, f"bare '机构' (not qualified by 席位/专用) at rest: {bad}"
    assert "3 inst seats" in visible or "机构席位" in visible


# ── NIT12: board abs column colors by direction (neutral -> muted), not raw sign ──────
def test_theme_abs_column_colors_by_direction_not_raw_sign():
    """A value like -0.04% sits inside the 0.1pp de-minimis neutral band (direction=
    'neutral') but rounds for display to '-0.0%' — the raw-sign coloring used to print
    that in outflow-red ink, contradicting the quadrant's own neutral read of the same
    figure. Must be muted ('neu'), not 'neg'."""
    snap = _snap()
    rows = [_autos_row(rate_4wk=-0.04, vel=0.2, rate_rel=0.1),   # abs+rel both neutral
           _gold_row()]
    snap["ashare_sectors"] = {**snap["ashare_sectors"], "rows": rows}
    v2 = build_v2(snap, log_rows=[], market_session="2026-09-01",
                 generated_at="2026-09-01T12:00:00+00:00", seats_as_of="2026-08-30")
    autos = next(r for r in v2["ashare_sectors"]["rows"] if r["id"] == "cn_autos")
    assert autos["abs"]["direction"] == "neutral"
    table_html = _sectortbl_html(_render(v2))
    row_html = next(r for r in _TR_RE.findall(table_html) if "cn_autos" in r or "Autos" in r)
    assert 'class="chg neu"' in row_html, "a neutral-direction abs value must use the muted 'neu' class"
    assert 'class="chg neg"' not in row_html, "a neutral-direction abs value must never render as 'neg'"
