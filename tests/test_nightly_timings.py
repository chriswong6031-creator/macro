"""W2 nightly runtime telemetry (masterplan §0.2 acceptance gate).

Two halves:

1. BEHAVIOR — scripts/nightly_timings.py: a synthetic run at 86% of its cap
   MUST trip the ``::warning`` (at line start — GitHub parses ``::`` only at
   column 0), an 84% run must NOT, bands are computed from the marks, and dark
   telemetry (no start stamp) is loud instead of silently recording nothing.

2. WIRING — .github/workflows/daily.yml AND .github/workflows/asia-close.yml:
   every instrumentable self-hosted job carries the job-start mark as its FIRST
   step and the ``if: always()`` finish step LAST (bar the delivery tail below),
   and the finish step's cap argument equals the job's actual
   ``timeout-minutes``. This is the anti-drift pin: raising a cap without
   updating the finish arg would silently rescale the 85% tripwire (the same
   stale-label class that produced the tech_lab 8-day outage). asia-close joined
   the scan for W-L4 gate 1: its ``asia`` job spends 46.1m of adapter wall-clock
   (55 sources, measured 2026-08-09) in no timings band on any job.

3. PERSISTENCE — the row has to survive the night it is most needed. `always()`
   is not enough on its own: a timeout-cancel gives the whole remaining
   always() tail one ~5-minute grace window, so a finish step parked behind a
   heavy delivery step never gets scheduled. That is exactly what happened to
   the engine job (run 31067383446, 2026-08-06: cancelled at 200m cap + 5m
   grace, `upload pages artifact` ended `failure` at the wall, and the finish
   step never appeared in the step list at all) — 15 of 16 jobs had native rows
   and engine had a single `backfill-gh-api` one, leaving the 85% tripwire dark
   for the one job whose creep caused the Jul31-Aug6 outage. The tests below
   pin the ordering that fixes it and the loudness of every early exit in
   scripts/ci/nightly_timings_finish.sh.

Run: .venv/bin/python -m pytest tests/test_nightly_timings.py -q
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from scripts import nightly_timings as nt
from scripts import nightly_timings_report as ntr

ROOT = Path(__file__).resolve().parent.parent
DAILY = ROOT / ".github" / "workflows" / "daily.yml"
ASIA = ROOT / ".github" / "workflows" / "asia-close.yml"
FINISH_SH = ROOT / "scripts" / "ci" / "nightly_timings_finish.sh"

#: Every workflow whose self-hosted jobs carry the W2 wiring. The wiring tests are
#: parametrised over this tuple rather than duplicated per file, so a new nightly
#: lane opts in by adding its path here — and until it does, its jobs are simply
#: unscanned rather than silently "passing".
INSTRUMENTED_WORKFLOWS = (DAILY, ASIA)

START_STEP_NAME = "timings — job start mark (W2)"
FINISH_STEP_NAME = "timings ledger + 85% budget tripwire (W2)"

#: The instrumented job set, pinned BY NAME per workflow.
#:
#: ``_instrumented()`` is a PREDICATE, and a predicate that stops matching reads
#: exactly like a clean run: every assertion below iterates the jobs it returns,
#: so narrowing it to nothing would turn the whole wiring suite green while the
#: nightly went dark. That is the same shape as the tech_lab outage this module
#: exists to prevent — a tripwire that is quiet because it can no longer see.
#: These sets are the floor: they may grow when a lane is instrumented, and a
#: SHRINK is a defect until the name is deleted here on purpose.
DAILY_INSTRUMENTED_JOBS = frozenset({
    "active_build_map", "capital_structure", "causal", "collect", "collect_tail",
    "cortex", "engine", "factor_panel", "factor_series", "ledger_heartbeat",
    "oracle_offrender", "standout_audit_us", "stock_briefs", "tech_lab_offrender",
    "us_prophet_ledgers", "us_scan_tier",
})
#: `ths_rescrape` (GMI W1a) is the weekly 同花顺 re-scrape: self-hosted, capped, and
#: job-level skipped on the six non-Saturday days, so it appends a ledger row only on
#: the days it actually runs — which is precisely the cadence its cap needs measuring at.
ASIA_INSTRUMENTED_JOBS = frozenset({"asia", "ths_rescrape"})
EXPECTED_INSTRUMENTED = {DAILY: DAILY_INSTRUMENTED_JOBS, ASIA: ASIA_INSTRUMENTED_JOBS}

#: The ONLY steps allowed to follow the finish step, and only because they are
#: pure artifact DELIVERY: no engine work happens in them, so the timings row
#: loses nothing by being written first, and a cancel night sacrifices them
#: anyway. Add to this set only with the same reasoning written down — anything
#: else scheduled after the finish step re-creates the silent-loss shape.
DELIVERY_TAIL_STEPS = frozenset({
    "strip heavy per-ticker stores from the Pages artifact (served from R2 now)",
    "upload pages artifact",
})


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("NIGHTLY_TIMINGS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("GITHUB_JOB", "engine")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("RUNNER_NAME", "mac-builder-test")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    # Hermetic in DATA: no test may read the repo's real data/run_status.json.
    # Tests that exercise attribution pass their own fixture path explicitly.
    monkeypatch.setattr(nt, "DEFAULT_RUN_STATUS", tmp_path / "no-such-run-status.json")
    (tmp_path / "state").mkdir()
    return tmp_path


def _write_start(seconds_ago: float, now: float = 1_800_000_000.0) -> float:
    nt.start_path().parent.mkdir(parents=True, exist_ok=True)
    nt.start_path().write_text(str(now - seconds_ago))
    return now


# ---------------------------------------------------------------------------
# behavior
# ---------------------------------------------------------------------------

def test_synthetic_86_percent_run_trips_the_warning(env, capsys):
    """Masterplan §0.2 gate: a synthetic 86% run trips the ::warning."""
    cap = 240.0
    now = _write_start(seconds_ago=0.86 * cap * 60)
    row = nt.cmd_finish(cap, env / "ledger", now=now)
    assert row["pct_of_cap"] == pytest.approx(86.0, abs=0.2)
    out = capsys.readouterr().out
    warn = [l for l in out.splitlines() if l.startswith("::warning")]
    assert len(warn) == 1, f"expected exactly one line-start ::warning, got: {out!r}"
    # column 0 is what GitHub parses — a prefixed line would ship a dead alarm
    assert warn[0].startswith("::warning title=nightly budget 85% tripwire::")
    assert "engine" in warn[0] and "86%" in warn[0]


def test_84_percent_run_does_not_warn(env, capsys):
    cap = 240.0
    now = _write_start(seconds_ago=0.84 * cap * 60)
    row = nt.cmd_finish(cap, env / "ledger", now=now)
    assert row["pct_of_cap"] == pytest.approx(84.0, abs=0.2)
    out = capsys.readouterr().out
    assert not [l for l in out.splitlines() if l.startswith("::warning")]
    assert "nightly-timings: engine elapsed" in out  # the plain trend line still prints


def test_ledger_row_appends_per_job_file(env):
    now = _write_start(seconds_ago=600)
    nt.cmd_finish(200.0, env / "ledger", now=now)
    nt.cmd_finish(200.0, env / "ledger", now=now + 60)
    path = env / "ledger" / "engine.jsonl"
    rows = [json.loads(l) for l in path.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["job"] == "engine"
    assert rows[0]["cap_minutes"] == 200.0
    assert rows[0]["elapsed_minutes"] == pytest.approx(10.0, abs=0.1)
    assert rows[0]["run_id"] == "12345"
    assert rows[0]["runner"] == "mac-builder-test"


def test_bands_computed_from_marks(env):
    now = 1_800_000_000.0
    _write_start(seconds_ago=1000, now=now)
    nt.cmd_mark("engine-core", now=now - 700)
    nt.cmd_mark("builders-parallel", now=now - 250)
    row = nt.cmd_finish(240.0, env / "ledger", now=now)
    assert row["bands"] == [
        {"band": "startup", "seconds": 300},
        {"band": "engine-core", "seconds": 450},
        {"band": "builders-parallel", "seconds": 250},
    ]


def test_dark_telemetry_is_loud_not_silent(env, capsys):
    """No start stamp + no marks = a row with null elapsed AND a ::warning.

    A tripwire that silently records nothing is the failure mode W2 exists to
    end (tech_lab's cap cancelled its own alarm step for 8 straight nights)."""
    row = nt.cmd_finish(240.0, env / "ledger", now=1_800_000_000.0)
    assert row["elapsed_minutes"] is None
    assert row["telemetry"] == "dark"
    out = capsys.readouterr().out
    warn = [l for l in out.splitlines() if l.startswith("::warning")]
    assert len(warn) == 1 and "title=nightly timings dark" in warn[0]
    # the row still lands, so the dark night is visible in the ledger too
    assert (env / "ledger" / "engine.jsonl").exists()


def test_missing_start_falls_back_to_first_mark(env):
    now = 1_800_000_000.0
    nt.cmd_mark("collectors", now=now - 900)
    row = nt.cmd_finish(240.0, env / "ledger", now=now)
    assert row["elapsed_minutes"] == pytest.approx(15.0, abs=0.1)
    assert row["bands"] == [{"band": "collectors", "seconds": 900}]


# ---------------------------------------------------------------------------
# W-L1 — per-source attribution (research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md
# §4 W-L1, §0 W-L4 gate 1)
#
# HERMETIC IN DATA, NOT IN TIME. Every stamp below is derived from a base epoch
# taken at test time, so these fixtures cannot become clock bombs the way a
# hardcoded "2026-08-09T05:35:57+00:00" would (16 such fixtures were defused
# tree-wide on 2026-08-09). The assertions are on DURATIONS and membership;
# nothing here compares against a calendar date.
# ---------------------------------------------------------------------------

def _run_status(tmp_path: Path, sources: dict, name: str = "run_status.json") -> Path:
    p = tmp_path / name
    p.write_text(json.dumps({"last_run": "irrelevant", "sources": sources}), encoding="utf-8")
    return p


def _stamp(epoch: float) -> str:
    """The exact shape scripts/collect.py writes: aware ISO-8601, UTC offset."""
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


@pytest.fixture
def clock():
    """A synthetic 'now', anchored to the real clock so it can never go stale."""
    import time
    return float(int(time.time()))


def _collect_shaped_run(env, clock, *, startup=300.0, collectors=1200.0):
    """A collect-shaped job: startup band, then a collectors band ending at now."""
    job_start = clock - (startup + collectors)
    nt.start_path().parent.mkdir(parents=True, exist_ok=True)
    nt.start_path().write_text(str(job_start))
    nt.cmd_mark("collectors", now=job_start + startup)
    return job_start


def test_band_windows_and_compute_bands_cannot_drift(env, clock):
    """Anti-drift pin: a source is charged to the window that produced the very
    duration it is charged against. Two independent boundary computations would
    let attribution and the band total disagree without either looking wrong."""
    job_start = clock - 1000.0
    marks = [{"t": job_start + 300, "band": "collectors"},
             {"t": job_start + 900, "band": "commit"}]
    windows = nt.band_windows(job_start, marks, clock)
    bands = nt.compute_bands(job_start, marks, clock)
    assert [w[0] for w in windows] == [b["band"] for b in bands]
    assert [round(w[2] - w[1]) for w in windows] == [b["seconds"] for b in bands]


def test_every_source_in_the_window_gets_an_elapsed_row(env, clock):
    """Gate 1: every source run_status records inside a band is attributed."""
    job_start = _collect_shaped_run(env, clock)
    wrote_at = _stamp(job_start + 300 + 1100)  # inside the collectors band
    status = _run_status(env, {
        "massive_stock_day": {"elapsed_sec": 610.5, "checked_at": wrote_at},
        "fred": {"elapsed_sec": 127.0, "checked_at": wrote_at},
        "cot": {"elapsed_sec": 90.1, "checked_at": wrote_at},
    })
    row = nt.cmd_finish(240.0, env / "ledger", now=clock, run_status_path=status)
    attribution = row["source_attribution"]
    assert attribution["read"] == "ok"
    assert attribution["matched"] == 3 and attribution["unmatched"] == 0
    band = attribution["bands"][0]
    assert band["band"] == "collectors"
    assert set(band["sources"]) == {"massive_stock_day", "fred", "cot"}
    # slowest first — the row itself has to read as evidence
    assert list(band["sources"]) == ["massive_stock_day", "fred", "cot"]


def test_untimed_source_is_null_never_zero(env, clock, capsys):
    """Gate 1's teeth. A source that ran without a timing must NOT read as the
    fastest source in the table used to choose what leaves the nightly path.

    This is a live shape, not a hypothetical: scripts/collect.py keys `timings`
    by REGISTRY KEY and the status row by `FetchResult.source`, and the two
    accrual pseudo-sources are not adapters at all — 3 of 186 sources carried a
    null elapsed_sec on 2026-08-09."""
    job_start = _collect_shaped_run(env, clock)
    wrote_at = _stamp(job_start + 300 + 600)
    status = _run_status(env, {
        "fred": {"elapsed_sec": 127.0, "checked_at": wrote_at},
        "polygon_gex_accrual": {"status": "ok", "checked_at": wrote_at},        # key absent
        "options_flow_creds": {"elapsed_sec": None, "checked_at": wrote_at},    # explicit null
        "instant_source": {"elapsed_sec": 0.0, "checked_at": wrote_at},         # measured zero
    })
    row = nt.cmd_finish(240.0, env / "ledger", now=clock, run_status_path=status)
    band = row["source_attribution"]["bands"][0]

    assert band["sources"]["polygon_gex_accrual"] is None
    assert band["sources"]["options_flow_creds"] is None
    # a MEASURED zero is preserved as a number — only a missing measurement is null
    assert band["sources"]["instant_source"] == 0.0
    assert band["n_null_elapsed"] == 2
    assert band["attributed_sec"] == 127.0, "a null must contribute nothing, not 0-as-a-measurement"
    assert row["source_attribution"]["null_elapsed"] == ["options_flow_creds", "polygon_gex_accrual"]

    # printed, not hidden
    out = capsys.readouterr().out
    assert "NO elapsed measurement" in out
    assert "polygon_gex_accrual" in out and "options_flow_creds" in out


def test_attribution_reconciles_against_the_band_total(env, clock):
    """Gate 2: attributed + residue == the band's own elapsed, exactly."""
    job_start = _collect_shaped_run(env, clock, startup=300.0, collectors=1200.0)
    wrote_at = _stamp(job_start + 300 + 1000)
    status = _run_status(env, {
        "a": {"elapsed_sec": 400.5, "checked_at": wrote_at},
        "b": {"elapsed_sec": 199.5, "checked_at": wrote_at},
        "untimed": {"elapsed_sec": None, "checked_at": wrote_at},
    })
    row = nt.cmd_finish(240.0, env / "ledger", now=clock, run_status_path=status)
    band = row["source_attribution"]["bands"][0]
    assert band["band_sec"] == 1200
    assert band["attributed_sec"] == 600.0
    assert band["residue_sec"] == 600.0
    assert round(band["attributed_sec"] + band["residue_sec"], 6) == band["band_sec"]
    # the band total in `bands` and the one attribution reconciles against are the same number
    assert [b["seconds"] for b in row["bands"] if b["band"] == "collectors"] == [band["band_sec"]]


def test_residue_is_published_not_distributed(env, clock, capsys):
    """Gate 2's second half: the remainder stays a remainder. No source may be
    inflated to absorb it — an unexplained monolith IS the finding."""
    job_start = _collect_shaped_run(env, clock, startup=300.0, collectors=3600.0)
    wrote_at = _stamp(job_start + 300 + 3000)
    status = _run_status(env, {
        "slow": {"elapsed_sec": 1000.0, "checked_at": wrote_at},
        "quick": {"elapsed_sec": 100.0, "checked_at": wrote_at},
    })
    row = nt.cmd_finish(240.0, env / "ledger", now=clock, run_status_path=status)
    band = row["source_attribution"]["bands"][0]
    assert band["sources"] == {"slow": 1000.0, "quick": 100.0}, "per-source values were rewritten"
    assert sum(band["sources"].values()) == band["attributed_sec"]
    assert band["residue_sec"] == 2500.0
    assert "residue 41.7m" in capsys.readouterr().out


def test_negative_residue_is_reported_as_overlap_not_hidden(env, clock, capsys):
    """collect runs its pure-REST sources in parallel host-groups, so summed
    adapter time can EXCEED the band. The identity still has to hold, and the
    negative remainder is a published fact about concurrency, not an error."""
    job_start = _collect_shaped_run(env, clock, startup=300.0, collectors=600.0)
    wrote_at = _stamp(job_start + 300 + 500)
    status = _run_status(env, {
        "host_a": {"elapsed_sec": 500.0, "checked_at": wrote_at},
        "host_b": {"elapsed_sec": 450.0, "checked_at": wrote_at},
    })
    row = nt.cmd_finish(240.0, env / "ledger", now=clock, run_status_path=status)
    band = row["source_attribution"]["bands"][0]
    assert band["attributed_sec"] == 950.0
    assert band["residue_sec"] == -350.0
    assert round(band["attributed_sec"] + band["residue_sec"], 6) == band["band_sec"]
    assert "concurrent host-groups overlap" in capsys.readouterr().out


def test_foreign_lane_and_prior_night_writes_are_not_attributed(env, clock):
    """run_status is cumulative and multi-writer (asia-close writes the same
    file). Only writes inside THIS job's bands may be charged to them; the rest
    is counted as unmatched, in the open, never folded into a band."""
    job_start = _collect_shaped_run(env, clock, startup=300.0, collectors=1200.0)
    status = _run_status(env, {
        "mine": {"elapsed_sec": 100.0, "checked_at": _stamp(job_start + 400)},
        "last_night": {"elapsed_sec": 999.0, "checked_at": _stamp(job_start - 86400)},
        "after_finish": {"elapsed_sec": 888.0, "checked_at": _stamp(clock + 600)},
        "unparseable": {"elapsed_sec": 777.0, "checked_at": "not-a-timestamp"},
        "no_stamp": {"elapsed_sec": 666.0},
    })
    row = nt.cmd_finish(240.0, env / "ledger", now=clock, run_status_path=status)
    attribution = row["source_attribution"]
    assert attribution["recorded"] == 5
    assert attribution["matched"] == 1 and attribution["unmatched"] == 4
    assert attribution["undated"] == 2
    charged = {s for b in attribution["bands"] for s in b["sources"]}
    assert charged == {"mine"}


def test_source_lands_in_the_band_that_contains_its_write(env, clock):
    """Band membership is the window, not the job: a write during startup is a
    startup fact. Bands the run never wrote into get no attribution entry."""
    job_start = _collect_shaped_run(env, clock, startup=600.0, collectors=1200.0)
    status = _run_status(env, {
        "early": {"elapsed_sec": 10.0, "checked_at": _stamp(job_start + 100)},
        "late": {"elapsed_sec": 20.0, "checked_at": _stamp(job_start + 700)},
    })
    row = nt.cmd_finish(240.0, env / "ledger", now=clock, run_status_path=status)
    by_band = {b["band"]: b for b in row["source_attribution"]["bands"]}
    assert set(by_band) == {"startup", "collectors"}
    assert set(by_band["startup"]["sources"]) == {"early"}
    assert set(by_band["collectors"]["sources"]) == {"late"}
    assert by_band["startup"]["band_sec"] == 600
    assert by_band["startup"]["residue_sec"] == 590.0


def test_batches_expose_which_writes_a_band_absorbed(env, clock):
    """A foreign lane writing INSIDE the window would be attributed here; the
    per-band batch list is how that shows up instead of hiding in a total.

    Bucketed to the SECOND, and that is load-bearing: collect.py stamps each
    source in one write_status call with its own `datetime.now()`, so the raw
    strings are microsecond-unique. Keying on them turned ONE write of 126
    sources into 126 batches and 6.9 KB of ledger row (measured against the real
    2026-08-09 run_status) — a diagnostic that said nothing, at 25x the size."""
    job_start = _collect_shaped_run(env, clock, startup=300.0, collectors=1200.0)
    first, second = job_start + 400, job_start + 900
    status = _run_status(env, {
        # same write, microsecond-apart stamps — must collapse to ONE batch
        "a": {"elapsed_sec": 1.0, "checked_at": _stamp(first) + ""},
        "b": {"elapsed_sec": 2.0, "checked_at": _stamp(first).replace("+00:00", ".000731+00:00")},
        "c": {"elapsed_sec": 3.0, "checked_at": _stamp(first).replace("+00:00", ".914022+00:00")},
        # a genuinely separate write — must stay a second batch
        "foreign": {"elapsed_sec": 4.0, "checked_at": _stamp(second)},
    })
    row = nt.cmd_finish(240.0, env / "ledger", now=clock, run_status_path=status)
    band = row["source_attribution"]["bands"][0]
    assert band["batches"] == [{"checked_at": nt._iso(first), "n": 3},
                               {"checked_at": nt._iso(second), "n": 1}]


def test_unreadable_run_status_costs_the_attribution_not_the_row(env, clock, capsys):
    """Telemetry law: this module must never fail a nightly job. A missing or
    corrupt run_status loses the attribution block and SAYS so; the timings row,
    the bands and the 85% tripwire are untouched."""
    _collect_shaped_run(env, clock)
    broken = env / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    row = nt.cmd_finish(240.0, env / "ledger", now=clock, run_status_path=broken)
    assert row["source_attribution"]["read"] == "unreadable"
    assert row["source_attribution"]["bands"] == []
    assert row["elapsed_minutes"] == pytest.approx(25.0, abs=0.1)
    assert [b["band"] for b in row["bands"]] == ["startup", "collectors"]
    assert "unreadable" in capsys.readouterr().out

    row2 = nt.cmd_finish(240.0, env / "ledger", now=clock, run_status_path=env / "gone.json")
    assert row2["source_attribution"]["read"] == "missing"


def test_attribution_survives_the_jsonl_round_trip(env, clock):
    """The ledger row is the artifact — the block has to be readable back out of
    the appended jsonl, nulls included."""
    job_start = _collect_shaped_run(env, clock)
    wrote_at = _stamp(job_start + 400)
    status = _run_status(env, {
        "timed": {"elapsed_sec": 42.5, "checked_at": wrote_at},
        "untimed": {"elapsed_sec": None, "checked_at": wrote_at},
    })
    nt.cmd_finish(240.0, env / "ledger", now=clock, run_status_path=status)
    line = (env / "ledger" / "engine.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    assert '"untimed":null' in line, "a null must survive as null in the ledger"
    band = json.loads(line)["source_attribution"]["bands"][0]
    assert band["sources"] == {"timed": 42.5, "untimed": None}


def test_attribution_emits_no_workflow_annotation(env, clock, capsys):
    """Every night has the same untimed pseudo-sources, so an annotation here
    would be a scheduled alarm. The facts print; nothing cries wolf."""
    job_start = _collect_shaped_run(env, clock)
    status = _run_status(env, {
        "untimed": {"elapsed_sec": None, "checked_at": _stamp(job_start + 400)},
    })
    nt.cmd_finish(100.0, env / "ledger", now=clock, run_status_path=status)
    out = capsys.readouterr().out
    assert "nightly-timings attribution:" in out
    assert not [l for l in out.splitlines() if l.startswith("::")], out


# ---------------------------------------------------------------------------
# W-L4 gate 1 — the asia-close lane (.github/workflows/asia-close.yml, job `asia`)
#
# The asia job was the last uninstrumented nightly: `python -m scripts.collect
# --group asia` is 55 sources and 46.1m of adapter wall-clock (measured
# 2026-08-09) that sat in no timings band on any job. Instrumenting it puts a
# SECOND writer's bands over the SAME cumulative data/run_status.json, so the
# tests below are about scoping: what the asia bands may claim, what they must
# refuse, and what they must show rather than silently absorb.
#
# Same fixture law as the block above — hermetic in DATA, not in TIME: every
# stamp is derived from the `clock` fixture's live base epoch, and the `env`
# fixture keeps nt.DEFAULT_RUN_STATUS pointed away from the repo's real file.
# ---------------------------------------------------------------------------

#: The `asia` job's band layout exactly as wired in asia-close.yml, with the
#: measured 2026-08-09 shape where one exists (the collect batch summed 2767.0s
#: of adapter wall-clock). The last band runs to `now`.
ASIA_BAND_PLAN = (
    ("collectors", 2880.0),
    ("collect-commit-push", 180.0),
    ("build-china", 2160.0),
    ("builders-parallel", 1500.0),
    ("tail-desks", 900.0),
    ("commit-publish", 600.0),
)
ASIA_STARTUP = 420.0
#: 55 sources × 50.3s = 2766.5s = 46.1m — the real batch's total, spread evenly.
ASIA_BATCH_N = 55
ASIA_BATCH_SEC = 50.3


@pytest.fixture
def asia_env(env, monkeypatch):
    """The asia-close job's identity. GITHUB_JOB names the ledger file AND the
    runner-temp state stamps, so a fixture written for `asia` has to be read back
    under the same job name the workflow will actually set."""
    monkeypatch.setenv("GITHUB_JOB", "asia")
    monkeypatch.setenv("GITHUB_WORKFLOW", "asia-close")
    return env


def _asia_shaped_run(env, clock, plan=ASIA_BAND_PLAN, *, startup=ASIA_STARTUP):
    """Lay the asia job's bands out ending at ``clock``.

    Returns ``(job_start, {band: (start, end)})`` so a test can place a
    run_status write at an instant inside a NAMED band instead of counting
    offsets — the band a source is charged to is the whole subject here."""
    job_start = clock - (startup + sum(sec for _band, sec in plan))
    nt.start_path().parent.mkdir(parents=True, exist_ok=True)
    nt.start_path().write_text(str(job_start))
    windows: dict[str, tuple[float, float]] = {}
    t = job_start + startup
    for band, sec in plan:
        nt.cmd_mark(band, now=t)
        windows[band] = (t, t + sec)
        t += sec
    return job_start, windows


def _asia_batch(wrote_at: str) -> dict:
    """The 55-source `collect --group asia` batch: one write, one stamp."""
    return {f"china_src_{i:02d}": {"elapsed_sec": ASIA_BATCH_SEC, "checked_at": wrote_at}
            for i in range(ASIA_BATCH_N)}


def test_asia_bands_charge_only_the_asia_batch(asia_env, clock):
    """Cross-lane scoping, in the shape the two lanes really have.

    data/run_status.json is ONE cumulative store: scripts/collect.py reads the
    existing status and merges only THIS run's results in, and lib/store.py
    write_status full-overwrites the file — so a lane's sources PERSIST with
    their old `checked_at` while another lane writes. Measured 2026-08-09: 186
    sources in the file, 126 stamped by daily's collect an hour earlier and 55 by
    asia's single collect batch. `FetchResult` carries no lane/group field, so
    band-window containment is the only scoping mechanism that exists without
    changing the collect write path — and nightly_timings is deliberately
    read-only w.r.t. run_status. If it leaked, asia's very first ledger row would
    charge 126 US adapters to a band where none of them ran."""
    job_start, windows = _asia_shaped_run(asia_env, clock)
    asia_write = _stamp(windows["collectors"][0] + 900.0)
    daily_write = _stamp(job_start - 3 * 3600)      # daily's collect, hours earlier
    sources = _asia_batch(asia_write)
    sources.update({f"us_src_{i:03d}": {"elapsed_sec": 90.0, "checked_at": daily_write}
                    for i in range(126)})
    row = nt.cmd_finish(165.0, asia_env / "ledger", now=clock,
                        run_status_path=_run_status(asia_env, sources))

    assert row["job"] == "asia" and row["workflow"] == "asia-close"
    attribution = row["source_attribution"]
    assert attribution["recorded"] == 181
    assert attribution["matched"] == ASIA_BATCH_N
    assert attribution["unmatched"] == 126, "the daily batch must be counted, not folded in"
    assert attribution["undated"] == 0
    # exactly one band absorbed anything, and it is the collect band
    assert [b["band"] for b in attribution["bands"]] == ["collectors"]
    band = attribution["bands"][0]
    assert band["n_sources"] == ASIA_BATCH_N
    assert set(band["sources"]) == {f"china_src_{i:02d}" for i in range(ASIA_BATCH_N)}
    assert band["attributed_sec"] == pytest.approx(2766.5, abs=0.05)   # 46.1m
    charged = {n for b in attribution["bands"] for n in b["sources"]}
    assert not [n for n in charged if n.startswith("us_src_")], (
        "a foreign lane's persisted rows were charged to an asia band")


def test_a_daily_shaped_run_does_not_absorb_the_asia_batch(env, clock):
    """The reverse direction of the same law, and it needs its own test: the two
    jobs OVERLAP in wall-clock (asia's collect landed 06:14 while daily's lane was
    still writing), so "asia started later" is not what keeps them apart — the
    band windows are. Here daily's collect job has already closed its last band
    when asia's batch lands, and its row must stay clean."""
    daily_end = clock - 3600.0            # daily's collect finished an hour ago
    job_start = _collect_shaped_run(env, daily_end, startup=300.0, collectors=1200.0)
    sources = {"fred": {"elapsed_sec": 127.0, "checked_at": _stamp(job_start + 400)}}
    sources.update(_asia_batch(_stamp(daily_end + 1800.0)))   # asia writes 30m later
    row = nt.cmd_finish(240.0, env / "ledger", now=daily_end,
                        run_status_path=_run_status(env, sources))

    attribution = row["source_attribution"]
    assert attribution["recorded"] == 1 + ASIA_BATCH_N
    assert attribution["matched"] == 1
    assert attribution["unmatched"] == ASIA_BATCH_N
    charged = {n for b in attribution["bands"] for n in b["sources"]}
    assert charged == {"fred"}


def test_a_foreign_write_inside_an_asia_band_stays_visible(asia_env, clock):
    """The DECLARED limit, pinned so it stays declared instead of pretending.

    The lanes genuinely overlap: on 2026-08-09 daily's tape_flow band wrote
    `tape_flow_etf-history` at 06:25:18 with elapsed_sec=1236.9 (20.6m) — AFTER
    asia's collect batch, i.e. inside one of asia's build bands, where no adapter
    of asia's runs at all. Band-window containment cannot tell that apart from
    asia's own work, because run_status rows carry no lane marker.

    So the contract is visibility, not correctness: the write lands in the band
    that contains it AND shows up as its own single-source entry in that band's
    `batches` list, which is exactly how a reader spots 20.6m of US adapter time
    in a CN band. What must NOT happen is it drifting into `collectors` (the band
    whose total is the thing W-L4 is trying to argue about) or vanishing into a
    total with no trace."""
    _job_start, windows = _asia_shaped_run(asia_env, clock)
    asia_write_at = windows["collectors"][0] + 900.0
    foreign_at = windows["build-china"][0] + 600.0
    sources = _asia_batch(_stamp(asia_write_at))
    sources["tape_flow_etf-history"] = {"elapsed_sec": 1236.9,
                                        "checked_at": _stamp(foreign_at)}
    row = nt.cmd_finish(165.0, asia_env / "ledger", now=clock,
                        run_status_path=_run_status(asia_env, sources))
    by_band = {b["band"]: b for b in row["source_attribution"]["bands"]}

    # it is NOT in the collect band, and the collect band's total is untouched
    assert "tape_flow_etf-history" not in by_band["collectors"]["sources"]
    assert by_band["collectors"]["n_sources"] == ASIA_BATCH_N
    assert by_band["collectors"]["attributed_sec"] == pytest.approx(2766.5, abs=0.05)
    # it IS in build-china, alone, and the batch list names the write that carried it
    assert by_band["build-china"]["sources"] == {"tape_flow_etf-history": 1236.9}
    assert by_band["build-china"]["batches"] == [{"checked_at": nt._iso(foreign_at), "n": 1}]
    assert by_band["collectors"]["batches"] == [{"checked_at": nt._iso(asia_write_at),
                                                 "n": ASIA_BATCH_N}]
    # and the contamination is loud enough to read off the band line: 20.6m of
    # "adapter" time in a band where asia runs no adapters
    assert by_band["build-china"]["residue_sec"] == pytest.approx(2160.0 - 1236.9, abs=0.05)


def test_every_asia_band_publishes_its_residue_exactly(asia_env, clock):
    """Gate 2 on the new job: `attributed_sec + residue_sec == band_sec`, exactly,
    for every band that absorbed anything — including the negative case.

    Two edges are pinned deliberately:
      * a band with NO sources gets no attribution row at all, so no residue is
        invented for it; its duration is still published in `bands`, which is
        where a reader learns the band existed and explained nothing.
      * `collectors` runs pure-REST sources in concurrent host-groups, so summed
        adapter wall-clock can EXCEED the band. The negative remainder is a
        published fact about concurrency — it must not be clamped to zero, which
        would quietly convert an overlap measurement into a fake clean total."""
    plan = (("collectors", 600.0),              # overlap: summed adapter > band
            ("collect-commit-push", 180.0),     # no sources at all
            ("build-china", 1200.0),
            ("builders-parallel", 900.0))       # no sources at all
    _job_start, windows = _asia_shaped_run(asia_env, clock, plan)
    sources = {
        "china_stocks": {"elapsed_sec": 500.0,
                         "checked_at": _stamp(windows["collectors"][0] + 60.0)},
        "china_filings": {"elapsed_sec": 450.0,
                          "checked_at": _stamp(windows["collectors"][0] + 60.0)},
        "china_library": {"elapsed_sec": 300.0,
                          "checked_at": _stamp(windows["build-china"][0] + 120.0)},
    }
    row = nt.cmd_finish(165.0, asia_env / "ledger", now=clock,
                        run_status_path=_run_status(asia_env, sources))
    attribution = row["source_attribution"]
    by_band = {b["band"]: b for b in attribution["bands"]}
    band_sec = {b["band"]: b["seconds"] for b in row["bands"]}

    # the identity, on every band that has an attribution row
    for band in attribution["bands"]:
        assert round(band["attributed_sec"] + band["residue_sec"], 6) == band["band_sec"], band
        assert band["band_sec"] == band_sec[band["band"]], (
            f"{band['band']}: attribution reconciles against a different total than `bands` "
            "publishes — the two boundary computations have drifted")
    # negative residue: published, signed, not clamped
    assert by_band["collectors"]["attributed_sec"] == 950.0
    assert by_band["collectors"]["residue_sec"] == -350.0
    assert by_band["build-china"]["residue_sec"] == 900.0
    # zero-source bands: duration published, NO attribution row, no phantom residue
    assert set(by_band) == {"collectors", "build-china"}
    for empty in ("startup", "collect-commit-push", "builders-parallel"):
        assert empty in band_sec, f"{empty}: the band's own duration was lost"
        assert empty not in by_band, f"{empty}: residue invented for a band with no sources"
    assert band_sec["collect-commit-push"] == 180 and band_sec["builders-parallel"] == 900


def test_an_untimed_asia_source_is_null_never_zero(asia_env, clock, capsys):
    """NULL, never 0 — carried into the new lane before it can happen there.

    The real 2026-08-09 asia batch had ZERO nulls (55 sources, 55 timed), so this
    is the guard for the first night one appears, not a description of today.
    scripts/collect.py keys `timings` by REGISTRY KEY and the status row by
    `FetchResult.source`, so any key/source mismatch in a CN/HK adapter lands
    untimed — and 0 would make the slowest unknown in the lane read as its
    fastest source, in the exact table W-L4 uses to decide what moves off the
    nightly path. A measured 0.0 is a different fact and must survive as one."""
    _job_start, windows = _asia_shaped_run(asia_env, clock)
    wrote_at = _stamp(windows["collectors"][0] + 900.0)
    sources = {
        "china_filings": {"elapsed_sec": 555.8, "checked_at": wrote_at},   # the real slowest
        "hk_cbbc_sld": {"status": "ok", "checked_at": wrote_at},           # key absent
        "china_flow_accrual": {"elapsed_sec": None, "checked_at": wrote_at},  # explicit null
        "hk_shortsell": {"elapsed_sec": 0.0, "checked_at": wrote_at},      # MEASURED zero
    }
    row = nt.cmd_finish(165.0, asia_env / "ledger", now=clock,
                        run_status_path=_run_status(asia_env, sources))
    attribution = row["source_attribution"]
    band = attribution["bands"][0]

    assert band["sources"]["hk_cbbc_sld"] is None
    assert band["sources"]["china_flow_accrual"] is None
    assert band["sources"]["hk_shortsell"] == 0.0
    assert isinstance(band["sources"]["hk_shortsell"], float), "a measured 0.0 became a null"
    assert band["n_null_elapsed"] == 2
    assert band["attributed_sec"] == 555.8, "a null must contribute nothing, not 0-as-a-measurement"
    assert attribution["null_elapsed"] == ["china_flow_accrual", "hk_cbbc_sld"]

    # printed, not hidden — attribution_lines is what cmd_finish emits to the job log
    out = capsys.readouterr().out
    assert "NO elapsed measurement" in out
    assert "china_flow_accrual" in out and "hk_cbbc_sld" in out
    printed = "\n".join(nt.attribution_lines(attribution))
    assert "china_flow_accrual" in printed and "hk_cbbc_sld" in printed
    # the untimed pair is named; the measured zero is NOT called a missing measurement
    assert "hk_shortsell" not in printed.split("NO elapsed measurement")[-1]


def test_report_sources_view_names_targets_residue_and_nulls(env, clock):
    """The reader for the new data: without it the evidence has no consumer."""
    job_start = _collect_shaped_run(env, clock, startup=300.0, collectors=1200.0)
    wrote_at = _stamp(job_start + 400)
    status = _run_status(env, {
        "massive_stock_day": {"elapsed_sec": 600.0, "checked_at": wrote_at},
        "fred": {"elapsed_sec": 120.0, "checked_at": wrote_at},
        "untimed": {"elapsed_sec": None, "checked_at": wrote_at},
    })
    nt.cmd_finish(240.0, env / "ledger", now=clock, run_status_path=status)
    joined = "\n".join(ntr.report(env / "ledger", nights=14, show_bands=False, show_sources=5))
    assert "attribution · collectors" in joined
    assert "massive_stock_day" in joined and "10.0m" in joined
    assert "residue 8.0m" in joined
    assert "untimed" in joined and "NO elapsed measurement" in joined
    assert "null" in joined
    # a report that has no attribution rows must not invent any
    assert ntr.report(env / "ledger", nights=14, show_bands=False, show_sources=5,
                      only_job="not-a-job") == \
        [f"no timings rows under {env / 'ledger'} — has the nightly run since W2 shipped?"]


def test_report_flags_a_breach(env):
    now = _write_start(seconds_ago=0.9 * 100 * 60)
    nt.cmd_finish(100.0, env / "ledger", now=now)
    lines = ntr.report(env / "ledger", nights=14, show_bands=True)
    joined = "\n".join(lines)
    assert "engine" in joined
    assert "TRIPWIRE" in joined


def test_backfill_seeds_only_instrumented_jobs(env, tmp_path):
    payload = {"jobs": [
        {"name": "engine", "run_id": 1, "run_attempt": 1, "runner_name": "mac-builder-1",
         "conclusion": "success",
         "started_at": "2026-08-06T02:00:00Z", "completed_at": "2026-08-06T04:30:00Z"},
        {"name": "publish", "run_id": 1, "run_attempt": 1, "runner_name": "",
         "conclusion": "success",
         "started_at": "2026-08-06T05:00:00Z", "completed_at": "2026-08-06T05:02:00Z"},
    ]}
    jf = tmp_path / "jobs.json"
    jf.write_text(json.dumps(payload))
    n = nt.cmd_backfill(jf, DAILY, tmp_path / "ledger")
    assert n == 1  # publish is not self-hosted/instrumented → skipped
    rows = [json.loads(l) for l in (tmp_path / "ledger" / "engine.jsonl").read_text().splitlines()]
    assert rows[0]["elapsed_minutes"] == pytest.approx(150.0)
    assert rows[0]["source"] == "backfill-gh-api"
    # engine cap history lives in daily.yml's timeout-minutes comment; 300 since 2026-08-08
    assert rows[0]["cap_minutes"] == 300.0


# ---------------------------------------------------------------------------
# wiring — daily.yml + asia-close.yml
# ---------------------------------------------------------------------------

def _jobs(workflow: Path) -> dict:
    return yaml.safe_load(workflow.read_text(encoding="utf-8"))["jobs"]


def _daily_jobs() -> dict:
    return _jobs(DAILY)


def _has_checkout(spec: dict) -> bool:
    """Does the job check the repo out at all?

    STRUCTURAL, not a name allowlist. ``scripts/nightly_timings.py`` and
    ``scripts/ci/nightly_timings_finish.sh`` are repo files: a job with no
    ``actions/checkout`` has neither in its workspace, so it cannot be
    instrumented without giving it a checkout — see the ``gate`` exemption test
    below for the live instance. Verified 2026-08-09: all 16 instrumented
    daily.yml jobs DO check out, so adding this clause changes that set by
    nothing (pinned by name in EXPECTED_INSTRUMENTED).
    """
    return any(str(step.get("uses", "")).startswith("actions/checkout")
               for step in (spec.get("steps") or []))


def _instrumented(workflow: Path = DAILY) -> dict[str, dict]:
    out = {}
    for key, spec in _jobs(workflow).items():
        if not isinstance(spec, dict):
            continue
        runs_on = spec.get("runs-on")
        if isinstance(runs_on, list) and "self-hosted" in runs_on \
           and spec.get("timeout-minutes") is not None and _has_checkout(spec):
            out[key] = spec
    return out


def _finish_index(spec: dict) -> int:
    """Index of the job's finish step, or -1 when it has none."""
    for i, step in enumerate(spec["steps"]):
        if step.get("name") == FINISH_STEP_NAME:
            return i
    return -1


@pytest.mark.parametrize("workflow", INSTRUMENTED_WORKFLOWS, ids=lambda p: p.name)
def test_instrumented_job_set_is_pinned_by_name(workflow):
    """The anti-blinding pin. Every wiring assertion below iterates
    ``_instrumented()``; a predicate change that stops matching would empty that
    loop and turn this whole file green while the nightly lost its telemetry —
    a suite that exempts everything passes for the wrong reason.

    So the set is asserted by NAME, not by count alone: adding a lane means
    adding it here deliberately, and a job dropping out of the predicate is a
    failure with the missing name printed rather than a silent -1."""
    found = set(_instrumented(workflow))
    expected = EXPECTED_INSTRUMENTED[workflow]
    assert found == expected, (
        f"{workflow.name}: instrumented-job set drifted — "
        f"{len(found)} found vs {len(expected)} pinned.\n"
        f"  no longer matched (telemetry would go dark, unscanned): "
        f"{sorted(expected - found) or '—'}\n"
        f"  newly matched (wire it up, then add the name here): "
        f"{sorted(found - expected) or '—'}"
    )


@pytest.mark.parametrize("workflow", INSTRUMENTED_WORKFLOWS, ids=lambda p: p.name)
def test_every_self_hosted_job_is_instrumented(workflow):
    jobs = _instrumented(workflow)
    assert jobs, f"{workflow.name} parse found no self-hosted jobs — wiring test is broken"
    missing = []
    for key, spec in jobs.items():
        steps = spec["steps"]
        if steps[0].get("name") != START_STEP_NAME:
            missing.append(f"{key}: first step is {steps[0].get('name')!r}, not the job-start mark")
        idx = _finish_index(spec)
        if idx < 0:
            missing.append(f"{key}: no {FINISH_STEP_NAME!r} step at all")
            continue
        # Last, or followed ONLY by the declared delivery tail. The finish step
        # is where it is so it beats the grace window, not so it can be buried.
        tail = [s.get("name") for s in steps[idx + 1:]]
        strays = [n for n in tail if n not in DELIVERY_TAIL_STEPS]
        if strays:
            missing.append(
                f"{key}: steps run after the finish step that are not pure delivery: {strays}"
            )
    assert not missing, (
        f"W2 telemetry wiring gap — a self-hosted {workflow.name} job is missing its timings steps "
        "(add the job-start mark as the FIRST step and nightly_timings_finish.sh as the LAST):\n"
        + "\n".join(f"  {m}" for m in missing)
    )


@pytest.mark.parametrize("workflow", INSTRUMENTED_WORKFLOWS, ids=lambda p: p.name)
def test_finish_cap_argument_matches_timeout_minutes(workflow):
    """The anti-drift pin: cap raises must update the finish arg in the same edit,
    or the 85% tripwire silently rescales against a stale cap."""
    bad = []
    for key, spec in _instrumented(workflow).items():
        idx = _finish_index(spec)
        if idx < 0:
            # `steps[-1]` is a real step, so indexing it here would report the cap
            # as "drifted" and quote the job's LAST step's script — blaming a step
            # that is innocent for a finish step that does not exist. Name the
            # actual defect instead; test_every_self_hosted_job_is_instrumented
            # covers the same case from the wiring side.
            bad.append(f"{key}: no {FINISH_STEP_NAME!r} step at all — nothing carries the cap arg")
            continue
        finish = spec["steps"][idx]
        run = finish.get("run", "")
        expected = f"bash scripts/ci/nightly_timings_finish.sh {spec['timeout-minutes']}"
        if run.strip() != expected:
            bad.append(f"{key}: timeout-minutes={spec['timeout-minutes']} but finish step runs {run.strip()!r}")
        # Exactly always(), never `always() && <condition>`: a conditioned finish
        # step is a tripwire that goes dark on the nights it is needed. (The
        # trailing YAML comment on the engine step is stripped by the parser.)
        if finish.get("if") != "always()":
            bad.append(f"{key}: finish step must be if: always() so a cap-cancel night still records")
    assert not bad, "finish step drifted from the job cap:\n" + "\n".join(f"  {b}" for b in bad)


def test_finish_step_is_not_stranded_behind_the_pages_artifact_upload():
    """THE persistence pin — the defect this test exists to make un-revertable.

    `if: always()` buys the step the right to run after a cancel; it does not
    buy it TIME. The runner force-terminates a cancelled job ~5 minutes in, and
    every remaining always() step shares that one window. The engine job spent
    it on `upload pages artifact` — a multi-thousand-file upload that fails on a
    cancel night anyway — and the finish step behind it was never scheduled.

    Evidence, GH jobs API for run 31067383446 (daily, 2026-08-06):
        engine  conclusion=cancelled  started 10:05:45Z  completed 13:30:46Z
        (= 205.0m = the 200m cap + exactly 5m of grace)
        117 commit engine outputs .......................... success
        121 strip heavy per-ticker stores ................... success
        122 upload pages artifact ........................... FAILURE
        <no step 123 — the finish/tripwire step never ran>
    Consequence: data/ops/nightly_timings/engine.jsonl held ONE row, and its
    `source` was `backfill-gh-api` — reconstructed by hand from the API, not
    written by the job — while all 15 sibling jobs carried native rows.

    Any job that uploads a pages artifact must write its timings row FIRST.
    """
    offenders = []
    for key, spec in _instrumented(DAILY).items():
        steps = spec["steps"]
        uploads = [i for i, s in enumerate(steps)
                   if str(s.get("uses", "")).startswith("actions/upload-pages-artifact")]
        if not uploads:
            continue
        idx = _finish_index(spec)
        if idx > min(uploads):
            offenders.append(
                f"{key}: finish step is at index {idx}, behind the pages-artifact upload "
                f"at index {min(uploads)} — on a cap-cancel night it will not be scheduled "
                f"and the night's row (and its 85% tripwire) is lost"
            )
    assert not offenders, "\n".join(offenders)


# ---------------------------------------------------------------------------
# wiring — scripts/ci/nightly_timings_finish.sh (non-fatal must not mean silent)
# ---------------------------------------------------------------------------

def test_every_loss_path_in_the_finish_script_announces_itself():
    """Telemetry is allowed to fail the night; it is not allowed to fail QUIETLY.

    Every early `exit 0` in the wrapper drops that night's row, and each one was
    reachable while the ledger sat empty for three nights with a clean-looking
    job log. Each must emit a titled workflow annotation so the loss shows up in
    the Actions summary instead of only in a diff nobody runs."""
    src = FINISH_SH.read_text(encoding="utf-8")
    for slug in ("nightly timings finish failed", "nightly timings row missing",
                 "nightly timings not staged", "nightly timings commit failed",
                 "nightly timings push lost"):
        assert f"::warning title={slug}::" in src, (
            f"loss path {slug!r} lost its annotation — a silent exit 0 is the defect"
        )


def test_finish_script_annotations_start_the_line():
    """House law: GitHub parses `::` only at column 0 of the emitted line, so the
    annotation must be the FIRST thing echoed (never behind a prefix, never
    through a logger). A prefixed call reviews as an alarm and produces nothing —
    it shipped dead five times before #3587 swept it."""
    src = FINISH_SH.read_text(encoding="utf-8")
    emitters = re.findall(r'^\s*echo "([^"]*::(?:warning|error|notice)[^"]*)"',
                          src, flags=re.MULTILINE)
    assert emitters, "no annotation emitters found — the scan regex has drifted"
    for text in emitters:
        assert text.startswith("::"), (
            f"annotation is not at column 0 of the echoed string: {text!r}"
        )


@pytest.mark.parametrize("workflow", INSTRUMENTED_WORKFLOWS, ids=lambda p: p.name)
def test_start_mark_writes_the_path_the_reader_expects(workflow):
    """The shell stamp and the Python reader must agree on the state filename."""
    for key, spec in _instrumented(workflow).items():
        run = spec["steps"][0].get("run", "")
        assert 'nightly-timings-${GITHUB_RUN_ID}-${GITHUB_JOB}-start' in run, (
            f"{workflow.name}:{key}: job-start mark writes an unexpected path: {run!r} — "
            "scripts/nightly_timings.py start_path() would never find it (dark telemetry)"
        )
        assert "${RUNNER_TEMP}" in run


@pytest.mark.parametrize("workflow", INSTRUMENTED_WORKFLOWS, ids=lambda p: p.name)
def test_band_marks_use_the_cli(workflow):
    """Every band-mark step goes through the mark subcommand (state-file contract)."""
    for key, spec in _instrumented(workflow).items():
        for step in spec["steps"]:
            name = step.get("name") or ""
            if name.startswith("timings band — "):
                run = step.get("run", "").strip()
                assert run.startswith("python3 scripts/nightly_timings.py mark --band "), (
                    f"{workflow.name}:{key}: {name!r} runs {run!r}"
                )


def test_publish_job_carries_no_timings_wrapper():
    """publish runs on ubuntu-latest with no explicit cap — the wrapper's cap arg
    would be an invented number; it must stay uninstrumented until it gets one."""
    steps = _daily_jobs()["publish"].get("steps") or []
    for step in steps:
        assert "timings" not in (step.get("name") or ""), step


def test_asia_gate_job_carries_no_timings_wrapper():
    """asia-close's `gate` job is self-hosted WITH a timeout-minutes and still must
    stay uninstrumented — for a structural reason, not a preference.

    `gate` has NO `actions/checkout`: its single step is a heredoc'd
    GitHub-API-plus-clock decision run by /opt/homebrew/bin/python3.12. So
    scripts/nightly_timings.py and scripts/ci/nightly_timings_finish.sh do not
    EXIST in its workspace — instrumenting it means giving a checkout to the one
    job whose whole purpose is to be cheap enough to fire on seven cron slots a
    day and no-op six of them (it holds a runner slot out of only three on this
    box). That is why `_has_checkout` is part of the predicate instead of a
    name allowlist: the exemption is a property of the job, and it lapses
    automatically the day `gate` checks the repo out.

    The same reasoning that keeps it out of the wiring scan keeps timings steps
    out of the job: a mark/finish step here would fail every run (file not
    found), which the `|| echo` swallows into a permanent non-fatal warning."""
    gate = _jobs(ASIA)["gate"]
    assert not _has_checkout(gate), (
        "asia-close `gate` now checks out the repo — the structural exemption above "
        "has lapsed. Instrument it (mark + finish, cap = its timeout-minutes) and add "
        "'gate' to ASIA_INSTRUMENTED_JOBS, or delete the checkout."
    )
    for step in gate.get("steps") or []:
        assert "timings" not in (step.get("name") or ""), step
