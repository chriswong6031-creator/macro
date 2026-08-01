"""tests/test_marketing_fastlane.py — Marketing fast lane W0 test suite.

Test list:
1. run_tick emits an outbox item and media SVG for a valid fixture event
2. Re-running run_tick with the same events emits 0 (seen-ledger dedupe)
3. Dedupe survives a fresh run_tick call (ledger reload from disk)
4. Ineligible ticker (not in universe) is skipped with reason
5. Copy-violation event is quarantined (not emitted) with violation strings
6. daemon main() with MARKETING_FASTLANE_ENABLED unset returns 0 without ticking
7. --dry-run flag: run_tick with dry_run=True writes nothing to disk
8. wire_rank.v1 sidecar: numberless payload, position-is-rank, window-only,
   path ladder, atomicity, dry-run skip, fail-soft, kill switch
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Root resolution (same pattern as sibling test files)
# ---------------------------------------------------------------------------

def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Cannot locate repo root from {p}")


ROOT = _worktree_root()

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 7, 19, 14, 30, 0, tzinfo=timezone.utc)  # RTH session

# Universe set injected for all tests — avoids hitting sp500_heatmap.json
_UNIVERSE: set[str] = {"AAPL", "MSFT", "GOOG", "NVDA", "META"}


def _make_event(
    ticker: str = "AAPL",
    eps_actual: float = 5.89,
    eps_est: float = 5.72,
    rev_actual: float | None = 94.5e9,
    rev_est: float | None = 94.0e9,
    quarter: str | None = "Q2 2026",
    event_id: str | None = None,
) -> dict:
    """Build a minimal valid earnings event dict."""
    from engine.marketing.earnings_feed import _event_id
    if event_id is None:
        event_id = _event_id(ticker, quarter, "test")
    return {
        "id": event_id,
        "ticker": ticker.upper(),
        "when": "2026-07-19T14:30:00",
        "eps_actual": eps_actual,
        "eps_est": eps_est,
        "rev_actual": rev_actual,
        "rev_est": rev_est,
        "quarter": quarter,
        "source": "test",
    }


# ---------------------------------------------------------------------------
# 1. run_tick emits outbox item + media SVG
# ---------------------------------------------------------------------------

def test_run_tick_emits_outbox_item(tmp_path: Path) -> None:
    """A valid event with a universe-eligible ticker should produce an outbox
    JSON item and a media SVG file."""
    from engine.marketing.fastlane import run_tick

    events = [_make_event("AAPL")]
    result = run_tick(events, root=tmp_path, now=_NOW, universe=_UNIVERSE)

    assert len(result["emitted"]) == 1, (
        f"Expected 1 emitted, got {len(result['emitted'])}; "
        f"skipped={result['skipped']}, quarantined={result['quarantined']}"
    )
    assert len(result["skipped"]) == 0
    assert len(result["quarantined"]) == 0

    item = result["emitted"][0]

    # Outbox item has required keys. XG-W2: the lane emits through the CANONICAL
    # outbox path (make_item/validate_item/enqueue), so `text` is the flattened
    # post string, `priority` is an int, the rich event record moved to `source`,
    # and the two copy halves stay readable as top-level headline/body.
    assert item["account"] == "flagship"
    assert item["kind"] == "earnings"
    assert item["immediate"] is True
    assert isinstance(item["priority"], int)
    assert item["status"] == "queued"
    assert item["headline"]
    assert item["body"]
    assert item["text"] == f"{item['headline']}\n\n{item['body']}"
    assert len(item["media"]) == 1
    assert item["source"]["ticker"] == "AAPL"

    # The item lands in the canonical queue (items.jsonl), which is what the
    # publisher folds — the old per-item <id>.json file had no reader at all.
    items_file = tmp_path / "data" / "marketing" / "outbox" / "items.jsonl"
    assert items_file.exists(), f"outbox items.jsonl not found at {items_file}"
    queued = [json.loads(line) for line in
              items_file.read_text().splitlines() if line.strip()]
    assert [q for q in queued if q["id"] == item["id"]], "item not in items.jsonl"
    assert queued[0]["kind"] == "earnings"
    assert queued[0]["schema"] == "marketing.outbox/v1"

    # No hand-rolled per-item JSON is written any more.
    stray = list((tmp_path / "data" / "marketing" / "outbox").glob("*.json"))
    assert stray == [], f"raw-file bypass still writing: {stray}"

    # Media SVG file exists (path unchanged — keyed on the EVENT id).
    media_rel = item["media"][0]["path"]  # "data/marketing/outbox/media/<id>.svg"
    media_file = tmp_path / media_rel
    assert media_file.exists(), f"Media SVG not found at {media_file}"
    svg_text = media_file.read_text()
    assert "<svg" in svg_text.lower(), "Media file does not contain SVG markup"


# ---------------------------------------------------------------------------
# 2. Re-running same events emits 0 (in-memory seen set)
# ---------------------------------------------------------------------------

def test_run_tick_dedupes_same_call(tmp_path: Path) -> None:
    """Calling run_tick twice in the same call with duplicate events should
    emit each event only once."""
    from engine.marketing.fastlane import run_tick

    event = _make_event("AAPL")
    events = [event, event]  # deliberately duplicate
    result = run_tick(events, root=tmp_path, now=_NOW, universe=_UNIVERSE)

    assert len(result["emitted"]) == 1, (
        "Duplicate event in the same batch must be deduplicated"
    )


# ---------------------------------------------------------------------------
# 3. Dedupe survives a fresh run_tick call (ledger reload from disk)
# ---------------------------------------------------------------------------

def test_run_tick_dedupe_survives_restart(tmp_path: Path) -> None:
    """After a first run_tick produces an outbox item, a second run_tick
    with the same event (simulating a daemon restart) must skip it via the
    persisted seen-ledger."""
    from engine.marketing.fastlane import run_tick

    event = _make_event("MSFT")
    events = [event]

    # First call: should emit
    result1 = run_tick(events, root=tmp_path, now=_NOW, universe=_UNIVERSE)
    assert len(result1["emitted"]) == 1, "First call should emit"

    # Verify ledger file exists
    ledger = tmp_path / "data" / "marketing" / "fastlane_seen.jsonl"
    assert ledger.exists(), "Seen-ledger was not written"
    assert event["id"] in ledger.read_text(), "Event id not in seen-ledger"

    # Second call with same event (fresh run_tick call = simulated restart)
    result2 = run_tick(events, root=tmp_path, now=_NOW, universe=_UNIVERSE)
    assert len(result2["emitted"]) == 0, (
        "Second call must return 0 emitted — seen-ledger should prevent re-emit"
    )
    assert any(
        s["reason"] == "dedupe" for s in result2["skipped"]
    ), "Skipped record should have reason='dedupe'"


# ---------------------------------------------------------------------------
# 4. Ineligible ticker (not in universe) is skipped with reason
# ---------------------------------------------------------------------------

def test_run_tick_skips_ineligible_ticker(tmp_path: Path) -> None:
    """An event whose ticker is not in the injected universe must be skipped,
    never emitted or quarantined."""
    from engine.marketing.fastlane import run_tick

    events = [_make_event("TSLA")]  # TSLA not in _UNIVERSE
    result = run_tick(events, root=tmp_path, now=_NOW, universe=_UNIVERSE)

    assert len(result["emitted"]) == 0
    assert len(result["quarantined"]) == 0
    assert len(result["skipped"]) == 1

    skip = result["skipped"][0]
    assert skip["ticker"] == "TSLA"
    assert "universe" in skip["reason"].lower(), (
        f"Skip reason should mention universe, got: {skip['reason']!r}"
    )


# ---------------------------------------------------------------------------
# 5. Copy-violation event → quarantined with violation strings
# ---------------------------------------------------------------------------

def test_run_tick_quarantines_copy_violations(tmp_path: Path) -> None:
    """An event that produces copy violating validate_copy must be quarantined
    (never emitted) and the quarantine record must include the violation strings.

    Strategy: patch _build_earnings_copy in fastlane to return a headline
    containing a banned word ("guaranteed") which will fail validate_copy.
    """
    import engine.marketing.fastlane as fl_mod

    original_build = fl_mod._build_earnings_copy

    def _bad_copy(event: dict) -> dict:
        result = original_build(event)
        # Inject a banned word — validate_copy will flag this
        result["headline"] = result["headline"] + " guaranteed"
        return result

    fl_mod._build_earnings_copy = _bad_copy
    try:
        from engine.marketing.fastlane import run_tick
        events = [_make_event("NVDA")]
        result = run_tick(events, root=tmp_path, now=_NOW, universe=_UNIVERSE)
    finally:
        fl_mod._build_earnings_copy = original_build

    assert len(result["emitted"]) == 0, (
        f"Expected 0 emitted but got {len(result['emitted'])}; "
        f"quarantined={result['quarantined']}"
    )
    assert len(result["quarantined"]) == 1, (
        f"Expected 1 quarantined but got {len(result['quarantined'])}"
    )

    q = result["quarantined"][0]
    assert q["ticker"] == "NVDA"
    assert q["reason"] == "copy_violations"
    assert "violations" in q
    assert len(q["violations"]) > 0
    # The banned-word violation string should name the word
    violation_text = " ".join(q["violations"])
    assert "guaranteed" in violation_text.lower(), (
        f"Expected 'guaranteed' in violations, got: {q['violations']}"
    )


# ---------------------------------------------------------------------------
# 6. daemon main() with MARKETING_FASTLANE_ENABLED unset returns 0
# ---------------------------------------------------------------------------

def test_daemon_kill_switch_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """When MARKETING_FASTLANE_ENABLED is not set (or != '1'), main() must
    return 0 immediately without executing any tick."""
    # Ensure the env var is absent
    monkeypatch.delenv("MARKETING_FASTLANE_ENABLED", raising=False)

    # Confirm the import hasn't cached state from a prior test
    import importlib
    import scripts.marketing_fastlane_daemon as daemon_mod
    importlib.reload(daemon_mod)

    # Capture stdout to verify the note is printed
    import io
    from unittest.mock import patch

    buf = io.StringIO()
    with patch("sys.stdout", buf):
        rc = daemon_mod.main([])

    assert rc == 0, f"Expected return code 0, got {rc}"
    note = buf.getvalue()
    assert "MARKETING_FASTLANE_ENABLED" in note, (
        f"Expected kill-switch note in stdout, got: {note!r}"
    )


def test_daemon_kill_switch_set_blocks_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """With MARKETING_FASTLANE_ENABLED=1 and --once, main() runs one tick
    and returns 0 (smoke-test: no crash)."""
    monkeypatch.setenv("MARKETING_FASTLANE_ENABLED", "1")

    import importlib
    import scripts.marketing_fastlane_daemon as daemon_mod
    importlib.reload(daemon_mod)

    # Patch _run_one_tick to avoid actual network calls and disk side-effects
    from unittest.mock import patch
    fake_result = {"emitted": [], "skipped": [], "quarantined": []}
    with patch.object(daemon_mod, "_run_one_tick", return_value=fake_result):
        rc = daemon_mod.main(["--once", "--dry-run"])

    assert rc == 0


# ---------------------------------------------------------------------------
# 7. --dry-run: run_tick with dry_run=True writes nothing to disk
# ---------------------------------------------------------------------------

def test_run_tick_dry_run_writes_nothing(tmp_path: Path) -> None:
    """When dry_run=True, run_tick should compute and return results but not
    write any files to disk (no outbox JSON, no media SVG, no seen-ledger)."""
    from engine.marketing.fastlane import run_tick

    events = [_make_event("GOOG")]
    result = run_tick(
        events, root=tmp_path, now=_NOW, universe=_UNIVERSE, dry_run=True
    )

    # Result should still be produced correctly
    assert len(result["emitted"]) == 1, (
        f"dry-run should still return emitted items; "
        f"skipped={result['skipped']}, quarantined={result['quarantined']}"
    )

    # Verify nothing was written
    outbox_dir = tmp_path / "data" / "marketing" / "outbox"
    ledger = tmp_path / "data" / "marketing" / "fastlane_seen.jsonl"

    assert not outbox_dir.exists() or not any(outbox_dir.rglob("*")), (
        "dry-run must not write any outbox files"
    )
    assert not ledger.exists(), (
        "dry-run must not write to the seen-ledger"
    )


# ---------------------------------------------------------------------------
# Bonus: fetch_events returns [] when FreePollProvider fails (no network needed)
# ---------------------------------------------------------------------------

def test_fetch_events_injectable_provider() -> None:
    """fetch_events should use the injected provider and never hit the network."""
    from engine.marketing.earnings_feed import fetch_events, EarningsProvider

    class _FakeProvider:
        def fetch(self, since: datetime) -> list[dict]:
            return [
                {
                    "id": "fake001",
                    "ticker": "NVDA",
                    "when": "2026-07-19T10:00:00",
                    "eps_actual": 7.50,
                    "eps_est": 7.20,
                    "rev_actual": None,
                    "rev_est": None,
                    "quarter": "Q2 2026",
                    "source": "fake",
                }
            ]

    events = fetch_events(datetime.now(timezone.utc), provider=_FakeProvider())
    assert len(events) == 1
    assert events[0]["ticker"] == "NVDA"


def test_fetch_events_provider_exception_returns_empty() -> None:
    """If the provider raises, fetch_events must return [] (fail-soft)."""
    from engine.marketing.earnings_feed import fetch_events

    class _BrokenProvider:
        def fetch(self, since: datetime) -> list[dict]:
            raise RuntimeError("simulated failure")

    events = fetch_events(datetime.now(timezone.utc), provider=_BrokenProvider())
    assert events == []


# ---------------------------------------------------------------------------
# Fix 2 — fastlane universe fail-closed
# ---------------------------------------------------------------------------

def test_run_tick_fails_closed_when_universe_unavailable(tmp_path: Path) -> None:
    """When universe=None AND sp500_heatmap.json is absent/broken, ALL events
    must be skipped with reason 'universe unavailable', nothing emitted, and
    nothing written to the seen-ledger (so they retry once the universe loads)."""
    from engine.marketing.fastlane import run_tick

    events = [_make_event("AAPL"), _make_event("MSFT", event_id="evt-msft-001")]

    # universe=None → fastlane tries to load sp500_heatmap.json which doesn't exist
    result = run_tick(events, root=tmp_path, now=_NOW, universe=None)

    assert len(result["emitted"]) == 0, (
        f"Expected 0 emitted when universe unavailable, got {len(result['emitted'])}"
    )
    assert len(result["quarantined"]) == 0, (
        "Nothing should be quarantined when universe unavailable"
    )
    assert len(result["skipped"]) == 2, (
        f"Expected 2 skipped, got {len(result['skipped'])}"
    )
    for skip in result["skipped"]:
        assert "universe" in skip["reason"].lower(), (
            f"Skip reason must mention universe, got: {skip['reason']!r}"
        )

    # Nothing written to seen-ledger (events must retry once universe loads)
    ledger = tmp_path / "data" / "marketing" / "fastlane_seen.jsonl"
    assert not ledger.exists(), (
        "seen-ledger must not be written when events are skipped due to unavailable universe"
    )


# ---------------------------------------------------------------------------
# Fix 3 — quarantine permanence: separate ledger with TEMPLATE_VERSION
# ---------------------------------------------------------------------------

def test_quarantine_uses_separate_ledger(tmp_path: Path) -> None:
    """Quarantined events must be written to fastlane_quarantine.jsonl, NOT to
    fastlane_seen.jsonl, so bumping TEMPLATE_VERSION lets them retry."""
    import engine.marketing.fastlane as fl_mod

    original_build = fl_mod._build_earnings_copy

    def _bad_copy(event: dict) -> dict:
        result = original_build(event)
        result["headline"] = result["headline"] + " guaranteed"
        return result

    fl_mod._build_earnings_copy = _bad_copy
    try:
        events = [_make_event("NVDA")]
        result = fl_mod.run_tick(events, root=tmp_path, now=_NOW, universe=_UNIVERSE)
    finally:
        fl_mod._build_earnings_copy = original_build

    assert len(result["quarantined"]) == 1

    seen_ledger = tmp_path / "data" / "marketing" / "fastlane_seen.jsonl"
    quarantine_ledger = tmp_path / "data" / "marketing" / "fastlane_quarantine.jsonl"

    # Must NOT be in seen-ledger (so a version bump lets it retry)
    assert not seen_ledger.exists(), (
        "Quarantined events must not appear in the seen-ledger"
    )

    # Must be in quarantine ledger
    assert quarantine_ledger.exists(), "Quarantine ledger was not created"
    rec = json.loads(quarantine_ledger.read_text().strip())
    assert rec["event_id"] == result["quarantined"][0]["id"]
    assert rec["template_version"] == fl_mod.TEMPLATE_VERSION


def test_quarantine_dedupe_same_version(tmp_path: Path) -> None:
    """A quarantined event must not be re-quarantined on a second tick at the
    same TEMPLATE_VERSION — quarantine ledger dedupe prevents double entries."""
    import engine.marketing.fastlane as fl_mod

    original_build = fl_mod._build_earnings_copy

    def _bad_copy(event: dict) -> dict:
        result = original_build(event)
        result["headline"] = result["headline"] + " guaranteed"
        return result

    fl_mod._build_earnings_copy = _bad_copy
    try:
        events = [_make_event("NVDA")]
        # First tick — quarantines it
        result1 = fl_mod.run_tick(events, root=tmp_path, now=_NOW, universe=_UNIVERSE)
        # Second tick — must still surface in quarantined list (for visibility)
        # but must NOT append a second row to the quarantine ledger
        result2 = fl_mod.run_tick(events, root=tmp_path, now=_NOW, universe=_UNIVERSE)
    finally:
        fl_mod._build_earnings_copy = original_build

    assert len(result1["quarantined"]) == 1
    assert len(result2["quarantined"]) == 1

    quarantine_ledger = tmp_path / "data" / "marketing" / "fastlane_quarantine.jsonl"
    lines = [l for l in quarantine_ledger.read_text().splitlines() if l.strip()]
    assert len(lines) == 1, (
        f"Expected exactly 1 quarantine record, got {len(lines)}"
    )


def test_quarantine_version_bump_retries(tmp_path: Path) -> None:
    """Monkeypatching TEMPLATE_VERSION simulates a template fix: a previously
    quarantined event retries (no longer appears as already-quarantined at the
    new version), so it can proceed through the pipeline."""
    import engine.marketing.fastlane as fl_mod

    original_build = fl_mod._build_earnings_copy
    original_version = fl_mod.TEMPLATE_VERSION

    # First tick: bad copy at version N → quarantined
    def _bad_copy(event: dict) -> dict:
        result = original_build(event)
        result["headline"] = result["headline"] + " guaranteed"
        return result

    fl_mod._build_earnings_copy = _bad_copy
    try:
        events = [_make_event("NVDA")]
        result1 = fl_mod.run_tick(events, root=tmp_path, now=_NOW, universe=_UNIVERSE)
    finally:
        fl_mod._build_earnings_copy = original_build

    assert len(result1["quarantined"]) == 1

    # Second tick: bump TEMPLATE_VERSION and use good copy → event retries and emits
    fl_mod.TEMPLATE_VERSION = original_version + 1
    try:
        result2 = fl_mod.run_tick(events, root=tmp_path, now=_NOW, universe=_UNIVERSE)
    finally:
        fl_mod.TEMPLATE_VERSION = original_version

    assert len(result2["emitted"]) == 1, (
        f"Expected emit after version bump; got emitted={result2['emitted']}, "
        f"skipped={result2['skipped']}, quarantined={result2['quarantined']}"
    )


# ---------------------------------------------------------------------------
# Fix 4 — _fmt_rev always uses unit suffix (no comma tokens)
# ---------------------------------------------------------------------------

def test_sub_million_revenue_does_not_quarantine(tmp_path: Path) -> None:
    """An event with revenue < $1M must be emitted, not quarantined.
    Previously _fmt_rev formatted sub-$1M as '500,000', which validate_copy
    tokenised as '500' and '000' — neither whitelisted → spurious quarantine."""
    from engine.marketing.fastlane import run_tick

    event = _make_event(
        "AAPL",
        rev_actual=500_000.0,
        rev_est=480_000.0,
        event_id="sub-million-rev-001",
    )
    result = run_tick([event], root=tmp_path, now=_NOW, universe=_UNIVERSE)

    assert len(result["quarantined"]) == 0, (
        f"Sub-$1M revenue must not quarantine; violations: "
        f"{[q['violations'] for q in result['quarantined']]}"
    )
    assert len(result["emitted"]) == 1, (
        f"Sub-$1M revenue event must be emitted; "
        f"skipped={result['skipped']}, quarantined={result['quarantined']}"
    )


def test_fmt_rev_unit_suffix_format() -> None:
    """_fmt_rev must always return a unit-suffixed string, never a comma integer."""
    import engine.marketing.fastlane as fl_mod

    # Access the inner function by building a minimal earnings copy and
    # checking the whitelist tokens — they must not contain commas.
    event = _make_event("AAPL", rev_actual=500_000.0, rev_est=480_000.0)
    copy_result = fl_mod._build_earnings_copy(event)
    whitelist = copy_result["ctx"]["numbers_whitelist"]
    body = copy_result["body"]

    # No token in whitelist should contain a comma (that would be "500,000" style)
    for token in whitelist:
        assert "," not in token, (
            f"Whitelist token {token!r} contains a comma — _fmt_rev must use unit suffixes"
        )

    # The body must not contain any comma-grouped number pattern
    import re
    comma_numbers = re.findall(r"\d{1,3}(?:,\d{3})+", body)
    assert not comma_numbers, (
        f"Body contains comma-grouped numbers {comma_numbers!r} — use unit suffixes"
    )


# ═════════════════════════════════════════════════════════════════════════════
# 8. wire_rank.v1 sidecar — the NON-PUBLIC ranked view of the wires window
#
# Contract (frozen): {"schema": "wire_rank.v1", "updated_at": <ISO-8601 UTC>,
# "ids": [<wire id>, ... best first]} and NOTHING else. Element order is the ONLY
# expression of rank, so no number exists in the file to leak even at a
# non-public path. Written by the VPS daemon on the same tick as the wires sink,
# immediately after it, atomically, fail-soft, never in --dry-run.
# ═════════════════════════════════════════════════════════════════════════════

_SIDE_NOW = datetime(2026, 7, 29, 18, 0, 0, tzinfo=timezone.utc)
_SIDE_STAMP = "2026-07-29T18:00:00Z"


def _daemon():
    import scripts.marketing_fastlane_daemon as d
    return d


def _wire(iid: str, *, fresh: bool = False) -> dict:
    """One published wires.v1 item (only `id` matters to the sidecar).

    `fresh=True` stamps the item at the RUN's wall clock. Required by any test
    that drives the real `_run_press_tick`, whose `now` is the wall clock: the
    wires sink age-filters the window (`rail_max_age_h`, 48h), so a fixed
    fixture date is a time bomb — green on build day, red two days later when
    the sink silently ages the item out (the repo's known fixture-date +
    wall-clock-gate trap; it detonated here on 2026-07-31). Tests that pass an
    explicit `now` into the helpers keep the fixed stamp for determinism.
    """
    ts = (datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
          if fresh else "2026-07-29T17:59:00Z")
    return {"id": iid, "ts": ts, "en": f"headline {iid}"}


def _armed_cfg() -> dict:
    return {"wire": {"rank_sidecar_enabled": True}}


def _numbers(node: object, path: str = "$"):
    """Every (path, value) pair in a parsed payload whose value is int/float.

    bool is deliberately included (it is an int subclass) — the contract is that
    NOTHING numeric appears anywhere in this file, at any depth.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _numbers(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _numbers(value, f"{path}[{index}]")
    elif isinstance(node, (int, float)):
        yield path, node


def _write_sidecar(monkeypatch, tmp_path, *, window, order, state=None, cfg=None):
    """Run the sidecar writer against a tmp state dir; return (payload, state)."""
    d = _daemon()
    monkeypatch.setenv("MACRO_LIVE_STATE_DIR", str(tmp_path))
    st = {} if state is None else state
    d._write_wire_rank_sidecar(window, order, st, cfg or _armed_cfg(), _SIDE_NOW)
    target = tmp_path / "wire_rank.json"
    if not target.exists():
        return None, st
    return json.loads(target.read_text(encoding="utf-8")), st


# (a) exact payload shape — and not one number anywhere in the file
def test_wire_rank_payload_is_schema_updated_at_ids_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload, _ = _write_sidecar(
        monkeypatch, tmp_path,
        window=[_wire("a"), _wire("b")],
        order={"a": 41.0, "b": 88.0},
    )
    assert set(payload) == {"schema", "updated_at", "ids"}
    assert payload["schema"] == "wire_rank.v1"
    assert payload["updated_at"] == _SIDE_STAMP
    assert payload["ids"] == ["b", "a"]


def test_wire_rank_file_contains_no_number_at_any_depth(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The whole point of the sidecar: order carries the rank, so there is no
    ranking number in the file to leak even though the path is non-public."""
    payload, _ = _write_sidecar(
        monkeypatch, tmp_path,
        window=[_wire("a"), _wire("b"), _wire("c")],
        order={"a": 41.0, "b": 88.5, "c": 12.0},
    )
    leaked = list(_numbers(payload))
    assert leaked == [], f"numeric value(s) reached the sidecar: {leaked}"


# (b) position IS the rank
def test_position_is_rank_and_unknown_ids_keep_recency_after_the_ranked_ones(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Window is served newest-first: c, a, b, d. Only a and b are ranked.
    window = [_wire("c"), _wire("a"), _wire("b"), _wire("d")]
    payload, _ = _write_sidecar(
        monkeypatch, tmp_path, window=window, order={"a": 40.0, "b": 90.0},
    )
    assert payload["ids"] == ["b", "a", "c", "d"]
    assert payload["ids"] == list(dict.fromkeys(payload["ids"])), "an id repeated"
    assert set(payload["ids"]) == {"a", "b", "c", "d"}, "the file must list EVERY window id"


def test_equal_ordering_values_keep_their_recency_position(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A stable sort is the tiebreak, so a tie is resolved newest-first rather
    than arbitrarily — otherwise the rail order would churn between ticks."""
    payload, _ = _write_sidecar(
        monkeypatch, tmp_path,
        window=[_wire("newer"), _wire("older")],
        order={"newer": 50.0, "older": 50.0},
    )
    assert payload["ids"] == ["newer", "older"]


def test_a_quiet_tick_still_ranks_the_window_from_the_persisted_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The file is rewritten EVERY real tick. A tick whose rail is empty must
    still publish the ranked window from the folded state map, and re-stamp
    updated_at — the reader's freshness contract is updated_at-driven."""
    state = {"wire_rank_order": {"a": 10.0, "b": 90.0}}
    payload, state = _write_sidecar(
        monkeypatch, tmp_path,
        window=[_wire("a"), _wire("b")], order={}, state=state,
    )
    assert payload["ids"] == ["b", "a"]
    assert payload["updated_at"] == _SIDE_STAMP


# (c) window-only — never historical
def test_an_id_that_left_the_window_leaves_the_file_and_the_state_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = {"wire_rank_order": {"gone": 99.0, "still": 10.0}}
    payload, state = _write_sidecar(
        monkeypatch, tmp_path, window=[_wire("still")], order={}, state=state,
    )
    assert payload["ids"] == ["still"], "an id outside the window reached the file"
    assert set(state["wire_rank_order"]) == {"still"}, "the state map was not pruned"


def test_the_state_map_folds_this_tick_over_the_persisted_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state = {"wire_rank_order": {"a": 10.0}}
    payload, state = _write_sidecar(
        monkeypatch, tmp_path,
        window=[_wire("a"), _wire("b")], order={"a": 95.0, "b": 20.0}, state=state,
    )
    assert state["wire_rank_order"] == {"a": 95.0, "b": 20.0}
    assert payload["ids"] == ["a", "b"], "the re-scored value did not win"


# (d) write-location ladder
def test_the_state_dir_env_override_wins_the_ladder(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    d = _daemon()
    monkeypatch.setenv("MACRO_LIVE_STATE_DIR", str(tmp_path))
    assert d._wire_rank_target() == tmp_path / "wire_rank.json"


def test_the_ladder_falls_through_to_the_gitignored_repo_dev_sink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    d = _daemon()
    monkeypatch.delenv("MACRO_LIVE_STATE_DIR", raising=False)
    dev = tmp_path / "dev" / "wire_rank.json"
    monkeypatch.setattr(
        d, "_WIRE_RANK_SINK_PATHS",
        ("/dev/null/no-such-state-dir/wire_rank.json", str(dev)),
    )
    assert d._wire_rank_target() == dev


def test_the_shipped_ladder_is_the_vps_state_dir_then_the_dev_sink() -> None:
    """Pinned because the brain-side reader mirrors this ladder. The sidecar must
    NEVER land in the public live dir — it is non-public by path."""
    d = _daemon()
    assert d._WIRE_RANK_SINK_PATHS == (
        "/var/lib/macro-live/state/wire_rank.json",
        "data/marketing/press/wire_rank.json",
    )
    assert d._WIRE_RANK_STATE_DIR_ENV == "MACRO_LIVE_STATE_DIR"
    for rung in d._WIRE_RANK_SINK_PATHS:
        assert "public" not in rung, f"{rung} is a served path"


# (e) atomicity idiom
def test_the_sidecar_write_leaves_no_stray_tmp_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """tmp + os.replace via the house atomic writer — a reader must never see a
    half-written file, and the tmp must not survive the write."""
    _write_sidecar(monkeypatch, tmp_path, window=[_wire("a")], order={"a": 1.0})
    assert [p.name for p in tmp_path.iterdir()] == ["wire_rank.json"]


# (h) kill switch
def test_deleting_the_config_key_disarms_the_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Code default FALSE: an absent key stops the write (house pattern)."""
    payload, _ = _write_sidecar(
        monkeypatch, tmp_path, window=[_wire("a")], order={"a": 1.0},
        cfg={"wire": {}},
    )
    assert payload is None
    assert not (tmp_path / "wire_rank.json").exists()


def test_the_shipped_config_arms_the_sidecar() -> None:
    import yaml
    cfg = yaml.safe_load(
        (ROOT / "config" / "press_sources.yml").read_text(encoding="utf-8")
    )
    assert cfg["wire"]["rank_sidecar_enabled"] is True


# ── daemon tick wiring: dry-run, fail-soft, no leak into the served rail ──────

def _stub_press_tick(monkeypatch, tmp_path, *, press_cfg):
    """Wire _run_press_tick to tmp paths with every poller/desk stubbed out."""
    import engine.marketing.breaking_feed as bf
    import engine.marketing.intelligence_desk as idesk
    import engine.marketing.press_providers as pp
    d = _daemon()
    monkeypatch.setattr(d, "ROOT", tmp_path)
    monkeypatch.setattr(d, "_PRESS_STATE_PATH", tmp_path / "press" / "state.json")
    monkeypatch.setattr(d, "_PRESS_SEEN_PATH", tmp_path / "press" / "seen.json")
    monkeypatch.setattr(bf, "poll_all", lambda root, cfg: [])
    monkeypatch.setattr(pp, "poll_all",
                        lambda root, cfg, state, *, offline=False, now=None: [])
    monkeypatch.setattr(idesk, "update_intelligence_desk",
                        lambda *a, **k: {"health": {}})
    monkeypatch.setattr(d, "_load_yaml", lambda p: press_cfg
                        if p.name == "press_sources.yml" else {})
    return d


# (f) dry-run writes nothing
def test_dry_run_writes_no_sidecar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("MACRO_LIVE_STATE_DIR", str(state_dir))
    cfg = {"wire": {"rank_sidecar_enabled": True,
                    "wires_sink_paths": [str(tmp_path / "live" / "wires.json")]}}
    d = _stub_press_tick(monkeypatch, tmp_path, press_cfg=cfg)
    d._run_press_tick(dry_run=True)
    assert not (state_dir / "wire_rank.json").exists()
    assert not (tmp_path / "live" / "wires.json").exists()


# (g) fail-soft
def test_a_raising_sidecar_writer_never_costs_the_tick(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog
) -> None:
    """The tick's return is what main() logs and heartbeats on — a sink fault
    that escaped here would present as a DEAD DAEMON, not as a missing file."""
    cfg = {"wire": {"rank_sidecar_enabled": True,
                    "wires_sink_paths": [str(tmp_path / "live" / "wires.json")]}}
    d = _stub_press_tick(monkeypatch, tmp_path, press_cfg=cfg)

    def boom(*a, **k):
        raise RuntimeError("sidecar exploded")

    monkeypatch.setattr(d, "_write_wire_rank_sidecar", boom)
    with caplog.at_level("ERROR"):
        result = d._run_press_tick(dry_run=False)   # must not raise
    assert isinstance(result, dict)
    assert result["_emit_allowed"] is False
    assert "wire_rank sidecar error (continuing)" in caplog.text
    # The rail the users see published regardless.
    assert (tmp_path / "live" / "wires.json").exists()


# (i) _rail_order never leaks into the served rail
_RANK_TOKENS = ("_rail_order", "rank_score", "salience", "_components",
                "wire_rank_order")


def test_the_served_wires_payload_carries_no_ranking_token(tmp_path: Path) -> None:
    d = _daemon()
    sink = tmp_path / "live" / "wires.json"
    cfg = {"wire": {"wires_sink_paths": [str(sink)], "rail_max_items": 50}}
    window = d._write_wires_sink(
        [{"id": "a", "ts": "2026-07-29T17:59:00Z", "en": "one"}], cfg, _SIDE_NOW
    )
    assert [it["id"] for it in window] == ["a"], "the sink must return its window"
    raw = sink.read_text(encoding="utf-8")
    for token in _RANK_TOKENS:
        assert token not in raw, f"wires.json leaked {token}"


# (j) the daemon's pinned literals survive this diff
def test_the_pinned_daemon_literals_survive() -> None:
    """Re-pinned here so a sidecar edit near the sink block cannot quietly undo
    them (they are the publish-switch/collection separation, #V2 §0-A)."""
    daemon = (ROOT / "scripts" / "marketing_fastlane_daemon.py").read_text(
        encoding="utf-8"
    )
    assert "offline=dry_run" in daemon
    assert "offline=effective_dry" not in daemon
    assert "update_intelligence_desk" in daemon


def test_a_live_tick_persists_the_ordering_map_after_the_sink(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The numbers live ONLY in the daemon's gitignored state.json — and step 5's
    save runs BEFORE the sink, so the fold has to be persisted by the sidecar
    step itself or it is silently lost every tick."""
    import engine.marketing.press_lane as pl
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("MACRO_LIVE_STATE_DIR", str(state_dir))
    cfg = {"wire": {"rank_sidecar_enabled": True,
                    "wires_sink_paths": [str(tmp_path / "live" / "wires.json")]}}
    d = _stub_press_tick(monkeypatch, tmp_path, press_cfg=cfg)
    # A pre-existing state file means this is NOT a cold start, so the tick takes
    # the full path rather than the prime early-return.
    d._PRESS_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    d._PRESS_STATE_PATH.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(pl, "run_press_tick", lambda *a, **k: {
        "emitted": [], "skipped": [], "digest": [], "blocked": [],
        # fresh=True: this test drives the REAL tick, whose clock is the wall
        # clock — a fixed fixture date ages out of the 48h window and empties
        # the sidecar (detonated 2026-07-31).
        "rail": [_wire("hot", fresh=True), _wire("cold", fresh=True)],
        "_rail_order": {"hot": 91.0, "cold": 44.0},
        "intelligence": [], "corpus": [], "_seen": [],
    })

    d._run_press_tick(dry_run=False)

    payload = json.loads((state_dir / "wire_rank.json").read_text(encoding="utf-8"))
    assert payload["ids"] == ["hot", "cold"]
    persisted = json.loads(d._PRESS_STATE_PATH.read_text(encoding="utf-8"))
    assert persisted["wire_rank_order"] == {"hot": 91.0, "cold": 44.0}
class TestTheEarningsPostObeysTheHouseVoice:
    """It emitted six numbers and no point of view, and nobody had seen it.

    The lane is dark by accident — nothing runs `--lane earnings`; the only
    systemd unit drives `--lane press`. Driven by hand on 2026-07-31 it produced:

        🧾 $AAPL (Q3 2026) earnings: BEAT.
        EPS $2.11 vs $1.98 est (+6.6%). Rev $98.40B vs $97.10B est (+1.3%).
        After-hours earnings drop.

    Six distinct figures against a house budget of two, an emoji lead, a shouted
    machine token for a verdict, and not one word that costs us anything. Arming
    the lane in that state would have re-introduced the exact voice this whole
    program removed.
    """

    @staticmethod
    def _emit(tmp_path, **kw):
        import json
        from datetime import datetime, timezone

        from engine.marketing.earnings_feed import _event_id
        from engine.marketing.fastlane import run_tick

        ev = {"id": _event_id(kw.get("ticker", "AAPL"), "Q3 2026", "t"),
              "ticker": kw.get("ticker", "AAPL"), "when": "2026-07-31T20:30:00",
              "eps_actual": kw.get("eps_actual", 2.11),
              "eps_est": kw.get("eps_est", 1.98),
              "rev_actual": kw.get("rev_actual", 98.4e9),
              "rev_est": kw.get("rev_est", 97.1e9),
              "quarter": kw.get("quarter", "Q3 2026"), "source": "t"}
        run_tick([ev], root=tmp_path,
                 now=datetime(2026, 7, 31, 21, 0, tzinfo=timezone.utc),
                 universe={ev["ticker"]}, dry_run=False, cta=True, spool=False)
        for f in (tmp_path / "data" / "marketing" / "outbox").glob("items*.jsonl"):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    return json.loads(line)["text"]
        raise AssertionError("the earnings lane emitted nothing")

    def test_it_clears_the_number_budget(self, tmp_path):
        from engine.marketing.copywriter import number_soup_violations

        text = self._emit(tmp_path)
        assert not number_soup_violations(text, kind="earnings"), text

    def test_the_verdict_reads_as_english_not_as_a_token(self, tmp_path):
        """`verdict` is BEAT/MISS/INLINE. Lowercasing it into a sentence gave
        "$AAPL miss on the Q3 2026", which is not English."""
        beat = self._emit(tmp_path / "a", eps_actual=2.11, eps_est=1.98)
        miss = self._emit(tmp_path / "b", eps_actual=1.80, eps_est=1.98)
        assert "beat on Q3 2026" in beat, beat
        assert "missed on Q3 2026" in miss, miss
        assert "miss on the" not in miss

    def test_a_missing_quarter_still_reads(self, tmp_path):
        text = self._emit(tmp_path, quarter=None)
        assert "on the quarter." in text, text

    def test_the_revenue_leg_is_words_not_a_second_pair_of_figures(self, tmp_path):
        """Same claim told twice is a data dump, not a stronger post."""
        ahead = self._emit(tmp_path / "a", rev_actual=98.4e9, rev_est=97.1e9)
        light = self._emit(tmp_path / "b", rev_actual=92.0e9, rev_est=97.1e9)
        assert "Revenue came in ahead too." in ahead
        assert "Revenue came in light." in light
        for text in (ahead, light):
            assert "B vs $" not in text, "the revenue figures are back in the copy"

    def test_it_carries_a_reaction_that_costs_something(self, tmp_path):
        """The house voice law: a fact PLUS a reaction that costs you."""
        text = self._emit(tmp_path)
        assert "don't trade the print" in text, text

    def test_it_passes_the_shared_guards(self, tmp_path):
        from engine.marketing.copywriter import banned_language
        from engine.marketing.value_gate import evaluate

        text = self._emit(tmp_path)
        assert not banned_language(text), text
        hl, bd = text.split("\n\n", 1)
        assert evaluate(hl, bd, kind="earnings", has_media=True).verdict == "pass"

    def test_the_whitelist_does_not_vouch_for_numbers_the_copy_never_says(self, tmp_path):
        """The whitelist CERTIFIES a figure as ours. Listing one the post never
        prints widens the certificate for nothing — the quiet direction for a
        guard to weaken in."""
        import json

        from datetime import datetime, timezone

        from engine.marketing.earnings_feed import _event_id
        from engine.marketing.fastlane import run_tick

        ev = {"id": _event_id("AAPL", "Q3 2026", "wl"), "ticker": "AAPL",
              "when": "2026-07-31T20:30:00", "eps_actual": 2.11, "eps_est": 1.98,
              "rev_actual": 98.4e9, "rev_est": 97.1e9, "quarter": "Q3 2026",
              "source": "t"}
        run_tick([ev], root=tmp_path,
                 now=datetime(2026, 7, 31, 21, 0, tzinfo=timezone.utc),
                 universe={"AAPL"}, dry_run=False, cta=True, spool=False)
        for f in (tmp_path / "data" / "marketing" / "outbox").glob("items*.jsonl"):
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                wl = (item.get("source") or {}).get("numbers_whitelist") or []
                text = item["text"]
                for token in wl:
                    assert str(token) in text, (
                        f"whitelisted {token!r} never appears in the post")


class TestTheEarningsLaneIsActuallyArmed:
    """The lane existed and nothing ran it. This pins the wiring that does.

    Three switches, and they are not the same one — getting it wrong is how a
    workflow runs 36 times a day and does nothing:

        MARKETING_FASTLANE_ENABLED   arms the daemon; without it a live run
                                     prints one line and exits 0 before fetching
        MARKETING_OUTBOX_ENABLED     lets the lane WRITE the queue
        MARKETING_PUBLISH_ENABLED    lets marketing-publish.yml SEND

    The first must be present or the workflow is inert. The last must be ABSENT
    or this lane stops being queue-only and starts posting to live accounts.
    """

    WORKFLOW = "​.github/workflows/marketing-earnings-wire.yml".replace("​", "")

    def _wf(self):
        import pathlib

        import pytest

        yaml = pytest.importorskip("yaml")
        p = pathlib.Path(self.WORKFLOW)
        assert p.exists(), "the earnings lane has no workflow — it is dark again"
        return yaml.safe_load(p.read_text(encoding="utf-8"))

    def _run_env(self):
        job = self._wf()["jobs"]["earnings"]
        step = next(s for s in job["steps"] if s.get("name") == "run the earnings lane")
        return step["env"], step["run"]

    def test_the_daemon_switch_is_set_or_every_pass_is_a_no_op(self):
        env, _ = self._run_env()
        assert env.get("MARKETING_FASTLANE_ENABLED") == "1"
        assert env.get("MARKETING_OUTBOX_ENABLED") == "1"

    def test_the_SEND_switch_is_absent_so_the_lane_stays_queue_only(self):
        env, _ = self._run_env()
        assert "MARKETING_PUBLISH_ENABLED" not in env, (
            "this lane would now POST to live accounts instead of queueing"
        )

    def test_it_writes_the_TRACKED_outbox_not_the_host_spool(self):
        """spool=True routes to the GITIGNORED items-host.jsonl, which the
        publisher never folds — the split-brain that kept the press wire dark."""
        _, run = self._run_env()
        assert "--no-spool" in run

    def test_it_stays_off_the_render_pool(self):
        """The nightly's ~67-minute budget is law."""
        assert self._wf()["jobs"]["earnings"]["runs-on"] == "ubuntu-latest"

    def test_it_polls_the_reporting_windows_on_weekdays_only(self):
        on = self._wf().get(True) or self._wf().get("on")
        crons = [e["cron"] for e in on["schedule"]]
        assert crons, "no schedule — the lane is dark again"
        fields = crons[0].split()
        assert fields[4] == "1-5", "weekend passes poll a calendar that cannot move"
        assert "11-13" in fields[1] and "20-22" in fields[1], fields[1]

    def test_the_earnings_calendar_is_in_the_checkout_cone(self):
        """earnings.parquet IS the input. Coning it out makes the lane blind."""
        job = self._wf()["jobs"]["earnings"]
        cone = job["steps"][0]["with"]["sparse-checkout"].split()
        assert "data/earnings" in cone
        install = next(s for s in job["steps"] if s.get("name") == "install deps")
        assert "pandas" in install["run"], "the parquet cannot be read without it"

    def test_the_daemon_exposes_the_no_spool_flag(self):
        """The workflow's command is only honest if the flag exists."""
        from scripts.marketing_fastlane_daemon import main  # noqa: F401
        import inspect
        import scripts.marketing_fastlane_daemon as D

        src = inspect.getsource(D)
        assert '"--no-spool"' in src
        assert "spool=args.spool" in src, "the flag is parsed but never threaded"
