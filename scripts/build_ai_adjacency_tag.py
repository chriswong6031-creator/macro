"""Build the AI-adjacency ticker tag table (DISPLAY-ONLY, no score).

Produces:
  data/breadth/ticker_ai_tag.parquet   — ai_core | ai_infra_power tags per ticker
  data/breadth/ticker_ai_tag_log.parquet — change log (adds/removes/reclasses)

Sources (read-only, committed):
  finviz_themes/finviz_themes_map.json   — 'Artificial Intelligence' theme subsectors
  data/baskets/membership.json          — basket-level membership with slug keys

Tag classes:
  ai_core         — finviz AI subsectors UNION ai_infra/ai_software/ai_neoclouds/
                    ai_semiconductors/semicap_equipment/memory_storage/ai_agents baskets
  ai_infra_power  — data_center_power/power_grid/nuclear_power/uranium_miners
                    (assigned only if not already ai_core)

Conflict rule: if a ticker is in BOTH AI sources AND an explicit non_ai basket
(non_ai_software / non_ai_tech), AI wins but a log.warning is emitted (data smell).

Output is sorted by ticker (deterministic). Same inputs → identical bytes.
Only AI-classed tickers are stored; non_ai is the complement (computed downstream).

ensure_ai_tags(force=False) -> pd.DataFrame | None:
  Regenerates when tag file is missing or source as_of/version changed; else returns
  existing. Never raises.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source paths
# ---------------------------------------------------------------------------

def _finviz_path() -> Path:
    return config.ROOT / "finviz_themes" / "finviz_themes_map.json"


def _membership_path() -> Path:
    return config.data_dir() / "baskets" / "membership.json"


def _tag_path() -> Path:
    return config.data_dir() / "breadth" / "ticker_ai_tag.parquet"


def _log_path() -> Path:
    return config.data_dir() / "breadth" / "ticker_ai_tag_log.parquet"


# ---------------------------------------------------------------------------
# Basket slug definitions
# ---------------------------------------------------------------------------

_AI_CORE_BASKETS = [
    "ai_infra", "ai_software", "ai_neoclouds", "ai_semiconductors",
    "semicap_equipment", "memory_storage", "ai_agents",
]

_AI_INFRA_POWER_BASKETS = [
    "data_center_power", "power_grid", "nuclear_power", "uranium_miners",
]

_NON_AI_BASKETS = ["non_ai_software", "non_ai_tech"]


# ---------------------------------------------------------------------------
# Source readers
# ---------------------------------------------------------------------------

def _read_finviz_ai_tickers() -> tuple[dict[str, list[str]], str]:
    """Return ({subsector_key: [tickers]}, asof_str) for the AI theme."""
    p = _finviz_path()
    if not p.exists():
        log.warning("finviz_themes_map.json not found at %s", p)
        return {}, ""
    try:
        d = json.loads(p.read_text())
        asof = d.get("asof", "")
        themes = d.get("themes", [])
        for t in themes:
            if t.get("theme") == "Artificial Intelligence":
                result: dict[str, list[str]] = {}
                for s in t.get("subsectors", []):
                    key = s.get("key", "")
                    members = [m for m in s.get("members", []) if isinstance(m, str)]
                    if key and members:
                        result[key] = members
                return result, asof
        log.warning("'Artificial Intelligence' theme not found in finviz_themes_map.json")
        return {}, asof
    except Exception as e:  # noqa: BLE001
        log.warning("finviz read failed: %s", e)
        return {}, ""


def _read_membership_baskets(slugs: list[str]) -> tuple[dict[str, list[str]], str]:
    """Return ({slug: [active_tickers]}, version) from membership.json."""
    p = _membership_path()
    if not p.exists():
        log.warning("membership.json not found at %s", p)
        return {}, ""
    try:
        d = json.loads(p.read_text())
        version = d.get("version", "")
        baskets = d.get("baskets", {})
        result: dict[str, list[str]] = {}
        for slug in slugs:
            b = baskets.get(slug)
            if b is None:
                log.warning("basket slug '%s' not found in membership.json", slug)
                continue
            # Only active members (removed == None)
            members = [
                m["ticker"] for m in b.get("members", [])
                if isinstance(m, dict) and m.get("removed") is None
            ]
            result[slug] = members
        return result, version
    except Exception as e:  # noqa: BLE001
        log.warning("membership.json read failed: %s", e)
        return {}, ""


# ---------------------------------------------------------------------------
# Source fingerprint: the version key used to decide whether to regenerate
# ---------------------------------------------------------------------------

def _source_fingerprint() -> str:
    """Stable string encoding source versions; changed input -> different fingerprint."""
    try:
        fv_p = _finviz_path()
        fv_asof = ""
        if fv_p.exists():
            d = json.loads(fv_p.read_text())
            fv_asof = d.get("asof", "")

        mb_p = _membership_path()
        mb_ver = ""
        if mb_p.exists():
            d2 = json.loads(mb_p.read_text())
            mb_ver = d2.get("version", "")

        return f"finviz:{fv_asof}|membership:{mb_ver}"
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------------------
# Core build logic
# ---------------------------------------------------------------------------

def _build_tags() -> pd.DataFrame | None:
    """Build the tag DataFrame from source files.

    Returns DataFrame with columns (ticker, tag, sources, as_of) sorted by ticker.
    Returns None only on catastrophic failure (no source data at all).
    """
    # Load finviz AI subsectors
    fv_subs, fv_asof = _read_finviz_ai_tickers()
    all_fv_tickers: set[str] = set()
    fv_sources: dict[str, list[str]] = {}  # ticker -> [source tags]
    for sub_key, members in fv_subs.items():
        for ticker in members:
            all_fv_tickers.add(ticker)
            fv_sources.setdefault(ticker, []).append(f"finviz:{sub_key}")

    # Load basket memberships
    all_slugs = _AI_CORE_BASKETS + _AI_INFRA_POWER_BASKETS + _NON_AI_BASKETS
    basket_data, mb_version = _read_membership_baskets(all_slugs)

    if not all_fv_tickers and not basket_data:
        log.error("No source data available for AI tag build")
        return None

    # Build ai_core ticker set with sources
    # ai_core = finviz AI tickers UNION ai_core basket members
    ai_core_tickers: dict[str, list[str]] = {}
    for ticker in all_fv_tickers:
        ai_core_tickers.setdefault(ticker, []).extend(fv_sources.get(ticker, []))

    for slug in _AI_CORE_BASKETS:
        for ticker in basket_data.get(slug, []):
            ai_core_tickers.setdefault(ticker, []).append(f"basket:{slug}")

    # Build ai_infra_power set (only if not already in ai_core)
    ai_infra_power_tickers: dict[str, list[str]] = {}
    for slug in _AI_INFRA_POWER_BASKETS:
        for ticker in basket_data.get(slug, []):
            if ticker not in ai_core_tickers:
                ai_infra_power_tickers.setdefault(ticker, []).append(f"basket:{slug}")

    # Non-AI tickers for conflict detection
    non_ai_tickers: set[str] = set()
    for slug in _NON_AI_BASKETS:
        for ticker in basket_data.get(slug, []):
            non_ai_tickers.add(ticker)

    # Conflict check: AI wins, but log a warning for data quality
    ai_all = set(ai_core_tickers) | set(ai_infra_power_tickers)
    conflicts = ai_all & non_ai_tickers
    if conflicts:
        for ticker in sorted(conflicts):
            log.warning(
                "Conflict: %s in both AI source and non_ai basket — AI tag wins (data smell)",
                ticker,
            )

    # Determine as_of (max of source dates)
    as_of_parts = [fv_asof, mb_version]
    as_of = max((x for x in as_of_parts if x), default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    # Assemble rows
    rows: list[dict] = []
    for ticker, src_list in sorted(ai_core_tickers.items()):
        rows.append({
            "ticker": ticker,
            "tag": "ai_core",
            "sources": ";".join(sorted(set(src_list))),
            "as_of": as_of,
        })
    for ticker, src_list in sorted(ai_infra_power_tickers.items()):
        rows.append({
            "ticker": ticker,
            "tag": "ai_infra_power",
            "sources": ";".join(sorted(set(src_list))),
            "as_of": as_of,
        })

    if not rows:
        log.error("AI tag build produced zero rows")
        return None

    df = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    log.info(
        "AI tag build: ai_core=%d ai_infra_power=%d total=%d (conflicts with non_ai=%d)",
        (df["tag"] == "ai_core").sum(),
        (df["tag"] == "ai_infra_power").sum(),
        len(df),
        len(conflicts),
    )
    return df


def _append_change_log(new_df: pd.DataFrame) -> None:
    """Append rows to the change log for any adds/removes/reclasses vs current on-disk tag file."""
    tag_path = _tag_path()
    if not tag_path.exists():
        # No previous version — no diff to log
        return
    try:
        old_df = pd.read_parquet(tag_path)
    except Exception as e:  # noqa: BLE001
        log.warning("Could not read old tag file for diff: %s", e)
        return

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    old_map = dict(zip(old_df["ticker"], old_df["tag"])) if not old_df.empty else {}
    new_map = dict(zip(new_df["ticker"], new_df["tag"]))

    old_set = set(old_map)
    new_set = set(new_map)

    change_rows: list[dict] = []

    # Adds
    for ticker in sorted(new_set - old_set):
        change_rows.append({
            "date": today_str,
            "ticker": ticker,
            "old_tag": None,
            "new_tag": new_map[ticker],
        })

    # Removes
    for ticker in sorted(old_set - new_set):
        change_rows.append({
            "date": today_str,
            "ticker": ticker,
            "old_tag": old_map[ticker],
            "new_tag": None,
        })

    # Reclasses
    for ticker in sorted(old_set & new_set):
        if old_map[ticker] != new_map[ticker]:
            change_rows.append({
                "date": today_str,
                "ticker": ticker,
                "old_tag": old_map[ticker],
                "new_tag": new_map[ticker],
            })

    if not change_rows:
        log.info("AI tag log: no changes vs previous version")
        return

    new_log = pd.DataFrame(change_rows)
    log_path = _log_path()
    if log_path.exists():
        try:
            old_log = pd.read_parquet(log_path)
            combined = pd.concat([old_log, new_log], ignore_index=True)
        except Exception:  # noqa: BLE001
            combined = new_log
    else:
        combined = new_log

    combined.to_parquet(log_path, index=False)
    log.info("AI tag log: %d change(s) appended", len(change_rows))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def ensure_ai_tags(force: bool = False) -> pd.DataFrame | None:
    """Return the AI tag DataFrame, regenerating if needed.

    Regenerates when:
      - The tag parquet does not exist, OR
      - The source fingerprint (finviz asof + membership version) has changed, OR
      - force=True

    Never raises. Returns None on failure.
    """
    tag_path = _tag_path()
    sentinel_path = tag_path.with_suffix(".version")

    current_fp = _source_fingerprint()

    # Check whether we can reuse the cached file
    if not force and tag_path.exists() and sentinel_path.exists():
        try:
            stored_fp = sentinel_path.read_text().strip()
            if stored_fp == current_fp:
                df = pd.read_parquet(tag_path)
                log.debug("AI tags up-to-date (fingerprint: %s)", current_fp)
                return df
        except Exception:  # noqa: BLE001
            pass  # fall through to rebuild

    log.info("AI tags: regenerating (fingerprint: %s)", current_fp)
    try:
        df = _build_tags()
        if df is None:
            return None

        tag_path.parent.mkdir(parents=True, exist_ok=True)

        # Compute change log before overwriting
        _append_change_log(df)

        # Write tag file (deterministic: sorted by ticker)
        df.to_parquet(tag_path, index=False)

        # Write fingerprint sentinel
        sentinel_path.write_text(current_fp)

        return df
    except Exception as e:  # noqa: BLE001
        log.error("ensure_ai_tags failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    df = ensure_ai_tags(force=True)
    if df is not None:
        print(f"Generated {len(df)} AI-tagged tickers")
        print(df["tag"].value_counts().to_string())
    else:
        print("AI tag build failed")
        sys.exit(1)
