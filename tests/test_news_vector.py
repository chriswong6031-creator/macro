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
    # MN-06: CPI on 06-10 must NOT stamp the geopolitics/trade articles — neither
    # theme is in CPI's macro channel, so neither move is "explained" by the print.
    assert recs[0]["scheduled_ref"] == ""
    assert recs[1]["scheduled_ref"] == ""


def test_scheduled_ref_reaction_window_and_channel():
    # same-day inflation article -> stamped
    assert nv._scheduled_ref_for("2026-06-10T14:00:00+00:00", _SCHED, "inflation") == "CPI@2026-06-10"
    # day-AFTER reaction (release yesterday) -> stamped
    assert nv._scheduled_ref_for("2026-06-11T00:00:00+00:00", _SCHED, "inflation") == "CPI@2026-06-10"
    # rate-path and market-wrap reactions are the calendar-explained flow too
    assert nv._scheduled_ref_for("2026-06-10T14:00:00+00:00", _SCHED, "monetary") == "CPI@2026-06-10"
    assert nv._scheduled_ref_for("2026-06-10T14:00:00+00:00", _SCHED, "markets") == "CPI@2026-06-10"
    # day-BEFORE preview (release tomorrow) can't explain today's flow -> no stamp
    assert nv._scheduled_ref_for("2026-06-09T00:00:00+00:00", _SCHED, "inflation") == ""
    # off-channel themes are the headline-shock flow -> never stamped (MN-06)
    for theme in ("geopolitics", "trade", "industrial_policy", "ai_tech", "energy"):
        assert nv._scheduled_ref_for("2026-06-10T14:00:00+00:00", _SCHED, theme) == "", theme
    # 2 days away / garbage dates -> no stamp
    assert nv._scheduled_ref_for("2026-06-12T00:00:00+00:00", _SCHED, "inflation") == ""
    assert nv._scheduled_ref_for("bad-date", _SCHED, "inflation") == ""


def test_scheduled_ref_channel_map_covers_high_impact():
    """Fail-closed contract: every _HIGH_IMPACT release type must have a channel
    entry — an unmapped type stamps NOTHING (silently reverting to the blanket
    stamp is the MN-06 bug), so the map must stay in lockstep."""
    missing = nv._HIGH_IMPACT - set(nv._SCHEDULED_REF_THEMES)
    assert not missing, f"_SCHEDULED_REF_THEMES missing high-impact types: {missing}"
    # unmapped type -> fail closed, no stamp even on a matching-looking theme
    assert nv._scheduled_ref_for("2026-06-10T14:00:00+00:00", {"2026-06-10": "RETAIL"},
                                 "inflation") == ""


# --------------------------------------------------------------------------- #
# MN-05: low-value junk gate — listicles/advertorials must not pollute the theme
# counts that feed news_flow velocity (a scored leg via theme_activity)
# --------------------------------------------------------------------------- #
def test_low_value_advertorials_dropped_from_build():
    junk = [
        {"title": "Prediction: This Will Be Nvidia Stock Price Next Year "
                  "(Hint: The Time to Buy Is Now)",
         "domain": "cnbc.com", "seendate": "2026-06-10T12:00:00+00:00"},
        {"title": "Is Silo Pharma an AI Opportunity",
         "domain": "cnbc.com", "seendate": "2026-06-10T12:00:00+00:00"},
        {"title": "3 Artificial Intelligence Stocks to Buy Before the Fed Cuts Rates",
         "domain": "cnbc.com", "seendate": "2026-06-10T12:00:00+00:00"},
    ]
    real = [
        {"title": "Nvidia announces new data center chip partnership with OpenAI",
         "domain": "reuters.com", "seendate": "2026-06-10T12:00:00+00:00"},
    ]
    recs = nv.build_records(junk + real, _SCHED, _ALLOW, "2026-06-10T20:00:00+00:00")
    titles = [r["title"] for r in recs]
    assert len(recs) == 1 and titles[0].startswith("Nvidia announces"), (
        f"low-value junk leaked into the accrual: {titles}")


def test_low_value_gate_degrades_open():
    """If news_common is unavailable the gate must degrade to NO filtering (the
    pre-filter behavior) — a broken helper must never blank the accrual. Patches
    BOTH resolution paths of `from engine import news_common` (the sys.modules
    entry and the already-set package attribute)."""
    import sys
    from unittest.mock import patch
    import engine as engine_pkg
    junk = [{"title": "Is Silo Pharma an AI Opportunity",   # would be dropped when healthy
             "domain": "cnbc.com", "seendate": "2026-06-10T12:00:00+00:00"}]
    with patch.dict(sys.modules, {"engine.news_common": None}), \
         patch.object(engine_pkg, "news_common", None, create=True):
        recs = nv.build_records(junk, _SCHED, _ALLOW, "2026-06-10T20:00:00+00:00")
    assert len(recs) == 1, "degrade-open failed: gate blanked the accrual without news_common"


def test_already_accrued_junk_is_not_rewritten():
    """Forward-only contract: the filter changes what accrues from NOW on; rows
    already in the store (junk or not, old blanket stamps included) are preserved
    verbatim by keep-FIRST accrual — history is never rewritten."""
    import pandas as pd
    legacy = pd.DataFrame([{
        "event_id": nv.event_id("Is Silo Pharma an AI Opportunity", "cnbc.com"),
        "first_seen_utc": "2026-06-01T20:00:00+00:00", "seendate": "2026-06-01T10:00:00+00:00",
        "title": "Is Silo Pharma an AI Opportunity", "url": "u", "domain": "cnbc.com",
        "theme": "ai_tech", "source_tier": 2, "scheduled_ref": "PPI@2026-06-01",
    }])
    recs = nv.build_records(_ARTS, _SCHED, _ALLOW, "2026-06-10T20:00:00+00:00")
    merged = nv.accrue(legacy, recs)
    old = merged[merged["event_id"] == legacy["event_id"].iloc[0]]
    assert len(old) == 1, "legacy junk row must survive accrual untouched"
    assert old["scheduled_ref"].iloc[0] == "PPI@2026-06-01", "historical stamp rewritten"
    assert len(merged) == 1 + 2


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
# qbus is a W2 LEAF — allowed for the ingest_to_qbus boundary call.
# gdelt_client is the shared GDELT transport LEAF (lib.config only) — allowed.
# news_common is the shared news-suite LEAF (low_value_reason junk gate, MN-05).
_ALLOWED_ENGINE = {"macro_news", "event_calendar", "qbus", "gdelt_client", "news_common"}
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


def _imports_news_vector_bus(py_path: Path) -> bool:
    """True iff the file actually IMPORTS engine.news_vector (any form) — as opposed to
    merely naming the module in a comment/docstring. ast.walk catches lazy in-function
    imports too. Forms covered:
        import engine.news_vector [as nv]
        from engine.news_vector import X
        from engine import news_vector [as nv]
    """
    tree = ast.parse(py_path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "engine.news_vector" for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "engine.news_vector":
                return True
            if mod == "engine" and any(a.name == "news_vector" for a in node.names):
                return True
    return False


def test_no_engine_module_imports_news_vector():
    """Nothing in engine/ (the scoring core) may IMPORT the bus — it is read only by the
    display path (scripts/build_site.py). Enforced at the IMPORT level (AST), so a passing
    documentary mention of the module name in a comment/docstring is NOT a violation: a
    scoring leg may legitimately read the bus's OUTPUT parquet and say so (e.g. news_flow).
    A real ``import engine.news_vector`` — including a lazy in-function one — is the violation."""
    offenders = [p.name for p in (ROOT / "engine").glob("*.py")
                 if p.name != "news_vector.py" and _imports_news_vector_bus(p)]
    assert not offenders, f"scoring-core modules import the bus: {offenders}"


# --------------------------------------------------------------------------- #
# W2-B3: accrual fix regression tests
# --------------------------------------------------------------------------- #
def test_failed_fetch_result_is_not_cached(tmp_path):
    """Root-cause regression: a rate_limited / fetch_error response with 0 articles
    must NOT be written to the fetch cache.  If it were cached, every subsequent
    ingest call within the 12-hour TTL would silently return 0 articles and the
    accrual store would stall (exactly the bug that caused newest event 2026-06-20)."""
    import json
    from datetime import date as d
    from unittest.mock import patch, MagicMock

    cfg = {
        "enabled": True, "window_days": 2, "max_records": 10,
        "min_request_interval_s": 0, "cache_ttl_hours": 12,
        "cache_dir": str(tmp_path / "cache"),
        "lang": "eng", "query_terms": [],
    }
    today = d(2026, 6, 25)

    # Simulate a 429 rate-limited response from GDELT. time.sleep is patched:
    # engine.gdelt_client's bounded retry sleeps 30s+75s on persistent 429.
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {}

    with patch("requests.get", return_value=mock_resp), patch("time.sleep"):
        articles, reason = nv._fetch_gdelt(cfg, today)

    assert articles == [], "rate_limited should return empty articles"
    assert reason == "rate_limited"

    # Cache must NOT have been written for a failed response
    cache_dir = tmp_path / "cache"
    cache_files = list(cache_dir.glob("*.json")) if cache_dir.exists() else []
    assert cache_files == [], (
        "Failed fetch (rate_limited/empty) must NOT be written to cache — "
        "caching it would silently stall the accrual for 12 hours"
    )


def test_successful_fetch_is_cached(tmp_path):
    """Successful responses (articles present) ARE cached to avoid hammering GDELT."""
    import json
    from datetime import date as d
    from unittest.mock import patch, MagicMock

    cfg = {
        "enabled": True, "window_days": 2, "max_records": 10,
        "min_request_interval_s": 0, "cache_ttl_hours": 12,
        "cache_dir": str(tmp_path / "cache"),
        "lang": "eng", "query_terms": [],
    }
    today = d(2026, 6, 25)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_resp.json.return_value = {"articles": [
        {"title": "Fed holds rates", "url": "https://reuters.com/1",
         "domain": "reuters.com", "seendate": "20260625T120000Z"},
    ]}

    with patch("requests.get", return_value=mock_resp):
        articles, reason = nv._fetch_gdelt(cfg, today)

    assert len(articles) == 1
    assert reason is None

    cache_dir = tmp_path / "cache"
    cache_files = list(cache_dir.glob("*.json"))
    assert len(cache_files) == 1, "Successful fetch must be cached"
    blob = json.loads(cache_files[0].read_text())
    assert blob["articles"] and blob["degraded_reason"] is None


def test_freshness_check_warns_when_stale(tmp_path):
    """_check_freshness must log a WARNING and return warn=True when newest event
    is older than _FRESHNESS_WARN_DAYS (currently 3)."""
    import pandas as pd
    from datetime import date as dt, timedelta

    path = tmp_path / "events.parquet"
    stale_date = (dt.today() - timedelta(days=nv._FRESHNESS_WARN_DAYS + 5)).isoformat()
    df = pd.DataFrame([{
        "event_id": "abc123", "first_seen_utc": stale_date + "T00:00:00+00:00",
        "seendate": stale_date, "title": "old news", "url": "http://reuters.com",
        "domain": "reuters.com", "theme": "trade", "source_tier": 1, "scheduled_ref": "",
    }])
    df.to_parquet(path, index=False)

    result = nv._check_freshness(path, dt.today())
    assert result["warn"] is True, "stale store must set warn=True"
    assert result["age_days"] is not None and result["age_days"] > nv._FRESHNESS_WARN_DAYS


def test_freshness_check_ok_when_fresh(tmp_path):
    """_check_freshness returns warn=False when newest event is recent."""
    import pandas as pd
    from datetime import date as dt, timedelta, timezone
    from datetime import datetime

    path = tmp_path / "events.parquet"
    fresh_date = datetime.now(timezone.utc).isoformat()
    df = pd.DataFrame([{
        "event_id": "abc123", "first_seen_utc": fresh_date,
        "seendate": fresh_date[:10], "title": "fresh news", "url": "http://reuters.com",
        "domain": "reuters.com", "theme": "trade", "source_tier": 1, "scheduled_ref": "",
    }])
    df.to_parquet(path, index=False)

    result = nv._check_freshness(path, dt.today())
    assert result["warn"] is False


def test_freshness_check_warns_missing_file(tmp_path):
    """_check_freshness returns warn=True with reason='missing' for absent parquet."""
    from datetime import date as dt
    result = nv._check_freshness(tmp_path / "nofile.parquet", dt.today())
    assert result["warn"] is True and result.get("reason") == "missing"


def test_leaf_still_allows_qbus_import():
    """news_vector.ingest_to_qbus may import engine.qbus — qbus is a LEAF (W2), so
    this is allowed.  The LEAF test above checks the static top-level imports; this
    test verifies the new function's lazy import does not violate the allowed-set."""
    # ingest_to_qbus lazily imports qbus inside the function body; that is the
    # expected pattern for LEAF-to-LEAF calls.  We just verify the function exists
    # and is callable without raising at import time.
    assert callable(nv.ingest_to_qbus)


def test_ingest_to_qbus_no_raise_when_parquet_missing(tmp_path):
    """ingest_to_qbus must degrade gracefully when events.parquet doesn't exist."""
    import os
    from unittest.mock import patch

    # Point data dir to tmp_path so events.parquet won't be found
    with patch.object(nv, "_events_path", return_value=tmp_path / "nofile.parquet"):
        result = nv.ingest_to_qbus()
    # Should return None (no parquet found) without raising
    assert result is None


# --------------------------------------------------------------------------- #
# 2026-06-20..07-10 outage regression: GDELT rejected the single 288-char query
# ("Your query was too short or too long.", HTTP 200 + text/html) daily for
# three weeks; the generic "fetch_error" label hid the structural cause.
# --------------------------------------------------------------------------- #
def test_queries_split_under_gdelt_limit():
    """Every sub-query must stay under _MAX_QUERY_LEN and no term may be lost."""
    qs = nv._queries({})
    assert len(qs) >= 2, "the default core must split (single query was 288 chars)"
    for q in qs:
        assert len(q) <= nv._MAX_QUERY_LEN, f"sub-query too long ({len(q)}): {q!r}"
        assert q.startswith("(") and " sourcecountry:US sourcelang:eng" in q
    joined = " ".join(qs)
    for term in nv._QUERY_CORE:
        assert term in joined, f"term lost in the split: {term}"


def test_queries_respects_config_override():
    qs = nv._queries({"query_terms": ["alpha", "beta"], "lang": "eng"})
    assert qs == ["(alpha OR beta) sourcecountry:US sourcelang:eng"]


def test_query_rejected_is_structural_and_not_cached(tmp_path):
    """A GDELT 200+text/html 'too short or too long' rejection must surface as
    query_rejected (NOT fetch_error) and must not be cached."""
    from datetime import date as d
    from unittest.mock import patch, MagicMock

    cfg = {"enabled": True, "window_days": 2, "max_records": 10,
           "min_request_interval_s": 0, "cache_ttl_hours": 12,
           "cache_dir": str(tmp_path / "cache"), "lang": "eng", "query_terms": []}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    mock_resp.text = "Your query was too short or too long."

    with patch("requests.get", return_value=mock_resp):
        articles, reason = nv._fetch_gdelt(cfg, d(2026, 7, 10))

    assert articles == []
    assert reason == "query_rejected", (
        "structural rejection must be labeled query_rejected — the generic "
        "fetch_error label is what hid the 2026-06-20 stall for three weeks")
    cache_dir = tmp_path / "cache"
    assert not (cache_dir.exists() and list(cache_dir.glob("*.json")))


def test_partial_rejection_stays_loud(tmp_path):
    """If ONE sub-query is rejected while another returns articles, the articles
    are kept AND degraded_reason still says query_rejected (structural beats
    partial success — it never self-heals)."""
    from datetime import date as d
    from unittest.mock import patch, MagicMock

    cfg = {"enabled": True, "window_days": 2, "max_records": 10,
           "min_request_interval_s": 0, "cache_ttl_hours": 12,
           "cache_dir": str(tmp_path / "cache"), "lang": "eng", "query_terms": []}

    ok = MagicMock()
    ok.status_code = 200
    ok.headers = {"Content-Type": "application/json"}
    ok.json.return_value = {"articles": [
        {"title": "Fed holds rates", "url": "https://reuters.com/1",
         "domain": "reuters.com", "seendate": "20260710T120000Z"}]}
    rejected = MagicMock()
    rejected.status_code = 200
    rejected.headers = {"Content-Type": "text/html"}
    rejected.text = "Your query was too short or too long."

    with patch("requests.get", side_effect=[ok, rejected]):
        with patch.object(nv, "_queries", return_value=["(qa) x", "(qb) x"]):
            articles, reason = nv._fetch_gdelt(cfg, d(2026, 7, 10))

    assert len(articles) == 1, "the healthy sub-query's articles must be kept"
    assert reason == "query_rejected"


def test_fetch_dedups_across_subqueries(tmp_path):
    """The same story matched by two sub-queries must appear once."""
    from datetime import date as d
    from unittest.mock import patch, MagicMock

    cfg = {"enabled": True, "window_days": 2, "max_records": 10,
           "min_request_interval_s": 0, "cache_ttl_hours": 12,
           "cache_dir": str(tmp_path / "cache"), "lang": "eng", "query_terms": []}
    ok = MagicMock()
    ok.status_code = 200
    ok.headers = {"Content-Type": "application/json"}
    ok.json.return_value = {"articles": [
        {"title": "Tariffs hit semiconductor stocks", "url": "https://reuters.com/2",
         "domain": "reuters.com", "seendate": "20260710T120000Z"}]}

    with patch("requests.get", return_value=ok):
        articles, reason = nv._fetch_gdelt(cfg, d(2026, 7, 10))

    assert len(articles) == 1, "cross-sub-query duplicates must be deduped"
    assert reason is None


def test_freshness_escalates_to_error_after_a_week(tmp_path):
    """3 < age <= 7 days -> warn only; age > _FRESHNESS_ERROR_DAYS -> escalated."""
    import pandas as pd
    from datetime import date as dt, timedelta

    def _store(age_days: int) -> Path:
        p = tmp_path / f"events_{age_days}.parquet"
        day = (dt.today() - timedelta(days=age_days)).isoformat()
        pd.DataFrame([{
            "event_id": "abc123", "first_seen_utc": day + "T00:00:00+00:00",
            "seendate": day, "title": "old news", "url": "http://reuters.com",
            "domain": "reuters.com", "theme": "trade", "source_tier": 1,
            "scheduled_ref": "",
        }]).to_parquet(p, index=False)
        return p

    mild = nv._check_freshness(_store(nv._FRESHNESS_WARN_DAYS + 2), dt.today())
    assert mild["warn"] is True and mild["escalated"] is False

    stalled = nv._check_freshness(_store(nv._FRESHNESS_ERROR_DAYS + 13), dt.today())
    assert stalled["warn"] is True and stalled["escalated"] is True, (
        "a 20-day stall must escalate past WARNING — daily warnings with no "
        "escalation is how the 2026-06 outage ran for three weeks")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        try:
            import inspect
            sig = inspect.signature(fn)
            if sig.parameters:
                import tempfile
                with tempfile.TemporaryDirectory() as td:
                    fn(Path(td))
            else:
                fn()
            print(f"ok  {fn.__name__}")
        except Exception as exc:
            print(f"FAIL {fn.__name__}: {exc}")
            raise
    print(f"\n{len(fns)} passed")
