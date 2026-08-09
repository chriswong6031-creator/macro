"""Two-year replay of the LEADER-PULLBACK organ (`engine/us_leader_pullback.py`).

MEASUREMENT ONLY. Writes two files into this directory and nothing else — no `site/`,
no `data/`, no engine, board, ranker, grader or ledger touched:

    LEADER_PULLBACK_REPLAY_2026-08-08.json
    LEADER_PULLBACK_REPLAY_2026-08-08.md

WHAT IS MEASURED
----------------
Every RESET_TURN fire over the last `EVAL_SESSIONS` sessions on the full `data/yahoo`
universe with at least `MIN_BARS` bars:

  n                       fires, and the episode/name concentration behind them
  precision               P(forward-10-session excess vs SPY >= +5pp)
  loser rate              P(forward-10-session excess vs SPY <= -3pp)
  entry-vs-low            median (entry / min close over [T, T+20] - 1) — THE lateness
                          number this lane exists to minimize. Reported for the fire-day
                          CLOSE (what an EOD signal actually pays) and for the zone floor
                          (`reset_low` — what the zone machinery is trying to deliver).
  forward path            median excess at h = 1, 2, 3, 5, 10, 20

Pooled AND per-name-first (each name's FIRST fire only, so a handful of names cannot carry
the table). Two controls, because a precision number with no denominator says nothing:
the whole-universe base rate and the LEADER-STATE base rate over the same sessions — the
second is the one that matters, since it asks whether the RESET_TURN adds anything over
simply being a high-RS leader that day. Half-split sign check on both halves of the window.

DEFINITIONS AND THEIR LIMITS (stated, not buried)
-------------------------------------------------
* CLOSE BASIS. `data/yahoo` carries close and volume, no intraday high/low, so every
  high, low, drawdown and reset level here is close-basis. An intraday restatement is a
  different measurement.
* ENTRY = the fire day's CLOSE. The EOD cadence floor (§6.9 item 4) means a signal at
  close T is actionable T+1; the close-T entry is therefore the OPTIMISTIC end of what an
  EOD lane can pay, and the zone-floor column is the honest target, not a fill.
* FORWARD LOW WINDOW = [T, T+20] inclusive of the fire day, so a fire ON the low reads
  exactly 0.0% and the statistic can never go negative.
* EXCESS = name return minus SPY return over the same window. Both legs come from
  `data/yahoo`, which is the ADJUSTED family (`price_adjustment_audit` §1), so the two
  legs share one adjustment basis.
* SURVIVORSHIP. `data/yahoo` is a CURRENT-universe store: names that delisted inside the
  window are largely absent. A two-year forward-return study on it is survivorship-biased
  upward, and nothing here corrects that. The controls are computed on the same biased
  universe, which is why the LEADER-state base rate — not the absolute precision — is the
  number to read.
* RIGHT CENSORING. Fires inside the last 20 sessions have no complete forward window.
  They are COUNTED as fires and EXCLUDED from forward statistics, and both counts print.

CASE RECEIPTS
-------------
NVDA, AVGO and ADAM over the operator's late-July 2026 window. If a case does not fire
under the v0 constants, the failing leg is printed by name and date. Constants are NOT
tuned to capture them (`DNR:KILL-OUTCOME-AUDITION`); §6.6 revision is the only route.

Runtime: ~2 minutes on the Mac Studio, deterministic (no sampling, no randomness).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
os.chdir(REPO)
sys.path.insert(0, REPO)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine import us_leader_pullback as lp  # noqa: E402
from price_ladder import resolve_close  # noqa: E402

STAMP = "2026-08-08"
HERE = Path(__file__).resolve().parent
OUT_JSON = HERE / f"LEADER_PULLBACK_REPLAY_{STAMP}.json"
OUT_MD = HERE / f"LEADER_PULLBACK_REPLAY_{STAMP}.md"

EVAL_SESSIONS = 504          # 2 years of sessions
MIN_BARS = 260               # the house US research history floor
H_PRECISION = 10             # forward horizon for precision / loser rate
LOW_WINDOW = 20              # forward sessions for the entry-vs-low statistic
PRECISION_EXCESS = 0.05      # +5pp excess vs SPY
LOSER_EXCESS = -0.03         # -3pp excess vs SPY
PATH_HORIZONS = (1, 2, 3, 5, 10, 20)
THIN_N = 20                  # cells below this are labelled thin, never quietly averaged
BENCH = "SPY"

CASES = (
    {"ticker": "NVDA", "receipt_date": "2026-07-29", "note": "operator receipt: Jul-29 reset -> Aug run"},
    {"ticker": "AVGO", "receipt_date": "2026-07-29", "note": "operator receipt: same window as NVDA"},
    {"ticker": "ADAM", "receipt_date": "2026-07-27", "note": "operator receipt: Jul-27 reset (masterplan §6.8b)"},
)
CASE_WINDOW = ("2026-07-15", "2026-08-07")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def _yahoo_universe() -> tuple[pd.DataFrame, dict[str, pd.Series], dict]:
    """Wide close frame + per-name volume from data/yahoo, on the SPY session calendar."""
    files = sorted(
        f for f in os.listdir("data/yahoo")
        if f.endswith(".parquet") and not f.startswith("_")
    )
    bench = pd.read_parquet(f"data/yahoo/{BENCH}.parquet")["close"]
    bench.index = pd.to_datetime(bench.index)
    bench = bench.sort_index()
    bench = bench[~bench.index.duplicated(keep="last")]

    closes: dict[str, pd.Series] = {}
    vols: dict[str, pd.Series] = {}
    skipped_short = 0
    no_volume: list[str] = []
    for fn in files:
        t = fn[:-8]
        try:
            d = pd.read_parquet(f"data/yahoo/{fn}")
        except (OSError, ValueError, ImportError):
            continue
        if "close" not in d.columns:
            continue
        d.index = pd.to_datetime(d.index)
        d = d.sort_index()
        d = d[~d.index.duplicated(keep="last")]
        c = pd.to_numeric(d["close"], errors="coerce").dropna()
        if len(c) < MIN_BARS:
            skipped_short += 1
            continue
        closes[t] = c
        if "volume" in d.columns:
            v = pd.to_numeric(d["volume"], errors="coerce")
            if v.fillna(0).sum() > 0:
                vols[t] = v
            else:
                no_volume.append(t)
        else:
            no_volume.append(t)

    px = pd.DataFrame(closes)
    px = px.reindex(bench.index.union(px.index)).loc[bench.index.min():]
    px = px.loc[px.index.isin(bench.index)]
    prov = {
        "store": "data/yahoo",
        "adjustment_basis": "ADJUSTED (price_adjustment_audit §1) — name and benchmark legs share it",
        "files_seen": len(files),
        "names_kept": int(px.shape[1]),
        "names_dropped_short_history": int(skipped_short),
        "names_without_usable_volume": sorted(no_volume),
        "benchmark": BENCH,
        "session_calendar": f"{BENCH} sessions",
    }
    return px, vols, prov


def _forward_frames(px: pd.DataFrame, bench: pd.Series) -> dict:
    """Forward excess-vs-benchmark frames and the forward-low frame, all PIT-safe."""
    b = bench.reindex(px.index).ffill()
    out = {}
    for h in PATH_HORIZONS:
        name_fwd = px.shift(-h) / px - 1.0
        bench_fwd = b.shift(-h) / b - 1.0
        out[h] = name_fwd.sub(bench_fwd, axis=0)
    # min close over [T, T+LOW_WINDOW] — reverse-rolling so min_periods marks censoring
    rev = px.iloc[::-1]
    out["low_fwd"] = rev.rolling(LOW_WINDOW + 1, min_periods=LOW_WINDOW + 1).min().iloc[::-1]
    return out


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _pct(x) -> float | None:
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x) * 100, 2)


def _rate_block(ev: pd.DataFrame, label: str) -> dict:
    """Precision / loser / entry-vs-low / forward path for one event set."""
    graded = ev[ev[f"ex{H_PRECISION}"].notna()]
    lowset = ev[ev["entry_vs_low"].notna()]
    n = int(len(ev))
    ng = int(len(graded))
    block = {
        "label": label,
        "n_events": n,
        "n_names": int(ev["ticker"].nunique()) if n else 0,
        "n_graded_h10": ng,
        "n_right_censored_h10": int(n - ng),
        "n_with_low_window": int(len(lowset)),
        "thin": bool(ng < THIN_N),
        "precision_pct": _pct((graded[f"ex{H_PRECISION}"] >= PRECISION_EXCESS).mean()) if ng else None,
        "loser_pct": _pct((graded[f"ex{H_PRECISION}"] <= LOSER_EXCESS).mean()) if ng else None,
        "median_entry_vs_low_pct": _pct(lowset["entry_vs_low"].median()) if len(lowset) else None,
        "median_zone_floor_vs_low_pct": _pct(lowset["zone_vs_low"].median()) if len(lowset) else None,
        "p75_entry_vs_low_pct": _pct(lowset["entry_vs_low"].quantile(0.75)) if len(lowset) else None,
        "median_forward_path_pct": {},
    }
    for h in PATH_HORIZONS:
        col = ev[f"ex{h}"].dropna()
        block["median_forward_path_pct"][f"h{h}"] = (
            {"median": _pct(col.median()), "n": int(len(col)),
             "thin": bool(len(col) < THIN_N)} if len(col) else
            {"median": None, "n": 0, "thin": True}
        )
    return block


def _episode_diagnostics(win: pd.DataFrame) -> list[dict]:
    """Walk one name's episodes in the eval window and record why each ended where it did.

    An episode is a contiguous run of PULLBACK / RESET_TURN / RESUMED rows; the row AFTER
    the run carries `episode_end_reason`. The two shapes the operator receipts exposed are
    counted here at population scale, so they stop being anecdotes:

      `cross_on_the_exit_bar`      — the %K/%D cross printed on the very session the
                                     episode was closed (the AVGO shape: the recovery exit
                                     is evaluated before the transition, so a V-shaped
                                     reset lands one bar outside the episode).
      `turn_legs_on_the_exit_bar`  — stricter: BOTH turn legs printed on that exit bar, so
                                     a transition-before-exit ordering alone would have
                                     fired it.
      `legs_never_coincided`       — inside the episode the %K cross printed on some bars
                                     and the rising histogram on others, but never on the
                                     same bar (the ADAM shape: the cost of AND-ing two
                                     turn legs on a daily grid).
    """
    active = win["state"].isin([lp.STATE_PULLBACK, lp.STATE_RESET_TURN, lp.STATE_RESUMED])
    a = active.to_numpy()
    out = []
    i, n = 0, len(a)
    while i < n:
        if not a[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and a[j + 1]:
            j += 1
        seg = win.iloc[i:j + 1]
        exit_row = win.iloc[j + 1] if j + 1 < n else None
        pb = seg[seg["state"] == lp.STATE_PULLBACK]
        turn = seg[seg["state"] == lp.STATE_RESET_TURN]
        fired = bool(len(turn) > 0)
        rec = {
            "fired": fired,
            # A run can begin already IN RESET_TURN when the eval window cuts an episode in
            # half; only a first-day RESET_TURN row is a fire counted in the headline.
            "fired_first_day_in_window": bool(fired and (turn["days_in_state"] == 1).any()),
            "reached_dip": bool(seg["leg_k_dip"].fillna(False).astype(bool).any()),
            "cross_days_in_pullback": int(pb["leg_k_cross"].fillna(False).astype(bool).sum()),
            "rise_days_in_pullback": int(pb["leg_hist_rising"].fillna(False).astype(bool).sum()),
            "end_reason": (None if exit_row is None or pd.isna(exit_row["episode_end_reason"])
                           else str(exit_row["episode_end_reason"])),
            "cross_on_the_exit_bar": bool(
                exit_row is not None and not fired and bool(exit_row["leg_k_cross"])),
            "turn_legs_on_the_exit_bar": bool(
                exit_row is not None and not fired
                and bool(exit_row["leg_k_cross"]) and bool(exit_row["leg_hist_rising"])),
        }
        rec["legs_never_coincided"] = bool(
            not fired and rec["cross_days_in_pullback"] > 0 and rec["rise_days_in_pullback"] > 0)
        out.append(rec)
        i = j + 1
    return out


def _base_rate(excess10: pd.DataFrame, mask: pd.DataFrame | None, label: str) -> dict:
    """Control denominator over the same sessions (optionally state-masked)."""
    e = excess10 if mask is None else excess10.where(mask)
    flat = e.to_numpy().ravel()
    flat = flat[np.isfinite(flat)]
    n = int(flat.size)
    return {
        "label": label,
        "n_name_days": n,
        "thin": bool(n < THIN_N),
        "precision_pct": _pct((flat >= PRECISION_EXCESS).mean()) if n else None,
        "loser_pct": _pct((flat <= LOSER_EXCESS).mean()) if n else None,
        "median_excess_pct": _pct(float(np.median(flat))) if n else None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    t_start = time.time()
    print("::group::leader-pullback replay", flush=True)
    px, vols, prov = _yahoo_universe()
    bench = px[BENCH] if BENCH in px.columns else None
    if bench is None:
        raise SystemExit(f"benchmark {BENCH} missing from the universe frame")
    print(f"universe: {px.shape[1]} names x {px.shape[0]} sessions "
          f"({px.index.min().date()} .. {px.index.max().date()})", flush=True)

    rs = lp.rs_excess_percentile(px, bench)
    fwd = _forward_frames(px, bench)
    ex10 = fwd[H_PRECISION]

    di = px.index
    n_sessions = len(di)
    eval_lo = max(0, n_sessions - EVAL_SESSIONS)
    eval_start, eval_end = di[eval_lo], di[-1]
    half = eval_lo + (n_sessions - eval_lo) // 2
    half_date = di[half]

    fires: list[dict] = []
    episodes: list[dict] = []
    leader_mask = pd.DataFrame(False, index=di, columns=px.columns)
    state_counts: dict[str, int] = {}
    n_eval = 0

    for t in px.columns:
        if t == BENCH:
            continue
        c = px[t].dropna()
        if len(c) < MIN_BARS:
            continue
        frame = lp.evaluate(c, rs_pct=rs[t], volume=vols.get(t))
        if frame.empty:
            continue
        win = frame.loc[frame.index >= eval_start]
        if win.empty:
            continue
        n_eval += 1
        vc = win["state"].value_counts(dropna=True)
        for k, v in vc.items():
            state_counts[str(k)] = state_counts.get(str(k), 0) + int(v)
        # leader-state control: any day the name qualified as a leader (episode or not)
        lead_days = win.index[win["state"].isin(
            [lp.STATE_LEADER, lp.STATE_PULLBACK, lp.STATE_RESET_TURN, lp.STATE_RESUMED])]
        if len(lead_days):
            leader_mask.loc[lead_days, t] = True
        episodes.extend(_episode_diagnostics(win))

        fire_rows = win[(win["state"] == lp.STATE_RESET_TURN) & (win["days_in_state"] == 1)]
        for d, row in fire_rows.iterrows():
            entry = float(px.at[d, t])
            low = fwd["low_fwd"].at[d, t]
            # Rounded on the way in: this list is the committed EVENT LEDGER a chained
            # session re-measures from, and 15 significant figures of float noise would
            # quadruple the artifact for precision no statistic here can use.
            rec = {
                "ticker": t,
                "date": str(d.date()),
                "half": "H1" if d < half_date else "H2",
                "entry_close": round(entry, 4),
                "reset_low": round(float(row["reset_low"]), 4),
                "zone_low": round(float(row["zone_low"]), 4) if pd.notna(row["zone_low"]) else None,
                "zone_high": round(float(row["zone_high"]), 4) if pd.notna(row["zone_high"]) else None,
                "pullback_depth_pct": _pct(row["pullback_depth"]),
                "pullback_age": int(row["pullback_age"]),
                "rs_pct": round(float(row["rs_pct"]), 4),
                "avwap": round(float(row["avwap"]), 4) if pd.notna(row["avwap"]) else None,
                "entry_vs_low": (round(entry / float(low) - 1.0, 6)
                                 if pd.notna(low) and low > 0 else None),
                "zone_vs_low": (round(float(row["reset_low"]) / float(low) - 1.0, 6)
                                if pd.notna(low) and low > 0 else None),
            }
            for h in PATH_HORIZONS:
                v = fwd[h].at[d, t]
                rec[f"ex{h}"] = round(float(v), 6) if pd.notna(v) else None
            fires.append(rec)

    ev = pd.DataFrame(fires)
    print(f"evaluated {n_eval} names; RESET_TURN fires in window: {len(ev)}", flush=True)

    eval_slice = slice(eval_start, eval_end)
    ex10_win = ex10.loc[eval_slice].drop(columns=[BENCH], errors="ignore")
    lead_win = leader_mask.loc[eval_slice].drop(columns=[BENCH], errors="ignore")

    results: dict = {
        "schema": "leader_pullback_replay.v0",
        "stamp": STAMP,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "organ": {"module": "engine/us_leader_pullback.py", "schema": lp.SCHEMA,
                  "construction_era": lp.CONSTRUCTION_ERA, "constants": lp.CONSTANTS,
                  "authority": lp.AUTHORITY},
        "measurement": {
            "eval_sessions": EVAL_SESSIONS,
            "eval_window": [str(eval_start.date()), str(eval_end.date())],
            "half_split_boundary": str(half_date.date()),
            "precision_rule": f"forward-{H_PRECISION}-session excess vs {BENCH} >= "
                              f"{PRECISION_EXCESS * 100:.0f}pp",
            "loser_rule": f"forward-{H_PRECISION}-session excess vs {BENCH} <= "
                          f"{LOSER_EXCESS * 100:.0f}pp",
            "entry_definition": "fire-day CLOSE (EOD cadence: knowable at close T, "
                                "actionable T+1 — this is the optimistic end)",
            "low_window": f"min close over [T, T+{LOW_WINDOW}] inclusive of the fire day",
            "thin_cell_n": THIN_N,
        },
        "universe": prov,
        "state_day_counts": dict(sorted(state_counts.items())),
    }

    results["headline"] = {
        "pooled": _rate_block(ev, "pooled (every RESET_TURN fire)"),
        "per_name_first": _rate_block(
            ev.sort_values("date").groupby("ticker", as_index=False).first()
            if len(ev) else ev, "per-name-first (each name's first fire only)"),
    }
    # A control must not contain the treatment: strip the fire days out of the leader mask.
    fire_mask = pd.DataFrame(False, index=lead_win.index, columns=lead_win.columns)
    for f in fires:
        d = pd.Timestamp(f["date"])
        if d in fire_mask.index and f["ticker"] in fire_mask.columns:
            fire_mask.at[d, f["ticker"]] = True
    results["controls"] = {
        "universe_base_rate": _base_rate(ex10_win, None, "whole universe, same sessions"),
        "leader_state_base_rate": _base_rate(
            ex10_win, lead_win & ~fire_mask,
            "LEADER-qualified name-days (fire days removed), same sessions"),
    }
    results["half_split"] = {}
    for h in ("H1", "H2"):
        sub = ev[ev["half"] == h] if len(ev) else ev
        results["half_split"][h] = _rate_block(sub, f"{h} fires")
    if len(ev):
        p1 = results["half_split"]["H1"]["precision_pct"]
        p2 = results["half_split"]["H2"]["precision_pct"]
        base = results["controls"]["leader_state_base_rate"]["precision_pct"]
        if None not in (p1, p2, base):
            results["half_split"]["sign_stable_vs_leader_base"] = bool(
                np.sign(p1 - base) == np.sign(p2 - base))
        else:
            results["half_split"]["sign_stable_vs_leader_base"] = None
    else:
        results["half_split"]["sign_stable_vs_leader_base"] = None

    epi = pd.DataFrame(episodes)
    n_epi = int(len(epi))
    dipped_no_fire = epi[(~epi["fired"]) & (epi["reached_dip"])] if n_epi else epi
    results["episode_anatomy"] = {
        "n_episodes": n_epi,
        "n_containing_a_reset_turn": int(epi["fired"].sum()) if n_epi else 0,
        "n_fired_first_day_in_window": int(epi["fired_first_day_in_window"].sum()) if n_epi else 0,
        "n_reached_stoch_reset": int(epi["reached_dip"].sum()) if n_epi else 0,
        "n_reset_but_never_turned": int(len(dipped_no_fire)),
        "n_cross_on_the_exit_bar": int(epi["cross_on_the_exit_bar"].sum()) if n_epi else 0,
        "n_turn_legs_on_the_exit_bar": int(epi["turn_legs_on_the_exit_bar"].sum()) if n_epi else 0,
        "n_legs_never_coincided": int(epi["legs_never_coincided"].sum()) if n_epi else 0,
        # UNION, not a sum: the two shapes overlap (an episode can both hold a cross on its
        # exit bar and have seen the legs apart inside it). Summing them double-counts.
        "n_lost_to_leg_placement": int(
            (epi["cross_on_the_exit_bar"] | epi["legs_never_coincided"]).sum()) if n_epi else 0,
        "end_reasons": (epi["end_reason"].fillna("still_open_at_window_end")
                        .value_counts().to_dict() if n_epi else {}),
        "note": "`n_containing_a_reset_turn` exceeds the headline fire count by the "
                "episodes that were already in RESET_TURN on the window's first session; "
                "only a first-day RESET_TURN row is counted as a fire.",
    }

    # The store is not an equity universe: it also carries FX crosses and fund proxies.
    # Counted rather than assumed away, so the contamination is a number, not a worry.
    novol = set(prov["names_without_usable_volume"])
    results["universe_composition"] = {
        "note": "data/yahoo is the raw price store, not a curated equity universe — FX "
                "crosses (`*_X`) and fund/ETF proxies sit beside single names. Filtering "
                "to an equity universe is a v1 candidate; here it is measured instead.",
        "fx_suffixed_names_in_universe": int(sum(1 for t in px.columns if t.endswith("_X"))),
        "fires_from_fx_suffixed_names": int(sum(1 for f in fires if f["ticker"].endswith("_X"))),
        "fires_from_names_without_volume": int(sum(1 for f in fires if f["ticker"] in novol)),
    }

    results["concentration"] = (
        {"fires_per_name_max": int(ev["ticker"].value_counts().max()),
         "fires_per_name_median": float(ev["ticker"].value_counts().median()),
         "top_names": ev["ticker"].value_counts().head(8).to_dict()}
        if len(ev) else {"fires_per_name_max": 0, "fires_per_name_median": None, "top_names": {}}
    )
    results["fires"] = fires

    results["case_receipts"] = _case_receipts(px, rs, vols, fwd)

    results["runtime_seconds"] = round(time.time() - t_start, 1)
    OUT_JSON.write_text(json.dumps(results, indent=2, default=str) + "\n")
    OUT_MD.write_text(_render_md(results))
    print(f"wrote {OUT_JSON.name} and {OUT_MD.name} in "
          f"{results['runtime_seconds']}s", flush=True)
    print("::endgroup::", flush=True)


def _case_receipts(px: pd.DataFrame, rs: pd.DataFrame, vols: dict, fwd: dict) -> list[dict]:
    """Fire-or-miss receipt per operator case, with the failing leg named on a miss."""
    out = []
    lo, hi = pd.Timestamp(CASE_WINDOW[0]), pd.Timestamp(CASE_WINDOW[1])
    bench = px[BENCH]
    for case in CASES:
        t = case["ticker"]
        rec = dict(case)
        if t in px.columns:
            c = px[t].dropna()
            rs_series = rs[t]
            vol = vols.get(t)
            rec["price_source"] = "data/yahoo"
            rec["adjusted"] = True
            rec["rs_basis"] = "in the replay cross-section"
        else:
            # Off-universe case: resolve through the disclosed adjusted-first ladder.
            r = resolve_close(t, asof=str(px.index[-1].date()))
            if not r.ok:
                rec.update({"fired": None, "null_reason": r.reason or "no price series",
                            "price_source": r.price_source, "tried": r.tried})
                out.append(rec)
                continue
            c = r.series.reindex(px.index).dropna()
            rec["price_source"] = r.price_source
            rec["adjusted"] = bool(r.adjusted) if r.adjusted is not None else None
            rec["source_deviation"] = (
                f"{t} is absent from data/yahoo; resolved via the price_ladder rung "
                f"'{r.price_source}'. That rung is "
                f"{'ADJUSTED' if r.adjusted else 'UNADJUSTED'}, so its excess-vs-SPY legs "
                f"{'share' if r.adjusted else 'do NOT share'} one adjustment basis. "
                f"It is also outside the replay cross-section, so its RS percentile is "
                f"computed against that same cross-section by reindexing — the name is "
                f"scored against the universe, not added to it."
            )
            vol = None
            # RS for an off-universe name: rank its excess return INTO the existing panel.
            b = bench.reindex(px.index).ffill()
            name_ret = c.reindex(px.index) / c.reindex(px.index).shift(lp.RS_LOOKBACK) - 1.0
            bench_ret = b / b.shift(lp.RS_LOOKBACK) - 1.0
            excess = name_ret - bench_ret
            panel_excess = (px / px.shift(lp.RS_LOOKBACK) - 1.0).sub(bench_ret, axis=0)
            rs_series = (panel_excess.lt(excess, axis=0).sum(axis=1)
                         / panel_excess.notna().sum(axis=1).replace(0, np.nan))
            rec["rs_basis"] = "ranked INTO the replay cross-section (not a member of it)"

        frame = lp.evaluate(c, rs_pct=rs_series, volume=vol)
        win = frame.loc[(frame.index >= lo) & (frame.index <= hi)]
        rec["avwap_available"] = bool(vol is not None)
        if win.empty:
            rec.update({"fired": None, "null_reason": "no evaluated sessions in the case window"})
            out.append(rec)
            continue

        fired = win[(win["state"] == lp.STATE_RESET_TURN) & (win["days_in_state"] == 1)]
        rec["fired"] = bool(len(fired) > 0)
        rec["fire_dates"] = [str(d.date()) for d in fired.index]
        rec["timeline"] = [
            {"date": str(d.date()),
             "state": r["state"],
             "close": round(float(px.at[d, t]), 4) if t in px.columns and d in px.index
             else (round(float(c.loc[d]), 4) if d in c.index else None),
             "depth_pct": _pct(r["pullback_depth"]),
             "stoch_k": round(float(r["stoch_k"]), 1) if pd.notna(r["stoch_k"]) else None,
             "rs_pct": round(float(r["rs_pct"]), 3) if pd.notna(r["rs_pct"]) else None,
             "leg_rs": _b(r["leg_rs"]), "leg_52w": _b(r["leg_52w"]),
             "leg_above_200": _b(r["leg_above_200"]), "leg_depth": _b(r["leg_depth"]),
             "leg_age": _b(r["leg_age"]), "leg_k_dip": _b(r["leg_k_dip"]),
             "leg_k_cross": _b(r["leg_k_cross"]), "leg_hist_rising": _b(r["leg_hist_rising"]),
             "episode_end_reason": _s(r["episode_end_reason"]),
             "null_reason": _s(r["null_reason"])}
            for d, r in win.iterrows()
        ]

        # Which leg failed ON the operator's receipt date? The LEADER legs (rs, 52w) and
        # the band legs gate a name INTO an episode; the turn legs gate the FIRE. Splitting
        # them is the difference between "never in the lane" and "in the lane, never fired".
        rd = pd.Timestamp(case["receipt_date"])
        if rd in win.index:
            r = win.loc[rd]
            entry_legs = [k for k, v in (
                ("rs_top_quartile", r["leg_rs"]), ("52w_high_recent", r["leg_52w"]),
                ("above_200dma", r["leg_above_200"]),
            ) if v is False]
            fire_legs = [k for k, v in (
                ("stoch_dipped_below_30", r["leg_k_dip"]),
                ("stoch_k_crossed_d", r["leg_k_cross"]),
                ("hist_rising_2_sessions", r["leg_hist_rising"]),
            ) if v is False or v is None]
            rec["receipt_date_state"] = r["state"]
            rec["receipt_date_rs_pct"] = (round(float(r["rs_pct"]), 3)
                                          if pd.notna(r["rs_pct"]) else None)
            rec["receipt_date_failed_entry_legs"] = entry_legs
            rec["receipt_date_failed_fire_legs"] = fire_legs
            rec["receipt_date_episode_end_reason"] = _s(r["episode_end_reason"])
        else:
            rec["receipt_date_state"] = None
            rec["receipt_date_rs_pct"] = None
            rec["receipt_date_failed_entry_legs"] = ["receipt date is not an evaluated session"]
            rec["receipt_date_failed_fire_legs"] = []
            rec["receipt_date_episode_end_reason"] = None

        # The blocker, in one line: the earliest leg in the chain that never let it through.
        tl = rec["timeline"]
        ever_episode = any(row["state"] in (lp.STATE_PULLBACK, lp.STATE_RESET_TURN,
                                            lp.STATE_RESUMED) for row in tl)
        if rec["fired"]:
            rec["blocker"] = None
        elif not ever_episode:
            rs_true = sum(1 for row in tl if row["leg_rs"] is True)
            rec["blocker"] = (
                f"never entered an episode in the window — the LEADER gate held on only "
                f"{rs_true}/{len(tl)} sessions (rs_top_quartile), so no qualifying pullback "
                f"was ever opened")
        else:
            pb = [row for row in tl if row["state"] == lp.STATE_PULLBACK]
            xs = [row["date"] for row in pb if row["leg_k_cross"]]
            rs_ = [row["date"] for row in pb if row["leg_hist_rising"]]
            ends = [row for row in tl if row["episode_end_reason"]]
            exit_note = ""
            if ends:
                e = ends[0]
                bits = []
                if e["leg_k_cross"]:
                    bits.append("the %K/%D cross printed on that very bar")
                if e["leg_hist_rising"]:
                    bits.append("the histogram was rising on it")
                if bits:
                    exit_note = (" — and " + " and ".join(bits)
                                 + ", one session outside the episode")
            rec["blocker"] = (
                "entered an episode but the turn legs never coincided inside it: "
                "%K crossed %D on {0}, the histogram was rising on {1}; episode closed {2}{3}"
            ).format(xs or "no session inside the episode",
                     rs_ or "no session inside the episode",
                     ", ".join("{0}:{1}".format(e["date"], e["episode_end_reason"])
                               for e in ends) or "not inside the window",
                     exit_note)

        # Lateness of the actual fire vs the case window's own low.
        if rec["fire_dates"]:
            fd = pd.Timestamp(rec["fire_dates"][0])
            entry = float(c.loc[fd])
            fwd_lo = c.loc[fd:]
            fwd_lo = fwd_lo.iloc[:LOW_WINDOW + 1]
            rec["fire_entry_close"] = round(entry, 4)
            rec["fire_reset_low"] = round(float(frame.at[fd, "reset_low"]), 4)
            rec["fire_zone"] = [round(float(frame.at[fd, "zone_low"]), 4),
                                round(float(frame.at[fd, "zone_high"]), 4)]
            rec["forward_low_sessions_available"] = int(len(fwd_lo))
            rec["forward_low_complete"] = bool(len(fwd_lo) == LOW_WINDOW + 1)
            rec["entry_vs_forward_low_pct"] = _pct(entry / float(fwd_lo.min()) - 1.0)
            rec["zone_floor_vs_forward_low_pct"] = _pct(
                float(frame.at[fd, "reset_low"]) / float(fwd_lo.min()) - 1.0)
            wlow = c.loc[lo:hi].min()
            rec["entry_vs_case_window_low_pct"] = _pct(entry / float(wlow) - 1.0)
            rec["case_window_low"] = round(float(wlow), 4)
            rec["case_window_low_date"] = str(c.loc[lo:hi].idxmin().date())
        out.append(rec)
    return out


def _s(v) -> str | None:
    """A string cell, or None — NaN never reaches the report as the text 'nan'."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


def _b(v) -> bool | None:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return bool(v)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _p1(v) -> str:
    """One-decimal percent, or the printed null."""
    return "null" if v is None else f"{v:.1f}%"


def _p2(v) -> str:
    """Two-decimal percent, or the printed null."""
    return "null" if v is None else f"{v:.2f}%"


def _sp2(v) -> str:
    """Signed two-decimal percent, or the printed null."""
    return "null" if v is None else f"{v:+.2f}%"


def _render_md(r: dict) -> str:
    m, c = r["measurement"], r["controls"]
    pooled, pnf = r["headline"]["pooled"], r["headline"]["per_name_first"]
    L = []
    A = L.append
    A(f"# LEADER-PULLBACK replay — the above-200 early-entry lane ({r['stamp']})\n")
    A("**Tier: RESEARCH / display.** Measurement only. No engine, gate, board, ranker, "
      "grader or ledger changes; nothing under `site/` or `data/` is written. Organ: "
      "`engine/us_leader_pullback.py` (v0 constants, ungauntleted). Instrument: "
      "`research/prophet_us_audit/leader_pullback_replay.py`. Charter: "
      "`research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §6.8(d), §6.9 R4.\n")
    A("---\n")
    A("## §0 Verdict, in plain words\n")
    lead = c["leader_state_base_rate"]
    d_pool = (None if None in (pooled["precision_pct"], lead["precision_pct"])
              else pooled["precision_pct"] - lead["precision_pct"])
    d_pnf = (None if None in (pnf["precision_pct"], lead["precision_pct"])
             else pnf["precision_pct"] - lead["precision_pct"])
    gain = (None if None in (pooled["median_entry_vs_low_pct"],
                             pooled["median_zone_floor_vs_low_pct"])
            else pooled["median_entry_vs_low_pct"] - pooled["median_zone_floor_vs_low_pct"])
    A("**As a standalone signal the RESET_TURN does not reproduce; as an entry-LOCATION "
      "instrument the zone does.** Two findings, and they point opposite ways.\n")
    A(f"1. **The fire adds nothing over being a leader.** Pooled precision "
      f"{_p1(pooled['precision_pct'])} against a LEADER-state base rate of "
      f"{_p1(lead['precision_pct'])} on the same sessions "
      f"({'null' if d_pool is None else f'{d_pool:+.1f}pp'}), and per-name-first "
      f"{_p1(pnf['precision_pct'])} "
      f"({'null' if d_pnf is None else f'{d_pnf:+.1f}pp'}) — the pooled margin is carried "
      f"by names that fire repeatedly and does not survive one-event-per-name. Loser rate "
      f"{_p1(pooled['loser_pct'])} vs {_p1(lead['loser_pct'])} is flat, and the median "
      f"forward path is within a quarter-point of zero at every horizon out to 20 "
      f"sessions. Under the house epistemics this is a NULL on the standalone-ranking "
      f"question — printed, not hidden — and it neither blocks this display-tier organ nor "
      f"retires the factor: a null standalone signal is retained as a confluence input.\n")
    A(f"2. **The zone is the finding.** Median distance from a fire to the subsequent "
      f"{LOW_WINDOW}-session low is {_p2(pooled['median_entry_vs_low_pct'])} taking the "
      f"fire-day close, and {_p2(pooled['median_zone_floor_vs_low_pct'])} waiting at the "
      f"zone floor — {'null' if gain is None else f'{gain:.2f}pp'} of entry location, on "
      f"{pooled['n_with_low_window']} fires, repeating in both halves. That is exactly the "
      f"residual-lateness target of §6.9: a late SIGNAL stops implying a late PRICE when "
      f"the plan waits at a structure-anchored band.\n")
    A("3. **All three operator case receipts MISS under the v0 constants** (§3). They are "
      "reported as misses; no constant was moved to capture them "
      "(`DNR:KILL-OUTCOME-AUDITION`). Each miss names a leg, and §3.1 measures the two "
      "shapes behind them across the whole universe rather than leaving them anecdotal.\n")
    A("## §1 What this lane is, and what it is not\n")
    A("The shipped US early-entry machinery is built around WASHOUT-IGNITION: a deep base, "
      "a cohort, and a turn from BELOW the 200dMA. The NVDA/AVGO/ADAM class never washes "
      "out. This organ is the ABOVE-200 complement — high-RS leaders taking a shallow "
      "controlled retrace, resetting the daily oscillator, and resuming. It is one member "
      "of the entry battery (§6.8d), not a replacement for any other lane, and it carries "
      "zero authority: it ranks nothing, gates nothing, sizes nothing, escalates nothing.\n")
    A("**Nothing is wired.** The organ is not imported by any board, ranker, plan builder "
      "or nightly job in this PR; no surface renders it and no ledger accrues from it. "
      "Wiring is a later change, and this receipt is what that change would have to "
      "argue with.\n")
    A(f"Window: **{m['eval_window'][0]} → {m['eval_window'][1]}** "
      f"({m['eval_sessions']} sessions). Universe: **{r['universe']['names_kept']} names** "
      f"from `{r['universe']['store']}` with ≥ {r['organ']['constants']['min_history_bars']} "
      f"bars ({r['universe']['names_dropped_short_history']} dropped short). "
      f"Benchmark: {r['universe']['benchmark']}. "
      f"Runtime {r['runtime_seconds']}s.\n")
    A("## §2 Headline\n")
    A(f"| set | n fires | names | graded (h{H_PRECISION}) | precision "
      f"(≥+{PRECISION_EXCESS * 100:.0f}pp) | loser (≤{LOSER_EXCESS * 100:.0f}pp) | "
      f"median entry-vs-{LOW_WINDOW}d-low | median zone-floor-vs-low |")
    A("|---|---|---|---|---|---|---|---|")
    for blk in (pooled, pnf):
        thin = " *(thin)*" if blk["thin"] else ""
        A(f"| {blk['label']} | {blk['n_events']} | {blk['n_names']} | "
          f"{blk['n_graded_h10']}{thin} | {_p1(blk['precision_pct'])} | "
          f"{_p1(blk['loser_pct'])} | {_p2(blk['median_entry_vs_low_pct'])} | "
          f"{_p2(blk['median_zone_floor_vs_low_pct'])} |")
    A("")
    A(f"Right-censored (fired inside the last {LOW_WINDOW} sessions, no complete forward "
      f"window — counted as fires, excluded from forward stats): "
      f"**{pooled['n_right_censored_h10']}**.\n")
    A("### Controls — the denominators\n")
    A(f"| control | n name-days | precision | loser | median excess (h{H_PRECISION}) |")
    A("|---|---|---|---|---|")
    for key in ("universe_base_rate", "leader_state_base_rate"):
        b = c[key]
        A(f"| {b['label']} | {b['n_name_days']:,} | {_p1(b['precision_pct'])} | "
          f"{_p1(b['loser_pct'])} | {_sp2(b['median_excess_pct'])} |")
    A("")
    A("The LEADER-state row is the one that matters: it asks whether the RESET_TURN adds "
      "anything over simply being a high-RS leader on that session. Absolute precision on "
      "a current-universe store is survivorship-inflated; the DIFFERENCE against a control "
      "drawn from the same biased universe is not.\n")
    A("### Median forward path (excess vs SPY)\n")
    A("| horizon | " + " | ".join(f"h{h}" for h in PATH_HORIZONS) + " |")
    A("|---|" + "---|" * len(PATH_HORIZONS))
    for blk in (pooled, pnf):
        cells = []
        for h in PATH_HORIZONS:
            cell = blk["median_forward_path_pct"][f"h{h}"]
            v = _sp2(cell["median"])
            cells.append(v + (" *(thin)*" if cell["thin"] and cell["median"] is not None else ""))
        A(f"| {blk['label']} | " + " | ".join(cells) + " |")
    A("")
    A("## §2.1 Half-split (sign stability)\n")
    A(f"Boundary: {m['half_split_boundary']}.\n")
    A("| half | n graded | precision | loser | median entry-vs-low | median zone-floor-vs-low |")
    A("|---|---|---|---|---|---|")
    for h in ("H1", "H2"):
        b = r["half_split"][h]
        thin = " *(thin)*" if b["thin"] else ""
        A(f"| {h} | {b['n_graded_h10']}{thin} | {_p1(b['precision_pct'])} | "
          f"{_p1(b['loser_pct'])} | {_p2(b['median_entry_vs_low_pct'])} | "
          f"{_p2(b['median_zone_floor_vs_low_pct'])} |")
    A("")
    ss = r["half_split"]["sign_stable_vs_leader_base"]
    h1, h2 = r["half_split"]["H1"], r["half_split"]["H2"]
    A(f"Sign of (precision − LEADER-state base rate) stable across halves: "
      f"**{'yes' if ss else ('null' if ss is None else 'NO')}**.")
    if None not in (h1["precision_pct"], h2["precision_pct"], lead["precision_pct"]):
        A(f"Read it with the magnitudes, not just the sign: H1 is "
          f"{h1['precision_pct'] - lead['precision_pct']:+.1f}pp over the base rate and H2 "
          f"is {h2['precision_pct'] - lead['precision_pct']:+.1f}pp. A stable sign on a "
          f"margin that small in one half is not an edge; it is a coin that landed the "
          f"same way twice. The entry-location columns, by contrast, agree to within "
          f"{abs(h1['median_entry_vs_low_pct'] - h2['median_entry_vs_low_pct']):.2f}pp "
          f"across the halves.")
    A("")
    A("## §3 Case receipts\n")
    A("Constants were NOT tuned to make these fire (`DNR:KILL-OUTCOME-AUDITION`). Where a "
      "case does not fire on the operator's date, the failing legs are named.\n")
    for case in r["case_receipts"]:
        A(f"### {case['ticker']} — {case['note']}\n")
        if case.get("fired") is None:
            A(f"- **No verdict**: {case.get('null_reason')}"
              + (f" (source `{case.get('price_source')}`)" if case.get("price_source") else "") + "\n")
            continue
        A(f"- source `{case['price_source']}` "
          f"({'adjusted' if case.get('adjusted') else 'UNADJUSTED'}); "
          f"anchored VWAP {'available' if case['avwap_available'] else '**null** (no volume in that store)'}")
        if case.get("source_deviation"):
            A(f"- **Source deviation**: {case['source_deviation']}")
        A(f"- fired in window: **{'YES' if case['fired'] else 'NO'}**"
          + (f" on **{', '.join(case['fire_dates'])}**" if case["fire_dates"] else ""))
        rsv = case.get("receipt_date_rs_pct")
        A(f"- on the operator's date {case['receipt_date']}: state "
          f"`{case.get('receipt_date_state')}`, RS percentile "
          f"{'null' if rsv is None else f'{rsv:.3f}'} (gate ≥ "
          f"{r['organ']['constants']['rs_top_pct']})")
        A(f"  - failing ENTRY legs (gate a name into an episode): "
          f"`{', '.join(case.get('receipt_date_failed_entry_legs') or []) or 'none'}`")
        A(f"  - failing FIRE legs (gate the RESET_TURN): "
          f"`{', '.join(case.get('receipt_date_failed_fire_legs') or []) or 'none'}`"
          + (f"; episode ended `{case['receipt_date_episode_end_reason']}`"
             if case.get("receipt_date_episode_end_reason") else ""))
        if case.get("blocker"):
            A(f"- **Blocker**: {case['blocker']}")
        if case.get("fire_dates"):
            A(f"- entry (fire close) **{case['fire_entry_close']}**, zone "
              f"**[{case['fire_zone'][0]}, {case['fire_zone'][1]}]**, "
              f"case-window low **{case['case_window_low']}** on {case['case_window_low_date']}")
            comp = "complete" if case["forward_low_complete"] else \
                f"**partial — only {case['forward_low_sessions_available']} of "\
                f"{LOW_WINDOW + 1} forward sessions exist yet**"
            A(f"- entry-vs-forward-low **{_p2(case['entry_vs_forward_low_pct'])}** "
              f"({comp}); zone-floor-vs-forward-low "
              f"**{_p2(case['zone_floor_vs_forward_low_pct'])}**; "
              f"entry-vs-case-window-low **{_p2(case['entry_vs_case_window_low_pct'])}**")
        A("")
    ea = r["episode_anatomy"]
    A("## §3.1 Episode anatomy — the two misses, measured at population scale\n")
    A("Three anecdotes carry nothing. These are the same two shapes counted across every "
      "episode in the window.\n")
    A("| quantity | n |")
    A("|---|---|")
    A(f"| episodes opened (a leader entered the retrace band above its 200dMA) | {ea['n_episodes']} |")
    A(f"| of those, reached the oscillator reset (%K < "
      f"{r['organ']['constants']['stoch_reset_max']:.0f} inside the episode) | "
      f"{ea['n_reached_stoch_reset']} |")
    A(f"| of those, contained a RESET_TURN | {ea['n_containing_a_reset_turn']} |")
    A(f"| — first RESET_TURN day inside the window (the headline fire count) | "
      f"{ea['n_fired_first_day_in_window']} |")
    A(f"| **reset but never turned** (the population this lane loses) | "
      f"{ea['n_reset_but_never_turned']} |")
    A(f"| — %K crossed %D on the very bar the episode CLOSED (the AVGO shape) | "
      f"{ea['n_cross_on_the_exit_bar']} |")
    A(f"| — …and the histogram was rising on that bar too, so ordering alone would fire it | "
      f"{ea['n_turn_legs_on_the_exit_bar']} |")
    A(f"| — %K cross and rising histogram both seen inside the episode, never on one bar "
      f"(the ADAM shape) | {ea['n_legs_never_coincided']} |")
    A(f"| — **union of the two shapes** (they overlap; do not add them) | "
      f"{ea['n_lost_to_leg_placement']} |")
    A("")
    A("Episode end reasons: " + ", ".join(f"`{k}` {v}" for k, v in ea["end_reasons"].items()) + ".\n")
    lost = ea["n_reset_but_never_turned"]
    both = ea["n_lost_to_leg_placement"]
    A(f"Read the middle rows together: of the {lost} episodes that reset and never turned, "
      f"**{both} ({both / lost * 100:.0f}%)** were lost to WHERE the two turn legs landed "
      f"rather than to the name failing to turn — against "
      f"{ea['n_fired_first_day_in_window']} fires in total. (That figure is the UNION of "
      f"the two shapes, not their sum: an episode can be in both.) Two v0 mechanics "
      f"produce it, and both are structural, not tuning:\n")
    A(f"- **The recovery exit is evaluated before the transition.** `recovered_without_"
      f"reset` closes an episode the moment depth drops back under "
      f"{r['organ']['constants']['pullback_depth_min'] * 100:.0f}%, and that test runs "
      f"BEFORE the RESET_TURN test on the same bar. A V-shaped two-day reset — dip on day "
      f"one, cross on day two as price jumps back — therefore lands one session outside "
      f"the episode. AVGO is exactly this: %K dipped to 26.3 on 07-29, crossed on 07-30, "
      f"and the 07-30 bar closed the episode instead of firing on it.")
    A("- **AND-ing two daily turn legs is expensive.** The %K/%D cross and a 2-session "
      "rising histogram are near-simultaneous in principle and days apart in practice. "
      "ADAM crossed on 07-24 and had a rising histogram from 07-27 onward — the legs never "
      "shared a bar, so nothing fired inside a textbook shallow reset. AVGO fails this one "
      "too: its histogram only turned up on 07-31, the session after its cross.\n")
    A("Neither observation is a licence to loosen anything today. They are the reason §3.2 "
      "pre-registers the alternatives *before* they are measured.\n")
    A("## §3.2 Pre-registered v1 revision candidates (NOT applied here)\n")
    A("Named now so the next measurement is a comparison and not a rediscovery. None of "
      "these is applied in this artifact, and none may be adopted on the strength of the "
      "three case names — adoption goes through §6.6 (chartered horizon, n ≥ 50 per cell, "
      "sign-stable across half-splits, era-stamped episodes), with the v0 population kept "
      "as the comparison arm.\n")
    A("1. **Transition-before-exit ordering.** Evaluate the RESET_TURN test before the "
      "`recovered_without_reset` exit on the same bar. Pre-registered measurement: does "
      f"the recovered population ({ea['n_turn_legs_on_the_exit_bar']} episodes where both "
      "legs printed on the exit bar) grade better or worse than the v0 fires on the same "
      "window and horizon, and what does it do to entry-vs-low?")
    A("2. **Turn-leg window instead of coincidence.** Accept the %K cross and the rising "
      "histogram within N sessions of each other rather than on one bar, firing on the "
      f"LATER of the two. Pre-registered: N ∈ {{2, 3}}, measured against the "
      f"{ea['n_legs_never_coincided']}-episode population above, reporting both the added "
      "fires' grade AND the entry-vs-low cost of firing later — a later fire that grades "
      "the same is a WORSE instrument for this lane, since lateness is the thing being "
      "attacked.")
    A("3. **RS reflexivity — the gate reads leadership at the worst possible moment.** A "
      "leader's own pullback lowers its trailing 126-session return, so the leg that "
      "admits it closes precisely while it draws down. NVDA is the clean case: percentile "
      "0.747 on 07-15, **0.522 at the 07-29 low**, back to 0.79–0.82 by 08-05 — above the "
      "gate only AFTER the move it was supposed to catch. It never entered an episode at "
      "all. (AVGO and ADAM did enter, and their percentiles also sagged under the gate "
      "mid-pullback — 0.728 and 0.649 respectively — which is the v0 design working: the "
      "LEADER legs are checked when an episode OPENS and not thereafter, precisely because "
      "requiring top-quartile RS throughout would make the lane self-defeating.) "
      "Pre-registered candidates: evaluate the LEADER legs at the episode's ANCHOR HIGH "
      "rather than on the current bar; or measure RS on the pullback-start date; or "
      "lengthen `rs_lookback` so a 4-week drawdown moves the rank less. All three are "
      "PIT-legal. None may be chosen by which one lights NVDA up — the selection rule is "
      "the §6.6 gate on the whole population, with the v0 arm reported beside it.\n")
    A("## §4 Definitions, limits, nulls\n")
    A(f"- **Close basis.** `data/yahoo` carries close and volume, no intraday high/low. "
      f"Every high, low, drawdown and reset level is close-basis; an intraday restatement "
      f"is a different measurement, not a refinement.")
    A(f"- **Entry.** {m['entry_definition']}. The zone floor column is what the zone "
      f"machinery is trying to deliver; the entry column is what an EOD close-taker pays.")
    A(f"- **Forward low window.** {m['low_window']} — a fire ON the low reads 0.00%.")
    A(f"- **Excess.** {m['precision_rule']}; loser {m['loser_rule']}. Both legs from "
      f"`data/yahoo` — {r['universe']['adjustment_basis']}.")
    A("- **Survivorship.** `data/yahoo` is a CURRENT-universe store; names that delisted "
      "inside the window are largely absent, so absolute forward statistics are biased "
      "upward. Nothing here corrects it. Read the control differences, not the levels.")
    A("- **Rank invariance.** The RS percentile ranks excess-vs-SPY, but subtracting a "
      "per-date constant cannot change a cross-sectional ordering — the SPY leg does no "
      "selection work in the LEADER gate. It is retained because the excess is what the "
      "lane reports. Stated so nobody reads the benchmark as a filter it is not.")
    uc = r["universe_composition"]
    A(f"- **The universe is the raw store, not a curated equity list.** {uc['note']} "
      f"Measured contamination: {uc['fx_suffixed_names_in_universe']} FX-suffixed names in "
      f"the universe produced {uc['fires_from_fx_suffixed_names']} of "
      f"{pooled['n_events']} fires, and {uc['fires_from_names_without_volume']} fires came "
      f"from names with no volume (so their resumption test used the zone top alone). "
      f"Too small to move a headline; named because 'too small' is a measurement, not an "
      f"assumption.")
    A(f"- **Thin cells.** Any cell with n < {m['thin_cell_n']} is labelled *(thin)*.")
    nv = r["universe"]["names_without_usable_volume"]
    A(f"- **Nulls printed.** {len(nv)} universe names carry no usable volume, so their "
      f"anchored VWAP is null and the resumption test falls back to the zone top: "
      f"{', '.join(nv) if nv else '(none)'}.")
    A("- **v0 constants are revisable, not fitted.** They are named once at the top of "
      "`engine/us_leader_pullback.py`, stamped into every row via `construction_era`, and "
      "may only move through the §6.6 discipline (chartered horizon, n ≥ 50 per cell, "
      "sign-stable across half-splits, era-stamped episodes).")
    A("")
    A("## §5 Constants (v0, printed)\n")
    A("| constant | value |")
    A("|---|---|")
    for k, v in r["organ"]["constants"].items():
        A(f"| `{k}` | {v} |")
    A("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    main()
