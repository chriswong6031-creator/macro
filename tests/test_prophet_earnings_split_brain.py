"""tests/test_prophet_earnings_split_brain.py — R0-C: the legacy earnings arm is fenced.

WHAT THIS FILE PINS (earnings/company-event suite Wave 0, ticket R0-C).

Prophet had two earnings paths. The governed one — ``_load_earnings_evidence_context``
/ ``_earnings_plan_annotation`` — runs strictly after ``select_candidates`` and is
hard-fenced to annotation. The other was a split-brain: ``engine/prophet_bridge.py``
and ``engine/prophet_stage_shadow.py``, both PRODUCTION modules on the nightly lane,
imported ``engine/prophet_stage_fusion.py`` — a RESEARCH BACKTEST HARNESS — to reach a
handful of point-in-time primitives, and through it read a legacy earnings parquet.

Two properties are pinned here.

1. SEVERANCE. No production module imports the research harness. The shared
   primitives live in ``engine/prophet_stage_inputs.py``; the harness re-exports them,
   so published PSF/PSQ results stay reproducible against identical code.

2. BLAST RADIUS. The legacy earnings source cannot reach candidate identity, order,
   rank, size, gate, geometry, options, or tranches. Its ONLY lawful channel is the
   provisionally-promoted hold-horizon leash (PSQ-H1, 2026-07-20), and that channel is
   pinned to its ratified numbers — 45 base, 56 tilted, nothing else.

WHY A THIRD PROPERTY IS DISCLOSURE, NOT INVARIANCE. The legacy parquet
(``data/stage_analysis/backfill/earnings_calls.parquet``) is gitignored, was never
committed, and has no fetch/publish pair, so it is ABSENT on every CI and deploy host.
The leash's earnings arm therefore never fires in production: the tilt has been inert
since it shipped. That is not repaired by deleting the leash (a promoted authority
needs an operator ruling) nor by re-pointing the join at a different, differently-scaled
artifact (that would silently re-scale a promoted construction). What IS repaired is
that the starvation used to be invisible — "no positive earnings call" and "no
earnings-call data at all" produced identical output. They are now distinguishable in
the plan block and in the forward shadow that arms the leash's auto-demote clause.

Run: python3 -m pytest tests/test_prophet_earnings_split_brain.py -q
"""
from __future__ import annotations

import ast
import json
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import engine.prophet_bridge as pb  # noqa: E402
import engine.prophet_stage_inputs as psi  # noqa: E402
import engine.prophet_stage_shadow as pss  # noqa: E402

RESEARCH_HARNESS = "prophet_stage_fusion"

# The research harness may be imported ONLY by the research CLIs that produce the
# point-in-time PSF/PSQ ledger, and by tests. Everything else is production.
HARNESS_IMPORT_ALLOWLIST = {
    "scripts/run_prophet_stage_fusion.py",
    "scripts/run_prophet_stage_quality.py",
}

PRODUCTION_ROOTS = ("engine", "scripts", "app", "collectors", "lib", "admin", "worker")

# Every plan field the R0-C ticket enumerates, by the key that carries it.
PLAN_FIELDS = (
    "id",              # candidate identity
    "asset",
    "direction",
    "_conviction_score",   # rank
    "_act_level",          # rank
    "_gate_go",            # gate
    "trigger",             # geometry
    "entry",               # geometry
    "invalidation",        # geometry
    "targets",             # geometry
    "_r_unit",             # size
    "tranche",             # tranches / size
    "horizon_days",        # horizon
    "min_hold_days",       # horizon
    "option_contract",     # options
)


# --------------------------------------------------------------------------- #
# Harness fixtures — a real parquet on disk, read through the real loader.      #
# --------------------------------------------------------------------------- #
def _write_ec_parquet(data_root: Path, rows: list[tuple[str, str, float]]) -> Path:
    """Write a real earnings_calls parquet in the layout the loader expects."""
    p = data_root / "stage_analysis" / "backfill" / "earnings_calls.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "document_ticker": [r[0] for r in rows],
        "call_date": pd.to_datetime([r[1] for r in rows]),
        "earnings_call_sent": [r[2] for r in rows],
    }).to_parquet(p)
    return p


def _make_buy(ticker: str, score: int, act_level: int, spot: float) -> dict:
    return {
        "ticker": ticker,
        "dir": "up",
        "state": "TURN SIGNALED",
        "conviction": {"score": score, "band": "neutral",
                       "drivers": ["momentum"], "cautions": ["macro risk"],
                       "trust_tier": {"en": "tier-2"}},
        "entry_signal": {"act_level": act_level, "status": "partial", "spot": spot,
                         "stop": spot * 0.95, "chase_above": spot * 1.05,
                         "atr_pct": 2.0, "entry_grade": "solid",
                         "horizon": {"d21": 0.5}},
        "hold": {"state": "HOLD", "anchor": "2026-07-02",
                 "invalidation": spot * 0.90},
        "coiled": {"coiled": False, "star": False},
        "signal": {"above200": True, "weekly_bull": True},
    }


def _standouts_file(tmp_dir: Path) -> Path:
    p = tmp_dir / "us_standouts.json"
    p.write_text(json.dumps({
        "as_of": "2026-07-02",
        "gate_go": False,
        "buy": [
            _make_buy("MSFT", score=80, act_level=3, spot=420.0),
            _make_buy("AAPL", score=70, act_level=3, spot=150.0),
        ],
    }))
    return p


def _run_origination(tmp_path: Path, monkeypatch, *, ec_rows, stage_at_entry=None,
                     tag: str = "run") -> list[dict]:
    """Run originate_plans against an isolated data root.

    ``ec_rows=None`` leaves the legacy parquet ABSENT (the production configuration on
    every CI and deploy host). A list of rows writes a real parquet the real loader
    reads — this is the only way to exercise the present-file case, since the file is
    gitignored and never ships.

    ``stage_at_entry`` optionally substitutes the Weinstein stage lookup. The stage arm
    is not what these tests exercise; the earnings arm stays fully real end to end.
    """
    data_root = tmp_path / tag / "data"
    work = tmp_path / tag / "work"
    data_root.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)

    # A healthy regime, so the bear gate is not what forces the leash to 1.0.
    (data_root / "regime").mkdir(parents=True, exist_ok=True)
    (data_root / "regime" / "latest.json").write_text(json.dumps({
        "risk_radar": {"context_gate": {"spy_below_200dma": False}, "state": "caution"}
    }))

    if ec_rows is not None:
        _write_ec_parquet(data_root, ec_rows)

    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: data_root)

    if stage_at_entry is not None:
        monkeypatch.setattr(psi, "stage_at_entry", stage_at_entry)
        monkeypatch.setattr(
            psi, "load_ticker_prices",
            lambda ticker, root: (
                pd.Series(range(400), dtype=float,
                          index=pd.bdate_range("2020-01-01", periods=400)) + 100.0,
                None,
            ),
        )

    return pb.originate_plans(_standouts_file(work), asof="2026-07-02",
                              existing_ids=set(), thetadata_store=None)


def _projection(plans: list[dict]) -> list[dict]:
    """The ticket's full enumerated field set, in candidate order."""
    return [{k: p.get(k) for k in PLAN_FIELDS} for p in plans]


def _differing_keys(a: list[dict], b: list[dict]) -> set[str]:
    """Every plan key whose value differs between two same-length plan lists."""
    assert [p["id"] for p in a] == [p["id"] for p in b], "plan id/order diverged"
    diff: set[str] = set()
    for pa, pb_ in zip(a, b):
        for key in set(pa) | set(pb_):
            if pa.get(key) != pb_.get(key):
                diff.add(key)
    return diff


# --------------------------------------------------------------------------- #
# 1. Severance — no production module imports the research backtest harness.    #
# --------------------------------------------------------------------------- #
def _imports_of(path: Path) -> set[str]:
    """Module names this file imports, via AST (a docstring mention is not a read)."""
    try:
        # Parsing the whole production tree surfaces unrelated SyntaxWarnings from other
        # modules (e.g. a stray regex escape). Those are not this guard's subject and
        # must not be reported against it.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):  # pragma: no cover - not our subject
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
                names.update(f"{node.module}.{a.name}" for a in node.names)
    return names


def test_no_production_module_imports_the_research_backtest_harness():
    """A 2022-26 backtest harness must not be a live dependency of nightly origination.

    This is the R0-C severance gate. It fails on the unfixed tree, where
    engine/prophet_bridge.py and engine/prophet_stage_shadow.py both import it.
    """
    offenders = []
    for root in PRODUCTION_ROOTS:
        for path in sorted((_REPO / root).rglob("*.py")):
            rel = path.relative_to(_REPO).as_posix()
            if rel in HARNESS_IMPORT_ALLOWLIST:
                continue
            if any(RESEARCH_HARNESS in name for name in _imports_of(path)):
                offenders.append(rel)
    assert offenders == [], (
        f"production modules import the research harness {RESEARCH_HARNESS!r}: {offenders}. "
        "The shared point-in-time primitives belong in engine/prophet_stage_inputs.py."
    )


def test_the_research_harness_still_exposes_its_documented_surface():
    """Severance must not rewrite research history: every primitive the published PSF/PSQ
    results were produced with is still reachable at its old name, and is the SAME object
    the production module owns (one definition, not a fork)."""
    from engine import prophet_stage_fusion as psf

    for name in ("EC_SENT_GATE", "STAGE2", "FRESH_WEEKS_MAX", "BENCH_TICKER",
                 "FWD_HORIZONS", "PARAM_CLEAN15_126", "PARAM_CLEAN8_21"):
        assert getattr(psf, name) == getattr(psi, name), name
    for name in ("load_ec_table", "ec_index", "ec_sent_at_entry", "stage_at_entry",
                 "load_ticker_prices", "load_bench_close"):
        assert getattr(psf, name) is getattr(psi, name), (
            f"{name} forked — research and production must read ONE definition")


# --------------------------------------------------------------------------- #
# 2. Blast radius — with vs without the legacy parquet.                         #
# --------------------------------------------------------------------------- #
def test_legacy_parquet_cannot_alter_any_plan_field_without_the_stage_conjunction(
        tmp_path, monkeypatch):
    """Earnings sentiment ALONE moves nothing.

    Present-file vs absent-file, over the ticket's full enumerated field set — candidate
    IDs and order, rank, size, gate, geometry, horizon, options, tranches — with the
    ratified Stage-2 conjunction unmet (no price store, so the stage is unknown). This is
    the production shape on every host: identical plans either way.
    """
    absent = _run_origination(tmp_path, monkeypatch, ec_rows=None, tag="absent")
    monkeypatch.undo()
    present = _run_origination(
        tmp_path, monkeypatch,
        ec_rows=[("MSFT", "2026-06-01", 90.0), ("AAPL", "2026-06-02", 95.0)],
        tag="present")

    assert [p["id"] for p in present] == [p["id"] for p in absent]
    assert _projection(present) == _projection(absent)
    # And the earnings reading really was loaded — otherwise this proves nothing.
    assert present[0]["stage_tilt"]["ec_source_state"] == psi.EC_SOURCE_AVAILABLE
    assert absent[0]["stage_tilt"]["ec_source_state"] == psi.EC_SOURCE_UNAVAILABLE


def test_legacy_parquet_blast_radius_is_exactly_the_ratified_hold_horizon(
        tmp_path, monkeypatch):
    """With the Stage-2 conjunction MET, the legacy source reaches exactly two plan
    keys: the hold horizon (45 -> 56, the PSQ-ratified leash) and the stage_tilt
    provenance block that discloses it.

    Everything else the ticket enumerates — candidate identity and order, rank, size,
    gate, geometry, options, tranches — is byte-identical. This is the assertion that
    goes red if a future edit lets earnings sentiment reach rank, size, or geometry.
    """
    stage2 = lambda close, vol, bench, entry_date: (2, 5, 100)  # noqa: E731

    absent = _run_origination(tmp_path, monkeypatch, ec_rows=None,
                              stage_at_entry=stage2, tag="s2absent")
    monkeypatch.undo()
    present = _run_origination(
        tmp_path, monkeypatch,
        ec_rows=[("MSFT", "2026-06-01", 90.0), ("AAPL", "2026-06-02", 95.0)],
        stage_at_entry=stage2, tag="s2present")

    assert _differing_keys(present, absent) == {"horizon_days", "stage_tilt"}, (
        "the legacy earnings source reached a plan field outside the ratified "
        "hold-horizon lane")

    # Candidate identity/order, rank, size, gate, geometry, options, tranches: identical.
    for key in PLAN_FIELDS:
        if key == "horizon_days":
            continue
        assert [p.get(key) for p in present] == [p.get(key) for p in absent], key

    # The one permitted channel, at its ratified numbers and nothing else.
    assert {p["horizon_days"] for p in absent} == {pb.HORIZON_DAYS_DEFAULT} == {45}
    assert {p["horizon_days"] for p in present} == {
        round(pb.HORIZON_DAYS_DEFAULT * pb.STAGE_TILT_LEASH)} == {56}
    assert {p["stage_tilt"]["leash"] for p in present} == {pb.STAGE_TILT_LEASH}
    assert {p["stage_tilt"]["leash"] for p in absent} == {1.0}


def test_leash_horizon_matrix_is_frozen():
    """The ratified leash matrix. Any refactor of the inputs layer must leave every one
    of these resolved horizons untouched (R0-C acceptance gate 4)."""
    from tests.test_prophet_stage_tilt import _tilt_inputs

    matrix = [
        # (stage, ec_sent, bear, demoted, ec_load_ok) -> horizon_days
        ((2, 30.0, False, False, True), 56),   # every condition met
        ((2, 24.0, False, False, True), 56),   # exactly at the gate
        ((2, 23.0, False, False, True), 45),   # below the gate
        ((2, None, False, False, True), 45),   # no earnings reading
        ((1, 30.0, False, False, True), 45),   # not Stage-2
        ((3, 30.0, False, False, True), 45),   # not Stage-2
        ((2, 30.0, True, False, True), 45),    # bear gate
        ((2, 30.0, False, True, True), 45),    # auto-demoted
        ((2, 30.0, False, False, False), 45),  # earnings table unreadable
    ]
    for (stage, ec, bear, demoted, ok), expected in matrix:
        ti = _tilt_inputs(stage=stage, ec_sent=ec,
                          ec_call_date=(None if ec is None else "2026-06-01"),
                          bear=bear, demoted=demoted, ec_load_ok=ok)
        horizon, _block = pb._compute_stage_tilt("AAA", "2026-07-01", ti)
        assert horizon == expected, (stage, ec, bear, demoted, ok)


# --------------------------------------------------------------------------- #
# 3. Disclosure — a starved earnings null is not an honest one.                 #
# --------------------------------------------------------------------------- #
def test_absent_earnings_source_is_disclosed_in_every_plan(tmp_path, monkeypatch):
    """On a host with no earnings-call source, every plan says so.

    Without this the leash reads as a healthy negative on every deploy host, which is
    indistinguishable from a real "no name qualified" result.
    """
    plans = _run_origination(tmp_path, monkeypatch, ec_rows=None, tag="disclose")
    assert plans, "fixture produced no plans"
    for plan in plans:
        block = plan["stage_tilt"]
        assert block["ec_source_state"] == psi.EC_SOURCE_UNAVAILABLE
        assert block["ec_source_reason"], "an unavailable source must carry a reason"
        assert "earnings_calls.parquet" in str(block["ec_source_path"])
        assert block["leash"] == 1.0
        assert "validated" not in json.dumps(block).lower()


def test_present_earnings_source_is_disclosed_as_available(tmp_path, monkeypatch):
    plans = _run_origination(
        tmp_path, monkeypatch,
        ec_rows=[("MSFT", "2026-06-01", 90.0)], tag="available")
    for plan in plans:
        block = plan["stage_tilt"]
        assert block["ec_source_state"] == psi.EC_SOURCE_AVAILABLE
        assert block["ec_source_reason"] is None


def test_source_record_separates_absent_from_unreadable(tmp_path):
    """Three distinguishable outcomes, one read: absent, unreadable, present."""
    absent = psi.resolve_ec_source(tmp_path / "nope.parquet")
    assert absent["state"] == psi.EC_SOURCE_UNAVAILABLE
    assert absent["reason"]

    corrupt = tmp_path / "corrupt.parquet"
    corrupt.write_text("not a parquet")
    table, record = psi.load_ec_table_with_source(corrupt)
    assert table.empty, "an unreadable source must still fail open to an empty table"
    assert record["state"] == psi.EC_SOURCE_UNAVAILABLE
    assert "unreadable" in record["reason"]

    good = _write_ec_parquet(tmp_path, [("AAA", "2026-06-01", 30.0)])
    table, record = psi.load_ec_table_with_source(good)
    assert record["state"] == psi.EC_SOURCE_AVAILABLE
    assert record["reason"] is None
    assert record["rows"] == 1 == len(table)


# --------------------------------------------------------------------------- #
# 4. The forward shadow that arms the auto-demote clause.                       #
# --------------------------------------------------------------------------- #
def _shadow_row(pid: str, stage: int, ec_sent: float | None, fwd126: float | None) -> dict:
    return {
        "schema": pss.LEDGER_SCHEMA, "id": pid, "asset": pid.split("-")[0],
        "direction": "BULL", "signal_date": "2021-02-24",
        "stage_at_entry": stage,
        "last_ec": ({"sent": ec_sent, "call_date": "2021-01-01"}
                    if ec_sent is not None else None),
        "fwd": ({"fwd_ret_126": fwd126} if fwd126 is not None else {}),
    }


def test_shadow_marks_a_zero_earnings_cohort_as_starved_not_measured(tmp_path):
    """A median_tilt computed on ZERO earnings-tagged entries must be visibly different
    from a real non-positive tilt.

    The hold-leash's auto-demote clause reads median_tilt.n_matured_126.stage2_ec. With
    no earnings source that cohort is empty by ABSENCE, so the clause can never be
    reached and the provisional promotion can never be graded or self-demoted. That has
    to be legible in the artifact, not inferred.
    """
    starved = {f"A{i}-BULL-1": _shadow_row(f"A{i}-BULL-1", pss.STAGE2, None, 5.0)
               for i in range(4)}
    pss._write_ledger(tmp_path, starved)
    s = pss.summarize(root=tmp_path)
    cov = s["median_tilt"]["ec_coverage"]

    assert cov["state"] == psi.EC_SOURCE_UNAVAILABLE
    assert cov["n_rows_with_ec"] == 0
    assert cov["n_matured_126_with_ec"] == 0
    assert cov["n_rows"] == 4
    assert "not a measured result" in cov["note"] or "empty-sample" in cov["note"]
    # The cohort is empty, so every number in the block is a null — not a measured <= 0.
    assert s["median_tilt"]["n_matured_126"]["stage2_ec"] == 0
    assert s["median_tilt"]["diff"] is None


def test_shadow_marks_a_measured_cohort_as_covered(tmp_path):
    """The same shape with real earnings tags reports covered — so the starved state
    above is a real signal, not a constant."""
    measured = {
        "A-BULL-1": _shadow_row("A-BULL-1", pss.STAGE2, 30.0, 10.0),
        "B-BULL-1": _shadow_row("B-BULL-1", pss.STAGE2, 40.0, 20.0),
        "C-BULL-1": _shadow_row("C-BULL-1", pss.STAGE2, 10.0, 4.0),
        "D-BULL-1": _shadow_row("D-BULL-1", 1, 30.0, 6.0),
    }
    pss._write_ledger(tmp_path, measured)
    s = pss.summarize(root=tmp_path)
    cov = s["median_tilt"]["ec_coverage"]

    assert cov["state"] == psi.EC_SOURCE_AVAILABLE
    assert cov["n_rows_with_ec"] == 4
    assert cov["n_matured_126_with_ec"] == 4
    assert s["median_tilt"]["n_matured_126"]["stage2_ec"] == 2
    assert s["median_tilt"]["diff"] is not None


def test_shadow_summary_reports_its_earnings_source_state(tmp_path):
    """The summary states whether an earnings source existed on the host at all."""
    pss._write_ledger(tmp_path, {"A-BULL-1": _shadow_row("A-BULL-1", 2, None, None)})
    s = pss.summarize(root=tmp_path)
    assert s["ec_source"]["state"] in (psi.EC_SOURCE_AVAILABLE, psi.EC_SOURCE_UNAVAILABLE)
    assert "earnings_calls.parquet" in str(s["ec_source"]["path"])
    # The disclosure must not break the shadow's standing context-only pins.
    assert s["is_context_only"] is True and s["display_only"] is True
    blob = json.dumps(s).lower()
    assert "validated" not in blob
    for verb in (" buy ", " sell ", " short "):
        assert verb not in blob


def test_tag_entries_reports_the_earnings_source_state(tmp_path, monkeypatch):
    """The function that performs the join reports whether it had a source."""
    monkeypatch.delenv("COLLECT_LANE", raising=False)
    site_root = tmp_path / "site"
    (site_root / "prophet" / "plans").mkdir(parents=True)
    result = pss.tag_entries(root=tmp_path, site_root=site_root,
                             ec_path=tmp_path / "absent.parquet")
    assert result["ec_source"]["state"] == psi.EC_SOURCE_UNAVAILABLE
    assert result["ec_source"]["reason"]


# --------------------------------------------------------------------------- #
# 5. Authority constraints (DNR:KILL-STAGE-WIN-GATE / PSQ-H1 provisional).       #
# --------------------------------------------------------------------------- #
def test_the_earnings_gate_is_not_repointed_at_a_differently_scaled_artifact():
    """EC_SENT_GATE = 24 is calibrated to EquityDesk's 0-100 earnings_call_sent. The
    repo's own data/earnings_calls/scores.parquet carries a -1..1 ``sentiment`` — a
    sibling name, a different scale. Re-pointing the join there would silently re-scale
    a promoted construction rather than repair it."""
    assert psi.EC_SENT_GATE == 24
    resolved = psi.ec_source_path().as_posix()
    assert resolved.endswith("stage_analysis/backfill/earnings_calls.parquet")
    assert "earnings_calls/scores.parquet" not in resolved


def test_the_disclosure_never_enters_the_eligibility_test():
    """ec_source_state is disclosure. Flipping it must not move the leash."""
    from tests.test_prophet_stage_tilt import _tilt_inputs

    available = _tilt_inputs(ec_source_state=psi.EC_SOURCE_AVAILABLE)
    unavailable = _tilt_inputs(ec_source_state=psi.EC_SOURCE_UNAVAILABLE)
    h_a, block_a = pb._compute_stage_tilt("AAA", "2026-07-01", available)
    h_u, block_u = pb._compute_stage_tilt("AAA", "2026-07-01", unavailable)

    assert h_a == h_u == 56
    assert block_a["leash"] == block_u["leash"] == pb.STAGE_TILT_LEASH
    assert block_a["eligible"] is block_u["eligible"] is True
    assert block_a["ec_source_state"] != block_u["ec_source_state"]


@pytest.mark.parametrize("symbol", ["STAGE_TILT_LEASH", "STAGE_TILT_DEMOTE_MIN_MATURED"])
def test_the_promoted_leash_mechanism_is_still_present(symbol):
    """R0-C fences the legacy source; it does not retire a promoted authority. Removing
    the leash or its auto-demote floor requires an operator ruling, not a refactor."""
    assert hasattr(pb, symbol)
    assert pb.STAGE_TILT_LEASH == 1.25
    assert pb.STAGE_TILT_DEMOTE_MIN_MATURED == 30
