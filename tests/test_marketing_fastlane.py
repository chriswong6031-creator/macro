"""tests/test_marketing_fastlane.py — Marketing fast lane W0 test suite.

Test list:
1. run_tick emits an outbox item and media SVG for a valid fixture event
2. Re-running run_tick with the same events emits 0 (seen-ledger dedupe)
3. Dedupe survives a fresh run_tick call (ledger reload from disk)
4. Ineligible ticker (not in universe) is skipped with reason
5. Copy-violation event is quarantined (not emitted) with violation strings
6. daemon main() with MARKETING_FASTLANE_ENABLED unset returns 0 without ticking
7. --dry-run flag: run_tick with dry_run=True writes nothing to disk
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

    # Outbox item has required keys
    assert item["account"] == "flagship"
    assert item["kind"] == "earnings"
    assert item["immediate"] is True
    assert item["priority"] == "high"
    assert item["status"] == "queued"
    assert "headline" in item["text"]
    assert "body" in item["text"]
    assert len(item["media"]) == 1
    assert item["provenance"]["ticker"] == "AAPL"

    # Outbox JSON file exists on disk
    event_id = item["id"]
    outbox_file = tmp_path / "data" / "marketing" / "outbox" / f"{event_id}.json"
    assert outbox_file.exists(), f"Outbox JSON not found at {outbox_file}"

    saved = json.loads(outbox_file.read_text())
    assert saved["id"] == event_id
    assert saved["kind"] == "earnings"

    # Media SVG file exists
    media_rel = item["media"][0]  # "data/marketing/outbox/media/<id>.svg"
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
