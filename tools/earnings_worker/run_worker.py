"""tools/earnings_worker/run_worker.py — standalone Windows-PC earnings scorer.

SGA W4 (rulings SGA-R5/R6, masterplan §4).

This runner lives INSIDE the repo tree for source control, but it RUNS on the
operator's Windows PC OUTSIDE the nightly render pipeline.  Its job:

  1. Poll Terminal's published transcript index commit marker and merge new or
     corrected bodies into a durable pending queue. Legacy flat files/explicit
     ticker modes remain available for diagnostics.
  2. Fetch only queued Terminal gzip bodies and map speaker/role segments
     directly into the scorer without copying the transcript corpus.
  3. Score it via engine.earnings_qual.score_text against the LOCAL
     OpenAI-compatible endpoint (llama.cpp / LM Studio / vLLM serving Qwen3-14B).
  4. Upsert the rows into data/earnings_calls/scores.parquet (atomic, dedup).
  5. Publish scores.parquet + manifest.json to R2 (scripts.publish_earnings_r2).

SGA-R6 — PRODUCER / TRANSPORT LAW:
  This worker writes the local parquet and publishes immutable generations to
  R2. It never advances score data through git. Multiple producer hosts hydrate
  first and compare-and-swap the R2 manifest; a lost race rebases and retries.
  The nightly render pipeline is a consumer, not a model-serving path.

SGA-R5:
  Every score is context-only (is_context_only=True, enforced by score_text). The
  trading-verb post-filter runs inside score_text — the worker cannot bypass it.

FAIL-OPEN:
  A missing transcript, an unreachable endpoint, or a publish failure logs a
  warning and remains retryable. The worker never poisons the live Stage overlay.

USAGE (see README.md for the full Windows setup)
------------------------------------------------
  python run_worker.py --tickers NVDA,AAPL --transcripts-dir D:/earnings/transcripts
  python run_worker.py --queue --limit 64 --base-url http://localhost:8000/v1 --model qwen3-14b
  python run_worker.py --transcripts-dir D:/earnings/transcripts --auto   # score whatever is un-scored
  python run_worker.py --terminal-auto --bootstrap-since 2026-07-24       # one-time recent catch-up
  python run_worker.py --terminal-auto                                    # every later scheduled run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------- #
# Locate the repo root so `engine.earnings_qual` + `scripts.*` import.
# This file is at <repo>/tools/earnings_worker/run_worker.py → parents[2] = repo.
# An explicit --repo-root overrides (useful if the worker is copied elsewhere).
# --------------------------------------------------------------------------- #
def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


log = logging.getLogger("earnings_worker")


def _future_call_date(
    raw: object,
    *,
    source_updated_at: object = None,
    today: date | None = None,
) -> bool:
    """Return True when a source labels a transcript after the current UTC day.

    Terminal is an upstream archive, not an oracle.  A provider can publish a
    complete body with a bad future event date; scoring it would create
    point-in-time leakage across Stage, Chronicle, Press, and X.  Keep the body
    retryable until its advertised day instead of guessing a corrected date.
    """

    value = str(raw or "").strip()
    if not value:
        return False
    try:
        call_day = date.fromisoformat(value[:10])
    except ValueError:
        return False
    observed_day = today or datetime.now(timezone.utc).date()
    if call_day > observed_day:
        return True
    source_value = str(source_updated_at or "").strip()
    if not source_value:
        return False
    try:
        source_day = date.fromisoformat(source_value[:10])
    except ValueError:
        return True
    # Require a causal source marker: the archive cannot credibly claim a call
    # occurred after the commit marker that made its transcript visible.  A
    # future-dated marker is quarantined as an upstream clock error as well.
    return source_day > observed_day or call_day > source_day


def _load_queue(repo_root: Path) -> list[str]:
    """Load the upcoming-earnings priority queue: a JSON list of tickers ordered
    by earnings proximity (soonest first), or {"tickers": [...]}.  Absent → []."""
    p = repo_root / "data" / "earnings_calls" / "queue.json"
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("queue.json unreadable (%s) — empty queue", exc)
        return []
    if isinstance(data, dict):
        data = data.get("tickers") or []
    if isinstance(data, list):
        return [str(t).upper() for t in data if str(t).strip()]
    return []


def _find_transcript(transcripts_dir: Path, ticker: str) -> tuple[dict, str] | None:
    """Find the newest transcript JSON for a ticker in transcripts_dir.

    Matches files named like <TICKER>*.json (case-insensitive) OR any *.json whose
    payload ticker matches.  Returns (payload, text) or None.
    """
    if not transcripts_dir.is_dir():
        return None
    tk = ticker.upper()
    candidates: list[tuple[float, dict, str]] = []
    for p in transcripts_dir.glob("*.json"):
        try:
            payload = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(payload, dict):
            continue
        ptk = str(payload.get("ticker") or "").upper()
        name_match = p.stem.upper().startswith(tk)
        if ptk != tk and not name_match:
            continue
        text = str(payload.get("text") or "")
        if not text.strip():
            continue
        candidates.append((p.stat().st_mtime, payload, text))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    _, payload, text = candidates[0]
    return payload, text


def run(
    *,
    tickers: list[str],
    transcripts_dir: Path,
    repo_root: Path,
    provider_cfg: dict,
    limit: int,
    do_publish: bool,
    auto: bool,
) -> int:
    """Score `tickers` (or, with auto=True, everything un-scored in the dir).

    Returns the number of rows scored + upserted.
    """
    # Import the repo harness (repo_root must be on sys.path).
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from engine import earnings_qual  # noqa: PLC0415

    if not _fetch_remote_first(repo_root):
        log.warning("refusing local score writes until the committed R2 generation hydrates")
        return 0
    cfg = earnings_qual.load_config(repo_root)

    # AUTO mode: delegate to the engine's score_new over the transcripts dir.
    # It handles dedup (source_sha256) and the daily cap internally.  We point
    # the engine at the operator's transcripts dir by symlinking is undesirable;
    # instead, when --transcripts-dir differs from the repo default, we score
    # explicitly below.  auto with the DEFAULT dir uses score_new directly.
    default_dir = repo_root / "data" / "earnings_calls" / "transcripts"
    if auto and transcripts_dir.resolve() == default_dir.resolve():
        n = earnings_qual.score_new(
            root=repo_root, source="auto", limit=limit,
            cfg=cfg, provider_cfg=provider_cfg,
        )
        log.info("auto score_new wrote %d row(s)", n)
        if do_publish and earnings_qual.store_path(repo_root).exists():
            _publish(repo_root)
        return n

    # Explicit / custom-dir path: resolve tickers, load text, score each.
    seen = earnings_qual._seen_shas(repo_root)  # dedup against existing store
    if auto:
        # score everything un-scored in the custom dir (bounded by limit)
        found: list[tuple[dict, str]] = []
        for p in sorted(transcripts_dir.glob("*.json")):
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(payload, dict):
                continue
            text = str(payload.get("text") or "")
            if text.strip():
                found.append((payload, text))
        work = found
    else:
        work = []
        for tk in tickers:
            hit = _find_transcript(transcripts_dir, tk)
            if hit is None:
                log.warning("no transcript found for %s in %s", tk, transcripts_dir)
                continue
            work.append(hit)

    rows = []
    for payload, text in work:
        if len(rows) >= limit:
            break
        sha = earnings_qual.source_sha256(text)
        if sha in seen:
            log.info("already scored (sha match): %s — skip", payload.get("ticker"))
            continue
        row = earnings_qual.score_text(
            text,
            payload.get("ticker", ""),
            payload.get("quarter"),
            payload.get("year"),
            provider_cfg=provider_cfg,
            cfg=cfg,
            call_date=payload.get("call_date"),
            source=payload.get("source", "transcript"),
            source_record_id=payload.get("source_record_id"),
            source_updated_at=payload.get("source_updated_at"),
            source_url=payload.get("terminal_url"),
        )
        if row.get("degraded_reason"):
            log.warning("scored %s DEGRADED (%s)", row.get("ticker"),
                        row.get("degraded_reason"))
        else:
            log.info("scored %s %s FY%s — sentiment=%.2f performance=%.1f tone=%s",
                     row.get("ticker"), row.get("quarter"), row.get("year"),
                     row.get("sentiment") or 0.0, row.get("performance") or 0.0,
                     row.get("tone_word"))
        seen.add(sha)
        rows.append(row)

    if not rows:
        log.info("nothing new to score")
        if do_publish and earnings_qual.store_path(repo_root).exists():
            _publish(repo_root)
        return 0

    n = earnings_qual.upsert_scores(rows, root=repo_root)
    log.info("upserted %d row(s) into %s", n, earnings_qual.store_path(repo_root))
    if do_publish:
        _publish(repo_root)
    return n


def run_terminal(
    *,
    repo_root: Path,
    provider_cfg: dict,
    limit: int,
    do_publish: bool,
    base_url: str,
    tx_root: Path | None,
    state_path: Path,
    bootstrap_since: str | None,
    seed_existing: bool,
) -> int:
    """Poll Terminal's commit-marker index and score its durable pending queue.

    Discovery/cursor advancement is independent from model completion. A failed
    fetch or degraded model row stays pending and retries on the next run.
    """

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from engine import earnings_qual  # noqa: PLC0415
    from engine import earnings_transcript_intake as intake  # noqa: PLC0415

    # This producer is a read-modify-publish writer.  Always hydrate the latest
    # committed generation before the first local upsert so a fresh PC clone
    # cannot publish a one-row store over the accumulated R2 score history.
    hydration_base = _fetch_remote_first(repo_root)
    if not hydration_base:
        log.warning("refusing Terminal score writes until R2 hydration succeeds")
        return -1
    expected_manifest_etag = (
        hydration_base if isinstance(hydration_base, str) else None
    )

    source_key = f"local:{tx_root.resolve()}" if tx_root is not None else base_url.rstrip("/")
    state = intake.load_state(state_path, source=source_key)

    if tx_root is not None:
        index_path = tx_root / "index.json"
        if not index_path.exists():
            raise ValueError(
                f"Terminal local tx root has no committed index marker: {index_path}"
            )
        raw_index = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        raw_index = intake.fetch_global_index(base_url)
    refs, metadata = intake.parse_global_index(raw_index)

    first_run = not bool(state.get("initialized"))
    # Safe default: a first unattended run establishes a forward-only cursor.
    # --bootstrap-since deliberately opts into a bounded recent catch-up.
    state, pending = intake.plan_index(
        refs,
        state,
        metadata=metadata,
        seed_existing=(seed_existing or (first_run and not bootstrap_since)),
        bootstrap_since=bootstrap_since,
    )
    intake.save_state(state_path, state)
    if first_run and not bootstrap_since:
        log.info(
            "seeded Terminal cursor with %d committed bodies; future calls will queue",
            len(refs),
        )

    if not pending:
        log.info("Terminal transcript queue is current; nothing new to score")
        if do_publish and earnings_qual.store_path(repo_root).exists():
            _publish(repo_root, expected_manifest_etag=expected_manifest_etag)
        return 0

    cfg = earnings_qual.load_config(repo_root)
    limit = min(int(limit), int(cfg.get("daily_cap", 64)))
    completed_records = earnings_qual._completed_record_shas(repo_root)
    succeeded = 0
    attempted = 0
    for ref in pending:
        if attempted >= limit:
            break
        attempted += 1
        try:
            body = (
                intake.read_local_body(tx_root, ref)
                if tx_root is not None
                else intake.fetch_body(base_url, ref)
            )
            payload, text = intake.body_to_score_input(
                body,
                index_generated_at=str(metadata.get("generated_at") or ""),
                source_base_url=(
                    base_url
                    if tx_root is None
                    else os.environ.get(
                        "TERMINAL_TX_PUBLIC_BASE_URL",
                        "https://app.mastermind-x.com/data/tx",
                    )
                ),
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("Terminal transcript %s unavailable/invalid (%s) — retry", ref.pair, exc)
            state = intake.mark_failed(
                state,
                ref,
                error=f"source_unavailable:{type(exc).__name__}",
            )
            intake.save_state(state_path, state)
            continue

        if _future_call_date(
            payload.get("call_date"),
            source_updated_at=payload.get("source_updated_at"),
        ):
            # Preserve the queued revision and retry it on a later run.  This
            # is deliberately checked before provider dispatch, so a bad
            # upstream timestamp costs no tokens and reaches no product store.
            log.warning(
                "Terminal transcript %s is future-dated (%s) -- quarantined",
                ref.pair,
                payload.get("call_date"),
            )
            state = intake.mark_failed(
                state,
                ref,
                error="source_future_call_date",
            )
            intake.save_state(state_path, state)
            continue

        sha = str(payload.get("source_revision_sha256") or ref.body_sha256 or "")
        if not sha:
            sha = earnings_qual.source_sha256(text)
        record_id = str(payload.get("source_record_id") or "")
        if record_id and completed_records.get(record_id) == sha:
            log.info("Terminal transcript already scored: %s", ref.pair)
            state = intake.mark_completed(state, ref)
            intake.save_state(state_path, state)
            continue

        row = earnings_qual.score_text(
            text,
            payload["ticker"],
            payload["quarter"],
            payload["year"],
            provider_cfg=provider_cfg,
            cfg=cfg,
            call_date=payload.get("call_date"),
            source=payload.get("source", "transcript"),
            source_record_id=payload.get("source_record_id"),
            source_updated_at=payload.get("source_updated_at"),
            source_url=payload.get("terminal_url"),
            source_revision_sha256=payload.get("source_revision_sha256"),
        )
        if row.get("degraded_reason"):
            # Keep the cursor pending.  upsert_scores may retain a degraded
            # observability receipt, but it will preserve any prior healthy row.
            earnings_qual.upsert_scores([row], root=repo_root)
            log.warning(
                "Terminal transcript %s DEGRADED (%s) — retained in retry queue",
                ref.pair,
                row.get("degraded_reason"),
            )
            state = intake.mark_failed(
                state,
                ref,
                error=f"model:{row.get('degraded_reason') or 'unknown'}",
            )
            intake.save_state(state_path, state)
            continue

        earnings_qual.upsert_scores([row], root=repo_root)
        if record_id:
            completed_records[record_id] = sha
        succeeded += 1
        state = intake.mark_completed(state, ref)
        intake.save_state(state_path, state)
        log.info(
            "scored Terminal %s — sentiment=%.2f performance=%.1f tone=%s",
            ref.pair,
            row.get("sentiment") or 0.0,
            row.get("performance") or 0.0,
            row.get("tone_word"),
        )

    if do_publish and earnings_qual.store_path(repo_root).exists():
        _publish(repo_root, expected_manifest_etag=expected_manifest_etag)
    log.info(
        "Terminal intake attempted=%d succeeded=%d pending=%d",
        attempted,
        succeeded,
        len(state.get("pending") or []),
    )
    return succeeded


def _fetch_remote_first(repo_root: Path) -> bool | str:
    """Hydrate and merge the current committed R2 generation before writing.

    With no R2 writer credentials this remains a harmless local-only no-op.
    When publication is configured, however, the worker fails closed unless it
    can prove the local base matches the remote commit marker. Pending local
    rows from an earlier failed publish are preserved across hydration and
    merged back by stable source identity.
    """
    try:
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from engine import earnings_qual  # noqa: PLC0415
        from scripts import fetch_earnings_scores  # noqa: PLC0415
        from scripts import publish_earnings_r2  # noqa: PLC0415

        configured = all(
            os.environ.get(name)
            for name in (
                "R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET",
            )
        )
        if not configured:
            fetch_earnings_scores.fetch(data_dir=repo_root / "data")
            return True

        client = fetch_earnings_scores._client()
        bucket = os.environ.get("R2_BUCKET", "")
        manifest, manifest_etag = (
            publish_earnings_r2._remote_manifest_snapshot(client, bucket)
            if client
            else (None, None)
        )
        valid, reason = fetch_earnings_scores._manifest_contract(manifest)
        if not valid or manifest is None or not manifest_etag:
            log.warning("remote earnings commit marker unavailable/invalid (%s)", reason)
            return False

        earnings_dir = repo_root / "data" / "earnings_calls"
        if fetch_earnings_scores._local_generation_current(earnings_dir, manifest):
            return manifest_etag

        # Preserve unpublished local rows before the manifest-last fetch replaces
        # the base generation.  They are merged back only after remote validation.
        local_pending = earnings_qual._load_scores_unvalidated(repo_root)
        fetch_earnings_scores.fetch(data_dir=repo_root / "data")
        if not fetch_earnings_scores._local_generation_current(earnings_dir, manifest):
            log.warning("local earnings store did not reach remote generation after fetch")
            return False
        if not local_pending.empty:
            earnings_qual.merge_score_store_frame(local_pending, root=repo_root)
        return manifest_etag
    except Exception as exc:  # noqa: BLE001
        log.warning("pre-write R2 hydration failed (%s) — retaining local store", exc)
        return False


def _publish(
    repo_root: Path,
    *,
    expected_manifest_etag: str | None = None,
) -> bool:
    """Publish scores with optimistic R2 conflict rebase.  Fail-open.

    Immutable generation payloads may be uploaded concurrently, but the
    manifest commit marker is compare-and-swapped.  On a lost race, hydrate the
    winner, merge our still-local rows by stable source identity, and retry.
    """
    try:
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from scripts import publish_earnings_r2  # noqa: PLC0415
        conflict_rc = int(getattr(publish_earnings_r2, "PUBLISH_CONFLICT", 2))
        if expected_manifest_etag is None:
            hydration_base = _fetch_remote_first(repo_root)
            if not hydration_base:
                log.warning("earnings pre-publish hydration failed")
                return False
            if isinstance(hydration_base, str):
                expected_manifest_etag = hydration_base
        for attempt in range(3):
            rc = publish_earnings_r2.publish(
                data_dir=repo_root / "data",
                expected_manifest_etag=expected_manifest_etag,
            )
            if rc == 0:
                log.info("publish_earnings_r2 completed")
                return True
            if rc != conflict_rc:
                log.warning(
                    "publish_earnings_r2 returned %d — scores stay local; next run retries",
                    rc,
                )
                return False
            log.warning(
                "earnings manifest changed during publish (attempt %d/3) — rebasing",
                attempt + 1,
            )
            hydration_base = _fetch_remote_first(repo_root)
            if not hydration_base:
                log.warning("earnings publish rebase failed — local rows retained")
                return False
            expected_manifest_etag = (
                hydration_base if isinstance(hydration_base, str) else None
            )
        log.warning("earnings publish lost three manifest races — local rows retained")
        return False
    except Exception as exc:  # noqa: BLE001
        log.warning("publish step failed (%s) — scores stay local; next run retries", exc)
        return False


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tickers", default="",
                    help="Comma-separated tickers to score (e.g. NVDA,AAPL).")
    ap.add_argument("--queue", action="store_true",
                    help="Pull tickers from data/earnings_calls/queue.json "
                         "(upcoming-earnings priority order).")
    ap.add_argument("--auto", action="store_true",
                    help="Score every un-scored transcript in --transcripts-dir.")
    ap.add_argument(
        "--terminal-auto",
        action="store_true",
        help="Poll the Terminal transcript commit-marker index and process its durable queue.",
    )
    ap.add_argument(
        "--terminal-tx-base-url",
        default=os.environ.get(
            "TERMINAL_TX_BASE_URL", "https://app.mastermind-x.com/data/tx"
        ),
        help="Terminal transcript base URL containing index.json (remote worker mode).",
    )
    ap.add_argument(
        "--terminal-tx-root",
        default=None,
        help="Optional local Terminal tx root; must contain the published index.json marker.",
    )
    ap.add_argument(
        "--terminal-state",
        default=None,
        help="Durable intake cursor path (default data/earnings_calls/terminal_intake_state.json).",
    )
    ap.add_argument(
        "--bootstrap-since",
        default=None,
        help="On first Terminal run, queue calls dated on/after YYYY-MM-DD; otherwise seed forward-only.",
    )
    ap.add_argument(
        "--seed-existing",
        action="store_true",
        help="Explicitly seed all currently published Terminal pairs without scoring them.",
    )
    ap.add_argument("--transcripts-dir", default=None,
                    help="Directory of transcript JSONs "
                         "({ticker,quarter,year,call_date,text}).")
    ap.add_argument("--limit", type=int, default=64,
                    help="Max scores this run (also bounded by config daily_cap).")
    ap.add_argument("--base-url", default=None,
                    help="Local OpenAI-compatible endpoint base URL "
                         "(overrides config; e.g. http://localhost:8000/v1).")
    ap.add_argument("--model", default=None,
                    help="Local model id (overrides config; e.g. qwen3-14b).")
    ap.add_argument(
        "--provider-order",
        default=os.environ.get("EARNINGS_PROVIDER_ORDER", "openai_compat"),
        help=(
            "Comma-separated provider order. Default local-only; for zero-touch fallback use "
            "openai_compat,deepseek,kimi,codex,anthropic."
        ),
    )
    ap.add_argument("--no-publish", action="store_true",
                    help="Do not publish to R2 after scoring (local test).")
    ap.add_argument("--repo-root", default=None,
                    help="Repo root override (default: two dirs up from this file).")
    args = ap.parse_args(argv)

    repo_root = Path(args.repo_root) if args.repo_root else _default_repo_root()
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # Resolve transcripts dir (default: repo store).
    if args.transcripts_dir:
        transcripts_dir = Path(args.transcripts_dir)
    else:
        transcripts_dir = repo_root / "data" / "earnings_calls" / "transcripts"

    # Build the provider override for the LOCAL endpoint.
    oc_override: dict = {}
    if args.base_url:
        oc_override["base_url"] = args.base_url
    if args.model:
        oc_override["model"] = args.model
    # Allow base-url/model via env too (Task Scheduler convenience).
    if not args.base_url and os.environ.get("EARNINGS_LLM_BASE_URL"):
        oc_override["base_url"] = os.environ["EARNINGS_LLM_BASE_URL"]
    if not args.model and os.environ.get("EARNINGS_LLM_MODEL"):
        oc_override["model"] = os.environ["EARNINGS_LLM_MODEL"]
    provider_cfg: dict = {}
    if oc_override:
        provider_cfg["openai_compat"] = oc_override
    provider_order = [
        name.strip() for name in str(args.provider_order).split(",") if name.strip()
    ]
    provider_cfg["provider_order"] = provider_order or ["openai_compat"]

    # Resolve ticker list.
    tickers: list[str] = []
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.queue:
        tickers = _load_queue(repo_root)
        if not tickers:
            log.warning("queue empty — nothing to do")
            return 0

    if not tickers and not args.auto and not args.terminal_auto:
        log.error("no work: pass --tickers, --queue, --auto, or --terminal-auto")
        return 2

    if args.terminal_auto:
        state_path = (
            Path(args.terminal_state)
            if args.terminal_state
            else repo_root / "data" / "earnings_calls" / "terminal_intake_state.json"
        )
        tx_root = Path(args.terminal_tx_root) if args.terminal_tx_root else None
        n = run_terminal(
            repo_root=repo_root,
            provider_cfg=provider_cfg,
            limit=args.limit,
            do_publish=not args.no_publish,
            base_url=args.terminal_tx_base_url,
            tx_root=tx_root,
            state_path=state_path,
            bootstrap_since=args.bootstrap_since,
            seed_existing=args.seed_existing,
        )
        if n < 0:
            print(
                "earnings_worker: Terminal intake blocked before cursor initialization",
                file=sys.stderr,
            )
            return 1
        print(f"earnings_worker: scored {n} Terminal transcript row(s)")
        return 0

    n = run(
        tickers=tickers,
        transcripts_dir=transcripts_dir,
        repo_root=repo_root,
        provider_cfg=provider_cfg,
        limit=args.limit,
        do_publish=not args.no_publish,
        auto=args.auto,
    )
    print(f"earnings_worker: scored {n} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
