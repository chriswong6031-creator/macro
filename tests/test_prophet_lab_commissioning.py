"""tests/test_prophet_lab_commissioning.py — LAB-0 §6 commissioning-prep suite.

Covers the three pieces built for Radar live commissioning readiness
(`research/prophet_v4/LAB0_B5_RECUT_OPERATOR_LAB_2026-08-18.md` §6 step 3,
`research/prophet_v4/P_LAB_COMMISSIONING_NOTES.md`):

1. R2-first spool transport (`engine.prophet_lab.sources.resolve_radar_spool`),
   mirroring the exact backend ladder the Radar spool WRITER
   (`engine.entry_radar.spool.NominationSpool._put`) uses.
2. Baseline provisioning (`scripts/prophet_lab_baseline.py`) — refuses to
   mint unless it can read at least one real spooled pass with a parseable,
   tz-aware `pass_ts`; mints strictly-after-first-pass.
3. An end-to-end chain proving the two combine correctly: an event first
   observed BEFORE the baseline is minted stays `retrospective_seed`
   forever, while a genuinely new event first spooled AFTER the mint
   classifies `live_forward`.

No fixture files beyond this module's own `tmp_path`-built spool
directories — every envelope here is written inline, in the exact
`entry_radar.events/v1` shape `engine.entry_radar.live_ledger.build_event_payload`
produces (`schema`/`pass_ts`/`pass_id`/`pack`/`transitions`/`events`), so this
file never imports `engine.entry_radar.live_ledger` — keeps this suite's own
import surface off the ~150-file Radar detector/challenger fan-out (see
`engine/prophet_lab/sources.py`'s module docstring).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.prophet_lab_baseline as baseline_cli
from engine.entry_radar import spool as radar_spool
from engine.prophet_lab import LabRoots, build_lab_response
from engine.prophet_lab import sources as sources_mod
from engine.prophet_lab.contracts import (
    BOARD_G0,
    OBSERVATION_LIVE_FORWARD,
    OBSERVATION_RETROSPECTIVE_SEED,
)


# ---------------------------------------------------------------------------
# fixture builders — plain dicts, no live_ledger import (see module docstring)
# ---------------------------------------------------------------------------
def _envelope(*, pass_ts: str, pass_id: str, events: list[dict]) -> dict:
    return {
        "schema": sources_mod.ENVELOPE_SCHEMA,
        "pass_ts": pass_ts,
        "pass_id": pass_id,
        "pack": {"as_of": pass_ts[:10], "pack_hash": f"hash-{pass_id}"},
        "transitions": [],
        "events": events,
        "health": {},
    }


def _g0_event(event_id: str, ticker: str, *, signal_ts: str) -> dict:
    return {
        "event_id": event_id,
        "producer": "radar.entry_radar",
        "detector_id": "G0_GREY_DOT@1",
        "ticker": ticker,
        "family": "grey_dot",
        "subtype": None,
        "signal_ts": signal_ts,
        "signal_known_ts": None,
        "bar_state": "confirmed",
        "final": True,
        "quality": None,
        "authority": {"decision_authority": False},
    }


def _write_pass(spool_dir: Path, *, session: str, stamp: str, envelope: dict) -> Path:
    """Real Radar key shape: ``<prefix>/<session>/<stamp>.json`` under the
    local spool root, matching ``engine.entry_radar.spool.spool_key``."""
    path = spool_dir / sources_mod.RADAR_EVENT_SPOOL_PREFIX / session / f"{stamp}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope), encoding="utf-8")
    return path


class _Body:
    """Minimal boto3-``StreamingBody`` double: only ``.read()`` is used."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakeR2:
    """``list_objects_v2``/``get_object`` double — same plain-method-fake
    convention already used against this module's WRITE side
    (``tests/test_entry_radar_w4_lane.py``'s ``ExplodingR2``)."""

    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.list_calls: list[dict] = []

    def list_objects_v2(self, **kwargs):
        self.list_calls.append(kwargs)
        prefix = kwargs.get("Prefix", "")
        keys = sorted(k for k in self.objects if k.startswith(prefix))
        return {"Contents": [{"Key": k} for k in keys], "IsTruncated": False}

    def get_object(self, **kwargs):
        return {"Body": _Body(self.objects[kwargs["Key"]])}


class _ExplodingListR2:
    """A credentialed-but-broken R2: ListBucket itself fails (the
    credential/permission-error shape LAB-0 §6 requires stay VISIBLE)."""

    def list_objects_v2(self, **kwargs):  # noqa: ARG002
        raise RuntimeError("AccessDenied: not authorized to perform ListBucket")


# ---------------------------------------------------------------------------
# Piece 1 — R2-first transport (engine.prophet_lab.sources.resolve_radar_spool)
# ---------------------------------------------------------------------------
def test_resolve_radar_spool_reads_r2_when_a_client_is_injected() -> None:
    prefix = sources_mod.RADAR_EVENT_SPOOL_PREFIX
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    key = f"{prefix}/2026-08-19/100000-p1.json"
    s3 = _FakeR2({key: json.dumps(env).encode("utf-8")})

    result = sources_mod.resolve_radar_spool(None, s3=s3)

    assert result.backend == "r2"
    assert result.configured is True
    assert result.dir_exists is True
    assert result.error is None
    assert len(result.envelopes) == 1
    assert result.envelopes[0]["pass_ts"] == "2026-08-19T10:00:00Z"
    assert result.files_seen == 1
    assert result.envelopes_skipped == 0
    assert s3.list_calls and s3.list_calls[0]["Prefix"] == prefix


def test_resolve_radar_spool_skips_off_schema_r2_objects_and_counts_them() -> None:
    prefix = sources_mod.RADAR_EVENT_SPOOL_PREFIX
    good = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                     events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    s3 = _FakeR2({
        f"{prefix}/2026-08-19/100000-p1.json": json.dumps(good).encode("utf-8"),
        f"{prefix}/2026-08-19/100500-p2.json": b'{"schema": "some.other/v1"}',
        f"{prefix}/2026-08-19/101000-p3.json": b"{not json",
    })
    result = sources_mod.resolve_radar_spool(None, s3=s3)
    assert result.backend == "r2"
    assert result.files_seen == 3
    assert len(result.envelopes) == 1
    assert result.envelopes_skipped == 2


def test_resolve_radar_spool_falls_back_to_local_with_no_r2_credentials(
    tmp_path: Path, monkeypatch,
) -> None:
    for name in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)

    result = sources_mod.resolve_radar_spool(spool)

    assert result.backend == "local"
    assert result.error is None
    assert len(result.envelopes) == 1


def test_resolve_radar_spool_unconfigured_when_neither_backend_available(monkeypatch) -> None:
    for name in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    result = sources_mod.resolve_radar_spool(None)
    assert result.backend == "unconfigured"
    assert result.configured is False
    assert result.envelopes == []


def test_resolve_radar_spool_r2_list_failure_is_visible_with_no_local_fallback() -> None:
    result = sources_mod.resolve_radar_spool(None, s3=_ExplodingListR2())
    assert result.backend == "r2"
    assert result.dir_exists is False
    assert result.error is not None
    assert "r2_list_failed" in result.error
    assert result.envelopes == []


def test_resolve_radar_spool_r2_list_failure_falls_back_to_local_but_stays_visible(
    tmp_path: Path,
) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)

    result = sources_mod.resolve_radar_spool(spool, s3=_ExplodingListR2())

    # Backend ladder mirrors the WRITER: R2 failed, a local dir IS configured
    # -> fall back and still serve real data...
    assert result.backend == "local"
    assert len(result.envelopes) == 1
    # ...but the R2 failure must stay VISIBLE, never silently absorbed by a
    # fallback that happened to work (LAB-0 §6's explicit requirement).
    assert result.error is not None
    assert "r2_list_failed" in result.error


def test_health_block_names_r2_backend_when_credentials_resolve(monkeypatch) -> None:
    prefix = sources_mod.RADAR_EVENT_SPOOL_PREFIX
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    key = f"{prefix}/2026-08-19/100000-p1.json"
    s3 = _FakeR2({key: json.dumps(env).encode("utf-8")})
    monkeypatch.setattr(radar_spool, "r2_credentials_present", lambda: True)
    monkeypatch.setattr(radar_spool, "r2_client_for_read", lambda: s3)

    payload = build_lab_response(LabRoots())

    assert payload["health"]["radar_spool_source"] == "r2"
    assert "radar_spool_error" not in payload["health"]


def test_health_block_surfaces_r2_credential_failure_as_a_visible_state(monkeypatch) -> None:
    # THE fail-closed property LAB-0 §6 requires: a credential/permission
    # error must never present as an empty-and-clean board.
    monkeypatch.setattr(radar_spool, "r2_credentials_present", lambda: True)
    monkeypatch.setattr(radar_spool, "r2_client_for_read", lambda: _ExplodingListR2())

    payload = build_lab_response(LabRoots())
    health = payload["health"]

    assert health["radar_spool_source"] == "r2"
    assert health["radar_spool_configured"] is True
    assert health["radar_spool_readable"] is False
    assert "radar_spool_error" in health
    assert "r2_list_failed" in health["radar_spool_error"]
    # And the board itself degrades honestly (no envelopes -> no rows),
    # never a fabricated empty-looks-clean board.
    assert payload["boards"][BOARD_G0] == []


def test_health_block_names_unconfigured_when_no_backend_resolves(monkeypatch) -> None:
    for name in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(name, raising=False)
    payload = build_lab_response(LabRoots())
    assert payload["health"]["radar_spool_source"] == "unconfigured"


# ---------------------------------------------------------------------------
# Piece 2 — baseline provisioning CLI (scripts/prophet_lab_baseline.py)
# ---------------------------------------------------------------------------
def test_baseline_cli_refuses_when_no_baseline_path_configured(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    monkeypatch.delenv("PROPHET_LAB_OBSERVATION_BASELINE_PATH", raising=False)
    rc = baseline_cli.main(["--spool-dir", str(tmp_path / "spool")])
    assert rc == 1
    assert "no baseline path configured" in capsys.readouterr().err


def test_baseline_cli_refuses_when_no_spooled_pass_exists(tmp_path: Path, capsys) -> None:
    baseline_path = tmp_path / "state" / "observation_baseline.json"
    rc = baseline_cli.main([
        "--spool-dir", str(tmp_path / "empty_spool"),
        "--baseline-path", str(baseline_path),
    ])
    assert rc == 1
    assert not baseline_path.exists()
    err = capsys.readouterr().err
    assert "REFUSING" in err
    assert "no real spooled pass" in err


def test_baseline_cli_refuses_when_every_spooled_pass_ts_is_naive(
    tmp_path: Path, capsys,
) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00", pass_id="p1",  # naive -- no offset
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
    ])

    assert rc == 1
    assert not baseline_path.exists()
    assert "no real spooled pass" in capsys.readouterr().err


def test_baseline_cli_dry_run_reports_but_never_writes(tmp_path: Path, capsys) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-08-19T12:00:00Z",
    ])

    assert rc == 0
    assert not baseline_path.exists()
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "would mint" in out


def test_baseline_cli_write_mints_a_schema_valid_marker(tmp_path: Path) -> None:
    spool = tmp_path / "spool"
    env_early = _envelope(pass_ts="2026-08-19T09:00:00Z", pass_id="p0",
                          events=[_g0_event("evt-0", "AAA", signal_ts="2026-08-19T08:55:00Z")])
    env_late = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                         events=[_g0_event("evt-1", "BBB", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="090000-p0", envelope=env_early)
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env_late)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-08-19T11:00:00Z", "--write", "--i-know-this-is-rehearsal",
    ])

    assert rc == 0
    marker = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert marker["schema"] == sources_mod.BASELINE_SCHEMA
    assert marker["baseline_started_at"] == "2026-08-19T11:00:00.000000Z"
    # And the marker the CLI just wrote is one the API's own reader accepts.
    read_back = sources_mod.read_observation_baseline(baseline_path)
    assert read_back.error is None
    assert read_back.baseline is not None


def test_baseline_cli_refuses_an_as_of_that_does_not_strictly_postdate_the_latest_pass(
    tmp_path: Path, capsys,
) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-08-19T10:00:00Z",  # equal to the latest pass -- not STRICTLY after
        "--write", "--i-know-this-is-rehearsal",
    ])

    assert rc == 1
    assert not baseline_path.exists()
    err = capsys.readouterr().err
    assert "REFUSING" in err
    assert "not strictly after the latest" in err


def test_baseline_cli_refuses_a_naive_as_of_override(tmp_path: Path, capsys) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-08-19T12:00:00",  # naive -- no offset, must be refused
        "--write", "--i-know-this-is-rehearsal",
    ])

    assert rc == 1
    assert not baseline_path.exists()
    err = capsys.readouterr().err
    assert "REFUSING" in err
    assert "does not parse to a tz-aware ISO-8601 instant" in err


def test_naive_baseline_marker_written_directly_is_rejected_by_the_reader(
    tmp_path: Path,
) -> None:
    """A defensive belt-and-braces check: even if some OTHER path ever wrote
    a naive marker directly (bypassing this CLI), the API's own reader still
    refuses it — the honesty invariant does not depend on this CLI being the
    only writer."""
    baseline_path = tmp_path / "state" / "observation_baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(json.dumps({
        "schema": sources_mod.BASELINE_SCHEMA,
        "baseline_started_at": "2026-08-19T09:30:00",  # naive
    }), encoding="utf-8")

    result = sources_mod.read_observation_baseline(baseline_path)

    assert result.baseline is None
    assert result.error == "naive_or_unparseable_started_at"


# ---------------------------------------------------------------------------
# Piece 3 — end-to-end commissioning chain
# ---------------------------------------------------------------------------
def test_e2e_commissioning_chain_seed_then_baseline_then_live_forward(tmp_path: Path) -> None:
    """The headline acceptance scenario (mission commission, verbatim):

    first spooled pass (T0) -> baseline minted at T1 > T0 -> a later event
    first spooled at T2 > T1 classifies live_forward, while the event first
    seen at T0 stays retrospective_seed.
    """
    spool = tmp_path / "spool"
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    # T0: the FIRST real spooled pass, minted BEFORE any baseline exists.
    t0 = "2026-08-19T09:00:00Z"
    env_t0 = _envelope(pass_ts=t0, pass_id="p0",
                       events=[_g0_event("evt-seed", "AAA", signal_ts="2026-08-19T08:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="090000-p0", envelope=env_t0)

    # Commission: mint the baseline at T1 > T0, exactly as the CLI is meant
    # to be run once the first real pass has spooled.
    t1 = "2026-08-19T09:30:00Z"
    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", t1, "--write", "--i-know-this-is-rehearsal",
    ])
    assert rc == 0

    # T2 > T1: a genuinely NEW event, first spooled AFTER the baseline mint.
    t2 = "2026-08-19T10:00:00Z"
    env_t2 = _envelope(pass_ts=t2, pass_id="p1",
                       events=[_g0_event("evt-live", "BBB", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env_t2)

    roots = LabRoots(radar_spool_dir=spool, observation_baseline_path=baseline_path)
    payload = build_lab_response(roots)

    assert payload["health"]["radar_spool_source"] == "local"
    assert payload["health"]["observation_baseline_present"] is True
    assert payload["generation"]["baseline_coverage_verified"] is True

    g0_rows = {row["ticker"]: row for row in payload["boards"][BOARD_G0]}
    assert g0_rows["AAA"]["observation_class"] == OBSERVATION_RETROSPECTIVE_SEED
    assert g0_rows["AAA"]["evidence_eligible"] is False
    assert g0_rows["BBB"]["observation_class"] == OBSERVATION_LIVE_FORWARD
    assert g0_rows["BBB"]["evidence_eligible"] is True


def test_e2e_baseline_minted_with_no_spooled_pass_leaves_the_cli_refusing(
    tmp_path: Path,
) -> None:
    """The negative control: nothing to read -> nothing minted -> the Lab
    stays fully seeded (no board falsely promotes)."""
    baseline_path = tmp_path / "state" / "observation_baseline.json"
    rc = baseline_cli.main([
        "--spool-dir", str(tmp_path / "empty_spool"),
        "--baseline-path", str(baseline_path),
        "--write",
    ])
    assert rc == 1
    assert not baseline_path.exists()

    # And the Lab, reading the same (still-unconfigured) baseline path,
    # stays fully fail-honest.
    roots = LabRoots(observation_baseline_path=baseline_path)
    payload = build_lab_response(roots)
    assert payload["health"]["observation_baseline_present"] is False


# ---------------------------------------------------------------------------
# Review round 2 (2026-08-19) — B2: R2 client BUILD failure must never read
# as "R2 unconfigured".
# ---------------------------------------------------------------------------
def test_resolve_radar_spool_client_build_failure_is_a_visible_r2_error(monkeypatch) -> None:
    monkeypatch.setattr(radar_spool, "r2_credentials_present", lambda: True)
    monkeypatch.setattr(radar_spool, "r2_client_for_read", lambda: None)

    result = sources_mod.resolve_radar_spool(None)

    assert result.backend == "r2"
    assert result.dir_exists is False
    assert result.error == "r2_client_build_failed"
    assert result.envelopes == []


def test_resolve_radar_spool_client_build_failure_falls_back_to_local_but_stays_visible(
    tmp_path: Path, monkeypatch,
) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    monkeypatch.setattr(radar_spool, "r2_credentials_present", lambda: True)
    monkeypatch.setattr(radar_spool, "r2_client_for_read", lambda: None)

    result = sources_mod.resolve_radar_spool(spool)

    assert result.backend == "local"
    assert result.error == "r2_client_build_failed"
    assert len(result.envelopes) == 1


def test_health_block_surfaces_r2_client_build_failure(monkeypatch) -> None:
    monkeypatch.setattr(radar_spool, "r2_credentials_present", lambda: True)
    monkeypatch.setattr(radar_spool, "r2_client_for_read", lambda: None)

    payload = build_lab_response(LabRoots())
    health = payload["health"]

    assert health["radar_spool_source"] == "r2"
    assert health["radar_spool_error"] == "r2_client_build_failed"
    assert payload["boards"][BOARD_G0] == []


# ---------------------------------------------------------------------------
# Review round 2 — B3: an errored (even fallback-salvaged) read must never
# contribute to baseline-coverage verification -- LAB-0 §4 frozen violation
# risk otherwise (a partial local set could look "verified" purely because
# the evidence that would have disproven it was never read).
# ---------------------------------------------------------------------------
def test_response_forces_coverage_unverified_when_r2_errored_even_with_local_fallback_data(
    tmp_path: Path, monkeypatch,
) -> None:
    spool = tmp_path / "spool"
    # This LOCAL fallback envelope's pass_ts (09:00Z) is BEFORE
    # baseline_started_at (09:30Z) -- taken alone, it would VERIFY coverage.
    # It must not be trusted to, because it only exists because R2 (the
    # configured PRIMARY backend) failed and this is a partial substitute.
    env = _envelope(pass_ts="2026-08-19T09:00:00Z", pass_id="p0",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T08:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="090000-p0", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(json.dumps({
        "schema": sources_mod.BASELINE_SCHEMA,
        "baseline_started_at": "2026-08-19T09:30:00Z",
    }), encoding="utf-8")

    monkeypatch.setattr(radar_spool, "r2_credentials_present", lambda: True)
    monkeypatch.setattr(radar_spool, "r2_client_for_read", lambda: _ExplodingListR2())

    roots = LabRoots(radar_spool_dir=spool, observation_baseline_path=baseline_path)
    payload = build_lab_response(roots)

    assert payload["health"]["radar_spool_source"] == "local"
    assert "radar_spool_error" in payload["health"]
    # THE property under test: coverage must be FORCED unverified, never
    # derived from the partial fallback set, even though that set alone
    # would otherwise satisfy baseline_coverage_verified's own check.
    assert payload["generation"]["baseline_coverage_verified"] is False
    g0_rows = {row["ticker"]: row for row in payload["boards"][BOARD_G0]}
    assert g0_rows["AAA"]["observation_class"] == OBSERVATION_RETROSPECTIVE_SEED
    assert g0_rows["AAA"]["evidence_eligible"] is False


# ---------------------------------------------------------------------------
# Review round 2 — S2: list_r2_keys pagination hardening.
# ---------------------------------------------------------------------------
class _BadPaginationR2:
    def list_objects_v2(self, **kwargs):  # noqa: ARG002
        return {"Contents": [{"Key": "a.json"}], "IsTruncated": True}  # no token


class _LoopingR2:
    def list_objects_v2(self, **kwargs):  # noqa: ARG002
        return {"Contents": [], "IsTruncated": True, "NextContinuationToken": "same-token"}


def test_list_r2_keys_raises_when_truncated_with_no_usable_token() -> None:
    with pytest.raises(RuntimeError, match="no usable NextContinuationToken"):
        radar_spool.list_r2_keys(_BadPaginationR2(), "prefix/")


def test_list_r2_keys_raises_on_a_repeated_continuation_token() -> None:
    with pytest.raises(RuntimeError, match="same"):
        radar_spool.list_r2_keys(_LoopingR2(), "prefix/")


def test_list_r2_keys_paginates_correctly_across_multiple_pages() -> None:
    pages = [
        {"Contents": [{"Key": "a.json"}], "IsTruncated": True, "NextContinuationToken": "t1"},
        {"Contents": [{"Key": "b.json"}], "IsTruncated": False},
    ]
    calls: list[dict] = []

    class _PagedR2:
        def list_objects_v2(self, **kwargs):
            calls.append(kwargs)
            return pages[len(calls) - 1]

    keys = radar_spool.list_r2_keys(_PagedR2(), "prefix/")

    assert keys == ["a.json", "b.json"]
    assert "ContinuationToken" not in calls[0]
    assert calls[1].get("ContinuationToken") == "t1"


def test_truncation_failure_surfaces_through_resolve_radar_spool_as_a_visible_error() -> None:
    result = sources_mod.resolve_radar_spool(None, s3=_BadPaginationR2())
    assert result.backend == "r2"
    assert result.error is not None
    assert "no usable NextContinuationToken" in result.error


# ---------------------------------------------------------------------------
# Review round 2 — S3: the local reader must not be polluted by Radar's OWN
# sibling nomination spool sharing the same local root in production.
# ---------------------------------------------------------------------------
def test_resolve_radar_spool_ignores_nomination_objects_sharing_the_local_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "shared_spool_root"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(root, session="2026-08-19", stamp="100000-p1", envelope=env)
    # A legitimate NOMINATION object at Radar's real sibling prefix -- same
    # local root, different schema (mastermind.entry_probe_nomination_spool.v1).
    nom_dir = root / "live_flow" / "entry_radar_nominations" / "2026-08-19"
    nom_dir.mkdir(parents=True)
    (nom_dir / "100500-hot_tape.json").write_text(json.dumps({
        "schema": "mastermind.entry_probe_nomination_spool.v1",
        "nominations": [],
    }), encoding="utf-8")

    result = sources_mod.resolve_radar_spool(root)

    assert result.backend == "local"
    assert len(result.envelopes) == 1
    # The nomination object must never even be WALKED -- envelopes_skipped
    # must stay a genuine signal, never permanently polluted by a sibling
    # spool family sharing the same root.
    assert result.envelopes_skipped == 0
    assert result.files_seen == 1


# ---------------------------------------------------------------------------
# Review round 2 — S4: an R2 list that succeeds with zero keys still
# discloses exactly what was queried, so an operator can check it.
# ---------------------------------------------------------------------------
def test_resolve_radar_spool_r2_empty_success_discloses_bucket_and_prefix(monkeypatch) -> None:
    monkeypatch.setenv("R2_BUCKET", "test-bucket")
    s3 = _FakeR2({})

    result = sources_mod.resolve_radar_spool(None, s3=s3)

    assert result.backend == "r2"
    assert result.envelopes == []
    assert result.error is None
    assert result.bucket == "test-bucket"
    assert result.prefix == sources_mod.RADAR_EVENT_SPOOL_PREFIX


def test_health_block_discloses_bucket_and_prefix_when_r2_resolves(monkeypatch) -> None:
    monkeypatch.setenv("R2_BUCKET", "test-bucket")
    s3 = _FakeR2({})
    monkeypatch.setattr(radar_spool, "r2_credentials_present", lambda: True)
    monkeypatch.setattr(radar_spool, "r2_client_for_read", lambda: s3)

    payload = build_lab_response(LabRoots())

    assert payload["health"]["radar_spool_bucket"] == "test-bucket"
    assert payload["health"]["radar_spool_prefix_queried"] == sources_mod.RADAR_EVENT_SPOOL_PREFIX


# ---------------------------------------------------------------------------
# Review round 2 — per-object GET failure counting (distinct from a total
# LIST failure): a partial read is visible via envelopes_skipped, not .error.
# ---------------------------------------------------------------------------
class _PartialGetFailureR2:
    def __init__(self, objects: dict[str, bytes], bad_keys: set[str]) -> None:
        self.objects = objects
        self.bad_keys = bad_keys

    def list_objects_v2(self, **kwargs):
        prefix = kwargs.get("Prefix", "")
        keys = sorted(k for k in self.objects if k.startswith(prefix))
        return {"Contents": [{"Key": k} for k in keys], "IsTruncated": False}

    def get_object(self, **kwargs):
        key = kwargs["Key"]
        if key in self.bad_keys:
            raise RuntimeError(f"GetObject denied for {key}")
        return {"Body": _Body(self.objects[key])}


def test_resolve_radar_spool_counts_per_object_get_failures_as_skipped_not_as_error() -> None:
    prefix = sources_mod.RADAR_EVENT_SPOOL_PREFIX
    good = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                     events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    good_key = f"{prefix}/2026-08-19/100000-p1.json"
    bad_key = f"{prefix}/2026-08-19/100500-p2.json"
    s3 = _PartialGetFailureR2(
        {good_key: json.dumps(good).encode("utf-8"), bad_key: b"irrelevant"},
        bad_keys={bad_key},
    )

    result = sources_mod.resolve_radar_spool(None, s3=s3)

    assert result.backend == "r2"
    assert result.error is None  # a per-object failure is NOT a list failure
    assert len(result.envelopes) == 1
    assert result.envelopes_skipped == 1
    assert result.files_seen == 2


# ---------------------------------------------------------------------------
# Review round 2 — S5: never silently overwrite an existing valid marker.
# ---------------------------------------------------------------------------
def test_baseline_cli_refuses_to_overwrite_an_existing_valid_marker_without_remint(
    tmp_path: Path, capsys,
) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(json.dumps({
        "schema": sources_mod.BASELINE_SCHEMA,
        "baseline_started_at": "2026-08-19T05:00:00Z",
    }), encoding="utf-8")
    original = baseline_path.read_text(encoding="utf-8")

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path), "--write",
    ])

    assert rc == 1
    assert baseline_path.read_text(encoding="utf-8") == original  # untouched
    err = capsys.readouterr().err
    assert "REFUSING" in err
    assert "--remint" in err


def test_baseline_cli_remint_overwrites_an_existing_valid_marker(tmp_path: Path) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(json.dumps({
        "schema": sources_mod.BASELINE_SCHEMA,
        "baseline_started_at": "2026-08-19T05:00:00Z",
    }), encoding="utf-8")

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-08-19T11:00:00Z", "--write",
        "--i-know-this-is-rehearsal", "--remint",
    ])

    assert rc == 0
    marker = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert marker["baseline_started_at"] == "2026-08-19T11:00:00.000000Z"


def test_baseline_cli_dry_run_does_not_need_remint_even_with_an_existing_marker(
    tmp_path: Path,
) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"
    baseline_path.parent.mkdir(parents=True)
    baseline_path.write_text(json.dumps({
        "schema": sources_mod.BASELINE_SCHEMA,
        "baseline_started_at": "2026-08-19T05:00:00Z",
    }), encoding="utf-8")

    rc = baseline_cli.main(["--spool-dir", str(spool), "--baseline-path", str(baseline_path)])

    assert rc == 0  # a dry run never touches the file, so no gate needed


# ---------------------------------------------------------------------------
# Review round 2 — S7: --as-of + --write requires --i-know-this-is-rehearsal.
# ---------------------------------------------------------------------------
def test_baseline_cli_as_of_plus_write_without_rehearsal_flag_is_refused(
    tmp_path: Path, capsys,
) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-08-19T11:00:00Z", "--write",
    ])

    assert rc == 1
    assert not baseline_path.exists()
    err = capsys.readouterr().err
    assert "REFUSING" in err
    assert "--i-know-this-is-rehearsal" in err


def test_baseline_cli_as_of_without_write_needs_no_rehearsal_flag(tmp_path: Path) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-08-19T11:00:00Z",  # dry run -- no --write
    ])

    assert rc == 0  # a dry run never mints, so no production-corruption risk


# ---------------------------------------------------------------------------
# Review round 2 — N1: skew disclosure/refusal (negative and implausible),
# and the post-write re-read consistency hard-fail.
# ---------------------------------------------------------------------------
def test_baseline_cli_prints_and_refuses_a_zero_skew(tmp_path: Path, capsys) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-08-19T10:00:00Z",  # exactly equal -- zero skew
    ])

    assert rc == 1
    out = capsys.readouterr()
    assert "now - latest_pass skew:" in out.out
    assert "CLOCK SKEW" in out.err


def test_baseline_cli_refuses_an_implausibly_large_skew(tmp_path: Path, capsys) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-09-19T10:00:00Z",  # a month later -- implausible
        "--write", "--i-know-this-is-rehearsal",
    ])

    assert rc == 1
    assert not baseline_path.exists()
    err = capsys.readouterr().err
    assert "REFUSING" in err
    assert "implausibly large" in err


def test_baseline_cli_prints_a_plausible_positive_skew_and_succeeds(
    tmp_path: Path, capsys,
) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-08-19T10:05:00Z",  # 5 minutes later -- the pack cadence
        "--write", "--i-know-this-is-rehearsal",
    ])

    assert rc == 0
    assert "now - latest_pass skew: 0:05:00" in capsys.readouterr().out


def test_baseline_cli_post_write_recheck_hard_fails_and_removes_the_marker_on_a_race(
    tmp_path: Path, capsys, monkeypatch,
) -> None:
    """N1: simulate the spool advancing DURING the write window -- a
    post-write re-read shows a pass at or after the just-minted
    baseline_started_at, so the CLI must remove the marker and hard-fail
    rather than leave a marker whose ordering guarantee is already stale."""
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    real_resolve = sources_mod.resolve_radar_spool
    calls = {"n": 0}

    def _racy_resolve(local_dir, **kwargs):
        calls["n"] += 1
        result = real_resolve(local_dir, **kwargs)
        if calls["n"] >= 2:
            # Simulate a NEW pass landing after the CLI's own read/write,
            # with a pass_ts AT the just-minted baseline_started_at.
            race_env = _envelope(
                pass_ts="2026-08-19T10:05:00Z", pass_id="p2",
                events=[_g0_event("evt-race", "BBB", signal_ts="2026-08-19T10:04:00Z")],
            )
            from dataclasses import replace as _replace
            result = _replace(result, envelopes=[*result.envelopes, race_env])
        return result

    monkeypatch.setattr(baseline_cli.sources, "resolve_radar_spool", _racy_resolve)

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-08-19T10:05:00Z", "--write", "--i-know-this-is-rehearsal",
    ])

    assert rc == 1
    assert not baseline_path.exists()  # removed after the hard-fail
    err = capsys.readouterr().err
    assert "HARD-FAIL" in err
    assert "removed" in err.lower() or "Removed" in err


def test_baseline_cli_post_write_recheck_passes_when_the_spool_is_quiet(
    tmp_path: Path,
) -> None:
    """The control: no race -> the marker survives the post-write re-read."""
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-08-19T10:05:00Z", "--write", "--i-know-this-is-rehearsal",
    ])

    assert rc == 0
    assert baseline_path.exists()
