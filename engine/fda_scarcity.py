"""FDA drug-scarcity read — per-theme physical feed for glp1_obesity (Wave 5b / §3.4).

Maps GLP-1-relevant molecules (semaglutide, tirzepatide, liraglutide + an extensible dict)
onto a per-theme band that can serve as a physical correlate chip on the foresight cascade
theme card.

BAND semantics:
  SHORTAGE_ACTIVE    — ≥1 active shortage record for a molecule in the theme's basket.
                       Literal demand-exceeds-supply; the 2022-2025 GLP-1 thesis state.
  SHORTAGE_RESOLVED  — all recent shortage records have status "Resolved" or are
                       discontinued; no current active records.
                       "A resolved shortage = the glut tell" (§3.4). Surface explicitly.
  NONE               — no shortage records found for any molecule in the theme's basket.

Display-only. NOT a stage-changer. NOT a band input (that wiring is a calibrated later step).
Degrades to None on missing cache per house rule.

Usage: imported by foresight_cascade.py as a display chip via `theme_feed_summary` field,
mirroring how `altdata_summary` flows into cascade rows.
"""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

# ─── Extensible molecule → theme mapping ─────────────────────────────────────
# Keys are lowercase search tokens matched against generic_name (case-insensitive).
# Values are the theme keys they apply to. Add new molecules here to extend coverage.
MOLECULE_THEME_MAP: dict[str, list[str]] = {
    "semaglutide":  ["glp1_obesity"],
    "tirzepatide":  ["glp1_obesity"],
    "liraglutide":  ["glp1_obesity"],
}

# Status strings from the openFDA shortages endpoint that indicate an active shortage
_ACTIVE_STATUSES = {"current"}                      # "Current" = in shortage now
_ACTIVE_AVAILABILITY = {"limited availability", "unavailable"}  # sub-status tells
_RESOLVED_STATUSES = {"resolved", "to be discontinued"}  # no longer a supply crunch

SHORTAGE_ACTIVE = "SHORTAGE_ACTIVE"
SHORTAGE_RESOLVED = "SHORTAGE_RESOLVED"
BAND_NONE = "NONE"


def _is_active(row: pd.Series) -> bool:
    """Return True if a shortage row represents a current/active shortage."""
    status = (row.get("status") or "").strip().lower()
    avail = (row.get("availability") or "").strip().lower()
    if status in _ACTIVE_STATUSES:
        if avail in _ACTIVE_AVAILABILITY or avail == "":
            return True
    return False


def _is_resolved(row: pd.Series) -> bool:
    """Return True if a shortage row represents a resolved shortage."""
    status = (row.get("status") or "").strip().lower()
    return status in _RESOLVED_STATUSES


def compute_fda_scarcity(df: pd.DataFrame | None = None) -> dict[str, dict | None]:
    """Compute per-theme FDA shortage bands from the cached shortages DataFrame.

    Args:
        df: the shortages DataFrame (columns: generic_name, status, availability, …).
            Pass None to load from cache automatically.

    Returns:
        dict mapping theme_key -> {band, n_active, n_resolved, details, molecules_checked}
        or theme_key -> None if the cache is absent or a molecule lookup fails.

    The returned dict contains an entry for every theme in MOLECULE_THEME_MAP.
    Missing cache → ALL entries are None (honest degradation; caller surfaces as missing).
    """
    if df is None:
        try:
            from collectors.fda_shortages import load_shortages_cache
            df = load_shortages_cache()
        except Exception as e:  # noqa: BLE001
            log.warning("fda_scarcity: cache load failed: %s", e)
            df = None

    if df is None or df.empty:
        # Cache absent or empty — degrade all themes to None
        themes_touched: set[str] = set()
        for themes in MOLECULE_THEME_MAP.values():
            themes_touched.update(themes)
        return {t: None for t in themes_touched}

    # Build molecule -> matching rows index (case-insensitive substring match)
    generic_lower = df["generic_name"].str.lower().fillna("")

    # Accumulate per-theme observations
    theme_active: dict[str, list[str]] = {}
    theme_resolved: dict[str, list[str]] = {}
    theme_molecules: dict[str, list[str]] = {}

    for molecule, themes in MOLECULE_THEME_MAP.items():
        mask = generic_lower.str.contains(molecule, regex=False)
        matched = df[mask]
        for t in themes:
            theme_molecules.setdefault(t, []).append(molecule)
            if matched.empty:
                continue
            for _, row in matched.iterrows():
                if _is_active(row):
                    theme_active.setdefault(t, []).append(
                        f"{row.get('generic_name','')} [{row.get('status','')}/"
                        f"{row.get('availability','')}]"
                    )
                elif _is_resolved(row):
                    theme_resolved.setdefault(t, []).append(
                        f"{row.get('generic_name','')} [{row.get('status','')}]"
                    )

    result: dict[str, dict | None] = {}
    all_themes: set[str] = set()
    for themes in MOLECULE_THEME_MAP.values():
        all_themes.update(themes)

    for t in all_themes:
        n_active = len(theme_active.get(t) or [])
        n_resolved = len(theme_resolved.get(t) or [])
        molecules = theme_molecules.get(t, [])

        if n_active > 0:
            band = SHORTAGE_ACTIVE
            detail_parts = (theme_active.get(t) or [])[:3]  # cap display length
            rationale = (f"{n_active} active shortage record(s) — demand exceeds supply "
                         f"({', '.join(molecules)} in shortage)")
        elif n_resolved > 0:
            band = SHORTAGE_RESOLVED
            detail_parts = (theme_resolved.get(t) or [])[:3]
            rationale = (f"shortage RESOLVED ({n_resolved} record(s)) — glut tell: "
                         f"supply constraint lifted ({', '.join(molecules)})")
        else:
            band = BAND_NONE
            detail_parts = []
            rationale = f"no shortage records found for {', '.join(molecules)}"

        result[t] = {
            "band": band,
            "n_active": n_active,
            "n_resolved": n_resolved,
            "molecules_checked": molecules,
            "details": detail_parts,
            "rationale": rationale,
        }

    return result


def format_theme_feed_chip(scarcity_row: dict | None, theme_key: str) -> dict | None:
    """Format a theme_feed_summary chip for a single theme from fda_scarcity output.

    Returns a dict suitable for the cascade row's `theme_feed_summary` field, or None.
    Mirrors the structure of `altdata_summary` so the template can reuse the same chip.
    """
    if scarcity_row is None:
        return None
    band = scarcity_row.get("band")
    if not band or band == BAND_NONE:
        return None
    n_active = scarcity_row.get("n_active", 0)
    n_resolved = scarcity_row.get("n_resolved", 0)
    if band == SHORTAGE_ACTIVE:
        label = f"FDA shortage ACTIVE ({n_active} record{'s' if n_active != 1 else ''})"
        tone = "warn"          # shortage active = supply crunch; thesis supportive but caution
    elif band == SHORTAGE_RESOLVED:
        label = f"FDA shortage RESOLVED — glut tell ({n_resolved} record{'s' if n_resolved != 1 else ''})"
        tone = "cool"          # resolved = supply normalising; thesis may be maturing
    else:
        return None

    return {
        "source": "fda_shortages",
        "theme": theme_key,
        "band": band,
        "label": label,
        "tone": tone,
        "rationale": scarcity_row.get("rationale"),
        "n_active": n_active,
        "n_resolved": n_resolved,
    }
