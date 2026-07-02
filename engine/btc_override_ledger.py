"""BTC Override Forward-Grading Ledger — W5 of the Override-Registry program.

Implements the forward-grading ledger for the ``midterm_blackout`` allocation override
(the rule holding BTC allocation at 0% through 2026), as specified in:
    research/BTC_VECTOR_FIX_MASTERPLAN.md §4 N4, §5 W5

This is MONITORING ONLY — it carries ZERO allocation authority. The scored output
(data/vector/override_scored.json) is display/research metadata. Nothing in the
sizing or allocation execution path may import or read this module or its outputs.

Frozen sub-claim set: v1 (THE SET IS FROZEN — config may not add/remove members).

API:
    stamp(asof=None, *, root=None, sig=None, thesis=None, _persist=True) → dict
    score(asof=None, *, root=None, sig=None, _persist=True) → dict
    render_summary(asof=None, *, root=None) → dict

Ledger:  data/vector/override_ledger.jsonl   (rewritten idempotent per date)
Scored:  data/vector/override_scored.json    (rewritten on each score() call)
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config
from engine.btc_signals import _us_election_date

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# schema / paths
# --------------------------------------------------------------------------- #
SCHEMA = "btc_override_ledger.v1"

_LEDGER_PATH = ("data", "vector", "override_ledger.jsonl")
_SCORED_PATH = ("data", "vector", "override_scored.json")
_SIGNALS_PATH = ("data", "vector", "signals.parquet")

OVERRIDE_ID = "midterm_blackout"

# --------------------------------------------------------------------------- #
# FROZEN sub-claim set v1 — THE SET IS FROZEN.
# Code must warn and ignore any config attempt to add/remove members.
# --------------------------------------------------------------------------- #
FROZEN_SUBCLAIMS_V1: dict[str, str] = {
    "drawdown_deepens_into_window": (
        "The minimum BTC price in the thesis bottom-window is lower than the "
        "minimum price between gate-start and window-open (the window is the "
        "genuine trough, not a mid-gate noise dip)."
    ),
    "no_new_high": (
        "BTC does not print a new all-time high (above ATH at gate-start) at "
        "any point during the gate period [GS, election-day]. An ATH breach "
        "is the Class-1 invalidation trigger for the midterm-blackout thesis."
    ),
    "bottom_lands_in_window": (
        "The lowest BTC close from gate-start through window-close+90d falls "
        "inside the thesis bottom-window [window_start, window_close], "
        "confirming the cycle-clock timing claim."
    ),
    "re_entry_captures_recovery": (
        "BTC closes on election-day are lower than at gate-start (the gate "
        "protected against a declining tape), AND BTC close 180d after "
        "election-day exceeds the election-day close (the post-gate rally "
        "materialises — the opportunity cost of the gate was negative)."
    ),
}

# --------------------------------------------------------------------------- #
# pre-committed tuning knobs — a-priori, never re-tuned;
# family size fixed at 4 even when fewer claims have resolved.
# --------------------------------------------------------------------------- #
CONFIRM_DAYS_BOTTOM = 90      # days after window_close before bottom_lands can resolve
RECOVERY_HORIZON_DAYS = 180   # days after election-day for re_entry_captures_recovery
BOOT_BLOCK = 21               # circular block-bootstrap block length (trading days)
BOOT_B = 2000                 # bootstrap replicates
BOOT_SEED = 7                 # deterministic RNG seed
FDR_Q = 0.10                  # Benjamini-Hochberg FDR level
FAMILY_M = 4                  # family size: FIXED at 4 even when <4 claims resolved


# --------------------------------------------------------------------------- #
# low-level helpers (mirror btc_regime_ledger style)
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str(asof=None) -> str:
    if asof is None:
        return date.today().isoformat()
    if hasattr(asof, "isoformat"):
        return asof.isoformat()
    return str(asof)


def _load_jsonl(path: Path) -> list[dict]:
    try:
        if not path.exists():
            return []
        lines = path.read_text().splitlines()
        return [json.loads(line) for line in lines if line.strip()]
    except Exception as e:  # noqa: BLE001
        log.warning("btc_override_ledger: jsonl load failed %s: %s", path, e)
        return []


def _dedupe_by_date(rows: list[dict]) -> dict[str, dict]:
    """Last write wins per date — makes stamp idempotent."""
    out: dict[str, dict] = {}
    for r in rows:
        d = r.get("date")
        if d:
            out[d] = r
    return out


def _write_json(path: Path, obj: Any) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("btc_override_ledger: json write failed %s: %s", path, e)


def _f(v) -> float | None:
    """Safe float cast; returns None for NaN/None."""
    try:
        if v is None:
            return None
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# BTC close helpers
# --------------------------------------------------------------------------- #
def _load_close(root: Path) -> pd.Series | None:
    """Load BTC daily closes from signals.parquet, indexed by datetime."""
    try:
        p = root / _SIGNALS_PATH[0] / _SIGNALS_PATH[1] / _SIGNALS_PATH[2]
        df = pd.read_parquet(p, columns=["close"])
        s = df["close"].dropna()
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("btc_override_ledger: close load failed: %s", e)
        return None


def _load_sig(root: Path) -> pd.DataFrame | None:
    """Load full signals.parquet."""
    try:
        p = root / _SIGNALS_PATH[0] / _SIGNALS_PATH[1] / _SIGNALS_PATH[2]
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df.index)
        return df.sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("btc_override_ledger: sig load failed: %s", e)
        return None


def _close_at(closes: pd.Series, dt) -> float | None:
    """Last close on or before dt."""
    try:
        sub = closes[closes.index <= pd.Timestamp(dt)]
        return _f(sub.iloc[-1]) if len(sub) else None
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------------- #
# grading-spec source resolution
# --------------------------------------------------------------------------- #
def _grading_spec(vcfg: dict) -> str:
    """Determine grading-spec source, warn loudly on drift, always return frozen set.

    Returns a source-description string (informational only — callers always
    grade FROZEN_SUBCLAIMS_V1 regardless).
    """
    overrides = vcfg.get("overrides")
    if not isinstance(overrides, list):
        return "frozen_v1 (registry pending W0)"

    entry = next(
        (o for o in overrides if isinstance(o, dict) and o.get("id") == OVERRIDE_ID),
        None,
    )
    if entry is None:
        return "frozen_v1 (registry pending W0)"

    gs = entry.get("grading_spec")
    if gs is None:
        return "frozen_v1 (registry pending W0)"

    # Accept both list and dict forms
    if isinstance(gs, list):
        spec_keys = set(gs)
    elif isinstance(gs, dict):
        spec_keys = set(gs.keys())
    else:
        return "frozen_v1 (registry pending W0)"

    frozen_keys = set(FROZEN_SUBCLAIMS_V1.keys())
    if spec_keys == frozen_keys:
        return "registry"

    log.warning(
        "btc_override_ledger: grading_spec drift vs FROZEN v1 — post-hoc additions "
        "are barred; using frozen set. registry_keys=%s frozen_keys=%s",
        sorted(spec_keys),
        sorted(frozen_keys),
    )
    return "frozen_v1 (registry drift ignored)"


# --------------------------------------------------------------------------- #
# gate-span helper
# --------------------------------------------------------------------------- #
def _gate_span(year: int, gate_cfg: dict) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return (gate_start, gate_release) for a midterm year.

    gate_start  = Jan 1 of `year`
    gate_release = election_day - buy_lead_days
    """
    gate_start = pd.Timestamp(year=int(year), month=1, day=1)
    election = _us_election_date(int(year))
    buy_lead = int(gate_cfg.get("buy_lead_days", 0))
    gate_release = election - pd.Timedelta(days=buy_lead)
    return gate_start, gate_release


def _midterm_year_for_date(dt: pd.Timestamp) -> int:
    """Return the relevant midterm year (year%4==2) for a given date.

    If the date's year IS a midterm year, return it; otherwise return the
    next midterm year (the gate we are heading toward).
    """
    y = dt.year
    if y % 4 == 2:
        return y
    # years until next midterm year
    remainder = (2 - y % 4) % 4
    if remainder == 0:
        remainder = 4
    return y + remainder


def _gate_source(vcfg: dict) -> str:
    """Describe where the gate configuration comes from."""
    overrides = vcfg.get("overrides")
    if isinstance(overrides, list):
        entry = next(
            (o for o in overrides if isinstance(o, dict) and o.get("id") == OVERRIDE_ID),
            None,
        )
        if entry is not None:
            return "registry"

    alloc = vcfg.get("allocation") or {}
    midterm_gate = alloc.get("midterm_gate") or {}
    if midterm_gate.get("enabled", False):
        return "legacy_config"

    return "disabled"


def _gate_cfg_from_vcfg(vcfg: dict) -> dict:
    """Extract the gate sub-config dict (for buy_lead_days etc)."""
    overrides = vcfg.get("overrides")
    if isinstance(overrides, list):
        entry = next(
            (o for o in overrides if isinstance(o, dict) and o.get("id") == OVERRIDE_ID),
            None,
        )
        if entry is not None:
            return entry.get("gate_cfg") or entry
    alloc = vcfg.get("allocation") or {}
    return alloc.get("midterm_gate") or {}


def _is_gate_active_on(dt: pd.Timestamp, vcfg: dict) -> bool:
    """Return True if the midterm_blackout gate is active on `dt`."""
    source = _gate_source(vcfg)
    if source == "disabled":
        return False
    gate_cfg = _gate_cfg_from_vcfg(vcfg)
    # Use the midterm year relevant for this date
    mt_year = _midterm_year_for_date(dt)
    gs, gr = _gate_span(mt_year, gate_cfg)
    # Gate is active only inside [Jan 1 of midterm year, release) AND only if
    # the date itself is in a midterm year (year%4==2).
    if dt.year % 4 != 2:
        return False
    return bool(gs <= dt < gr)


# --------------------------------------------------------------------------- #
# stamp — one row per day
# --------------------------------------------------------------------------- #
def stamp(
    asof=None,
    *,
    root=None,
    sig: pd.DataFrame | None = None,
    thesis: dict | None = None,
    _persist: bool = True,
) -> dict:
    """Append one row to the override ledger for `asof`. Idempotent per date.

    Args:
        asof:    override the stamp date (for testing / back-fill); default today
        root:    override the project root (for testing)
        sig:     DataFrame from btc_signals.compute_all(); if None, loaded from disk
        thesis:  dict from btc_cycle_thesis.monitor(); may be None
        _persist: if False, nothing is written to disk (for testing)

    Returns the stamped row dict.
    """
    try:
        return _stamp(asof=asof, root=root, sig=sig, thesis=thesis, _persist=_persist)
    except Exception as e:  # noqa: BLE001
        log.warning("btc_override_ledger stamp failed: %s", e)
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def _stamp(
    asof=None,
    *,
    root=None,
    sig: pd.DataFrame | None = None,
    thesis: dict | None = None,
    _persist: bool = True,
) -> dict:
    root = Path(root) if root else config.ROOT
    stamp_date = _today_str(asof)
    dt = pd.Timestamp(stamp_date)

    vcfg: dict = {}
    try:
        vcfg = config.load().get("vector") or {}
    except Exception:  # noqa: BLE001
        pass  # config may be absent in tests — degrade gracefully

    # ---- load signals -------------------------------------------------------- #
    if sig is None:
        sig = _load_sig(root)

    closes: pd.Series | None = None
    if sig is not None and "close" in sig.columns:
        closes = sig["close"].dropna()
        closes.index = pd.to_datetime(closes.index)
        closes = closes.sort_index()
    elif sig is None:
        raw = _load_close(root)
        closes = raw

    # ---- gate metadata ------------------------------------------------------- #
    gs_src = _gate_source(vcfg)
    gate_cfg = _gate_cfg_from_vcfg(vcfg)
    mt_year = _midterm_year_for_date(dt)
    gate_start_ts, gate_release_ts = _gate_span(mt_year, gate_cfg)
    gate_active = _is_gate_active_on(dt, vcfg)

    # ---- price fields -------------------------------------------------------- #
    close_val: float | None = None
    ath: float | None = None
    dd_from_ath: float | None = None
    alloc_gated: float | None = None
    alloc_raw: float | None = None
    override_active_col: bool | None = None

    if closes is not None and len(closes):
        pit = closes[closes.index <= dt]
        if len(pit):
            close_val = _f(pit.iloc[-1])
            ath_val = _f(pit.cummax().iloc[-1])
            ath = ath_val
            if close_val is not None and ath_val and ath_val > 0:
                dd_from_ath = _f(close_val / ath_val - 1.0)

    if sig is not None:
        pit_sig = sig[sig.index <= dt]
        if len(pit_sig):
            row_sig = pit_sig.iloc[-1]
            if "alloc_optimal" in sig.columns:
                alloc_gated = _f(row_sig.get("alloc_optimal"))
            if "alloc_optimal_raw" in sig.columns:
                alloc_raw = _f(row_sig.get("alloc_optimal_raw"))
            if "override_active" in sig.columns:
                v = row_sig.get("override_active")
                if v is not None and not (isinstance(v, float) and np.isnan(v)):
                    override_active_col = bool(v)

    # ---- thesis fields ------------------------------------------------------- #
    window_start: str | None = None
    window_end: str | None = None
    thesis_status: str | None = None
    if thesis is not None:
        window_start = thesis.get("window_start")
        window_end = thesis.get("window_end")
        thesis_status = thesis.get("thesis_status")

    row = {
        "schema": SCHEMA,
        "date": stamp_date,
        "stamped_at": _now_iso(),
        "override_id": OVERRIDE_ID,
        "gate_source": gs_src,
        "gate_active": gate_active,
        "gate_start": gate_start_ts.date().isoformat(),
        "gate_release": gate_release_ts.date().isoformat(),
        "close": close_val,
        "running_ath": ath,
        "drawdown_from_ath": dd_from_ath,
        "alloc_gated": alloc_gated,
        "alloc_raw": alloc_raw,
        "override_active_col": override_active_col,
        "window_start": window_start,
        "window_end": window_end,
        "thesis_status": thesis_status,
    }

    if _persist:
        path = root.joinpath(*_LEDGER_PATH)
        existing = _dedupe_by_date(_load_jsonl(path))
        existing[stamp_date] = row
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as fh:
                for r in sorted(existing.values(), key=lambda x: x["date"]):
                    fh.write(json.dumps(r, default=str) + "\n")
        except Exception as e:  # noqa: BLE001
            log.warning("btc_override_ledger: stamp write failed: %s", e)

    return row


# --------------------------------------------------------------------------- #
# Benjamini-Hochberg step-up (pure helper — directly testable)
# --------------------------------------------------------------------------- #
def _bh(pvals: dict[str, float], q: float, m: int) -> dict[str, dict]:
    """Benjamini-Hochberg step-up FDR correction.

    Args:
        pvals: mapping from claim key → p_raw (only RESOLVED claims)
        q:     FDR level (e.g. 0.10)
        m:     FIXED family size (use FAMILY_M=4 always)

    Returns mapping from claim key → {rank, bh_threshold, p_bh, significant_at_q}
    """
    if not pvals:
        return {}

    # Sort by p_raw ascending to assign ranks
    sorted_items = sorted(pvals.items(), key=lambda kv: kv[1])
    result: dict[str, dict] = {}

    for rank_1based, (key, _p_raw) in enumerate(sorted_items, start=1):
        result[key] = {
            "rank": rank_1based,
            "bh_threshold": round(q * rank_1based / m, 6),
            "p_bh": None,  # filled in second pass
            "significant_at_q": None,
        }

    # Second pass: monotone step-up adjusted p — p_bh[i] = min over ranks k>=i of
    # p_k * m/k, computed backwards from the largest rank. Significance is judged on
    # the ADJUSTED p (p_bh <= q), which is the canonical step-up rule: if any larger
    # rank clears its threshold, every smaller-p claim is rejected with it. Testing
    # each raw p only against its own rank's threshold would under-reject.
    keys_sorted = [k for k, _ in sorted_items]
    min_so_far = 1.0
    for key in reversed(keys_sorted):
        raw = pvals[key]
        rank = result[key]["rank"]
        candidate = min(1.0, raw * m / rank)
        min_so_far = min(min_so_far, candidate)
        result[key]["p_bh"] = round(min_so_far, 6)
        result[key]["significant_at_q"] = bool(min_so_far <= q)

    return result


# --------------------------------------------------------------------------- #
# circular block bootstrap
# --------------------------------------------------------------------------- #
def _bootstrap_null(
    closes_full: pd.Series,
    ath0: float,
    gate_start: pd.Timestamp,
    window_start: pd.Timestamp | None,
    window_end: pd.Timestamp | None,
    gate_release: pd.Timestamp,
    block: int = BOOT_BLOCK,
    B: int = BOOT_B,
    seed: int = BOOT_SEED,
) -> dict[str, float | None]:
    """Circular block bootstrap null: what fraction of paths would PASS each claim.

    ``closes_full`` is the full PIT close series (through asof); its post-gate dates
    give the simulated paths their calendar. The bootstrap log-returns are drawn
    STRICTLY from before gate_start — the null must not learn from the realized
    gate-period outcome it is testing. We simulate B price paths forward from
    close_at(gate_start) long enough to cover all claim resolution dates.

    Returns dict[claim_key -> p_raw | None].  None means the claim is not resolved
    or we lack data to simulate.
    """
    # ---- pre-gate log returns (PIT: nothing on/after gate_start) -------------- #
    pregap = closes_full[closes_full.index < gate_start].dropna().sort_index()
    if len(pregap) < block * 3:
        return {k: None for k in FROZEN_SUBCLAIMS_V1}

    log_rets = np.log(pregap.values[1:] / pregap.values[:-1])
    n = len(log_rets)
    rng = np.random.default_rng(seed)

    # ---- realized post-gate dates (for indexing simulated paths) ------------- #
    # We need a realized index of business-day-like dates from gate_start to
    # the latest needed resolution date (PIT-capped), to give the simulated path
    # proper date keys.
    need_end = gate_start
    if window_end is not None:
        need_end = max(need_end, window_end + pd.Timedelta(days=CONFIRM_DAYS_BOTTOM))
    need_end = max(need_end, gate_release + pd.Timedelta(days=RECOVERY_HORIZON_DAYS))

    # Use the realized closes to build the index of dates after gate_start
    realized_after = closes_full.index[closes_full.index > gate_start]
    # Filter to what's available (PIT)
    realized_after = realized_after[realized_after <= need_end]
    path_len = len(realized_after)
    if path_len == 0:
        return {k: None for k in FROZEN_SUBCLAIMS_V1}

    # Starting price = last known close on or before gate_start
    c0 = _close_at(closes_full, gate_start)
    if c0 is None or c0 <= 0:
        return {k: None for k in FROZEN_SUBCLAIMS_V1}

    nb = int(np.ceil(path_len / block))
    block_offsets = np.arange(block)

    # Pre-allocate counts for each claim
    counts = {k: 0 for k in FROZEN_SUBCLAIMS_V1}
    n_resolved = {k: False for k in FROZEN_SUBCLAIMS_V1}

    # We will compute for each path and check each claim
    # Map from date → array index for fast lookup
    date_to_idx = {ts: i for i, ts in enumerate(realized_after)}

    def idx_at(ts: pd.Timestamp) -> int | None:
        """Index of last date in realized_after on or before ts."""
        candidates = [i for dt, i in date_to_idx.items() if dt <= ts]
        return max(candidates) if candidates else None

    def idx_first_after(ts: pd.Timestamp) -> int | None:
        """Index of first date in realized_after strictly after ts."""
        candidates = [i for dt, i in date_to_idx.items() if dt > ts]
        return min(candidates) if candidates else None

    # Pre-compute indices for claim resolution dates
    # Claim 1: drawdown_deepens_into_window — needs window_start, window_end
    # Claim 2: no_new_high — needs gate_start..gate_release
    # Claim 3: bottom_lands_in_window — needs gate_start..window_end+90d
    # Claim 4: re_entry_captures_recovery — needs gate_start, gate_release, gate_release+180d

    idx_ws = idx_at(window_start) if window_start is not None else None
    idx_ws_excl = idx_first_after(window_start) if window_start is not None else None
    idx_we = idx_at(window_end) if window_end is not None else None
    idx_we90 = (idx_at(window_end + pd.Timedelta(days=CONFIRM_DAYS_BOTTOM))
                if window_end is not None else None)
    idx_gr = idx_at(gate_release)
    idx_gr180 = idx_at(gate_release + pd.Timedelta(days=RECOVERY_HORIZON_DAYS))

    # A claim is graded in the null only if its resolution date is within the realized path
    can_1 = (window_start is not None and window_end is not None
              and idx_ws is not None and idx_we is not None)
    can_2 = idx_gr is not None
    can_3 = (window_start is not None and window_end is not None
              and idx_we90 is not None)
    can_4 = (idx_gr is not None and idx_gr180 is not None)

    n_resolved["drawdown_deepens_into_window"] = can_1
    n_resolved["no_new_high"] = can_2
    n_resolved["bottom_lands_in_window"] = can_3
    n_resolved["re_entry_captures_recovery"] = can_4

    for _ in range(B):
        # Sample circular block indices
        starts = rng.integers(0, n, nb)
        idx_arr = (starts[:, None] + block_offsets[None, :]).ravel()[:path_len] % n
        sim_log_rets = log_rets[idx_arr]

        # Build simulated price path (length = path_len + 1: [c0, ...])
        sim_prices = np.empty(path_len + 1)
        sim_prices[0] = c0
        sim_prices[1:] = c0 * np.exp(np.cumsum(sim_log_rets))

        # Helper: price at array index i (0-based into realized_after; +1 offset for sim_prices)
        def sp(i: int | None) -> float | None:
            if i is None:
                return None
            j = i + 1  # offset because sim_prices[0] = c0 (at gate_start, before the path)
            if j >= len(sim_prices):
                return None
            return float(sim_prices[j])

        # Claim 1: drawdown_deepens_into_window
        if can_1:
            # pre-window min: prices in [gs, window_start) — indices [0..idx_ws_excl)
            # Note: sim_prices[1..] correspond to realized_after[0..]
            # pre-window = realized_after dates < window_start
            pre_end = idx_ws_excl if idx_ws_excl is not None else idx_ws
            if pre_end is not None and pre_end > 0:
                pre_min = float(np.min(sim_prices[1:pre_end + 1]))
            else:
                pre_min = c0
            # window min: prices in [window_start, window_end] — indices [idx_ws..idx_we+1)
            w_start_i = (idx_ws_excl if idx_ws_excl is not None else 0)
            w_end_i = idx_we if idx_we is not None else path_len - 1
            win_slice = sim_prices[w_start_i + 1: w_end_i + 2]
            if len(win_slice) > 0:
                win_min = float(np.min(win_slice))
                if win_min < pre_min:
                    counts["drawdown_deepens_into_window"] += 1

        # Claim 2: no_new_high — PASS iff no price in (gate_start..gate_release] > ath0
        if can_2:
            # sim_prices[1..idx_gr+1] correspond to realized_after[0..idx_gr]
            gate_slice = sim_prices[1: idx_gr + 2]
            if len(gate_slice) > 0 and float(np.max(gate_slice)) <= ath0:
                counts["no_new_high"] += 1

        # Claim 3: bottom_lands_in_window
        if can_3:
            # argmin of prices in [gate_start..window_end+90d] — sim_prices[1..idx_we90+2]
            full_slice = sim_prices[1: idx_we90 + 2]
            if len(full_slice) > 0:
                argmin_rel = int(np.argmin(full_slice))
                # Which realized date is that?
                if argmin_rel < len(realized_after):
                    min_date = realized_after[argmin_rel]
                    if window_start is not None and window_end is not None:
                        if window_start <= min_date <= window_end:
                            counts["bottom_lands_in_window"] += 1

        # Claim 4: re_entry_captures_recovery
        if can_4:
            p_gr = sp(idx_gr)
            p_gr180 = sp(idx_gr180)
            if p_gr is not None and p_gr180 is not None:
                if p_gr < c0 and p_gr180 > p_gr:
                    counts["re_entry_captures_recovery"] += 1

    result: dict[str, float | None] = {}
    for k in FROZEN_SUBCLAIMS_V1:
        if n_resolved[k]:
            result[k] = round(counts[k] / B, 6)
        else:
            result[k] = None
    return result


# --------------------------------------------------------------------------- #
# score — grade the four frozen sub-claims
# --------------------------------------------------------------------------- #
def score(
    asof=None,
    *,
    root=None,
    sig: pd.DataFrame | None = None,
    _persist: bool = True,
) -> dict:
    """Grade the four frozen sub-claims against realized BTC closes.

    Returns a summary dict + writes data/vector/override_scored.json when _persist.
    """
    try:
        return _score(asof=asof, root=root, sig=sig, _persist=_persist)
    except Exception as e:  # noqa: BLE001
        log.warning("btc_override_ledger score failed: %s", e)
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


def _score(
    asof=None,
    *,
    root=None,
    sig: pd.DataFrame | None = None,
    _persist: bool = True,
) -> dict:
    root = Path(root) if root else config.ROOT
    asof_str = _today_str(asof)
    asof_dt = pd.Timestamp(asof_str)

    vcfg: dict = {}
    try:
        vcfg = config.load().get("vector") or {}
    except Exception:  # noqa: BLE001
        pass

    gs_src = _gate_source(vcfg)
    spec_src = _grading_spec(vcfg)
    gate_cfg = _gate_cfg_from_vcfg(vcfg)

    # ---- load ledger --------------------------------------------------------- #
    ledger_path = root.joinpath(*_LEDGER_PATH)
    all_rows = list(_dedupe_by_date(_load_jsonl(ledger_path)).values())
    n_ledger_rows = len(all_rows)

    # ---- determine graded midterm year --------------------------------------- #
    # Most recent year%4==2 ≤ asof_dt.year that has gate-active ledger rows,
    # or (if ledger is thin) the most recent midterm year ≤ asof.
    gate_active_rows = [r for r in all_rows if r.get("gate_active")]
    graded_year: int | None = None
    if gate_active_rows:
        years = sorted({int(pd.Timestamp(r["date"]).year) for r in gate_active_rows
                        if int(pd.Timestamp(r["date"]).year) % 4 == 2}, reverse=True)
        # most recent ≤ asof year
        for y in years:
            if y <= asof_dt.year:
                graded_year = y
                break
    if graded_year is None:
        # fall back to nearest past midterm year
        for y in range(asof_dt.year, asof_dt.year - 5, -1):
            if y % 4 == 2:
                graded_year = y
                break
    if graded_year is None:
        graded_year = asof_dt.year - (asof_dt.year % 4 - 2) % 4

    gate_start, gate_release = _gate_span(graded_year, gate_cfg)

    # ---- load closes --------------------------------------------------------- #
    if sig is None:
        sig = _load_sig(root)

    closes: pd.Series | None = None
    if sig is not None and "close" in sig.columns:
        closes = sig["close"].dropna()
        closes.index = pd.to_datetime(closes.index)
        closes = closes.sort_index()
    if closes is None:
        closes = _load_close(root)

    # PIT cap
    if closes is not None:
        closes = closes[closes.index <= asof_dt]

    # ---- window start/end from ledger rows or thesis ------------------------- #
    window_start: pd.Timestamp | None = None
    window_end: pd.Timestamp | None = None

    # Use the most recent ledger row that carries window_start
    ws_rows = [r for r in all_rows
               if r.get("window_start") and pd.Timestamp(r["date"]) <= asof_dt]
    if ws_rows:
        latest = sorted(ws_rows, key=lambda r: r["date"])[-1]
        ws = latest.get("window_start")
        we = latest.get("window_end")
        if ws:
            try:
                window_start = pd.Timestamp(ws)
            except Exception:  # noqa: BLE001
                pass
        if we:
            try:
                window_end = pd.Timestamp(we)
            except Exception:  # noqa: BLE001
                pass

    # ---- helpers ------------------------------------------------------------- #
    def _pending(eta: pd.Timestamp | None, reason: str = "") -> dict:
        return {
            "status": "PENDING",
            "observed": None,
            "resolved_on": None,
            "eta": eta.date().isoformat() if eta is not None else None,
            "reason": reason,
            "p_raw": None,
            "p_bh": None,
            "significant_at_q10": None,
        }

    def _result(status: str, observed, resolved_on: pd.Timestamp | None = None,
                eta: pd.Timestamp | None = None) -> dict:
        return {
            "status": status,
            "observed": observed,
            "resolved_on": resolved_on.date().isoformat() if resolved_on is not None else None,
            "eta": eta.date().isoformat() if eta is not None else None,
            "reason": None,
            "p_raw": None,   # filled by bootstrap
            "p_bh": None,    # filled by BH
            "significant_at_q10": None,
        }

    subclaims: dict[str, dict] = {}
    window_unknown = (window_start is None or window_end is None)

    # ---- ATH at gate_start --------------------------------------------------- #
    ath0: float | None = None
    if closes is not None:
        pit_pre = closes[closes.index <= gate_start]
        if len(pit_pre):
            ath0 = _f(pit_pre.cummax().iloc[-1])

    # ---- Claim 1: drawdown_deepens_into_window ------------------------------- #
    if window_unknown:
        subclaims["drawdown_deepens_into_window"] = _pending(
            None, "window unknown"
        )
    elif asof_dt < window_end:
        subclaims["drawdown_deepens_into_window"] = _pending(
            window_end, "not yet reached window_end"
        )
    elif closes is None:
        subclaims["drawdown_deepens_into_window"] = _pending(
            window_end, "no price data"
        )
    else:
        # pre-window min: [GS, WO)
        pre_win = closes[(closes.index >= gate_start) & (closes.index < window_start)]
        # window min: [WO, WC]
        in_win = closes[(closes.index >= window_start) & (closes.index <= window_end)]
        if len(pre_win) == 0 or len(in_win) == 0:
            subclaims["drawdown_deepens_into_window"] = _pending(
                window_end, "insufficient data"
            )
        else:
            pre_min = float(pre_win.min())
            win_min = float(in_win.min())
            passed = bool(win_min < pre_min)
            subclaims["drawdown_deepens_into_window"] = _result(
                "PASS" if passed else "FAIL",
                {"pre_window_min": _f(pre_min), "window_min": _f(win_min)},
                resolved_on=window_end,
            )

    # ---- Claim 2: no_new_high ------------------------------------------------ #
    check_end_2 = min(asof_dt, gate_release)
    if closes is None or ath0 is None:
        subclaims["no_new_high"] = _pending(gate_release, "no price data")
    else:
        gate_series = closes[(closes.index > gate_start) & (closes.index <= check_end_2)]
        offense_dates = gate_series[gate_series > ath0]
        if len(offense_dates) > 0:
            # FAIL early — resolved on the first offense date
            first_offense = offense_dates.index[0]
            subclaims["no_new_high"] = _result(
                "FAIL",
                {"ath0": _f(ath0), "breach_price": _f(offense_dates.iloc[0])},
                resolved_on=first_offense,
            )
        elif asof_dt >= gate_release:
            # Full window passed with no offense
            subclaims["no_new_high"] = _result(
                "PASS",
                {"ath0": _f(ath0), "max_in_gate": _f(gate_series.max()) if len(gate_series) else None},
                resolved_on=gate_release,
            )
        else:
            subclaims["no_new_high"] = _pending(gate_release, "gate not yet elapsed")

    # ---- Claim 3: bottom_lands_in_window ------------------------------------- #
    confirm_end = (window_end + pd.Timedelta(days=CONFIRM_DAYS_BOTTOM)
                   if window_end is not None else None)
    if window_unknown:
        subclaims["bottom_lands_in_window"] = _pending(None, "window unknown")
    elif asof_dt < confirm_end:
        subclaims["bottom_lands_in_window"] = _pending(
            confirm_end, "not yet reached window_end + 90d"
        )
    elif closes is None:
        subclaims["bottom_lands_in_window"] = _pending(confirm_end, "no price data")
    else:
        # min of close[GS..WC+90d]
        full_range = closes[(closes.index >= gate_start) & (closes.index <= confirm_end)]
        if len(full_range) == 0:
            subclaims["bottom_lands_in_window"] = _pending(confirm_end, "insufficient data")
        else:
            argmin_dt = full_range.idxmin()
            in_window = bool(window_start <= argmin_dt <= window_end)
            subclaims["bottom_lands_in_window"] = _result(
                "PASS" if in_window else "FAIL",
                {"min_date": argmin_dt.date().isoformat(),
                 "min_price": _f(float(full_range.min())),
                 "window_start": window_start.date().isoformat() if window_start else None,
                 "window_end": window_end.date().isoformat() if window_end else None},
                resolved_on=confirm_end,
            )

    # ---- Claim 4: re_entry_captures_recovery --------------------------------- #
    r_plus_180 = gate_release + pd.Timedelta(days=RECOVERY_HORIZON_DAYS)
    if asof_dt < r_plus_180:
        subclaims["re_entry_captures_recovery"] = _pending(
            r_plus_180, "not yet reached gate_release + 180d"
        )
    elif closes is None:
        subclaims["re_entry_captures_recovery"] = _pending(r_plus_180, "no price data")
    else:
        c_gs = _close_at(closes, gate_start)
        c_gr = _close_at(closes, gate_release)
        c_gr180 = _close_at(closes, r_plus_180)
        if c_gs is None or c_gr is None or c_gr180 is None:
            subclaims["re_entry_captures_recovery"] = _pending(
                r_plus_180, "price data missing at key dates"
            )
        else:
            passed = bool(c_gr < c_gs and c_gr180 > c_gr)
            subclaims["re_entry_captures_recovery"] = _result(
                "PASS" if passed else "FAIL",
                {"close_at_gs": _f(c_gs),
                 "close_at_gr": _f(c_gr),
                 "close_at_gr180": _f(c_gr180)},
                resolved_on=r_plus_180,
            )

    # ---- bootstrap p_raw for resolved claims --------------------------------- #
    resolved_keys = [k for k, v in subclaims.items() if v["status"] in ("PASS", "FAIL")]

    if resolved_keys and closes is not None:
        # closes is already PIT-capped; the null slices its pre-gate returns itself
        p_raws = _bootstrap_null(
            closes,
            ath0=ath0 if ath0 is not None else float("inf"),
            gate_start=gate_start,
            window_start=window_start,
            window_end=window_end,
            gate_release=gate_release,
        )
        for k in FROZEN_SUBCLAIMS_V1:
            if k in subclaims:
                subclaims[k]["p_raw"] = p_raws.get(k)

    # ---- BH correction ------------------------------------------------------- #
    resolved_p_raws = {
        k: subclaims[k]["p_raw"]
        for k in resolved_keys
        if subclaims[k].get("p_raw") is not None
    }
    bh_results = _bh(resolved_p_raws, q=FDR_Q, m=FAMILY_M)
    for k, bh in bh_results.items():
        subclaims[k]["p_bh"] = bh["p_bh"]
        subclaims[k]["significant_at_q10"] = bh["significant_at_q"]

    # ---- add definitions to output ------------------------------------------- #
    for k, defn in FROZEN_SUBCLAIMS_V1.items():
        subclaims[k]["definition"] = defn

    out = {
        "schema": SCHEMA,
        "as_of": asof_str,
        "override_id": OVERRIDE_ID,
        "graded_year": graded_year,
        "gate_start": gate_start.date().isoformat(),
        "gate_release": gate_release.date().isoformat(),
        "window_start": window_start.date().isoformat() if window_start else None,
        "window_end": window_end.date().isoformat() if window_end else None,
        "frozen_spec_version": "v1",
        "grading_spec_source": spec_src,
        "subclaims": subclaims,
        "family_size": FAMILY_M,
        "fdr": f"Benjamini-Hochberg step-up, q={FDR_Q}, family m={FAMILY_M} fixed a-priori",
        "bootstrap": {
            "block": BOOT_BLOCK,
            "B": BOOT_B,
            "seed": BOOT_SEED,
            "null": "circular block bootstrap of pre-gate log returns",
        },
        "authority": (
            "MONITORING ONLY — zero allocation authority. "
            "Nothing in sizing/allocation reads this file."
        ),
        "n_ledger_rows": n_ledger_rows,
    }

    if _persist:
        _write_json(root.joinpath(*_SCORED_PATH), out)

    return out


# --------------------------------------------------------------------------- #
# render_summary — combined dashboard payload
# --------------------------------------------------------------------------- #
def render_summary(asof=None, *, root=None) -> dict:
    """Return a single render-ready dict combining last ledger row + score().

    Safe to call on every build; degrades gracefully with no ledger data.
    """
    try:
        root_path = Path(root) if root else config.ROOT
        asof_str = _today_str(asof)

        # Last ledger row (most recent stamped entry)
        ledger_path = root_path.joinpath(*_LEDGER_PATH)
        rows = list(_dedupe_by_date(_load_jsonl(ledger_path)).values())
        last_row = sorted(rows, key=lambda r: r["date"])[-1] if rows else None

        scored = score(asof=asof, root=root_path, _persist=False)

        return {
            "schema": SCHEMA,
            "as_of": asof_str,
            "override_id": OVERRIDE_ID,
            "last_ledger_row": last_row,
            "score": scored,
            "authority": (
                "MONITORING ONLY — zero allocation authority. "
                "Nothing in sizing/allocation reads this file."
            ),
        }
    except Exception as e:  # noqa: BLE001
        log.error("btc_override_ledger render_summary failed: %s", e)
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}


# --------------------------------------------------------------------------- #
# CLI entry point
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    s = render_summary()
    print(json.dumps(s, indent=2, default=str))
