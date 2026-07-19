"""tools/earnings_worker/run_worker.py — standalone Windows-PC earnings scorer.

SGA W4 (rulings SGA-R5/R6, masterplan §4).

This runner lives INSIDE the repo tree for source control, but it RUNS on the
operator's Windows PC OUTSIDE the nightly render pipeline.  Its job:

  1. Pick the next tickers to score, by upcoming-earnings priority from a local
     queue file (data/earnings_calls/queue.json) or an explicit --tickers list.
  2. Load each ticker's transcript text from --transcripts-dir (one JSON per
     filing, shaped {ticker, quarter, year, call_date, text}).
  3. Score it via engine.earnings_qual.score_text against the LOCAL
     OpenAI-compatible endpoint (llama.cpp / LM Studio / vLLM serving Qwen3-14B).
  4. Upsert the rows into data/earnings_calls/scores.parquet (atomic, dedup).
  5. Publish scores.parquet + manifest.json to R2 (scripts.publish_earnings_r2).

SGA-R6 — SINGLE-WRITER LAW:
  This worker is PRODUCER-ONLY. It writes the local parquet and publishes to R2.
  It NEVER runs git (no add / commit / push / pull). The nightly pipeline is the
  sole ledger advancer and pulls scores from R2 via scripts/fetch_earnings_scores.py.

SGA-R5:
  Every score is context-only (is_context_only=True, enforced by score_text). The
  trading-verb post-filter runs inside score_text — the worker cannot bypass it.

FAIL-OPEN:
  A missing transcript, an unreachable endpoint, or a publish failure logs a
  warning and moves on. The worker never crashes a scheduled run.

USAGE (see README.md for the full Windows setup)
------------------------------------------------
  python run_worker.py --tickers NVDA,AAPL --transcripts-dir D:/earnings/transcripts
  python run_worker.py --queue --limit 8 --base-url http://localhost:8000/v1 --model qwen3-14b
  python run_worker.py --transcripts-dir D:/earnings/transcripts --auto   # score whatever is un-scored
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Locate the repo root so `engine.earnings_qual` + `scripts.*` import.
# This file is at <repo>/tools/earnings_worker/run_worker.py → parents[2] = repo.
# An explicit --repo-root overrides (useful if the worker is copied elsewhere).
# --------------------------------------------------------------------------- #
def _default_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


log = logging.getLogger("earnings_worker")


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
        if do_publish and n:
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
        return 0

    n = earnings_qual.upsert_scores(rows, root=repo_root)
    log.info("upserted %d row(s) into %s", n, earnings_qual.store_path(repo_root))
    if do_publish:
        _publish(repo_root)
    return n


def _publish(repo_root: Path) -> None:
    """Publish scores.parquet + manifest.json to R2.  Fail-open."""
    try:
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        from scripts import publish_earnings_r2  # noqa: PLC0415
        rc = publish_earnings_r2.publish()
        log.info("publish_earnings_r2 returned %d", rc)
    except Exception as exc:  # noqa: BLE001
        log.warning("publish step failed (%s) — scores stay local; next run retries", exc)


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
    ap.add_argument("--transcripts-dir", default=None,
                    help="Directory of transcript JSONs "
                         "({ticker,quarter,year,call_date,text}).")
    ap.add_argument("--limit", type=int, default=8,
                    help="Max scores this run (also bounded by config daily_cap).")
    ap.add_argument("--base-url", default=None,
                    help="Local OpenAI-compatible endpoint base URL "
                         "(overrides config; e.g. http://localhost:8000/v1).")
    ap.add_argument("--model", default=None,
                    help="Local model id (overrides config; e.g. qwen3-14b).")
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
    # The worker forces the local endpoint FIRST (never cloud on the PC lane).
    provider_cfg["provider_order"] = ["openai_compat"]

    # Resolve ticker list.
    tickers: list[str] = []
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    elif args.queue:
        tickers = _load_queue(repo_root)
        if not tickers:
            log.warning("queue empty — nothing to do")
            return 0

    if not tickers and not args.auto:
        log.error("no work: pass --tickers, --queue, or --auto")
        return 2

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
