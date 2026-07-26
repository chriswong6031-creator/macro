"""engine.marketing.ad_central — the facade the console and the nightly both read.

Ad Central (`research/AD_CENTRAL_MASTERPLAN.md`).  Resolves config, folds the
arena ledgers, and returns one panel-ready payload: for every arena, what is
running, what it has learned so far, and what the budget would do about it.

Two rules govern what this module returns:

* **A null is a result.**  An arena that found nothing says so in plain words.
  An arena still gathering data says *that*, with how far it has to go.  Neither
  renders as an empty panel — "no verdict yet" and "no effect" are different
  facts and the reader must be able to tell them apart.
* **The gate is always visible.**  Every payload carries the G-A triple gate's
  state, so nobody has to infer from a $0 total whether spend is off or merely
  idle.

Never raises.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import ad_allocator, ad_arena, ad_stats

log = logging.getLogger(__name__)

SCHEMA = "marketing.ad_central/v1"


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def _num(block: dict, key: str, default: float) -> float:
    try:
        v = block.get(key)
        return default if v is None else float(v)
    except Exception:  # noqa: BLE001
        return default


def resolve(cfg: dict | None, *, operator_armed: bool = False) -> dict[str, Any]:
    """Resolve the `ad_central:` block against defaults.  Missing block ⇒ all defaults."""
    cfg = cfg or {}
    block = cfg.get("ad_central") or {}
    envelope = block.get("envelope") or {}
    arena = block.get("arena") or {}
    matrix = block.get("matrix") or {}
    settings = cfg.get("settings") or {}

    return {
        "paid_enabled": bool(settings.get("paid_enabled", False)),
        "operator_armed": bool(operator_armed),
        "envelope": {
            "daily_usd": _num(envelope, "daily_usd", 0.0),
            "per_arm_daily_cap_usd": _num(
                envelope, "per_arm_daily_cap_usd", ad_allocator.DEFAULT_PER_ARM_CAP_USD),
            "min_daily_usd": _num(envelope, "min_daily_usd", ad_allocator.DEFAULT_MIN_DAILY_USD),
        },
        "arena": {
            "n_floor": int(_num(arena, "n_floor", ad_stats.DEFAULT_N_FLOOR)),
            "credible_level": _num(arena, "credible_level", ad_stats.DEFAULT_CREDIBLE_LEVEL),
            "decisive": _num(arena, "decisive", ad_stats.DEFAULT_DECISIVE),
            "practical_pp": _num(arena, "practical_pp", ad_stats.DEFAULT_PRACTICAL_PP),
            "prior_alpha": _num(arena, "prior_alpha", ad_stats.DEFAULT_PRIOR_ALPHA),
            "prior_beta": _num(arena, "prior_beta", ad_stats.DEFAULT_PRIOR_BETA),
            "exploration_floor_share": _num(
                arena, "exploration_floor_share",
                ad_allocator.DEFAULT_EXPLORATION_FLOOR_SHARE),
        },
        "matrix": {
            "max_creatives": int(_num(matrix, "max_creatives", 24)),
            "jaccard_ceiling": _num(matrix, "jaccard_ceiling", 0.7),
        },
    }


def allocator_config(resolved: dict[str, Any]) -> ad_allocator.AllocatorConfig:
    env = resolved["envelope"]
    arena = resolved["arena"]
    return ad_allocator.AllocatorConfig(
        daily_envelope_usd=env["daily_usd"],
        per_arm_daily_cap_usd=env["per_arm_daily_cap_usd"],
        min_daily_usd=env["min_daily_usd"],
        exploration_floor_share=arena["exploration_floor_share"],
        n_floor=arena["n_floor"],
        prior_alpha=arena["prior_alpha"],
        prior_beta=arena["prior_beta"],
        credible_level=arena["credible_level"],
        paid_enabled=resolved["paid_enabled"],
        operator_armed=resolved["operator_armed"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Gate
# ─────────────────────────────────────────────────────────────────────────────

_GATE_PLAIN = {
    "paid_enabled_false": "Paid ads are switched off in config.",
    "envelope_zero": "No daily budget is set.",
    "operator_not_armed": "Nobody has armed spending.",
}


def gate_state(resolved: dict[str, Any]) -> dict[str, Any]:
    """The G-A triple gate, in the plain words the console prints."""
    cfg = allocator_config(resolved)
    permitted, blocked = ad_allocator.spend_permitted(cfg)
    return {
        "spend_permitted": permitted,
        "blocked_by": blocked,
        "arms": {
            "paid_enabled": resolved["paid_enabled"],
            "envelope_set": resolved["envelope"]["daily_usd"] > 0,
            "operator_armed": resolved["operator_armed"],
        },
        "plain": (
            f"Spending is live — up to ${resolved['envelope']['daily_usd']:.2f} a day."
            if permitted else
            "Nothing can be spent. " + " ".join(_GATE_PLAIN.get(b, b) for b in blocked)
            + " All three must be on before a single ad is bought."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────

def _headline(readout: dict[str, Any]) -> str:
    """One sentence a person can act on — the glance tier for this arena."""
    verdict = readout.get("verdict")
    plain = readout.get("plain") or ""
    if verdict == "separated":
        return plain + " Ship it."
    if verdict == "equivalent":
        return plain
    if verdict == "seeding":
        return plain + " Watch — don't act on the ordering yet."
    return plain + " Vary something bigger, or accept that this axis does not move it."


def state(
    root: Path | str | None = None,
    *,
    cfg: dict | None = None,
    operator_armed: bool = False,
) -> dict[str, Any]:
    """Full Ad Central payload.  Never raises; degrades to an honest empty state."""
    try:
        r = Path(root) if root is not None else Path(".")
        if cfg is None:
            from .state import _load_cfg  # noqa: PLC0415
            cfg = _load_cfg(r)

        resolved = resolve(cfg, operator_armed=operator_armed)
        gate = gate_state(resolved)
        acfg = allocator_config(resolved)
        arena_cfg = resolved["arena"]

        arenas = ad_arena.load_arenas(root=r)
        creatives = ad_arena.load_creatives(root=r)
        rows: list[dict[str, Any]] = []
        for arena in arenas:
            # The arena's own n_floor wins over the global default — a test may be
            # pre-registered with a stricter floor, never a looser one at read time.
            arena.n_floor = max(int(arena.n_floor), 0) or arena_cfg["n_floor"]
            tallied = ad_arena.tally_from_ledgers(arena, root=r)
            read = ad_arena.readout(
                arena, tallied,
                credible_level=arena_cfg["credible_level"],
                decisive=arena_cfg["decisive"],
                practical_pp=arena_cfg["practical_pp"],
                prior_alpha=arena_cfg["prior_alpha"],
                prior_beta=arena_cfg["prior_beta"],
            )
            per_arena_cfg = ad_allocator.AllocatorConfig(**{
                **acfg.as_dict(),
                "daily_envelope_usd": (arena.envelope_usd or acfg.daily_envelope_usd),
            })
            plan = ad_allocator.allocate(tallied.arms, per_arena_cfg)
            rows.append({
                "arena": arena.as_dict(),
                "readout": read,
                "headline": _headline(read),
                "budget": plan.as_dict(),
                "budget_plain": ad_allocator.plan_summary(plan),
                # The copy behind each arm, so the console shows the ad rather
                # than its id. Absent for an arena whose creatives predate the
                # creatives ledger — the panel falls back to the id.
                "creatives": {
                    cid: creatives[cid]
                    for cid in arena.arm_creative_ids if cid in creatives
                },
            })

        counts = {
            "arenas": len(rows),
            "running": sum(1 for x in rows if x["arena"]["status"] == "running"),
            "seeding": sum(1 for x in rows if x["readout"]["verdict"] == "seeding"),
            "separated": sum(1 for x in rows if x["readout"]["verdict"] == "separated"),
            "null": sum(1 for x in rows if x["readout"]["verdict"] in ("null", "equivalent")),
        }
        return {
            "ok": True,
            "schema": SCHEMA,
            "config": resolved,
            "gate": gate,
            "arenas": rows,
            "counts": counts,
            # Two forms on purpose: `counts_plain` for a surface that already
            # shows the gate elsewhere, `plain` for one that does not. Printing
            # the gate sentence twice on one screen reads as a stutter.
            "counts_plain": _counts_plain(counts),
            "plain": _overview_plain(counts, gate),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("ad_central.state failed: %s", exc)
        return {"ok": False, "error": str(exc), "schema": SCHEMA}


_EMPTY_PLAIN = ("No split tests yet. Ad Central is built and idle — "
                "the first one starts on our own pages, where a test costs nothing.")


def _counts_plain(counts: dict[str, int]) -> str:
    if not counts["arenas"]:
        return _EMPTY_PLAIN
    parts = [f"{counts['arenas']} split test{'s' if counts['arenas'] != 1 else ''}"]
    if counts["seeding"]:
        parts.append(f"{counts['seeding']} still gathering data")
    if counts["separated"]:
        parts.append(f"{counts['separated']} with a clear winner")
    if counts["null"]:
        parts.append(f"{counts['null']} that found no difference")
    return ", ".join(parts) + "."


def _overview_plain(counts: dict[str, int], gate: dict[str, Any]) -> str:
    if not counts["arenas"]:
        return _EMPTY_PLAIN
    return _counts_plain(counts) + " " + gate["plain"]
