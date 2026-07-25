#!/usr/bin/env python3
"""PTT-W1 — Personality-Tailored Timing: persistence-of-fit study (THE DECISIVE STUDY).

PRE-REGISTRATION — this header is the pinned ruler, committed BEFORE any outcome
was computed (MWR precedent: ruler pre-stated in the script, results land after).
Any post-first-run change is an AMENDMENT and must be disclosed in the report.
Charter: research/PERSONALITY_TIMING_TAILORING_HANDOFF_FOR_FABLE.md §2 (v2, #3417).
Trial-ledger family: personality_timing_w1 (registered in data/trial_ledger.jsonl
in the same pre-run commit as this file).

QUESTION. Is per-stock timing-tool fit persistent out-of-sample, and at what
altitude (name vs class vs global)? Run as a head-to-head of fitting METHODS:
  W1a  audition-tailoring — in-sample best of 6 tools by OUTCOME (overfit-prone
       baseline; 6-way selection multiplicity is the studied object, disclosed).
  W1b  structure-tailoring — the operator's "measure the stock, don't audition
       the wardrobe" method formalized: rung DERIVED mechanically from bars-only
       structure; outcomes only VALIDATE, never select (pure arm) or select only
       the 2-way family choice (hybrid arm, disclosed).

MEASUREMENT AMENDMENT LOG (all PRE-OUTCOME — measurement-stage distribution
diagnostics only; no IS/OOS uplift was computed or read before the final pin):
  A1 (original pin): dominant swing period via zigzag, reversal ≥3×ATR14,
     P = 2×median leg — DEGENERATE at measurement: ATR normalization removes
     the cross-name variance the map needs (8-name probe: P≈40-50td for names
     as different as KO/MCD/TSLA/AAPL → all rungs 3D; would trip the gate).
  A2 (charter's alternative): spectral peak — periodogram argmax of
     log(close)−200d-SMA, band 20-250td, 3-bin smoothed — DEGENERATE:
     detrended price spectra are red, the argmax pins to the high-pass corner
     (30-name probe: all names → 2W).
  FINAL PIN — reversion-strength-by-scale: for each rung R, ρ_R = lag-1
     autocorrelation of BAR RETURNS on R's own bar series (bars built on the
     FULL series — anchor-A phase preserved — then sliced to the window;
     ≥60 bars FIT, ≥40 sub-windows). Derived rung = argmin ρ_R (the scale
     whose bars mean-revert hardest — the mechanism a washout oscillator
     monetizes; the scale-resolved form of §1b's mean-reversion parameter, on
     the same bar ladder as the tool grid). Unmeasurable → 1W, flagged.
     no_reversion codex flag: all ρ_R > 0 (structural "washouts continue"
     class; ~5% in a 400-name probe). Probe distribution: 1W 45% / 3D 30% /
     2W 25% — non-degenerate. MCD derives 1W from bars alone (its §2d
     empirical home rung; noted as encouraging, NOT claimed as validation —
     the OOS head-to-head below is the test).

UNIVERSE. All names in data/baskets/ohlcv with ≥2900 daily closes, first bar
≤ 2014-06-30, last AND median close ≥ $2 — byte-identical to the
mwr_phase1_conditioner_study.py filter (~1,6xx names; survivor tape, disclosed).

TOOL GRID (6, pinned; constructions identical to engine/mag7_washout.py):
  families  S = Stoch-RSI(14/14/3/3 on Wilder RSI14): K crosses above D with
                prior-bar K < 20.
            M = RSI-MACD (MACD 12/26/9 computed ON RSI14): line crosses above
                signal while line < 0. No arming condition (phase-1 convention).
  rungs     3D = daily closes iloc[2::3] · 1W = W-FRI closes · 2W = W-FRI closes
            iloc[::2] (anchor-A; anchor-phase fragility disclosed, not re-tested).
Indicators are computed once on the FULL series per name (identical construction
across halves); only signal DATES are split. Signal basis = signal-date close
(census basis, as §2d / phase-1).

SPLIT (era law DT-R16; sample is entirely post-2010). FIT = signal dates
≤ 2020-06-30 · TEST = signal dates ≥ 2020-07-01 · SUB-SPLIT reported: TEST
restricted to ≥ 2021-01-01 (operator's post-2020 dissimilarity flag). Disclosed:
fwd63 of the last ~63 trading days of FIT spills into H2 — selection material
only; TEST grading is untouched by FIT selection.

OUTCOME RULER. fwd63 on daily closes (t0-close basis). Per-signal excess =
fwd63 − the name's OWN same-half all-days median fwd63 (IS baseline for IS
signals, OOS baseline for OOS signals, 2021+ baseline for the sub-split —
base-rate removed per name per half). Per-(name, tool, half) uplift = median of
per-signal excesses. Registered horizons: fwd63 (primary, decision-bearing);
fwd126 (secondary, DESCRIPTIVE ONLY, reported for the low-vol tercile — the
§2d defensive-compounder flag; no decision reads it).

ELIGIBILITY. A name enters the panel iff ALL 6 tools have ≥3 FIT signals and
≥3 TEST signals with resolvable fwd63. Excluded counts + the tilt of exclusion
(trend/vol of excluded vs included) are printed — the M@2W rung is expected to
be the binding constraint; disclosed, not corrected. Charter-exhibit names that
fall to eligibility (e.g. NVDA if so) are named in §D.

ARMS (per name; all graded on TEST uplift; tie-breaks = first in pinned tool
order S3D S1W S2W M3D M1W M2W):
  (a)   W1a tailored: argmax FIT uplift over all 6 tools.
  (a')  W1b-pure:    (derived rung, family S). ZERO outcome input.
  (a'') W1b-hybrid:  derived rung; family = better FIT uplift of {S, M} at that
        rung (2-way audition vs W1a's 6-way, disclosed).
  (b)   global one-size: argmax over tools of the panel-wide median of per-name
        FIT uplifts (one tool for everyone).
  (c)   class-best: within-class argmax of median member FIT uplift; class needs
        ≥8 panel names else falls back to the global tool.
        PRIMARY class lens = vol-tercile × trend-tercile cells measured on FIT
        bars only (charter fallback lens, forced primary by coverage: archetype
        PIT covers ~177 of ~1,6xx panel names at 2020-06-30 — disclosed).
        SECONDARY lens = archetype from personality_pit_labels.parquet, last
        non-null row ≤ 2020-06-30 (PIT), covered subset only, reported apart.
  (d)   random floor: per-name MEAN of all 6 tools' TEST uplifts (= exact
        expectation of a uniform random tool draw; no seed noise).

W1b PROFILE EXTRAS (codex columns; NOT decision inputs): OU/AR(1) half-life on
log(close/SMA200); trend persistence (share of days > SMA200); vol-cluster
timescale (AR(1) half-life of squared daily returns); ann. vol.
NON-DEGENERACY GATE (measurement-only, runs BEFORE any outcome is read): if
>90% of measured names map to one rung, the script ABORTS after writing the
measurement distribution — a further amendment would be made and disclosed
BEFORE outcomes are ever computed.
STATIONARITY. stationarity_fit = mean |Δρ_R| across the 3 rungs between FIT
sub-halves (2014→2017-03-31 vs 2017-04-01→2020-06-30) — PIT at the boundary;
low = stationary; conflates true drift with estimation noise (disclosed;
terciles are relative reads). Stratifies the TEST report. stationarity_full =
same between FIT and TEST bars — codex column ONLY, never stratifies a
decision metric (it uses test-period bars).

METRICS (pooled inference = month-cluster bootstrap, cluster = signal calendar
month, NB=1000 draws, RNG seed 20260726 — DT-R14: ticker-only clustering is a
forbidden estimator; names are not independent, signals cluster on dates):
  1. per-arm panel median TEST uplift (+ bootstrap 95% CI) — full TEST + 2021+.
  2. pairwise differences with CIs: (a)−(b), (a)−(c), (c)−(b), (a')−(a),
     (a')−(b), (a'')−(b), (a'')−(a), and each arm −(d). Name-level medians are
     PRIMARY; pooled signal-level medians are the phase-1-house-form robustness
     read.
  3. persistence diagnostics: per-name Spearman(FIT tool ranks, TEST tool ranks)
     distribution; fraction of names whose FIT-best tool lands in the TEST top-2
     (chance = 2/6 = 33.3%).
  4. W1b-pure TEST uplift by stationarity_fit tercile + by the no_reversion flag.
  5. rung-map distribution + named examples (MCD JNJ KO PG PEP WMT COST NVDA
     TSLA AAPL MSFT) vs the §2d ladder reads.
  All nulls printed; no cell dropped.

PRE-STATED READINGS (charter §2 verbatim, operationalized: "X > Y" = point
difference positive AND month-cluster 95% CI excludes 0; "≈" = CI includes 0):
  tailored > class > global   ⇒ per-name altitude earned → proceed §4 fully.
  class > global ≈ tailored   ⇒ the altitude is the CLASS → class profiles;
                                per-name display-tier only.
  tailored ≤ random-ish       ⇒ tool tailoring is noise → personality work stays
                                at the setup-compat/context tier.
  W1b > W1a                   ⇒ structure-fitting (measurement) beats audition →
                                becomes the Prophet tailoring engine (W3/W4).
  W1b ≥ class                 ⇒ structure-fitting earns the engine seat (charter).
  Stationarity gradient (stationary tercile > shape-shifter tercile for W1b)
  ⇒ the codex shrinkage weight is earned.

REGISTRY COMPLIANCE. DT-R14 month-cluster inference · DT-R16 era split · TI-R2
cited (per-name TIMING PROFILES are a different object from the deferred
business-model exposure tags; no tags are created here) · DNR §1 untouched (no
LLM-originated anything — deterministic arithmetic; no graded-board writes; no
positioning fusion) · 63d apparatus at its registered horizon, fwd126 registered
here as descriptive-only · display-tier artifact (panel parquet) ships freely;
NOTHING here promotes any tool to authority — that requires its own prereg.

Outputs: reports/ptt_w1_persistence_of_fit.md + data/research/ptt_w1_panel.parquet.
Run: python3 scripts/research/ptt_w1_persistence_of_fit.py  (~5-10 min)
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from engine.mag7_washout import stoch_rsi, rsi_macd, cross_up  # noqa: E402

RNG = np.random.default_rng(20260726)
OHLCV = ROOT / "data" / "baskets" / "ohlcv"
LABELS = ROOT / "data" / "research" / "personality_pit_labels.parquet"
OUT_MD = ROOT / "reports" / "ptt_w1_persistence_of_fit.md"
OUT_PQ = ROOT / "data" / "research" / "ptt_w1_panel.parquet"

H = 63
H126 = 126
SPLIT = pd.Timestamp("2020-06-30")      # FIT = signal dates <= SPLIT
OOS_START = pd.Timestamp("2020-07-01")  # TEST = signal dates >= OOS_START
SUB2021 = pd.Timestamp("2021-01-01")
SUBA_END = pd.Timestamp("2017-03-31")   # FIT sub-halves for stationarity_fit

RUNGS = ["3D", "1W", "2W"]
FAMS = ["S", "M"]
TOOLS = [f"{f}{r}" for f in FAMS for r in RUNGS]  # pinned tie-break order
MIN_SIG = 3          # per tool per half
MIN_CLASS = 8        # names per class cell for a class-best tool
NB = 1000            # bootstrap draws
MIN_BARS_FIT = 60    # bars needed for a FIT-window rho
MIN_BARS_SUB = 40    # bars needed for a sub-window rho
DEGEN_SHARE = 0.90   # non-degeneracy gate on the rung map
EXAMPLES = ["MCD", "JNJ", "KO", "PG", "PEP", "WMT", "COST",
            "NVDA", "TSLA", "AAPL", "MSFT"]


# ── constructions ──────────────────────────────────────────────────────────

def bars_for(close: pd.Series, rung: str) -> pd.Series:
    if rung == "3D":
        return close.iloc[2::3]
    if rung == "1W":
        return close.resample("W-FRI").last().dropna()
    return close.resample("W-FRI").last().dropna().iloc[::2]  # 2W anchor-A


def tool_dates(bars: pd.Series, fam: str) -> list[pd.Timestamp]:
    if fam == "S":
        k, d = stoch_rsi(bars)
        sig = (cross_up(k, d) & (k.shift() < 20)).fillna(False)
    else:
        line, s = rsi_macd(bars)
        sig = (cross_up(line, s) & (line < 0)).fillna(False)
    return list(bars.index[sig])


def fwd_ret(close: pd.Series, when: pd.Timestamp, h: int) -> float | None:
    i = close.index.searchsorted(when)
    if i + h >= len(close):
        return None
    return float(close.iloc[i + h] / close.iloc[i] - 1) * 100


def half_baseline(close: pd.Series, lo: pd.Timestamp | None,
                  hi: pd.Timestamp | None, h: int) -> float:
    f = (close.shift(-h) / close - 1) * 100
    if lo is not None:
        f = f[f.index >= lo]
    if hi is not None:
        f = f[f.index <= hi]
    return float(f.dropna().median())


# ── W1b structure measurement (bars only; FINAL PIN per amendment log) ─────

def rho_window(bars: pd.Series, lo: pd.Timestamp | None, hi: pd.Timestamp | None,
               min_bars: int) -> float:
    b = bars
    if lo is not None:
        b = b[b.index >= lo]
    if hi is not None:
        b = b[b.index <= hi]
    rets = b.pct_change().dropna()
    if len(rets) < min_bars:
        return float("nan")
    return float(rets.autocorr(1))


def rung_from_rhos(rhos: dict[str, float]) -> tuple[str, bool]:
    """Derived rung = argmin rho (pinned order breaks exact ties); measured flag."""
    s = pd.Series({r: rhos.get(r, np.nan) for r in RUNGS})[RUNGS]
    if s.isna().any():
        return "1W", False  # pinned fallback: middle rung, flagged upstream
    return str(s.idxmin()), True


def ou_halflife(close: pd.Series) -> float:
    ma = close.rolling(200).mean()
    z = np.log(close / ma).dropna()
    if len(z) < 260:
        return float("nan")
    dz = z.diff().dropna()
    zl = z.shift().dropna().reindex(dz.index)
    b = float(np.polyfit(zl.to_numpy(), dz.to_numpy(), 1)[0])
    if -1 < b < 0:
        return float(min(-np.log(2) / np.log(1 + b), 500.0))
    return 500.0


def volcluster_halflife(close: pd.Series) -> float:
    r2 = close.pct_change().dropna() ** 2
    if len(r2) < 260:
        return float("nan")
    rho = float(r2.autocorr(1))
    if 0 < rho < 1:
        return float(min(-np.log(2) / np.log(rho), 500.0))
    return float("nan")


# ── per-name computation ───────────────────────────────────────────────────

def load_name(f: Path) -> dict | None:
    px = pd.read_parquet(f)["close"].dropna()
    if len(px) < 2900 or px.index[0] > pd.Timestamp("2014-06-30"):
        return None
    if float(px.iloc[-1]) < 2 or float(px.median()) < 2:
        return None

    base = {
        "is63": half_baseline(px, None, SPLIT, H),
        "oos63": half_baseline(px, OOS_START, None, H),
        "oos21_63": half_baseline(px, SUB2021, None, H),
        "is126": half_baseline(px, None, SPLIT, H126),
        "oos126": half_baseline(px, OOS_START, None, H126),
    }
    bars_full = {r: bars_for(px, r) for r in RUNGS}

    sig_rows, up = [], {}
    for tool in TOOLS:
        fam, rung = tool[0], tool[1:]
        dates = tool_dates(bars_full[rung], fam)
        is_ex, oos_ex, oos21_ex = [], [], []
        for t in dates:
            v = fwd_ret(px, t, H)
            if v is None:
                continue
            v126 = fwd_ret(px, t, H126)
            if t <= SPLIT:
                is_ex.append(v - base["is63"])
            else:
                e = v - base["oos63"]
                oos_ex.append(e)
                if t >= SUB2021:
                    oos21_ex.append(v - base["oos21_63"])
                sig_rows.append({
                    "sym": f.stem, "tool": tool, "date": t,
                    "month": str(t)[:7], "excess": e,
                    "excess21": (v - base["oos21_63"]) if t >= SUB2021 else np.nan,
                    "excess126": (v126 - base["oos126"]) if v126 is not None else np.nan,
                    "sub21": bool(t >= SUB2021),
                })
        if len(is_ex) < MIN_SIG or len(oos_ex) < MIN_SIG:
            return {"sym": f.stem, "eligible": False,
                    "trend_all": float((px > px.rolling(200).mean()).mean()),
                    "vol_all": float(px.pct_change().std() * np.sqrt(252) * 100)}
        up[f"is_{tool}"] = float(np.median(is_ex))
        up[f"oos_{tool}"] = float(np.median(oos_ex))
        up[f"oos21_{tool}"] = float(np.median(oos21_ex)) if oos21_ex else np.nan
        up[f"n_is_{tool}"] = len(is_ex)
        up[f"n_oos_{tool}"] = len(oos_ex)

    # structure: rho per rung per window (bars from FULL series — anchor kept)
    rho_fit = {r: rho_window(bars_full[r], None, SPLIT, MIN_BARS_FIT) for r in RUNGS}
    rho_a = {r: rho_window(bars_full[r], None, SUBA_END, MIN_BARS_SUB) for r in RUNGS}
    rho_b = {r: rho_window(bars_full[r], SUBA_END + pd.Timedelta(days=1), SPLIT,
                           MIN_BARS_SUB) for r in RUNGS}
    rho_t = {r: rho_window(bars_full[r], OOS_START, None, MIN_BARS_FIT) for r in RUNGS}
    rung, measured = rung_from_rhos(rho_fit)
    rung_a, meas_a = rung_from_rhos(rho_a)
    rung_b, meas_b = rung_from_rhos(rho_b)

    def drift(x: dict, y: dict) -> float:
        d = [abs(x[r] - y[r]) for r in RUNGS
             if np.isfinite(x.get(r, np.nan)) and np.isfinite(y.get(r, np.nan))]
        return float(np.mean(d)) if len(d) == len(RUNGS) else float("nan")

    fit_px = px[px.index <= SPLIT]
    return {
        "sym": f.stem, "eligible": True, **up,
        "rho_3D": rho_fit["3D"], "rho_1W": rho_fit["1W"], "rho_2W": rho_fit["2W"],
        "rung_derived": rung, "p_measured": measured,
        "no_reversion": bool(measured and all(rho_fit[r] > 0 for r in RUNGS)),
        "ou_hl": ou_halflife(fit_px),
        "trend": float((fit_px > fit_px.rolling(200).mean()).mean()),
        "volcl_hl": volcluster_halflife(fit_px),
        "vol": float(fit_px.pct_change().std() * np.sqrt(252) * 100),
        "rung_subA": rung_a if meas_a else None,
        "rung_subB": rung_b if meas_b else None,
        "stationarity_fit": drift(rho_a, rho_b),
        "stationarity_full": drift(rho_fit, rho_t),
        "_sig_rows": sig_rows,
    }


# ── arm assignment ─────────────────────────────────────────────────────────

def argmax_tool(series_by_tool: dict[str, float], tools: list[str]) -> str:
    s = pd.Series({t: series_by_tool.get(t, np.nan) for t in tools})[tools]
    return str(s.idxmax())


def assign_arms(panel: pd.DataFrame) -> pd.DataFrame:
    p = panel.copy()
    # (a) W1a — 6-way audition
    p["tool_w1a"] = p.apply(lambda r: argmax_tool({t: r[f"is_{t}"] for t in TOOLS}, TOOLS), axis=1)
    # (a') W1b-pure — derived rung, family S, zero outcome input
    p["tool_w1b_pure"] = "S" + p["rung_derived"]
    # (a'') W1b-hybrid — derived rung, 2-way family audition
    p["tool_w1b_hyb"] = p.apply(
        lambda r: argmax_tool({f + r["rung_derived"]: r[f"is_{f}{r['rung_derived']}"] for f in FAMS},
                              [f + r["rung_derived"] for f in FAMS]), axis=1)
    # (b) global one-size
    med_is = {t: float(p[f"is_{t}"].median()) for t in TOOLS}
    global_tool = argmax_tool(med_is, TOOLS)
    p["tool_global"] = global_tool
    # (c) primary class lens: vol×trend terciles on FIT measures
    p["volT"] = pd.qcut(p["vol"], 3, labels=["v0", "v1", "v2"])
    p["trendT"] = pd.qcut(p["trend"], 3, labels=["t0", "t1", "t2"])
    p["class_vt"] = p["volT"].astype(str) + "x" + p["trendT"].astype(str)
    class_tool: dict[str, str] = {}
    for cell, sub in p.groupby("class_vt"):
        if len(sub) >= MIN_CLASS:
            class_tool[cell] = argmax_tool({t: float(sub[f"is_{t}"].median()) for t in TOOLS}, TOOLS)
        else:
            class_tool[cell] = global_tool
    p["tool_class"] = p["class_vt"].map(class_tool)
    # (c-secondary) archetype PIT lens, covered subset
    if LABELS.exists():
        lab = pd.read_parquet(LABELS, columns=["ticker", "date", "archetype"])
        lab = lab[(lab.date <= SPLIT) & lab.archetype.notna()]
        arch = lab.sort_values("date").groupby("ticker").archetype.last()
        p["archetype"] = p["sym"].map(arch)
    else:
        p["archetype"] = None
    arch_tool: dict[str, str] = {}
    for cell, sub in p[p.archetype.notna()].groupby("archetype"):
        if len(sub) >= MIN_CLASS:
            arch_tool[cell] = argmax_tool({t: float(sub[f"is_{t}"].median()) for t in TOOLS}, TOOLS)
    p["tool_arch"] = p["archetype"].map(arch_tool)  # NaN where class too small / uncovered
    # per-name arm OOS values
    for arm, col in [("w1a", "tool_w1a"), ("w1b_pure", "tool_w1b_pure"),
                     ("w1b_hyb", "tool_w1b_hyb"), ("global", "tool_global"),
                     ("class", "tool_class")]:
        p[f"oos_{arm}"] = p.apply(lambda r, c=col: r[f"oos_{r[c]}"], axis=1)
        p[f"oos21_{arm}"] = p.apply(lambda r, c=col: r[f"oos21_{r[c]}"], axis=1)
    p["oos_arch"] = p.apply(
        lambda r: r[f"oos_{r['tool_arch']}"] if isinstance(r["tool_arch"], str) else np.nan, axis=1)
    # random floor = exact mean of ALL 6 tools (skipna=False: a name missing any
    # 2021+ tool value drops from the 2021+ random floor rather than silently
    # averaging over fewer than 6 tools — disclosed in §A)
    p["oos_random"] = p[[f"oos_{t}" for t in TOOLS]].mean(axis=1, skipna=False)
    p["oos21_random"] = p[[f"oos21_{t}" for t in TOOLS]].mean(axis=1, skipna=False)
    return p


# ── persistence diagnostics ────────────────────────────────────────────────

def persistence(p: pd.DataFrame) -> dict:
    spear, top2 = [], []
    for _, r in p.iterrows():
        is_v = pd.Series({t: r[f"is_{t}"] for t in TOOLS})
        oos_v = pd.Series({t: r[f"oos_{t}"] for t in TOOLS})
        spear.append(float(is_v.corr(oos_v, method="spearman")))
        top2.append(r["tool_w1a"] in list(oos_v.sort_values(ascending=False).index[:2]))
    s = pd.Series(spear).dropna()
    return {"spear_med": float(s.median()), "spear_frac_pos": float((s > 0).mean()),
            "top2_frac": float(np.mean(top2)), "n": len(p)}


# ── month-cluster bootstrap ────────────────────────────────────────────────

ARMS = ["w1a", "w1b_pure", "w1b_hyb", "global", "class"]


def bootstrap(p: pd.DataFrame, sig: pd.DataFrame, sub21: bool = False) -> dict:
    """Month-cluster bootstrap of panel-median arm uplifts + differences.
    Name-level primary: per draw, per-name arm value = median of its arm-tool's
    signals in drawn months; panel median across names. Pool secondary: median
    of pooled per-signal excess for rows matching each arm's (name, tool)."""
    if sub21:
        s = sig[sig.sub21].copy()
        s["excess"] = s["excess21"]  # 2021+ levels graded vs the 2021+ baseline
    else:
        s = sig.copy()
    tool_col = {a: f"tool_{a}" if a != "class" else "tool_class" for a in ARMS}
    pair = {a: set(zip(p["sym"], p[tool_col[a]])) for a in ARMS}
    for a in ARMS:
        s[f"in_{a}"] = [(y, t) in pair[a] for y, t in zip(s["sym"], s["tool"])]
    months = sorted(s["month"].unique())
    by_month = {m: g for m, g in s.groupby("month")}
    # ≥50%-names draw guard measured against each arm's own eligible population
    # (2021+ sub-split: only names whose arm value exists there — reviewer M2)
    if sub21:
        ref = {a: int(p[f"oos21_{a}"].notna().sum()) for a in ARMS}
        ref["random"] = int(p["oos21_random"].notna().sum())
    else:
        ref = {a: len(p) for a in ARMS}
        ref["random"] = len(p)
    stats: dict[str, list[float]] = {}

    def add(key: str, val: float) -> None:
        stats.setdefault(key, []).append(val)

    for _ in range(NB):
        pick = RNG.choice(months, size=len(months), replace=True)
        boot = pd.concat([by_month[m] for m in pick])
        med = boot.groupby(["sym", "tool"]).excess.median()
        med_d = med.to_dict()  # O(1) lookups — MultiIndex .get is too slow here
        vals = {}
        for a in ARMS:
            per_name = []
            for y, t in pair[a]:
                v = med_d.get((y, t))
                if v is not None and np.isfinite(v):
                    per_name.append(v)
            vals[a] = float(np.median(per_name)) if len(per_name) >= ref[a] * 0.5 else np.nan
        # random floor: strict mean over ALL 6 tools (skipna=False — matches the
        # §A point estimand; names missing any tool in the draw drop out)
        mm = (med.reset_index().pivot(index="sym", columns="tool", values="excess")
              .reindex(columns=TOOLS))
        rnd = mm.mean(axis=1, skipna=False).dropna()
        vals["random"] = (float(rnd.median())
                          if len(rnd) >= ref["random"] * 0.5 else np.nan)
        for a, v in vals.items():
            add(a, v)
        for x, y in [("w1a", "global"), ("w1a", "class"), ("class", "global"),
                     ("w1b_pure", "w1a"), ("w1b_pure", "global"), ("w1b_hyb", "global"),
                     ("w1a", "random"), ("w1b_pure", "random"), ("class", "random"),
                     ("global", "random"), ("w1b_hyb", "random"), ("w1b_hyb", "w1a")]:
            add(f"{x}-{y}", vals[x] - vals[y])
        for a in ARMS:
            add(f"pool_{a}", float(boot.loc[boot[f"in_{a}"], "excess"].median()))
        add("pool_w1a-global", float(boot.loc[boot.in_w1a, "excess"].median()
                                     - boot.loc[boot.in_global, "excess"].median()))
        add("pool_w1b_pure-global", float(boot.loc[boot.in_w1b_pure, "excess"].median()
                                          - boot.loc[boot.in_global, "excess"].median()))
    return {k: (float(np.nanpercentile(v, 2.5)), float(np.nanpercentile(v, 97.5)))
            for k, v in stats.items()}


# ── report ─────────────────────────────────────────────────────────────────

def ci_str(ci: tuple[float, float] | None) -> str:
    if not ci or not np.isfinite(ci[0]):
        return "[—]"
    return f"[{ci[0]:+.2f}, {ci[1]:+.2f}]"


def main() -> None:
    files = sorted(OHLCV.glob("*.parquet"))
    rows, excluded, sig_all, failed = [], [], [], []
    for f in files:
        try:
            r = load_name(f)
        except Exception as e:  # noqa: BLE001 — counted, never silent
            failed.append(f"{f.stem}: {type(e).__name__}")
            continue
        if r is None:
            continue
        if not r["eligible"]:
            excluded.append(r)
            continue
        sig_all.extend(r.pop("_sig_rows"))
        rows.append(r)
    panel = pd.DataFrame(rows)
    sig = pd.DataFrame(sig_all)
    exc = pd.DataFrame(excluded)

    # ── non-degeneracy gate (measurement-only; runs before outcomes are read)
    measured = panel[panel.p_measured]
    rung_share = measured["rung_derived"].value_counts(normalize=True)
    if len(rung_share) and float(rung_share.iloc[0]) > DEGEN_SHARE:
        OUT_MD.write_text(
            "# PTT-W1 — ABORTED at the non-degeneracy gate (pre-outcome)\n\n"
            f"Rung map degenerate: {rung_share.to_dict()} — >{DEGEN_SHARE:.0%} of "
            "measured names map to one rung. A further measurement amendment "
            "would be pinned and disclosed BEFORE outcomes are computed. "
            "No outcome was read.\n",
            encoding="utf-8")
        print("ABORT: degenerate rung map", rung_share.to_dict())
        sys.exit(2)

    p = assign_arms(panel)
    pers = persistence(p)
    ci = bootstrap(p, sig, sub21=False)
    ci21 = bootstrap(p, sig, sub21=True)

    L: list[str] = []
    L.append("# PTT-W1 — persistence-of-fit: audition vs structure vs class vs global\n")
    L.append(f"Pre-registered ruler: script header (committed pre-run; measurement "
             f"amendment log A1/A2 disclosed there — both pre-outcome). Universe: "
             f"{len(p)} eligible names (ALL 6 tools ≥{MIN_SIG} FIT + ≥{MIN_SIG} TEST "
             f"signals); {len(exc)} names excluded by eligibility; "
             f"{len(files)} files scanned; load failures: {len(failed)}"
             + (f" ({'; '.join(failed[:5])}{'…' if len(failed) > 5 else ''})" if failed else "")
             + f". Signals pooled (TEST): {len(sig):,}. "
             f"Split: FIT ≤ {SPLIT.date()} · TEST ≥ {OOS_START.date()} "
             f"(sub-split ≥ {SUB2021.date()}). Uplift = median signal fwd63 − "
             f"own-half all-days median fwd63 (%). Random floor = strict mean of "
             f"all 6 tools (a name missing any 2021+ tool value drops from the "
             f"2021+ random floor — no partial averages).\n")
    if len(exc):
        L.append(f"Eligibility tilt (disclosed): included median trend "
                 f"{p['trend'].median():.2f} / vol {p['vol'].median():.0f}% vs excluded "
                 f"{exc['trend_all'].median():.2f} / {exc['vol_all'].median():.0f}%. "
                 f"Charter-exhibit names excluded: "
                 + (", ".join(s for s in EXAMPLES if s in set(exc['sym'])) or "none")
                 + ".\n")

    # §A arms
    L.append("## A. Arms — panel median TEST uplift (name-level primary)\n")
    L.append("| arm | tool policy | median OOS uplift | 95% CI (month-cluster) | "
             "median 2021+ | CI 2021+ |")
    L.append("|---|---|---|---|---|---|")
    arm_label = {
        "w1a": "(a) W1a audition-tailored (6-way IS best)",
        "w1b_pure": "(a′) W1b-pure structure (derived rung, S)",
        "w1b_hyb": "(a″) W1b-hybrid (derived rung, 2-way family)",
        "global": "(b) global one-size",
        "class": "(c) class-best (vol×trend cells)",
    }
    for a in ARMS:
        med = float(p[f"oos_{a}"].median())
        med21 = float(p[f"oos21_{a}"].dropna().median())
        L.append(f"| {arm_label[a]} | per name | {med:+.2f}% | {ci_str(ci.get(a))} | "
                 f"{med21:+.2f}% | {ci_str(ci21.get(a))} |")
    L.append(f"| (d) random floor | mean of 6 tools | "
             f"{float(p['oos_random'].median()):+.2f}% | {ci_str(ci.get('random'))} | "
             f"{float(p['oos21_random'].dropna().median()):+.2f}% | "
             f"{ci_str(ci21.get('random'))} |")
    gt = p["tool_global"].iloc[0]
    L.append(f"\nGlobal one-size tool selected in FIT: **{gt}**. W1a FIT selections: "
             + ", ".join(f"{t} {n}" for t, n in p['tool_w1a'].value_counts().items())
             + ". Class-cell tools: "
             + ", ".join(f"{c}→{t}" for c, t in sorted(
                   p.groupby('class_vt')['tool_class'].first().items())) + ".\n")

    # §B decision block
    L.append("## B. Pairwise differences (decision block; name-level medians, "
             "month-cluster 95% CI)\n")
    L.append("| comparison | point | 95% CI | reads |")
    L.append("|---|---|---|---|")
    def diff_row(x: str, y: str, label: str) -> None:
        xs = p[f"oos_{x}"] if x != "random" else p["oos_random"]
        ys = p[f"oos_{y}"] if y != "random" else p["oos_random"]
        d = float(xs.median() - ys.median())
        c = ci.get(f"{x}-{y}")
        verdict = ("excludes 0 ↑" if c and c[0] > 0 else
                   "excludes 0 ↓" if c and c[1] < 0 else "includes 0")
        L.append(f"| {label} | {d:+.2f}% | {ci_str(c)} | {verdict} |")
    diff_row("w1a", "global", "(a) tailored − (b) global")
    diff_row("w1a", "class", "(a) tailored − (c) class")
    diff_row("class", "global", "(c) class − (b) global")
    diff_row("w1b_pure", "w1a", "(a′) W1b-pure − (a) W1a")
    diff_row("w1b_hyb", "w1a", "(a″) W1b-hybrid − (a) W1a")
    diff_row("w1b_pure", "global", "(a′) W1b-pure − (b) global")
    diff_row("w1b_hyb", "global", "(a″) W1b-hybrid − (b) global")
    diff_row("w1a", "random", "(a) − (d) random floor")
    diff_row("w1b_pure", "random", "(a′) − (d) random floor")
    diff_row("w1b_hyb", "random", "(a″) − (d) random floor")
    diff_row("class", "random", "(c) − (d) random floor")
    diff_row("global", "random", "(b) − (d) random floor")
    tool_col = {a: f"tool_{a}" if a != "class" else "tool_class" for a in ARMS}
    pool_pt = {}
    for a in ARMS:
        pr = set(zip(p["sym"], p[tool_col[a]]))
        pool_pt[a] = float(sig[[(y, t) in pr for y, t in
                                zip(sig["sym"], sig["tool"])]].excess.median())
    L.append("\nPooled signal-level robustness (phase-1 house form) — per-arm "
             "pooled median excess (CI): "
             + " · ".join(f"{a} {pool_pt[a]:+.2f}% {ci_str(ci.get(f'pool_{a}'))}"
                          for a in ARMS)
             + f". Diffs: W1a−global {ci_str(ci.get('pool_w1a-global'))}; "
               f"W1b-pure−global {ci_str(ci.get('pool_w1b_pure-global'))}.\n")

    # §C persistence diagnostics
    L.append("## C. Is IS tool-fit persistent at the name level?\n")
    L.append(f"- Per-name Spearman(FIT tool ranks, TEST tool ranks): median "
             f"**{pers['spear_med']:+.3f}**; {pers['spear_frac_pos']:.0%} of names "
             f"positive (n={pers['n']}; 0 = no persistence; Spearman over 6 tool "
             f"ranks is coarse by construction — read with the top-2 fraction).")
    L.append(f"- FIT-best tool lands in TEST top-2: **{pers['top2_frac']:.1%}** "
             f"(chance = 33.3%).\n")

    # §D W1b measurement
    L.append("## D. W1b structure measurement (bars-only, reversion-by-scale)\n")
    L.append(f"Rung-map distribution (measured names, n={len(measured)}): "
             + ", ".join(f"{r} {v:.0%}" for r, v in rung_share.items())
             + f"; unmeasurable → 1W fallback: {int((~panel.p_measured).sum())} names. "
               f"Non-degeneracy gate (≤{DEGEN_SHARE:.0%} single-rung share): PASSED. "
               f"no_reversion flag (all ρ>0): {int(panel.no_reversion.sum())} names "
               f"({float(panel.no_reversion.mean()):.1%}).")
    L.append(f"Panel median ρ by rung: 3D {float(panel.rho_3D.median()):+.3f} · "
             f"1W {float(panel.rho_1W.median()):+.3f} · "
             f"2W {float(panel.rho_2W.median()):+.3f}.\n")
    L.append("| name | ρ3D | ρ1W | ρ2W | derived rung | W1b-pure OOS | W1a tool | "
             "W1a OOS | best OOS tool (hindsight) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for sym in EXAMPLES:
        if sym not in set(p["sym"]):
            continue
        r = p[p.sym == sym].iloc[0]
        oos_v = pd.Series({t: r[f"oos_{t}"] for t in TOOLS})
        L.append(f"| {sym} | {r.rho_3D:+.3f} | {r.rho_1W:+.3f} | {r.rho_2W:+.3f} | "
                 f"{r.rung_derived} | {r.oos_w1b_pure:+.2f}% | {r.tool_w1a} | "
                 f"{r.oos_w1a:+.2f}% | {oos_v.idxmax()} {oos_v.max():+.2f}% |")

    # §E stationarity stratification
    L.append("\n## E. Stationarity (befriendability) stratification\n")
    st = p[np.isfinite(p.stationarity_fit)].copy()
    if len(st) >= 30:
        st["stT"] = pd.qcut(st["stationarity_fit"], 3,
                            labels=["stationary", "mid", "shape-shifter"])
        L.append("| stationarity_fit tercile (mean |Δρ| FIT sub-halves) | names | "
                 "W1b-pure median OOS | W1a median OOS | rung subA==subB |")
        L.append("|---|---|---|---|---|")
        for lab in ["stationary", "mid", "shape-shifter"]:
            sub = st[st.stT == lab]
            agree = (sub.rung_subA == sub.rung_subB).mean()
            L.append(f"| {lab} | {len(sub)} | {float(sub.oos_w1b_pure.median()):+.2f}% | "
                     f"{float(sub.oos_w1a.median()):+.2f}% | {agree:.0%} |")
        nr = p[p.no_reversion]
        if len(nr):
            L.append(f"\nno_reversion names (n={len(nr)}): W1b-pure median OOS "
                     f"{float(nr.oos_w1b_pure.median()):+.2f}% vs panel "
                     f"{float(p.oos_w1b_pure.median()):+.2f}% (structural "
                     f"'washouts continue' class — codex flag).")
        L.append(f"\n(stationarity_full — FIT vs TEST drift — is emitted to the panel "
                 f"parquet as a codex column only; it uses test bars and never "
                 f"stratifies a decision metric here. Names with unmeasured drift: "
                 f"{int((~np.isfinite(p.stationarity_fit)).sum())}.)\n")

    # §F archetype secondary lens
    L.append("## F. Archetype PIT lens (secondary; covered subset only)\n")
    cov = p[p.tool_arch.notna()]
    L.append(f"Coverage: {int(p.archetype.notna().sum())} of {len(p)} panel names "
             f"carry an archetype at {SPLIT.date()}; {len(cov)} sit in classes with "
             f"≥{MIN_CLASS} names.")
    if len(cov) >= 30:
        sub = cov
        d_ag = float(sub.oos_arch.median() - sub.oos_global.median())
        d_at = float(sub.oos_arch.median() - sub.oos_w1a.median())
        L.append(f"On that subset: archetype-class arm median OOS "
                 f"{float(sub.oos_arch.median()):+.2f}% vs global "
                 f"{float(sub.oos_global.median()):+.2f}% (Δ {d_ag:+.2f}%) vs W1a "
                 f"{float(sub.oos_w1a.median()):+.2f}% (Δarch−W1a {d_at:+.2f}%). "
                 f"Class tools: "
                 + ", ".join(f"{k}→{v}" for k, v in sorted(
                       cov.groupby('archetype')['tool_arch'].first().items()))
                 + ". Descriptive (no CI — subset too small for month-cluster "
                   "power; disclosed).\n")
    else:
        L.append("Subset too small for any read — null printed, not hidden.\n")

    # §G fwd126 descriptive (low-vol stratum)
    L.append("## G. fwd126 descriptive — low-vol tercile only (registered "
             "secondary; no decision reads this)\n")
    lowv = p[p.volT == "v0"]
    s126 = sig[sig.sym.isin(set(lowv.sym)) & np.isfinite(sig.excess126)]
    if len(s126):
        pair_b = set(zip(lowv.sym, lowv.tool_w1b_pure))
        pair_g = set(zip(lowv.sym, lowv.tool_global))
        m_b = s126[[(y, t) in pair_b for y, t in zip(s126.sym, s126.tool)]].excess126.median()
        m_g = s126[[(y, t) in pair_g for y, t in zip(s126.sym, s126.tool)]].excess126.median()
        L.append(f"Low-vol tercile ({len(lowv)} names): pooled median excess fwd126 — "
                 f"W1b-pure {float(m_b):+.2f}% vs global {float(m_g):+.2f}%.\n")

    # §H verdict scaffold (filled by the adjudicating session)
    L.append("## H. Pre-stated readings → verdict\n")
    L.append("Ruler (header, pinned): tailored>class>global ⇒ per-name altitude; "
             "class>global≈tailored ⇒ class altitude; tailored≤random ⇒ tool "
             "tailoring is noise. W1b>W1a ⇒ structure-fitting becomes the engine; "
             "W1b≥class ⇒ engine seat. Adjudication lands in the charter §6 "
             "(research/PERSONALITY_TIMING_TAILORING_HANDOFF_FOR_FABLE.md).\n")

    # §I limitations
    L.append("## I. Limitations (standing)\n")
    L.append("- Survivor tape: data/baskets/ohlcv holds today's listings; per-name "
             "own-baseline netting removes level bias but not composition bias.")
    L.append("- 2W bars are anchor-A; anchor-phase fragility is a known MWR "
             "limitation, not re-tested here.")
    L.append("- FIT-tail fwd63 spills ≤63td past the split (selection material "
             "only; TEST grading unaffected).")
    L.append("- ρ at 2W rests on ~170 FIT bars (se≈0.08); the stationarity "
             "sub-halves have only ~84 2W returns each (se≈0.11) — the "
             "stationarity_fit column conflates true drift with that estimation "
             "noise; terciles are relative reads.")
    L.append("- Eligibility (≥3+≥3 on ALL 6 tools) tilts the panel — see header "
             "disclosure; M@2W is the binding rung.")
    L.append("- fwd63/fwd126 are the registered horizons; nothing else was read.")

    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))

    keep = [c for c in p.columns if not c.startswith("_")]
    p[keep].to_parquet(OUT_PQ, index=False)
    print(f"\nwrote {OUT_MD.relative_to(ROOT)} + {OUT_PQ.relative_to(ROOT)} "
          f"({len(p)} names)")


if __name__ == "__main__":
    main()
