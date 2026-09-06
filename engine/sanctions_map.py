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
from pathlib import Path
from typing import Any

import yaml

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


def _load_programs_config(path: Path = PROGRAMS_CONFIG) -> list[dict]:
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    return raw.get("programs") or []


def _load_program_code_counts(sdn_file: Path = SDN_FILE) -> dict[str, int]:
    """Count SDN entries per OFAC programme code from the raw snapshot.
    Column 7 (0-indexed) is OFAC's published 'program' field."""
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
            if len(row) > 7 and row[7].strip():
                code = row[7].strip()
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


def build(
    sdn_file: Path = SDN_FILE,
    meta_file: Path = META_FILE,
    programs_config: Path = PROGRAMS_CONFIG,
) -> dict[str, Any]:
    """Build the Sanctions Map view model. Never raises."""
    try:
        code_counts = _load_program_code_counts(sdn_file)
        meta = _load_meta(meta_file)
        config_rows = _load_programs_config(programs_config)
    except Exception:
        code_counts, meta, config_rows = {}, {}, []

    if not code_counts:
        return {
            "as_of": None,
            "source_url": meta.get("source_url"),
            "fetched_at": meta.get("fetched_at"),
            "n_programs_total": 0,
            "countries": [],
            "unresolved": [],
            "coverage": None,
        }

    by_code = {row["code"]: row for row in config_rows if row.get("code")}

    by_iso3: dict[str, dict] = {}
    unresolved: list[dict] = []
    n_programs_total = 0
    resolved_count = 0
    unresolved_count = 0

    for code, n_entries in code_counts.items():
        n_programs_total += 1
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
                "name_en": row.get("name_en", iso3),
                "name_zh": row.get("name_zh", iso3),
                "n_programs": 0,
                "programs": [],
            },
        )
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
        "as_of": meta.get("list_published_date"),
        "source_url": meta.get("source_url"),
        "fetched_at": meta.get("fetched_at"),
        "n_programs_total": n_programs_total,
        "countries": countries,
        "unresolved": unresolved,
        "coverage": {"resolved": resolved_count, "unresolved": unresolved_count},
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=2, default=str))
