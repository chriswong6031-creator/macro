"""scripts/build_rebalance_pulse.py — RLT-R2 nightly builder (off render path).

Computes the Rebalance Pulse for the latest NYSE session; appends to the
append-only ledger when class != quiet and the date is not already present
(idempotent — PIT law RC-R2 class).

Writes:
  data/rebalance_pulse/events.jsonl       append-only ledger (non-quiet only)
  data/rebalance_pulse/latest.json        latest pulse record
  site/marketdata/rebalance_pulse.json    display payload (authority block included)

Authority: display/context tier.  may_rank=false, may_gate=false, may_size=false.

Usage:
    python -m scripts.build_rebalance_pulse
    python -m scripts.build_rebalance_pulse --root /path/to/repo
    python -m scripts.build_rebalance_pulse --asof 2026-07-10
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("build_rebalance_pulse")

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Maximum recent events in site payload
_RECENT_N = 10

# How many upcoming events to show
_UPCOMING_N = 3


def _atomic_write_json(path: Path, payload: dict | list) -> None:
    """Write JSON atomically via temp-file + rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".tmp_{path.name}_",
        suffix=".json",
        delete=False,
    ) as tf:
        tf.write(text)
        tmp_path = Path(tf.name)
    tmp_path.replace(path)


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return rows


def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def _next_upcoming_events(asof: date, y_range: int = 2) -> list[dict]:
    """Return up to _UPCOMING_N upcoming calendar events from today."""
    import pandas as pd
    from engine.rebalance_calendar import (
        quarter_end_sessions,
        russell_recon_sessions,
        sp_rebalance_sessions,
        month_end_sessions,
    )
    from lib.nyse_calendar import is_session

    y0 = asof.year
    y1 = asof.year + y_range

    qe_set = {d: "quarter_end" for d in quarter_end_sessions(y0, y1) if d > asof}
    recon_set = {d: "russell_recon" for d in russell_recon_sessions(y0, y1) if d > asof}

    # Build S&P sessions for the window
    import pandas as _pd
    idx = _pd.bdate_range(start=asof, periods=200)
    sp_set = {d: "sp_rebalance" for d in sp_rebalance_sessions(idx) if d > asof}

    # Merge (a day can be multiple types)
    from collections import defaultdict
    merged: dict[date, list[str]] = defaultdict(list)
    for ev_dict in (qe_set, recon_set, sp_set):
        for d, kind in ev_dict.items():
            merged[d].append(kind)

    upcoming = []
    from engine.rebalance_calendar import _signed_td
    for d in sorted(merged.keys())[:_UPCOMING_N * 3]:  # oversample, then trim
        td = _signed_td(asof, d) if asof != d else 0
        upcoming.append({
            "date": d.isoformat(),
            "types": sorted(set(merged[d])),
            "td_to": td,
        })
        if len(upcoming) >= _UPCOMING_N:
            break

    return upcoming


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="RLT-R2: build rebalance pulse (nightly, off-render)."
    )
    ap.add_argument("--root", type=Path, default=None)
    ap.add_argument(
        "--asof",
        type=str,
        default=None,
        help="Override session date (YYYY-MM-DD; default: latest expected session).",
    )
    args = ap.parse_args(argv)

    root = args.root.resolve() if args.root is not None else _REPO_ROOT

    # Determine asof
    if args.asof:
        asof = date.fromisoformat(args.asof)
    else:
        from lib.nyse_calendar import expected_last_session
        asof = expected_last_session()

    log.info("build_rebalance_pulse: asof=%s", asof)

    data_dir = root / "data"
    site_dir = root / "site"

    ledger_path = data_dir / "rebalance_pulse" / "events.jsonl"
    latest_path = data_dir / "rebalance_pulse" / "latest.json"
    site_path = site_dir / "marketdata" / "rebalance_pulse.json"

    # ── Load data (all fail-open) ────────────────────────────────────────────
    import pandas as pd
    gaps = []

    # Volume cache
    vol_path = data_dir / "breadth" / "_volume_cache.parquet"
    volume_cache_df: pd.DataFrame = pd.DataFrame()
    try:
        volume_cache_df = pd.read_parquet(vol_path)
        volume_cache_df.index = pd.DatetimeIndex(volume_cache_df.index)
        log.info("loaded _volume_cache: %s rows x %s tickers", len(volume_cache_df), len(volume_cache_df.columns))
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"_volume_cache: {exc}")
        log.warning("build_rebalance_pulse: _volume_cache absent — %s", exc)

    # Updown
    updown_path = data_dir / "breadth" / "updown.parquet"
    updown_df: pd.DataFrame | None = None
    try:
        updown_df = pd.read_parquet(updown_path)
        updown_df.index = pd.DatetimeIndex(updown_df.index)
        log.info("loaded updown: %s rows", len(updown_df))
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"updown: {exc}")
        log.warning("build_rebalance_pulse: updown absent — %s", exc)

    # ── Calendar tags ────────────────────────────────────────────────────────
    from engine.rebalance_calendar import tag as cal_tag
    try:
        calendar_tags = cal_tag(asof)
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"calendar_tags: {exc}")
        log.warning("build_rebalance_pulse: calendar tag failed — %s", exc)
        calendar_tags = {
            "is_quarter_end": False,
            "td_to_quarter_end": 999,
            "in_qtr_end_window": False,
            "is_russell_recon_session": False,
            "in_recon_week": False,
            "is_sp_rebalance_session": False,
            "is_month_end_session": False,
        }

    # ── Compute pulse ────────────────────────────────────────────────────────
    from engine.rebalance_pulse import compute_pulse
    try:
        pulse = compute_pulse(
            asof=asof,
            volume_cache_df=volume_cache_df,
            updown_df=updown_df,
            calendar_tags=calendar_tags,
            closes=None,
        )
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"compute_pulse: {exc}")
        log.error("build_rebalance_pulse: compute_pulse failed — %s", exc)
        pulse = {
            "date": asof.isoformat(),
            "class": "quiet",
            "market_vol_ratio": None,
            "up_share": None,
            "basis": "error",
            "n_megacap_rvol2": 0,
            "megacap_rvol": {},
            "calendar": calendar_tags,
            "summary_en": "Data unavailable for this session.",
            "summary_zh": "本交易日数据不可用。",
            "authority": {"may_rank": False, "may_gate": False, "may_size": False},
        }

    pulse_class = pulse.get("class", "quiet")
    log.info("pulse: class=%s vol_ratio=%s up_share=%s", pulse_class,
             pulse.get("market_vol_ratio"), pulse.get("up_share"))

    # ── Write latest.json ────────────────────────────────────────────────────
    _atomic_write_json(latest_path, pulse)
    log.info("wrote %s", latest_path)

    # ── Append to ledger (idempotent, non-quiet only) ─────────────────────────
    if pulse_class != "quiet":
        existing = _load_jsonl(ledger_path)
        existing_dates = {r.get("date") for r in existing}
        if asof.isoformat() not in existing_dates:
            _append_jsonl(ledger_path, pulse)
            log.info("appended to ledger: %s", ledger_path)
        else:
            log.info("ledger already has %s — skipping append (idempotent)", asof.isoformat())

    # ── Build upcoming calendar events ────────────────────────────────────────
    upcoming: list[dict] = []
    try:
        upcoming = _next_upcoming_events(asof)
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"upcoming_events: {exc}")
        log.warning("build_rebalance_pulse: upcoming events failed — %s", exc)

    # ── Build recent events from ledger ──────────────────────────────────────
    all_ledger = _load_jsonl(ledger_path)
    recent = sorted(all_ledger, key=lambda r: r.get("date", ""), reverse=True)[:_RECENT_N]

    # ── Site payload ─────────────────────────────────────────────────────────
    site_payload = {
        "as_of": asof.isoformat(),
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latest_pulse": pulse,
        "upcoming_events": upcoming,
        "recent_events": recent,
        "gaps": gaps,
        "authority": {
            "may_rank": False,
            "may_gate": False,
            "may_size": False,
        },
        "note_en": (
            "Rebalance Pulse is a mechanical day-classifier showing whether "
            "elevated volume coincides with scheduled calendar events. "
            "Display/context only — no rank, gate, or sizing authority."
        ),
        "note_zh": (
            "再平衡脉冲是一种机械性日分类器，显示异常量能是否与计划中的日历事件同步发生。"
            "仅供展示/参考——不具备排名、门槛或仓位权限。"
        ),
    }

    _atomic_write_json(site_path, site_payload)
    log.info("wrote %s", site_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
