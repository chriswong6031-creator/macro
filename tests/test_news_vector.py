"""Data-quality gate for engine/news_vector.py — the PIT event bus (P0).

This module ships no forward-return claim, so its Phase-0 is a DATA-QUALITY bar
(memory narrative-quant-framework): the keep-FIRST accrual must never restamp an
event (the #1 look-ahead failure mode), the event_id must be stable, the gate must
drop off-narrative / non-reputable / duplicate headlines, and the module must stay
a LEAF (no mechanical-core imports; nothing in engine/ imports it). No network.

Run as a plain script:  python tests/test_news_vector.py
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import news_vector as nv  # noqa: E402


# --------------------------------------------------------------------------- #
# event_id — stable, normalization-invariant, content-defined
# --------------------------------------------------------------------------- #
def test_event_id_stable_and_normalized():
    a = nv.event_id("Trump Threatens 50% Tariff on EU", "reuters.com")
    b = nv.event_id("trump   threatens 50%  tariff on eu!!!", "Reuters.com")
    assert a == b, "event_id must be invariant to case/whitespace/punctuation"
    assert a != nv.event_id("Trump threatens 50% tariff on EU", "cnbc.com"), "domain participates"
    assert len(a) == 16 and all(c in "0123456789abcdef" for c in a)


# --------------------------------------------------------------------------- #
# theme taxonomy — distinctive policy/geo buckets beat generic macro
# --------------------------------------------------------------------------- #
def test_classify_theme_ordering():
    assert nv.classify_theme("US and Iran reach ceasefire deal") == "geopolitics"
    assert nv.classify_theme("White House weighs new tariffs on China") == "trade"
    assert nv.classify_theme("Government takes a stake in Intel semiconductor plant") == "industrial_policy"
    assert nv.classify_theme("Fed holds interest rates steady") == "monetary"
    assert nv.classify_theme("CPI shows inflation cooling") == "inflation"
    # off-narrative -> dropped
    assert nv.classify_theme("Local team wins championship") is None
    assert nv.classify_theme("") is None


def test_source_tier():
    assert nv.source_tier("reuters.com") == 1 and nv.source_tier("finance.bloomberg.com") == 1
    assert nv.source_tier("someblog.substack.com") == 2 and nv.source_tier("") == 2


# --------------------------------------------------------------------------- #
# build_records — allowlist + relevance gate + dedup + scheduled_ref stamp
# --------------------------------------------------------------------------- #
_ARTS = [
    {"title": "US, Iran reach ceasefire deal", "domain": "reuters.com", "seendate": "2026-06-10T12:00:00+00:00"},
    {"title": "US, Iran reach ceasefire deal", "domain": "reuters.com", "seendate": "2026-06-10T13:00:00+00:00"},  # dup id
    {"title": "New tariffs rattle markets", "domain": "cnbc.com", "seendate": "2026-06-09T09:00:00+00:00"},
    {"title": "Celebrity gossip roundup", "domain": "reuters.com", "seendate": "2026-06-10T10:00:00+00:00"},  # off-theme
    {"title": "Fed CPI inflation report", "domain": "randomspam.xyz", "seendate": "2026-06-10T08:30:00+00:00"},  # not allowlisted
]
_SCHED = {"2026-06-10": "CPI"}
_ALLOW = ["reuters.com", "cnbc.com"]


def test_build_records_gates_and_stamps():
    recs = nv.build_records(_ARTS, _SCHED, _ALLOW, "2026-06-10T20:00:00+00:00")
    assert len(recs) == 2, "dedup + allowlist + theme gate should leave exactly 2"
    assert [r["theme"] for r in recs] == ["geopolitics", "trade"]
    assert all(r["first_seen_utc"] == "2026-06-10T20:00:00+00:00" for r in recs)
    # scheduled_ref: CPI on 06-10 catches the 06-10 article AND (±1 day) the 06-09 one
    assert recs[0]["scheduled_ref"] == "CPI@2026-06-10"
    assert recs[1]["scheduled_ref"] == "CPI@2026-06-10"


def test_scheduled_ref_window():
    assert nv._scheduled_ref_for("2026-06-12T00:00:00+00:00", _SCHED) == ""   # 2 days away -> no stamp
    assert nv._scheduled_ref_for("2026-06-11T00:00:00+00:00", _SCHED) == "CPI@2026-06-10"  # +1 day
    assert nv._scheduled_ref_for("bad-date", _SCHED) == ""


# --------------------------------------------------------------------------- #
# keep-FIRST accrual — the load-bearing anti-look-ahead invariant
# --------------------------------------------------------------------------- #
def test_keep_first_no_restamp():
    recs = nv.build_records(_ARTS, _SCHED, _ALLOW, "2026-06-10T20:00:00+00:00")
    df1 = nv.accrue(None, recs)
    assert len(df1) == 2
    # re-ingest the SAME events on a later day -> first_seen_utc MUST be preserved
    later = [dict(r, first_seen_utc="2026-06-12T20:00:00+00:00") for r in recs]
    df2 = nv.accrue(df1, later)
    assert len(df2) == 2, "re-ingesting the same events must not grow the store"
    fs = set(df2["first_seen_utc"])
    assert fs == {"2026-06-10T20:00:00+00:00"}, f"RESTAMP LEAK: {fs}"


def test_accrual_grows_on_new_and_is_idempotent():
    recs = nv.build_records(_ARTS, _SCHED, _ALLOW, "2026-06-10T20:00:00+00:00")
    df = nv.accrue(None, recs)
    new = [{"event_id": nv.event_id("Israel strikes facility", "apnews.com"),
            "first_seen_utc": "2026-06-12T20:00:00+00:00", "seendate": "2026-06-12T01:00:00+00:00",
            "title": "Israel strikes facility", "url": "u", "domain": "apnews.com",
            "theme": "geopolitics", "source_tier": 1, "scheduled_ref": ""}]
    df2 = nv.accrue(df, new)
    assert len(df2) == 3
    # re-accruing the same batch is a no-op (byte-stable content)
    df3 = nv.accrue(df2, new)
    assert len(df3) == 3
    assert list(df3["event_id"]) == list(df2["event_id"]), "re-accrue must be order-stable"


def test_accrue_empty_records():
    df = nv.accrue(None, [])
    assert len(df) == 0 and list(df.columns) == list(nv._COLUMNS)


# --------------------------------------------------------------------------- #
# percentile helper + read paths never raise
# --------------------------------------------------------------------------- #
def test_pct_rank():
    import pandas as pd
    s = pd.Series(range(100))
    assert nv._pct_rank(s, 49) == 50.0
    assert nv._pct_rank(s, 99) == 100.0
    assert nv._pct_rank(pd.Series([1, 2, 3]), 2) is None       # < 30 obs -> None
    assert nv._pct_rank(s, None) is None


def test_reads_never_raise():
    # whatever the local store contains, these must return None-or-dict, never raise
    rp = nv.recent_panel()
    assert rp is None or (isinstance(rp, dict) and rp.get("is_context_only") is True)
    ur = nv.uncertainty_regime()
    assert ur is None or isinstance(ur, dict)


# --------------------------------------------------------------------------- #
# LLM extraction is OFF in P0
# --------------------------------------------------------------------------- #
def test_llm_extract_stays_off_even_when_bus_enabled():
    # The event bus may be ENABLED (it accrues the forward PIT event store), but the
    # LLM structured-extraction STAGE is a separate switch (llm_extract) that stays
    # off — extract_structured must remain a no-op with neutral placeholders.
    assert nv._cfg().get("llm_extract", False) is False, "LLM extraction stage must stay off"
    rec = {"event_id": "x", "title": "t", "theme": "trade"}
    out = nv.extract_structured(rec)
    assert out["llm_extracted"] is False
    assert out["direction_claimed"] == "unknown" and out["surprise"] is None
    assert out["reversibility"] == "unknown" and out["scope"] == "unknown"


# --------------------------------------------------------------------------- #
# LEAF discipline — enforced, not aspirational
# --------------------------------------------------------------------------- #
# news_vector may import only these engine siblings (other LEAF modules).
_ALLOWED_ENGINE = {"macro_news", "event_calendar"}
# mechanical-core modules nothing in any scoring path may pull into this leaf.
_FORBIDDEN_ROOTS = {"engine.conditions", "engine.regime", "engine.run", "engine.inputs",
                    "engine.cycles", "engine.equity_alloc", "engine.calibrate"}


def _imported_modules(py_path: Path) -> set[str]:
    tree = ast.parse(py_path.read_text())
    mods: set[str] = set()
    for node in ast.walk(tree):           # walk handles lazy in-function imports too
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module)
    return mods


def test_news_vector_is_a_leaf():
    mods = _imported_modules(ROOT / "engine" / "news_vector.py")
    for m in mods:
        assert m not in _FORBIDDEN_ROOTS, f"LEAF violation: news_vector imports core {m}"
        if m.startswith("engine."):
            sub = m.split(".", 1)[1]
            assert sub in _ALLOWED_ENGINE, f"news_vector may only import sibling leaves, not engine.{sub}"


def test_no_engine_module_imports_news_vector():
    """Nothing in engine/ (the scoring core) may import the bus — it is read only by
    the display path (scripts/build_site.py)."""
    offenders = []
    for p in (ROOT / "engine").glob("*.py"):
        if p.name == "news_vector.py":
            continue
        if "news_vector" in p.read_text():
            offenders.append(p.name)
    assert not offenders, f"scoring-core modules import the bus: {offenders}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} passed")
