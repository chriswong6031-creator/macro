"""Flow Observatory V2 W4 — official/curated lenses, coverage floor, overlap disclosure,
concentration and contribution (research/flow_observatory/W4_SPEC.md).

Written FIRST and failing per the frozen spec's §0 gate, against
``engine.flow_observatory.groups`` (new) and the W4 extensions to
``engine.flow_velocity.ashare_sector_velocity`` / ``templates/flow_velocity.html.j2`` /
``scripts/build_flow_velocity.py``. The eleven numbered tests below correspond 1:1 to
spec §6's numbered list; each test's docstring names its bullet.

Mutation M1 (spec §6 item 11 — "relabel curated themes as official (set group_kind
official on theme rows) -> duplicate-ticker or overlap tests fail") is a manual
verification, not a permanent test (same precedent as W3's M1,
tests/test_flow_observatory_history.py): paste the failing output of
test_duplicate_active_membership_is_excluded_never_double_counted (test 1) into the PR
body/EVIDENCE after temporarily disabling ``resolve_active_membership``'s dedup guard,
then revert.
"""
from __future__ import annotations

import re

import pandas as pd
import pytest
from jinja2 import Environment, FileSystemLoader

from engine import i18n
from engine.flow_observatory import groups as fo_groups
from engine.flow_observatory.contract import (
    QUADRANT_LABELS,
    STATUS_WORD,
    assign_ranks,
    enrich_group,
)
from scripts.build_vector import C
from tests.test_flow_observatory_contract import ROOT, TMPL, _autos_row, _snap, _v2  # noqa: F401

TMPL_DIR = TMPL


def _render(v2, built="test"):
    env = Environment(loader=FileSystemLoader(str(TMPL_DIR)), autoescape=True)
    env.globals.update(td=i18n.td, tr=i18n.tr, quadrant_labels=QUADRANT_LABELS,
                       status_word=STATUS_WORD)
    return env.get_template("flow_velocity.html.j2").render(C=C, snap=v2, built=built)


def _visible_only(html: str) -> str:
    return re.sub(r'data-tip-(?:en|zh)="[^"]*"', "", html)


# ── membership fixtures (interval-store shape: ticker/l1_code/l1_name/start_date/
#    end_date/collected_at) ─────────────────────────────────────────────────────────
def _membership_df(rows):
    cols = ["ticker", "l1_code", "l1_name", "start_date", "end_date", "collected_at"]
    return pd.DataFrame(rows, columns=cols)


def _mrow(ticker, l1_code, l1_name="Banks", start="2021-01-01", end=None, collected="2026-09-01"):
    return {"ticker": ticker, "l1_code": l1_code, "l1_name": l1_name,
           "start_date": start, "end_date": end, "collected_at": collected}


def _kmap_member(ticker, name, vel, rate_rel):
    return {"ticker": ticker, "name": name, "vel": vel, "accel": 0.0,
           "rate_now": rate_rel, "rate_4wk": rate_rel, "rate_norm": 0.0, "rate_rel": rate_rel,
           "state": "above norm, rising" if vel and vel >= 0 else "below norm, worsening",
           "state_zh": "高于常态·升温"}


def _wide_from_kmap(kmap, n=140):
    """A minimal [date x ticker] flow panel wide enough for every ticker in ``kmap`` to
    be a real column with genuine variance (a constant-zero column has zero vol, so
    ``_kinetics`` can never resolve a velocity for it — most of these fixtures only need
    column PRESENCE for coverage/membership math, but the ones that also check
    ``coverage_state == 'ok'`` need real, scoreable data)."""
    import numpy as np

    idx = pd.date_range("2025-01-01", periods=n, freq="D")
    rng = np.random.default_rng(11)
    data = {t: rng.normal(0, 1, n) for t in kmap}
    return pd.DataFrame(data, index=idx)


# ── 1: official lens — no duplicate ticker per effective date ─────────────────────────
def test_duplicate_active_membership_is_excluded_never_double_counted():
    """A ticker active in TWO l1_codes at once is a source contradiction (spec §2A last
    bullet) — excluded from BOTH, counted, never silently assigned to either."""
    mem = _membership_df([
        _mrow("600000.SS", "801780", "Banks"),
        _mrow("600000.SS", "801790", "Non-bank Financials"),   # same ticker, 2nd open l1_code
        _mrow("600036.SS", "801780", "Banks"),
    ])
    by_code, excluded = fo_groups.resolve_active_membership(mem)
    assert "600000.SS" not in by_code.get("801780", [])
    assert "600000.SS" not in by_code.get("801790", [])
    assert "600036.SS" in by_code.get("801780", [])
    assert excluded == [{"ticker": "600000.SS", "reason": "duplicate_membership"}]


def test_no_duplicates_leaves_all_groups_intact():
    mem = _membership_df([_mrow("600000.SS", "801780"), _mrow("600036.SS", "801780"),
                          _mrow("601318.SS", "801790", "Non-bank Financials")])
    by_code, excluded = fo_groups.resolve_active_membership(mem)
    assert excluded == []
    assert sorted(by_code["801780"]) == ["600000.SS", "600036.SS"]
    assert by_code["801790"] == ["601318.SS"]


# ── 2: themes may overlap; overlap_count correct on a constructed fixture ─────────────
def test_overlap_count_correct_on_constructed_fixture():
    """cn_a and cn_b share AAA/BBB; cn_c is disjoint. overlap_count = members shared
    with >=1 OTHER theme (spec §3)."""
    membership = {
        "cn_a": ["AAA", "BBB", "CCC"],
        "cn_b": ["AAA", "BBB", "DDD"],
        "cn_c": ["EEE", "FFF"],
    }
    overlap_by_ticker = fo_groups.compute_overlap_counts(membership)
    assert overlap_by_ticker["AAA"] == 1   # in cn_a AND cn_b -> 1 OTHER group
    assert overlap_by_ticker["BBB"] == 1
    assert overlap_by_ticker.get("CCC", 0) == 0
    assert overlap_by_ticker.get("EEE", 0) == 0
    assert fo_groups.theme_overlap_count(membership["cn_a"], overlap_by_ticker) == 2   # AAA, BBB
    assert fo_groups.theme_overlap_count(membership["cn_c"], overlap_by_ticker) == 0


# ── 3: official lens refuses historical claims before seed_date ───────────────────────
def test_official_lens_refuses_a_window_before_seed_date():
    kmap = {"600000.SS": _kmap_member("600000.SS", "SPDB", 1.0, 1.0),
           "600036.SS": _kmap_member("600036.SS", "CMB", 1.2, 1.1),
           "601318.SS": _kmap_member("601318.SS", "Ping An", 0.9, 0.8)}
    wide = _wide_from_kmap(kmap)
    mem = _membership_df([_mrow("600000.SS", "801780", collected="2026-09-01"),
                          _mrow("600036.SS", "801780", collected="2026-09-01"),
                          _mrow("601318.SS", "801790", "Non-bank Financials", collected="2026-09-01")])
    res = fo_groups.aggregate_lens(wide, kmap, mem, as_of="2020-01-01")
    assert res["available"] is False
    assert res["reason"] == "before_seed_date"
    assert res["seed_date"] == "2026-09-01"


def test_official_lens_available_for_a_window_on_or_after_seed_date():
    kmap = {"600000.SS": _kmap_member("600000.SS", "SPDB", 1.0, 1.0)}
    wide = _wide_from_kmap(kmap)
    mem = _membership_df([_mrow("600000.SS", "801780", collected="2026-09-01")])
    res = fo_groups.aggregate_lens(wide, kmap, mem, as_of="2026-09-01")
    assert res["available"] is True
    res_none = fo_groups.aggregate_lens(wide, kmap, mem)   # as_of=None -> current, always available
    assert res_none["available"] is True


def test_official_lens_row_carries_a_real_zh_name_not_the_english_name_twice():
    """Regression (caught live during evidence screenshots): the official-sector row
    used to ship ``name_zh`` == ``name`` (both English) because the caller only passed
    a bare code->EN-name map — the ZH UI silently showed English sector names.
    ``l1_names`` is ``code -> (name_en, name_zh)``; the row must carry each in its own
    field, and the two must differ for a real Shenwan L1 name."""
    kmap = {"600000.SS": _kmap_member("600000.SS", "SPDB", 1.0, 1.0)}
    wide = _wide_from_kmap(kmap)
    mem = _membership_df([_mrow("600000.SS", "801780", collected="2026-09-01")])
    res = fo_groups.aggregate_lens(wide, kmap, mem, l1_names={"801780": ("Banks", "银行")})
    row = res["rows"][0]
    assert row["name"] == "Banks"
    assert row["name_zh"] == "银行"
    assert row["name"] != row["name_zh"]


# ── 4: coverage floor -> insufficient_coverage state, no rank, neutral quadrant ───────
def test_coverage_below_floor_renders_insufficient_never_partial():
    """A group with real membership but almost nothing scored must NEVER drop silently
    (spec §0.2 "never a survivor-biased read") and must NEVER show a partial statistic
    (spec §3): vel/rate fields null, quadrant forced neutral_or_unknown, rank null."""
    kmap = {"600000.SS": _kmap_member("600000.SS", "SPDB", 1.0, 1.0)}
    wide = _wide_from_kmap(kmap)
    # 10 members total, only 1 scored -> 10% coverage, well below the 60% floor
    rows = [_mrow("600000.SS", "801780")] + [_mrow(f"60000{i}.SS", "801780") for i in range(2, 11)]
    mem = _membership_df(rows)
    res = fo_groups.aggregate_lens(wide, kmap, mem)
    assert res["available"] is True
    row = res["rows"][0]
    assert row["n_members"] == 10
    assert row["n_covered"] == 1
    assert row["coverage_pct"] == 10.0
    assert row["coverage_state"] == "insufficient_coverage"
    assert row["vel"] is None and row["rate_4wk"] is None and row["concentration"] is None
    # run the SAME abs/rel/quadrant/rank enrichment build_flow_velocity.py applies
    row.update(enrich_group(row.get("rate_4wk"), row.get("vel")))
    assign_ranks(res["rows"])
    assert row["quadrant"] == "neutral_or_unknown"
    assert row["rank"] is None


def test_coverage_at_or_above_floor_computes_normally():
    kmap = {t: _kmap_member(t, t, 1.0, 1.0) for t in
           ["600000.SS", "600036.SS", "601318.SS", "600016.SS"]}
    wide = _wide_from_kmap(kmap)
    mem = _membership_df([_mrow(t, "801780") for t in kmap])   # 4/4 = 100% coverage
    res = fo_groups.aggregate_lens(wide, kmap, mem)
    row = res["rows"][0]
    assert row["coverage_pct"] == 100.0
    assert row["coverage_state"] == "ok"
    assert row["vel"] is not None


# ── 5: contributors reconcile to the aggregate within 1e-6 ─────────────────────────────
def test_contributors_reconcile_to_group_rel_within_tolerance():
    kmap = {"AAA": _kmap_member("AAA", "Alpha", 1.5, 3.0),
           "BBB": _kmap_member("BBB", "Beta", -0.5, -1.0),
           "CCC": _kmap_member("CCC", "Gamma", 0.8, 1.6)}
    contrib = fo_groups.member_contributions(list(kmap), kmap)
    conc = fo_groups.concentration_from_contributions(contrib)
    assert abs(sum(c["contribution"] for c in contrib) - conc["group_rel"]) < 1e-6
    # group_rel is exactly the mean of the member rate_rel values by construction
    assert abs(conc["group_rel"] - (3.0 - 1.0 + 1.6) / 3) < 1e-6


def test_reconciliation_holds_on_a_larger_random_style_fixture():
    vals = [2.3, -1.1, 0.4, -3.7, 5.0, -0.2, 1.9, -2.6, 0.05, 4.4]
    kmap = {f"T{i}": _kmap_member(f"T{i}", f"Name{i}", v, v) for i, v in enumerate(vals)}
    contrib = fo_groups.member_contributions(list(kmap), kmap)
    conc = fo_groups.concentration_from_contributions(contrib)
    assert abs(sum(c["contribution"] for c in contrib) - conc["group_rel"]) < 1e-6
    assert abs(conc["group_rel"] - sum(vals) / len(vals)) < 1e-6


# ── 6: without_top1 flip detection on a constructed concentrated fixture ──────────────
def test_without_top1_flips_direction_on_a_dominant_member():
    """One member (+9.0) swamps three small negatives (-0.3 each): group is net
    positive, but removing the dominant member flips it negative."""
    kmap = {"DOM": _kmap_member("DOM", "Dominant", 3.0, 9.0),
           "A": _kmap_member("A", "A", -0.3, -0.3),
           "B": _kmap_member("B", "B", -0.3, -0.3),
           "C": _kmap_member("C", "C", -0.3, -0.3)}
    contrib = fo_groups.member_contributions(list(kmap), kmap)
    conc = fo_groups.concentration_from_contributions(contrib)
    assert conc["group_rel"] > 0            # net positive WITH the dominant member
    assert conc["without_top1_direction"] == "flip"
    assert conc["top1_share"] is not None and conc["top1_share"] > fo_groups.CONCENTRATION_CHIP_PCT


def test_without_top1_keeps_direction_on_a_diversified_fixture():
    kmap = {f"T{i}": _kmap_member(f"T{i}", f"N{i}", 1.0, 1.0) for i in range(8)}
    contrib = fo_groups.member_contributions(list(kmap), kmap)
    conc = fo_groups.concentration_from_contributions(contrib)
    assert conc["without_top1_direction"] == "same"
    assert conc["top1_share"] < fo_groups.CONCENTRATION_CHIP_PCT


# ── 7: excluded/missing members visible with reasons ───────────────────────────────────
def test_excluded_members_carry_unscored_or_missing_reason():
    kmap = {"AAA": _kmap_member("AAA", "Alpha", 1.0, 1.0)}
    wide_columns = ["AAA", "BBB"]   # BBB has flow data but never scored (too short)
    members = ["AAA", "BBB", "CCC"]   # CCC has no flow data at all
    ex = fo_groups.excluded_members(members, wide_columns, kmap, {"BBB": "Beta", "CCC": "Gamma"})
    by_ticker = {e["ticker"]: e for e in ex}
    assert by_ticker["BBB"]["reason"] == "unscored"
    assert by_ticker["CCC"]["reason"] == "missing"
    assert "AAA" not in by_ticker


def test_excluded_members_render_in_the_drilldown():
    v2 = _v2()
    v2["ashare_sectors"]["rows"][0] = dict(
        v2["ashare_sectors"]["rows"][0],
        excluded=[{"ticker": "999999.SZ", "name": "GhostCo", "reason": "missing"}])
    html = _render(v2)
    assert "GhostCo" in html


# ── 8: lens tabset renders both lenses; JS-off stacked rendering ──────────────────────
def test_lens_tabset_renders_both_lenses_and_stacks_without_js():
    v2 = _v2()
    v2["official_sectors"] = {
        "available": True, "seed_date": "2026-09-01", "n": 1,
        "rows": [dict(**enrich_group(None, None), id="801780", name="Banks", name_zh="银行",
                     group_kind="official_sector", overlap_allowed=False,
                     membership_as_of="current", n_members=10, n_covered=9, coverage_pct=90.0,
                     coverage_state="ok", excluded=[], vel=1.1, accel=0.02, rate_now=1.0,
                     rate_4wk=1.0, rate_norm=0.0, rate_rel=1.0, state="above norm, rising",
                     state_zh="高于常态·升温", spark=None, concentration=None, members=[],
                     rank=1, rank_change=None)],
    }
    html = _render(v2)
    assert 'id="lens-curated"' in html and 'id="lens-official"' in html
    assert 'data-lens="curated"' in html and 'data-lens="official"' in html
    assert "Official sectors" in html and "官方行业" in html
    assert "Banks" in html and "银行" in html
    # JS-off stacking is a CSS/JS contract (`html:not(.js) .fv-lens-tabs{display:none}` /
    # `html.js #lens-official{display:none}`), never a baked-in inline style on the
    # panel itself — an inline display:none on #lens-official would defeat the no-JS
    # stacked render unconditionally.
    m = re.search(r'<div id="lens-official"[^>]*>', html)
    assert m and "display:none" not in m.group(0) and "display: none" not in m.group(0)


def test_lens_switch_js_sets_a_real_display_value_not_an_empty_override():
    """Regression (caught live during evidence screenshots): ``style.display=''`` on
    the panel becoming active does NOT make it visible when a CSS rule
    (``html.js #lens-official{display:none}``) already targets it — clearing an
    inline override just falls back to that CSS default, so the official tab stayed
    hidden even after being selected. The active panel must get a REAL value
    ('block'), not an empty string."""
    html = _render(_v2())
    m = re.search(r"Object\.keys\(panels\)\.forEach\(function\(k\)\{[^}]*\}\);", html)
    assert m, "lens-switch JS not found in rendered page"
    assert "k===name?'block':'none'" in m.group(0) or 'k===name?"block":"none"' in m.group(0)


# ── 9: long ZH labels + dense contribution rows — no overflow ─────────────────────────
def test_long_zh_labels_and_dense_contributors_stay_inside_the_scroll_wrapper():
    v2 = _v2()
    long_zh = "非常长的官方行业中文名称测试超出容器宽度换行滚动条溢出边界情形" * 2
    contrib_names = [f"member-{i}-{'x' * 20}" for i in range(12)]
    conc = {
        "top1_share": 55.0, "top3_share": 88.0, "without_top1_direction": "flip",
        "top3_pos": [{"ticker": f"T{i}", "name": n} for i, n in enumerate(contrib_names[:3])],
        "top3_neg": [{"ticker": f"T{i}", "name": n} for i, n in enumerate(contrib_names[3:6])],
        "gross": 10.0, "group_rel": 1.0, "top1": {"ticker": "T0", "name": contrib_names[0]},
    }
    v2["ashare_sectors"]["rows"][0] = dict(
        v2["ashare_sectors"]["rows"][0], name=long_zh, name_zh=long_zh, concentration=conc)
    html = _render(v2)
    # structural containment: the board table sits inside the existing horizontally-
    # scrollable wrapper (spec §0.5 "no horizontal scroll" — content overflows its OWN
    # container, never the page), and the new concentration row's <td> keeps the SAME
    # colspan total as the header (no column drift from the long label / dense list).
    assert '<div class="tbl-wrap">' in html
    m = re.search(r'<table class="board" id="sectortbl">.*?</table>', html, re.S)
    assert m and 'class="tbl-wrap"' in html[:m.start()][-400:]
    assert long_zh in html
    conc_row = re.search(r'<tr class="mrow fv-conc-row[^"]*"[^>]*>.*?</tr>', html, re.S)
    assert conc_row, "concentration drilldown row not rendered"
    cs = re.search(r'colspan="(\d+)"', conc_row.group(0))
    assert cs and int(cs.group(1)) == 8


# ── 10: spike-failure (2B) path — unavailable state, pinned strings, no leakage ───────
def test_official_lens_unavailable_state_renders_pinned_strings_no_curated_leak():
    """This wave's spike SUCCEEDED (2A ships), but the 2B "unavailable" branch is real,
    reachable code (a fresh checkout before the membership collector's first run, or a
    ``before_seed_date`` refusal) — spec §2B's designed-unavailable copy must render
    verbatim, and none of the curated theme names/ids may leak into that panel."""
    v2 = _v2()
    v2["official_sectors"] = None
    html = _render(v2)
    m = re.search(r'<div id="lens-official"[^>]*>.*?(?=<div id="lens-official"|\Z)',
                 html[html.find('id="lens-official"'):], re.S)
    panel = m.group(0) if m else html[html.find('id="lens-official"'):html.find('id="lens-official"') + 2000]
    assert "no lawful keyless constituent source" in panel
    assert "缺少合规的成分数据源" in panel
    assert "showing curated themes only" in panel or "仅显示精选主题" in panel
    for theme_id in ("cn_autos", "cn_gold"):
        assert theme_id not in panel


def test_official_lens_refused_window_renders_its_own_pinned_reason():
    v2 = _v2()
    v2["official_sectors"] = {"available": False, "reason": "before_seed_date",
                              "seed_date": "2026-09-01", "requested": "2020-01-01"}
    html = _render(v2)
    assert "Official sector lens unavailable" in html
    assert "官方行业视图暂不可用" in html
    assert "2026-09-01" in html


# ── theme lens: same coverage/overlap/concentration machinery via ashare_sector_velocity
def test_ashare_sector_velocity_never_drops_a_basket_for_low_coverage():
    """Integration proof that the theme rollup (engine.flow_velocity.ashare_sector_velocity)
    reuses THIS module rather than re-implementing coverage — a basket with too few
    covered members renders insufficient_coverage instead of vanishing (spec §0.2)."""
    import numpy as np

    from engine.flow_velocity import ashare_sector_velocity

    class _FakeBaskets:
        @staticmethod
        def _membership():
            return {"baskets": {
                "thin": {"name": "Thin", "name_zh": "薄", "category": "x",
                         "members": [{"ticker": f"T{i}.SZ", "removed": None} for i in range(10)]},
                "b2": {"name": "B2", "name_zh": "乙", "category": "x",
                       "members": [{"ticker": f"U{i}.SZ", "removed": None} for i in range(10)]},
                "b3": {"name": "B3", "name_zh": "丙", "category": "x",
                       "members": [{"ticker": f"V{i}.SZ", "removed": None} for i in range(10)]},
                "b4": {"name": "B4", "name_zh": "丁", "category": "x",
                       "members": [{"ticker": f"W{i}.SZ", "removed": None} for i in range(10)]},
            }}

    idx = pd.date_range("2025-01-01", periods=140, freq="D")
    rng = np.random.default_rng(7)
    cols = ([f"T{0}.SZ"] +                      # only ONE 'thin' member has any data
           [f"U{i}.SZ" for i in range(10)] +
           [f"V{i}.SZ" for i in range(10)] +
           [f"W{i}.SZ" for i in range(10)])
    wide = pd.DataFrame({c: rng.normal(0, 1, len(idx)) for c in cols}, index=idx)

    import sys
    import types
    fake_mod = types.ModuleType("engine.baskets_china")
    fake_mod._membership = _FakeBaskets._membership
    old = sys.modules.get("engine.baskets_china")
    sys.modules["engine.baskets_china"] = fake_mod
    try:
        sec = ashare_sector_velocity(wide)
    finally:
        if old is not None:
            sys.modules["engine.baskets_china"] = old
        else:
            del sys.modules["engine.baskets_china"]

    assert sec is not None
    assert sec["n"] == 4, "every basket must render a row — never dropped for coverage"
    thin = next(r for r in sec["rows"] if r["id"] == "thin")
    assert thin["coverage_state"] == "insufficient_coverage"
    assert thin["n_members"] == 10 and thin["n_covered"] <= 1
    assert thin["vel"] is None
