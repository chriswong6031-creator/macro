"""Transmission CALIBRATION — the historical episode miner + regime-conditional hop
calibration (TXI W3). A DISPLAY-ONLY LEAF: it imports the node-evaluation grammar from
``engine.transmission_chains`` (never the scoring core) and nothing in the scoring path
imports it. It turns each chain hop from "untested" into a MEASURED conditional base rate.

WHAT IT DOES (masterplan §5 TXI-R4 "calibration is the product", TXI-R6 regime-conditional):
For each chain, for each hop ``from_node -> to_node``:
  1. Scan the FULL history of the collected source series (``lib.store``-backed) and build,
     for each node, its boolean ACTIVATION history — the exact node test evaluated at every
     bar, REUSING ``transmission_chains.series_test_timeseries`` (no duplicated threshold
     parser). State-adapter nodes (transmission/regime/forex latest.json — no stored
     history) bind to a DOCUMENTED series proxy (TXI-R6 sanctions deriving a coarse cell /
     detector from an observable); a node with no reconstructable proxy is ``untested`` with
     the reason — NEVER fabricated.
  2. Find every bar where ``from_node`` fired (an "activation"); for each, measure whether
     ``to_node`` fired within the hop's ``lag_d`` window → the empirical
     ``P(hop confirms | upstream fired)`` with n.
  3. Split every activation by the REGIME CELL it occurred in (TXI-R6). Regime source:
     ``data/regime/regime_history.parquet`` (a real daily quad/liquidity/inflation
     time-series back to 1927) — the ``condition`` field of the hop selects which coarse
     cell to split on (supply-vs-demand oil → global-growth-accelerating; QE/non-QE vol →
     Fed-liquidity direction; etc.). When a regime series genuinely is not available for a
     condition, the POOLED rate is computed and the hop is marked
     ``regime_split: unavailable`` with the reason — NEVER a fabricated split.
  4. A cohort event-study where cheap: after a chain fully expresses historically, the
     forward return of the downstream cohort proxy vs SPY — descriptive, with n.

Output ``data/transmission/chain_calibration.json`` (``transmission_calibration.v1``):
per chain -> per hop -> {p_confirm, n, lag_d, per_regime:{cell:{p,n}}, regime_split, asof,
method}. Nulls / thin cells (n < ``N_FLOOR``) print ``"untested"`` WITH the n, never a
fabricated rate — honest coverage is the whole point (this is permanent knowledge accrual).

DISCIPLINE (masterplan §4; DNR row 45 / TXI Article 1/2): display / LLM-context ONLY.
A base rate NEVER gates, ranks, sizes, or escalates anything; the word "validated" never
appears in emitted text; there is no LLM anywhere in this module. Every emit dict carries
``display_only=True``. FAIL-OPEN: absent history leaves a hop ``untested``, never raising.
Heavy compute (a full-history scan of ~10 series) runs OFF the render path on a WEEKLY
cadence (``scripts/run_transmission_calibration.py`` in weekly.yml), never nightly.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from engine import transmission_chains as tc

log = logging.getLogger(__name__)

SCHEMA_ID = "transmission_calibration.v1"
ROOT = tc.ROOT

# n floor: a cell with fewer than this many activations prints "untested" with its n, never
# a rate. 8 is the masterplan's suggested floor — enough for a base rate to be non-vacuous
# without demanding a sample the 25y (often ~15y usable) history can't supply.
N_FLOOR = 8


# --------------------------------------------------------------------------- #
# SERIES ACCESS — a store-backed close reader, ROOT-AWARE + hermetic (tests pass a tmp root).
# Reuses transmission_chains._SeriesAdapter (the same on-disk parquet layout as lib.store),
# so the miner reads exactly the bars the nightly node evaluator reads.
# --------------------------------------------------------------------------- #
class SeriesSource:
    """Reads a group's close series by ticker, caching each. Groups: yahoo / commodity /
    fred (the resolvable node srcs). A missing series raises tc._Unresolvable (the caller
    turns that into an ``untested`` hop, never a crash)."""

    def __init__(self, data_dir: Path):
        self._adapters = {
            "yahoo": tc._SeriesAdapter(data_dir, "yahoo"),
            "commodity": tc._SeriesAdapter(data_dir, "commodity"),
            "fred": tc._SeriesAdapter(data_dir, "fred"),
        }
        self._cache: dict[tuple[str, str], pd.Series] = {}

    def get(self, group: str, name: str) -> pd.Series:
        key = (group, name)
        if key not in self._cache:
            adapter = self._adapters.get(group)
            if adapter is None:
                raise tc._Unresolvable(f"no series group {group!r}")
            self._cache[key] = adapter.series(name)   # raises _Unresolvable if absent
        return self._cache[key]

    def reader(self, group: str) -> Callable[[str], pd.Series]:
        """A one-arg ``get_series(name)`` bound to a group — the shape
        ``transmission_chains.series_test_timeseries`` expects."""
        return lambda name: self.get(group, name)


# --------------------------------------------------------------------------- #
# NODE ACTIVATION HISTORY. A series-adapter node reconstructs directly from its test (the
# shared vectorized evaluator). A state-adapter node has NO stored history — it binds to a
# documented series PROXY below, or is ``untested`` (reason recorded). Returns
# (bool pd.Series | None, method_str). None ⇒ this node cannot be historized.
# --------------------------------------------------------------------------- #
# STATE-NODE PROXIES (TXI-R6: derive a coarse detector from an observable). Each entry maps a
# chain's state-adapter node id → a builder(SeriesSource) -> (bool Series, method-note). Only
# nodes whose LIVE test can be honestly reconstructed from a collected series appear here; a
# state node ABSENT from this registry is reported ``untested`` with a reason (never faked).
#
# Provenance of each proxy (why it is faithful to the live node test, not a convenient fudge):
#   oil.yield_rise (live: transmission latest.state.rates direction=rising AND
#       real_10y_chg_63d_bp>30) → fred/DFII10 (the constant-maturity 10y TIPS real yield the
#       transmission engine itself reads): Δ63d in bp > 30 AND Δ63d > 0 (rising). Same
#       observable, same 63d window, same +30bp cut — reconstructed from the raw series.
#   vol.vol_expansion (live: vol_regime.regime in {warning, backwardation-stress} OR vix>=25)
#       → fred/VIXCLS vix_close >= 25. The VIX>=25 leg is reproduced EXACTLY; the categorical
#       4-state vol-regime label is engine-internal and not stored historically, so this proxy
#       is the OR's observable leg only (a HONEST PARTIAL — noted in the method string; it
#       under-counts activations that fired on the label alone below VIX 25).
#   dollar.dollar_spike (live: dollar_desk.trend=up AND usd_pos_pctile>=60) → fred/DTWEXBGS
#       broad dollar: price above its 50d MA AND 63d return>0 (trend up) AND level in the top
#       40% of its trailing 252d range (usd_pos_pctile>=60 ≈ rolling 1y percentile≥0.60).
#   dollar.usd_transmission_on (live: transmission.usd_dir=strengthening AND headwind_for
#       contains 'EM equities') → fred/DTWEXBGS 21d return>0 (strengthening). The headwind_for
#       membership is a derived label the forex engine writes when the dollar strengthens vs
#       EM; strengthening-dollar is its observable driver, reconstructed here.
def _proxy_yield_rise(src: SeriesSource) -> tuple[pd.Series, str]:
    s = src.get("fred", "DFII10")
    chg = (s - s.shift(63)) * 100.0            # Δ63d in basis points (series in %)
    fired = (chg > 30.0) & (chg > 0.0)
    return fired.dropna().astype(bool), "proxy: fred/DFII10 real-10y Δ63d>30bp AND rising (Δ63d>0)"


def _proxy_vol_expansion(src: SeriesSource) -> tuple[pd.Series, str]:
    s = src.get("fred", "VIXCLS")
    fired = s >= 25.0
    return (fired.dropna().astype(bool),
            "proxy: fred/VIXCLS vix>=25 (VIX-floor leg only; categorical vol-regime label not "
            "historized — honest partial, under-counts label-only activations below VIX 25)")


def _proxy_dollar_spike(src: SeriesSource) -> tuple[pd.Series, str]:
    s = src.get("fred", "DTWEXBGS")
    ma50 = s.rolling(50).mean()
    ret63 = s / s.shift(63) - 1.0
    roll_pct = s.rolling(252).apply(lambda w: (w <= w[-1]).mean(), raw=True)  # trailing-1y pctile of last value
    fired = (s > ma50) & (ret63 > 0.0) & (roll_pct >= 0.60)
    return fired.dropna().astype(bool), "proxy: fred/DTWEXBGS >50d MA AND 63d ret>0 AND trailing-252d pctile>=0.60"


def _proxy_usd_transmission_on(src: SeriesSource) -> tuple[pd.Series, str]:
    s = src.get("fred", "DTWEXBGS")
    fired = (s / s.shift(21) - 1.0) > 0.0
    return fired.dropna().astype(bool), "proxy: fred/DTWEXBGS 21d ret>0 (dollar strengthening)"


# keyed by (chain_slug, node_id)
_STATE_NODE_PROXIES: dict[tuple[str, str], Callable[[SeriesSource], tuple[pd.Series, str]]] = {
    ("oil_inflation_duration_derate", "yield_rise"): _proxy_yield_rise,
    ("vol_regime_deleveraging", "vol_expansion"): _proxy_vol_expansion,
    ("dollar_spike_em_multinational", "dollar_spike"): _proxy_dollar_spike,
    ("dollar_spike_em_multinational", "usd_transmission_on"): _proxy_usd_transmission_on,
}


def node_activation_history(chain: dict, node_id: str, src: SeriesSource) -> tuple[pd.Series | None, str]:
    """The boolean activation history of one node → (bool pd.Series | None, method).

    * series-adapter node → reconstructed directly from its test via the shared vectorized
      evaluator (same thresholds as the nightly point-in-time evaluator).
    * state-adapter node  → a documented series proxy (``_STATE_NODE_PROXIES``), else
      (None, "untested: <reason>") — never fabricated.
    """
    node = chain["nodes"][node_id]
    node_src = node["src"]
    if node_src in ("yahoo", "commodity", "fred"):
        try:
            hist = tc.series_test_timeseries(src.reader(node_src), node["test"])
            return (hist if not hist.empty else None), f"series:{node_src}"
        except tc._Unresolvable as e:
            return None, f"untested: series unavailable ({e})"
    # state-adapter node — look for a documented proxy
    proxy = _STATE_NODE_PROXIES.get((chain["chain"], node_id))
    if proxy is None:
        return None, (f"untested: state-adapter node (src={node_src}) has no stored history "
                      f"and no documented series proxy — not reconstructable, not fabricated")
    try:
        hist, method = proxy(src)
        return (hist if not hist.empty else None), method
    except tc._Unresolvable as e:
        return None, f"untested: proxy series unavailable ({e})"


# --------------------------------------------------------------------------- #
# REGIME CELLS (TXI-R6). A hop's ``condition`` prose names the regime the hop SHOULD work in;
# we split activations by a COARSE, observable cell from data/regime/regime_history.parquet
# (a real daily quad/liquidity/growth/inflation series back to 1927, fully populated post-2000).
# Each regime scheme is a function date -> cell-label (or None = uncovered that day). We pick
# the scheme by matching keywords in the hop's condition; if none matches (or the history is
# absent), the hop is POOLED with regime_split="unavailable"+reason — never a fabricated split.
# --------------------------------------------------------------------------- #
class RegimeHistory:
    """The daily regime label frame (regime_history.parquet), loaded once. Exposes coarse
    cell schemes keyed by name; each returns a date-indexed Series of string cell labels."""

    def __init__(self, frame: pd.DataFrame | None):
        self.frame = frame

    @classmethod
    def load(cls, data_dir: Path) -> "RegimeHistory":
        p = data_dir / "regime" / "regime_history.parquet"
        if not p.exists():
            return cls(None)
        try:
            df = pd.read_parquet(p)
            df.index = pd.to_datetime(df.index)
            return cls(df.sort_index())
        except Exception as e:  # noqa: BLE001 — corrupt/absent history = pooled, never fatal
            log.warning("regime_history unreadable (%s) — hops will pool", e)
            return cls(None)

    def available(self) -> bool:
        return self.frame is not None and not self.frame.empty

    # ---- coarse cell schemes ------------------------------------------------
    def _growth_accel(self) -> pd.Series:
        """Global-growth-accelerating vs not — the supply-vs-demand distinction the oil chain's
        condition needs (a demand-driven oil shock rides accelerating growth; a supply shock
        does not). growth_score in [-1,1]; accelerating ≈ score rising over 63d AND > 0."""
        g = self.frame["growth_score"].astype(float)
        chg = g - g.shift(63)
        cell = pd.Series("growth_steady_or_slowing", index=g.index)
        cell[(chg > 0) & (g > 0)] = "growth_accelerating"
        return cell

    def _liquidity_dir(self) -> pd.Series:
        """Fed / liquidity direction — the QE/non-QE distinction the vol and yield hops name.
        The engine's own liquidity label {expanding, contracting, neutral, unknown}; we fold to
        expanding ('qe_easing') vs not."""
        liq = self.frame["liquidity"].astype(str)
        cell = pd.Series("liquidity_neutral_or_draining", index=liq.index)
        cell[liq == "expanding"] = "liquidity_expanding"
        cell[liq == "contracting"] = "liquidity_contracting"
        return cell

    def _inflation_regime(self) -> pd.Series:
        """Inflation-up vs inflation-down — for the breakeven / passthrough hops. inflation_score
        in [-1,1]; >0 = inflation impulse up."""
        infl = self.frame["inflation_score"].astype(float)
        cell = pd.Series("inflation_down_or_flat", index=infl.index)
        cell[infl > 0] = "inflation_up"
        return cell

    def _quad(self) -> pd.Series:
        """The growth×inflation quad (Q1-Q4) — the coarsest always-available macro cell."""
        return self.frame["quad"].astype(str)

    _SCHEMES = {
        "growth_accel": ("_growth_accel", ("pmi", "supply-driven", "demand-driven", "demand", "supply", "global pmi")),
        "liquidity_dir": ("_liquidity_dir", ("qe", "ycc", "fed not capping", "fed capping", "balance-sheet", "balance sheet", "liquidity", "vol-target", "realized-vol")),
        "inflation_regime": ("_inflation_regime", ("breakeven", "passthrough", "cost-push", "inflation", "expectations")),
    }

    def scheme_for_condition(self, condition_text: str) -> tuple[str, pd.Series] | None:
        """Pick the coarse regime scheme whose keyword set best matches the hop condition
        prose. Returns (scheme_name, cell Series) or None (→ pooled with reason). The quad
        fallback is used only when a condition names a regime but no keyword scheme matches."""
        if not self.available():
            return None
        text = (condition_text or "").lower()
        for name, (meth, keys) in self._SCHEMES.items():
            if any(k in text for k in keys):
                return name, getattr(self, meth)()
        return None


# --------------------------------------------------------------------------- #
# HOP CALIBRATION — the measurement. Given the from/to activation histories and the hop's
# lag window, compute P(to fires within [0, lag_hi]d of a from-activation) with n, split by
# regime cell. Nulls / thin cells → "untested" WITH n (never a fabricated rate).
# --------------------------------------------------------------------------- #
def _confirm_flags(from_hist: pd.Series, to_hist: pd.Series, lag_hi: int) -> pd.DataFrame:
    """For every FROM-activation date, whether the TO-node fired within lag_hi CALENDAR days
    (inclusive), plus the activation's own date (for the regime join). Returns a frame indexed
    by activation date with a bool ``confirmed`` column. A from-activation whose forward window
    extends past the end of the TO history is DROPPED (right-censored — we can't observe its
    outcome), so p is never biased by unresolved-yet windows."""
    from_dates = from_hist.index[from_hist.values.astype(bool)]
    if len(from_dates) == 0:
        return pd.DataFrame(columns=["confirmed"])
    to_true = to_hist[to_hist.values.astype(bool)]
    to_true_dates = to_true.index
    to_end = to_hist.index.max()
    rows = {}
    for d in from_dates:
        window_end = d + pd.Timedelta(days=int(lag_hi))
        if window_end > to_end:
            continue   # right-censored: outcome not yet observable — exclude from the base rate
        confirmed = bool(((to_true_dates >= d) & (to_true_dates <= window_end)).any())
        rows[d] = confirmed
    if not rows:
        return pd.DataFrame(columns=["confirmed"])
    return pd.DataFrame({"confirmed": pd.Series(rows)}).sort_index()


def _rate_or_untested(n_confirm: int, n: int) -> dict:
    """A {p, n} cell, or {p:"untested", n} when n < N_FLOOR. NEVER a rate below the floor."""
    if n < N_FLOOR:
        return {"p": "untested", "n": int(n), "reason": f"n<{N_FLOOR}"}
    return {"p": round(n_confirm / n, 4), "n": int(n)}


def calibrate_hop(chain: dict, hop: dict, from_id: str, to_id: str,
                  src: SeriesSource, regimes: RegimeHistory) -> dict:
    """Calibrate one hop → the per-hop calibration dict. Honest: an unreconstructable node
    (either end) → the whole hop is ``untested`` with the reason; a thin pooled/cell sample →
    "untested" with n. Regime split present only when a scheme matched AND the history exists."""
    lag_lo, lag_hi = hop.get("lag_d", [0, 0])
    base = {
        "from": from_id, "to": to_id, "lag_d": [lag_lo, lag_hi],
        "method": None, "p_confirm": "untested", "n": 0,
        "per_regime": {}, "regime_split": "unavailable",
    }
    from_hist, from_method = node_activation_history(chain, from_id, src)
    to_hist, to_method = node_activation_history(chain, to_id, src)
    base["method"] = {"from": from_method, "to": to_method}
    if from_hist is None or to_hist is None:
        # one leg not reconstructable → hop is honestly untested (masterplan: never fabricate)
        base["regime_split_reason"] = "a node could not be historized (see method)"
        base["untested_reason"] = "upstream or downstream node not reconstructable from collected series"
        return base

    flags = _confirm_flags(from_hist, to_hist, int(lag_hi))
    n = len(flags)
    n_confirm = int(flags["confirmed"].sum()) if n else 0
    pooled = _rate_or_untested(n_confirm, n)
    base["p_confirm"] = pooled["p"]
    base["n"] = pooled["n"]
    if "reason" in pooled:
        base["untested_reason"] = f"pooled {pooled['reason']}"
    if n:
        base["span"] = {"first": str(flags.index.min().date()), "last": str(flags.index.max().date())}

    # ---- regime-conditional split (TXI-R6) ----
    cond = hop.get("condition")
    cond_text = cond.get("en") if isinstance(cond, dict) else (cond or "")
    scheme = regimes.scheme_for_condition(cond_text)
    if scheme is None:
        base["regime_split"] = "unavailable"
        base["regime_split_reason"] = (
            "no regime-history series matched this hop's condition — pooled rate only "
            "(regime_history.parquet absent)" if not regimes.available()
            else f"no coarse regime scheme matched the condition prose {cond_text!r}; pooled only")
        return base
    if n == 0:
        base["regime_split"] = "unavailable"
        base["regime_split_reason"] = "no activations to split"
        return base
    scheme_name, cell_series = scheme
    # label each activation date with its regime cell (as-of that day; forward-fill the daily
    # label to the activation date so a weekend/holiday activation inherits the prior session).
    cells = cell_series.reindex(cell_series.index.union(flags.index)).sort_index().ffill().reindex(flags.index)
    joined = flags.assign(cell=cells.values)
    per_regime: dict[str, dict] = {}
    for cell_label, grp in joined.groupby("cell"):
        if not isinstance(cell_label, str):
            continue
        per_regime[cell_label] = _rate_or_untested(int(grp["confirmed"].sum()), len(grp))
    # activations whose cell was uncovered (NaN) bucket honestly
    n_uncovered = int(joined["cell"].isna().sum())
    base["regime_split"] = "available"
    base["regime_scheme"] = scheme_name
    base["per_regime"] = per_regime
    if n_uncovered:
        base["regime_uncovered_n"] = n_uncovered
    return base


# --------------------------------------------------------------------------- #
# COHORT EVENT-STUDY (masterplan §W3 "where cheaply possible"). After a chain fully expresses
# historically (its terminal node fires while the chain arc was recently active), the forward
# return of the terminal cohort proxy vs SPY. Descriptive, with n. Uses the terminal node's
# RS-proxy series (the ``vs`` leg of a series terminal node) — the W1 cohort proxies.
# --------------------------------------------------------------------------- #
_EVENT_HORIZONS_D = [21, 63]


def cohort_event_study(chain: dict, src: SeriesSource) -> dict:
    """Descriptive forward-return study of the terminal cohort vs SPY at the moments the chain's
    terminal node fired. Cheap + honest: only runs when the terminal node is a series RS/ratio
    proxy (its cohort series is known); otherwise returns {available:false, reason}. n printed."""
    node_ids = list(chain["nodes"].keys())
    term = chain["nodes"][node_ids[-1]]
    t = term.get("test", {})
    if term.get("src") not in ("yahoo", "commodity", "fred") or "series" not in t:
        return {"available": False, "reason": "terminal node is not a single-series cohort proxy"}
    cohort_name = t["series"]
    try:
        cohort = src.get(term["src"], cohort_name)
        spy = src.get("yahoo", "SPY")
        term_hist, _ = node_activation_history(chain, node_ids[-1], src)
    except tc._Unresolvable as e:
        return {"available": False, "reason": f"series unavailable ({e})"}
    if term_hist is None:
        return {"available": False, "reason": "terminal activation history empty"}
    cohort, spy = cohort.align(spy, join="inner")
    fire_dates = term_hist.index[term_hist.values.astype(bool)]
    fire_dates = fire_dates[fire_dates.isin(cohort.index)]
    out_horizons: dict[str, Any] = {}
    for h in _EVENT_HORIZONS_D:
        excess = []
        pos = {d: i for i, d in enumerate(cohort.index)}
        for d in fire_dates:
            i = pos.get(d)
            if i is None or i + h >= len(cohort):
                continue
            cr = cohort.iloc[i + h] / cohort.iloc[i] - 1.0
            sr = spy.iloc[i + h] / spy.iloc[i] - 1.0
            excess.append((cr - sr) * 100.0)   # cohort-minus-SPY forward return, pct points
        if len(excess) >= N_FLOOR:
            ser = pd.Series(excess)
            out_horizons[f"{h}d"] = {
                "mean_excess_pct": round(float(ser.mean()), 3),
                "median_excess_pct": round(float(ser.median()), 3),
                "n": int(len(excess)),
            }
        else:
            out_horizons[f"{h}d"] = {"mean_excess_pct": "untested", "n": int(len(excess)),
                                     "reason": f"n<{N_FLOOR}"}
    return {"available": True, "cohort": cohort_name, "vs": "SPY",
            "note": "descriptive forward excess return of the terminal cohort proxy at "
                    "terminal-node firings — NOT a forecast, NOT a signal (display-only).",
            "horizons": out_horizons}


# --------------------------------------------------------------------------- #
# TOP-LEVEL — calibrate every chain, assemble transmission_calibration.v1.
# --------------------------------------------------------------------------- #
CAVEATS = [
    {"en": "Display-only historical context — base rates NEVER gate, size, rank, or escalate "
           "anything (masterplan §4; DNR row 45). A base rate is a printed conditional "
           "frequency, not a forecast and not a signal.",
     "zh": "仅供展示的历史上下文——基础发生率从不做门控、仓位、排名或升级（总纲§4）。基础发生率是打印的条件频率，既非预测也非信号。"},
    {"en": "A cell with n below the floor prints \"untested\" WITH its n — never a fabricated "
           "rate. Honest coverage (many hops thin/untested on ~15y usable history) is the "
           "correct, publishable result.",
     "zh": "样本量低于下限的单元格打印“未检验”并附上其n——绝不编造发生率。诚实的覆盖率（许多跳在约15年可用历史上样本稀薄/未检验）是正确且可公开的结果。"},
    {"en": "State-adapter nodes (transmission/regime/forex snapshots have no stored history) "
           "bind to a DOCUMENTED series proxy where one faithfully reconstructs the live test, "
           "else the hop is untested. Each proxy's derivation is printed in the hop's method.",
     "zh": "状态适配器节点（传导/regime/外汇快照无历史留存）在能忠实重建实时判定时绑定至有据可查的序列代理，否则该跳标记未检验。每个代理的推导打印在该跳的method中。"},
]


def build_calibration(chains: list[dict], src: SeriesSource, regimes: RegimeHistory,
                      asof: str) -> dict:
    """Calibrate every chain → the transmission_calibration.v1 dict. A chain that raises is
    logged and SKIPPED (fail-open); its absence from the emit is honest (the live read falls
    back to the null base_rates placeholder → tier stays hypothesis)."""
    out_chains: list[dict] = []
    for chain in chains:
        if chain.get("_killed"):
            continue
        slug = chain["chain"]
        try:
            hops_cal = []
            node_ids = list(chain["nodes"].keys())
            for i, hop in enumerate(chain["hops"]):
                hops_cal.append(calibrate_hop(chain, hop, hop["from"], hop["to"], src, regimes))
            calibrated_hops = sum(1 for h in hops_cal if h["p_confirm"] != "untested")
            out_chains.append({
                "chain": slug,
                "rev": chain.get("rev", 0),
                "n_hops": len(hops_cal),
                "calibrated_hops": calibrated_hops,
                "hops": hops_cal,
                "cohort_event_study": cohort_event_study(chain, src),
                "display_only": True,
            })
        except Exception as e:  # noqa: BLE001 — one bad chain never breaks the batch
            log.error("calibration for chain %s failed (skipped): %s", slug, e)
            continue
    return {
        "schema": SCHEMA_ID,
        "asof": asof,
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "n_floor": N_FLOOR,
        "regime_history_available": regimes.available(),
        "chains": out_chains,
        "caveats": CAVEATS,
        "display_only": True,
    }


def _resolve_asof(data_dir: Path) -> str:
    """asof stamp — the regime history's last bar if present, else today (UTC)."""
    p = data_dir / "regime" / "regime_history.parquet"
    if p.exists():
        try:
            df = pd.read_parquet(p)
            return str(pd.to_datetime(df.index).max().date())
        except Exception:  # noqa: BLE001
            pass
    return date.today().isoformat()


def run(root: Path | None = None, *, write: bool = True) -> dict:
    """Load the chain library, mine each hop's historical conditional base rates, and (if
    write) emit data/transmission/chain_calibration.json. FAIL-OPEN: absent series/history
    leave hops ``untested``, never raising; ``write=False`` is the dry-run/test path.

    NOTE (ledger law): this writes a nightly/weekly-advanced forward ARTIFACT — a worktree
    run must ``git restore data/`` before commit. The weekly runner is the sole scheduled
    writer on main."""
    base = Path(root) if root else ROOT
    data_dir = base / "data"
    chains = load_chains_for_calibration(base)
    src = SeriesSource(data_dir)
    regimes = RegimeHistory.load(data_dir)
    asof = _resolve_asof(data_dir)
    state = build_calibration(chains, src, regimes, asof)
    if write:
        outdir = data_dir / "transmission"
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "chain_calibration.json").write_text(
            json.dumps(state, indent=2, ensure_ascii=False, default=str))
        log.info("transmission_calibration: %d chains, asof=%s, floor=%d",
                 len(state["chains"]), asof, N_FLOOR)
    return state


def load_chains_for_calibration(root: Path) -> list[dict]:
    """Load the chain library (fail-loud on a schema-violating file, same as the nightly
    compiler). Thin wrapper so the runner/tests have one entry point."""
    return tc.load_chains(root)
