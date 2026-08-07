"""W5.2 — the FRESH_TICKS-extension frozen-frame replay (US Superintelligence §3 rung 1).

THE QUESTION. ``engine/confluence_tiers.FRESH_TICKS = 2`` expires a cross's buyability after
two native-timeframe ticks. The §5 S-B stand-in measured, WITHIN actual board admissions on
the frozen ``retro_grades`` buy/H=10 frame, that outcomes IMPROVE with cross age right up to
that boundary (ticks 0 → 20.8% loser / +0.10pp demeaned; 1 → 10.0% / +0.92; 2 → 11.5% /
+3.04; n=53/30/26). This instrument asks the only question that follows: does the gradient
EXTEND to ticks 3-4 — the cohort the freshness gate currently excludes — or does it peak at
the boundary? Nothing here changes a gate. FRESH_TICKS is untouched; the prereg that consumes
these numbers is ``FRESH_TICKS_EXTENSION_PREREG.md``.

THE CONSTRUCTION (the crux — the counterfactual extends ONLY the freshness clock).
``tier_stream`` already exposes ``fresh_ticks`` as a documented knob-sweep override, so the
counterfactual needs no re-derivation at all: the SAME production function is called twice on
the SAME panel, once at the shipped gate and once extended. Every other leg — the not-topped
veto (stoch_ob / stoch_bear / macd_bear), ``long_bias``, ``recent3``/``confirm3``,
``rsi_ok``, the T3 persistence hardening — is re-evaluated per day by the engine itself under
both settings. A day enters the extension cohort only if the cross is still intact and every
veto leg still passes; the ``macd_bear`` leg is what enforces "cross still intact" (a 3D
RSI-MACD that fell back below its signal blanks the day).

  gate  = tier_stream(close, fresh_ticks=FRESH_TICKS)   # what the board admits today
  ext   = tier_stream(close, fresh_ticks=EXT_TICKS)     # freshness clock extended, nothing else

COMPARABILITY CONTROL. The ticks 0/1/2 cohorts are built the SAME synthetic way, on the same
panel and the same evaluation window, as the ticks 3/4 cohorts. The primary comparison is
therefore synthetic-vs-synthetic. S-B's measured-admissions table is quoted beside it as the
anchor, and the divergence between the synthetic ticks-0/2 cells and S-B's is measured and
printed: that delta IS the board-selection effect (S-B saw only names the board actually
admitted; this panel sees every name that reached the state). It is stated, not hidden.

WHAT A TICK COHORT IS CONDITIONED ON — say it out loud. A name at ticks 3 is, by
construction, a cross that SURVIVED three ticks without topping or rolling over. The tick-0
cohort survived nothing. That conditioning is inherent to the gate question rather than a bias
to scrub: on the evening the board would fire, survival-to-tick-3 is already observed, so the
conditioning is ex-ante available and involves no lookahead. The paired within-cross block
below separates the two readings anyway — "later entries do better" (mechanism) vs "crosses
that survive are better crosses" (selection).

UNITS. Primary = one row per (ticker, cross episode, tick level): the FIRST eligible session
at which that cross reaches that tick age. Overlapping daily sessions inside one tick bucket
are reported as the supporting pooled view, never as independent observations.

OUTCOMES. Next-bar fill, matching production grading (``engine.grading.forward_metrics``:
entry = close of the session STRICTLY AFTER the signal bar; exit = H sessions later). Excess
vs SPY (``data/yahoo/SPY.parquet``, the benchmark ``scripts/grade_us_board.py`` uses) AND
excess vs the same-day universe median — both reported. loser := excess-vs-SPY < -3pp,
threshold stated, medians printed so no verdict hangs on it. H=10 primary (the S-B/record
basis), H=21 supporting (the doors' primary horizon). The evaluation window is cut so every
row carries full H=21 coverage: H=10 and H=21 grade an IDENTICAL row set, and no denominator
is conditioned on resolution.

FROZEN-REPLAY PIN. Every series is truncated at :data:`FRAME_ASOF` before anything is
computed. This is load-bearing, not cosmetic (the CN #4522 precedent): the caches accrue a bar
nightly, so an unpinned re-run is a DIFFERENT measurement and would break the S-B reproduction
gate. Re-running against a later snapshot needs its own pin.

REPRODUCTION GATE. Before any new number is printed, this script reproduces S-B's
``by_cross_age_ticks`` table from the current stores and compares it cell-by-cell to the
frozen ``superintelligence_standins_results.json``. A mismatch is reported as a hard FAIL in
the results JSON and on stdout.

Exploratory frozen-frame replay. Confers no authority; changes no gate; arms a prereg.
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

REPO = str(Path(__file__).resolve().parents[2])
HERE = os.path.dirname(os.path.abspath(__file__))
SB_FROZEN = os.path.join(HERE, "superintelligence_standins_results.json")
os.chdir(REPO)
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

# PRICE-ADJUSTMENT AUDIT (2026-08-06). This packet prices NAMES from the breadth close
# caches (raw, re-based only at an infrequent full rebuild) and the BENCHMARK from
# data/yahoo/SPY.parquet (back-adjusted), so a name that goes ex-distribution inside a
# measurement window books its own payout as a loss against an unaffected SPY. Basis is
# now switchable so the frozen result and its adjusted-first correction are BOTH
# reproducible; `cache` is the default and reproduces the shipped JSON unchanged.
# See PRICE_ADJUSTMENT_AUDIT_2026-08-06.md.
import price_ladder  # noqa: E402  (needs HERE on the path)

PRICE_BASIS = os.environ.get("PRICE_BASIS", "cache").strip().lower()
if PRICE_BASIS not in ("cache", "adjusted"):
    raise SystemExit(f"PRICE_BASIS must be 'cache' or 'adjusted', got {PRICE_BASIS!r}")
OUT = os.path.join(HERE, "fresh_ticks_extension_replay_results.json"
                   if PRICE_BASIS == "cache"
                   else "fresh_ticks_extension_replay_adjusted_rerun.json")
PANEL_PROVENANCE: dict = {}

from engine import confluence_tiers as ct  # noqa: E402
from engine.confluence_tiers import (  # noqa: E402
    BUY_RSI_MAX, CONF_W, OB, RSI_LEN,
    _last_true_pos, _rsi_macd, _since, _stoch_rsi_kd, _tf_bars, _ticks_since_vec,
    _to_daily, _xup,
)
from engine.technicals import rsi  # noqa: E402

# --------------------------------------------------------------------------- #
# frame constants
# --------------------------------------------------------------------------- #
FRAME_ASOF = pd.Timestamp("2026-07-31")   # frozen-replay pin — the caches' last committed bar
GATE_TICKS = int(ct.FRESH_TICKS)          # READ from the engine (2), never hardcoded here
EXT_TICKS = 6                             # 3/4 = the question; 5/6 = decay context only
H_PRIMARY, H_SUPPORT = 10, 21
LOSER_PP = -3.0
GROUPS = ("breadth", "midcap_breadth", "smallcap_breadth")
SB_WINDOW = (pd.Timestamp("2026-06-16"), pd.Timestamp("2026-07-16"))   # the S-B era frame
THIN_N = 20                               # below this a cell is printed and labelled thin
POST_CROSS = ("T1", "T2")                 # tiers whose `ticks` IS a cross age


def _r(x, nd=2):
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return round(f, nd) if np.isfinite(f) else None


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #
def _cache_panel() -> pd.DataFrame:
    """The frozen basis: raw closes straight from the three breadth caches."""
    px = pd.concat([pd.read_parquet(f"data/{g}/_closes_cache.parquet") for g in GROUPS],
                   axis=1, sort=False)
    px = px.loc[:, ~px.columns.duplicated()].sort_index()
    px.index = pd.to_datetime(px.index)
    return px[px.index <= FRAME_ASOF]


def load_panel() -> pd.DataFrame:
    """Full-universe close panel, pinned at :data:`FRAME_ASOF`.

    ``PRICE_BASIS`` selects the adjustment basis and NOTHING else:

    ``cache`` (default)
        The frozen basis this packet shipped on — raw closes from the breadth caches.
        Byte-reproduces ``fresh_ticks_extension_replay_results.json``.

    ``adjusted``
        The same names on the same calendar, re-priced adjusted-first through
        ``price_ladder`` (baskets/ohlcv → yahoo → data_stocks → cache). The benchmark leg
        (``data/yahoo/SPY.parquet``) is already adjusted, so this is the run where both
        legs of every excess number share one basis.

    The universe, the session calendar AND the observed-cell mask are all held FIXED
    across the two bases, so a delta between the runs is attributable to the price basis
    and to nothing else. The mask is load-bearing, not defensive: the ``breadth``
    (large-cap) cache only starts 2025-03-18 while ``data/baskets/ohlcv`` carries the
    same names back to 2014, so an unmasked swap silently hands ~500 large caps two extra
    years of warm-up and grows the admitted population by ~31% — a COVERAGE change
    masquerading as a basis effect. Every cell that is NaN in the cache panel is forced
    NaN here (memory: ``comparing-across-measures-manufactures-results``).

    Names absent from every adjusted store fall through to the cache and are counted in
    :data:`PANEL_PROVENANCE`, never dropped.
    """
    base = _cache_panel()
    if PRICE_BASIS == "cache":
        PANEL_PROVENANCE.clear()
        PANEL_PROVENANCE.update({"basis": "cache", "ladder": ["closes_cache_UNADJUSTED"],
                                 "panel_names": int(base.shape[1]),
                                 "panel_sessions": int(base.shape[0])})
        return base

    px, prov = price_ladder.close_panel(list(base.columns), asof=FRAME_ASOF,
                                        start=base.index.min())
    px = px.reindex(index=base.index, columns=base.columns)   # fix calendar + universe
    px = px.where(base.notna())                               # fix the observed cells
    prov["basis"] = "adjusted"
    prov["held_fixed"] = ("universe, session calendar AND observed-cell mask taken from "
                          "the cache panel; only the price VALUES differ between runs")
    prov["cells_observed"] = int(base.notna().to_numpy().sum())
    prov["cells_masked_out"] = int((px.isna() & base.notna()).to_numpy().sum())
    PANEL_PROVENANCE.clear()
    PANEL_PROVENANCE.update(prov)
    return px


def load_spy(index: pd.DatetimeIndex) -> pd.Series:
    """SPY total-return close on the panel calendar — the benchmark grade_us_board uses."""
    s = pd.read_parquet("data/yahoo/SPY.parquet")["close"]
    s.index = pd.to_datetime(s.index)
    s = s[s.index <= FRAME_ASOF].sort_index()
    return s.reindex(index).ffill()


def load_sectors() -> dict[str, str]:
    u = pd.read_parquet("data/universe/membership.parquet").drop_duplicates("ticker")
    return dict(zip(u["ticker"], u["sector"]))


# --------------------------------------------------------------------------- #
# reproduction gate — S-B's by_cross_age table, rebuilt from the current stores
# --------------------------------------------------------------------------- #
def sb_frame() -> pd.DataFrame:
    """S-B's frame verbatim: retro_grades buy-lane H=10, excess_spy, date-demeaned."""
    df = pd.read_parquet("data/us_board_ledger/retro_grades.parquet")
    df = df[(df["lane"] == "buy") & (df["horizon"] == 10)].copy()
    df = df.dropna(subset=["excess_spy", "entry_date", "ticker"])
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["excess_pp"] = df["excess_spy"] * 100.0
    df["excess_dm"] = df["excess_pp"] - df.groupby("entry_date")["excess_pp"].transform("mean")
    df["loser"] = df["excess_pp"] < LOSER_PP
    return df


def reproduce_sb(px: pd.DataFrame) -> dict:
    """Rebuild S-B's ``by_cross_age_ticks`` and diff it against the frozen results JSON.

    S-B's construction, reproduced exactly (superintelligence_standins.py lines 111-161):
    per-episode tier looked up on ``entry_date`` from ``tier_stream`` on the un-truncated
    panel. NOTE the pin does not apply here — S-B ran on the full cache — but the frame ends
    2026-07-16, well inside FRAME_ASOF, and the check below proves the numbers still stand.
    """
    df = sb_frame()
    cache: dict[str, pd.DataFrame] = {}

    def tier_at(t, d):
        if t not in px.columns:
            return None, None
        if t not in cache:
            cache[t] = ct.tier_stream(px[t].dropna())
        st = cache[t]
        if st.empty or d not in st.index:
            return None, None
        row = st.loc[d]
        return row["tier"], (float(row["ticks"]) if pd.notna(row["ticks"]) else None)

    tiers, ticks = [], []
    for _, r in df.iterrows():
        a, b = tier_at(r["ticker"], r["entry_date"])
        tiers.append(a)
        ticks.append(b)
    df["adm_tier"], df["adm_ticks"] = tiers, ticks
    el = df.dropna(subset=["adm_tier"])

    rebuilt = []
    for a in (0.0, 1.0, 2.0):
        m = el[el["adm_ticks"] == a]
        rebuilt.append({"ticks": int(a), "n": int(len(m)),
                        "loser_rate_pct": _r(m["loser"].mean() * 100, 1),
                        "median_excess_pp": _r(m["excess_pp"].median()),
                        "median_excess_dm_pp": _r(m["excess_dm"].median())})

    frozen = json.load(open(SB_FROZEN))["S_B_confirmation"]["by_cross_age_ticks"]
    diffs = []
    for got, want in zip(rebuilt, frozen):
        for k in ("n", "loser_rate_pct", "median_excess_pp", "median_excess_dm_pp"):
            if got.get(k) != want.get(k):
                diffs.append({"ticks": got["ticks"], "field": k,
                              "rebuilt": got.get(k), "frozen": want.get(k)})
    return {
        "status": "PASS — exact" if not diffs else "FAIL — stores drifted",
        "rebuilt": rebuilt, "frozen": frozen, "cell_diffs": diffs,
        "frame": {"rows": int(len(df)), "names": int(df["ticker"].nunique()),
                  "dates": [str(df["entry_date"].min().date()),
                            str(df["entry_date"].max().date())],
                  "base_loser_rate_pct": _r(df["loser"].mean() * 100, 1),
                  "base_median_excess_pp": _r(df["excess_pp"].median())},
        "note": ("If this ever FAILs, the frame must be re-pinned at a REPRO_ASOF and every "
                 "number below re-read against the new anchor — the CN replay law."),
    }


# --------------------------------------------------------------------------- #
# leg reconstruction — confluence_tiers' OWN helpers, never a hand-rolled indicator
# --------------------------------------------------------------------------- #
def leg_streams(c: pd.Series) -> pd.DataFrame | None:
    """Per-day admission/veto leg booleans + BOTH tick clocks, for every day of ``c``.

    ``tier_stream`` reports ``ticks`` only on days it admits, so a day BLOCKED at tick 3 has
    no tick age in its output and the leg-mix question ("what kills the excluded cohort?")
    cannot be asked of it. This function replicates the leg composition of
    ``confluence_tiers.tier_stream`` lines 377-434 using that module's OWN functions
    (``_tf_bars``, ``_rsi_macd``, ``_stoch_rsi_kd``, ``_xup``, ``_since``, ``_to_daily``,
    ``_last_true_pos``, ``_ticks_since_vec``, ``technicals.rsi``) — only the composition is
    replicated, never an indicator. :func:`fidelity_check` then asserts, per name, that these
    legs reproduce ``tier_stream``'s own ``not_topped`` column on every day and its ``ticks``
    column on every day it admits. Returns None on a series tier_stream would refuse.
    """
    c = c.dropna()
    if not isinstance(c.index, pd.DatetimeIndex):
        c = c.copy()
        c.index = pd.to_datetime(c.index)
    if len(c) < ct.MIN_HISTORY:
        return None
    di = c.index

    # 2D grid (tier_stream lines 377-383)
    sm, smk = _tf_bars(c, 2)
    m2, s2 = _rsi_macd(sm)
    h2 = m2 - s2
    mb2 = _xup(m2, s2)
    slope2 = h2 - h2.shift(1)
    btc = (-h2 / slope2)
    imm2 = ((h2 < 0) & (slope2 > 0) & (btc > 0) & (btc <= ct.EARLY_CROSS_BARS)).fillna(False)

    # 3D grid (lines 385-396)
    ss3, sk3 = _tf_bars(c, 3)
    k3, d3 = _stoch_rsi_kd(ss3)
    sb3 = _xup(k3, d3)
    recent3 = _since(sb3) <= CONF_W
    fromos3 = d3.rolling(CONF_W).min() < ct.OS
    r14_3 = rsi(ss3, RSI_LEN)
    m3, s3 = _rsi_macd(ss3)
    mb3 = _xup(m3, s3)
    k2, d2 = _stoch_rsi_kd(sm)
    sb2 = _xup(k2, d2)
    recent2 = _since(sb2) <= CONF_W
    fromos2 = d2.rolling(CONF_W).min() < ct.OS

    wk = c.resample("W-FRI").last().dropna()
    wm, ws = _rsi_macd(wk)
    wbull = (wm >= ws).shift(1)
    ma200 = c.rolling(200).mean()

    def td(s, kn, how="ffill"):
        return _to_daily(s, kn, di, how)

    mb2_d = td(mb2.fillna(False), smk, "event")
    imm2_d = td(imm2.fillna(False), smk).fillna(False)
    m2_d, s2_d = td(m2, smk), td(s2, smk)
    mb3_d = td(mb3.fillna(False), sk3, "event")
    m3_d, s3_d = td(m3, sk3), td(s3, sk3)
    recent3_d = td(recent3.fillna(False), sk3).fillna(False)
    fromos3_d = td(fromos3.fillna(False), sk3).fillna(False)
    k3_d, d3_d = td(k3, sk3), td(d3, sk3)
    r14_d = td(r14_3, sk3)
    recent2_d = td(recent2.fillna(False), smk).fillna(False)
    fromos2_d = td(fromos2.fillna(False), smk).fillna(False)
    wbull_d = wbull.reindex(di, method="ffill").fillna(False).astype(bool)
    above200 = (c > ma200).fillna(False)

    # veto legs — tier_stream lines 424-429. Comparisons against NaN are False on both sides,
    # matching the engine's numpy path exactly (a NaN warmup day reads constructive).
    k3n, d3n = k3_d.to_numpy(), d3_d.to_numpy()
    m3n, s3n = m3_d.to_numpy(), s3_d.to_numpy()
    stoch_ob = (k3n >= OB) | (d3n >= OB)
    stoch_bear = k3n < d3n
    macd_bear = m3n < s3n
    not_topped = ~(stoch_ob | stoch_bear | macd_bear)

    # tick clocks — lines 431-438. Both are FRESH_TICKS-independent (the knob only enters the
    # `<= ft` comparisons downstream), so one pass serves every setting.
    t1_ticks = _ticks_since_vec(sk3, _last_true_pos(mb3_d.fillna(False).to_numpy().astype(bool)),
                                di, EXT_TICKS)
    t2_buy = (mb2_d & recent3_d & (wbull_d | fromos3_d)
              & (r14_d < BUY_RSI_MAX).fillna(False)).fillna(False).to_numpy().astype(bool)
    t2_ticks = _ticks_since_vec(smk, _last_true_pos(t2_buy), di, EXT_TICKS)

    return pd.DataFrame({
        "stoch_ob": stoch_ob, "stoch_bear": stoch_bear, "macd_bear": macd_bear,
        "not_topped": not_topped,
        "rsi_ok": (r14_d < BUY_RSI_MAX).fillna(False).to_numpy(),
        "long_bias": ((m2_d >= s2_d) & (k3_d >= d3_d)).fillna(False).to_numpy(),
        "recent3": recent3_d.to_numpy(), "confirm3": (wbull_d | fromos3_d).to_numpy(),
        "recent2": recent2_d.to_numpy(), "confirm2": (wbull_d | fromos2_d).to_numpy(),
        "above200": above200.to_numpy(), "imm2": imm2_d.to_numpy(),
        "t1_ticks": t1_ticks, "t2_ticks": t2_ticks,
    }, index=di)


def fidelity_check(legs: pd.DataFrame, gate: pd.DataFrame, ext: pd.DataFrame) -> dict:
    """Equality spot-check of the reconstruction against tier_stream's own output.

    Three assertions, on the FULL overlapping range of every name:
      1. reconstructed ``not_topped`` == tier_stream's ``not_topped`` (every day, both ft)
      2. on days tier_stream admits T1, reconstructed ``t1_ticks`` == its ``ticks``
      3. on days tier_stream admits T2, reconstructed ``t2_ticks`` == its ``ticks``
    """
    idx = legs.index.intersection(gate.index)
    out = {"days": int(len(idx)), "not_topped_mismatch": 0,
           "t1_ticks_mismatch": 0, "t2_ticks_mismatch": 0}
    if not len(idx):
        return out
    L, G, E = legs.loc[idx], gate.loc[idx], ext.loc[idx]
    out["not_topped_mismatch"] = int(
        (L["not_topped"].to_numpy() != G["not_topped"].to_numpy()).sum()
        + (L["not_topped"].to_numpy() != E["not_topped"].to_numpy()).sum())
    for stream in (G, E):
        for tier, col in (("T1", "t1_ticks"), ("T2", "t2_ticks")):
            m = (stream["tier"] == tier) & stream["ticks"].notna()
            if m.any():
                bad = int((L.loc[m, col].to_numpy() != stream.loc[m, "ticks"].to_numpy()).sum())
                out[f"{col}_mismatch"] += bad
    return out


# --------------------------------------------------------------------------- #
# the counterfactual-eligibility helper (unit-tested)
# --------------------------------------------------------------------------- #
def classify_states(gate: pd.DataFrame, ext: pd.DataFrame, legs: pd.DataFrame | None = None,
                    *, gate_ticks: int = GATE_TICKS, ext_ticks: int = EXT_TICKS) -> pd.DataFrame:
    """Classify every session of one name against the FRESH_TICKS counterfactual.

    ``gate`` = tier_stream at the shipped FRESH_TICKS; ``ext`` = the same stream with ONLY the
    freshness clock extended. Tick level and tier are read from ``ext`` (the extended stream is
    a superset: for ticks <= gate_ticks the two streams agree by construction, asserted in-run
    as ``admitted_not_on_board``). ``on_board_now`` is read from ``gate`` — the flag for "this
    session is already on the board tonight".

    cohort values, post-cross tiers only (T1/T2 — the only tiers whose ``ticks`` IS a cross age;
    T3/T4 are pre-cross projections and are labelled ``projection`` and excluded from the
    tick comparison, a disclosed exclusion, never a silent one):
      admitted        ticks 0..gate_ticks — what the board admits today
      ext_marginal    ticks in (gate_ticks, 4] and NOT on the board today — the W5.2 cohort:
                      names the gate extension would ADD
      ext_relabel     same tick range but already on the board tonight via another tier — the
                      extension would not add these, it would only re-tier (and re-weight) them
      decay_marginal  ticks 5..ext_ticks, not on the board — context beyond the question
      decay_relabel   ticks 5..ext_ticks, already on the board
      blocked         the cross is <= ext_ticks old but no tier admits the day (a veto fired);
                      ``block_leg`` names the first failing leg when ``legs`` is supplied

    ``episode`` groups the sessions of ONE cross: a new episode starts when the tier changes or
    the tick age DECREASES (a fresh cross resets the clock), so tick 0 and tick 4 of the same
    cross carry the same id — which is what the paired within-cross block needs.
    """
    idx = gate.index.intersection(ext.index)
    g, e = gate.loc[idx], ext.loc[idx]
    tier = e["tier"].where(e["eligible"].astype(bool))
    ticks = e["ticks"].where(e["eligible"].astype(bool))
    on_board = g["eligible"].astype(bool)

    post = tier.isin(POST_CROSS)
    cohort = pd.Series(None, index=idx, dtype=object)
    cohort[e["eligible"].astype(bool) & ~post] = "projection"
    lo, hi = gate_ticks + 1, 4
    admitted = post & (ticks <= gate_ticks)
    in_ext = post & (ticks >= lo) & (ticks <= hi)
    in_decay = post & (ticks > hi) & (ticks <= ext_ticks)
    cohort[admitted] = "admitted"
    cohort[in_ext & ~on_board] = "ext_marginal"
    cohort[in_ext & on_board] = "ext_relabel"
    cohort[in_decay & ~on_board] = "decay_marginal"
    cohort[in_decay & on_board] = "decay_relabel"

    out = pd.DataFrame({"tier": tier, "ticks": ticks, "on_board_now": on_board,
                        "cohort": cohort}, index=idx)

    if legs is not None:
        li = legs.reindex(idx)
        # OPERATIVE cross clock, in the engine's own tier precedence: T1 is tested first
        # (tier_stream lines 474-478), so the operative age is the 3D master's whenever that
        # clock is inside the extended window, and the 2D T2 clock only otherwise. (Taking a
        # min instead would mis-file a day whose T1 cross is 3 ticks old under a fresh T2.)
        t1c, t2c = li["t1_ticks"].to_numpy(), li["t2_ticks"].to_numpy()
        clock = np.where(t1c <= ext_ticks, t1c, t2c)
        live = (clock <= ext_ticks) & ~e["eligible"].to_numpy().astype(bool)
        out.loc[live, "cohort"] = "blocked"
        out["clock_ticks"] = np.where(clock <= ext_ticks, clock, np.nan)
        out["clock_tier"] = np.where(t1c <= ext_ticks, "T1", "T2")
        out["t1_ticks"] = t1c
        # first failing leg, in the engine's own evaluation order (the not-topped veto is
        # checked before any tier — tier_stream lines 429/472-473).
        blk = pd.Series(None, index=idx, dtype=object)
        for leg in ("stoch_ob", "stoch_bear", "macd_bear"):
            hit = li[leg].fillna(False).to_numpy().astype(bool) & blk.isna().to_numpy()
            blk[hit] = leg
        rest = blk.isna().to_numpy()
        for leg, col in (("rsi_cap", "rsi_ok"), ("long_bias", "long_bias"),
                         ("stoch_recent", "recent3"), ("confirm", "confirm3")):
            hit = ~li[col].fillna(False).to_numpy().astype(bool) & rest & blk.isna().to_numpy()
            blk[hit] = leg
        out["block_leg"] = blk.where(out["cohort"] == "blocked")

    # episode id: new episode on a tier change or a tick reset
    ep = pd.Series(np.nan, index=idx)
    live_rows = out["tier"].notna()
    if live_rows.any():
        sub = out.loc[live_rows]
        new = (sub["tier"] != sub["tier"].shift(1)) | (sub["ticks"] < sub["ticks"].shift(1))
        new.iloc[0] = True
        ep.loc[live_rows] = new.cumsum().to_numpy()
    out["episode"] = ep
    return out


# --------------------------------------------------------------------------- #
# outcome tables
# --------------------------------------------------------------------------- #
def cell(m: pd.DataFrame, dm_col: str = "excess_dm_pp") -> dict:
    """One cohort cell. Raw beside demeaned, per-name-first beside pooled, n always printed."""
    if not len(m):
        return {"n": 0, "thin": True}
    byname = m.groupby("ticker")["excess_spy_pp"].median()
    out = {
        "n": int(len(m)), "names": int(byname.shape[0]),
        "dates": int(m["date"].nunique()),
        "loser_rate_pct": _r(m["loser"].mean() * 100, 1),
        "median_excess_pp": _r(m["excess_spy_pp"].median()),
        "median_excess_dm_pp": _r(m[dm_col].median()),
        "median_excess_vs_univ_pp": _r(m["excess_med_pp"].median()),
        "per_name_median_pp": _r(byname.median()),
        "mean_excess_pp": _r(m["excess_spy_pp"].mean()),
        "win_pct": _r((m["excess_spy_pp"] > 0).mean() * 100, 1),
    }
    if f"excess_spy_pp_h{H_SUPPORT}" in m.columns:
        out[f"median_excess_pp_h{H_SUPPORT}"] = _r(m[f"excess_spy_pp_h{H_SUPPORT}"].median())
        out[f"loser_rate_pct_h{H_SUPPORT}"] = _r(
            (m[f"excess_spy_pp_h{H_SUPPORT}"] < LOSER_PP).mean() * 100, 1)
    if len(m) < THIN_N:
        out["thin"] = True
        out["thin_note"] = f"n < {THIN_N} — read as a count, not a rate"
    return out


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """Wilson interval on a rate. Reported WITH the caveat that sessions inside one tick
    bucket are the same cross on consecutive days, so this interval overstates independence;
    the date-blocked bootstrap beside it is the honest one."""
    if not n:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [_r(100 * (c - h), 1), _r(100 * (c + h), 1)]


def date_block_bootstrap(a: pd.DataFrame, b: pd.DataFrame, draws: int = 1000,
                         seed: int = 20260804) -> dict:
    """Date-blocked bootstrap of the A-minus-B delta: resample DATES with replacement and
    recompute on the drawn days. One session is one bet, not N — resampling rows would treat
    the same cross on consecutive days as independent evidence and shrink the interval by a
    factor the data does not earn."""
    if not len(a) or not len(b):
        return {"thin": True}
    rng = np.random.default_rng(seed)
    dates = np.array(sorted(set(a["date"]) | set(b["date"])))
    ga = {d: g for d, g in a.groupby("date")}
    gb = {d: g for d, g in b.groupby("date")}
    dm, lo = [], []
    for _ in range(draws):
        pick = rng.choice(dates, size=len(dates), replace=True)
        sa = pd.concat([ga[d] for d in pick if d in ga], ignore_index=True)
        sb = pd.concat([gb[d] for d in pick if d in gb], ignore_index=True)
        if not len(sa) or not len(sb):
            continue
        dm.append(sa["excess_dm_pp"].median() - sb["excess_dm_pp"].median())
        lo.append(sa["loser"].mean() * 100 - sb["loser"].mean() * 100)
    if not dm:
        return {"thin": True}
    return {
        "draws": len(dm), "blocks": int(len(dates)),
        "delta_median_dm_pp_ci95": [_r(np.percentile(dm, 2.5)), _r(np.percentile(dm, 97.5))],
        "delta_loser_pp_ci95": [_r(np.percentile(lo, 2.5), 1), _r(np.percentile(lo, 97.5), 1)],
        "pct_draws_delta_dm_positive": _r(float(np.mean(np.array(dm) > 0)) * 100, 1),
        "straddles_zero": bool(np.percentile(dm, 2.5) < 0 < np.percentile(dm, 97.5)),
    }


def half_split(rows: pd.DataFrame, a_mask: pd.Series, b_mask: pd.Series, label: str) -> dict:
    """Robustness: the A-minus-B delta re-measured on each calendar half of the window."""
    mid = rows["date"].median()
    out = {"label": label, "split_date": str(pd.Timestamp(mid).date())}
    for half, m in (("first_half", rows[rows["date"] <= mid]),
                    ("second_half", rows[rows["date"] > mid])):
        a = rows.loc[a_mask & rows.index.isin(m.index)]
        b = rows.loc[b_mask & rows.index.isin(m.index)]
        if len(a) < 10 or len(b) < 10:
            out[half] = {"n_a": int(len(a)), "n_b": int(len(b)),
                         "thin": True, "note": "thin — no delta read"}
            continue
        out[half] = {
            "n_a": int(len(a)), "n_b": int(len(b)),
            "delta_median_dm_pp": _r(a["excess_dm_pp"].median() - b["excess_dm_pp"].median()),
            "delta_loser_pp": _r(a["loser"].mean() * 100 - b["loser"].mean() * 100, 1),
        }
    return out


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> None:
    warnings.filterwarnings("ignore")   # CLI-only: never at import time (repo guard)
    res: dict = {
        "instrument": "W5.2 FRESH_TICKS-extension frozen-frame replay",
        "frame_asof_pin": str(FRAME_ASOF.date()),
        "gate_ticks_from_engine": GATE_TICKS,
        "ext_ticks": EXT_TICKS,
        "loser_def": f"excess vs SPY < {LOSER_PP}pp at H={H_PRIMARY}",
        "fill_convention": ("next-bar (entry = close of the session after the state bar), "
                            "matching engine.grading.forward_metrics"),
    }
    px = load_panel()
    res["price_basis"] = PRICE_BASIS
    res["panel_provenance"] = dict(PANEL_PROVENANCE)
    print(f"[1/6] panel {px.shape[1]} names x {px.shape[0]} sessions, pinned at "
          f"{FRAME_ASOF.date()} (basis={PRICE_BASIS}, "
          f"{PANEL_PROVENANCE.get('names_on_unadjusted_basis', 0)} names still unadjusted)",
          flush=True)

    # ---- reproduction gate (runs BEFORE anything new is printed) ----
    res["reproduction_gate"] = reproduce_sb(px)
    print(f"[2/6] S-B reproduction gate: {res['reproduction_gate']['status']}", flush=True)

    di = px.index
    n = len(di)
    spy = load_spy(di)
    sectors = load_sectors()

    # forward returns, next-bar fill, for BOTH horizons on an identical row set
    fwd: dict[int, pd.DataFrame] = {}
    bench: dict[int, pd.Series] = {}
    univ_med: dict[int, pd.Series] = {}
    for h in (H_PRIMARY, H_SUPPORT):
        entry = px.shift(-1)
        exitp = px.shift(-(1 + h))
        fwd[h] = (exitp / entry - 1.0) * 100.0
        be, bx = spy.shift(-1), spy.shift(-(1 + h))
        bench[h] = (bx / be - 1.0) * 100.0
        univ_med[h] = fwd[h].median(axis=1)
    # evaluation window: every row carries FULL H_SUPPORT coverage, so H=10 and H=21 grade an
    # identical row set and no denominator is conditioned on resolution.
    last_eval = n - (2 + H_SUPPORT)
    eval_dates = di[:last_eval + 1]
    res["eval_window"] = {"start": str(eval_dates.min().date()),
                          "end": str(eval_dates.max().date()),
                          "sessions": int(len(eval_dates)),
                          "note": ("cut so every row has full H=21 forward coverage inside the "
                                   "pin — H=10 and H=21 grade the SAME rows")}

    # ---- per-name streams + classification ----
    rows: list[dict] = []
    leg_fire = {k: 0 for k in ("stoch_ob", "stoch_bear", "macd_bear", "rsi_ok", "long_bias",
                               "recent3", "confirm3", "recent2", "confirm2", "above200", "imm2")}
    leg_days = 0
    fid = {"names": 0, "days": 0, "not_topped_mismatch": 0,
           "t1_ticks_mismatch": 0, "t2_ticks_mismatch": 0}
    block_mix: dict[str, dict[str, int]] = {}
    admitted_not_on_board = 0
    tickers = [t for t in px.columns if px[t].notna().sum() >= ct.MIN_HISTORY]
    for i, t in enumerate(tickers):
        if i % 250 == 0:
            print(f"[3/6] streams {i}/{len(tickers)}", flush=True)
        s = px[t].dropna()
        gate = ct.tier_stream(s, fresh_ticks=GATE_TICKS)
        ext = ct.tier_stream(s, fresh_ticks=EXT_TICKS)
        if gate.empty or ext.empty:
            continue
        legs = leg_streams(s)
        if legs is not None:
            f = fidelity_check(legs, gate, ext)
            fid["names"] += 1
            for k in ("days", "not_topped_mismatch", "t1_ticks_mismatch", "t2_ticks_mismatch"):
                fid[k] += f[k]
            leg_days += len(legs)
            for k in leg_fire:
                leg_fire[k] += int(legs[k].fillna(False).astype(bool).sum())
        cls = classify_states(gate, ext, legs)
        cls = cls[cls.index.isin(eval_dates)]
        admitted_not_on_board += int(((cls["cohort"] == "admitted")
                                      & ~cls["on_board_now"]).sum())
        blk = cls[(cls["cohort"] == "blocked") & (cls["clock_tier"] == "T1")]
        if len(blk):
            for tick_v, sub in blk.groupby(blk["clock_ticks"]):
                if not np.isfinite(tick_v):
                    continue
                key = str(int(tick_v))
                d = block_mix.setdefault(key, {})
                for leg, cnt in sub["block_leg"].value_counts().items():
                    d[str(leg)] = d.get(str(leg), 0) + int(cnt)
                d["_total"] = d.get("_total", 0) + int(len(sub))
        keep = cls[cls["cohort"].isin(["admitted", "ext_marginal", "ext_relabel",
                                       "decay_marginal", "decay_relabel", "projection"])]
        for d, r in keep.iterrows():
            e10 = fwd[H_PRIMARY].at[d, t]
            if not np.isfinite(e10):
                continue
            e21 = fwd[H_SUPPORT].at[d, t]
            rows.append({
                "ticker": t, "date": d, "tier": r["tier"],
                "ticks": (float(r["ticks"]) if pd.notna(r["ticks"]) else np.nan),
                "cohort": r["cohort"], "on_board_now": bool(r["on_board_now"]),
                "episode": f"{t}#{r['episode']:.0f}" if pd.notna(r["episode"]) else None,
                "sector": sectors.get(t),
                "excess_spy_pp": float(e10 - bench[H_PRIMARY].at[d]),
                "excess_med_pp": float(e10 - univ_med[H_PRIMARY].at[d]),
                f"excess_spy_pp_h{H_SUPPORT}": (float(e21 - bench[H_SUPPORT].at[d])
                                                if np.isfinite(e21) else np.nan),
            })

    ev = pd.DataFrame(rows)
    print(f"[4/6] {len(ev)} classified sessions over {ev['ticker'].nunique()} names",
          flush=True)
    ev["loser"] = ev["excess_spy_pp"] < LOSER_PP
    # date-demeaned within the union of states the board could SEE that day — the analogue of
    # S-B's within-admission-date demeaning on a full-universe basis.
    ev["excess_dm_pp"] = ev["excess_spy_pp"] - ev.groupby("date")["excess_spy_pp"].transform("mean")

    res["construction_checks"] = {
        "admitted_states_not_on_board_today": admitted_not_on_board,
        "admitted_check_note": ("MUST be 0: for ticks <= FRESH_TICKS the extended stream and "
                                "the shipped gate agree by construction; a non-zero here would "
                                "mean the counterfactual moved something other than the clock"),
        "reconstruction_fidelity": fid,
        "fidelity_note": ("mismatches MUST be 0 — the reconstructed legs reproduce "
                          "tier_stream's own not_topped on every day and its ticks on every "
                          "admitted day, for every name"),
        "leg_fire_counts": {k: {"days": v, "pct": _r(100.0 * v / max(1, leg_days), 1)}
                            for k, v in leg_fire.items()},
        "leg_fire_note": ("a leg at 0 days is a DEAD leg (the numpy `x is True` trap) — these "
                          "counts exist so a dead leg is visible in the output, not merely wrong"),
        "leg_days_total": leg_days,
    }

    # ---- primary unit: one row per (episode, tick level) = first eligible session there ----
    epi = ev[ev["episode"].notna() & ev["tier"].isin(POST_CROSS)].copy()
    epi = epi.sort_values("date").groupby(["episode", "ticks"], as_index=False).first()
    print(f"[5/6] {len(epi)} episode-tick rows ({epi['episode'].nunique()} crosses)", flush=True)

    def tick_table(frame: pd.DataFrame, cohorts: list[str] | None = None) -> list[dict]:
        out = []
        for tk in range(0, EXT_TICKS + 1):
            m = frame[frame["ticks"] == tk]
            if cohorts is not None:
                m = m[m["cohort"].isin(cohorts)]
            c = cell(m)
            c["ticks"] = tk
            c["gate_status"] = ("admitted today" if tk <= GATE_TICKS else
                                "EXCLUDED — the W5.2 question" if tk <= 4 else
                                "EXCLUDED — decay context only")
            out.append(c)
        return out

    res["A_primary_by_tick_episode_unit"] = {
        "unit": "one row per cross episode per tick level (first eligible session at that age)",
        "all_states": tick_table(epi),
        "marginal_only": tick_table(epi, ["admitted", "ext_marginal", "decay_marginal"]),
        "marginal_note": ("marginal_only drops the ext_relabel rows — sessions already on the "
                          "board tonight via a projection tier. Those are what the extension "
                          "would RE-TIER (T3 weight 0.6 -> T1 0.9), not what it would ADD."),
    }
    res["B_supporting_by_tick_all_sessions"] = {
        "unit": "every eligible session (overlapping inside a tick bucket — not independent)",
        "all_states": tick_table(ev),
    }

    # ---- the headline contrast: ticks 3/4 vs ticks 0-2 ----
    def contrast(frame: pd.DataFrame, label: str) -> dict:
        base = frame[(frame["ticks"] <= GATE_TICKS) & (frame["cohort"] == "admitted")]
        ext_m = frame[(frame["ticks"] >= GATE_TICKS + 1) & (frame["ticks"] <= 4)
                      & (frame["cohort"] == "ext_marginal")]
        ext_all = frame[(frame["ticks"] >= GATE_TICKS + 1) & (frame["ticks"] <= 4)]
        decay = frame[(frame["ticks"] > 4) & (frame["ticks"] <= EXT_TICKS)]
        out = {
            "label": label,
            "admitted_ticks_0_2": cell(base),
            "ext_ticks_3_4_marginal": cell(ext_m),
            "ext_ticks_3_4_all": cell(ext_all),
            "decay_ticks_5_6_context": cell(decay),
            "tick_3_alone": cell(frame[(frame["ticks"] == 3) & (frame["cohort"] == "ext_marginal")]),
            "tick_4_alone": cell(frame[(frame["ticks"] == 4) & (frame["cohort"] == "ext_marginal")]),
        }
        if len(base) and len(ext_m):
            out["delta_ext_minus_admitted"] = {
                "median_dm_pp": _r(ext_m["excess_dm_pp"].median() - base["excess_dm_pp"].median()),
                "median_raw_pp": _r(ext_m["excess_spy_pp"].median() - base["excess_spy_pp"].median()),
                "loser_rate_pp": _r(ext_m["loser"].mean() * 100 - base["loser"].mean() * 100, 1),
                "per_name_median_pp": _r(
                    ext_m.groupby("ticker")["excess_spy_pp"].median().median()
                    - base.groupby("ticker")["excess_spy_pp"].median().median()),
                f"median_h{H_SUPPORT}_pp": _r(
                    ext_m[f"excess_spy_pp_h{H_SUPPORT}"].median()
                    - base[f"excess_spy_pp_h{H_SUPPORT}"].median()),
            }
        return out

    epi_base = epi[(epi["ticks"] <= GATE_TICKS) & (epi["cohort"] == "admitted")]
    epi_ext = epi[(epi["ticks"] >= GATE_TICKS + 1) & (epi["ticks"] <= 4)
                  & (epi["cohort"] == "ext_marginal")]
    res["C_headline_contrast"] = {
        "episode_unit_primary": contrast(epi, "episode-tick unit (primary)"),
        "all_sessions_supporting": contrast(ev, "all eligible sessions (supporting)"),
        "intervals": {
            "loser_rate_wilson95_admitted_0_2": wilson(int(epi_base["loser"].sum()),
                                                       int(len(epi_base))),
            "loser_rate_wilson95_ext_3_4": wilson(int(epi_ext["loser"].sum()),
                                                  int(len(epi_ext))),
            "date_blocked_bootstrap_ext_minus_admitted":
                date_block_bootstrap(epi_ext, epi_base),
            "note": ("Wilson assumes independent rows and therefore reads TIGHTER than the "
                     "data earns (one cross contributes several sessions); the date-blocked "
                     "bootstrap resamples trading days and is the honest interval."),
        },
    }
    res["C_half_split_robustness"] = half_split(
        epi,
        (epi["ticks"] >= GATE_TICKS + 1) & (epi["ticks"] <= 4) & (epi["cohort"] == "ext_marginal"),
        (epi["ticks"] <= GATE_TICKS) & (epi["cohort"] == "admitted"),
        "ticks-3/4 marginal MINUS ticks-0/2 admitted, episode unit")

    # ---- paired within-cross: same cross, entered at tick 0 vs at tick 3/4 ----
    piv = epi.pivot_table(index="episode", columns="ticks", values="excess_spy_pp",
                          aggfunc="first")
    paired = {}
    for late in (3, 4):
        if 0 in piv.columns and late in piv.columns:
            p = piv[[0, late]].dropna()
            paired[f"tick0_vs_tick{late}"] = {
                "n_crosses": int(len(p)),
                "median_tick0_pp": _r(p[0].median()),
                f"median_tick{late}_pp": _r(p[late].median()),
                "median_paired_delta_pp": _r((p[late] - p[0]).median()),
                "pct_late_better": _r((p[late] > p[0]).mean() * 100, 1),
                "thin": bool(len(p) < THIN_N),
            }
    res["D_paired_within_cross"] = {
        "question": ("does WAITING pay on the same cross (mechanism), or are the crosses that "
                     "survive to tick 3-4 simply better crosses (selection)? The marginal-"
                     "admission contrast above is the DECISION; this block is the mechanism."),
        "pairs": paired,
    }

    # ---- veto-leg mix: what kills the excluded cohort at ticks 3-4 ----
    res["E_veto_leg_mix_at_excluded_ticks"] = {
        "question": ("of the sessions whose 3D-master cross clock reads 0-6 ticks, how many are "
                     "blocked, and by WHICH leg? This is what the prereg's tripwire has to "
                     "watch: the leg that carries the exclusion is the leg that would carry "
                     "the risk if the freshness window widened."),
        "scope": ("T1-clock sessions only. On the T1 path the tick window and the not-topped "
                  "veto are the ONLY gates (tier_stream line 451: t1_fresh = a cross exists AND "
                  "its age <= ft), so a blocked T1-clock session is by construction a veto "
                  "story — which is exactly the tripwire's subject."),
        "by_tick": {k: v for k, v in sorted(block_mix.items(), key=lambda kv: int(kv[0]))},
        "attribution": ("first failing leg in the engine's own evaluation order (the not-topped "
                        "veto is checked before any tier); `_total` = all blocked sessions at "
                        "that clock reading"),
    }

    # ---- volume: what saying yes actually puts on the board ----
    n_sessions = int(ev["date"].nunique())
    vol = {}
    for label, mask in (("admitted_ticks_0_2", (epi["ticks"] <= GATE_TICKS)
                         & (epi["cohort"] == "admitted")),
                        ("added_ticks_3_4", (epi["ticks"] >= GATE_TICKS + 1)
                         & (epi["ticks"] <= 4) & (epi["cohort"] == "ext_marginal")),
                        ("added_ticks_5_6", (epi["ticks"] > 4)
                         & (epi["cohort"] == "decay_marginal"))):
        m = epi[mask]
        vol[label] = {"episode_tick_rows": int(len(m)),
                      "distinct_crosses": int(m["episode"].nunique()),
                      "per_session_mean": _r(len(m) / max(1, n_sessions))}
    allses = ev[ev["tier"].isin(POST_CROSS)]
    vol["board_size_effect_all_sessions"] = {
        "eligible_now_per_session": _r(
            len(allses[allses["cohort"] == "admitted"]) / max(1, n_sessions), 1),
        "added_per_session_ticks_3_4": _r(
            len(allses[allses["cohort"] == "ext_marginal"]) / max(1, n_sessions), 1),
        "pct_widening": _r(
            100.0 * len(allses[allses["cohort"] == "ext_marginal"])
            / max(1, len(allses[allses["cohort"] == "admitted"])), 1),
    }
    vol["retier_only"] = {
        "ext_relabel_rows": int((epi["cohort"] == "ext_relabel").sum()),
        "note": ("sessions already on the board via a projection tier whose T1/T2 clock reads "
                 "3-4: the extension would not ADD them, it would re-tier them (T3 weight 0.6 "
                 "-> T1 0.9) and move them up the ordering — a real secondary effect"),
    }
    res["H_volume_what_yes_buys"] = vol

    # ---- sector concentration of the ticks-3/4 cohort ----
    ext_rows = epi[(epi["ticks"] >= GATE_TICKS + 1) & (epi["ticks"] <= 4)
                   & (epi["cohort"] == "ext_marginal")]
    base_rows = epi[(epi["ticks"] <= GATE_TICKS) & (epi["cohort"] == "admitted")]
    sec = ext_rows["sector"].value_counts(normalize=True) * 100
    sec_b = base_rows["sector"].value_counts(normalize=True) * 100
    res["F_sector_concentration"] = {
        "ticks_3_4_pct": {str(k): _r(v, 1) for k, v in sec.head(8).items()},
        "ticks_0_2_pct": {str(k): _r(v, 1) for k, v in sec_b.head(8).items()},
        "top_sector_share_pct": _r(sec.iloc[0], 1) if len(sec) else None,
        "verdict": ("CONCENTRATED — read the delta as partly a sector call"
                    if len(sec) and sec.iloc[0] >= 35 else
                    "no single sector dominates the ticks-3/4 cohort"),
    }

    # ---- board-selection delta: synthetic ticks 0/1/2 vs S-B's measured admissions ----
    sb_tab = res["reproduction_gate"]["rebuilt"]
    win = epi[(epi["date"] >= SB_WINDOW[0]) & (epi["date"] <= SB_WINDOW[1])
              & (epi["cohort"] == "admitted")]
    synth = []
    for tk in (0, 1, 2):
        c = cell(win[win["ticks"] == tk])
        c["ticks"] = tk
        synth.append(c)
    deltas = []
    for s, b in zip(synth, sb_tab):
        deltas.append({
            "ticks": s["ticks"], "n_synthetic": s.get("n"), "n_sb_admissions": b.get("n"),
            "loser_rate_synthetic_pct": s.get("loser_rate_pct"),
            "loser_rate_sb_pct": b.get("loser_rate_pct"),
            "loser_delta_pp": (_r(s["loser_rate_pct"] - b["loser_rate_pct"], 1)
                               if s.get("loser_rate_pct") is not None
                               and b.get("loser_rate_pct") is not None else None),
            "median_dm_synthetic_pp": s.get("median_excess_dm_pp"),
            "median_dm_sb_pp": b.get("median_excess_dm_pp"),
        })
    res["G_board_selection_delta"] = {
        "window": [str(SB_WINDOW[0].date()), str(SB_WINDOW[1].date())],
        "synthetic_same_window": synth,
        "sb_measured_admissions": sb_tab,
        "per_tick_delta": deltas,
        "reading": ("this delta IS the board-selection effect — S-B measured names the board "
                    "ACTUALLY admitted (ranked, capped, human-shaped), this panel measures "
                    "every name that reached the state. It also bundles a fill-convention "
                    "difference: S-B reads tier ON the ledger's fill bar and grades from that "
                    "same bar, this instrument reads state on day d and fills at d+1. Both "
                    "sources of divergence are named; neither is netted out."),
    }

    res["caveats"] = [
        f"FROZEN REPLAY, PINNED AT {FRAME_ASOF.date()}. Every price series is truncated there "
        "before anything is computed. Re-running against a later snapshot is a DIFFERENT "
        "measurement and needs its own pin (the CN #4522 precedent).",
        "SYNTHETIC ELIGIBILITY, NOT ADMISSIONS. Cohorts are per-name PIT states from the "
        "production stream, not board rows: no ranking, no cap, no lane, no operator. The "
        "board-selection delta in block G measures how far that is from what S-B saw.",
        "SURVIVORSHIP IS THE COHORT, NOT A BUG. A ticks-3 state is a cross that survived three "
        "ticks un-topped. The conditioning is ex-ante observable on the firing evening (no "
        "lookahead), and block D separates 'waiting pays' from 'survivors were better'.",
        "ERA. The panel spans the pre- AND post-cascade-gate eras; S-B's frame is the "
        "pre-gate month only. Tier composition and admission behaviour differ across that "
        "boundary — the block-G comparison is era-matched, the rest is not.",
        "T3/T4 EXCLUDED FROM THE TICK COMPARISON. Their `ticks` is 0 by construction (a "
        "projection has no cross to age), so they are labelled `projection` and counted "
        "separately rather than pooled into the tick-0 cell.",
        "OVERLAP. Sessions inside one tick bucket are the same cross on consecutive days. The "
        "episode-tick unit is primary for that reason; the all-sessions table is supporting "
        "and its n is NOT an independent sample size.",
        "NO AUTHORITY. Exploratory; confers nothing, changes no gate, and is not a forward "
        "read. FRESH_TICKS is untouched by this PR.",
    ]

    with open(OUT, "w") as f:
        json.dump(res, f, indent=1, default=str)
    print(f"[6/6] wrote {OUT}", flush=True)
    print(json.dumps({k: res[k] for k in
                      ("reproduction_gate", "construction_checks", "C_headline_contrast")},
                     indent=1, default=str))


if __name__ == "__main__":
    main()
