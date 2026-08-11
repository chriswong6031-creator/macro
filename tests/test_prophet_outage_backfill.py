"""tests/test_prophet_outage_backfill.py — the force-majeure 2026-08-09 replay.

DESIGN OF RECORD: research/PROPHET_OUTAGE_BACKFILL_2026_08.md (rev-1, 2026-08-11).
Operator order: replay the ONE receipted origination event the 2026-08-09 bake
refused on a mixed-vintage flag that #5241 later proved wrong. The standing
no-backfill law (research/PROPHET_LEDGER_SCHEMA.md) is not repealed — it is exempted
for exactly this event, and these tests are what keeps the exemption from widening.

WHAT EACH GROUP PINS

  INPUT IDENTITY (§0.2) — the blocker review found. The replay input must be the
  BAKE-TIME board, not a later re-render of the same ``as_of``: the 2026-08-10
  re-render swapped the ranker v1→v2, refreshed its options snapshot, and admitted
  three tickers through a wall-clock earnings-blackout hole. Four hard refusals are
  pinned here (sha256, as_of, ranker, ancestry), and the sha256 one is checked
  against the REAL contaminated board on main, not a fixture.

  THE HEAL IS RECOMPUTED, NOT ASSERTED (§0.2). Flipping ``mixed_vintage`` is only
  honest if the flag was wrong, so the tests drive the real ``_panel_price_reach``
  over a panel that reproduces the board's own receipt (six Sunday-dated members
  against a Friday majority) and pin both directions: a panel that clamps clean
  verifies, and a genuinely torn panel REFUSES.

  SEGREGATION THROUGH EVERY CONSUMER (§0.6) — the set of plans stamped
  ``origination_mode`` and the set enumerated in the disclosure must be the SAME set,
  both directions; and the stamp must survive into the index row, the FORWARD-LEDGER
  row at close, and the published record's split. Marketing surfaces must
  HARD-EXCLUDE, and the stage-shadow tilt cohort — the one block read back into live
  geometry — must exclude too.

  MUTATION CHECKS ARE TESTS, NOT NOTES (M9). The two segregation-critical mutations
  are executed in-process via monkeypatch: the suite proves the guard goes red when
  the guarded behaviour is removed, rather than asking a reader to trust a pasted
  terminal transcript.

NOTHING HERE WRITES THE REPO. Every executing test builds a throwaway git repo under
``tmp_path``. The real-tree census tests are read-only and skip when the checkout is
sparse (agent worktrees commonly omit ``site/`` and ``data/``); those are the ones
that run for real in CI, where the checkout is complete.

Run: TZ=UTC python3 -m pytest tests/test_prophet_outage_backfill.py -q
"""
from __future__ import annotations

import hashlib
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
import scripts.build_stock_library as bsl  # noqa: E402
from scripts.audit_prophet_plan_chronology import (  # noqa: E402
    _validate_receipt_shape,
)

REAL_PLANS_DIR = _REPO / "site" / "prophet" / "plans"
REAL_DISCLOSURES = _REPO / bf.DISCLOSURES_RELPATH
REAL_SCHEMA_DOC = _REPO / "research" / "PROPHET_LEDGER_SCHEMA.md"

#: last_session_on_or_before("2026-08-09") — the Friday close the replay prices off.
PRICE_THROUGH = "2026-08-07"
#: The board's own receipt: 1,758 members, six of them carrying Sunday-dated bars.
PANEL_MEMBERS_TOTAL = 1758
PANEL_SUNDAY_MEMBERS = 6


@pytest.fixture(autouse=True)
def _arena_writes_to_tmp(tmp_path, monkeypatch):
    """Send the Prophet Arena's ledgers to tmp for every test in this file.

    ``build_prophet.main()`` calls ``run_arena(..., repo_root=_REPO)``, which writes
    seven TRACKED files under ``data/prophet_arena/``. Same reasoning (and same
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
# synthetic panel — reproduces the board's own recorded reach evidence
# ---------------------------------------------------------------------------

def _series(last_day: str) -> pd.Series:
    idx = pd.bdate_range(end=pd.Timestamp(last_day), periods=5)
    if pd.Timestamp(last_day) not in idx:
        idx = idx.append(pd.DatetimeIndex([pd.Timestamp(last_day)]))
    return pd.Series([100.0] * len(idx), index=idx)


def _panel(*, sunday_members: int = PANEL_SUNDAY_MEMBERS,
           total: int = PANEL_MEMBERS_TOTAL,
           fresher_members: int = 0,
           majority_day: str = PRICE_THROUGH) -> list[tuple]:
    """A universe() stand-in shaped like the 2026-08-09 panel.

    ``sunday_members`` carry 2026-08-09 (SUNDAY) bars — the six the pre-#5241 reach
    function counted as a fresher vintage, and which the session clamp folds back
    into Friday.

    ``fresher_members`` carry a genuinely FRESHER SESSION than the majority, which is
    what a real tear looks like: ``mixed_vintage`` is ``majority != max``, so a
    minority ahead of the mode is the condition, and the clamp does not and must not
    erase it.
    """
    rows: list[tuple] = []
    for i in range(sunday_members):
        rows.append((f"SUN{i}", _series("2026-08-09"), None, "", ""))
    for i in range(fresher_members):
        rows.append((f"FRESH{i}", _series(PRICE_THROUGH), None, "", ""))
    for i in range(total - sunday_members - fresher_members):
        rows.append((f"EQ{i}", _series(majority_day), None, "", ""))
    return rows


@pytest.fixture
def clean_panel(monkeypatch):
    """The real panel's shape: six Sunday bars over a Friday majority."""
    monkeypatch.setattr(bsl, "universe", lambda: _panel())


@pytest.fixture
def agreeing_geometry(monkeypatch):
    """Bake vintage and live tree agree, so the PIT gate passes on its own terms."""
    monkeypatch.setattr(
        bf, "geometry_vintages",
        lambda repo, commit: {
            "fields": {"regime": {"pinned": True, "agrees": True}},
            "divergent": [],
        })


# ---------------------------------------------------------------------------
# synthetic pinned repo
# ---------------------------------------------------------------------------

def _buy_row(ticker: str, *, spot: float = 100.0, priority: float = 90.0,
             anchor: str = "2026-07-31", signal: dict | None = None) -> dict:
    """One admitted ``us_standouts.json["buy"]`` row that originates cleanly.

    Shaped after tests/test_prophet_w1_intake_repair.py::_buy — the known-good
    admitted row — so a failure here is about the backfill, never about whether the
    fixture clears intake.
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
    live dry run reproduces verbatim: a formation anchor that POSTDATES the tier
    event the plan claims to descend from. The tier contract has to be present or
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


def _board(buys: list[dict], *, price_through: str = PRICE_THROUGH,
           mixed_vintage: bool = True, rank_by: str = "us_prophet_v1") -> dict:
    """The bake-time board: mixed_vintage TRUE is the flag the replay heals."""
    return {
        "as_of": price_through,
        "rank_by": rank_by,
        "board_definition": rank_by,
        "ranking": {"definition": rank_by},
        "staleness": {
            "price_through": price_through,
            "delayed": False,
            "unknown": False,
            "basis": "panel_majority",
            "inputs": {
                "panel": {
                    "through": "2026-08-09",
                    "majority_through": price_through,
                    "members_at_through": PANEL_SUNDAY_MEMBERS,
                    "members_total": PANEL_MEMBERS_TOTAL,
                    "mixed_vintage": mixed_vintage,
                },
            },
        },
        "gate_go": False,
        "buy": buys,
    }


def _seed_plan(plan_id: str, ticker: str, *, recorded_at: str,
               origination_mode: str | None = None,
               direction: str = "BULL") -> dict:
    plan: dict = {
        "schema": "prophet.trade_plan/v1",
        "id": plan_id,
        "asof": recorded_at,
        "recorded_at": recorded_at,
        "asset": ticker,
        "direction": direction,
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


def _pinned_repo(tmp_path: Path, monkeypatch, *, buys: list[dict],
                 plans: dict[str, dict] | None = None,
                 closed_ids: tuple[str, ...] = (),
                 board: dict | None = None,
                 name: str = "pinned_repo") -> tuple[Path, str]:
    """A throwaway git repo carrying a board, a plan baseline and a ledger.

    The script reads every input through ``git show``/``ls-tree`` at a pinned SHA, so
    a real (tiny) repo exercises the actual extraction path instead of a stub. An
    ``origin/main`` ref is planted so the ANCESTRY gate runs for real rather than
    being monkeypatched away, and ``BAKE_BOARD_SHA256`` is re-pinned to this
    fixture's bytes so the identity fence also runs for real — the production
    constant is exercised separately, against the real contaminated board.
    """
    repo = tmp_path / name
    (repo / "site" / "factordata").mkdir(parents=True)
    (repo / "site" / "prophet" / "plans").mkdir(parents=True)
    (repo / "data" / "prophet").mkdir(parents=True)

    payload = json.dumps(board if board is not None else _board(buys))
    (repo / bf.BOARD_RELPATH).write_text(payload, encoding="utf-8")
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
    # The ancestry gate is a real check, so give it a real origin/main to check against.
    _git(repo, "update-ref", "refs/remotes/origin/main", sha)

    blob = (repo / bf.BOARD_RELPATH).read_bytes()
    monkeypatch.setattr(bf, "BAKE_BOARD_SHA256", hashlib.sha256(blob).hexdigest())
    return repo, sha


def _replay(repo: Path, sha: str, *, execute: bool = False,
            executed_at: str = "2026-08-11T00:00:00+00:00", **kw) -> dict:
    kw.setdefault("allow_empty_baseline_proof", True)
    return bf.run_backfill(
        repo, board_commit=sha, plans_baseline=sha,
        executed_at=executed_at, execute=execute, **kw,
    )


# ===========================================================================
# 1. INPUT IDENTITY (§0.2) — the contaminated-board fence
# ===========================================================================

class TestTheReplayInputIsFenced:
    """Four hard refusals, each closing a contamination vector review found real."""

    def test_a_board_whose_bytes_are_not_the_pinned_bake_board_is_refused(
            self, tmp_path, monkeypatch, clean_panel, agreeing_geometry):
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        monkeypatch.setattr(bf, "BAKE_BOARD_SHA256", "0" * 64)
        with pytest.raises(bf.BackfillRefused, match="RE-RENDER"):
            _replay(repo, sha)

    def test_a_v2_ranked_board_is_refused(
            self, tmp_path, monkeypatch, clean_panel, agreeing_geometry):
        """The 2026-08-10 re-render's actual defect: same as_of, different ranker."""
        repo, sha = _pinned_repo(
            tmp_path, monkeypatch, buys=[_buy_row("AAA")],
            board=_board([_buy_row("AAA")], rank_by="us_prophet_v2"))
        with pytest.raises(bf.BackfillRefused, match="ranker"):
            _replay(repo, sha)

    def test_a_board_from_another_day_is_refused(
            self, tmp_path, monkeypatch, clean_panel, agreeing_geometry):
        repo, sha = _pinned_repo(
            tmp_path, monkeypatch, buys=[_buy_row("AAA")],
            board=_board([_buy_row("AAA")], price_through="2026-08-10"))
        with pytest.raises(bf.BackfillRefused, match="as_of"):
            _replay(repo, sha)

    def test_a_commit_off_main_is_refused(
            self, tmp_path, monkeypatch, clean_panel, agreeing_geometry):
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
        with pytest.raises(bf.BackfillRefused, match="NOT an ancestor"):
            _replay(repo, sha)

    def test_a_shallow_clone_refuses_INDETERMINATE_rather_than_guessing(
            self, tmp_path, monkeypatch, clean_panel, agreeing_geometry):
        """Measured 2026-08-11: the real bake commit read as NOT-an-ancestor at
        depth 79 and as a clean ancestor at depth 479. A gate that took the shallow
        false negative at face value would refuse every honest CI run, so shallowness
        gets its own message naming the fix."""
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        _git(repo, "update-ref", "-d", "refs/remotes/origin/main")
        monkeypatch.setattr(bf, "is_shallow", lambda repo: True)
        with pytest.raises(bf.BackfillRefused, match="SHALLOW"):
            _replay(repo, sha)

    def test_the_production_constant_rejects_the_board_now_on_main(self):
        """The fence, against the REAL contaminated artifact rather than a fixture.

        The board sitting on main is a post-heal re-render of the same as_of. If the
        pinned constant ever matched it, the re-pin this whole PR exists for would
        have silently come undone.
        """
        board_path = _REPO / bf.BOARD_RELPATH
        if not board_path.exists():
            pytest.skip("sparse checkout: site/factordata is not materialised here")
        digest = hashlib.sha256(board_path.read_bytes()).hexdigest()
        assert digest != bf.BAKE_BOARD_SHA256, (
            "the pinned bake-time board sha256 now matches the board on main — "
            "either the constant was edited to whatever was convenient, or main "
            "was rewritten. The replay input must be the 2026-08-09 BAKE-TIME "
            "board, never a later re-render."
        )


# ===========================================================================
# 2. THE HEAL IS RECOMPUTED (§0.2)
# ===========================================================================

class TestTheHealIsVerifiedNotAsserted:

    def test_the_session_clamp_turns_the_recorded_tear_into_no_tear(
            self, monkeypatch):
        """The #5241 mechanism, end to end on the board's own recorded evidence."""
        monkeypatch.setattr(bsl, "universe", lambda: _panel())
        out = bf.verify_heal_by_recomputation(_board([_buy_row("AAA")]))
        assert out["recomputed"]["mixed_vintage"] is False
        assert out["recomputed"]["through"] == PRICE_THROUGH
        assert out["recomputed"]["majority_through"] == PRICE_THROUGH
        assert out["panel_coverage"] == 1.0

    def test_a_genuinely_torn_panel_still_REFUSES(self, monkeypatch):
        """The direction that matters: the heal is not a rubber stamp.

        A member at a genuinely FRESHER session than the majority is a real tear,
        which the clamp does not and must not erase.
        """
        monkeypatch.setattr(
            bsl, "universe",
            lambda: _panel(sunday_members=0, fresher_members=3,
                           majority_day="2026-08-06"))
        with pytest.raises(bf.BackfillRefused, match="still reports"):
            bf.verify_heal_by_recomputation(_board([_buy_row("AAA")]))

    def test_a_short_panel_refuses_rather_than_answering_for_a_smaller_object(
            self, monkeypatch):
        monkeypatch.setattr(bsl, "universe", lambda: _panel(total=400))
        with pytest.raises(bf.BackfillRefused, match="covers only"):
            bf.verify_heal_by_recomputation(_board([_buy_row("AAA")]))

    def test_the_short_panel_waiver_records_itself(self, monkeypatch):
        monkeypatch.setattr(bsl, "universe", lambda: _panel(total=400))
        out = bf.verify_heal_by_recomputation(
            _board([_buy_row("AAA")]), allow_short_panel=True)
        assert out["coverage_gate_waived"] is True
        assert out["panel_coverage"] < 0.9

    def test_the_heal_changes_exactly_one_field(self):
        original = _board([_buy_row("AAA")])
        healed, before = bf.heal_board(original)
        assert before is True
        assert healed["staleness"]["inputs"]["panel"]["mixed_vintage"] is False
        assert bf._only_difference_is_the_heal(original, healed)
        # and the original is untouched evidence
        assert original["staleness"]["inputs"]["panel"]["mixed_vintage"] is True

    def test_a_heal_that_touched_anything_else_would_be_caught(self):
        original = _board([_buy_row("AAA")])
        healed, _ = bf.heal_board(original)
        healed["gate_go"] = True
        assert not bf._only_difference_is_the_heal(original, healed)


# ===========================================================================
# 3. PIT GEOMETRY (B4)
# ===========================================================================

class TestGeometryVintages:

    def test_a_divergent_geometry_input_refuses_the_mint(
            self, tmp_path, monkeypatch, clean_panel):
        monkeypatch.setattr(
            bf, "geometry_vintages",
            lambda repo, commit: {
                "fields": {"regime": {"pinned": True, "agrees": False}},
                "divergent": ["regime"],
            })
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        with pytest.raises(bf.BackfillRefused, match="DIFFERENTLY"):
            _replay(repo, sha)

    def test_the_drift_waiver_records_the_divergence_per_field(
            self, tmp_path, monkeypatch, clean_panel):
        monkeypatch.setattr(
            bf, "geometry_vintages",
            lambda repo, commit: {
                "fields": {"regime": {"pinned": True, "agrees": False,
                                      "vintage_used": "live (DIVERGENT)"}},
                "divergent": ["regime"],
            })
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        row = _replay(repo, sha, allow_geometry_drift=True)["row"]
        assert row["geometry_divergent"] == ["regime"]
        assert row["geometry_vintages"]["regime"]["vintage_used"].endswith("(DIVERGENT)")

    def test_every_geometry_field_names_the_vintage_actually_used(self):
        """§0.2: an input that cannot be pinned is disclosed PER FIELD, never
        silently defaulted to whatever the host happened to have."""
        out = bf.geometry_vintages(_REPO, "HEAD")
        assert out["fields"], "no geometry fields reported at all"
        for name, field in out["fields"].items():
            assert "vintage_used" in field, f"{name} does not name its vintage"
            if not field.get("pinned"):
                assert field.get("reason"), f"{name} is unpinned without a reason"


# ===========================================================================
# 4. SEGREGATION (§0.6) — the two sets are the same set, both directions
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


@pytest.mark.usefixtures("clean_panel", "agreeing_geometry")
class TestSegregation:
    """Every backfilled plan is disclosed, and every disclosed plan exists."""

    def test_the_stamped_set_and_the_disclosed_set_are_identical(
            self, tmp_path, monkeypatch):
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[
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
        assert stamped, "no plan carries the backfill stamp — the assertion is vacuous"
        assert stamped == disclosed, (
            f"stamped-not-disclosed={sorted(stamped - disclosed)}, "
            f"disclosed-not-stamped={sorted(disclosed - stamped)}. "
            "An undisclosed backfill is exactly what this artifact prevents."
        )

    def test_MUTATION_dropping_the_stamp_turns_this_suite_red(
            self, tmp_path, monkeypatch):
        """M9 — the mutation check, executed rather than described.

        Removing the provenance stamp is the single change that would make a
        backfilled plan indistinguishable from a live one. If the segregation
        assertion above can pass without it, the assertion is decoration.
        """
        monkeypatch.setattr(
            bf, "_stamp",
            lambda plan, *, executed_at: {**plan,
                                          "backfill_executed_at": executed_at})
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        _replay(repo, sha, execute=True)

        on_disk = {
            json.loads(p.read_text(encoding="utf-8"))["id"]:
                json.loads(p.read_text(encoding="utf-8"))
            for p in (repo / bf.PLANS_RELDIR).glob("*.json")
        }
        document = json.loads(
            (repo / bf.DISCLOSURES_RELPATH).read_text(encoding="utf-8"))
        assert _stamped(on_disk) != _disclosed_ids(document), (
            "the unstamped mutant still satisfied the segregation equality — the "
            "real test would pass with the stamp removed, so it proves nothing"
        )

    def test_every_backfilled_plan_is_recorded_inside_the_disclosed_window(
            self, tmp_path, monkeypatch):
        repo, sha = _pinned_repo(tmp_path, monkeypatch,
                                 buys=[_buy_row("AAA"), _buy_row("BBB")])
        result = _replay(repo, sha, execute=True)
        document = json.loads(
            (repo / bf.DISCLOSURES_RELPATH).read_text(encoding="utf-8"))
        window = document["backfills"][-1]["window"]

        assert result["minted"], "nothing minted — window assertion would be vacuous"
        for plan in result["minted"]:
            assert window["from"] <= plan["recorded_at"] <= window["to"]
            assert plan["recorded_at"] == bf.BACKFILL_ASOF

    def test_the_stamp_names_the_event_and_the_execution_is_dated(
            self, tmp_path, monkeypatch):
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        result = _replay(repo, sha, execute=True,
                         executed_at="2026-08-11T03:14:15+00:00")
        for plan in result["minted"]:
            assert plan["origination_mode"] == "outage_backfill_2026_08_09"
            assert plan["backfill_executed_at"] == "2026-08-11T03:14:15+00:00"
            # Same engine, same rule: the SELECTION era must not be forged into
            # something new just because the write happened later.
            assert plan["selection_era"] == bf_selection_era()

    def test_a_live_plan_carries_no_backfill_stamp(self, tmp_path, monkeypatch):
        """The null IS "live", and it is printed rather than defaulted to a word."""
        repo, sha = _pinned_repo(
            tmp_path, monkeypatch, buys=[_buy_row("AAA")],
            plans={"ZZZ-BULL-20260601": _seed_plan(
                "ZZZ-BULL-20260601", "ZZZ", recorded_at="2026-06-01")},
        )
        _replay(repo, sha, execute=True)
        live = json.loads(
            (repo / bf.PLANS_RELDIR / "ZZZ-BULL-20260601.json").read_text(
                encoding="utf-8"))
        assert "origination_mode" not in live
        assert "backfill_executed_at" not in live

    def test_the_refused_dates_stay_refused_in_the_disclosure(
            self, tmp_path, monkeypatch):
        """08-03→08-06 are NOT reconstructed, and the document says why (§2)."""
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        never = _replay(repo, sha)["row"]["never_reconstructed"]
        assert never["dates"] == [
            "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"
        ]
        assert never["ruling"] == "us-board-frozen-alpha-2026-08"


def bf_selection_era() -> str:
    """m14 — read the era from the engine, never a literal in this file."""
    from engine.prophet_bridge import SELECTION_ERA
    return SELECTION_ERA


# ===========================================================================
# 5. RECONCILIATION (M8)
# ===========================================================================

class TestReconciliation:
    """The identities are derived from pass 1 of ``originate_plans``, not guessed."""

    def test_both_identities_hold_on_a_run_with_all_four_buckets_nonzero(
            self, tmp_path, monkeypatch, clean_panel, agreeing_geometry):
        """NON-DEGENERATE by construction (M8): duplicate, re-origination-blocked,
        minted, collided and refused are ALL nonzero, so an identity that only
        happens to hold when three terms are zero cannot pass here."""
        row = _four_bucket_run(tmp_path, monkeypatch)["row"]
        counts = row["counts"]
        assert counts["duplicate_id_blocked"] >= 1
        assert counts["reorigination_blocked"] >= 1
        assert counts["minted"] >= 1
        assert counts["collided"] >= 1
        assert counts["still_refused"] >= 1
        for name, identity in row["reconciliation"].items():
            assert identity["holds"], (
                f"{name} broke: {identity['lhs']} != {identity['rhs']} "
                f"({identity['statement']})"
            )

    def test_MUTATION_zeroing_collided_and_refused_breaks_the_identity(self):
        """M9/M8 — the arithmetic is load-bearing, so prove it can fail.

        The earlier form of this check summed only the buckets that happened to be
        nonzero, which is an identity that cannot be violated.
        """
        honest = {
            "admitted": 54, "duplicate_id_blocked": 24, "reorigination_blocked": 2,
            "eligible_after_skips": 28, "minted": 25, "collided": 3,
            "still_refused": 2,
        }
        assert all(i["holds"] for i in bf.check_reconciliation(honest).values())
        mutated = {**honest, "collided": 0, "still_refused": 0}
        checked = bf.check_reconciliation(mutated)
        assert not checked["disposition_identity"]["holds"], (
            "zeroing collided and still_refused left the disposition identity "
            "holding — it is not actually checking the disposition"
        )

    def test_a_broken_identity_is_reported_not_swallowed(self):
        broken = {
            "admitted": 54, "duplicate_id_blocked": 1, "reorigination_blocked": 0,
            "eligible_after_skips": 1, "minted": 1, "collided": 0,
            "still_refused": 0,
        }
        checked = bf.check_reconciliation(broken)
        assert not checked["admission_identity"]["holds"]
        assert checked["admission_identity"]["lhs"] == 54


def _four_bucket_run(tmp_path, monkeypatch) -> dict:
    """A replay where every disposition bucket is genuinely exercised.

    * DUP      — a baseline plan sharing an admitted row's id.
    * REORIG   — an open baseline plan on a DIFFERENT admitted ticker (blocks its key).
    * COLLIDED — that same open plan is recorded post-cutoff, so live wins.
    * REFUSED  — the chronology row.
    * MINTED   — a clean row.
    """
    dup_id = "DUPE-BULL-20260731"
    open_id = "OPEN-BULL-20260801"
    return _replay(*_pinned_repo(
        tmp_path, monkeypatch,
        buys=[
            _buy_row("MINT"),
            _buy_row("DUPE", spot=60.0),
            _buy_row("OPEN", spot=70.0),
            _late_anchor_row("LATE"),
        ],
        plans={
            dup_id: _seed_plan(dup_id, "DUPE", recorded_at="2026-07-31"),
            open_id: _seed_plan(open_id, "OPEN", recorded_at="2026-08-10"),
        },
    ))


# ===========================================================================
# 6. NIGHTLY PASSTHROUGH + LEDGER + RECORD (§0.6c, §0.7)
# ===========================================================================

def _run_nightly(tmp_path: Path, buys: list[dict], *, asof: str,
                 seed_plans: dict[str, dict],
                 ledger: dict[str, str] | None = None,
                 price_history: "pd.DataFrame | None" = "keep",  # type: ignore[assignment]
                 ) -> tuple[dict, dict[str, Path]]:
    """Run ``build_prophet.main()`` against tmp_path.

    Returns ``(index, paths)``. The paths come back explicitly because the module
    constants are RESTORED in the ``finally`` below — a caller that read
    ``bp.PLANS_DIR`` afterwards would be reading the real repo, which is how the
    first draft of this harness "passed" against ``site/prophet/plans``.

    Same redirection list as tests/test_prophet_w1_intake_repair.py::_run_main,
    including neutering ``write_showcase``, whose out_path default binds at def time
    and would otherwise write the REAL showcase.json.
    """
    standouts = tmp_path / "us_standouts.json"
    # The board a nightly reads is the board that nightly built: price_through must
    # be the run's own session, and it is not mixed-vintage (that is the whole point
    # of #5241) or origination would refuse every candidate.
    standouts.write_text(
        json.dumps(_board(buys, price_through=asof, mixed_vintage=False)),
        encoding="utf-8")

    if price_history == "keep":
        # Runs THROUGH the run date, not up to the entry basis: a plan priced off
        # 2026-08-07 needs sessions after 2026-08-07 for the management engine to
        # scan, or nothing can ever close and the ledger assertions are vacuous.
        n = 45
        price_history = pd.DataFrame(
            {"close": [100.0 + i for i in range(n)],
             "high": [100.0 + i for i in range(n)],
             "low": [100.0 + i for i in range(n)]},
            index=pd.date_range("2026-06-15", periods=n, freq="B"),
        )

    saved = {name: getattr(bp, name) for name in
             ("STANDOUTS_PATH", "SITE_PROPHET", "PLANS_DIR", "STATES_DIR",
              "INDEX_PATH", "LEDGER_PATH", "LEDGER_DIR", "write_showcase")}
    paths = {
        "plans": tmp_path / "site" / "prophet" / "plans",
        "states": tmp_path / "site" / "prophet" / "states",
        "index": tmp_path / "site" / "prophet" / "index.json",
        "ledger": tmp_path / "data" / "prophet" / "ledger.jsonl",
    }
    try:
        bp.STANDOUTS_PATH = standouts
        bp.SITE_PROPHET = tmp_path / "site" / "prophet"
        bp.PLANS_DIR = paths["plans"]
        bp.STATES_DIR = paths["states"]
        bp.INDEX_PATH = paths["index"]
        bp.LEDGER_DIR = tmp_path / "data" / "prophet"
        bp.LEDGER_PATH = paths["ledger"]
        bp.write_showcase = lambda: None

        paths["plans"].mkdir(parents=True, exist_ok=True)
        for plan_id, plan in seed_plans.items():
            (paths["plans"] / f"{plan_id}.json").write_text(
                json.dumps(plan, indent=2), encoding="utf-8")
        if ledger:
            bp.LEDGER_DIR.mkdir(parents=True, exist_ok=True)
            paths["ledger"].write_text(
                "\n".join(
                    json.dumps({"schema": "prophet.ledger/v1", "id": pid,
                                "outcome": outcome})
                    for pid, outcome in ledger.items()) + "\n",
                encoding="utf-8")

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
        """§0.6c: consumers read index.json, so a stamp that stops at the plan file
        is a stamp no track-record aggregate can split a rate by."""
        index, _paths = _run_nightly(
            tmp_path, [_buy_row("AAA")], asof="2026-08-11", seed_plans=self._seed())
        by_id = {row["id"]: row for row in index["plans"]}

        row = by_id[self.BACKFILLED]
        assert row["origination_mode"] == bf.ORIGINATION_MODE
        assert row["backfill_executed_at"] == "2026-08-11T00:00:00+00:00"
        # And the split actually works: the live rows say "live" by saying nothing.
        live_rows = [r for r in index["plans"] if r["id"] != self.BACKFILLED]
        assert live_rows, "no live row to contrast against — the split is unproven"
        assert all("origination_mode" not in r for r in live_rows)

    def test_the_backfilled_plan_renders_a_management_state(self, tmp_path):
        index, paths = _run_nightly(
            tmp_path, [_buy_row("AAA")], asof="2026-08-11", seed_plans=self._seed())
        row = {r["id"]: r for r in index["plans"]}[self.BACKFILLED]
        assert row["management_status"] == "available"
        assert row["state"]["phase"]
        assert (paths["states"] / f"{self.BACKFILLED}.json").exists()

    def test_a_degraded_backfilled_row_is_still_splittable(self, tmp_path):
        """A missing price history must not silently strip the provenance stamp —
        the degraded row still SHIPS, so it still has to be excludable."""
        index, _paths = _run_nightly(
            tmp_path, [_buy_row("AAA")], asof="2026-08-11", seed_plans=self._seed(),
            price_history=None)
        row = {r["id"]: r for r in index["plans"]}[self.BACKFILLED]
        assert row["management_status"] == "unavailable"
        assert row["origination_mode"] == bf.ORIGINATION_MODE


class TestTheClosedRowStaysSplittable:
    """§0.6c — the ledger and the published record, not just the index."""

    BACKFILLED = "BFIL-BULL-20260731"

    #: The clocks a REAL backfilled plan carries: priced off the Friday the bake
    #: read, recorded on the Sunday being replayed.  An earlier draft of this fixture
    #: dated the entry basis to June, which the forward-ledger QUARANTINE correctly
    #: rejected as graded-on-a-clock-that-predated-the-plan — the row then never
    #: reached `scored`, and the record split had nothing to split. Keeping the
    #: fixture chronologically honest is what makes the assertion mean anything.
    PRICE_BASIS = PRICE_THROUGH

    def _closing_seed(self, *, plan_id: str | None = None, ticker: str = "BFIL",
                      mode: str | None = None) -> dict[str, dict]:
        """A plan whose invalidation the tape has already broken, so the nightly
        CLOSES it and writes a forward-ledger row on this very run."""
        pid = plan_id or self.BACKFILLED
        plan = _seed_plan(
            pid, ticker,
            recorded_at=bf.BACKFILL_ASOF if mode else "2026-08-07",
            origination_mode=mode)
        plan.update({
            "entry": 100.0, "trigger": 95.0, "invalidation": 200.0,
            "targets": [300.0, 400.0], "price_basis_date": self.PRICE_BASIS,
            "entry_date": self.PRICE_BASIS, "signal_date": self.PRICE_BASIS,
            "_signal_date": self.PRICE_BASIS, "min_hold_days": 0,
        })
        return {pid: plan}

    def _run(self, tmp_path):
        return _run_nightly(
            tmp_path, [_buy_row("AAA")], asof="2026-08-11",
            seed_plans=self._closing_seed(mode=bf.ORIGINATION_MODE))

    def test_the_forward_ledger_row_carries_the_origination_mode(self, tmp_path):
        _index, paths = self._run(tmp_path)
        rows = [
            json.loads(line) for line in
            paths["ledger"].read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        closed = [r for r in rows if r.get("id") == self.BACKFILLED]
        assert closed, (
            "the backfilled plan never closed, so the ledger-carry assertion below "
            "would be vacuous — check the fixture's invalidation/tape"
        )
        assert closed[0]["origination_mode"] == bf.ORIGINATION_MODE, (
            "the forward-ledger row does not carry origination_mode. The ledger is "
            "the substrate every rate is computed over, and a consumer reading it "
            "directly never sees the index row's stamp."
        )
        assert closed[0]["backfill_executed_at"]

    def test_a_live_close_writes_no_origination_key_at_all(self, tmp_path):
        """Absent means live — an unconditional null would be a schema change on an
        append-only store for a fact that is almost never true."""
        live_id = "LIVE-BULL-20260807"
        _index, paths = _run_nightly(
            tmp_path, [_buy_row("AAA")], asof="2026-08-11",
            seed_plans=self._closing_seed(plan_id=live_id, ticker="LIVE"))
        rows = [
            json.loads(line) for line in
            paths["ledger"].read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        closed = [r for r in rows if r.get("id") == live_id]
        assert closed, "the live plan never closed — assertion would be vacuous"
        assert "origination_mode" not in closed[0]

    def test_the_published_record_SPLITS_the_reconstructed_row(self, tmp_path):
        """The ratified form (#5301): an additive split, not a fourth exclusion.

        These plans were graded by the nightly on their own real bars, so the
        headline rate is untouched — but a reader must be able to see the cohort.
        """
        index, _paths = self._run(tmp_path)
        record = index["record"]
        assert record["n_reconstructed"] >= 1, (
            "the published record does not disclose the reconstructed cohort at all"
        )
        assert self.BACKFILLED in record["reconstructed_ids"]
        assert record.get("reconstructed_note")

    def test_MUTATION_a_record_blind_to_the_cohort_turns_this_red(self):
        """M9 — the split is load-bearing, so prove its absence is detectable."""
        rows = [{
            "id": "BFIL-BULL-20260731", "outcome": "T1_HIT",
            "stock_result_pct": 4.0,
        }]
        honest = bp.record_summary(rows, set(), {"BFIL-BULL-20260731"})
        assert honest["n_reconstructed"] == 1
        blind = bp.record_summary(rows, set(), set())
        assert "n_reconstructed" not in blind, (
            "record_summary reports a reconstructed cohort even when told there is "
            "none — the split is not actually driven by reconstructed_ids"
        )
        # ...and the headline is genuinely unchanged between the two (a SPLIT, not
        # an exclusion): if these ever differ, the ratified form has drifted.
        assert honest["win_rate"] == blind["win_rate"]
        assert honest["n_scored"] == blind["n_scored"]


# ===========================================================================
# 7. MARKETING + GEOMETRY CONSUMERS HARD-EXCLUDE (§0.6d, §0.6e)
# ===========================================================================

class TestReconstructedPlansNeverReachALiveSurface:

    def _pair(self) -> list[dict]:
        """One live plan and one reconstructed plan, both RESOLVED.

        ``receipt_source._is_resolved`` wants a real resolution — an invalidated
        phase, or a profit-plan level marked DONE — so both carry one. Without that
        neither produces a receipt and the exclusion test below would pass because
        nothing qualified, which is precisely what its mutation twin checks for.
        """
        live = _seed_plan("LIVE-BULL-20260701", "LIVE", recorded_at="2026-07-01")
        rebuilt = _seed_plan("BFIL-BULL-20260731", "BFIL",
                             recorded_at=bf.BACKFILL_ASOF,
                             origination_mode=bf.ORIGINATION_MODE)
        for plan in (live, rebuilt):
            plan.update({
                "outcome": "T1_HIT", "closed": True, "stock_result_pct": 5.0,
                "phase": "invalidated",
                # `effective_public_plan_date` refuses to guess across date families,
                # so a plan without a declared basis has NO public date and produces
                # no receipt at all — the fixture must declare one or the exclusion
                # test would be measuring the wrong absence.
                "signal_date_basis": "tier_event_date",
                "profit_plan": [{"level": 120.0, "label": "T1", "action": "trim",
                                 "status": "DONE"}],
            })
        return [live, rebuilt]

    def test_graded_receipts_drops_the_reconstructed_plan(self):
        """A reconstructed pick may never be presented as a live historical call."""
        from engine.marketing import receipt_source

        tickers = {
            str(r.get("ticker") or "").upper()
            for r in receipt_source.graded_receipts(
                self._pair(), today="2026-08-11", max_age_days=3650)
        }
        assert "BFIL" not in tickers, (
            "a reconstructed plan reached the marketing receipt surface — it would "
            "be published as a call the desk made on a day it did not make it"
        )

    def test_MUTATION_without_the_filter_the_reconstructed_plan_WOULD_appear(
            self, monkeypatch):
        """M9 — proves the assertion above is testing the filter, not the fixture.

        With the predicate forced to "nothing is reconstructed", the same input must
        produce the leak; if it does not, the test above passes for the wrong reason
        (e.g. the fixture never qualified as a receipt at all).
        """
        import engine.prophet_bridge as pb
        from engine.marketing import receipt_source

        monkeypatch.setattr(pb, "is_reconstructed", lambda row: False)
        tickers = {
            str(r.get("ticker") or "").upper()
            for r in receipt_source.graded_receipts(
                self._pair(), today="2026-08-11", max_age_days=3650)
        }
        assert "BFIL" in tickers, (
            "even with the exclusion disabled the reconstructed plan produced no "
            "receipt — the exclusion test above is vacuous"
        )

    def test_content_plan_filters_its_plan_population_at_the_entry_point(self):
        """Five downstream sites read `plans`; the parameter is filtered once so a
        sixth cannot be added without inheriting the exclusion."""
        import inspect

        from engine.marketing import content_studio

        source = inspect.getsource(content_studio.content_plan)
        head = source[:source.index("from engine.marketing.chart_render")]
        assert "is_reconstructed" in head, (
            "content_plan no longer filters `plans` before its body runs"
        )

    def test_the_stage_tilt_cohort_excludes_reconstructed_rows(self):
        """§0.6e — the one block whose output is read BACK into live geometry."""
        from engine import prophet_stage_shadow as pss

        def _row(rid, ret, *, mode=None):
            row = {
                "id": rid, "stage_at_entry": "STAGE2",
                "last_ec": {"sent": 1.0}, "fwd": {"fwd_ret_126": ret},
            }
            if mode:
                row["origination_mode"] = mode
            return row

        live_only = [_row("a", 0.10), _row("b", 0.12)]
        with_rebuilt = live_only + [
            _row("c", -0.90, mode=bf.ORIGINATION_MODE),
            _row("d", -0.90, mode=bf.ORIGINATION_MODE),
        ]
        assert pss._median_tilt(live_only) == pss._median_tilt(with_rebuilt), (
            "reconstructed rows moved the stage-tilt cohort statistic — that number "
            "feeds plan_horizon_days on LIVE plans, so a rebuilt selection would be "
            "steering live geometry"
        )

    def test_the_brain_projection_can_see_the_stamp(self):
        """§0.6f — a field the projection drops is a caveat the chat cannot make."""
        import inspect

        from engine.neuralweb import brain_gateway

        source = inspect.getsource(brain_gateway._tool_get_house_view)
        assert '"origination_mode": p.get("origination_mode")' in source
        assert '"origination_note": p.get("origination_note")' in source


# ===========================================================================
# 8. COLLISION RULE (§0.4) — live wins
# ===========================================================================

@pytest.mark.usefixtures("clean_panel", "agreeing_geometry")
class TestCollisionRuleLiveWins:

    def test_a_live_plan_closed_in_the_ledger_still_wins(self, tmp_path, monkeypatch):
        """The case the engine's open-plan block CANNOT see.

        ``active_keys`` only holds OPEN plans, so a live 08-10 plan the ledger has
        already closed frees its ticker+direction key and the replay would mint a
        SECOND episode for that name. The post-process drop is what stops that.
        """
        live_id = "AAA-BULL-20260806"
        repo, sha = _pinned_repo(
            tmp_path, monkeypatch,
            buys=[_buy_row("AAA"), _buy_row("BBB", spot=50.0)],
            plans={live_id: _seed_plan(live_id, "AAA", recorded_at="2026-08-10")},
            closed_ids=(live_id,),
        )
        row = _replay(repo, sha)["row"]

        minted = {entry["ticker"] for entry in row["minted"]}
        collided = {entry["ticker"]: entry for entry in row["collided"]}
        assert "AAA" not in minted, "live plan lost the collision — AAA double-minted"
        assert "BBB" in minted, "the uncontested name must still mint"
        assert collided["AAA"]["reason"] == "live_origination_wins"
        assert collided["AAA"]["counterfactual"]["entry"] is not None

    def test_MUTATION_without_the_post_process_drop_AAA_is_double_minted(
            self, tmp_path, monkeypatch):
        """M9 — the second segregation-critical mutation, executed."""
        monkeypatch.setattr(bf, "live_plans_since", lambda plans, cutoff: {})
        live_id = "AAA-BULL-20260806"
        repo, sha = _pinned_repo(
            tmp_path, monkeypatch, buys=[_buy_row("AAA")],
            plans={live_id: _seed_plan(live_id, "AAA", recorded_at="2026-08-10")},
            closed_ids=(live_id,),
        )
        row = _replay(repo, sha)["row"]
        assert "AAA" in {e["ticker"] for e in row["minted"]}, (
            "with the collision rule disabled AAA still did not mint — the "
            "collision test above proves nothing"
        )

    def test_a_bear_incumbent_does_not_block_a_bull_replay(self, tmp_path, monkeypatch):
        """m15 — collisions key on ticker+DIRECTION. A live BEAR plan is a different
        episode and must not knock out the BULL reconstruction."""
        bear_id = "AAA-BEAR-20260810"
        repo, sha = _pinned_repo(
            tmp_path, monkeypatch, buys=[_buy_row("AAA")],
            plans={bear_id: _seed_plan(bear_id, "AAA", recorded_at="2026-08-10",
                                       direction="BEAR")},
            closed_ids=(bear_id,),
        )
        row = _replay(repo, sha)["row"]
        assert "AAA" in {e["ticker"] for e in row["minted"]}
        assert row["collided"] == []

    def test_an_open_live_plan_is_disclosed_as_a_collision_not_a_refusal(
            self, tmp_path, monkeypatch):
        live_id = "AAA-BULL-20260806"
        repo, sha = _pinned_repo(
            tmp_path, monkeypatch, buys=[_buy_row("AAA")],
            plans={live_id: _seed_plan(live_id, "AAA", recorded_at="2026-08-10")},
        )
        row = _replay(repo, sha)["row"]
        assert row["minted"] == []
        collided = {entry["ticker"]: entry for entry in row["collided"]}
        assert collided["AAA"]["reason"] == "live_origination_wins_open_plan_block"
        assert not row["still_refused"]

    def test_a_duplicate_id_the_LIVE_lane_won_is_surfaced_not_buried(
            self, tmp_path, monkeypatch):
        """§0.4 reaches the duplicate-id bucket too.

        Found live: once the 2026-08-10 nightly landed, twelve counterfactual names
        stopped being minted and started being duplicate-id suppressed — because the
        nightly originated them off the SAME formation anchor, producing the same
        plan id. Filing those as "the same episode published by an earlier bake"
        would erase exactly the live-vs-replay overlap this gate exists to show.
        """
        dup_id = "AAA-BULL-20260731"
        repo, sha = _pinned_repo(
            tmp_path, monkeypatch, buys=[_buy_row("AAA"), _buy_row("BBB", spot=50.0)],
            plans={dup_id: _seed_plan(dup_id, "AAA", recorded_at="2026-08-10")},
        )
        published = _replay(repo, sha)["row"]["already_published"]
        assert published["live_wins_within_window_count"] == 1
        won = published["live_wins_within_window"][0]
        assert won["plan_id"] == dup_id
        assert won["reason"] == "live_origination_wins_duplicate_id"
        assert won["live_recorded_at"] == "2026-08-10"

    def test_a_pre_window_duplicate_is_NOT_counted_as_a_live_win(
            self, tmp_path, monkeypatch):
        """The other direction: an id published before the window really is just an
        earlier bake's episode, and inflating the live-wins list would misreport the
        overlap in the opposite direction."""
        dup_id = "AAA-BULL-20260731"
        repo, sha = _pinned_repo(
            tmp_path, monkeypatch, buys=[_buy_row("AAA")],
            plans={dup_id: _seed_plan(dup_id, "AAA", recorded_at="2026-07-31")},
        )
        published = _replay(repo, sha)["row"]["already_published"]
        assert published["plan_ids"] == [dup_id]
        assert published["live_wins_within_window_count"] == 0

    def test_a_pre_window_open_plan_is_a_refusal_not_a_collision(
            self, tmp_path, monkeypatch):
        """An open plan from BEFORE the window is a block the 08-09 bake would have
        applied itself — honest as a refusal, dishonest as a collision."""
        old_id = "AAA-BULL-20260601"
        repo, sha = _pinned_repo(
            tmp_path, monkeypatch, buys=[_buy_row("AAA")],
            plans={old_id: _seed_plan(old_id, "AAA", recorded_at="2026-06-01")},
        )
        row = _replay(repo, sha)["row"]
        assert row["collided"] == []
        reasons = {e["ticker"]: e["reason"] for e in row["still_refused"]}
        assert reasons["AAA"] == "engine_refusal:reorigination_blocked"

    def test_gates_are_recorded_not_overridden(self, tmp_path, monkeypatch):
        """§0.8 — a candidate the engine refuses stays refused, with its own reason."""
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[
            _buy_row("AAA"), _late_anchor_row("LATE"),
        ])
        row = _replay(repo, sha)["row"]
        assert "LATE" not in {e["ticker"] for e in row["minted"]}
        refused = {e["ticker"]: e for e in row["still_refused"]}
        assert refused["LATE"]["reason"].startswith("engine_refusal:")
        assert refused["LATE"]["detail"]

    def test_verify_collisions_flags_a_name_that_went_live_after_execution(
            self, tmp_path, monkeypatch):
        """M7 — §0.4's window closes at MERGE, and this is what enforces it."""
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        _replay(repo, sha, execute=True)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "executed backfill")

        clean = bf.verify_collisions(repo, against="HEAD")
        assert clean["new_collisions"] == []

        # A later nightly originates AAA live — the exact race the mode exists for.
        late = _seed_plan("AAA-BULL-20260812", "AAA", recorded_at="2026-08-12")
        (repo / bf.PLANS_RELDIR / "AAA-BULL-20260812.json").write_text(
            json.dumps(late), encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "nightly originates AAA")

        dirty = bf.verify_collisions(repo, against="HEAD")
        assert [e["plan_key"] for e in dirty["new_collisions"]] == ["AAA-BULL"]


#: Ticker+direction keys that ALREADY carry multiple open plans on main, from before
#: the W1 re-origination block shipped (tests/test_prophet_w1_intake_repair.py
#: documents the same debt: "10 ticker+direction pairs held duplicate open plans on
#: 2026-08-03; PI held three"). This backfill did not create them and does not fix
#: them; the ratchet below stops it from ADDING to them, which is the part §0.4 owns.
_LEGACY_DOUBLED_KEYS = 10


@pytest.mark.skipif(
    not REAL_PLANS_DIR.exists(),
    reason="sparse checkout: site/prophet/plans is not materialised here",
)
class TestOnePlanPerEpisodeOnTheShippedTree:
    """§0.4 — one active plan per candidate episode, scoped to what this lane owns."""

    @staticmethod
    def _open_keys() -> dict[str, list[dict]]:
        ledger = _REPO / bf.LEDGER_RELPATH
        closed: set[str] = set()
        if ledger.exists():
            for line in ledger.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    closed.add(str(json.loads(line).get("id")))
                except Exception:  # noqa: BLE001
                    continue
        keys: dict[str, list[dict]] = {}
        for plan in _real_plans().values():
            if str(plan.get("id")) in closed:
                continue
            keys.setdefault(bf.plan_key_of(plan), []).append(plan)
        return keys

    def test_no_reconstructed_plan_shares_an_open_key_with_another_plan(self):
        """THE §0.4 assertion: a backfill must never double-mint a live name."""
        offenders = {
            key: [str(p.get("id")) for p in plans]
            for key, plans in self._open_keys().items()
            if len(plans) > 1 and any(
                str(p.get("origination_mode") or "").startswith("outage_backfill")
                for p in plans
            )
        }
        assert not offenders, (
            f"a reconstructed plan shares an open ticker+direction key with another "
            f"open plan: {offenders}. Live wins (§0.4) — the replay should have "
            "recorded this as a collision in backfill_disclosures.json instead of "
            "minting it. Re-run `--verify-collisions` before merging."
        )

    def test_the_legacy_duplicate_open_keys_do_not_grow(self):
        """A ratchet, not a heal. The pre-W1 duplicates are somebody else's lane; the
        point here is that this PR cannot quietly add an eleventh."""
        doubled = {k: [str(p.get("id")) for p in v]
                   for k, v in self._open_keys().items() if len(v) > 1}
        assert len(doubled) <= _LEGACY_DOUBLED_KEYS, (
            f"{len(doubled)} ticker+direction keys now carry multiple OPEN plans, up "
            f"from the {_LEGACY_DOUBLED_KEYS} pre-W1 legacy pairs: {doubled}. "
            "Something minted a second episode for a live name."
        )


# ===========================================================================
# 9. DETERMINISM + IDEMPOTENCE
# ===========================================================================

@pytest.mark.usefixtures("clean_panel", "agreeing_geometry")
class TestDeterminismAndIdempotence:

    def test_two_differently_seeded_trees_agree_on_the_pinned_inputs(
            self, tmp_path, monkeypatch):
        """B4 — determinism that could actually CATCH working-tree leakage.

        The old version ran the same repo twice, which is satisfied by any pure
        function of its own arguments. These two repos hold DIFFERENT extra plans and
        different scratch content, so anything the replay read from the tree rather
        than from the pinned board/baseline would move the minted set.
        """
        buys = [_buy_row("AAA"), _buy_row("BBB", spot=50.0)]
        repo_a, sha_a = _pinned_repo(
            tmp_path, monkeypatch, buys=buys, name="tree_a",
            plans={"NOISE-BULL-20260101": _seed_plan(
                "NOISE-BULL-20260101", "NOISE", recorded_at="2026-01-01")})
        first = _replay(repo_a, sha_a)

        repo_b, sha_b = _pinned_repo(
            tmp_path, monkeypatch, buys=buys, name="tree_b",
            plans={"OTHER-BULL-20260202": _seed_plan(
                "OTHER-BULL-20260202", "OTHER", recorded_at="2026-02-02"),
                "MORE-BULL-20260303": _seed_plan(
                    "MORE-BULL-20260303", "MORE", recorded_at="2026-03-03")})
        second = _replay(repo_b, sha_b)

        assert ([p["id"] for p in first["minted"]]
                == [p["id"] for p in second["minted"]])
        # Entry geometry too, not just identity: a re-run that re-prices is not a
        # replay, and a geometry input read from the tree would show up here.
        assert (
            [(p["id"], p["entry"], p["invalidation"], p["targets"],
              p["horizon_days"]) for p in first["minted"]]
            == [(p["id"], p["entry"], p["invalidation"], p["targets"],
                 p["horizon_days"]) for p in second["minted"]]
        )

    def test_a_dry_run_writes_nothing(self, tmp_path, monkeypatch):
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        before = sorted(p.name for p in (repo / bf.PLANS_RELDIR).glob("*.json"))
        _replay(repo, sha, execute=False)
        assert sorted(p.name for p in (repo / bf.PLANS_RELDIR).glob("*.json")) == before
        assert not (repo / bf.DISCLOSURES_RELPATH).exists()
        assert not (repo / bf.RECEIPTS_RELDIR).exists()

    def test_the_dry_run_and_the_execute_run_agree(self, tmp_path, monkeypatch):
        repo, sha = _pinned_repo(tmp_path, monkeypatch,
                                 buys=[_buy_row("AAA"), _buy_row("BBB", spot=50.0)])
        dry = _replay(repo, sha, execute=False)
        wet = _replay(repo, sha, execute=True)
        assert [p["id"] for p in dry["minted"]] == [p["id"] for p in wet["minted"]]

    def test_a_recorded_window_refuses_to_run_again(self, tmp_path, monkeypatch):
        """M5 — and the lock is read from COMMITTED history, so it must be committed
        before it locks anything."""
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        _replay(repo, sha, execute=True)
        # Not yet committed → not yet locked. That is the contract, stated.
        _replay(repo, sha, execute=False)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "executed backfill")
        with pytest.raises(bf.BackfillRefused, match="already records window"):
            _replay(repo, sha, execute=True)

    def test_the_lock_ignores_an_uncommitted_deletion(self, tmp_path, monkeypatch):
        """M5's whole point: deleting the working-tree copy must NOT unlock a
        one-off lane."""
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        _replay(repo, sha, execute=True)
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "executed backfill")
        (repo / bf.DISCLOSURES_RELPATH).unlink()
        with pytest.raises(bf.BackfillRefused, match="already records window"):
            _replay(repo, sha, execute=True)

    def test_a_missing_board_commit_refuses_rather_than_guessing(
            self, tmp_path, monkeypatch):
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        with pytest.raises(bf.BackfillRefused, match="does not resolve to a commit"):
            bf.run_backfill(
                repo, board_commit="deadbeef" * 5, plans_baseline=sha,
                executed_at="2026-08-11T00:00:00+00:00", execute=False)

    def test_a_baseline_with_no_post_bake_plan_refuses(self, tmp_path, monkeypatch):
        """M6 — a pre-nightly baseline shows zero collisions because the live plans
        do not exist yet, not because there are none."""
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        with pytest.raises(bf.BackfillRefused, match="post-bake baseline"):
            bf.run_backfill(
                repo, board_commit=sha, plans_baseline=sha,
                executed_at="2026-08-11T00:00:00+00:00", execute=False)

    def test_the_baseline_waiver_records_itself_in_the_disclosure(
            self, tmp_path, monkeypatch):
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        row = _replay(repo, sha, allow_empty_baseline_proof=True)["row"]
        proof = row["inputs"]["plans_baseline_post_bake_proof"]
        assert proof["waived"] is True and proof["found"] == 0

    def test_a_baseline_carrying_a_post_bake_plan_satisfies_the_proof(
            self, tmp_path, monkeypatch):
        repo, sha = _pinned_repo(
            tmp_path, monkeypatch, buys=[_buy_row("AAA")],
            plans={"NEW-BULL-20260810": _seed_plan(
                "NEW-BULL-20260810", "NEW", recorded_at="2026-08-10")})
        row = bf.run_backfill(
            repo, board_commit=sha, plans_baseline=sha,
            executed_at="2026-08-11T00:00:00+00:00", execute=False)["row"]
        proof = row["inputs"]["plans_baseline_post_bake_proof"]
        assert proof["waived"] is False and proof["found"] == 1


# ===========================================================================
# 10. RECEIPT SHAPE — pinned against the real downstream validator
# ===========================================================================

@pytest.mark.usefixtures("clean_panel", "agreeing_geometry")
class TestOriginationReceipt:

    def test_the_receipt_passes_the_chronology_audit_validator(
            self, tmp_path, monkeypatch):
        """``audit_prophet_plan_chronology`` validates EVERY receipt in a plan's
        creation commit, so a malformed backfill receipt breaks chronology audits
        for every plan created from that commit forward."""
        repo, sha = _pinned_repo(tmp_path, monkeypatch,
                                 buys=[_buy_row("AAA"), _buy_row("BBB", spot=50.0)])
        result = _replay(repo, sha, execute=True)
        path = f"{bf.RECEIPTS_RELDIR}/{result['receipt_id']}.json"
        source, by_id = _validate_receipt_shape(result["receipt"], receipt_path=path)
        assert source["path"] == bf.BOARD_RELPATH
        assert source["price_through"] == PRICE_THROUGH
        assert sorted(by_id) == sorted(p["id"] for p in result["minted"])

    def test_the_run_block_is_honest_about_what_produced_it(
            self, tmp_path, monkeypatch):
        """m12 — the auditor reads none of these fields, so a misleading `run` block
        would cost an auditor's trust for nothing."""
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        run = _replay(repo, sha)["receipt"]["run"]
        assert run["is_backfill"] is True
        assert run["actor"] == "scripts/backfill_prophet_outage.py"
        assert run["event"] == "operator_force_majeure_backfill"
        assert "prophet-outage-backfill" in run["ref"]

    def test_the_receipt_records_the_heal_and_the_geometry_vintages(
            self, tmp_path, monkeypatch):
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        backfill = _replay(repo, sha)["receipt"]["backfill"]
        assert backfill["heal"]["to"] is False
        assert backfill["heal"]["recomputed"]["mixed_vintage"] is False
        assert backfill["geometry_vintages"]

    def test_the_receipt_plan_hash_matches_the_bytes_on_disk(
            self, tmp_path, monkeypatch):
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        result = _replay(repo, sha, execute=True)
        for origin in result["receipt"]["originations"]:
            blob = (repo / origin["plan_path"]).read_bytes()
            assert hashlib.sha256(blob).hexdigest() == origin["plan_sha256"]

    def test_rewriting_a_receipt_with_different_bytes_is_a_hard_failure(
            self, tmp_path, monkeypatch):
        """m13 — receipts are immutable publication records, same discipline as the
        nightly writer (daily.yml:2687-2698)."""
        repo, sha = _pinned_repo(tmp_path, monkeypatch, buys=[_buy_row("AAA")])
        result = _replay(repo, sha, execute=True)
        path = repo / bf.RECEIPTS_RELDIR / f"{result['receipt_id']}.json"
        path.write_text('{"tampered": true}\n', encoding="utf-8")
        with pytest.raises(SystemExit):
            bf._write_artifacts(
                repo, minted=result["minted"], receipt=result["receipt"],
                receipt_id=result["receipt_id"], document=result["document"])


# ===========================================================================
# 11. THE LANE'S WRITE FENCE (§3.4)
# ===========================================================================

@pytest.mark.usefixtures("clean_panel", "agreeing_geometry")
class TestWriteFence:
    """The backfill NEVER advances the forward ledger or renders the surfaces."""

    def test_the_forward_ledger_and_rendered_surfaces_are_untouched(
            self, tmp_path, monkeypatch):
        live_id = "ZZZ-BULL-20260601"
        repo, sha = _pinned_repo(
            tmp_path, monkeypatch, buys=[_buy_row("AAA")],
            plans={live_id: _seed_plan(live_id, "ZZZ", recorded_at="2026-06-01")},
            closed_ids=(live_id,),
        )
        before = (repo / bf.LEDGER_RELPATH).read_bytes()
        _replay(repo, sha, execute=True)
        assert (repo / bf.LEDGER_RELPATH).read_bytes() == before, (
            "the backfill wrote data/prophet/ledger.jsonl — the nightly is the SOLE "
            "advancer of forward ledgers (house law)"
        )
        assert not (repo / "site" / "prophet" / "index.json").exists()
        assert not (repo / "site" / "prophet" / "states").exists()

    def test_only_the_minted_plan_files_appear(self, tmp_path, monkeypatch):
        repo, sha = _pinned_repo(tmp_path, monkeypatch,
                                 buys=[_buy_row("AAA"), _buy_row("BBB")])
        result = _replay(repo, sha, execute=True)
        written = sorted(p.stem for p in (repo / bf.PLANS_RELDIR).glob("*.json"))
        assert written == sorted(p["id"] for p in result["minted"])


# ===========================================================================
# 12. REAL-TREE CENSUS — read-only; the halves that run for real in CI
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
    hiding unlisted. The guard-the-guard below keeps that from being vacuous.
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
            f"disclosed-not-stamped={sorted(disclosed - stamped)}. Every plan whose "
            f"origination_mode starts 'outage_backfill' must be enumerated in "
            f"{bf.DISCLOSURES_RELPATH}, and vice versa. A NEW backfill needs its own "
            "operator authority, its own disclosure row and an amendment to "
            "research/PROPHET_LEDGER_SCHEMA.md — do not just delete the test."
        )

    def test_no_shipped_backfill_escapes_the_one_authorised_window(self):
        """One event. A second date here is scope creep, not a backfill."""
        for plan_id, plan in _real_plans().items():
            mode = str(plan.get("origination_mode") or "")
            if not mode.startswith("outage_backfill"):
                continue
            assert mode == bf.ORIGINATION_MODE, (
                f"{plan_id} carries origination_mode={mode!r}; the only authorised "
                f"backfill is {bf.ORIGINATION_MODE!r} (operator 2026-08-11)"
            )
            assert str(plan.get("recorded_at"))[:10] == bf.BACKFILL_ASOF


class TestTheDocsAndTheArtifactCannotDisagree:
    """M10 — this one ALWAYS runs, including before the replay executes."""

    def test_a_schema_addendum_claiming_execution_requires_the_artifact(self):
        """If the docs say the window was executed, the disclosure must exist.

        The other real-tree classes skip while the artifact is absent, which is
        correct but leaves a hole: docs claiming an executed backfill with no
        artifact behind them would be invisible. This closes it.
        """
        text = REAL_SCHEMA_DOC.read_text(encoding="utf-8")
        # UNINDENTED, at column 0. The addendum also *describes* this convention in
        # prose, and an anywhere-in-the-file substring match fired on that
        # description — a guard that trips on its own documentation is a guard
        # nobody keeps.
        claims_executed = any(
            line.startswith(f"executed_window: {bf.WINDOW_ID}")
            for line in text.splitlines()
        )
        if not claims_executed:
            pytest.skip("the addendum does not declare the window executed yet")
        assert REAL_DISCLOSURES.exists(), (
            f"research/PROPHET_LEDGER_SCHEMA.md declares {bf.WINDOW_ID} executed "
            f"but {bf.DISCLOSURES_RELPATH} does not exist. Either the artifact was "
            "lost or the doc is claiming something that never happened."
        )

    def test_the_addendum_scopes_the_exception_to_the_one_window(self):
        text = REAL_SCHEMA_DOC.read_text(encoding="utf-8")
        assert "Addendum 2026-08-11" in text, (
            "research/PROPHET_LEDGER_SCHEMA.md carries no force-majeure addendum; "
            "an undocumented exception reads as a repeal of the no-backfill law"
        )
        assert bf.BACKFILL_ASOF in text
        assert "us-board-frozen-alpha-2026-08" in text, (
            "the addendum does not name the ruling that keeps 08-03→08-06 refused"
        )


@pytest.mark.skipif(
    not REAL_DISCLOSURES.exists(),
    reason="the backfill has not been executed in this tree yet",
)
class TestTheDisclosureArtifactIsWellFormed:

    def test_the_document_declares_its_authority_and_inputs(self):
        document = json.loads(REAL_DISCLOSURES.read_text(encoding="utf-8"))
        rows = document.get("backfills") or []
        assert rows, "backfill_disclosures.json lists no backfills — truncated?"
        for row in rows:
            assert row["authority"]
            assert row["window"]["from"] and row["window"]["to"]
            inputs = row["inputs"]
            assert len(inputs["board_commit"]) == 40, "input SHAs must be pinned full"
            assert len(inputs["plans_baseline_commit"]) == 40
            assert inputs["board_sha256"] == bf.BAKE_BOARD_SHA256, (
                "the executed run did NOT read the pinned bake-time board"
            )
            assert inputs["board_rank_by"] == bf.REQUIRED_RANK_BY
            assert row["engine_selection_era"]

    def test_the_executed_run_verified_its_heal(self):
        document = json.loads(REAL_DISCLOSURES.read_text(encoding="utf-8"))
        for row in document.get("backfills") or []:
            heal = row["heal"]
            assert heal["recomputed"]["mixed_vintage"] is False
            assert heal["method"] == "recomputed_panel_price_reach"

    def test_the_executed_run_reconciles(self):
        document = json.loads(REAL_DISCLOSURES.read_text(encoding="utf-8"))
        for row in document.get("backfills") or []:
            for name, identity in row["reconciliation"].items():
                assert identity["holds"], f"{name} does not close on the shipped run"

    def test_the_only_disclosed_window_is_the_authorised_one(self):
        document = json.loads(REAL_DISCLOSURES.read_text(encoding="utf-8"))
        ids = [row["id"] for row in document.get("backfills") or []]
        assert ids == [bf.WINDOW_ID], (
            f"disclosed windows {ids} — the force-majeure exception covers exactly "
            f"one event ({bf.WINDOW_ID})."
        )
