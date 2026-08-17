"""§10 confirmatory family assembly — five questions, NC-2 pairs, guardrails.

Consumes the runner's episode/outcome tables (plain DataFrames) and produces
graded, floor-checked, verdict-worded results.  Everything statistical routes
through :mod:`engine.entry_radar.replay.ruler` (per-name-first, month-cluster
bootstrap, BH at m=5); everything lexical uses the §10/§23 verdict vocabulary
and nothing stronger.

Input frame contract (one row per candidate episode, produced by the runner):
    name, session (decision session), detector (G0|C1|C2A|C3|C5|INCUMBENT),
    panel (A|B), era (FIT|TEST), excess_net (subject net fwd ret − matched
    control mean, H=10; NaN when uninformative_no_control),
    excess_net_unmatched (the §9 proximity-unmatched companion),
    false_start (bool|None), matched_pair_gap (Q5 signed session gap, NaN
    elsewhere), c2a_fired_in_episode (bool, C1 rows only), same_band_support
    (bool — §9 common-support flag from the unmatched match),
    n_cell (CEM cell size before k-NN, from the matched ControlMatch),
    n_controls (selected k = len(matched.controls)),
    cohort, regime, c32.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from engine.entry_radar.replay import prereg, ruler

# §10/§23 verdict vocabulary — nothing outside this list is ever emitted.
VERDICTS = ("PASS_SHAPED", "NULL", "PROXIMITY_SHADOW", "UNINFORMATIVE",
            "ACCRUING", "ADVERSE")
GUARDRAIL_STATES = ("NON_INFERIOR", "INCONCLUSIVE", "ADVERSE",
                    "EQUAL_OR_BETTER", "WORSE", "ACCRUING")


@dataclass(frozen=True)
class QuestionResult:
    question: str
    verdict: str                       # from VERDICTS
    primary: ruler.RulerResult | None  # None when ACCRUING/UNINFORMATIVE pre-read
    nc2_matched: ruler.RulerResult | None
    nc2_unmatched: ruler.RulerResult | None
    nc2_overlap: float                 # §9 common-support share (NaN when n/a)
    guardrail_state: str | None        # Q3/Q5 only
    guardrail: ruler.RulerResult | None
    bh_survives: bool | None           # filled after the family BH pass
    notes: tuple[str, ...] = field(default_factory=tuple)


def _floors_ok(res: ruler.RulerResult | None, *extra: ruler.RulerResult | None) -> bool:
    checks = [r for r in (res, *extra) if r is not None]
    return bool(checks) and all(r.floors_met() for r in checks)


def _excess_result(frame: pd.DataFrame, value_col: str, seed: int) -> ruler.RulerResult:
    return ruler.month_cluster_bootstrap(
        frame, stat_fn=lambda fr: ruler.per_name_first(fr, value_col), seed=seed)


def _difference_result(frame: pd.DataFrame, value_col: str, arm_col: str,
                       arm_a: str, arm_b: str, seed: int) -> ruler.RulerResult:
    return ruler.month_cluster_bootstrap(
        frame, stat_fn=ruler.difference_stat(value_col, arm_col, arm_a, arm_b),
        seed=seed)


def _nc2_pair(frame: pd.DataFrame, seed: int) -> tuple[
        ruler.RulerResult, ruler.RulerResult, float]:
    """§9: the matched primary re-read beside its proximity-unmatched companion,
    plus the common-support share from the unmatched matching pass."""
    matched = _excess_result(frame, "excess_net", prereg.seed_for(f"nc2m_{seed}"))
    unmatched = _excess_result(frame.dropna(subset=["excess_net_unmatched"]),
                               "excess_net_unmatched",
                               prereg.seed_for(f"nc2u_{seed}"))
    support = frame["same_band_support"].dropna()
    overlap = float(support.mean()) if len(support) else float("nan")
    return matched, unmatched, overlap


def _nc2_verdict(primary_verdict: str, matched: ruler.RulerResult,
                 unmatched: ruler.RulerResult, overlap: float) -> tuple[str, str]:
    """Map the §9 contrast onto the verdict + a note.  Never 'KILLED'."""
    if not np.isfinite(overlap) or overlap < prereg.NC2_OVERLAP_FLOOR:
        return "UNINFORMATIVE", (
            f"NC-2 common support {overlap:.2f} below the {prereg.NC2_OVERLAP_FLOOR}"
            " floor — UNINFORMATIVE, never KILLED (no common support is not a"
            " proximity shadow)")
    un_favorable = np.isfinite(unmatched.ci_low) and unmatched.ci_low > 0
    m_favorable = np.isfinite(matched.ci_low) and matched.ci_low > 0
    if un_favorable and not m_favorable:
        return "PROXIMITY_SHADOW", (
            "excess is favorable only when proximity is UNMATCHED — a proximity"
            " shadow per DNR:KILL-WASHOUT-TURN's NC-2 instrument, not detector"
            " edge")
    return primary_verdict, "NC-2: matched primary stands on its own"


def _primary_verdict(res: ruler.RulerResult, *, favorable_high: bool = True) -> str:
    if not np.isfinite(res.stat):
        return "UNINFORMATIVE"
    lo, hi = res.ci_low, res.ci_high
    if favorable_high and np.isfinite(lo) and lo > 0:
        return "PASS_SHAPED"
    if favorable_high and np.isfinite(hi) and hi < 0:
        return "ADVERSE"
    return "NULL"


def _three_state(res: ruler.RulerResult, *, margin: float,
                 better_is_low: bool) -> str:
    """Q3/Q5 guardrails (§10): NON_INFERIOR/EQUAL_OR_BETTER vs ADVERSE/WORSE vs
    INCONCLUSIVE.  ``better_is_low`` True for Q5 (rate difference; low good)."""
    lo, hi = res.ci_low, res.ci_high
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return "INCONCLUSIVE"
    if better_is_low:
        if hi <= margin:
            return "EQUAL_OR_BETTER"
        if lo > margin:
            return "WORSE"
        return "INCONCLUSIVE"
    if lo > margin:
        return "NON_INFERIOR"
    if hi < margin:
        return "ADVERSE"
    return "INCONCLUSIVE"


# --------------------------------------------------------------------------- #
# the five questions
# --------------------------------------------------------------------------- #
def q1_g0_vs_controls(frame: pd.DataFrame, *, row16_agreement: float) -> QuestionResult:
    """Q1 (Panel-B, TEST): per-name-first mean net excess vs matched controls.

    Subject to the §4 row-16 identity floor: below 90% agreement the graded
    population's identity is not established and Q1 is UNINFORMATIVE.
    """
    f = frame[(frame["detector"] == "G0") & (frame["panel"] == "B")
              & (frame["era"] == "TEST")].dropna(subset=["excess_net"])
    notes: list[str] = []
    if not np.isfinite(row16_agreement) or row16_agreement < prereg.ROW16_AGREEMENT_FLOOR:
        # FAIL-CLOSED both ways (§4/§14): an UNMEASURED agreement is not an
        # established identity — NaN refuses exactly like a sub-floor measure.
        why = ("not measured this run" if not np.isfinite(row16_agreement)
               else f"{row16_agreement:.2%} below the "
                    f"{prereg.ROW16_AGREEMENT_FLOOR:.0%} floor")
        return QuestionResult(
            "Q1", "UNINFORMATIVE", None, None, None, float("nan"), None, None,
            None, notes=(
                f"row-16 G0 date agreement {why} — Panel-B population identity "
                "not established (§4 binding floor)",))
    res = _excess_result(f, "excess_net", prereg.CONFIRMATORY_SEEDS["Q1_g0_vs_controls"])
    if not _floors_ok(res):
        return QuestionResult("Q1", "ACCRUING", res, None, None, float("nan"),
                              None, None, None,
                              notes=("§12 floors not met; look unspent",))
    verdict = _primary_verdict(res)
    m, u, ov = _nc2_pair(f, 1)
    verdict, nc2_note = _nc2_verdict(verdict, m, u, ov)
    notes.append(nc2_note)
    return QuestionResult("Q1", verdict, res, m, u, ov, None, None, None,
                          notes=tuple(notes))


def q2_c2_vs_c1minus(frame: pd.DataFrame) -> QuestionResult:
    """Q2 (Panel-A, TEST): C2a excess minus (C1 episodes with no C2a fire).

    Anti-conservative conditioning disclosed (§10); the PIT-clean sensitivity
    arm is a separate §13 cell the runner reports beside this.
    """
    a = frame[(frame["detector"] == "C2A") & (frame["panel"] == "A")
              & (frame["era"] == "TEST")].dropna(subset=["excess_net"]).copy()
    b = frame[(frame["detector"] == "C1") & (frame["panel"] == "A")
              & (frame["era"] == "TEST")
              & (frame["c2a_fired_in_episode"] == False)  # noqa: E712
              ].dropna(subset=["excess_net"]).copy()
    a["arm"], b["arm"] = "A", "B"
    both = pd.concat([a, b], ignore_index=True)
    res = _difference_result(both, "excess_net", "arm", "A", "B",
                             prereg.CONFIRMATORY_SEEDS["Q2_c2_vs_c1minus"])
    arm_a = _excess_result(a, "excess_net", prereg.seed_for("q2_arm_a"))
    arm_b = _excess_result(b, "excess_net", prereg.seed_for("q2_arm_b"))
    if not (_floors_ok(arm_a) and _floors_ok(arm_b)):
        return QuestionResult("Q2", "ACCRUING", res, None, None, float("nan"),
                              None, None, None,
                              notes=("§12 floors not met on an arm; look unspent",))
    verdict = _primary_verdict(res)
    m, u, ov = _nc2_pair(a, 2)
    verdict, nc2_note = _nc2_verdict(verdict, m, u, ov)
    return QuestionResult(
        "Q2", verdict, res, m, u, ov, None, None, None,
        notes=(nc2_note,
               "B-arm conditions on absence of a future in-window event — bias "
               "direction anti-conservative (upward) for Q2; read beside the "
               "PIT-clean sensitivity cell (q2_pit_clean_sensitivity)",
               "interpretation ceiling: a favorable Q2 is partly mechanical and "
               "does not on its own evidence incremental information in the turn"))


def q3_c3_vs_c2(frame: pd.DataFrame) -> QuestionResult:
    """Q3 (Panel-A, TEST, common-eligibility rows): false-start-rate difference
    (C3 − C2a) per-name-first; excess non-inferiority guardrail (three-state)."""
    elig = frame[(frame["panel"] == "A") & (frame["era"] == "TEST")
                 & frame["common_eligible_c3_c2a"].fillna(False)]
    c3 = elig[elig["detector"] == "C3"].dropna(subset=["false_start"]).copy()
    c2 = elig[elig["detector"] == "C2A"].dropna(subset=["false_start"]).copy()
    c3["fs"], c2["fs"] = c3["false_start"].astype(float), c2["false_start"].astype(float)
    c3["arm"], c2["arm"] = "C3", "C2A"
    both = pd.concat([c3, c2], ignore_index=True)
    res = _difference_result(both, "fs", "arm", "C3", "C2A",
                             prereg.CONFIRMATORY_SEEDS["Q3_c3_vs_c2"])
    arm3 = _excess_result(c3, "fs", prereg.seed_for("q3_arm_c3"))
    arm2 = _excess_result(c2, "fs", prereg.seed_for("q3_arm_c2a"))
    if not (_floors_ok(arm3) and _floors_ok(arm2)):
        return QuestionResult("Q3", "ACCRUING", res, None, None, float("nan"),
                              "ACCRUING", None, None,
                              notes=("§12 floors not met on an arm; look unspent",))
    # favorable direction for Q3 is NEGATIVE (C3 reduces false starts)
    if np.isfinite(res.ci_high) and res.ci_high < 0:
        verdict = "PASS_SHAPED"
    elif np.isfinite(res.ci_low) and res.ci_low > 0:
        verdict = "ADVERSE"
    else:
        verdict = "NULL" if np.isfinite(res.stat) else "UNINFORMATIVE"
    ex = pd.concat([
        elig[elig["detector"] == "C3"].dropna(subset=["excess_net"]).assign(arm="C3"),
        elig[elig["detector"] == "C2A"].dropna(subset=["excess_net"]).assign(arm="C2A"),
    ], ignore_index=True)
    guard = _difference_result(ex, "excess_net", "arm", "C3", "C2A",
                               prereg.seed_for("q3_guardrail_excess"))
    # margins are in pp; excess_net is a fraction — convert
    gstate = _three_state(guard, margin=prereg.Q3_NONINFERIORITY_MARGIN_PP / 100.0,
                          better_is_low=False)
    m, u, ov = _nc2_pair(c3.rename(columns={"fs": "_fs"}), 3)
    verdict, nc2_note = _nc2_verdict(verdict, m, u, ov)
    return QuestionResult("Q3", verdict, res, m, u, ov, gstate, guard, None,
                          notes=(nc2_note,
                                 "guardrail INCONCLUSIVE is the expected state at "
                                 "§12 floors per §0(e) measured dispersion",))


def q4_lobe_enlisted(live_forward_rows: pd.DataFrame | None) -> QuestionResult:
    """Q4: LIVE-FORWARD ONLY.  With no W4 stream the honest state is ACCRUING
    at n=0 / WAITING_FOR_LIVE_SOURCE — no historical reconstruction exists."""
    n = 0 if live_forward_rows is None else int(len(live_forward_rows))
    return QuestionResult(
        "Q4", "ACCRUING", None, None, None, float("nan"), None, None, None,
        notes=(f"LIVE-FORWARD ACCRUING; n={n}; state="
               f"{prereg.WAITING_FOR_LIVE_SOURCE} until the W4 spool exists; "
               "no historical lobe-enlistment reconstruction is lawful",))


def q5_g0_vs_incumbent(pairs: pd.DataFrame) -> QuestionResult:
    """Q5 (Panel-B, TEST): signed nearest-incumbent gap, per-name median →
    cross-name mean; +2-session minimum lead; false-start-burden guardrail.

    ``pairs`` rows: name, session (G0 decision), matched_pair_gap (signed),
    g0_false_start, incumbent_false_start (bool; on the matched set).
    """
    f = pairs.dropna(subset=["matched_pair_gap"]).copy()

    def _gap_stat(fr: pd.DataFrame) -> float:
        sub = fr[["name", "matched_pair_gap"]].dropna()
        if sub.empty:
            return float("nan")
        return float(sub.groupby("name")["matched_pair_gap"].median().mean())

    res = ruler.month_cluster_bootstrap(
        f, stat_fn=_gap_stat, seed=prereg.CONFIRMATORY_SEEDS["Q5_g0_vs_incumbent"])
    if not _floors_ok(res):
        return QuestionResult("Q5", "ACCRUING", res, None, None, float("nan"),
                              "ACCRUING", None, None,
                              notes=("§12 floors not met; look unspent",))
    pass_shaped = (np.isfinite(res.ci_low) and res.ci_low > 0
                   and res.stat >= prereg.Q5_MIN_LEAD_SESSIONS)
    if pass_shaped:
        verdict = "PASS_SHAPED"
    elif np.isfinite(res.ci_high) and res.ci_high < 0:
        verdict = "ADVERSE"
    else:
        verdict = "NULL" if np.isfinite(res.stat) else "UNINFORMATIVE"
    fs = f.dropna(subset=["g0_false_start", "incumbent_false_start"]).copy()
    fs["fs_diff"] = fs["g0_false_start"].astype(float) - fs["incumbent_false_start"].astype(float)
    guard = ruler.month_cluster_bootstrap(
        fs, stat_fn=lambda fr: ruler.per_name_first(fr, "fs_diff"),
        seed=prereg.seed_for("q5_guardrail_falsestart"))
    gstate = _three_state(guard, margin=prereg.Q5_FALSESTART_MARGIN_PP / 100.0,
                          better_is_low=True)
    return QuestionResult(
        "Q5", verdict, res, None, None, float("nan"), gstate, guard, None,
        notes=("two-sided ±30-session nearest matching; unmatched candidates "
               "reported with the coverage line and the +30-lead bounding read",
               f"minimum practically-meaningful lead {prereg.Q5_MIN_LEAD_SESSIONS} "
               "sessions applies to the point estimate",))


def apply_bh(results: Mapping[str, QuestionResult]) -> dict[str, QuestionResult]:
    """Family BH pass at q=0.10, m=5 fixed (§10).  Only PASS_SHAPED/ADVERSE
    verdicts carry a keyed p; ACCRUING/UNINFORMATIVE spend nothing."""
    pvals = {name: r.primary.p_boot
             for name, r in results.items()
             if r.primary is not None and r.verdict in ("PASS_SHAPED", "ADVERSE", "NULL")
             and np.isfinite(r.primary.p_boot)}
    survives = ruler.bh_fdr(pvals)
    out: dict[str, QuestionResult] = {}
    for name, r in results.items():
        out[name] = QuestionResult(
            question=r.question, verdict=r.verdict, primary=r.primary,
            nc2_matched=r.nc2_matched, nc2_unmatched=r.nc2_unmatched,
            nc2_overlap=r.nc2_overlap, guardrail_state=r.guardrail_state,
            guardrail=r.guardrail, bh_survives=survives.get(name), notes=r.notes)
    return out


__all__ = ["QuestionResult", "VERDICTS", "GUARDRAIL_STATES",
           "q1_g0_vs_controls", "q2_c2_vs_c1minus", "q3_c3_vs_c2",
           "q4_lobe_enlisted", "q5_g0_vs_incumbent", "apply_bh"]


# --------------------------------------------------------------------------- #
# panel-level adapter — the runner's seam (run_all / write_results)
# --------------------------------------------------------------------------- #
def _summary_table(frame: pd.DataFrame, cell: str) -> dict[str, Any]:
    """One descriptive/exploratory cell: per-name-first excess with CI, plus the
    §7 outcome medians and censuses.  NaN-safe on empty frames."""
    f = frame.dropna(subset=["excess_net"]) if "excess_net" in frame else frame
    res = (ruler.month_cluster_bootstrap(
        f, stat_fn=lambda fr: ruler.per_name_first(fr, "excess_net"),
        seed=prereg.seed_for(cell)) if len(f) else None)
    fs = frame["false_start"].dropna() if "false_start" in frame else pd.Series(dtype=float)
    out: dict[str, Any] = {
        "cell": cell,
        "n_episodes": int(len(frame)),
        "n_names": int(frame["name"].nunique()) if len(frame) else 0,
        "excess_net_mean": None if res is None else res.stat,
        "ci_low": None if res is None else res.ci_low,
        "ci_high": None if res is None else res.ci_high,
        "p_boot": None if res is None else res.p_boot,
        "t_cluster": None if res is None else res.t_cluster,
        "n_months": None if res is None else res.n_months,
        "eff_names": None if res is None else res.eff_names,
        "floors_met": None if res is None else res.floors_met(),
        "false_start_rate": float(fs.mean()) if len(fs) else None,
        "false_start_n": int(len(fs)),
        "mfe_median": _med(frame, "mfe"), "mae_median": _med(frame, "mae"),
        "fwd_ret_net_median": _med(frame, "fwd_ret_net"),
        "cost_bps_median": _med(frame, "cost_per_side_bps"),
        "censored_n": int(frame["censored"].fillna(False).sum()) if "censored" in frame else 0,
        "uninformative_no_control_n": int(
            frame["uninformative_no_control"].fillna(False).sum())
        if "uninformative_no_control" in frame else 0,
    }
    out.update(_control_pool_diagnostics(frame))
    return out


def _control_pool_diagnostics(frame: pd.DataFrame) -> dict[str, Any]:
    """Persist already-produced matching diagnostics onto the summary table.

    Null when the frame never carried the column (pre-W5.1 / old readers).
    Does not call ``controls.match`` and does not change any confirmatory
    statistic — it only serializes what the matching machinery already made.
    """
    out: dict[str, Any] = {}
    if "n_cell" in frame.columns:
        cells = pd.to_numeric(frame["n_cell"], errors="coerce").dropna()
        if len(cells):
            out["n_cell_mean"] = float(cells.mean())
            out["n_cell_median"] = float(cells.median())
            out["n_cell_min"] = int(cells.min())
            out["n_cell_max"] = int(cells.max())
        else:
            out["n_cell_mean"] = out["n_cell_median"] = None
            out["n_cell_min"] = out["n_cell_max"] = None
    else:
        out["n_cell_mean"] = out["n_cell_median"] = None
        out["n_cell_min"] = out["n_cell_max"] = None

    if "n_controls" in frame.columns:
        ks = pd.to_numeric(frame["n_controls"], errors="coerce").dropna()
        counts = ks.astype(int).value_counts() if len(ks) else pd.Series(dtype=int)
        for i in range(prereg.CONTROL_K + 1):
            out[f"k_n_{i}"] = int(counts.get(i, 0))
    else:
        for i in range(prereg.CONTROL_K + 1):
            out[f"k_n_{i}"] = None

    if "same_band_support" in frame.columns:
        support = frame["same_band_support"].dropna()
        out["overlap_share"] = float(support.mean()) if len(support) else None
    else:
        out["overlap_share"] = None
    return out


def _med(frame: pd.DataFrame, col: str) -> float | None:
    if col not in frame or frame[col].dropna().empty:
        return None
    return float(frame[col].dropna().median())


def _spend(inputs: Any, cell: str, config: dict[str, Any]) -> bool:
    """Spend a §13 look through the shell's enforced logger; refuse-closed."""
    log = getattr(inputs, "log_look", None)
    if log is None:
        raise RuntimeError("run_all needs the shell's look-logger — a cell may "
                           "not run unlogged (§13)")
    return bool(log(cell, config))


def run_all(inputs: Any) -> dict[str, Any]:
    """Grade the §10 questions this panel carries + the §13 table families the
    assembled frame supports.  Cells whose inputs this run does not carry are
    returned as NOT_EXECUTED with the missing input NAMED (look unspent) —
    'could not look' never reads as 'looked and saw nothing' (standards §9.2).
    """
    frame = getattr(inputs, "frame", None)
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return {"panel": inputs.panel, "questions": {}, "tables": {},
                "not_executed": {"all": "no assembled episode frame"},
                "refusal_census": list(getattr(inputs, "refusals", ()))}
    test = frame[frame["era"] == "TEST"]
    tables: dict[str, Any] = {}
    not_executed: dict[str, str] = {}

    # ---- confirmatory questions (panel-appropriate) ----------------------- #
    questions: dict[str, QuestionResult] = {}
    if inputs.panel == "B":
        _spend(inputs, "q1_primary", {"panel": "B"})
        questions["Q1"] = q1_g0_vs_controls(
            test, row16_agreement=float(getattr(inputs, "row16_agreement", float("nan"))))
        _spend(inputs, "nc2_q1", {"panel": "B"})
        pairs = getattr(inputs, "q5_pairs", None)
        if pairs is not None and len(pairs):
            _spend(inputs, "q5_primary", {"panel": "B"})
            _spend(inputs, "q5_guardrail_falsestart", {"panel": "B"})
            questions["Q5"] = q5_g0_vs_incumbent(pairs)
        else:
            not_executed["q5_primary"] = "no Q5 pair table assembled"
        questions["Q4"] = q4_lobe_enlisted(None)  # ACCRUING; spends nothing
    if inputs.panel == "A":
        _spend(inputs, "q2_primary", {"panel": "A"})
        _spend(inputs, "nc2_q2", {"panel": "A"})
        questions["Q2"] = q2_c2_vs_c1minus(test)
        if test["common_eligible_c3_c2a"].fillna(False).any():
            _spend(inputs, "q3_primary", {"panel": "A"})
            _spend(inputs, "q3_guardrail_excess", {"panel": "A"})
            _spend(inputs, "nc2_q3", {"panel": "A"})
            questions["Q3"] = q3_c3_vs_c2(test)
        else:
            not_executed["q3_primary"] = "no common-eligibility C3/C2a rows"
    questions = apply_bh(questions)

    # ---- per-detector primary + FIT tables -------------------------------- #
    for det in sorted(test["detector"].dropna().unique()):
        if det not in ("G0", "C1", "C2A", "C3", "C5"):
            continue
        cell = f"primary_table_{det}"
        tables[cell] = _summary_table(test[test["detector"] == det], cell)
        fit = frame[(frame["era"] == "FIT") & (frame["detector"] == det)]
        fcell = f"fit_table_{det}"
        if len(fit):
            _spend(inputs, fcell, {"era": "FIT"})
            tables[fcell] = _summary_table(fit, fcell)
        else:
            not_executed[fcell] = "no FIT-era rows in this run"

    # ---- cohort / regime cuts --------------------------------------------- #
    for det in sorted(test["detector"].dropna().unique()):
        if det not in ("G0", "C1", "C2A", "C3", "C5"):
            continue
        sub = test[test["detector"] == det]
        for coh in sorted(sub["cohort"].dropna().unique()):
            cell = f"cohort_{coh}_{det}"
            if cell in prereg.LOOK_CELLS:
                _spend(inputs, cell, {"cohort": coh, "detector": det})
                tables[cell] = _summary_table(sub[sub["cohort"] == coh], cell)
        for reg in ("stressed", "quiet"):
            cell = f"regime_{reg}_{det}"
            if cell in prereg.LOOK_CELLS and (sub["regime"] == reg).any():
                _spend(inputs, cell, {"regime": reg, "detector": det})
                tables[cell] = _summary_table(sub[sub["regime"] == reg], cell)

    # ---- C2 exploratory variants ------------------------------------------ #
    if inputs.panel == "A" and "variant" in test:
        c2 = test[test["detector"] == "C2A"]
        base = c2  # c2a rows carry variant == 'c2a_kd_cross'
        for v in ("b", "c", "d", "e", "f"):
            cell = f"c2variant_{v}"
            rows = test[test["variant"].astype(str).str.startswith(f"c2{v}")]
            if len(rows):
                _spend(inputs, cell, {"variant": f"c2{v}"})
                tables[cell] = _summary_table(rows, cell)
            else:
                not_executed[cell] = "variant emitted no candidates in this run"
        del base

    # ---- incumbent standalone / common eligibility / exemplar ------------- #
    if inputs.panel == "B":
        inc = frame[frame["detector"] == "INCUMBENT"]
        if len(inc):
            _spend(inputs, "incumbent_table", {})
            tables["incumbent_table"] = _summary_table(inc[inc["era"] == "TEST"],
                                                       "incumbent_table")
        else:
            not_executed["incumbent_table"] = "no incumbent rows assembled"
        exemplars = ("KRUS", "MCK", "NVDA", "REGN", "YELP")
        ex = test[test["name"].isin(exemplars)]
        _spend(inputs, "exemplar_read", {"names": list(exemplars)})
        tables["exemplar_read"] = {
            "cell": "exemplar_read",
            "note": ("motivating exemplars; TEST closes 2026-02-13 so the current "
                     "regime is out of sample by construction (§18 lead)"),
            "per_name": {n: _summary_table(ex[ex["name"] == n], f"exemplar_{n}")
                         for n in exemplars if (ex["name"] == n).any()},
            "absent": [n for n in exemplars if not (ex["name"] == n).any()],
        }
    _spend(inputs, "common_eligibility", {"panel": inputs.panel})
    tables["common_eligibility"] = {
        "cell": "common_eligibility", "panel": inputs.panel,
        "n_rows_common_c3_c2a": int(test["common_eligible_c3_c2a"].fillna(False).sum())
        if "common_eligible_c3_c2a" in test else 0,
        "eligibility_by_detector": {
            d: int((test["detector"] == d).sum())
            for d in sorted(test["detector"].dropna().unique())},
    }

    # ---- false-start sensitivity grid (diagnostic) ------------------------ #
    grid = getattr(inputs, "fs_grid", None)
    if grid is not None and len(grid):
        for _, g in grid.iterrows():
            cell = str(g["cell"])
            if cell in prereg.LOOK_CELLS:
                _spend(inputs, cell, {"fav": g["fav"], "adv": g["adv"], "h": g["h"]})
                tables[cell] = {k: (None if pd.isna(v) else v) for k, v in g.items()}
    else:
        not_executed["fs_grid"] = "grid not assembled in this run"

    # ---- C32 conditioner reads -------------------------------------------- #
    for qn, det in (("q1", "G0"), ("q2", "C2A"), ("q3", "C3")):
        if (inputs.panel == "B") != (qn == "q1"):
            continue
        for coh_key, coh in (("gapcat", "gap_catalyst"), ("deepwash", "deep_mtf_washout")):
            sub = test[(test["detector"] == det) & (test["cohort"] == coh)]
            for arm in ("with", "without"):
                cell = f"c32_{qn}_{arm}_{coh_key}"
                rows = sub[sub["c32"] == True] if arm == "with" else sub  # noqa: E712
                if len(rows):
                    _spend(inputs, cell, {"cohort": coh, "arm": arm})
                    tables[cell] = _summary_table(rows, cell)
                else:
                    not_executed[cell] = f"no {coh} rows for {det} in this run"

    return {
        "panel": inputs.panel,
        "questions": {k: _question_dict(v) for k, v in questions.items()},
        "tables": tables,
        "not_executed": not_executed,
        "refusal_census": list(getattr(inputs, "refusals", ())),
        "gate_receipts": [dict(gate=r.gate, detail=r.detail)
                          for r in getattr(inputs, "gate_receipts", ())],
        "info_cutoff": getattr(inputs, "info_cutoff", None),
        "seeds_used": dict(getattr(inputs, "seeds", {}) or {}),
    }


def _question_dict(q: QuestionResult) -> dict[str, Any]:
    def _r(res: ruler.RulerResult | None) -> dict[str, Any] | None:
        if res is None:
            return None
        return {"stat": res.stat, "ci_low": res.ci_low, "ci_high": res.ci_high,
                "p_boot": res.p_boot, "t_cluster": res.t_cluster,
                "n_episodes": res.n_episodes, "n_names": res.n_names,
                "n_months": res.n_months, "eff_names": res.eff_names,
                "nb": res.nb, "seed": res.seed}
    return {"question": q.question, "verdict": q.verdict,
            "primary": _r(q.primary), "nc2_matched": _r(q.nc2_matched),
            "nc2_unmatched": _r(q.nc2_unmatched), "nc2_overlap": q.nc2_overlap,
            "guardrail_state": q.guardrail_state, "guardrail": _r(q.guardrail),
            "bh_survives": q.bh_survives, "notes": list(q.notes)}


__all__ += ["run_all"]
