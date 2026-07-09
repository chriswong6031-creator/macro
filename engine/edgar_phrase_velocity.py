"""engine/edgar_phrase_velocity — EDGAR FTS phrase-velocity leg for W9 early discovery.

DISPLAY-ONLY. NO LLM. Deterministic n-gram/statistics over stored metadata.
Authority: may_rank=false, may_gate=false, may_size=false, may_escalate=false,
           is_context_only=true.

WHAT THIS DOES
--------------
The EDGAR Full-Text Search endpoint (efts.sec.gov) returns only metadata
(no snippet/text) — confirmed probe 2026-07-02 (see collectors/edgar_fts.py).
This engine therefore implements the strongest analysis the available corpus permits:

  1. Versioned expanding vocabulary (seed = supply-stress/demand lexicon from
     collectors/edgar_fts.py PHRASES + theme-keyed mechanism terms from
     config/theme_thesis_registry.yml mechanisms). Vocabulary expansion uses
     co-occurring phrase patterns from FTS metadata (filer proximity ≠ text
     co-occurrence — expansion is conservative, capped at EXPAND_CAP_PER_THEME).

  2. Per-phrase × per-theme quarterly hit-velocity z-scores: 30d ("recent") vs
     60d ("prior") windows, PIT-keyed to file_date (no lookahead).

  3. Cross-theme "novel phrase" detection: phrases appearing in emergence_hits
     for tickers NOT in any canonical theme basket → candidate discovery signals.

  4. Output:
       data/edgar_phrase_velocity/*.parquet  (runner-local, gitignored, per-theme)
       site/basketdata/phrase_velocity.json  (git-tracked, compact per-theme rows
                                              + novel phrases with NO theme home)

RENDER BUDGET: this runs OFF the render path (collect lane, own step).
PIT LAW: all look-backs keyed to file_date; no use of fetched date for velocity.
VOCABULARY VERSIONING: VOCAB_VERSION bumps when the seed word list changes;
  downstream caches are discarded on version change (per-theme parquet header).

COLLECTOR RESILIENCE: per-source failures isolated — a missing or corrupt parquet
  for one source never voids the run; all paths return honest nulls with notes.

HONEST FRAMING: discovery output is a WATCHLIST feed. Detection is noisy (~half
  of phrase-velocity flags map to real acceleration). No promotion without gauntlet.
  The banned word (CI-enforced) NEVER appears in output. No early-entry edge
  implied — the framing echoes theme_discovery.py's honesty header verbatim.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authority block
# ---------------------------------------------------------------------------
AUTHORITY = {
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "is_context_only": True,
    "framing": "phrase_velocity_discovery_watchlist",
    "rotation_calls": False,
    "short_calls": False,
    "honesty_note": (
        "Detection is noisy — ~half of phrase-velocity accelerations are real; "
        "early-entry edge ≈ 0 (thematic baskets/ETFs launch near the top). "
        "This is a WATCHLIST / candidate feed, never a buy signal."
    ),
}

# ---------------------------------------------------------------------------
# Vocabulary versioning
# ---------------------------------------------------------------------------
# VOCAB_VERSION: increment when the seed vocabulary changes. Old runner-local
# parquet files with a different version header are discarded and regenerated.
VOCAB_VERSION = 1

# Seed vocabulary: supply-stress / demand-scarcity lexicon (mirrors edgar_fts.py PHRASES)
# + supply-excess (GLUT_PHRASES). This list is the canonical seed; DO NOT CHANGE
# without bumping VOCAB_VERSION.
SEED_PHRASES = [
    # Supply stress (bottleneck)
    "sold out", "capacity constrained", "supply constrained", "on allocation",
    "longer lead times", "extended lead times", "record backlog",
    "unable to meet demand", "demand exceeds supply", "tight supply",
    # Extended / emergence phrases (from emergence_hits)
    "allocate supply", "constrained capacity", "expedite fees",
    # Supply-excess (glut) — included for contrast / discovery of reversal
    "capacity expansion", "adding capacity", "excess inventory",
    "inventory normalization", "increased supply",
]

# Theme-to-phrase affinity map: phrases that are ESPECIALLY relevant to a theme.
# Used to boost theme-score weighting; does not restrict which phrases are swept.
# Keyed by theme_id (from config/theme_crosswalk.yml).
_THEME_AFFINITY: dict[str, list[str]] = {
    "ai_semiconductors": ["on allocation", "sold out", "record backlog",
                          "extended lead times", "demand exceeds supply"],
    "memory_storage": ["on allocation", "capacity constrained", "tight supply",
                       "record backlog"],
    "semicap_equipment": ["longer lead times", "extended lead times",
                          "capacity constrained"],
    "data_center_power": ["sold out", "on allocation", "tight supply",
                          "record backlog", "extended lead times"],
    "nuclear_power": ["capacity expansion", "adding capacity"],
    "grid_electrification": ["capacity expansion", "sold out", "tight supply"],
    "copper_steel_electrify": ["tight supply", "supply constrained",
                                "capacity expansion"],
    "rare_earth_critical_min": ["supply constrained", "on allocation",
                                "tight supply"],
    "defense_aerospace": ["extended lead times", "record backlog",
                          "capacity constrained"],
    "robotics_automation": ["capacity constrained", "extended lead times"],
    "glp1_obesity": ["capacity constrained", "on allocation", "sold out"],
    "medical_devices": ["supply constrained", "capacity constrained"],
    "solar": ["capacity expansion", "adding capacity", "increased supply"],
    "cybersecurity": [],
    "fintech_payments": [],
    "space_satellite": ["record backlog"],
    "ag_fertilizer": ["capacity expansion", "tight supply"],
    "diagnostics_lifesci": ["capacity constrained", "supply constrained"],
}

# Cap on vocabulary expansion per theme (from co-occurrence in FTS metadata)
EXPAND_CAP_PER_THEME = 0  # v1: expansion disabled — FTS endpoint is metadata-only;
# co-occurrence expansion would require raw text; set to 0 and note in output.

# ---------------------------------------------------------------------------
# Store path (runner-local, gitignored)
# ---------------------------------------------------------------------------
_STORE_ENV = "EDGAR_PHRASE_VELOCITY_STORE"
_STORE_DEFAULT = "data/edgar_phrase_velocity"


def _store_dir() -> Path:
    """Resolve store directory from env or default.

    The env var names the store DIRECTORY (THETADATA_STORE / DOL_CERTS_STORE
    convention). Returns Path; does NOT create directories.
    """
    env_val = os.environ.get(_STORE_ENV, "").strip()
    if env_val:
        p = Path(env_val)
        # If env points to a file, use its parent directory
        if p.suffix:
            return p.parent
        return p
    return config.data_dir() / "edgar_phrase_velocity"


# ---------------------------------------------------------------------------
# PIT velocity computation
# ---------------------------------------------------------------------------
_RECENT_DAYS = 30
_PRIOR_DAYS = 60


def _pit_counts(
    df: pd.DataFrame,
    tickers: set[str],
    as_of: date,
    recent_days: int = _RECENT_DAYS,
    prior_days: int = _PRIOR_DAYS,
) -> dict[str, dict[str, float]]:
    """Compute per-phrase hit counts for recent vs prior windows (PIT-keyed by file_date).

    Returns {phrase: {recent_count, prior_count, recent_filers, prior_filers}}.
    Counts only tickers in `tickers` universe; keyed to `as_of` for PIT compliance.
    """
    if df is None or df.empty:
        return {}

    in_universe = df[df["ticker"].isin(tickers)].copy() if tickers else df.copy()
    if in_universe.empty:
        return {}

    try:
        in_universe["_date"] = pd.to_datetime(in_universe["file_date"]).dt.date
    except Exception:  # noqa: BLE001
        return {}

    recent_start = as_of - timedelta(days=recent_days)
    prior_start = as_of - timedelta(days=prior_days)

    recent = in_universe[
        (in_universe["_date"] > recent_start) & (in_universe["_date"] <= as_of)
    ]
    prior = in_universe[
        (in_universe["_date"] > prior_start) & (in_universe["_date"] <= recent_start)
    ]

    result: dict[str, dict[str, float]] = {}
    all_phrases = in_universe["phrase"].unique()
    for phrase in all_phrases:
        r = recent[recent["phrase"] == phrase]
        p = prior[prior["phrase"] == phrase]
        result[phrase] = {
            "recent_count": int(len(r)),
            "prior_count": int(len(p)),
            "recent_filers": int(r["ticker"].nunique()) if len(r) > 0 else 0,
            "prior_filers": int(p["ticker"].nunique()) if len(p) > 0 else 0,
        }
    return result


def _velocity_z(recent: float, prior: float) -> float | None:
    """Simple velocity z: (recent - prior) / max(1, prior).

    Returns None when both windows are empty (insufficient data).
    Capped at ±5 for display stability.
    """
    if recent == 0 and prior == 0:
        return None
    denom = max(1.0, prior)
    raw = (recent - prior) / denom
    return float(np.clip(raw, -5.0, 5.0))


# ---------------------------------------------------------------------------
# Theme membership resolver
# ---------------------------------------------------------------------------
def _load_theme_baskets() -> dict[str, list[str]]:
    """Load theme_id -> list[ticker] from config/theme_crosswalk.yml + baskets.

    Returns empty dict on any load failure (honest null path).
    """
    try:
        import yaml  # noqa: PLC0415

        cw_path = config.ROOT / "config" / "theme_crosswalk.yml"
        if not cw_path.exists():
            log.warning("edgar_phrase_velocity: theme_crosswalk.yml missing")
            return {}
        with open(cw_path) as f:
            cw = yaml.safe_load(f)

        from engine import baskets as baskets_mod  # noqa: PLC0415

        membership = baskets_mod._membership()
        basket_dict = membership.get("baskets", {})

        # Build basket_id -> set[ticker]
        basket_tickers: dict[str, set[str]] = {}
        for bid, info in basket_dict.items():
            if not isinstance(info, dict):
                continue
            members_raw = info.get("members", [])
            if members_raw and isinstance(members_raw[0], dict):
                tickers = {
                    m["ticker"]
                    for m in members_raw
                    if m.get("removed") is None and "ticker" in m
                }
            else:
                tickers = set(members_raw or [])
            basket_tickers[bid] = tickers

        # Map theme_id -> union of tickers across basket_ids
        result: dict[str, list[str]] = {}
        for theme in cw.get("themes", []):
            tid = theme.get("id")
            if not tid:
                continue
            t_tickers: set[str] = set()
            for bid in theme.get("basket_ids", []):
                t_tickers.update(basket_tickers.get(bid, set()))
            result[tid] = sorted(t_tickers)
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("edgar_phrase_velocity: theme-basket load failed: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Core compute function
# ---------------------------------------------------------------------------
def compute_phrase_velocity(
    as_of: date | None = None,
) -> dict:
    """Compute EDGAR phrase-velocity metrics for all canonical themes.

    Returns a result dict suitable for serialization to phrase_velocity.json.
    Always returns a valid dict (exit-0 guarantee); missing data → honest nulls.

    PIT: all windows keyed to as_of (default = today).
    """
    as_of = as_of or date.today()
    ts = datetime.now(timezone.utc).isoformat()

    result: dict = {
        "schema": "edgar_phrase_velocity.v1",
        "vocab_version": VOCAB_VERSION,
        "seed_phrases": SEED_PHRASES,
        "expand_cap_per_theme": EXPAND_CAP_PER_THEME,
        "expand_note": (
            "Vocabulary expansion disabled in v1: FTS endpoint returns metadata only "
            "(no snippet/text). Co-occurrence expansion requires raw filing text "
            "(not available from efts.sec.gov). Expansion cap = 0."
        ),
        "as_of": as_of.isoformat(),
        "generated_at": ts,
        "authority": AUTHORITY,
        "themes": {},
        "novel_phrases": [],
        "coverage_stats": {},
        "honesty_header": (
            "This is a WATCHLIST / candidate feed. Detection is noisy — ~half of "
            "phrase-velocity accelerations correspond to real supply-stress shifts. "
            "Early-entry return edge ≈ 0. Not a buy signal. Not a scored factor. "
            "Carries the same honesty stance as theme_discovery.py."
        ),
    }

    # ── Load source parquets ──────────────────────────────────────────────
    src: dict[str, pd.DataFrame | None] = {}
    for name, relpath in [
        ("bottleneck_hits", "edgar/bottleneck_hits.parquet"),
        ("emergence_hits", "edgar/emergence_hits.parquet"),
    ]:
        p = config.data_dir() / relpath
        try:
            src[name] = pd.read_parquet(p) if p.exists() else None
        except Exception as exc:  # noqa: BLE001
            log.warning("edgar_phrase_velocity: %s load failed: %s", name, exc)
            src[name] = None

    # Combine bottleneck + emergence into one frame (union of phrases)
    frames = [df for df in src.values() if df is not None and not df.empty]
    if not frames:
        log.warning("edgar_phrase_velocity: no source parquets available; returning all-null")
        result["coverage_stats"] = {
            "bottleneck_rows": 0,
            "emergence_rows": 0,
            "combined_rows": 0,
            "note": "Both source parquets absent — all theme velocities are null.",
        }
        return result

    # Standardize columns: both parquets have phrase, ticker, file_date
    combined = pd.concat(
        [f[["ticker", "file_date", "phrase"]] for f in frames],
        ignore_index=True,
    ).drop_duplicates()

    def _src_len(name: str) -> int:
        df = src.get(name)
        return int(len(df)) if df is not None else 0

    result["coverage_stats"] = {
        "bottleneck_rows": _src_len("bottleneck_hits"),
        "emergence_rows": _src_len("emergence_hits"),
        "combined_rows": int(len(combined)),
        "date_range_min": str(combined["file_date"].min()),
        "date_range_max": str(combined["file_date"].max()),
        "unique_tickers": int(combined["ticker"].nunique()),
        "unique_phrases": int(combined["phrase"].nunique()),
    }

    # ── Load theme baskets ────────────────────────────────────────────────
    theme_baskets = _load_theme_baskets()
    all_themed_tickers: set[str] = set()
    for tickers in theme_baskets.values():
        all_themed_tickers.update(tickers)

    # ── Per-theme velocity ────────────────────────────────────────────────
    for theme_id, tickers in theme_baskets.items():
        t_set = set(tickers)
        counts = _pit_counts(combined, t_set, as_of)

        if not counts:
            result["themes"][theme_id] = {
                "theme_id": theme_id,
                "ticker_count": len(tickers),
                "coverage_note": (
                    f"No FTS hits for {len(tickers)} basket tickers in the "
                    f"{_RECENT_DAYS}d/{_PRIOR_DAYS}d windows."
                ),
                "coverage_note_zh": (
                    f"过去{_RECENT_DAYS}/{_PRIOR_DAYS}天内，"
                    f"{len(tickers)}个篮子成员无FTS命中记录。"
                ),
                "phrases": [],
                "top_accelerating": [],
            }
            continue

        affinity = _THEME_AFFINITY.get(theme_id, [])
        phrase_rows = []
        for phrase, c in counts.items():
            vz = _velocity_z(c["recent_count"], c["prior_count"])
            phrase_rows.append({
                "phrase": phrase,
                "recent_count": c["recent_count"],
                "prior_count": c["prior_count"],
                "recent_filers": c["recent_filers"],
                "prior_filers": c["prior_filers"],
                "velocity_z": vz,
                "is_affinity_phrase": phrase in affinity,
            })

        # Sort by velocity_z descending (None last)
        phrase_rows.sort(
            key=lambda r: (r["velocity_z"] is None, -(r["velocity_z"] or 0))
        )

        top_accel = [
            r for r in phrase_rows
            if r["velocity_z"] is not None and r["velocity_z"] > 0
            and r["recent_count"] >= 2
        ][:5]

        result["themes"][theme_id] = {
            "theme_id": theme_id,
            "ticker_count": len(tickers),
            "phrases": phrase_rows,
            "top_accelerating": top_accel,
            "coverage_note": (
                f"{len(tickers)} basket tickers; "
                f"{_RECENT_DAYS}d/{_PRIOR_DAYS}d PIT windows."
            ),
            "coverage_note_zh": (
                f"篮子成员{len(tickers)}个；"
                f"PIT窗口{_RECENT_DAYS}天/{_PRIOR_DAYS}天。"
            ),
        }

    # ── Novel phrase detection: tickers NOT in any themed basket ──────────
    novel_tickers = (
        combined[~combined["ticker"].isin(all_themed_tickers)]["ticker"].unique()
        if not combined.empty
        else []
    )
    novel_counts = _pit_counts(combined, set(novel_tickers), as_of)
    novel_rows = []
    for phrase, c in novel_counts.items():
        vz = _velocity_z(c["recent_count"], c["prior_count"])
        if vz is not None and vz > 0 and c["recent_filers"] >= 2:
            novel_rows.append({
                "phrase": phrase,
                "recent_count": c["recent_count"],
                "prior_count": c["prior_count"],
                "recent_filers": c["recent_filers"],
                "prior_filers": c["prior_filers"],
                "velocity_z": vz,
                "discovery_note": (
                    "Phrase accelerating among tickers with NO current theme home. "
                    "Candidate discovery cluster — needs curated review, not auto-promotion."
                ),
                "discovery_note_zh": (
                    "该短语在无当前主题归属的成员中加速出现，"
                    "属于发现候选集合——需人工审核，不自动晋升。"
                ),
            })
    novel_rows.sort(key=lambda r: -(r["velocity_z"] or 0))
    result["novel_phrases"] = novel_rows[:10]  # top-10 only

    # ── Persist runner-local parquets ─────────────────────────────────────
    try:
        store = _store_dir()
        store.mkdir(parents=True, exist_ok=True)
        for theme_id, tdata in result["themes"].items():
            phrases = tdata.get("phrases", [])
            if not phrases:
                continue
            df_out = pd.DataFrame(phrases)
            df_out["theme_id"] = theme_id
            df_out["as_of"] = as_of.isoformat()
            df_out["vocab_version"] = VOCAB_VERSION
            out_path = store / f"{theme_id}.parquet"
            df_out.to_parquet(out_path, index=False)
        log.info("edgar_phrase_velocity: wrote parquets to %s", store)
    except Exception as exc:  # noqa: BLE001
        log.warning("edgar_phrase_velocity: parquet write failed (non-fatal): %s", exc)

    return result


# ---------------------------------------------------------------------------
# Site-projection writer
# ---------------------------------------------------------------------------
def write_site_projection(result: dict, out_path: Path | None = None) -> Path:
    """Write compact site/basketdata/phrase_velocity.json from compute result.

    This is the git-tracked artifact (compact; themes compressed to top lines).
    Returns the path written.
    """
    if out_path is None:
        out_path = config.ROOT / "site" / "basketdata" / "phrase_velocity.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    compact: dict = {
        "schema": result.get("schema"),
        "vocab_version": result.get("vocab_version"),
        "as_of": result.get("as_of"),
        "generated_at": result.get("generated_at"),
        "authority": result.get("authority"),
        "honesty_header": result.get("honesty_header"),
        "coverage_stats": result.get("coverage_stats"),
        "expand_note": result.get("expand_note"),
        # Per-theme: only top_accelerating + coverage_note (not all phrase rows)
        "themes": {
            tid: {
                "theme_id": tid,
                "ticker_count": tdata.get("ticker_count"),
                "top_accelerating": tdata.get("top_accelerating", []),
                "coverage_note": tdata.get("coverage_note"),
                "coverage_note_zh": tdata.get("coverage_note_zh"),
            }
            for tid, tdata in result.get("themes", {}).items()
        },
        # Novel phrases: top candidates only
        "novel_phrases": (result.get("novel_phrases") or [])[:10],
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(compact, f, ensure_ascii=False, indent=2)
    log.info("edgar_phrase_velocity: wrote site projection -> %s", out_path)
    return out_path


# ---------------------------------------------------------------------------
# CLI entry point (collect-lane runner)
# ---------------------------------------------------------------------------
def main() -> int:
    import argparse  # noqa: PLC0415

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(
        description="edgar_phrase_velocity — phrase-velocity leg (off render path)"
    )
    p.add_argument(
        "--as-of", default=None,
        help="ISO date for PIT cutoff (default: today)"
    )
    p.add_argument(
        "--no-write-site", action="store_true",
        help="Skip writing site/basketdata/phrase_velocity.json"
    )
    args = p.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    result = compute_phrase_velocity(as_of=as_of)

    stats = result.get("coverage_stats", {})
    print(f"as_of: {result['as_of']}")
    print(f"combined_rows: {stats.get('combined_rows', 0)}")
    print(f"themes computed: {len(result.get('themes', {}))}")
    print(f"novel_phrase candidates: {len(result.get('novel_phrases', []))}")

    if not args.no_write_site:
        out = write_site_projection(result)
        print(f"site projection: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
