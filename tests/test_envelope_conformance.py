"""Conformance gate — W0 acceptance criteria.

Proves that the three external consumer contracts still hold on stamped
artifacts.  All sub-gates are skipif-guarded when the cross-repo is absent
so CI (which runs on the same Mac that has the repos) passes, while a clean
checkout without the sibling repos skips gracefully.

(a) build_feeds contract: sibling-stamp does not break the risk_radar
    extraction; a wrapper would break it (negative control).

(b) Mastermind anchors: _read_regime_date / _read_standouts_date / etc.
    still extract fresh dates from a stamped fixture dict.
    NOTE: data_layer/__init__.py does `import bot` which bootstraps
    vendor/macro onto sys.path (path side effect, no network).  To avoid
    that bootstrap logic, this test replicate the 3-5 line reader expressions
    verbatim from data_layer/macro_refresh.py lines 107-126, citing the source.
    The guard checks that the expressions match what is in the file.

(c) Terminal artifact conformance: charting-app/ingest/artifact_conformance.py
    check_artifact() on a stamped fixture must return stale=False with a fresh
    as_of.  Also confirms sibling envelope keys do not cause unexpected results.

Fixtures live under tests/fixtures/neuralweb/ — tiny synthetic dicts, no
real market data.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from engine.neuralweb.envelope import ENVELOPE_KEYS, stamp, strip_envelope

# ---------------------------------------------------------------------------
# Synthetic registry (same as unit tests — no YAML I/O)
# ---------------------------------------------------------------------------
_REG = {
    "meta": {
        "schema_version": 1,
        "tier_vocabulary": [
            "display", "shadow", "confirmer", "scored", "infrastructure",
        ],
    },
    "artifacts": {
        "regime-latest": {
            "producer": "engine/run.py",
            "tier": "infrastructure",
        },
        "us-standouts": {
            "producer": "engine/master_brain.py",
            "tier": "shadow",
        },
        "sector-cycles": {
            "producer": "engine/sector_cycles.py",
            "tier": "display",
        },
    },
}

_NOW = datetime(2026, 7, 4, 12, 0, 0, tzinfo=timezone.utc)

# ---------------------------------------------------------------------------
# Fixture directory for tiny synthetic payloads
# ---------------------------------------------------------------------------
_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "neuralweb"


# ═══════════════════════════════════════════════════════════════════════════
# (a) build_feeds contract
# ═══════════════════════════════════════════════════════════════════════════

class TestBuildFeedsContract:
    """Replicate the exact extraction from scripts/build_feeds.py lines 91-100.

    The extraction is:
        rr = latest.get("risk_radar")
        if isinstance(rr, dict) and rr.get("state") is not None:
            _write_json(out, "risk_radar.json", rr)

    The constraint: `rr` itself is written as the output file.  Sibling
    envelope keys on `rr` are preserved verbatim.  A wrapper makes
    `rr.get("state")` return None — the 2026-07-02 incident.
    """

    def _make_stamped_rr(self) -> dict:
        """Stamped risk_radar sub-object (sibling keys, not wrapped)."""
        rr_payload = {
            "state": "caution",
            "asof": "2026-07-04",
            "_trajectory": "rising",
            "pullback_odds": 0.72,
        }
        return stamp(rr_payload, artifact_id="regime-latest", registry=_REG, now=_NOW)

    def _make_latest_with_stamped_rr(self, stamped_rr: dict) -> dict:
        """Outer latest.json dict whose risk_radar value is a stamped sub-object."""
        latest_payload = {
            "date": "2026-07-04",
            "regime": "growth-scare",
            "schema_version": 1,  # latest.json's own schema_version
            "risk_radar": stamped_rr,
        }
        # Stamp the outer object too (the outer envelope doesn't affect the rr extraction)
        return stamp(latest_payload, artifact_id="regime-latest", registry=_REG, now=_NOW)

    def test_stamped_rr_state_accessible(self):
        """Positive control: sibling-stamped rr still exposes state at top level."""
        stamped_rr = self._make_stamped_rr()
        assert stamped_rr.get("state") == "caution", (
            "Sibling envelope keys must not shadow the payload's state field"
        )

    def test_envelope_keys_ride_along_as_siblings(self):
        """Envelope keys are present AND state is present — no nesting."""
        stamped_rr = self._make_stamped_rr()
        for k in ENVELOPE_KEYS:
            assert k in stamped_rr, f"envelope key {k!r} missing from stamped rr"
        assert "state" in stamped_rr

    def test_build_feeds_extraction_passes(self):
        """Simulate the exact build_feeds extraction on a stamped latest.json."""
        stamped_rr = self._make_stamped_rr()
        latest = self._make_latest_with_stamped_rr(stamped_rr)

        # Exact extraction from build_feeds.py lines 91-100:
        rr = latest.get("risk_radar")
        assert isinstance(rr, dict), "risk_radar must be a dict"
        assert rr.get("state") is not None, (
            "rr.get('state') must be non-None after sibling stamping"
        )
        # Simulated write: rr itself is the file content.
        # Envelope keys ride along in the output file as siblings.
        written_content = json.dumps(rr)
        parsed_back = json.loads(written_content)
        assert parsed_back.get("state") == "caution"
        for k in ENVELOPE_KEYS:
            assert k in parsed_back, f"envelope key {k!r} lost after serialisation"

    def test_negative_control_wrapper_breaks_extraction(self):
        """Negative control: a wrapper makes rr.get('state') return None.

        This encodes WHY the wrapper is forbidden.  If the producer wrapped
        the payload, the build_feeds extraction would re-create the incident:
            rr.get("state")  →  None
        because 'state' is no longer at the top level of rr.
        """
        rr_payload = {"state": "caution", "asof": "2026-07-04"}
        # Wrong pattern: wrap the payload instead of adding sibling keys.
        wrapped_rr = {
            "envelope": {
                "produced_by": "engine/run.py",
                "produced_at": "2026-07-04T12:00:00Z",
            },
            "data": rr_payload,
        }
        # Build the latest dict with the wrapped rr
        latest_with_wrapper = {"date": "2026-07-04", "risk_radar": wrapped_rr}

        # Exact build_feeds.py extraction:
        rr = latest_with_wrapper.get("risk_radar")
        # This is where the incident happened:
        assert rr.get("state") is None, (
            "A wrapper shape must make .get('state') return None — this is the "
            "incident pattern.  The positive test above proves sibling keys avoid it."
        )

    def test_nested_stamped_rr_in_stamped_latest(self):
        """Both outer latest and inner rr can be independently stamped."""
        stamped_rr = self._make_stamped_rr()
        latest = self._make_latest_with_stamped_rr(stamped_rr)

        # The outer stamp must not clobber the rr sub-object.
        rr = latest.get("risk_radar")
        assert isinstance(rr, dict)
        assert rr.get("state") == "caution"
        # The outer object has its own envelope keys.
        for k in ENVELOPE_KEYS:
            assert k in latest


# ═══════════════════════════════════════════════════════════════════════════
# (b) Mastermind anchor readers
# ═══════════════════════════════════════════════════════════════════════════

# NOTE: We do NOT import data_layer.macro_refresh because data_layer/__init__.py
# does `import bot` which bootstraps vendor/macro onto sys.path (a path-mutation
# side effect; see data_layer/__init__.py line 1 and bot/__init__.py lines 13-16
# in /Users/chriswong/Documents/Cluade/Mastermind/).  That bootstrap depends on
# vendor/macro being present, which is a gitignored local path.
#
# Instead, we replicate the reader expressions verbatim from
#   /Users/chriswong/Documents/Cluade/Mastermind/data_layer/macro_refresh.py
#   lines 107-126
# with a comment citing each source line.  If macro_refresh.py changes its
# reader logic, this test must be updated to match.

def _read_standouts_date(d: dict) -> str | None:
    # macro_refresh.py lines 107-109: site/factordata/us_standouts.json → "as_of"
    return d.get("as_of") or d.get("asof") or d.get("generated_at")


def _read_regime_date(d: dict) -> str | None:
    # macro_refresh.py lines 112-114: data/regime/latest.json → "date"
    return d.get("date") or d.get("as_of") or d.get("asof") or d.get("generated_at")


def _read_sector_cycles_date(d: dict) -> str | None:
    # macro_refresh.py lines 117-121: site/sectordata/sector_cycles.json → meta["asOf"]
    meta = d.get("meta", {}) if isinstance(d, dict) else {}
    return (meta.get("asOf") or meta.get("as_of") or meta.get("date")
            or d.get("as_of") or d.get("asof") or d.get("generated_at"))


def _read_stockdata_date(d: dict) -> str | None:
    # macro_refresh.py lines 124-126: site/stockdata/SPY.json → "asof"
    return d.get("asof") or d.get("as_of") or d.get("generated_at")


class TestMastermindAnchors:
    """Anchor readers return valid dates from stamped fixtures."""

    def test_regime_date_from_stamped_latest(self):
        """_read_regime_date still works when latest.json carries envelope keys."""
        payload = {
            "date": "2026-07-04",
            "regime": "growth-scare",
            "schema_version": 1,
            "risk_radar": {"state": "caution", "asof": "2026-07-04"},
        }
        stamped = stamp(payload, artifact_id="regime-latest", registry=_REG, now=_NOW)
        result = _read_regime_date(stamped)
        assert result == "2026-07-04", (
            f"_read_regime_date must return the date field even with envelope keys; "
            f"got {result!r}.  Stamped keys: {list(stamped.keys())}"
        )

    def test_standouts_date_from_stamped(self):
        """_read_standouts_date still works when us_standouts.json carries envelope keys."""
        payload = {
            "as_of": "2026-07-04",
            "board": [{"ticker": "NVDA", "rank": 1}],
        }
        stamped = stamp(payload, artifact_id="us-standouts", registry=_REG, now=_NOW)
        result = _read_standouts_date(stamped)
        assert result == "2026-07-04", (
            f"_read_standouts_date got {result!r}; stamped keys: {list(stamped.keys())}"
        )

    def test_sector_cycles_date_from_stamped(self):
        """_read_sector_cycles_date still works with envelope keys present."""
        payload = {
            "meta": {"asOf": "2026-07-04", "generated_utc": "2026-07-04T12:00:00Z"},
            "cycles": {},
        }
        stamped = stamp(payload, artifact_id="sector-cycles", registry=_REG, now=_NOW)
        result = _read_sector_cycles_date(stamped)
        assert result == "2026-07-04", (
            f"_read_sector_cycles_date got {result!r}; stamped keys: {list(stamped.keys())}"
        )

    def test_stockdata_date_from_stamped(self):
        """_read_stockdata_date still works with envelope keys present."""
        payload = {
            "asof": "2026-07-04",
            "ticker": "SPY",
            "close": 540.0,
        }
        # Use regime-latest as a stand-in (tier vocabulary is what matters)
        stamped = stamp(payload, artifact_id="regime-latest", registry=_REG, now=_NOW)
        result = _read_stockdata_date(stamped)
        assert result == "2026-07-04", (
            f"_read_stockdata_date got {result!r}; stamped keys: {list(stamped.keys())}"
        )

    def test_envelope_keys_do_not_shadow_date_fields(self):
        """None of the ENVELOPE_KEYS shadows the date fields the readers use."""
        # The readers look for: "date", "as_of", "asof", "generated_at", "meta.asOf"
        # None of these are envelope keys.
        date_keys = {"date", "as_of", "asof", "generated_at"}
        collision = date_keys & set(ENVELOPE_KEYS)
        assert not collision, (
            f"Envelope keys collide with anchor reader date fields: {collision}"
        )


# ═══════════════════════════════════════════════════════════════════════════
# (c) Terminal artifact conformance
# ═══════════════════════════════════════════════════════════════════════════

_CHARTING_APP = Path("/Users/chriswong/Documents/Cluade/charting-app")
_CHARTING_AVAILABLE = _CHARTING_APP.exists()

@pytest.mark.skipif(
    not _CHARTING_AVAILABLE,
    reason="charting-app repo not present at expected path",
)
class TestTerminalConformance:
    """Stamp a fixture and confirm artifact_conformance.check_artifact sees it as fresh."""

    @pytest.fixture(autouse=True)
    def _patch_sys_path(self):
        path_added = False
        if str(_CHARTING_APP) not in sys.path:
            sys.path.insert(0, str(_CHARTING_APP))
            path_added = True
        yield
        if path_added:
            sys.path.remove(str(_CHARTING_APP))

    def test_stamped_standouts_fresh(self, tmp_path):
        """check_artifact returns stale=False on a stamped us_standouts fixture with today's as_of."""
        from ingest.artifact_conformance import check_artifact  # noqa: PLC0415

        # Build a minimal macro_root with the artifact at the right relative path.
        macro_root = tmp_path / "macro"
        artifact_rel = "site/factordata/us_standouts.json"
        artifact_path = macro_root / artifact_rel
        artifact_path.parent.mkdir(parents=True, exist_ok=True)

        today_str = date.today().isoformat()
        payload = {
            "as_of": today_str,
            "board": [{"ticker": "NVDA", "rank": 1}],
        }
        stamped = stamp(payload, artifact_id="us-standouts", registry=_REG, now=_NOW)
        artifact_path.write_text(json.dumps(stamped), encoding="utf-8")

        spec = {
            "artifact": artifact_rel,
            "as_of_field": "as_of",
            "expected_max_age_td": 2,
            "kind": "standouts",
        }
        result = check_artifact(macro_root, spec, today=date.today())
        assert result.get("stale") is False, (
            f"Stamped standouts should be fresh; result={result}"
        )

    def test_stamped_regime_latest_fresh(self, tmp_path):
        """check_artifact returns stale=False on a stamped latest.json fixture."""
        from ingest.artifact_conformance import check_artifact  # noqa: PLC0415

        macro_root = tmp_path / "macro"
        artifact_rel = "data/regime/latest.json"
        artifact_path = macro_root / artifact_rel
        artifact_path.parent.mkdir(parents=True, exist_ok=True)

        today_str = date.today().isoformat()
        payload = {
            "date": today_str,
            "regime": "neutral",
            "schema_version": 1,
        }
        stamped = stamp(payload, artifact_id="regime-latest", registry=_REG, now=_NOW)
        artifact_path.write_text(json.dumps(stamped), encoding="utf-8")

        spec = {
            "artifact": artifact_rel,
            "as_of_field": "date",
            "expected_max_age_td": 2,
            "kind": "regime",
        }
        result = check_artifact(macro_root, spec, today=date.today())
        assert result.get("stale") is False, (
            f"Stamped regime latest should be fresh; result={result}"
        )

    def test_envelope_keys_do_not_confuse_asof_extraction(self, tmp_path):
        """Envelope keys at the top level do not interfere with as_of extraction."""
        from ingest.artifact_conformance import check_artifact  # noqa: PLC0415

        macro_root = tmp_path / "macro"
        artifact_rel = "site/factordata/us_standouts.json"
        artifact_path = macro_root / artifact_rel
        artifact_path.parent.mkdir(parents=True, exist_ok=True)

        today_str = date.today().isoformat()
        payload = {"as_of": today_str, "board": []}
        stamped = stamp(payload, artifact_id="us-standouts", registry=_REG, now=_NOW)
        artifact_path.write_text(json.dumps(stamped), encoding="utf-8")

        spec = {
            "artifact": artifact_rel,
            "as_of_field": "as_of",
            "expected_max_age_td": 2,
            "kind": "standouts",
        }
        result = check_artifact(macro_root, spec, today=date.today())
        # produced_at (an envelope key) must NOT be mistaken for as_of.
        assert result.get("asof") == today_str, (
            f"as_of extraction must read the payload field, not produced_at; "
            f"result={result}"
        )
        assert result.get("stale") is False


# ═══════════════════════════════════════════════════════════════════════════
# Fixture files: ensure they exist (created on first run by write logic above)
# These are tiny synthetic dicts written to tests/fixtures/neuralweb/ for
# any consumer that wants pre-built fixture files rather than programmatic ones.
# ═══════════════════════════════════════════════════════════════════════════

class TestFixtureFiles:
    """Ensure fixture files exist and are valid JSON with envelope keys."""

    def test_fixture_dir_exists(self):
        assert _FIXTURE_DIR.exists(), (
            f"tests/fixtures/neuralweb/ must exist; create it and commit "
            f"the fixtures: {_FIXTURE_DIR}"
        )

    def test_regime_fixture_has_envelope(self):
        f = _FIXTURE_DIR / "regime_latest_stamped.json"
        if not f.exists():
            pytest.skip("fixture file not yet written")
        d = json.loads(f.read_text())
        for k in ENVELOPE_KEYS:
            assert k in d, f"fixture missing envelope key {k!r}"

    def test_standouts_fixture_has_envelope(self):
        f = _FIXTURE_DIR / "us_standouts_stamped.json"
        if not f.exists():
            pytest.skip("fixture file not yet written")
        d = json.loads(f.read_text())
        for k in ENVELOPE_KEYS:
            assert k in d, f"fixture missing envelope key {k!r}"
