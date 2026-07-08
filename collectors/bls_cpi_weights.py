"""BLS CPI Relative-Importance Weight Collector (keyless, fail-open).

Fetches the BLS annual relative-importance table from:
  https://www.bls.gov/cpi/tables/relative-importance/{year}.htm

The BLS website has a WAF that blocks python-requests default UA and browser UAs,
but accepts a descriptive custom UA (same pattern as the FREDGRAPH_UA workaround
in collectors/fred.py — see comment there).

Fail-open contract: on WAF/parse/network failure, the committed YAML
(`data/release_forecast/component_weights/cpi_relative_importance_{year}.yml`)
is left untouched. The function returns the committed YAML as fallback.

Cache: 12h TTL in /tmp/bls_ri_{year}.html (mirrors sibling collectors).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# Weight year active for 2026 (Dec-2025 basis). Update each January.
CURRENT_WEIGHT_YEAR = 2026

# BLS WAF workaround UA — descriptive, not browser-mimicking.
# The BLS site blocks python-requests default UA and all browser UAs,
# but allows descriptive research-oriented UAs (verified 2026-07-08).
_BLS_UA = "BLS-DataFetch/1.0 (macro-research; non-commercial)"
_BLS_BASE_URL = "https://www.bls.gov/cpi/tables/relative-importance/{year}.htm"

_CACHE_TTL_SECONDS = 12 * 3600  # 12h
_CACHE_DIR = Path("/tmp")


def _cache_path(year: int) -> Path:
    return _CACHE_DIR / f"bls_ri_{year}.html"


def _fetch_raw(year: int, timeout: int = 20) -> str | None:
    """Fetch raw HTML from BLS. Returns None on any failure."""
    try:
        import requests

        cache = _cache_path(year)
        if cache.exists():
            age = time.time() - cache.stat().st_mtime
            if age < _CACHE_TTL_SECONDS:
                log.debug("BLS RI cache hit for %d (age %.0fs)", year, age)
                return cache.read_text(encoding="utf-8")

        url = _BLS_BASE_URL.format(year=year)
        r = requests.get(
            url,
            headers={"User-Agent": _BLS_UA, "Accept": "text/html"},
            timeout=timeout,
        )
        if r.status_code != 200:
            log.warning(
                "BLS RI fetch failed: HTTP %d for %s (UA: %s)",
                r.status_code, url, _BLS_UA,
            )
            return None

        html = r.text
        cache.write_text(html, encoding="utf-8")
        log.info("BLS RI fetched and cached for year %d", year)
        return html

    except Exception as e:
        log.warning("BLS RI fetch exception: %s", e)
        return None


def _parse_table(html: str) -> dict[str, float] | None:
    """Parse BLS relative-importance HTML table.

    Returns dict of {category_name_slug: weight_float} for CPI-U column, or None on failure.
    Expects rows like:
      <tr><td>Category name</td><td>CPI-U weight</td><td>CPI-W weight</td></tr>
    """
    try:
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        weights: dict[str, float] = {}

        for row in rows:
            cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', row, re.DOTALL)
            cleaned = []
            for c in cells:
                text = re.sub(r'<[^>]+>', '', c)
                text = re.sub(r'&nbsp;', ' ', text)
                text = re.sub(r'\s+', ' ', text).strip()
                cleaned.append(text)

            if len(cleaned) < 2:
                continue
            name = cleaned[0]
            value_str = cleaned[1] if len(cleaned) > 1 else ""

            # Skip header rows, blank rows, special-aggregate section headers
            if not name or name in ("Item and Group", "Special aggregate indexes", ""):
                continue
            if value_str in ("", "&nbsp;", "U.S. City Average, CPI-U"):
                continue

            # Try parsing value as float
            try:
                val = float(value_str)
            except ValueError:
                continue

            # Slugify the category name
            slug = _slugify(name)
            weights[slug] = val

        if not weights:
            return None
        return weights

    except Exception as e:
        log.warning("BLS RI parse failed: %s", e)
        return None


def _slugify(name: str) -> str:
    """Convert BLS category name to a snake_case slug."""
    s = name.lower()
    s = re.sub(r"[',.]", "", s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s


def _load_committed_yaml(root: Path, year: int) -> dict[str, Any] | None:
    """Load the committed (fallback) YAML for year."""
    yml_path = root / "data" / "release_forecast" / "component_weights" / f"cpi_relative_importance_{year}.yml"
    if not yml_path.exists():
        log.warning("BLS RI fallback YAML not found: %s", yml_path)
        return None
    try:
        with open(yml_path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        log.warning("BLS RI fallback YAML parse failed: %s", e)
        return None


def fetch_bls_cpi_weights(
    year: int | None = None,
    root: Path | str | None = None,
    write_yaml: bool = True,
) -> dict[str, Any]:
    """Fetch BLS CPI relative-importance weights for `year`.

    Parameters
    ----------
    year : int or None
        Weight year to fetch (e.g. 2026 → Dec-2025 basis). Defaults to CURRENT_WEIGHT_YEAR.
    root : Path or None
        Repository root. Required only if write_yaml=True.
    write_yaml : bool
        If True and fetch succeeds, writes/updates the committed YAML file.

    Returns
    -------
    dict with keys matching the committed YAML schema plus 'fetch_status'.
    On failure: returns the committed YAML content with 'fetch_status': 'fallback'.
    """
    if year is None:
        year = CURRENT_WEIGHT_YEAR
    if root is not None:
        root = Path(root)

    html = _fetch_raw(year)
    parsed: dict[str, float] | None = None
    fetch_status = "fallback"

    if html is not None:
        parsed = _parse_table(html)
        if parsed:
            fetch_status = "success"
            log.info("BLS RI parsed %d weights for year %d", len(parsed), year)

    if parsed is not None and write_yaml and root is not None:
        _write_yaml(parsed, year, root)

    if parsed is not None:
        return {
            "meta": {
                "weight_year_effective": year,
                "basis": f"December {year - 1} relative importance (fetched {datetime.now().date()})",
                "source_url": _BLS_BASE_URL.format(year=year),
                "last_updated": str(datetime.now().date()),
                "fetch_status": fetch_status,
            },
            "weights": parsed,
        }

    # Fallback: return committed YAML
    log.info("BLS RI using committed YAML fallback for year %d", year)
    committed = _load_committed_yaml(root, year) if root is not None else None
    if committed:
        committed.setdefault("meta", {})["fetch_status"] = "fallback"
        return committed

    # Last resort: return empty structure
    return {
        "meta": {
            "weight_year_effective": year,
            "fetch_status": "unavailable",
            "error": "fetch failed and no committed YAML found",
        },
        "weights": {},
    }


def _write_yaml(weights: dict[str, float], year: int, root: Path) -> None:
    """Write fetched weights to the committed YAML file (updates meta section only)."""
    yml_path = root / "data" / "release_forecast" / "component_weights" / f"cpi_relative_importance_{year}.yml"
    if not yml_path.exists():
        log.warning("BLS RI write skipped: committed YAML not found at %s", yml_path)
        return
    try:
        with open(yml_path, encoding="utf-8") as f:
            current = yaml.safe_load(f)

        if current is None:
            current = {}
        current.setdefault("meta", {})["last_updated"] = str(datetime.now().date())
        current.setdefault("meta", {})["fetch_status"] = "success"
        current.setdefault("meta", {})["n_parsed_weights"] = len(weights)
        # Note: we do NOT overwrite bridge_blocks or the hand-curated entries;
        # we only update the meta timestamp. Full weight reconciliation is manual.

        with open(yml_path, "w", encoding="utf-8") as f:
            yaml.dump(current, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        log.info("BLS RI YAML meta updated at %s", yml_path)
    except Exception as e:
        log.warning("BLS RI YAML write failed: %s", e)


def get_block_weights(root: Path | str | None = None, year: int | None = None) -> dict[str, float]:
    """Return bridge block weights dict from the committed YAML.

    Returns {block_name: ri_weight} for all bridge_blocks entries.
    Fail-open: returns empty dict on any failure.
    """
    if year is None:
        year = CURRENT_WEIGHT_YEAR
    if root is None:
        # Try to infer repo root from this file's location
        root = Path(__file__).resolve().parents[1]
    root = Path(root)

    committed = _load_committed_yaml(root, year)
    if not committed:
        return {}

    try:
        bridge_blocks = committed.get("bridge_blocks", {})
        result: dict[str, float] = {}
        for block_name, block_data in bridge_blocks.items():
            if isinstance(block_data, dict):
                w = block_data.get("total_weight")
                if w is not None:
                    result[block_name] = float(w)
        return result
    except Exception as e:
        log.warning("get_block_weights failed: %s", e)
        return {}


if __name__ == "__main__":
    import sys
    import json

    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    _root = Path(__file__).resolve().parents[1]
    result = fetch_bls_cpi_weights(year=CURRENT_WEIGHT_YEAR, root=_root, write_yaml=True)
    print(json.dumps({
        "fetch_status": result.get("meta", {}).get("fetch_status"),
        "n_weights": len(result.get("weights", {})),
        "sample": dict(list(result.get("weights", {}).items())[:10]),
    }, indent=2))
