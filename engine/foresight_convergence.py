"""Foresight convergence — the "neural web" that fuses every leaf into one HEATING-UP read
(research/THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md §0/§8).

THE HONEST MECHANISM. The desk has many independent leaves — T1 physical bottleneck, T2
customer capex, T3 guidance language, leading alt-data confirmers (insider clusters / award
accel), the small-cap DISCOVERY clusters, and the 113-subsector RADAR. Each is noisy alone
(~half of any single flag is real). The edge is CONVERGENCE: when several INDEPENDENT LEADING
signals point at the same place BEFORE the revision wave (T4) has broadened, the joint signal
is far less likely to be noise — and it is EARLY, which is the only state with edge remaining.

So this engine does not invent a new signal. It counts, per theme, how many independent
leading surfaces are lit, weights that by EARLINESS (inverse to revision breadth — a converged
signal that the street has already priced is late, not hot), and gates on a PHYSICAL correlate
(text/attention alone can't be "hot"). It also looks ACROSS surfaces: if a curated theme's
members overlap a scarcity-aligned subsector or a discovery cluster, that cross-surface
corroboration counts too. The output is a single ranked "what's heating up early" board —
the thing to investigate now, before the crowd.

NOT MAGIC. This is convergence-counting + earliness-weighting, fully transparent and forward-
graded. It raises precision (fewer false positives survive multi-surface agreement) and
surfaces the EARLY ones; it does not predict returns. DISPLAY-ONLY; pure given its inputs.
"""
from __future__ import annotations

import logging

from lib import config

log = logging.getLogger(__name__)

# the independent LEADING surfaces, each read straight off a cascade row (booleans)
SIGNALS = [
    ("physical", lambda r: r.get("bottleneck_band") in ("TIGHT", "SOLD_OUT")),
    ("demand", lambda r: r.get("demand_band") in ("ACCELERATING", "STEADY")),
    ("guidance", lambda r: r.get("guidance_band") in ("RAISING", "BROAD-RAISE")),
    ("altdata", lambda r: (r.get("n_altdata_leading") or 0) > 0),
]
CROSS = ["subsector_scarcity", "discovery_echo"]      # cross-surface corroboration
MAX_SIGNALS = len(SIGNALS) + len(CROSS)
HEAT_HOT = 0.55                                       # board threshold for "heating up"


def _theme_members() -> dict[str, set]:
    themes = (config.load() or {}).get("themes") or {}
    return {k: set(spec.get("tickers") or []) for k, spec in themes.items()}


def _scarce_subsector_tickers(subsectors: dict | None) -> dict[str, set]:
    """{sub_industry: set(scarcity members)} for scarcity-aligned subsectors only."""
    out: dict[str, set] = {}
    for s in (subsectors or {}).get("subsectors", []) or []:
        if (s.get("n_scarcity") or 0) >= 2:
            out[s.get("sub_industry")] = set(s.get("scarcity_members") or [])
    return out


def _discovery_filers(emergence: dict | None) -> dict[str, set]:
    """{sic_desc: set(new filers)} across discovery candidates."""
    out: dict[str, set] = {}
    for c in (emergence or {}).get("candidates", []) or []:
        out[c.get("sic_desc")] = set(c.get("new_filers") or [])
    return out


def compute_convergence(cascade: dict | None, emergence: dict | None = None,
                        subsectors: dict | None = None) -> dict | None:
    """Fuse the cascade rows + discovery + subsector radar into a ranked heating-up board.
    DISPLAY-ONLY. Returns None when the cascade is absent."""
    if not cascade or not cascade.get("themes"):
        return None
    members = _theme_members()
    scarce_subs = _scarce_subsector_tickers(subsectors)
    disc = _discovery_filers(emergence)
    # flatten the scarcity / discovery ticker pools for cheap overlap tests
    scarce_pool = set().union(*scarce_subs.values()) if scarce_subs else set()
    disc_pool = set().union(*disc.values()) if disc else set()

    items = []
    for r in cascade["themes"]:
        sigs = [name for name, fn in SIGNALS if fn(r)]
        mem = members.get(r.get("theme"), set())
        cross = []
        if mem & scarce_pool:
            cross.append("subsector_scarcity")
        if mem & disc_pool:
            cross.append("discovery_echo")
        all_sigs = sigs + cross
        breadth = r.get("revision_breadth")
        earliness = max(0.0, 1.0 - max(0.0, breadth)) if breadth is not None else 0.6
        physical = bool((r.get("score_detail") or {}).get("physical_confirmed"))
        # heat = converged-leading-signals x earliness, gated by a physical correlate. A late
        # (already-broad) theme decays toward 0 even with many signals — it is priced, not hot.
        heat = round((len(all_sigs) / MAX_SIGNALS) * earliness * (1.15 if physical else 0.75), 3)
        heat = min(1.0, heat)
        items.append({
            "theme": r.get("theme"),
            "name": r.get("name"),
            "stage": r.get("stage"),
            "signals": all_sigs,
            "n_signals": len(all_sigs),
            "cross_surface": cross,
            "earliness": round(earliness, 2),
            "physical_confirmed": physical,
            "heat": heat,
            "score": r.get("score"),
            "size_band": r.get("size_band"),
        })
    items.sort(key=lambda x: (-x["heat"], -x["n_signals"]))
    heating = [x for x in items if x["heat"] >= HEAT_HOT and x["n_signals"] >= 2]

    return {
        "asof": cascade.get("asof"),
        "n_items": len(items),
        "ranked": items,                              # NB: not "items" (collides with dict.items in Jinja)
        "heating_up": heating,
        "n_heating": len(heating),
        "max_signals": MAX_SIGNALS,
        "note": ("display-only; HEAT = count of independent LEADING surfaces converging on a "
                 "theme (physical bottleneck / demand / guidance / insider-award / subsector "
                 "scarcity / discovery echo), weighted by EARLINESS (inverse to revision breadth) "
                 "and gated by a physical correlate. Multi-surface agreement raises precision and "
                 "surfaces the EARLY ones — what to investigate before the crowd. Not a return "
                 "forecast; forward-graded like every leg."),
    }
