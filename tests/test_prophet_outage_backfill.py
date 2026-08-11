"""tests/test_prophet_outage_backfill.py — the force-majeure 2026-08-09 replay.

DESIGN OF RECORD: research/PROPHET_OUTAGE_BACKFILL_2026_08.md.  Operator order
2026-08-11: replay the ONE receipted origination event the 2026-08-09 bake refused
on a poisoned mixed-vintage flag.  The standing no-backfill law
(research/PROPHET_LEDGER_SCHEMA.md) is not repealed — it is exempted for exactly
this event, and these tests are what keeps the exemption from widening.

WHAT EACH GROUP PINS

  SEGREGATION (§0.6) — the load-bearing pair.  The set of plans stamped
  ``origination_mode`` starting ``outage_backfill`` and the set enumerated in
  ``data/prophet/backfill_disclosures.json`` must be THE SAME SET, in both
  directions.  A backfilled plan missing from the disclosure is an undisclosed
  backfill; a disclosed id with no plan is a disclosure that lies.  Both are the
  failure this artifact exists to make impossible.  Modelled on
  ``tests/test_grade_us_board.py::test_no_graded_rows_were_backfilled_into_a_disclosed_null_era``.

  PASSTHROUGH (§0.7) — the nightly must neither drop, rewrite, nor choke on a plan
  carrying the two extra fields, and the stamp must SURVIVE INTO ``index.json``.
  That last clause is the whole point: every track-record and calibration aggregate
  reads the index, not the per-plan files, so a stamp that stops at the plan file is
  a stamp no consumer can split a rate by.

  COLLISION (§0.4) — live wins.  Two independent mechanisms have to hold: the
  engine's own open-plan block, and the post-process drop that catches the case the
  block cannot see (a live plan already CLOSED in the ledger, whose ticker would
  otherwise get a second episode).

  DETERMINISM + IDEMPOTENCE — same pinned SHAs → same minted set; a window already
  recorded in the disclosure refuses instead of double-minting.

  RECEIPT SHAPE — not cosmetic.  ``scripts/audit_prophet_plan_chronology.py``
  validates EVERY receipt in a plan's creation commit before auditing that plan, so
  a malformed backfill receipt would break chronology audits for every plan created
  from that commit forward.  Pinned against the real validator, not a copy of it.

NOTHING HERE WRITES THE REPO.  Every executing test builds a throwaway git repo
under ``tmp_path``.  The two real-tree census tests are read-only and skip when the
checkout is sparse (agent worktrees commonly omit ``site/`` and ``data/``); they are
the ones that run for real in CI, where the checkout is complete.

Run: TZ=UTC python3 -m pytest tests/test_prophet_outage_backfill.py -q
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import scripts.backfill_prophet_outage as bf  # noqa: E402
import scripts.build_prophet as bp  # noqa: E402
from scripts.audit_prophet_plan_chronology import (  # noqa: E402
    _validate_receipt_shape,
)

REAL_PLANS_DIR = _REPO / "site" / "prophet" / "plans"
REAL_DISCLOSURES = _REPO / bf.DISCLOSURES_RELPATH


@pytest.fixture(autouse=True)
def _arena_writes_to_tmp(tmp_path, monkeypatch):
    """Send the Prophet Arena's ledgers to tmp for every test in this file.

    ``build_prophet.main()`` calls ``run_arena(..., repo_root=_REPO)``, which writes
    seven TRACKED files under ``data/prophet_arena/``.  Same reasoning (and same
    fixture) as tests/test_prophet_w1_intake_repair.py: redirect ``repo_root`` rather
    than stub the hook, so it still executes end to end here.
    """
    try:
        import engine.prophet_arena as arena
    except Exception:  # noqa: BLE001 - minimal-deps job that never reaches main()
        return
    real = arena.run_arena
    monkeypatch.setattr(
        arena, "run_arena",
        lambda *a, **kw: real(*a, **{**kw, "repo_root": tmp_path}))


# ---------------------------------------------------------------------------
# synthetic pinned repo
# ---------------------------------------------------------------------------

#: last_session_on_or_before("2026-08-09") — the Friday close the replay prices off.
PRICE_THROUGH = "2026-08-07"


def _buy_row(ticker: str, *, spot: float = 100.0, priority: float = 90.0,
             anchor: str = "2026-07-31", signal: dict | None = None) -> dict:
    """One admitted ``us_standouts.json["buy"]`` row that originates cleanly.

    Shaped after tests/test_prophet_w1_intake_repair.py::_buy — the known-good
    admitted row — so a failure here is about the backfill, never about whether the
    fixture clears intake.  Pass ``signal`` to attach a tier contract and exercise
    ``_resolve_candidate_signal_dates`` (see ``_late_anchor_row``).
    """
    row = {
        "ticker": ticker,
        "dir": "up",
        "conviction": {
            "score": 70, "band": "neutral", "drivers": ["momentum"],
            "cautions": ["macro risk"], "trust_tier": {"en": "tier-2"},
        },
        "entry_signal": {
            "act_level": 3, "status": "partial", "spot": spot,
            "chase_above": spot * 1.03, "atr_pct": 2.0, "entry_grade": "solid",
        },
        "hold": {"state": "HOLD", "anchor": anchor, "invalidation": spot * 0.9},
        "prophet": {"version": "us_prophet_v1", "score": priority},
    }
    if signal is not None:
        row["signal"] = signal
    return row


def _late_anchor_row(ticker: str, *, spot: float = 50.0) -> dict:
    """A row the chronology gate MUST refuse.

    Reproduces the exact refusal the R6 audit found on five real candidates and the
    live dry run reproduced verbatim: a formation anchor that POSTDATES the tier
    event the plan claims to descend from.  The tier contract has to be present or
    ``_resolve_candidate_signal_dates`` takes its legacy path and never checks.
    """
    return _buy_row(
        ticker, spot=spot, anchor="2026-08-20",
        signal={
            "tier_cascade": "T2",
            "tier_event_date": "2026-08-03",
            "tier_observed_date": PRICE_THROUGH,
            "tier_observation_provisional": False,
        },
    )


def _board(buys: list[dict], *, price_through: str = PRICE_THROUGH) -> dict:
    """The healed 2026-08-07 board: mixed_vintage FALSE is the flipped input.

    ``price_through`` is a parameter because the origination clock requires it to be
    ``last_session_on_or_before(run date)``: the replay reads the Friday board, while
    the nightly harness below reads the board that nightly built.
    """
    return {
        "as_of": price_through,
        "staleness": {
            "price_through": price_through,
            "delayed": False,
            "unknown": False,
            "basis": "panel_majority",
            "inputs": {"panel": {"mixed_vintage": False}},
        },
        "gate_go": False,
        "buy": buys,
    }


def _seed_plan(plan_id: str, ticker: str, *, recorded_at: str,
               origination_mode: str | None = None) -> dict:
    plan: dict = {
        "schema": "prophet.trade_plan/v1",
        "id": plan_id,
        "asof": recorded_at,
        "recorded_at": recorded_at,
        "asset": ticker,
        "direction": "BULL",
        "thesis": "seeded plan",
        "source_engines": ["us_standouts_buy_lane"],
        "trigger": 100.0,
        "entry": 100.0,
        "invalidation": 90.0,
        "targets": [115.0, 130.0],
        "horizon_days": 45,
        "min_hold_days": 10,
        "tranche": 1,
        "option_contract": None,
        "authority_tier": "display",
        "signal_date": recorded_at,
        "_signal_date": recorded_at,
        "_conviction_score": 50,
    }
    if origination_mode is not None:
        plan["origination_mode"] = origination_mode
        plan["backfill_executed_at"] = "2026-08-11T00:00:00+00:00"
    return plan


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _pinned_repo(tmp_path: Path, *, buys: list[dict],
                 plans: dict[str, dict] | None = None,
                 closed_ids: tuple[str, ...] = ()) -> tuple[Path, str]:
    """A throwaway git repo carrying a board, a plan baseline and a ledger.

    The script reads every input through ``git show``/``ls-tree`` at a pinned SHA, so
    a real (tiny) repo exercises the actual extraction path instead of a stub.
    """
    repo = tmp_path / "pinned_repo"
    (repo / "site" / "factordata").mkdir(parents=True)
    (repo / "site" / "prophet" / "plans").mkdir(parents=True)
    (repo / "data" / "prophet").mkdir(parents=True)

    (repo / bf.BOARD_RELPATH).write_text(json.dumps(_board(buys)), encoding="utf-8")
    for plan_id, plan in (plans or {}).items():
        (repo / bf.PLANS_RELDIR / f"{plan_id}.json").write_text(
            json.dumps(plan), encoding="utf-8")
    (repo / bf.LEDGER_RELPATH).write_text(
        "".join(
            json.dumps({"schema": "prophet.ledger/v1", "id": pid, "outcome": "T1_HIT"}) + "\n"
            for pid in closed_ids
        ),
        encoding="utf-8",
    )

    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "test")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "pinned inputs")
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True,
    ).stdout.decode().strip()
    return repo, sha


def _replay(repo: Path, sha: str, *, execute: bool = False,
            executed_at: str = "2026-08-11T00:00:00+00:00") -> dict:
    return bf.run_backfill(
        repo, board_commit=sha, plans_baseline=sha,
        executed_at=executed_at, execute=execute,
    )


# ===========================================================================
# 1. SEGREGATION (§0.6) — the two sets are the same set, both directions
# ===========================================================================

def _stamped(plans: dict[str, dict]) -> set[str]:
    return {
        plan_id for plan_id, plan in plans.items()
        if str(plan.get("origination_mode") or "").startswith("outage_backfill")
    }


def _disclosed_ids(document: dict) -> set[str]:
    return {
        str(entry["plan_id"])
        for row in (document.get("backfills") or [])
        for entry in (row.get("minted") or [])
    }


class TestSegregation:
    """Every backfilled plan is disclosed, and every disclosed plan exists."""

    def test_the_stamped_set_and_the_disclosed_set_are_identical(self, tmp_path):
        repo, sha = _pinned_repo(tmp_path, buys=[
            _buy_row("AAA"), _buy_row("BBB", spot=50.0), _buy_row("CCC", spot=25.0),
        ])
        _replay(repo, sha, execute=True)

        on_disk = {
            json.loads(p.read_text(encoding="utf-8"))["id"]:
                json.loads(p.read_text(encoding="utf-8"))
            for p in (repo / bf.PLANS_RELDIR).glob("*.json")
        }
        document = json.loads(
            (repo / bf.DISCLOSURES_RELPATH).read_text(encoding="utf-8"))

        stamped = _stamped(on_disk)
        disclosed = _disclosed_ids(document)
        assert stamped, "no plan carries the backfill stamp — the assertions below would be vacuous"
        assert stamped == disclosed, (
            f"the stamped set and the disclosed set disagree: "
            f"stamped-not-disclosed={sorted(stamped - disclosed)}, "
            f"disclosed-not-stamped={sorted(disclosed - stamped)}. "
            "An undisclosed backfill is exactly what this artifact exists to prevent."
        )

    def test_every_backfilled_plan_is_recorded_inside_the_disclosed_window(self, tmp_path):
        repo, sha = _pinned_repo(tmp_path, buys=[_buy_row("AAA"), _buy_row("BBB")])
        result = _replay(repo, sha, execute=True)
        document = json.loads(
            (repo / bf.DISCLOSURES_RELPATH).read_text(encoding="utf-8"))
        row = document["backfills"][-1]
        window = row["window"]

        assert result["minted"], "nothing minted — window assertion would be vacuous"
        for plan in result["minted"]:
            assert window["from"] <= plan["recorded_at"] <= window["to"], (
                f"{plan['id']} claims recorded_at={plan['recorded_at']}, outside the "
                f"disclosed window {window}. The replay may mint ONE event."
            )
            assert plan["recorded_at"] == bf.BACKFILL_ASOF

    def test_the_stamp_names_the_event_and_the_execution_is_dated(self, tmp_path):
        repo, sha = _pinned_repo(tmp_path, buys=[_buy_row("AAA")])
        result = _replay(repo, sha, execute=True, executed_at="2026-08-11T03:14:15+00:00")
        for plan in result["minted"]:
            assert plan["origination_mode"] == "outage_backfill_2026_08_09"
            assert plan["backfill_executed_at"] == "2026-08-11T03:14:15+00:00"
            # Same engine, same rule: the SELECTION era must not be forged into
            # something new just because the write happened later.
            assert plan["selection_era"] == "anticipation-v1-2026-08-08"

    def test_a_live_plan_carries_no_backfill_stamp(self, tmp_path):
        """The null IS "live", and it is printed rather than defaulted to a word."""
        repo, sha = _pinned_repo(
            tmp_path, buys=[_buy_row("AAA")],
            plans={"ZZZ-BULL-20260601": _seed_plan(
                "ZZZ-BULL-20260601", "ZZZ", recorded_at="2026-06-01")},
        )
        _replay(repo, sha, execute=True)
        live = json.loads(
            (repo / bf.PLANS_RELDIR / "ZZZ-BULL-20260601.json").read_text(encoding="utf-8"))
        assert "origination_mode" not in live
        assert "backfill_executed_at" not in live

    def test_the_disclosure_arithmetic_reconciles(self, tmp_path):
        """A counterfactual set with an unexplained remainder is not a full set."""
        repo, sha = _pinned_repo(tmp_path, buys=[
            _buy_row("AAA"), _buy_row("BBB", spot=50.0),
        ])
        row = _replay(repo, sha, execute=True)["row"]
        counts = row["counts"]
        assert counts["admitted"] == (
            counts["duplicate_id_blocked"] + counts["eligible_after_skips"]
        )
        assert counts["eligible_after_skips"] == (
            counts["minted"] + counts["collided"] + counts["still_refused"]
        )
        assert counts["minted"] == len(row["minted"])

    def test_the_refused_dates_stay_refused_in_the_disclosure(self, tmp_path):
        """08-03→08-06 are NOT reconstructed, and the document says why (§2)."""
        repo, sha = _pinned_repo(tmp_path, buys=[_buy_row("AAA")])
        row = _replay(repo, sha)["row"]
        never = row["never_reconstructed"]
        assert never["dates"] == [
            "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"
        ]
        assert never["ruling"] == "us-board-frozen-alpha-2026-08"
        assert "frozen" in never["reason"]


# ===========================================================================
# 2. NIGHTLY PASSTHROUGH (§0.7)
# ===========================================================================

def _run_nightly(tmp_path: Path, buys: list[dict], *, asof: str,
                 seed_plans: dict[str, dict],
                 price_history: pd.DataFrame | None = "keep",  # type: ignore[assignment]
                 ) -> tuple[dict, dict[str, Path]]:
    """Run ``build_prophet.main()`` against tmp_path.

    Returns ``(index, paths)``.  The paths come back explicitly because the module
    constants are RESTORED in the ``finally`` below — a caller that read
    ``bp.PLANS_DIR`` afterwards would be reading the real repo, which is how the
    first draft of this harness "passed" against ``site/prophet/plans``.

    Same redirection list as tests/test_prophet_w1_intake_repair.py::_run_main,
    including neutering ``write_showcase``, whose out_path default binds at def time
    and would otherwise write the REAL showcase.json.  ``price_history`` is a
    parameter rather than something a caller patches around this function: an outer
    ``patch`` of the same target loses to the inner one.
    """
    standouts = tmp_path / "us_standouts.json"
    # The board a nightly reads is the board that nightly built: price_through must
    # be the run's own session or the origination clock refuses every candidate and
    # the "live row to contrast against" would never exist.
    standouts.write_text(
        json.dumps(_board(buys, price_through=asof)), encoding="utf-8")

    if price_history == "keep":
        price_history = pd.DataFrame(
            {"close": [100.0 + i for i in range(40)],
             "high": [100.0 + i for i in range(40)],
             "low": [100.0 + i for i in range(40)]},
            index=pd.date_range("2026-06-15", periods=40, freq="B"),
        )

    saved = {name: getattr(bp, name) for name in
             ("STANDOUTS_PATH", "SITE_PROPHET", "PLANS_DIR", "STATES_DIR",
              "INDEX_PATH", "LEDGER_PATH", "LEDGER_DIR", "write_showcase")}
    paths = {
        "plans": tmp_path / "site" / "prophet" / "plans",
        "states": tmp_path / "site" / "prophet" / "states",
        "index": tmp_path / "site" / "prophet" / "index.json",
    }
    try:
        bp.STANDOUTS_PATH = standouts
        bp.SITE_PROPHET = tmp_path / "site" / "prophet"
        bp.PLANS_DIR = paths["plans"]
        bp.STATES_DIR = paths["states"]
        bp.INDEX_PATH = paths["index"]
        bp.LEDGER_DIR = tmp_path / "data" / "prophet"
        bp.LEDGER_PATH = bp.LEDGER_DIR / "ledger.jsonl"
        bp.write_showcase = lambda: None

        paths["plans"].mkdir(parents=True, exist_ok=True)
        for plan_id, plan in seed_plans.items():
            (paths["plans"] / f"{plan_id}.json").write_text(
                json.dumps(plan, indent=2), encoding="utf-8")

        with patch.object(sys, "argv", ["build_prophet", "--date", asof]), \
             patch("scripts.build_prophet._load_price_history_for_management",
                   return_value=price_history):
            bp.main()
        return json.loads(paths["index"].read_text(encoding="utf-8")), paths
    finally:
        for name, value in saved.items():
            setattr(bp, name, value)


class TestNightlyPassthrough:
    """§0.7 — the nightly must carry a backfilled plan, not trip over it."""

    BACKFILLED = "BFIL-BULL-20260731"

    def _seed(self) -> dict[str, dict]:
        return {
            self.BACKFILLED: _seed_plan(
                self.BACKFILLED, "BFIL", recorded_at=bf.BACKFILL_ASOF,
                origination_mode=bf.ORIGINATION_MODE,
            ),
        }

    def test_a_backfilled_plan_is_neither_dropped_nor_rewritten(self, tmp_path):
        index, paths = _run_nightly(
            tmp_path, [_buy_row("AAA")], asof="2026-08-11", seed_plans=self._seed())

        ids = {row["id"] for row in index["plans"]}
        assert self.BACKFILLED in ids, (
            "the nightly dropped the backfilled plan from index.json — a plan the "
            "forward ledger is supposed to advance organically"
        )
        # Plan files are immutable publication records: an EXISTING plan is never
        # rewritten by a later run, so the bytes on disk must still be the seed's.
        on_disk = json.loads(
            (paths["plans"] / f"{self.BACKFILLED}.json").read_text(encoding="utf-8"))
        assert on_disk == self._seed()[self.BACKFILLED]

    def test_the_stamp_survives_into_the_index_row(self, tmp_path):
        """§0.6(c): consumers read index.json, so a stamp that stops at the plan
        file is a stamp no track-record aggregate can split a rate by."""
        index, _paths = _run_nightly(
            tmp_path, [_buy_row("AAA")], asof="2026-08-11", seed_plans=self._seed())
        by_id = {row["id"]: row for row in index["plans"]}

        row = by_id[self.BACKFILLED]
        assert row["origination_mode"] == bf.ORIGINATION_MODE
        assert row["backfill_executed_at"] == "2026-08-11T00:00:00+00:00"
        # And the split actually works: the live rows say "live" by saying nothing.
        live_rows = [r for r in index["plans"] if r["id"] != self.BACKFILLED]
        assert live_rows, "no live row to contrast against — the split is unproven"
        assert all(r.get("origination_mode") is None for r in live_rows)

    def test_the_backfilled_plan_renders_a_management_state(self, tmp_path):
        index, paths = _run_nightly(
            tmp_path, [_buy_row("AAA")], asof="2026-08-11", seed_plans=self._seed())
        by_id = {row["id"]: row for row in index["plans"]}
        row = by_id[self.BACKFILLED]
        assert row["management_status"] == "available"
        assert row["state"]["phase"]
        assert (paths["states"] / f"{self.BACKFILLED}.json").exists()

    def test_a_degraded_backfilled_row_is_still_splittable(self, tmp_path):
        """A missing price history must not silently strip the provenance stamp —
        the degraded row still SHIPS, so it still has to be excludable."""
        index, _paths = _run_nightly(
            tmp_path, [_buy_row("AAA")], asof="2026-08-11", seed_plans=self._seed(),
            price_history=None)
        by_id = {row["id"]: row for row in index["plans"]}
        row = by_id[self.BACKFILLED]
        assert row["management_status"] == "unavailable"
        assert row["origination_mode"] == bf.ORIGINATION_MODE


# ===========================================================================
# 3. COLLISION RULE (§0.4) — live wins
# ===========================================================================

class TestCollisionRuleLiveWins:

    def test_a_live_plan_closed_in_the_ledger_still_wins(self, tmp_path):
        """The case the engine's open-plan block CANNOT see.

        ``active_keys`` only holds OPEN plans, so a live 08-10 plan that the ledger
        has already closed frees its ticker+direction key and the replay would mint a
        SECOND episode for the same name.  The post-process drop is what stops that,
        and this is the only test that exercises it.
        """
        live_id = "AAA-BULL-20260806"
        repo, sha = _pinned_repo(
            tmp_path,
            buys=[_buy_row("AAA"), _buy_row("BBB", spot=50.0)],
            plans={live_id: _seed_plan(live_id, "AAA", recorded_at="2026-08-10")},
            closed_ids=(live_id,),
        )
        row = _replay(repo, sha)["row"]

        minted = {entry["ticker"] for entry in row["minted"]}
        collided = {entry["ticker"]: entry for entry in row["collided"]}
        assert "AAA" not in minted, "live plan lost the collision — AAA was double-minted"
        assert "BBB" in minted, "the uncontested name must still mint"
        assert collided["AAA"]["reason"] == "live_origination_wins"
        assert collided["AAA"]["live_plan_ids"] == [live_id]
        assert collided["AAA"]["counterfactual"]["entry"] is not None, (
            "a dropped collision must still be disclosed display-only (§0.4)"
        )

    def test_an_open_live_plan_is_disclosed_as_a_collision_not_a_refusal(self, tmp_path):
        """The engine blocks it; the disclosure must still call it what it is."""
        live_id = "AAA-BULL-20260806"
        repo, sha = _pinned_repo(
            tmp_path,
            buys=[_buy_row("AAA")],
            plans={live_id: _seed_plan(live_id, "AAA", recorded_at="2026-08-10")},
        )
        row = _replay(repo, sha)["row"]
        assert row["minted"] == []
        collided = {entry["ticker"]: entry for entry in row["collided"]}
        assert collided["AAA"]["reason"] == "live_origination_wins_open_plan_block"
        assert collided["AAA"]["live_plan_ids"] == [live_id]
        assert not row["still_refused"], (
            "a live-won name must be disclosed as a collision, not filed as a gate refusal"
        )

    def test_a_pre_window_open_plan_is_a_refusal_not_a_collision(self, tmp_path):
        """An open plan from BEFORE the window is a block the 08-09 bake would have
        applied itself — honest to record as a refusal, dishonest as a collision."""
        old_id = "AAA-BULL-20260601"
        repo, sha = _pinned_repo(
            tmp_path,
            buys=[_buy_row("AAA")],
            plans={old_id: _seed_plan(old_id, "AAA", recorded_at="2026-06-01")},
        )
        row = _replay(repo, sha)["row"]
        assert row["collided"] == []
        reasons = {entry["ticker"]: entry["reason"] for entry in row["still_refused"]}
        assert reasons["AAA"] == "engine_refusal:reorigination_blocked"

    def test_an_earlier_backfill_row_cannot_win_a_collision_against_itself(self, tmp_path):
        """A plan already stamped as a backfill is not a LIVE incumbent.

        Otherwise the lane would read its own output as the winner and refuse for
        the wrong reason.  Refusing twice is idempotence's job, and it says so.
        """
        prior = "AAA-BULL-20260731"
        plans = {prior: _seed_plan(
            prior, "AAA", recorded_at=bf.BACKFILL_ASOF,
            origination_mode=bf.ORIGINATION_MODE)}
        repo, sha = _pinned_repo(tmp_path, buys=[_buy_row("AAA")], plans=plans)
        row = _replay(repo, sha)["row"]
        assert row["collided"] == []
        # Same id already published → duplicate suppression, not a collision.
        assert row["already_published"]["plan_ids"] == [prior]

    def test_gates_are_recorded_not_overridden(self, tmp_path):
        """§0.8 — a candidate the engine refuses stays refused, with its own reason.

        The anchor postdates the board's own marker date, which is the exact
        ``clock_provenance`` refusal the R6 audit found on five real candidates.
        """
        repo, sha = _pinned_repo(tmp_path, buys=[
            _buy_row("AAA"), _late_anchor_row("LATE"),
        ])
        row = _replay(repo, sha)["row"]
        assert "LATE" not in {entry["ticker"] for entry in row["minted"]}
        refused = {entry["ticker"]: entry for entry in row["still_refused"]}
        assert refused["LATE"]["reason"].startswith("engine_refusal:")
        assert refused["LATE"]["detail"], "a refusal without its reason is not a disclosure"


# ===========================================================================
# 4. DETERMINISM + IDEMPOTENCE
# ===========================================================================

class TestDeterminismAndIdempotence:

    def test_same_pinned_inputs_produce_the_same_minted_set(self, tmp_path):
        repo, sha = _pinned_repo(tmp_path, buys=[
            _buy_row("AAA"), _buy_row("BBB", spot=50.0), _buy_row("CCC", spot=25.0),
        ])
        first = _replay(repo, sha)
        second = _replay(repo, sha)

        assert [p["id"] for p in first["minted"]] == [p["id"] for p in second["minted"]]
        assert first["receipt_id"] == second["receipt_id"]
        # Entry geometry too, not just identity: a re-run that re-prices is not a replay.
        assert (
            [(p["id"], p["entry"], p["invalidation"], p["targets"]) for p in first["minted"]]
            == [(p["id"], p["entry"], p["invalidation"], p["targets"]) for p in second["minted"]]
        )

    def test_a_dry_run_writes_nothing(self, tmp_path):
        repo, sha = _pinned_repo(tmp_path, buys=[_buy_row("AAA")])
        before = sorted(p.name for p in (repo / bf.PLANS_RELDIR).glob("*.json"))
        _replay(repo, sha, execute=False)
        after = sorted(p.name for p in (repo / bf.PLANS_RELDIR).glob("*.json"))
        assert before == after
        assert not (repo / bf.DISCLOSURES_RELPATH).exists()
        assert not (repo / bf.RECEIPTS_RELDIR).exists()

    def test_the_dry_run_and_the_execute_run_agree(self, tmp_path):
        repo, sha = _pinned_repo(tmp_path, buys=[
            _buy_row("AAA"), _buy_row("BBB", spot=50.0),
        ])
        dry = _replay(repo, sha, execute=False)
        wet = _replay(repo, sha, execute=True)
        assert [p["id"] for p in dry["minted"]] == [p["id"] for p in wet["minted"]]

    def test_a_recorded_window_refuses_to_run_again(self, tmp_path):
        repo, sha = _pinned_repo(tmp_path, buys=[_buy_row("AAA")])
        _replay(repo, sha, execute=True)
        with pytest.raises(bf.BackfillRefused, match="already records window"):
            _replay(repo, sha, execute=True)

    def test_the_refusal_also_blocks_a_second_dry_run(self, tmp_path):
        """The lock is the ARTIFACT, not the write: a dry run that reports a mintable
        set over an already-executed window is a wrong answer, not a harmless one."""
        repo, sha = _pinned_repo(tmp_path, buys=[_buy_row("AAA")])
        _replay(repo, sha, execute=True)
        with pytest.raises(bf.BackfillRefused):
            _replay(repo, sha, execute=False)

    def test_a_missing_board_commit_refuses_rather_than_guessing(self, tmp_path):
        repo, sha = _pinned_repo(tmp_path, buys=[_buy_row("AAA")])
        with pytest.raises(bf.BackfillRefused, match="does not resolve to a commit"):
            bf.run_backfill(
                repo, board_commit="deadbeef" * 5, plans_baseline=sha,
                executed_at="2026-08-11T00:00:00+00:00", execute=False)


# ===========================================================================
# 5. RECEIPT SHAPE — pinned against the real downstream validator
# ===========================================================================

class TestOriginationReceipt:

    def test_the_receipt_passes_the_chronology_audit_validator(self, tmp_path):
        """``audit_prophet_plan_chronology`` validates EVERY receipt in a plan's
        creation commit, so a malformed backfill receipt breaks chronology audits
        for every plan created from that commit forward."""
        repo, sha = _pinned_repo(tmp_path, buys=[
            _buy_row("AAA"), _buy_row("BBB", spot=50.0),
        ])
        result = _replay(repo, sha, execute=True)
        path = f"{bf.RECEIPTS_RELDIR}/{result['receipt_id']}.json"
        source, by_id = _validate_receipt_shape(result["receipt"], receipt_path=path)

        assert source["path"] == bf.BOARD_RELPATH
        assert source["price_through"] == PRICE_THROUGH
        assert sorted(by_id) == sorted(p["id"] for p in result["minted"])

    def test_the_receipt_plan_hash_matches_the_bytes_on_disk(self, tmp_path):
        """The hash and the file must come from ONE serialization — the audit
        compares the receipt's plan_sha256 against the committed blob."""
        import hashlib

        repo, sha = _pinned_repo(tmp_path, buys=[_buy_row("AAA")])
        result = _replay(repo, sha, execute=True)
        for origin in result["receipt"]["originations"]:
            blob = (repo / origin["plan_path"]).read_bytes()
            assert hashlib.sha256(blob).hexdigest() == origin["plan_sha256"]

    def test_the_receipt_freezes_the_board_row_that_originated_each_plan(self, tmp_path):
        repo, sha = _pinned_repo(tmp_path, buys=[
            _buy_row("AAA"), _buy_row("BBB", spot=50.0),
        ])
        result = _replay(repo, sha, execute=True)
        for origin in result["receipt"]["originations"]:
            assert origin["board_row"]["ticker"] == origin["asset"]
            # The chronology audit matches the plan's entry against this row's spot.
            assert origin["board_row"]["entry_signal"]["spot"] is not None


# ===========================================================================
# 6. THE LANE'S WRITE FENCE (§3.4)
# ===========================================================================

class TestWriteFence:
    """The backfill NEVER advances the forward ledger or renders the surfaces."""

    def test_the_forward_ledger_and_rendered_surfaces_are_untouched(self, tmp_path):
        live_id = "ZZZ-BULL-20260601"
        repo, sha = _pinned_repo(
            tmp_path, buys=[_buy_row("AAA")],
            plans={live_id: _seed_plan(live_id, "ZZZ", recorded_at="2026-06-01")},
            closed_ids=(live_id,),
        )
        ledger_before = (repo / bf.LEDGER_RELPATH).read_bytes()
        _replay(repo, sha, execute=True)

        assert (repo / bf.LEDGER_RELPATH).read_bytes() == ledger_before, (
            "the backfill wrote data/prophet/ledger.jsonl — the nightly is the SOLE "
            "advancer of forward ledgers (house law)"
        )
        assert not (repo / "site" / "prophet" / "index.json").exists()
        assert not (repo / "site" / "prophet" / "states").exists()
        assert not (repo / "site" / "factordata" / "alpha.json").exists()

    def test_only_the_minted_plan_files_appear(self, tmp_path):
        repo, sha = _pinned_repo(tmp_path, buys=[_buy_row("AAA"), _buy_row("BBB")])
        result = _replay(repo, sha, execute=True)
        written = sorted(p.stem for p in (repo / bf.PLANS_RELDIR).glob("*.json"))
        assert written == sorted(p["id"] for p in result["minted"])


# ===========================================================================
# 7. REAL-TREE CENSUS — read-only; the halves that run for real in CI
# ===========================================================================

def _real_plans() -> dict[str, dict]:
    plans: dict[str, dict] = {}
    for path in REAL_PLANS_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a malformed plan is not this test's subject
            continue
        if isinstance(data, dict) and data.get("schema") == "prophet.trade_plan/v1":
            plans[str(data.get("id"))] = data
    return plans


@pytest.mark.skipif(
    not REAL_PLANS_DIR.exists(),
    reason="sparse checkout: site/prophet/plans is not materialised here",
)
class TestTheShippedTreeIsSegregated:
    """The same both-directions assertion, against the tree that actually ships.

    Meaningful BEFORE the replay executes too: with no disclosure file and no
    stamped plans, both sets are empty and the test asserts that no backfill is
    hiding unlisted.  The guard-the-guard below keeps that from being vacuous.
    """

    def test_the_plan_census_actually_read_something(self):
        assert len(_real_plans()) >= 50, (
            f"only {len(_real_plans())} plan(s) read from {REAL_PLANS_DIR} — the "
            "census below would be vacuous; read the tree before trusting it"
        )

    def test_no_shipped_plan_is_backfilled_without_being_disclosed(self):
        stamped = _stamped(_real_plans())
        document = (
            json.loads(REAL_DISCLOSURES.read_text(encoding="utf-8"))
            if REAL_DISCLOSURES.exists() else {}
        )
        disclosed = _disclosed_ids(document)
        assert stamped == disclosed, (
            f"stamped-not-disclosed={sorted(stamped - disclosed)}, "
            f"disclosed-not-stamped={sorted(disclosed - stamped)}. "
            f"Every plan whose origination_mode starts 'outage_backfill' must be "
            f"enumerated in {bf.DISCLOSURES_RELPATH}, and vice versa. If a NEW "
            f"backfill is deliberate it needs its own operator authority, its own "
            f"disclosure row and an amendment to research/PROPHET_LEDGER_SCHEMA.md "
            f"— do not just delete the test."
        )

    def test_no_shipped_backfill_escapes_the_one_authorised_window(self):
        """One event. A second date appearing here is scope creep, not a backfill."""
        for plan_id, plan in _real_plans().items():
            mode = str(plan.get("origination_mode") or "")
            if not mode.startswith("outage_backfill"):
                continue
            assert mode == bf.ORIGINATION_MODE, (
                f"{plan_id} carries origination_mode={mode!r}; the only authorised "
                f"backfill is {bf.ORIGINATION_MODE!r} (operator 2026-08-11)"
            )
            assert str(plan.get("recorded_at"))[:10] == bf.BACKFILL_ASOF, (
                f"{plan_id} is stamped as the 2026-08-09 replay but claims "
                f"recorded_at={plan.get('recorded_at')!r}"
            )


@pytest.mark.skipif(
    not REAL_DISCLOSURES.exists(),
    reason="the backfill has not been executed in this tree yet",
)
class TestTheDisclosureArtifactIsWellFormed:

    def test_the_document_declares_its_authority_and_inputs(self):
        document = json.loads(REAL_DISCLOSURES.read_text(encoding="utf-8"))
        rows = document.get("backfills") or []
        assert rows, "backfill_disclosures.json lists no backfills — did it get truncated?"
        for row in rows:
            assert row["authority"], "a backfill without a named authority is not disclosed"
            assert row["window"]["from"] and row["window"]["to"]
            inputs = row["inputs"]
            assert len(inputs["board_commit"]) == 40, "input SHAs must be pinned in full"
            assert len(inputs["plans_baseline_commit"]) == 40
            assert inputs["board_path"] == bf.BOARD_RELPATH
            assert row["engine_selection_era"]

    def test_the_only_disclosed_window_is_the_authorised_one(self):
        document = json.loads(REAL_DISCLOSURES.read_text(encoding="utf-8"))
        ids = [row["id"] for row in document.get("backfills") or []]
        assert ids == [bf.WINDOW_ID], (
            f"disclosed windows {ids} — the force-majeure exception covers exactly "
            f"one event ({bf.WINDOW_ID}). A second window needs its own operator "
            f"order and its own amendment to research/PROPHET_LEDGER_SCHEMA.md."
        )

    def test_the_standing_no_backfill_law_is_still_declared(self):
        """The exception must point back at the law it is an exception TO."""
        schema_doc = (_REPO / "research" / "PROPHET_LEDGER_SCHEMA.md").read_text(
            encoding="utf-8")
        assert bf.WINDOW_ID in schema_doc or "2026-08-09" in schema_doc, (
            "research/PROPHET_LEDGER_SCHEMA.md does not scope the force-majeure "
            "exception; an undocumented exception reads as a repeal"
        )
