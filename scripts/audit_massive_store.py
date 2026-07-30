"""Coverage-continuity audit for the massive_stock_day whole-market OHLCV store.

WHY THIS EXISTS (2026-07-03 incident): the store's committed _manifest.json claimed
`latest_date: 2026-06-30` while the parquets held only 2025-01-02→2026-03-12 — a
smoke test had advanced the v1 scalar resume state past a 110-day hole, and nothing
watched the store's CONTENT.  audit_r2 checks only that a manifest object is fresh
on R2 (Last-Modified), so a store that is freshly published yet full of holes sails
through.  The Options-Alpha W1.1 agent tripped over the hole and had to route around
the store entirely.  This audit is the content-level tripwire.

FAILS ARE FOR THE INCIDENT CLASS, NOT FOR OLD HISTORY (2026-07-29).  Continuity is
judged only over the trailing cfg[massive_recent_window_bdays] business days: an
in-window hole or a lying manifest is a live defect and fails, while a large gap deeper
in history is descriptive and only FLAGS.  Why: a full-history continuity fail says
nothing about tonight's feed and aborts every full-run quality gate until the gap
closes — and the two ways a big historical gap arises are both non-incidents.  A
mid-backfill or otherwise stale resume-state snapshot reports coverage the live store
already has (2026-07-29: the committed sidecar claimed 471 days against the 1,302 the
published store actually held), and a genuine hole being chipped by the capped nightly
incremental is a known remainder shrinking on its own.  What must alarm either way is a
NEW tip-adjacent gap.

WHAT IT CHECKS — ground truth is the ANCHOR PARQUETS, never the manifest:
  FAIL (counts toward the collect.py governance gate, aborts at >5% of the universe):
    - an anchor ticker (SPY/QQQ/AAPL/MSFT/IWM — maximally liquid, trade every US
      session) is missing from the store or unreadable;
    - CONTINUITY (IN-WINDOW): an anchor has a run of more than
      cfg[massive_max_gap_bdays] consecutive missing BUSINESS days between bars within
      the trailing window (holidays cost 1-2; the default of 5 = a full missing week;
      the incident hole was ~75).  Anchor continuity is equivalent to whole-store day
      continuity because each day is fetched as ONE whole-market file — a day missing
      from SPY is a day missing from everyone.
    - MANIFEST LIE: _manifest.json `latest_date` is more than
      cfg[massive_manifest_ahead_bdays] business days AHEAD of what the anchors
      actually hold — freshness claims the data cannot back (the incident signature).
  FLAG (logged, never fatal — suite convention: staleness is a flag):
    - the newest anchor bar is more than cfg[massive_stale_bdays] business days old;
    - a worst-gap older than the window, reported with its size so deep history stays
      visible rather than silently excused;
    - _manifest.json absent/unparsable while parquets exist.

SKIP: a checkout without the parquet store (fewer than cfg[massive_min_files] files
— e.g. a collect job whose R2 restore failed) is skipped entirely, never a failure —
matching the audit_prices convention that an absent backing store never aborts a
build.  On the nightly lane that skip is itself annotated: there, an absent store
means the restore did not work and the store did not advance.

Deterministic, READ-ONLY over the store; writes only data/quality/massive_store_audit.json.
Wired into scripts/collect.py run_quality_audits alongside prices/macro/universe, AND
run as its own non-fatal daily.yml collect step — the nightly lane passes
--exclude-group asia, which makes collect.py skip the whole quality gate as a partial
run, so this audit had ZERO nightly coverage through the 2026-07 freeze.  Exits 1 when
a member failed (content fail); stale flags and skips exit 0.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import audit_common as ac

log = logging.getLogger("audit.massive_store")

STORE = "massive_stock_day"
# Must-trade-daily names: any healthy whole-market day contains all of these.
ANCHORS = ["SPY", "QQQ", "AAPL", "MSFT", "IWM"]


def _read_dates(path: Path) -> pd.DatetimeIndex | None:
    try:
        return pd.to_datetime(pd.read_parquet(path, columns=[]).index).sort_values()
    except Exception:   # noqa: BLE001 — unreadable = audit fail, handled by caller
        return None


def _max_missing_bday_run(idx: pd.DatetimeIndex) -> tuple[int, str]:
    """Longest run of missing business days strictly between consecutive bars, and
    the ISO date where the worst gap starts.  Weekends are free; holidays cost 1."""
    if len(idx) < 2:
        return 0, ""
    d64 = idx.values.astype("datetime64[D]")
    # busday_count over [a, b) includes a (always a bday here) and excludes b.
    missing = np.busday_count(d64[:-1], d64[1:]) - 1
    worst = int(missing.max())
    where = str(d64[int(missing.argmax())]) if worst > 0 else ""
    return worst, where


def run(cfg: dict | None = None, asof: date | None = None,
        out_dir: Path | None = None, data_dir: Path | None = None) -> dict:
    """Audit the massive_stock_day store and persist
    data/quality/massive_store_audit.json.  Never raises for a data issue — every
    problem is a fail or a flag on the universe."""
    cfg = cfg or ac.quality_cfg()
    asof = asof or date.today()
    data_dir = Path(data_dir) if data_dir is not None else ac.ROOT / "data"
    store = data_dir / STORE

    max_gap = int(cfg.get("massive_max_gap_bdays", 5))
    stale_bd = int(cfg.get("massive_stale_bdays", 5))
    ahead_bd = int(cfg.get("massive_manifest_ahead_bdays", 2))
    min_files = int(cfg.get("massive_min_files", 100))
    window_bd = int(cfg.get("massive_recent_window_bdays", 90))

    uni = ac.Universe(name=STORE)
    n_parquets = len(list(store.glob("*.parquet"))) if store.is_dir() else 0
    if n_parquets < min_files:
        uni.skipped = True
        uni.note = (f"store absent/partial ({n_parquets} parquets < {min_files}) — "
                    "heavy store is R2-canonical, restored into the collect job")
        log.info("[massive_store] skipped: %s", uni.note)
        # On the nightly lane the store is supposed to BE here (daily.yml restores it
        # before the collectors run), so a skip means the restore failed or never ran
        # — i.e. the store did not advance tonight.  Other lanes skip in silence.
        if os.environ.get("COLLECT_LANE") == "nightly":
            print(f"::warning title=massive_store audit skipped::store absent "
                  f"({n_parquets} parquets < {min_files}) on the nightly lane — the R2 "
                  "restore failed or did not run; the store did not advance tonight",
                  flush=True)
        return ac.write_audit("massive_store", STORE, [uni], cfg, asof=asof,
                              out_dir=out_dir)

    # Members: the anchor tickers + the manifest contract. n is fixed so fail_pct is
    # meaningful even when an anchor file is missing outright.
    uni.n = len(ANCHORS) + 1
    anchor_last: list[date] = []
    stale_hits: list[tuple[date, int]] = []
    # Continuity is judged from this day forward; bars older than it are descriptive
    # only.  The left-anchor bar just BEFORE the window is kept in the slice (see
    # below) so a gap that straddles the boundary is still measured.
    window_start = pd.Timestamp(str(np.busday_offset(
        np.datetime64(asof, "D"), -window_bd, roll="backward")))
    for t in ANCHORS:
        p = store / f"{t}.parquet"
        if not p.exists():
            uni.fail(t, "anchor parquet missing from a populated store")
            continue
        idx = _read_dates(p)
        if idx is None or len(idx) == 0:
            uni.fail(t, "anchor parquet unreadable/empty")
            continue
        anchor_last.append(idx[-1].date())
        # Slice = every in-window bar PLUS the last bar before the window. Without that
        # left anchor a hole ending inside the window (bars stop in February, resume in
        # June) would present as a clean run of recent bars — invisible to the very
        # check that exists to catch it.
        before = idx[idx < window_start]
        recent = idx[idx >= window_start]
        if len(before):
            recent = recent.insert(0, before[-1])
        worst, where = _max_missing_bday_run(recent)
        if worst > max_gap:
            uni.fail(t, f"coverage hole: {worst} consecutive business days missing "
                        f"after {where} (limit {max_gap}) — inside the trailing "
                        f"{window_bd}-business-day window; store content has a gap "
                        "regardless of what the manifest claims")
        # Deep history stays visible as a flag: narrowing the FAIL to a window must not
        # also delete the report of what sits behind it.
        worst_all, where_all = _max_missing_bday_run(idx)
        if worst_all > max_gap and worst_all > worst:
            uni.flag(t, "historical_gap",
                     f"{worst_all} consecutive business days missing after {where_all} "
                     f"— older than the {window_bd}-business-day continuity window, so "
                     "it flags rather than fails (descriptive, not tonight's feed)")
        age_bd = int(np.busday_count(idx[-1].date(), asof))
        if age_bd > stale_bd:
            uni.flag(t, "stale", f"newest bar {idx[-1].date()} is {age_bd} business "
                                 f"days old (limit {stale_bd})")
            stale_hits.append((idx[-1].date(), age_bd))

    # Manifest-lie detector: freshness claims must be backed by anchor content.
    mf = store / "_manifest.json"
    claimed: date | None = None
    if mf.exists():
        try:
            claimed = date.fromisoformat(str(json.loads(mf.read_text())["latest_date"]))
        except Exception:   # noqa: BLE001
            uni.flag("_manifest", "unparsable", "manifest exists but latest_date "
                                                "missing/unparsable")
    else:
        uni.flag("_manifest", "absent", "parquet store present but _manifest.json "
                                        "missing — freshness beacon dark")
    if claimed and anchor_last:
        actual = max(anchor_last)
        ahead = int(np.busday_count(actual, claimed)) if claimed > actual else 0
        if ahead > ahead_bd:
            uni.fail("_manifest",
                     f"manifest claims latest_date={claimed} but the anchors' newest "
                     f"bar is {actual} ({ahead} business days behind the claim, limit "
                     f"{ahead_bd}) — freshness the store content cannot back "
                     "(the 2026-07-03 incident signature)")

    doc = ac.write_audit("massive_store", STORE, [uni], cfg, asof=asof, out_dir=out_dir)
    reasons = "; ".join(f["name"] + ": " + f["reasons"][0] for f in uni.failed)
    if uni.n_failed:
        log.error("[massive_store] %d/%d member(s) FAILED — %s",
                  uni.n_failed, uni.n, reasons)
        print(f"::error title=massive_store audit::{uni.n_failed} member(s) failed — "
              f"{reasons}", flush=True)
    else:
        log.info("[massive_store] clean — %d anchors continuous in the trailing %d "
                 "business days, manifest honest (%d parquets)",
                 len(ANCHORS), window_bd, n_parquets)
    if stale_hits:
        newest, age = max(stale_hits)
        print(f"::warning title=massive_store stale::newest anchor bar {newest} is "
              f"{age} business days old (limit {stale_bd}) — the whole-market store is "
              "not advancing", flush=True)
    return doc


def exit_code(doc: dict) -> int:
    """1 when a member FAILED (content fail), 0 otherwise.

    Stale flags and skips are warnings and exit 0 — they are already annotated, and the
    daily.yml step is continue-on-error, so the code exists for humans and reruns rather
    than as a gate.
    """
    return 1 if any(u.get("n_failed") for u in doc.get("universes", [])) else 0


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _doc = run()
    print(json.dumps(_doc, indent=2))
    sys.exit(exit_code(_doc))
