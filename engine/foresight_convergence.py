"""Foresight convergence — W4a rebuild on true independence (research/FORESIGHT_DESK_UPGRADE_BY_FABLE.md §2 P2-A + §3.5).

P2-A FIXES:
  1. Source de-duplication: ``subsector_scarcity`` and ``discovery_echo`` both read the SAME
     ``data/edgar/emergence_hits.parquet`` — they are merged into ONE ``edgar_scarcity`` surface
     so one parquet sweep counts as ONE source, not two.
  2. Distinct DATA SOURCES counted (not engine calls): physical bottleneck / demand / guidance /
     altdata / edgar_scarcity / earliness-composite.  6 → 5 true distinct sources.
  3. Earliness from ``engine/foresight_earliness.py`` (attention-based, Q3).  Below 2 usable
     legs, earliness is treated as ABSENT (mirroring the earliness engine's own gate).
  4. Dark legs leave the DENOMINATOR: heat = n_lit / n_AVAILABLE surfaces.  A surface whose
     data source is dark is excluded from n_available — the old fixed ×0.75 physical penalty
     punished the desk for its own outages.  ``physical`` remains a BONUS multiplier when
     genuinely lit (numeric TIGHT/SOLD_OUT only — text bands are a lit surface but NOT physical
     confirmation per house rule TEXT_ONLY_CAP).
  5. Provisional HEAT_HOT threshold (0.40, down from the unreachable 0.55) documented as
     provisional pending shadow calibration.  Added to SHADOW_GRID in foresight_shadow.py
     (comment-only extension; registry wiring noted there for the next entry).
  6. Meta-driver cards (§3.5): when ≥3 same-cluster themes light the same surfaces, ONE
     combined meta-driver entry is emitted alongside the per-theme rows.  Cluster membership
     is data-derived nightly from the ENB module (engine/foresight_enb.py); hand-named clusters
     in CLUSTER_NAMES provide the display label with a numeric fallback.
"""
from __future__ import annotations

import logging

from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data SOURCES (not engine calls — the audit found subsector_scarcity and
# discovery_echo read the SAME parquet, so they are ONE source).
# Each entry: (surface_key, test_fn)
# test_fn receives the cascade row dict and returns True when the source is LIT.
# ---------------------------------------------------------------------------
# "dark" for a surface means the underlying data store is absent/empty — the
# convergence engine detects this per-theme by testing for None values below.

# 5 distinct sources (down from 6 in the old engine):
#   physical · demand · guidance · altdata · edgar_scarcity
# The old "subsector_scarcity" + "discovery_echo" are merged into ONE.
SOURCES: list[tuple[str, object]] = [
    ("physical",        lambda r: r.get("bottleneck_band") in ("TIGHT", "SOLD_OUT")),
    ("demand",          lambda r: r.get("demand_band") in ("ACCELERATING", "STEADY")),
    ("guidance",        lambda r: r.get("guidance_band") in ("RAISING", "BROAD-RAISE")),
    ("altdata",         lambda r: (r.get("n_altdata_leading") or 0) > 0),
    ("edgar_scarcity",  None),   # filled below via cross-surface overlap (subsectors ∪ discovery)
]
# Sources whose raw value can be None (no data) — these leave the denominator when dark
_NULLABLE_SOURCES = {"physical", "edgar_scarcity", "altdata"}

# PROVISIONAL — documented as shadow-calibration pending; see foresight_shadow.SHADOW_GRID note
HEAT_HOT = 0.40   # provisional threshold; old 0.55 was structurally unreachable

# Physical confirmation bonus: numeric TIGHT/SOLD_OUT (not text-only bands) adds a 15% boost
# when the source IS lit.  A text-only band is a lit edgar_scarcity surface but NOT physical.
PHYSICAL_BONUS = 1.15

# Meta-driver card: ≥3 same-cluster themes heating together = one bet, not N separate tiles
META_DRIVER_MIN_THEMES = 3

# Hand-named cluster labels — fallback "cluster-N" when key is unknown
CLUSTER_NAMES: dict[str, str] = {
    "ai_capex":    "AI-capex complex",
    "defense":     "defense/geopolitics",
    "healthcare":  "healthcare",
    # Any cluster label from foresight_enb not listed here gets "cluster-N" via _cluster_label()
}


def len_sources() -> int:
    """Return the number of distinct data sources tracked (for test assertions)."""
    return len(SOURCES)


def _cluster_label(cluster_id: str, idx: int) -> str:
    return CLUSTER_NAMES.get(cluster_id, f"cluster-{idx + 1}")


def _theme_members() -> dict[str, set]:
    themes = (config.load() or {}).get("themes") or {}
    return {k: set(spec.get("tickers") or []) for k, spec in themes.items()}


def _scarce_subsector_tickers(subsectors: dict | None) -> set[str]:
    """Flat pool of tickers that appear in scarcity-aligned subsectors."""
    pool: set[str] = set()
    for s in (subsectors or {}).get("subsectors", []) or []:
        if (s.get("n_scarcity") or 0) >= 2:
            pool.update(s.get("scarcity_members") or [])
    return pool


def _discovery_filer_tickers(emergence: dict | None) -> set[str]:
    """Flat pool of tickers appearing across discovery candidates."""
    pool: set[str] = set()
    for c in (emergence or {}).get("candidates", []) or []:
        pool.update(c.get("new_filers") or [])
    return pool


def _power_tight_themes(power_scarcity: dict | None) -> set[str]:
    """Power-cluster themes whose electricity-scarcity read is numeric TIGHT/SOLD_OUT."""
    if not power_scarcity or power_scarcity.get("band") not in ("TIGHT", "SOLD_OUT"):
        return set()
    return set((power_scarcity.get("themes") or {}).keys())


def _load_earliness() -> dict[str, dict]:
    """Load today's earliness payload from foresight_earliness if available.

    Returns {theme: {"earliness": float|None, "n_legs_live": int}} for each theme.
    Degrades gracefully to empty dict — the convergence engine handles absent earliness."""
    try:
        from engine.foresight_earliness import compute_foresight_earliness
        result = compute_foresight_earliness(write_log=False)
        if result and result.get("themes"):
            return result["themes"]
    except Exception as e:  # noqa: BLE001
        log.debug("convergence: earliness load failed: %s", e)
    return {}


def _load_enb_clusters() -> dict[str, str]:
    """Load theme→cluster_id from the ENB module (nightly, data-derived).

    Returns {theme_key: cluster_id_str}.  Degrades to {} when ENB is absent (first run,
    data short history, import error) — meta-driver cards are skipped when absent."""
    try:
        from engine.foresight_enb import load_cluster_membership
        return load_cluster_membership()
    except Exception as e:  # noqa: BLE001
        log.debug("convergence: enb cluster load failed: %s", e)
    return {}


def _is_physical_numeric(r: dict, power_tight: set[str]) -> bool:
    """True when the theme has NUMERIC physical confirmation (TIGHT/SOLD_OUT, not text-only)."""
    bn = r.get("bottleneck_band")
    if bn in ("TIGHT", "SOLD_OUT"):
        return True
    if r.get("theme") in power_tight:
        return True
    if bool((r.get("score_detail") or {}).get("physical_confirmed")):
        return True
    return False


def _meta_driver_sentence(cluster_name: str, member_themes: list[str], shared_sources: list[str]) -> str:
    src_str = ", ".join(shared_sources) if shared_sources else "overlapping sources"
    return (f"{cluster_name} ({len(member_themes)} themes) share {src_str} — "
            "one macro bet in multiple hats.")


def compute_convergence(
    cascade: dict | None,
    emergence: dict | None = None,
    subsectors: dict | None = None,
    power_scarcity: dict | None = None,
    earliness_payload: dict | None = None,
) -> dict | None:
    """Fuse the cascade rows + discovery + subsector radar (+ power-cluster physical) into a
    ranked heating-up board.  W4a rebuild: distinct data sources / dark-leaves-denominator /
    earliness from Q3 engine / meta-driver cards for same-cluster co-heating themes.

    DISPLAY-ONLY.  Returns None when the cascade is absent or has no rows."""
    if not cascade or not cascade.get("themes"):
        return None

    members = _theme_members()
    # Merged edgar scarcity pool (was two separate cross-surfaces in the old engine)
    scarce_pool = _scarce_subsector_tickers(subsectors)
    disc_pool = _discovery_filer_tickers(emergence)
    edgar_pool = scarce_pool | disc_pool   # UNION — the de-duplicated single source

    power_tight = _power_tight_themes(power_scarcity)

    # Earliness payload: either provided by caller (test injection) or loaded fresh
    if earliness_payload is None:
        earliness_payload = _load_earliness()

    # ENB clusters for meta-driver cards
    enb_clusters = _load_enb_clusters()

    # Is edgar_scarcity data available at all?  (If both pools are empty, source is dark)
    edgar_data_available = bool(edgar_pool)

    items = []
    for r in cascade["themes"]:
        theme = r.get("theme")
        mem = members.get(theme, set())

        # --- per-source availability (is the underlying data present?) ---
        # A source is UNAVAILABLE when its data store is dark (returns None/0/empty).
        # UNAVAILABLE sources leave the denominator so the desk isn't penalised for outages.
        source_available: dict[str, bool] = {
            "physical":       True,   # always a defined surface; may be "AWAITING_DATA" = dark below
            "demand":         r.get("demand_band") is not None,
            "guidance":       r.get("guidance_band") is not None,
            "altdata":        r.get("n_altdata_leading") is not None,
            "edgar_scarcity": edgar_data_available,
        }

        # Physical is "dark" when the band is AWAITING_DATA or None (i.e. FRED not landed)
        bn_band = r.get("bottleneck_band")
        physical_dark = (bn_band is None or bn_band == "AWAITING_DATA")
        if physical_dark and theme not in power_tight:
            source_available["physical"] = False

        # --- which sources are LIT for this theme? ---
        lit_sources: list[str] = []

        # physical
        if source_available["physical"]:
            is_phys = _is_physical_numeric(r, power_tight)
            if is_phys:
                lit_sources.append("physical")

        # demand
        if source_available["demand"]:
            if r.get("demand_band") in ("ACCELERATING", "STEADY"):
                lit_sources.append("demand")

        # guidance
        if source_available["guidance"]:
            if r.get("guidance_band") in ("RAISING", "BROAD-RAISE"):
                lit_sources.append("guidance")

        # altdata
        if source_available["altdata"]:
            if (r.get("n_altdata_leading") or 0) > 0:
                lit_sources.append("altdata")

        # edgar_scarcity (merged subsector_scarcity + discovery_echo — ONE source)
        if source_available["edgar_scarcity"]:
            if mem & edgar_pool:
                lit_sources.append("edgar_scarcity")

        # --- earliness from Q3 engine (attention-based, not 1-breadth) ---
        n_available = sum(1 for v in source_available.values() if v)

        e_data = earliness_payload.get(theme) or {}
        e_val: float | None = e_data.get("earliness")
        n_legs_live: int = e_data.get("n_legs_live", 0)
        # Gate: below 2 usable legs, earliness is absent (per spec Q3)
        if n_legs_live < 2:
            e_val = None
        # F1: when earliness is absent, DROP the factor entirely rather than
        # default-filling 0.5 (absence-laundered-as-measurement pathology).
        # heat = n_lit / n_available alone; the factor is only applied when
        # earliness is genuinely measured (n_legs_live >= 2).
        earliness_absent = e_val is None

        # --- heat = n_lit / n_available [× earliness if available] (+ physical bonus) ---
        n_lit = len(lit_sources)
        if n_available == 0:
            heat = 0.0
        else:
            raw = n_lit / n_available
            # Earliness factor: applied ONLY when measured (n_legs_live >= 2)
            if not earliness_absent:
                raw = raw * e_val
            # Physical BONUS (not penalty): numeric TIGHT/SOLD_OUT adds +15%; text-only does NOT
            numeric_physical = _is_physical_numeric(r, power_tight)
            if numeric_physical:
                raw *= PHYSICAL_BONUS
            heat = round(min(1.0, raw), 3)

        items.append({
            "theme": theme,
            "name": r.get("name"),
            "stage": r.get("stage"),
            "lit_sources": lit_sources,
            "n_lit": n_lit,
            "n_available": n_available,
            "source_available": source_available,
            "earliness": round(e_val, 3) if e_val is not None else None,
            "earliness_absent": earliness_absent,
            "earliness_available": not earliness_absent,
            "n_earliness_legs": n_legs_live,
            "physical_confirmed": _is_physical_numeric(r, power_tight),
            "heat": heat,
            "score": r.get("score"),
            "size_band": r.get("size_band"),
            # backward-compat aliases
            "signals": lit_sources,
            "n_signals": n_lit,
            "cross_surface": (["edgar_scarcity"] if "edgar_scarcity" in lit_sources else []),
        })

    items.sort(key=lambda x: (-x["heat"], -x["n_lit"]))
    heating = [x for x in items if x["heat"] >= HEAT_HOT and x["n_lit"] >= 1]

    # --- meta-driver cards (§3.5): ≥3 co-heating same-cluster themes ---
    meta_drivers: list[dict] = []
    if enb_clusters:
        # Group heating items by cluster_id
        cluster_items: dict[str, list[dict]] = {}
        for it in heating:
            cid = enb_clusters.get(it["theme"])
            if cid:
                cluster_items.setdefault(cid, []).append(it)

        for idx, (cid, c_items) in enumerate(cluster_items.items()):
            if len(c_items) < META_DRIVER_MIN_THEMES:
                continue
            shared_sources = list(
                set(c_items[0]["lit_sources"]).intersection(
                    *(set(it["lit_sources"]) for it in c_items[1:])
                )
            )
            combined_heat = round(
                sum(it["heat"] for it in c_items) / len(c_items), 3
            )
            meta_drivers.append({
                "cluster_id":     cid,
                "cluster_name":   _cluster_label(cid, idx),
                "member_themes":  [it["theme"] for it in c_items],
                "member_names":   [it["name"] for it in c_items],
                "n_members":      len(c_items),
                "combined_heat":  combined_heat,
                "shared_sources": shared_sources,
                "driver_sentence": _meta_driver_sentence(
                    _cluster_label(cid, idx),
                    [it["theme"] for it in c_items],
                    shared_sources,
                ),
            })
        meta_drivers.sort(key=lambda x: -x["combined_heat"])

    return {
        "asof":           cascade.get("asof"),
        "n_items":        len(items),
        "ranked":         items,
        "heating_up":     heating,
        "n_heating":      len(heating),
        "max_sources":    len(SOURCES),        # 5 distinct data sources
        # backward compat (old templates used max_signals)
        "max_signals":    len(SOURCES),
        "meta_drivers":   meta_drivers,
        "n_meta_drivers": len(meta_drivers),
        "heat_threshold": HEAT_HOT,
        "heat_threshold_note": (
            "PROVISIONAL — chosen to be REACHABLE under the new denominator semantics so "
            "the board is not永-empty — NOT evidence-based; shadow calibration pending. "
            "Candidates [0.30, 0.40, 0.50] are wired in foresight_shadow.SHADOW_GRID and "
            "accrue heat-verdict rows in shadow_log.jsonl (type='heat'); grading not yet "
            "wired — labeled 'accruing' in the promotion report."
        ),
        "note": (
            "W4a rebuild: HEAT = n_lit_sources / n_available_sources [× earliness when "
            "measured — dropped, not filled, when absent].  5 distinct data feeds "
            "(physical · demand · guidance · altdata · edgar_scarcity — the old "
            "subsector_scarcity + discovery_echo were one EDGAR parquet, now counted once). "
            "Dark sources leave the denominator — no outage penalty.  Earliness from "
            "engine/foresight_earliness.py (attention-based, Q3); absent below 2 usable legs "
            "→ factor DROPPED (not laundered as neutral 0.5).  Physical numeric bonus ×1.15 "
            "when genuinely TIGHT/SOLD_OUT.  Threshold 0.40 PROVISIONAL.  Meta-driver cards "
            "emit for ≥3 co-heating same-cluster themes.  Cross-theme heats reflect "
            "agreement among AVAILABLE surfaces only — themes with different data coverage "
            "are not on a fully comparable scale."
        ),
    }
