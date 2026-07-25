#!/usr/bin/env python3
"""PTT-W1-T — the §7 re-grade: W1 arms, §2d ladder, MWR census under the TIMING ruler.

PRE-REGISTRATION — header pinned and committed BEFORE any timing outcome was
computed (MWR/PTT-W1 precedent). Charter: PERSONALITY_TIMING_TAILORING_HANDOFF
§7 (operator correction 2026-07-25, PR #3430): washout/bottom tools are
REVERSION-class — grading them on the fwd63 hold-return apparatus is the DNR §3
wrong-ruler law (#1458, Oracle reversion reframe). Bottom-picking is primary;
hold-returns are demoted to secondary/confirmatory (§6's fwd63 numbers stand as
that secondary — not recomputed here).
WRONG-RULER CHECK (§7 item 5, performed): the object under test is a bottom-
catching claim → metrics below are entry-quality metrics, not drift metrics.
Trial-ledger family: personality_timing_w1t (registered in the pre-run commit).

PANEL AND ARMS ARE FROZEN FROM W1. Names, eligibility, fixed arm tools
(tool_w1a / tool_w1b_pure / tool_w1b_hyb / tool_global / tool_class), class
cells (class_vt) and derived rungs come from data/research/ptt_w1_panel.parquet
verbatim. CONSISTENCY GATE (two-pass): pass 1 recounts signal dates for ALL names and
aborts on any mismatch vs the panel's n_is_/n_oos_ columns BEFORE pass 2
computes any timing outcome. Constructions are imported from the W1 script
(identical code paths). Split unchanged: FIT ≤ 2020-06-30 · TEST ≥ 2020-07-01 ·
2021+ sub-split reported.

TIMING METRICS (per signal at daily index i; closes only, house form):
  mae63   = min(close[i+1..i+63]) / close[i] − 1        (%; ≤0; PRIMARY)
  prox    = close[i] / min(close[i−31..i+31]) − 1        (%; ≥0; §7 ±31td window)
  w3, w5  = prox ≤ 3% / ≤ 5%                             ("entered within Y% of the low")
  tdt     = argmin offset of close in [i−31, i+31] (td; ties → earliest, numpy
            first-hit; negative = trough BEFORE entry)
  mfe21   = max(close[i+1..i+21]) / close[i] − 1         (swing-high capture)
  rc21    = close[i+21] / close[i] − 1                   (~21td time-exit, Oracle law)
  labels (descriptive only): called_low = −2 ≤ tdt ≤ +5 · confirmed_reset =
  tdt < −2 · early = tdt > +5   (§7 item 3's "calls the low" vs "confirms the
  reset" separation).
VALID-DAY UNIVERSE per half: indices with i ≥ 31 AND i + 63 < len (proximity
window + forward window both resolvable); signals restricted identically (head
trim vs W1's tail-only rule is expected to be zero — indicator spin-up exceeds
31 days; any trim is printed). RANDOM-DAY NULLS (§7 item 1, per metric, per
name, per half — the 69%-class trap guard): all-days median mae63, w5/w3 rate,
median prox, called_low rate, median mfe21/rc21 over the half's valid days.
UPLIFTS: U_MAE = median signal mae63 − all-days median mae63 (pp; positive =
shallower adverse = better timing) · U_W5 = signal w5 rate − all-days w5 rate
(pp). INFERENTIAL METRICS = U_MAE (primary) and U_W5 (co-primary), EXACTLY TWO
— everything else is printed without decision weight (multiplicity held).

ARMS (all graded on TEST U_MAE / U_W5):
  A. FIXED W1 arms re-graded (tools verbatim from the panel; random floor =
     strict mean of all 6 tools' TEST uplifts, skipna=False) — answers "does
     the §6 ordering survive the ruler swap on grading alone?" (reading R1).
  B. TIMING-NATIVE re-selection (the decisive re-test; same 6-tool grid, same
     eligibility, tie-break = pinned tool order S3D S1W S2W M3D M1W M2W):
       W1a_T     per-name argmax FIT U_MAE over 6 tools (audition, timing-native)
       global_T  argmax over tools of panel median FIT U_MAE
       class_T   within class_vt cells (≥8 names else global_T), by median
                 member FIT U_MAE
       W1b_pure  unchanged (derived rung + S; zero outcome input — identical
                 tool to W1)
       W1b_hyb_T derived rung; family by FIT U_MAE at that rung (2-way)
     Persistence diagnostics under the timing ruler: per-name Spearman(FIT U_MAE
     tool ranks, TEST U_MAE tool ranks); FIT-best-in-TEST-top-2 rate (chance
     33.3%).
INFERENCE: month-cluster bootstrap (cluster = signal month), NB = 1000, RNG
seed 20260727 (DT-R14). CIs on arm medians + pairwise diffs for BOTH
inferential metrics, full TEST + 2021+ sub-split. Nulls printed.

ESTATE RE-GRADES (§7 item 2b/2c; FULL-SAMPLE frames matching the originals):
  LADDER (re-grades §2d): S-family only on 3D/1W/2W/1M (1M added for this
  section only, never an arm), full 2014→2026, ≥4 signals per (name, rung),
  on the §2d UNIVERSE (mwr_timeframe filter, ~1,63x names — not the W1
  eligibility panel; PG et al. stay in);
  vol-tercile × rung median U_MAE and U_W5 + the named defensives table
  (MCD JNJ KO PG PEP WMT COST) — does "MCD's home rung is 1W" survive?
  MWR CENSUS (re-grades the 13-signal S1-A basket census): EW MAG7 basket,
  2W-A stoch signals, per-signal mae63/prox/tdt/w5/rc21 vs basket all-days
  nulls + the calls-the-low/confirmed-reset split; per-member one-line
  summaries. Amendment-2 live-gate HIT/FAIL rules are NOT touched (§7 item 4).

PRE-STATED READINGS (pin; "X > Y" = point positive AND 95% CI excludes 0):
  R1 ruler-robustness: §6's fixed-arm ordering (W1b ≥ random ≥ W1a ≈ global)
     PRESERVED under U_MAE ⇒ §6 findings are ruler-robust; a FLIP of the fixed
     W1a arm above random (CI excludes 0) ⇒ §6 re-read must say so.
  R2 decisive re-test: W1a_T top-2 ≈ chance AND (W1a_T − random) CI includes 0
     ⇒ audition is noise under BOTH rulers → the DNR kill row STANDS and gains
     the ruler-swap leg. W1a_T > random ⇒ the kill row stays as registered
     (fwd63-scoped, per §7 item 2) but §8 must charter the timing-scoped
     audition as a NEW pre-registerable question — never a silent revival.
  R3 altitude under the timing ruler: same §2 matrix on W1a_T / class_T /
     global_T.
  R4 engine seat: W1b_pure > random on U_MAE (CI excludes 0) ⇒ structure-
     fitting's engine-seat evidence is UPGRADED (still shadow-first, W3).
  R5 product separation (descriptive): report the called_low vs confirmed_reset
     shares per arm and for the MWR census — different products, different
     honest copy; no promotion decision reads R5.

REGISTRY COMPLIANCE: DT-R14 month-cluster · DT-R16 era split (unchanged) ·
DNR §3 wrong-ruler law is the MOTIVE for this study · TI-R2 cited (profiles,
not tags) · DNR §1 untouched · fwd63 demoted per §7 (its numbers live in §6;
registered horizons here: 21td time-exit, 63td MAE window, ±31td proximity) ·
display-tier only; nothing promotes to authority.

Outputs: reports/ptt_w1_timing_regrade.md + data/research/ptt_w1t_panel.parquet.
Run: python3 scripts/research/ptt_w1_timing_regrade.py   (~5-10 min)
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from numpy.lib.stride_tricks import sliding_window_view  # noqa: E402

from engine.mag7_washout import ew_basket  # noqa: E402
from scripts.research.ptt_w1_persistence_of_fit import (  # noqa: E402
    FAMS, MIN_CLASS, OOS_START, RUNGS, SPLIT, SUB2021, TOOLS,
    bars_for, tool_dates,
)

RNG = np.random.default_rng(20260727)
OHLCV = ROOT / "data" / "baskets" / "ohlcv"
PANEL_PQ = ROOT / "data" / "research" / "ptt_w1_panel.parquet"
OUT_MD = ROOT / "reports" / "ptt_w1_timing_regrade.md"
OUT_PQ = ROOT / "data" / "research" / "ptt_w1t_panel.parquet"

H = 63           # MAE window
PROX = 31        # ±31td proximity window (§7)
TEXIT = 21       # reversion-capture time-exit (Oracle law ~20-25d; pinned 21)
NB = 1000
W_Y = {"w3": 3.0, "w5": 5.0}
LADDER_RUNGS = ["3D", "1W", "2W", "1M"]
DEFENSIVES = ["MCD", "JNJ", "KO", "PG", "PEP", "WMT", "COST"]
M7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]

ARMS_FIXED = ["w1a", "w1b_pure", "w1b_hyb", "global", "class"]
ARMS_T = ["w1a_T", "w1b_pure", "w1b_hyb_T", "global_T", "class_T"]


# ── metric arrays (whole-series, vectorized) ───────────────────────────────

def metric_arrays(c: np.ndarray) -> dict[str, np.ndarray]:
    """Per-index timing metrics; NaN outside the valid-day universe
    (i >= PROX and i + H < len)."""
    n = len(c)
    out = {k: np.full(n, np.nan) for k in
           ("mae63", "prox", "tdt", "mfe21", "rc21")}
    if n < PROX + H + 2:
        return out
    # forward windows over [i+1, i+H] → defined for i in [0, n-H-1]
    fw = sliding_window_view(c[1:], H)              # rows: i = 0..n-H-1
    fmin63 = fw.min(axis=1)
    i_hi = n - H - 1                                # last valid i (inclusive)
    out["mae63"][:i_hi + 1] = (fmin63[:i_hi + 1] / c[:i_hi + 1] - 1) * 100
    f21 = sliding_window_view(c[1:], TEXIT)
    j_hi = n - TEXIT - 1
    out["mfe21"][:j_hi + 1] = (f21.max(axis=1)[:j_hi + 1] / c[:j_hi + 1] - 1) * 100
    out["rc21"][:j_hi + 1] = (c[TEXIT:TEXIT + j_hi + 1] / c[:j_hi + 1] - 1) * 100
    # centered window [i-PROX, i+PROX] → rows j = i-PROX for i in [PROX, n-PROX-1]
    cw = sliding_window_view(c, 2 * PROX + 1)
    ctr = np.arange(PROX, n - PROX)
    out["prox"][ctr] = (c[ctr] / cw.min(axis=1) - 1) * 100
    out["tdt"][ctr] = cw.argmin(axis=1).astype(float) - PROX
    # clamp universe: require BOTH windows
    invalid = np.zeros(n, dtype=bool)
    invalid[:PROX] = True
    invalid[n - H:] = True
    for k in out:
        out[k][invalid] = np.nan
    return out


def half_masks(idx: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    return {
        "is": np.asarray(idx <= SPLIT),
        "oos": np.asarray(idx >= OOS_START),
        "oos21": np.asarray(idx >= SUB2021),
        "full": np.ones(len(idx), dtype=bool),
    }


def null_stats(m: dict[str, np.ndarray], mask: np.ndarray) -> dict[str, float]:
    v = mask & np.isfinite(m["mae63"]) & np.isfinite(m["prox"])
    if v.sum() < 60:
        return {}
    prox = m["prox"][v]
    tdt = m["tdt"][v]
    return {
        "mae_med": float(np.median(m["mae63"][v])),
        "w3_rate": float((prox <= W_Y["w3"]).mean() * 100),
        "w5_rate": float((prox <= W_Y["w5"]).mean() * 100),
        "prox_med": float(np.median(prox)),
        "called_rate": float((( -2 <= tdt) & (tdt <= 5)).mean() * 100),
        "mfe21_med": float(np.median(m["mfe21"][v])) if np.isfinite(m["mfe21"][v]).any() else np.nan,
        "rc21_med": float(np.median(m["rc21"][v])) if np.isfinite(m["rc21"][v]).any() else np.nan,
    }


# ── per-name computation (panel names only; arms frozen from W1) ──────────

def sig_metrics(px: pd.Series, m: dict[str, np.ndarray], dates: list[pd.Timestamp]
                ) -> pd.DataFrame:
    idx = px.index
    rows = []
    for t in dates:
        i = idx.searchsorted(t)
        if i >= len(idx):
            continue  # bar stamped past the last daily close (W-FRI tail)
        if not np.isfinite(m["mae63"][i]) or not np.isfinite(m["prox"][i]):
            continue  # outside valid-day universe (head trim; counted upstream)
        rows.append({
            "date": idx[i], "month": str(idx[i])[:7],
            "mae63": m["mae63"][i], "prox": m["prox"][i], "tdt": m["tdt"][i],
            "w3": bool(m["prox"][i] <= W_Y["w3"]), "w5": bool(m["prox"][i] <= W_Y["w5"]),
            "mfe21": m["mfe21"][i], "rc21": m["rc21"][i],
        })
    return pd.DataFrame(rows)


def gate_name(sym: str, prow: pd.Series) -> tuple[list[str], dict[str, list[pd.Timestamp]]]:
    """Pass-1 consistency gate: recount signal dates ONLY (no timing outcome is
    computed here). Returns (errors, per-tool signal dates for pass-2 reuse)."""
    px = pd.read_parquet(OHLCV / f"{sym}.parquet")["close"].dropna()
    bars_full = {r: bars_for(px, r) for r in RUNGS}
    errs: list[str] = []
    dates_by_tool: dict[str, list[pd.Timestamp]] = {}
    for tool in TOOLS:
        fam, rung = tool[0], tool[1:]
        dates = tool_dates(bars_full[rung], fam)
        dates_by_tool[tool] = dates
        idxs = px.index.searchsorted(dates)
        w1_ok = [i for i in idxs if i + H < len(px)]
        n_is_w1 = sum(1 for i in w1_ok if px.index[i] <= SPLIT)
        n_oos_w1 = len(w1_ok) - n_is_w1
        if n_is_w1 != int(prow[f"n_is_{tool}"]) or n_oos_w1 != int(prow[f"n_oos_{tool}"]):
            errs.append(f"{sym}/{tool}: recomputed {n_is_w1}/{n_oos_w1} "
                        f"vs panel {int(prow[f'n_is_{tool}'])}/{int(prow[f'n_oos_{tool}'])}")
    return errs, dates_by_tool


def load_name(sym: str, dates_by_tool: dict[str, list[pd.Timestamp]]
              ) -> tuple[dict, pd.DataFrame]:
    """Pass-2 (runs only after the gate cleared for ALL names)."""
    px = pd.read_parquet(OHLCV / f"{sym}.parquet")["close"].dropna()
    c = px.to_numpy(dtype=float)
    m = metric_arrays(c)
    masks = half_masks(px.index)
    nulls = {h: null_stats(m, masks[h]) for h in ("is", "oos", "oos21")}
    if not nulls["is"] or not nulls["oos"]:
        raise RuntimeError(f"{sym}: null-universe too small")

    out: dict = {"sym": sym}
    sig_rows = []
    trims = 0
    for tool in TOOLS:
        dates = dates_by_tool[tool]
        idxs = px.index.searchsorted(dates)
        w1_ok = [i for i in idxs if i + H < len(px)]
        sm = sig_metrics(px, m, dates)
        trims += max(0, len(w1_ok) - len(sm))
        for half, mask_fn in (("is", lambda d: d <= SPLIT), ("oos", lambda d: d >= OOS_START)):
            sub = sm[sm.date.map(mask_fn)]
            nl = nulls[half]
            if len(sub) == 0:
                out[f"umae_{half}_{tool}"] = np.nan
                out[f"uw5_{half}_{tool}"] = np.nan
                continue
            out[f"umae_{half}_{tool}"] = float(sub.mae63.median() - nl["mae_med"])
            out[f"uw5_{half}_{tool}"] = float(sub.w5.mean() * 100 - nl["w5_rate"])
        sub21 = sm[sm.date >= SUB2021]
        nl21 = nulls["oos21"]
        out[f"umae_oos21_{tool}"] = (float(sub21.mae63.median() - nl21["mae_med"])
                                     if len(sub21) and nl21 else np.nan)
        out[f"uw5_oos21_{tool}"] = (float(sub21.w5.mean() * 100 - nl21["w5_rate"])
                                    if len(sub21) and nl21 else np.nan)
        oos_sm = sm[sm.date >= OOS_START]
        for _, r in oos_sm.iterrows():
            sig_rows.append({
                "sym": sym, "tool": tool, "month": r.month,
                "mae_ex": r.mae63 - nulls["oos"]["mae_med"],
                "w5_ex": (100.0 if r.w5 else 0.0) - nulls["oos"]["w5_rate"],
                "mae_ex21": (r.mae63 - nulls["oos21"]["mae_med"])
                            if (r.date >= SUB2021 and nulls["oos21"]) else np.nan,
                "w5_ex21": ((100.0 if r.w5 else 0.0) - nulls["oos21"]["w5_rate"])
                           if (r.date >= SUB2021 and nulls["oos21"]) else np.nan,
                "tdt": r.tdt, "sub21": bool(r.date >= SUB2021),
            })
    out["_trims"] = trims
    for k, v in nulls["oos"].items():
        out[f"null_oos_{k}"] = v
    return out, pd.DataFrame(sig_rows)


# ── arm assignment (fixed from panel + timing-native) ──────────────────────

def argmax_tool(vals: dict[str, float], tools: list[str]) -> str:
    s = pd.Series({t: vals.get(t, np.nan) for t in tools})[tools]
    if s.isna().all():
        return tools[0]  # pinned-order fallback; unreachable for current panel
    return str(s.idxmax())


def assign_arms(p: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    p = p.merge(
        panel[["sym", "tool_w1a", "tool_w1b_pure", "tool_w1b_hyb", "tool_global",
               "tool_class", "class_vt", "rung_derived"]],
        on="sym", validate="1:1")
    # timing-native selections (FIT U_MAE)
    p["tool_w1a_T"] = p.apply(
        lambda r: argmax_tool({t: r[f"umae_is_{t}"] for t in TOOLS}, TOOLS), axis=1)
    med_is = {t: float(p[f"umae_is_{t}"].median()) for t in TOOLS}
    p["tool_global_T"] = argmax_tool(med_is, TOOLS)
    cls: dict[str, str] = {}
    for cell, sub in p.groupby("class_vt"):
        cls[cell] = (argmax_tool({t: float(sub[f"umae_is_{t}"].median()) for t in TOOLS}, TOOLS)
                     if len(sub) >= MIN_CLASS else p["tool_global_T"].iloc[0])
    p["tool_class_T"] = p["class_vt"].map(cls)
    p["tool_w1b_hyb_T"] = p.apply(
        lambda r: argmax_tool({f + r["rung_derived"]: r[f"umae_is_{f}{r['rung_derived']}"]
                               for f in FAMS}, [f + r["rung_derived"] for f in FAMS]), axis=1)
    # arm OOS values, both metrics, full + 2021+
    arm_tool = {**{a: f"tool_{a}" for a in ARMS_FIXED},
                **{a: f"tool_{a}" for a in ARMS_T if a not in ("w1b_pure",)}}
    for a, col in arm_tool.items():
        for met in ("umae", "uw5"):
            p[f"{met}_oos_{a}"] = p.apply(lambda r, c=col: r[f"{met}_oos_{r[c]}"], axis=1)
            p[f"{met}_oos21_{a}"] = p.apply(lambda r, c=col: r[f"{met}_oos21_{r[c]}"], axis=1)
    for met in ("umae", "uw5"):
        p[f"{met}_oos_random"] = p[[f"{met}_oos_{t}" for t in TOOLS]].mean(axis=1, skipna=False)
        p[f"{met}_oos21_random"] = p[[f"{met}_oos21_{t}" for t in TOOLS]].mean(axis=1, skipna=False)
    return p


def persistence(p: pd.DataFrame) -> dict:
    spear, top2 = [], []
    for _, r in p.iterrows():
        is_v = pd.Series({t: r[f"umae_is_{t}"] for t in TOOLS})
        oos_v = pd.Series({t: r[f"umae_oos_{t}"] for t in TOOLS})
        if is_v.isna().any() or oos_v.isna().any():
            continue
        spear.append(float(is_v.corr(oos_v, method="spearman")))
        top2.append(r["tool_w1a_T"] in list(oos_v.sort_values(ascending=False).index[:2]))
    s = pd.Series(spear).dropna()
    return {"spear_med": float(s.median()), "spear_frac_pos": float((s > 0).mean()),
            "top2_frac": float(np.mean(top2)), "n": len(top2)}


# ── month-cluster bootstrap (both metrics, one pass) ───────────────────────

ALL_ARMS = ARMS_FIXED + [a for a in ARMS_T if a != "w1b_pure"]
DIFF_PAIRS = [
    ("w1a", "random"), ("w1b_pure", "random"), ("global", "random"),
    ("class", "random"), ("w1b_hyb", "random"), ("w1a", "global"),
    ("w1b_pure", "w1a"), ("w1b_pure", "global"),
    ("w1a_T", "random"), ("global_T", "random"), ("class_T", "random"),
    ("w1b_hyb_T", "random"), ("w1a_T", "global_T"), ("w1a_T", "class_T"),
    ("class_T", "global_T"), ("w1b_pure", "w1a_T"), ("w1b_pure", "global_T"),
    ("w1b_hyb_T", "w1a_T"),
]


def bootstrap(p: pd.DataFrame, sig: pd.DataFrame, sub21: bool = False) -> dict:
    if sub21:
        s = sig[sig.sub21].copy()
        s["mae_x"], s["w5_x"] = s["mae_ex21"], s["w5_ex21"]
    else:
        s = sig.copy()
        s["mae_x"], s["w5_x"] = s["mae_ex"], s["w5_ex"]
    s = s[np.isfinite(s.mae_x)]
    pair = {a: set(zip(p["sym"], p[f"tool_{a}"])) for a in ALL_ARMS}
    months = sorted(s["month"].unique())
    by_month = {mm: g for mm, g in s.groupby("month")}
    suffix = "oos21" if sub21 else "oos"
    ref = {a: int(p[f"umae_{suffix}_{a}"].notna().sum()) for a in ALL_ARMS}
    ref["random"] = int(p[f"umae_{suffix}_random"].notna().sum())
    stats: dict[str, list[float]] = {}

    def add(k: str, v: float) -> None:
        stats.setdefault(k, []).append(v)

    for _ in range(NB):
        pick = RNG.choice(months, size=len(months), replace=True)
        boot = pd.concat([by_month[mm] for mm in pick])
        agg = boot.groupby(["sym", "tool"]).agg(
            mae=("mae_x", "median"), w5=("w5_x", "mean"))
        d_mae, d_w5 = agg["mae"].to_dict(), agg["w5"].to_dict()
        vals: dict[str, dict[str, float]] = {"umae": {}, "uw5": {}}
        for a in ALL_ARMS:
            pm, pw = [], []
            for y, t in pair[a]:
                v = d_mae.get((y, t))
                if v is not None and np.isfinite(v):
                    pm.append(v)
                    pw.append(d_w5[(y, t)])
            ok = len(pm) >= ref[a] * 0.5
            vals["umae"][a] = float(np.median(pm)) if ok else np.nan
            vals["uw5"][a] = float(np.median(pw)) if ok else np.nan
        for met, dd in (("umae", d_mae), ("uw5", d_w5)):
            mm2 = (pd.Series(dd).rename_axis(["sym", "tool"]).reset_index(name="v")
                   .pivot(index="sym", columns="tool", values="v")
                   .reindex(columns=TOOLS))
            rnd = mm2.mean(axis=1, skipna=False).dropna()
            vals[met]["random"] = (float(rnd.median())
                                   if len(rnd) >= ref["random"] * 0.5 else np.nan)
        for met in ("umae", "uw5"):
            for a, v in vals[met].items():
                add(f"{met}:{a}", v)
            for x, y in DIFF_PAIRS:
                add(f"{met}:{x}-{y}", vals[met][x] - vals[met][y])
    return {k: (float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5)))
            for k, v in stats.items()}


# ── estate re-grades (full-sample frames) ──────────────────────────────────

def bars_ext(close: pd.Series, rung: str) -> pd.Series:
    if rung == "1M":
        return close.resample("ME").last().dropna()
    return bars_for(close, rung)


def ladder_regrade() -> pd.DataFrame:
    """Re-grades the §2d ladder on ITS OWN universe (the mwr_timeframe filter:
    ≥2900 closes, first bar ≤2014-06-30, last+median ≥$2 — ~1,63x names, NOT the
    W1 eligibility panel; reviewer M1: PG et al. must not be silently dropped)."""
    rows = {}
    for f in sorted(OHLCV.glob("*.parquet")):
        sym = f.stem
        try:
            px = pd.read_parquet(f)["close"].dropna()
            if len(px) < 2900 or px.index[0] > pd.Timestamp("2014-06-30"):
                continue
            if float(px.iloc[-1]) < 2 or float(px.median()) < 2:
                continue
            c = px.to_numpy(dtype=float)
            m = metric_arrays(c)
            nl = null_stats(m, np.ones(len(px), dtype=bool))
            if not nl:
                continue
            rets = px.pct_change().dropna()
            rec = {"vol": float(rets.std() * np.sqrt(252) * 100)}
            for rung in LADDER_RUNGS:
                sm = sig_metrics(px, m, tool_dates(bars_ext(px, rung), "S"))
                if len(sm) >= 4:
                    rec[f"umae_{rung}"] = float(sm.mae63.median() - nl["mae_med"])
                    rec[f"uw5_{rung}"] = float(sm.w5.mean() * 100 - nl["w5_rate"])
                    rec[f"n_{rung}"] = len(sm)
            if sum(1 for r in LADDER_RUNGS if f"umae_{r}" in rec) >= 3:
                rows[sym] = rec
        except Exception:  # noqa: BLE001 — census fan-out, counted by absence
            continue
    return pd.DataFrame(rows).T


def mwr_census_regrade() -> tuple[pd.DataFrame, dict, list[str]]:
    ewp = ew_basket()
    c = ewp.to_numpy(dtype=float)
    m = metric_arrays(c)
    nl = null_stats(m, np.ones(len(ewp), dtype=bool))
    sm = sig_metrics(ewp, m, tool_dates(bars_for(ewp, "2W"), "S"))
    members = []
    for t in M7:
        px = pd.read_parquet(OHLCV / f"{t}.parquet")["close"].dropna()
        mm = metric_arrays(px.to_numpy(dtype=float))
        nlm = null_stats(mm, np.ones(len(px), dtype=bool))
        smm = sig_metrics(px, mm, tool_dates(bars_for(px, "2W"), "S"))
        if len(smm) and nlm:
            members.append(
                f"{t}: U_MAE {float(smm.mae63.median() - nlm['mae_med']):+.2f}pp, "
                f"w5 {float(smm.w5.mean() * 100):.0f}% (base {nlm['w5_rate']:.0f}%), "
                f"called-low {float(((smm.tdt >= -2) & (smm.tdt <= 5)).mean() * 100):.0f}% "
                f"(n={len(smm)})")
    return sm, nl, members


# ── report ─────────────────────────────────────────────────────────────────

def ci_str(ci: tuple[float, float] | None) -> str:
    if not ci or not np.isfinite(ci[0]):
        return "[—]"
    return f"[{ci[0]:+.2f}, {ci[1]:+.2f}]"


def verdict_str(ci: tuple[float, float] | None) -> str:
    if not ci or not np.isfinite(ci[0]):
        return "—"
    if ci[0] > 0:
        return "excludes 0 ↑"
    if ci[1] < 0:
        return "excludes 0 ↓"
    return "includes 0"


def main() -> None:
    panel = pd.read_parquet(PANEL_PQ)
    # pass 1: consistency gate on ALL names — no timing outcome computed yet
    all_gate_errs, dates_cache = [], {}
    for _, prow in panel.iterrows():
        errs, dates_by_tool = gate_name(prow["sym"], prow)
        all_gate_errs.extend(errs)
        dates_cache[prow["sym"]] = dates_by_tool
    if all_gate_errs:
        print("CONSISTENCY GATE FAILED — aborting; no timing outcome was computed")
        for e in all_gate_errs[:10]:
            print(" ", e)
        sys.exit(2)
    # pass 2: timing outcomes (gate cleared)
    rows, sig_all = [], []
    trims = 0
    for sym in panel["sym"]:
        out, sig = load_name(sym, dates_cache[sym])
        trims += out.pop("_trims")
        rows.append(out)
        sig_all.append(sig)
    p = pd.DataFrame(rows)
    sig = pd.concat(sig_all, ignore_index=True)
    p = assign_arms(p, panel)
    pers = persistence(p)
    ci = bootstrap(p, sig, sub21=False)
    ci21 = bootstrap(p, sig, sub21=True)

    L: list[str] = []
    L.append("# PTT-W1-T — the §7 re-grade: bottom-picking ruler "
             "(MAE primary, within-5%-of-low co-primary)\n")
    L.append(f"Pre-registered ruler: script header, committed pre-run (charter §7, "
             f"PR #3430; DNR §3 wrong-ruler law #1458). Panel + fixed arms FROZEN "
             f"from W1 ({len(p)} names, consistency gate PASSED, head-trims: {trims}). "
             f"TEST signals: {len(sig):,}. U_MAE = median signal MAE63 − all-days "
             f"median MAE63 (pp, positive = shallower adverse); U_W5 = signal "
             f"within-5%-of-low rate − all-days rate (pp). Random-day nulls are "
             f"per-name per-half per-metric (§7 base-rate guard). Panel all-days "
             f"OOS base rates (median across names): MAE {p.null_oos_mae_med.median():+.2f}%, "
             f"w5 {p.null_oos_w5_rate.median():.1f}%, called-low "
             f"{p.null_oos_called_rate.median():.1f}%.\n")

    # §A fixed arms (R1)
    L.append("## A. R1 — fixed W1 arms re-graded (ruler swap on grading alone)\n")
    L.append("| arm (tools verbatim from W1) | U_MAE OOS | CI | U_W5 OOS | CI | "
             "U_MAE 2021+ | U_W5 2021+ |")
    L.append("|---|---|---|---|---|---|---|")
    lbl_fixed = {"w1a": "(a) W1a fwd63-audition tools", "w1b_pure": "(a′) W1b-pure structure",
                 "w1b_hyb": "(a″) W1b-hybrid", "global": "(b) global one-size (S2W)",
                 "class": "(c) class (≡ global, degenerate)"}
    for a in ARMS_FIXED:
        L.append(f"| {lbl_fixed[a]} | {float(p[f'umae_oos_{a}'].median()):+.2f}pp | "
                 f"{ci_str(ci.get(f'umae:{a}'))} | {float(p[f'uw5_oos_{a}'].median()):+.2f}pp | "
                 f"{ci_str(ci.get(f'uw5:{a}'))} | "
                 f"{float(p[f'umae_oos21_{a}'].dropna().median()):+.2f}pp | "
                 f"{float(p[f'uw5_oos21_{a}'].dropna().median()):+.2f}pp |")
    L.append(f"| (d) random floor | {float(p.umae_oos_random.median()):+.2f}pp | "
             f"{ci_str(ci.get('umae:random'))} | {float(p.uw5_oos_random.median()):+.2f}pp | "
             f"{ci_str(ci.get('uw5:random'))} | "
             f"{float(p.umae_oos21_random.dropna().median()):+.2f}pp | "
             f"{float(p.uw5_oos21_random.dropna().median()):+.2f}pp |")

    # §B timing-native arms (R2/R3)
    L.append("\n## B. R2/R3 — timing-native re-selection (the decisive re-test)\n")
    gt = p["tool_global_T"].iloc[0]
    L.append(f"Global-T tool (FIT U_MAE best): **{gt}**. W1a_T FIT selections: "
             + ", ".join(f"{t} {n}" for t, n in p['tool_w1a_T'].value_counts().items())
             + ". Class-T cells: "
             + ", ".join(f"{c}→{t}" for c, t in sorted(
                   p.groupby('class_vt')['tool_class_T'].first().items())) + ".\n")
    L.append("| arm | U_MAE OOS | CI | U_W5 OOS | CI |")
    L.append("|---|---|---|---|---|")
    lbl_t = {"w1a_T": "(aT) W1a_T timing-audition", "w1b_pure": "(a′) W1b-pure (unchanged)",
             "w1b_hyb_T": "(a″T) W1b-hybrid_T", "global_T": "(bT) global_T",
             "class_T": "(cT) class_T"}
    for a in ARMS_T:
        L.append(f"| {lbl_t[a]} | {float(p[f'umae_oos_{a}'].median()):+.2f}pp | "
                 f"{ci_str(ci.get(f'umae:{a}'))} | {float(p[f'uw5_oos_{a}'].median()):+.2f}pp | "
                 f"{ci_str(ci.get(f'uw5:{a}'))} |")

    L.append("\n### Decision block (U_MAE primary; U_W5 co-primary in parens)\n")
    L.append("| comparison | U_MAE point | CI | reads | U_W5 point (CI) |")
    L.append("|---|---|---|---|---|")
    for x, y in DIFF_PAIRS:
        dm = float(p[f"umae_oos_{x}"].median() - (p[f"umae_oos_{y}"].median()
                   if y != "random" else p["umae_oos_random"].median()))
        dw = float(p[f"uw5_oos_{x}"].median() - (p[f"uw5_oos_{y}"].median()
                   if y != "random" else p["uw5_oos_random"].median()))
        cm, cw = ci.get(f"umae:{x}-{y}"), ci.get(f"uw5:{x}-{y}")
        L.append(f"| {x} − {y} | {dm:+.2f}pp | {ci_str(cm)} | {verdict_str(cm)} | "
                 f"{dw:+.2f}pp {ci_str(cw)} |")

    # §C persistence under the timing ruler
    L.append("\n## C. Persistence under the timing ruler\n")
    L.append(f"- Per-name Spearman(FIT U_MAE tool ranks, TEST U_MAE tool ranks): "
             f"median **{pers['spear_med']:+.3f}**; {pers['spear_frac_pos']:.0%} positive "
             f"(n={pers['n']}; 6-rank granularity — read with top-2).")
    L.append(f"- FIT-best (by U_MAE) lands in TEST top-2: **{pers['top2_frac']:.1%}** "
             f"(chance = 33.3%).\n")

    # §D calls-the-low vs confirms-the-reset (R5, descriptive)
    L.append("## D. R5 — calls the low vs confirms the reset (descriptive)\n")
    L.append("| arm tool set | called low (−2..+5td) | confirmed reset (<−2td) | "
             "early (>+5td) | median td_to_trough |")
    L.append("|---|---|---|---|---|")
    for a in ["w1b_pure", "w1a_T", "global"]:
        pr = set(zip(p["sym"], p[f"tool_{a}"]))
        ss = sig[[(y, t) in pr for y, t in zip(sig.sym, sig.tool)]]
        called = float(((ss.tdt >= -2) & (ss.tdt <= 5)).mean() * 100)
        conf = float((ss.tdt < -2).mean() * 100)
        early = float((ss.tdt > 5).mean() * 100)
        L.append(f"| {a} | {called:.0f}% | {conf:.0f}% | {early:.0f}% | "
                 f"{float(ss.tdt.median()):+.0f}td |")
    L.append(f"\nPanel all-days called-low base rate (median name): "
             f"{p.null_oos_called_rate.median():.1f}% — the §7 base-rate trap "
             f"quantified.\n")

    # §E ladder re-grade (§2d estate)
    L.append("## E. §2d ladder re-graded (S family, full-sample, U_MAE / U_W5)\n")
    lad = ladder_regrade()
    if len(lad) >= 100:
        lad["volT"] = pd.qcut(lad["vol"], 3, labels=["low-vol", "mid-vol", "high-vol"])
        L.append("| vol tercile | " + " | ".join(LADDER_RUNGS) + " | best rung (U_MAE) |")
        L.append("|---|" + "---|" * (len(LADDER_RUNGS) + 1))
        for lab in ["low-vol", "mid-vol", "high-vol"]:
            sub = lad[lad.volT == lab]
            vals = [float(sub[f"umae_{r}"].median()) if f"umae_{r}" in sub else np.nan
                    for r in LADDER_RUNGS]
            best = LADDER_RUNGS[int(np.nanargmax(vals))]
            L.append(f"| {lab} (n={len(sub)}) | "
                     + " | ".join(f"{v:+.2f}" for v in vals) + f" | **{best}** |")
        L.append("")
        L.append("| name | " + " | ".join(f"{r} U_MAE (n)" for r in LADDER_RUNGS)
                 + " | best rung | W1 §2d best (fwd63) |")
        L.append("|---|" + "---|" * (len(LADDER_RUNGS) + 2))
        sec2d = {"MCD": "1W", "JNJ": "1W", "KO": "2W", "PG": "3D",
                 "PEP": "1W", "WMT": "3D", "COST": "1W"}
        for sym in DEFENSIVES:
            if sym not in lad.index:
                continue
            r = lad.loc[sym]
            cells = []
            vals = {}
            for rg in LADDER_RUNGS:
                v = r.get(f"umae_{rg}")
                if pd.notna(v):
                    vals[rg] = float(v)
                    cells.append(f"{v:+.2f} ({int(r[f'n_{rg}'])})")
                else:
                    cells.append("—")
            best = max(vals, key=vals.get) if vals else "—"
            L.append(f"| {sym} | " + " | ".join(cells)
                     + f" | **{best}** | {sec2d.get(sym, '—')} |")

    # §F MWR census re-grade
    L.append("\n## F. MWR S1-A basket census re-graded (13-signal estate)\n")
    sm, nl, members = mwr_census_regrade()
    if len(sm) and nl:
        L.append(f"Basket all-days nulls: median MAE63 {nl['mae_med']:+.2f}%, "
                 f"w5 base {nl['w5_rate']:.1f}%, called-low base {nl['called_rate']:.1f}%.\n")
        L.append("| signal | MAE63 | prox to low | td_to_trough | within 5% | "
                 "mfe21 | rc21 | label |")
        L.append("|---|---|---|---|---|---|---|---|")
        for _, r in sm.iterrows():
            lab = ("called low" if -2 <= r.tdt <= 5 else
                   "confirmed reset" if r.tdt < -2 else "early")
            L.append(f"| {str(r.date.date())} | {r.mae63:+.2f}% | {r.prox:+.2f}% | "
                     f"{r.tdt:+.0f}td | {'✓' if r.w5 else '—'} | {r.mfe21:+.2f}% | "
                     f"{r.rc21:+.2f}% | {lab} |")
        L.append(f"\nSignal medians: MAE63 {float(sm.mae63.median()):+.2f}% "
                 f"(vs base {nl['mae_med']:+.2f}%), w5 rate "
                 f"{float(sm.w5.mean() * 100):.0f}% (base {nl['w5_rate']:.1f}%), "
                 f"called-low {float(((sm.tdt >= -2) & (sm.tdt <= 5)).mean() * 100):.0f}% "
                 f"(base {nl['called_rate']:.1f}%).")
        L.append("\nPer-member (2W-A stoch, own tape): " + " · ".join(members)
                 + "\n\n(Amendment-2 live-gate HIT/FAIL rules untouched — §7 item 4; "
                   "this is the additive scorecard read on the census.)\n")

    # §G verdict scaffold
    L.append("## G. Pre-stated readings → §8 verdict\n")
    L.append("R1 ruler-robustness · R2 decisive re-test (kill-row disposition) · "
             "R3 altitude · R4 engine seat · R5 product split. Adjudication lands "
             "in charter §8.\n")

    # §H limitations
    L.append("## H. Limitations\n")
    L.append("- Closes-only MAE/troughs (house shadow-book form); intraday lows "
             "are deeper — levels are comparable across arms, not absolute.")
    L.append("- ±31td proximity window is the §7 pin; longer bear legs make "
             "'the low' window-relative.")
    L.append("- Survivor tape, anchor-A 2W bars, FIT-tail spill: as W1.")
    L.append("- U_W5 is a rate on small per-name signal counts (3-15 OOS): "
             "per-name values are coarse; panel medians + month-cluster CIs "
             "carry the inference.")
    L.append("- Ladder/census re-grades are FULL-SAMPLE frames (matching the "
             "estates they re-grade), not persistence tests.")

    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    keep = [c for c in p.columns if not c.startswith("_")]
    p[keep].to_parquet(OUT_PQ, index=False)
    print(f"\nwrote {OUT_MD.relative_to(ROOT)} + {OUT_PQ.relative_to(ROOT)} ({len(p)} names)")


if __name__ == "__main__":
    main()
