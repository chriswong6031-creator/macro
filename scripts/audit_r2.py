"""R2 data-plane freshness audit (dead-man's switch for the PUBLIC data plane).

The heavy per-ticker stores (stockdata/ohlc/intraday/...) are served to the live
site from Cloudflare R2 (see scripts/publish_r2.py + templates/data_base.js), not
git/Pages. Every CI publish invocation is deliberately non-fatal (`|| ::warning::`)
and publish_r2 exits 0 when the R2_* creds are absent — so if the secrets expire or
uploads start failing, the live site keeps serving silently stale per-ticker data
forever. This audit is the tripwire.

Check: HTTP HEAD the public anchors and compare Last-Modified against now. Per
anchored dir we take the FRESHEST of `<dir>/_manifest.json` (put unconditionally on
every successful FULL publish, even no-delta days — the canonical freshness beacon;
partial lanes pass --no-manifest and leave it alone, which is why we take the
freshest of the two anchors rather than the manifest alone) and,
for the *stockdata search libraries, `<dir>/index.json` (fallback while the manifest
rollout reaches every lane; content-hash skip means index only re-uploads on change,
so it alone would false-alarm on no-delta weekends). A content-level probe parses
`asof` out of stockdata/SPY.json (the same anchor the Mastermind bot tripwires on),
catching the subtler failure where publishes run but ship an old build. Cloudflare
403s pythonish User-Agents on r2.dev, so we send a custom one.

Verdicts: STALE / DARK (no anchor object at all) / FORBIDDEN (bucket public access
broken) / CONTENT STALE are definitive server responses -> FAIL. Network-layer
errors (DNS, timeout) after retries are INDETERMINATE -> warning only, so a flaky
runner can't fake an outage. Stdlib-only on purpose: the heartbeat venv installs no
requirements.

Consumers:
  * scripts/healthcheck.py folds this into the scheduled heartbeat (telegram + red run).
  * daily.yml / asia-close.yml run `--strict --max-age-hours 2` right after their
    publish_r2 step, so a silently-failed/skipped publish reddens THAT run's summary.
Writes data/quality/r2_audit.json (observability only; read-only over data stores).

Usage: python -m scripts.audit_r2 [--strict] [--anchors stockdata,chinastockdata]
                                  [--max-age-hours 26] [--base URL]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

# Cloudflare's WAF 403s python-default User-Agents on the public r2.dev host.
UA = "macro-audit/1.0"
DEFAULT_BASE = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"
# NOTE: config.yml's r2_data_plane.anchors REPLACES this list wholesale (see run()) —
# the live heartbeat reads config, so an anchor added only here is inert. Keep both.
DEFAULT_ANCHORS = [
    "stockdata",      # US-evening lane — canonical daily freshness beacon
    "chinastockdata", # Asia-close lane — daily ~08:30 UTC
    "thetadata_eod",  # ThetaData EOD options store (~60 GB / ~13k parquets). Per
                      # ops/THETADATA_R2_SYNC_RUNBOOK.md the store "exists only on the
                      # ops Mac", so this R2 copy is its SOLE offsite backup — the
                      # highest-value object in the bucket, and until 2026-07-30 the
                      # only major store with no anchor at all (a 3-night manifest
                      # freeze went unseen until a human read the log). Published by
                      # launchd 22:00 PT daily = ~05:00 UTC; at the 14:30 UTC heartbeat
                      # a healthy manifest is ~9.5h old and the FIRST missed night reads
                      # ~33.5h, so the shared 26h budget below trips on that first miss.
                      # 7-days-a-week lane (weekend runs are md5 no-ops that still put
                      # the manifest), so the weekday-only heartbeat needs no exception.
    # hk_stocks_ext: expanded HSCI universe (~380 names) R2 store — per-ticker OHLCV.
    # Added as a named anchor (pass --anchors hk_stocks_ext to include in the heartbeat
    # once the first full backfill publish completes).  Not in DEFAULT yet: the initial
    # backfill may take several nightly runs; only stable after the _manifest.json is
    # first written by a successful --dirs hk_stocks_ext run.
    # massive_stock_day: whole-market daily OHLCV parquets (Setup-Species W0.6a).
    # Same deal — NOT in DEFAULT until the first publish from the store host lands
    # (as of 2026-07-03 the store has never been published; anchoring it now would
    # red-flag every heartbeat with DARK). Add via config r2_data_plane.anchors once
    # live; the coverage probe below then also checks its CONTENT continuity.
    # ── options planes (R0.9, Options Superintelligence masterplan 2026-07-31) ──
    # Until 2026-07-31 NO options plane had a dead-man's switch, which is exactly
    # how the chain-heat lane served an 8-day-stale artifact unnoticed and the
    # gex_history accrual grew silent holes. Each has its own age budget in
    # PER_ANCHOR_MAX_AGE_H (their cadences are nothing like the daily lanes').
    "options_hub",    # nightly hub payloads (M1 launchd 16:45 PT weekdays);
                      # anchor = oi_movers.json, put on every successful run.
    "live_flow",      # RTH poller cycles (M1 launchd, 09:25–16:05 ET weekdays);
                      # anchor = meta.json, put every cycle.
    "levels_ledger",  # pre-open sealed levels boards (M1 launchd 04:30/06:00 PT);
                      # anchor = index.json, put on every successful seal.
]
# Both lanes republish daily (daily.yml 02:00 UTC + cron lag lands ~05-10 UTC;
# asia-close 08:30 UTC), so the manifest's expected age at the 14:30 UTC heartbeat is
# ~5-9h and the FIRST missed day shows ~29-33h. 26 trips on the first miss; a ~30h
# limit can let a late-publishing run slide to day 2.
DEFAULT_MAX_AGE_H = 26.0
# Per-anchor age budgets (hours) for lanes whose cadence does not fit the shared
# daily budget. Reasoning is against the 14:30 UTC weekday heartbeat; config key
# r2_data_plane.anchor_max_age_hours overrides per name (merged over these).
#   options_hub 68h:  nightly 23:45 UTC weekdays → healthy Monday reads Friday's
#                     put at 62.75h (must NOT trip); first missed weekday nightly
#                     reads 86.75h → trips.
#   live_flow 22h:    RTH cycles → healthy heartbeat age is minutes (poller has
#                     been up ~1h at 14:30 UTC). Prior-day close (20:05 UTC) →
#                     next 14:30 UTC = 18.4h and day-after-half-day = 21.5h, both
#                     legitimately quiet — 22h clears them; a poller that never
#                     starts trips the day after (42h), a dead-over-weekend
#                     poller trips Monday (66h).
#   levels_ledger 30h: seal puts index.json ~11:30-13:00 UTC weekdays; a missed
#                     seal reads ~27h the next heartbeat → trips at 30h one day
#                     late, but 30h clears the Tuesday-after-Monday-holiday 27h
#                     no-session gap. KNOWN false positive: the Monday after a
#                     FRIDAY market holiday reads ~75h (no Friday session to
#                     seal) — ~2-3×/yr, dismiss on sight.
PER_ANCHOR_MAX_AGE_H: dict[str, float] = {
    "options_hub": 68.0,
    "live_flow": 22.0,
    "levels_ledger": 30.0,
}
ASOF_KEY = "stockdata/SPY.json"
DEFAULT_ASOF_MAX_DAYS = 6  # `asof` = last bar date: 3-day weekend + a market holiday tolerated

# Dated-accrual planes: one JSON per session at {prefix}/{root}/{YYYY-MM-DD}.json,
# written nightly with NO manifest or index to anchor on (the gex_history index is
# a known R0/R2 follow-up). Freshness = existence of two session keys: BOTH
# missing → FAIL (lane dead); exactly one missing → WARN (single-day hole /
# market holiday — the 07-18/07-20 holes were exactly this shape). `gate` ties
# the probe to an active anchor so --anchors selections behave consistently.
#
# lag_bdays: how many of the most recent weekdays to SKIP before the two checked
# days. gex_history needs 1: the hub builds from the EOD store (T-1 greeks), so
# session D's file uploads on D+1 evening (~23:45 UTC; measured 2026-07-31:
# COMPLETE asof=2026-07-30) — at the 14:30 UTC heartbeat the previous weekday's
# file is never due yet, and checking it would emit a permanent daily
# hole-warning (noise-trained warnings are how the 8-day chain-heat staleness
# slipped by).
ACCRUAL_ANCHORS: list[dict] = [
    {"name": "gex_history", "prefix": "options_hub/gex_history", "root": "SPY",
     "gate": "options_hub", "lag_bdays": 1},
]

# Data-dir stores whose publish-side manifest embeds the collector's own manifest under
# "store" (see publish_r2) — carrying coverage/anchor blocks this audit can content-check.
# Probed only when the dir is ALSO in the active anchors list. 2026-07-03 lesson
# (massive_stock_day): a manifest can be FRESH while the store misses 110 days of
# content — Last-Modified freshness alone cannot see that.
#
# thetadata_eod is deliberately NOT here (2026-07-30). Its collector manifest
# (backfill_thetadata_eod._write_manifest) emits store/n_roots/per_root/updated_at and
# NO coverage, anchor or latest_date block, so the probe could only ever emit the
# "no store coverage yet" warning — a permanent nag with zero signal, which is how
# warnings get trained into noise. Its freshness anchor above is live either way.
# To make a coverage probe meaningful here, _write_manifest must first emit the blocks
# (per-root year continuity is the natural coverage unit for a per-root/per-year store);
# `updated_at` is also an unused remote-visible view of collector — not publisher —
# health. Both are follow-ups, not preconditions for the freshness tripwire.
COVERAGE_ANCHORS = ["massive_stock_day", "hk_stocks_ext"]
DEFAULT_COVERAGE_MAX_RUN_BDAYS = 5   # store-reported longest missing-weekday run tolerated
DEFAULT_COVERAGE_MAX_AGE_DAYS = 6    # newest store content older than this = content-stale


def _fetch(url: str, method: str = "HEAD", timeout: float = 20.0):
    """(status, headers-dict, body-bytes|None). HTTP error statuses are RETURNED
    (definitive server responses); network-layer failures raise OSError upward."""
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 — fixed https base
            return r.status, dict(r.headers), (r.read() if method == "GET" else None)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), None


def _try(fetch, url: str, retries: int, method: str = "HEAD"):
    last: OSError | None = None
    for i in range(retries + 1):
        try:
            return fetch(url, method=method)
        except OSError as e:  # URLError + socket timeouts — indeterminate, retry
            last = e
            if i < retries:
                time.sleep(1.5 * (i + 1))
    raise last  # type: ignore[misc]


# Options-plane lanes publish per-cycle/per-run artifacts directly (no publish_r2
# manifest), so each anchors on its always-rewritten beacon object instead.
_DIR_CANDIDATES = {
    "options_hub":   ["options_hub/oi_movers.json"],
    "live_flow":     ["live_flow/meta.json"],
    "levels_ledger": ["levels_ledger/index.json"],
}


def _candidates(d: str) -> list[str]:
    # index.json exists only in the *stockdata search libraries; the OHLC trees are
    # per-ticker files + manifest only.
    if d in _DIR_CANDIDATES:
        return list(_DIR_CANDIDATES[d])
    keys = [f"{d}/_manifest.json"]
    if d.endswith("stockdata"):
        keys.append(f"{d}/index.json")
    return keys


def probe(now: datetime, base: str = DEFAULT_BASE, anchors: list[str] | None = None,
          max_age_hours: float = DEFAULT_MAX_AGE_H, asof_key: str | None = ASOF_KEY,
          asof_max_days: int = DEFAULT_ASOF_MAX_DAYS, fetch=_fetch, retries: int = 2,
          coverage_anchors: list[str] | None = None,
          coverage_max_run_bdays: int = DEFAULT_COVERAGE_MAX_RUN_BDAYS,
          coverage_max_age_days: int = DEFAULT_COVERAGE_MAX_AGE_DAYS,
          anchor_max_age: dict[str, float] | None = None,
          accrual_anchors: list[dict] | None = None) -> dict:
    """Pure evaluation -> {ok, fail_reasons, warnings, anchors}. `fetch` injectable for tests."""
    base = base.rstrip("/")
    anchors = list(anchors or DEFAULT_ANCHORS)
    per_anchor = dict(PER_ANCHOR_MAX_AGE_H)
    per_anchor.update(anchor_max_age or {})
    fail: list[str] = []
    warn: list[str] = []
    detail: dict[str, dict] = {}

    for d in anchors:
        best: tuple[datetime, str] | None = None
        notes: list[str] = []
        indeterminate = hard_failed = False
        for key in _candidates(d):
            try:
                st, hdrs, _ = _try(fetch, f"{base}/{key}", retries)
            except OSError as e:
                indeterminate = True
                notes.append(f"{key}: unreachable ({e})")
                continue
            if st == 200:
                lm = hdrs.get("Last-Modified") or hdrs.get("last-modified")
                if not lm:
                    notes.append(f"{key}: 200 but no Last-Modified")
                    continue
                try:
                    dt = parsedate_to_datetime(lm)
                except (TypeError, ValueError):
                    notes.append(f"{key}: unparseable Last-Modified {lm!r}")
                    continue
                if best is None or dt > best[0]:
                    best = (dt, key)
            elif st in (401, 403):
                hard_failed = True
                fail.append(f"R2 FORBIDDEN: {key} HTTP {st} — public bucket access broken "
                            "(the browser data_base.js fetches fail the same way)")
            else:
                notes.append(f"{key}: HTTP {st}")
        if best is not None:
            limit_h = per_anchor.get(d, max_age_hours)
            age_h = (now - best[0]).total_seconds() / 3600.0
            detail[d] = {"anchor": best[1], "last_modified": best[0].isoformat(),
                         "age_hours": round(age_h, 1)}
            if age_h > limit_h:
                fail.append(f"R2 STALE: {d} last published {age_h:.1f}h ago "
                            f"(limit {limit_h:g}h; anchor {best[1]}) — the live site is "
                            "serving stale per-ticker data")
        elif indeterminate:
            warn.append(f"R2 UNREACHABLE: {d} anchors could not be checked ({'; '.join(notes)}) — "
                        "network-layer, not treated as an outage")
        elif not hard_failed:
            fail.append(f"R2 DARK: {d} has no anchor object ({'; '.join(notes)}) — "
                        "data plane never published or bucket wiped")

    # Content-level probe: manifest freshness proves a publish RAN, not that it shipped
    # today's build (e.g. a partial sync from another lane keeps the manifest warm).
    if asof_key and asof_key.split("/")[0] in anchors:
        try:
            st, _, body = _try(fetch, f"{base}/{asof_key}", retries, method="GET")
            if st == 200 and body:
                asof = json.loads(body).get("asof")
                age_d = (now.date() - date.fromisoformat(str(asof))).days
                detail[asof_key] = {"asof": asof, "age_days": age_d}
                if age_d > asof_max_days:
                    fail.append(f"R2 CONTENT STALE: {asof_key} asof={asof} is {age_d}d old "
                                f"(limit {asof_max_days}d) — publishes may be running but "
                                "shipping an old build")
            elif st in (401, 403, 404):
                fail.append(f"R2 CONTENT PROBE: {asof_key} HTTP {st} — must-exist anchor missing")
            else:
                warn.append(f"asof probe {asof_key}: HTTP {st}")
        except OSError as e:
            warn.append(f"asof probe {asof_key}: unreachable ({e})")
        except (ValueError, KeyError, TypeError) as e:
            warn.append(f"asof probe {asof_key}: unparseable ({e!r})")

    # Content-level COVERAGE probe for data-dir stores: freshness (above) proves a
    # publish ran; the embedded store manifest proves the content is CONTINUOUS. A
    # store can be freshly published yet miss months of interior days — the
    # 2026-07-03 massive_stock_day incident — and only this check can see it.
    for d in (coverage_anchors if coverage_anchors is not None else COVERAGE_ANCHORS):
        if d not in anchors:
            continue
        try:
            st, _, body = _try(fetch, f"{base}/{d}/_manifest.json", retries, method="GET")
        except OSError as e:
            warn.append(f"coverage probe {d}: unreachable ({e})")
            continue
        if st != 200 or not body:
            # anchor-existence failures are already handled by the freshness loop
            warn.append(f"coverage probe {d}: HTTP {st}")
            continue
        try:
            doc = json.loads(body)
        except ValueError as e:
            warn.append(f"coverage probe {d}: unparseable ({e!r})")
            continue
        # The probe reads the PUBLISH-side doc, whose "store" block is the embedded
        # collector manifest. Every data-dir collector also writes a LOCAL _manifest.json
        # whose own top-level "store" is the store NAME — a plain string. When that raw
        # doc ends up at the publish-side key (publish_r2 uploaded it in the delta pass
        # until the _uploadable fix), `store.get(...)` raised AttributeError, which is
        # caught by neither except above. healthcheck.check_r2_freshness swallows any
        # exception from run() into {"ok": True}, so that crash would not have been a
        # loud failure — it would have silently voided the WHOLE R2 tripwire, every
        # anchor included. Shape-check before dereferencing; warn, never raise.
        if not isinstance(doc, dict):
            warn.append(f"coverage probe {d}: manifest is a JSON {type(doc).__name__}, "
                        "not an object — content continuity unverifiable")
            continue
        store = doc.get("store")
        if store is not None and not isinstance(store, dict):
            # `store` present but scalar == the RAW collector doc, whose own top-level
            # "store" is the store NAME. Distinct from `store` merely ABSENT, which is a
            # legitimate pre-coverage publisher doc and falls through to the softer
            # warning below.
            warn.append(f"coverage probe {d}: manifest \"store\" is a "
                        f"{type(store).__name__}, not a dict — the RAW collector manifest "
                        "is sitting at the publish-side key; content continuity "
                        "unverifiable")
            continue
        store = store or {}
        cov = store.get("coverage")
        anchor_blk = store.get("anchor")
        cov = cov if isinstance(cov, dict) else {}
        anchor_blk = anchor_blk if isinstance(anchor_blk, dict) else {}
        if not cov and not anchor_blk:
            warn.append(f"coverage probe {d}: manifest carries no store coverage yet "
                        "(pre-coverage publish?) — content continuity unverifiable")
            continue
        run_bd = cov.get("max_missing_run_weekdays")
        latest = anchor_blk.get("last") or store.get("latest_date") or cov.get("last_day")
        rec: dict = {}
        if run_bd is not None:
            try:
                run_bd = int(run_bd)
            except (TypeError, ValueError):
                warn.append(f"coverage probe {d}: bad max_missing_run_weekdays {run_bd!r}")
            else:
                rec["max_missing_run_weekdays"] = run_bd
                if run_bd > coverage_max_run_bdays:
                    fail.append(f"R2 COVERAGE HOLE: {d} reports a {run_bd}-business-day "
                                f"missing run (limit {coverage_max_run_bdays}) — the "
                                "published store has an interior content gap")
        if latest:
            try:
                age_d = (now.date() - date.fromisoformat(str(latest))).days
            except ValueError:
                warn.append(f"coverage probe {d}: bad latest date {latest!r}")
            else:
                rec.update({"latest": str(latest), "age_days": age_d})
                if age_d > coverage_max_age_days:
                    fail.append(f"R2 CONTENT STALE: {d} newest content {latest} is "
                                f"{age_d}d old (limit {coverage_max_age_days}d) — "
                                "publishes may be running but shipping old data")
        if rec:
            detail[f"{d}/coverage"] = rec

    # Dated-accrual probe: planes that write one JSON per session with no
    # manifest/index (see ACCRUAL_ANCHORS). Existence of the last two completed
    # weekdays' keys is the freshness signal — a manifest-style Last-Modified
    # does not exist for these.
    for acc in (accrual_anchors if accrual_anchors is not None else ACCRUAL_ANCHORS):
        gate = acc.get("gate")
        if gate and gate not in anchors:
            continue
        prefix = acc["prefix"]
        root_sym = acc.get("root", "SPY")
        lag = int(acc.get("lag_bdays", 0))
        days: list[date] = []
        dd = now.date()
        skipped = 0
        while len(days) < 2:
            dd -= timedelta(days=1)
            if dd.weekday() >= 5:
                continue
            if skipped < lag:
                skipped += 1
                continue
            days.append(dd)
        missing: list[str] = []
        acc_notes: list[str] = []
        indeterminate = False
        for day_ in days:
            key = f"{prefix}/{root_sym}/{day_.isoformat()}.json"
            try:
                st, _, _ = _try(fetch, f"{base}/{key}", retries)
            except OSError as e:
                indeterminate = True
                acc_notes.append(f"{key}: unreachable ({e})")
                continue
            if st != 200:
                missing.append(key)
                acc_notes.append(f"{key}: HTTP {st}")
        detail[f"{prefix}/accrual"] = {
            "checked": [day_.isoformat() for day_ in days],
            "missing": [k.rsplit("/", 1)[-1] for k in missing],
        }
        if indeterminate:
            warn.append(f"R2 ACCRUAL UNREACHABLE: {prefix} could not be checked "
                        f"({'; '.join(acc_notes)}) — network-layer, not treated as an outage")
        elif len(missing) == len(days):
            fail.append(f"R2 ACCRUAL DEAD: {prefix} has no {root_sym} file for the last "
                        f"{len(days)} weekdays ({'; '.join(acc_notes)}) — the accrual "
                        "lane has stopped writing")
        elif missing:
            warn.append(f"R2 ACCRUAL HOLE: {prefix} missing {missing[0]} — single-day "
                        "hole (market holiday, or a gap needing self-heal)")

    return {"ok": not fail, "fail_reasons": fail, "warnings": warn, "anchors": detail}


def run(now: datetime | None = None, anchors: list[str] | None = None,
        max_age_hours: float | None = None, base: str | None = None) -> dict:
    """Config-aware probe + persist data/quality/r2_audit.json. CLI args > config > defaults."""
    now = now or datetime.now(timezone.utc)
    cfg = (config.load().get("r2_data_plane", {}) or {})
    report = probe(
        now,
        base=base or cfg.get("public_base", DEFAULT_BASE),
        anchors=anchors or cfg.get("anchors") or DEFAULT_ANCHORS,
        max_age_hours=max_age_hours if max_age_hours is not None
        else float(cfg.get("max_age_hours", DEFAULT_MAX_AGE_H)),
        asof_max_days=int(cfg.get("asof_max_days", DEFAULT_ASOF_MAX_DAYS)),
        coverage_anchors=cfg.get("coverage_anchors"),
        coverage_max_run_bdays=int(cfg.get("coverage_max_run_bdays",
                                           DEFAULT_COVERAGE_MAX_RUN_BDAYS)),
        coverage_max_age_days=int(cfg.get("coverage_max_age_days",
                                          DEFAULT_COVERAGE_MAX_AGE_DAYS)),
        anchor_max_age=cfg.get("anchor_max_age_hours"),
        accrual_anchors=cfg.get("accrual_anchors"),
    )
    out_dir = config.data_dir() / "quality"
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = {"audit": "r2_data_plane", "generated_utc": now.isoformat(), **report}
    (out_dir / "r2_audit.json").write_text(json.dumps(doc, indent=1))
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--anchors", default=None,
                    help="comma-separated site/ dirs to anchor on (default: config or "
                         + ",".join(DEFAULT_ANCHORS))
    ap.add_argument("--max-age-hours", type=float, default=None)
    ap.add_argument("--base", default=None, help="public R2 base URL override")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 on STALE/DARK/FORBIDDEN (default: report-only)")
    a = ap.parse_args()
    anchors = [d.strip() for d in a.anchors.split(",") if d.strip()] if a.anchors else None
    report = run(anchors=anchors, max_age_hours=a.max_age_hours, base=a.base)
    for name, rec in report["anchors"].items():
        print(f"{name}: {rec}")
    for w in report["warnings"]:
        print(f"::warning::{w}")
    if report["ok"]:
        print("R2 data plane OK")
        return 0
    for f in report["fail_reasons"]:
        print(f"::error::{f}")
    return 1 if a.strict else 0


if __name__ == "__main__":
    raise SystemExit(main())
