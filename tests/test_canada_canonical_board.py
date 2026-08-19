"""tests/test_canada_canonical_board.py — CA-TRUTH: one canonical Canada Prophet
board per session (masterplan §5.0).

Regression coverage for the production defect: scripts/build_canada_library.py
built the Canada board with Branch-B ripe-list ordering inside
compute_canada_standouts() (stamping branch='B', rank_basis=
'momentum_screen_accruing', per-row board_pos), but the old main() then re-sorted
wide["buy"] with an obsolete composite key (_combine_key) and entry_open_first()
BEFORE writing site/factordata/canada_standouts.json — so the artifact's row order
silently contradicted its own board_pos stamps and its declared branch/rank_basis,
and diverged from the separately-recomputed page object in build_canada.py.

The fix: build_canada_library._build_canonical_board() is the ONE place the board
is built — Branch-B order (compute_canada_standouts -> _branch_b_order), enriched
in place (order-neutral), stamped with board-level authority fields, and NO sort
of any kind runs after it. main() writes and returns the exact same object;
build_canada.py renders that object verbatim (no second compute_canada_standouts
pass); scripts/build_canada._canada_board_ledger() logs it in that same order,
stamping board_definition on every row.

Tests import the REAL functions under test (compute_canada_standouts,
_build_canonical_board, _branch_b_order, _canada_board_ledger,
engine.board_ledger.append_board) — no mirrored logic — per the house convention
(tests/test_us_standouts_cascade_gate.py).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.board_ledger as bl  # noqa: E402
from engine.setups import entry_open_first as _old_entry_open_first  # noqa: E402
from lib import config as lib_config  # noqa: E402
from scripts import build_canada_library as bcal  # noqa: E402
from scripts import build_canada as bca  # noqa: E402


# ---------------------------------------------------------------------------
# Shared synthetic fixture: 3 buy rows engineered so the OLD composite key
# (_combine_key: align_tier=='aligned' group first, then setup-score percentile)
# and the OLD entry_open_first (buy_now + composite_z>0 floats to top, then by
# conviction score) BOTH disagree with the Branch-B order (group=entry_open
# before setting_up, then alpha desc within group).
#
#   Branch-B canonical order:      B.TO, C.TO, A.TO   (entry_open by alpha desc, then setting_up)
#   OLD entry_open_first order:    B.TO, A.TO, C.TO   (buy_now floats up, then conviction score desc)
#   OLD _combine_key order:        A.TO, C.TO, B.TO   (aligned group first, then setup-score desc)
# ---------------------------------------------------------------------------

def _synthetic_cand_and_maps():
    cand = [
        (0.9, {"ticker": "A.TO", "name": "Alpha Bank", "alpha": 0.6, "factor_z": 0.0,
              "setup": 0.9,
              "entry_signal": {"status": "wait_pullback"},
              "conviction": {"score": 90, "composite_z": 1.0}}),
        (0.2, {"ticker": "B.TO", "name": "Bravo Energy", "alpha": 2.0, "factor_z": 0.0,
              "setup": 0.2,
              "entry_signal": {"status": "buy_now"},
              "conviction": {"score": 40, "composite_z": 0.3}}),
        (0.5, {"ticker": "C.TO", "name": "Charlie Metals", "alpha": 1.0, "factor_z": 0.0,
              "setup": 0.5,
              "entry_signal": {"status": "partial"},
              "conviction": {"score": 70, "composite_z": 0.6}}),
    ]
    align_map = {
        "A.TO": {"aligned": True, "score": 0.8},
        "B.TO": {"aligned": False, "near": True, "score": 0.4},
        "C.TO": {"aligned": True, "score": 0.8},
    }
    profiles = {t: r["conviction"] for _s, r in cand for t in [r["ticker"]]}
    sig_verdict: dict = {}   # empty -> signal_gate.compact(None) on every row
    entry_sig: dict = {}
    risk_sig: dict = {}
    return cand, align_map, profiles, sig_verdict, entry_sig, risk_sig


@pytest.fixture(autouse=True)
def _hermetic_breadth_and_data_dir(tmp_path, monkeypatch):
    """compute_canada_standouts() reads _breadth_panel() (closes/sector/name) and
    lib.config.data_dir() (W8-G board-ledger first-seen lookup). Neither must touch
    real repo data in this sparse checkout — mirrors
    test_w8g_ca_days_since_signal_builder_enrichment's mocking pattern."""
    monkeypatch.setattr(bcal, "_breadth_panel",
                        lambda: (pd.DataFrame(), {}, {}))
    monkeypatch.setattr(lib_config, "data_dir", lambda: tmp_path)


def _no_real_track_ledger_write(monkeypatch):
    """_canada_board_ledger's TRD-popup step (build_canada.py) writes
    ca_track_ledger.json to the REAL site dir (engine.track_ledger.atomic_write) as
    a best-effort side step, independent of the board_ledger parquet store this
    file otherwise redirects to tmp_path. Neutralize it so hermetic tests never
    touch the real site/ tree (MM_DATA_GUARD)."""
    import engine.track_ledger as _tl
    monkeypatch.setattr(_tl, "atomic_write", lambda *_a, **_k: None)


def _build_board(overlay=None):
    cand, align_map, profiles, sig_verdict, entry_sig, risk_sig = _synthetic_cand_and_maps()
    eligible = sum(1 for _s, r in cand
                   if (align_map.get(r.get("ticker")) or {}).get("aligned"))
    return bcal._build_canonical_board(
        cand, as_of="2026-07-10", align_map=align_map, sig_verdict=sig_verdict,
        profiles=profiles, entry_sig=entry_sig, risk_sig=risk_sig,
        eligible=eligible, disp_regime=None, overlay=overlay)


# ---------------------------------------------------------------------------
# 1. Single source of truth
# ---------------------------------------------------------------------------

def test_canada_canonical_board_is_single_source_of_truth():
    """The object _build_canonical_board() returns IS the object main() both writes
    to canada_standouts.json and returns to the caller — round-tripping it through
    JSON (exactly as the artifact write does) must not change row order."""
    board = _build_board()
    written = json.loads(json.dumps(board, separators=(",", ":"), default=str))
    assert [r["ticker"] for r in written["buy"]] == [r["ticker"] for r in board["buy"]]

    # structural: main() must write and return the SAME variable — a swapped-order
    # artifact write (mutation c) would require a DIFFERENT expression at the write
    # site than the returned object.
    src = Path(bcal.__file__).read_text()
    assert 'json.dumps(board, separators=(",", ":"), default=str))' in src, (
        "main() must write canada_standouts.json from the exact `board` object "
        "_build_canonical_board() returns"
    )
    main_body = src.split("\ndef main(", 1)[1].split('\nif __name__', 1)[0]
    assert main_body.rstrip().endswith("return board"), (
        "main() must return the canonical `board` object (CA-TRUTH), not a "
        "re-derived or renamed one"
    )
    # exactly one canonical-board build call in main() — no second compute pass
    assert src.count("_build_canonical_board(") == 2, (  # def + the one call site
        "main() must build the canonical board exactly ONCE"
    )


# ---------------------------------------------------------------------------
# 2. Artifact / page order parity
# ---------------------------------------------------------------------------

def test_canada_artifact_page_order_parity():
    """The written artifact's row order == board_pos order == the object
    build_canada.py renders (main()'s returned board, verbatim)."""
    board = _build_board()
    tickers = [r["ticker"] for r in board["buy"]]
    board_pos_order = [r["ticker"] for r in sorted(board["buy"], key=lambda r: r["board_pos"])]
    assert tickers == board_pos_order == ["B.TO", "C.TO", "A.TO"]

    # build_canada.py must render main()'s return value verbatim: no second
    # compute_canada_standouts() pass, no re-sort of vm["setups"].
    src = Path(bca.__file__).read_text()
    assert "compute_canada_standouts" not in src, (
        "build_canada.py must not re-derive the board — it renders build_canada_"
        "library.main()'s return value verbatim (CA-TRUTH)"
    )
    assert 'setups = build_canada_library.main(alpha=alpha, overlay=' in src

    # nothing may re-sort vm["setups"]["buy"] between the assignment and the next
    # section (top_setups) — mutation-kill target (f): a page-level re-sort.
    marker = 'vm["setups"] = setups'
    idx = src.index(marker)
    window = src[idx + len(marker):idx + len(marker) + 400]
    assert "sort" not in window, (
        f"build_canada.py must not re-sort vm['setups'] after assignment; "
        f"found a sort-like call in the window right after it:\n{window}"
    )


# ---------------------------------------------------------------------------
# 3. Ledger order matches the canonical board
# ---------------------------------------------------------------------------

def test_canada_ledger_order_matches_canonical_board(tmp_path, monkeypatch):
    monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _no_real_track_ledger_write(monkeypatch)

    board = _build_board()
    board["watch"] = [{"ticker": "W.TO", "name": "Watch Co", "alpha": 0.9,
                       "watch_reason": "blocked", "block_reason": "no turn"}]
    latest = {"date": "2026-07-10"}

    bca._canada_board_ledger(board, latest)

    df = pd.read_parquet(tmp_path / "ca_board.parquet").sort_values("board_pos")
    n_buy = len(board["buy"])
    assert df["ticker"].tolist() == ["B.TO", "C.TO", "A.TO", "W.TO"]
    assert df["board_pos"].tolist() == [1, 2, 3, 4]
    assert (df["group"].tolist()[:n_buy] ==
            [r["group"] for r in board["buy"]])
    assert df.iloc[n_buy]["group"] == "watch"
    assert len(df) == n_buy + 1


# ---------------------------------------------------------------------------
# 4. No second sort after Branch-B
# ---------------------------------------------------------------------------

def test_canada_no_second_sort_after_branch_b():
    """Synthetic board where the OLD composite key AND the OLD entry_open_first
    would BOTH re-rank differently from Branch-B (see fixture docstring above).
    The canonical board must stay exactly Branch-B ordered."""
    board = _build_board()
    branch_b_order = [r["ticker"] for r in bcal._branch_b_order(
        [dict(r) for r in
         [{"ticker": "A.TO", "alpha": 0.6, "entry_signal": {"status": "wait_pullback"}},
          {"ticker": "B.TO", "alpha": 2.0, "entry_signal": {"status": "buy_now"}},
          {"ticker": "C.TO", "alpha": 1.0, "entry_signal": {"status": "partial"}}]],
        overlay={})]
    assert [r["ticker"] for r in board["buy"]] == branch_b_order == ["B.TO", "C.TO", "A.TO"]

    # the OLD order (computed independently here, NOT applied) proves the fixture
    # has teeth: it would have produced a DIFFERENT order than Branch-B.
    old_order = [r["ticker"] for r in
                _old_entry_open_first([dict(r) for _s, r in _synthetic_cand_and_maps()[0]])]
    assert old_order != [r["ticker"] for r in board["buy"]], (
        "fixture must be engineered so the old open-entry-first re-sort disagrees "
        "with Branch-B"
    )

    src = Path(bcal.__file__).read_text()
    assert "_combine_key" not in src, (
        "the obsolete composite re-rank (_combine_key) must be fully removed from "
        "scripts/build_canada_library.py, not just unused"
    )
    assert "entry_open_first" not in src, (
        "entry_open_first must not be called anywhere in the CA board build path"
    )


# ---------------------------------------------------------------------------
# 5. Board-level authority stamps
# ---------------------------------------------------------------------------

def test_canada_official_pick_authority_false_under_branch_b():
    board = _build_board()
    assert board["board_definition"] == bcal.CA_BOARD_DEFINITION == "ca_prophet_branch_b_v1"
    assert board["authority"] == bcal.CA_BOARD_AUTHORITY == "screen"
    assert board["selection_status"] == "accruing"
    assert board["official_pick_authority"] is False


def test_canada_legacy_buy_key_is_projection_not_authority():
    board = _build_board()
    assert board["legacy_buy_key_semantics"] == "ripe_list_screen"
    assert board["official_pick_authority"] is False


# ---------------------------------------------------------------------------
# 6. board_definition stamped on every current-board ledger row
# ---------------------------------------------------------------------------

def test_canada_current_rows_stamp_board_definition(tmp_path, monkeypatch):
    monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")
    monkeypatch.setenv("COLLECT_LANE", "nightly")
    _no_real_track_ledger_write(monkeypatch)

    board = _build_board()
    board["watch"] = [{"ticker": "W.TO", "name": "Watch Co", "alpha": 0.9,
                       "watch_reason": "blocked", "block_reason": "no turn"}]
    latest = {"date": "2026-07-10"}

    bca._canada_board_ledger(board, latest)

    df = pd.read_parquet(tmp_path / "ca_board.parquet")
    assert (df["board_definition"] == bcal.CA_BOARD_DEFINITION).all(), (
        f"every CA board ledger row must stamp board_definition; got "
        f"{df['board_definition'].tolist()}"
    )


# ---------------------------------------------------------------------------
# 7. Legacy (unstamped) rows are never retroactively stamped / overwritten
# ---------------------------------------------------------------------------

def test_canada_legacy_rows_remain_unstamped(tmp_path, monkeypatch):
    """append_board's keep-FIRST semantics (engine/board_ledger.py, untouched here):
    a pre-existing legacy row (board_definition=None) keeps None after a LATER
    stamped append, and a same-(date,ticker) re-append can never overwrite the
    incumbent row — CA appends are lane-gated on nightly_advance_enabled()
    (tests/test_board_ledger.py pattern)."""
    monkeypatch.setattr(bl, "_store_path", lambda m: tmp_path / f"{m.lower()}_board.parquet")
    monkeypatch.setenv("COLLECT_LANE", "nightly")

    # day 1: legacy (unstamped) row
    n1 = bl.append_board(
        [{"ticker": "SHOP.TO", "group": "entry_open", "edge_z": 1.0}],
        market="CA", asof="2026-07-01")
    assert n1 == 1

    # day 2: a NEW stamped row for a different ticker
    n2 = bl.append_board(
        [{"ticker": "RY.TO", "group": "entry_open", "edge_z": 0.8,
          "board_definition": bcal.CA_BOARD_DEFINITION}],
        market="CA", asof="2026-07-02")
    assert n2 == 2

    df = pd.read_parquet(tmp_path / "ca_board.parquet")
    legacy_row = df[df["ticker"] == "SHOP.TO"].iloc[0]
    assert pd.isna(legacy_row["board_definition"]), (
        "a legacy row must NOT be retroactively stamped by a later append"
    )
    stamped_row = df[df["ticker"] == "RY.TO"].iloc[0]
    assert stamped_row["board_definition"] == bcal.CA_BOARD_DEFINITION

    # re-append the SAME (date, ticker) with a DIFFERENT (stamped) payload — keep-
    # FIRST means the incumbent (unstamped, edge_z=1.0) value wins, never overwritten
    n3 = bl.append_board(
        [{"ticker": "SHOP.TO", "group": "watch", "edge_z": 9.9,
          "board_definition": bcal.CA_BOARD_DEFINITION}],
        market="CA", asof="2026-07-01")
    assert n3 == 2   # still 2 rows — no duplicate added
    df2 = pd.read_parquet(tmp_path / "ca_board.parquet")
    row2 = df2[df2["ticker"] == "SHOP.TO"].iloc[0]
    assert row2["group"] == "entry_open"          # original value, NOT "watch"
    assert abs(float(row2["edge_z"]) - 1.0) < 1e-9  # original value, NOT 9.9
    assert pd.isna(row2["board_definition"]), (
        "keep-FIRST must not let a later re-append stamp board_definition onto an "
        "already-written legacy row"
    )


# ---------------------------------------------------------------------------
# 8. Laggards strip keeps the PAGE's historical count (n_lag=6, not the
#    canada_setups.json artifact's n_lag=12) — templates/canada.html.j2 renders
#    setups.laggards UNSLICED, so an n_lag drift back to 12 silently doubles the
#    user-visible "Weakest screen (laggards)" strip (review finding, PR #5926).
# ---------------------------------------------------------------------------

def _cand_with_many_laggards():
    """14 distinct laggard candidates (alpha well under LAG_MAX=-0.3) — more than
    both the fixed n_lag=6 ceiling AND the old n_lag=12 one, so a regression back
    to 12 is caught (14 candidates -> 12 laggards under the old value, still >6)."""
    cand, align_map, profiles, sig_verdict, entry_sig, risk_sig = _synthetic_cand_and_maps()
    for i in range(14):
        t = f"L{i:02d}.TO"
        cand.append((0.0, {"ticker": t, "name": f"Laggard {i} Corp",
                           "alpha": -1.0 - i * 0.1, "factor_z": 0.0,
                           "setup": 0.0}))
    return cand, align_map, profiles, sig_verdict, entry_sig, risk_sig


def test_canada_laggards_strip_capped_at_six():
    """The canonical board's laggards strip must stay at the page's historical
    n_lag=6 ceiling, even when far more than 6 (or 12) laggard candidates exist —
    a regression to n_lag=12 (or any drift) is caught here."""
    cand, align_map, profiles, sig_verdict, entry_sig, risk_sig = _cand_with_many_laggards()
    eligible = sum(1 for _s, r in cand
                   if (align_map.get(r.get("ticker")) or {}).get("aligned"))
    board = bcal._build_canonical_board(
        cand, as_of="2026-07-10", align_map=align_map, sig_verdict=sig_verdict,
        profiles=profiles, entry_sig=entry_sig, risk_sig=risk_sig,
        eligible=eligible, disp_regime=None, overlay=None)
    assert len(board["laggards"]) <= 6, (
        f"laggards strip must stay <= 6 (page's historical n_lag); got "
        f"{len(board['laggards'])} from 14 candidates — n_lag drifted"
    )
    assert len(board["laggards"]) == 6, (
        "with 14 laggard-eligible candidates the strip should fill to exactly 6"
    )
