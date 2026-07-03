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
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

# Cloudflare's WAF 403s python-default User-Agents on the public r2.dev host.
UA = "macro-audit/1.0"
DEFAULT_BASE = "https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev"
DEFAULT_ANCHORS = [
    "stockdata",      # US-evening lane — canonical daily freshness beacon
    "chinastockdata", # Asia-close lane — daily ~08:30 UTC
    # hk_stocks_ext: expanded HSCI universe (~380 names) R2 store — per-ticker OHLCV.
    # Added as a named anchor (pass --anchors hk_stocks_ext to include in the heartbeat
    # once the first full backfill publish completes).  Not in DEFAULT yet: the initial
    # backfill may take several nightly runs; only stable after the _manifest.json is
    # first written by a successful --dirs hk_stocks_ext run.
]
# Both lanes republish daily (daily.yml 02:00 UTC + cron lag lands ~05-10 UTC;
# asia-close 08:30 UTC), so the manifest's expected age at the 14:30 UTC heartbeat is
# ~5-9h and the FIRST missed day shows ~29-33h. 26 trips on the first miss; a ~30h
# limit can let a late-publishing run slide to day 2.
DEFAULT_MAX_AGE_H = 26.0
ASOF_KEY = "stockdata/SPY.json"
DEFAULT_ASOF_MAX_DAYS = 6  # `asof` = last bar date: 3-day weekend + a market holiday tolerated


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


def _candidates(d: str) -> list[str]:
    # index.json exists only in the *stockdata search libraries; the OHLC trees are
    # per-ticker files + manifest only.
    keys = [f"{d}/_manifest.json"]
    if d.endswith("stockdata"):
        keys.append(f"{d}/index.json")
    return keys


def probe(now: datetime, base: str = DEFAULT_BASE, anchors: list[str] | None = None,
          max_age_hours: float = DEFAULT_MAX_AGE_H, asof_key: str | None = ASOF_KEY,
          asof_max_days: int = DEFAULT_ASOF_MAX_DAYS, fetch=_fetch, retries: int = 2) -> dict:
    """Pure evaluation -> {ok, fail_reasons, warnings, anchors}. `fetch` injectable for tests."""
    base = base.rstrip("/")
    anchors = list(anchors or DEFAULT_ANCHORS)
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
            age_h = (now - best[0]).total_seconds() / 3600.0
            detail[d] = {"anchor": best[1], "last_modified": best[0].isoformat(),
                         "age_hours": round(age_h, 1)}
            if age_h > max_age_hours:
                fail.append(f"R2 STALE: {d} last published {age_h:.1f}h ago "
                            f"(limit {max_age_hours:g}h; anchor {best[1]}) — the live site is "
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
