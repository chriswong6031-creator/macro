"""Tripwire for a scorer that is still running but has stopped discriminating.

WHY THIS EXISTS.  Every instrument around the earnings scorer answers "did it
run".  None answered "is what it produced any good", so the answer went
unmeasured for months and was only found by reading the parquet by hand on
2026-08-14.  Over the 64 calls scored that morning through the local Qwen rung:

    tone_word        2 of the 10 allowed words ever used (confident 42, cautious 22)
    sentiment        45 of 64 rows on exactly TWO values (0.85 and -0.15)
    performance      34.4% of quarters scored >= 9  (metered rungs, same schema: 8.4%)

None of that is visible from a run log.  The worker reported
`attempted=64 succeeded=64`, published cleanly, and promoted a new R2
generation — a perfect run that emitted a barely-graded corpus.  A scorer whose
output has collapsed onto a handful of values is still "working" by every
liveness check we own, which is exactly the shape of failure this file exists to
name.

WHAT IT MEASURES, and why these three.  Each metric is the direct observable of
one of the three failures above, and each threshold is set against the metered
rungs reading the SAME schema rather than against a guess:

  * tone vocabulary use — a bounded vocabulary the model only reaches two words
    into is a field carrying almost no information.
  * top-2 sentiment concentration — bunching on a couple of habitual numbers is
    what an under-anchored scale looks like from the store side.
  * share of quarters scored >= 9 — a top-heavy distribution means the scale has
    lost its middle. Most quarters are ordinary; a corpus where a third are
    near-blowouts is not describing the market.

NOT A MODEL GRADER.  This cannot tell you a score is WRONG for a given call —
only that the distribution has degenerated in a way that makes the field useless
downstream. It is deliberately cheap, reads only the store, and calls no model.

Usage:
    python -m scripts.audit_earnings_score_quality --scores data/earnings_calls/scores.parquet
    python -m scripts.audit_earnings_score_quality --window-days 7 --strict
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.earnings_qual import TONE_WORDS  # noqa: E402

DEFAULT_SCORES = Path("data/earnings_calls/scores.parquet")

# Minimum rows before any verdict. Below this the shares are noise, and a
# tripwire that fires on 5 rows is a tripwire that gets muted.
DEFAULT_MIN_ROWS = 30

# (warn, error). Observed local-Qwen values on 2026-08-14 in brackets.
TONE_VOCAB_FLOOR = (0.40, 0.30)        # share of the 10 tone words used   [0.20]
SENTIMENT_TOP2_CEIL = (0.40, 0.55)     # share on the two commonest values [0.70]
HIGH_PERF_CEIL = (0.15, 0.25)          # share of performance >= 9         [0.344]
_HIGH_PERF_THRESHOLD = 9.0


class EarningsScoreQualityError(RuntimeError):
    """The audit could not be computed (missing/unreadable/empty store)."""


def _level(value: float, bounds: tuple[float, float], *, higher_is_worse: bool) -> str:
    warn, err = bounds
    if higher_is_worse:
        if value >= err:
            return "error"
        return "warning" if value >= warn else "ok"
    if value <= err:
        return "error"
    return "warning" if value <= warn else "ok"


def _worst(levels: list[str]) -> str:
    for rank in ("error", "warning"):
        if rank in levels:
            return rank
    return "ok"


def audit_frame(df: Any, *, min_rows: int = DEFAULT_MIN_ROWS) -> dict:
    """Grade one already-filtered frame of scored rows."""
    n = len(df)
    if n == 0:
        raise EarningsScoreQualityError("no scored rows in the selected window")

    tones = df["tone_word"].dropna()
    distinct = {str(t).strip().lower() for t in tones if str(t).strip()}
    vocab_share = len(distinct & set(TONE_WORDS)) / len(TONE_WORDS)

    sentiment = df["sentiment"].dropna()
    top2_share = (
        float(sentiment.value_counts().head(2).sum()) / len(sentiment) if len(sentiment) else 0.0
    )

    performance = df["performance"].dropna()
    high_share = (
        float((performance >= _HIGH_PERF_THRESHOLD).sum()) / len(performance)
        if len(performance)
        else 0.0
    )

    checks = {
        "tone_vocabulary_share": {
            "value": round(vocab_share, 4),
            "level": _level(vocab_share, TONE_VOCAB_FLOOR, higher_is_worse=False),
            "detail": f"{len(distinct & set(TONE_WORDS))} of {len(TONE_WORDS)} tone words used",
        },
        "sentiment_top2_share": {
            "value": round(top2_share, 4),
            "level": _level(top2_share, SENTIMENT_TOP2_CEIL, higher_is_worse=True),
            "detail": f"{top2_share * 100:.0f}% of rows on the two commonest sentiment values",
        },
        "high_performance_share": {
            "value": round(high_share, 4),
            "level": _level(high_share, HIGH_PERF_CEIL, higher_is_worse=True),
            "detail": f"{high_share * 100:.0f}% of quarters scored >= {_HIGH_PERF_THRESHOLD:g}",
        },
    }

    # Under-sampled windows are reported, never graded: a share over 12 rows says
    # nothing, and a false alarm here is how a tripwire earns a permanent mute.
    level = "insufficient_data" if n < min_rows else _worst([c["level"] for c in checks.values()])

    return {
        "schema": "macro.earnings_score_quality/v1",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "rows": n,
        "min_rows": min_rows,
        "checks": checks,
        "level": level,
        "ok": level in {"ok", "insufficient_data"},
    }


def load_scores(path: Path, *, window_days: int | None, prompt_version: str | None) -> Any:
    try:
        import pandas as pd
    except ImportError as exc:  # pragma: no cover - environment guard
        raise EarningsScoreQualityError(f"pandas unavailable: {exc}") from exc
    if not path.is_file():
        raise EarningsScoreQualityError(f"scores store not found: {path}")
    df = pd.read_parquet(path)
    for column in ("tone_word", "sentiment", "performance", "scored_at"):
        if column not in df.columns:
            raise EarningsScoreQualityError(f"scores store has no `{column}` column")
    if prompt_version:
        df = df[df["prompt_version"].astype(str).str.startswith(prompt_version)]
    if window_days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
        stamps = pd.to_datetime(df["scored_at"], errors="coerce", utc=True)
        df = df[stamps >= cutoff]
    return df


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Earnings scorer degeneration tripwire")
    parser.add_argument("--scores", default=str(DEFAULT_SCORES))
    parser.add_argument("--window-days", type=int, default=7)
    parser.add_argument(
        "--prompt-version",
        default=None,
        help="only grade rows whose prompt_version starts with this (e.g. equal-v3)",
    )
    parser.add_argument("--min-rows", type=int, default=DEFAULT_MIN_ROWS)
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--strict", action="store_true", help="exit 1 on an error verdict")
    args = parser.parse_args(argv)

    # Every annotation is a BARE print at column 0 with flush=True. Through a
    # logger the level name prefixes the line, GitHub drops it, and the alarm
    # reviews as armed while emitting nothing (CLAUDE.md §GitHub annotations).
    try:
        df = load_scores(
            Path(args.scores),
            window_days=args.window_days,
            prompt_version=args.prompt_version,
        )
        report = audit_frame(df, min_rows=args.min_rows)
    except Exception as exc:
        print(
            f"::warning title=earnings-score-quality::earnings_score_quality: "
            f"audit could not be computed: {exc}",
            flush=True,
        )
        return 1 if args.strict else 0

    detail = " | ".join(c["detail"] for c in report["checks"].values())
    summary = f"n={report['rows']} {detail}"

    if report["level"] == "error":
        print(
            f"::error title=earnings-scorer-degenerated::earnings_score_quality: the "
            f"scorer is running but has stopped discriminating ({summary}). Check the "
            f"prompt's calibration anchors and the resolved context bound before "
            f"trusting these scores downstream.",
            flush=True,
        )
    elif report["level"] == "warning":
        print(
            f"::warning title=earnings-score-quality::earnings_score_quality: score "
            f"distribution is narrowing ({summary}).",
            flush=True,
        )
    elif report["level"] == "insufficient_data":
        print(
            f"earnings_score_quality: not graded — {report['rows']} rows "
            f"(< {report['min_rows']}) in the window",
            flush=True,
        )
    else:
        print(f"earnings_score_quality: ok ({summary})", flush=True)

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    return 1 if (args.strict and report["level"] == "error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
