"""Per-name freshness tripwire for the data/stocks/ single-stock price store.

WHY THIS EXISTS (2026-08-03 incident): data/stocks/<T>.parquet is written solely by
collectors.sector_holdings.StockPriceAdapter, whose fetch set used to be JUST
top10_union() — the union of the CURRENT top-20 holdings across the 11 sector SPDRs.
The moment a name fell out of every fund's top-20 it silently left the fetch set and
its parquet froze forever, while scripts/build_stock_library.py's universe() kept
preferring the frozen deep store over fresher breadth caches — nothing ever noticed.
Measured receipts: QCOM/HOOD froze 24d, MRVL 21d, CVNA/HON 17d, WDC 10d, SATS 46d (as
of this adjudication). collectors/sector_holdings.py now carries a retention fix
(_fetch_universe: union PLUS everything still on disk, minus confirmed-dead names) so
a dropped name keeps getting fetched going forward — but NOTHING previously audited
per-name tips: scripts/audit_prices.py checks interior gaps only (a frozen series has
no gap to find), scripts/check_price_store_freshness.py gates only SPY in data/yahoo,
and the Adapter-level stale_after_days convention is GROUP-level (one fresh name in a
235-name store masks 234 stale ones). This audit is the missing per-name tripwire.

WHAT IT CHECKS — accountable set = every stem under data/stocks/*.parquet (skip
leading-underscore stems) UNION top10_union() (a name the union just added but the
store hasn't caught up to yet shows as "missing", never silently absent):
  fresh        — lag <= cfg[stocks_stale_calendar_days] (default 7)
  stale_live   — lag > threshold, ticker NOT in the dead-name registry (a live alarm —
                 the fetch for this name is not advancing)
  stale_dead   — lag > threshold, ticker IS in the dead-name registry (counted for the
                 record, never alarmed — the name is gone for a documented reason, not
                 a fetch defect)
  missing      — ticker is in the union but has no parquet on disk at all
  unreadable   — the parquet exists but fails to read (corrupt/short file)

LAG ANCHOR (2026-08-03 correction): lag is measured from the ET calendar date of `now`
to the store's last bar date — NOT from lib.nyse_calendar.expected_last_session(now).
Anchoring to the expected session let an exact-boundary case (e.g. a freeze that lands
on a multiple of the trading-week cadence) hide under a `<= threshold` read that the
wall-clock calendar itself would call stale (WDC: last bar Fri 07-24, expected session
Fri 07-31 => exactly 7 days => inadmissible under the session anchor even though the
real freeze was already 10 calendar days deep by the time this audit ran on 08-03).
expected_last_session(now) is still computed and recorded in the marker doc as human
context, but it never participates in the flag decision. The THRESHOLD alone absorbs
weekends/holidays: the worst MODELLED consecutive-session gap on the 2000-2026
calendar is 5 calendar days (Hurricane Sandy, 2012-10-26 -> 10-31); the worst REAL one
is the 9/11 closure (2001-09-10 -> 09-17 = 7 calendar days — absent from
lib/nyse_calendar's ONE_OFF_CLOSURES) — exactly the 7-day default, admissible only
through the strict `>`, the same zero-margin contract as PR #4441's ledger gate
_MAX_BAR_LAG_DAYS. A Friday-tip store checked the following Monday (3 calendar days)
reads fresh.

EVERYTHING IS A FLAG, NEVER A FAIL (disclosure-only by law — DO_NOT_REBUILD CSP-R1,
"staleness is a flag"): every stale_live/stale_dead/missing/unreadable name is recorded
via Universe.flag(), never Universe.fail(), so n_failed is always 0 and the
run_quality_audits governance gate (scripts/collect.py) can never abort a run on this
audit's account. audit_prices.py remains the sole corruption FAIL authority for these
stores; this audit only discloses staleness, loudly, and lets a human (or a downstream
consumer) decide what to do about it.

SKIP: an absent or empty data/stocks/ directory (a CI checkout whose restore step did
not run, or one that has not yet populated the store) is skipped entirely — matching
the audit_prices/audit_massive_store convention that an absent backing store never
aborts a build.

Deterministic, READ-ONLY over the store; writes only
data/quality/stocks_freshness_audit.json. Wired into scripts/collect.py
run_quality_audits AND run as its own daily.yml step: the nightly lane runs
`collect.py --exclude-group asia`, which makes collect.py skip the WHOLE
run_quality_audits gate as a partial run (see scripts/audit_massive_store.py's
identical note) — so without its own step this audit would have zero nightly
coverage. The default exit code (used by both run_quality_audits and the daily.yml
step) is ALWAYS 0 for data findings — the annotation carries the alarm, never the
exit code. `--strict` exits 3 when any stale_live/missing/unreadable name exists. An
unexpected crash exits 2.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from collectors.sector_holdings import _dead_tickers, top10_union  # noqa: E402
from lib import config, nyse_calendar  # noqa: E402
from scripts import audit_common as ac  # noqa: E402

log = logging.getLogger("audit.stocks_freshness")

STORE = "stocks"


def _today_et(now: datetime | None) -> date:
    """The ET calendar date `now` falls on — same UTC-default/naive-as-UTC convention
    as lib.nyse_calendar.expected_last_session, but WITHOUT that function's session
    roll-back: lag here is measured against the actual day the audit runs, because the
    THRESHOLD (not the anchor) is what must absorb weekends/holidays — see the module
    docstring's LAG ANCHOR section for why expected_last_session must not be used in
    the flag decision itself (2026-08-03 correction)."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(nyse_calendar.ET).date()


def run(cfg: dict | None = None, now: datetime | None = None,
        out_dir: Path | None = None, data_dir: Path | None = None) -> dict:
    """Audit data/stocks/ per-name freshness and persist
    data/quality/stocks_freshness_audit.json. Never raises for a data issue — every
    finding is a flag, never a fail (see module docstring)."""
    cfg = cfg or ac.quality_cfg()
    data_dir = Path(data_dir) if data_dir is not None else ac.ROOT / "data"
    store_dir = data_dir / STORE
    threshold = int(cfg.get("stocks_stale_calendar_days", 7))

    today_et = _today_et(now)
    expected = nyse_calendar.expected_last_session(now)  # context only — see docstring

    uni = ac.Universe(name=STORE)
    files = sorted(store_dir.glob("*.parquet")) if store_dir.is_dir() else []
    if not files:
        uni.skipped = True
        uni.note = f"data/stocks absent/empty ({store_dir}) — nothing to audit"
        log.info("[stocks_freshness] skipped: %s", uni.note)
        doc = ac.write_audit("stocks_freshness", STORE, [uni], cfg, asof=today_et, out_dir=out_dir)
        doc["expected_session"] = str(expected)
        doc["threshold_calendar_days"] = threshold
        doc["totals"] = {"fresh": 0, "stale_live": 0, "stale_dead": 0, "missing": 0, "unreadable": 0}
        doc["stale_live"], doc["stale_dead"], doc["missing"], doc["unreadable"] = [], [], [], []
        _rewrite(doc, out_dir)
        # data/stocks is git-TRACKED (unlike the R2-restored massive store): an
        # absent/empty dir means the checkout itself is broken, and a silent skip
        # would be the detector going dark — annotate, never just log.
        print("::warning title=stocks store freshness::data/stocks absent/empty — "
              "per-name freshness detector DARK this run", flush=True)
        print(f"[stocks_freshness] now_et={today_et} expected_session={expected} "
              f"threshold={threshold}d status=skipped fresh=0 stale_live=0 stale_dead=0 "
              f"missing=0 unreadable=0")
        return doc

    union_unavailable = False
    try:
        union = set(top10_union())
    except Exception as e:  # noqa: BLE001 — the accountable set must never crash the audit
        # Without the union the `missing` class is structurally undetectable and every
        # record's in_union field degrades to False — that blindness must be DISCLOSED,
        # not just logged (the #4441 dark-gate precedent: a detector may fail, never
        # silently disarm).
        union_unavailable = True
        log.warning("[stocks_freshness] top10_union() failed (%s) — union contributes nothing", e)
        print(f"::warning title=stocks store freshness::top10_union() unavailable ({e}) — "
              "the 'missing' detector is DARK this run", flush=True)
        union = set()

    # dead_store_absent reflects FILE EXISTENCE only (via the same path _dead_tickers()
    # reads): a present-but-corrupt registry silently degrades to frozenset() through
    # _dead_tickers()'s own contract and is not separately distinguished here.
    dead_path = config.data_dir() / "edgar" / "dead_name_prices.parquet"
    dead_store_absent = not dead_path.exists()
    try:
        dead = _dead_tickers()
    except Exception as e:  # noqa: BLE001 — _dead_tickers() already degrades gracefully; belt+suspenders
        log.warning("[stocks_freshness] _dead_tickers() raised (%s) — treating as empty", e)
        dead = frozenset()

    stems = {p.stem for p in files if not p.stem.startswith("_")}
    accountable = sorted(stems | union)
    uni.n = len(accountable)

    totals = {"fresh": 0, "stale_live": 0, "stale_dead": 0, "missing": 0, "unreadable": 0}
    stale_live_records: list[dict] = []
    stale_dead_records: list[dict] = []
    missing_records: list[dict] = []
    unreadable_records: list[dict] = []

    for t in accountable:
        p = store_dir / f"{t}.parquet"
        in_union = t in union
        if not p.exists():
            totals["missing"] += 1
            uni.flag(t, "missing", "in the top-N union, no data/stocks parquet on disk")
            missing_records.append({"ticker": t, "in_union": in_union})
            continue
        try:
            idx = pd.to_datetime(pd.read_parquet(p, columns=[]).index)
        except Exception as e:  # noqa: BLE001 — one bad file must not crash the audit
            totals["unreadable"] += 1
            uni.flag(t, "unreadable", f"parquet read failed: {e}")
            unreadable_records.append({"ticker": t, "in_union": in_union})
            continue
        if len(idx) == 0:
            totals["unreadable"] += 1
            uni.flag(t, "unreadable", "parquet read ok but empty")
            unreadable_records.append({"ticker": t, "in_union": in_union})
            continue
        last_bar = idx.max().date()
        lag_days = (today_et - last_bar).days
        if lag_days <= threshold:
            totals["fresh"] += 1
            continue
        if t in dead and not in_union:
            # Union-aware mute, mirroring _fetch_universe's union-wins rule: a
            # dead-registry ticker STILL in the current union is a reused symbol
            # being actively fetched (live specimen: ECHO — 2021 registry corpse
            # ~$48 vs the live store ~$96, in today's union) and must alarm as
            # stale_live below when its fetch breaks, or the reuse recreates the
            # 2026-08-03 incident silently.
            totals["stale_dead"] += 1
            uni.flag(t, "stale_dead", f"last bar {last_bar} ({lag_days}d) — dead-name "
                                      "registry, not alarmed")
            stale_dead_records.append({"ticker": t, "last_bar": str(last_bar),
                                       "lag_days": lag_days, "in_union": in_union})
            continue
        totals["stale_live"] += 1
        uni.flag(t, "stale_live", f"last bar {last_bar} ({lag_days}d stale)")
        stale_live_records.append({"ticker": t, "last_bar": str(last_bar),
                                   "lag_days": lag_days, "in_union": in_union})

    stale_live_records.sort(key=lambda r: (-r["lag_days"], r["ticker"]))

    doc = ac.write_audit("stocks_freshness", STORE, [uni], cfg, asof=today_et, out_dir=out_dir)
    doc["expected_session"] = str(expected)
    doc["threshold_calendar_days"] = threshold
    doc["totals"] = totals
    doc["stale_live"] = stale_live_records
    doc["stale_dead"] = stale_dead_records
    doc["missing"] = missing_records
    doc["unreadable"] = unreadable_records
    if dead_store_absent:
        doc["dead_store_absent"] = True
    if union_unavailable:
        doc["union_unavailable"] = True
    _rewrite(doc, out_dir)

    alarm_items = ([f"{r['ticker']}({r['lag_days']}d)" for r in stale_live_records]
                   + [f"{r['ticker']}(missing)" for r in missing_records]
                   + [f"{r['ticker']}(unreadable)" for r in unreadable_records])
    if alarm_items:
        shown = alarm_items[:12]
        tail = f" +{len(alarm_items) - 12} more" if len(alarm_items) > 12 else ""
        print(f"::warning title=stocks store freshness::{len(alarm_items)} stocks store "
              f"issue(s) ({len(stale_live_records)} stale >{threshold}d, "
              f"{len(missing_records)} missing, {len(unreadable_records)} unreadable): "
              f"{', '.join(shown)}{tail} — see "
              "data/quality/stocks_freshness_audit.json", flush=True)
    print(f"[stocks_freshness] now_et={today_et} expected_session={expected} "
          f"threshold={threshold}d fresh={totals['fresh']} stale_live={totals['stale_live']} "
          f"stale_dead={totals['stale_dead']} missing={totals['missing']} "
          f"unreadable={totals['unreadable']}"
          + (" union_unavailable=True" if union_unavailable else ""))
    return doc


def _rewrite(doc: dict, out_dir: Path | None) -> None:
    """ac.write_audit() already persisted the standard shape; this re-serializes the
    SAME path with the extra fields (expected_session/totals/per-name records) this
    audit's marker doc carries beyond the shared shape."""
    out = Path(out_dir) if out_dir is not None else ac.quality_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "stocks_freshness_audit.json").write_text(json.dumps(doc, indent=1))


def exit_code(doc: dict, strict: bool) -> int:
    """0 always for data findings when not strict (flags-only law). With --strict, 3
    when any stale_live/missing/unreadable name exists. A skip (empty totals) is 0
    either way — there is nothing to alarm on."""
    if not strict:
        return 0
    t = doc.get("totals", {})
    n = int(t.get("stale_live", 0)) + int(t.get("missing", 0)) + int(t.get("unreadable", 0))
    return 3 if n else 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true",
                    help="exit 3 when any stale_live/missing/unreadable name exists "
                         "(default: always exit 0 for data findings — flags-only law)")
    ap.add_argument("--now", default=None,
                    help="ISO timestamp override for the freshness reference (tests)")
    args = ap.parse_args(argv)
    try:
        now = datetime.fromisoformat(args.now) if args.now else None
        doc = run(now=now)
    except Exception as e:  # noqa: BLE001 — an unexpected crash must still be VISIBLE (exit 2)
        log.error("stocks freshness audit crashed: %s", e)
        return 2
    return exit_code(doc, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
