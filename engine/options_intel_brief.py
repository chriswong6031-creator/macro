"""engine/options_intel_brief.py — AD-1 Daily EOD Options Intelligence Brief, pure engine.

Contract (BINDING, transcription only): ``contracts/options/OPTIONS_INTEL_BRIEF_V1.md``
(``model_version = intel_brief_heuristic/v1.2``). Secondary prose law:
``research/ADVANCED_DATA_OPTIONS_EOD_AD1_DAILY_INTELLIGENCE_BRIEF_HANDOFF_2026-08-17.md``
§5.3/§5.4. Any divergence between this module and the contract is a defect in exactly
one of them and must be RETURNED, never silently adapted (contract preamble).

Pure and deterministic: no file I/O, no network, no LLM, no randomness, no wall-clock
read anywhere in the scoring path. ``built_at_utc`` is a caller-supplied string threaded
through for display only and is explicitly excluded from ``receipt_id`` (contract §7,
test 31). The producer (``scripts/build_options_intel_brief.py``) does every filesystem
read, hands this module fully materialised in-memory frames/dicts, and writes the
resulting payload to disk.

Semantic-authority ladder (contract §5.3, `DEC:AD1-DIRECTION-AUTHORITY-SEPARATES-
SALIENCE-MECHANICS-AND-DIRECTION`): salience (``d1``, ``d3``, ``D_salience``) may raise
research priority but never carries direction; ``Q_oi`` and ``Q_skew`` are the ONLY two
legs that may jointly originate a directional (LONG/SHORT) hypothesis; GEX/mechanics may
only ever LOWER an already-qualified LONG's actionability; Prophet is display-only and
never touches score, confidence, or rank. ``Q_flow`` has no implementation anywhere in
this module — the signing gate (``data/options_flow/signing_gate.json``) currently reads
``direction_reliable: false`` and activation requires a new ``model_version`` plus
explicit review (contract §2 input #6, §4 direction-qualification law, test 17i);
there is intentionally no function, attribute, or code path here that could compute it.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# §3 — Frozen CONFIG (every constant, verbatim from the contract; test-pinned).
# ─────────────────────────────────────────────────────────────────────────────

MODEL_VERSION = "intel_brief_heuristic/v1.2"
SCHEMA = "options.intel_brief/v1"

CONFIG: dict[str, Any] = {
    "MODEL_VERSION": MODEL_VERSION,
    "SCHEMA": SCHEMA,
    "MIN_CONTRACTS": 20,
    "MIN_HISTORY": 10,
    "LOOKBACK": 20,
    "DOI_TARGET_WINDOW": 60,
    "DOI_FLOOR": 10,
    "SKEW_CHANGE_FLOOR": 8,
    "SALIENCE_W_D1": 0.65,
    "SALIENCE_W_D3": 0.35,
    "Q_TH": 0.50,
    "SALIENCE_TH": 0.60,
    "VOL_STATE_TH": 0.60,
    "EVENT_STATE_TH": 0.50,
    "ES_W_DIR": 0.70,
    "ES_W_SAL": 0.30,
    "CONF_BASE": 0.30,
    "CONF_PERSIST_BONUS": 0.10,
    "CONF_COVERAGE_BONUS": 0.05,
    "CONF_CEIL": 0.60,
    "CONF_CEIL_DIRECTIONAL": 0.45,
    "CONF_BAND_TENTATIVE_MAX": 0.40,   # < this => "tentative"
    "CONF_BAND_MODERATE_MAX": 0.55,    # < this (and >= tentative max) => "moderate"; else "firm"
    "TIER_MULT": {"T1": 1.0, "T2": 0.8, "T3": 0.5},
    "FRESH_PENALTY": 0.5,
    "EVENT_CONTAM_MULT": 0.6,
    "EVENT_CONTAM_SESSIONS": 2,
    "CROWD_MULT_LONG": 0.5,
    "M_GEX_CAUTION_LONG": 0.75,
    "R_MIN": 250,
    "BOARD_N": 6,
    "EVENT_BOARD_N": 4,
    "RISK_BOARD_N": 4,
    "NO_SIGNAL_R": 100,
    "ELIGIBILITY_GATE": 0.60,
    "SOURCE_COVERAGE_GATE": 0.90,
    "EVENT_MIN_NAMES": 5,
    "EVENT_WINDOW_DAYS": 45,
    "HIST_EVENT_ACTIVATION": 3,
    "BLEND_XS": 0.5,
    "BLEND_LONG": 0.5,
    "FRESH_LIVES_SESSIONS": {
        "Q_oi": 3, "D_salience": 3, "Q_skew": 3, "V": 5, "P": 1,
        "C_0DTE": 0, "E": "event_close",
    },
    "ATM_BAND": 0.05,
    "ATM_DTE": [7, 60],
    "ATM_N_CONTRACTS": 6,
    "TERM_FRONT_DTE": [7, 45],
    "TERM_BACK_DTE": [60, 120],
    "SKEW_PUT_DELTA": [-0.35, -0.15],
    "SKEW_CALL_DELTA": [0.15, 0.35],
    "SD_DTE": 1.5,
    "C1_TH": 0.90,
    "C2_IV_TH": 0.95,
    "C2_EXT": 0.98,
    "C3_D1": 0.95,
    "C3_D3": 0.5,
    "C3_V2": 0.90,
    "DTE_BUCKETS": [[0, 7], [8, 30], [31, 90], [91, None]],
    "MONEYNESS_BUCKETS": [[None, 0.95], [0.95, 1.05], [1.05, None]],
    "D1_PERSIST_TH": 0.8,
    "D1_PERSIST_WINDOW": 10,
    "DOI_CLAMP": 3.0,
}

# ─────────────────────────────────────────────────────────────────────────────
# Generic numeric helpers (pure).
# ─────────────────────────────────────────────────────────────────────────────


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def clamp01(x: float) -> float:
    return clamp(x, 0.0, 1.0)


def _finite(v) -> bool:
    try:
        return v is not None and np.isfinite(v)
    except TypeError:
        return False


def robust_z(value: float | None, history: Sequence[float | None]) -> float | None:
    """Median/MAD robust z of ``value`` against ``history``. None if either is unusable."""
    hist = [float(h) for h in history if _finite(h)]
    if not _finite(value) or not hist:
        return None
    med = float(np.median(hist))
    mad = float(np.median(np.abs(np.array(hist) - med))) * 1.4826
    return (float(value) - med) / (mad + 1e-9)


def clamped_z_over_3(value: float | None, history: Sequence[float | None],
                      *, sign: float = 1.0, clamp_at: float = CONFIG["DOI_CLAMP"]) -> float | None:
    z = robust_z(value, history)
    if z is None:
        return None
    return sign * clamp(z, -clamp_at, clamp_at) / clamp_at


def percentile_long(history: Sequence[float | None], value: float | None,
                     *, floor: int = CONFIG["MIN_HISTORY"]) -> float | None:
    """``p_long`` — value's percentile against its own trailing history. None below floor."""
    hist = [float(h) for h in history if _finite(h)]
    if not _finite(value) or len(hist) < floor:
        return None
    return float((np.array(hist) <= float(value)).mean())


def percentile_xs(peer_values: Mapping[str, float | None], symbol: str,
                   *, floor: int = CONFIG["MIN_HISTORY"]) -> float | None:
    """``p_xs`` — symbol's percentile among its (already tier-matched) peers."""
    vals = {k: float(v) for k, v in peer_values.items() if _finite(v)}
    if symbol not in vals or len(vals) < floor:
        return None
    arr = np.array(list(vals.values()))
    return float((arr <= vals[symbol]).mean())


def blend(p_xs: float | None, p_long: float | None,
          *, w_xs: float = CONFIG["BLEND_XS"], w_long: float = CONFIG["BLEND_LONG"]) -> float | None:
    """§4 conditioning blend: both present -> weighted mean; one present -> that one; else None."""
    if p_xs is None and p_long is None:
        return None
    if p_xs is None:
        return p_long
    if p_long is None:
        return p_xs
    return w_xs * p_xs + w_long * p_long


def signed_surprise(p: float | None) -> float | None:
    return None if p is None else (2.0 * p - 1.0)


def canonical_json_bytes(payload: Any) -> bytes:
    """House canonical-hash idiom (matches ``scripts/backfill_prophet_outage.py::
    _canonical_sha256``): sorted keys, compact separators, no NaN."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                       allow_nan=False, default=str).encode("utf-8")


def sha256_of(payload: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def config_hash(cfg: Mapping[str, Any] | None = None) -> str:
    return sha256_of(cfg if cfg is not None else CONFIG)


def receipt_id(*, schema: str, model_version: str, as_of_session: str,
               oi_counted_date: str, source_watermarks: Mapping[str, Any],
               input_receipts: Sequence[Mapping[str, Any]]) -> str:
    """``sha256(canonical_json({schema, model_version, as_of_session, oi_counted_date,
    source_watermarks, sorted(input_receipts)}))`` per contract §5. ``built_at_utc`` is
    NOT a parameter here — that is the exclusion test 31 pins."""
    sorted_receipts = sorted(
        input_receipts, key=lambda r: (str(r.get("logical_source")), str(r.get("path")))
    )
    return sha256_of({
        "schema": schema,
        "model_version": model_version,
        "as_of_session": as_of_session,
        "oi_counted_date": oi_counted_date,
        "source_watermarks": source_watermarks,
        "input_receipts": sorted_receipts,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Display vocabulary (closed; EN + ZH). No LLM anywhere near this file.
# ─────────────────────────────────────────────────────────────────────────────

DISPLAY_STATE = {
    "LONG": ("Upside evidence", "上行证据"),
    "SHORT": ("Downside evidence", "下行证据"),
    "VOLATILITY": ("Volatility", "波动性"),
    "RISK_ONLY": ("Risk / crowding", "风险/拥挤"),
}

CONF_BAND_WORDS = ("tentative", "moderate", "firm")

_PROPHET_MAP = {
    "hold": "ALREADY_OPEN", "partial": "ALREADY_OPEN",
    "bounce_wait": "NOT_READY",
    "buy_now": "READY",
    "extended": "EXTENDED", "topping": "EXTENDED",
}
_PROPHET_KNOWN_OTHER = {
    "await_confluence", "buy_soon", "watch", "exit", "avoid", "blocked",
}

#: intake.receipts.groups bucket -> display state (contract §5, B4 ruling). Buckets are
#: the ones the real artifact carries (`plan_not_built`, `already_open`, `not_ready`,
#: `ran_too_far`, `stood_down`, `conviction_low`, `pointing_down`); `wait_pullback` and
#: `buy_now` are included defensively for a differently-worded future bucket set — never
#: observed alongside the seven above, but lawful under the same closed vocabulary.
_PROPHET_GROUP_MAP = {
    "ran_too_far": "EXTENDED", "extended": "EXTENDED", "topping": "EXTENDED",
    "already_open": "ALREADY_OPEN",
    "not_ready": "NOT_READY", "wait_pullback": "NOT_READY", "bounce_wait": "NOT_READY",
    "buy_now": "READY",
    "stood_down": "OTHER", "conviction_low": "OTHER", "pointing_down": "OTHER",
    "plan_not_built": "OTHER",
}

#: Per-symbol precedence when the two Prophet domains (plans[] vs
#: intake.receipts.groups) disagree for the same ticker (B4 ruling, real-artifact
#: collisions e.g. BIIB: plans[].entry_status="bounce_wait" -> NOT_READY, but
#: receipts.groups reason="ran_too_far" -> EXTENDED; EXTENDED wins).
_PROPHET_STATE_PRECEDENCE = ("EXTENDED", "ALREADY_OPEN", "NOT_READY", "READY", "OTHER")


def prophet_state_for(entry_status: str | None) -> str:
    """Display-only Prophet echo mapping (contract §5 Prophet mapping table).

    Never blank: missing -> UNAVAILABLE; unmapped-but-lawful -> OTHER. This function
    has zero effect on any score — callers must never feed its output into R/M_ad/
    evidence_strength/evidence_confidence (test 21). Single-domain (plans[].entry_status
    only) — kept for callers that only ever had that one field; the two-domain B4
    resolution lives in :func:`prophet_state_combined`.
    """
    if entry_status is None:
        return "UNAVAILABLE"
    mapped = _PROPHET_MAP.get(entry_status)
    if mapped is not None:
        return mapped
    return "OTHER"


def prophet_plan_state(entry_status: str | None, lifecycle_state: str | None, closed: bool,
                        *, has_plan: bool) -> str | None:
    """plans[] domain mapping only (B4). ``None`` means "this domain has nothing lawful
    to say" (no plan record at all) — distinct from ``"OTHER"``, which means a plan
    record exists but maps to no more specific state. Never called for a symbol with no
    plan record: callers pass ``has_plan = symbol in <plans-domain dict>``.

    ``hold``/``partial`` only resolve to ALREADY_OPEN while the plan is still OPEN
    (``closed`` False) — contract ruling: "open plan with entry_status hold/partial".
    A ``None`` entry_status resolves to ALREADY_OPEN only for an open ``entered`` plan
    ("open entered plan with entry_status None"); any other None-status plan is a lawful
    but unmapped record -> OTHER. ``extended``/``topping``/``bounce_wait``/``buy_now``
    resolve unconditionally (unchanged from :func:`prophet_state_for`) — the contract's
    open-condition is stated only for the hold/partial and None-status cases.
    """
    if not has_plan:
        return None
    if entry_status is None:
        if lifecycle_state == "entered" and not closed:
            return "ALREADY_OPEN"
        return "OTHER"
    mapped = _PROPHET_MAP.get(entry_status)
    if mapped == "ALREADY_OPEN":
        return mapped if not closed else "OTHER"
    if mapped is not None:
        return mapped
    return "OTHER"


def prophet_group_state(reason: str | None) -> str | None:
    """intake.receipts.groups domain mapping only (B4). ``None`` when the symbol carries
    no group-reason record at all (never called otherwise — see ``has_group`` at the
    call site); an unmapped-but-present reason is a lawful bucket -> OTHER."""
    if reason is None:
        return None
    return _PROPHET_GROUP_MAP.get(reason, "OTHER")


def prophet_state_combined(plan_state: str | None, group_state: str | None) -> str:
    """B4 per-symbol precedence across the two Prophet domains: EXTENDED >
    ALREADY_OPEN > NOT_READY > READY > OTHER > UNAVAILABLE. Absent from both domains
    -> UNAVAILABLE (never blank, contract §5)."""
    candidates = [s for s in (plan_state, group_state) if s is not None]
    if not candidates:
        return "UNAVAILABLE"
    for rank in _PROPHET_STATE_PRECEDENCE:
        if rank in candidates:
            return rank
    return "OTHER"  # unreachable under the closed vocabulary above; safe fallback


def confidence_band(ec: float) -> str:
    if ec < CONFIG["CONF_BAND_TENTATIVE_MAX"]:
        return "tentative"
    if ec < CONFIG["CONF_BAND_MODERATE_MAX"]:
        return "moderate"
    return "firm"


# ─────────────────────────────────────────────────────────────────────────────
# §4 Feature families — per-session raw metrics from ONE chain snapshot.
# ─────────────────────────────────────────────────────────────────────────────

_DTE_BUCKET_EDGES = [-1.0, 7.0, 30.0, 90.0, 1e9]
_DTE_BUCKET_LABELS = ["d7", "d30", "d90", "far"]
_MONEY_BUCKET_EDGES = [0.0, 0.95, 1.05, np.inf]
_MONEY_BUCKET_LABELS = ["dn", "at", "up"]


def _atm_iv(day: pd.DataFrame, spot: float, lo_dte: float, hi_dte: float,
            *, band: float = CONFIG["ATM_BAND"], n: int = CONFIG["ATM_N_CONTRACTS"]) -> float | None:
    dte = day["T"].astype("float64") * 365.0
    mask = dte.between(lo_dte, hi_dte) & day["iv"].notna() & ((day["K"] / spot - 1).abs() <= band)
    m = day[mask]
    if m.empty:
        return None
    dist = (m["K"] / spot - 1).abs()
    nearest = m.assign(_dist=dist).nsmallest(n, "_dist")
    val = float(nearest["iv"].mean())
    return val if math.isfinite(val) else None


def _skew(day: pd.DataFrame, spot: float, atm_iv_7_60: float | None,
          *, lo_dte: float = 7, hi_dte: float = 60) -> float | None:
    if not _finite(atm_iv_7_60) or atm_iv_7_60 == 0:
        return None
    dte = day["T"].astype("float64") * 365.0
    sk = day[day["iv"].notna() & day["delta"].notna() & dte.between(lo_dte, hi_dte)]
    put_lo, put_hi = CONFIG["SKEW_PUT_DELTA"]
    call_lo, call_hi = CONFIG["SKEW_CALL_DELTA"]
    puts = sk[(~sk["is_call"]) & sk["delta"].between(put_lo, put_hi)]
    calls = sk[(sk["is_call"]) & sk["delta"].between(call_lo, call_hi)]
    if puts.empty or calls.empty:
        return None
    pu, ca = float(puts["iv"].mean()), float(calls["iv"].mean())
    if not (math.isfinite(pu) and math.isfinite(ca)):
        return None
    return (pu - ca) / atm_iv_7_60


def quotable_mask(day: pd.DataFrame) -> pd.Series:
    """§3 MIN_CONTRACTS gate: iv notna AND oi+volume > 0 (test 5 quote-quality)."""
    return day["iv"].notna() & ((day["oi"].fillna(0) + day["volume"].fillna(0)) > 0)


#: Standard OCC-style Polygon contract ticker: ``O:{ROOT}{YYMMDD}{C|P}{8-digit strike}``.
#: A vendor ticker whose OCC root carries a trailing digit/suffix that does not equal the
#: chain's own ``underlying`` (e.g. ``O:PANW1261218C00280000`` on underlying ``PANW`` —
#: verified present in the committed store, 595/185,072 rows on 2026-08-13, ~0.3%) marks
#: an ADJUSTED/nonstandard-deliverable contract (AD0 §6.1: no dedicated contract-identity
#: plane exists yet; this is the named, tested exclusion that adjudication requires in its
#: place — "must treat adjusted/nonstandard contracts as a named exclusion with a test,
#: and must not silently aggregate across them", tests 1/2).
_STANDARD_TICKER_RE = r"^O:([A-Za-z.]+)(\d{6})[CP]\d{8}$"


def contract_identity_split(day: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """(standard-contract rows, count of adjusted/nonstandard rows excluded)."""
    if day is None or len(day) == 0:
        return day, 0
    root = day["strike_ticker"].astype(str).str.extract(_STANDARD_TICKER_RE, expand=True)[0]
    ok = root.notna() & (root == day["underlying"].astype(str))
    return day[ok], int((~ok).sum())


def session_metrics(day: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Per-underlying raw metrics for ONE session's chain frame.

    Pure function of one already-loaded DataFrame (production dtypes: ``underlying``
    category, ``expiry`` datetime64, ``K``/``T``/``iv``/``delta``/``oi``/``volume``/
    ``spot`` float32, ``is_call`` bool). No knowledge of any other session. Adjusted/
    nonstandard vendor contracts are excluded first (test 1/2) — never silently
    aggregated into any feature family.
    """
    return session_metrics_and_exclusions(day)[0]


def session_metrics_and_exclusions(day: pd.DataFrame) -> tuple[dict[str, dict[str, Any]], int]:
    """:func:`session_metrics` plus the adjusted/nonstandard-contract exclusion count."""
    out: dict[str, dict[str, Any]] = {}
    if day is None or len(day) == 0:
        return out, 0
    day, excluded = contract_identity_split(day)
    for name, grp in day.groupby("underlying", observed=True):
        if grp.empty:
            continue
        spot = float(grp["spot"].iloc[0])
        if not math.isfinite(spot) or spot <= 0:
            continue
        dte = grp["T"].astype("float64") * 365.0
        aiv = _atm_iv(grp, spot, *CONFIG["ATM_DTE"])
        aiv_front = _atm_iv(grp, spot, *CONFIG["TERM_FRONT_DTE"])
        aiv_back = _atm_iv(grp, spot, *CONFIG["TERM_BACK_DTE"])
        term = ((aiv_front - aiv_back) / aiv_back
                if (_finite(aiv_front) and _finite(aiv_back) and aiv_back != 0) else None)
        skew = _skew(grp, spot, aiv)
        quot = grp[quotable_mask(grp)]
        money = pd.cut(grp["K"].astype("float64") / spot, _MONEY_BUCKET_EDGES,
                        labels=_MONEY_BUCKET_LABELS)
        dtb = pd.cut(dte, _DTE_BUCKET_EDGES, labels=_DTE_BUCKET_LABELS)
        vb = grp.groupby([money, dtb], observed=True)["volume"].sum(min_count=1)
        vol_tot = float(grp["volume"].fillna(0).sum())
        sd = grp[dte <= CONFIG["SD_DTE"]]
        sd_share = float(sd["volume"].fillna(0).sum() / vol_tot) if vol_tot > 0 else None
        out[str(name)] = {
            "spot": spot,
            "n_quot": int(len(quot)),
            "n_total": int(len(grp)),
            "atm_iv": aiv,
            "term": term,
            "skew": skew,
            "vol_tot": vol_tot,
            "sd_share": sd_share,
            "vb": {f"{a}|{b}": float(v) for (a, b), v in vb.items() if math.isfinite(v)},
        }
    return out, excluded


def doi_lean(chain_settled: pd.DataFrame, chain_next: pd.DataFrame,
             next_session: str) -> dict[str, float]:
    """Contract-matched ΔOI lean ``r`` per symbol for the lawful ``(settled, next)`` pair.

    ``r = (call ΔOI − put ΔOI) / (call ΔOI + put ΔOI + ε)``, per-contract ΔOI floored
    at 0 ("positive ΔOI on each side", contract §4), joined on ``strike_ticker``,
    restricted to ``expiry > next_session`` (contracts still alive past the OI print).
    This is the settled-pair OI computation — ``chain_settled`` supplies the PRIOR OI
    baseline, ``chain_next``'s own ``oi`` column is the lawful settled count (test 4/25:
    a session's own same-day OI column is never itself the settled OI for that session).
    """
    if chain_settled is None or chain_next is None or len(chain_settled) == 0 or len(chain_next) == 0:
        return {}
    chain_settled, _ = contract_identity_split(chain_settled)
    chain_next, _ = contract_identity_split(chain_next)
    m = chain_next[["underlying", "strike_ticker", "expiry", "is_call", "oi"]].merge(
        chain_settled[["strike_ticker", "oi"]], on="strike_ticker", suffixes=("", "_prev"),
    )
    m = m[m["expiry"] > pd.Timestamp(next_session)]
    if m.empty:
        return {}
    d = (m["oi"].fillna(0) - m["oi_prev"].fillna(0)).clip(lower=0)
    m = m.assign(_d=d)
    agg = m.groupby(["underlying", "is_call"], observed=True)["_d"].sum().unstack(fill_value=0.0)
    out: dict[str, float] = {}
    for name, row in agg.iterrows():
        c = float(row.get(True, 0.0))
        p = float(row.get(False, 0.0))
        out[str(name)] = (c - p) / (c + p + 1e-9)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# §5.3 tiers, salience, Q-legs, family scores, C family.
# ─────────────────────────────────────────────────────────────────────────────


def liquidity_tiers(mean_volume_by_symbol: Mapping[str, float]) -> dict[str, str]:
    """Cross-sectional quintiles of trailing mean total contract volume (§5.3).

    T1 = top 20%, T2 = next 40%, T3 = rest. Symbols with a non-finite mean are T3
    (never crash the tier assignment; they simply carry the lowest actionability
    multiplier, which is the conservative direction).
    """
    vals = {k: v for k, v in mean_volume_by_symbol.items() if _finite(v)}
    if not vals:
        return {k: "T3" for k in mean_volume_by_symbol}
    s = pd.Series(vals)
    q80, q40 = s.quantile(0.8), s.quantile(0.4)
    out: dict[str, str] = {}
    for k, v in mean_volume_by_symbol.items():
        if k not in vals:
            out[k] = "T3"
        elif v >= q80:
            out[k] = "T1"
        elif v >= q40:
            out[k] = "T2"
        else:
            out[k] = "T3"
    return out


def d_salience(d1: float | None, d3: float | None,
               *, w1: float = CONFIG["SALIENCE_W_D1"], w3: float = CONFIG["SALIENCE_W_D3"]) -> float | None:
    """``D_salience = clamp01(0.65*d1 + 0.35*d3)``, renormalised over present members.

    UNSIGNED — this function may raise research priority but structurally cannot carry
    direction: it returns a bare float in [0,1], never a sign (test 17a/b).
    """
    parts, wts = [], []
    if d1 is not None:
        parts.append(w1 * d1)
        wts.append(w1)
    if d3 is not None:
        parts.append(w3 * d3)
        wts.append(w3)
    if not parts:
        return None
    return clamp01(sum(parts) / sum(wts))


def q_oi(today_r: float | None, history_r: Sequence[float | None],
         *, floor: int = CONFIG["DOI_FLOOR"]) -> float | None:
    """``Q_oi = d2`` — robust z of today's ΔOI lean vs its own history, clamp ±3 -> /3.

    Unsigned positioning HYPOTHESIS (contract §4/§5.3): never "observed buying/selling".
    """
    hist = [h for h in history_r if _finite(h)]
    if not _finite(today_r) or len(hist) < floor:
        return None
    return clamped_z_over_3(today_r, hist, sign=1.0)


def q_skew(today_delta_skew: float | None, history_delta_skew: Sequence[float | None],
           *, floor: int = CONFIG["SKEW_CHANGE_FLOOR"], window: int = CONFIG["LOOKBACK"]) -> float | None:
    """``Q_skew`` — robust z of skew CHANGE (never level), floor 8, sign flipped.

    Positive = downside skew flattened unusually (upside-evidence hypothesis).
    """
    hist = [h for h in history_delta_skew if _finite(h)][-window:]
    if not _finite(today_delta_skew) or len(hist) < floor:
        return None
    return clamped_z_over_3(today_delta_skew, hist, sign=-1.0)


def classify_direction(q_oi_v: float | None, q_skew_v: float | None, d_sal: float | None,
                        *, q_th: float = CONFIG["Q_TH"], sal_th: float = CONFIG["SALIENCE_TH"]) -> str | None:
    """Direction qualification law (contract §5.3, binding, frozen thresholds).

    ``LONG  = Q_oi >= +q_th AND Q_skew >= +q_th AND D_salience >= sal_th``
    ``SHORT = Q_oi <= -q_th AND Q_skew <= -q_th AND D_salience >= sal_th``
    Returns None (no machine direction) otherwise — including when only one leg is
    present, when the legs disagree in sign, or when salience is below the gate. No
    other quantity (d1, d3, GEX, raw volume, 0DTE share, event premium, …) may ever
    enter this function — that is the zero-authority list (test 17, test 18).
    """
    if q_oi_v is None or q_skew_v is None or d_sal is None:
        return None
    if d_sal < sal_th:
        return None
    if q_oi_v >= q_th and q_skew_v >= q_th:
        return "LONG"
    if q_oi_v <= -q_th and q_skew_v <= -q_th:
        return "SHORT"
    return None


def fallback_route(f_v: float | None, f_e: float | None, c_fire: bool,
                    *, vol_th: float = CONFIG["VOL_STATE_TH"],
                    event_th: float = CONFIG["EVENT_STATE_TH"]) -> str:
    """VOLATILITY / RISK_ONLY / NEUTRAL fallback when direction qualification fails."""
    if (f_v is not None and abs(f_v) >= vol_th) or (f_e is not None and abs(f_e) >= event_th):
        return "VOLATILITY"
    if c_fire:
        return "RISK_ONLY"
    return "NEUTRAL"


def evidence_strength(direction: str, *, q_oi_v: float | None = None, q_skew_v: float | None = None,
                       d_sal: float | None = None, f_v: float | None = None, f_e: float | None = None,
                       c_sev: float = 0.0,
                       w_dir: float = CONFIG["ES_W_DIR"], w_sal: float = CONFIG["ES_W_SAL"]) -> float:
    if direction in ("LONG", "SHORT"):
        dir_strength = float(np.mean([abs(q_oi_v), abs(q_skew_v)]))
        return clamp01(w_dir * dir_strength + w_sal * (d_sal or 0.0))
    if direction == "VOLATILITY":
        if f_e is not None:
            return clamp01(abs(f_e))
        return clamp01(abs(f_v) if f_v is not None else 0.0)
    if direction == "RISK_ONLY":
        return clamp01(c_sev)
    return 0.0


def evidence_confidence(direction: str, *, d3: float | None, coverage_complete: bool,
                         base: float = CONFIG["CONF_BASE"], persist_bonus: float = CONFIG["CONF_PERSIST_BONUS"],
                         coverage_bonus: float = CONFIG["CONF_COVERAGE_BONUS"],
                         ceil_dir: float = CONFIG["CONF_CEIL_DIRECTIONAL"], ceil: float = CONFIG["CONF_CEIL"]) -> float:
    ec = base + (persist_bonus if (d3 or 0.0) >= 0.5 else 0.0) + (coverage_bonus if coverage_complete else 0.0)
    cap = ceil_dir if direction in ("LONG", "SHORT") else ceil
    return min(ec, cap)


def m_gex_multiplier(direction: str, gex_verdict: str | None,
                      *, mult: float = CONFIG["M_GEX_CAUTION_LONG"]) -> float:
    """Only lawful GEX effect: qualified LONG + verdict=='caution' -> 0.75. Never SHORT,
    never a positive multiplier, never a synthetic SHORT inverse (test 18)."""
    if direction == "LONG" and gex_verdict == "caution":
        return mult
    return 1.0


def actionability(*, tier: str, direction: str, fresh_ok: bool, event_imminent: bool,
                   c_fire: bool, gex_verdict: str | None,
                   tier_mult: Mapping[str, float] = CONFIG["TIER_MULT"],
                   fresh_penalty: float = CONFIG["FRESH_PENALTY"],
                   event_mult: float = CONFIG["EVENT_CONTAM_MULT"],
                   crowd_mult: float = CONFIG["CROWD_MULT_LONG"]) -> float:
    m = tier_mult.get(tier, tier_mult["T3"])
    m *= 1.0 if fresh_ok else fresh_penalty
    if event_imminent and direction in ("LONG", "SHORT"):
        m *= event_mult
    if c_fire and direction == "LONG":
        m *= crowd_mult
    m *= m_gex_multiplier(direction, gex_verdict)
    return m


def research_priority(evid_strength: float, evid_confidence: float, m_ad: float) -> int:
    return int(round(1000.0 * evid_strength * evid_confidence * m_ad))


def crowd_family(c1: float | None, c2: int, c3: int,
                  *, c1_th: float = CONFIG["C1_TH"]) -> tuple[bool, float]:
    """C family: fires iff c1>=0.90 or c2 or c3. Severity = max of the FIRED members'
    own scores (never an unfired member — contract §5.3 'Severity = max(fired inputs)')."""
    fired = []
    if c1 is not None and c1 >= c1_th:
        fired.append(c1)
    if c2:
        fired.append(1.0)
    if c3:
        fired.append(1.0)
    return (len(fired) > 0), (max(fired) if fired else 0.0)


def crowd_fired_legs(c1: float | None, c2: int, c3: int,
                      *, c1_th: float = CONFIG["C1_TH"]) -> list[str]:
    """Which C-family legs actually fired (B3 freshness needs to know WHICH, not just
    THAT — c1/c2/c3 carry different evidence lives). Shares the exact firing predicate
    with :func:`crowd_family` (kept as two functions rather than widening that one's
    return type, since ``crowd_family`` is the older, already-covered severity API)."""
    return [k for k, v in (("c1", c1 is not None and c1 >= c1_th), ("c2", bool(c2)), ("c3", bool(c3))) if v]


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic closed-vocabulary copy: why_now / trigger / invalidation.
# Every string here is a template filled with numbers — no LLM, ever.
# ─────────────────────────────────────────────────────────────────────────────


def why_now_strings(direction: str, *, q_oi_v: float | None = None, q_skew_v: float | None = None,
                     d_sal: float | None = None, f_v: float | None = None, f_e: float | None = None,
                     c_sev: float | None = None) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    if direction in ("LONG", "SHORT"):
        tilt_en = "call" if (q_oi_v or 0) >= 0 else "put"
        tilt_zh = "看涨" if (q_oi_v or 0) >= 0 else "看跌"
        out.append({
            "en": f"Open interest grew mostly on the {tilt_en} side",
            "zh": f"未平仓量增长主要集中在{tilt_zh}一侧",
        })
        skew_word_en = "flattened" if (q_skew_v or 0) >= 0 else "steepened"
        skew_word_zh = "走平" if (q_skew_v or 0) >= 0 else "走陡"
        out.append({
            "en": f"Downside skew {skew_word_en} unusually",
            "zh": f"下行偏度异常{skew_word_zh}",
        })
        out.append({
            "en": "Activity far above its normal range",
            "zh": "活跃度远高于正常区间",
        })
    elif direction == "VOLATILITY":
        if f_e is not None:
            ep_word_en = "high" if f_e >= 0 else "low"
            ep_word_zh = "偏高" if f_e >= 0 else "偏低"
            out.append({
                "en": f"Event premium {ep_word_en} versus current event peers",
                "zh": f"事件溢价相对当前事件同类{ep_word_zh}",
            })
        if f_v is not None:
            out.append({
                "en": "Volatility evidence far outside its normal range",
                "zh": "波动率证据远超正常区间",
            })
    elif direction == "RISK_ONLY":
        out.append({
            "en": "Crowding or mechanical risk is active",
            "zh": "拥挤或机制性风险处于活跃状态",
        })
    return out


def trigger_watch_string(direction: str) -> dict[str, str]:
    if direction in ("LONG", "SHORT"):
        return {"en": "Q_oi and Q_skew remain same-sign with |each| >= 0.50 on the next settled session",
                "zh": "下一结算交易日 Q_oi 与 Q_skew 保持同向，且绝对值均 >= 0.50"}
    if direction == "VOLATILITY":
        return {"en": "Volatility/event-premium extremity persists or expands",
                "zh": "波动率/事件溢价极端度持续或扩大"}
    if direction == "RISK_ONLY":
        return {"en": "The named crowding/mechanics condition remains active",
                "zh": "所标注的拥挤/机制状态持续存在"}
    return {"en": "No qualifying condition", "zh": "无符合条件的状态"}


def invalidation_watch_string(direction: str) -> dict[str, str]:
    if direction in ("LONG", "SHORT"):
        return {"en": "Sign agreement is lost, or |Q_oi| < 0.25, or |Q_skew| < 0.25, "
                      "or a required source becomes stale or degraded",
                "zh": "方向一致性消失，或 |Q_oi| < 0.25，或 |Q_skew| < 0.25，或所需数据源变得陈旧/降级"}
    if direction == "VOLATILITY":
        return {"en": "Extremity falls below the card's threshold",
                "zh": "极端度跌破该卡片的门槛"}
    if direction == "RISK_ONLY":
        return {"en": "The named condition clears",
                "zh": "所标注的状态解除"}
    return {"en": "N/A", "zh": "不适用"}


def horizon_for(direction: str, *, event_board: bool = False, zero_dte: bool = False) -> str:
    if direction in ("LONG", "SHORT"):
        return "next_5_sessions"
    if direction == "VOLATILITY":
        return "through_event_close" if event_board else "next_5_sessions"
    if direction == "RISK_ONLY":
        return "next_session"
    return "next_session"


def signal_id_for(as_of_session: str, symbol: str) -> str:
    return f"adib:v1.2:{as_of_session}:{symbol}"


def _crowd_leg_life(leg: str, *, lives: Mapping[str, Any]) -> int:
    """Evidence life (NYSE sessions) of ONE fired crowd leg (B3 ruling): c1 is the
    same-day/0DTE family (life 0, ``C_0DTE``); c2 derives from V (IV percentile) AND
    spot-history, both life 5 -> 5; c3 derives from D_salience (life 3) AND V (life 5)
    -> min(3, 5) = 3."""
    if leg == "c1":
        return int(lives["C_0DTE"])
    if leg == "c2":
        return int(lives["V"])
    if leg == "c3":
        return min(int(lives["D_salience"]), int(lives["V"]))
    raise ValueError(f"unknown crowd leg {leg!r}")


def fresh_until_for(*, direction: str, S: str, session_n_forward_fn,
                     gex_active: bool = False, crowd_fired_legs: Sequence[str] = (),
                     f_e_active: bool = False, event_date: str | None = None,
                     d3_bonus_applied: bool = False,
                     lives: Mapping[str, Any] = CONFIG["FRESH_LIVES_SESSIONS"]) -> str:
    """B3 evidence-derived freshness (Fable's binding rulings, transcribed exactly):
    ``fresh_until`` = the minimum lawful expiry over the card's ACTUAL contribution
    set — every evidence input that entered ``state`` (direction/route classification),
    ``evidence_strength``, ``evidence_confidence``, or ``M_ad``. Never derived from the
    card's DIRECTION alone (the pre-B3 defect this replaces).

    Session-count lives are converted to real NYSE-session dates via
    ``session_n_forward_fn`` (injected, same pattern as the rest of this pure module —
    see the module docstring); the E-family life is an actual calendar date (event
    close) rather than a session count, so it is combined with everything else via a
    plain ``min()`` over ISO date strings (lexicographic order == chronological order
    for ``YYYY-MM-DD``).

    * LONG/SHORT: Q_oi(3) + Q_skew(3) + D_salience(3) always (the direction-qualification
      law requires all three present) ``+`` P/GEX-mechanics(1) when ``M_gex != 1.0``
      (a qualified LONG under caution) ``+`` the fired crowd leg's own life when a crowd
      multiplier cut this LONG's actionability (same-day c1 -> 0; c2 -> 5; c3 -> 3).
    * VOLATILITY: event-driven (F_E contributed, i.e. ``f_e_active``) -> the event-close
      date alone, UNLESS the confidence d3 persist-bonus also applied (D_salience(3)
      contributed to evidence_confidence), in which case the min of the two; V-driven
      non-event VOLATILITY (F_V used instead) -> V(5), again refined by the d3 bonus.
    * RISK_ONLY (always crowd-fired by construction — ``fallback_route`` only routes
      here when ``c_fire``): the fired leg's own life, refined by the d3 bonus.
    * Anything else (NEUTRAL): life 0 -> fresh_until == S (no lawful positive claim to
      extend past the current session).

    The d3 confidence bonus is itself salience evidence (life 3, contract ruling) and
    is folded in for every direction — for LONG/SHORT this is a no-op (D_salience(3) is
    already unconditionally in the set), which is why the ruling only calls it out
    explicitly for VOLATILITY/RISK_ONLY.
    """
    session_lives: list[int] = []
    if direction in ("LONG", "SHORT"):
        session_lives += [int(lives["Q_oi"]), int(lives["Q_skew"]), int(lives["D_salience"])]
        if gex_active:
            session_lives.append(int(lives["P"]))
        if crowd_fired_legs:
            session_lives.append(min(_crowd_leg_life(leg, lives=lives) for leg in crowd_fired_legs))
    elif direction == "VOLATILITY":
        if not f_e_active:
            session_lives.append(int(lives["V"]))
        if d3_bonus_applied:
            session_lives.append(int(lives["D_salience"]))
    elif direction == "RISK_ONLY":
        if crowd_fired_legs:
            session_lives.append(min(_crowd_leg_life(leg, lives=lives) for leg in crowd_fired_legs))
        if d3_bonus_applied:
            session_lives.append(int(lives["D_salience"]))
    else:
        session_lives.append(0)

    candidates: list[str] = []
    if session_lives:
        candidates.append(session_n_forward_fn(S, min(session_lives)))
    if direction == "VOLATILITY" and f_e_active and event_date:
        candidates.append(event_date)
    if not candidates:
        candidates.append(S)
    return min(candidates)


def market_implied_move_pct(atm_iv: float | None, *, horizon_sessions: float | None = None,
                             event_horizon_sessions: float | None = None) -> float | None:
    if not _finite(atm_iv):
        return None
    if event_horizon_sessions is not None:
        return float(atm_iv * math.sqrt(max(event_horizon_sessions, 0.0) / 252.0))
    if horizon_sessions is not None:
        return float(atm_iv * math.sqrt(max(horizon_sessions, 0.0) / 252.0))
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Board composition (pure — operates on a list of already-scored card dicts).
# ─────────────────────────────────────────────────────────────────────────────


def compose_opportunities(cards: Sequence[Mapping[str, Any]],
                           *, r_min: int = CONFIG["R_MIN"], cap: int = CONFIG["BOARD_N"]) -> tuple[list[dict], int]:
    elig = [c for c in cards if c["direction"] in ("LONG", "SHORT", "VOLATILITY") and c["research_priority_score"] >= r_min]
    elig.sort(key=lambda c: (-c["research_priority_score"], -c["evidence_confidence"], -c.get("tier_metric", 0.0), c["symbol"]))
    return list(elig[:cap]), max(0, len(elig) - cap)


def compose_event_board(event_cards: Sequence[Mapping[str, Any]], *, cap: int = CONFIG["EVENT_BOARD_N"]) -> list[dict]:
    ordered = sorted(event_cards, key=lambda c: (-abs(c.get("f_e") or 0.0), c["symbol"]))
    return list(ordered[:cap])


def compose_risk_board(risk_cards: Sequence[Mapping[str, Any]], *, cap: int = CONFIG["RISK_BOARD_N"]) -> list[dict]:
    ordered = sorted(risk_cards, key=lambda c: (-c.get("evidence_strength", 0.0), c["symbol"]))
    return list(ordered[:cap])


def no_signal_exemplar(cards: Sequence[Mapping[str, Any]]) -> dict | None:
    """Highest-tier-metric eligible coverage-complete name with R < NO_SIGNAL_R."""
    cands = [c for c in cards if c.get("board_state_symbol") == "NO_SIGNAL" and c.get("coverage_complete")]
    if not cands:
        return None
    cands.sort(key=lambda c: (-c.get("tier_metric", 0.0), c["symbol"]))
    return cands[0]


# ─────────────────────────────────────────────────────────────────────────────
# Eligibility.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Eligibility:
    present: int = 0
    eligible: int = 0
    insufficient_history: int = 0
    insufficient_coverage: int = 0
    # B2 — the board-level SOURCE_COVERAGE_GATE denominator/ratio (distinct from the
    # per-name `ratio` property below, which feeds the SEPARATE ELIGIBILITY_GATE).
    # None when undecidable (no chain loaded yet, e.g. MIXED_VINTAGE).
    universe_count: int | None = None
    source_coverage_pct: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "present": self.present, "eligible": self.eligible,
            "insufficient_history": self.insufficient_history,
            "insufficient_coverage": self.insufficient_coverage,
            "universe_count": self.universe_count,
            "source_coverage_pct": (round(self.source_coverage_pct, 4)
                                     if self.source_coverage_pct is not None else None),
        }

    @property
    def ratio(self) -> float | None:
        return None if self.present == 0 else self.eligible / self.present


def eligibility_reason(n_quot: int, h: int,
                        *, min_contracts: int = CONFIG["MIN_CONTRACTS"],
                        min_history: int = CONFIG["MIN_HISTORY"]) -> str | None:
    """None (eligible), 'INSUFFICIENT_COVERAGE', or 'INSUFFICIENT_HISTORY'.

    Coverage checked first: a name failing BOTH is reported as INSUFFICIENT_COVERAGE
    (a per-name contract/quality failure), distinct from a name with enough contracts
    but too little session depth (test 16).
    """
    if n_quot < min_contracts:
        return "INSUFFICIENT_COVERAGE"
    if h < min_history:
        return "INSUFFICIENT_HISTORY"
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Settled-pair session selection (contract §1 — pure calendar/set arithmetic; the
# producer supplies the NYSE-session predicate so this file has zero calendar
# dependency of its own — see ``scripts/build_options_intel_brief.py`` header).
# ─────────────────────────────────────────────────────────────────────────────


def select_settled_pair(committed_sessions: Sequence[str],
                         next_session_fn) -> tuple[str | None, str | None, str | None]:
    """Newest lawful consecutive ``(S, D)`` pair, walking backward on a gap (test 23/26).

    ``committed_sessions`` — ascending session-date strings ("YYYY-MM-DD") for every
    chain snapshot actually on disk. ``next_session_fn(date_str) -> date_str`` is the
    repo's NYSE-session arithmetic (``lib.nyse_calendar.session_n_forward(d, 1)``,
    injected so this module never imports a calendar itself).

    Returns ``(S, D, pending_session)``:
      * ``S``/``D`` — the newest pair with ``D == next_session_fn(S)`` AND both present
        in ``committed_sessions``; ``(None, None)`` if no such pair exists at all
        (MIXED_VINTAGE — test 26/§1).
      * ``pending_session`` — the newest committed session strictly after ``D`` that
        itself lacks its own lawful next-session print, OR ``D`` itself when nothing
        newer than ``D`` has yet printed its own settlement (test 27). ``None`` when
        the newest committed session IS the chosen ``D`` and a session strictly after
        it also exists with its own OI print already settled (i.e. nothing is pending).
    """
    sessions = sorted(set(committed_sessions))
    if len(sessions) < 2:
        return None, None, (sessions[-1] if sessions else None)
    S = D = None
    for i in range(len(sessions) - 1, 0, -1):
        a, b = sessions[i - 1], sessions[i]
        if next_session_fn(a) == b:
            S, D = a, b
            break
    if S is None:
        return None, None, sessions[-1]
    # Pending: the newest committed session > D that has no lawful next print among
    # committed_sessions (this is always true for D itself when D is the newest file —
    # D's own settlement, next_session_fn(D), has not printed yet).
    newer = [s for s in sessions if s > D]
    if newer:
        newest = newer[-1]
        pending = newest if next_session_fn(newest) not in sessions else None
    else:
        pending = D if next_session_fn(D) not in sessions else None
    return S, D, pending


# ─────────────────────────────────────────────────────────────────────────────
# Top-level orchestration. Pure: every argument is already-materialised in-memory
# data (frames, dicts, scalars). The producer does 100% of the file I/O and hands
# this function fully-loaded inputs; this function does 100% of the scoring math.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class SessionPanel:
    """Fully materialised inputs for one build. Everything the engine needs to score
    session ``as_of_session``; the producer assembles this by reading files."""
    as_of_session: str
    oi_counted_date: str
    pending_session: str | None
    pending_reason: str | None
    chains_by_session: dict[str, pd.DataFrame]          # session -> chain frame, keys <= as_of_session
    chain_next: pd.DataFrame | None                      # the oi_counted_date frame (D), OI-only use
    lawful_pairs: dict[str, str]                         # settled_session -> next_session, every lawful
                                                          # consecutive pair found in chains_by_session ∪ {D}
    summary_spot: dict[str, list[float]] = field(default_factory=dict)   # symbol -> ascending spot history <= S
    gex_verdict: dict[str, str | None] = field(default_factory=dict)     # symbol -> confirm/neutral/caution/None
    gex_bound_to_S: bool = True                          # False -> every gex_verdict treated as absent (mixed vintage)
    event_date: dict[str, str | None] = field(default_factory=dict)      # symbol -> next earnings date or None
    events_loaded: bool = True
    # Prophet — TWO domains (B4): plans[] (entry_status/lifecycle_state/closed) and
    # intake.receipts.groups (bucket `reason`). `prophet_entry_status`/`prophet_lifecycle_
    # state`/`prophet_plan_closed` are keyed by symbols WITH a plans[] record (a symbol's
    # presence as a dict KEY, even with a None entry_status, is itself meaningful — see
    # `prophet_plan_state`'s `has_plan` parameter). `prophet_group_reason` is keyed by
    # symbols the intake receipts placed in a bucket.
    prophet_entry_status: dict[str, str | None] = field(default_factory=dict)
    prophet_lifecycle_state: dict[str, str | None] = field(default_factory=dict)
    prophet_plan_closed: dict[str, bool] = field(default_factory=dict)
    prophet_group_reason: dict[str, str | None] = field(default_factory=dict)
    prophet_asof: str | None = None
    signing_gate_direction_reliable: bool = False
    signing_gate_asof: str | None = None
    # B2 — the CANONICAL current options universe (engine/options_universe.py::
    # gex_symbols(), producer-resolved). None -> defaults to this session's own present
    # names (ratio 1.0; every pre-B2 test panel that never supplies a universe keeps
    # passing), and is itself NOT a historical-max heuristic — it depends on nothing but
    # the CURRENT session's own chain, never on any other loaded session.
    universe: Sequence[str] | None = None
    stale: bool = False                                  # producer's wall-clock freshness verdict


def _session_key_for(session: str, all_sessions: Sequence[str]) -> str | None:
    idx = list(all_sessions).index(session) if session in all_sessions else None
    return None if idx in (None, 0) else all_sessions[idx - 1]


def build_intel_brief(panel: SessionPanel, *, source_watermarks: Mapping[str, Any],
                       input_receipts: Sequence[Mapping[str, Any]], built_at_utc: str,
                       sessions_apart_fn, session_n_forward_fn,
                       source_manifest: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Assemble the full ``options.intel_brief/v1`` payload for ``panel``.

    ``sessions_apart_fn(a, b) -> int|None`` and ``session_n_forward_fn(d, n) -> str``
    are the injected NYSE-session primitives (``lib.nyse_calendar.sessions_apart`` /
    ``session_n_forward``) — see the module docstring for why this file never imports
    a calendar module directly (keeps it a function of its inputs alone, testable with
    a tiny hand-rolled calendar in ``tests/``).

    ``source_manifest`` (B1) — the producer's already-computed {gex_summary, gex_confirm}
    per-file sha256 manifest (path -> hash, member_count, merkle-style aggregate root).
    This function does zero hashing of its own (no file I/O anywhere in this module);
    it only packages the manifest into the payload verbatim. The two aggregate roots
    are NOT re-derived here — the producer folds them into ``input_receipts`` BEFORE
    calling this function, which is what actually binds them into ``receipt_id`` (this
    function's ``receipt_id()`` call already hashes the full ``input_receipts`` list).
    """
    S, D = panel.as_of_session, panel.oi_counted_date
    all_sessions = sorted(panel.chains_by_session.keys())

    # ---- MIXED_VINTAGE short-circuit: no lawful pair at all -----------------------
    if S is None or D is None or S not in panel.chains_by_session:
        return _degraded_payload(
            reason="MIXED_VINTAGE", panel=panel, source_watermarks=source_watermarks,
            input_receipts=input_receipts, built_at_utc=built_at_utc,
            source_manifest=source_manifest,
        )

    chain_S = panel.chains_by_session[S]

    # ---- B2: two SEPARATE gates. Source coverage (board-level: is chain[S] itself a
    # plausible full snapshot of the CANONICAL universe?) vs eligibility (per-name data
    # quality, checked further below) used to share one constant — collapsing two
    # different failure modes into one number. `panel.universe` is the producer-resolved
    # `engine/options_universe.py::gex_symbols()` list; no historical-chain-max fallback
    # anywhere (a session with no override simply asserts 100% of ITS OWN names, never
    # borrowing another session's count).
    present_names = sorted(session_metrics(chain_S).keys())
    universe_list = list(panel.universe) if panel.universe is not None else list(present_names)
    universe_count = len(universe_list)
    source_coverage_pct = ((len(set(present_names) & set(universe_list)) / universe_count)
                            if universe_count > 0 else None)
    if source_coverage_pct is not None and source_coverage_pct < CONFIG["SOURCE_COVERAGE_GATE"]:
        return _insufficient_coverage_payload(
            panel=panel, present=len(present_names), universe_count=universe_count,
            source_coverage_pct=source_coverage_pct, source_watermarks=source_watermarks,
            input_receipts=input_receipts, built_at_utc=built_at_utc,
            source_manifest=source_manifest,
        )

    if panel.stale:
        return _stale_payload(
            panel=panel, source_watermarks=source_watermarks, input_receipts=input_receipts,
            built_at_utc=built_at_utc, universe_count=universe_count,
            source_coverage_pct=source_coverage_pct, source_manifest=source_manifest,
        )

    # ---- per-session metrics for every loaded session (pure, session-local) -------
    _metrics_and_excl = {s: session_metrics_and_exclusions(f) for s, f in panel.chains_by_session.items()}
    metrics_by_session = {s: v[0] for s, v in _metrics_and_excl.items()}
    contract_identity_excluded_S = _metrics_and_excl.get(S, ({}, 0))[1]
    hist_sessions = [s for s in all_sessions if s < S]

    def hist_of(symbol: str, key: str) -> list[float]:
        return [metrics_by_session[s][symbol][key] for s in hist_sessions
                if symbol in metrics_by_session[s] and metrics_by_session[s][symbol].get(key) is not None]

    H = {n: sum(1 for s in hist_sessions if n in metrics_by_session[s]) for n in present_names}

    # ---- liquidity tiers -----------------------------------------------------------
    mean_vol = {}
    for n in present_names:
        window = [metrics_by_session[s][n]["vol_tot"] for s in (hist_sessions + [S])[-CONFIG["LOOKBACK"]:]
                  if n in metrics_by_session.get(s, {})]
        mean_vol[n] = float(np.mean(window)) if window else None
    tiers = liquidity_tiers(mean_vol)

    # ---- contract-matched ΔOI: today's r (S->D) + lawful history series -----------
    doi_today = doi_lean(chain_S, panel.chain_next, D) if panel.chain_next is not None else {}
    doi_history: dict[str, list[float]] = {n: [] for n in present_names}
    for a, b in sorted(panel.lawful_pairs.items()):
        if a >= S:
            continue
        if a not in panel.chains_by_session or b not in panel.chains_by_session:
            continue
        pair_r = doi_lean(panel.chains_by_session[a], panel.chains_by_session[b], b)
        for n, r in pair_r.items():
            doi_history.setdefault(n, []).append(r)

    # ---- skew delta series (same-session-lawful; only calendar-consecutive pairs) -
    skew_delta_today: dict[str, float | None] = {}
    skew_delta_hist: dict[str, list[float]] = {n: [] for n in present_names}
    ordered_all = all_sessions  # ascending, includes S
    for n in present_names:
        prev_session = _session_key_for(S, ordered_all)
        sk_S = metrics_by_session.get(S, {}).get(n, {}).get("skew")
        sk_prev = metrics_by_session.get(prev_session, {}).get(n, {}).get("skew") if prev_session else None
        if sessions_apart_fn(prev_session, S) == 1 if prev_session else False:
            skew_delta_today[n] = ((sk_S - sk_prev) if (_finite(sk_S) and _finite(sk_prev)) else None)
        else:
            skew_delta_today[n] = None
        # history of deltas across calendar-consecutive committed pairs strictly before S
        deltas = []
        for i in range(1, len(hist_sessions)):
            a, b = hist_sessions[i - 1], hist_sessions[i]
            if sessions_apart_fn(a, b) != 1:
                continue
            va = metrics_by_session.get(a, {}).get(n, {}).get("skew")
            vb = metrics_by_session.get(b, {}).get(n, {}).get("skew")
            if _finite(va) and _finite(vb):
                deltas.append(vb - va)
        skew_delta_hist[n] = deltas

    # ---- event window (S, S+45d] --------------------------------------------------
    event_names = set()
    for n, ed in panel.event_date.items():
        if ed is None:
            continue
        try:
            days = (pd.Timestamp(ed) - pd.Timestamp(S)).days
        except Exception:
            continue
        if 0 < days <= CONFIG["EVENT_WINDOW_DAYS"]:
            event_names.add(n)
    event_family_active = panel.events_loaded and len(event_names) >= CONFIG["EVENT_MIN_NAMES"]

    # ---- per-symbol feature assembly -----------------------------------------------
    eligibility = Eligibility(present=len(present_names), universe_count=universe_count,
                               source_coverage_pct=source_coverage_pct)
    cards: list[dict[str, Any]] = []
    xs_today = {k: {n: metrics_by_session[S][n].get(k) for n in present_names} for k in ("term", "sd_share")}
    v1_today: dict[str, float | None] = {n: metrics_by_session[S][n].get("atm_iv") for n in present_names}
    spreads: dict[str, float | None] = {}
    for n in present_names:
        aiv = v1_today.get(n)
        hist_spot = panel.summary_spot.get(n) or []
        window = hist_spot[-(CONFIG["LOOKBACK"] + 1):]
        if aiv is not None and len(window) >= CONFIG["MIN_HISTORY"] + 1:
            logret = np.diff(np.log(np.array(window, dtype=float)))
            if len(logret) >= CONFIG["MIN_HISTORY"] and np.all(np.isfinite(logret)):
                rv = float(np.std(logret) * math.sqrt(252))
                if rv > 0:
                    spreads[n] = (aiv - rv) / rv

    # ---- E family: cross-sectional event-premium read (contract §5.3, v1.2) -------
    # Needs >= EVENT_MIN_NAMES event names with a usable today's ATM IV; F_E is defined
    # ONLY for names in the event window (never a directional signal — event board only).
    f_e_by_symbol: dict[str, float | None] = {}
    p_xs_event_by_symbol: dict[str, float | None] = {}
    if event_family_active:
        event_iv = {n: v1_today.get(n) for n in event_names if v1_today.get(n) is not None}
        for n in event_names:
            if n not in event_iv:
                continue
            p_xs_event = percentile_xs(event_iv, n, floor=CONFIG["EVENT_MIN_NAMES"])
            if p_xs_event is None:
                continue
            p_long_iv = percentile_long(hist_of(n, "atm_iv"), v1_today.get(n))
            val = 0.6 * (2 * p_xs_event - 1) + (0.4 * (2 * p_long_iv - 1) if p_long_iv is not None else 0.0)
            f_e_by_symbol[n] = clamp(val, -1.0, 1.0)
            p_xs_event_by_symbol[n] = p_xs_event

    for n in present_names:
        m = metrics_by_session[S][n]
        reason = eligibility_reason(m["n_quot"], H.get(n, 0))
        if reason == "INSUFFICIENT_COVERAGE":
            eligibility.insufficient_coverage += 1
            continue
        if reason == "INSUFFICIENT_HISTORY":
            eligibility.insufficient_history += 1
            continue
        eligibility.eligible += 1

        # V family
        p_v1 = percentile_long(hist_of(n, "atm_iv"), m.get("atm_iv"))
        p_v2 = percentile_xs(spreads, n) if n in spreads else None
        p_v3 = blend(percentile_xs(xs_today["term"], n), percentile_long(hist_of(n, "term"), m.get("term")))
        v_members = [p for p in (p_v1, p_v2, p_v3) if p is not None]
        f_v = float(np.mean([signed_surprise(p) for p in v_members])) if v_members else None

        # salience d1/d3
        vb_hist: dict[str, list[float]] = {}
        for s in hist_sessions:
            row = metrics_by_session.get(s, {}).get(n)
            if not row:
                continue
            for k, v in row.get("vb", {}).items():
                vb_hist.setdefault(k, []).append(v)
        d1 = None
        for k, tv in m.get("vb", {}).items():
            hv = vb_hist.get(k, [])
            if len(hv) >= CONFIG["MIN_HISTORY"]:
                p = float((np.array(hv) <= tv).mean())
                if d1 is None or p > d1:
                    d1 = p
        last_w = hist_sessions[-CONFIG["D1_PERSIST_WINDOW"]:]
        d3 = None
        if len(hist_sessions) >= CONFIG["MIN_HISTORY"]:
            cnt = 0
            counted = 0
            for s in last_w:
                row = metrics_by_session.get(s, {}).get(n)
                if not row:
                    continue
                best = None
                idx = hist_sessions.index(s) if s in hist_sessions else None
                prior = hist_sessions[:idx] if idx is not None else []
                for k, tv in row.get("vb", {}).items():
                    hv = [metrics_by_session.get(t, {}).get(n, {}).get("vb", {}).get(k) for t in prior]
                    hv = [x for x in hv if x is not None]
                    if len(hv) >= CONFIG["MIN_HISTORY"]:
                        p = float((np.array(hv) <= tv).mean())
                        best = max(best or 0.0, p)
                if best is not None:
                    counted += 1
                    if best >= CONFIG["D1_PERSIST_TH"]:
                        cnt += 1
            d3 = (cnt / counted) if counted >= CONFIG["MIN_HISTORY"] else None
        d_sal = d_salience(d1, d3)

        # Q legs
        q_oi_v = q_oi(doi_today.get(n), doi_history.get(n, []))
        q_skew_v = q_skew(skew_delta_today.get(n), skew_delta_hist.get(n, []))

        # C family
        c1 = percentile_xs(xs_today["sd_share"], n)
        c2 = 0
        hist_spot = panel.summary_spot.get(n) or []
        window_spot = hist_spot[-CONFIG["LOOKBACK"]:]
        if p_v1 is not None and len(window_spot) >= CONFIG["MIN_HISTORY"] and p_v1 >= CONFIG["C2_IV_TH"] \
                and m["spot"] >= CONFIG["C2_EXT"] * max(window_spot):
            c2 = 1
        c3 = 1 if (d1 is not None and d1 >= CONFIG["C3_D1"] and d3 is not None and d3 >= CONFIG["C3_D3"]
                   and p_v2 is not None and p_v2 >= CONFIG["C3_V2"]) else 0
        c_fire, c_sev = crowd_family(c1, c2, c3)
        fired_legs = crowd_fired_legs(c1, c2, c3)

        # event / gex
        in_event = n in event_names
        ed = panel.event_date.get(n)
        f_e = f_e_by_symbol.get(n)
        p_xs_event = p_xs_event_by_symbol.get(n)
        gex_verdict = panel.gex_verdict.get(n) if panel.gex_bound_to_S else None

        direction = classify_direction(q_oi_v, q_skew_v, d_sal)
        if direction is None:
            direction = fallback_route(f_v, f_e, c_fire)

        coverage_complete = (m["n_quot"] >= CONFIG["MIN_CONTRACTS"] and H.get(n, 0) >= CONFIG["MIN_HISTORY"])

        # fresh: only V-family staleness is structurally checkable at build time (two
        # independently-collected stores: chains vs GEX summary spot history). See the
        # engine module docstring "fresh" note in the contract-implementation report.
        fresh_ok = True
        if p_v2 is not None:
            fresh_ok = len(hist_spot) > 0  # summary series exists and contributed -> current by construction

        event_imminent = False
        if in_event and direction in ("LONG", "SHORT"):
            gap = sessions_apart_fn(S, ed) if ed else None
            event_imminent = gap is not None and gap <= CONFIG["EVENT_CONTAM_SESSIONS"]

        m_gex_value = m_gex_multiplier(direction, gex_verdict)
        es = evidence_strength(direction, q_oi_v=q_oi_v, q_skew_v=q_skew_v, d_sal=d_sal,
                                f_v=f_v, f_e=f_e, c_sev=c_sev)
        ec = evidence_confidence(direction, d3=d3, coverage_complete=coverage_complete)
        m_ad = actionability(tier=tiers.get(n, "T3"), direction=direction, fresh_ok=fresh_ok,
                              event_imminent=event_imminent, c_fire=c_fire, gex_verdict=gex_verdict)
        R = research_priority(es, ec, m_ad)

        # B3 — evidence-derived freshness: the minimum lawful expiry over the card's
        # ACTUAL contribution set (never derived from direction alone). See
        # `fresh_until_for`'s docstring for the full rule; `d3_bonus_applied` mirrors
        # `evidence_confidence`'s own persist-bonus condition exactly (contract ruling:
        # "the confidence d3 bonus is salience evidence").
        d3_bonus_applied = (d3 or 0.0) >= 0.5
        fresh_until_date = fresh_until_for(
            direction=direction, S=S, session_n_forward_fn=session_n_forward_fn,
            gex_active=(m_gex_value != 1.0), crowd_fired_legs=fired_legs,
            f_e_active=(in_event and f_e is not None), event_date=ed,
            d3_bonus_applied=d3_bonus_applied,
        )

        # "NEUTRAL cards are never ranked; an eligible name that is NEUTRAL or below
        # R < 100 reports NO_SIGNAL" (contract §5.3) — the R<100 clause applies to
        # EVERY direction, not just NEUTRAL (a low-conviction VOLATILITY/RISK_ONLY
        # name is just as much a no-signal name as a NEUTRAL one).
        symbol_state = "NO_SIGNAL" if (direction == "NEUTRAL" or R < CONFIG["NO_SIGNAL_R"]) else direction

        # B4 — Prophet TWO-domain resolution (plans[] vs intake.receipts.groups),
        # per-symbol precedence when they collide. Display-only; zero rank authority —
        # nothing computed above this point (or below) ever reads these two lines.
        plan_state = prophet_plan_state(
            panel.prophet_entry_status.get(n), panel.prophet_lifecycle_state.get(n),
            panel.prophet_plan_closed.get(n, False), has_plan=(n in panel.prophet_entry_status),
        )
        group_state = (prophet_group_state(panel.prophet_group_reason.get(n))
                        if n in panel.prophet_group_reason else None)
        prophet_state_value = prophet_state_combined(plan_state, group_state)
        card = {
            "signal_id": signal_id_for(S, n),
            "symbol": n,
            "canonical_instrument_id": f"US:{n}",
            "as_of_session": S,
            "direction": direction if direction != "NEUTRAL" else "NEUTRAL",
            "display_state_en": DISPLAY_STATE.get(direction, ("No signal", "无信号"))[0],
            "display_state_zh": DISPLAY_STATE.get(direction, ("No signal", "无信号"))[1],
            "horizon": horizon_for(direction, event_board=False),
            "evidence_strength": round(es, 4),
            "evidence_confidence": round(ec, 4),
            "evidence_confidence_band": confidence_band(ec),
            "research_priority_score": R,
            "why_now": why_now_strings(direction, q_oi_v=q_oi_v, q_skew_v=q_skew_v, d_sal=d_sal,
                                        f_v=f_v, f_e=f_e, c_sev=c_sev),
            "evidence": [
                {"name": "Q_oi", "value": q_oi_v, "history_n": len(doi_history.get(n, [])), "observed_or_inferred": "inferred"},
                {"name": "Q_skew", "value": q_skew_v, "history_n": len(skew_delta_hist.get(n, [])), "observed_or_inferred": "inferred"},
                {"name": "D_salience", "value": d_sal, "history_n": H.get(n, 0), "observed_or_inferred": "inferred"},
                {"name": "F_V", "value": f_v, "history_n": H.get(n, 0), "observed_or_inferred": "inferred"},
                {"name": "F_E", "value": f_e, "history_n": (H.get(n, 0) if in_event else 0), "observed_or_inferred": "inferred"},
            ],
            "contradictions": [],
            "mechanics_context": {
                "gex_confirm_verdict": gex_verdict,
                "gamma_regime": None,
                "flip_proximity": None,
            },
            "crowding": ({"fired": fired_legs, "severity": round(c_sev, 4)} if c_fire else None),
            "event": ({
                "event_date": panel.event_date.get(n), "history_mode": "cross_sectional",
                "event_premium_state": (
                    "LOW" if (p_xs_event is not None and p_xs_event <= 0.25) else
                    "HIGH" if (p_xs_event is not None and p_xs_event >= 0.75) else
                    ("NORMAL" if p_xs_event is not None else None)
                ),
                "fresh_until": panel.event_date.get(n),
            } if in_event else None),
            "market_implied_move_pct": (round(market_implied_move_pct(m.get("atm_iv"), horizon_sessions=5), 6)
                                         if direction in ("LONG", "SHORT", "VOLATILITY") and m.get("atm_iv") else None),
            "trigger_watch": trigger_watch_string(direction),
            "invalidation_watch": invalidation_watch_string(direction),
            "fresh_until": fresh_until_date,
            "source_state": "ok",
            "prophet_state": prophet_state_value,
            "prophet_asof": panel.prophet_asof,
            "asymmetry_score": None, "asymmetry_state": "UNCALIBRATED",
            "probability_up": None, "probability_down": None,
            "expected_edge_bps": None,
            "supersedes_signal_id": None, "corrected_at": None,
            # Calendar absent entirely -> event conditioning cannot be evaluated for
            # ANY name this session (test 6 EVENT_STATE_UNKNOWN path); a loaded
            # calendar with this name simply outside the window is not an unknown,
            # it is "no event family" (event=None above).
            "null_reason": ("EVENT_STATE_UNKNOWN" if not panel.events_loaded else None),
            # internal-only bookkeeping fields (stripped before the boards use them;
            # kept on the card since consumers ignore unknown keys and tests want them)
            "tier_metric": mean_vol.get(n) or 0.0,
            "tier": tiers.get(n, "T3"),
            "coverage_complete": coverage_complete,
            "board_state_symbol": symbol_state,
            "f_e": f_e,
        }
        cards.append(card)

    opportunities, overflow = compose_opportunities(cards)
    event_cards = [c for c in cards if c["event"] is not None and c.get("f_e") is not None]
    event_board = compose_event_board(event_cards)
    risk_cards = [c for c in cards if c["crowding"] is not None]
    risk_board = compose_risk_board(risk_cards)
    no_sig = no_signal_exemplar(cards)

    eligible_ratio = eligibility.ratio
    if eligible_ratio is not None and eligible_ratio < CONFIG["ELIGIBILITY_GATE"]:
        return _degraded_payload(
            reason="ELIGIBILITY_COLLAPSE", panel=panel, source_watermarks=source_watermarks,
            input_receipts=input_receipts, built_at_utc=built_at_utc, eligibility=eligibility,
            source_manifest=source_manifest,
        )

    # §5.2 no-signal law: an empty board (opportunities AND event AND risk all empty)
    # with HEALTHY eligibility (already checked above) is a first-class OK-shaped
    # outcome — the session had nothing to say, never "the data could not support it".
    board_state = "OK" if (opportunities or event_board or risk_board) else "NO_SIGNAL"
    board_reason = None

    header = {
        "schema": SCHEMA,
        "model_version": MODEL_VERSION,
        "as_of_session": S,
        "oi_counted_date": D,
        "pending_session": panel.pending_session,
        "pending_reason": panel.pending_reason,
        "built_at_utc": built_at_utc,
        "source_watermarks": dict(source_watermarks),
        "input_receipts": list(input_receipts),
        "eligibility": eligibility.as_dict(),
        "board_state": board_state,
        "board_reason": board_reason,
        # AD0 §6.1 named exclusion stat (tests 1/2) — adjusted/nonstandard vendor
        # contract tickers on chain[S], never silently aggregated into any family.
        "contract_identity_exclusions": contract_identity_excluded_S,
        # B1 — deterministic per-file manifest of every consumed GEX summary/confirm
        # input (path -> sha256, member_count, merkle-style aggregate root per domain).
        "source_manifest": (dict(source_manifest) if source_manifest is not None else _empty_source_manifest()),
    }
    header["receipt_id"] = receipt_id(
        schema=SCHEMA, model_version=MODEL_VERSION, as_of_session=S, oi_counted_date=D,
        source_watermarks=source_watermarks, input_receipts=input_receipts,
    )
    header["config_hash"] = config_hash()

    def strip(c: dict) -> dict:
        return {k: v for k, v in c.items() if k not in ("tier_metric", "tier", "coverage_complete", "board_state_symbol", "f_e")}

    payload = {
        **header,
        "opportunities": [strip(c) for c in opportunities],
        "opportunities_overflow": overflow,
        "event_board": [strip(c) for c in event_board],
        "risk_warnings": [strip(c) for c in risk_board],
        "no_signal_exemplar": (strip(no_sig) if no_sig else None),
    }
    return payload


def _empty_source_manifest() -> dict[str, Any]:
    """The B1 ``source_manifest`` shape when the producer hasn't (or couldn't) resolve
    one — e.g. MIXED_VINTAGE, where no chain[S] was ever loaded to consume anything."""
    empty_domain = {"root": None, "member_count": 0, "files": {}}
    return {"gex_summary": dict(empty_domain, files={}), "gex_confirm": dict(empty_domain, files={})}


def _base_header(*, panel: SessionPanel, source_watermarks, input_receipts, built_at_utc,
                  board_state: str, board_reason: str | None, eligibility: Eligibility | None = None,
                  source_manifest: Mapping[str, Any] | None = None) -> dict:
    S = panel.as_of_session or ""
    D = panel.oi_counted_date or ""
    header = {
        "schema": SCHEMA, "model_version": MODEL_VERSION,
        "as_of_session": S, "oi_counted_date": D,
        "pending_session": panel.pending_session, "pending_reason": panel.pending_reason,
        "built_at_utc": built_at_utc,
        "source_watermarks": dict(source_watermarks),
        "input_receipts": list(input_receipts),
        "eligibility": (eligibility.as_dict() if eligibility else Eligibility().as_dict()),
        "board_state": board_state, "board_reason": board_reason,
        "contract_identity_exclusions": 0,
        "source_manifest": (dict(source_manifest) if source_manifest is not None else _empty_source_manifest()),
    }
    header["receipt_id"] = receipt_id(
        schema=SCHEMA, model_version=MODEL_VERSION, as_of_session=S, oi_counted_date=D,
        source_watermarks=source_watermarks, input_receipts=input_receipts,
    )
    header["config_hash"] = config_hash()
    return {
        **header, "opportunities": [], "opportunities_overflow": 0,
        "event_board": [], "risk_warnings": [], "no_signal_exemplar": None,
    }


def _degraded_payload(*, reason: str, panel: SessionPanel, source_watermarks, input_receipts,
                       built_at_utc, eligibility: Eligibility | None = None,
                       source_manifest: Mapping[str, Any] | None = None) -> dict:
    return _base_header(panel=panel, source_watermarks=source_watermarks, input_receipts=input_receipts,
                         built_at_utc=built_at_utc, board_state="DEGRADED", board_reason=reason,
                         eligibility=eligibility, source_manifest=source_manifest)


def _stale_payload(*, panel: SessionPanel, source_watermarks, input_receipts, built_at_utc,
                    universe_count: int | None = None, source_coverage_pct: float | None = None,
                    source_manifest: Mapping[str, Any] | None = None) -> dict:
    elig = Eligibility(universe_count=universe_count, source_coverage_pct=source_coverage_pct)
    return _base_header(panel=panel, source_watermarks=source_watermarks, input_receipts=input_receipts,
                         built_at_utc=built_at_utc, board_state="STALE_SOURCE", board_reason=None,
                         eligibility=elig, source_manifest=source_manifest)


def _insufficient_coverage_payload(*, panel: SessionPanel, present: int, source_watermarks,
                                    input_receipts, built_at_utc, universe_count: int | None = None,
                                    source_coverage_pct: float | None = None,
                                    source_manifest: Mapping[str, Any] | None = None) -> dict:
    elig = Eligibility(present=present, universe_count=universe_count, source_coverage_pct=source_coverage_pct)
    return _base_header(panel=panel, source_watermarks=source_watermarks, input_receipts=input_receipts,
                         built_at_utc=built_at_utc, board_state="INSUFFICIENT_COVERAGE", board_reason=None,
                         eligibility=elig, source_manifest=source_manifest)
