"""RC-RUL-5 item 5 — time-shift placebo sweep of the 10 non-SEQ reversion base rows.

RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.

Authority: research/TIME_CONFOUND_RECHECK_ADJUDICATION.md RC-RUL-5 (rulings 4+5):
the reversion screen's Leg-6 independent-draw placebo is retired as a verdict
instrument; the other 10 rows of the published reversion base
(research/ORACLE_REVERSION_VALIDATED.md) were graded by that retired machinery
and must be re-expressed with the time-preserving circular time-shift placebo
before ANY of them is promoted beyond display. Registry display statuses stay
`screened` regardless of what this sweep prints.

Discipline (mirrors scripts/research/oracle_seq_tc_recheck.py, PR #1869):
  - Signal definitions, fire sets, exit convention (W=25, E=21, time-exit),
    leg thresholds, and dev/holdout splits are FROZEN. Inference machinery only.
  - Mandatory reproduction gate per row against the published numbers
    (registry top-level `reversion` block = the durable published record):
    n exact, WR/ret_exit within 1pp. Rows failing the gate get NO new inference.
  - New inference per row:
      1. Episode collapse (same node, entry gaps <=10 trading days chain) —
         the same chaining rule as OTA-RC-1 (gap <=10 td) and OTA-RC-2.
      2. Episode-cluster bootstrap 95% CIs (2000 draws) on WR / ret_exit / asym,
         full set and holdout subset; lower bounds read against the frozen
         Leg-2 (0.62), Leg-5 (0.58), Leg-3 (1.5) bars.
      3. Circular time-shift placebo (2000 draws): per node, one shared uniform
         offset per draw shifts the real entry sequence within the node's
         realizable-outcome pool (wrapping) — preserves inter-fire
         spacing/clustering; count-matched by construction.
         For the single-regime row (SRM_BEARTAPE_ACCEL_K20, Amendment-1 path)
         the pool is restricted to operating-regime (risk_off) dates — the
         time-preserving analog of the shipped Leg-6' regime-matched placebo.
      4. Reproduced old bar: the shipped Leg-6 machinery re-run as-is
         (500 draws, seed 42) for a like-for-like old-bar column.

Outputs:
  research/ORACLE_REVERSION_BASE10_TC_SWEEP.md
  research/oracle_reversion_base10_tc_sweep.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from scripts.oracle_screen import (  # noqa: E402
    _load_panel,
    _load_episodes,
    _load_rotation_groups,
)
from engine.oracle.compounds import (  # noqa: E402
    get_entry_dates,
    augment_panel_with_derived,
    load_registry,
)
from scripts.oracle_reversion_screen import (  # noqa: E402
    _compute_entry_metrics,
    _agg_stats,
    _gauntlet_placebo,
    _gauntlet_placebo_regime_matched,
    _GAUNTLET_TIER_SPLITS,
    _DEFAULT_TIER_SPLIT,
)
from scripts.research.oracle_seq_tc_recheck import (  # noqa: E402
    _cluster_episodes,
    _episode_cluster_bootstrap,
    _build_node_pools_time,
    _circular_shift_placebo,
    _coverage_stats,
)

SEED = 20260705
WINDOW = 25
EXIT = 21
COOLDOWN = 10  # episode chaining gap, sessions (same rule as OTA-RC-1/OTA-RC-2)
N_DRAWS_DEFAULT = 2000
OLD_BAR_DRAWS = 500  # shipped Leg-6 convention
OLD_BAR_SEED = 42    # shipped Leg-6 convention

# Leg bars (frozen, research/ORACLE_REVERSION_GATE_PREREG.md)
LEG2_WR_BAR = 0.62
LEG3_ASYM_BAR = 1.5
LEG5_WR_BAR = 0.58

# The 10 non-SEQ rows of the published reversion base, in published-table order.
SIGNAL_IDS = [
    "A15_WASHOUT_OPP_OUT_2NODE",
    "B4_WASHOUT_DOLLAR_RELIEF",
    "B4_EP_SAME_OUT_CREDIT_EASE",
    "R16_VBOT_ACCELZ_NEG2_K_LOW",
    "E_DOLLAR_EASE_TLT_POS_K25",
    "R3_B2_ACCELZ_NEG15_K20",
    "R4_E10_OIL_EASE_K30_VIX40",
    "M1_OIL_DOWN_K30_RS_NEG",
    "SRM_BEARTAPE_ACCEL_K20",
    "RSLAG_OVERSOLD_K20",
]


# ---------------------------------------------------------------------------
# Regime-matched time pool (single-regime path only)
# ---------------------------------------------------------------------------

def _build_node_pools_time_regime(
    entries_df: pd.DataFrame,
    panel: pd.DataFrame,
    exit_sessions: int,
    operating_regime: str,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per-node realizable-outcome pools restricted to operating-regime dates.

    Mirrors oracle_seq_tc_recheck._build_node_pools_time, with the pool
    restricted to dates where the node is in the operating regime, using the
    same regime definition as the shipped Leg-6' machinery
    (_is_risk_off_date: spy_above_200d == 0 OR vix_pctile >= 0.70).
    A circular shift within this pool moves fires in "regime time" —
    inter-fire ordering is preserved while risk-off beta is stripped,
    matching the shipped Leg-6' semantics.
    """
    pool: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    nodes = entries_df["node"].unique().tolist()

    for node in nodes:
        try:
            npn = panel.xs(node, level="node")
        except KeyError:
            continue
        if "ret" not in npn.columns:
            continue
        npn = npn.sort_index()
        ret_s = npn["ret"]
        dates = ret_s.index
        n = len(dates)
        lvl = (1 + ret_s.fillna(0)).cumprod()

        # Vectorized regime mask, NaN-safe (NaN comparisons are False, matching
        # the row-wise _is_risk_off_date behavior).
        is_off = pd.Series(False, index=dates)
        if "spy_above_200d" in npn.columns:
            is_off = is_off | (npn["spy_above_200d"] == 0)
        if "vix_pctile" in npn.columns:
            is_off = is_off | (npn["vix_pctile"] >= 0.70)
        op_mask = is_off if operating_regime == "risk_off" else ~is_off
        op_arr = op_mask.to_numpy(dtype=bool)

        outcomes: list[float] = []
        outcome_dates: list[int] = []
        for exec_pos in range(n):
            if not op_arr[exec_pos]:
                continue
            exit_pos = exec_pos + exit_sessions
            if exit_pos >= n:
                continue
            exec_price = lvl.iat[exec_pos]
            exit_price = lvl.iat[exit_pos]
            if exec_price == 0 or np.isnan(exec_price) or exit_price == 0 or np.isnan(exit_price):
                continue
            outcomes.append(float(exit_price / exec_price - 1))
            outcome_dates.append(int(dates[exec_pos].value))

        if outcomes:
            d_arr = np.array(outcome_dates, dtype="int64")
            r_arr = np.array(outcomes, dtype=float)
            order = np.argsort(d_arr)
            pool[str(node)] = (d_arr[order], r_arr[order])

    return pool


# ---------------------------------------------------------------------------
# Per-signal runner
# ---------------------------------------------------------------------------

def run_signal(
    compound: dict,
    panel: pd.DataFrame,
    episodes: pd.DataFrame,
    rg: dict,
    n_draws: int,
    rng: np.random.Generator,
) -> dict:
    sid = compound["id"]
    rev = compound.get("reversion") or (compound.get("validation") or {}).get("reversion") or {}
    tier = compound.get("universe", {}).get("tier", "s")

    single_regime = str(rev.get("path", "")).startswith("single-regime")
    operating_regime = rev.get("operating_regime") if single_regime else None

    shipped = {
        "n": rev.get("n"),
        "wr": rev.get("wr"),
        "asym": rev.get("asym"),
        "ret_exit": rev.get("ret_exit"),
        "holdout_n": (rev.get("oos_holdout") or {}).get("n"),
        "holdout_wr": (rev.get("oos_holdout") or {}).get("wr"),
        "holdout_ret_exit": (rev.get("oos_holdout") or {}).get("ret_exit"),
        "placebo_kind": "regime_matched" if single_regime else "independent_draw",
        "placebo_p95": (rev.get("regime_matched_placebo") or rev.get("placebo") or {}).get("p95"),
    }

    print(f"\n[{sid}] tier={tier} path={'single-regime(' + str(operating_regime) + ')' if single_regime else 'standard'}", flush=True)

    entry_dates = get_entry_dates(compound, panel, episodes, rg)
    if not entry_dates or "__blocked__" in entry_dates:
        return {"signal_id": sid, "error": f"entry dates blocked/empty: {entry_dates.get('__blocked__', 'empty')}"}
    total_triggers = sum(len(v) for v in entry_dates.values())
    print(f"[{sid}] triggers={total_triggers}", flush=True)

    entries_df = _compute_entry_metrics(entry_dates, panel, WINDOW, EXIT, "time")
    print(f"[{sid}] mature entries={len(entries_df)}", flush=True)

    all_stats = _agg_stats(entries_df)
    n_actual = all_stats["n"]
    wr_actual = all_stats["WR"]
    asym_actual = all_stats["asym"]
    ret_actual = all_stats["mean_ret_exit"]

    split_str = _GAUNTLET_TIER_SPLITS.get(tier, _DEFAULT_TIER_SPLIT)
    split_date = pd.Timestamp(split_str)
    hold_df_flat = entries_df[entries_df["trigger_date"] > split_date]
    hold_stats = _agg_stats(hold_df_flat)

    repro = {
        "n": n_actual,
        "wr": round(wr_actual, 4),
        "asym": round(asym_actual, 4),
        "ret_exit": round(ret_actual, 4),
        "holdout_n": hold_stats["n"],
        "holdout_wr": round(hold_stats["WR"], 4) if not np.isnan(hold_stats["WR"]) else None,
        "holdout_ret_exit": round(hold_stats["mean_ret_exit"], 4) if not np.isnan(hold_stats["mean_ret_exit"]) else None,
        "shipped": shipped,
    }
    repro_ok = (
        shipped["n"] is not None
        and n_actual == shipped["n"]
        and abs(wr_actual - shipped["wr"]) < 0.01
        and abs(ret_actual - shipped["ret_exit"]) < 0.01
    )
    repro["match"] = bool(repro_ok)
    print(
        f"[{sid}] repro: n={n_actual}/{shipped['n']} wr={wr_actual:.4f}/{shipped['wr']}"
        f" asym={asym_actual:.4f}/{shipped['asym']} ret={ret_actual:.4f}/{shipped['ret_exit']}"
        f" -> {'MATCH' if repro_ok else 'NO MATCH'}",
        flush=True,
    )
    if not repro_ok:
        return {"signal_id": sid, "tier": tier, "single_regime": single_regime,
                "reproduction_gate": repro, "error": "REPRODUCTION_GATE_NO_MATCH"}

    entries_df = entries_df.copy()
    entries_df["entry_date"] = entries_df["trigger_date"]

    # 1. Episode collapse
    df_ep = _cluster_episodes(entries_df, cooldown=COOLDOWN)
    cov = _coverage_stats(df_ep, split_date)
    # Trim the potentially huge per-episode distribution list for the JSON
    cov = {k: v for k, v in cov.items() if k != "fires_per_episode_distribution"}
    print(f"[{sid}] episodes={cov['n_episodes']} months={cov['n_months']} fires/ep mean={cov['fires_per_episode_mean']}", flush=True)

    # 2a. Episode-cluster bootstrap — full
    t0 = time.time()
    ci_full = _episode_cluster_bootstrap(df_ep, n_draws, rng)
    print(f"[{sid}] full CIs ({time.time()-t0:.0f}s): WR[{ci_full['wr'][0]:.4f},{ci_full['wr'][1]:.4f}]"
          f" ret[{ci_full['ret_exit'][0]:.4f},{ci_full['ret_exit'][1]:.4f}]"
          f" asym[{ci_full['asym'][0]:.4f},{ci_full['asym'][1]:.4f}]", flush=True)

    # 2b. Episode-cluster bootstrap — holdout
    hold_ep_df = df_ep[pd.to_datetime(df_ep["entry_date"]) > split_date].copy()
    n_hold_ep = hold_ep_df["episode_id"].nunique()
    if n_hold_ep >= 5:
        ci_hold = _episode_cluster_bootstrap(hold_ep_df, n_draws, rng)
        leg5_ci_clears = bool(ci_hold["wr"][0] >= LEG5_WR_BAR)
    else:
        ci_hold = {"wr": (np.nan, np.nan), "ret_exit": (np.nan, np.nan), "asym": (np.nan, np.nan)}
        leg5_ci_clears = None
    print(f"[{sid}] holdout episodes={n_hold_ep} WR CI[{ci_hold['wr'][0]:.4f},{ci_hold['wr'][1]:.4f}]", flush=True)

    # 3. Time-shift placebo
    t0 = time.time()
    if single_regime:
        pool_by_node = _build_node_pools_time_regime(entries_df, panel, EXIT, operating_regime)
    else:
        pool_by_node = _build_node_pools_time(entries_df, panel, EXIT)
    ts_draws = _circular_shift_placebo(entries_df, pool_by_node, n_draws, rng)
    ts_p95 = float(np.nanpercentile(ts_draws, 95))
    ts_p = float(np.mean(ts_draws >= ret_actual))
    ts_clears = bool(ret_actual > ts_p95)
    print(f"[{sid}] time-shift ({time.time()-t0:.0f}s): p95={ts_p95*100:+.2f}% observed={ret_actual*100:+.2f}%"
          f" p={ts_p:.4f} clears={ts_clears}", flush=True)

    # 4. Reproduced old bar — the shipped Leg-6 machinery re-run as-is
    t0 = time.time()
    if single_regime:
        _, old_p95_repro = _gauntlet_placebo_regime_matched(
            entries_df, panel, WINDOW, EXIT, "time",
            operating_regime=operating_regime,
            n_draws=OLD_BAR_DRAWS, rng_seed=OLD_BAR_SEED,
        )
    else:
        _, old_p95_repro = _gauntlet_placebo(
            entries_df, panel, WINDOW, EXIT, "time",
            n_draws=OLD_BAR_DRAWS, rng_seed=OLD_BAR_SEED,
        )
    print(f"[{sid}] old-bar reproduced ({time.time()-t0:.0f}s): p95={old_p95_repro*100:+.2f}%"
          f" (published {shipped['placebo_p95']*100:+.2f}%)", flush=True)

    return {
        "signal_id": sid,
        "tier": tier,
        "single_regime": single_regime,
        "operating_regime": operating_regime,
        "split_date": split_str,
        "reproduction_gate": repro,
        "episode_coverage": cov,
        "episode_cluster_ci_full": {
            "wr_point": round(wr_actual, 4),
            "wr_ci": [round(ci_full["wr"][0], 4), round(ci_full["wr"][1], 4)],
            "wr_ci_lower_clears_leg2": bool(ci_full["wr"][0] >= LEG2_WR_BAR),
            "ret_exit_point": round(ret_actual, 4),
            "ret_exit_ci": [round(ci_full["ret_exit"][0], 4), round(ci_full["ret_exit"][1], 4)],
            "ret_exit_ci_excludes_zero": bool(ci_full["ret_exit"][0] > 0),
            "asym_point": round(asym_actual, 4),
            "asym_ci": [round(ci_full["asym"][0], 4), round(ci_full["asym"][1], 4)],
            "asym_ci_lower_clears_leg3": bool(ci_full["asym"][0] >= LEG3_ASYM_BAR),
        },
        "episode_cluster_ci_holdout": {
            "n_fires": int(len(hold_ep_df)),
            "n_episodes": int(n_hold_ep),
            "wr_point": repro["holdout_wr"],
            "wr_ci": [round(ci_hold["wr"][0], 4), round(ci_hold["wr"][1], 4)] if n_hold_ep >= 5 else None,
            "wr_ci_lower_clears_leg5": leg5_ci_clears,
            "ret_exit_ci": [round(ci_hold["ret_exit"][0], 4), round(ci_hold["ret_exit"][1], 4)] if n_hold_ep >= 5 else None,
        },
        "leg6_side_by_side": {
            "observed_ret_exit": round(ret_actual, 4),
            "old_bar_kind": shipped["placebo_kind"],
            "old_bar_published_p95": shipped["placebo_p95"],
            "old_bar_reproduced_p95": round(float(old_p95_repro), 4) if not np.isnan(old_p95_repro) else None,
            "timeshift_p95": round(ts_p95, 4),
            "timeshift_p": round(ts_p, 4),
            "observed_clears_timeshift_p95": ts_clears,
        },
    }


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def _pct(v, d=2):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v*100:+.{d}f}%"


def _f(v, d=3):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "n/a"
    return f"{v:.{d}f}"


def _ci_str(ci, pct=False):
    if not ci:
        return "n/a"
    if pct:
        return f"[{_pct(ci[0])}, {_pct(ci[1])}]"
    return f"[{_f(ci[0])}, {_f(ci[1])}]"


def _write_report(results: list[dict], meta: dict, out_md: Path, out_json: Path) -> None:
    ok = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    md: list[str] = [
        "# Oracle Reversion Base (10 non-SEQ rows) — Time-Shift Placebo Sweep + Episode-Cluster CIs",
        "",
        "**RE-CHECK — adjudication pending (Fable). No verdict is changed by this document.**",
        "",
        f"Date: {meta['date']}  |  Seed: {meta['seed']}  |  Draws: {meta['n_draws']}  |  "
        f"Script: `scripts/research/oracle_reversion_base10_tc_sweep.py`",
        "",
        "**Authority:** RC-RUL-5 items 4+5 (`research/TIME_CONFOUND_RECHECK_ADJUDICATION.md`): the",
        "reversion screen's Leg-6 independent-draw placebo is retired as a verdict instrument;",
        "the 10 non-SEQ rows of the published reversion base (`research/ORACLE_REVERSION_VALIDATED.md`)",
        "were graded by that retired machinery. This sweep re-expresses each row's Leg-6 read with the",
        "time-preserving circular time-shift placebo (per the DT-R14 rubric,",
        "`research/TIME_CONFOUND_EXPOSURE_AUDIT.md` §1) and adds episode-cluster CIs on WR/ret_exit/asym.",
        "Events, thresholds, exit convention (W=25, E=21, time-exit), and dev/holdout splits are frozen;",
        "inference machinery only. **Registry display statuses stay `screened` regardless of anything in",
        "this document. This sweep is the pre-condition for any future promotion, not a promotion.**",
        "",
        "---",
        "",
        "## Reproduction gate (published numbers, registry `reversion` blocks, asof 2026-07-05)",
        "",
        "Gate: n exact; WR and ret_exit within 1pp. Rows failing the gate get no new inference.",
        "",
        "| row | tier | n | WR | asym | ret_exit | holdout n | holdout WR | holdout ret | match |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        rep = r.get("reproduction_gate", {})
        sh = rep.get("shipped", {})
        if not rep:
            md.append(f"| {r['signal_id']} | ? | — | — | — | — | — | — | — | ERROR: {r.get('error')} |")
            continue
        md.append(
            f"| {r['signal_id']} | {r.get('tier','?')} "
            f"| {rep['n']} / {sh['n']} "
            f"| {_f(rep['wr'])} / {_f(sh['wr'])} "
            f"| {_f(rep['asym'])} / {_f(sh['asym'])} "
            f"| {_pct(rep['ret_exit'])} / {_pct(sh['ret_exit'])} "
            f"| {rep['holdout_n']} / {sh['holdout_n']} "
            f"| {_f(rep['holdout_wr'])} / {_f(sh['holdout_wr'])} "
            f"| {_pct(rep['holdout_ret_exit'])} / {_pct(sh['holdout_ret_exit'])} "
            f"| {'yes' if rep.get('match') else 'NO'} |"
        )

    md += [
        "",
        "---",
        "",
        "## Side-by-side — old Leg-6 bar vs time-shift p95 vs observed (per row)",
        "",
        "Old bar = the shipped Leg-6 placebo p95 (independent per-node count-matched draws;",
        "for the single-regime row †, the shipped Leg-6' regime-matched variant). Retired for",
        "verdict use by RC-RUL-5. Reproduced = same machinery re-run as-is (500 draws, seed 42).",
        "Time-shift = circular per-node offset placebo (this sweep, 2000 draws), which preserves",
        "inter-fire spacing/clustering; for † the shift pool is restricted to operating-regime",
        "(risk_off) dates, the time-preserving analog of Leg-6'.",
        "",
        "| row | observed ret_exit | old bar p95 (published) | old bar p95 (reproduced) | time-shift p95 | time-shift p | observed > time-shift p95? |",
        "|---|---|---|---|---|---|---|",
    ]

    for r in ok:
        s = r["leg6_side_by_side"]
        mark = " †" if r.get("single_regime") else ""
        md.append(
            f"| {r['signal_id']}{mark} "
            f"| {_pct(s['observed_ret_exit'])} "
            f"| {_pct(s['old_bar_published_p95'])} "
            f"| {_pct(s['old_bar_reproduced_p95'])} "
            f"| {_pct(s['timeshift_p95'])} "
            f"| {s['timeshift_p']:.4f} "
            f"| {'yes' if s['observed_clears_timeshift_p95'] else 'NO'} |"
        )

    md += [
        "",
        "† single-regime row (Amendment-1 path): both the old bar and the time-shift pool are",
        "regime-matched (risk_off dates only).",
        "",
        "Interpretation discipline (RC-RUL-5 ruling 2, applies here unchanged, both ways): the",
        "single-offset circular shift has low effective null degrees of freedom — each draw is one",
        "fully-correlated portfolio — so this is a wide, conservative bar. A row that does not clear",
        "it is not thereby shown to be calendar luck; the affirmative timing evidence is simply not",
        "established on a time-preserving null. A row that does clear it has timing evidence that",
        "survives temporal-structure preservation.",
        "",
        "---",
        "",
        "## Episode-cluster CIs (2000 draws; episodes = same-node fires chained at gaps ≤10 td)",
        "",
        "| row | episodes | months | fires/ep mean | WR CI (LB vs 0.62) | ret_exit CI (LB vs 0) | asym CI (LB vs 1.5) |",
        "|---|---|---|---|---|---|---|",
    ]

    for r in ok:
        cf = r["episode_cluster_ci_full"]
        cov = r["episode_coverage"]
        md.append(
            f"| {r['signal_id']} | {cov['n_episodes']} | {cov['n_months']} | {cov['fires_per_episode_mean']} "
            f"| {_ci_str(cf['wr_ci'])} {'≥' if cf['wr_ci_lower_clears_leg2'] else '<'} 0.62 "
            f"| {_ci_str(cf['ret_exit_ci'], pct=True)} {'> 0' if cf['ret_exit_ci_excludes_zero'] else '(includes 0)'} "
            f"| {_ci_str(cf['asym_ci'])} {'≥' if cf['asym_ci_lower_clears_leg3'] else '<'} 1.5 |"
        )

    md += [
        "",
        "### Holdout subset (Leg-5 bar 0.58; split per tier: s=2019-12-31, m=2023-12-31)",
        "",
        "| row | holdout fires | holdout episodes | holdout WR CI (LB vs 0.58) | holdout ret_exit CI |",
        "|---|---|---|---|---|",
    ]

    for r in ok:
        ch = r["episode_cluster_ci_holdout"]
        clears = ch["wr_ci_lower_clears_leg5"]
        note = "≥ 0.58" if clears else ("< 0.58" if clears is False else "(<5 episodes — no CI)")
        md.append(
            f"| {r['signal_id']} | {ch['n_fires']} | {ch['n_episodes']} "
            f"| {_ci_str(ch['wr_ci'])} {note} "
            f"| {_ci_str(ch['ret_exit_ci'], pct=True)} |"
        )

    if failed:
        md += [
            "",
            "---",
            "",
            "## Rows with no new inference (reproduction gate not matched / error)",
            "",
        ]
        for r in failed:
            md.append(f"- **{r['signal_id']}** — {r['error']}")

    md += [
        "",
        "---",
        "",
        "## Method notes",
        "",
        "- Fire sets come from `get_entry_dates` on the frozen registry specs; outcomes from",
        "  `_compute_entry_metrics` (W=25, E=21, time-exit, absolute returns) — the gauntlet's own",
        "  machinery, unchanged.",
        "- Episode chaining (≤10 trading-day gaps within a node, 5/7 calendar approximation) is the",
        "  same rule used by OTA-RC-1 (gap ≤10 td) and OTA-RC-2; it is a re-check convention, not a",
        "  new signal parameter.",
        "- The circular time-shift placebo mirrors `scripts/research/oracle_compound_tc_recheck.py`",
        "  (canonized for gauntlet use by RC-RUL-3 ruling 5) via",
        "  `scripts/research/oracle_seq_tc_recheck.py`, which this script generalizes.",
        "- Scope caveat (for the adjudicator): the episode unit is within-node (same convention as",
        "  OTA-RC-1/OTA-RC-2), so cross-node co-firing in the same macro window is not collapsed, and",
        "  per-node time-shift offsets are drawn independently across nodes. On tier-M (354 nodes) the",
        "  episode counts therefore overstate independent time — the months column is the conservative",
        "  independent-time read (tier-M rows touch only 45 / 16 / 50 calendar months). Same-instrument",
        "  trade-off as the canonized re-checks; noted, not corrected, here.",
        "- Per-row RNG streams are seeded deterministically from (seed, row-index) so single rows can",
        "  be re-run without disturbing the others.",
        "- Heavy panels are read from the main checkout's `data/` (gitignored stores; asof 2026-07-05,",
        "  the same stores the published blocks were re-verified against).",
        "",
        "*RE-CHECK artifact. No verdict is changed. Display statuses stay `screened`. Adjudication",
        "pending (Fable). Per RC-RUL-5 ruling 5 and the time-preserving-null standing law, this sweep",
        "is the pre-condition for any future promotion of these rows beyond display.*",
        "",
    ]

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[Output] {out_md}", flush=True)

    payload = {"meta": meta, "results": results}
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"[Output] {out_json}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--data-dir", type=Path,
        default=Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data"),
        help="Heavy-store data dir (main checkout; worktrees lack gitignored stores)",
    )
    p.add_argument("--compounds-dir", type=Path, default=None,
                   help="Registry dir (tracked; defaults to this checkout's copy)")
    p.add_argument("--draws", type=int, default=N_DRAWS_DEFAULT)
    p.add_argument("--seed", type=int, default=SEED)
    p.add_argument("--only", type=str, default=None,
                   help="Comma-separated signal ids to run (subset re-runs)")
    args = p.parse_args()

    compounds_dir = args.compounds_dir or (ROOT / "data" / "oracle" / "compounds")

    print("=== RC-RUL-5 item 5: reversion base 10-row time-shift placebo sweep ===", flush=True)
    print(f"data-dir: {args.data_dir}", flush=True)
    print(f"compounds-dir: {compounds_dir}", flush=True)
    print(f"draws: {args.draws}  seed: {args.seed}", flush=True)

    registry = {c["id"]: c for c in load_registry(compounds_dir)}
    todo = SIGNAL_IDS if not args.only else [s.strip() for s in args.only.split(",")]

    # Cache panels per tier
    panels: dict[str, pd.DataFrame] = {}
    episodes_by_tier: dict[str, pd.DataFrame] = {}
    rg = _load_rotation_groups(args.data_dir)

    results: list[dict] = []
    for idx, sid in enumerate(todo):
        compound = registry.get(sid)
        if compound is None:
            results.append({"signal_id": sid, "error": "not found in registry"})
            continue
        tier = compound.get("universe", {}).get("tier", "s")
        if tier not in panels:
            print(f"\n[load] panel/episodes tier={tier}...", flush=True)
            panels[tier] = augment_panel_with_derived(_load_panel(args.data_dir, tier))
            episodes_by_tier[tier] = _load_episodes(args.data_dir, tier)
        rng = np.random.default_rng([args.seed, idx])
        try:
            results.append(run_signal(
                compound, panels[tier], episodes_by_tier[tier], rg, args.draws, rng,
            ))
        except Exception as e:  # noqa: BLE001
            results.append({"signal_id": sid, "error": f"exception: {e}"})
            print(f"[{sid}] EXCEPTION: {e}", flush=True)

    meta = {
        "date": "2026-07-07",
        "seed": args.seed,
        "n_draws": args.draws,
        "window": WINDOW,
        "exit": EXIT,
        "cooldown": COOLDOWN,
        "old_bar_draws": OLD_BAR_DRAWS,
        "old_bar_seed": OLD_BAR_SEED,
        "authority": "RC-RUL-5 items 4+5 (research/TIME_CONFOUND_RECHECK_ADJUDICATION.md)",
        "script": "scripts/research/oracle_reversion_base10_tc_sweep.py",
        "signals": todo,
        "per_row_rng": "np.random.default_rng([seed, row_index])",
    }

    out_md = ROOT / "research" / "ORACLE_REVERSION_BASE10_TC_SWEEP.md"
    out_json = ROOT / "research" / "oracle_reversion_base10_tc_sweep.json"
    _write_report(results, meta, out_md, out_json)

    n_ok = sum(1 for r in results if "error" not in r)
    print(f"\n=== done: {n_ok}/{len(todo)} rows with full inference ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
