"""engine/sanctions_map.py — pure leaf view-model builder for the Sanctions
Map page (packet A-F02-1). Display-only, like engine.strategic_reserves: no
LLM originates any attribution, count, or rung. Every country<->programme
edge comes from the human-reviewed config/sanctions_ofac_programs.yml.

Never raises. Nulls are ``None``, never ``0``.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

import yaml

from engine.intl_risk import _IMF_COUNTRIES

# Shared ISO3 key convention with intl_risk (acceptance 3): this leaf must not
# mint a parallel country master. Painted geometry comes from the existing
# Natural Earth worldmap partial; attribution rows carry display names.
SHARED_ISO3_KEYS = frozenset(_IMF_COUNTRIES)

STORE_DIR = Path("data/sanctions_ofac")
SDN_FILE = STORE_DIR / "sdn_snapshot.csv"
META_FILE = STORE_DIR / "meta.json"
PROGRAMS_CONFIG = Path("config/sanctions_ofac_programs.yml")


def _rung(n: int) -> int:
    """Three-state ladder: 1 programme -> 1, 2-3 -> 2, 4+ -> 3."""
    if n >= 4:
        return 3
    if n >= 2:
        return 2
    return 1


UNKNOWN_RUNG = "x"
NOT_NAMED_RUNG = 0


def split_program_field(raw: str) -> list[str]:
    """OFAC's 'program' field packs multiple codes as ``[A] [B]`` — split on
    the ``] [`` join (any whitespace) and strip stray brackets/whitespace.
    Shared by collectors/ofac_sdn.py so both parsers agree on whitespace
    variants."""
    raw = (raw or "").strip()
    if not raw or raw == "-0-":
        return []
    parts = re.split(r"\]\s*\[", raw)
    return [p.strip().strip("[]").strip() for p in parts if p.strip().strip("[]").strip()]


# Back-compat alias used by older call sites / tests.
_split_program_field = split_program_field


def rungs_for(vm: dict, all_iso3=None) -> dict:
    """Per-country rung map for the world map SVG, honest about unknown
    coverage (acceptance 3: missing coverage prints as unknown, never as
    zero).

    - Positively resolved countries keep their 1/2/3 rung.
    - When any *country-scoped* OFAC programme failed to resolve
      (``coverage.unresolved > 0``), every other known country is painted
      unknown (hatch) — we cannot prove they are unsanctioned.
    - When country-scoped coverage is fully resolved, absent countries are
      an honest ``0`` ("not named"). Thematic programmes never trigger the
      hatch — they are not country attributions.
    """
    rungs: dict = {}
    coverage = vm.get("coverage") or {}
    unresolved = int(coverage.get("unresolved") or 0)
    if unresolved > 0:
        for iso3 in (all_iso3 or ()):
            rungs[iso3] = UNKNOWN_RUNG
    else:
        for iso3 in (all_iso3 or ()):
            rungs[iso3] = NOT_NAMED_RUNG
    for c in vm.get("countries") or []:
        rungs[c["iso3"]] = c["rung"]
    return rungs


def _load_programs_config(path: Path = PROGRAMS_CONFIG) -> tuple[list[dict], set[str]]:
    if not path.exists():
        return [], set()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return [], set()
    thematic = {
        row["code"]
        for row in (raw.get("thematic") or [])
        if isinstance(row, dict) and row.get("code")
    }
    return list(raw.get("programs") or []), thematic


def _load_program_code_counts(sdn_file: Path = SDN_FILE) -> dict[str, int]:
    """Count SDN entries per OFAC programme code from the raw snapshot.
    Column 3 (0-indexed) is OFAC's published 'program' field (verified
    against a live SDN.CSV fetch 2026-09-05 — column 7 was wrong)."""
    counts: dict[str, int] = {}
    if not sdn_file.exists():
        return counts
    try:
        text = sdn_file.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return counts
    try:
        reader = csv.reader(io.StringIO(text))
        for row in reader:
            if len(row) > 3 and row[3].strip():
                for code in split_program_field(row[3]):
                    counts[code] = counts.get(code, 0) + 1
    except Exception:
        return {}
    return counts


def _load_meta(meta_file: Path = META_FILE) -> dict:
    if not meta_file.exists():
        return {}
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _as_of_from_meta(meta: dict) -> str | None:
    """Prefer OFAC list_published_date; fall back to the fetch date so the
    page never claims 'unknown' when we have a verified snapshot timestamp."""
    published = meta.get("list_published_date")
    if published:
        return str(published)[:10]
    fetched = meta.get("fetched_at")
    if fetched:
        return str(fetched)[:10]
    return None


def build(
    sdn_file: Path = SDN_FILE,
    meta_file: Path = META_FILE,
    programs_config: Path = PROGRAMS_CONFIG,
) -> dict[str, Any]:
    """Build the Sanctions Map view model. Never raises."""
    try:
        code_counts = _load_program_code_counts(sdn_file)
        meta = _load_meta(meta_file)
        config_rows, thematic_codes = _load_programs_config(programs_config)
    except Exception:
        code_counts, meta, config_rows, thematic_codes = {}, {}, [], set()

    if not code_counts:
        return {
            "as_of": _as_of_from_meta(meta),
            "source_url": meta.get("source_url"),
            "fetched_at": meta.get("fetched_at"),
            "n_programs_total": 0,
            "n_countries": 0,
            "countries": [],
            "unresolved": [],
            "thematic": [],
            "coverage": None,
        }

    by_code = {row["code"]: row for row in config_rows if row.get("code")}

    by_iso3: dict[str, dict] = {}
    unresolved: list[dict] = []
    thematic: list[dict] = []
    n_programs_total = 0
    resolved_count = 0
    unresolved_count = 0
    thematic_count = 0

    for code, n_entries in code_counts.items():
        n_programs_total += 1
        if code in thematic_codes:
            thematic.append({"code": code, "n_entries": n_entries})
            thematic_count += 1
            continue
        row = by_code.get(code)
        if row is None or not row.get("iso3"):
            unresolved.append({"code": code, "n_entries": n_entries})
            unresolved_count += 1
            continue
        resolved_count += 1
        iso3 = row["iso3"]
        entry = by_iso3.setdefault(
            iso3,
            {
                "iso3": iso3,
                "name_en": row.get("country_name_en") or row.get("name_en", iso3),
                "name_zh": row.get("country_name_zh") or row.get("name_zh", iso3),
                "n_programs": 0,
                "programs": [],
            },
        )
        # Prefer explicit country_* once set; don't overwrite with a later program title.
        if row.get("country_name_en"):
            entry["name_en"] = row["country_name_en"]
        if row.get("country_name_zh"):
            entry["name_zh"] = row["country_name_zh"]
        entry["n_programs"] += 1
        entry["programs"].append(
            {
                "code": code,
                "name_en": row.get("name_en"),
                "name_zh": row.get("name_zh"),
                "url": row.get("ofac_program_url"),
            }
        )

    countries = []
    for iso3, entry in by_iso3.items():
        entry["rung"] = _rung(entry["n_programs"])
        countries.append(entry)
    countries.sort(key=lambda c: c["n_programs"], reverse=True)

    return {
        "as_of": _as_of_from_meta(meta),
        "source_url": meta.get("source_url"),
        "fetched_at": meta.get("fetched_at"),
        "n_programs_total": n_programs_total,
        "n_countries": len(countries),
        "countries": countries,
        "unresolved": unresolved,
        "thematic": thematic,
        "coverage": {
            "resolved": resolved_count,
            "unresolved": unresolved_count,
            "thematic": thematic_count,
        },
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, default=str))
