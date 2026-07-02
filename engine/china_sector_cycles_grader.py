"""China Sector Cycles — forward-log GRADER: close the falsifiability loop.

engine.china_sector_cycles.append_forward_log stamps every Shenwan L1 sector and every
A-share thematic basket daily (phase / pos / signature / signal / next-turn projection)
into data/china_sector_cycles/forward_log.parquet — an append-only, point-in-time
ledger keyed (date, id), keep-FIRST. Until this module existed NOTHING graded those
stamps, which made every CN rotation claim on the cycles page unfalsifiable. This
grader joins each stamp to its realized forward window on the SAME price series the
stamp was computed from (engine.china_sector_index.sw_close for sectors, the
baskets_china equal-weight level series for baskets) and publishes a scorecard.

DOCTRINE (hard prior — research/CHINA_SECTOR_PATHWAY_PHASE0.md): CN Phase-0 found
0/152 drivers clear a strict FWER bar on monthly sector forward returns. So this
grader NEVER emits a directional trading verdict. It grades three SEPARATE claims:

  (a) DRAWDOWN channel — do topping-region stamps (phase 'Peak' / 'Downturn', the
      SELL transition badge, a Stretched/Overheated euphoria-side signature — the
      exact state vocabulary of engine.sector_cycles._classify_phase and
      engine.china_sector_pathway._position) precede a DEEPER forward 21d/63d
      max-drawdown than the all-stamp base rate? A risk claim, not a return claim —
      the ONLY channel that may ever earn a sizing verdict.
  (b) RETURN channel — do washout→turn stamps (phase 'Recovery', the BUY badge)
      precede positive forward SHCOMP-relative returns? EXPECTED ~coin-flip (the
      Phase-0 null). Graded to PROVE the null: the null is a first-class,
      prominently-reported output (`return_null`), never an omission. This channel
      can never earn — a favourable CI here downgrades to 'inconclusive' by design.
  (c) CALIBRATION — hit-rate / Brier of the median-half-cycle proj_next direction
      (next turn 'peak' ⇒ the current up-leg is projected to continue; 'trough' ⇒
      to fall). Display-honesty metric; can never earn.

LOOK-AHEAD RULE (the repo's measured trap — engine/signal_quality.py marker-date
grading embedded +5.7pp/10d of leak; pinned by tests/test_signal_quality_no_leak.py):
every forward window anchors at the FIRST close STRICTLY AFTER the stamp date (the
bar-i+1 convention). grade() REFUSES any other convention with a ValueError — the
one deliberate exception to the never-raise contract, so a tainted caller fails loud
instead of publishing leaked numbers.

HONEST LIMITS. Basket series are current-membership equal-weight reconstructions
(engine.baskets_china): if membership is later edited, an old stamp's realized window
is re-marked on the refreshed series — sectors (fixed Shenwan indices) carry no such
drift. Relative returns ffill the benchmark onto each series' own calendar (the
engine.sector_cycles._basket_rs convention). Nothing here is read back into any
score, gate or sizing decision — display/research only.

Pure + additive + never-raise (except the convention guard): compute() returns {} on
any missing input.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from engine import grading_stats as _gs

log = logging.getLogger(__name__)

SCHEMA = "china_sector_cycles.grader.v1"

# ── PRE-REGISTERED GATES — fixed before any stamp had matured; do NOT tune ──────────
HORIZONS = (21, 63)     # trading-BAR forward windows: the doctrine's 21d/63d MaxDD horizons.

# Shared constants from engine.grading_stats (library-not-copy — D2 §2.3):
MIN_EARN_N = _gs.MIN_N_DEFAULT  # 40. mirrors engine.index_leadership_track._MIN_PROVEN_N.
                                # WHY: below ~40 matured obs every CI here is wide enough
                                # to fit any story — "accruing", full stop.
BOOT_DRAWS = _gs.BOOT_DRAWS    # 800. date-blocked bootstrap draws.
BOOT_SEED = _gs.BOOT_SEED      # 7. deterministic seed.
CONVENTION = _gs.CONVENTION    # "first_close_strictly_after_stamp" — the ONLY legal anchor.

RETURN_MIN_EDGE = 0.05  # WHY: the return claim stays merely 'inconclusive' while its Wilson
                        # CI still admits ≥ +5pp over base; once the CI-hi drops below
                        # base+5pp the claim can't even pay A-share round-trip costs —
                        # falsified. (It can never be 'earning' regardless — doctrine.)
SIG_EUPHORIA = 65.0     # euphoria-side signature = score > 65: the Stretched (>65) /
                        # Overheated (>85) bands of engine.china_sector_pathway._position —
                        # the code's own washout(0)↔euphoria(100) vocabulary.

# DRAWDOWN earning gate (pre-registered): earning ⇔ n_matured ≥ MIN_EARN_N AND the
# date-blocked bootstrap CI on (conditional mean MaxDD − base mean MaxDD) sits ENTIRELY
# below zero (conditional strictly deeper). Falsified ⇔ the CI sits entirely above zero
# (conditional strictly SHALLOWER than base — the topping claim proven wrong). Anything
# else is inconclusive. Registered here so the gate cannot drift toward whatever the
# first matured sample happens to show.

# State vocabulary — derived from the stamp writer (engine.china_sector_cycles
# append_forward_log) + the phase wheel (engine.sector_cycles._classify_phase: Peak =
# pos≥68 & rising = "Topping"; Downturn = falling = "Rolling over"; Recovery = pos≤32 &
# turning up = "Prime entry") + the transition badges (SELL = pos≥55 & osc_slope<-0.5;
# BUY = pos≤45 & osc_slope>0.5).
_DD_STATES = ("phase_peak", "phase_downturn", "signal_sell", "sig_euphoria")
_RET_STATES = ("phase_recovery", "signal_buy")
_CAL_STATES = ("proj_all", "proj_peak", "proj_trough")

_CAVEAT_EN = ("Conditional, display-only context — not a forecast or a trading signal. "
              "Phase 0 found no China driver clears a strict significance bar on monthly "
              "sector returns; this scorecard exists to MEASURE the cycle page's own "
              "claims, and every cell below its minimum sample is 'accruing', full stop.")
_CAVEAT_ZH = ("仅为条件化展示，非预测或买卖信号。Phase 0 检验显示无单一驱动能通过严格显著性门槛；"
              "此记分卡用于度量周期页自身的论断，样本不足的单元一律标记为累积中。")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────── forward-window primitives ──────
# Delegated to engine.grading_stats (library-not-copy, D2 §2.3). Local names preserved
# so internal call-sites do not need to change.

def _entry_pos(idx: pd.DatetimeIndex, stamp: pd.Timestamp) -> int | None:
    """Bar-i+1 anchor — delegates to grading_stats.entry_pos (one implementation)."""
    return _gs.entry_pos(idx, stamp)


def _fwd(px: pd.Series, stamp: pd.Timestamp, h: int) -> dict | None:
    """Forward window — delegates to grading_stats.fwd_window (one implementation)."""
    return _gs.fwd_window(px, stamp, h)


# ─────────────────────────────────────────────────────────────────── statistics ─────────
# Delegated to engine.grading_stats (library-not-copy, D2 §2.3).

def _wilson(k: int, n: int) -> tuple[float, float] | None:
    """Wilson CI — delegates to grading_stats.wilson_ci (one implementation)."""
    return _gs.wilson_ci(k, n)


def _boot_gap_ci(dates: np.ndarray, vals: np.ndarray, mask: np.ndarray) -> list | None:
    """Date-blocked bootstrap CI — delegates to grading_stats.block_bootstrap_ci."""
    return _gs.block_bootstrap_ci(dates, vals, mask)


def _dd_verdict(n: int, ci: list | None) -> str:
    """Drawdown verdict — delegates to grading_stats.dd_verdict (one implementation)."""
    return _gs.dd_verdict(n, ci)


def _rate_verdict(n: int, ci: tuple | None, base: float | None) -> str:
    """Return/calibration verdict — delegates to grading_stats.rate_verdict."""
    return _gs.rate_verdict(n, ci, base, min_edge=RETURN_MIN_EDGE)

# ──────────────────────────────────────────────────────────────── state flags ───────

def _flags(r: dict) -> dict:
    sig = r.get("signature")
    sig = float(sig) if sig is not None and pd.notna(sig) else None
    return {
        "phase_peak": r.get("phase") == "Peak",
        "phase_downturn": r.get("phase") == "Downturn",
        "signal_sell": r.get("signal") == "SELL",
        "sig_euphoria": sig is not None and sig > SIG_EUPHORIA,
        "phase_recovery": r.get("phase") == "Recovery",
        "signal_buy": r.get("signal") == "BUY",
        "proj_peak": r.get("proj_next") == "peak",
        "proj_trough": r.get("proj_next") == "trough",
    }


# ─────────────────────────────────────────────────────────────────── grading ────────

def grade(log_df: pd.DataFrame | None, prices: dict, bench: pd.Series | None = None,
          horizons=HORIZONS, convention: str = CONVENTION) -> dict:
    """Pure grading core: PIT-join the forward-log stamps to realized forward windows
    and emit the scorecard dict. `prices` = {stamp id -> close/level Series} — the SAME
    series the stamps were computed on. Never raises EXCEPT the convention guard."""
    if convention != CONVENTION:
        raise ValueError(
            f"look-ahead guard: forward grading must anchor at the {CONVENTION!r} bar "
            "(bar i+1). Stamp/marker-date anchoring leaks the confirmation bar into the "
            "'forward' window — the engine/signal_quality.py trap that measured "
            "+5.7pp/10d of phantom edge (tests/test_signal_quality_no_leak.py). Refused.")
    try:
        return _grade(log_df, prices, bench, tuple(horizons))
    except Exception as e:  # noqa: BLE001 — additive: a broken grade never breaks a build
        log.warning("china_sector_cycles_grader: grade failed: %s", e)
        return {}


def _grade(log_df: pd.DataFrame | None, prices: dict, bench: pd.Series | None,
           horizons: tuple) -> dict:
    if log_df is None or len(log_df) == 0 or not prices:
        return {}
    df = log_df.copy()
    if "date" not in df.columns or "id" not in df.columns:
        return {}
    # PIT integrity: keep-FIRST per (date, id) — the writer's semantics, re-enforced so a
    # rewritten/merged log can never let a later re-stamp overwrite what was knowable first.
    df = df.drop_duplicates(subset=["date", "id"], keep="first")
    df = df[df["date"].notna() & df["id"].notna()]

    ratio_cache: dict = {}

    def _ratio(sid: str, px: pd.Series) -> pd.Series | None:
        if bench is None or bench.dropna().empty:
            return None
        if sid not in ratio_cache:
            b = bench.dropna().sort_index().reindex(px.index).ffill()
            r = (px / b).dropna()
            ratio_cache[sid] = r if not r.empty else None
        return ratio_cache[sid]

    matured = {h: [] for h in horizons}          # graded rows per horizon
    pending = {h: {"total": 0} for h in horizons}
    n_unpriced = 0

    for r in df.to_dict("records"):
        sid = str(r["id"])
        px = prices.get(sid)
        if px is None:
            n_unpriced += 1
            continue
        px = px.dropna().sort_index()
        if px.empty:
            n_unpriced += 1
            continue
        try:
            stamp = pd.Timestamp(r["date"])
        except Exception:  # noqa: BLE001
            continue
        fl = _flags(r)
        rr = _ratio(sid, px)
        for h in horizons:
            w = _fwd(px, stamp, h)
            if w is None:                        # window not fully realized → pending
                pending[h]["total"] += 1
                for k, v in fl.items():
                    if v:
                        pending[h][k] = pending[h].get(k, 0) + 1
                continue
            rel = None
            if rr is not None:
                wr = _fwd(rr, stamp, h)
                rel = wr["ret"] if wr else None
            matured[h].append({"date": str(r["date"]), "id": sid,
                               "entry": str(w["entry"].date()),
                               "ret": w["ret"], "maxdd": w["maxdd"], "rel": rel, **fl})

    channels = {
        "drawdown": _dd_channel(matured, pending, horizons),
        "return": _ret_channel(matured, pending, horizons),
        "calibration": _cal_channel(matured, pending, horizons),
    }
    return_null = _return_null(channels["return"], horizons)

    cal = _calendar(prices, bench)
    stamps = sorted(df["date"].astype(str).unique())
    meta_asof = str(cal.max().date()) if cal is not None and len(cal) else (stamps[-1] if stamps else None)
    out = {
        "schema": SCHEMA, "as_of": meta_asof, "generated_at": _now_iso(),
        "is_context_only": True,
        "caveat_en": _CAVEAT_EN, "caveat_zh": _CAVEAT_ZH,
        "convention": CONVENTION,
        "gates": {"min_earn_n": MIN_EARN_N, "horizons": [int(h) for h in horizons],
                  "return_min_edge": RETURN_MIN_EDGE, "sig_euphoria": SIG_EUPHORIA,
                  "bootstrap": {"draws": BOOT_DRAWS, "seed": BOOT_SEED, "blocks": "stamp dates"}},
        "log": {"n_rows": int(len(df)), "n_ids": int(df["id"].nunique()),
                "n_dates": len(stamps),
                "first_stamp": stamps[0] if stamps else None,
                "last_stamp": stamps[-1] if stamps else None,
                "n_unpriced": int(n_unpriced),
                "n_matured": {str(h): len(matured[h]) for h in horizons},
                "n_pending": {str(h): pending[h]["total"] for h in horizons},
                "earliest_maturity": {str(h): _earliest_maturity(stamps, cal, h) for h in horizons}},
        "return_null": return_null,
        "channels": channels,
    }
    return out


def _cell_dd(rows: list, pend: dict, state: str) -> dict:
    sub = [r for r in rows if r.get(state)]
    n, n_base = len(sub), len(rows)
    cond = base = effect = ci = None
    if n and n_base:
        vals = np.array([r["maxdd"] for r in rows], dtype=float)
        mask = np.array([bool(r.get(state)) for r in rows])
        dates = np.array([r["date"] for r in rows])
        cond = round(float(vals[mask].mean()), 4)
        base = round(float(vals.mean()), 4)
        effect = round(cond - base, 4)
        ci = _boot_gap_ci(dates, vals, mask)
    return {"verdict": _dd_verdict(n, ci), "n_matured": n, "n_base": n_base,
            "n_pending": int(pend.get(state, 0)),
            "cond_mean_maxdd": cond, "base_mean_maxdd": base,
            "effect": effect, "ci": ci}


def _cell_rate(rows: list, pend: dict, state: str, key: str, base_rows: list | None = None) -> dict:
    """Rate cell: share of positive `key` ('rel' or a bool hit) in-state vs the base pool."""
    pool = [r for r in (base_rows if base_rows is not None else rows) if r.get(key) is not None]
    sub = [r for r in rows if r.get(state) and r.get(key) is not None]
    n, n_base = len(sub), len(pool)
    cond = base = effect = None
    ci = None
    if n:
        k = sum(1 for r in sub if r[key] > 0)
        cond = round(k / n, 3)
        ci = _wilson(k, n)
        ci = list(ci) if ci else None
    if n_base:
        base = round(sum(1 for r in pool if r[key] > 0) / n_base, 3)
    if cond is not None and base is not None:
        effect = round(cond - base, 3)
    return {"verdict": _rate_verdict(n, ci, base), "n_matured": n, "n_base": n_base,
            "n_pending": int(pend.get(state, 0)),
            "cond_rate": cond, "base_rate": base, "effect": effect, "ci": ci}


def _dd_channel(matured: dict, pending: dict, horizons: tuple) -> dict:
    states = {s: {str(h): _cell_dd(matured[h], pending[h], s) for h in horizons}
              for s in _DD_STATES}
    return {
        "claim_en": ("Topping-region stamps (Peak/Downturn phase, SELL badge, euphoria-side "
                     "signature) precede a DEEPER forward max-drawdown than the all-stamp base."),
        "sizing_eligible": True,   # the ONLY channel that may ever earn a sizing verdict
        "earn_rule": ("n_matured >= %d AND the date-blocked bootstrap CI on the conditional-vs-"
                      "base MaxDD gap sits entirely below zero" % MIN_EARN_N),
        "states": states,
    }


def _ret_channel(matured: dict, pending: dict, horizons: tuple) -> dict:
    states = {s: {str(h): _cell_rate(matured[h], pending[h], s, "rel") for h in horizons}
              for s in _RET_STATES}
    return {
        "claim_en": ("Washout→turn stamps (Recovery phase, BUY badge) precede positive forward "
                     "SHCOMP-relative returns. EXPECTED NULL: Phase-0 found 0/152 drivers clear "
                     "a strict FWER bar — this claim is presumed a coin-flip until the data says "
                     "otherwise, and it is graded precisely to prove that null."),
        "sizing_eligible": False,
        "never_earning": ("doctrine: this channel can never emit a directional/sizing verdict; "
                          "a favourable CI is capped at 'inconclusive' and flagged for re-research."),
        "states": states,
    }


def _cal_channel(matured: dict, pending: dict, horizons: tuple) -> dict:
    out: dict = {}
    for h in horizons:
        rows = [r for r in matured[h] if r.get("proj_peak") or r.get("proj_trough")]
        for r in rows:
            implied_up = bool(r.get("proj_peak"))       # next turn 'peak' ⇒ up-leg continues
            r["_hit"] = 1.0 if ((r["ret"] > 0) == implied_up) else -1.0   # >0 = hit for _cell_rate
        for s in _CAL_STATES:
            key = {"proj_all": None, "proj_peak": "proj_peak", "proj_trough": "proj_trough"}[s]
            sub = rows if key is None else [r for r in rows if r.get(key)]
            n = len(sub)
            k = sum(1 for r in sub if r["_hit"] > 0)
            hit = round(k / n, 3) if n else None
            ci = _wilson(k, n) if n else None
            ci = list(ci) if ci else None
            pend_n = (pending[h].get("proj_peak", 0) + pending[h].get("proj_trough", 0)
                      if key is None else pending[h].get(key, 0))
            cell = {"verdict": _rate_verdict(n, ci, 0.5), "n_matured": n,
                    "n_pending": int(pend_n),
                    "hit_rate": hit, "base_rate": 0.5,
                    "brier": round(1.0 - hit, 3) if hit is not None else None,
                    "effect": round(hit - 0.5, 3) if hit is not None else None, "ci": ci}
            out.setdefault(s, {})[str(h)] = cell
    return {
        "claim_en": ("The median-half-cycle projection's next-turn direction (proj_next: 'peak' "
                     "⇒ the series rises into the next turn; 'trough' ⇒ falls) beats a coin-flip. "
                     "proj_next is a hard call (implied p=1), so its Brier score degenerates to "
                     "the miss rate — reported as such, no false precision."),
        "sizing_eligible": False,
        "states": out,
    }


def _return_null(ret_channel: dict, horizons: tuple) -> dict:
    """The return channel's expected-null status as a FIRST-CLASS output."""
    parts = []
    all_accruing = True
    for s, by_h in (ret_channel.get("states") or {}).items():
        for h in horizons:
            c = by_h.get(str(h)) or {}
            if c.get("verdict") != "accruing":
                all_accruing = False
            if c.get("n_matured"):
                parts.append(f"{s} {h}d: {c['cond_rate']} vs base {c['base_rate']} "
                             f"(n={c['n_matured']}, {c['verdict']})")
    status = ("all cells accruing — nothing matured yet; the null stands unchallenged and "
              "unproven" if all_accruing else "; ".join(parts))
    return {
        "expected": True,
        "prior_en": ("Phase-0 prior: 0/152 China drivers cleared a strict FWER bar on monthly "
                     "sector forward returns — the washout→turn RETURN claim is presumed a "
                     "coin-flip. This grader exists to prove (or, against expectation, "
                     "embarrass) that null in public."),
        "status_en": status,
    }


def _calendar(prices: dict, bench: pd.Series | None) -> pd.DatetimeIndex | None:
    if bench is not None and not bench.dropna().empty:
        return bench.dropna().sort_index().index
    best = None
    for s in prices.values():
        if s is None:
            continue
        s = s.dropna()
        if len(s) and (best is None or len(s) > len(best)):
            best = s.sort_index().index
    return best


def _earliest_maturity(stamps: list, cal: pd.DatetimeIndex | None, h: int) -> dict | None:
    """When the OLDEST stamp's h-bar window completes on the reference calendar —
    realized date if already matured, else a business-day projection."""
    if not stamps or cal is None or not len(cal):
        return None
    d0 = pd.Timestamp(stamps[0])
    j = int(cal.searchsorted(d0, side="right"))
    if j >= len(cal):
        est = d0 + pd.offsets.BDay(h + 1)
        return {"date": str(est.date()), "matured": False, "projected": True}
    if j + h < len(cal):
        return {"date": str(cal[j + h].date()), "matured": True, "projected": False}
    extra = j + h - (len(cal) - 1)
    est = cal[-1] + pd.offsets.BDay(extra)
    return {"date": str(est.date()), "matured": False, "projected": True}


# ───────────────────────────────────────────────────────────── real-data entry ──────

def compute() -> dict:
    """Load the real forward log + the SAME price loaders the stamp writer used, then
    grade. Never raises; returns {} on any missing input."""
    try:
        from lib import config
        p = config.data_dir() / "china_sector_cycles" / "forward_log.parquet"
        if not p.exists():
            return {}
        log_df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("china_sector_cycles_grader: cannot read forward log: %s", e)
        return {}
    try:
        from engine import china_sector_index as csi
        bench = csi.benchmark_close()
    except Exception as e:  # noqa: BLE001
        log.warning("china_sector_cycles_grader: benchmark load failed: %s", e)
        bench = None

    ids = sorted({str(i) for i in log_df.get("id", pd.Series(dtype=str)).dropna().unique()})
    prices: dict = {}

    basket_chart = None
    if any(i.startswith("b-") for i in ids):
        try:
            from engine.baskets_china import compute_china_baskets
            bdata = compute_china_baskets()
            basket_chart = (bdata or {}).get("chart")
        except Exception as e:  # noqa: BLE001
            log.warning("china_sector_cycles_grader: baskets plane failed (%s) — basket "
                        "stamps will be reported unpriced", e)

    for sid in ids:
        try:
            if sid.startswith("b-"):
                if basket_chart:
                    from engine.china_sector_cycles import _basket_series
                    s = _basket_series(sid[2:], basket_chart)
                else:
                    s = None
            else:
                from engine import china_sector_index as csi
                s = csi.sw_close(sid)
        except Exception as e:  # noqa: BLE001
            log.debug("china_sector_cycles_grader: price load %s failed: %s", sid, e)
            s = None
        if s is not None and not s.dropna().empty:
            prices[sid] = s

    if not prices:
        return {}
    return grade(log_df, prices, bench)
