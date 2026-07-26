"""tests/test_chronicle.py — Chronicle W0 engine tests
(CHRONICLE_CONTEXT_TIMELINE_MASTERPLAN_BY_FABLE.md §0 acceptance gates).

Covers:
  (a) build twice -> events.jsonl byte-identical (determinism)
  (b) re-run adds zero duplicates (idempotency); a source row leaving the
      snapshot RETAINS its event (union-merge, never a silent delete)
  (c) every emitted event's keys == schema keys exactly; every fact <=200
      chars (public-safe / schema law); every adapter proves an EXACT,
      non-zero census on the seeded fixture (presence != coverage)
  (d) pack() respects token_budget, returns a coverage note, renders facts
      into the line text, matches on word boundaries + exact theme
      membership, is a hard right edge on as_of by default, discloses
      budget-evicted lines, degrades fail-soft on a malformed as_of, and
      as_of far-past returns empty-with-reason
  (e) adapter fail-soft: missing/corrupt fixture root -> gap note, no raise
  (f) state_log flip derivation: a quad change between two state_log rows ->
      exactly one regime_flip event; first-run baseline -> zero flip events;
      a gap night defers (never resets) the comparison; the production seam
      (capture_row -> append_row_if_new -> read_state_log -> derive_flip_events)
      is exercised end to end, not just hand-built row fixtures
  (g) manifest carries envelope keys + correct row counts + honest gap notes
  (h) the mastermind summarizer returns an ok-shaped dict on the seeded store
      (recent sorted by deterministic salience) and fails soft on a bare root
  (i) risk_band reads the real committed data/risk_radar/forward_log.jsonl
      history directly (B6); the Prophet BEAR sign fix; the macro_release
      scored-print join; rollups.py exercised directly

Uses tmp_path fixture roots throughout (root=None-style injection — every
Chronicle function takes root), mirroring tests/test_marketing_engine.py.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()


# ---------------------------------------------------------------------------
# Fixture root builder — one synthetic row per W0 source
# ---------------------------------------------------------------------------

def _make_fixture_root(tmp_path: Path) -> Path:
    """Seeds exactly one event-producing row per file adapter (research_vault,
    prophet_ledger, macro_release, earnings, risk_band = 5 events) plus a
    world_state.json shaped for state_log capture (0 regime_flip events on a
    single build — first-run baseline). Total baseline events on a fresh
    fixture root: 5.

    m8: the vault item deliberately carries EMPTY tags/tickers — the real
    committed catalog has neither populated on any of its 86 items, so a
    fixture that gave itself both was masking the M6/M8 defects the review
    caught. Tests that need themes-driven matching build their own tiny local
    fixture instead of leaning on this shared one (see
    test_theme_matches_when_title_lacks_topic_word below).
    """
    root = tmp_path
    (root / "data" / "research_vault").mkdir(parents=True)
    (root / "data" / "prophet").mkdir(parents=True)
    (root / "data" / "release_forecast").mkdir(parents=True)
    (root / "data" / "earnings").mkdir(parents=True)
    (root / "data" / "risk_radar").mkdir(parents=True)
    (root / "data" / "neuralweb").mkdir(parents=True)

    catalog = {
        "schema": "research_vault.catalog.v1",
        "generated_at": "2026-07-20T00:00:00Z",
        "count": 1,
        "institutions": ["Test Bank"],
        "items": [{
            "id": "test-item-1",
            "title": "Semis positioning stretched",
            "institution": "Test Bank",
            "side": "sell",
            "desk": "",
            "published_at": "2026-07-20T14:00:00Z",
            "summary_points": [
                "Fund positioning in semis is at a 2-year high.",
                "Watch NVDA into earnings.",
            ],
            "tags": [],       # m8: real catalog items carry no tags — mirror that
            "tickers": [],    # m8: real catalog items carry no tickers — mirror that
            "top_pick": True,
            "pages": 5,
            "needs_metadata": False,
        }],
    }
    (root / "data" / "research_vault" / "catalog.json").write_text(
        json.dumps(catalog), encoding="utf-8")

    ledger_lines = [
        "# prophet ledger row schema — see research/PROPHET_LEDGER_SCHEMA.md",
        json.dumps({
            "schema": "prophet.ledger/v1", "id": "TST-BULL-20260601", "asset": "TST",
            "direction": "BULL", "signal_date": "2026-06-01", "close_date": "2026-07-15",
            "outcome": "EXPIRED", "stock_result_pct": -1.5, "option_result_pct": None,
            "days_held": 44, "plan_adherence": "test row", "asof": "2026-07-15",
        }),
    ]
    (root / "data" / "prophet" / "ledger.jsonl").write_text(
        "\n".join(ledger_lines) + "\n", encoding="utf-8")

    release_row = {
        "schema": 2, "row_type": "reaction", "asof_night": "2026-07-16", "release": "claims",
        "period": "2026-07-09", "release_date": "2026-07-09", "h0_day": "2026-07-09",
        "h1_day": "2026-07-10", "dgs10_h0_bp": -2.0, "dgs10_h1_bp": 2.0,
        "spread_2s10s_h0_bp": 3.0, "spy_h0_pct": 1.2, "spy_h1_pct": 0.4, "dollar_h0_pct": -0.3,
    }
    (root / "data" / "release_forecast" / "forward_ledger.jsonl").write_text(
        json.dumps(release_row) + "\n", encoding="utf-8")

    df = pd.DataFrame(
        [{
            "next_date": "2026-08-01", "next_time": "amc",
            "eps_forecast": 1.5,
            "surprises_json": json.dumps([{
                "qtr": "Jun 2026", "reported": "7/14/2026",
                "eps": 2.0, "consensus": 1.5, "surprise_pct": 33.3,
            }]),
            "as_of": "2026-07-20T00:00:00Z",
        }],
        index=pd.Index(["TST"], name="ticker"),
    )
    df.to_parquet(root / "data" / "earnings" / "earnings.parquet")

    # B6: risk_band's real source — a committed, dated, source-native ledger
    # with a genuine state change (1 flip expected).
    risk_radar_rows = [
        {"asof": "2026-07-17", "state": "calm", "dominant_scare": "growth", "top_score": 20.0},
        {"asof": "2026-07-18", "state": "elevated", "dominant_scare": "growth", "top_score": 55.0},
    ]
    (root / "data" / "risk_radar" / "forward_log.jsonl").write_text(
        "\n".join(json.dumps(r) for r in risk_radar_rows) + "\n", encoding="utf-8")

    # M1: global_regimes carries a source-native per-market `date`, distinct
    # from produced_at (fixture deliberately mirrors the real skew: as-of
    # dated one day before produced_at).
    world_state = {
        "global_regimes": {
            "us": {"market": "us", "date": "2026-07-20", "quad": "Q1",
                   "quad_name": "Goldilocks", "cycle_tag": "mid"},
            "china": {"market": "china", "date": "2026-07-20", "quad": "Q3",
                      "quad_name": "Stagflation", "cycle_tag": "mid"},
        },
        "intl_risk": {"em_stress_state": "strained", "two_tier_state": "contained"},
        "context_risk": {"available": True},
        "produced_at": "2026-07-21T00:00:00Z",
    }
    (root / "data" / "neuralweb" / "world_state.json").write_text(
        json.dumps(world_state), encoding="utf-8")

    return root


def _with_nightly_lane():
    """Context manager-ish helper: returns the saved COLLECT_LANE value so
    callers can restore it. Use as:
        env_save = _with_nightly_lane()
        try: ...
        finally: os.environ["COLLECT_LANE"] = env_save
    """
    env_save = os.environ.get("COLLECT_LANE", "")
    os.environ["COLLECT_LANE"] = "nightly"
    return env_save


# ---------------------------------------------------------------------------
# (a) determinism: build twice -> events.jsonl byte-identical
# ---------------------------------------------------------------------------

def test_build_twice_byte_identical(tmp_path):
    from engine.chronicle.governor import build_and_write
    root = _make_fixture_root(tmp_path)

    r1 = build_and_write(root=root, rebuild=True)
    assert not r1.get("error"), r1
    bytes1 = Path(r1["events_path"]).read_bytes()

    r2 = build_and_write(root=root, rebuild=True)
    assert not r2.get("error"), r2
    bytes2 = Path(r2["events_path"]).read_bytes()

    assert bytes1 == bytes2, "events.jsonl not byte-identical across two --rebuild runs"
    assert bytes1, "events.jsonl unexpectedly empty on the fixture root"


# ---------------------------------------------------------------------------
# (b) idempotency: re-run adds zero duplicates
# ---------------------------------------------------------------------------

def test_rerun_adds_zero_duplicates(tmp_path):
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.spine import load_events_jsonl
    root = _make_fixture_root(tmp_path)
    events_path = root / "data" / "chronicle" / "events.jsonl"

    build_and_write(root=root, rebuild=True)
    events1 = load_events_jsonl(events_path)
    build_and_write(root=root, rebuild=True)
    events2 = load_events_jsonl(events_path)

    ids1 = [e["id"] for e in events1]
    ids2 = [e["id"] for e in events2]
    assert len(ids1) == len(set(ids1)), "duplicate ids after the first run"
    assert ids1 == ids2, "event id set changed on a no-op re-run"


def test_incremental_second_run_added_zero(tmp_path):
    """The governor's own added-count must read 0 on a same-source-date
    incremental re-run. m1: explicit now= (not the real clock) on BOTH calls
    so this is deterministic regardless of when the suite runs; COLLECT_LANE
    is armed so state_log capture genuinely exercises its idempotency path
    rather than being blocked by the B2 lane gate."""
    from engine.chronicle.governor import build_and_write
    root = _make_fixture_root(tmp_path)
    now = datetime(2026, 7, 25, 3, 0, 0, tzinfo=timezone.utc)

    env_save = _with_nightly_lane()
    try:
        r1 = build_and_write(root=root, rebuild=False, now=now)
        assert r1["added"] == r1["total_events"] == 5
        r2 = build_and_write(root=root, rebuild=False, now=now)
        assert r2["added"] == 0
        assert r2["state_appended"] is False  # same SOURCE as-of -> idempotent, no 2nd baseline row
    finally:
        os.environ["COLLECT_LANE"] = env_save


# ---------------------------------------------------------------------------
# (c) schema / public-safe: keys exact, facts <=200 chars, exact per-adapter
#     census (B4)
# ---------------------------------------------------------------------------

def test_every_event_matches_schema_exactly(tmp_path):
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.spine import load_events_jsonl
    from engine.chronicle.schema import EVENT_FIELDS, FACT_MAX_LEN, validate_event
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)
    events = load_events_jsonl(root / "data" / "chronicle" / "events.jsonl")
    assert len(events) == 5, "fixture must produce exactly 5 baseline events"
    for e in events:
        assert set(e.keys()) == set(EVENT_FIELDS), (
            f"event {e.get('id')} keys != schema: {set(e.keys()) ^ set(EVENT_FIELDS)}"
        )
        problems = validate_event(e)
        assert not problems, f"event {e.get('id')} schema problems: {problems}"
        for f in e["facts"]:
            assert len(f) <= FACT_MAX_LEN


def test_real_repo_events_pass_schema():
    """Belt-and-braces: whatever is actually seeded in the committed store must
    also be schema-clean (catches adapter bugs the synthetic fixture can't).

    m2: skip ONLY when the committed file is genuinely absent — a present-but-
    empty store (a real regression: the build ran and wrote nothing) used to
    pass this same skip condition and vanish from CI's view entirely. Once we
    know the file exists, assert a non-trivial floor so an emptied store is a
    hard failure, not silence.
    """
    from engine.chronicle.spine import load_events_jsonl
    from engine.chronicle.schema import EVENT_FIELDS, FACT_MAX_LEN, validate_event
    path = ROOT / "data" / "chronicle" / "events.jsonl"
    if not path.exists():
        pytest.skip("no committed data/chronicle/events.jsonl in this checkout")
    events = load_events_jsonl(path)
    assert len(events) >= 50, (
        f"committed data/chronicle/events.jsonl has only {len(events)} events — "
        "a near-empty seeded store is a regression, not a legitimate accrual state"
    )
    for e in events:
        assert set(e.keys()) == set(EVENT_FIELDS)
        assert not validate_event(e)
        for f in e["facts"]:
            assert len(f) <= FACT_MAX_LEN


def test_per_adapter_exact_event_counts(tmp_path):
    """B4: every adapter must independently prove non-zero, EXACT output on
    the seeded fixture. Pre-fix, 3 of 4 adapters could silently emit zero
    events while every other assertion in this suite stayed green — one
    surviving vault event satisfied the entire suite. That must never
    recur: this test fails the moment any adapter's count drifts from its
    exact expected value, in either direction."""
    from engine.chronicle.governor import build_and_write
    root = _make_fixture_root(tmp_path)
    result = build_and_write(root=root, rebuild=True)
    assert not result.get("error"), result
    report = result["adapter_report"]

    counts = {name: info["count"] for name, info in report.items()}
    assert counts == {
        "research_vault": 1,
        "prophet_ledger": 1,
        "macro_release": 1,
        "earnings": 1,
        "regime_flip": 0,
        "risk_band": 1,
    }, counts
    assert result["total_events"] == 5


# ---------------------------------------------------------------------------
# B1: events.jsonl is append-only — a source row leaving the snapshot must
# RETAIN its event (union-merge), not silently delete it
# ---------------------------------------------------------------------------

def test_source_row_removed_retains_event_and_records_drop(tmp_path):
    """Reproduces the reviewer's exact finding: seed a fixture, build, delete
    a source row, rebuild -> the event the deleted row produced must still be
    present in events.jsonl AND the manifest must record the drop (both in
    the per-adapter report and as a manifest gap note)."""
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.spine import load_events_jsonl
    root = _make_fixture_root(tmp_path)

    r1 = build_and_write(root=root, rebuild=True)
    assert not r1.get("error"), r1
    events_path = root / "data" / "chronicle" / "events.jsonl"
    events1 = load_events_jsonl(events_path)
    vault_ids_before = {e["id"] for e in events1 if e["source"] == "research_vault"}
    assert vault_ids_before, "fixture must seed at least one vault event"

    # The source row leaves the current snapshot (vault catalog drops the item
    # by id — exactly the reviewer-verified real-world trigger).
    catalog_path = root / "data" / "research_vault" / "catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["items"] = []
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    r2 = build_and_write(root=root, rebuild=True)
    assert not r2.get("error"), r2
    events2 = load_events_jsonl(events_path)
    vault_ids_after = {e["id"] for e in events2 if e["source"] == "research_vault"}
    assert vault_ids_after == vault_ids_before, (
        "an event was silently deleted when its source row left the snapshot — "
        "events.jsonl must be append-only"
    )

    assert r2["adapter_report"]["research_vault"]["dropped_from_source"] == 1
    manifest = json.loads(Path(r2["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["adapters"]["research_vault"]["dropped_from_source"] == 1
    assert any("research_vault" in n and "retained" in n for n in manifest["gap_notes"]), (
        manifest["gap_notes"]
    )


# ---------------------------------------------------------------------------
# (d) pack(): budget, coverage note, as_of, matching, facts rendering
# ---------------------------------------------------------------------------

def test_pack_respects_budget_and_coverage(tmp_path):
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.context_pack import pack
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)

    result = pack(topics=["semis"], token_budget=3000, root=root)
    assert len(result["lines"]) == 1, "expected exactly the one 'semis' vault event"
    for line in result["lines"]:
        assert line["source_ref"]
    assert result["narratives"] == []
    assert result["coverage"]["note"]
    assert isinstance(result["budget_used"], int)
    assert result["budget_used"] <= 3000

    tiny = pack(topics=["semis"], token_budget=1, root=root)
    assert tiny["budget_used"] <= 5  # near-zero budget admits ~nothing
    assert tiny["lines"] == []


def test_pack_as_of_far_past_is_empty_with_reason(tmp_path):
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.context_pack import pack
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)

    result = pack(as_of="2000-01-01", window="1w", root=root)
    assert result["lines"] == []
    assert "predates" in result["coverage"]["note"] or "2000-01-01" in result["coverage"]["note"]


def test_pack_empty_store_is_honest(tmp_path):
    from engine.chronicle.context_pack import pack
    result = pack(root=tmp_path)
    assert result["lines"] == []
    assert result["narratives"] == []
    assert result["coverage"] == {"start": None, "end": None,
                                   "note": "chronicle store is empty — no events have accrued yet"}


def test_pack_as_of_hard_right_edge_excludes_future_events(tmp_path):
    """B3: as_of must be a HARD RIGHT EDGE by default — a PIT query (e.g. a
    vault-W6 as_of join) must never see events dated after as_of. Pre-fix,
    the symmetric +-7d window leaked the prophet close (07-15) and the vault
    report (07-20) into an as_of=07-14 query."""
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.context_pack import pack
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)

    result = pack(as_of="2026-07-14", token_budget=100000, root=root)
    assert result["lines"], "expected events within the backward window"
    line_dates = [ln["text"][1:11] for ln in result["lines"]]
    assert all(d <= "2026-07-14" for d in line_dates), (
        f"pack() leaked a future event past as_of: {line_dates}"
    )
    assert "2026-07-15" not in line_dates  # prophet close -- 1 day AFTER as_of
    assert "2026-07-20" not in line_dates  # vault report -- 6 days AFTER as_of


def test_pack_as_of_window_forward_opt_in_still_expressible(tmp_path):
    """B3: the masterplan's own §0 gate-3(c) '+-1w' query remains expressible
    via the explicit window_forward opt-in -- the fix narrows the DEFAULT,
    it does not remove the capability."""
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.context_pack import pack
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)

    result = pack(as_of="2026-07-14", window="1w", window_forward="1w",
                   token_budget=100000, root=root)
    line_dates = [ln["text"][1:11] for ln in result["lines"]]
    assert "2026-07-15" in line_dates  # now inside the explicit forward window


def test_pack_malformed_as_of_is_fail_soft(tmp_path):
    """M11: an unguarded strptime used to raise straight out of pack() — the
    one API every consumer binds, while every other Chronicle entry point is
    never-raise. Must degrade to the empty-with-reason contract instead."""
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.context_pack import pack
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)

    result = pack(as_of="not-a-date", root=root)  # must not raise
    assert result["lines"] == []
    assert "not-a-date" in result["coverage"]["note"]


def test_pack_empty_filter_result_says_why(tmp_path):
    """Honest-null law: a query whose FILTER matched nothing must say so.

    Reporting only the coverage window implies the store was the limit, which
    reads as "we have no history here" when the truth is "your topic matched no
    event" — the exact failure the review found on the commissioned gate-3(a)
    query (0 lines, note asserting full coverage, no reason given).
    """
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.context_pack import pack
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)

    hit = pack(root=root)
    assert hit["lines"], "fixture should yield events unfiltered"

    miss = pack(topics=["zzz-no-such-topic"], root=root)
    assert miss["lines"] == []
    note = miss["coverage"]["note"]
    # names the filter, the store size, and does NOT merely state coverage
    assert "zzz-no-such-topic" in note
    assert "matched" in note
    assert str(len(hit["lines"])) or "0 of" in note
    assert note != f"chronicle coverage {miss['coverage']['start']}..{miss['coverage']['end']}"


def test_pack_macro_release_line_carries_its_numbers(tmp_path):
    """M4: pack() used to discard `facts` entirely -- lines were date+title
    only, so a generic title like 'Macro print: claims (...)' shipped
    contentless. The rendered line must carry real numbers."""
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.context_pack import pack
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)

    result = pack(topics=["claims"], token_budget=3000, root=root)
    assert result["lines"], "expected the macro_release event to surface"
    line_text = result["lines"][0]["text"]
    assert "claims" in line_text.lower()
    assert any(ch.isdigit() for ch in line_text), (
        f"pack line carries no numbers -- facts were discarded: {line_text!r}"
    )


def test_pack_discloses_budget_evicted_count(tmp_path):
    """m5: pack() silently dropped budget-evicted lines with no disclosure,
    while rollups DO disclose trimming. A near-zero budget must evict
    matching lines AND say so in coverage.note."""
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.context_pack import pack
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)

    full = pack(token_budget=100000, root=root)
    n_total = len(full["lines"])
    assert n_total >= 2, "fixture must seed multiple short/medium events"

    tiny = pack(token_budget=20, root=root)
    assert len(tiny["lines"]) < n_total
    assert "omitted" in tiny["coverage"]["note"], tiny["coverage"]["note"]


def test_topic_word_boundary_excludes_substring_match(tmp_path):
    """M7: matching must be word-boundary, not a bare substring search.
    'position' is a substring of the vault event's title ('...positioning
    stretched') but must NOT match — 'positioning' continues past the word
    boundary that would end 'position'."""
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.context_pack import pack
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)

    result = pack(topics=["position"], token_budget=3000, root=root)
    assert result["lines"] == []


def test_theme_matches_when_title_lacks_topic_word(tmp_path):
    """M6/M7: pack() must match on themes (exact set membership), not just a
    title substring -- an event whose tags carry a topic the title text never
    mentions must still surface for that topic query. This is what makes
    §0 gate 3(a) ('what changed for semis') answerable once real tag data
    exists, instead of degenerating to a title-substring search."""
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.context_pack import pack
    root = tmp_path
    (root / "data" / "research_vault").mkdir(parents=True)
    catalog = {
        "schema": "research_vault.catalog.v1", "generated_at": "2026-07-20T00:00:00Z",
        "count": 1, "institutions": ["Test Bank"],
        "items": [{
            "id": "test-item-tagged", "title": "Quarterly outlook note",
            "institution": "Test Bank", "side": "independent", "desk": "",
            "published_at": "2026-07-20T14:00:00Z",
            "summary_points": ["General market commentary."],
            "tags": ["hedge-funds"], "tickers": [], "top_pick": False,
            "pages": 3, "needs_metadata": False,
        }],
    }
    (root / "data" / "research_vault" / "catalog.json").write_text(
        json.dumps(catalog), encoding="utf-8")

    build_and_write(root=root, rebuild=True)

    result = pack(topics=["hedge-funds"], token_budget=3000, root=root)
    assert result["lines"], "expected the tagged event to surface via themes"
    assert "hedge-funds" not in result["lines"][0]["text"].lower()  # title truly lacks the word


# ---------------------------------------------------------------------------
# (e) adapter fail-soft: missing/corrupt fixture root -> gap note, no raise
# ---------------------------------------------------------------------------

def test_adapters_fail_soft_on_missing_sources(tmp_path):
    from engine.chronicle.governor import build_and_write
    result = build_and_write(root=tmp_path, rebuild=True)
    assert not result.get("error"), "governor must never raise on an empty fixture root"
    report = result["adapter_report"]
    for name in ("research_vault", "prophet_ledger", "macro_release", "risk_band"):
        assert report[name]["count"] == 0
        assert report[name]["gap"], f"{name} should carry a gap note on an absent source"
    assert report["earnings"]["count"] == 0
    assert report["earnings"]["gap"]  # earnings always carries an honest coverage note


def test_adapter_corrupt_source_is_gap_not_raise(tmp_path):
    from engine.chronicle.governor import build_and_write
    root = _make_fixture_root(tmp_path)
    (root / "data" / "research_vault" / "catalog.json").write_text(
        "{not valid json", encoding="utf-8")
    result = build_and_write(root=root, rebuild=True)
    assert not result.get("error")
    assert result["adapter_report"]["research_vault"]["gap"]
    assert result["adapter_report"]["research_vault"]["count"] == 0


# ---------------------------------------------------------------------------
# (f) state_log flip derivation
# ---------------------------------------------------------------------------

def test_flip_derivation_single_change_single_event():
    from engine.chronicle.state_log import derive_flip_events
    rows = [
        {"date": "2026-07-20", "captured_at": "2026-07-20T03:00:00Z",
         "regimes": {"us": {"quad": "Q1", "quad_name": "Goldilocks", "cycle_tag": "mid"}},
         "risk": {"intl": "calm"}},
        {"date": "2026-07-21", "captured_at": "2026-07-21T03:00:00Z",
         "regimes": {"us": {"quad": "Q2", "quad_name": "Reflation", "cycle_tag": "mid"}},
         "risk": {"intl": "calm"}},
    ]
    events = derive_flip_events(rows)
    assert len(events) == 1
    assert events[0]["source"] == "regime_flip"
    assert events[0]["kind"] == "state_flip"
    assert "Goldilocks" in events[0]["title"] and "Reflation" in events[0]["title"]
    assert events[0]["weight_hint"] == 3
    assert events[0]["date"] == "2026-07-21"


def test_flip_derivation_first_run_zero_events():
    from engine.chronicle.state_log import derive_flip_events
    rows = [{"date": "2026-07-20", "captured_at": "2026-07-20T03:00:00Z",
             "regimes": {"us": {"quad": "Q1", "quad_name": "Goldilocks", "cycle_tag": "mid"}},
             "risk": {}}]
    assert derive_flip_events(rows) == []
    assert derive_flip_events([]) == []


def test_flip_derivation_unchanged_rows_zero_events():
    from engine.chronicle.state_log import derive_flip_events
    row = {"date": "2026-07-20", "regimes": {"us": {"quad": "Q1", "quad_name": "Goldilocks",
           "cycle_tag": "mid"}}, "risk": {"intl": "calm"}}
    row2 = dict(row, date="2026-07-21")
    assert derive_flip_events([row, row2]) == []


def test_flip_derivation_gap_night_defers_not_resets():
    """M2: comparison used to be against the immediately-preceding row only,
    so Goldilocks -> (market absent) -> Reflation yielded ZERO flips. The gap
    night must DEFER the comparison, not reset it — the flip still fires,
    landing on the row where the new label actually appears."""
    from engine.chronicle.state_log import derive_flip_events
    rows = [
        {"date": "2026-07-20", "regimes": {"us": {"quad": "Q1", "quad_name": "Goldilocks", "cycle_tag": "mid"}}},
        {"date": "2026-07-21", "regimes": {}},  # gap night -- market absent (e.g. cancelled engine run)
        {"date": "2026-07-22", "regimes": {"us": {"quad": "Q2", "quad_name": "Reflation", "cycle_tag": "mid"}}},
    ]
    events = derive_flip_events(rows)
    assert len(events) == 1
    assert events[0]["source"] == "regime_flip"
    assert "Goldilocks" in events[0]["title"] and "Reflation" in events[0]["title"]
    assert events[0]["date"] == "2026-07-22"


def test_flip_derivation_market_disappears_no_flip():
    from engine.chronicle.state_log import derive_flip_events
    rows = [
        {"date": "2026-07-20", "regimes": {"us": {"quad": "Q1", "quad_name": "Goldilocks", "cycle_tag": "mid"}}},
        {"date": "2026-07-21", "regimes": {}},  # market drops out and never reappears
    ]
    assert derive_flip_events(rows) == []


def test_flip_derivation_market_reappears_same_label_no_flip():
    from engine.chronicle.state_log import derive_flip_events
    rows = [
        {"date": "2026-07-20", "regimes": {"us": {"quad": "Q1", "quad_name": "Goldilocks", "cycle_tag": "mid"}}},
        {"date": "2026-07-21", "regimes": {}},
        {"date": "2026-07-22", "regimes": {"us": {"quad": "Q1", "quad_name": "Goldilocks", "cycle_tag": "mid"}}},
    ]
    assert derive_flip_events(rows) == []


def test_risk_band_adapter_state_flip_on_change(tmp_path):
    """B6: risk_band moved OUT of state_log/derive_flip_events entirely -- it
    now reads the real committed data/risk_radar/forward_log.jsonl history.
    derive_flip_events must NEVER emit a risk_band-sourced event any more
    (regression guard for the old, wrong construction)."""
    from engine.chronicle.adapters import adapt_risk_band
    from engine.chronicle.state_log import derive_flip_events

    root = tmp_path
    (root / "data" / "risk_radar").mkdir(parents=True)
    rows = [
        {"asof": "2026-07-20", "state": "calm", "dominant_scare": "growth", "top_score": 25.0},
        {"asof": "2026-07-21", "state": "strained", "dominant_scare": "credit", "top_score": 71.4},
    ]
    (root / "data" / "risk_radar" / "forward_log.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    events, gap = adapt_risk_band(root)
    assert len(events) == 1
    ev = events[0]
    assert ev["source"] == "risk_band"
    assert ev["kind"] == "state_flip"
    assert ev["weight_hint"] == 2
    assert ev["date"] == "2026-07-21"
    assert "calm" in ev["title"] and "strained" in ev["title"]
    assert any("credit" in f for f in ev["facts"])

    # regime_flip's own state_log rows carrying a `risk` key must never
    # produce a risk_band event any more -- that path is fully removed.
    state_log_rows = [
        {"date": "2026-07-20", "regimes": {}, "risk": {"intl": "calm"}},
        {"date": "2026-07-21", "regimes": {}, "risk": {"intl": "strained"}},
    ]
    assert derive_flip_events(state_log_rows) == []


def test_append_row_if_new_idempotent_same_day(tmp_path):
    from engine.chronicle import state_log
    root = _make_fixture_root(tmp_path)
    now = datetime(2026, 7, 25, 3, 0, 0, tzinfo=timezone.utc)

    env_save = _with_nightly_lane()
    try:
        appended1, gap1 = state_log.append_row_if_new(root, now=now)
        assert appended1 is True
        assert gap1 is None
        appended2, gap2 = state_log.append_row_if_new(root, now=now)
        assert appended2 is False
    finally:
        os.environ["COLLECT_LANE"] = env_save
    rows = state_log.read_state_log(root)
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-07-20"  # M1: source as-of (global_regimes.us.date), not `now`


def test_append_row_if_new_requires_nightly_lane(tmp_path):
    """B2: the write path must no-op with an honest gap note when
    COLLECT_LANE is absent/not nightly -- house law: nightly is the sole
    advancer of forward ledgers; intraday lanes discard writes."""
    from engine.chronicle import state_log
    root = _make_fixture_root(tmp_path)
    now = datetime(2026, 7, 25, 3, 0, 0, tzinfo=timezone.utc)

    env_save = os.environ.get("COLLECT_LANE", "")
    try:
        os.environ.pop("COLLECT_LANE", None)
        appended, gap = state_log.append_row_if_new(root, now=now)
        assert appended is False
        assert gap and "nightly" in gap
        assert state_log.read_state_log(root) == []

        os.environ["COLLECT_LANE"] = "render"  # any non-nightly value
        appended2, gap2 = state_log.append_row_if_new(root, now=now)
        assert appended2 is False
        assert gap2 and "nightly" in gap2
    finally:
        os.environ["COLLECT_LANE"] = env_save


def test_capture_row_absent_world_state_is_gap(tmp_path):
    from engine.chronicle import state_log
    row, gap = state_log.capture_row(tmp_path)
    assert row is None
    assert gap and "world_state.json" in gap


def test_state_log_seam_production_path_derives_flip(tmp_path):
    """B5: the 4 hand-built-row flip tests never exercise capture_row — the
    only thing that produces those rows in production. This seam test writes
    two REAL world_state.json snapshots into a tmp root, captures each via
    append_row_if_new (the actual production call path), reads them back, and
    derives flips -- and separately asserts capture_row's own returned dict
    content against the fixture, not merely that a row appended."""
    from engine.chronicle import state_log
    root = _make_fixture_root(tmp_path)

    env_save = _with_nightly_lane()
    try:
        now1 = datetime(2026, 7, 20, 3, 0, 0, tzinfo=timezone.utc)
        appended1, gap1 = state_log.append_row_if_new(root, now=now1)
        assert appended1 is True
        assert gap1 is None

        ws_path = root / "data" / "neuralweb" / "world_state.json"
        ws = json.loads(ws_path.read_text(encoding="utf-8"))
        ws["global_regimes"]["us"] = {
            "market": "us", "date": "2026-07-21", "quad": "Q2",
            "quad_name": "Reflation", "cycle_tag": "mid",
        }
        ws_path.write_text(json.dumps(ws), encoding="utf-8")

        now2 = datetime(2026, 7, 21, 3, 0, 0, tzinfo=timezone.utc)
        appended2, gap2 = state_log.append_row_if_new(root, now=now2)
        assert appended2 is True
        assert gap2 is None
    finally:
        os.environ["COLLECT_LANE"] = env_save

    rows = state_log.read_state_log(root)
    assert len(rows) == 2

    events = state_log.derive_flip_events(rows)
    regime_events = [e for e in events if e["source"] == "regime_flip"]
    assert len(regime_events) == 1
    assert regime_events[0]["title"] == "US regime: Q1 Goldilocks → Q2 Reflation"
    assert regime_events[0]["date"] == "2026-07-21"

    row2, gap = state_log.capture_row(root, now=now2)
    assert gap is None
    assert row2["regimes"]["us"]["quad_name"] == "Reflation"
    assert row2["date"] == "2026-07-21"


def test_read_state_log_dedupes_duplicate_dates_keeps_latest(tmp_path):
    """m6: a duplicate-date pair (a retried nightly, a hand-edited ledger)
    must never fabricate a spurious flip pair -- read_state_log dedupes by
    date, keeping the row with the latest captured_at, before anything else
    ever sees the rows."""
    from engine.chronicle import state_log
    root = tmp_path
    (root / "data" / "chronicle").mkdir(parents=True)
    rows = [
        {"date": "2026-07-20", "captured_at": "2026-07-20T03:00:00Z",
         "regimes": {"us": {"quad": "Q1", "quad_name": "Goldilocks", "cycle_tag": "mid"}}, "risk": {}},
        {"date": "2026-07-20", "captured_at": "2026-07-20T09:00:00Z",  # later capture, same date (a retry)
         "regimes": {"us": {"quad": "Q2", "quad_name": "Reflation", "cycle_tag": "mid"}}, "risk": {}},
    ]
    path = root / "data" / "chronicle" / "state_log.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    read = state_log.read_state_log(root)
    assert len(read) == 1
    assert read[0]["captured_at"] == "2026-07-20T09:00:00Z"
    assert read[0]["regimes"]["us"]["quad_name"] == "Reflation"


# ---------------------------------------------------------------------------
# (g) manifest carries envelope keys + correct row counts + honest gap notes
# ---------------------------------------------------------------------------

def test_manifest_envelope_and_row_counts(tmp_path):
    from engine.chronicle.governor import build_and_write
    root = _make_fixture_root(tmp_path)
    (root / "data" / "earnings" / "earnings.parquet").unlink()  # m12: deliberately-absent source

    env_save = _with_nightly_lane()
    try:
        now = datetime(2026, 7, 25, 3, 0, 0, tzinfo=timezone.utc)  # m1: explicit now=
        result = build_and_write(root=root, rebuild=False, now=now)
    finally:
        os.environ["COLLECT_LANE"] = env_save
    assert not result.get("error"), result
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))

    for k in ("schema_version", "produced_by", "produced_at", "inputs_hash", "tier"):
        assert k in manifest, f"manifest missing envelope key: {k}"
    assert manifest["schema"] == "chronicle.manifest/v1"

    events_path = root / "data" / "chronicle" / "events.jsonl"
    n_lines = sum(1 for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip())
    assert manifest["ledgers"]["events"]["rows"] == n_lines
    assert manifest["ledgers"]["events"]["sha256"]
    assert manifest["ledgers"]["state_log"]["rows"] == 1  # baseline row just appended
    assert manifest["ledgers"]["state_log"]["present"] is True

    # m12: a deliberately-absent source must produce a matching, honest gap
    # note on the manifest's gap_notes surface (not just the per-adapter report).
    assert any("earnings" in n and "absent" in n for n in manifest["gap_notes"]), manifest["gap_notes"]


# ---------------------------------------------------------------------------
# (h) mastermind summarizer: ok-shaped on seeded store, fail-soft on bare root
# ---------------------------------------------------------------------------

def test_mastermind_summarizer_seeded(tmp_path):
    from engine.chronicle.governor import build_and_write
    from engine.neuralweb.mastermind_context import _summarize_chronicle
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)

    lobe, gap = _summarize_chronicle(root)
    assert gap is None
    assert lobe["is_context_only"] is True
    assert lobe["display_only"] is True
    assert lobe["narratives"] == []
    assert isinstance(lobe["recent"], list) and lobe["recent"]
    assert lobe["recent"][0]["title"]
    # m4: recent is salience-ordered (-weight_hint, date, id), not just
    # (date, id) -- the fixture's top_pick vault event (weight 3) must lead
    # even though it is not the most recent date (risk_band, 07-18, is).
    assert lobe["recent"][0]["title"] == "Test Bank: Semis positioning stretched"


def test_mastermind_summarizer_bare_root_fail_soft(tmp_path):
    from engine.neuralweb.mastermind_context import _summarize_chronicle
    lobe, gap = _summarize_chronicle(tmp_path)
    assert gap  # honest gap note, never a raise
    assert lobe == {}


def test_mastermind_registration_points():
    """The 3 required registration points (masterplan §0 gate 6)."""
    import engine.neuralweb.mastermind_context as mc
    assert "chronicle" in mc.LOBE_SUMMARIZERS
    assert mc.LOBE_SUMMARIZERS["chronicle"] is mc._summarize_chronicle
    assert mc._LOBE_TO_ARTIFACT_IDS.get("chronicle") == ["chronicle-events", "chronicle-manifest"]

    # m3: the THIRD registration point (source_artifacts) was asserted nowhere.
    payload = mc.build_context(root=Path("/tmp/does-not-need-to-exist-for-this-literal-list"))
    assert "data/chronicle/events.jsonl" in payload["source_artifacts"]


# ---------------------------------------------------------------------------
# Admin inspector — read-only, fail-soft (mirrors tests/test_admin_marketing.py)
# ---------------------------------------------------------------------------

def test_admin_overview_seeded(tmp_path):
    from engine.chronicle.governor import build_and_write
    from admin import chronicle as admin_chronicle
    root = _make_fixture_root(tmp_path)

    env_save = _with_nightly_lane()
    try:
        now = datetime(2026, 7, 25, 3, 0, 0, tzinfo=timezone.utc)  # m1: explicit now=
        build_and_write(root=root, rebuild=False, now=now)
    finally:
        os.environ["COLLECT_LANE"] = env_save

    result = admin_chronicle.overview(root=root)
    assert result["ok"] is True
    assert result["manifest"] is not None
    assert result["total_events"] == 5
    assert len(result["recent_events"]) == 5
    assert len(result["state_log_tail"]) == 1
    assert result["adapters"]["research_vault"]["count"] == 1


def test_admin_overview_bare_root_is_honest_accruing(tmp_path):
    from admin import chronicle as admin_chronicle
    result = admin_chronicle.overview(root=tmp_path)
    assert result["ok"] is True  # never ok:False on an absent-but-readable root
    assert result["manifest"] is None
    assert result["note"]
    assert result["recent_events"] == []
    assert result["state_log_tail"] == []


# ---------------------------------------------------------------------------
# M8: vault events carry a real links.site
# ---------------------------------------------------------------------------

def test_vault_event_carries_site_link(tmp_path):
    from engine.chronicle.governor import build_and_write
    from engine.chronicle.spine import load_events_jsonl
    root = _make_fixture_root(tmp_path)
    build_and_write(root=root, rebuild=True)
    events = load_events_jsonl(root / "data" / "chronicle" / "events.jsonl")
    vault_events = [e for e in events if e["source"] == "research_vault"]
    assert vault_events
    assert any(e["links"]["site"] for e in vault_events), (
        "expected at least one vault event with a non-null links.site"
    )
    site = next(e["links"]["site"] for e in vault_events if e["links"]["site"])
    assert site.startswith("/research/") and site.endswith(".html")


# ---------------------------------------------------------------------------
# M3: Prophet BEAR close sign fix
# ---------------------------------------------------------------------------

def test_prophet_bear_close_sign_adjusted_to_plan_result(tmp_path):
    """stock_result_pct is a RAW price-direction move computed the same way
    for BULL and BEAR (scripts/build_prophet.py). A BEAR plan that hits its
    target on a price DECLINE must render as a WIN (+), not a loss (-)."""
    from engine.chronicle.adapters import adapt_prophet_ledger
    root = tmp_path
    (root / "data" / "prophet").mkdir(parents=True)
    row = {
        "schema": "prophet.ledger/v1", "id": "TST-BEAR-20260601", "asset": "XYZ",
        "direction": "BEAR", "signal_date": "2026-06-01", "close_date": "2026-06-20",
        "outcome": "T1_HIT",
        "stock_result_pct": -8.3,  # raw price move: price FELL 8.3% -- a WIN for a BEAR plan
        "option_result_pct": None, "days_held": 19, "plan_adherence": "test row",
        "asof": "2026-06-20",
    }
    (root / "data" / "prophet" / "ledger.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    events, gap = adapt_prophet_ledger(root)
    assert len(events) == 1
    ev = events[0]
    assert "+8.3%" in ev["title"], ev["title"]
    assert "-8.3%" not in ev["title"]
    assert any("+8.30%" in f for f in ev["facts"]), ev["facts"]


def test_prophet_bull_close_sign_unchanged(tmp_path):
    """Guard: BULL plans must NOT be sign-flipped -- only BEAR gets adjusted."""
    from engine.chronicle.adapters import adapt_prophet_ledger
    root = tmp_path
    (root / "data" / "prophet").mkdir(parents=True)
    row = {
        "schema": "prophet.ledger/v1", "id": "TST-BULL-20260601", "asset": "ABC",
        "direction": "BULL", "signal_date": "2026-06-01", "close_date": "2026-06-20",
        "outcome": "T1_HIT", "stock_result_pct": 6.1, "option_result_pct": None,
        "days_held": 19, "plan_adherence": "test row", "asof": "2026-06-20",
    }
    (root / "data" / "prophet" / "ledger.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")

    events, gap = adapt_prophet_ledger(root)
    assert "+6.1%" in events[0]["title"]


# ---------------------------------------------------------------------------
# m7: macro_release joins the scored actual print
# ---------------------------------------------------------------------------

def test_macro_release_joins_scored_actual_print(tmp_path):
    from engine.chronicle.adapters import adapt_macro_release
    root = tmp_path
    (root / "data" / "release_forecast").mkdir(parents=True)
    rows = [
        {"schema": 2, "row_type": "scored", "release": "cpi_headline", "release_date": "2026-07-14",
         "actual": -0.42, "raw_initial_print": -0.42, "interval_hit": False},  # grade field must NOT leak
        {"schema": 2, "row_type": "reaction", "release": "cpi_headline", "release_date": "2026-07-14",
         "spy_h0_pct": 0.8},
    ]
    path = root / "data" / "release_forecast" / "forward_ledger.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    events, gap = adapt_macro_release(root)
    assert len(events) == 1
    ev = events[0]
    assert "-0.42" in ev["title"]
    assert any("actual -0.42" in f for f in ev["facts"])
    assert "interval_hit" not in json.dumps(ev)  # grade fields excluded from the public-safe projection
    assert gap and "1/1" in gap


def test_macro_release_no_scored_match_falls_back_generic(tmp_path):
    from engine.chronicle.adapters import adapt_macro_release
    root = tmp_path
    (root / "data" / "release_forecast").mkdir(parents=True)
    row = {"schema": 2, "row_type": "reaction", "release": "claims", "release_date": "2026-07-09",
           "spy_h0_pct": 0.3}
    path = root / "data" / "release_forecast" / "forward_ledger.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    events, gap = adapt_macro_release(root)
    assert len(events) == 1
    assert events[0]["title"] == "Macro print: claims (2026-07-09)"
    assert gap and "0/1" in gap


# ---------------------------------------------------------------------------
# M5: fact truncation never mutates numbers / mid-word
# ---------------------------------------------------------------------------

def test_truncate_fact_never_cuts_mid_number_or_mid_word():
    from engine.chronicle.schema import truncate_fact, FACT_MAX_LEN
    fact = ("Quarterly positioning update from the desk: fund flows accelerated broadly "
            "across the book this week, with hedge fund net exposure climbing to a "
            "reading of 123456.789 percent of NAV, the highest print recorded since "
            "the program began tracking this series many quarters ago")
    assert len(fact) > FACT_MAX_LEN
    out = truncate_fact(fact)
    assert out is not None  # plenty of safe word boundary before the cap
    assert out.endswith("…")
    core = out[:-1].rstrip()
    assert not core[-1].isdigit()  # never ends mid-number
    last_token = core.rsplit(" ", 1)[-1]
    assert not any(ch.isdigit() for ch in last_token)  # no trailing digit-bearing token at all
    assert fact.startswith(core.rstrip(",;:·—- "))  # still a true PREFIX (word-boundary cut, never rewritten)


def test_truncate_fact_too_short_after_truncation_drops_to_none():
    from engine.chronicle.schema import truncate_fact
    out = truncate_fact("x" * 250)  # one giant token, no safe word boundary at all
    assert out is None


def test_truncate_fact_short_text_passes_through_unchanged():
    from engine.chronicle.schema import truncate_fact
    assert truncate_fact("stock +12.34%") == "stock +12.34%"
    assert truncate_fact("") == ""
    assert truncate_fact(None) == ""


# ---------------------------------------------------------------------------
# M12: rollups.py — direct tests (previously exercised only incidentally)
# ---------------------------------------------------------------------------

def _mk_ev(id_, date, source="research_vault", kind="report", title="T", weight=1, themes=None):
    return {
        "id": id_, "ts": f"{date}T00:00:00Z", "date": date, "source": source,
        "source_ref": id_, "kind": kind, "title": title, "facts": [],
        "tickers": [], "themes": themes or [], "horizon_hint": "short",
        "weight_hint": weight, "links": {"site": None, "source": None, "receipt": None},
    }


def test_build_daily_session_count_and_ordering():
    from engine.chronicle.rollups import build_daily, DAILY_MAX_SESSIONS
    dates = [f"2026-07-{d:02d}" for d in range(1, 16)]  # 15 distinct dates
    events = [_mk_ev(f"ev-{i}", d, weight=i % 3) for i, d in enumerate(dates)]
    as_of = dates[-1]

    doc = build_daily(events, as_of)
    assert len(doc["sessions"]) == DAILY_MAX_SESSIONS  # capped at 10 even though 15 dates exist
    session_dates = [s["date"] for s in doc["sessions"]]
    assert session_dates == sorted(session_dates, reverse=True)  # newest-first
    assert session_dates[0] == as_of
    assert doc["coverage"]["end"] == as_of
    assert doc["coverage"]["note"]


def test_build_daily_per_session_weight_ordering():
    from engine.chronicle.rollups import build_daily
    events = [
        _mk_ev("low", "2026-07-20", weight=1),
        _mk_ev("high", "2026-07-20", weight=3),
        _mk_ev("mid", "2026-07-20", weight=2),
    ]
    doc = build_daily(events, "2026-07-20")
    ids_in_order = [e["id"] for e in doc["sessions"][0]["events"]]
    assert ids_in_order == ["high", "mid", "low"]


def test_build_daily_trim_loop_fires_and_notes_when_over_budget():
    from engine.chronicle.rollups import build_daily, DAILY_CHAR_BUDGET
    events = [_mk_ev(f"ev-{i}", "2026-07-20", weight=1, title="X" * 500) for i in range(40)]
    doc = build_daily(events, "2026-07-20")
    assert len(json.dumps(doc, ensure_ascii=False)) <= DAILY_CHAR_BUDGET
    assert "trimmed" in doc["coverage"]["note"]


def test_build_weekly_window_and_coverage_note():
    from engine.chronicle.rollups import build_weekly, WEEKLY_MAX_WEEKS
    events = [_mk_ev("old", "2020-01-01"), _mk_ev("recent", "2026-07-20")]
    as_of = "2026-07-20"
    doc = build_weekly(events, as_of)
    assert doc["coverage"]["end"] == as_of
    assert f"up to {WEEKLY_MAX_WEEKS} ISO weeks" in doc["coverage"]["note"]
    all_ids = {e["id"] for wk in doc["weeks"] for c in wk["clusters"] for e in c["top_events"]}
    assert "old" not in all_ids  # older than the 13-week cutoff, excluded
    assert "recent" in all_ids


def test_build_weekly_trim_loop_fires_and_notes_when_over_budget():
    from engine.chronicle.rollups import build_weekly, WEEKLY_CHAR_BUDGET
    events = [
        _mk_ev(f"ev-{i}", "2026-07-20", source=f"src{i % 5}", weight=1, title="Y" * 500,
               themes=[f"theme{i % 3}"])
        for i in range(80)
    ]
    doc = build_weekly(events, "2026-07-20")
    assert len(json.dumps(doc, ensure_ascii=False)) <= WEEKLY_CHAR_BUDGET
    assert "trimmed" in doc["coverage"]["note"]


# ---------------------------------------------------------------------------
# M9: gate 1 against REAL committed sources (not just the synthetic fixture)
# ---------------------------------------------------------------------------

def test_rebuild_from_committed_sources_reproduces_committed_store():
    """Gate 1: rebuilding into a scratch root from the ACTUAL committed
    sources must reproduce data/chronicle/events.jsonl byte-for-byte. The
    existing determinism test only proved engine self-consistency on a
    synthetic fixture -- it could not have caught the stale-seed defect (19
    of 86 vault titles carrying PDF-filename garbage from before PR #3570
    landed) because it never touches the committed sources at all."""
    import shutil
    import tempfile
    from engine.chronicle.governor import build_and_write

    committed_path = ROOT / "data" / "chronicle" / "events.jsonl"
    if not committed_path.exists():
        pytest.skip("no committed data/chronicle/events.jsonl in this checkout")
    committed_bytes = committed_path.read_bytes()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        for rel in (
            "data/research_vault/catalog.json",
            "data/prophet/ledger.jsonl",
            "data/release_forecast/forward_ledger.jsonl",
            "data/earnings/earnings.parquet",
            "data/risk_radar/forward_log.jsonl",
            "data/neuralweb/world_state.json",
            "data/chronicle/state_log.jsonl",
        ):
            src = ROOT / rel
            if src.exists():
                dst = tmp_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        result = build_and_write(root=tmp_root, rebuild=True)
        assert not result.get("error"), result
        rebuilt_bytes = (tmp_root / "data" / "chronicle" / "events.jsonl").read_bytes()

    assert rebuilt_bytes == committed_bytes, (
        "rebuilding from the committed sources did not reproduce the committed "
        "events.jsonl byte-for-byte — the committed store is stale (gate 1)\n"
        + _stale_store_report(committed_bytes, rebuilt_bytes)
    )


def _stale_store_report(committed_bytes: bytes, rebuilt_bytes: bytes) -> str:
    """Explain a gate-1 failure as EVENTS, not as a byte offset.

    Raw byte-equality reports this defect as ``At index 17454 diff: b'B' != b'C'``,
    which says nothing about which event moved or what to do — and because event
    ids sort by (date, id), one inserted event shifts every later line, so a
    line-by-line read is actively misleading. This gate also fires on whoever
    happens to touch ci.yml next rather than on whoever made the store stale, so
    the message has to carry its own remedy.
    """
    def parse(raw: bytes) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for line in raw.decode("utf-8").splitlines():
            if line.strip():
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("id"):
                    out[ev["id"]] = ev
        return out

    have, want = parse(committed_bytes), parse(rebuilt_bytes)
    missing = [want[i] for i in want.keys() - have.keys()]
    extra = [have[i] for i in have.keys() - want.keys()]
    changed = [(have[i], want[i]) for i in have.keys() & want.keys() if have[i] != want[i]]

    lines = [
        f"  committed: {len(have)} events   rebuilt: {len(want)} events",
        f"  missing from the committed store: {len(missing)}",
        f"  present only in the committed store: {len(extra)}",
        f"  same id, different body: {len(changed)}",
    ]
    for ev in sorted(missing, key=lambda e: e["id"])[:5]:
        lines.append(f"    MISSING  {ev['source']}/{ev.get('source_ref')}  {ev.get('title')!r}")
    for ev in sorted(extra, key=lambda e: e["id"])[:5]:
        lines.append(f"    ORPHANED {ev['source']}/{ev.get('source_ref')}  {ev.get('title')!r}")
    for old, new in sorted(changed, key=lambda p: p[0]["id"])[:5]:
        for field in sorted(set(old) | set(new)):
            if old.get(field) != new.get(field):
                lines.append(
                    f"    CHANGED  {old['source']}/{old.get('source_ref')} .{field}:\n"
                    f"        committed={old.get(field)!r}\n"
                    f"        rebuilt  ={new.get(field)!r}"
                )
    lines.append(
        "  remedy: `python -m scripts.build_chronicle --rebuild` regenerates the "
        "derived store (events + rollups + manifest) from the committed sources; it "
        "never touches data/chronicle/state_log.jsonl (forward ledger — nightly is "
        "the sole advancer). Commit the regenerated files."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# gate 1, second tooth: the rebuild must be byte-identical ACROSS ENVIRONMENTS,
# not just across runs in one environment.
# ---------------------------------------------------------------------------

_JINJA2LESS_PROBE = '''
import json, sys
from pathlib import Path


class _Blocker:
    """Make jinja2 unimportable, exactly as a minimal-deps lane leaves it.

    ModuleNotFoundError (with ``name`` set), not a bare ImportError: that is what
    a genuinely absent module raises, and callers legitimately discriminate on it.
    """

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] == "jinja2":
            raise ModuleNotFoundError(
                "No module named %r (simulated minimal-deps lane)" % name, name=name)
        return None


sys.meta_path.insert(0, _Blocker())

try:
    import jinja2  # noqa: F401
    blocked = False
except ImportError:
    blocked = True

from engine.chronicle.adapters import adapt_research_vault

events, gap = adapt_research_vault(Path(sys.argv[1]))
print(json.dumps({
    "blocked": blocked,
    "gap": gap,
    "sites": [e["links"]["site"] for e in events],
}))
'''


def _write_vault_catalog(root: Path, items: list[dict]) -> None:
    path = root / "data" / "research_vault" / "catalog.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"items": items}), encoding="utf-8")


_SLUG_ITEMS = [
    {"id": "marketdesk-aaaaaaaaaaa-111111", "title": "Alcon Inc. (ALCC)",
     "institution": "Goldman Sachs", "published_at": "2026-07-24T09:13:00Z",
     "summary_points": ["a fact"]},
    {"id": "marketdesk-bbbbbbbbbbb-222222", "title": "Weekly - Regional View Swiss",
     "institution": "UBS", "published_at": "2026-07-24T22:06:00Z",
     "summary_points": []},
]


def test_vault_links_site_survives_a_jinja2less_lane(tmp_path):
    """links.site must NOT depend on whether jinja2 happens to be installed.

    The adapter derives each vault event's published URL with the same slug
    function the site builder uses. That function used to be imported from
    ``scripts.build_research_pages``, which does ``from jinja2 import Environment``
    at module scope — so in this suite's OWN ci.yml job (``chronicle-suite``
    installs only pytest/pandas/numpy/pyarrow/pyyaml) the import raised, the
    adapter's fail-soft swallowed it, and every vault event emitted
    ``links.site: null``.

    That made the emitted bytes a function of the ENVIRONMENT: the committed store
    (built where jinja2 exists) and a rebuild in the minimal-deps lane disagreed on
    every vault event, so gate 1 above could only ever pass in a fat environment —
    a determinism gate unsatisfiable in the lane meant to enforce it. The
    derivation now lives in the stdlib-only leaf module
    ``engine.research_vault.slugs``; this test fails if anything ever puts a
    renderer back in that import path.
    """
    import subprocess  # noqa: PLC0415
    import sys  # noqa: PLC0415

    _write_vault_catalog(tmp_path, _SLUG_ITEMS)
    proc = subprocess.run(
        [sys.executable, "-c", _JINJA2LESS_PROBE, str(tmp_path)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"probe failed: {proc.stderr}"
    payload = json.loads(proc.stdout.strip().splitlines()[-1])

    assert payload["blocked"] is True, "probe did not actually block jinja2"
    assert payload["gap"] is None, f"adapter reported a gap: {payload['gap']}"
    assert len(payload["sites"]) == len(_SLUG_ITEMS)
    assert all(s is not None for s in payload["sites"]), (
        "links.site went null with jinja2 absent — the slug derivation is importing "
        "a renderer again, so events.jsonl bytes depend on the environment "
        f"(sites={payload['sites']})"
    )
    assert payload["sites"] == [
        "/research/alcon-inc-alcc-111111.html",
        "/research/weekly-regional-view-swiss-222222.html",
    ], payload["sites"]


def test_slug_leaf_module_is_the_site_builders_own_derivation():
    """The leaf module must not FORK the published URL — it must BE it.

    A copy that drifts would silently point every chronicle event at a URL the
    site never emits, so assert the site builder re-exports this exact function
    rather than keeping a second implementation.
    """
    from engine.research_vault import slugs

    try:
        from scripts import build_research_pages as rp
    except ImportError as exc:  # noqa: BLE001
        # The whole point of the leaf module is that THIS suite's lane need not be
        # able to import the renderer. Skip rather than fail — the jinja2-less test
        # above is the one that must hold in a minimal-deps lane.
        pytest.skip(f"site builder unimportable here (expected in a minimal-deps lane): {exc}")

    assert rp.slug_map is slugs.slug_map
    assert rp._slug is slugs.report_slug
    assert rp._title is slugs.report_title
    assert slugs.slug_map(_SLUG_ITEMS) == rp.slug_map(_SLUG_ITEMS)
