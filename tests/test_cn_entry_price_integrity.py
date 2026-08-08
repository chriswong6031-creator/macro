"""CN forward-ledger ENTRY-PRICE INTEGRITY — the 300363.SZ (博腾股份) regression.

WHAT WENT WRONG (measured, research/cn_prophet_audit/CASE_300363_FULL_CHAIN_2026-08-08.md)
-------------------------------------------------------------------------------------------
The operator's flagship CN winner surfaced #1 on the 2026-08-05 board. Its published
forward-ledger entry `e` was the T+1 open, RE-DERIVED from the price store on every
nightly — so a published number was mutable:

    2026-08-06 nightly   e = 16.30   l = 17.03   p = +4.5%
    2026-08-08 (today)   e = 17.52   l = 20.44   p = +16.7%      ← silently restated

The cause was an impossible bar. The 2026-08-06 T+1 bar as stored that night read
**open 16.2999 against low 16.98** — the open sat 4% BELOW the session low, which cannot
happen — and nothing on the entry path checked ``open ∈ [low, high]``. The ledger took it
at face value, published a return off it, and swapped in a different entry (+7.5% higher)
once the bar healed. Two compounding defects rode along: the entry was never latched, and
``fill_basis`` published the ENTRY_BASIS CONSTANT ("t1_hl2") for rows that used neither
HL2 (08-06 HL2 = 17.38) nor the same price twice.

WHAT THIS FILE PINS
-------------------
1. BAR SANITY   — a corrupt T+1 bar never supplies an entry; it falls back to the
                  documented HL2 basis, or DEFERS when even high/low are inconsistent.
                  A line-start ``::warning`` names ticker + date.
2. PIT LATCH    — the entry a row has published is the entry it keeps. A healed bar is
                  disclosed additively (``e_revised`` / ``er``), never substituted, and the
                  published return `p` derives from the latched entry.
3. PROVENANCE   — ``basis_used`` / ``eb`` says what actually happened.

Every test carries its own witness that the fixture can SEE the failure — the corrupt and
healed bars are constructed so the old and new answers differ by 7.5%, and the latch tests
re-run the same resolution with an empty latch to prove the restatement is reachable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib import config
from engine import china_standout_track as t
from scripts import build_china_library as bcl


# ── the exact 300363.SZ shape ──────────────────────────────────────────────────────
TICKER = "300363.SZ"
BOARD_DATE = pd.Timestamp("2026-08-05")      # the session it ranked #1
T1_DATE = pd.Timestamp("2026-08-06")         # the entry bar

CORRUPT_OPEN = 16.2999                       # < low — impossible, as stored on 08-06 night
HEALED_OPEN = 17.52                          # what the same bar reads today
T1_HIGH, T1_LOW, T1_CLOSE = 17.78, 16.98, 17.03
T1_HL2 = (T1_HIGH + T1_LOW) / 2.0            # 17.38 — the DOCUMENTED basis

# the +20% ChiNext limit close two sessions later
D2_OPEN, D2_HIGH, D2_LOW, D2_CLOSE = 17.03, 20.44, 17.03, 20.44


def _frame(*, t1_open: float, n_tail: int = 12) -> pd.DataFrame:
    """The name's OHLC frame with the T+1 bar's open under test.

    Index: 2026-08-04 (pre-board) · 2026-08-05 (board) · 2026-08-06 (T+1) · 2026-08-07
    (+20% limit) · then a flat tail so a 10-session horizon can mature.
    """
    idx = [pd.Timestamp("2026-08-04"), BOARD_DATE, T1_DATE, pd.Timestamp("2026-08-07")]
    rows = [
        # open, high, low, close — the 08-04 ignition bar, then the real 08-05 print
        (16.299999, 18.50, 16.200001, 17.73),
        (17.35, 17.85, 17.35, 17.60),
        (t1_open, T1_HIGH, T1_LOW, T1_CLOSE),
        (D2_OPEN, D2_HIGH, D2_LOW, D2_CLOSE),
    ]
    tail = pd.bdate_range("2026-08-10", periods=n_tail)
    for _d in tail:
        idx.append(_d)
        rows.append((D2_CLOSE, D2_CLOSE * 1.001, D2_CLOSE * 0.999, D2_CLOSE))
    return pd.DataFrame(
        {"open": [r[0] for r in rows], "high": [r[1] for r in rows],
         "low": [r[2] for r in rows], "close": [r[3] for r in rows],
         "volume": np.full(len(rows), 5e7)},
        index=pd.DatetimeIndex(idx, name="Date"),
    )


def _bench(idx) -> pd.Series:
    """A flat CSI300 so every excess number is the name's own move, not beta."""
    return pd.Series(np.full(len(idx), 4000.0), index=idx)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Isolate data_dir (the latch is a parquet under it) and reset the warning dedupe."""
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path)
    t._CORRUPT_BAR_WARNED.clear()
    yield
    t._CORRUPT_BAR_WARNED.clear()


# ===========================================================================
# 0. The fixture must be able to SEE the defect
# ===========================================================================

def test_the_fixture_reproduces_the_measured_restatement():
    """Guard the guard: corrupt-open vs healed-open must differ by the measured +7.5%.

    A fixture where both readings agree would let every test below pass vacuously.
    """
    assert CORRUPT_OPEN < T1_LOW, "the whole point is an open BELOW the session low"
    restatement = HEALED_OPEN / CORRUPT_OPEN - 1.0
    assert restatement == pytest.approx(0.0749, abs=5e-4), (
        f"the 300363 entry restatement was +7.5%, fixture gives {restatement:+.2%}")
    # and the published return moved with it: +4.5% off 16.30 vs +16.7% off 17.52
    assert T1_CLOSE / CORRUPT_OPEN - 1.0 == pytest.approx(0.0448, abs=5e-4)
    assert D2_CLOSE / HEALED_OPEN - 1.0 == pytest.approx(0.1667, abs=5e-4)


# ===========================================================================
# 1. BAR SANITY GATE
# ===========================================================================

def test_corrupt_t1_open_is_refused_and_falls_back_to_the_documented_hl2(capsys):
    """open 16.2999 < low 16.98 → the open is NOT an entry; HL2 (17.38) is."""
    d = t._t1_fill_detail(_frame(t1_open=CORRUPT_OPEN), BOARD_DATE, TICKER)

    assert d["corrupt_bar"] is True
    assert d["entry"] == pytest.approx(T1_HL2), (
        f"a corrupt bar must fall back to the documented HL2 basis, got {d['entry']}")
    assert d["entry"] != pytest.approx(CORRUPT_OPEN), "the impossible open must never fill"
    assert d["basis_used"] == t.BASIS_T1_HL2
    assert d["t1_date"] == "2026-08-06"

    line = _one_annotation(capsys, "cn-corrupt-t1-bar")
    assert line.startswith("::warning "), (
        "GitHub drops an annotation that does not START the line (house law)")
    assert TICKER in line and "2026-08-06" in line
    assert "16.2999" in line and "16.98" in line


def test_a_sane_open_still_fills_at_the_open(capsys):
    """The gate must not disturb the normal path — no warning, basis t1_open."""
    d = t._t1_fill_detail(_frame(t1_open=HEALED_OPEN), BOARD_DATE, TICKER)
    assert d["corrupt_bar"] is False
    assert d["entry"] == pytest.approx(HEALED_OPEN)
    assert d["basis_used"] == t.BASIS_T1_OPEN
    assert "::warning" not in capsys.readouterr().out


def test_float_dust_on_the_bounds_is_not_corruption(capsys):
    """An open a rounding-error outside [low, high] is storage dust, not an impossible bar."""
    df = _frame(t1_open=HEALED_OPEN)
    df.loc[T1_DATE, "open"] = T1_HIGH * (1 + 5e-8)      # ~1e-6 of a price ≈ float32 noise
    d = t._t1_fill_detail(df, BOARD_DATE, TICKER)
    assert d["corrupt_bar"] is False and d["basis_used"] == t.BASIS_T1_OPEN
    assert "::warning" not in capsys.readouterr().out


def test_an_inconsistent_high_low_defers_rather_than_guessing(capsys):
    """low > high: the open is refused AND HL2 is unavailable → no entry is derived.

    A bar already proven internally inconsistent does not get a third guess at a price;
    the episode stays in flight and the next nightly retries it.
    """
    df = _frame(t1_open=CORRUPT_OPEN)
    df.loc[T1_DATE, ["high", "low"]] = [T1_LOW, T1_HIGH]   # swapped — low > high
    d = t._t1_fill_detail(df, BOARD_DATE, TICKER)

    assert d["corrupt_bar"] is True
    assert d["entry"] is None, "a corrupt bar must never fabricate a price"
    assert d["basis_used"] == t.BASIS_DEFERRED
    assert d["defer_reason"] and "next nightly" in d["defer_reason"]
    assert _one_annotation(capsys, "cn-corrupt-t1-bar").startswith("::warning ")


def test_a_corrupt_bar_does_not_fall_through_to_the_close():
    """The legacy close fallback is for a close-only bar, never for a proven-bad one."""
    df = _frame(t1_open=CORRUPT_OPEN)
    df.loc[T1_DATE, ["high", "low"]] = [T1_LOW, T1_HIGH]
    d = t._t1_fill_detail(df, BOARD_DATE, TICKER)
    assert d["entry"] is None and d["entry"] != T1_CLOSE


def test_a_close_only_bar_still_fills_at_the_close_and_says_so():
    """Legacy path preserved — and it is no longer mislabelled as HL2."""
    df = _frame(t1_open=HEALED_OPEN)[["close", "volume"]]
    d = t._t1_fill_detail(df, BOARD_DATE, TICKER)
    assert d["entry"] == pytest.approx(T1_CLOSE)
    assert d["basis_used"] == t.BASIS_T1_CLOSE


def test_the_corrupt_warning_is_emitted_once_per_bar(capsys):
    """grade() walks each row through the fill four-plus times; the log must not repeat."""
    df = _frame(t1_open=CORRUPT_OPEN)
    for _ in range(4):
        t._t1_fill_detail(df, BOARD_DATE, TICKER)
    hits = [ln for ln in capsys.readouterr().out.splitlines() if "cn-corrupt-t1-bar" in ln]
    assert len(hits) == 1, f"expected one annotation per corrupt bar, got {len(hits)}"


# ===========================================================================
# 2. PIT LATCH
# ===========================================================================

def _resolve(df, latch, pending=None):
    return t.resolve_entry(TICKER, BOARD_DATE, df, latch=latch, pending=pending)


def test_a_healed_bar_cannot_restate_a_published_entry(capsys):
    """Two nightlies over the SAME board row: night 1 publishes, night 2 must not move it."""
    # ── night 1: the corrupt bar is live; the gate lands us on HL2 and we latch it ──
    pending: list[dict] = []
    n1 = _resolve(_frame(t1_open=CORRUPT_OPEN), latch={}, pending=pending)
    assert n1["entry"] == pytest.approx(T1_HL2) and n1["latched"] is False
    assert t.append_entry_latches(pending, latched_asof="2026-08-06T12:00:00Z") == 1
    capsys.readouterr()

    # ── night 2: the bar has healed to open 17.52 ──────────────────────────────────
    latch = t.read_entry_latch()
    n2 = _resolve(_frame(t1_open=HEALED_OPEN), latch=latch)

    assert n2["entry"] == pytest.approx(T1_HL2), (
        f"the published entry must survive the heal; got {n2['entry']}")
    assert n2["latched"] is True
    assert n2["basis_used"] == t.BASIS_T1_HL2, "the latch carries its own basis forward"
    assert n2["e_revised"] == pytest.approx(HEALED_OPEN), (
        "the disagreement is DISCLOSED, not swallowed")
    assert n2["e_revision_reason"] and "not restated" in n2["e_revision_reason"]

    line = _one_annotation(capsys, "cn-entry-restatement-refused")
    assert line.startswith("::warning ") and TICKER in line

    # WITNESS: with no latch the same night-2 frame DOES produce the restated entry, so
    # the assertion above is pinning the latch and not an accident of the fixture.
    assert _resolve(_frame(t1_open=HEALED_OPEN), latch={})["entry"] == pytest.approx(HEALED_OPEN)


def test_an_agreeing_rederivation_records_no_revision(capsys):
    """The disclosure fields stay null in the normal case — no noise on healthy rows."""
    pending: list[dict] = []
    _resolve(_frame(t1_open=HEALED_OPEN), latch={}, pending=pending)
    t.append_entry_latches(pending)
    capsys.readouterr()

    again = _resolve(_frame(t1_open=HEALED_OPEN), latch=t.read_entry_latch())
    assert again["latched"] is True and again["entry"] == pytest.approx(HEALED_OPEN)
    assert again["e_revised"] is None and again["e_revision_reason"] is None
    assert "::warning" not in capsys.readouterr().out


def test_the_latch_is_keep_first_and_a_relatch_cannot_move_it():
    """Immutability lives in the STORE, not only in the resolver."""
    t.append_entry_latches([{"date": "2026-08-05", "ticker": TICKER, "entry": T1_HL2,
                             "basis_used": t.BASIS_T1_HL2, "t1_date": "2026-08-06",
                             "corrupt_bar": True}])
    t.append_entry_latches([{"date": "2026-08-05", "ticker": TICKER, "entry": HEALED_OPEN,
                             "basis_used": t.BASIS_T1_OPEN, "t1_date": "2026-08-06",
                             "corrupt_bar": False}])
    latch = t.read_entry_latch()
    assert len(latch) == 1
    assert latch[("2026-08-05", TICKER)]["entry"] == pytest.approx(T1_HL2)
    assert latch[("2026-08-05", TICKER)]["corrupt_bar"] is True


def test_a_deferred_derivation_is_never_latched():
    """Deferral must stay retryable — latching a null would freeze the row forever."""
    df = _frame(t1_open=CORRUPT_OPEN)
    df.loc[T1_DATE, ["high", "low"]] = [T1_LOW, T1_HIGH]
    pending: list[dict] = []
    out = _resolve(df, latch={}, pending=pending)
    assert out["entry"] is None and pending == []
    assert t.append_entry_latches([{"date": "2026-08-05", "ticker": TICKER,
                                    "entry": None}]) == 0
    # the next nightly, on a healed bar, derives and latches normally
    p2: list[dict] = []
    assert _resolve(_frame(t1_open=HEALED_OPEN), latch=t.read_entry_latch(),
                    pending=p2)["entry"] == pytest.approx(HEALED_OPEN)
    assert len(p2) == 1


def test_a_missing_latch_store_is_forward_only_not_an_error():
    assert t.read_entry_latch() == {}
    assert t.append_entry_latches([]) == 0


def test_the_latch_lives_beside_the_board_store(monkeypatch, tmp_path):
    """The latch path is DERIVED from _store_path(), not read from data_dir() again.

    Reading data_dir() independently let a suite that had already redirected the board
    (tests/test_track_ledger_emitters.py monkeypatches `_store_path` only) write synthetic
    tickers into the repo's real data/china_standout_track/. Deriving it means one
    redirection covers both stores.
    """
    elsewhere = tmp_path / "somewhere_else" / "board.parquet"
    monkeypatch.setattr(t, "_store_path", lambda: elsewhere)
    assert t._entry_latch_path().parent == elsewhere.parent
    assert t._entry_latch_path().name == "entry_latch.parquet"


def test_the_latch_is_keyed_on_date_and_ticker_only():
    """The T+1 fill is a property of the price store, so two board definitions surfacing
    the same name on the same date must publish the SAME entry."""
    t.append_entry_latches([{"date": "2026-08-05", "ticker": TICKER, "entry": T1_HL2,
                             "basis_used": t.BASIS_T1_HL2, "t1_date": "2026-08-06",
                             "corrupt_bar": False}])
    assert set(t.read_entry_latch().keys()) == {("2026-08-05", TICKER)}


def test_append_entry_latches_is_gated_to_the_asia_lane():
    assert t.append_entry_latches(
        [{"date": "2026-08-05", "ticker": TICKER, "entry": T1_HL2}], lane="render") == 0
    assert t.read_entry_latch() == {}
    assert t.append_entry_latches(
        [{"date": "2026-08-05", "ticker": TICKER, "entry": T1_HL2}], lane="asia") == 1


# ===========================================================================
# 3. THE PUBLISHED LEDGER — the full chain, two nightlies
# ===========================================================================

def _ledger_row(monkeypatch, df) -> tuple[dict, tuple]:
    """Run one nightly's _cn_ledger_rows over a single-name board and return its row."""
    monkeypatch.setattr(t, "_price_frame", lambda tk: df if tk == TICKER else None)
    board = pd.DataFrame([{"date": "2026-08-05", "ticker": TICKER,
                           "board_rank": 1, "tier": "T2"}])
    rows, n_locked, scored, n_inflight, n_awaiting, n_no_price = bcl._cn_ledger_rows(
        board, _bench(df.index), {}, t)
    counters = (n_locked, len(scored), n_inflight, n_awaiting, n_no_price)
    return (rows[0] if rows else {}), counters


def test_published_entry_and_return_survive_the_bar_heal(monkeypatch, capsys):
    """THE REGRESSION. Night 1 on the corrupt bar, night 2 on the healed one — the
    published `e` and `p` must be byte-identical across the two runs."""
    night1, _ = _ledger_row(monkeypatch, _frame(t1_open=CORRUPT_OPEN))
    assert night1["e"] == pytest.approx(round(T1_HL2, 2)), (
        f"night 1 must publish the HL2 fallback, not the impossible open; got {night1['e']}")
    assert night1["eb"] == t.BASIS_T1_HL2
    assert night1["er"] is None
    capsys.readouterr()

    night2, _ = _ledger_row(monkeypatch, _frame(t1_open=HEALED_OPEN))

    assert night2["e"] == night1["e"], (
        f"published entry restated {night1['e']} → {night2['e']} — this is the defect")
    assert night2["p"] == night1["p"], (
        f"published return restated {night1['p']} → {night2['p']}")
    assert night2["eb"] == t.BASIS_T1_HL2
    assert night2["er"] == pytest.approx(round(HEALED_OPEN, 2)), (
        "the healed re-derivation is disclosed additively")
    assert night2["erw"] and "point-in-time" in night2["erw"]


def test_the_old_path_really_did_restate(monkeypatch):
    """WITNESS for the test above: with the latch removed the ledger DOES move.

    Without this, `night2['e'] == night1['e']` could pass because the two nightlies never
    differed — which is exactly how a regression test rots into a tautology.
    """
    monkeypatch.setattr(t, "read_entry_latch", dict)          # every night starts blank
    monkeypatch.setattr(t, "append_entry_latches", lambda *a, **k: 0)
    n1, _ = _ledger_row(monkeypatch, _frame(t1_open=CORRUPT_OPEN))
    n2, _ = _ledger_row(monkeypatch, _frame(t1_open=HEALED_OPEN))
    assert n2["e"] != n1["e"], "the fixture cannot see a restatement — it proves nothing"
    assert n2["e"] == pytest.approx(round(HEALED_OPEN, 2))


def test_a_deferred_entry_leaves_the_episode_in_flight(monkeypatch, capsys):
    """A row with no honest entry is awaiting-T+1, not a survivorship hole and not graded."""
    df = _frame(t1_open=CORRUPT_OPEN)
    df.loc[T1_DATE, ["high", "low"]] = [T1_LOW, T1_HIGH]
    row, (n_locked, n_scored, n_inflight, n_awaiting, n_no_price) = _ledger_row(monkeypatch, df)
    assert row == {}, "a deferred entry must not publish a price"
    assert (n_awaiting, n_no_price) == (1, 0)
    assert _one_annotation(capsys, "cn-corrupt-t1-bar").startswith("::warning ")


def test_the_published_return_derives_from_the_latched_entry(monkeypatch):
    """`p` is computed from `e`, so a latched `e` with a fresh `l` must stay consistent."""
    night1, _ = _ledger_row(monkeypatch, _frame(t1_open=CORRUPT_OPEN))
    e, latest, pct = night1["e"], night1["l"], night1["p"]
    assert pct == pytest.approx(round((latest / e - 1.0) * 100, 1), abs=0.15), (
        f"p={pct} does not derive from e={e} and l={latest}")


# ===========================================================================
# helpers
# ===========================================================================

def _one_annotation(capsys, title: str) -> str:
    """Return the single captured annotation line carrying ``title`` (asserting there is one)."""
    lines = [ln for ln in capsys.readouterr().out.splitlines() if title in ln]
    assert len(lines) == 1, f"expected exactly one {title!r} annotation, got {lines}"
    return lines[0]
