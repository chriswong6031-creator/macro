"""Tests for scripts/build_flow_archive — the dated tide/dte_tide R2 archives (OIP W0 T-lane).

The current keys (`live_flow/tide_current.json`, `live_flow/dte_tide_current.json`) are
overwritten every poller cycle, so the session's story used to die at the close. This lane
queues a SECOND, date-keyed R2 key for the SAME local files plus a per-family sessions
index, so the day's final write is the settled record the nightly Session Digest reads.

Invariants pinned here (OIP masterplan §6 E1 / §7, CLAUDE.md §Ledgers):

  (a) key shapes are exact, and a malformed family or session_date RAISES rather than
      creating a junk prefix the retention prune would never recognize;
  (b) the dated key points at the SAME local file as the current key — one write, two keys,
      so the live copy and the archive can never disagree byte-for-byte;
  (c) dates.json shape + newest-first/dedupe/trim/junk-drop law, and HEAL-NOW: a missing or
      corrupt index is rebuilt AND re-queued in the same cycle (a `--once` run must never
      defer its heal to a cycle that will not run — #3499 / #F3-04);
  (d) idempotence: re-running a cycle for the same session re-queues the same keys and
      leaves a single date in the index;
  (e) retention boundary: exactly the newest N sessions survive, and the prune NEVER touches
      dates.json or a current key (`live_flow/tide_current.json` prefix-matches
      `live_flow/tide` — the trailing slash in family_prefix is load-bearing);
  (f) fail-soft: an R2 error, a bad date, or an unwritable family degrades the lane without
      raising and without costing the other family its keys;
  (g) the poller loop really calls the new writers, uploads what they return, and writes
      ZERO `data/` artifacts (intraday law §0.9).
"""
from __future__ import annotations

import json

import pytest

from scripts.build_flow_archive import (
    ARCHIVE_DATES_NAME,
    ARCHIVE_FAMILIES,
    ARCHIVE_RETAIN_SESSIONS,
    DTE_TIDE_FAMILY,
    TIDE_FAMILY,
    archive_out_dir,
    build_archive_dates_index,
    dated_archive_key,
    dates_index_key,
    family_prefix,
    is_archive_dates,
    list_archive_session_dates,
    load_dates_ledger,
    merge_archive_dates,
    prune_archive_dates,
    stage_dated_archives,
)

SESSION = "2026-07-29"


@pytest.fixture
def staged(tmp_path, monkeypatch):
    """Redirect data_dir() at the staging root so nothing touches the real data/ tree."""
    import lib.config as cfg_mod

    monkeypatch.setattr(cfg_mod, "data_dir", lambda: tmp_path)
    return tmp_path


def _mk_payloads(tmp_path, *, tide=None, dte=None):
    """Write two stand-in current-key files (the poller's _write_json output)."""
    out = tmp_path / "live_flow_out"
    out.mkdir(parents=True, exist_ok=True)
    t = out / "tide_current.json"
    d = out / "dte_tide_current.json"
    t.write_text(json.dumps(tide or {"schema": "live_flow.tide/v1", "minutes": [{"t": "09:31"}]}))
    d.write_text(json.dumps(dte or {"schema": "live_flow.dte_tide/v1", "buckets": {"0d": []}}))
    return t, d


# ── (a) key shapes + malformed inputs raise ─────────────────────────────────────────

def test_key_shapes_are_exact():
    assert dated_archive_key(TIDE_FAMILY, SESSION) == "live_flow/tide/2026-07-29.json"
    assert dated_archive_key(DTE_TIDE_FAMILY, SESSION) == "live_flow/dte_tide/2026-07-29.json"
    assert dates_index_key(TIDE_FAMILY) == "live_flow/tide/dates.json"
    assert dates_index_key(DTE_TIDE_FAMILY) == "live_flow/dte_tide/dates.json"
    assert ARCHIVE_FAMILIES == ("tide", "dte_tide")
    # §7: retention must be at least 30 sessions for these families.
    assert ARCHIVE_RETAIN_SESSIONS >= 30


def test_family_prefix_carries_the_trailing_slash():
    # Without it, `live_flow/tide` also prefix-matches live_flow/tide_current.json — the
    # object the live Terminal reads. Every list/delete goes through this function.
    for fam in ARCHIVE_FAMILIES:
        assert family_prefix(fam) == f"live_flow/{fam}/"
        assert family_prefix(fam).endswith("/")
    assert not "live_flow/tide_current.json".startswith(family_prefix(TIDE_FAMILY))


def test_malformed_date_or_family_raises():
    for bad in ("2026-7-29", "20260729", "", "today", None, "2026-07-2"):
        with pytest.raises(ValueError):
            dated_archive_key(TIDE_FAMILY, bad)
    for bad_fam in ("tide/", "TIDE", "events", "", None, "tide_current"):
        with pytest.raises(ValueError):
            dated_archive_key(bad_fam, SESSION)
        with pytest.raises(ValueError):
            family_prefix(bad_fam)


# ── (b) one write, two keys ─────────────────────────────────────────────────────────

def test_dated_keys_reuse_the_current_key_files(staged):
    tide_p, dte_p = _mk_payloads(staged)
    pairs = stage_dated_archives(
        paths_by_family={TIDE_FAMILY: tide_p, DTE_TIDE_FAMILY: dte_p},
        session_date=SESSION, asof="2026-07-29T20:01:00Z", cadence_sec=120,
    )
    by_key = {k: p for p, k in pairs}
    assert set(by_key) == {
        "live_flow/tide/2026-07-29.json",
        "live_flow/dte_tide/2026-07-29.json",
        "live_flow/tide/dates.json",
        "live_flow/dte_tide/dates.json",
    }
    # The dated copy IS the file the poller already wrote for the current key — no
    # re-serialization, so the archive can never drift from the live payload.
    assert by_key["live_flow/tide/2026-07-29.json"] == tide_p
    assert by_key["live_flow/dte_tide/2026-07-29.json"] == dte_p
    # …and the payload is untouched full-session content.
    assert json.loads(tide_p.read_text())["schema"] == "live_flow.tide/v1"


def test_missing_payload_is_skipped_not_queued(staged):
    tide_p, _ = _mk_payloads(staged)
    ghost = staged / "live_flow_out" / "never_written.json"
    pairs = stage_dated_archives(
        paths_by_family={TIDE_FAMILY: tide_p, DTE_TIDE_FAMILY: ghost},
        session_date=SESSION, asof="a", cadence_sec=120,
    )
    keys = {k for _, k in pairs}
    # A missing file must not be queued (it would warn once a cycle forever); the healthy
    # family still gets its keys.
    assert "live_flow/dte_tide/2026-07-29.json" not in keys
    assert "live_flow/tide/2026-07-29.json" in keys


# ── (c) dates.json shape + heal-now ─────────────────────────────────────────────────

def test_dates_index_shape(staged):
    tide_p, dte_p = _mk_payloads(staged)
    pairs = stage_dated_archives(
        paths_by_family={TIDE_FAMILY: tide_p, DTE_TIDE_FAMILY: dte_p},
        session_date=SESSION, asof="2026-07-29T20:01:00Z", cadence_sec=300,
    )
    local = next(p for p, k in pairs if k == "live_flow/tide/dates.json")
    doc = json.loads(local.read_text())
    assert is_archive_dates(doc)
    assert doc["schema"] == "live_flow.archive_dates/v1"
    assert doc["family"] == "tide"
    assert doc["dates"] == [SESSION] and doc["latest"] == SESSION and doc["count"] == 1
    assert doc["retain"] == ARCHIVE_RETAIN_SESSIONS
    # Cadence honesty: verbatim from the true write interval.
    assert doc["cadenceSec"] == 300 and doc["cadence"] == "5-min"
    assert doc["asof"] == "2026-07-29T20:01:00Z" and doc["source"] == "poller"


def test_dates_index_newest_first_deduped_trimmed_junk_dropped():
    doc = build_archive_dates_index(
        TIDE_FAMILY,
        ["2026-07-27", "2026-07-29", "2026-07-28", "2026-07-29", "", None, "07/29/2026",
         "2026-07-2", "latest"],
        cadence_sec=120, asof="a", retain=2,
    )
    assert doc["dates"] == ["2026-07-29", "2026-07-28"]
    assert doc["latest"] == "2026-07-29" and doc["count"] == 2
    assert is_archive_dates(doc)


def test_dates_index_empty_latest_is_null():
    doc = build_archive_dates_index(TIDE_FAMILY, [], cadence_sec=120, asof="")
    assert doc["dates"] == [] and doc["latest"] is None and doc["count"] == 0
    assert is_archive_dates(doc)


def test_is_archive_dates_rejects_bad_docs():
    good = build_archive_dates_index(TIDE_FAMILY, ["2026-07-29", "2026-07-28"],
                                     cadence_sec=120, asof="")
    assert is_archive_dates(good)
    assert not is_archive_dates({**good, "dates": ["2026-07-28", "2026-07-29"]})  # oldest 1st
    assert not is_archive_dates({**good, "latest": "2026-07-28"})                 # != dates[0]
    assert not is_archive_dates({**good, "dates": ["not-a-date"]})
    assert not is_archive_dates({**good, "cadenceSec": "120"})
    assert not is_archive_dates({**good, "family": "nope"})
    assert not is_archive_dates([])


def test_corrupt_index_heals_in_the_same_cycle(staged):
    tide_p, dte_p = _mk_payloads(staged)
    # A truncated / garbage dates.json on disk (the droplet-redeploy or half-write case).
    bad = archive_out_dir(TIDE_FAMILY) / ARCHIVE_DATES_NAME
    bad.write_text("{not json at all")
    assert load_dates_ledger(TIDE_FAMILY) == []      # tolerated, not raised

    pairs = stage_dated_archives(
        paths_by_family={TIDE_FAMILY: tide_p, DTE_TIDE_FAMILY: dte_p},
        session_date=SESSION, asof="a", cadence_sec=120,
    )
    # Healed on disk NOW…
    doc = json.loads(bad.read_text())
    assert is_archive_dates(doc) and doc["dates"] == [SESSION]
    # …AND queued for upload in THIS cycle, so a --once run leaves R2 correct.
    assert (bad, "live_flow/tide/dates.json") in pairs


def test_missing_index_is_written_and_queued_every_cycle(staged):
    tide_p, dte_p = _mk_payloads(staged)
    for _ in range(2):
        pairs = stage_dated_archives(
            paths_by_family={TIDE_FAMILY: tide_p, DTE_TIDE_FAMILY: dte_p},
            session_date=SESSION, asof="a", cadence_sec=120,
        )
        # dates.json is re-queued on EVERY cycle, not just the first — the heal never waits.
        assert sum(1 for _, k in pairs if k.endswith("/dates.json")) == len(ARCHIVE_FAMILIES)


# ── (d) idempotence ─────────────────────────────────────────────────────────────────

def test_repeated_cycles_are_idempotent(staged):
    tide_p, dte_p = _mk_payloads(staged)
    runs = [
        stage_dated_archives(
            paths_by_family={TIDE_FAMILY: tide_p, DTE_TIDE_FAMILY: dte_p},
            session_date=SESSION, asof=f"asof-{i}", cadence_sec=120)
        for i in range(3)
    ]
    assert {k for _, k in runs[0]} == {k for _, k in runs[-1]}     # same keys every cycle
    doc = json.loads((archive_out_dir(TIDE_FAMILY) / ARCHIVE_DATES_NAME).read_text())
    assert doc["dates"] == [SESSION]                              # one date, not three
    assert doc["asof"] == "asof-2"                                # freshest stamp wins


def test_second_session_accumulates(staged):
    tide_p, dte_p = _mk_payloads(staged)
    for d in ("2026-07-28", "2026-07-29"):
        stage_dated_archives(paths_by_family={TIDE_FAMILY: tide_p, DTE_TIDE_FAMILY: dte_p},
                             session_date=d, asof="a", cadence_sec=120)
    doc = json.loads((archive_out_dir(TIDE_FAMILY) / ARCHIVE_DATES_NAME).read_text())
    assert doc["dates"] == ["2026-07-29", "2026-07-28"] and doc["latest"] == "2026-07-29"


# ── (e) retention boundary + never touching the live keys ────────────────────────────

class _FakeS3:
    """Minimal list_objects_v2 / delete_objects double over an in-memory key set."""

    def __init__(self, keys):
        self.keys = set(keys)
        self.deleted: list[str] = []

    def list_objects_v2(self, **kw):
        prefix = kw["Prefix"]
        delim = kw.get("Delimiter")
        contents = []
        for k in sorted(self.keys):
            if not k.startswith(prefix):
                continue
            if delim and delim in k[len(prefix):]:
                continue          # a nested "directory" — R2 would return a CommonPrefix
            contents.append({"Key": k})
        return {"Contents": contents, "IsTruncated": False}

    def delete_objects(self, **kw):
        for o in kw["Delete"]["Objects"]:
            self.keys.discard(o["Key"])
            self.deleted.append(o["Key"])
        return {}


def _store(n_sessions, family=TIDE_FAMILY):
    days = [f"2026-06-{d:02d}" for d in range(1, n_sessions + 1)]
    keys = [f"live_flow/{family}/{d}.json" for d in days]
    keys += [
        f"live_flow/{family}/dates.json",
        "live_flow/tide_current.json",          # the LIVE key the Terminal reads
        "live_flow/dte_tide_current.json",
        "live_flow/feed_current.json",
        f"live_flow/{family}/junk.json",        # not a session date
        f"live_flow/surface/SPY/2026-06-01/idx.json",
    ]
    return _FakeS3(keys), days


def test_list_session_dates_ignores_index_and_junk():
    s3, days = _store(3)
    got = list_archive_session_dates(s3, "b", TIDE_FAMILY)
    assert got == sorted(days, reverse=True)
    assert "dates" not in got and "junk" not in got


def test_prune_keeps_newest_n_exactly():
    s3, days = _store(35)
    res = prune_archive_dates(s3, "b", TIDE_FAMILY, keep=30)
    assert res["ok"] is True
    assert len(res["retained"]) == 30
    assert res["retained"] == sorted(days, reverse=True)[:30]
    assert sorted(res["deleted_dates"]) == sorted(days)[:5]      # the 5 oldest
    assert res["deleted_objects"] == 5
    # Boundary: the 30th-newest survives, the 31st does not.
    kept = sorted(days, reverse=True)
    assert f"live_flow/tide/{kept[29]}.json" in s3.keys
    assert f"live_flow/tide/{kept[30]}.json" not in s3.keys


def test_prune_never_touches_the_current_keys_or_the_index():
    s3, _ = _store(40)
    prune_archive_dates(s3, "b", TIDE_FAMILY, keep=30)
    for survivor in ("live_flow/tide_current.json", "live_flow/dte_tide_current.json",
                     "live_flow/feed_current.json", "live_flow/tide/dates.json",
                     "live_flow/tide/junk.json",
                     "live_flow/surface/SPY/2026-06-01/idx.json"):
        assert survivor in s3.keys, f"prune deleted {survivor}"
    assert all(d.startswith("live_flow/tide/2026-") for d in s3.deleted)


def test_prune_noop_when_within_retention():
    s3, _ = _store(10)
    res = prune_archive_dates(s3, "b", TIDE_FAMILY, keep=30)
    assert res["ok"] is True and res["deleted_dates"] == [] and res["deleted_objects"] == 0


def test_prune_is_fail_soft_on_r2_error():
    class Boom:
        def list_objects_v2(self, **kw):
            raise RuntimeError("R2 down")

    res = prune_archive_dates(Boom(), "b", TIDE_FAMILY, keep=30)
    assert res == {"ok": False, "retained": [], "deleted_dates": [], "deleted_objects": 0}


def test_prune_is_fail_soft_on_delete_error():
    s3, _ = _store(35)

    def boom(**kw):
        raise RuntimeError("delete denied")

    s3.delete_objects = boom
    res = prune_archive_dates(s3, "b", TIDE_FAMILY, keep=30)
    assert res["ok"] is False          # caller retries next session
    assert len(s3.keys) == 35 + 6      # nothing lost


def test_prune_retain_override_trims_the_index(staged):
    s3, days = _store(12)
    res = prune_archive_dates(s3, "b", TIDE_FAMILY, keep=5)
    kept = merge_archive_dates(TIDE_FAMILY, res["retained"], cadence_sec=120, asof="a",
                               retain=5)
    assert len(kept) == 5
    doc = json.loads((archive_out_dir(TIDE_FAMILY) / ARCHIVE_DATES_NAME).read_text())
    assert doc["dates"] == sorted(days, reverse=True)[:5] and doc["retain"] == 5


def test_merge_heals_ledger_from_r2_truth(staged):
    # Staging wiped (host redeploy): the local ledger knows nothing, R2 knows 8 sessions.
    s3, days = _store(8)
    assert load_dates_ledger(TIDE_FAMILY) == []
    res = prune_archive_dates(s3, "b", TIDE_FAMILY, keep=30)
    kept = merge_archive_dates(TIDE_FAMILY, res["retained"], cadence_sec=120, asof="a")
    assert kept == sorted(days, reverse=True)
    # The healed file lands at the EXACT local path the poller uploads from.
    healed = archive_out_dir(TIDE_FAMILY) / ARCHIVE_DATES_NAME
    assert healed.exists() and is_archive_dates(json.loads(healed.read_text()))


# ── (f) fail-soft staging ───────────────────────────────────────────────────────────

def test_bad_session_date_degrades_without_raising(staged):
    tide_p, dte_p = _mk_payloads(staged)
    pairs = stage_dated_archives(
        paths_by_family={TIDE_FAMILY: tide_p, DTE_TIDE_FAMILY: dte_p},
        session_date="2026-7-29", asof="a", cadence_sec=120,
    )
    assert pairs == []          # nothing queued, nothing raised


def test_unknown_family_in_the_map_is_ignored(staged):
    tide_p, _ = _mk_payloads(staged)
    pairs = stage_dated_archives(
        paths_by_family={TIDE_FAMILY: tide_p, "events": tide_p, "junk": tide_p},
        session_date=SESSION, asof="a", cadence_sec=120,
    )
    assert {k for _, k in pairs} == {"live_flow/tide/2026-07-29.json",
                                     "live_flow/tide/dates.json"}


def test_ledger_merge_failure_returns_prior_list(staged, monkeypatch):
    import scripts.build_flow_archive as mod

    tide_p, dte_p = _mk_payloads(staged)
    stage_dated_archives(paths_by_family={TIDE_FAMILY: tide_p, DTE_TIDE_FAMILY: dte_p},
                         session_date="2026-07-28", asof="a", cadence_sec=120)
    monkeypatch.setattr(mod, "stage_dates_index",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("read-only fs")))
    # Must not raise, and must not lose what was already recorded.
    assert merge_archive_dates(TIDE_FAMILY, [SESSION], cadence_sec=120,
                               asof="a") == ["2026-07-28"]


# ── (g) the poller loop really wires this up, and writes zero data/ artifacts ────────

def test_poller_calls_the_archive_writers_and_uploads_them():
    """The names the poller imports must exist, and the loop must upload what it stages."""
    import inspect

    import scripts.build_flow_archive as mod
    import scripts.live_flow_poller as poller

    src = inspect.getsource(poller.main)
    assert "stage_dated_archives" in src, "poller no longer stages dated archives"
    assert "archive_paths" in src and "for arch_local, arch_r2_key in archive_paths" in src, \
        "staged archive keys are not uploaded"
    assert "prune_archive_dates" in src, "no retention sweep wired"
    assert "last_archive_prune_date" in src, "retention sweep is not once-per-session"
    # Every symbol the poller imports from the module resolves (an ImportError inside the
    # fenced block would silently disable the whole lane).
    for name in ("ARCHIVE_DATES_NAME", "ARCHIVE_FAMILIES", "ARCHIVE_RETAIN_SESSIONS",
                 "DTE_TIDE_FAMILY", "TIDE_FAMILY", "archive_out_dir", "dates_index_key",
                 "merge_archive_dates", "prune_archive_dates", "stage_dated_archives"):
        assert hasattr(mod, name), f"poller imports missing symbol {name}"


def test_session_date_is_the_pollers_et_session_not_a_utc_pin():
    """§0.11: the dated key derives from the poller's ET session_date, never a UTC clock."""
    import inspect

    import scripts.build_flow_archive as mod
    import scripts.live_flow_poller as poller

    # The poller's own session date is ET-derived…
    assert "datetime.now(ET)" in inspect.getsource(poller._session_date)
    # …and this module never reads a clock at all: it can only use what it is handed.
    src = inspect.getsource(mod)
    for banned in ("utcnow", "datetime.now", "time.time", "timezone.utc"):
        assert banned not in src, f"archive module reads a clock ({banned})"


class _RecordingS3:
    """Records upload_file keys; list/delete behave like an empty store."""

    def __init__(self):
        self.puts: list[str] = []

    def upload_file(self, local, bucket, key, **kw):      # noqa: ARG002
        assert __import__("pathlib").Path(local).exists(), f"PUT of missing file {local}"
        self.puts.append(key)

    def list_objects_v2(self, **kw):                      # noqa: ARG002
        return {"Contents": [], "IsTruncated": False}

    def delete_objects(self, **kw):                       # noqa: ARG002
        return {}


def test_once_cycle_uploads_the_dated_keys_and_stays_out_of_data(staged, monkeypatch):
    """A real `--once` main() cycle: dated keys are PUT, and no data/ artifact is created.

    Drives the poller loop with a synthetic run_cycle (no ThetaData, no network) and a
    recording S3 double, so this pins the WIRING — that the loop stages the archives, uploads
    what it staged, and sweeps retention once — not just the pure functions.
    """
    import scripts.live_flow_poller as poller
    from collectors import thetadata as td
    from lib import store as store_mod

    s3 = _RecordingS3()
    asof = "2026-07-29T20:01:00Z"
    monkeypatch.setattr(td, "reachable", lambda **kw: True)
    # run_status registration (pre-existing, unrelated to this lane) resolves through
    # config.ROOT rather than data_dir(), so stub it to keep the smoke hermetic.
    monkeypatch.setattr(store_mod, "read_status", lambda: {})
    monkeypatch.setattr(store_mod, "write_status", lambda status: None)
    monkeypatch.setattr(poller, "_r2_client", lambda: s3)
    monkeypatch.setattr(poller, "_load_baselines", lambda: {})
    monkeypatch.setattr(poller, "_load_unusual_baseline", lambda: {})
    monkeypatch.setenv("R2_BUCKET", "test-bucket")

    tide_state = {
        "market_tide_minutes": {"09:31": {"ncp": 1.0, "npp": -2.0, "gross": 3.0, "vol": 4},
                                "09:32": {"ncp": 2.0, "npp": -1.0, "gross": 5.0, "vol": 6}},
        "sector_tide": {"Index/ETF": {"group": "Index/ETF", "group_zh": "指数",
                                      "ncp": 3.0, "npp": -3.0, "gross": 8.0,
                                      "minutes": {"09:31": {"ncp": 1.0, "npp": -2.0}}}},
        "dte_tide": {"0d": {"09:31": {"ncp": 1.0, "npp": -1.0}}},
        "root_gross_today": {"SPY": 8.0},
        "root_minutes": {"SPY": {"09:31": {"ncp": 1.0, "npp": -2.0, "vol": 4}}},
        "root_strikes": {}, "root_expiries": {}, "root_top_contracts": {},
        "surface_quotes": {}, "surface_spot_fallback": {},
    }
    meta = {"asof": asof, "roots_polled": 1, "universe_n": 1, "cycle_sec": 1.0}
    monkeypatch.setattr(poller, "run_cycle", lambda **kw: (
        {"asof": asof, "events": [], "unusual_names": []},
        {"groups": []}, meta, {}, tide_state))

    rc = poller.main(["--once", "--date", SESSION, "--roots", "SPY"])
    assert rc == 0

    # The current keys are still PUT, unchanged…
    assert "live_flow/tide_current.json" in s3.puts
    assert "live_flow/dte_tide_current.json" in s3.puts
    # …and the dated archives + both sessions indexes went up in the SAME cycle.
    for key in ("live_flow/tide/2026-07-29.json", "live_flow/dte_tide/2026-07-29.json",
                "live_flow/tide/dates.json", "live_flow/dte_tide/dates.json"):
        assert key in s3.puts, f"{key} not uploaded by a --once cycle"

    # The archived bytes ARE the current-key bytes (one write, two keys).
    out = staged / "live_flow_out"
    tide_doc = json.loads((out / "tide_current.json").read_text())
    assert tide_doc["schema"] == "live_flow.tide/v1"
    assert len(tide_doc["minutes"]) == 2          # full-session cumulative series present
    assert tide_doc["minutes"][-1]["ncp"] == 3.0  # cumulated, not instantaneous

    # Intraday law (§0.9): this lane adds NOTHING to data/ beyond the gitignored staging
    # dir. Nothing new outside live_flow_out/ + the poller's pre-existing state/status.
    top = {p.relative_to(staged).parts[0] for p in staged.rglob("*") if p.is_file()}
    assert top <= {"live_flow_out", "live_flow_state"}, \
        f"cycle wrote unexpected data/ entries: {top}"
    assert not list(staged.rglob("*.parquet"))
    # Every file the archive lane itself created is inside the staging dir.
    for fam in ARCHIVE_FAMILIES:
        assert (out / fam / ARCHIVE_DATES_NAME).exists()


def test_archive_lane_writes_zero_data_artifacts(staged):
    """Intraday law (§0.9 / CLAUDE.md §Ledgers): staging + R2 only, never a data/ store."""
    tide_p, dte_p = _mk_payloads(staged)
    stage_dated_archives(paths_by_family={TIDE_FAMILY: tide_p, DTE_TIDE_FAMILY: dte_p},
                         session_date=SESSION, asof="a", cadence_sec=120)
    written = {p.relative_to(staged).parts[0] for p in staged.rglob("*") if p.is_file()}
    # Everything this lane touches lives under the gitignored live_flow_out/ staging dir.
    assert written == {"live_flow_out"}, f"lane wrote outside staging: {written}"
    for fam in ARCHIVE_FAMILIES:
        assert (staged / "live_flow_out" / fam / ARCHIVE_DATES_NAME).exists()
