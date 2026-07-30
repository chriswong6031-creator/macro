"""scripts/x_intel_harvest.py — the E3 competitive-intelligence run.

ONE run, four ordered actions:

    1. HARVEST   — one twitterapi.io ``last_tweets`` call per roster account,
                   inside the committed monthly call/USD cap. Retweets are
                   dropped, HTML entities unescaped, format tags computed
                   deterministically. Rows APPEND to
                   ``data/marketing/x_intel/corpus.jsonl``.
    2. ANALYSE   — per-shape / per-register / per-account engagement tables,
                   shape distribution vs our own quotas, precision rates, and a
                   week-over-week diff against the previous ``report.json``.
    3. PROPOSE   — top-interaction-rate posts per register into the exemplar
                   store's PENDING pool. NOT promoted, NOT activated.
    4. WRITE     — ``report.json`` + ``WEEKLY_REPORT.md`` + ``state.json``
                   (+ ``exemplar_store.json`` when candidates changed).

**DARK BY DEFAULT.** With ``TWITTERAPI_IO_KEY`` unset the harvest makes zero
network calls, spends nothing, and re-analyses whatever corpus is already on
disk. That is what the weekly workflow does until the secret is present, and it
is also what ``--dry-run`` forces regardless of the key.

**IT CANNOT PROMOTE.** Step 3 fills a pending pool and stops. Minting an
exemplar version is an operator act (``--promote`` below, or
``exemplar_store.promote_pending`` from the admin), and ACTIVATING one is a
second operator act (a config edit pinning
``intel.exemplar_store.active_version``). Neither can happen on a schedule.

**TWO CADENCES, ONE CAP.** The weekly deep pass runs all four actions over the
whole roster. The DAILY LIGHT PASS (``--light``) runs step 1 only, over the
roster entries marked ``tier: daily`` (at most ``intel.light_max_handles``), and
stops: corpus appended, spend persisted, no tables and no candidate proposal.
This is the pass the monthly cap was always sized for and that nothing spent
until #3960 -- the budget arithmetic in ``x_intel.DEFAULTS`` reads "+ a daily
light pass on the 5 fastest desks (5 x 30) = 150 calls". NEITHER CAP MOVED to
add it, and the $5 intel carve of the shared $75 twitterapi.io bucket is
untouched.

**NO BILLED REQUEST WITHOUT A LANDING PUSH.** ``state.json`` carries the monthly
call and USD counters, so a run that spends and then fails to push forgets what
it spent, and the next pass reads $0.00 against the cap. A ``git push --dry-run``
probe runs BEFORE the first billed request (the press wire's rule, imported
rather than re-implemented); on failure the billed harvest stands down and the
free analysis of the committed corpus still runs.

Usage:
    # the weekly workflow's invocation (dark without the secret)
    python -m scripts.x_intel_harvest

    # the daily workflow's invocation: the `tier: daily` desks, corpus only
    python -m scripts.x_intel_harvest --light

    # analyse the committed corpus, make zero calls
    python -m scripts.x_intel_harvest --dry-run

    # re-run tables only, no harvest at all
    python -m scripts.x_intel_harvest --analyze-only

    # a subset of the roster
    python -m scripts.x_intel_harvest --handles DeItaone,unusual_whales

    # OPERATOR: mint a version from the pending pool (never run by CI)
    python -m scripts.x_intel_harvest --promote "wave 1 wire exemplars" \\
        --ratified-by chris
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

_CODE_ROOT = str(Path(__file__).resolve().parent.parent)
if _CODE_ROOT not in sys.path:  # pragma: no cover - import bootstrap
    sys.path.insert(0, _CODE_ROOT)

from engine.marketing import exemplar_store as xs  # noqa: E402
from engine.marketing import x_intel as xi  # noqa: E402

log = logging.getLogger("x_intel_harvest")


def _load_cfg(root: Path) -> dict:
    """config/marketing.yml, fail-soft. An unreadable config yields {} and the
    module defaults, which are safe (the roster is then empty → zero calls)."""
    path = root / "config" / "marketing.yml"
    try:
        import yaml  # noqa: PLC0415

        blob = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        print(
            f"::warning title=x-intel::cannot read {path} ({exc}) — running on "
            f"module defaults, which carry an EMPTY roster (zero calls)",
            flush=True,
        )
        return {}
    return blob if isinstance(blob, dict) else {}


def _push_access_ok(root: Path) -> tuple[bool, str]:
    """Would a push from this checkout be accepted right now? (ok, detail).

    SINGLE-SOURCED from the press wire, which argued this out first: the probe is
    a throwaway-ref ``git push --dry-run``, transfers nothing, and reads "cannot
    push" for git-missing / no-remote / hung, which is the conservative
    direction. Imported lazily so this module's import cost is unchanged and a
    refactor over there cannot silently re-implement the rule here.
    """
    try:
        from scripts.marketing_press_wire import push_access_ok  # noqa: PLC0415

        return push_access_ok(root)
    except Exception as exc:  # noqa: BLE001
        return False, f"probe unavailable ({type(exc).__name__}: {exc})"


def _emit_report(report_out: dict, json_out: str) -> None:
    """Print the run report, and copy it to --json-out as PURE JSON.

    stdout carries ::warning/::notice lines interleaved with the report, so a
    consumer that PARSES the report (the workflow's job summary) must read the
    file, never a tee of the stream.
    """
    blob = json.dumps(report_out, indent=2, ensure_ascii=False, default=str)
    if json_out:
        try:
            Path(json_out).write_text(blob + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 — a receipt file never fails a run
            print(f"::warning title=x-intel::--json-out write to {json_out} "
                  f"failed ({exc}) — the report is still on stdout", flush=True)
    print(blob)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="E3 X competitive-intelligence harvest")
    ap.add_argument("--root", default=None,
                    help="repo root (defaults to this checkout)")
    ap.add_argument("--dry-run", action="store_true",
                    help="make ZERO network calls and spend nothing; still "
                         "re-analyses the committed corpus")
    ap.add_argument("--analyze-only", action="store_true",
                    help="skip the harvest entirely; tables + report only")
    ap.add_argument("--light", action="store_true",
                    help="DAILY LIGHT PASS: poll only the roster entries marked "
                         "`tier: daily` (at most intel.light_max_handles), append "
                         "the corpus, persist spend, and STOP. No tables, no "
                         "report rewrite, no candidate proposal — the weekly deep "
                         "pass owns those. Spends from the same committed monthly "
                         "cap; raises no carve.")
    ap.add_argument("--handles", default="",
                    help="comma-separated subset of the roster to poll")
    ap.add_argument("--no-candidates", action="store_true",
                    help="skip the exemplar-candidate proposal step")
    ap.add_argument("--json-out", default="", dest="json_out",
                    help="also write the run report to this path as PURE JSON. "
                         "stdout carries ::warning/::notice annotations mixed with "
                         "the report, so a consumer that parses the report (the "
                         "workflow's job summary) must read this file, never a "
                         "tee of the stream.")
    ap.add_argument("--promote", default="",
                    help="OPERATOR ONLY — mint an exemplar version from the "
                         "pending pool with this note. Requires --ratified-by.")
    ap.add_argument("--ratified-by", default="",
                    help="who ratified the promotion (required with --promote)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)
    root = Path(args.root) if args.root else Path(_CODE_ROOT)
    now = datetime.now(tz=timezone.utc)
    cfg = _load_cfg(root)
    conf = xi.resolve_cfg(cfg)

    report_out: dict = {
        "as_of": xi.iso_stamp(now),
        "root": str(root),
        "dry_run": bool(args.dry_run),
    }

    # ── OPERATOR PATH: promote, then stop. Deliberately exclusive of the
    # harvest so a scheduled run can never reach it even by argument accident.
    if args.promote:
        who = str(args.ratified_by or "").strip()
        if not who:
            print("::error title=x-intel-exemplars::--promote requires "
                  "--ratified-by <name>: an unattributed ratification is "
                  "indistinguishable from an automatic one", flush=True)
            return 2
        result = xs.promote_pending(args.promote, ratified_by=who, root=root,
                                    cfg=cfg, now=now)
        result.pop("store", None)
        print(json.dumps({"promote": result}, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    # ── 1. HARVEST ────────────────────────────────────────────────────────
    state = xi.load_state(root)
    rows_written = 0
    if args.analyze_only:
        report_out["harvest"] = {"skipped": "analyze_only"}
    else:
        entries = xi.roster(cfg)
        if args.light:
            tier = str(conf.get("light_tier") or "daily").strip().lower()
            cap = max(0, int(conf.get("light_max_handles") or 0))
            entries = [e for e in entries
                       if str(e.get("tier") or "").strip().lower() == tier][:cap]
            report_out["light"] = {"tier": tier, "max_handles": cap,
                                   "handles": [e["handle"] for e in entries]}
            if not entries:
                # FAIL CLOSED ON THE BUDGET: an empty selection polls NOTHING.
                # Falling back to the full roster would turn a 5-call daily pass
                # into a 17-call one on a config typo, 30 times a month.
                print(f"::warning title=x-intel::--light found no roster entry "
                      f"with tier={tier!r} — polling nothing this pass. Mark the "
                      f"daily desks in config/marketing.yml intel.roster.",
                      flush=True)
        if args.handles:
            want = {h.strip().lstrip("@").lower() for h in args.handles.split(",") if h.strip()}
            entries = [e for e in entries if e["handle"].lower() in want]
            missing = want - {e["handle"].lower() for e in entries}
            if missing:
                print(f"::warning title=x-intel::--handles named {sorted(missing)}, "
                      f"which are not in intel.roster — skipped", flush=True)
        # ── PUSH-PROBE FAIL-CLOSED (press-wire blocker 2, same money, same
        # shape). state.json carries the monthly call and USD counters, so a run
        # whose push never lands spends AND forgets: the next pass reads $0.00
        # and the cap can never fire. That was a tolerable weekly risk and is not
        # a tolerable daily one. A `git push --dry-run` answers "would a write be
        # accepted right now" before any money moves; on failure the BILLED work
        # stands down and the free work (analysis of the committed corpus) still
        # runs, exactly like the wire lane.
        offline = bool(args.dry_run)
        if not offline and entries:
            pushable, why = _push_access_ok(root)
            if not pushable:
                print(f"::warning title=x-intel::push access probe FAILED ({why}) "
                      f"— standing the billed harvest down. state.json carries the "
                      f"monthly cap counters, so spending without a landing push "
                      f"would make the cap invisible to the next run. The corpus "
                      f"analysis below still runs.", flush=True)
                report_out["push_probe"] = {"ok": False, "detail": why}
                offline = True
            else:
                report_out["push_probe"] = {"ok": True, "detail": why}
        harvester = xi.Harvester(cfg)
        if args.light and entries:
            # One call per daily desk, never more, whatever max_calls_per_run says.
            harvester.max_calls_per_run = min(harvester.max_calls_per_run,
                                              len(entries))
        summary = harvester.run(state=state, now=now, handles=entries,
                                offline=offline)
        rows = summary.pop("rows", [])
        if rows and not args.dry_run:
            rows_written = xi.append_corpus(rows, root=root)
        summary["rows_harvested"] = len(rows)
        summary["rows_written"] = rows_written
        report_out["harvest"] = summary
        # PERSIST THE COUNTER ONLY WHEN WE SPENT. A dark run (no secret) that
        # rewrote state.json would put a fresh `last_run` timestamp on main every
        # single week for a run that did nothing — weekly commit noise, and it
        # would falsify the workflow's own claim that a dark run's diff is empty.
        # The run receipt lives in the job summary, which is where it belongs.
        if not args.dry_run and summary.get("calls", 0) > 0:
            xi.save_state(state, root, now=now)

    # ── THE LIGHT PASS STOPS HERE ─────────────────────────────────────────
    # Corpus in, spend persisted, done. Tables, WEEKLY_REPORT.md and the
    # exemplar pending pool belong to the Sunday deep pass: re-rendering a file
    # named WEEKLY_REPORT.md thirty times a month is churn on a tracked artifact
    # and a lie about its own cadence.
    if args.light:
        report_out["skipped"] = "light pass: analysis + candidates are weekly"
        report_out["budget"] = xi.month_bucket(xi.load_state(root), now)
        report_out["budget"]["call_cap"] = conf.get("monthly_call_cap")
        report_out["budget"]["usd_cap"] = conf.get("monthly_usd_cap")
        _emit_report(report_out, args.json_out)
        return 0

    # ── 2. ANALYSE ────────────────────────────────────────────────────────
    corpus = xi.load_corpus(root)
    prior = xi.load_report(root)
    report = xi.analyze(corpus, cfg=cfg, prior=prior, now=now)
    # A REPORT NOBODY'S DATA CHANGED IS NOT A NEW REPORT. Re-rendering it would
    # rewrite `generated_at` and nothing else, so a dark week would commit a
    # pure-timestamp diff to main. `--analyze-only` is an explicit request to
    # rebuild and always writes; so does a first run with no report on disk.
    stale = bool(prior) and rows_written == 0 and not args.analyze_only
    if args.dry_run:
        report_out["analysis"] = {
            "dry_run": True, "n_posts": report.get("n_posts"),
            "n_authors": report.get("n_authors"),
            "note": "report.json / WEEKLY_REPORT.md NOT written on a dry run",
        }
    elif stale:
        report_out["analysis"] = {
            "n_posts": report.get("n_posts"),
            "skipped": "no new corpus rows",
            "note": ("report.json / WEEKLY_REPORT.md left untouched — nothing "
                     "changed but the clock. Force with --analyze-only."),
        }
    else:
        paths = xi.write_report(report, root=root)
        report_out["analysis"] = {
            "n_posts": report.get("n_posts"),
            "n_authors": report.get("n_authors"),
            "n_posts_all_time": report.get("n_posts_all_time"),
            **paths,
        }

    # ── 3. PROPOSE (pending only — never a promotion) ─────────────────────
    if args.no_candidates:
        report_out["candidates"] = {"skipped": "no_candidates"}
    else:
        cands = xs.propose_candidates(corpus, cfg=cfg, now=now)
        if args.dry_run:
            report_out["candidates"] = {"dry_run": True, "proposed": len(cands)}
        else:
            merged = xs.add_pending(cands, root=root, cfg=cfg, now=now)
            store = merged.pop("store")
            if merged["added"] or merged["dropped"]:
                xs.save_store(store, root, now=now)
            merged["proposed"] = len(cands)
            merged["note"] = (
                "PENDING only. Nothing here is visible to the writer until an "
                "operator runs promote_pending() AND pins the resulting version "
                "at intel.exemplar_store.active_version."
            )
            report_out["candidates"] = merged

    report_out["exemplars_live"] = xs.active_version_meta(root=root, cfg=cfg)
    report_out["budget"] = xi.month_bucket(xi.load_state(root), now)
    report_out["budget"]["call_cap"] = conf.get("monthly_call_cap")
    report_out["budget"]["usd_cap"] = conf.get("monthly_usd_cap")

    _emit_report(report_out, args.json_out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
