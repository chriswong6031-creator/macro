#!/usr/bin/env python3
"""Census and tripwire the unlabelled H+60 options-episode population.

``engine/options_episode_coverage.py`` owns the classification and the declared
bounds; this is the I/O shell that reads the committed ledgers, optionally
resolves the ground-truth price-source set from the mutable intraday cache, and
emits the census plus GitHub annotations.

The audit is NON-FATAL by default.  The 2026-08-13 adjudication accepts one of
the two pending classes forever and puts the other on a fix path, so a known,
disclosed, bounded defect must not red the nightly lane that reports it.
``--strict`` exits non-zero on an ``error``-level tripwire for a caller that
wants the bound enforced.

Run:
    python3 -m scripts.audit_options_episode_outcome_coverage
    python3 -m scripts.audit_options_episode_outcome_coverage --out <path> --strict
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from engine.options_episode_coverage import (  # noqa: E402
    build_coverage_census,
)
from engine.options_signal_episode import EPISODE_REL, OUTCOME_REL  # noqa: E402


def _load_jsonl(path: Path) -> list[dict]:
    """Read one append-only ledger.  A missing ledger is an empty estate.

    A torn final line is a hard error rather than a silent truncation: this
    audit exists to make an invisible hole visible, so it must not introduce a
    second one by quietly dropping the newest rows.
    """
    if not path.exists():
        return []
    rows: list[dict] = []
    text = path.read_text(encoding="utf-8")
    if text and not text.endswith("\n"):
        raise SystemExit(f"ledger is torn (no trailing newline): {path}")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{path}:{number} is not valid JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise SystemExit(f"{path}:{number} is not a JSON object")
        rows.append(row)
    return rows


def _intraday_root(repo: Path, data_root: Path) -> Path:
    """Mirror the builder's resolution so both lanes read one cache."""
    configured = os.environ.get("MACRO_INTRADAY_DIR")
    root = Path(configured).expanduser() if configured else data_root / "intraday"
    if not root.is_absolute():
        root = repo / root
    return root.resolve()


def _priced_tickers(intraday_root: Path) -> set[str] | None:
    """Tickers with an admissible parquet + receipt PAIR, or None if unknowable.

    ``_price_snapshot`` treats a parquet without its causal receipt sidecar as
    inadmissible, so the pair — not the parquet — is the coverage unit.  When
    the cache directory is absent entirely (CI, a sparse worktree, any checkout
    without the mutable cache) this returns ``None`` and the census falls back
    to ledger-only inference rather than reporting every ticker as uncovered.
    """
    if not intraday_root.is_dir():
        return None
    found: set[str] = set()
    for receipt in intraday_root.glob("*.parquet.receipt.json"):
        ticker = receipt.name[: -len(".parquet.receipt.json")]
        if ticker and (intraday_root / f"{ticker}.parquet").exists():
            found.add(ticker)
    return found


def _annotate(census: dict) -> None:
    """Emit one GitHub annotation per fired tripwire.

    House law: annotations must START the line, so these are bare ``print``
    calls with ``flush=True`` and never a logger — a prefixing formatter turns
    ``::warning`` into ``WARNING ::warning`` and GitHub drops it silently.
    """
    for wire in census["tripwires"]:
        level = "error" if wire["level"] == "error" else "warning"
        print(
            f"::{level} title=options-episode-outcome-coverage::"
            f"{wire['id']}: {wire['message']}",
            flush=True,
        )


def _summarise(census: dict) -> None:
    totals = census["totals"]
    shares = census["shares"]
    print(
        f"options episode H+60 coverage [{census['evidence_mode']}]: "
        f"{totals['labelled_complete']} complete + "
        f"{totals['labelled_terminal_incomplete']} terminal-incomplete of "
        f"{totals['episodes']} episodes; "
        f"{totals['matured_unlabelled']}/{totals['matured']} matured unlabelled "
        f"({shares['matured_unlabelled_share']:.1%})",
        flush=True,
    )
    print(
        f"  structural price-source gap: {census['classes']['no_admissible_price_source']} "
        f"episode(s) across {len(census['structural_gap_tickers'])} ticker(s)"
        + (f" (+{census['truncated']['structural_gap_tickers']} truncated)"
           if census["truncated"]["structural_gap_tickers"] else ""),
        flush=True,
    )
    print(
        f"  source-dependent pending:    {census['classes']['source_dependent_pending']} "
        f"episode(s) [accepted class, bound "
        f"{census['bounds']['warn_source_dependent_share']:.0%}]",
        flush=True,
    )
    if census["structural_gap_tickers"]:
        names = ", ".join(
            f"{item['ticker']}({item['episodes']})"
            for item in census["structural_gap_tickers"]
        )
        print(f"  uncovered tickers: {names}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Census the unlabelled H+60 options-episode population",
    )
    parser.add_argument("--root-dir", default=None, help="repo root override")
    parser.add_argument("--data-dir", default=None, help="data root override")
    parser.add_argument("--out", default=None, help="write the census JSON here")
    parser.add_argument(
        "--strict", action="store_true",
        help="exit non-zero when an error-level tripwire fires",
    )
    parser.add_argument(
        "--json", action="store_true", help="print the census JSON to stdout",
    )
    args = parser.parse_args(argv)

    repo = Path(args.root_dir).resolve() if args.root_dir else _ROOT
    data_root = Path(args.data_dir).resolve() if args.data_dir else repo / "data"

    episodes = _load_jsonl(data_root / EPISODE_REL)
    outcomes = _load_jsonl(data_root / OUTCOME_REL)
    census = build_coverage_census(
        episodes,
        outcomes,
        now=datetime.now(timezone.utc),
        priced_tickers=_priced_tickers(_intraday_root(repo, data_root)),
    )

    _summarise(census)
    _annotate(census)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(census, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
    if args.json:
        print(json.dumps(census, sort_keys=True), flush=True)
    return 1 if (args.strict and not census["ok"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
