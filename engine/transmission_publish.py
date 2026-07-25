"""Transmission CHAINS — site publication adapter (TXI W4, deliverable A).

Derives the DISPLAY subset ``site/transmission_chains.json`` from the canonical
``data/transmission/chain_state.json`` (``transmission_chains.v1``, written by
``engine/transmission_chains.run``). This is a pure, deterministic projection — no IO,
no engine recompute, no LLM — mirroring the darkpool_context → world_state re-projection
discipline: the server already resolved the chains + blast radius; this only trims the
per-chain state to the fields the site + client render, drops the machine receipts, and
stamps a one-render-lag note.

WHY A LAG NOTE (verified pipeline fact): in ``.github/workflows/daily.yml`` the
``build_site`` step (~line 899) runs BEFORE ``run_transmission_chains`` (~line 1133), so
the site-published JSON is derived from LAST night's chain_state — one nightly stale. We
stamp ``lag_note`` in the emit so every consumer is honest about it (masterplan §7).

DISCIPLINE (masterplan §4; DNR row 45; TXI Article 1/2): the subset carries
``display_only=True`` and is context/watch tier only — it never scores, ranks, sizes, or
escalates. The word "validated" never appears. Chain-level and hop-level bilingual DISPLAY
labels come from the YAML (``title`` for the chain; the W4 hop ``label``); the resolver's
per-name blast lists + printed numeric cuts pass through verbatim so a client holding the
per-ticker substrate rebuilds the exact ticker set from the same fields.
"""
from __future__ import annotations

from typing import Any

SUBSET_SCHEMA = "transmission_chains_display.v1"

# The one-render-lag disclosure (build_site runs before run_transmission_chains in the
# nightly). Bilingual — every consumer surfaces its own copy.
LAG_NOTE = {
    "en": "Chain states are from the prior nightly — build_site publishes before the chains "
          "step runs, so this snapshot lags one night.",
    "zh": "链状态来自上一次夜间构建——build_site 在链计算步骤之前发布，故本快照滞后一晚。",
}


def _bilingual(d: Any) -> dict | None:
    """Coerce a value to a plain ``{en, zh}`` dict, or None if it isn't one."""
    if isinstance(d, dict) and ("en" in d or "zh" in d):
        return {"en": d.get("en"), "zh": d.get("zh")}
    return None


def _hop_subset(hop: dict) -> dict:
    """Trim one hop to {id, label, confirmed, asof} — drop the value receipts (the
    machine detail lives on the full artifact / the drill page)."""
    label = _bilingual(hop.get("label"))
    if label is None:
        # A pre-W4 chain (no hop label) falls back to the hop id so the subset is never
        # blank — honest, never invented copy.
        hid = hop.get("id") or f"{hop.get('from')}->{hop.get('to')}"
        label = {"en": hid, "zh": hid}
    return {
        "id": hop.get("id"),
        "label": label,
        "confirmed": bool(hop.get("confirmed")),
        "asof": hop.get("asof"),
    }


def _channel_subset(entry: dict) -> dict:
    """Trim one blast channel to the display fields. Keeps the full ticker array + the
    printed numeric cuts (a client rebuilds membership client-side from the same fields);
    always carries the unevaluable count (a missing field is never silently safe/unsafe)."""
    out: dict[str, Any] = {
        "label": _bilingual(entry.get("label")),
        "n": entry.get("n"),
        "unevaluable": entry.get("unevaluable"),
        "names": list(entry.get("names") or []),
        "cuts": dict(entry.get("cuts") or {}),
    }
    note = _bilingual(entry.get("note"))
    if note is not None:
        out["note"] = note
    return out


def _chain_subset(chain: dict, caveats: list) -> dict:
    """Trim one per-chain state to the published display subset."""
    blast_in = chain.get("blast") or {}
    blast_out: dict[str, Any] = {}
    if isinstance(blast_in, dict):
        for flag, entry in blast_in.items():
            if isinstance(entry, dict):
                blast_out[flag] = _channel_subset(entry)
    label = _bilingual(chain.get("title")) or {"en": chain.get("chain"), "zh": chain.get("chain")}
    return {
        "id": chain.get("chain"),
        "label": label,
        "state": chain.get("state"),
        "tier": chain.get("tier"),
        "hops": [_hop_subset(h) for h in (chain.get("hops") or []) if isinstance(h, dict)],
        "blast": blast_out,
        "caveats": caveats,
    }


def derive_display_subset(chain_state: dict) -> dict:
    """Project the canonical ``transmission_chains.v1`` artifact into the published display
    subset. Pure — no IO. Returns the exact shape baked to ``site/transmission_chains.json``.

    ``chain_state`` is the parsed ``data/transmission/chain_state.json``. A malformed /
    empty input yields an empty ``chains`` list (never raises) — the caller skips the emit
    when there are no chains, so an absent artifact publishes nothing at all.
    """
    if not isinstance(chain_state, dict):
        chain_state = {}
    caveats = chain_state.get("caveats") or []
    if not isinstance(caveats, list):
        caveats = []
    chains_in = chain_state.get("chains") or []
    chains_out = [_chain_subset(c, caveats) for c in chains_in if isinstance(c, dict)]
    substrate = chain_state.get("substrate") or {}
    substrate_asof = substrate.get("substrate_asof") if isinstance(substrate, dict) else None
    return {
        "schema": SUBSET_SCHEMA,
        "asof": chain_state.get("asof"),
        "substrate_asof": substrate_asof,
        "lag_note": LAG_NOTE,
        "chains": chains_out,
        "display_only": True,
    }
