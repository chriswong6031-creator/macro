"""China Market State — sovereign spine (W6 of China System Program).

Authority: context_only (CN-SYS-R1).  No scores, ranks, gates, or origination.
Schema: china_market_state.v1

This module assembles the per-lobe JSON artifacts produced by the W1–W4 engines
into a single daily spine packet.  Every lobe block is **nullable**: if the
source artifact is absent or malformed the block is null and the lobe's gap is
recorded in data_gaps.  The spine never raises on a missing lobe (CN-SYS-R11
degrade-don't-crash law).

NO FUSED SCORE (CN-SYS-R13): the spine emits per-lobe states + cross-lobe
contradictions; it never computes a weighted composite.

LLM surfaces (deepseek brief, intel narratives) are NEVER fed into the spine
(CN-SYS-R14): the spine is closed under deterministic inputs.

INPUTS — all nullable:
  phase        : site/chinastatedata/cycle_phase.json   (W3, may not exist yet)
  participation: site/chinastatedata/participation.json (W2, merged)
  microstructure: site/chinastatedata/microstructure.json (W1, merged)
  policy       : site/chinastatedata/policy_transmission.json (W4, merged)
  rotation     : data/china_sector_cycles/leg_context.json + data/baskets_china_ths/latest.json
  macro        : data/china_regime/latest.json
  external     : data/china_yield/rates.parquet + data/china_cgb_curve/cgb.parquet
                 + data/forex/latest.json (USDCNH)
  allocation   : data/china_regime/china_alloc_latest.json

OUTPUTS:
  data/china_state/market_state.json
  site/chinastatedata/market_state.json

CROSS-LOBE CONTRADICTIONS (deterministic, CN-SYS-R13):
  Computed from lobe fields only; never averaged into a score.
  1. participation_risk_vs_phase: participation.risk in {frothy, fire_sale} while
     phase.phase in {POLICY_PUT, LIQUIDITY_IGNITION} — contradicts risk-on impulse.
  2. policy_easing_vs_participation: policy_impulse == easing while
     participation.who_controls == margin — margin debt rising during easing
     may signal excess leverage ahead of the impulse's transmission.
  3. external_cnh_vs_macro: USDCNH quote > 7.25 while macro.quad in {Q1, Q2}
     (reflation/recovery) — currency stress contradicts domestic macro signal.
  4. microstructure_chase_vs_participation: microstructure has chase_veto names
     while participation.regime in {dormant, institutional_accumulation} —
     theme-level chase pressure in a low-participation tape.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

SCHEMA = "china_market_state.v1"

_AUTHORITY = {
    "tier": "context_only",
    "why": [
        "CN-SYS-R1: every W6-spine artifact is context_only",
        "CN-SYS-R13: no fused score — per-lobe states + contradictions only",
        "CN-SYS-R14: LLM surfaces never feed the spine",
    ],
    "cannot_do": ["rank", "size", "gate", "originate"],
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_str() -> str:
    return date.today().isoformat()


def _read_json(path: Path) -> dict | None:
    """Read a JSON file; return None (never raise) on any error."""
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        log.warning("Could not read %s: %s", path, exc)
        return None


def _read_parquet(path: Path) -> Any:
    """Read a parquet file; return None on any error."""
    if not path.exists():
        return None
    try:
        import pandas as pd
        return pd.read_parquet(path)
    except Exception as exc:
        log.warning("Could not read %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# per-lobe assemblers — each returns (block_dict_or_None, list_of_gap_strings)
# ---------------------------------------------------------------------------

def _build_phase_block(site_dir: Path) -> tuple[dict | None, list[str]]:
    """Load cycle_phase.json emitted by W3 (may not exist in parallel builds)."""
    path = site_dir / "cycle_phase.json"
    raw = _read_json(path)
    if raw is None:
        return None, ["phase: cycle_phase.json absent (W3 parallel build)"]

    try:
        block = {
            "phase": raw.get("phase"),
            "confidence": raw.get("confidence"),
            "as_of": raw.get("as_of") or raw.get("date"),
            "evidence": raw.get("evidence", []),
            "contradictions": raw.get("contradictions", []),
            "falsifiers": raw.get("falsifiers", []),
        }
        gaps = raw.get("data_gaps", [])
        return block, [f"phase: {g}" for g in gaps]
    except Exception as exc:
        log.warning("phase block assembly failed: %s", exc)
        return None, [f"phase: assembly error ({exc})"]


def _build_participation_block(site_dir: Path) -> tuple[dict | None, list[str]]:
    """Load participation.json emitted by W2."""
    path = site_dir / "participation.json"
    raw = _read_json(path)
    if raw is None:
        return None, ["participation: participation.json absent"]

    try:
        block = {
            "as_of": raw.get("date"),
            "regime": raw.get("regime"),
            "who_controls": raw.get("who_controls"),
            "risk": raw.get("risk"),
            "turnover_z20": raw.get("turnover_z20"),
            "turnover_z60": raw.get("turnover_z60"),
            "margin_balance": raw.get("margin_balance"),
            "margin_chg_5d": raw.get("margin_chg_5d"),
            "margin_to_mcap": raw.get("margin_to_mcap"),
            "zt_breadth": raw.get("zt_breadth"),
            "failed_seal_ratio": raw.get("failed_seal_ratio"),
            "southbound_net": raw.get("southbound_net"),
            "southbound_z": raw.get("southbound_z"),
            "qvix": raw.get("qvix"),
            "qvix_z": raw.get("qvix_z"),
            "evidence": raw.get("evidence", []),
            "contradictions": raw.get("contradictions", []),
        }
        gaps = raw.get("data_gaps", [])
        return block, [f"participation: {g}" for g in gaps]
    except Exception as exc:
        log.warning("participation block assembly failed: %s", exc)
        return None, [f"participation: assembly error ({exc})"]


def _build_microstructure_block(site_dir: Path) -> tuple[dict | None, list[str]]:
    """Load microstructure.json emitted by W1.

    Exposes the aggregate block only; name_packets are numerous (122+) and
    would inflate the spine.  A names_ref pointer is included so consumers
    can load the full per-name data when needed.
    """
    path = site_dir / "microstructure.json"
    raw = _read_json(path)
    if raw is None:
        return None, ["microstructure: microstructure.json absent"]

    try:
        agg = raw.get("latest_aggregate", {}) or {}
        # Count chase-veto names from the packets list for the summary
        packets = raw.get("name_packets", []) or []
        chase_veto_count = sum(
            1 for p in packets
            if isinstance(p, dict) and p.get("chase_veto", {}).get("flag")
        )
        fillable_count = sum(
            1 for p in packets
            if isinstance(p, dict) and p.get("fillable") is True
        )
        block = {
            "as_of": raw.get("as_of"),
            "aggregate": {
                "date": agg.get("date"),
                "limit_up_count": agg.get("limit_up_count"),
                "limit_down_count": agg.get("limit_down_count"),
                "sealed_up_close": agg.get("sealed_up_close"),
                "failed_up_seal_count": agg.get("failed_up_seal_count"),
                "lianban_2plus": agg.get("lianban_2plus"),
                "lianban_max": agg.get("lianban_max"),
                "universe_n": agg.get("universe_n"),
                "limit_up_breadth_pct": agg.get("limit_up_breadth_pct"),
                "limit_down_breadth_pct": agg.get("limit_down_breadth_pct"),
            },
            "name_summary": {
                "n_packets": len(packets),
                "chase_veto_count": chase_veto_count,
                "fillable_count": fillable_count,
            },
            "names_ref": "site/chinastatedata/microstructure.json#name_packets",
        }
        gaps = raw.get("data_gaps", [])
        return block, [f"microstructure: {g}" for g in gaps]
    except Exception as exc:
        log.warning("microstructure block assembly failed: %s", exc)
        return None, [f"microstructure: assembly error ({exc})"]


def _build_policy_block(site_dir: Path) -> tuple[dict | None, list[str]]:
    """Load policy_transmission.json emitted by W4."""
    path = site_dir / "policy_transmission.json"
    raw = _read_json(path)
    if raw is None:
        return None, ["policy: policy_transmission.json absent"]

    try:
        recent_events = raw.get("recent_events", []) or []
        block = {
            "as_of": raw.get("asof"),
            "policy_impulse": raw.get("policy_impulse"),
            "transmission_channel": raw.get("transmission_channel", []),
            "recent_event_count": len(recent_events),
            "recent_events_summary": [
                {
                    "source": e.get("source"),
                    "kind": e.get("kind"),
                    "title": e.get("title"),
                    "ts": e.get("ts"),
                }
                for e in recent_events[:5]  # top-5 for the spine summary
            ],
            "staleness": raw.get("staleness", {}),
        }
        gaps = raw.get("data_gaps", [])
        return block, [f"policy: {g}" for g in gaps]
    except Exception as exc:
        log.warning("policy block assembly failed: %s", exc)
        return None, [f"policy: assembly error ({exc})"]


def _build_rotation_block(data_dir: Path) -> tuple[dict | None, list[str]]:
    """Summarise sector phase distribution from leg_context.json + THS heat."""
    gaps: list[str] = []

    # Sector phase distribution
    leg_path = data_dir / "china_sector_cycles" / "leg_context.json"
    raw_leg = _read_json(leg_path)
    phase_dist: dict[str, int] = {}
    leaders: list[str] = []
    laggards: list[str] = []
    market_signals: list[str] = []
    as_of: str | None = None

    if raw_leg is None:
        gaps.append("rotation: leg_context.json absent")
    else:
        try:
            from collections import Counter
            phases = Counter(v.get("phase") for v in raw_leg.values() if isinstance(v, dict))
            phase_dist = dict(phases)

            # Extract signals from any sector's now_ctx
            for v in raw_leg.values():
                if isinstance(v, dict) and isinstance(v.get("now_ctx"), dict):
                    ctx = v["now_ctx"]
                    leaders = ctx.get("leaders", [])[:3]
                    laggards = ctx.get("laggards", [])[:3]
                    market_signals = ctx.get("signals", [])[:3]
                    break
        except Exception as exc:
            gaps.append(f"rotation: leg_context parse error ({exc})")

    # THS concept heat summary
    ths_path = data_dir / "baskets_china_ths" / "latest.json"
    raw_ths = _read_json(ths_path)
    ths_heat: dict | None = None

    if raw_ths is None:
        gaps.append("rotation: baskets_china_ths/latest.json absent")
    else:
        try:
            ths_as_of = raw_ths.get("as_of")
            as_of = ths_as_of
            baskets = raw_ths.get("baskets") or []
            if isinstance(baskets, list) and baskets:
                # Sort by ret_60d descending; top-5 hot, bottom-5 cold
                sorted_b = sorted(
                    [b for b in baskets if b.get("ret_60d") is not None],
                    key=lambda x: x["ret_60d"],
                    reverse=True,
                )
                above_200d_count = sum(1 for b in baskets if b.get("above_200d"))
                ths_heat = {
                    "as_of": ths_as_of,
                    "basket_count": len(baskets),
                    "above_200d_pct": round(above_200d_count / len(baskets) * 100, 1)
                    if baskets else None,
                    "hot_baskets": [
                        {"id": b["id"], "ret_60d": b["ret_60d"]}
                        for b in sorted_b[:5]
                    ],
                    "cold_baskets": [
                        {"id": b["id"], "ret_60d": b["ret_60d"]}
                        for b in sorted_b[-5:]
                    ],
                }
        except Exception as exc:
            gaps.append(f"rotation: THS basket parse error ({exc})")

    if not phase_dist and not ths_heat:
        return None, gaps

    block = {
        "as_of": as_of,
        "sector_phase_distribution": phase_dist,
        "sector_leaders": leaders,
        "sector_laggards": laggards,
        "market_signals": market_signals,
        "ths_heat": ths_heat,
    }
    return block, gaps


def _build_macro_block(data_dir: Path) -> tuple[dict | None, list[str]]:
    """Load quad / liquidity_overlay / cycle_tag from china_regime/latest.json."""
    path = data_dir / "china_regime" / "latest.json"
    raw = _read_json(path)
    if raw is None:
        return None, ["macro: china_regime/latest.json absent"]

    try:
        cond = raw.get("conditions", {}) or {}
        block = {
            "as_of": raw.get("date"),
            "quad": raw.get("quad"),
            "quad_name": raw.get("quad_name"),
            "liquidity_overlay": raw.get("liquidity_overlay"),
            "cycle_tag": raw.get("cycle_tag"),
            "pending_quad": raw.get("pending_quad"),
            "pending_days": raw.get("pending_days"),
            "confirming": raw.get("confirming", []),
            "contradicting": raw.get("contradicting", []),
            "conditions": {
                "roro": cond.get("roro"),
                "recession": cond.get("recession"),
                "drawdown_risk": cond.get("drawdown_risk"),
            },
        }
        return block, []
    except Exception as exc:
        log.warning("macro block assembly failed: %s", exc)
        return None, [f"macro: assembly error ({exc})"]


def _build_external_block(data_dir: Path) -> tuple[dict | None, list[str]]:
    """Summarise CN yield curve, CGBcurve, and USDCNH from orphaned accruers."""
    gaps: list[str] = []

    # ── CN yield curve (rates.parquet) ──────────────────────────────────────
    rates_df = _read_parquet(data_dir / "china_yield" / "rates.parquet")
    yield_summary: dict | None = None
    if rates_df is None:
        gaps.append("external: china_yield/rates.parquet absent")
    elif rates_df.empty:
        gaps.append("external: china_yield/rates.parquet empty")
    else:
        try:
            last = rates_df.dropna(how="all").iloc[-1] if not rates_df.dropna(how="all").empty else None
            if last is not None:
                idx = rates_df.index
                as_of = str(idx[-1].date()) if hasattr(idx[-1], "date") else str(idx[-1])
                # staleness = calendar days since last bar
                from datetime import date as _date
                try:
                    last_bar_date = idx[-1].date() if hasattr(idx[-1], "date") else None
                    stale_days = (_date.today() - last_bar_date).days if last_bar_date else None
                except Exception:
                    stale_days = None
                yield_summary = {
                    "as_of": as_of,
                    "staleness_days": stale_days,
                    "cn_10y": _safe_float(last.get("cn_10y")),
                    "cn_2y": _safe_float(last.get("cn_2y")),
                    "cn_slope_10_2": _safe_float(last.get("cn_slope_10_2")),
                    "cn_us_10y_spread": _safe_float(last.get("cn_us_10y_spread")),
                }
        except Exception as exc:
            gaps.append(f"external: rates.parquet parse error ({exc})")

    # ── CGB full curve (cgb.parquet) ─────────────────────────────────────────
    cgb_df = _read_parquet(data_dir / "china_cgb_curve" / "cgb.parquet")
    cgb_summary: dict | None = None
    if cgb_df is None:
        gaps.append("external: china_cgb_curve/cgb.parquet absent")
    elif cgb_df.empty:
        gaps.append("external: china_cgb_curve/cgb.parquet empty")
    else:
        try:
            last_row = cgb_df.dropna(how="all").iloc[-1] if not cgb_df.dropna(how="all").empty else None
            if last_row is not None:
                idx = cgb_df.index
                as_of = str(idx[-1].date()) if hasattr(idx[-1], "date") else str(idx[-1])
                from datetime import date as _date
                try:
                    last_bar_date = idx[-1].date() if hasattr(idx[-1], "date") else None
                    stale_days = (_date.today() - last_bar_date).days if last_bar_date else None
                except Exception:
                    stale_days = None
                # slope = 10y minus 3m (full curve measure)
                y10 = _safe_float(last_row.get("y10"))
                m3 = _safe_float(last_row.get("m3"))
                slope = round(y10 - m3, 4) if (y10 is not None and m3 is not None) else None
                cgb_summary = {
                    "as_of": as_of,
                    "staleness_days": stale_days,
                    "m3": m3,
                    "y1": _safe_float(last_row.get("y1")),
                    "y5": _safe_float(last_row.get("y5")),
                    "y10": y10,
                    "y30": _safe_float(last_row.get("y30")),
                    "slope_10y_3m": slope,
                }
        except Exception as exc:
            gaps.append(f"external: cgb.parquet parse error ({exc})")

    # ── USDCNH from forex/latest.json ───────────────────────────────────────
    usdcnh: dict | None = None
    forex_raw = _read_json(data_dir / "forex" / "latest.json")
    if forex_raw is None:
        gaps.append("external: forex/latest.json absent (USDCNH unavailable)")
    else:
        try:
            pairs = forex_raw.get("pairs") or {}
            if isinstance(pairs, dict) and "USDCNH" in pairs:
                p = pairs["USDCNH"]
                usdcnh = {
                    "quote": _safe_float(p.get("quote")),
                    "chg_pct": _safe_float(p.get("chg")),
                    "as_of": forex_raw.get("date"),
                }
            else:
                gaps.append("external: USDCNH not in forex/latest.json pairs")
        except Exception as exc:
            gaps.append(f"external: USDCNH parse error ({exc})")

    # DXY: read from forex/latest.json pairs.DXY (added by build_forex B1 lane).
    # B3 item 8: when present, use to distinguish broad-dollar move vs CNH-specific stress.
    # Keep exact existing fallback (dxy=None) when the key is absent — no behaviour change
    # until B1 ships the key on the next nightly.
    dxy: dict | None = None
    if forex_raw is not None:
        try:
            _pairs = forex_raw.get("pairs") or {}
            if isinstance(_pairs, dict) and "DXY" in _pairs:
                _dxy_p = _pairs["DXY"]
                dxy = {
                    "quote": _safe_float(_dxy_p.get("quote")),
                    "chg": _safe_float(_dxy_p.get("chg")),
                    "label": _dxy_p.get("label") or "DXY",
                }
            else:
                # DXY not yet exported — documented gap (will clear after B1 lands)
                gaps.append("external: DXY not yet in forex/latest.json pairs (pending B1)")
        except Exception as exc:
            gaps.append(f"external: DXY parse error ({exc})")
    else:
        gaps.append("external: DXY not in current forex/latest.json (no dedicated store)")

    if yield_summary is None and cgb_summary is None and usdcnh is None:
        return None, gaps

    block = {
        "yield_curve": yield_summary,
        "cgb_curve": cgb_summary,
        "usdcnh": usdcnh,
        "dxy": dxy,  # B3: now read from pairs.DXY when present; None if absent
    }
    return block, gaps


def _build_allocation_block(data_dir: Path) -> tuple[dict | None, list[str]]:
    """Load china_alloc_latest.json from china_regime/."""
    path = data_dir / "china_regime" / "china_alloc_latest.json"
    raw = _read_json(path)
    if raw is None:
        # Fallback path
        path2 = data_dir / "allocation" / "latest_china.json"
        raw = _read_json(path2)
        if raw is None:
            return None, ["allocation: neither china_alloc_latest.json nor allocation/latest_china.json found"]

    try:
        block = {
            "as_of": raw.get("date"),
            "variant": raw.get("variant"),
            "label_en": raw.get("label_en"),
            "label_zh": raw.get("label_zh"),
            "growth_w": raw.get("growth_w"),
            "defensive_w": raw.get("defensive_w"),
            "band": raw.get("band"),
        }
        return block, []
    except Exception as exc:
        log.warning("allocation block assembly failed: %s", exc)
        return None, [f"allocation: assembly error ({exc})"]


# ---------------------------------------------------------------------------
# Cross-lobe contradiction detector (CN-SYS-R13)
# ---------------------------------------------------------------------------

def _compute_contradictions(
    phase: dict | None,
    participation: dict | None,
    microstructure: dict | None,
    policy: dict | None,
    macro: dict | None,
    external: dict | None,
) -> list[str]:
    """Return list of cross-lobe contradiction strings (deterministic, text only)."""
    contradictions: list[str] = []

    # 1. participation.risk {frothy,fire_sale} while phase.phase in recovery phases
    if participation and phase:
        p_risk = participation.get("risk")
        ph_phase = phase.get("phase")
        if p_risk in {"frothy", "fire_sale"} and ph_phase in {
            "POLICY_PUT", "LIQUIDITY_IGNITION"
        }:
            contradictions.append(
                f"participation_risk_vs_phase: participation.risk={p_risk!r} "
                f"contradicts phase={ph_phase!r} (risk-on impulse vs elevated stress)"
            )

    # 2. policy easing + margin acceleration
    if policy and participation:
        pol_imp = policy.get("policy_impulse")
        who_ctrl = participation.get("who_controls")
        if pol_imp == "easing" and who_ctrl == "margin":
            contradictions.append(
                "policy_easing_vs_participation: policy_impulse=easing while "
                "who_controls=margin — leverage rising into easing impulse "
                "(transmission lag or excess risk-taking)"
            )

    # 3. USDCNH stress vs domestic recovery quad
    # B3 item 8: when DXY is present, distinguish broad-dollar move vs CNH-specific stress.
    # Keep the exact existing fallback when DXY absent (dxy=None → original message).
    if external and macro:
        usdcnh_info = external.get("usdcnh") or {}
        cnh_quote = usdcnh_info.get("quote")
        quad = macro.get("quad")
        if cnh_quote is not None and quad in {"Q1", "Q2"} and cnh_quote > 7.25:
            dxy_info = external.get("dxy") or {}
            dxy_chg = dxy_info.get("chg") if isinstance(dxy_info, dict) else None
            if dxy_chg is not None and dxy_chg > 0:
                # DXY also rising — broad dollar move, CNH weakness is partly USD-driven
                _cnh_ctx = (
                    "currency weakness partly reflects broad-dollar strength "
                    f"(DXY +{dxy_chg:.2f}%); CNH-specific pressure may be smaller"
                )
            elif dxy_chg is not None and dxy_chg <= 0:
                # DXY flat/falling — CNH weakness is CNH-specific, not a broad-dollar event
                _cnh_ctx = (
                    "currency weakness is CNH-specific — DXY is flat/falling, "
                    "so this is not a broad-dollar event"
                )
            else:
                # DXY absent — keep the exact original message
                _cnh_ctx = "currency weakness contradicts domestic recovery signal"
            contradictions.append(
                f"external_cnh_vs_macro: USDCNH={cnh_quote:.4f} (>7.25 stress threshold) "
                f"while macro.quad={quad!r} (recovery/reflation) — {_cnh_ctx}"
            )

    # 4. microstructure chase veto + low participation
    if microstructure and participation:
        chase_ct = (microstructure.get("name_summary") or {}).get("chase_veto_count", 0)
        regime = participation.get("regime")
        if chase_ct and chase_ct > 0 and regime in {
            "dormant", "institutional_accumulation"
        }:
            contradictions.append(
                f"microstructure_chase_vs_participation: {chase_ct} names carry "
                f"chase_veto while participation.regime={regime!r} "
                "(theme-level chase pressure in a low-participation tape — "
                "theme breadth may be narrow)"
            )

    return contradictions


# ---------------------------------------------------------------------------
# Evidence builder — cross-lobe alignment signals
# ---------------------------------------------------------------------------

def _compute_evidence(
    phase: dict | None,
    participation: dict | None,
    policy: dict | None,
    macro: dict | None,
) -> list[str]:
    """Collect cross-lobe alignment signals as evidence strings."""
    evidence: list[str] = []

    if macro:
        quad = macro.get("quad")
        liq = macro.get("liquidity_overlay")
        if quad and liq:
            evidence.append(f"macro: quad={quad} ({macro.get('quad_name')}) liquidity={liq}")
        for sig in (macro.get("confirming") or [])[:3]:
            evidence.append(f"macro_confirming: {sig}")

    if policy:
        imp = policy.get("policy_impulse")
        channels = policy.get("transmission_channel") or []
        if imp:
            evidence.append(
                f"policy: impulse={imp}"
                + (f" channels={channels}" if channels else "")
            )

    if participation:
        reg = participation.get("regime")
        risk = participation.get("risk")
        who = participation.get("who_controls")
        if reg:
            evidence.append(
                f"participation: regime={reg} who_controls={who} risk={risk}"
            )
        for e in (participation.get("evidence") or [])[:2]:
            evidence.append(f"participation_evidence: {e}")

    if phase:
        ph = phase.get("phase")
        conf = phase.get("confidence")
        if ph:
            evidence.append(f"phase: {ph}" + (f" confidence={conf}" if conf else ""))
        for e in (phase.get("evidence") or [])[:2]:
            evidence.append(f"phase_evidence: {e}")

    return evidence


# ---------------------------------------------------------------------------
# Falsifiers pass-through from phase block (CN-SYS-R5)
# ---------------------------------------------------------------------------

def _collect_falsifiers(phase: dict | None) -> list[dict]:
    if phase is None:
        return []
    return phase.get("falsifiers") or []


# ---------------------------------------------------------------------------
# Main assembler
# ---------------------------------------------------------------------------

def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if f != f else f  # NaN guard
    except (TypeError, ValueError):
        return None


def build(repo_root: Path) -> dict:
    """Assemble the spine packet from all lobe artifacts.

    Returns the packet dict (also suitable for JSON serialisation).
    Never raises; degrades to null blocks with data_gaps entries.
    """
    site_cn = repo_root / "site" / "chinastatedata"
    data_dir = repo_root / "data"

    all_gaps: list[str] = []

    # ── lobes ────────────────────────────────────────────────────────────────
    phase_block, phase_gaps = _build_phase_block(site_cn)
    all_gaps.extend(phase_gaps)

    participation_block, part_gaps = _build_participation_block(site_cn)
    all_gaps.extend(part_gaps)

    micro_block, micro_gaps = _build_microstructure_block(site_cn)
    all_gaps.extend(micro_gaps)

    policy_block, policy_gaps = _build_policy_block(site_cn)
    all_gaps.extend(policy_gaps)

    rotation_block, rot_gaps = _build_rotation_block(data_dir)
    all_gaps.extend(rot_gaps)

    macro_block, macro_gaps = _build_macro_block(data_dir)
    all_gaps.extend(macro_gaps)

    external_block, ext_gaps = _build_external_block(data_dir)
    all_gaps.extend(ext_gaps)

    alloc_block, alloc_gaps = _build_allocation_block(data_dir)
    all_gaps.extend(alloc_gaps)

    # ── cross-lobe analytics ─────────────────────────────────────────────────
    contradictions = _compute_contradictions(
        phase_block, participation_block, micro_block,
        policy_block, macro_block, external_block,
    )
    evidence = _compute_evidence(
        phase_block, participation_block, policy_block, macro_block,
    )
    falsifiers = _collect_falsifiers(phase_block)

    packet = {
        "schema": SCHEMA,
        "as_of": _today_str(),
        "generated_utc": _now_utc(),
        "authority": _AUTHORITY,
        # ── lobe blocks (each nullable) ──────────────────────────────────────
        "phase": phase_block,
        "participation": participation_block,
        "microstructure": micro_block,
        "policy": policy_block,
        "rotation": rotation_block,
        "macro": macro_block,
        "external": external_block,
        "allocation": alloc_block,
        # ── cross-lobe outputs ───────────────────────────────────────────────
        "evidence": evidence,
        "contradictions": contradictions,
        "falsifiers": falsifiers,
        "data_gaps": all_gaps,
    }

    log.info(
        "spine assembled: lobes_present=%d/8 contradictions=%d data_gaps=%d",
        sum(1 for b in [
            phase_block, participation_block, micro_block, policy_block,
            rotation_block, macro_block, external_block, alloc_block,
        ] if b is not None),
        len(contradictions),
        len(all_gaps),
    )
    return packet
