"""scripts/audit_qbus.py — qbus measurement harness (§2.4 / §2.5 W2-B3).

Runs standalone on the live bus to produce a JSON + Markdown report the integrator
can commit.  Never raises; broken ≠ quiet (non-zero exit + status file on failure).

Sections:
  (a) ECHO REPORT   — top event_keys by n_sources/n_desks in last 7d, demonstrating
                       one wire story = one event_key across macro_news / financial_news
                       / news_vector / china lanes.
  (b) NOVELTY DIST  — novelty_z histogram sanity (distribution should be roughly
                       standard-normal; tails flag either flood or drought).
  (c) PER-DESK MIX  — item counts + timestamp_quality mix per desk.
  (d) DUPLICATE RATE — same story counted N times pre-bus (raw item_id count per
                       event_key) vs 1 event_key post-clustering.  Reduction ratio is
                       the bus efficiency metric.

Run:
    python scripts/audit_qbus.py                       # use repo root
    python scripts/audit_qbus.py --root /other/root    # alternate root
    python scripts/audit_qbus.py --days 7              # lookback window (default 7)
    python scripts/audit_qbus.py --out data/qbus/audit_latest.json

Writes:
    data/qbus/audit_latest.json     — machine-readable report
    data/qbus/audit_latest.md       -- human-readable Markdown summary
    data/qbus/audit_run_status.json — health tri-state (ok / warn / error)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

_STATUS_FILE = ("data", "qbus", "audit_run_status.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_status(root: Path, status: str, summary: str, detail: dict | None = None) -> None:
    p = root / Path(*_STATUS_FILE)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"status": status, "summary": summary,
                              "checked_at": _now(), **(detail or {})}, default=str))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _read_bus(root: Path):
    """Read data/qbus/items.parquet. Returns DataFrame or None."""
    try:
        import pandas as pd
        p = root / "data" / "qbus" / "items.parquet"
        if not p.exists():
            return None
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("qbus read failed: %s", e)
        return None


def _window_df(df, days: int, today: date):
    """Filter to rows whose seendate or _crawled_at falls in last `days` days."""
    try:
        import pandas as pd
        cutoff = (today - timedelta(days=days)).isoformat()
        # prefer seendate; fall back to _crawled_at
        ts = df["seendate"].where(df["seendate"] != "", other=df["_crawled_at"])
        ts_str = ts.astype(str)
        mask = ts_str >= cutoff
        return df[mask].copy()
    except Exception:  # noqa: BLE001
        return df.copy()


# --------------------------------------------------------------------------- #
# section (a) — echo report
# --------------------------------------------------------------------------- #
def _echo_report(df, days: int, today: date, top_n: int = 20) -> dict:
    """Top event_keys by n_sources in window; shows cross-desk corroboration."""
    try:
        import pandas as pd
        w = _window_df(df, days, today)
        if w.empty:
            return {"top_events": [], "window_days": days, "n_items": 0}

        # group by event_key
        grp = (
            w[w["event_key"] != ""]
            .groupby("event_key")
            .agg(
                n_items=("item_id", "count"),
                n_sources=("source", "nunique"),
                n_desks=("desk", "nunique"),
                desks=("desk", lambda x: sorted(set(x))),
                first_seen=(
                    "seendate",
                    lambda x: min(
                        (str(v) for v in x if str(v) and str(v) != "nan"),
                        default="",
                    ),
                ),
                sample_title=("title", "first"),
            )
            .reset_index()
            .sort_values(["n_sources", "n_desks", "n_items"], ascending=False)
            .head(top_n)
        )
        events = grp.to_dict(orient="records")
        # coerce list columns for JSON
        for e in events:
            if not isinstance(e.get("desks"), list):
                e["desks"] = list(e.get("desks", []))

        # cross-desk hits: events seen in 2+ desks
        multi_desk = sum(1 for e in events if e.get("n_desks", 0) >= 2)

        return {
            "window_days": days,
            "n_items": int(len(w)),
            "n_unique_event_keys": int(w["event_key"].nunique()),
            "multi_desk_events_top20": multi_desk,
            "top_events": events,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("echo_report failed: %s", e)
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# section (b) — novelty distribution
# --------------------------------------------------------------------------- #
def _novelty_dist(df, days: int, today: date) -> dict:
    """Sample novelty_z for top themes/entities; report histogram + stats."""
    try:
        from engine import qbus

        w = _window_df(df, days, today)
        if w.empty:
            return {"n_sampled": 0}

        # collect unique themes
        all_themes: list[str] = []
        for v in w["themes"].fillna("").astype(str):
            all_themes.extend(t for t in v.split(",") if t)
        from collections import Counter
        top_themes = [t for t, _ in Counter(all_themes).most_common(10)]

        zscores: list[float] = []
        for theme in top_themes:
            z = qbus.novelty_z(theme, asof=today, window_days=30, df=df)
            if z is not None:
                zscores.append(round(z, 2))

        if not zscores:
            return {"n_sampled": 0, "note": "insufficient history for novelty_z"}

        import statistics
        return {
            "n_sampled": len(zscores),
            "themes_sampled": top_themes[: len(zscores)],
            "mean_z": round(statistics.mean(zscores), 3),
            "stdev_z": round(statistics.stdev(zscores), 3) if len(zscores) > 1 else None,
            "min_z": min(zscores),
            "max_z": max(zscores),
            "zscores": zscores,
            "sanity": "ok" if abs(statistics.mean(zscores)) < 3 else "WARN:high_mean",
        }
    except Exception as e:  # noqa: BLE001
        log.warning("novelty_dist failed: %s", e)
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# section (c) — per-desk item counts + timestamp_quality mix
# --------------------------------------------------------------------------- #
def _desk_mix(df, days: int, today: date) -> dict:
    """Per-desk item counts and timestamp_quality distribution."""
    try:
        import pandas as pd
        w = _window_df(df, days, today)
        if w.empty:
            return {"desks": [], "window_days": days}

        rows = []
        for desk, grp in w.groupby("desk"):
            tq_counts = grp["timestamp_quality"].value_counts().to_dict()
            rows.append({
                "desk": desk,
                "n_items": int(len(grp)),
                "n_unique_events": int(grp["event_key"].nunique()),
                "timestamp_quality_mix": {str(k): int(v) for k, v in tq_counts.items()},
            })
        rows.sort(key=lambda r: r["n_items"], reverse=True)

        # total summary
        total_items = int(len(w))
        tq_all = w["timestamp_quality"].value_counts().to_dict()
        return {
            "window_days": days,
            "total_items": total_items,
            "n_desks": len(rows),
            "timestamp_quality_all": {str(k): int(v) for k, v in tq_all.items()},
            "desks": rows,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("desk_mix failed: %s", e)
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# section (d) — duplicate rate before/after clustering
# --------------------------------------------------------------------------- #
def _duplicate_rate(df, days: int, today: date) -> dict:
    """Before-bus: same story lands N times (N item_ids per event_key).
    After-bus: collapses to 1 event_key.  Reduction ratio = bus efficiency."""
    try:
        import pandas as pd
        w = _window_df(df, days, today)
        if w.empty:
            return {"window_days": days, "n_items": 0, "reduction_ratio": None}

        keyed = w[w["event_key"] != ""]
        if keyed.empty:
            return {"window_days": days, "n_items": int(len(w)),
                    "n_keyed": 0, "reduction_ratio": None,
                    "note": "no event_keys assigned yet"}

        items_per_key = keyed.groupby("event_key")["item_id"].count()
        multi = items_per_key[items_per_key > 1]

        n_raw_items = int(len(keyed))
        n_unique_events = int(keyed["event_key"].nunique())
        reduction = round(n_raw_items / n_unique_events, 2) if n_unique_events else None
        return {
            "window_days": days,
            "n_items_total": int(len(w)),
            "n_items_keyed": n_raw_items,
            "n_unique_events": n_unique_events,
            "n_multi_source_events": int(len(multi)),
            "max_items_per_event": int(items_per_key.max()) if len(items_per_key) else 0,
            "mean_items_per_event": round(float(items_per_key.mean()), 2) if len(items_per_key) else 0,
            # ratio > 1 means the bus is collapsing duplicates; ratio == 1 means no dedup needed
            "raw_to_event_ratio": reduction,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("duplicate_rate failed: %s", e)
        return {"error": str(e)}


# --------------------------------------------------------------------------- #
# Markdown renderer
# --------------------------------------------------------------------------- #
def _render_md(report: dict) -> str:
    lines: list[str] = [
        "# qbus audit report",
        f"**generated:** {report.get('generated_at', '')}  ",
        f"**lookback:** {report.get('window_days', 7)}d  ",
        f"**bus size:** {report.get('n_total_items', '?')} items  ",
        "",
        "## (a) Echo — top events by cross-desk corroboration",
    ]
    echo = report.get("echo", {})
    lines.append(f"Items in window: {echo.get('n_items', 0)}  "
                 f"Unique event_keys: {echo.get('n_unique_event_keys', 0)}  "
                 f"Multi-desk (top 20): {echo.get('multi_desk_events_top20', 0)}")
    lines.append("")
    lines.append("| event_key | n_items | n_sources | n_desks | desks | sample_title |")
    lines.append("|-----------|---------|-----------|---------|-------|--------------|")
    for ev in (echo.get("top_events") or [])[:10]:
        desks = ", ".join(ev.get("desks") or [])
        title = str(ev.get("sample_title", ""))[:60].replace("|", "\\|")
        lines.append(
            f"| `{ev.get('event_key', '')[:10]}…` "
            f"| {ev.get('n_items', '')} "
            f"| {ev.get('n_sources', '')} "
            f"| {ev.get('n_desks', '')} "
            f"| {desks} "
            f"| {title} |"
        )
    lines.append("")
    lines.append("## (b) Novelty distribution")
    nov = report.get("novelty", {})
    if nov.get("n_sampled", 0):
        lines.append(
            f"n={nov['n_sampled']}  mean_z={nov.get('mean_z')}  "
            f"stdev_z={nov.get('stdev_z')}  "
            f"min={nov.get('min_z')}  max={nov.get('max_z')}  "
            f"sanity={nov.get('sanity', '?')}"
        )
    else:
        lines.append(f"Insufficient data: {nov.get('note', nov.get('error', '?'))}")
    lines.append("")
    lines.append("## (c) Per-desk mix")
    desk = report.get("desk_mix", {})
    lines.append(f"Total items: {desk.get('total_items', 0)}  "
                 f"Desks: {desk.get('n_desks', 0)}")
    lines.append("")
    lines.append("| desk | n_items | n_unique_events | timestamp_quality |")
    lines.append("|------|---------|-----------------|-------------------|")
    for d in (desk.get("desks") or []):
        tq = ", ".join(f"{k}:{v}" for k, v in (d.get("timestamp_quality_mix") or {}).items())
        lines.append(
            f"| {d.get('desk', '')} | {d.get('n_items', '')} "
            f"| {d.get('n_unique_events', '')} | {tq} |"
        )
    lines.append("")
    lines.append("## (d) Duplicate rate")
    dup = report.get("duplicate_rate", {})
    lines.append(
        f"Raw items: {dup.get('n_items_keyed', '?')}  "
        f"Unique events: {dup.get('n_unique_events', '?')}  "
        f"Ratio: {dup.get('raw_to_event_ratio', '?')}×  "
        f"Multi-source events: {dup.get('n_multi_source_events', '?')}"
    )
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def run(root: Path, days: int = 7, out: Path | None = None) -> dict:
    today = date.today()
    df = _read_bus(root)
    n_total = 0 if df is None else len(df)

    report: dict = {
        "generated_at": _now(),
        "window_days": days,
        "n_total_items": n_total,
    }

    if df is None:
        report["status"] = "warn"
        report["note"] = "data/qbus/items.parquet not found — bus has no data yet"
        log.warning("qbus audit: items.parquet not found")
    else:
        report["echo"] = _echo_report(df, days, today)
        report["novelty"] = _novelty_dist(df, days, today)
        report["desk_mix"] = _desk_mix(df, days, today)
        report["duplicate_rate"] = _duplicate_rate(df, days, today)
        report["status"] = "ok"

    # write JSON output
    out_json = out or (root / "data" / "qbus" / "audit_latest.json")
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, default=str, indent=2))

    # write Markdown
    out_md = out_json.with_suffix(".md")
    out_md.write_text(_render_md(report))

    # write health status
    _write_status(root, report["status"], f"qbus audit: {n_total} total items", report)

    print(f"qbus audit: {n_total} total items, window={days}d  [{report['status']}]")
    print(f"  echo:  {report.get('echo', {}).get('n_unique_event_keys', 0)} unique events")
    print(f"  dedup: {report.get('duplicate_rate', {}).get('raw_to_event_ratio', '?')}× reduction")
    print(f"  out:   {out_json}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repo root (default: cwd)")
    parser.add_argument("--days", type=int, default=7, help="lookback window in days")
    parser.add_argument("--out", default=None, help="output JSON path")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    # add root to sys.path so engine/lib imports work standalone
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    out = Path(args.out) if args.out else None
    try:
        report = run(root, days=args.days, out=out)
        return 0 if report.get("status") == "ok" else 1
    except Exception as e:  # noqa: BLE001
        log.error("audit_qbus failed: %s", e)
        _write_status(root, "error", str(e))
        return 2


if __name__ == "__main__":
    sys.exit(main())
