"""engine/forward_calendar_context.py — ADB-W2 forward-calendar state block.

Called by engine/master_brain.gather_state() to produce state['forward_calendar'].

Each sub-block is absent-tolerant: any exception or missing artifact emits
{absent: True, reason: <str>} rather than raising. The whole block is wrapped
in a try/except so a bug here can never fail the brief.

Serialized cap: ~4 KB.  Enforced by _trim_to_budget() which drops sub-blocks in
priority order (odds_fingerprint → hypothesis_clocks → cycle_hazards) until the
JSON-serialized byte count is under _BUDGET_BYTES.

EPISTEMIC LAWS (ADB-R4):
- Every number that appears in forward_watch / forward_read must exist verbatim
  in the forward_calendar state block.
- No arithmetic on or combination of quoted base rates / hazards (each row cites
  exactly one source).
- Model-emitted confidence fields (e.g. confidence_v2) are quoted-not-originated
  and stay off the glance tier.
- Claims model is KILLED (projection.mode == 'benchmark_only') → benchmark-only
  line, no projection band.
- Hazards surface ONLY where hazard_src == 'MODEL' for that horizon AND
  gate_status[direction][horizon] == 'PASS'.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timezone, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_BUDGET_BYTES = 4096
_DROP_ORDER = ("odds_fingerprint", "hypothesis_clocks", "cycle_hazards")

# Phase → hazard direction.  Trough is the cycle floor (hazard = turning up).
_PHASE_DIRECTION: dict[str, str] = {
    "Downturn": "down",
    "Peak": "down",
    "Recovery": "up",
    "Expansion": "up",
    "Trough": "up",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _absent(reason: str) -> dict:
    return {"absent": True, "reason": reason, "display_only": True}


def _today_str() -> str:
    return date.today().isoformat()


def _trim_to_budget(block: dict) -> dict:
    """Drop low-priority sub-blocks until serialized size <= _BUDGET_BYTES."""
    for key in _DROP_ORDER:
        raw = json.dumps(block, default=str)
        if len(raw.encode()) <= _BUDGET_BYTES:
            break
        if key in block:
            block[key] = _absent(f"dropped to stay within {_BUDGET_BYTES}B budget")
    return block


# ---------------------------------------------------------------------------
# sub-block 1: events (event_calendar high-impact strip, next 14 days)
# ---------------------------------------------------------------------------

def _gather_events() -> dict:
    try:
        from engine.event_calendar import high_impact_strip  # noqa: PLC0415
        today = date.today()
        strip = high_impact_strip(today=today, horizon_days=14)
        events = []
        for ev in strip:
            d = date.fromisoformat(ev["date"])
            events.append({
                "date": ev["date"],
                "kind": ev["type"],
                "label": ev.get("label") or ev["type"],
                "days_to": (d - today).days,
            })
        return {
            "as_of": _today_str(),
            "display_only": True,
            "horizon_days": 14,
            "events": events,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("forward_calendar events failed: %s", e)
        return _absent(f"event_calendar unavailable: {e}")


# ---------------------------------------------------------------------------
# sub-block 2: releases (release_forecast/latest.json, top-3 by days_to)
# ---------------------------------------------------------------------------

def _is_claims_killed(item: dict) -> bool:
    """Return True if this entry has the Claims kill (projection.mode == benchmark_only)."""
    proj = item.get("projection") or {}
    if isinstance(proj, dict):
        return proj.get("mode") == "benchmark_only"
    return False


def _release_entry_normal(item: dict, n_graded: int) -> dict:
    """Build a normal (non-killed) release entry."""
    proj = item.get("projection") or {}
    surprise = item.get("surprise_distribution") or {}
    mi = item.get("market_implied")
    mi_val = mi.get("implied") if isinstance(mi, dict) else None

    entry: dict[str, Any] = {
        "name": item["release"],
        "series": item.get("release_type", item["release"]),
        "date": item.get("release_date"),
        "days_to": item.get("days_to"),
        "target": item.get("target"),
    }

    # Projection band (p10/p50/p90) — only when present and not benchmark-only
    if isinstance(proj, dict) and "p10" in proj:
        entry["projection"] = {
            "p10": proj.get("p10"),
            "p50": proj.get("p50"),
            "p90": proj.get("p90"),
            "point": proj.get("point"),
        }

    # Surprise distribution
    if surprise:
        entry["surprise_distribution"] = {
            "p_hot": surprise.get("p_hot"),
            "p_cold": surprise.get("p_cold"),
            "p_inline": surprise.get("p_inline"),
        }

    # Market-implied (quoted verbatim)
    if mi_val is not None:
        entry["market_implied"] = mi_val

    # Track-record disclosure
    if n_graded == 0:
        entry["accuracy_note"] = "no accuracy record yet"

    entry["display_only"] = True
    return entry


def _release_entry_killed(item: dict) -> dict:
    """Build a benchmark-only line for a killed model (Claims)."""
    proj = item.get("projection") or {}
    bm = item.get("benchmark_set") or {}
    reason = proj.get("reason", "model killed") if isinstance(proj, dict) else "model killed"

    return {
        "name": item["release"],
        "series": item.get("release_type", item["release"]),
        "date": item.get("release_date"),
        "days_to": item.get("days_to"),
        "target": item.get("target"),
        "model_status": "benchmark_only",
        "kill_reason": reason,
        "benchmark_naive_prior": bm.get("naive_prior"),
        "display_only": True,
    }


def _gather_releases(root: Path) -> dict:
    try:
        path = root / "data" / "release_forecast" / "latest.json"
        data = _read_json(path)
        if not isinstance(data, dict):
            return _absent("release_forecast/latest.json not found or malformed")

        # Read n_graded from scoreboard
        n_graded = 0
        sb_path = root / "data" / "release_forecast" / "scoreboard.json"
        sb = _read_json(sb_path)
        if isinstance(sb, dict):
            by_rel = sb.get("by_release") or {}
            n_graded = sum(
                v.get("n_graded", 0) if isinstance(v, dict) else 0
                for v in by_rel.values()
            )

        upcoming = data.get("upcoming") or []
        # Deduplicate: take one entry per release_date × release pair (first occurrence).
        # Sort by days_to (ascending), skip None.
        seen: set[str] = set()
        entries = []
        for item in sorted(
            upcoming,
            key=lambda x: (x.get("days_to") is None, x.get("days_to") or 9999),
        ):
            key = f"{item.get('release')}:{item.get('release_date')}"
            if key in seen:
                continue
            seen.add(key)

            if _is_claims_killed(item):
                entries.append(_release_entry_killed(item))
            else:
                entries.append(_release_entry_normal(item, n_graded))

            if len(entries) >= 3:
                break

        return {
            "as_of": data.get("asof", _today_str()),
            "display_only": True,
            "n_graded": n_graded,
            "top_upcoming": entries,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("forward_calendar releases failed: %s", e)
        return _absent(f"release_forecast unavailable: {e}")


# ---------------------------------------------------------------------------
# sub-block 3: rebalance (rebalance_calendar.tag(today))
# ---------------------------------------------------------------------------

def _gather_rebalance() -> dict:
    try:
        from engine.rebalance_calendar import tag  # noqa: PLC0415
        today = date.today()
        t = tag(today)
        return {
            "as_of": _today_str(),
            "display_only": True,
            "td_to_quarter_end": t.get("td_to_quarter_end"),
            "in_qtr_end_window": t.get("in_qtr_end_window"),
            "is_russell_recon_session": t.get("is_russell_recon_session"),
            "in_recon_week": t.get("in_recon_week"),
            "is_sp_rebalance_session": t.get("is_sp_rebalance_session"),
        }
    except Exception as e:  # noqa: BLE001
        log.debug("forward_calendar rebalance failed: %s", e)
        return _absent(f"rebalance_calendar unavailable: {e}")


# ---------------------------------------------------------------------------
# sub-block 4: cycle_hazards (cycle_pattern_state.json, MODEL+PASS only)
# ---------------------------------------------------------------------------

def _gather_cycle_hazards(root: Path) -> dict:
    try:
        path = root / "data" / "neuralweb" / "cycle_pattern_state.json"
        data = _read_json(path)
        if not isinstance(data, dict):
            return _absent("cycle_pattern_state.json not found or malformed")

        gate_status = data.get("gate_status") or {}
        # gate_status: {up: {1m: PASS|PRIOR|...}, down: {1m: PASS|PRIOR|...}}
        gate_up = gate_status.get("up") or {}
        gate_down = gate_status.get("down") or {}

        def _gate_pass(direction: str, horizon: str) -> bool:
            g = gate_up if direction == "up" else gate_down
            return g.get(horizon) == "PASS"

        entities = data.get("entities") or []
        hazards = []
        for ent in entities:
            src = ent.get("hazard_src") or {}
            phase = ent.get("phase_v2")
            direction = _PHASE_DIRECTION.get(phase)
            if direction is None:
                continue  # unknown phase — skip

            for horizon in ("1m", "3m", "6m"):
                if src.get(horizon) != "MODEL":
                    continue  # PRIOR-sourced: skip
                if not _gate_pass(direction, horizon):
                    continue  # gate not PASS: skip

                hazard_p = ent.get(f"hazard_{horizon}_p")
                if hazard_p is None:
                    continue

                hazards.append({
                    "entity_id": ent.get("entity_id"),
                    "phase": phase,
                    "horizon": horizon,
                    "hazard_p": hazard_p,
                    "direction": direction,
                })

        # Keep up to 3, sorted by hazard_p descending
        hazards.sort(key=lambda x: x.get("hazard_p", 0), reverse=True)
        top3 = hazards[:3]

        return {
            "as_of": data.get("asof", _today_str()),
            "display_only": True,
            "gate_status": gate_status,
            "top_hazards": top3,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("forward_calendar cycle_hazards failed: %s", e)
        return _absent(f"cycle_pattern_state unavailable: {e}")


# ---------------------------------------------------------------------------
# sub-block 5: odds_fingerprint (site/oddsdata/factor_match.json)
# ---------------------------------------------------------------------------

def _gather_odds_fingerprint(root: Path) -> dict:
    """factor_match.json is per-ticker / template-shaped, not a single current-state row.

    Emits the closest honest summary available — the SPY core-template 20d base
    rate (SPY = market proxy) with a Wilson CI computed HERE, deterministically,
    from the artifact's raw (n, win_rate). The CI is engine-derived, not quoted
    from odds_lab (lawful: the no-origination law binds LLMs, not deterministic
    engine code; the LLM still only quotes numbers it is handed). Malformed or
    missing artifacts fall through to absent markers."""
    try:
        path = root / "site" / "oddsdata" / "factor_match.json"
        data = _read_json(path)
        if not isinstance(data, dict):
            return _absent("factor_match.json not found or malformed")

        # Inspect structure: rows is a list of per-ticker entries, not a current-state row.
        rows = data.get("rows") or []
        schema = data.get("schema", "")
        asof = data.get("asof", "")

        # If no rows or the artifact is template-shaped (per-ticker), emit absent.
        # The artifact has rows keyed by ticker (SPY, QQQ, etc.) not a fingerprint match row.
        if not rows:
            return _absent("factor_match artifact has no rows")

        # Emit the closest honest summary: the SPY row 'core' template at 20d horizon
        # as the market-fingerprint base rate (SPY = market proxy).
        spy_row = next((r for r in rows if r.get("t") == "SPY"), None)
        if spy_row is None:
            return _absent("no SPY row in factor_match artifact")

        res = spy_row.get("res") or {}
        core_20d = (res.get("core") or {}).get("20d")
        if not isinstance(core_20d, list) or len(core_20d) < 2:
            return _absent("factor_match SPY core/20d result not present")

        n, win_rate = core_20d[0], core_20d[1]
        # Wilson CI
        from math import sqrt  # noqa: PLC0415
        z = 1.96
        if n > 0:
            p_hat = win_rate
            denom = 1 + z * z / n
            centre = (p_hat + z * z / (2 * n)) / denom
            margin = z * sqrt(p_hat * (1 - p_hat) / n + z * z / (4 * n * n)) / denom
            ci_lo = round(max(0.0, centre - margin), 4)
            ci_hi = round(min(1.0, centre + margin), 4)
        else:
            ci_lo, ci_hi = None, None

        return {
            "as_of": asof,
            "display_only": True,
            "note": ("SPY core-template 20d base rate from factor_match; per-ticker artifact, "
                     "not a single current-state fingerprint row; Wilson CI engine-derived "
                     "from the artifact's raw n/win_rate, not quoted from odds_lab"),
            "template": "core",
            "horizon": "20d",
            "n": n,
            "win_rate": win_rate,
            "wilson_ci_lo": ci_lo,
            "wilson_ci_hi": ci_hi,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("forward_calendar odds_fingerprint failed: %s", e)
        return _absent(f"factor_match unavailable: {e}")


# ---------------------------------------------------------------------------
# sub-block 6: hypothesis_clocks (machine_registry.jsonl come_back dates)
# ---------------------------------------------------------------------------

def _gather_hypothesis_clocks(root: Path) -> dict:
    try:
        path = root / "data" / "neuralweb" / "machine_registry.jsonl"
        if not path.exists():
            return _absent("machine_registry.jsonl not found")

        clocks = []
        with path.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                come_back = rec.get("come_back")
                if come_back is None:
                    continue
                clocks.append({
                    "id": rec.get("id"),
                    "claim_shape": rec.get("claim_shape"),
                    "come_back": come_back,
                    "status": "verdict pending",
                })

        return {
            "as_of": _today_str(),
            "display_only": True,
            "clocks": clocks,
        }
    except Exception as e:  # noqa: BLE001
        log.debug("forward_calendar hypothesis_clocks failed: %s", e)
        return _absent(f"machine_registry unavailable: {e}")


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def gather_forward_calendar(root: Path) -> dict:
    """Assemble the forward_calendar state block from six feeds.

    Each sub-block is individually fail-open.  The overall block is serialized
    and trimmed to _BUDGET_BYTES by dropping low-priority sub-blocks.

    Returns a dict to be stored as state['forward_calendar'].
    """
    block: dict[str, Any] = {
        "as_of": _today_str(),
        "display_only": True,
        "events": _gather_events(),
        "releases": _gather_releases(root),
        "rebalance": _gather_rebalance(),
        "cycle_hazards": _gather_cycle_hazards(root),
        "odds_fingerprint": _gather_odds_fingerprint(root),
        "hypothesis_clocks": _gather_hypothesis_clocks(root),
    }

    return _trim_to_budget(block)
