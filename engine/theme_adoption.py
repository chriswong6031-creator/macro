"""engine/theme_adoption — GitHub developer-adoption velocity leg for W9 discovery.

DISPLAY-ONLY. Authority: may_rank=false, may_gate=false, may_size=false,
may_escalate=false, is_context_only=true.

WHAT THIS DOES
--------------
Rolls up the per-stock GitHub star/fork data (data/github/repo_stars.parquet,
collected by collectors/github_repos.py) to a per-basket and per-theme level.

Signals computed per basket:
  star_velocity_7d_z  — 7-day star delta normalized by trailing 7d baseline,
                        cross-sectionally z-scored across in-universe tickers.
  star_pct_rank       — within-universe percentile rank of star count (static
                        mindshare proxy; no baseline needed).
  coverage_n          — number of tickers with GitHub data in this basket.

HONEST NULLS
  Baskets with zero coverage → explicit null entry with coverage_note.
  Short history (19 days as of 2026-07-09) → clearly stated; no statistical
  claim. Basket-level z-scores are coarse until ~2026-09-17 (90d history).

NO npm/PyPI: no collectors exist anywhere in collectors/. Descoped per
  scoping result. Would require new collectors; flag for future waves.

BASKET→THEME MAPPING: themes composed from config/theme_crosswalk.yml basket_ids.

COVERAGE CAVEAT: only 17 tickers covered (those with flagship public OSS repos);
  closed-source SaaS (CRWD, PANW) and API-only AI labs are blind spots.
"""
from __future__ import annotations

import json
import logging
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
    "framing": "developer_adoption_mindshare_context",
    "rotation_calls": False,
    "short_calls": False,
    "coverage_caveat": (
        "Only 17 tickers with flagship public OSS repos covered. "
        "Closed-source SaaS and API-only AI labs are blind spots. "
        "19-day history as of 2026-07-09 — expanding nightly."
    ),
    "history_note": (
        "Momentum signals are coarse with <90d history. "
        "Do not promote to a scored factor until ~2026-09-17."
    ),
}

# Velocity window (days)
_VELOCITY_WINDOW = 7
_HISTORY_MIN_DAYS = 7  # need at least this much to compute a delta


def _load_stars() -> pd.DataFrame | None:
    """Load data/github/repo_stars.parquet. Returns None on failure."""
    p = config.data_dir() / "github" / "repo_stars.parquet"
    if not p.exists():
        log.warning("theme_adoption: repo_stars.parquet missing")
        return None
    try:
        df = pd.read_parquet(p)
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("theme_adoption: repo_stars.parquet load failed: %s", exc)
        return None


def _load_basket_members() -> dict[str, set[str]]:
    """Load basket_id -> set[ticker] from engine.baskets. Returns {} on failure."""
    try:
        from engine import baskets as bmod  # noqa: PLC0415

        membership = bmod._membership()
        basket_dict = membership.get("baskets", {})
        result: dict[str, set[str]] = {}
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
            elif isinstance(members_raw, list):
                tickers = set(members_raw)
            else:
                tickers = set()
            result[bid] = tickers
        return result
    except Exception as exc:  # noqa: BLE001
        log.warning("theme_adoption: basket member load failed: %s", exc)
        return {}


def _load_theme_to_baskets() -> dict[str, list[str]]:
    """Load theme_id -> basket_ids from theme_crosswalk.yml. Returns {} on failure."""
    try:
        import yaml  # noqa: PLC0415

        cw_path = config.ROOT / "config" / "theme_crosswalk.yml"
        if not cw_path.exists():
            return {}
        with open(cw_path) as f:
            cw = yaml.safe_load(f)
        return {
            t["id"]: t.get("basket_ids", [])
            for t in cw.get("themes", [])
            if "id" in t
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("theme_adoption: theme_crosswalk load failed: %s", exc)
        return {}


def _star_velocity(df: pd.DataFrame, ticker: str, as_of: date) -> float | None:
    """Compute 7-day star delta for a ticker, PIT-keyed to as_of.

    Returns (stars[as_of] - stars[as_of - 7d]) / max(1, stars[as_of - 7d]).
    Returns None if insufficient history.
    """
    t_df = df[df["ticker"] == ticker].copy()
    if t_df.empty:
        return None
    try:
        t_df["_date"] = pd.to_datetime(t_df["snapshot_date"]).dt.date
    except Exception:  # noqa: BLE001
        return None

    # Find closest snapshot on or before as_of
    recent_rows = t_df[t_df["_date"] <= as_of].sort_values("_date")
    if recent_rows.empty:
        return None
    recent_row = recent_rows.iloc[-1]
    recent_stars = recent_row["stars"]
    recent_date = recent_row["_date"]

    # Find closest snapshot around (as_of - window)
    target_prior = as_of - timedelta(days=_VELOCITY_WINDOW)
    prior_rows = t_df[t_df["_date"] <= target_prior].sort_values("_date")
    if prior_rows.empty:
        # Try the oldest available snapshot if within 2x the window
        oldest = recent_rows.iloc[0]
        days_span = (recent_date - oldest["_date"]).days
        if days_span < _VELOCITY_WINDOW // 2:
            return None  # not enough span
        prior_stars = oldest["stars"]
    else:
        prior_stars = prior_rows.iloc[-1]["stars"]

    delta = recent_stars - prior_stars
    denom = max(1.0, float(prior_stars))
    return float(delta / denom)


def _cross_section_z(values: list[float]) -> list[float | None]:
    """Robust cross-sectional z-score (median/IQR) for a list of floats.

    Returns list of same length with z-scores (None preserved).
    """
    valid = [v for v in values if v is not None]
    if len(valid) < 2:
        return [None] * len(values)
    arr = np.array(valid, dtype=float)
    med = float(np.median(arr))
    q75, q25 = np.percentile(arr, [75, 25])
    iqr = q75 - q25
    scale = iqr if iqr > 1e-10 else (np.std(arr) or 1.0)
    result = []
    for v in values:
        if v is None:
            result.append(None)
        else:
            z = (v - med) / scale
            result.append(float(np.clip(z, -5.0, 5.0)))
    return result


def _pct_rank(stars_dict: dict[str, float]) -> dict[str, float]:
    """Percentile rank of star counts within the in-universe set.

    Returns {ticker: percentile_rank_0_to_100}.
    """
    if not stars_dict:
        return {}
    items = sorted(stars_dict.items(), key=lambda x: x[1])
    n = len(items)
    return {tk: round(100.0 * i / max(1, n - 1), 1) for i, (tk, _) in enumerate(items)}


def compute_theme_adoption(as_of: date | None = None) -> dict:
    """Compute per-basket GitHub adoption velocity for all themed baskets.

    Returns a result dict; always valid (exit-0). Missing data → honest nulls.
    """
    as_of = as_of or date.today()
    ts = datetime.now(timezone.utc).isoformat()

    result: dict = {
        "schema": "theme_adoption.v1",
        "as_of": as_of.isoformat(),
        "generated_at": ts,
        "authority": AUTHORITY,
        "source": "data/github/repo_stars.parquet",
        "source_note": (
            "collectors/github_repos.py — 17 tickers, curated OSS repos, "
            "keyless at 60 req/hr (or 5k/hr with GITHUB_TOKEN)."
        ),
        "npm_pypi_note": (
            "npm/PyPI adoption descoped: no collectors exist in collectors/. "
            "Future wave: add npm_downloads.py and pypi_stats.py collectors."
        ),
        "history_note": AUTHORITY["history_note"],
        "baskets": {},
        "coverage_stats": {},
        "honesty_header": (
            "Developer-adoption signals from a 17-ticker curated OSS universe. "
            "19-day history (expanding). Basket-level z-scores are coarse. "
            "Not a buy signal. Not a scored factor. Display/context only."
        ),
    }

    # ── Load data ─────────────────────────────────────────────────────────
    stars_df = _load_stars()
    basket_members = _load_basket_members()
    theme_to_baskets = _load_theme_to_baskets()

    if stars_df is None or stars_df.empty:
        result["coverage_stats"] = {
            "total_rows": 0,
            "unique_tickers": 0,
            "date_range": "no data",
            "note": "repo_stars.parquet absent — all basket velocities are null.",
        }
        # Populate null entries for all themed baskets
        all_basket_ids: set[str] = set()
        for bids in theme_to_baskets.values():
            all_basket_ids.update(bids)
        for bid in sorted(all_basket_ids):
            result["baskets"][bid] = _null_basket(bid, basket_members.get(bid, set()))
        return result

    # ── Basic stats ───────────────────────────────────────────────────────
    try:
        stars_df["_date"] = pd.to_datetime(stars_df["snapshot_date"]).dt.date
    except Exception:  # noqa: BLE001
        pass

    result["coverage_stats"] = {
        "total_rows": int(len(stars_df)),
        "unique_tickers": int(stars_df["ticker"].nunique()),
        "date_range_min": str(stars_df["snapshot_date"].min()),
        "date_range_max": str(stars_df["snapshot_date"].max()),
        "history_days": (
            (
                pd.to_datetime(stars_df["snapshot_date"]).max().date()
                - pd.to_datetime(stars_df["snapshot_date"]).min().date()
            ).days
            if len(stars_df) > 0
            else 0
        ),
    }

    # ── Compute per-ticker velocities (cross-sectional) ───────────────────
    all_tickers = sorted(stars_df["ticker"].unique())
    raw_velocities: dict[str, float | None] = {}
    raw_stars: dict[str, float] = {}

    for ticker in all_tickers:
        vel = _star_velocity(stars_df, ticker, as_of)
        raw_velocities[ticker] = vel
        # latest star count for pct_rank
        t_rows = stars_df[stars_df["ticker"] == ticker]
        if not t_rows.empty:
            raw_stars[ticker] = float(
                t_rows.sort_values("snapshot_date").iloc[-1]["stars"]
            )

    # Cross-sectional z-scores across ALL tickers in universe
    tk_list = list(raw_velocities.keys())
    vel_list = [raw_velocities[t] for t in tk_list]
    z_list = _cross_section_z(vel_list)
    z_scores: dict[str, float | None] = dict(zip(tk_list, z_list))

    # Pct-rank of star counts
    pct_ranks = _pct_rank(raw_stars)

    # ── Per-basket rollup ─────────────────────────────────────────────────
    # Process all themed baskets
    all_basket_ids: set[str] = set()
    for bids in theme_to_baskets.values():
        all_basket_ids.update(bids)

    for bid in sorted(all_basket_ids):
        members = basket_members.get(bid, set())
        # Tickers in this basket that have GitHub data
        covered = [t for t in members if t in raw_velocities]

        if not covered:
            result["baskets"][bid] = _null_basket(bid, members)
            continue

        # Basket-level z: median of ticker z-scores (robust to outliers)
        ticker_zs = [z_scores[t] for t in covered if z_scores.get(t) is not None]
        basket_vel_z = float(np.median(ticker_zs)) if ticker_zs else None

        # Coverage
        n_covered = len(covered)
        n_total = len(members) if members else 0

        result["baskets"][bid] = {
            "basket_id": bid,
            "star_velocity_7d_z": round(basket_vel_z, 3) if basket_vel_z is not None else None,
            "n_covered": n_covered,
            "n_basket_total": n_total,
            "covered_tickers": sorted(covered),
            "ticker_detail": [
                {
                    "ticker": t,
                    "star_velocity_7d_raw": (
                        round(raw_velocities[t], 4) if raw_velocities.get(t) is not None else None
                    ),
                    "star_velocity_7d_z": (
                        round(z_scores[t], 3) if z_scores.get(t) is not None else None
                    ),
                    "star_pct_rank": pct_ranks.get(t),
                    "latest_stars": int(raw_stars[t]) if t in raw_stars else None,
                }
                for t in sorted(covered)
            ],
            "coverage_note": (
                f"{n_covered}/{n_total} basket tickers have GitHub data; "
                f"velocity window: {_VELOCITY_WINDOW}d. "
                f"History: ~{result['coverage_stats'].get('history_days', 0)}d (expanding)."
            ),
            "coverage_note_zh": (
                f"篮子成员{n_total}个，其中{n_covered}个有GitHub数据；"
                f"速度窗口：{_VELOCITY_WINDOW}天；"
                f"历史长度：约{result['coverage_stats'].get('history_days', 0)}天（持续扩展）。"
            ),
        }

    return result


def _null_basket(basket_id: str, members: set[str]) -> dict:
    """Return an honest-null basket entry for a basket with no GitHub coverage."""
    return {
        "basket_id": basket_id,
        "star_velocity_7d_z": None,
        "n_covered": 0,
        "n_basket_total": len(members),
        "covered_tickers": [],
        "ticker_detail": [],
        "coverage_note": (
            f"No GitHub data for any of {len(members)} basket tickers. "
            "Only 17 tickers have curated OSS repos (see data/github/repo_ticker.json). "
            "Non-tech themes have zero coverage by design."
        ),
        "coverage_note_zh": (
            f"篮子{len(members)}个成员均无GitHub数据。"
            "仅17个成员具有精选开源仓库（见data/github/repo_ticker.json），"
            "非科技主题天然覆盖率为零。"
        ),
    }


def write_site_projection(result: dict, out_path: Path | None = None) -> Path:
    """Write compact site/basketdata/github_adoption.json from compute result.

    This is the git-tracked artifact (compact; full ticker_detail excluded for size).
    """
    if out_path is None:
        out_path = config.ROOT / "site" / "basketdata" / "github_adoption.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Compact: drop full ticker_detail from site artifact (accessible from runner-local)
    compact_baskets = {}
    for bid, bdata in result.get("baskets", {}).items():
        compact_baskets[bid] = {
            "basket_id": bid,
            "star_velocity_7d_z": bdata.get("star_velocity_7d_z"),
            "n_covered": bdata.get("n_covered"),
            "n_basket_total": bdata.get("n_basket_total"),
            "covered_tickers": bdata.get("covered_tickers", []),
            "coverage_note": bdata.get("coverage_note"),
            "coverage_note_zh": bdata.get("coverage_note_zh"),
        }

    compact: dict = {
        "schema": result.get("schema"),
        "as_of": result.get("as_of"),
        "generated_at": result.get("generated_at"),
        "authority": result.get("authority"),
        "coverage_stats": result.get("coverage_stats"),
        "npm_pypi_note": result.get("npm_pypi_note"),
        "history_note": result.get("history_note"),
        "honesty_header": result.get("honesty_header"),
        "baskets": compact_baskets,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(compact, f, ensure_ascii=False, indent=2)
    log.info("theme_adoption: wrote site projection -> %s", out_path)
    return out_path


def main() -> int:
    import argparse  # noqa: PLC0415

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(
        description="theme_adoption — GitHub adoption velocity (off render path)"
    )
    p.add_argument("--as-of", default=None, help="ISO date for PIT cutoff")
    p.add_argument("--no-write-site", action="store_true")
    args = p.parse_args()

    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    result = compute_theme_adoption(as_of=as_of)

    stats = result.get("coverage_stats", {})
    baskets = result.get("baskets", {})
    covered = sum(1 for b in baskets.values() if b.get("n_covered", 0) > 0)
    print(f"as_of: {result['as_of']}")
    print(f"github rows: {stats.get('total_rows', 0)}")
    print(f"baskets with coverage: {covered}/{len(baskets)}")

    if not args.no_write_site:
        out = write_site_projection(result)
        print(f"site projection: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
