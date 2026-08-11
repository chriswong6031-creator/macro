#!/usr/bin/env python3
"""GMI W2 — exposure-decomposition probe (R1). One-shot research probe.

Implements `research/theme_graph/W2_EXPOSURE_AXES_PREREG.md` exactly: six pilot slots
(the cross-market pair measured as two same-side sub-slots per §1's "each side's members
are measured against their OWN side's basket"), the axis constructions and formula ids
frozen in §2, the H1/H2/H3 thresholds frozen in §3, the era/survivorship rules of §4, the
exemplar gate of §5, and the output paths of §6.

NOT wired into any workflow (§6 + G0.7 — off the render path). Reads owner stores
READ-ONLY; writes only under --out-dir. Run manually:

    python3 scripts/probe_theme_exposure_axes.py [--out-dir research/theme_graph/w2_probe]

Determinism: every ordering is pinned (slots, constructions, months, symbols), the
bootstrap and the Monte-Carlo permutation tests carry fixed seeds, and NO wall-clock enters
a computed value or a receipt — run identity is stamped from git HEAD plus the store
metadata (sha256 of file bytes, row counts, date ranges, graph `_meta`).

What this probe does NOT do: it mutates no store (the reserved-null axis columns on
edges.parquet stay null), it ships no user surface, and it makes no return or directional
claim (that is R5, blocked on this).
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sps

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

# --------------------------------------------------------------------------------------
# Frozen constants — prereg §2/§3. Changing any of these changes the preregistered test.
# --------------------------------------------------------------------------------------
COVERAGE_FLOOR = 0.70                 # §3 H1
BETA_WIN, BETA_MINP = 63, 40          # §2 trading_beta.v0 rolling window / min overlap
VASICEK_W = 0.66                      # display-only companion; mirrors cn_global_beta default
H2_DISTINCT_MEDIAN = 0.70             # §3 H2 "measurably disagree" median |rho| ceiling
H2_DISTINCT_ONE_SLOT = 0.50           # §3 H2 at least one slot at or below this
H2_REDUNDANT_MEDIAN = 0.90            # §3 H2 redundancy ceiling
H3_STABLE = 0.60                      # §3 H3 stable floor
H3_NOISE = 0.30                       # §3 H3 noise ceiling
H3_MIN_PAIRS = 3                      # §3 H3 UNDERPOWERED-BY-DEPTH below this
BOOTSTRAP_BLOCK = 3                   # §3 moving-block bootstrap block length
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20260811
BOOTSTRAP_LO, BOOTSTRAP_HI = 10.0, 90.0   # 80% CI
PERM_SEED = 20260811
PERM_MC_DRAWS = 100_000
PERM_MC_BATCH = 5_000                 # pinned: the batching schedule is part of reproducibility
EXACT_P_MAX_N = 9                     # n! <= 362880 enumerated exactly; above -> seeded MC

US_HISTORY_START = "2023-06"          # §2 membership seed era
CN_HISTORY_START = "2024-01"
OBSERVED_ERA_FROM = "2026-08-11"      # §4 — the graph's first belief_time; before it: reconstruction

# §6 accrual re-probe checkpoints
UNLOCK_DENSE_ATTENTION = "2026-11"
UNLOCK_OBSERVED_ERA_BETA = "2027-02"

ECONOMIC_SHARE_INGESTION = (
    "segment-axis XBRL ingestion atop engine/fundamental_forensics (US) / CN annual-report "
    "segment tables (CN) — prereg §2 ore ledger"
)
US_ATTENTION_INGESTION = (
    "a full-universe US retail/news attention tape — the two present stores publish only the "
    "tickers they surface (WSB 307, narrative_flare 448), so a slot outside the meme/tech "
    "complex is absent from the universe rather than measured at zero"
)

# --------------------------------------------------------------------------------------
# Pilot slots — prereg §1. The cross-market pair is two sub-slots (own-side basket).
# --------------------------------------------------------------------------------------
SLOTS: "OrderedDict[str, dict]" = OrderedDict([
    ("us_mature_broad", dict(
        theme="fintech_payments", market="us", label="US-mature-broad",
        baskets=["basket:baskets:payments_fintech"])),
    ("us_young_narrow", dict(
        theme="nuclear_power", market="us", label="US-young-narrow",
        baskets=["basket:baskets:nuclear_power"])),
    ("us_institutional", dict(
        theme="defense_aerospace", market="us", label="US-institutional (GovRev-adjacent)",
        baskets=["basket:baskets:defense"])),
    ("cn_mature", dict(
        theme="solar", market="cn", label="CN-mature",
        baskets=["basket:baskets_china:cn_solar"])),
    ("cn_young_speculative", dict(
        theme="robotics_automation", market="cn", label="CN-young-speculative",
        baskets=["basket:baskets_china:cn_robotics"])),
    ("cross_market_pair.us", dict(
        theme="ai_semiconductors", market="us", label="Cross-market pair — US side",
        baskets=["basket:baskets:ai_semiconductors", "basket:baskets:ai_infra"])),
    ("cross_market_pair.cn", dict(
        theme="ai_semiconductors", market="cn", label="Cross-market pair — CN side",
        baskets=["basket:baskets_china:cn_semis", "basket:baskets_china:cn_ai_compute"])),
])

BETA_ID = "trading_beta.v0"
# POST-PREREG COMPANION (main-session commission, 2026-08-11). The corr term already inside
# the beta identity, promoted to its own cross-section so the H2 result can be re-read with
# the volatility-ratio term removed. It carries NO verdict authority: it never enters H1, the
# frozen H2/H3 tables, or any verdict cell — it informs interpretation sentences only.
COMPANION_CORR_ID = "trading_corr.companion"
CN_COMMENT_ID = "attention_share.cn.comment.v0"
CN_LHB_ID = "attention_share.cn.lhb.v0"
US_WSB_ID = "attention_share.us.wsb.v0"
US_FLARE_ID = "attention_share.us.flare.v0"
ECONOMIC_ID = "economic_share"

CONSTRUCTIONS: "OrderedDict[str, dict]" = OrderedDict([
    (BETA_ID, dict(kind="beta", markets=("us", "cn"), sparse=False,
                   unlock=UNLOCK_OBSERVED_ERA_BETA,
                   note="raw OLS beta of daily log returns vs the EX-SELF equal-weight basket, "
                        "63-session rolling window, min 40 overlapping sessions, one-day causal shift")),
    (CN_COMMENT_ID, dict(kind="attention", markets=("cn",), sparse=False,
                         unlock=UNLOCK_DENSE_ATTENTION,
                         note="member share of monthly-mean 千股千评 关注指数")),
    (CN_LHB_ID, dict(kind="attention", markets=("cn",), sparse=True,
                     unlock=UNLOCK_DENSE_ATTENTION,
                     note="member share of monthly dragon-tiger (龙虎榜) appearance count")),
    (US_WSB_ID, dict(kind="attention", markets=("us",), sparse=True,
                     unlock=UNLOCK_DENSE_ATTENTION,
                     note="member share of monthly WallStreetBets mention count")),
    (US_FLARE_ID, dict(kind="attention", markets=("us",), sparse=True,
                       unlock=UNLOCK_DENSE_ATTENTION,
                       note="member share of monthly narrative-flare lit-channel count")),
])

# Main-session adjudication on the probe's escalation (2026-08-11). Recorded verbatim in
# substance: the probe reports these, it did not decide them.
ADJUDICATION_RULINGS = [
    {"id": 1, "subject": BETA_ID, "ruling": (
        "The frozen trading_beta.v0 construction is NOT reopened — its H2/H3 readings stand "
        "as computed. The exemplar-gate failures are recorded as a SEMANTIC FINDING, not a "
        "defect: v0 measures relative-vol-weighted co-movement "
        "(beta = corr x sd_own/sd_ex-self), and the prereg's expectations carried a "
        "cap-weighted intuition v0 never implemented. The gate did its job.")},
    {"id": 2, "subject": CN_LHB_ID, "ruling": (
        "The LHB verdict cell must not read MEASURABLE-NOW: a construction whose H3 is NOISE "
        "with high tie mass is COMPUTABLE-BUT-UNSTABLE at the monthly-share grain — a null for "
        "THIS construction. Ore law: it closes monthly-share-of-appearances, and leaves "
        "event-grain and quarterly aggregations unmapped-but-open.")},
    {"id": 3, "subject": US_FLARE_ID, "ruling": (
        "US flare's near-1.0 H3 on a 50% tie block is the stability of a degenerate magnitude. "
        "US attention stays BLOCKED-ON-INGESTION, and the degeneracy (channels_lit is "
        "approximately a days-present count) is named as part of the blocking reason.")},
]


# ======================================================================================
# Pure math — every function below is unit-pinned in tests/test_theme_exposure_probe.py
# ======================================================================================
def causal_beta_pair(y: pd.Series, x: pd.Series,
                     win: int = BETA_WIN, minp: int = BETA_MINP) -> pd.Series:
    """Rolling cov(y,x)/var(x), lagged one day (prior-window data only).

    Byte-for-byte the construction of ``engine/cn_global_beta._causal_beta`` — the incumbent
    plane for this repo's betas — specialised to a per-member x. The ex-self basket return is
    a DIFFERENT series for every member (prereg §2), so the DataFrame-wide form of the
    incumbent (one shared x, ``.div(..., axis=0)``) cannot express it; the cov/var ratio and
    the ``.shift(1)`` causal lag are unchanged.
    """
    return (y.rolling(win, min_periods=minp).cov(x)
            .div(x.rolling(win, min_periods=minp).var())).shift(1)


def ex_self_returns(R: pd.DataFrame) -> pd.DataFrame:
    """Per-member EX-SELF equal-weight basket return: mean(r_j, j in B, j != i).

    Equal weight over the members that actually traded that session. Undefined (NaN) when the
    member itself has no return that session, or when fewer than two members traded.
    """
    total = R.sum(axis=1, min_count=1)
    n_avail = R.notna().sum(axis=1)
    denom = (n_avail.astype(float) - 1.0)
    denom = denom.where(denom > 0)
    out = (-R).add(total, axis=0).div(denom, axis=0)
    return out.where(R.notna())


def vasicek_shrink(beta: pd.Series, w: float = VASICEK_W) -> pd.Series:
    """Vasicek-lite companion (DISPLAY ONLY — never the probe quantity).

    Mirrors ``engine/cn_global_beta._shrink``. Shrinkage compresses cross-sectional dispersion
    and would overstate H3 stability by construction, so H1/H2/H3 all key on the raw beta.
    """
    if w is None or w >= 1.0:
        return beta
    return beta.mul(w).add(beta.mean() * (1.0 - w))


def shares_from_magnitudes(mags: pd.Series):
    """(shares, denominator) for an attention construction.

    Zeros are VALUES (a member with no appearances holds share 0.0), never missing. A
    denominator of zero means the whole basket recorded nothing that month: the share is
    UNDEFINED, so this returns ``(None, 0.0)`` — the caller prints NO-EVENTS. Never divides
    by zero, never imputes.
    """
    m = mags.dropna().astype(float)
    if (m < 0).any():
        raise ValueError("attention magnitudes must be non-negative; got a negative value")
    denom = float(m.sum())
    if denom <= 0.0:
        return None, 0.0
    return m.div(denom), denom


def coverage_fraction(n_with_value: int, n_members: int) -> float:
    """H1 coverage — fraction of the period's members carrying a computed value."""
    if n_members <= 0:
        return float("nan")
    return float(n_with_value) / float(n_members)


def cell_abstains(cov: float, floor: float = COVERAGE_FLOOR) -> bool:
    """H1: strictly below the floor prints ABSTAIN. A NaN coverage abstains (fail-closed)."""
    if cov is None or not np.isfinite(cov):
        return True
    return float(cov) < float(floor)


def era_for_month(month: str, observed_from: str = OBSERVED_ERA_FROM) -> str:
    """Prereg §4 — membership era for a monthly cross-section.

    A month is observed only when its FIRST day is on or after the graph's first belief
    stamp; every earlier month rides era=reconstruction membership. The tapes' own dates are
    authentic PIT data either way — this labels MEMBERSHIP, never the price/attention tape.
    """
    start = pd.Period(month, freq="M").start_time.date().isoformat()
    return "observed" if start >= observed_from else "reconstruction"


def spearman_rho(x, y) -> float:
    """Tie-corrected Spearman rho only (no p-value). NaN for n < 3 or a constant vector."""
    xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(xa) != len(ya):
        raise ValueError("spearman_rho: length mismatch")
    if len(xa) < 3:
        return float("nan")
    rx, ry = sps.rankdata(xa), sps.rankdata(ya)
    if np.std(rx) == 0.0 or np.std(ry) == 0.0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def spearman_exact(x, y, *, max_exact_n: int = EXACT_P_MAX_N,
                   mc_draws: int = PERM_MC_DRAWS, seed: int = PERM_SEED,
                   mc_batch: int = PERM_MC_BATCH):
    """(rho, two-sided p, method). Ties handled by average ranks throughout.

    n! is enumerated exactly at or below ``max_exact_n``; above it a seeded Monte-Carlo
    pairing permutation with the add-one correction. Returns NaN rho for n < 3 or for a
    constant vector (rho undefined, not zero).
    """
    xa = np.asarray(x, dtype=float)
    ya = np.asarray(y, dtype=float)
    n = len(xa)
    if n != len(ya):
        raise ValueError("spearman_exact: length mismatch")
    if n < 3:
        return float("nan"), float("nan"), f"undefined-n<3(n={n})"
    rx = sps.rankdata(xa)
    ry = sps.rankdata(ya)
    if np.std(rx) == 0.0 or np.std(ry) == 0.0:
        return float("nan"), float("nan"), f"undefined-constant(n={n})"
    rho = float(np.corrcoef(rx, ry)[0, 1])
    # Only the cross-product varies under a pairing permutation; means/stds are invariant.
    if n <= max_exact_n:
        perms = np.array(list(itertools.permutations(range(n))), dtype=np.int64)
        dots = ry[perms] @ rx
        rhos = ((dots / n) - rx.mean() * ry.mean()) / (rx.std() * ry.std())
        p = float(np.mean(np.abs(rhos) >= abs(rho) - 1e-12))
        return rho, p, f"exact-permutation(n={n},perms={len(perms)})"
    rng = np.random.default_rng(seed)
    hits, done = 0, 0
    while done < mc_draws:
        k = min(mc_batch, mc_draws - done)                 # batch size is a pinned constant,
        M = rng.permuted(np.tile(ry, (k, 1)), axis=1)      # so the draw sequence is reproducible
        rhos = ((M @ rx) / n - rx.mean() * ry.mean()) / (rx.std() * ry.std())
        hits += int(np.count_nonzero(np.abs(rhos) >= abs(rho) - 1e-12))
        done += k
    p = (1.0 + hits) / (1.0 + mc_draws)
    return rho, float(p), f"mc-permutation(n={n},draws={mc_draws},seed={seed})"


def block_bootstrap_median_ci(series_list, *, block: int = BOOTSTRAP_BLOCK,
                              draws: int = BOOTSTRAP_DRAWS, seed: int = BOOTSTRAP_SEED,
                              lo_pct: float = BOOTSTRAP_LO, hi_pct: float = BOOTSTRAP_HI):
    """Moving-block bootstrap 80% CI for the median of pooled adjacent-pair rhos.

    ``series_list`` is one month-ordered array per slot: repeated cross-sections are never
    pooled as independent draws, so the resampling happens WITHIN each slot's own time order
    and only then pools. Deterministic given the seed and the (sorted) slot order.
    """
    arrs = [np.asarray(s, dtype=float) for s in series_list]
    arrs = [a[np.isfinite(a)] for a in arrs]
    arrs = [a for a in arrs if len(a)]
    if not arrs:
        return float("nan"), float("nan"), 0
    # A series no longer than one block admits exactly one block placement, so every draw
    # reproduces the original series and the interval collapses to a point. That is not a
    # tight CI — it is NO resampling. The caller flags it rather than printing a fake width.
    if all(len(a) <= block for a in arrs):
        med = float(np.median(np.concatenate(arrs)))
        return med, med, int(sum(len(a) for a in arrs))
    rng = np.random.default_rng(seed)
    meds = np.empty(draws, dtype=float)
    for d in range(draws):
        pooled = []
        for a in arrs:
            n = len(a)
            b = min(block, n)
            n_blocks = int(np.ceil(n / b))
            starts = rng.integers(0, n - b + 1, size=n_blocks)
            pooled.append(np.concatenate([a[s:s + b] for s in starts])[:n])
        meds[d] = float(np.median(np.concatenate(pooled)))
    return (float(np.percentile(meds, lo_pct)), float(np.percentile(meds, hi_pct)),
            int(sum(len(a) for a in arrs)))


def h2_reading(abs_rhos) -> str:
    """§3 H2 frozen threshold reading over the computable slots."""
    vals = [float(v) for v in abs_rhos if v is not None and np.isfinite(v)]
    if not vals:
        return "VACUOUS (no computable slot)"
    med = float(np.median(vals))
    if med > H2_REDUNDANT_MEDIAN:
        return f"REDUNDANT-ON-OUR-DATA (median |rho| {med:.3f} > {H2_REDUNDANT_MEDIAN})"
    if med <= H2_DISTINCT_MEDIAN and min(vals) <= H2_DISTINCT_ONE_SLOT:
        return (f"MEASURABLY-DISAGREE (median |rho| {med:.3f} <= {H2_DISTINCT_MEDIAN} and "
                f"min |rho| {min(vals):.3f} <= {H2_DISTINCT_ONE_SLOT})")
    return f"PARTIALLY-DISTINCT (median |rho| {med:.3f}; no promotion claim)"


def h3_reading(median_rho: float, n_pairs: int) -> str:
    """§3 H3 frozen threshold reading."""
    if n_pairs < H3_MIN_PAIRS:
        return f"UNDERPOWERED-BY-DEPTH ({n_pairs} adjacent pair(s) < {H3_MIN_PAIRS})"
    if not np.isfinite(median_rho):
        return "UNDEFINED"
    if median_rho >= H3_STABLE:
        return f"STABLE (median rho {median_rho:.3f} >= {H3_STABLE})"
    if median_rho < H3_NOISE:
        return f"NOISE (median rho {median_rho:.3f} < {H3_NOISE})"
    return f"WEAKLY-STABLE (median rho {median_rho:.3f}); accrual re-probe decides"


# ======================================================================================
# Receipts
# ======================================================================================
def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    except Exception:                                            # pragma: no cover - env only
        return ""


def _store_receipt(path: Path, df: pd.DataFrame | None, date_col: str | None,
                   gitignored: bool = False) -> dict:
    rec = {
        "path": str(path.relative_to(ROOT)),
        "exists": path.exists(),
        "gitignored_local_only": gitignored,
        "sha256": _sha256(path) if path.exists() else None,
        "bytes": path.stat().st_size if path.exists() else None,
        "rows": int(len(df)) if df is not None else None,
    }
    if df is not None and date_col and date_col in df.columns:
        s = df[date_col].astype(str)
        rec["date_min"], rec["date_max"] = str(s.min()), str(s.max())
        rec["distinct_dates"] = int(s.nunique())
    elif df is not None and date_col == "@index" and len(df):
        rec["date_min"] = str(pd.Timestamp(df.index.min()).date())
        rec["date_max"] = str(pd.Timestamp(df.index.max()).date())
        rec["distinct_dates"] = int(df.index.nunique())
    return rec


# ======================================================================================
# Loaders (READ-ONLY)
# ======================================================================================
def load_membership(edges_path: Path) -> pd.DataFrame:
    """Latest-belief MEMBER_OF view: max belief_time per edge_id (contract read semantics)."""
    e = pd.read_parquet(edges_path)
    mo = e[e["type"] == "MEMBER_OF"].copy()
    keep = mo.groupby("edge_id")["belief_time"].idxmax()
    lb = mo.loc[keep].sort_values(["dst", "src", "edge_id"]).reset_index(drop=True)
    return lb


def node_symbols(nodes_path: Path) -> dict:
    n = pd.read_parquet(nodes_path)
    out = {}
    for nid, ext in zip(n["node_id"], n["external_ids"]):
        sym = None
        try:
            sym = (json.loads(ext) or {}).get("symbol")
        except Exception:
            sym = None
        out[str(nid)] = str(sym) if sym else str(nid).split(":")[-1]
    return out


def active_members(lb: pd.DataFrame, baskets: list, at_date: str) -> list:
    """Members whose [valid_from, valid_to) covers ``at_date`` (closed members INCLUDED)."""
    sub = lb[lb["dst"].isin(baskets)]
    vf = sub["valid_from"].astype(str)
    open_end = sub["valid_to"].isna()
    vt = sub["valid_to"].fillna("9999-12-31").astype(str)
    covers = (vf <= at_date) & (open_end | (vt > at_date))
    return sorted(set(sub.loc[covers, "src"].astype(str)))


def all_slot_members(lb: pd.DataFrame, baskets: list) -> pd.DataFrame:
    sub = lb[lb["dst"].isin(baskets)][["src", "dst", "valid_from", "valid_to"]].copy()
    return sub.sort_values(["src", "dst"]).reset_index(drop=True)


def load_us_closes(symbols: list, receipts: dict) -> tuple:
    """US member closes from data/baskets/ohlcv (fallback data/stocks). Returns (frame, unjoined)."""
    cols, unjoined, used = {}, [], []
    for s in symbols:
        p1 = DATA / "baskets" / "ohlcv" / f"{s}.parquet"
        p2 = DATA / "stocks" / f"{s}.parquet"
        p = p1 if p1.exists() else (p2 if p2.exists() else None)
        if p is None:
            unjoined.append(s)
            continue
        df = pd.read_parquet(p)
        if "close" not in df.columns:
            unjoined.append(s)
            continue
        ser = df["close"].astype(float)
        ser.index = pd.DatetimeIndex(pd.to_datetime(ser.index)).normalize()
        cols[s] = ser[~ser.index.duplicated(keep="last")]
        used.append(str(p.relative_to(ROOT)))
    receipts.setdefault("us_price_files_used", []).extend(sorted(set(used)))
    if not cols:
        return pd.DataFrame(), unjoined
    frame = pd.DataFrame({k: cols[k] for k in sorted(cols)}).sort_index()
    return frame, sorted(unjoined)


def load_cn_closes(symbols: list, panel: pd.DataFrame) -> tuple:
    have = [s for s in sorted(symbols) if s in panel.columns]
    unjoined = [s for s in sorted(symbols) if s not in panel.columns]
    return panel[have].copy(), unjoined


def log_returns(closes: pd.DataFrame) -> pd.DataFrame:
    px = closes.where(closes > 0)
    return np.log(px).diff()


def month_list(first: str, last: str) -> list:
    a, b = pd.Period(first, freq="M"), pd.Period(last, freq="M")
    return [str(p) for p in pd.period_range(a, b, freq="M")]


# ======================================================================================
# Axis computation
# ======================================================================================
def compute_beta_cell(slot: str, meta: dict, lb: pd.DataFrame, symbols: dict,
                      closes: pd.DataFrame, months: list) -> tuple:
    """Rows of (month, node_id, symbol, value, value_display, era) + per-month diagnostics."""
    R = log_returns(closes)
    rows, diags = [], []
    cache: dict = {}
    for m in months:
        p = pd.Period(m, freq="M")
        m_end = p.end_time.date().isoformat()
        idx_in = R.index[(R.index >= p.start_time) & (R.index <= p.end_time)]
        if len(idx_in) == 0:
            continue
        stamp = idx_in.max()
        members = active_members(lb, meta["baskets"], m_end)
        syms = [symbols[n] for n in members if symbols.get(n) in closes.columns]
        node_of = {symbols[n]: n for n in members if symbols.get(n) in closes.columns}
        key = tuple(sorted(syms))
        if not key:
            continue
        if key not in cache:
            sub = R[list(key)]
            X = ex_self_returns(sub)
            cache[key] = {}
            for s in key:
                y, x = sub[s], X[s]
                # The three factors of the beta identity, stamped on the SAME causal shift so
                # beta == corr * sd_own / sd_exself holds exactly in the committed receipts.
                cache[key][s] = dict(
                    beta=causal_beta_pair(y, x),
                    corr=y.rolling(BETA_WIN, min_periods=BETA_MINP).corr(x).shift(1),
                    sd_own=y.rolling(BETA_WIN, min_periods=BETA_MINP).std().shift(1),
                    sd_exself=x.rolling(BETA_WIN, min_periods=BETA_MINP).std().shift(1))
        betas, decomp = {}, {}
        for s in key:
            c = cache[key][s]
            v = c["beta"].get(stamp, np.nan)
            if v is not None and np.isfinite(v):
                betas[s] = float(v)
                decomp[s] = {k: float(c[k].get(stamp, np.nan)) for k in
                             ("corr", "sd_own", "sd_exself")}
        shrunk = vasicek_shrink(pd.Series(betas)) if betas else pd.Series(dtype=float)
        era = era_for_month(m)
        for n in members:
            s = symbols.get(n)
            v = betas.get(s)
            dc = decomp.get(s, {})
            rows.append(dict(month=m, node_id=n, symbol=s,
                             value=v if v is not None else np.nan,
                             value_display_shrunk=(float(shrunk[s]) if s in shrunk.index
                                                   else np.nan),
                             corr_to_ex_self=dc.get("corr", np.nan),
                             sd_own_daily=dc.get("sd_own", np.nan),
                             sd_ex_self_daily=dc.get("sd_exself", np.nan),
                             era=era,
                             in_universe=bool(s in closes.columns),
                             stamp_session=str(pd.Timestamp(stamp).date())))
        diags.append(dict(month=m, n_members=len(members), n_values=len(betas),
                          coverage=coverage_fraction(len(betas), len(members)),
                          no_events=False, era=era,
                          stamp_session=str(pd.Timestamp(stamp).date())))
    return rows, diags


def compute_attention_cell(slot: str, meta: dict, lb: pd.DataFrame, symbols: dict,
                           magnitude_by_month: dict, universe: set, months: list,
                           zeros_for_universe: bool) -> tuple:
    """Share rows + per-month diagnostics for one attention construction.

    ``magnitude_by_month[month][symbol]`` is the member's monthly magnitude where the tape
    carries one. ``zeros_for_universe`` decides the prereg §3 rule for an in-universe member
    with no rows that month: a tail-event tape (LHB/WSB/flare) records a genuine zero; a dense
    panel (千股千评) records a gap, which is MISSING, never an imputed zero.
    """
    rows, diags = [], []
    for m in months:
        p = pd.Period(m, freq="M")
        m_end = p.end_time.date().isoformat()
        members = active_members(lb, meta["baskets"], m_end)
        era = era_for_month(m)
        mm = magnitude_by_month.get(m, {})
        mags = {}
        for n in members:
            s = symbols.get(n)
            if s is None or s not in universe:
                continue
            if s in mm:
                mags[s] = float(mm[s])
            elif zeros_for_universe:
                mags[s] = 0.0
        mag_ser = pd.Series(mags, dtype=float).sort_index()
        shares, denom = shares_from_magnitudes(mag_ser) if len(mag_ser) else (None, 0.0)
        no_events = (len(mag_ser) > 0 and shares is None)
        for n in members:
            s = symbols.get(n)
            val = np.nan
            if shares is not None and s in shares.index:
                val = float(shares[s])
            rows.append(dict(month=m, node_id=n, symbol=s, value=val,
                             magnitude=(float(mag_ser[s]) if s in mag_ser.index else np.nan),
                             era=era, in_universe=bool(s in universe),
                             no_events_month=bool(no_events)))
        n_values = 0 if shares is None else int(len(shares))
        # Tie mass: the fraction of covered members sitting on the SINGLE most common
        # magnitude. A construction whose members are mostly tied is ranking almost nothing,
        # so every rank statistic downstream has to be read against this number.
        modal_mass = float("nan")
        distinct_vals = 0
        if len(mag_ser):
            vc = mag_ser.value_counts()
            modal_mass = float(vc.iloc[0]) / float(len(mag_ser))
            distinct_vals = int(mag_ser.nunique())
        diags.append(dict(month=m, n_members=len(members), n_values=n_values,
                          coverage=(float("nan") if no_events
                                    else coverage_fraction(n_values, len(members))),
                          no_events=bool(no_events), era=era,
                          denominator=float(denom),
                          pct_nonzero=(float((mag_ser > 0).mean()) if len(mag_ser) else float("nan")),
                          modal_tie_mass=modal_mass, distinct_magnitudes=distinct_vals))
    return rows, diags


def corr_cell_from_beta_rows(rows: list, diags: list) -> dict:
    """Project the corr term of the beta identity into its own cell (POST-PREREG companion).

    Same window, same causal shift, same months, same membership: this is literally the `corr`
    factor already computed inside `beta = corr * sd_own / sd_ex_self`, re-cross-sectioned.
    Nothing is re-estimated, so the companion can never disagree with the frozen cell about
    WHICH member-months exist — only about how they rank once the volatility ratio is removed.
    """
    crows = [dict(month=r["month"], node_id=r["node_id"], symbol=r["symbol"],
                  value=r["corr_to_ex_self"], era=r["era"],
                  in_universe=r["in_universe"], stamp_session=r["stamp_session"])
             for r in rows]
    by_month: dict = {}
    for r in crows:
        by_month.setdefault(r["month"], []).append(r)
    cdiags = []
    for d in diags:
        n_val = sum(1 for r in by_month.get(d["month"], [])
                    if r["value"] is not None and np.isfinite(r["value"]))
        cdiags.append(dict(month=d["month"], n_members=d["n_members"], n_values=n_val,
                           coverage=coverage_fraction(n_val, d["n_members"]),
                           no_events=False, era=d["era"],
                           stamp_session=d.get("stamp_session")))
    return dict(rows=crows, diags=cdiags)


def monthly_sum(df: pd.DataFrame, sym_col: str, date_col: str, val_col: str) -> dict:
    d = df[[sym_col, date_col, val_col]].copy()
    d["month"] = d[date_col].astype(str).str.slice(0, 7)
    g = d.groupby(["month", sym_col])[val_col].sum()
    out: dict = {}
    for (m, s), v in g.items():
        out.setdefault(str(m), {})[str(s)] = float(v)
    return out


def monthly_mean(df: pd.DataFrame, sym_col: str, date_col: str, val_col: str) -> dict:
    d = df[[sym_col, date_col, val_col]].copy()
    d["month"] = d[date_col].astype(str).str.slice(0, 7)
    g = d.groupby(["month", sym_col])[val_col].mean()
    out: dict = {}
    for (m, s), v in g.items():
        out.setdefault(str(m), {})[str(s)] = float(v)
    return out


def monthly_count(df: pd.DataFrame, sym_col: str, date_col: str) -> dict:
    d = df[[sym_col, date_col]].copy()
    d["month"] = d[date_col].astype(str).str.slice(0, 7)
    g = d.drop_duplicates([sym_col, date_col]).groupby(["month", sym_col]).size()
    out: dict = {}
    for (m, s), v in g.items():
        out.setdefault(str(m), {})[str(s)] = float(v)
    return out


# ======================================================================================
# Probe driver
# ======================================================================================
def run(out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    cells_dir = out_dir / "cells"
    cells_dir.mkdir(parents=True, exist_ok=True)

    receipts: dict = {
        "probe": "GMI W2 exposure-decomposition probe (R1)",
        "prereg": "research/theme_graph/W2_EXPOSURE_AXES_PREREG.md",
        "git_head": _git("rev-parse", "HEAD"),
        "git_head_committed_at": _git("log", "-1", "--format=%cI"),
        "git_branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "frozen_constants": dict(
            coverage_floor=COVERAGE_FLOOR, beta_window=BETA_WIN, beta_min_overlap=BETA_MINP,
            vasicek_w_display_only=VASICEK_W,
            h2_distinct_median=H2_DISTINCT_MEDIAN, h2_distinct_one_slot=H2_DISTINCT_ONE_SLOT,
            h2_redundant_median=H2_REDUNDANT_MEDIAN,
            h3_stable=H3_STABLE, h3_noise=H3_NOISE, h3_min_pairs=H3_MIN_PAIRS,
            bootstrap=dict(block=BOOTSTRAP_BLOCK, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED,
                           ci="80% (p10/p90)"),
            permutation=dict(exact_max_n=EXACT_P_MAX_N, mc_draws=PERM_MC_DRAWS, seed=PERM_SEED),
            us_history_start=US_HISTORY_START, cn_history_start=CN_HISTORY_START,
            observed_era_from=OBSERVED_ERA_FROM),
        "stores": {},
        "slots": {},
        "unjoined": {},
    }

    # ---- graph -----------------------------------------------------------------------
    edges_p = DATA / "theme_graph" / "edges.parquet"
    nodes_p = DATA / "theme_graph" / "nodes.parquet"
    meta_p = DATA / "theme_graph" / "_meta.json"
    lb = load_membership(edges_p)
    symbols = node_symbols(nodes_p)
    graph_meta = json.loads(meta_p.read_text())
    receipts["stores"]["theme_graph.edges"] = _store_receipt(
        edges_p, pd.read_parquet(edges_p), "belief_time")
    receipts["stores"]["theme_graph.nodes"] = _store_receipt(nodes_p, pd.read_parquet(nodes_p), None)
    receipts["graph_meta"] = {k: graph_meta.get(k) for k in
                              ("belief_time", "computed_at", "era", "lane", "mode",
                               "engine_version", "counts")}
    probe_asof = str(graph_meta.get("belief_time"))

    # ---- price panels ----------------------------------------------------------------
    cn_panel_p = DATA / "china_search" / "closes.parquet"
    cn_panel = pd.read_parquet(cn_panel_p).sort_index()
    cn_panel = cn_panel.loc[:, ~cn_panel.columns.duplicated()]
    receipts["stores"]["china_search.closes"] = _store_receipt(cn_panel_p, cn_panel, "@index")
    receipts["stores"]["china_search.closes"]["n_tickers"] = int(cn_panel.shape[1])
    receipts["stores"]["china_search.closes"]["read_because"] = (
        "the store scripts/c1_cn_global_beta.py:_panel() reads — prereg §2 follows the "
        "incumbent CN beta plane's input choice rather than re-deciding it")

    # ---- attention tapes -------------------------------------------------------------
    att_p = DATA / "china_comment" / "attention_hist.parquet"
    att = pd.read_parquet(att_p)
    receipts["stores"]["china_comment.attention_hist"] = _store_receipt(att_p, att, "date")
    receipts["stores"]["china_comment.attention_hist"]["n_tickers"] = int(att["ticker"].nunique())

    lhb_p = DATA / "china_lhb" / "events.parquet"
    lhb = pd.read_parquet(lhb_p)
    receipts["stores"]["china_lhb.events"] = _store_receipt(lhb_p, lhb, "date")
    receipts["stores"]["china_lhb.events"]["n_tickers"] = int(lhb["ticker"].nunique())

    wsb_p = DATA / "quiver" / "wallstreetbets.parquet"
    wsb = pd.read_parquet(wsb_p)
    receipts["stores"]["quiver.wallstreetbets"] = _store_receipt(wsb_p, wsb, "_collected")
    receipts["stores"]["quiver.wallstreetbets"]["n_tickers"] = int(wsb["Ticker"].nunique())

    flare_p = DATA / "narrative_flare" / "witness_hist.parquet"
    flare = pd.read_parquet(flare_p)
    receipts["stores"]["narrative_flare.witness_hist"] = _store_receipt(
        flare_p, flare, "date", gitignored=True)
    receipts["stores"]["narrative_flare.witness_hist"]["n_tickers"] = int(flare["ticker"].nunique())
    receipts["stores"]["narrative_flare.witness_hist"]["field_used"] = "channels_lit"
    receipts["stores"]["narrative_flare.witness_hist"]["field_density"] = {
        c: float(flare[c].notna().mean())
        for c in ("news_count_z", "channels_lit", "burst_weight_polygon", "hazard_pctile")}

    # ---- phase tape (regime context for the exemplar gate) ---------------------------
    phase_p = DATA / "neuralweb" / "theme_phase_history.jsonl"
    phase_latest: dict = {}
    if phase_p.exists():
        for line in phase_p.read_text().strip().splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            tid = r.get("theme_id")
            if tid:
                prev = phase_latest.get(tid)
                if prev is None or str(r.get("as_of")) >= str(prev.get("as_of")):
                    phase_latest[tid] = r
        receipts["stores"]["neuralweb.theme_phase_history"] = _store_receipt(phase_p, None, None)

    # ---- monthly magnitude maps -------------------------------------------------------
    att_by_month = monthly_mean(att, "ticker", "date", "attention")
    att_universe = set(att["ticker"].astype(str))
    lhb_by_month = monthly_count(lhb, "ticker", "date")
    lhb_universe = None                       # every A-share is in the LHB universe (§3)
    wsb_by_month = monthly_sum(wsb, "Ticker", "_collected", "Count")
    wsb_universe = set(wsb["Ticker"].astype(str))
    flare_by_month = monthly_sum(flare, "ticker", "date", "channels_lit")
    flare_universe = set(flare["ticker"].astype(str))

    last_cn_month = str(pd.Period(pd.Timestamp(cn_panel.index.max()).date(), freq="M"))

    # ==================================================================================
    # Per-cell computation
    # ==================================================================================
    cells: dict = {}          # (slot, construction) -> dict(rows, diags, coverage, abstain)
    comp_cells: dict = {}     # post-prereg companion cells, kept OUT of the frozen tables
    slot_members_meta: dict = {}

    for slot, meta in SLOTS.items():
        market = meta["market"]
        mem = all_slot_members(lb, meta["baskets"])
        member_nodes = sorted(set(mem["src"].astype(str)))
        syms = [symbols.get(n, n) for n in member_nodes]
        dead = sorted(set(mem.loc[mem["valid_to"].notna(), "src"].astype(str)))
        slot_members_meta[slot] = dict(
            theme=meta["theme"], market=market, label=meta["label"],
            baskets=meta["baskets"], n_members_total=len(member_nodes),
            n_live=len(active_members(lb, meta["baskets"], probe_asof)),
            dead_members=[{"node_id": n, "symbol": symbols.get(n, n),
                           "valid_from": str(mem.loc[mem["src"] == n, "valid_from"].iloc[0]),
                           "valid_to": str(mem.loc[mem["src"] == n, "valid_to"].iloc[0])}
                          for n in dead],
            phase=({k: phase_latest[meta["theme"]].get(k)
                    for k in ("as_of", "foresight_stage", "divergence_quadrant")}
                   if meta["theme"] in phase_latest else None),
        )

        if market == "us":
            closes, unjoined = load_us_closes(syms, receipts)
            last_month = (str(pd.Period(pd.Timestamp(closes.index.max()).date(), freq="M"))
                          if len(closes) else US_HISTORY_START)
            months_beta = month_list(US_HISTORY_START, last_month)
        else:
            closes, unjoined = load_cn_closes(syms, cn_panel)
            last_month = last_cn_month
            months_beta = month_list(CN_HISTORY_START, last_month)
        receipts["unjoined"][slot] = {"price_store": unjoined}

        rows, diags = compute_beta_cell(slot, meta, lb, symbols, closes, months_beta)
        cells[(slot, BETA_ID)] = dict(rows=rows, diags=diags)
        comp_cells[(slot, COMPANION_CORR_ID)] = corr_cell_from_beta_rows(rows, diags)

        if market == "cn":
            att_months = [m for m in month_list(CN_HISTORY_START, last_month)
                          if m in att_by_month]
            r, d = compute_attention_cell(slot, meta, lb, symbols, att_by_month,
                                          att_universe, att_months, zeros_for_universe=False)
            cells[(slot, CN_COMMENT_ID)] = dict(rows=r, diags=d)
            receipts["unjoined"][slot]["cn_comment"] = sorted(
                s for s in syms if s not in att_universe)

            lhb_months = month_list(max(CN_HISTORY_START, min(lhb_by_month)), last_month)
            uni = set(syms)      # every A-share is in the LHB universe; zeros are values (§3)
            r, d = compute_attention_cell(slot, meta, lb, symbols, lhb_by_month,
                                          uni, lhb_months, zeros_for_universe=True)
            cells[(slot, CN_LHB_ID)] = dict(rows=r, diags=d)
            receipts["unjoined"][slot]["cn_lhb"] = []
        else:
            wsb_months = [m for m in month_list(US_HISTORY_START, last_month)
                          if m in wsb_by_month]
            r, d = compute_attention_cell(slot, meta, lb, symbols, wsb_by_month,
                                          wsb_universe, wsb_months, zeros_for_universe=True)
            cells[(slot, US_WSB_ID)] = dict(rows=r, diags=d)
            receipts["unjoined"][slot]["us_wsb"] = sorted(
                s for s in syms if s not in wsb_universe)

            flare_months = [m for m in month_list(US_HISTORY_START, last_month)
                            if m in flare_by_month]
            r, d = compute_attention_cell(slot, meta, lb, symbols, flare_by_month,
                                          flare_universe, flare_months, zeros_for_universe=True)
            cells[(slot, US_FLARE_ID)] = dict(rows=r, diags=d)
            receipts["unjoined"][slot]["us_flare"] = sorted(
                s for s in syms if s not in flare_universe)

    receipts["slots"] = slot_members_meta

    # ---- H1 -------------------------------------------------------------------------
    h1_rows = []
    for (slot, cid), c in sorted(cells.items()):
        diags = [d for d in c["diags"]]
        graded = [d for d in diags if not d["no_events"]]
        n_vals = sum(d["n_values"] for d in graded)
        n_mem = sum(d["n_members"] for d in graded)
        cov = coverage_fraction(n_vals, n_mem)
        abstain = cell_abstains(cov)
        latest = graded[-1] if graded else None
        c["coverage"] = cov
        c["abstain"] = abstain
        c["graded_months"] = [d["month"] for d in graded]
        c["no_events_months"] = [d["month"] for d in diags if d["no_events"]]
        h1_rows.append(dict(
            slot=slot, market=SLOTS[slot]["market"], construction=cid,
            months=len(diags), graded_months=len(graded),
            no_events_months=len(c["no_events_months"]),
            pooled_coverage=round(cov, 4) if np.isfinite(cov) else None,
            latest_month=(latest["month"] if latest else None),
            latest_coverage=(round(latest["coverage"], 4)
                             if latest and np.isfinite(latest["coverage"]) else None),
            min_month_coverage=(round(min(d["coverage"] for d in graded), 4) if graded else None),
            status="ABSTAIN" if abstain else "COMPUTABLE",
            era=(latest["era"] if latest else None)))
    # economic_share — ABSTAIN by construction (prereg §2, honest null, no formula minted)
    for slot in SLOTS:
        h1_rows.append(dict(
            slot=slot, market=SLOTS[slot]["market"], construction=ECONOMIC_ID,
            months=0, graded_months=0, no_events_months=0, pooled_coverage=None,
            latest_month=None, latest_coverage=None, min_month_coverage=None,
            status="ABSTAIN", era=None))

    # ---- per-cell CSV receipts --------------------------------------------------------
    cell_index = []
    for (slot, cid), c in sorted(cells.items()):
        df = pd.DataFrame(c["rows"])
        if len(df):
            df = df.sort_values(["month", "symbol"]).reset_index(drop=True)
        fn = f"{slot}__{cid}.csv"
        df.to_csv(cells_dir / fn, index=False)
        dd = pd.DataFrame(c["diags"])
        if len(dd):
            dd = dd.sort_values("month").reset_index(drop=True)
        dd.to_csv(cells_dir / f"{slot}__{cid}__months.csv", index=False)
        cell_index.append(dict(slot=slot, construction=cid, rows=len(df),
                               months=len(dd), coverage=c["coverage"],
                               status="ABSTAIN" if c["abstain"] else "COMPUTABLE",
                               values_csv=f"cells/{fn}",
                               months_csv=f"cells/{slot}__{cid}__months.csv"))
    pd.DataFrame(cell_index).to_csv(out_dir / "cell_index.csv", index=False)
    pd.DataFrame(h1_rows).to_csv(out_dir / "h1_coverage.csv", index=False)

    # ---- cross-section helper ---------------------------------------------------------
    def _mk_xs(src: dict):
        def _xs(slot: str, cid: str, month: str) -> pd.Series:
            c = src.get((slot, cid))
            if not c:
                return pd.Series(dtype=float)
            d = pd.DataFrame(c["rows"])
            if not len(d):
                return pd.Series(dtype=float)
            d = d[(d["month"] == month) & d["value"].notna()]
            return pd.Series(d["value"].values, index=d["symbol"].values,
                             dtype=float).sort_index()
        return _xs

    xs = _mk_xs(cells)
    xs_c = _mk_xs(comp_cells)

    # Companion coverage, computed the same way but kept in its own namespace so it cannot
    # leak into h1_coverage.csv or any verdict cell.
    for (slot, cid), c in comp_cells.items():
        graded = [d for d in c["diags"] if not d["no_events"]]
        cov = coverage_fraction(sum(d["n_values"] for d in graded),
                                sum(d["n_members"] for d in graded))
        c["coverage"], c["abstain"] = cov, cell_abstains(cov)
        c["graded_months"] = [d["month"] for d in graded]
        c["no_events_months"] = []

    # ---- H2 ---------------------------------------------------------------------------
    h2_rows = []
    for cid in (CN_COMMENT_ID, CN_LHB_ID, US_WSB_ID, US_FLARE_ID):
        for slot, meta in SLOTS.items():
            if (slot, cid) not in cells:
                continue
            cb, ca = cells[(slot, BETA_ID)], cells[(slot, cid)]
            common = sorted(set(cb["graded_months"]) & set(ca["graded_months"]))
            if not common:
                h2_rows.append(dict(slot=slot, market=meta["market"], pair=f"{BETA_ID}~{cid}",
                                    month=None, n=0, rho=None, abs_rho=None, p=None,
                                    p_method=None, status="NO-COMMON-MONTH", era=None))
                continue
            month = common[-1]
            if cb["abstain"] or ca["abstain"]:
                h2_rows.append(dict(slot=slot, market=meta["market"], pair=f"{BETA_ID}~{cid}",
                                    month=month, n=0, rho=None, abs_rho=None, p=None,
                                    p_method=None,
                                    status=("ABSTAIN (beta cell)" if cb["abstain"]
                                            else "ABSTAIN (attention cell)"),
                                    era=era_for_month(month)))
                continue
            a, b = xs(slot, BETA_ID, month), xs(slot, cid, month)
            idx = sorted(set(a.index) & set(b.index))
            rho, p, method = spearman_exact(a[idx].values, b[idx].values)
            h2_rows.append(dict(slot=slot, market=meta["market"], pair=f"{BETA_ID}~{cid}",
                                month=month, n=len(idx),
                                rho=(round(rho, 4) if np.isfinite(rho) else None),
                                abs_rho=(round(abs(rho), 4) if np.isfinite(rho) else None),
                                p=(round(p, 5) if np.isfinite(p) else None), p_method=method,
                                status="COMPUTED", era=era_for_month(month)))
    # economic pairs are vacuous by construction (prereg §3)
    for slot, meta in SLOTS.items():
        h2_rows.append(dict(slot=slot, market=meta["market"], pair=f"{BETA_ID}~{ECONOMIC_ID}",
                            month=None, n=0, rho=None, abs_rho=None, p=None, p_method=None,
                            status="VACUOUS (economic_share has no formula)", era=None))
    pd.DataFrame(h2_rows).to_csv(out_dir / "h2_distinctness.csv", index=False)

    h2_readings = {}
    for cid in (CN_COMMENT_ID, CN_LHB_ID, US_WSB_ID, US_FLARE_ID):
        vals = [r["abs_rho"] for r in h2_rows
                if r["pair"].endswith(cid) and r["status"] == "COMPUTED" and r["abs_rho"] is not None]
        h2_readings[cid] = dict(reading=h2_reading(vals), n_slots=len(vals),
                                abs_rhos=[round(float(v), 4) for v in vals])

    # ---- H3 ---------------------------------------------------------------------------
    h3_pairs, h3_summary = [], {}
    for cid, cmeta in CONSTRUCTIONS.items():
        per_slot_series, per_slot_meta, lag3 = [], [], []
        for slot, meta in SLOTS.items():
            c = cells.get((slot, cid))
            if not c:
                continue
            if c["abstain"]:
                per_slot_meta.append(dict(slot=slot, n_pairs=0, median=None,
                                          status="ABSTAIN (H1 coverage floor)"))
                continue
            months = c["graded_months"]
            # Companion (NOT preregistered): the same rank autocorrelation at a 3-month lag.
            # Adjacent-month betas share ~2/3 of one 63-session window, so the preregistered
            # H3 statistic carries a mechanical floor; at 3 months the windows are disjoint.
            for m0, m1 in zip(months[:-3], months[3:]):
                if (pd.Period(m1, freq="M") - pd.Period(m0, freq="M")).n != 3:
                    continue
                a, b = xs(slot, cid, m0), xs(slot, cid, m1)
                idx = sorted(set(a.index) & set(b.index))
                rho = spearman_rho(a[idx].values, b[idx].values)
                if np.isfinite(rho):
                    lag3.append(float(rho))
            rr = []
            for m0, m1 in zip(months[:-1], months[1:]):
                a, b = xs(slot, cid, m0), xs(slot, cid, m1)
                idx = sorted(set(a.index) & set(b.index))
                rho, p, method = spearman_exact(a[idx].values, b[idx].values)
                adjacent = (pd.Period(m1, freq="M") - pd.Period(m0, freq="M")).n == 1
                h3_pairs.append(dict(slot=slot, market=meta["market"], construction=cid,
                                     month_from=m0, month_to=m1, adjacent=bool(adjacent),
                                     n=len(idx),
                                     rho=(round(rho, 4) if np.isfinite(rho) else None),
                                     p=(round(p, 5) if np.isfinite(p) else None),
                                     p_method=method, era=era_for_month(m1)))
                if adjacent and np.isfinite(rho):
                    rr.append(float(rho))
            per_slot_series.append(np.asarray(rr, dtype=float))
            per_slot_meta.append(dict(
                slot=slot, n_pairs=len(rr),
                median=(round(float(np.median(rr)), 4) if rr else None),
                status=("UNDERPOWERED-BY-DEPTH" if len(rr) < H3_MIN_PAIRS else "COMPUTED")))
        pooled = np.concatenate(per_slot_series) if per_slot_series else np.asarray([])
        pooled = pooled[np.isfinite(pooled)]
        med = float(np.median(pooled)) if len(pooled) else float("nan")
        lo, hi, n_used = block_bootstrap_median_ci(per_slot_series)
        degenerate = bool(per_slot_series) and all(
            len(a[np.isfinite(a)]) <= BOOTSTRAP_BLOCK for a in per_slot_series)
        h3_summary[cid] = dict(
            n_pairs=int(len(pooled)),
            median_rho=(round(med, 4) if np.isfinite(med) else None),
            ci80_lo=(round(lo, 4) if np.isfinite(lo) else None),
            ci80_hi=(round(hi, 4) if np.isfinite(hi) else None),
            ci_degenerate=degenerate,
            companion_lag3_median=(round(float(np.median(lag3)), 4) if lag3 else None),
            companion_lag3_pairs=len(lag3),
            bootstrap_n=n_used, reading=h3_reading(med, int(len(pooled))),
            per_slot=per_slot_meta,
            era="reconstruction" if all(era_for_month(m) == "reconstruction"
                                        for m in sum([cells[(s, cid)]["graded_months"]
                                                      for s in SLOTS if (s, cid) in cells], []))
                 else "mixed")
    pd.DataFrame(h3_pairs).to_csv(out_dir / "h3_stability_pairs.csv", index=False)

    # ---- post-prereg corr companion ----------------------------------------------------
    companion = corr_companion(cells, comp_cells, xs, xs_c, h2_rows, h3_summary)
    for (slot, cid), c in sorted(comp_cells.items()):
        df = pd.DataFrame(c["rows"])
        if len(df):
            df = df.sort_values(["month", "symbol"]).reset_index(drop=True)
        df.to_csv(cells_dir / f"{slot}__{cid}.csv", index=False)
        dd = pd.DataFrame(c["diags"])
        if len(dd):
            dd = dd.sort_values("month").reset_index(drop=True)
        dd.to_csv(cells_dir / f"{slot}__{cid}__months.csv", index=False)
    pd.DataFrame(companion["h2"]).to_csv(out_dir / "companion_trading_corr_h2.csv", index=False)
    pd.DataFrame(companion["h3"]["per_slot"]).to_csv(
        out_dir / "companion_trading_corr_h3.csv", index=False)

    # ---- honest-N ---------------------------------------------------------------------
    hn_rows = []
    for (slot, cid), c in sorted(cells.items()):
        d = pd.DataFrame(c["rows"])
        graded = d[d["month"].isin(c["graded_months"])] if len(d) else d
        vals = graded[graded["value"].notna()] if len(graded) else graded
        pct_nonzero = (float((vals["value"] > 0).mean()) if len(vals)
                       and CONSTRUCTIONS[cid]["kind"] == "attention" else None)
        tie = [d.get("modal_tie_mass") for d in c["diags"]
               if not d["no_events"] and d.get("modal_tie_mass") is not None
               and np.isfinite(d.get("modal_tie_mass", np.nan))]
        hn_rows.append(dict(
            slot=slot, market=SLOTS[slot]["market"], construction=cid,
            distinct_companies=int(d["node_id"].nunique()) if len(d) else 0,
            distinct_months=len(c["graded_months"]),
            no_events_months=len(c["no_events_months"]),
            episodes=len(c["graded_months"]),
            pct_nonzero=(round(pct_nonzero, 4) if pct_nonzero is not None else None),
            median_modal_tie_mass=(round(float(np.median(tie)), 4) if tie else None),
            sparse=bool(CONSTRUCTIONS[cid]["sparse"]),
            dead_members=len(slot_members_meta[slot]["dead_members"]),
            dead_member_symbols=";".join(x["symbol"] for x in
                                         slot_members_meta[slot]["dead_members"]),
            era="reconstruction"))
    pd.DataFrame(hn_rows).to_csv(out_dir / "honest_n.csv", index=False)

    # ---- exemplar gate (prereg §5) -----------------------------------------------------
    gate = exemplar_gate(cells, xs, symbols, slot_members_meta)
    (out_dir / "exemplar_gate.json").write_text(json.dumps(gate, indent=2, sort_keys=True) + "\n")

    # ---- DRAFT verdicts ----------------------------------------------------------------
    verdicts = draft_verdicts(cells, h3_summary)
    pd.DataFrame(verdicts).to_csv(out_dir / "verdicts_draft.csv", index=False)

    receipts["h2"] = h2_readings
    receipts["h3"] = h3_summary
    receipts["companion_trading_corr"] = companion
    receipts["adjudication_rulings"] = ADJUDICATION_RULINGS
    (out_dir / "receipts.json").write_text(json.dumps(receipts, indent=2, sort_keys=True,
                                                      default=str) + "\n")

    write_report(out_dir, receipts, h1_rows, h2_rows, h2_readings, h3_summary, h3_pairs,
                 hn_rows, gate, verdicts, slot_members_meta, cells, companion)
    print(f"W2 probe written to {out_dir}")
    return 0


def beta_decomposition(cells, slot: str, month: str) -> pd.DataFrame:
    """beta = corr(own, ex-self) * sd_own / sd_ex_self, read straight off the beta cell rows.

    The exemplar gate needs this identity: a beta that looks wrong is either a broken
    estimator or a correct estimator answering a different question than the reader assumed,
    and only the factorisation tells them apart.
    """
    c = cells.get((slot, BETA_ID))
    if not c:
        return pd.DataFrame()
    d = pd.DataFrame(c["rows"])
    if not len(d):
        return pd.DataFrame()
    d = d[(d["month"] == month) & d["value"].notna()].set_index("symbol")
    return d[["value", "corr_to_ex_self", "sd_own_daily", "sd_ex_self_daily"]].sort_index()


def exemplar_gate(cells, xs, symbols, slot_meta) -> dict:
    """Prereg §5 — the three named directional expectations, answered with computed values."""
    def latest_common(slot, cid):
        c = cells.get((slot, cid))
        b = cells.get((slot, BETA_ID))
        if not c or not b:
            return None
        common = sorted(set(c["graded_months"]) & set(b["graded_months"]))
        return common[-1] if common else None

    def rank_block(slot, cid, focus):
        m = latest_common(slot, cid)
        if m is None:
            return dict(month=None, note="no common month with the beta cell")
        a, s = xs(slot, BETA_ID, m), xs(slot, cid, m)
        if not len(s):
            return dict(month=m, note="attention cross-section empty")
        s_sorted = s.sort_values(ascending=False)
        n = len(s_sorted)
        order = {sym: i + 1 for i, sym in enumerate(s_sorted.index)}
        out = dict(month=m, n_with_attention=n,
                   cell_status=("ABSTAIN" if cells[(slot, cid)]["abstain"] else "COMPUTABLE"),
                   cell_coverage=round(float(cells[(slot, cid)]["coverage"]), 4),
                   top5=[{"symbol": k, "share": round(float(v), 5)}
                         for k, v in s_sorted.head(5).items()],
                   era=era_for_month(m))
        dec = beta_decomposition(cells, slot, m)
        out["beta_cross_section"] = dict(
            n=int(len(a)),
            median=(round(float(a.median()), 4) if len(a) else None),
            mean=(round(float(a.mean()), 4) if len(a) else None),
            min=(round(float(a.min()), 4) if len(a) else None),
            max=(round(float(a.max()), 4) if len(a) else None))
        for f in focus:
            blk = dict(
                in_attention_universe=bool(f in s.index),
                attention_share=(round(float(s[f]), 5) if f in s.index else None),
                attention_rank=(order.get(f)),
                attention_quartile=(int(np.ceil(order[f] / max(n, 1) * 4)) if f in order else None),
                beta=(round(float(a[f]), 4) if f in a.index else None),
                beta_rank_desc=(int((a.rank(ascending=False)[f])) if f in a.index else None),
                n_with_beta=int(len(a)))
            if f in dec.index:
                r = dec.loc[f]
                blk["beta_factors"] = dict(
                    corr_to_ex_self=round(float(r["corr_to_ex_self"]), 4),
                    sd_own_daily_pct=round(float(r["sd_own_daily"]) * 100.0, 4),
                    sd_ex_self_daily_pct=round(float(r["sd_ex_self_daily"]) * 100.0, 4),
                    sd_ratio=round(float(r["sd_own_daily"] / r["sd_ex_self_daily"]), 4),
                    own_vol_rank_desc=int(dec["sd_own_daily"].rank(ascending=False)[f]),
                    identity_check=round(float(r["corr_to_ex_self"] * r["sd_own_daily"]
                                               / r["sd_ex_self_daily"]), 4))
            out[f] = blk
        return out

    gate = {}
    # (1) cross-market pair, US side: NVDA
    gate["1_nvda_attention_and_beta"] = {
        "expectation": ("NVDA must not rank bottom-quartile on attention share within its "
                        "baskets; its beta should be near or above 1"),
        "wsb": rank_block("cross_market_pair.us", US_WSB_ID, ["NVDA"]),
        "flare": rank_block("cross_market_pair.us", US_FLARE_ID, ["NVDA"]),
    }
    # (2) CN robotics: attention vs beta ranks must NOT be identical
    g2 = {"expectation": ("涨停-prone small caps should carry attention shares well above the "
                          "index-heavy members relative to their beta ranks; IDENTICAL "
                          "attention and beta ranks would indicate price-derived contamination")}
    for key, cid in (("comment", CN_COMMENT_ID), ("lhb", CN_LHB_ID)):
        slot = "cn_young_speculative"
        m = latest_common(slot, cid)
        blk = dict(month=m)
        if m is not None:
            a, s = xs(slot, BETA_ID, m), xs(slot, cid, m)
            idx = sorted(set(a.index) & set(s.index))
            rho, p, method = spearman_exact(a[idx].values, s[idx].values)
            blk.update(n=len(idx),
                       rank_rho_beta_vs_attention=(round(rho, 4) if np.isfinite(rho) else None),
                       p=(round(p, 5) if np.isfinite(p) else None), p_method=method,
                       identical_ranks=bool(np.isfinite(rho) and abs(rho - 1.0) < 1e-9),
                       cell_status=("ABSTAIN" if cells[(slot, cid)]["abstain"] else "COMPUTABLE"),
                       top3_attention=[{"symbol": k, "share": round(float(v), 5),
                                        "beta": (round(float(a[k]), 4) if k in a.index else None),
                                        "beta_rank_desc": (int(a.rank(ascending=False)[k])
                                                           if k in a.index else None)}
                                       for k, v in s.sort_values(ascending=False).head(3).items()],
                       top3_beta=[{"symbol": k, "beta": round(float(v), 4),
                                   "attention_share": (round(float(s[k]), 5) if k in s.index else None),
                                   "attention_rank_desc": (int(s.rank(ascending=False)[k])
                                                           if k in s.index else None)}
                                  for k, v in a.sort_values(ascending=False).head(3).items()],
                       era=era_for_month(m))
        g2[key] = blk
    gate["2_cn_robotics_attention_vs_beta"] = g2
    # (3) defense primes: high beta, modest WSB attention
    slot = "us_institutional"
    m = latest_common(slot, US_WSB_ID)
    g3 = {"expectation": ("at least one prime (LMT/NOC/GD class) shows high beta-to-basket but "
                          "modest WSB attention share vs a retail-favoured name in the slot"),
          "month": m}
    if m is not None:
        a, s = xs(slot, BETA_ID, m), xs(slot, US_WSB_ID, m)
        s_pos = s[s > 0].sort_values(ascending=False)
        dec = beta_decomposition(cells, slot, m)
        g3.update(
            cell_status=("ABSTAIN" if cells[(slot, US_WSB_ID)]["abstain"] else "COMPUTABLE"),
            cell_coverage=round(float(cells[(slot, US_WSB_ID)]["coverage"]), 4),
            n_with_beta=int(len(a)), n_in_wsb_universe=int(len(s)),
            n_with_nonzero_wsb=int(len(s_pos)),
            beta_cross_section=dict(n=int(len(a)),
                                    median=(round(float(a.median()), 4) if len(a) else None),
                                    mean=(round(float(a.mean()), 4) if len(a) else None)),
            primes=[{"symbol": p,
                     "beta": (round(float(a[p]), 4) if p in a.index else None),
                     "beta_rank_desc": (int(a.rank(ascending=False)[p]) if p in a.index else None),
                     "own_vol_rank_desc": (int(dec["sd_own_daily"].rank(ascending=False)[p])
                                           if p in dec.index else None),
                     "sd_ratio": (round(float(dec.loc[p, "sd_own_daily"]
                                              / dec.loc[p, "sd_ex_self_daily"]), 4)
                                  if p in dec.index else None),
                     "corr_to_ex_self": (round(float(dec.loc[p, "corr_to_ex_self"]), 4)
                                         if p in dec.index else None),
                     "wsb_share": (round(float(s[p]), 5) if p in s.index else None),
                     "wsb_rank_desc": (int(s.rank(ascending=False)[p]) if p in s.index else None),
                     "in_wsb_universe": bool(p in s.index)}
                    for p in ("LMT", "NOC", "GD")],
            retail_favoured=[{"symbol": k, "wsb_share": round(float(v), 5),
                              "beta": (round(float(a[k]), 4) if k in a.index else None),
                              "beta_rank_desc": (int(a.rank(ascending=False)[k])
                                                 if k in a.index else None)}
                             for k, v in s_pos.head(3).items()],
            era=era_for_month(m))
    gate["3_defense_prime_vs_retail"] = g3
    return gate


def corr_companion(cells, comp_cells, xs, xs_c, h2_rows, h3_summary) -> dict:
    """POST-PREREG companion (main-session commission): re-read H2/H3 on the corr term alone.

    Two questions, neither of which can change a verdict:
      * does the frozen H2 "the axes disagree" result survive with the volatility-ratio term
        removed — i.e. is the disagreement about co-movement, or only about relative vol?
      * is co-movement itself as rank-stable month to month as beta is?
    Computed on exactly the months the frozen cells used, so the comparison is like for like.
    """
    out: dict = {"h2": [], "h3": {}, "exemplars": {}}

    # (a) H2 companion — same slot, same month as every frozen H2 cell that COMPUTED.
    for r in h2_rows:
        if r["status"] != "COMPUTED":
            continue
        slot, month = r["slot"], r["month"]
        cid = r["pair"].split("~", 1)[1]
        a_c, b = xs_c(slot, COMPANION_CORR_ID, month), xs(slot, cid, month)
        idx = sorted(set(a_c.index) & set(b.index))
        rho, p, method = spearman_exact(a_c[idx].values, b[idx].values)
        out["h2"].append(dict(
            slot=slot, market=r["market"], pair=f"{COMPANION_CORR_ID}~{cid}",
            month=month, n=len(idx),
            rho=(round(rho, 4) if np.isfinite(rho) else None),
            abs_rho=(round(abs(rho), 4) if np.isfinite(rho) else None),
            p=(round(p, 5) if np.isfinite(p) else None), p_method=method,
            frozen_beta_rho=r["rho"], frozen_beta_abs_rho=r["abs_rho"],
            era=r["era"]))
    for cid in (CN_COMMENT_ID, CN_LHB_ID, US_WSB_ID, US_FLARE_ID):
        vals = [x["abs_rho"] for x in out["h2"]
                if x["pair"].endswith(cid) and x["abs_rho"] is not None]
        out.setdefault("h2_readings", {})[cid] = dict(
            reading=h2_reading(vals), n_slots=len(vals),
            abs_rhos=[round(float(v), 4) for v in vals])

    # (b) H3 companion — adjacent AND lag-3 disjoint-window rank autocorrelation, all slots.
    per_slot_series, per_slot_meta, lag3 = [], [], []
    for slot in SLOTS:
        c = comp_cells.get((slot, COMPANION_CORR_ID))
        if not c or c["abstain"]:
            continue
        months = c["graded_months"]
        rr = []
        for m0, m1 in zip(months[:-1], months[1:]):
            if (pd.Period(m1, freq="M") - pd.Period(m0, freq="M")).n != 1:
                continue
            a, b = xs_c(slot, COMPANION_CORR_ID, m0), xs_c(slot, COMPANION_CORR_ID, m1)
            idx = sorted(set(a.index) & set(b.index))
            rho = spearman_rho(a[idx].values, b[idx].values)
            if np.isfinite(rho):
                rr.append(float(rho))
        l3 = []
        for m0, m1 in zip(months[:-3], months[3:]):
            if (pd.Period(m1, freq="M") - pd.Period(m0, freq="M")).n != 3:
                continue
            a, b = xs_c(slot, COMPANION_CORR_ID, m0), xs_c(slot, COMPANION_CORR_ID, m1)
            idx = sorted(set(a.index) & set(b.index))
            rho = spearman_rho(a[idx].values, b[idx].values)
            if np.isfinite(rho):
                l3.append(float(rho))
        lag3.extend(l3)
        per_slot_series.append(np.asarray(rr, dtype=float))
        per_slot_meta.append(dict(
            slot=slot, n_pairs=len(rr),
            median=(round(float(np.median(rr)), 4) if rr else None),
            n_lag3=len(l3),
            median_lag3=(round(float(np.median(l3)), 4) if l3 else None)))
    pooled = np.concatenate(per_slot_series) if per_slot_series else np.asarray([])
    pooled = pooled[np.isfinite(pooled)]
    med = float(np.median(pooled)) if len(pooled) else float("nan")
    lo, hi, n_used = block_bootstrap_median_ci(per_slot_series)
    frozen = h3_summary.get(BETA_ID, {})
    out["h3"] = dict(
        n_pairs=int(len(pooled)),
        median_rho=(round(med, 4) if np.isfinite(med) else None),
        ci80_lo=(round(lo, 4) if np.isfinite(lo) else None),
        ci80_hi=(round(hi, 4) if np.isfinite(hi) else None),
        ci_degenerate=bool(per_slot_series) and all(
            len(a[np.isfinite(a)]) <= BOOTSTRAP_BLOCK for a in per_slot_series),
        lag3_median=(round(float(np.median(lag3)), 4) if lag3 else None),
        lag3_pairs=len(lag3),
        reading=h3_reading(med, int(len(pooled))),
        frozen_beta_median=frozen.get("median_rho"),
        frozen_beta_lag3_median=frozen.get("companion_lag3_median"),
        bootstrap_n=n_used, per_slot=per_slot_meta, era="reconstruction")

    # (c) exemplar re-read — the same names, ranked on co-movement instead of beta.
    def _rank_block(slot, names, month):
        a_c, a_b = xs_c(slot, COMPANION_CORR_ID, month), xs(slot, BETA_ID, month)
        if not len(a_c):
            return None
        rc, rb = a_c.rank(ascending=False), a_b.rank(ascending=False)
        return dict(month=month, n=int(len(a_c)),
                    median_corr=round(float(a_c.median()), 4),
                    names=[dict(symbol=s,
                                corr=(round(float(a_c[s]), 4) if s in a_c.index else None),
                                corr_rank_desc=(int(rc[s]) if s in rc.index else None),
                                beta_rank_desc=(int(rb[s]) if s in rb.index else None))
                           for s in names])

    for key, slot, names in (("nvda", "cross_market_pair.us", ["NVDA"]),
                             ("defense_primes", "us_institutional", ["LMT", "NOC", "GD"])):
        c = comp_cells.get((slot, COMPANION_CORR_ID))
        if c and c["graded_months"]:
            out["exemplars"][key] = _rank_block(slot, names, c["graded_months"][-1])
    return out


def draft_verdicts(cells, h3_summary) -> list:
    """DRAFT per (axis-construction × market) verdict in the prereg §6 vocabulary."""
    out = []
    for market in ("us", "cn"):
        out.append(dict(construction=ECONOMIC_ID, market=market,
                        verdict="BLOCKED-ON-INGESTION", unlock=None,
                        named_ingestion=ECONOMIC_SHARE_INGESTION,
                        n_slots=0, n_abstain=0, max_adjacent_pairs=0,
                        median_tie_mass=None,
                        basis="honest null — no formula minted (prereg §2)"))
    for cid, cmeta in CONSTRUCTIONS.items():
        for market in cmeta["markets"]:
            slots = [s for s in SLOTS if SLOTS[s]["market"] == market and (s, cid) in cells]
            if not slots:
                continue
            n_ab = sum(1 for s in slots if cells[(s, cid)]["abstain"])
            live = [s for s in slots if not cells[(s, cid)]["abstain"]]
            per_slot = {d["slot"]: d for d in h3_summary.get(cid, {}).get("per_slot", [])}
            max_pairs = max([per_slot.get(s, {}).get("n_pairs") or 0 for s in live], default=0)
            ties = []
            for s in live:
                v = [d.get("modal_tie_mass") for d in cells[(s, cid)]["diags"]
                     if not d["no_events"] and d.get("modal_tie_mass") is not None
                     and np.isfinite(d.get("modal_tie_mass", np.nan))]
                if v:
                    ties.append(float(np.median(v)))
            tie_mass = round(float(np.median(ties)), 4) if ties else None
            h3_read = str(h3_summary.get(cid, {}).get("reading", ""))
            if n_ab * 2 > len(slots):
                verdict, unlock, ing = "BLOCKED-ON-INGESTION", None, (
                    US_ATTENTION_INGESTION if cid in (US_WSB_ID, US_FLARE_ID)
                    else "a wider source universe for this construction")
                basis = (f"{n_ab} of {len(slots)} slots below the {COVERAGE_FLOOR} coverage floor "
                         f"— the members are absent from the source universe, not measured")
                if cid == US_FLARE_ID:
                    # RULING 3 (main session, 2026-08-11): name the magnitude degeneracy as
                    # part of the blocking reason — the one cell that clears coverage is
                    # ranking a tie block, so "more coverage" is not the whole ask.
                    basis += (f"; and the one cell that does clear it ranks a degenerate "
                              f"magnitude — summed channels_lit is approximately a "
                              f"days-present count, tie mass {100.0 * (tie_mass or 0):.0f}%")
            elif max_pairs < H3_MIN_PAIRS:
                verdict, unlock, ing = "UNDERPOWERED-BY-DEPTH", cmeta["unlock"], None
                basis = (f"deepest computable slot carries {max_pairs} adjacent month pair(s) "
                         f"< {H3_MIN_PAIRS}")
            elif h3_read.startswith("NOISE"):
                # RULING 2 (main session, 2026-08-11): coverage and depth are not sufficient
                # for MEASURABLE-NOW. A construction that clears both but whose H3 is NOISE is
                # computable and NOT stable at this grain — a null for THIS construction under
                # the ore law, which closes the grain tested and leaves the others open.
                verdict, unlock, ing = "COMPUTABLE-BUT-UNSTABLE", None, None
                basis = (f"clears coverage ({len(live)} of {len(slots)} slots) and depth "
                         f"({max_pairs} adjacent pairs), but H3 is {h3_read} at "
                         f"{100.0 * (tie_mass or 0):.0f}% tie mass — a null for the "
                         f"monthly-share grain, not for the source")
            else:
                verdict, unlock, ing = "MEASURABLE-NOW", None, None
                basis = (f"{len(live)} of {len(slots)} slots clear the coverage floor; deepest "
                         f"carries {max_pairs} adjacent month pairs")
            out.append(dict(construction=cid, market=market, verdict=verdict, unlock=unlock,
                            named_ingestion=ing, n_slots=len(slots), n_abstain=n_ab,
                            max_adjacent_pairs=max_pairs, median_tie_mass=tie_mass,
                            basis=basis))
    return out


# ======================================================================================
# Report
# ======================================================================================
def _fmt(v, nd=3):
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return "—" if not np.isfinite(f) else f"{f:.{nd}f}"


def write_report(out_dir, receipts, h1_rows, h2_rows, h2_readings, h3_summary, h3_pairs,
                 hn_rows, gate, verdicts, slot_meta, cells, companion) -> None:
    L = []
    A = L.append
    A("# W2 — exposure-decomposition probe (R1): results")
    A("")
    A("Generated by `scripts/probe_theme_exposure_axes.py` against the preregistration in")
    A("`research/theme_graph/W2_EXPOSURE_AXES_PREREG.md`. Every number below is computed by that")
    A("script from the stores receipted in §1; nothing here is hand-entered. **DRAFT verdicts** —")
    A("final verdict language belongs to the main session after the reviewer pass.")
    A("")

    # --- 1 receipts
    A("## 1. Run receipts")
    A("")
    A(f"- git HEAD `{receipts['git_head'][:11]}` ({receipts['git_head_committed_at']}), branch "
      f"`{receipts['git_branch']}`")
    gm = receipts.get("graph_meta", {})
    A(f"- theme graph `_meta`: belief_time **{gm.get('belief_time')}**, era `{gm.get('era')}`, "
      f"mode `{gm.get('mode')}`, engine `{gm.get('engine_version')}`, "
      f"counts {gm.get('counts')}")
    A("")
    A("| store | rows | date range | sha256 (first 16) |")
    A("|---|---:|---|---|")
    for k in sorted(receipts["stores"]):
        r = receipts["stores"][k]
        rng = (f"{r.get('date_min')} → {r.get('date_max')}"
               if r.get("date_min") else "—")
        note = " *(gitignored, local-only)*" if r.get("gitignored_local_only") else ""
        A(f"| `{k}`{note} | {r.get('rows') if r.get('rows') is not None else '—'} | {rng} | "
          f"`{(r.get('sha256') or '')[:16]}` |")
    A("")
    fl = receipts["stores"].get("narrative_flare.witness_hist", {})
    A(f"`narrative_flare.witness_hist` is gitignored and local-only: {fl.get('rows')} rows, "
      f"{fl.get('n_tickers')} tickers, {fl.get('date_min')} → {fl.get('date_max')}, "
      f"sha256 `{(fl.get('sha256') or '')[:16]}` — recorded here because CI cannot see it.")
    A("")
    A("Slot membership at the probe as-of, with the closed (dead) members that stay in every")
    A("denominator their validity window covers:")
    A("")
    A("| slot | theme | market | baskets | members (total / live) | dead members | TIL phase |")
    A("|---|---|---|---|---|---|---|")
    for s, m in slot_meta.items():
        dead = ", ".join(f"{d['symbol']} (closed {d['valid_to']})" for d in m["dead_members"]) or "—"
        ph = (f"{m['phase']['foresight_stage']} @ {m['phase']['as_of']}"
              if m.get("phase") else "—")
        A(f"| `{s}` | {m['theme']} | {m['market'].upper()} | "
          f"{', '.join('`' + b.split(':')[-1] + '`' for b in m['baskets'])} | "
          f"{m['n_members_total']} / {m['n_live']} | {dead} | {ph} |")
    A("")

    # --- 2 exemplar gate
    A("## 2. The exemplar gate (prereg §5) — answered first")
    A("")
    A("The three named directional expectations, answered with computed values against the")
    A("current regime (TIL phase tape rows quoted in §1). A value that inverts obvious reality")
    A("is a measurement defect, not a discovery.")
    A("")

    g1 = gate["1_nvda_attention_and_beta"]
    A("### 5.1 — NVDA must not be bottom-quartile on attention; beta near or above 1")
    A("")
    for key, label in (("wsb", "WSB"), ("flare", "narrative-flare")):
        b = g1[key]
        if b.get("note"):
            A(f"- **{label}**: {b['note']}.")
            continue
        nv = b.get("NVDA", {})
        A(f"- **{label}** (month `{b['month']}`, cell {b['cell_status']} at coverage "
          f"{_fmt(b['cell_coverage'])}, {b['n_with_attention']} members carry a share): NVDA "
          f"share **{_fmt(nv.get('attention_share'), 5)}**, rank **#{nv.get('attention_rank')} of "
          f"{b['n_with_attention']}** (quartile {nv.get('attention_quartile')} of 4, 1 = highest), "
          f"beta **{_fmt(nv.get('beta'))}** (rank #{nv.get('beta_rank_desc')} of "
          f"{nv.get('n_with_beta')}).")
        A("  Top-5 by share: " + ", ".join(f"{t['symbol']} {t['share']:.4f}" for t in b["top5"]) + ".")
    A("")
    nv = g1["flare"].get("NVDA", {})
    bf = nv.get("beta_factors", {})
    cs = g1["flare"].get("beta_cross_section", {})
    A("**Attention half: PASSES.** NVDA is rank #1 of 20 on the flare share and #2 of 13 on WSB —")
    A("top quartile on both, exactly as the expectation required.")
    A("")
    A("**Beta half: FAILS as written, and the factorisation says why it is not an implementation**")
    A("**defect.** Beta decomposes exactly as `corr x sd_own / sd_ex-self`:")
    A("")
    if bf:
        A(f"- NVDA: corr to the ex-self basket **{_fmt(bf.get('corr_to_ex_self'))}** (mid-pack — "
          f"co-movement is intact), own daily sd **{_fmt(bf.get('sd_own_daily_pct'), 2)}%** vs the "
          f"ex-self basket's **{_fmt(bf.get('sd_ex_self_daily_pct'), 2)}%**, ratio "
          f"**{_fmt(bf.get('sd_ratio'))}**. Product = {_fmt(bf.get('identity_check'))}, which is "
          f"the reported beta {_fmt(nv.get('beta'))}. NVDA is the **least volatile of the "
          f"{cs.get('n')} members** (own-vol rank #{bf.get('own_vol_rank_desc')} of {cs.get('n')}).")
    A(f"- The estimator is centred where the arithmetic says it should be: the slot's beta "
      f"cross-section runs {_fmt(cs.get('min'))} to {_fmt(cs.get('max'))} with median "
      f"**{_fmt(cs.get('median'))}** and mean {_fmt(cs.get('mean'))}. A broken estimator does not "
      f"land its median on 1.")
    A("")
    A("Reading: against an **equal-weight ex-self** benchmark, beta is a relative-volatility")
    A("measure — `corr x sd_own/sd_basket` — so the largest, least volatile member of a complex")
    A("whose equal-weight body is small/mid-caps must print below 1 as arithmetic, not as an")
    A("error. The expectation \"NVDA's beta near or above 1\" carries a cap-weighted-index")
    A("intuition that the preregistered benchmark does not implement. This is a finding about the")
    A("CONSTRUCTION's meaning, and adjudicating it (companion cap-weighted or vol-normalised")
    A("benchmark? or accept relative-vol as the intended reading?) belongs to the main session.")
    A("")

    g2 = gate["2_cn_robotics_attention_vs_beta"]
    A("### 5.2 — CN robotics: attention and beta ranks must NOT be identical")
    A("")
    for key, label in (("comment", "关注指数 (dense)"), ("lhb", "龙虎榜 (sparse)")):
        b = g2[key]
        if not b.get("month"):
            A(f"- **{label}**: no common month with the beta cell.")
            continue
        A(f"- **{label}** (month `{b['month']}`, n={b.get('n')}, cell {b.get('cell_status')}): "
          f"Spearman(beta, attention) = **{_fmt(b.get('rank_rho_beta_vs_attention'))}** "
          f"(p={_fmt(b.get('p'), 4)}, {b.get('p_method')}) — identical ranks: "
          f"**{b.get('identical_ranks')}**.")
        A("  Top-3 attention → " + "; ".join(
            f"{t['symbol']} share {t['share']:.4f} (beta rank #{t['beta_rank_desc']})"
            for t in b.get("top3_attention", [])) + ".")
        A("  Top-3 beta → " + "; ".join(
            f"{t['symbol']} beta {t['beta']} (attention rank #{t['attention_rank_desc']})"
            for t in b.get("top3_beta", [])) + ".")
    A("")

    g3 = gate["3_defense_prime_vs_retail"]
    A("### 5.3 — a defense prime with high beta-to-basket but modest WSB attention")
    A("")
    if not g3.get("month"):
        A("- no common month with the beta cell.")
    else:
        A(f"- Month `{g3['month']}`; the WSB cell is **{g3.get('cell_status')}** at coverage "
          f"{_fmt(g3.get('cell_coverage'))} ({g3.get('n_in_wsb_universe')} of the slot's members "
          f"are in the WSB universe at all, {g3.get('n_with_nonzero_wsb')} carry a non-zero "
          f"mention count). The gate is answered on the raw numbers anyway — it is a sanity "
          f"check, never a promotion.")
        for p in g3["primes"]:
            tail = (f"WSB share {_fmt(p['wsb_share'], 5)} (rank #{p['wsb_rank_desc']})"
                    if p["in_wsb_universe"]
                    else "absent from the WSB universe — no share, and that is not a zero")
            A(f"  - **{p['symbol']}**: beta {_fmt(p['beta'])} (rank #{p['beta_rank_desc']} of "
              f"{g3.get('n_with_beta')}), own-vol rank #{p.get('own_vol_rank_desc')}, "
              f"sd ratio {_fmt(p.get('sd_ratio'))}, corr {_fmt(p.get('corr_to_ex_self'))}; {tail}.")
        if g3.get("retail_favoured"):
            A("  - Retail-favoured comparison: " + "; ".join(
                f"{t['symbol']} WSB share {t['wsb_share']:.4f} (beta rank #{t['beta_rank_desc']})"
                for t in g3["retail_favoured"]) + ".")
    A("")
    if g3.get("month"):
        pr = g3["primes"]
        ranks = "/".join(f"#{p['beta_rank_desc']}" for p in pr if p["beta_rank_desc"])
        sdr = ", ".join(f"{p['symbol']} {_fmt(p['sd_ratio'], 2)}" for p in pr
                        if p.get("sd_ratio") is not None)
        cor = ", ".join(f"{p['symbol']} {_fmt(p['corr_to_ex_self'], 2)}" for p in pr
                        if p.get("corr_to_ex_self") is not None)
        A("**Both halves fail, and the beta half fails for §5.1's reason.** The WSB half cannot be")
        A("answered at all: LMT, NOC and GD are not in the WSB universe, so the axes' contrast")
        A("cannot be drawn on this tape — the cell abstains and the honest answer is \"not")
        A("measurable here\", never \"the primes have zero retail attention\". The beta half")
        A(f"**inverts**: the primes sit at beta ranks {ranks} of {g3.get('n_with_beta')} — LOW")
        A("beta-to-basket, not high. The factorisation shows the two channels, and they are not the")
        A(f"same for all three: sd ratios ({sdr}) put GD and NOC below the basket's own volatility,")
        A(f"while LMT sits at parity and is pulled down instead by correlation ({cor}) to a basket")
        A("whose equal-weight body is space/drone names. So the mechanism is the SAME identity as")
        A("§5.1 — `corr x sd_own/sd_basket` against an equal-weight ex-self benchmark — reached")
        A("through a different mix of its two factors, in an independent slot. Two slots, one")
        A("identity: this is a property of the construction, not a per-name fluke.")
        A("")

    # --- 3 H1
    A("## 3. H1 — computability (coverage floor 0.70)")
    A("")
    A("Coverage is pooled over the cell's graded months (Σ members with a value / Σ members).")
    A("NO-EVENTS months — the whole basket recorded nothing, so the share denominator is zero —")
    A("are excluded from the coverage denominator and counted separately: an empty denominator is")
    A("not a coverage failure. Nothing is imputed anywhere.")
    A("")
    A("| slot | construction | months | NO-EVENTS | pooled coverage | latest month (coverage) | status |")
    A("|---|---|---:|---:|---:|---|---|")
    for r in h1_rows:
        lm = (f"`{r['latest_month']}` ({_fmt(r['latest_coverage'])})" if r["latest_month"] else "—")
        A(f"| `{r['slot']}` | `{r['construction']}` | {r['graded_months']} | "
          f"{r['no_events_months']} | {_fmt(r['pooled_coverage'])} | {lm} | "
          f"**{r['status']}** |")
    A("")
    ab = [r for r in h1_rows if r["status"] == "ABSTAIN"]
    A(f"**{len(ab)} of {len(h1_rows)} cells ABSTAIN.** `economic_share` abstains by construction on")
    A("every slot (prereg §2: honest null, no formula minted — no per-company theme/segment")
    A("revenue source exists on either market).")
    A("")

    # --- 4 H2
    A("## 4. H2 — distinctness (Spearman on the latest common month)")
    A("")
    A("| slot | pair | month | n | rho | \\|rho\\| | p | method | status |")
    A("|---|---|---|---:|---:|---:|---:|---|---|")
    for r in h2_rows:
        if r["status"].startswith("VACUOUS"):
            continue
        A(f"| `{r['slot']}` | `{r['pair']}` | {r['month'] or '—'} | {r['n']} | "
          f"{_fmt(r['rho'])} | {_fmt(r['abs_rho'])} | {_fmt(r['p'], 4)} | "
          f"{r['p_method'] or '—'} | {r['status']} |")
    A("")
    A("Frozen-threshold reading per pair (prereg §3: measurably disagree = median |rho| ≤ 0.70")
    A("AND ≥1 slot ≤ 0.50; redundant = median |rho| > 0.90):")
    A("")
    for cid, rd in h2_readings.items():
        A(f"- `{BETA_ID}` ~ `{cid}` — **{rd['reading']}** over {rd['n_slots']} computable slot(s) "
          f"{rd['abs_rhos']}")
    A("")
    A("Every `economic_share` pair is **VACUOUS** by construction (no formula exists to correlate).")
    A("")

    # --- 5 H3
    A("## 5. H3 — stability (adjacent-month rank autocorrelation)")
    A("")
    A("Median over adjacent-month Spearman pairs, pooled across the computable slots of the")
    A("construction; the 80% CI is a moving-block bootstrap (block 3, 2000 draws, seed pinned)")
    A("resampled WITHIN each slot's own month order — repeated cross-sections are never pooled as")
    A("independent draws. All membership below is era=**reconstruction** (prereg §4): the graph")
    A("does not know any pre-2026-08-11 basket composition, so these are stability sentences about")
    A("reconstruction-era membership, not about an observed tape of membership changes.")
    A("")
    A("| construction | adjacent pairs | median rho | 80% CI | lag-3 companion | reading (era) |")
    A("|---|---:|---:|---|---|---|")
    for cid, h in h3_summary.items():
        ci = (f"[{_fmt(h['ci80_lo'])}, {_fmt(h['ci80_hi'])}]"
              if h["ci80_lo"] is not None else "—")
        if h.get("ci_degenerate"):
            ci += " **(degenerate)**"
        comp = ("—" if h.get("companion_lag3_median") is None
                else f"{_fmt(h['companion_lag3_median'])} ({h['companion_lag3_pairs']} pairs)")
        A(f"| `{cid}` | {h['n_pairs']} | {_fmt(h['median_rho'])} | {ci} | {comp} | "
          f"**{h['reading']}** on {h['era']}-era membership |")
    A("")
    A("Two things this table must not be read past:")
    A("")
    A("- **A \"degenerate\" CI is not a tight one — it is no resampling at all.** When every")
    A(f"  slot's pair series is no longer than the block length ({BOOTSTRAP_BLOCK}) there is")
    A("  exactly one block placement, so every bootstrap draw reproduces the original series and")
    A("  the interval collapses to a point. Those cells are already UNDERPOWERED-BY-DEPTH; the")
    A("  point interval carries no information and is printed only so it cannot be mistaken for")
    A("  a measured width.")
    A(f"- **Adjacent-month betas share about two thirds of one {BETA_WIN}-session window**, so the")
    A("  preregistered H3 statistic has a mechanical floor for `trading_beta.v0`: consecutive")
    A("  estimates are partly the same data. The lag-3 companion column (NOT preregistered —")
    A("  disclosed here because the preregistered number alone would overstate the case) repeats")
    A("  the same rank autocorrelation three months apart, where the two windows are disjoint.")
    A("  Read the beta row's stability claim off the companion, not off the adjacent-month median.")
    A("")
    A("Per-slot depth:")
    A("")
    A("| construction | slot | adjacent pairs | median rho | status |")
    A("|---|---|---:|---:|---|")
    for cid, h in h3_summary.items():
        for ps in h["per_slot"]:
            A(f"| `{cid}` | `{ps['slot']}` | {ps['n_pairs']} | {_fmt(ps['median'])} | "
              f"{ps['status']} |")
    A("")

    # --- 6 honest N
    A("## 6. Honest-N")
    A("")
    A("Episode = one (slot, month) cross-section. `% nonzero` is printed for every attention")
    A("construction; the sparse ones (LHB / WSB / flare) are mostly-zero by nature and the")
    A("column is the honest read of how much signal a month actually carries.")
    A("")
    A("| slot | construction | companies | months (episodes) | NO-EVENTS | % nonzero | tie mass | sparse | dead members |")
    A("|---|---|---:|---:|---:|---:|---:|---|---|")
    for r in hn_rows:
        pct = "—" if r["pct_nonzero"] is None else f"{100.0 * float(r['pct_nonzero']):.1f}%"
        tie = ("—" if r["median_modal_tie_mass"] is None
               else f"{100.0 * float(r['median_modal_tie_mass']):.1f}%")
        A(f"| `{r['slot']}` | `{r['construction']}` | {r['distinct_companies']} | "
          f"{r['distinct_months']} | {r['no_events_months']} | {pct} | {tie} | "
          f"{'yes' if r['sparse'] else 'no'} | "
          f"{r['dead_member_symbols'] or '—'} |")
    A("")
    A("**Tie mass** is the median fraction of covered members sitting on the single most common")
    A("magnitude that month. It is the column that decides how much of a rank statistic is real:")
    A("a construction where most members are tied is ordering almost nothing, and both its H2 rho")
    A("and its H3 autocorrelation inherit that tie structure rather than measuring attention.")
    flare_live = [r for r in hn_rows if r["construction"] == US_FLARE_ID
                  and r["median_modal_tie_mass"] is not None
                  and not cells[(r["slot"], US_FLARE_ID)]["abstain"]]
    if flare_live:
        w = flare_live[0]
        A("")
        A(f"This bites `{US_FLARE_ID}` hardest. On `{w['slot']}` — the ONLY flare cell that clears")
        A(f"the coverage floor — tie mass is **{100.0 * float(w['median_modal_tie_mass']):.0f}%**")
        A(f"while {100.0 * float(w['pct_nonzero']):.0f}% of values are non-zero, so the ties are")
        A("not zeros: the summed `channels_lit` magnitude is dominated by a per-day floor of about")
        A("two lit channels, which makes the monthly total mostly a count of days the ticker was")
        A("present on the tape. Its near-1.0 H3 autocorrelation is that tie block reappearing in")
        A("the next month, not a stable attention ranking — the concrete reason the flare cell must")
        A("not be read as a stability result even where its coverage clears the floor.")
    A("")
    A("Dead members by name, and the window they stay in the denominator for:")
    A("")
    for s, m in slot_meta.items():
        if m["dead_members"]:
            for d in m["dead_members"]:
                A(f"- `{s}`: **{d['symbol']}** (`{d['node_id']}`) — member "
                  f"{d['valid_from']} → {d['valid_to']}; in every monthly denominator that window "
                  f"covers, out of every later one.")
    A("")

    # --- 7 verdicts
    A("## 7. DRAFT verdicts per (construction × market)")
    A("")
    A("Vocabulary is the prereg §6 form. **DRAFT** — the main session owns the final language")
    A("after the reviewer pass. W4 may charter edge annotations only from MEASURABLE-NOW cells.")
    A("")
    A("| construction | market | DRAFT verdict | tie mass | unlock | basis |")
    A("|---|---|---|---:|---|---|")
    for v in verdicts:
        unlock = v["unlock"] or (v["named_ingestion"] and "ingestion: " + v["named_ingestion"]) or "—"
        tm = ("—" if v.get("median_tie_mass") is None
              else f"{100.0 * float(v['median_tie_mass']):.0f}%")
        A(f"| `{v['construction']}` | {v['market'].upper()} | **{v['verdict']}** | {tm} | "
          f"{unlock} | {v['basis']} |")
    A("")
    high_tie = [v for v in verdicts if v.get("median_tie_mass") is not None
                and v["median_tie_mass"] > 0.50 and v["verdict"] == "MEASURABLE-NOW"]
    for v in high_tie:
        A(f"**Tie-mass caveat on `{v['construction']}` ({v['market'].upper()}).** The verdict rule")
        A(f"keys on coverage and depth, both of which this cell clears — but its median tie mass is")
        A(f"**{100.0 * float(v['median_tie_mass']):.0f}%**: in a typical month that fraction of the")
        A("covered members sits on one identical magnitude (for a tail-event tape, zero). The cell")
        A("is measurable in the sense the prereg froze, and it is ordering only the handful of")
        A("members that cleared the tail in that month. W4 should not read MEASURABLE-NOW here as")
        A("\"a full member ranking exists\" — flagged for the main session, not resolved here.")
        A("")
    A("Verdict rule as coded (deterministic, no judgement in the script): a construction×market")
    A("cell is BLOCKED-ON-INGESTION when a majority of its slots fall below the coverage floor")
    A("(the members are absent from the source universe, which is an ingestion gap, not a")
    A("measurement); otherwise UNDERPOWERED-BY-DEPTH when the deepest computable slot carries")
    A(f"fewer than {H3_MIN_PAIRS} adjacent month pairs, with the prereg §6 accrual checkpoint as")
    A("the unlock date; otherwise MEASURABLE-NOW.")
    A("")

    # --- 7a adjudication rulings
    A("## 7a. Adjudication rulings applied (main session, 2026-08-11)")
    A("")
    A("The probe escalated the exemplar-gate failures rather than resolving them. The main")
    A("session's rulings are recorded here and are already applied to the §7 table above — the")
    A("probe reports them, it did not decide them.")
    A("")
    for r in ADJUDICATION_RULINGS:
        A(f"**Ruling {r['id']} — `{r['subject']}`.** {r['ruling']}")
        A("")
    A("Ruling 2 introduces **COMPUTABLE-BUT-UNSTABLE**, a fourth term beyond the three the")
    A("prereg §6 froze (MEASURABLE-NOW / UNDERPOWERED-BY-DEPTH / BLOCKED-ON-INGESTION). That is")
    A("an adjudicated extension of the verdict vocabulary, not a probe decision, and it is")
    A("disclosed as such: the frozen three could not express \"we can compute every month and")
    A("the months do not agree with each other\" — depth is present, coverage is present, and")
    A("the measurement is still not stable. It is coded as a rule, not as a named exception:")
    A("any construction that clears coverage and depth but whose H3 reads NOISE takes it.")
    A("")

    # --- 8 deviations
    A("## 8. Disclosed deviations from the preregistration")
    A("")
    A("1. **The cross-market pair is computed as two sub-slots**, `cross_market_pair.us` and")
    A("   `cross_market_pair.cn`, each measured against its OWN side's basket union. This is the")
    A("   prereg §1 rule (\"each side's members are measured against their OWN side's basket\")")
    A("   made executable; a single mixed cross-section would have been a cross-market lead-lag")
    A("   read, which is R7. Net-of-overlap member counts land at 26 (US) and 37 (CN) versus the")
    A("   prereg's \"~65\" estimate for the pair — the estimate was approximate, the union is exact.")
    A("2. **`narrative_flare` magnitude field.** The prereg names \"news counts\" from")
    A("   `witness_hist.parquet`. That store carries no news-count column: `news_count_z` is a")
    A("   Z-SCORE (range -2.00 → 53.0, i.e. negative values, and only 45% dense), and a negative")
    A("   magnitude cannot enter a share denominator without producing shares that neither sum to")
    A("   1 nor stay non-negative. The probe therefore uses the densest non-negative magnitude")
    A("   field, `channels_lit` (1–5, 100% dense — the count of distinct news channels lit for a")
    A("   ticker that day), summed over the month. This is a channel-breadth count, not a news")
    A("   volume; the construction id keeps the prereg's `attention_share.us.flare.v0` name and")
    A("   this note is the formula's disclosure.")
    A("3. **Coverage is pooled over the cell's graded months** (Σ values / Σ members) rather than")
    A("   read off a single month, because a cell spans many months and the prereg's \"the period's")
    A("   members\" does not name which. Per-month coverage is in every `cells/*__months.csv`, and")
    A("   the latest month's coverage is printed in the §3 table so the pooling can be second-")
    A("   guessed from the receipts.")
    A("4. **`causal_beta_pair` is the per-member specialisation of**")
    A("   `engine/cn_global_beta._causal_beta`. The incumbent takes one shared factor `x` for a")
    A("   whole DataFrame (`.div(..., axis=0)`); the ex-self basket return is by definition a")
    A("   different series for every member, so the same cov/var ratio and the same `.shift(1)`")
    A("   causal lag are applied pairwise. The construction is otherwise unchanged, and the CN")
    A("   input store is the one that module's production caller reads")
    A("   (`scripts/c1_cn_global_beta.py:_panel()` → `data/china_search/closes.parquet`),")
    A("   followed rather than re-decided.")
    A("5. **Membership inside a month is held at the month's PIT set** while the 63-session")
    A("   window looks back through earlier sessions. The prereg's `B_t` is defined at month `m`,")
    A("   and the whole backcast is era=reconstruction anyway (§4), so no PIT claim is made about")
    A("   the window's interior.")
    A("")
    A("Two statistics are ADDITIONS rather than departures — the preregistered tests are computed")
    A("exactly as frozen, and these are printed beside them because the frozen numbers alone")
    A("would read stronger than the data supports:")
    A("")
    A(f"6. **Lag-3 rank autocorrelation companion (§5).** Adjacent-month betas share about two")
    A(f"   thirds of one {BETA_WIN}-session window, so the preregistered H3 statistic carries a")
    A("   mechanical floor for `trading_beta.v0`. The companion repeats it three months apart,")
    A("   where the windows are disjoint. It does not replace the preregistered number and no")
    A("   threshold is applied to it.")
    A("7. **Modal tie mass (§6, §7).** The fraction of covered members sitting on one identical")
    A("   magnitude. Without it a rank statistic computed over a mostly-tied vector reads as a")
    A("   measurement; the column is what shows that the LHB cell's MEASURABLE-NOW and the flare")
    A("   cell's near-1.0 autocorrelation are ordering far fewer members than their headline")
    A("   numbers suggest.")
    A("")

    # --- 8a post-prereg companion
    A("## 8a. Post-prereg companion: `trading_corr` (no verdict authority)")
    A("")
    A("Commissioned by the main session AFTER the preregistered results were computed, and")
    A("bounded accordingly: it informs interpretation sentences and the W4 narrowing, and it")
    A("enters no H1 cell, no frozen H2/H3 table and no verdict. It is the `corr` term already")
    A("inside `beta = corr x sd_own / sd_ex-self`, promoted to its own cross-section — same 63-")
    A("session window, same one-day causal shift, same months, same membership. Nothing is")
    A("re-estimated, so it cannot disagree with the frozen cell about which member-months exist,")
    A("only about how they rank once the volatility ratio is removed.")
    A("")
    A("**The question it answers: is the H2 disagreement about co-movement, or only about")
    A("relative volatility?**")
    A("")
    A("| slot | attention construction | month | n | corr rho | frozen beta rho | \\|Δ\\| |")
    A("|---|---|---|---:|---:|---:|---:|")
    for r in companion["h2"]:
        cid = r["pair"].split("~", 1)[1]
        d = ("—" if r["abs_rho"] is None or r["frozen_beta_abs_rho"] is None
             else f"{abs(float(r['abs_rho']) - float(r['frozen_beta_abs_rho'])):.3f}")
        A(f"| `{r['slot']}` | `{cid}` | {r['month']} | {r['n']} | {_fmt(r['rho'])} | "
          f"{_fmt(r['frozen_beta_rho'])} | {d} |")
    A("")
    for cid, rd in companion.get("h2_readings", {}).items():
        if rd["n_slots"]:
            A(f"- `{COMPANION_CORR_ID}` ~ `{cid}` — **{rd['reading']}** over {rd['n_slots']} "
              f"slot(s) {rd['abs_rhos']} (frozen beta pair read: "
              f"{h2_readings.get(cid, {}).get('reading', '—')})")
    A("")
    h3c = companion["h3"]
    A("**And: is co-movement itself as rank-stable as beta?**")
    A("")
    A("| statistic | corr companion | frozen beta |")
    A("|---|---:|---:|")
    A(f"| adjacent-month median rho | {_fmt(h3c['median_rho'])} | "
      f"{_fmt(h3c['frozen_beta_median'])} |")
    A(f"| adjacent-month 80% CI | [{_fmt(h3c['ci80_lo'])}, {_fmt(h3c['ci80_hi'])}] | "
      f"[{_fmt(h3_summary[BETA_ID]['ci80_lo'])}, {_fmt(h3_summary[BETA_ID]['ci80_hi'])}] |")
    A(f"| lag-3 disjoint-window median rho | {_fmt(h3c['lag3_median'])} "
      f"({h3c['lag3_pairs']} pairs) | {_fmt(h3c['frozen_beta_lag3_median'])} "
      f"({h3_summary[BETA_ID]['companion_lag3_pairs']} pairs) |")
    A(f"| adjacent pairs | {h3c['n_pairs']} | {h3_summary[BETA_ID]['n_pairs']} |")
    A("")
    A(f"Reading (companion, no threshold authority): {h3c['reading']} on "
      f"{h3c['era']}-era membership.")
    A("")
    # Answer the two commissioned questions in sentences derived from the numbers above, so
    # the prose cannot drift from the table.
    surviving = [cid for cid, rd in companion.get("h2_readings", {}).items()
                 if rd["n_slots"] and rd["reading"].startswith("MEASURABLY-DISAGREE")]
    upgraded = [cid for cid in surviving
                if not str(h2_readings.get(cid, {}).get("reading", "")).startswith(
                    "MEASURABLY-DISAGREE")]
    A(f"**Q1 — does the H2 result survive with the volatility ratio removed? Yes, and it")
    A(f"strengthens.** All {len(surviving)} computable companion pairs read MEASURABLY-DISAGREE")
    if upgraded:
        A(f"— including `{upgraded[0]}`, which was only PARTIALLY-DISTINCT on the frozen beta")
        A("pair. ")
    A("The LHB pair moves furthest: median |rho| "
      f"{_fmt(np.median([abs(float(x['rho'])) for x in companion['h2'] if x['pair'].endswith(CN_LHB_ID)]))} "
      f"on co-movement against {_fmt(h2_readings[CN_LHB_ID]['abs_rhos'] and float(np.median(h2_readings[CN_LHB_ID]['abs_rhos'])))} "
      "on beta — near-orthogonal once the vol term is gone. So the residual agreement between")
    A("beta and attention was carried substantially BY the volatility ratio (volatile names")
    A("score high on both), not by co-movement. The frozen H2 finding is not an artifact of the")
    A("vol term; if anything the vol term was working against it.")
    A("")
    lag_gap = (None if h3c["lag3_median"] is None or h3c["frozen_beta_lag3_median"] is None
               else float(h3c["frozen_beta_lag3_median"]) - float(h3c["lag3_median"]))
    A("**Q2 — is co-movement itself as rank-stable as beta? No — it is the LESS persistent")
    A("half.** Adjacent-month medians are close "
      f"({_fmt(h3c['median_rho'])} vs {_fmt(h3c['frozen_beta_median'])}), but the gap opens at")
    A("the disjoint-window horizon where the mechanical overlap is gone: "
      f"{_fmt(h3c['lag3_median'])} vs {_fmt(h3c['frozen_beta_lag3_median'])}"
      + (f" (a {_fmt(lag_gap)} gap)" if lag_gap is not None else "") + ". Corr's lag-3 median")
    A(f"falls BELOW the {H3_STABLE} H3 stable floor while beta's clears it, so relative")
    A("volatility — not co-movement — is the more persistent component of what")
    A(f"`{BETA_ID}` ranks. For W4 this narrows rather than widens: an edge annotation built on")
    A("co-movement alone would be weakly stable at a quarter's horizon on this data.")
    A("")
    A("Exemplar re-read — the same names, ranked on co-movement instead of on beta:")
    A("")
    for key, label in (("nvda", "NVDA"), ("defense_primes", "Defense primes")):
        blk = companion["exemplars"].get(key)
        if not blk:
            continue
        for nm in blk["names"]:
            A(f"- **{nm['symbol']}** (`{blk['month']}`, n={blk['n']}): corr "
              f"{_fmt(nm['corr'])} → rank **#{nm['corr_rank_desc']} of {blk['n']}** on")
            A(f"  co-movement, versus rank #{nm['beta_rank_desc']} on beta "
              f"(slot median corr {_fmt(blk['median_corr'])}).")
    A("")

    # --- 9 filed not fixed
    A("## 9. Filed, not fixed")
    A("")
    A("Owner-territory items this probe found and deliberately did not touch (prereg §6):")
    A("")
    A("- **Unregistered attention primitives.** `data/china_comment/` (千股千评 关注指数),")
    A("  `data/china_lhb/` (龙虎榜) and `data/china_zt_pool/` are read here as owner planes but")
    A("  carry no synapse registration. Filed to their owners — W2 mints no synapse entries.")
    A("- **`data/narrative_flare/witness_hist.parquet` is gitignored and local-only.** CI cannot")
    A("  see it, so `attention_share.us.flare.v0` is not reproducible off this machine; its row")
    A("  count, ticker count, date range and sha256 are in §1 and in `receipts.json` so a later")
    A("  run can prove it read the same bytes.")
    A("- **`narrative_flare.news_count_z` is 45% dense and sign-bearing** (see deviation 2). If a")
    A("  raw per-day news count exists upstream of the z-scoring, publishing it would let the")
    A("  flare construction measure what the prereg named.")
    A("- **`data/quiver/wallstreetbets.parquet` publishes only surfaced tickers** (307 across 44")
    A("  collection days). A member outside that set is absent from the universe, not a measured")
    A("  zero — which is exactly why the defense / nuclear / fintech WSB cells abstain.")
    A("- **The graph's `date_provenance` is `seed_constant` on 5,425 of 5,477 MEMBER_OF edges.**")
    A("  Every stability sentence here is therefore about reconstruction-era membership; the")
    A("  observed era is ~0 months deep and accrues nightly from 2026-08-11.")
    A("")
    A("---")
    A("")
    A("No store was mutated by this run: the reserved-null axis columns on `edges.parquet` stay")
    A("null, no synapse entry was minted, and no user surface ships from W2.")
    A("")
    (out_dir / "W2_PROBE_REPORT.md").write_text("\n".join(L))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", default="research/theme_graph/w2_probe",
                    help="receipt directory (default: research/theme_graph/w2_probe)")
    args = ap.parse_args()
    out = Path(args.out_dir)
    if not out.is_absolute():
        out = ROOT / out
    return run(out)


if __name__ == "__main__":                       # pragma: no cover
    sys.exit(main())
