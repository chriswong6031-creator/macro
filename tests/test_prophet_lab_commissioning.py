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
        "--as-of", "2026-08-19T11:00:00Z", "--write",
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
        "--write",
    ])

    assert rc == 1
    assert not baseline_path.exists()
    assert "REFUSING" in capsys.readouterr().err


def test_baseline_cli_refuses_a_naive_as_of_override(tmp_path: Path, capsys) -> None:
    spool = tmp_path / "spool"
    env = _envelope(pass_ts="2026-08-19T10:00:00Z", pass_id="p1",
                    events=[_g0_event("evt-1", "AAA", signal_ts="2026-08-19T09:55:00Z")])
    _write_pass(spool, session="2026-08-19", stamp="100000-p1", envelope=env)
    baseline_path = tmp_path / "state" / "observation_baseline.json"

    rc = baseline_cli.main([
        "--spool-dir", str(spool), "--baseline-path", str(baseline_path),
        "--as-of", "2026-08-19T12:00:00",  # naive -- no offset, must be refused
        "--write",
    ])

    assert rc == 1
    assert not baseline_path.exists()
    assert "REFUSING" in capsys.readouterr().err


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
        "--as-of", t1, "--write",
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
