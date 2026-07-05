"""Signal-sanity tripwire — the CORRECTNESS dead-man's switch (run after the daily build).

Liveness (``scripts/healthcheck.py``) catches "the pipeline stopped". This catches "the
pipeline ran and published wrong numbers" — the silent-breakage class that propagates to BOTH
the Flagship book and the Autonomous Brain because they select from the same boards.

It reads the freshly built per-ticker boards under ``site/`` (us_standouts, briefing, radar,
alt-data, news, intel-hub), evaluates the invariants in ``engine/signal_sanity.py`` (coverage /
degeneracy / content-freeze / staleness / drift) against a rolling per-vintage baseline, writes a
machine report (``data/signal_sanity/signal_sanity.json``) + a human report
(``reports/signal-sanity.md``), updates the baseline, and EXITS NON-ZERO on a tripped invariant —
so a daily.yml step placed before "commit engine outputs" prevents bad numbers from publishing.
On failure it best-effort pings Telegram/Discord (reusing scripts.notify), exactly like the
heartbeat.

Run:  python -m scripts.signal_sanity            (writes baseline + reports, exits 0/1)
      python -m scripts.signal_sanity --dry-run  (evaluate only; no baseline/report writes)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from engine import signal_sanity as ss  # noqa: E402

log = logging.getLogger("signal_sanity")

_DEFAULT_BASELINE = "signal_sanity/baseline.jsonl"
_MACHINE_REPORT = "signal_sanity/signal_sanity.json"
_HUMAN_REPORT = "signal-sanity.md"
_BASELINE_CAP = 4000   # bound the rolling file (≈ 6 surfaces × ~650 vintages)


# ---------------------------------------------------------------------------
# baseline persistence (rolling, idempotent per (surface, as_of) vintage)
# ---------------------------------------------------------------------------

def _baseline_path(cfg: dict) -> Path:
    rel = (cfg.get("baseline_file") or _DEFAULT_BASELINE)
    return config.data_dir() / rel


def _load_baseline(path: Path) -> list:
    rows: list = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001 — a bad line never sinks the check
            continue
    return rows


def _select_prior(rows: list, surface: str, today_as_of) -> "dict | None":
    """The previous DATA vintage for ``surface`` — the correct comparand for freeze/drift (a
    same-day rerun shares as_of and is skipped). Keyed on as_of (the data date) primary so a late
    replay/backfill carrying an OLD as_of but a NEW run_date cannot become the comparand; run_date
    only breaks ties between corrections of the same vintage."""
    cand = [r for r in rows if r.get("surface") == surface and r.get("as_of") != today_as_of]
    if not cand:
        return None
    return max(cand, key=lambda r: (r.get("as_of") or "", r.get("run_date") or ""))


def _update_baseline(path: Path, rows: list, new_rows: list) -> None:
    """Append today's rows, replacing any existing row with the same (surface, as_of)."""
    today_keys = {(r["surface"], r.get("as_of")) for r in new_rows}
    kept = [r for r in rows if (r.get("surface"), r.get("as_of")) not in today_keys]
    out = (kept + new_rows)[-_BASELINE_CAP:]
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, default=str, ensure_ascii=False) for r in out) + "\n"
    # atomic write — a CI cancel/timeout mid-write must never truncate the rolling baseline to 0
    # bytes (which would silently blind freeze+drift on the next run). Mirrors engine/ticker_alerts.
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# reports
# ---------------------------------------------------------------------------

def _render_md(report: dict, now: datetime) -> str:
    L = [f"# Signal sanity — {now.date().isoformat()}", "",
         f"**{'✅ OK' if report['ok'] else '🚨 FAIL'}** · "
         f"{len(report['fail_reasons'])} failure(s), {len(report['warnings'])} warning(s)", "",
         "| board | as_of | records | coverage | status |",
         "|---|---|---:|---:|---|"]
    for k, v in report["surfaces"].items():
        status = "🚨 fail" if v["fails"] else ("⚠️ warn" if v["warns"] else "ok")
        L.append(f"| {k} ({v['label']}) | {v['as_of'] or '—'} | {v['n']} | {v['coverage']} | {status} |")
    if report["fail_reasons"]:
        L += ["", "## Failures (these block publish)", ""] + [f"- {r}" for r in report["fail_reasons"]]
    if report["warnings"]:
        L += ["", "## Warnings", ""] + [f"- {w}" for w in report["warnings"]]
    L += ["", "_Invariants: coverage floor · score-column degeneracy · content-freeze (as_of "
          "advanced but values identical) · staleness · distribution drift. "
          "Ground-truth-free — see engine/signal_sanity.py._"]
    return "\n".join(L)


def _write_reports(report: dict, now: datetime) -> None:
    try:
        mp = config.data_dir() / _MACHINE_REPORT
        mp.parent.mkdir(parents=True, exist_ok=True)
        mp.write_text(json.dumps(report, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
    except Exception as e:  # noqa: BLE001 — a write failure must never crash the check
        log.warning("signal_sanity: machine report write failed: %r", e)
    try:
        rp = config.ROOT / config.load()["storage"]["reports_dir"] / _HUMAN_REPORT
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text(_render_md(report, now), encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        log.warning("signal_sanity: human report write failed: %r", e)


def _notify(report: dict) -> None:
    """Best-effort outbound alert via the W6b push spine.
    The non-zero exit is the primary signal; push_ops_alert() dispatches raw
    even when alert_push.enabled=false (dedup/ledger skipped, transport fires).
    W6b: replaces the former direct send_telegram/send_discord call."""
    msg = "🚨 signal-sanity tripwire FAILED — " + "; ".join(report["fail_reasons"][:6])
    try:
        from engine.alert_triage import push_ops_alert  # noqa: PLC0415
        push_ops_alert(
            source="signal_sanity",
            type_="tripwire_failed",
            message=msg,
            severity="critical",
            lane="signal_sanity",
        )
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# entrypoint
# ---------------------------------------------------------------------------

def run(*, now: "datetime | None" = None, site_dir=None, dry_run: bool = False) -> dict:
    """Evaluate every board against the rolling baseline; persist (unless dry_run). Pure of
    sys.exit so it stays callable/testable; main() owns the process exit code."""
    cfg = (config.load().get("signal_sanity", {}) or {})
    now = now or datetime.now(timezone.utc)
    site_dir = Path(site_dir) if site_dir else (config.ROOT / config.load()["storage"]["site_dir"])

    payloads = ss.load_payloads(site_dir)
    bpath = _baseline_path(cfg)
    rows = _load_baseline(bpath)
    prior = {}
    for s in ss.SURFACES:
        doc = payloads.get(s.key) or {}
        prior[s.key] = _select_prior(rows, s.key, doc.get(s.as_of_key))

    report = ss.evaluate_all(payloads, prior, now=now, cfg=cfg)

    if not dry_run:
        _write_reports(report, now)
        try:
            _update_baseline(bpath, rows, ss.baseline_rows(report))
        except Exception as e:  # noqa: BLE001
            log.warning("signal_sanity: baseline update failed: %r", e)
    return report


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description="Signal-sanity correctness tripwire over the engine's boards.")
    ap.add_argument("--dry-run", action="store_true", help="evaluate only; do not write baseline/reports")
    ap.add_argument("--site", default=None, help="override the site/ directory (for testing)")
    args = ap.parse_args(argv)

    now = datetime.now(timezone.utc)
    report = run(now=now, site_dir=args.site, dry_run=args.dry_run)

    print(ss.summary_line(report))
    for w in report["warnings"]:
        print(f"::warning::{w}")
    if report["ok"]:
        print("signal sanity OK")
        return 0
    for r in report["fail_reasons"]:
        print(f"::error::{r}")
    if not args.dry_run:
        _notify(report)
    return 1


if __name__ == "__main__":
    sys.exit(main())
