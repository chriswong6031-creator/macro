"""engine.marketing.radar_internal — Radar (intelligence dept) W1.

Sweeps the repo's OWN nightly artifacts for postable-but-unposted assets and
tiers cashtags by deterministic attention proxies.  Observes and scores only;
never posts.

Public API (all fail-soft — no public function raises):
    _feed_prophet(root) -> list[dict]
    _feed_confluence(root) -> list[dict]
    _feed_movers(root) -> list[dict]
    _feed_earnings(root, as_of_date=None) -> list[dict]
    _feed_stage(root) -> list[dict]
    _posted_tickers(root, n_plans=7) -> set[str]
    update_plan_history(root) -> dict
    scan_signal_surplus(root, as_of_date=None) -> list[dict]
    emit_opportunities(surplus, as_of_date) -> list[dict]
    sync_opportunities(root, opps) -> dict
    build_cashtag_tiers(root) -> dict | None
    load_cashtag_tiers(root) -> dict | None
    load_competitor_cadence(root) -> dict | None
    build_radar(root) -> dict
"""
from __future__ import annotations

import json
import logging
import math
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def _finite(v: Any) -> float | None:
    """Return float(v) if v is finite, else None.  Guards JSON against NaN/Inf."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


# ─────────────────────────────────────────────────────────────────────────────
# Internal write helper (mirrors marketing_governor._write_json_atomic)
# ─────────────────────────────────────────────────────────────────────────────

def _write_json_atomic(path: Path, obj: dict) -> None:
    """Atomic write via temp file in the same directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=path.parent, prefix=".tmp_", suffix=".json"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except Exception:  # noqa: BLE001
            pass
        raise


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_str() -> str:
    return date.today().isoformat()


def _staleness_days(as_of_str: str | None) -> int:
    """Days between as_of_str (YYYY-MM-DD) and today(). 0 on parse error."""
    try:
        if not as_of_str:
            return 0
        d = date.fromisoformat(str(as_of_str)[:10])
        return max(0, (date.today() - d).days)
    except Exception:  # noqa: BLE001
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# Feed readers
# ─────────────────────────────────────────────────────────────────────────────

def _feed_prophet(root: Path) -> list[dict]:
    """Read site/prophet/index.json → active plan asset dicts."""
    try:
        path = root / "site" / "prophet" / "index.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        plans = data.get("plans") or []
        results: list[dict] = []
        for plan in plans:
            if not isinstance(plan, dict):
                continue
            phase = plan.get("phase", "")
            if phase in {"closed", "invalidated", "stopped"}:
                continue
            ticker = plan.get("asset", "")
            if not ticker:
                continue
            as_of = (plan.get("_signal_date") or data.get("asof") or _today_str())[:10]
            pid = plan.get("id", "")
            conviction = plan.get("_conviction_score", "")
            why = f"active Prophet plan {pid}, phase {phase}, conviction {conviction}"
            results.append({"ticker": ticker, "feed": "prophet", "why": why, "as_of": as_of})
        return results
    except Exception:  # noqa: BLE001
        return []


def _feed_confluence(root: Path) -> list[dict]:
    """Read site/factordata/tech_confluence.json → firing combos."""
    try:
        from engine.marketing.confluence_source import load_confluence
        conf = load_confluence(root)
        if not isinstance(conf, dict):
            return []
        generated_utc = conf.get("generated_utc", "")
        as_of = generated_utc[:10] if generated_utc else _today_str()
        combos_long = (conf.get("combos") or {}).get("long") or []
        results: list[dict] = []
        for combo in combos_long:
            if not isinstance(combo, dict):
                continue
            active_now = combo.get("active_now") or []
            if not active_now:
                continue
            h21 = combo.get("h21") or {}
            wr_mc_test = h21.get("wr_mc_test")
            if wr_mc_test is None:
                continue
            name_en = combo.get("name_en", combo.get("id", ""))
            try:
                wr_str = f"{float(wr_mc_test):.0%}"
            except (TypeError, ValueError):
                wr_str = str(wr_mc_test)
            why = f"confluence combo {name_en} firing, test WR {wr_str}"
            for ticker in list(active_now)[:3]:
                if not ticker:
                    continue
                results.append({"ticker": str(ticker), "feed": "confluence", "why": why, "as_of": as_of})
        return results
    except Exception:  # noqa: BLE001
        return []


def _feed_movers(root: Path) -> list[dict]:
    """Read sp500_heatmap → top movers via movers_source."""
    try:
        from engine.marketing.movers_source import load_movers, top_movers
        data = load_movers(root)
        if data is None:
            return []
        movers = top_movers(data, tf="1D", n=8, min_abs=3.0)
        as_of = (data.get("asof") or _today_str())[:10]
        results: list[dict] = []
        for m in list(movers.get("gainers", [])) + list(movers.get("losers", [])):
            ticker = m.get("ticker", "")
            pct = m.get("pct", 0.0)
            sector = m.get("sector", "")
            why = f"S&P mover {pct:+.1f}% 1D ({sector})"
            results.append({"ticker": ticker, "feed": "movers", "why": why, "as_of": as_of})
        return results
    except Exception:  # noqa: BLE001
        return []


_EARNINGS_TIME_MAP: dict[str, str] = {
    "time-pre-market": "pre-market",
    "time-after-hours": "after hours",
}


def _plainify_earnings_time(next_time: str) -> str:
    """Map raw earnings timing slug to display-safe string.

    "time-pre-market"   → "pre-market"
    "time-after-hours"  → "after hours"
    "time-not-supplied" → "" (omit from why)
    anything else       → "" (safe default; omit)
    """
    return _EARNINGS_TIME_MAP.get(next_time, "")


def _feed_earnings(root: Path, as_of_date: str | None = None) -> list[dict]:
    """Read data/earnings/earnings.parquet → tickers with earnings in 3 calendar days."""
    try:
        import pandas as pd
        path = root / "data" / "earnings" / "earnings.parquet"
        if not path.exists():
            return []
        df = pd.read_parquet(path)
        if df.empty:
            return []
        # Determine as_of_date
        if as_of_date:
            ref_date = date.fromisoformat(str(as_of_date)[:10])
        else:
            # max as_of[:10] in the file
            try:
                col_asof = df["as_of"].dropna()
                ref_str = col_asof.str[:10].max()
                ref_date = date.fromisoformat(ref_str)
            except Exception:  # noqa: BLE001
                ref_date = date.today()
        aod_str = ref_date.isoformat()
        results: list[dict] = []
        for ticker, row in df.iterrows():
            nd = row.get("next_date") or ""
            if not nd:
                continue
            try:
                nd_date = date.fromisoformat(str(nd)[:10])
            except ValueError:
                continue
            delta = (nd_date - ref_date).days
            if 0 <= delta <= 3:
                next_time = str(row.get("next_time", "") or "")
                time_display = _plainify_earnings_time(next_time)
                if time_display:
                    why = f"earnings {nd_date.isoformat()} {time_display}"
                else:
                    why = f"earnings {nd_date.isoformat()}"
                results.append({
                    "ticker": str(ticker),
                    "feed": "earnings",
                    "why": why,
                    "as_of": aod_str,
                })
        # Cap 20, sorted by ticker for determinism
        results.sort(key=lambda x: x["ticker"])
        return results[:20]
    except Exception:  # noqa: BLE001
        return []


def _feed_stage(root: Path) -> list[dict]:
    """Read equitydesk_overview.parquet → USA stage 2 names."""
    try:
        import pandas as pd
        path = root / "data" / "stage_analysis" / "backfill" / "equitydesk_overview.parquet"
        if not path.exists():
            return []
        cols = ["ticker", "region", "stage_flag", "stage_detailed", "sata_score", "weeks_in_stage", "as_of_date"]
        df = pd.read_parquet(path, columns=cols)
        if df.empty:
            return []
        df = df[(df["region"] == "USA") & (df["stage_flag"] == 2)].copy()
        df = df.sort_values(["sata_score", "ticker"], ascending=[False, True]).head(15)
        results: list[dict] = []
        for _, row in df.iterrows():
            ticker = str(row.get("ticker", ""))
            as_of = str(row.get("as_of_date", _today_str()))[:10]
            stage_detailed = str(row.get("stage_detailed", ""))
            sata_score = row.get("sata_score", "")
            weeks = row.get("weeks_in_stage", "")
            why = f"stage {stage_detailed}, SATA {sata_score}, {weeks}w in stage"
            results.append({"ticker": ticker, "feed": "stage", "why": why, "as_of": as_of})
        return results
    except Exception:  # noqa: BLE001
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Posted-set + plan history
# ─────────────────────────────────────────────────────────────────────────────

def _posted_tickers(root: Path, n_plans: int = 7) -> set[str]:
    """Union of posted tickers from content_plan, plan_history, and publications."""
    tickers: set[str] = set()

    # (a) current content_plan.json
    try:
        cp_path = root / "data" / "marketing" / "content_plan.json"
        if cp_path.exists():
            cp = json.loads(cp_path.read_text(encoding="utf-8"))
            for account in cp.get("accounts") or []:
                for item in account.get("queue") or []:
                    t = item.get("ticker", "")
                    if t:
                        tickers.add(str(t).upper())
                    # Also parse cashtags list
                    for ct in item.get("cashtags") or []:
                        tickers.add(str(ct).lstrip("$").upper())
    except Exception:  # noqa: BLE001
        pass

    # (b) plan history
    try:
        hist_path = root / "data" / "marketing" / "radar_plan_history.json"
        if hist_path.exists():
            hist = json.loads(hist_path.read_text(encoding="utf-8"))
            for plan_entry in (hist.get("plans") or []):
                for t in plan_entry.get("tickers") or []:
                    tickers.add(str(t).upper())
    except Exception:  # noqa: BLE001
        pass

    # (c) publications.jsonl — strip "$", uppercase asset_id
    try:
        pub_path = root / "data" / "marketing" / "publications.jsonl"
        if pub_path.exists():
            for line in pub_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    asset_id = str(row.get("asset_id") or "")
                    if asset_id:
                        tickers.add(asset_id.lstrip("$").upper())
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass

    return tickers


def update_plan_history(root: Path) -> dict:
    """Read content_plan.json, extract posted tickers, upsert into plan history.

    Maintains data/marketing/radar_plan_history.json with newest 7 as_ofs.
    Returns the history dict.
    """
    hist_path = root / "data" / "marketing" / "radar_plan_history.json"
    hist: dict = {"schema": "marketing.radar_plan_history/v1", "plans": []}

    # Load existing history
    try:
        if hist_path.exists():
            loaded = json.loads(hist_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                hist = loaded
    except Exception:  # noqa: BLE001
        pass

    # Extract current plan's as_of and tickers
    try:
        cp_path = root / "data" / "marketing" / "content_plan.json"
        if cp_path.exists():
            cp = json.loads(cp_path.read_text(encoding="utf-8"))
            plan_asof = str(cp.get("as_of", _today_str()))[:10]
            posted: list[str] = []
            for account in cp.get("accounts") or []:
                for item in account.get("queue") or []:
                    t = item.get("ticker", "")
                    if t:
                        posted.append(str(t).upper())
            posted = sorted(set(posted))
            # Upsert by as_of
            plans = [p for p in (hist.get("plans") or []) if p.get("as_of") != plan_asof]
            plans.append({"as_of": plan_asof, "tickers": posted})
            # Keep newest 7 by as_of descending
            plans.sort(key=lambda x: x.get("as_of", ""), reverse=True)
            hist["plans"] = plans[:7]
    except Exception:  # noqa: BLE001
        pass

    # Atomic write
    try:
        _write_json_atomic(hist_path, hist)
    except Exception:  # noqa: BLE001
        pass

    return hist


# ─────────────────────────────────────────────────────────────────────────────
# Surplus scan
# ─────────────────────────────────────────────────────────────────────────────

_SURPLUS_FEED_ORDER = ["prophet", "confluence", "earnings", "movers", "stage"]


def scan_signal_surplus(
    root: Path,
    as_of_date: str | None = None,
    feed_results: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """Run all 5 feeds, dedupe, exclude posted tickers, select round-robin across feeds.

    Selection algorithm (deterministic, no randomness):
    1. Run all 5 feeds; exclude posted tickers and dedupe by ticker (first feed wins).
    2. Per feed, keep items ordered by (staleness_days asc, ticker asc).
    3. Round-robin across feeds in priority order [prophet, confluence, earnings, movers, stage]:
       take one item from each feed that still has items, repeat until the 40-cap or exhaustion.
    4. Sort the final selected list by (staleness_days asc, ticker asc) for display.

    Args:
        feed_results: Pre-run feed results keyed by feed name.  When provided the
            feeds are NOT re-run, which avoids duplicate I/O inside build_radar.
            When None (default) the feeds are run as usual so existing callers and
            tests are unaffected.
    """
    posted = _posted_tickers(root)

    # Collect raw feed items in priority order — reuse caller-supplied results if given.
    if feed_results is not None:
        raw_feeds: dict[str, list[dict]] = {name: list(feed_results.get(name, [])) for name in _SURPLUS_FEED_ORDER}
    else:
        raw_feeds = {
            "prophet": _feed_prophet(root),
            "confluence": _feed_confluence(root),
            "earnings": _feed_earnings(root, as_of_date),
            "movers": _feed_movers(root),
            "stage": _feed_stage(root),
        }

    # Dedupe by ticker across feeds (prophet wins over movers for same ticker, etc.)
    seen_tickers: set[str] = set()
    # Build per-feed candidate lists, excluding posted + already-seen tickers.
    # Feeds are processed in priority order so first-feed-wins dedupe is correct.
    per_feed: dict[str, list[dict]] = {name: [] for name in _SURPLUS_FEED_ORDER}
    for feed_name in _SURPLUS_FEED_ORDER:
        for item in raw_feeds.get(feed_name, []):
            ticker = str(item.get("ticker", "")).upper()
            if not ticker:
                continue
            if ticker in posted:
                continue
            if ticker in seen_tickers:
                continue
            seen_tickers.add(ticker)
            stale = _staleness_days(item.get("as_of"))
            per_feed[feed_name].append({
                "ticker": ticker,
                "feed": item.get("feed", feed_name),
                "why": item.get("why", ""),
                "as_of": item.get("as_of", ""),
                "staleness_days": stale,
            })

    # Within each feed: sort by (staleness_days asc, ticker asc) and use as a queue
    feed_queues: dict[str, list[dict]] = {}
    for feed_name in _SURPLUS_FEED_ORDER:
        items = sorted(per_feed[feed_name], key=lambda x: (x["staleness_days"], x["ticker"]))
        feed_queues[feed_name] = items

    # Round-robin selection (pointer per feed)
    feed_pointers: dict[str, int] = {name: 0 for name in _SURPLUS_FEED_ORDER}
    selected: list[dict] = []
    cap = 40
    exhausted = False
    while len(selected) < cap and not exhausted:
        exhausted = True
        for feed_name in _SURPLUS_FEED_ORDER:
            if len(selected) >= cap:
                break
            ptr = feed_pointers[feed_name]
            queue = feed_queues[feed_name]
            if ptr < len(queue):
                selected.append(queue[ptr])
                feed_pointers[feed_name] = ptr + 1
                exhausted = False

    # Final sort for display: (staleness_days asc, ticker asc)
    selected.sort(key=lambda x: (x["staleness_days"], x["ticker"]))
    return selected


# ─────────────────────────────────────────────────────────────────────────────
# Opportunity emission
# ─────────────────────────────────────────────────────────────────────────────

_FEED_SOURCE_TYPE: dict[str, str] = {
    "earnings": "earnings",
    "movers": "market_event",
    "prophet": "weekly_signal",
    "confluence": "weekly_signal",
    "stage": "weekly_signal",
}

_FEED_EXPECTED_VALUE: dict[str, float] = {
    "prophet": 0.6,
    "confluence": 0.55,
    "earnings": 0.5,
    "movers": 0.45,
    "stage": 0.4,
}

_FEED_ARTIFACT_PATH: dict[str, str] = {
    "prophet": "site/prophet/index.json",
    "confluence": "site/factordata/tech_confluence.json",
    "earnings": "data/earnings/earnings.parquet",
    "movers": "site/marketdata/sp500_heatmap.json",
    "stage": "data/stage_analysis/backfill/equitydesk_overview.parquet",
}


def emit_opportunities(surplus: list[dict], as_of_date: str) -> list[dict]:
    """Convert surplus items to Opportunity dicts (consumer contract for opportunity_bus)."""
    try:
        from engine.marketing.opportunity_bus import half_life_class as _hlc
    except Exception:  # noqa: BLE001
        def _hlc(st: str) -> str:  # type: ignore[misc]
            return "weekly_signal"

    # Get all Opportunity dataclass field names for completeness
    try:
        import dataclasses
        from engine.marketing.opportunity_bus import Opportunity
        _opp_fields = {f.name for f in dataclasses.fields(Opportunity)}
    except Exception:  # noqa: BLE001
        _opp_fields = set()

    results: list[dict] = []
    for item in surplus[:40]:
        feed = item.get("feed", "")
        ticker = item.get("ticker", "")
        item_asof = item.get("as_of", as_of_date)
        source_type = _FEED_SOURCE_TYPE.get(feed, "weekly_signal")
        opp_id = f"radar-{feed}-{ticker}-{item_asof}"
        detected_at = f"{item_asof}T00:00:00Z"
        ev = _FEED_EXPECTED_VALUE.get(feed, 0.4)
        artifact_path = _FEED_ARTIFACT_PATH.get(feed, "")
        why = item.get("why", "")
        problem_or_desire = f"${ticker}: {why}"
        hlc = _hlc(source_type)

        opp: dict[str, Any] = {
            "opportunity_id": opp_id,
            "detected_at": detected_at,
            "source_type": source_type,
            "source_refs": [artifact_path] if artifact_path else [],
            "audience_hypothesis": "active equity traders following this ticker",
            "problem_or_desire": problem_or_desire,
            "attention_half_life": hlc,
            "expected_value": ev,
            "originality": 1.0,
            "evidence_available": True,
            "possible_products": ["content"],
            "possible_channels": ["x"],
            "consequence_class": "market_education",
            "owner_department": "intelligence",
            "status": "open",
            "mode": "live",
        }
        results.append(opp)

    return results


# ─────────────────────────────────────────────────────────────────────────────
# Sync opportunities
# ─────────────────────────────────────────────────────────────────────────────

# Rows already below this score floor are treated as expired by sync_opportunities.
# build_radar uses the same constant to pre-filter DOA opportunities before they
# enter the ledger — fast-decay movers (breaking_event 2h half-life) belong to
# the D01 fastlane, not the nightly queue.
_SCORE_FLOOR = 0.05


def sync_opportunities(root: Path, opps: list[dict]) -> dict:
    """Read opportunities.jsonl, sync radar rows, atomic rewrite.

    Returns {"added": n, "expired": n, "total": n, "open": n}.
    Idempotent: second run with same inputs adds 0.
    """
    try:
        from engine.marketing.opportunity_bus import score_dict
    except Exception:  # noqa: BLE001
        def score_dict(row: dict, now: Any = None) -> float:  # type: ignore[misc]
            return 1.0

    opp_path = root / "data" / "marketing" / "opportunities.jsonl"

    # Read existing rows
    existing_rows: list[dict] = []
    try:
        if opp_path.exists():
            for raw_line in opp_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    existing_rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass

    # Partition existing rows
    non_radar: list[dict] = []
    old_radar: list[dict] = []
    for row in existing_rows:
        oid = str(row.get("opportunity_id", ""))
        if oid.startswith("radar-"):
            old_radar.append(row)
        else:
            non_radar.append(row)

    # Expire old radar rows with score < _SCORE_FLOOR.
    # Only rows TRANSITIONING open→expired this run increment the counter;
    # rows already status=="expired" pass through unchanged.
    expired_count = 0
    kept_radar: list[dict] = []
    for row in old_radar:
        if row.get("status") == "expired":
            kept_radar.append(row)
            continue
        sc = score_dict(row)
        if sc < _SCORE_FLOOR:
            row = dict(row, status="expired")
            expired_count += 1
        kept_radar.append(row)

    # Build set of existing radar ids
    existing_ids = {str(r.get("opportunity_id", "")) for r in kept_radar}

    # Add new opps not already present
    added_count = 0
    new_radar: list[dict] = list(kept_radar)
    for opp in opps:
        oid = str(opp.get("opportunity_id", ""))
        if oid not in existing_ids:
            new_radar.append(opp)
            existing_ids.add(oid)
            added_count += 1

    # Prune expired radar rows older than 30 days to bound ledger growth.
    # Fail-safe: rows whose detected_at can't be parsed are kept.
    _PRUNE_DAYS = 30
    pruned_radar: list[dict] = []
    for row in new_radar:
        if row.get("status") != "expired":
            pruned_radar.append(row)
            continue
        detected_raw = row.get("detected_at", "")
        try:
            dt = datetime.fromisoformat(str(detected_raw).replace("Z", "+00:00"))
            age_days = (datetime.now(tz=timezone.utc) - dt).days
            if age_days > _PRUNE_DAYS:
                continue  # drop — too old
        except Exception:  # noqa: BLE001
            pass  # keep — fail-safe on unparseable date
        pruned_radar.append(row)

    all_rows = non_radar + pruned_radar

    # Atomic rewrite
    try:
        opp_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=opp_path.parent, prefix=".tmp_", suffix=".jsonl"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                for row in all_rows:
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            os.replace(tmp_path, opp_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except Exception:  # noqa: BLE001
                pass
            raise
    except Exception:  # noqa: BLE001
        pass

    open_count = sum(1 for r in all_rows if r.get("status") == "open")
    return {
        "added": added_count,
        "expired": expired_count,
        "total": len(all_rows),
        "open": open_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Cashtag tiers
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_T1_ALWAYS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    "AVGO", "AMD", "NFLX", "PLTR", "COIN", "HOOD", "MSTR",
    "SMCI", "GME", "AMC",
]


def _load_t1_always(root: Path) -> list[str]:
    """Load t1_always list from config/marketing.yml; fall back to built-in default."""
    try:
        from engine.marketing.state import _load_cfg
        cfg = _load_cfg(root)
        radar_cfg = cfg.get("radar") or {}
        lst = radar_cfg.get("t1_always")
        if isinstance(lst, list) and lst:
            return [str(t).upper() for t in lst]
    except Exception:  # noqa: BLE001
        pass
    return list(_DEFAULT_T1_ALWAYS)


def build_cashtag_tiers(root: Path) -> dict | None:
    """Build cashtag attention tiers from nightly artifacts.

    Returns a dict with schema marketing.cashtag_tiers/v1, or None only if
    the universe itself cannot be built.
    """
    try:
        import pandas as pd
    except Exception:  # noqa: BLE001
        return None

    t1_always = _load_t1_always(root)
    t1_always_set = set(t1_always)

    # Build universe
    universe: set[str] = set()

    # SP500 from membership.parquet
    try:
        mem_path = root / "data" / "universe" / "membership.parquet"
        if mem_path.exists():
            mem = pd.read_parquet(mem_path)
            sp500_tickers = mem[(mem["group"] == "sp500") & (mem["active"])]["ticker"].tolist()
            universe.update(str(t).upper() for t in sp500_tickers)
    except Exception:  # noqa: BLE001
        pass

    # NDX from finviz_screener/idx_ndx.json (list or dict with rows key)
    try:
        ndx_path = root / "data" / "finviz_screener" / "idx_ndx.json"
        if ndx_path.exists():
            ndx_data = json.loads(ndx_path.read_text(encoding="utf-8"))
            if isinstance(ndx_data, list):
                rows = ndx_data
            elif isinstance(ndx_data, dict):
                rows = ndx_data.get("rows") or []
            else:
                rows = []
            for row in rows:
                t = row.get("ticker", "") if isinstance(row, dict) else ""
                if t:
                    universe.add(str(t).upper())
    except Exception:  # noqa: BLE001
        pass

    # Always-list tickers outside the index universe must be included as T1.
    # Add them now so they participate in proxy lookups and tier assignment.
    universe.update(t1_always_set)

    if not universe:
        return None

    # Heatmap proxies
    heatmap_asof: str = _today_str()
    heatmap_by_ticker: dict[str, dict] = {}
    try:
        hm_path = root / "site" / "marketdata" / "sp500_heatmap.json"
        if hm_path.exists():
            hm_data = json.loads(hm_path.read_text(encoding="utf-8"))
            heatmap_asof = str(hm_data.get("asof") or _today_str())[:10]
            for tile in hm_data.get("tiles") or []:
                if not isinstance(tile, dict):
                    continue
                t = str(tile.get("t", "")).upper()
                if t:
                    perf = tile.get("perf") or {}
                    heatmap_by_ticker[t] = {
                        "size": tile.get("size"),
                        "pct_1d": perf.get("1D"),
                        "pct_1w": perf.get("1W"),
                    }
    except Exception:  # noqa: BLE001
        pass

    # Top-20 sizes for T1 megacap rule
    all_sizes = [v["size"] for v in heatmap_by_ticker.values() if v.get("size") is not None]
    all_sizes.sort(reverse=True)
    top20_threshold = all_sizes[19] if len(all_sizes) >= 20 else (all_sizes[-1] if all_sizes else 0.0)

    # Earnings proximity
    earnings_by_ticker: dict[str, int] = {}  # ticker -> days until next_date (abs)
    try:
        import pandas as pd
        ep_path = root / "data" / "earnings" / "earnings.parquet"
        if ep_path.exists():
            edf = pd.read_parquet(ep_path)
            try:
                ref_date = date.fromisoformat(heatmap_asof)
            except Exception:  # noqa: BLE001
                ref_date = date.today()
            for ticker, row in edf.iterrows():
                nd = row.get("next_date") or ""
                if not nd:
                    continue
                try:
                    nd_date = date.fromisoformat(str(nd)[:10])
                    days_away = abs((nd_date - ref_date).days)
                    earnings_by_ticker[str(ticker).upper()] = days_away
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001
        pass

    # Dollar volume per-ticker
    dollar_vol_by_ticker: dict[str, float] = {}
    stocks_dir = root / "data" / "stocks"
    try:
        import pandas as pd
        for ticker in universe:
            ticker_path = stocks_dir / f"{ticker}.parquet"
            try:
                if not ticker_path.exists():
                    continue
                sdf = pd.read_parquet(ticker_path, columns=["close", "volume"])
                if sdf.empty:
                    continue
                last = sdf.iloc[-1]
                c = last["close"]
                v = last["volume"]
                dv = _finite(c) if c is not None else None
                dv = _finite(float(dv) * float(v) / 1e6) if dv is not None and v is not None else None
                if dv is not None:
                    dollar_vol_by_ticker[ticker] = dv
            except Exception:  # noqa: BLE001
                pass
    except Exception:  # noqa: BLE001
        pass

    # Assign tiers
    t1_list: list[str] = []
    t2_list: list[str] = []
    t3_list: list[str] = []
    tickers_detail: dict[str, dict] = {}

    for ticker in sorted(universe):
        hm = heatmap_by_ticker.get(ticker, {})
        size = hm.get("size")
        pct_1d = hm.get("pct_1d")
        pct_1w = hm.get("pct_1w")
        earnings_in_days = earnings_by_ticker.get(ticker)
        dollar_vol = dollar_vol_by_ticker.get(ticker)

        reasons: list[str] = []
        tier = "T3"

        # T1 rules
        if ticker in t1_always_set:
            reasons.append("always_list")
            tier = "T1"
        elif size is not None and float(size) >= float(top20_threshold):
            reasons.append("megacap_weight")
            tier = "T1"

        # T2 rules (only if not already T1)
        if tier != "T1":
            if pct_1d is not None and abs(float(pct_1d)) >= 3.0:
                reasons.append("move_1d")
                tier = "T2"
            if pct_1w is not None and abs(float(pct_1w)) >= 5.0:
                reasons.append("move_1w")
                tier = "T2"
            if earnings_in_days is not None and earnings_in_days <= 5:
                reasons.append("earnings_window")
                tier = "T2"
            if dollar_vol is not None and float(dollar_vol) >= 1000.0:
                reasons.append("dollar_volume")
                tier = "T2"

        tickers_detail[ticker] = {
            "tier": tier,
            "reasons": reasons,
            "proxies": {
                "mcap_weight": _finite(size),
                "pct_1d": _finite(pct_1d),
                "pct_1w": _finite(pct_1w),
                "earnings_in_days": int(earnings_in_days) if earnings_in_days is not None else None,
                "dollar_vol_musd": _finite(dollar_vol),
            },
        }

        if tier == "T1":
            t1_list.append(ticker)
        elif tier == "T2":
            t2_list.append(ticker)
        else:
            t3_list.append(ticker)

    return {
        "schema": "marketing.cashtag_tiers/v1",
        "schema_version": 1,
        "produced_by": "engine/marketing/radar_internal.py",
        "produced_at": _utc_now_iso(),
        "tier": "display",
        "as_of": heatmap_asof,
        "universe_n": len(universe),
        "tiers": {
            "T1": sorted(t1_list),
            "T2": sorted(t2_list),
            "T3": sorted(t3_list),
        },
        "tickers": tickers_detail,
    }


def load_cashtag_tiers(root: Path) -> dict | None:
    """Read data/marketing/cashtag_tiers.json if present."""
    try:
        path = root / "data" / "marketing" / "cashtag_tiers.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Competitor cadence
# ─────────────────────────────────────────────────────────────────────────────

def load_competitor_cadence(root: Path) -> dict | None:
    """Load config/marketing_competitor_cadence.yml fail-soft."""
    try:
        import yaml  # type: ignore[import-untyped]
        path = root / "config" / "marketing_competitor_cadence.yml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        schema = str(data.get("schema", ""))
        if not schema.startswith("marketing.competitor_cadence"):
            return None
        return data
    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Report + orchestrator
# ─────────────────────────────────────────────────────────────────────────────

def build_radar(root: Path | str | None = None) -> dict:
    """Main entry point: sweep artifacts, tier cashtags, write all outputs.

    Steps (each fail-soft):
    1. update_plan_history
    2. scan_signal_surplus (run all 5 feeds, record per-feed stats)
    3. emit_opportunities
    4. filter DOA opportunities (score < _SCORE_FLOOR skipped from ledger)
    5. sync_opportunities (ledger receives only live_opps; doa_skipped in queue summary)
    6. build_cashtag_tiers → write data/marketing/cashtag_tiers.json
    7. load_competitor_cadence
    8. assemble + write data/marketing/radar_report.json

    Returns the report dict (with "error" key instead of raising on catastrophic failure).
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent.parent
    r = Path(root)

    try:
        # 1. Update plan history
        try:
            update_plan_history(r)
        except Exception as exc:  # noqa: BLE001
            log.warning("radar: update_plan_history failed: %s", exc)

        today = _today_str()

        # 2. Run individual feeds (track per-feed stats)
        feed_defs = [
            ("prophet", _feed_prophet),
            ("confluence", _feed_confluence),
            ("earnings", _feed_earnings),
            ("movers", _feed_movers),
            ("stage", _feed_stage),
        ]
        feed_results: dict[str, list[dict]] = {}
        feeds_meta: list[dict] = []
        for fname, ffunc in feed_defs:
            try:
                if fname == "earnings":
                    items = ffunc(r, None)  # type: ignore[call-arg]
                else:
                    items = ffunc(r)
                feed_results[fname] = items
                # as_of from first item
                as_of_val = items[0].get("as_of") if items else None
                feeds_meta.append({"name": fname, "ok": True, "n_assets": len(items), "as_of": as_of_val})
            except Exception as exc:  # noqa: BLE001
                log.warning("radar: feed %s failed: %s", fname, exc)
                feed_results[fname] = []
                feeds_meta.append({"name": fname, "ok": False, "n_assets": 0, "as_of": None})

        # 3. Scan surplus — pass already-run feed_results so each feed runs exactly once.
        try:
            surplus = scan_signal_surplus(r, feed_results=feed_results)
        except Exception as exc:  # noqa: BLE001
            log.warning("radar: scan_signal_surplus failed: %s", exc)
            surplus = []

        # 4. Emit opportunities
        try:
            opps = emit_opportunities(surplus, today)
        except Exception as exc:  # noqa: BLE001
            log.warning("radar: emit_opportunities failed: %s", exc)
            opps = []

        # 5. Filter out dead-on-arrival opportunities before ledger sync.
        # Rows already below _SCORE_FLOOR (fast-decay movers whose detected_at comes
        # from the heatmap asof, typically 1-2 days back) never enter the ledger.
        # The surplus REPORT above already captured all items including movers.
        try:
            from engine.marketing.opportunity_bus import score_dict as _score_dict
            live_opps = [o for o in opps if _score_dict(o) >= _SCORE_FLOOR]
            doa_skipped = len(opps) - len(live_opps)
        except Exception:  # noqa: BLE001
            live_opps = opps
            doa_skipped = 0

        # 6. Sync opportunities
        queue_summary: dict = {}
        try:
            queue_summary = sync_opportunities(r, live_opps)
            queue_summary["doa_skipped"] = doa_skipped
        except Exception as exc:  # noqa: BLE001
            log.warning("radar: sync_opportunities failed: %s", exc)

        # 7. Build cashtag tiers
        tiers_summary: dict | None = None
        try:
            tiers = build_cashtag_tiers(r)
            if tiers is not None:
                tiers_path = r / "data" / "marketing" / "cashtag_tiers.json"
                _write_json_atomic(tiers_path, tiers)
                t = tiers.get("tiers") or {}
                tiers_summary = {
                    "as_of": tiers.get("as_of"),
                    "t1": len(t.get("T1") or []),
                    "t2": len(t.get("T2") or []),
                    "t3": len(t.get("T3") or []),
                }
        except Exception as exc:  # noqa: BLE001
            log.warning("radar: build_cashtag_tiers failed: %s", exc)

        # 8. Competitor cadence
        cadence_data = load_competitor_cadence(r)
        if cadence_data is not None:
            competitors = list(cadence_data.get("competitors") or [])
            comp_ids = [str(c.get("id", c)) if isinstance(c, dict) else str(c) for c in competitors]
            ppd = cadence_data.get("posts_per_day")
            cadence_meta = {
                "available": True,
                "source": "config/marketing_competitor_cadence.yml",
                "competitors": comp_ids,
                "posts_per_day": ppd,
            }
        else:
            cadence_meta = {
                "available": False,
                "source": "config/marketing_competitor_cadence.yml",
                "competitors": [],
                "posts_per_day": None,
            }

        # Build posted_recent count
        posted_set = _posted_tickers(r)

        # Assemble surplus items with opportunity_id
        opp_id_map = {o["opportunity_id"]: o for o in opps}
        surplus_with_ids: list[dict] = []
        for item in surplus[:40]:
            feed = item.get("feed", "")
            ticker = item.get("ticker", "")
            as_of = item.get("as_of", "")
            oid = f"radar-{feed}-{ticker}-{as_of}"
            surplus_with_ids.append(dict(item, opportunity_id=oid))

        report: dict = {
            "schema": "marketing.radar_report/v1",
            "schema_version": 1,
            "produced_by": "engine/marketing/radar_internal.py",
            "produced_at": _utc_now_iso(),
            "tier": "display",
            "as_of": today,
            "feeds": feeds_meta,
            "posted_recent": {"n_tickers": len(posted_set), "window_plans": 7},
            "surplus": surplus_with_ids,
            "queue": queue_summary,
            "tiers_summary": tiers_summary,
            "cadence": cadence_meta,
        }

        # Atomic write
        try:
            report_path = r / "data" / "marketing" / "radar_report.json"
            _write_json_atomic(report_path, report)
        except Exception as exc:  # noqa: BLE001
            log.warning("radar: write radar_report.json failed: %s", exc)

        return report

    except Exception as exc:  # noqa: BLE001
        log.warning("radar: build_radar catastrophic failure: %s", exc, exc_info=True)
        return {"error": str(exc)}
