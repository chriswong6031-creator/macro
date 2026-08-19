"""GD-4A — CN/HK forward-ledger liveness repair (2026-08-19).

Root cause (census confirmed 2026-08-19; see
research/grey_deer/commissions/GD-4A_CNHK_LEDGER_REPAIR_COMMISSION_2026-08-19.md):
engine/risk_radar_intl_audit.py's ledger_lane_armed() requires COLLECT_LANE=nightly
(or the legacy US_LANE alias) before scripts/build_china.py and scripts/build_hk.py
will call snapshot_and_grade() and advance data/risk_radar_intl/{cn,hk}_forward_log.jsonl
(engine/risk_radar_intl_audit.py:61-71, called at scripts/build_china.py:~1445 and
scripts/build_hk.py:~1365). .github/workflows/asia-close.yml — the canonical SETTLED
Asia-close lane and the only fresh-close lane that commits data/ for CN/HK — deliberately
sets NO job-wide COLLECT_LANE (arming it would un-gate other ledger writers reachable
from the same job; see the workflow's own line-667 comment) and, before this repair,
carried no per-step/per-call arm on the build_china spine step or the build_hk builder
call either — so both ledgers froze at asof 2026-07-16 while the lane ran green nightly.

This suite is FIXTURE-ONLY: every ledger read/write below goes through `root=tmp_path`,
never data/risk_radar_intl/. It proves the two production-facing FROZEN SPEC guarantees
for BOTH markets:

  TEST GROUP 1 (§0 item 3): duplicate-date idempotence — the keep-first-by-asof guard
  in engine.risk_radar_intl_audit.log_snapshot (module lines ~131-133) holds: rerunning
  the same settled session appends nothing. The writer is a FULL-FILE REWRITE despite the
  "append" wording (log_snapshot reads the whole file, conditionally appends in memory,
  then rewrites the whole file) — so the assertion that matters is ROW-COUNT STABILITY
  after a repeat call, not merely a truthy/falsy return.

  TEST GROUP 2 (§0 item 4): zero intraday/off-lane advancement — with COLLECT_LANE unset
  (the closing-bell / engine-render / render-relane contract), the exact gate the build
  scripts use (ledger_lane_armed() branching into snapshot_and_grade() vs the read-only
  scorecard(log_governance=False) fast-path — see
  tests/test_risk_radar_intl_profiles.py::test_cn_hk_ca_build_appenders_lane_gated for the
  companion source-level pin) must not create or extend either ledger file.

  TEST GROUP 3: source-level pin that the asia-close.yml repair itself (the per-step arm
  on the build_china spine step, the per-call arm on the build_hk builder invocation) is
  present and scoped no wider than described — never job-wide. Mirrors the existing
  tests/test_ignition_lane_gate.py::test_asia_close_arms_hk_baskets_lane pattern for the
  sibling HK ignition ledger.

NOTE tests/conftest.py arms COLLECT_LANE=nightly autouse — off-lane cases must pop
BOTH env vars explicitly (same contract test_ignition_lane_gate.py documents).

Run: python3 -m pytest tests/test_gd4a_cnhk_ledger_repair.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import risk_radar_intl as rri
from engine import risk_radar_intl_audit as rra

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "asia-close.yml"

MARKETS = {
    "cn": rri.CN_PROFILE,
    "hk": rri.HK_PROFILE,
}


def _offlane(monkeypatch):
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    monkeypatch.delenv("US_LANE", raising=False)


def _onlane(monkeypatch):
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    monkeypatch.delenv("US_LANE", raising=False)


def _snap(market: str, asof: str = "2026-08-19", state: str = "caution") -> dict:
    """Minimal risk_radar_intl snapshot dict — enough for _entry_from_snapshot to
    accept it (needs asof + state at minimum; the rest mirrors the real payload
    shape from engine.risk_radar_intl.snapshot())."""
    return {
        "schema": "risk_radar_intl.v1",
        "asof": asof,
        "market": market,
        "state": state,
        "state_ungated": state,
        "top_score": 42,
        "dominant_scare": "rate_shock",
        "conjunction": False,
        "context_gate": {"met": False, "below_200dma": False, "recent_parabolic": False},
        "scares": [],
        "drawdown_prob": {},
        "trajectory": None,
        "gross_factor": 1.0,
        "caveat_en": "test fixture",
        "caveat_zh": "test fixture",
        "disclaimer": "test fixture",
    }


def _ledger_path(root: Path, market: str) -> Path:
    return root / "data" / "risk_radar_intl" / f"{market}_forward_log.jsonl"


def _rows(root: Path, market: str) -> list[dict]:
    p = _ledger_path(root, market)
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def _advance_if_armed(snap: dict, profile, root: Path) -> dict:
    """Mirrors the EXACT call-site gate scripts/build_china.py and scripts/build_hk.py
    use around the ledger advancer (the code this PR arms in asia-close.yml):

        if _rra.ledger_lane_armed():
            ... = _rra.snapshot_and_grade(latest["risk_radar"], PROFILE)
        else:
            ... = _rra.scorecard(PROFILE.key, log_governance=False)

    tune() is intentionally NOT replicated here — it is a separate calibration
    ledger (data/risk_radar_intl/*_calibration.json / tune_log), out of GD-4A scope
    (the commission arms forward-log advancement only)."""
    if rra.ledger_lane_armed():
        return rra.snapshot_and_grade(snap, profile, root=root)
    return rra.scorecard(profile.key, root=root, log_governance=False)


# ═══════════════════════════════════════════════════════════════════════════
# TEST GROUP 1 — §0 item 3: duplicate-date idempotence (both markets)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("market", ["cn", "hk"])
def test_log_snapshot_duplicate_asof_is_row_count_stable(tmp_path, monkeypatch, market):
    """Direct engine.risk_radar_intl_audit.log_snapshot call: a rerun of the SAME
    settled asof must not grow the ledger. log_snapshot is a full-file REWRITE
    (read all rows, conditionally append in memory, rewrite the whole file) despite
    the "append" docstring wording, so row-count stability — not just the boolean
    return — is the guarantee that matters for a settled-close rerun."""
    snap = _snap(market, asof="2026-07-16")

    first = rra.log_snapshot(snap, market, root=str(tmp_path))
    assert first is True, "first log_snapshot for a new asof must report a write"
    assert len(_rows(tmp_path, market)) == 1

    # Rerun the same settled session 3x — same class of event a retried/re-fired
    # asia-close schedule slot (the workflow fires up to 7 candidate cron slots/day)
    # would produce if the lane re-ran after already advancing today's row.
    for _ in range(3):
        again = rra.log_snapshot(snap, market, root=str(tmp_path))
        assert again is False, "duplicate-asof log_snapshot must report no write"
        rows = _rows(tmp_path, market)
        assert len(rows) == 1, (
            f"{market}_forward_log.jsonl grew on a duplicate-asof rerun "
            f"(keep-first-by-asof guard failed): {len(rows)} rows"
        )
    assert _rows(tmp_path, market)[0]["asof"] == "2026-07-16"


@pytest.mark.parametrize("market", ["cn", "hk"])
def test_advance_if_armed_duplicate_asof_via_call_site_gate(tmp_path, monkeypatch, market):
    """Same guarantee, exercised through the actual build-script call-site gate
    (_advance_if_armed mirrors the branch in scripts/build_china.py / build_hk.py)
    rather than calling log_snapshot directly — proves the idempotence survives
    the snapshot_and_grade() + scorecard() wrapper the armed asia-close step runs."""
    _onlane(monkeypatch)
    profile = MARKETS[market]
    snap = _snap(market, asof="2026-08-19")

    _advance_if_armed(snap, profile, tmp_path)
    assert len(_rows(tmp_path, market)) == 1

    # A retried same-day asia-close fire (the schedule races up to 7 cron slots
    # and the `gate` job dedups most of them, but a same-day retry after a real
    # failure is explicitly allowed) must not double-append.
    _advance_if_armed(snap, profile, tmp_path)
    _advance_if_armed(snap, profile, tmp_path)
    rows = _rows(tmp_path, market)
    assert len(rows) == 1, (
        f"{market}: a rerun through the armed call-site gate grew the ledger "
        f"({len(rows)} rows) — duplicate-date idempotence violated"
    )


# ═══════════════════════════════════════════════════════════════════════════
# TEST GROUP 2 — §0 item 4: zero intraday/off-lane advancement (both markets)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize("market", ["cn", "hk"])
def test_offlane_advance_creates_no_ledger(tmp_path, monkeypatch, market):
    """With COLLECT_LANE unset (closing-bell / engine-render / render-relane
    contract), the call-site gate must take the read-only scorecard() fast-path —
    no ledger file may be created, let alone extended."""
    _offlane(monkeypatch)
    profile = MARKETS[market]
    snap = _snap(market, asof="2026-08-19")

    sc = _advance_if_armed(snap, profile, tmp_path)
    assert isinstance(sc, dict) and sc.get("market") == market, (
        "off-lane path must still return the display scorecard (never blank the card)"
    )
    p = _ledger_path(tmp_path, market)
    assert not p.exists(), (
        f"off-lane advance created {p} — a mid-session/off-lane append is "
        f"PIT-inconsistent and (being idempotent-by-asof) would permanently "
        f"displace the nightly row"
    )


@pytest.mark.parametrize("market", ["cn", "hk"])
def test_offlane_advance_after_nightly_row_does_not_extend_ledger(tmp_path, monkeypatch, market):
    """A more adversarial version of the zero-intraday guarantee: seed a genuine
    nightly row first (as the settled asia-close run would leave behind), then run
    an off-lane call for a LATER asof (simulating an engine-render/closing-bell
    re-render later the same day) and confirm the ledger is untouched — not just
    that a fresh file isn't created, but that an EXISTING one isn't extended."""
    profile = MARKETS[market]

    _onlane(monkeypatch)
    nightly_snap = _snap(market, asof="2026-08-18")
    _advance_if_armed(nightly_snap, profile, tmp_path)
    assert len(_rows(tmp_path, market)) == 1

    _offlane(monkeypatch)
    later_snap = _snap(market, asof="2026-08-18-later-same-day-rerender", state="risk-off")
    _advance_if_armed(later_snap, profile, tmp_path)

    rows = _rows(tmp_path, market)
    assert len(rows) == 1, (
        f"{market}: an off-lane call after the nightly row extended the ledger "
        f"to {len(rows)} rows — zero-intraday-advancement guarantee violated"
    )
    assert rows[0]["asof"] == "2026-08-18", "the nightly row itself must be unchanged"


@pytest.mark.parametrize("market", ["cn", "hk"])
def test_ledger_lane_armed_env_matrix_matches_asia_close_contract(monkeypatch, market):
    """Direct env-matrix pin on the gate the asia-close arm now sets: only
    COLLECT_LANE=nightly (or the legacy US_LANE alias) arms advancement — the
    exact values asia-close.yml's new per-step/per-call arms use."""
    cases = [
        ({}, False),
        ({"COLLECT_LANE": "nightly"}, True),
        ({"COLLECT_LANE": "NIGHTLY"}, True),          # case-insensitive
        ({"COLLECT_LANE": "intraday"}, False),
        ({"COLLECT_LANE": "asia"}, False),             # CN_LANE=asia must NOT arm this gate
        ({"US_LANE": "nightly"}, True),                # legacy alias
    ]
    for env, expected in cases:
        _offlane(monkeypatch)
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        assert rra.ledger_lane_armed() is expected, f"{market}: env {env} != {expected}"


# ═══════════════════════════════════════════════════════════════════════════
# TEST GROUP 3 — source-level pin: the asia-close.yml repair is scoped correctly
# ═══════════════════════════════════════════════════════════════════════════

def test_asia_close_arms_cn_spine_step_not_job_wide():
    """The 'build china a-share dashboard' step (the CN forward-ledger advancer,
    scripts.build_china) must carry a per-step COLLECT_LANE: nightly arm. The JOB
    itself must remain unarmed (no top-level `env:` at the job level setting
    COLLECT_LANE) — asia-close.yml deliberately never arms job-wide, because that
    would un-gate other ledger writers reachable elsewhere in the job (the
    workflow's own line-667 comment)."""
    src = WORKFLOW.read_text(encoding="utf-8")
    step_start = src.find("- name: build china a-share dashboard")
    assert step_start != -1, "asia-close.yml no longer has the build_china spine step?"
    next_step = src.find("\n      - name:", step_start + 1)
    assert next_step != -1
    step_body = src[step_start:next_step]

    assert "COLLECT_LANE: nightly" in step_body, (
        "build_china spine step must arm COLLECT_LANE: nightly in its own env: block "
        "or data/risk_radar_intl/cn_forward_log.jsonl freezes again"
    )
    assert "python -m scripts.build_china" in step_body or "python -m scripts.build_china\n" in step_body, (
        "build_china spine step no longer invokes scripts.build_china — arm placement stale"
    )

    # Job-wide check: the `asia:` job's own top-level env: (before the first step)
    # must not set COLLECT_LANE — only individual steps/calls may.
    job_start = src.find("\n  asia:\n")
    assert job_start != -1, "asia-close.yml no longer defines the `asia` job?"
    first_step = src.find("\n      - name:", job_start)
    job_header = src[job_start:first_step]
    assert "COLLECT_LANE" not in job_header, (
        "asia-close.yml's `asia` job sets COLLECT_LANE job-wide — this un-gates every "
        "other ledger_lane_armed() writer reachable in the job (house law violation)"
    )


def test_asia_close_arms_hk_spine_call_inline_not_whole_step():
    """scripts.build_hk runs inside the shared 'CN/HK builder band A' step alongside
    ~25 other independent brun() calls (sector_desk, baskets_cn, validation, ...).
    Arming that whole step's env: would be step-wide overreach even though it isn't
    job-wide, so the fix must be the SAME inline `VAR=val brun ...` idiom already
    used for baskets_hk/rotation_events_hk/rotation_events_cn — scoped to the one
    build_hk invocation only. Mirrors
    tests/test_ignition_lane_gate.py::test_asia_close_arms_hk_baskets_lane."""
    import re

    src = WORKFLOW.read_text(encoding="utf-8")
    lines = [l for l in src.splitlines()
             if re.search(r"\bscripts\.build_hk\b", l) and not l.strip().startswith("#")]
    assert lines, "asia-close.yml no longer invokes scripts.build_hk?"
    for line in lines:
        assert "COLLECT_LANE=nightly" in line, (
            "asia-close.yml's scripts.build_hk invocation must arm COLLECT_LANE=nightly "
            "inline or data/risk_radar_intl/hk_forward_log.jsonl freezes again"
        )

    # The step's OWN env: block (shared by every other brun() call in the band)
    # must not carry COLLECT_LANE — only the single inline `VAR=val brun hk ...`
    # invocation may.
    step_start = src.find("- name: CN/HK builder band A")
    assert step_start != -1, "asia-close.yml no longer has the CN/HK builder band A step?"
    env_start = src.find("\n        env:", step_start)
    run_start = src.find("\n        run:", step_start)
    assert 0 < env_start < run_start
    step_env_block = src[env_start:run_start]
    assert "COLLECT_LANE" not in step_env_block, (
        "CN/HK builder band A step's shared env: block sets COLLECT_LANE — this would "
        "arm every other brun() call in the band, not just build_hk/baskets_hk/"
        "rotation_events_hk (step-wide overreach, same class of violation as job-wide)"
    )


def test_daily_yml_untouched_by_gd4a():
    """Non-goal: GD-4A explicitly does not touch daily.yml's COLLECT_LANE contract
    (daily.yml already sets COLLECT_LANE=nightly job-wide for the US lane and never
    RUNS build_china/build_hk as a module — out of scope per the commission). Word-
    bounded so build_china_library / build_hk_library / build_hk_pick_lab rescue-net
    references (which DO legitimately appear in daily.yml) don't false-positive."""
    import re

    daily = ROOT / ".github" / "workflows" / "daily.yml"
    assert daily.exists()
    src = daily.read_text(encoding="utf-8")
    assert not re.search(r"\bscripts\.build_china\b", src), (
        "daily.yml now runs scripts.build_china — GD-4A's scope assumption "
        "(daily.yml never runs the CN builder) no longer holds"
    )
    assert not re.search(r"\bscripts\.build_hk\b", src), (
        "daily.yml now runs scripts.build_hk — GD-4A's scope assumption "
        "(daily.yml never runs the HK builder) no longer holds"
    )
