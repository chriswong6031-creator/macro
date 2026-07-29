"""ONE coverage shape across the options family (OIP R8).

Four builders each answered "how much of the universe did we see?" differently, and one
of them (build_flow_desk) answered it in a STRING no machine could read.  No surface
could put two side by side; no audit could compare them.  ``lib/options_coverage.py``
defines the shape once and all four now emit it under ``coverage_v1``.

These tests pin: the schema, the honesty rules (unknown stays None, never 0 or a
fabricated 100%), the calendar-derived staleness (never wall-clock days), the plain-word
bilingual naming (gate 4/5: no slugs, no enums, no "n=", in either language), and — the
load-bearing part — that all four builders actually construct it, ADDITIVELY, with every
pre-existing key intact.

Run: .venv/bin/python -m pytest tests/test_options_coverage_object.py -q
"""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import nyse_calendar, options_coverage  # noqa: E402

FAMILY = {
    "build_options_command": ROOT / "scripts" / "build_options_command.py",
    "build_gex_board": ROOT / "scripts" / "build_gex_board.py",
    "build_flow_desk": ROOT / "scripts" / "build_flow_desk.py",
    "build_options_screener": ROOT / "scripts" / "build_options_screener.py",
}


def _obj(**kw):
    base = dict(universe_name_en="Options names we track",
                universe_name_zh="我们跟踪的期权标的",
                universe_n=403, covered_n=370, asof="2026-07-28")
    base.update(kw)
    return options_coverage.coverage_object(**base)


# ────────────────────────────────────────────────────────────────── the schema


def test_schema_and_required_keys():
    o = _obj()
    assert o["schema"] == "options_coverage.v1"
    for k in ("schema", "universe", "covered", "coverage_pct", "asof",
              "sessions_behind", "sources"):
        assert k in o, f"missing required key {k}"
    assert set(o["universe"]) == {"name_en", "name_zh", "n"}


def test_coverage_pct_is_computed():
    assert _obj(universe_n=403, covered_n=370)["coverage_pct"] == 91.8


def test_source_row_shape():
    s = options_coverage.source("options_flow", "Options tape", "期权成交",
                                asof="2026-07-28", n=353)
    assert set(s) == {"key", "name_en", "name_zh", "asof", "n", "sessions_behind"}
    assert s["n"] == 353


# ─────────────────────────────────────────────────────────── honesty invariants


@pytest.mark.parametrize("uni,cov", [(None, 370), (403, None), (None, None), (0, 0)])
def test_an_unknown_denominator_is_null_not_a_fabricated_hundred_percent(uni, cov):
    o = _obj(universe_n=uni, covered_n=cov)
    assert o["coverage_pct"] is None, (
        "an uncountable universe must print as unknown, never as full coverage"
    )


def test_unknown_counts_stay_none_never_zero():
    """0 means 'we counted, and it was none'. None means 'we could not count'.
    Collapsing the two is how a dark feed reads as an empty market."""
    o = _obj(universe_n=None, covered_n=None)
    assert o["universe"]["n"] is None and o["covered"] is None
    s = options_coverage.source("x", "Store", "存储")
    assert s["n"] is None and s["asof"] is None and s["sessions_behind"] is None


def test_coverage_above_the_universe_is_clamped_not_published():
    o = _obj(universe_n=100, covered_n=140)
    assert o["coverage_pct"] == 100.0, "a >100% share is a counting bug, not a fact"
    assert o["covered"] == 140 and o["universe"]["n"] == 100, (
        "both raw counts must survive for inspection — clamping the SHARE, not the data"
    )


def test_no_exception_escapes_on_junk_input():
    for bad in (object(), "not-a-number", [], {}):
        o = options_coverage.coverage_object(
            universe_name_en="a", universe_name_zh="甲",
            universe_n=bad, covered_n=bad, asof=bad, sources=None)
        assert o["schema"] == "options_coverage.v1"
        assert o["coverage_pct"] is None


# ───────────────────────────────────── staleness is calendar-derived, not wall-clock


def test_sessions_behind_uses_the_exchange_calendar_not_calendar_days():
    """THE trap this guards: a store holding Friday's close is 0 sessions behind all
    weekend and on Monday morning. A wall-clock day count would call it 3 days stale
    and trip an SLA that is not actually blown."""
    friday = nyse_calendar.last_session_on_or_before(date.today())
    o = _obj(asof=friday.isoformat())
    expected = nyse_calendar.sessions_behind(friday)
    assert o["sessions_behind"] == expected
    # and it must equal what the calendar says, not (today - asof).days
    assert o["sessions_behind"] <= (date.today() - friday).days + 1


def test_sessions_behind_is_none_for_an_unparseable_stamp():
    for bad in (None, "", "not-a-date", "0000"):
        assert options_coverage._sessions_behind(bad) is None


def test_a_stale_source_reports_a_positive_lag():
    old = (date.today() - timedelta(days=40)).isoformat()
    s = options_coverage.source("x", "Store", "存储", asof=old)
    assert isinstance(s["sessions_behind"], int) and s["sessions_behind"] > 10


# ──────────────────────────────────── plain-word bilingual naming (gates 4/5)


_SLUGGY = re.compile(r"[_:]|\bn=|\bpct\b|\bidx\b|\basof\b", re.I)


def _display_names(obj) -> list[str]:
    out = [obj["universe"]["name_en"], obj["universe"]["name_zh"]]
    for s in obj["sources"]:
        out += [s["name_en"], s["name_zh"]]
    return out


def test_display_names_are_plain_words_in_both_languages():
    o = _obj(sources=[
        options_coverage.source("options_flow", "Options tape", "期权成交",
                                asof="2026-07-28", n=353),
        options_coverage.source("polygon_gex", "Option chains", "期权链",
                                asof="2026-07-28", n=403),
    ])
    for name in _display_names(o):
        assert name, "every display name must be non-empty in BOTH languages"
        assert not _SLUGGY.search(name), f"slug/enum leaked into display copy: {name!r}"


def test_zh_names_carry_no_english_state_words():
    """ZH must be independently plain — not an English name with Chinese around it."""
    o = _obj(sources=[options_coverage.source("options_flow", "Options tape", "期权成交")])
    for s in o["sources"]:
        assert not re.search(r"[A-Za-z]{3,}", s["name_zh"]), (
            f"ZH display name contains English: {s['name_zh']!r}"
        )
    assert not re.search(r"[A-Za-z]{3,}", o["universe"]["name_zh"])


def test_the_machine_key_is_separate_from_the_display_names():
    """`key` may be sluggy precisely BECAUSE it is never rendered."""
    s = options_coverage.source("options_ivspread", "Volatility vs peers", "波动率对比同业")
    assert "_" in s["key"]
    assert not _SLUGGY.search(s["name_en"]) and not _SLUGGY.search(s["name_zh"])


# ─────────────────────────────── all four builders emit it, additively


@pytest.mark.parametrize("name", sorted(FAMILY))
def test_every_family_builder_emits_the_shared_object(name):
    src = FAMILY[name].read_text()
    assert "options_coverage" in src, f"{name} does not import lib.options_coverage"
    assert '"coverage_v1"' in src or "coverage_v1" in src, \
        f"{name} does not emit the coverage_v1 key"
    assert "options_coverage.coverage_object(" in src, \
        f"{name} does not construct the shared object"


@pytest.mark.parametrize("name", sorted(FAMILY))
def test_every_family_builder_names_its_universe_bilingually(name):
    src = FAMILY[name].read_text()
    block = src.split("options_coverage.coverage_object(", 1)[1][:900]
    assert "universe_name_en=" in block and "universe_name_zh=" in block, (
        f"{name}'s coverage object must name its universe in both languages"
    )


def test_the_pre_existing_coverage_keys_survive():
    """ADDITIVE ONLY. These keys ship on live pages today; coverage_v1 must sit beside
    them, never replace them."""
    cmd = FAMILY["build_options_command"].read_text()
    for k in ('"covered"', '"universe"', '"coverage_pct"', '"quality_en"', '"quality_zh"'):
        assert k in cmd, f"build_options_command lost {k}"

    scr = FAMILY["build_options_screener"].read_text()
    for k in ('"n_names"', '"n_young"', '"median_depth_days"', '"n_skew"', '"n_ivspread"'):
        assert k in scr, f"build_options_screener lost {k}"

    fd = FAMILY["build_flow_desk"].read_text()
    assert '"coverage_note"' in fd, "build_flow_desk lost its coverage_note string"

    gb = FAMILY["build_gex_board"].read_text()
    assert 'coverage["__all__"]' in gb, "build_gex_board lost its __all__ roll-up"


def test_gex_board_key_cannot_collide_with_a_group_name():
    """build_gex_board's coverage dict is keyed by GROUP name and site/gex.js reads
    COV[grp] directly. `coverage_v1` must not be a group label."""
    gb = FAMILY["build_gex_board"].read_text()
    assert 'coverage["coverage_v1"]' in gb
    groups = re.findall(r'"(Core Index|Theme · [^"]+)"', gb)
    assert "coverage_v1" not in groups


# ──────────────────────────────────────────────── the real artifacts, if built


def test_the_screener_export_round_trips_the_object(tmp_path):
    """The export must carry whatever coverage the builder hands it — including the new
    key — without the builder having to know about the export.

    NOT asserted against the committed site/screenerdata/rows.json: that artifact is the
    last render's vintage and will not carry coverage_v1 until the next render lands, so
    an assertion on it would be red on a fresh checkout and green only by luck of local
    build order (the stale-artifact class).  The soft check below covers it when built."""
    import json

    import scripts.build_options_screener as bos

    coverage = {
        "n_names": 3, "n_young": 3, "n_mature": 0, "median_depth_days": 24,
        "young_threshold": 252, "tape_flow_present": False,
        "n_skew": 3, "n_ivspread": 2, "n_relvol": 1,
        "built": "2026-07-29 21:00 UTC",
        "coverage_v1": _obj(universe_n=3, covered_n=3, asof="2026-07-29", sources=[
            options_coverage.source("polygon_gex", "Option chains", "期权链",
                                    asof="2026-07-29", n=3)]),
    }
    out = bos.write_rows_export([{"ticker": "AAA"}], coverage,
                                out_path=tmp_path / "rows.json")
    doc = json.loads(Path(out).read_text())
    cov = doc["coverage"]
    assert cov["coverage_v1"]["schema"] == "options_coverage.v1"
    assert cov["coverage_v1"]["sources"], "the object must name its sources"
    for k in ("n_names", "n_skew", "n_ivspread", "median_depth_days"):
        assert k in cov, f"the export dropped the pre-existing key {k}"


@pytest.mark.parametrize("rel,getter", [
    ("site/screenerdata/rows.json", lambda d: d.get("coverage") or {}),
    ("site/flow_desk.json", lambda d: d.get("market_tide") or {}),
])
def test_built_artifacts_carry_the_object_when_freshly_rendered(rel, getter):
    """Soft: skips on a committed vintage that predates this change, asserts once a
    render has landed."""
    p = ROOT / rel
    if not p.exists():
        pytest.skip(f"{rel} absent on this runner")
    import json
    holder = getter(json.loads(p.read_text()))
    if "coverage_v1" not in holder:
        pytest.skip(f"{rel} predates this change on this runner")
    assert holder["coverage_v1"]["schema"] == "options_coverage.v1"
    if rel.endswith("flow_desk.json"):
        assert "coverage_note" in holder, "the human-readable note must survive alongside"
