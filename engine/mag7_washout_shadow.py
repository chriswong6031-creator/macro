"""MWR-W1 — shadow book + Prophet confluence sidecar (pure accrual, never a gate).

The §4 Use-B evidence vehicle for the Mag-7 washout re-entry prereg
(research/MAG7_WASHOUT_REENTRY_PREREG.md §7, recipes PINNED there before this
code was written). Mirrors engine/prophet_stage_shadow.py's discipline: PURE
ACCRUAL + MEASUREMENT — this module NEVER gates, ranks, sizes, or alters any
Prophet or board decision; every artifact is display/shadow tier. A null here
never blocks anything.

Three artifacts (all under data/mag7_washout/, synapse-registered):
  shadow_book.jsonl        — FORWARD LEDGER. One row per (tf, trigger_date,
                             instrument) appended ONLY at 63td maturity;
                             nightly is the sole advancer
                             (ledger_lane.nightly_advance_enabled()).
  shadow_state.json        — open-position mark-to-market + book tally
                             (display context; rewritten each nightly).
  prophet_confluence.jsonl — sidecar stamping MWR gate state onto US-board
                             picks whose ticker ∈ M7 (READ-ONLY wrt Prophet;
                             dedup (as_of, lane, ticker)).

Pinned recipe (§7 W1a): every triggers.jsonl row spawns 8 hypothetical
unit-notional entries — 'EW' + each member. Entry basis = next-session CLOSE
after the trigger date (closes only, conservative vs the census t0-close
ruler). Grades from store closes at maturity: ret21, ret63, adverse63 (worst
close within 63td). Frozen ruler: HIT = ret63 > +8.9 (census all-days median,
pinned) AND adverse63 > −10; FAIL = ret63 < 0 OR adverse63 ≤ −15; else MIXED.
Basket ('EW') rows are the §4 gauntlet rows; member rows are diagnostic only.

Matured rows additionally carry the §7-item-4 timing scorecard (bottom-picking
ruler): prox_pct + within_3/within_5 (entry close vs the ±31td local trough),
signed td_to_trough with timing_label called_low/confirmed_reset/early, and
mfe21/rc21 (21td reversion-capture, Oracle-law time-exit). The Amendment-2
HIT/FAIL ruler above stays the live-gate ruler — both rulers are presented
side-by-side at the first forward ruling.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from engine.ledger_lane import nightly_advance_enabled
from engine.mag7_washout import M7, ew_basket
from lib import config

log = logging.getLogger(__name__)

SCHEMA = "mag7_washout_shadow.v1"
BASELINE_FWD63 = 8.9      # frozen census all-days median (prereg §7 — never live-recomputed)
HIT_ADVERSE_FLOOR = -10.0
FAIL_ADVERSE_FLOOR = -15.0
HORIZON = 63
PROX = 31    # ±31td local-trough proximity window (charter §7 timing ruler)
TEXIT = 21   # reversion-capture time-exit (Oracle law ~20-25d; pinned 21)
INSTRUMENTS = ["EW", *M7]


def _base(root: Path | None) -> Path:
    return (root if root is not None else config.data_dir()) / "mag7_washout"


def _closes(root: Path | None, inst: str) -> pd.Series | None:
    try:
        if inst == "EW":
            return ew_basket(root)
        p = (root if root is not None else config.data_dir()) / "baskets" / "ohlcv" / f"{inst}.parquet"
        return pd.read_parquet(p)["close"]
    except Exception as e:  # noqa: BLE001 — per-instrument fail-open
        log.warning("mag7_washout_shadow: %s closes unavailable (%s)", inst, e)
        return None


def _grade(ret63: float, adverse: float) -> str:
    if ret63 < 0 or adverse <= FAIL_ADVERSE_FLOOR:
        return "FAIL"
    if ret63 > BASELINE_FWD63 and adverse > HIT_ADVERSE_FLOOR:
        return "HIT"
    return "MIXED"


def _timing_scorecard(s: pd.Series, e: int, entry_px: float) -> dict:
    """Additive §7-item-4 bottom-picking-ruler fields for a matured entry at
    positional index e. Arithmetic mirrors ptt_w1_timing_regrade.metric_arrays
    (closes only; first-hit argmin; PROX=31, TEXIT=21). Maturity guarantees
    e+HORIZON exists, so the forward windows (e+TEXIT) are always in-bounds."""
    # mfe21: max close in the NEXT 21td (entry bar EXCLUDED, window [e+1, e+21]).
    mfe21 = round((float(s.iloc[e + 1: e + TEXIT + 1].max()) / entry_px - 1) * 100, 1)
    # rc21: close at t+21 vs entry — arithmetically == ret21, kept under its own
    # timing-ruler name so the scorecard is self-contained (do NOT alias ret21).
    rc21 = round((float(s.iloc[e + TEXIT]) / entry_px - 1) * 100, 1)
    if e < PROX:
        # head-of-store trim: fewer than 31 prior sessions → the ±31td trough
        # window is undefined. Nulls printed, not hidden.
        return {"prox_pct": None, "td_to_trough": None, "within_3": None,
                "within_5": None, "timing_label": None, "mfe21": mfe21, "rc21": rc21}
    w = s.iloc[e - PROX: e + PROX + 1].to_numpy(dtype=float)  # 63-wide, centered on e
    lo = w.min()
    prox_raw = (entry_px / lo - 1) * 100  # entry premium over the local trough; ≥0 (window includes e)
    td_to_trough = int(np.argmin(w)) - PROX  # first-hit argmin tie-break; negative = trough BEFORE entry
    # flags read the RAW value before rounding
    within_3 = bool(prox_raw <= 3.0)
    within_5 = bool(prox_raw <= 5.0)
    if -2 <= td_to_trough <= 5:
        timing_label = "called_low"
    elif td_to_trough < -2:
        timing_label = "confirmed_reset"
    else:
        timing_label = "early"
    return {"prox_pct": round(prox_raw, 2), "td_to_trough": td_to_trough,
            "within_3": within_3, "within_5": within_5,
            "timing_label": timing_label, "mfe21": mfe21, "rc21": rc21}


def _load_triggers(root: Path | None) -> list[dict]:
    p = _base(root) / "triggers.jsonl"
    if not p.exists():
        return []
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(ln))
        except Exception:  # noqa: BLE001
            pass
    return rows


def _book_keys(p: Path) -> set[tuple]:
    if not p.exists():
        return set()
    seen = set()
    for ln in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(ln)
            seen.add((r.get("tf"), r.get("trigger_date"), r.get("instrument")))
        except Exception:  # noqa: BLE001
            pass
    return seen


def _positions(root: Path | None) -> tuple[list[dict], list[dict]]:
    """Replay triggers against store closes → (matured_rows, open_positions).
    Deterministic from stores; idempotency is enforced by the caller via keys."""
    matured, opens = [], []
    triggers = _load_triggers(root)
    if not triggers:
        return matured, opens
    series = {inst: _closes(root, inst) for inst in INSTRUMENTS}
    for tr in triggers:
        try:
            t_date = pd.Timestamp(tr["date"])
        except Exception:  # noqa: BLE001
            continue
        env = {k: tr[k] for k in ("midterm_yr", "policy", "dffr_6m_bp") if k in tr}
        for inst in INSTRUMENTS:
            s = series.get(inst)
            if s is None or s.empty:
                continue
            e = s.index.searchsorted(t_date, side="right")  # next session AFTER trigger bar date
            if e >= len(s):
                continue  # entry not yet printable
            entry_px = float(s.iloc[e])
            entry_date = str(s.index[e].date())
            win = s.iloc[e: e + HORIZON + 1]
            if len(win) >= HORIZON + 1:
                ret21 = round((float(s.iloc[e + 21]) / entry_px - 1) * 100, 1)
                ret63 = round((float(s.iloc[e + HORIZON]) / entry_px - 1) * 100, 1)
                adverse = round((float(win.min()) / entry_px - 1) * 100, 1)
                matured.append({
                    "schema": SCHEMA, "tf": tr.get("tf"), "trigger_date": tr.get("date"),
                    "instrument": inst, "entry_date": entry_date,
                    "ret21": ret21, "ret63": ret63, "adverse63": adverse,
                    "grade": _grade(ret63, adverse),
                    "gauntlet_row": inst == "EW",  # §7: basket rows carry §4; members diagnostic
                    **env,
                    **_timing_scorecard(s, e, entry_px),  # §7 item 4: additive timing ruler
                })
            else:
                mtm = round((float(s.iloc[-1]) / entry_px - 1) * 100, 1)
                worst = round((float(win.min()) / entry_px - 1) * 100, 1)
                opens.append({
                    "tf": tr.get("tf"), "trigger_date": tr.get("date"),
                    "instrument": inst, "entry_date": entry_date,
                    "sessions_held": int(len(win) - 1), "mtm_pct": mtm,
                    "worst_pct": worst,
                })
    return matured, opens


def _stamp_prophet_confluence(root: Path | None, gate: dict) -> int:
    """§7 W1d — stamp gate state onto US-board Mag-7 picks. READ-ONLY wrt
    Prophet: reads the latest snapshots_v2 row, appends sidecar rows, touches
    nothing the board consumes. Dedup (as_of, lane, ticker)."""
    try:
        snap_p = ((root if root is not None else config.data_dir())
                  / "us_board_ledger" / "snapshots_v2.jsonl")
        if not snap_p.exists():
            return 0
        last = None
        for ln in snap_p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                last = ln
        if not last:
            return 0
        snap = json.loads(last)
        as_of = snap.get("as_of")
        side_p = _base(root) / "prophet_confluence.jsonl"
        seen = set()
        if side_p.exists():
            for ln in side_p.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(ln)
                    seen.add((r.get("as_of"), r.get("lane"), r.get("ticker")))
                except Exception:  # noqa: BLE001
                    pass
        wrote = 0
        side_p.parent.mkdir(parents=True, exist_ok=True)
        with side_p.open("a", encoding="utf-8") as f:
            for lane, picks in (snap.get("lanes") or {}).items():
                for p in (picks or []):
                    tkr = p.get("ticker")
                    if tkr not in M7 or (as_of, lane, tkr) in seen:
                        continue
                    f.write(json.dumps({
                        "as_of": as_of, "lane": lane, "ticker": tkr,
                        "mwr_state": gate.get("state"),
                        "mwr_armed": gate.get("armed"),
                        "stoch2w_k": (gate.get("basket") or {}).get("stoch2w_k"),
                        "members_washed": gate.get("members_washed"),
                    }, ensure_ascii=False) + "\n")
                    wrote += 1
        return wrote
    except Exception as e:  # noqa: BLE001 — sidecar never fatal
        log.warning("mag7_washout_shadow: confluence stamp failed (%s)", e)
        return 0


def update(root: Path | None = None, gate: dict | None = None) -> dict | None:
    """Nightly entrypoint (engine/run.py, after mag7_washout.snapshot()).
    Appends matured shadow rows (nightly-gated), rewrites shadow_state.json,
    stamps the Prophet confluence sidecar. Never raises."""
    try:
        base = _base(root)
        matured, opens = _positions(root)
        book_p = base / "shadow_book.jsonl"
        appended = 0
        if nightly_advance_enabled():
            seen = _book_keys(book_p)
            fresh = [r for r in matured
                     if (r["tf"], r["trigger_date"], r["instrument"]) not in seen]
            if fresh:
                base.mkdir(parents=True, exist_ok=True)
                with book_p.open("a", encoding="utf-8") as f:
                    for r in fresh:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                appended = len(fresh)
        # tally the on-disk book (post-append) for the display state
        rows = []
        if book_p.exists():
            for ln in book_p.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(ln))
                except Exception:  # noqa: BLE001
                    pass
        gauntlet = [r for r in rows if r.get("gauntlet_row")]
        state = {
            "schema": SCHEMA,
            "as_of": (gate or {}).get("as_of"),
            "open_positions": opens,
            "book": {
                "rows": len(rows),
                "gauntlet_rows": len(gauntlet),
                "gauntlet_hits": sum(1 for r in gauntlet if r.get("grade") == "HIT"),
                "gauntlet_fails": sum(1 for r in gauntlet if r.get("grade") == "FAIL"),
                "timing": {
                    "called_low": sum(1 for r in gauntlet if r.get("timing_label") == "called_low"),
                    "confirmed_reset": sum(1 for r in gauntlet if r.get("timing_label") == "confirmed_reset"),
                    "early": sum(1 for r in gauntlet if r.get("timing_label") == "early"),
                    "within_5": sum(1 for r in gauntlet if r.get("within_5")),
                },
            },
            "confluence_stamped": _stamp_prophet_confluence(root, gate or {}),
            "note": "shadow tier (MWR §7 W1a/W1d) — measurement only; never gates, "
                    "ranks, or alters any decision; §4 Use-B stays un-ratified",
        }
        base.mkdir(parents=True, exist_ok=True)
        (base / "shadow_state.json").write_text(
            json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        if appended:
            log.info("mag7_washout_shadow: appended %d matured rows", appended)
        return state
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("mag7_washout_shadow update failed (%s)", e)
        return None
