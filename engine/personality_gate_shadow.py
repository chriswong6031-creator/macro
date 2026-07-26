"""PSS-W3 — Prophet tailored-gate shadow (pure accrual, never a gate).

The forward-shadow the personality-timing charter left open (masterplan
research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md §W3; candidate pinned by
ruling R-W1T-2 in research/PERSONALITY_TIMING_TAILORING_HANDOFF_FOR_FABLE.md §8).
Mirrors engine/mag7_washout_shadow.py and engine/prophet_stage_shadow.py: PURE
ACCRUAL + MEASUREMENT — this module NEVER gates, ranks, sizes, or alters any
Prophet, washout, or board decision. Every artifact is display / shadow tier. A
null here NEVER blocks anything, and no gate change ships from this lane: promotion
of any gate change needs its own prereg + ruling (contamination row absolute).

WHAT IT LOGS. For each covered name, nightly, it fires the SAME Stoch-RSI reset
construction two ways and logs where they DISAGREE (both directions is the product):

  uniform gate  — Stoch-RSI(14/14/3/3) cross up from K<20 on the INCUMBENT fixed
                  rung. The incumbent washout / Prophet lane fires on the 2W bar
                  (engine/mag7_washout.py two_week_bars + stoch_rsi; the same 2W
                  Stoch-RSI carrier index_momentum.py runs). UNIFORM_RUNG = "2W".
  tailored gate — the identical Stoch-RSI cross at each NAME'S structure-derived
                  rung (codex column `rung_derived` ∈ {3D, 1W, 2W}, the R-W1T-2
                  pinned S-family-at-derived-rung construction).

Both gates reuse the pinned stoch machinery verbatim — nothing is re-implemented:
scripts.research.ptt_w1_persistence_of_fit.bars_for + tool_dates(bars, "S"), which
themselves call engine.mag7_washout.stoch_rsi / cross_up. The flat-RSI window
(hi==lo → NaN, not a crash) is handled inside that shared stoch_rsi.

Per name we classify the most-recent evaluable bar of each rung:
  fired_uniform_only · fired_tailored_only · both · neither
Disagreements (the *_only classes) are the readout. When the derived rung IS 2W
the two gates are identical by construction (agree_by_construction=True) — logged
but never a "disagreement".

COPY LAW (R-W1T-3): these tools CONFIRM RESETS, they do not call bottoms. Nothing
here says "bottom"; the word "validated" is CI-banned and absent by design.

FORWARD LEDGER (house law). data/personality_timing/gate_shadow.jsonl is an
append-only forward ledger, keyed (as_of, sym); NIGHTLY IS THE SOLE ADVANCER
(engine.ledger_lane.nightly_advance_enabled(), COLLECT_LANE=nightly). A same-day
rerun appends nothing (idempotent on the key). Each fire row stores enough state
(entry_date + a positional entry index into the name's daily close) to grade later
under the DUAL rulers once 63td of forward tape accrues:
  legacy ruler  — fwd63 (forward 63td close return)
  timing ruler  — mae63 / prox / td_to_trough (charter §7 reset-confirmation set)
Grading is DEFERRED (grade_matured, nightly-gated): a fire graded prematurely would
read future prices that do not yet exist, so a not-yet-matured fire stays null and
is re-checked on a later nightly. The quarterly miss-rate readout is a separate
scan over this ledger (first readout ≈ 3 months post-ship).

data/personality_timing/gate_shadow_state.json is the display tally (coverage
census + disagreement counts + timing scorecard shares), rewritten each nightly.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from engine.ledger_lane import nightly_advance_enabled
from lib import config

# Pinned stoch construction — reused verbatim (never re-implemented). bars_for +
# tool_dates(bars, "S") is the S-family (Stoch-RSI<20 cross) firing rule; both call
# engine.mag7_washout.stoch_rsi / cross_up under the hood.
from scripts.research.ptt_w1_persistence_of_fit import bars_for, tool_dates

log = logging.getLogger(__name__)

LEDGER_SCHEMA = "personality_gate_shadow.ledger/v1"
STATE_SCHEMA = "personality_gate_shadow.v1"

# The incumbent uniform gate fires on the 2W Stoch-RSI bar (mag7_washout /
# index_momentum). Pinned — a change is a construction change, not a config knob.
UNIFORM_RUNG = "2W"
VALID_RUNGS = ("3D", "1W", "2W")

HORIZON = 63   # forward days for the legacy ruler (fwd63)
PROX = 31      # ±31td local-trough proximity window (charter §7 timing ruler)


def _base(root: Path | None) -> Path:
    return (root if root is not None else config.data_dir()) / "personality_timing"


def _codex_path(root: Path | None) -> Path:
    return _base(root) / "codex.parquet"


def ledger_path(root: Path | None) -> Path:
    return _base(root) / "gate_shadow.jsonl"


def state_path(root: Path | None) -> Path:
    return _base(root) / "gate_shadow_state.json"


def _closes(root: Path | None, sym: str) -> pd.Series | None:
    """Daily close series for one name from the baskets/ohlcv store (the same
    store the codex is built from). Fail-open per name."""
    try:
        p = (root if root is not None else config.data_dir()) / "baskets" / "ohlcv" / f"{sym}.parquet"
        s = pd.read_parquet(p)["close"].dropna()
        return s if not s.empty else None
    except Exception as e:  # noqa: BLE001 — per-name fail-open
        log.debug("personality_gate_shadow: %s closes unavailable (%s)", sym, e)
        return None


def _load_codex(root: Path | None) -> pd.DataFrame | None:
    """The per-name structure store (sym, as_of, rung_derived). Read as-of its
    build date — nightly evaluates only the newest bar, so the current codex rung
    is the PIT rung for today's fire (no historical rung lookahead)."""
    p = _codex_path(root)
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p, columns=["sym", "as_of", "rung_derived"])
        return df if not df.empty else None
    except Exception as e:  # noqa: BLE001
        log.warning("personality_gate_shadow: codex unreadable (%s)", e)
        return None


def _fires_on_latest_bar(close: pd.Series, rung: str) -> tuple[bool, int | None]:
    """Did the S-family Stoch-RSI cross print on the MOST RECENT bar of `rung`?

    Returns (fired, entry_idx) where entry_idx is the positional index into the
    DAILY close of the fire bar. A fire means: the newest bar of this rung is a
    Stoch-RSI cross-up from K<20 (the pinned reset-confirmation construction). We
    only look at the latest bar because the nightly lane logs today's tape — a fire
    on an older bar was (or will be) logged on the nightly of its own bar-date.

    The rung bar-date is mapped to its daily index via searchsorted (mirroring the
    canonical scripts.research.ptt_w1_timing_regrade.sig_metrics: idx.searchsorted(t),
    default side). A W-FRI label can fall past the last daily close (a Friday-holiday
    or Thursday-anchored week tail) — that bar is NOT reported as a fire (sig_metrics
    skips it identically), so no fire is ever stored with an unresolvable entry."""
    bars = bars_for(close, rung)
    if bars.empty:
        return False, None
    dates = tool_dates(bars, "S")  # bar-dates where the S-cross printed
    if not dates or dates[-1] != bars.index[-1]:
        return False, None
    i = int(close.index.searchsorted(dates[-1]))  # default side (== sig_metrics)
    if i >= len(close):
        return False, None  # W-FRI tail stamped past the last daily close — not a fire
    return True, i


def _classify(uniform: bool, tailored: bool) -> str:
    if uniform and tailored:
        return "both"
    if uniform:
        return "fired_uniform_only"
    if tailored:
        return "fired_tailored_only"
    return "neither"


def _scan(root: Path | None, as_of: str) -> tuple[list[dict], dict]:
    """Evaluate both gates for every covered name on the latest bar. Returns
    (fire_rows, census). Deterministic from the stores; idempotency enforced by the
    caller on the (as_of, sym) key."""
    codex = _load_codex(root)
    census = {
        "codex_names": 0, "covered": 0, "no_prices": 0, "bad_rung": 0,
        "rung_distribution": {}, "classes": {
            "both": 0, "fired_uniform_only": 0, "fired_tailored_only": 0, "neither": 0},
        "disagreements": 0, "agree_by_construction": 0,
    }
    fires: list[dict] = []
    if codex is None:
        return fires, census

    census["codex_names"] = int(codex["sym"].nunique())
    for _, r in codex.iterrows():
        sym = str(r["sym"])
        rung = str(r["rung_derived"])
        codex_asof = str(r["as_of"])
        if rung not in VALID_RUNGS:
            census["bad_rung"] += 1
            continue
        close = _closes(root, sym)
        if close is None:
            census["no_prices"] += 1
            continue
        census["covered"] += 1
        census["rung_distribution"][rung] = census["rung_distribution"].get(rung, 0) + 1

        try:
            uni_fired, uni_e = _fires_on_latest_bar(close, UNIFORM_RUNG)
            tai_fired, tai_e = _fires_on_latest_bar(close, rung)
        except Exception as e:  # noqa: BLE001 — per-name fail-open
            log.debug("personality_gate_shadow: %s eval failed (%s)", sym, e)
            census["covered"] -= 1
            census["rung_distribution"][rung] -= 1
            census["no_prices"] += 1
            continue

        cls = _classify(uni_fired, tai_fired)
        census["classes"][cls] += 1
        by_construction = rung == UNIFORM_RUNG
        if by_construction and (uni_fired or tai_fired):
            census["agree_by_construction"] += 1
        if cls in ("fired_uniform_only", "fired_tailored_only"):
            census["disagreements"] += 1

        # Only fires (either gate) become ledger rows — 'neither' is the silent
        # majority and is counted in the census, never stored.
        if not (uni_fired or tai_fired):
            continue

        # Frozen entry state per FIRED rung, so a later nightly grades the exact
        # same entry. A fire on the uniform bar and a fire on the tailored bar can
        # have different bar-dates (different rungs), so each carries its own entry.
        row: dict = {
            "schema": LEDGER_SCHEMA,
            "as_of": as_of,
            "sym": sym,
            "codex_asof": codex_asof,
            "uniform_rung": UNIFORM_RUNG,
            "tailored_rung": rung,
            "agree_by_construction": by_construction,
            "fired_uniform": bool(uni_fired),
            "fired_tailored": bool(tai_fired),
            "disagreement_class": cls,
            # entry state for deferred DUAL-ruler grading (null until matured)
            "uniform_entry": _entry_row(close, uni_e) if uni_fired else None,
            "tailored_entry": _entry_row(close, tai_e) if tai_fired else None,
            # grade fields — nightly-advanced at maturity; null until 63td accrues
            "graded": False,
            "graded_asof": None,
            "uniform_grade": None,
            "tailored_grade": None,
            "note": "reset-confirmer shadow — logs uniform/tailored gate "
                    "disagreements; never gates/ranks/alters any decision",
        }
        fires.append(row)

    return fires, census


def _entry_row(close: pd.Series, e: int | None) -> dict | None:
    """Frozen entry state at daily positional index `e` (the resolved fire bar).
    `e` is guaranteed in-bounds by _fires_on_latest_bar (an unresolvable W-FRI-tail
    fire is never reported), so no null-entry fire is ever stored."""
    if e is None:
        return None
    return {
        "entry_date": str(close.index[e].date()),
        "entry_idx": int(e),
        "entry_px": round(float(close.iloc[e]), 4),
    }


# --------------------------------------------------------------------------- #
# Deferred DUAL-ruler grading (nightly-gated; frozen-until-matured).          #
# --------------------------------------------------------------------------- #
def _grade_entry(close: pd.Series, entry: dict) -> dict | None:
    """Grade one frozen entry under BOTH rulers, once 63td of forward tape exists.

    legacy ruler — fwd63 = forward 63td close return (%).
    timing ruler — mae63 (shallowest adverse excursion after entry, ≤0),
                   prox (entry premium over the ±31td local trough, ≥0),
                   td_to_trough (signed offset of the trough from entry; negative =
                   trough already in = a CONFIRMED RESET), timing_label.
    Returns None while unmatured (nulls printed, not fabricated). Reuses the same
    arithmetic as mag7_washout_shadow._timing_scorecard (closes only; first-hit
    argmin; PROX=31).

    The entry is re-resolved from the stable `entry_date` on the CURRENT close (not
    the raw frozen positional index) so a store back-fill or re-base cannot silently
    shift the entry; entry_idx is only the fallback if the date is absent."""
    try:
        pos = int(close.index.searchsorted(pd.Timestamp(entry["entry_date"])))
    except Exception:  # noqa: BLE001
        pos = None
    if pos is not None and pos < len(close) and \
            str(close.index[pos].date()) == entry["entry_date"]:
        e = pos
    else:
        e = int(entry["entry_idx"])  # fallback: append-only store keeps positions
    if e >= len(close):
        return None
    entry_px = float(entry["entry_px"])
    if e + HORIZON >= len(close):
        return None  # not yet matured — re-checked on a later nightly
    fwd63 = round((float(close.iloc[e + HORIZON]) / entry_px - 1) * 100, 2)
    win = close.iloc[e: e + HORIZON + 1]
    mae63 = round((float(win.min()) / entry_px - 1) * 100, 2)  # ≤0
    out = {"fwd63": fwd63, "mae63": mae63,
           "prox": None, "td_to_trough": None, "timing_label": None}
    if e >= PROX:
        w = close.iloc[e - PROX: e + PROX + 1].to_numpy(dtype=float)
        lo = float(w.min())
        out["prox"] = round((entry_px / lo - 1) * 100, 2)  # ≥0 (window includes e)
        tdt = int(np.argmin(w)) - PROX  # negative = trough BEFORE entry
        out["td_to_trough"] = tdt
        if -2 <= tdt <= 5:
            out["timing_label"] = "called_low"
        elif tdt < -2:
            out["timing_label"] = "confirmed_reset"
        else:
            out["timing_label"] = "early"
    return out


def _grade_one(root: Path | None, row: dict) -> bool:
    """Advance grades for one fire row in place. Only writes a grade once its
    horizon has elapsed AND forward prices exist. Returns True if anything changed."""
    if row.get("graded"):
        return False
    close = _closes(root, str(row.get("sym")))
    if close is None:
        return False
    changed = False
    for side in ("uniform", "tailored"):
        if row.get(f"{side}_grade") is not None:
            continue
        entry = row.get(f"{side}_entry")
        if not entry:
            continue
        g = _grade_entry(close, entry)
        if g is not None:
            row[f"{side}_grade"] = g
            changed = True
    if changed:
        # a fire is "graded" once every FIRED side that can grade has graded
        pending = [
            side for side in ("uniform", "tailored")
            if row.get(f"{side}_entry") and row.get(f"{side}_grade") is None
        ]
        row["graded"] = not pending
    return changed


# --------------------------------------------------------------------------- #
# Ledger I/O — append-only fires; keyed (as_of, sym); atomic rewrite on grade. #
# --------------------------------------------------------------------------- #
def _load_ledger(root: Path | None) -> list[dict]:
    p = ledger_path(root)
    if not p.exists():
        return []
    rows = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:  # noqa: BLE001
            pass
    return rows


def _ledger_keys(rows: list[dict]) -> set[tuple]:
    return {(r.get("as_of"), r.get("sym")) for r in rows}


def _rewrite_ledger(root: Path | None, rows: list[dict]) -> None:
    """Atomic full rewrite (temp + os.replace) — used only when grades advance."""
    base = _base(root)
    base.mkdir(parents=True, exist_ok=True)
    p = ledger_path(root)
    header = (
        "# personality_gate_shadow forward ledger — schema " + LEDGER_SCHEMA + "\n"
        "# One row per FIRED (as_of, sym): uniform vs tailored Stoch-RSI reset gate\n"
        "# + frozen entry state; DUAL-ruler grades (nightly-advanced at 63td maturity).\n"
        "# Reset-confirmer shadow — NEVER gates/ranks/alters any decision.\n"
    )
    body = "\n".join(json.dumps(r, ensure_ascii=False, default=str) for r in rows)
    text = header + (body + "\n" if body else "")
    fd, tmp = tempfile.mkstemp(dir=str(base), prefix=".gate_shadow.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _append_fires(root: Path | None, fresh: list[dict]) -> None:
    base = _base(root)
    base.mkdir(parents=True, exist_ok=True)
    p = ledger_path(root)
    write_header = not p.exists()
    with p.open("a", encoding="utf-8") as f:
        if write_header:
            f.write(
                "# personality_gate_shadow forward ledger — schema " + LEDGER_SCHEMA + "\n"
                "# One row per FIRED (as_of, sym): uniform vs tailored Stoch-RSI reset gate\n"
                "# + frozen entry state; DUAL-ruler grades (nightly-advanced at 63td maturity).\n"
                "# Reset-confirmer shadow — NEVER gates/ranks/alters any decision.\n")
        for r in fresh:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def _timing_shares(rows: list[dict]) -> dict:
    """Display tally of graded timing labels per gate side (nulls printed)."""
    out: dict = {}
    for side in ("uniform", "tailored"):
        graded = [r.get(f"{side}_grade") for r in rows if r.get(f"{side}_grade")]
        labels = [g.get("timing_label") for g in graded if g and g.get("timing_label")]
        n = len(labels)
        out[side] = {
            "n_graded": len(graded),
            "n_timing_labeled": n,
            "confirmed_reset": labels.count("confirmed_reset"),
            "called_low": labels.count("called_low"),
            "early": labels.count("early"),
            "median_fwd63": (round(float(pd.Series(
                [g["fwd63"] for g in graded if g and g.get("fwd63") is not None]).median()), 2)
                if any(g and g.get("fwd63") is not None for g in graded) else None),
        }
    return out


def update(root: Path | None = None, *, as_of: str | None = None) -> dict | None:
    """Nightly entrypoint (engine/run.py, after mag7_washout_shadow.update()).

    1. Scans both gates over every covered name on the latest bar; appends FRESH
       fire rows (nightly-gated, idempotent on (as_of, sym)).
    2. Advances DUAL-ruler grades for matured fires (nightly-gated, frozen-until-
       matured, idempotent).
    3. Rewrites gate_shadow_state.json — the coverage census + disagreement counts
       + timing scorecard (display tier; nulls printed). Never raises."""
    try:
        as_of = as_of or pd.Timestamp.now("UTC").date().isoformat()
        gate_open = nightly_advance_enabled()

        fires, census = _scan(root, as_of)

        appended = 0
        existing = _load_ledger(root)
        if gate_open and fires:
            seen = _ledger_keys(existing)
            fresh = [r for r in fires if (r["as_of"], r["sym"]) not in seen]
            if fresh:
                _append_fires(root, fresh)
                existing.extend(fresh)
                appended = len(fresh)

        advanced = 0
        if gate_open and existing:
            for r in existing:
                try:
                    if _grade_one(root, r):
                        r["graded_asof"] = as_of
                        advanced += 1
                except Exception as e:  # noqa: BLE001 — per-row fail-open
                    log.debug("personality_gate_shadow: grade %s failed (%s)",
                              r.get("sym"), e)
            if advanced:
                _rewrite_ledger(root, existing)

        n_graded = sum(1 for r in existing if r.get("graded"))
        state = {
            "schema": STATE_SCHEMA,
            "is_context_only": True,
            "display_only": True,
            "authority_tier": "display",
            "as_of": as_of,
            "generated_utc": pd.Timestamp.now("UTC").isoformat(),
            "spec": "research/PERSONALITY_SIGNAL_SUITE_MASTERPLAN_BY_FABLE.md §W3",
            "gate_open": gate_open,
            "uniform_rung": UNIFORM_RUNG,
            "coverage_census": census,
            "ledger": {
                "fire_rows": len(existing),
                "appended_today": appended,
                "graded": n_graded,
                "grades_advanced_today": advanced,
            },
            "timing": _timing_shares(existing),
            "note": (
                "PSS-W3 reset-confirmer shadow (masterplan §W3, ruling R-W1T-2). "
                "Logs uniform-gate (2W Stoch-RSI) vs tailored-gate (Stoch-RSI at the "
                "codex structure-derived rung) disagreements both directions; graded "
                "later under dual rulers (fwd63 + timing). Display/shadow tier only: "
                "it NEVER gates, ranks, sizes, or alters any Prophet, washout, or board "
                "decision. Promotion of any gate change needs its own prereg + ruling. "
                "First quarterly miss-rate readout ≈ 3 months post-ship."
            ),
        }
        base = _base(root)
        base.mkdir(parents=True, exist_ok=True)
        p = state_path(root)
        fd, tmp = tempfile.mkstemp(dir=str(base), prefix=".gate_shadow_state.", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=1, default=str)
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
        if appended or advanced:
            log.info("personality_gate_shadow: +%d fires, +%d grades advanced",
                     appended, advanced)
        return state
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("personality_gate_shadow update failed (%s)", e)
        return None
