"""engine.neuralweb.world_state — The composed one-page truth (Neural Web N1).

PURPOSE
-------
build_world_state() reads a handful of existing stores and writes one stamped
JSON that gives every consumer a single canonical entry point for the current
macro/regime/rotation state.  This is COMPOSITION, not replacement — the
source stores continue to exist and be owned by their respective programs.

FAIL-OPEN CONTRACT
------------------
Every sub-block read is fail-open: a missing, corrupt, or unreadable source
yields null for that block plus an entry in the top-level 'gaps' list.  The
builder never raises on a missing store; it always produces a partial artifact
rather than aborting.  Consumers must treat null blocks as "not available this
run."

DESIGN (adjudicated W1 PR1)
---------------------------
* verdict      — post-radar-override resolved verdict from market_state/latest.json
* radar        — resolved radar override block (from same file)
* risk_radar_raw — data/regime/latest.json['risk_radar'] embedded VERBATIM
* regime       — quad/cycle/transition fields from data/regime/latest.json
* vol          — vol_regime sub-object from data/regime/latest.json
* breadth      — last row of data/breadth/breadth.parquet + rolling derivations
* rotation     — read-only summary of site/basketdata/oracle_state.json (Oracle-owned)
* liquidity    — liquidity_overlay from data/regime/latest.json
* data_health  — summary stats from data/run_status.json
* alerts       — summary counts from site/factordata/alerts_triage.json
* qi           — null (pending joint QI border ruling)
* live_overlay — best-effort regime freshness stamp
* factor_weather — factor panel lobe (§5.4 + RULING-B); data loaded inside
                   _compose_factor_weather, wired as one line in build_world_state.

R5 macro lobes (PR-B — display_only=True; all fail-open):
* rates_transmission — data/transmission/latest.json
* fx_dollar          — data/forex/latest.json
* rates_credit       — data/bonds/bond_health.json
* global_regimes     — data/{china,hk,canada}_regime/latest.json + regime block
* commodity_context  — data/commodity/latest.json
* intelligence       — site/intelligence/briefing.json
* macro_deltas       — data/macro_snapshots/transitions.jsonl (may be absent; gap OK)
factor_weather is composed by _compose_factor_weather() — see §5.4 notes below.

BORDER LAW (§9)
---------------
Neural Web owns rails, memory, governance, and synthesis; domain programs own
their signals.  This builder reads Oracle's oracle_state.json READ-ONLY and
summarises it — it does not aggregate raw Oracle internals nor reshape what
Oracle produced.  The QI slot is left null pending the W7 joint border ruling.

ENVELOPE
--------
The output is stamped with engine.neuralweb.envelope.stamp() — the first
producer adoption of the envelope on the Neural Web bus.

factor_weather lobe (§5.4): composed by _compose_factor_weather() below; panel
calibration notes and nightly-bounds law live in scripts/build_factor_panel.py.
"""
from __future__ import annotations

import copy
import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.neuralweb._law import display_only as _display_only
from engine.neuralweb._dates import to_iso as _to_iso

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# JSON-safety helpers (FIX-5)
# ─────────────────────────────────────────────────────────────────────────────

def _clean(v: Any) -> Any:
    """Coerce a value to a JSON-safe Python native type.

    Rules (FIX-5, RULING-B):
    - None → None
    - float NaN or Inf → None  (prevents 'NaN' literal in JSON output)
    - numpy scalar types → coerce to native float/int/str
    - everything else → returned as-is

    This must be applied to every value read from panel rows into the lobe dict
    before the dict is returned.  The house has shipped invalid JSON ('NaN'
    literal) and silently-zeroed ledgers from numpy types before.
    """
    if v is None:
        return None
    # NaN / Inf guard for floats and numpy-float-like objects:
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    # numpy scalar detection without importing numpy at module level:
    type_name = type(v).__name__
    module_name = getattr(type(v), "__module__", "") or ""
    if "numpy" in module_name:
        # numpy integer types → int
        if type_name.startswith("int") or type_name.startswith("uint"):
            return int(v)
        # numpy float types → float, then apply NaN/Inf guard
        if type_name.startswith("float"):
            fv = float(v)
            if math.isnan(fv) or math.isinf(fv):
                return None
            return fv
        # numpy bool_ → bool
        if type_name.startswith("bool"):
            return bool(v)
        # numpy string/bytes → str
        return str(v)
    return v

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read_json(p: Path) -> dict | None:
    """Read and parse JSON from *p*; return None on any failure."""
    try:
        text = p.read_text(encoding="utf-8")
        return json.loads(text)
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: unreadable json %s — %s", p, exc)
        return None


def _repo_root(root: Path | None) -> Path:
    """Resolve the repo root from an explicit override or the module location."""
    if root is not None:
        return Path(root)
    # engine/neuralweb/world_state.py → ../../.. = repo root
    return Path(__file__).resolve().parent.parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Sub-block composers
# ─────────────────────────────────────────────────────────────────────────────

def _compose_verdict(ms: dict) -> dict:
    """Extract the post-radar-resolved verdict block from market_state."""
    return {
        "verdict": ms.get("verdict"),
        "score": ms.get("score"),
        "raw_score": ms.get("raw_score"),
        "is_display_only": ms.get("is_display_only"),
        "label_en": ms.get("label_en"),
        "label_zh": ms.get("label_zh"),
        "asof": ms.get("asof"),
    }


def _compose_radar(ms: dict) -> dict | None:
    """Extract the radar override outcome block from market_state."""
    r = ms.get("radar")
    if not isinstance(r, dict):
        return None
    return {
        "state": r.get("state"),
        "ceiling": r.get("ceiling"),
        "amp": r.get("amp"),
        "amp_keys": r.get("amp_keys"),
        "severe_gated": r.get("severe_gated"),
        "recovery": r.get("recovery"),
        "is_loud": r.get("is_loud"),
    }


def _compose_regime(reg: dict) -> dict:
    """Extract the regime quad block; exactly the specified keys.

    sector_rs is included so consumers that migrate from direct latest.json
    reads (e.g. engine/etf_pulse.py) can consume the same data from
    world_state without needing a separate file open.  The value is the
    verbatim list produced by engine/sectors.py (or None if absent).
    """
    freshness = reg.get("freshness")
    return {
        "quad": reg.get("quad"),
        "quad_name": reg.get("quad_name"),
        "label": reg.get("label"),
        "confidence": reg.get("confidence"),
        "growth_score": reg.get("growth_score"),
        "inflation_score": reg.get("inflation_score"),
        "cycle_tag": reg.get("cycle_tag"),
        "transition_state": reg.get("transition_state"),
        "flip_condition": reg.get("flip_condition"),
        "flip_margin": reg.get("flip_margin"),
        "liquidity_quality": reg.get("liquidity_quality"),
        "business_cycle": reg.get("business_cycle"),
        "liquidity_overlay": reg.get("liquidity_overlay"),
        "sector_rs": reg.get("sector_rs"),
        "freshness": freshness,
        "asof": reg.get("asof"),
        "schema_version": reg.get("schema_version"),
    }


def _compose_vol(reg: dict) -> dict | None:
    """Extract the vol_regime sub-block; carry scored_active honestly."""
    vr = reg.get("vol_regime")
    if not isinstance(vr, dict):
        return None
    return {
        "regime": vr.get("regime"),
        "risk_score": vr.get("risk_score"),
        "scored_score": vr.get("scored_score"),
        "scored_active": vr.get("scored_active"),
        "vix": vr.get("vix"),
        "vrp_state": vr.get("vrp_state"),
        "vvix_state": vr.get("vvix_state"),
        "vol_target_scalar": vr.get("vol_target_scalar"),
        "fragility_confluence": vr.get("fragility_confluence"),
        "flags": vr.get("flags"),
        "asof": vr.get("asof"),
    }


def _compose_breadth(reg: dict, data_dir: Path) -> dict | None:
    """Last row of breadth.parquet + rolling derivations from regime."""
    raw: dict[str, Any] = {}
    date_str: str | None = None

    try:
        import pandas as pd
        bp = data_dir / "breadth" / "breadth.parquet"
        if bp.exists():
            df = pd.read_parquet(bp)
            if not df.empty:
                row = df.iloc[-1]
                date_str = str(df.index[-1])[:10]
                for col in ("n_members", "pct_above_50", "pct_above_200",
                            "nh", "nl", "adv", "dec", "ad_line"):
                    v = row.get(col)
                    if v is not None and not (hasattr(v, "__class__") and v.__class__.__name__ == "float" and v != v):
                        raw[col] = float(v) if col not in ("n_members", "nh", "nl", "adv", "dec") else int(v)
            else:
                log.warning("world_state: breadth.parquet is empty")
        else:
            log.warning("world_state: breadth.parquet absent")
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: breadth parquet read failed — %s", exc)

    # Derived rolling aggregates from regime/latest.json
    complacency = (reg.get("conditions") or {}).get("complacency") or {}
    raw["breadth_above200_pctile"] = complacency.get("breadth_above200_pctile")
    raw["breadth_div"] = complacency.get("breadth_div")

    if date_str:
        raw["date"] = date_str

    return raw if raw else None


def _compose_rotation(oracle: dict | None) -> dict | None:
    """Read-only summary of oracle_state.json (Oracle-owned, W4 ruling).

    Carries the regime block and complexes verbatim; condenses active_episodes
    into per-tier and per-direction counts rather than the 173-item list.
    Fail-open: missing oracle_state -> null.
    """
    if oracle is None:
        return None

    regime = oracle.get("regime")
    complexes = oracle.get("complexes")
    episodes: list = oracle.get("active_episodes") or []
    onset_watchlist: list = oracle.get("onset_watchlist") or []

    # episode_counts: counts grouped by tier and by direction
    by_tier: dict[str, int] = {}
    by_direction: dict[str, int] = {}
    for ep in episodes:
        tier = ep.get("tier") or "unknown"
        direction = ep.get("direction") or "unknown"
        by_tier[tier] = by_tier.get(tier, 0) + 1
        by_direction[direction] = by_direction.get(direction, 0) + 1

    return {
        "asof": oracle.get("asof"),
        "regime": regime,
        "complexes": complexes,
        "episode_counts": {
            "total": len(episodes),
            "by_tier": by_tier,
            "by_direction": by_direction,
        },
        "n_onset_watchlist": len(onset_watchlist),
    }


def _compose_liquidity(reg: dict) -> dict:
    """Extract liquidity_overlay (liquidity_quality lives in regime block)."""
    return {
        "liquidity_overlay": reg.get("liquidity_overlay"),
    }


def _compose_data_health(rs: dict) -> dict:
    """Summary stats from run_status.json — never the full 130+ source dict."""
    cb = rs.get("circuit_breaker") or {}
    sources = rs.get("sources") or {}
    stale_series = rs.get("stale_series") or []

    # Count sources by status
    status_counts: dict[str, int] = {}
    failed_sources: list[dict] = []
    for name, info in sources.items():
        if not isinstance(info, dict):
            continue
        status = info.get("status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "failed":
            err = str(info.get("error") or "")
            failed_sources.append({
                "source": name,
                "error": err[:120],
                "checked_at": info.get("checked_at") or info.get("probed_at"),
            })

    # Also count sources with non-zero circuit_breaker failures
    n_cb_failed = sum(1 for v in cb.values() if isinstance(v, int) and v > 0)

    return {
        "last_run": rs.get("last_run"),
        "counts": status_counts,
        "n_cb_failed": n_cb_failed,
        "n_stale_series": len(stale_series),
        "failed_sources": failed_sources,
    }


def _compose_alerts(at: dict) -> dict | None:
    """Summary counts only from alerts_triage.json."""
    summary = at.get("summary")
    if not isinstance(summary, dict):
        return None
    return {
        "asof": at.get("asof"),
        "generated_utc": at.get("generated_utc"),
        "total": summary.get("total"),
        "critical": summary.get("critical"),
        "major": summary.get("major"),
        "minor": summary.get("minor"),
        "actionable": summary.get("actionable"),
        "backtested": summary.get("backtested"),
    }


def _compose_live_overlay(reg: dict) -> dict | None:
    """Best-effort regime freshness stamp as the live overlay proxy.

    No dedicated intraday staleness artifact exists yet; the regime freshness
    block is the available EOD contract staleness stamp.  Fail-open: null if
    not readable.
    """
    freshness = reg.get("freshness")
    if not isinstance(freshness, dict):
        return None
    return {
        "source": "data/regime/latest.json:freshness",
        "asof": freshness.get("asof"),
        "built_at": freshness.get("built_at"),
        "age_days": freshness.get("age_days"),
        "stale": freshness.get("stale"),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Factor weather lobe (§5.4 + RULING-B)
# ─────────────────────────────────────────────────────────────────────────────

_OPTIONS_WEATHER_ROOTS = {
    "SPY", "QQQ", "IWM", "DIA",
    "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY",
    "SMH", "SOXX", "XBI", "KRE",
}
_OPTIONS_WEATHER_MIN_ROOTS = 5


def _compose_options_weather(
    root: "Path | str | None" = None,
) -> dict:
    """Compose the options_weather sub-block (Options→NW W-B, RO-1/RO-6).

    Follows the _compose_factor_weather discipline exactly: all data loading
    internal, _clean() on every value, display_only=True, try/except at the
    wiring site returns a null-filled fallback.

    Reads data/options_entry/state.parquet and aggregates ONLY over the
    deep-liquidity sector-ETF/index roots (the set with 15y ThetaData history —
    the W-E1 gauntlet's universe). Raw aggregate fields only — NO composite
    score (RO-2). Aggregates suppress to null below
    _OPTIONS_WEATHER_MIN_ROOTS contributing roots.

    W-E1 context baked into the field notes: gamma regime stratifies realized
    vol with an ERA-DEPENDENT sign (regime context, not direction).
    """
    repo = _repo_root(root)
    path = repo / "data" / "options_entry" / "state.parquet"

    out: dict[str, Any] = {
        "as_of": None,
        "n_roots": None,
        "median_iv30": None,
        "median_skew": None,
        "median_skew_5d_chg": None,
        "share_skew_rising": None,
        "median_ivspread_rel": None,
        "share_pin_risk": None,
        "opex_days": None,
        "note": (
            "sector-ETF/index options weather (raw aggregates; no composite — RO-2). "
            "Gamma-regime evidence is vol-conditioning with era-dependent sign (W-E1); "
            "never directional."
        ),
        "display_only": True,
    }
    if not path.exists():
        return out
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path)
        df = df[df["ticker"].isin(_OPTIONS_WEATHER_ROOTS)]
        if df.empty:
            return out

        def _med(col: str):
            s = df[col].dropna() if col in df.columns else None
            return float(s.median()) if s is not None and len(s) >= _OPTIONS_WEATHER_MIN_ROOTS else None

        def _share(col: str, pred):
            s = df[col].dropna() if col in df.columns else None
            if s is None or len(s) < _OPTIONS_WEATHER_MIN_ROOTS:
                return None
            return float(pred(s).mean())

        out["as_of"] = _clean(df["as_of"].max())
        out["n_roots"] = int(len(df))
        out["median_iv30"] = _clean(_med("iv30"))
        out["median_skew"] = _clean(_med("skew"))
        out["median_skew_5d_chg"] = _clean(_med("skew_5d_chg"))
        out["share_skew_rising"] = _clean(_share("skew_5d_chg", lambda s: s > 0))
        out["median_ivspread_rel"] = _clean(_med("ivspread_rel"))
        out["share_pin_risk"] = _clean(_share("pin_risk", lambda s: s.astype(bool)))
        od = df["opex_days"].dropna()
        out["opex_days"] = int(od.iloc[0]) if len(od) else None
    except Exception as exc:  # noqa: BLE001
        log.warning("options_weather: compose failed — %s", exc)
    return out


def _compose_factor_weather(
    root: "Path | str | None" = None,
    prefer_artifact: bool = True,
) -> dict:
    """Compose the factor_weather sub-block for world_state (§5.4).

    Parameters
    ----------
    root:
        Repo root override (defaults to _repo_root()).
    prefer_artifact:
        When True (default, world_state lobe path): attempt to read
        data/neuralweb/factor_intelligence_state.json as canonical
        (RUL-NW2).  If the artifact is present, parseable, and contains a
        ``factor_weather`` block, that block is returned AUGMENTED with a
        ``factor_state_as_of`` key carrying the artifact's top-level
        ``as_of`` value (staleness visibility, RUL-NW2).

        When False (builder path): the artifact read is skipped entirely
        and the function goes directly to the legacy direct-panel-read
        branch.  Pass ``prefer_artifact=False`` from
        ``build_factor_intelligence_state._build_factor_weather_block``
        to guarantee a fresh recompute every night — preventing the
        circular-freeze where the builder reads last night's committed
        artifact and re-emits it verbatim without touching the panel
        (regression: RUL-NW10 history tape would freeze at day-1 values).

    Fallback / legacy path (artifact absent/corrupt/missing factor_weather,
    OR prefer_artifact=False):
        the legacy direct-panel-read logic (below) runs unchanged.  The
        returned dict carries ``factor_state_as_of: null``.  Staleness is
        signalled solely by this null value — no additional gap-note entry
        is appended.

    RULING-B fold (FIX-1): all data loading is done inside this function.
    The wiring line in build_world_state is:
        "factor_weather": _compose_factor_weather(root=root)
    No panel_latest or factor_series arguments are passed from build_world_state.

    Data sources read internally (all fail-open):
    - data/neuralweb/factor_intelligence_state.json  (canonical — RUL-NW2)
    - data/factordata/panel/ — latest-date row, via max-date selection (FIX-9)
    - site/factordata/factor_series.json — rotation leader
    - data/edgar/ic_scorecard.json — leader IC (FIX-2)
    - data/yahoo/{IWF,IWD,QQQ,SPY,IWM}.parquet — real 20d ETF ratios (FIX-3)

    FIX-4: style_regime_hold_days computed from panel tail (trailing consecutive
    days of confirmed state), not a panel column.

    FIX-5: all values passed through _clean() before the dict is returned to
    prevent 'NaN' literals and numpy scalar types in the output JSON.

    Returns
    -------
    dict
        Keys: style_regime, style_regime_pending, style_regime_hold_days,
        factor_leader, factor_leader_ic, etf_pulse_summary, display_only,
        factor_state_as_of (11th key, RUL-NW2 staleness stamp).
        display_only is ALWAYS True — §5.4 mandates it.
    """
    repo = _repo_root(root)

    # ── RUL-NW2: try canonical committed state artifact first ─────────────────
    # Skipped when prefer_artifact=False (builder fresh-compute path — see docstring).
    _state_artifact_path = repo / "data" / "neuralweb" / "factor_intelligence_state.json"
    if prefer_artifact:
        try:
            if _state_artifact_path.exists():
                _state = json.loads(_state_artifact_path.read_text(encoding="utf-8"))
                if isinstance(_state, dict):
                    _fw_block = _state.get("factor_weather")
                    if isinstance(_fw_block, dict) and _fw_block:
                        # Canonical path: augment with staleness stamp and return.
                        _artifact_as_of = _state.get("as_of")
                        out = dict(_fw_block)
                        out["factor_state_as_of"] = _artifact_as_of
                        # Ensure display_only is always True regardless of artifact content.
                        out["display_only"] = True
                        log.info(
                            "factor_weather: canonical artifact path (RUL-NW2) — as_of=%s",
                            _artifact_as_of,
                        )
                        return out
                    else:
                        log.info(
                            "factor_weather: artifact present but factor_weather block "
                            "missing or empty — falling back to direct panel read"
                        )
                else:
                    log.warning(
                        "factor_weather: artifact at %s is not a dict — falling back",
                        _state_artifact_path,
                    )
            else:
                log.info(
                    "factor_weather: state artifact absent (%s) — falling back to "
                    "direct panel read",
                    _state_artifact_path,
                )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "factor_weather: artifact read/parse failed (%s) — falling back: %s",
                _state_artifact_path,
                exc,
            )
    else:
        log.info(
            "factor_weather: prefer_artifact=False — skipping artifact, fresh recompute from panel"
        )

    # ── Legacy fallback: direct panel / ETF / scorecard read ─────────────────
    # (unchanged from the pre-RUL-NW2 implementation; runs only when the
    # committed artifact is absent, corrupt, or missing the factor_weather block)
    data_dir = repo / "data"
    site_dir = repo / "site"

    style_regime: str | None = None
    style_regime_pending: str | None = None
    style_regime_hold_days: int | None = None
    factor_leader: str | None = None
    factor_leader_ic: float | None = None
    # etf_pulse_summary: three 20d ratios (IWF/IWD, QQQ/SPY, IWM/SPY) — FIX-3
    ratio_iwf_iwd: float | None = None
    ratio_qqq_spy: float | None = None
    ratio_iwm_spy: float | None = None

    gaps: list[str] = []

    # ── 1. Read latest panel row (FIX-1 data loading + FIX-9 max-date) ──────
    try:
        import pandas as _pd  # lazy import — world_state has no hard pandas dep

        panel_dir = data_dir / "factordata" / "panel"
        _panel_latest_row: dict | None = None
        _style_series: list[tuple[str, str]] = []  # [(date_str, confirmed_state), ...]

        if panel_dir.exists():
            # FIX-9: explicit max-date selection rather than sorted[-1] + iloc[-1]
            _parquet_files = list(panel_dir.rglob("panel.parquet"))
            if _parquet_files:
                # Read only last few partitions (last 2 sorted by path) for efficiency:
                _sorted_files = sorted(_parquet_files)
                _tail_files = _sorted_files[-2:]  # last 2 monthly partitions
                _frames = []
                for _pf in _tail_files:
                    try:
                        _frames.append(_pd.read_parquet(_pf,
                                                         columns=["date", "ticker",
                                                                  "style_regime",
                                                                  "style_regime_pending"]))
                    except Exception as _exc:
                        log.warning("factor_weather: panel partition unreadable %s — %s",
                                    _pf, _exc)
                if _frames:
                    _pdf = _pd.concat(_frames, ignore_index=True)
                    if not _pdf.empty:
                        # FIX-9: take rows at max date (not iloc[-1])
                        _max_date = _pdf["date"].max()
                        _latest_rows = _pdf[_pdf["date"] == _max_date]
                        if not _latest_rows.empty:
                            # Use first row for market-level fields (same for all tickers)
                            _panel_latest_row = _latest_rows.iloc[0].to_dict()

                        # FIX-4: compute hold_days from date-deduplicated style_regime series
                        # (market-level: same confirmed state for all tickers on a date)
                        _by_date = (
                            _pdf[["date", "style_regime"]]
                            .drop_duplicates(subset=["date"])
                            .sort_values("date")
                        )
                        _style_series = list(
                            zip(_by_date["date"].tolist(),
                                _by_date["style_regime"].tolist())
                        )

        # Extract style_regime + pending from latest row:
        if isinstance(_panel_latest_row, dict):
            style_regime = _clean(_panel_latest_row.get("style_regime")) or None
            style_regime_pending = (
                _clean(_panel_latest_row.get("style_regime_pending")) or None
            )

        # FIX-4: count trailing consecutive dates equal to current confirmed state:
        if style_regime and _style_series:
            _hold = 0
            for _d, _s in reversed(_style_series):
                if _s == style_regime:
                    _hold += 1
                else:
                    break
            style_regime_hold_days = _hold if _hold > 0 else None

    except Exception as exc:  # noqa: BLE001
        log.warning("factor_weather: panel read failed — %s", exc)
        gaps.append(f"panel: {exc}")

    # ── 2. Factor leader from factor_series.json + IC from scorecard (FIX-2) ─
    _fs_path = site_dir / "factordata" / "factor_series.json"
    _factor_series_json = _read_json(_fs_path)
    if isinstance(_factor_series_json, dict):
        try:
            rotation = _factor_series_json.get("rotation") or {}
            if isinstance(rotation, dict):
                factor_leader = _clean(
                    rotation.get("leader") or rotation.get("confirmed_leader")
                )

            # FIX-2: resolve IC from ic_scorecard.json (key 'mean_ic', lowercase factor)
            # NOT from the rotation dict — that is the panel-computed snapshot-day IC.
            if factor_leader:
                _sc_path = data_dir / "edgar" / "ic_scorecard.json"
                _scorecard = _read_json(_sc_path)
                if isinstance(_scorecard, dict):
                    _factors_block = _scorecard.get("factors") or {}
                    _leader_lower = str(factor_leader).lower()
                    _sc_entry = (
                        _factors_block.get(factor_leader)
                        or _factors_block.get(_leader_lower)
                    )
                    if isinstance(_sc_entry, dict) and _sc_entry.get("mean_ic") is not None:
                        _ic_raw = _sc_entry["mean_ic"]
                        factor_leader_ic = _clean(float(_ic_raw))
                        log.info(
                            "factor_weather: leader=%s mean_ic=%.4f (from ic_scorecard.json)",
                            factor_leader,
                            factor_leader_ic if factor_leader_ic is not None else float("nan"),
                        )
                    else:
                        log.info(
                            "factor_weather: leader=%s not found in ic_scorecard.json — "
                            "factor_leader_ic=None (scorecard absent or entry missing)",
                            factor_leader,
                        )
                else:
                    log.info(
                        "factor_weather: ic_scorecard.json unreadable — "
                        "factor_leader_ic=None"
                    )

        except Exception as exc:  # noqa: BLE001
            log.warning("factor_weather: factor_series/scorecard parse error — %s", exc)
            gaps.append(f"factor_series: {exc}")
    else:
        gaps.append("site/factordata/factor_series.json: missing or unreadable")

    # ── 3. Real 20d ETF ratios from data/yahoo/ closes (FIX-3 + RULING-D) ───
    # NOT from etf_pulse.json (does not exist in this repo — RULING-D).
    # ratio = 20d compounded return of A minus 20d compounded return of B (PIT).
    try:
        import pandas as _pd2  # may already be imported above; harmless re-import

        def _etf_close_series(sym: str) -> "_pd2.Series | None":  # type: ignore[name-defined]
            _p = data_dir / "yahoo" / f"{sym}.parquet"
            if not _p.exists():
                log.warning("factor_weather: ETF parquet missing: %s", _p)
                return None
            _df = _pd2.read_parquet(_p)
            if "close" not in _df.columns:
                return None
            _s = _df["close"].astype(float)
            _s.index = _pd2.to_datetime(_s.index)
            return _s.sort_index()

        def _ratio_20d(sym_a: str, sym_b: str) -> "float | None":
            _a = _etf_close_series(sym_a)
            _b = _etf_close_series(sym_b)
            if _a is None or _b is None:
                return None
            _ret_a = _a.pct_change(fill_method=None)
            _ret_b = _b.pct_change(fill_method=None)
            _roll_a = _ret_a.rolling(20, min_periods=10).apply(
                lambda x: (1 + x).prod() - 1, raw=True)
            _roll_b = _ret_b.rolling(20, min_periods=10).apply(
                lambda x: (1 + x).prod() - 1, raw=True)
            _diff = (_roll_a - _roll_b).dropna()
            if _diff.empty:
                return None
            # FIX-9: take last value at max date
            _max_d = _diff.index.max()
            _val = float(_diff.loc[_max_d])
            return None if (math.isnan(_val) or math.isinf(_val)) else _val

        ratio_iwf_iwd = _ratio_20d("IWF", "IWD")
        ratio_qqq_spy = _ratio_20d("QQQ", "SPY")
        ratio_iwm_spy = _ratio_20d("IWM", "SPY")

    except Exception as exc:  # noqa: BLE001
        log.warning("factor_weather: ETF ratio computation failed — %s", exc)
        gaps.append(f"etf_ratios: {exc}")

    # Build etf_pulse_summary from real ratios (FIX-3):
    if ratio_iwf_iwd is not None and ratio_qqq_spy is not None and ratio_iwm_spy is not None:
        etf_pulse_summary = (
            f"IWF/IWD_20d={ratio_iwf_iwd:+.4f}; "
            f"QQQ/SPY_20d={ratio_qqq_spy:+.4f}; "
            f"IWM/SPY_20d={ratio_iwm_spy:+.4f}"
        )
    else:
        _avail = [
            v for v in [ratio_iwf_iwd, ratio_qqq_spy, ratio_iwm_spy]
            if v is not None
        ]
        etf_pulse_summary = (
            "partial ETF data — some ratios unavailable" if _avail else None
        )
    if gaps:
        log.info("factor_weather gaps: %s", gaps)

    # RUL-NW2 fallback path: factor_state_as_of is null (artifact was absent/
    # corrupt/missing factor_weather block, or prefer_artifact=False was passed).
    # Staleness is signalled solely by the factor_state_as_of: null value —
    # no additional gap-note entry is emitted here.
    return {
        "style_regime": _clean(style_regime),
        "style_regime_pending": _clean(style_regime_pending),
        "style_regime_hold_days": _clean(style_regime_hold_days),
        "factor_leader": _clean(factor_leader),
        "factor_leader_ic": _clean(factor_leader_ic),
        "etf_pulse_summary": _clean(etf_pulse_summary),
        "ratio_iwf_iwd_20d": _clean(ratio_iwf_iwd),
        "ratio_qqq_spy_20d": _clean(ratio_qqq_spy),
        "ratio_iwm_spy_20d": _clean(ratio_iwm_spy),
        "display_only": True,
        "factor_state_as_of": None,  # null on legacy fallback path (RUL-NW2)
    }


# ─────────────────────────────────────────────────────────────────────────────
# R5 macro-context lobes (PR-B, §5.3)
# All composers follow the _compose_factor_weather discipline:
#   • all data loading is internal
#   • _clean() on every value
#   • display_only=True always (via _display_only)
#   • try/except at the wiring site returns a null-shaped fallback + gap
# ─────────────────────────────────────────────────────────────────────────────

def _compose_rates_transmission(root: "Path | str | None" = None) -> dict:
    """Compose rates_transmission lobe from data/transmission/latest.json.

    Field list per §5.3 lobe 1 (census-verified).
    """
    repo = _repo_root(root)
    path = repo / "data" / "transmission" / "latest.json"

    null_out: dict = {
        "asof": None,
        "scored_status": None,
        "calibrated": None,
        "state": None,
        "headwinds": None,
        "tailwinds": None,
        "yield_curve": None,
        "yield_curve_source": "transmission",
        "display_only": True,
    }

    raw = _read_json(path)
    if raw is None:
        return null_out

    try:
        # Headwinds / tailwinds: compact [{asset, verdict, net}]
        def _hw_tw(lst: list) -> list:
            out = []
            for item in (lst or []):
                if not isinstance(item, dict):
                    continue
                out.append({
                    "asset": _clean(item.get("asset")),
                    "verdict": _clean(item.get("verdict")),
                    "net": _clean(item.get("net")),
                })
            return out

        # yield_curve subset
        yc_raw = raw.get("yield_curve") or {}
        regime_raw = yc_raw.get("regime") or {}
        recession_raw = yc_raw.get("recession") or {}
        shape_raw = yc_raw.get("shape") or {}

        yc = {
            "regime": {
                "key": _clean(regime_raw.get("key")),
                "label": _clean(regime_raw.get("label")),
            },
            "recession": {
                "risk": _clean(recession_raw.get("risk")),
                "ntfs": _clean(recession_raw.get("ntfs")),
            },
            "shape": {
                "slope_2s10s": _clean(shape_raw.get("slope_2s10s")),
            },
        }

        return _display_only({
            "asof": _clean(raw.get("asof")),
            "scored_status": _clean(raw.get("scored_status")),
            "calibrated": _clean(raw.get("calibrated")),
            "state": raw.get("state"),
            "headwinds": _hw_tw(raw.get("headwinds") or []),
            "tailwinds": _hw_tw(raw.get("tailwinds") or []),
            "yield_curve": yc,
            "yield_curve_source": "transmission",
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("rates_transmission: compose failed — %s", exc)
        return null_out


def _compose_fx_dollar(root: "Path | str | None" = None) -> dict:
    """Compose fx_dollar lobe from data/forex/latest.json.

    Field list per §5.3 lobe 2 (census-verified).
    Uses _to_iso() to normalise the "Jul 02, 2026" display-string date.
    """
    repo = _repo_root(root)
    path = repo / "data" / "forex" / "latest.json"

    null_out: dict = {
        "asof": None,
        "regime": None,
        "risk": None,
        "favored": None,
        "dollar_desk": None,
        "transmission": None,
        "regime_radar": None,
        "display_only": True,
    }

    raw = _read_json(path)
    if raw is None:
        return null_out

    try:
        dd_raw = raw.get("dollar_desk") or {}
        tx_raw = raw.get("transmission") or {}
        rr_raw = raw.get("regime_radar") or {}

        dollar_desk = {
            "lean": _clean(dd_raw.get("lean")),
            "real_rate_regime": _clean(dd_raw.get("real_rate_regime")),
            "usd_valuation": _clean(dd_raw.get("usd_valuation")),
            "trend": _clean(dd_raw.get("trend")),
            "fed_path_lean": _clean(dd_raw.get("fed_path_lean")),
            "liquidity_dir": _clean(dd_raw.get("liquidity_dir")),
        }

        transmission = {
            "usd_dir": _clean(tx_raw.get("usd_dir")),
            "headwind_for": tx_raw.get("headwind_for"),
            "tailwind_for": tx_raw.get("tailwind_for"),
            "unstable": _clean(tx_raw.get("unstable")),
        }

        regime_radar = {
            "dominant": _clean(rr_raw.get("dominant")),
            "active": rr_raw.get("active"),
        }

        # Prefer ISO asof; fall back to display-string date normalisation
        asof = _to_iso(raw.get("asof") or raw.get("date"))

        return _display_only({
            "asof": asof,
            "regime": _clean(raw.get("regime")),
            "risk": _clean(raw.get("risk")),
            "favored": raw.get("favored"),
            "dollar_desk": dollar_desk,
            "transmission": transmission,
            "regime_radar": regime_radar,
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("fx_dollar: compose failed — %s", exc)
        return null_out


def _compose_rates_credit(root: "Path | str | None" = None) -> dict:
    """Compose rates_credit lobe from data/bonds/bond_health.json.

    Field list per §5.3 lobe 3 (census-verified).
    """
    repo = _repo_root(root)
    path = repo / "data" / "bonds" / "bond_health.json"

    null_out: dict = {
        "as_of": None,
        "health_score": None,
        "health_label": None,
        "cycle_phase": None,
        "recession_risk": None,
        "drawdown_risk": None,
        "alarms": None,
        "verdict_en": None,
        "fed_path": None,
        "bond_compass": None,
        "bond_cross_asset": None,
        "drivers_for": None,
        "display_only": True,
    }

    raw = _read_json(path)
    if raw is None:
        return null_out

    try:
        fp_raw = raw.get("fed_path") or {}
        bc_raw = raw.get("bond_compass") or {}
        bca_raw = raw.get("bond_cross_asset") or {}

        fed_path = {
            "policy_rate": _clean(fp_raw.get("policy_rate")),
            "implied_bp_12m": _clean(fp_raw.get("implied_bp_12m")),
            "implied_cuts_12m": _clean(fp_raw.get("implied_cuts_12m")),
        }

        bond_compass = {
            "duration": _clean(bc_raw.get("duration")),
            "curve_trade": _clean(bc_raw.get("curve_trade")),
        }

        bond_cross_asset = {
            "verdict_en": _clean(bca_raw.get("verdict_en")),
        }

        return _display_only({
            "as_of": _clean(raw.get("as_of")),
            "health_score": _clean(raw.get("health_score")),
            "health_label": _clean(raw.get("health_label")),
            "cycle_phase": _clean(raw.get("cycle_phase")),
            "recession_risk": _clean(raw.get("recession_risk")),
            "drawdown_risk": _clean(raw.get("drawdown_risk")),
            "alarms": raw.get("alarms"),
            "verdict_en": _clean(raw.get("verdict_en")),
            "fed_path": fed_path,
            "bond_compass": bond_compass,
            "bond_cross_asset": bond_cross_asset,
            "drivers_for": raw.get("drivers_for"),
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("rates_credit: compose failed — %s", exc)
        return null_out


def _compose_global_regimes(
    root: "Path | str | None" = None,
    regime_block: "dict | None" = None,
) -> dict:
    """Compose global_regimes lobe from three regional latest.json files + US regime.

    Field list per §5.3 lobe 4 (census-verified).
    regime_block is the already-composed US regime dict passed from build_world_state
    to avoid re-reading the same file.
    """
    repo = _repo_root(root)

    null_out: dict = {
        "us": None,
        "china": None,
        "hk": None,
        "canada": None,
        "dispersion_note": None,
        "display_only": True,
    }

    try:
        def _read_regional(p: Path, market: str) -> dict | None:
            raw = _read_json(p)
            if raw is None:
                return None
            row: dict = {
                "market": market,
                "date": _to_iso(raw.get("date") or raw.get("asof")),
                "quad": _clean(raw.get("quad")),
                "quad_name": _clean(raw.get("quad_name")),
                "cycle_tag": _clean(raw.get("cycle_tag")),
                "liquidity_overlay": _clean(raw.get("liquidity_overlay")),
                "pending_quad": _clean(raw.get("pending_quad")),
                "confidence": _clean(raw.get("confidence")),
                "stale": False,
            }
            if market == "hk":
                row["risk_state"] = _clean(raw.get("risk_state"))
                row["peg_state"] = _clean(raw.get("peg_state"))
            return row

        china = _read_regional(repo / "data" / "china_regime" / "latest.json", "china")
        hk = _read_regional(repo / "data" / "hk_regime" / "latest.json", "hk")
        canada = _read_regional(repo / "data" / "canada_regime" / "latest.json", "canada")

        # US quad from already-composed regime_block (avoid double read)
        us: dict | None = None
        if isinstance(regime_block, dict):
            us = {
                "market": "us",
                "date": _to_iso(regime_block.get("asof")),
                "quad": _clean(regime_block.get("quad")),
                "quad_name": _clean(regime_block.get("quad_name")),
                "cycle_tag": _clean(regime_block.get("cycle_tag")),
                "liquidity_overlay": _clean(regime_block.get("liquidity_overlay")),
                "confidence": _clean(regime_block.get("confidence")),
                "pending_quad": None,
                "stale": False,
            }

        # Dispersion: count of distinct non-None quads
        quads = [
            (us or {}).get("quad"),
            (china or {}).get("quad"),
            (hk or {}).get("quad"),
            (canada or {}).get("quad"),
        ]
        distinct_quads = len({q for q in quads if q is not None})
        dispersion_note = (
            f"{distinct_quads} distinct quads across US/China/HK/Canada"
        )

        return _display_only({
            "us": us,
            "china": china,
            "hk": hk,
            "canada": canada,
            "dispersion_note": dispersion_note,
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("global_regimes: compose failed — %s", exc)
        return null_out


def _compose_commodity_context(root: "Path | str | None" = None) -> dict:
    """Compose commodity_context lobe from data/commodity/latest.json.

    Field list per §5.3 lobe 5 (census-verified).
    """
    repo = _repo_root(root)
    path = repo / "data" / "commodity" / "latest.json"

    null_out: dict = {
        "asof": None,
        "regime": None,
        "favored": None,
        "assets": None,
        "display_only": True,
    }

    raw = _read_json(path)
    if raw is None:
        return null_out

    try:
        # assets: dict or list — normalise to list[{label, trend, action, conviction}]
        assets_raw = raw.get("assets")
        assets_out: list = []
        if isinstance(assets_raw, dict):
            for name, val in assets_raw.items():
                if not isinstance(val, dict):
                    continue
                assets_out.append({
                    "label": _clean(val.get("label") or name),
                    "trend": _clean(val.get("trend")),
                    "action": _clean(val.get("action")),
                    "conviction": _clean(val.get("conviction")),
                })
        elif isinstance(assets_raw, list):
            for item in assets_raw:
                if not isinstance(item, dict):
                    continue
                assets_out.append({
                    "label": _clean(item.get("label")),
                    "trend": _clean(item.get("trend")),
                    "action": _clean(item.get("action")),
                    "conviction": _clean(item.get("conviction")),
                })

        asof = _to_iso(raw.get("asof") or raw.get("date"))

        return _display_only({
            "asof": asof,
            "regime": _clean(raw.get("regime")),
            "favored": raw.get("favored"),
            "assets": assets_out if assets_out else None,
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("commodity_context: compose failed — %s", exc)
        return null_out


def _compose_intelligence(root: "Path | str | None" = None) -> dict:
    """Compose intelligence lobe from site/intelligence/briefing.json.

    Field list per §5.3 lobe 6 (census-verified).
    """
    repo = _repo_root(root)
    path = repo / "site" / "intelligence" / "briefing.json"

    null_out: dict = {
        "as_of": None,
        "n_universe": None,
        "n_priority": None,
        "n_actionable": None,
        "n_divergences": None,
        "macro_context": None,
        "top_actionable": None,
        "display_only": True,
    }

    raw = _read_json(path)
    if raw is None:
        return null_out

    try:
        mc_raw = raw.get("macro_context") or {}
        macro_ctx = {
            "regime": _clean(mc_raw.get("regime")),
            "posture": _clean(mc_raw.get("posture")),
            "fed_stance": _clean(mc_raw.get("fed_stance")),
        }

        pq = raw.get("priority_queue") or []
        top_actionable = []
        for item in pq[:5]:
            if not isinstance(item, dict):
                continue
            top_actionable.append({
                "ticker": _clean(item.get("ticker")),
                "priority": _clean(item.get("priority")),
                "lean": _clean(item.get("lean")),
                "read": _clean(item.get("read")),
            })

        return _display_only({
            "as_of": _clean(raw.get("as_of")),
            "n_universe": _clean(raw.get("n_universe")),
            "n_priority": _clean(raw.get("n_priority")),
            "n_actionable": _clean(raw.get("n_actionable")),
            "n_divergences": _clean(raw.get("n_divergences")),
            "macro_context": macro_ctx,
            "top_actionable": top_actionable,
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("intelligence: compose failed — %s", exc)
        return null_out


def _compose_macro_deltas(root: "Path | str | None" = None) -> dict:
    """Compose macro_deltas lobe from data/macro_snapshots/transitions.jsonl.

    Returns a gap when the file is absent (build-order independence — the file
    is created by PR-C's build_macro_snapshot; during W1/PR-B it will not exist).

    Field list per §5.3 lobe 7 (census-verified).
    """
    repo = _repo_root(root)
    path = repo / "data" / "macro_snapshots" / "transitions.jsonl"

    null_out: dict = {
        "transitions": None,
        "n_transitions_14d": None,
        "display_only": True,
    }

    if not path.exists():
        # Deliberate gap — file created by PR-C; absence is expected
        return null_out

    try:
        from datetime import timedelta  # noqa: PLC0415

        cutoff = (datetime.now(timezone.utc) - timedelta(days=14)).strftime("%Y-%m-%d")

        transitions: list[dict] = []
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if not isinstance(rec, dict):
                    continue
                asof = rec.get("asof") or rec.get("date") or ""
                if asof >= cutoff:
                    transitions.append({
                        "asof": _clean(asof),
                        "domain": _clean(rec.get("domain")),
                        "field": _clean(rec.get("field")),
                        "from": _clean(rec.get("from_value")),
                        "to": _clean(rec.get("to_value")),
                    })

        # Cap at 20 most-recent entries (already ordered by file append order)
        transitions = transitions[-20:]

        return _display_only({
            "transitions": transitions,
            "n_transitions_14d": len(transitions),
        })
    except Exception as exc:  # noqa: BLE001
        log.warning("macro_deltas: compose failed — %s", exc)
        return null_out


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def build_world_state(
    root: Path | str | None = None,
    now: datetime | None = None,
) -> dict:
    """Compose and return the world_state payload dict (un-stamped).

    Parameters
    ----------
    root:
        Repo root path override.  Defaults to three levels above this file.
    now:
        UTC datetime for the envelope stamp.  Defaults to now.

    Returns
    -------
    dict
        The world_state payload with envelope keys added by stamp().
        Always returns a dict (never raises).  Partial reads produce a
        partial payload with null sub-blocks and a non-empty 'gaps' list.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    repo = _repo_root(root)
    data_dir = repo / "data"
    site_dir = repo / "site"

    gaps: list[str] = []
    sources: dict[str, str | None] = {}

    # ── 1. market_state/latest.json ──────────────────────────────────────────
    ms_path = data_dir / "market_state" / "latest.json"
    ms = _read_json(ms_path)
    if ms is None:
        gaps.append("market_state/latest.json: missing or unreadable")
        verdict_block = None
        radar_block = None
    else:
        verdict_block = _compose_verdict(ms)
        radar_block = _compose_radar(ms)
    sources[str(ms_path.relative_to(repo))] = (ms or {}).get("asof")

    # ── 2. data/regime/latest.json ───────────────────────────────────────────
    reg_path = data_dir / "regime" / "latest.json"
    reg = _read_json(reg_path)
    if reg is None:
        gaps.append("data/regime/latest.json: missing or unreadable")
        reg = {}
    sources[str(reg_path.relative_to(repo))] = reg.get("asof")

    # risk_radar_raw — embedded VERBATIM (byte-untouched deep copy)
    # This is the raw risk_radar sub-object as produced by engine/radar.py.
    # build_feeds.py extracts and publishes this verbatim; any migration of
    # build_feeds to world_state depends on this being IDENTICAL in shape
    # (the 2026-07-02 semis incident is the cautionary tale).
    rr = reg.get("risk_radar")
    risk_radar_raw = copy.deepcopy(rr) if isinstance(rr, dict) else None
    if risk_radar_raw is None:
        gaps.append("data/regime/latest.json:risk_radar: absent")

    regime_block = _compose_regime(reg) if reg else None
    vol_block = _compose_vol(reg) if reg else None
    liquidity_block = _compose_liquidity(reg) if reg else None
    live_overlay_block = _compose_live_overlay(reg) if reg else None

    # ── 3. data/breadth/breadth.parquet ──────────────────────────────────────
    bp_path = data_dir / "breadth" / "breadth.parquet"
    try:
        breadth_block = _compose_breadth(reg, data_dir)
        sources[str(bp_path.relative_to(repo))] = (breadth_block or {}).get("date")
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: breadth compose failed — %s", exc)
        breadth_block = None
        gaps.append(f"data/breadth/breadth.parquet: {exc}")
        sources[str(bp_path.relative_to(repo))] = None

    # ── 4. site/basketdata/oracle_state.json (Oracle-owned, read-only) ───────
    oracle_path = site_dir / "basketdata" / "oracle_state.json"
    oracle = _read_json(oracle_path)
    if oracle is None:
        gaps.append("site/basketdata/oracle_state.json: missing or unreadable")
        rotation_block = None
    else:
        rotation_block = _compose_rotation(oracle)
    sources[str(oracle_path.relative_to(repo))] = (oracle or {}).get("asof")

    # ── 5. data/run_status.json ───────────────────────────────────────────────
    rs_path = data_dir / "run_status.json"
    rs = _read_json(rs_path)
    if rs is None:
        gaps.append("data/run_status.json: missing or unreadable")
        data_health_block = None
    else:
        data_health_block = _compose_data_health(rs)
    sources[str(rs_path.relative_to(repo))] = (rs or {}).get("last_run")

    # ── 6. site/factordata/alerts_triage.json ────────────────────────────────
    at_path = site_dir / "factordata" / "alerts_triage.json"
    at = _read_json(at_path)
    if at is None:
        gaps.append("site/factordata/alerts_triage.json: missing or unreadable")
        alerts_block = None
    else:
        alerts_block = _compose_alerts(at)
    sources[str(at_path.relative_to(repo))] = (at or {}).get("asof")

    # ── 6b. factor_weather lobe (§5.4 + RULING-B fold) ──────────────────────
    # RULING-B: one wiring line; all data loading is inside _compose_factor_weather.
    try:
        factor_weather_block: dict = _compose_factor_weather(root=repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: factor_weather lobe failed — %s", exc)
        gaps.append(f"factor_weather: {exc}")
        factor_weather_block = {
            "style_regime": None,
            "style_regime_pending": None,
            "style_regime_hold_days": None,
            "factor_leader": None,
            "factor_leader_ic": None,
            "etf_pulse_summary": None,
            "ratio_iwf_iwd_20d": None,
            "ratio_qqq_spy_20d": None,
            "ratio_iwm_spy_20d": None,
            "display_only": True,
            "factor_state_as_of": None,  # null on lobe failure (RUL-NW2)
        }
    try:
        options_weather_block: dict = _compose_options_weather(root=repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: options_weather lobe failed — %s", exc)
        gaps.append(f"options_weather: {exc}")
        options_weather_block = {
            "as_of": None, "n_roots": None, "median_iv30": None,
            "median_skew": None, "median_skew_5d_chg": None,
            "share_skew_rising": None, "median_ivspread_rel": None,
            "share_pin_risk": None, "opex_days": None,
            "note": "lobe failed — null fallback", "display_only": True,
        }

    # ── 6c. R5 macro-context lobes (PR-B §5.3) ───────────────────────────────
    # Each lobe is try/except-wrapped at the wiring site; failures produce a
    # null-shaped fallback + gap entry per the _compose_factor_weather pattern.

    # rates_transmission
    _tx_path = data_dir / "transmission" / "latest.json"
    try:
        rates_transmission_block: dict = _compose_rates_transmission(root=repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: rates_transmission lobe failed — %s", exc)
        gaps.append(f"rates_transmission: {exc}")
        rates_transmission_block = {"asof": None, "scored_status": None, "calibrated": None,
                                    "state": None, "headwinds": None, "tailwinds": None,
                                    "yield_curve": None, "yield_curve_source": "transmission",
                                    "display_only": True}
    sources[str(_tx_path.relative_to(repo))] = (rates_transmission_block or {}).get("asof")
    if rates_transmission_block.get("asof") is None and _tx_path.exists():
        pass  # file present but asof absent — not a gap at the lobe level
    elif not _tx_path.exists():
        gaps.append("data/transmission/latest.json: missing or unreadable")

    # fx_dollar
    _fx_path = data_dir / "forex" / "latest.json"
    try:
        fx_dollar_block: dict = _compose_fx_dollar(root=repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: fx_dollar lobe failed — %s", exc)
        gaps.append(f"fx_dollar: {exc}")
        fx_dollar_block = {"asof": None, "regime": None, "risk": None, "favored": None,
                           "dollar_desk": None, "transmission": None, "regime_radar": None,
                           "display_only": True}
    sources[str(_fx_path.relative_to(repo))] = (fx_dollar_block or {}).get("asof")
    if not _fx_path.exists():
        gaps.append("data/forex/latest.json: missing or unreadable")

    # rates_credit
    _bonds_path = data_dir / "bonds" / "bond_health.json"
    try:
        rates_credit_block: dict = _compose_rates_credit(root=repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: rates_credit lobe failed — %s", exc)
        gaps.append(f"rates_credit: {exc}")
        rates_credit_block = {"as_of": None, "health_score": None, "health_label": None,
                              "cycle_phase": None, "recession_risk": None, "drawdown_risk": None,
                              "alarms": None, "verdict_en": None, "fed_path": None,
                              "bond_compass": None, "bond_cross_asset": None, "drivers_for": None,
                              "display_only": True}
    sources[str(_bonds_path.relative_to(repo))] = (rates_credit_block or {}).get("as_of")
    if not _bonds_path.exists():
        gaps.append("data/bonds/bond_health.json: missing or unreadable")

    # global_regimes — pass already-composed regime_block to avoid double read
    _china_path = data_dir / "china_regime" / "latest.json"
    _hk_path = data_dir / "hk_regime" / "latest.json"
    _canada_path = data_dir / "canada_regime" / "latest.json"
    try:
        global_regimes_block: dict = _compose_global_regimes(
            root=repo, regime_block=regime_block
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: global_regimes lobe failed — %s", exc)
        gaps.append(f"global_regimes: {exc}")
        global_regimes_block = {"us": None, "china": None, "hk": None, "canada": None,
                                "dispersion_note": None, "display_only": True}
    gr = global_regimes_block or {}
    sources[str(_china_path.relative_to(repo))] = (
        (gr.get("china") or {}).get("date") if isinstance(gr.get("china"), dict) else None
    )
    sources[str(_hk_path.relative_to(repo))] = (
        (gr.get("hk") or {}).get("date") if isinstance(gr.get("hk"), dict) else None
    )
    sources[str(_canada_path.relative_to(repo))] = (
        (gr.get("canada") or {}).get("date") if isinstance(gr.get("canada"), dict) else None
    )
    for _rp, _label in [
        (_china_path, "data/china_regime/latest.json"),
        (_hk_path, "data/hk_regime/latest.json"),
        (_canada_path, "data/canada_regime/latest.json"),
    ]:
        if not _rp.exists():
            gaps.append(f"{_label}: missing or unreadable")

    # commodity_context
    _commodity_path = data_dir / "commodity" / "latest.json"
    try:
        commodity_context_block: dict = _compose_commodity_context(root=repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: commodity_context lobe failed — %s", exc)
        gaps.append(f"commodity_context: {exc}")
        commodity_context_block = {"asof": None, "regime": None, "favored": None,
                                   "assets": None, "display_only": True}
    sources[str(_commodity_path.relative_to(repo))] = (commodity_context_block or {}).get("asof")
    if not _commodity_path.exists():
        gaps.append("data/commodity/latest.json: missing or unreadable")

    # intelligence
    _briefing_path = site_dir / "intelligence" / "briefing.json"
    try:
        intelligence_block: dict = _compose_intelligence(root=repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: intelligence lobe failed — %s", exc)
        gaps.append(f"intelligence: {exc}")
        intelligence_block = {"as_of": None, "n_universe": None, "n_priority": None,
                              "n_actionable": None, "n_divergences": None,
                              "macro_context": None, "top_actionable": None, "display_only": True}
    sources[str(_briefing_path.relative_to(repo))] = (intelligence_block or {}).get("as_of")
    if not _briefing_path.exists():
        gaps.append("site/intelligence/briefing.json: missing or unreadable")

    # macro_deltas
    _transitions_path = data_dir / "macro_snapshots" / "transitions.jsonl"
    try:
        macro_deltas_block: dict = _compose_macro_deltas(root=repo)
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: macro_deltas lobe failed — %s", exc)
        gaps.append(f"macro_deltas: {exc}")
        macro_deltas_block = {"transitions": None, "n_transitions_14d": None, "display_only": True}
    # transitions.jsonl absence is an expected gap (PR-C creates this file)
    if not _transitions_path.exists():
        gaps.append("data/macro_snapshots/transitions.jsonl: absent (PR-C)")

    # ── 7. Contradictions summary (W4) ───────────────────────────────────────
    contradictions_block: dict | None = None
    try:
        from engine.neuralweb.contradictions import detect_contradictions  # noqa: PLC0415
        contra_records, contra_gaps = detect_contradictions(root=repo)
        by_severity: dict[str, int] = {}
        for rec in contra_records:
            sev = rec.get("severity") or "unknown"
            by_severity[sev] = by_severity.get(sev, 0) + 1
        top5 = [rec.get("pair_id") for rec in contra_records[:5]]
        contradictions_block = {
            "n": len(contra_records),
            "by_severity": by_severity,
            "top_pair_ids": top5,
            "gaps": contra_gaps,
            "display_only": True,
            "note": (
                "W4 contradiction detector: 6 typed pairs "
                "(regime-vs-market_state, regime_vector-vs-risk_radar, "
                "oracle-vs-sector_central, vol_regime-vs-market_state, "
                "briefing-divergences, cross_asset_confirm-diverge).  "
                "Display-only; no gate, no rank raise."
            ),
        }
        if contra_gaps:
            gaps.extend([f"contradictions/{g}" for g in contra_gaps])
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: contradictions block failed — %s", exc)
        gaps.append(f"contradictions: {exc}")

    # ── Assemble payload ──────────────────────────────────────────────────────
    payload: dict[str, Any] = {
        "verdict": verdict_block,
        "radar": radar_block,
        "risk_radar_raw": risk_radar_raw,
        "regime": regime_block,
        "vol": vol_block,
        "breadth": breadth_block,
        "rotation": rotation_block,
        "liquidity": liquidity_block,
        "data_health": data_health_block,
        "alerts": alerts_block,
        "factor_weather": factor_weather_block,  # §5.4 wiring line (RULING-B)
        "options_weather": options_weather_block,  # Options→NW W-B wiring line (RO-1)
        # R5 macro-context lobes (PR-B §5.3) — display_only=True on each
        "rates_transmission": rates_transmission_block,
        "fx_dollar": fx_dollar_block,
        "rates_credit": rates_credit_block,
        "global_regimes": global_regimes_block,
        "commodity_context": commodity_context_block,
        "intelligence": intelligence_block,
        "macro_deltas": macro_deltas_block,
        "qi": None,
        "qi_note": (
            "pending joint QI border ruling (masterplan W1) — "
            "QI produces the aggregate, Neural Web consumes; "
            "do not aggregate raw qbus here (border law §9)"
        ),
        "live_overlay": live_overlay_block,
        "contradictions": contradictions_block,
        "gaps": gaps,
        "sources": sources,
    }

    # ── Stamp with envelope (first producer adoption) ─────────────────────────
    try:
        from engine.neuralweb.envelope import stamp
        from engine.neuralweb.synapse import load_registry
        registry = load_registry(repo)
        payload = stamp(payload, artifact_id="world-state", registry=registry, now=now)
    except Exception as exc:  # noqa: BLE001
        log.error("world_state: envelope stamp failed — %s", exc)
        # Still return the payload without an envelope rather than aborting.

    return payload


def build_and_write(
    root: Path | str | None = None,
    now: datetime | None = None,
    out_path: Path | str | None = None,
) -> dict:
    """Compose world_state, apply stamp_if_changed, write JSON, return payload.

    Parameters
    ----------
    root:
        Repo root override.
    now:
        UTC datetime for the envelope stamp.
    out_path:
        Destination path override.  Defaults to data/neuralweb/world_state.json
        inside the repo root.

    Returns
    -------
    dict
        The (possibly unchanged) stamped payload.

    Raises
    ------
    OSError
        Only if writing the file itself fails.  Sub-block read failures are
        absorbed (fail-open) and reported in payload['gaps'].
    """
    repo = _repo_root(root)

    if out_path is None:
        dest = repo / "data" / "neuralweb" / "world_state.json"
    else:
        dest = Path(out_path)

    dest.parent.mkdir(parents=True, exist_ok=True)

    # Read previous version for stamp_if_changed byte-identity fast-path.
    prev: dict | None = None
    if dest.exists():
        try:
            prev = json.loads(dest.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            prev = None

    new_payload = build_world_state(root=repo, now=now)

    # Apply stamp_if_changed so unchanged days are byte-identical on disk.
    try:
        from engine.neuralweb.envelope import stamp_if_changed
        from engine.neuralweb.synapse import load_registry
        registry = load_registry(repo)
        final = stamp_if_changed(
            new_payload, prev,
            artifact_id="world-state",
            registry=registry,
            now=now or datetime.now(timezone.utc),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("world_state: stamp_if_changed failed — %s; using new payload", exc)
        final = new_payload

    dest.write_text(
        json.dumps(final, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return final
