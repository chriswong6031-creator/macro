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
"""
from __future__ import annotations

import copy
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

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
    """Extract the regime quad block; exactly the specified keys."""
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
        "qi": None,
        "qi_note": (
            "pending joint QI border ruling (masterplan W1) — "
            "QI produces the aggregate, Neural Web consumes; "
            "do not aggregate raw qbus here (border law §9)"
        ),
        "live_overlay": live_overlay_block,
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
