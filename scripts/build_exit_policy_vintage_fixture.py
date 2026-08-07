#!/usr/bin/env python3
"""Regenerate the pinned exit-policy calibration fixture (Learning Loop G3).

WHY THIS FIXTURE EXISTS
-----------------------
``tests/test_exit_policy_study.py`` makes two claims about committed artifacts: that the
study reproduces ``site/factordata/us_track_ledger.json`` key-for-key, and that
``reports/exit-policy-horserace.md`` matches a fresh render. Both were checked by
recomputing from the LIVE price caches — which makes them green only while one nightly
run wrote every input, and red the moment the lanes desync. On 2026-08-06 they went red
together with nothing wrong in either artifact or in the code:

  * FRONTIER — `daily` failed 08-02..08-06, but its *collect* step still committed prices
    on 08-06 (caches 07-31 -> 08-05) while the *grading* step never re-ran. 84 more
    episodes matured across 3 more board days than the shipped ledger had graded.
  * VINTAGE — the same collect RE-ADJUSTED 240 *historical* closes across 12 dividend
    names by 0.56..1.18% (ordinary total-return re-adjustment on a new ex-date), flipping
    ~6 marginal verdicts. These deltas survive ANY date clip, so no ``as_of`` pin can
    recover like-for-like.

Reconstruction fidelity is a property of the CODE, so it is pinned to a frozen INPUT
SLICE rather than to a date (the #4744 lesson: pinning the END leaves the START rolling;
here pinning the DATE leaves the VINTAGE rolling). Against this slice the study is exact
and the committed report renders byte-identical, so a failure there means the
reconstruction really did drift. Live-lane desync is reported separately, and warn-only,
by ``exit_policy_study.coupling_warning``.

WHAT IT WRITES
--------------
A ROOT-SHAPED tree, so ``load_prices(root)`` / ``load_board_days(root)`` /
``run_study(root)`` exercise the real production loaders unmodified — a bespoke fixture
loader would let the loaders themselves rot untested:

    tests/fixtures/exit_policy_vintage/
      data/breadth/_{closes,high,low}_cache.parquet   sliced to the cohort's tickers
      data/yahoo/SPY.parquet                          benchmark closes
      data/us_board_ledger/snapshots.jsonl            distilled to the fields read
      data/us_board_ledger/retro_grades.parquet       distilled to (as_of, lane, ticker)
      site/factordata/us_track_ledger.json            as_of + summary + meta
      MANIFEST.json                                   provenance of all of the above

USAGE
-----
    python3 scripts/build_exit_policy_vintage_fixture.py            # auto-detect the ref
    python3 scripts/build_exit_policy_vintage_fixture.py --ref <sha>

The default ref is the commit that last wrote the shipped ledger, i.e. the one commit at
which the ledger and the caches are known to agree. The script REFUSES to write a fixture
that does not reproduce both artifacts exactly, so a bad ref fails here rather than
shipping a fixture that pins the wrong numbers.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.exit_policy_study import (  # noqa: E402
    LEDGER_HISTORY_FROM,
    REPORT_PATH,
    load_board_days,
    load_prices,
    render_report,
    run_study,
)

FIXTURE = ROOT / "tests" / "fixtures" / "exit_policy_vintage"
LEDGER_REL = "site/factordata/us_track_ledger.json"

# Everything run_study touches. Russell ships no close cache; its high/low are 8 MiB each
# and are sliced to the cohort like the rest, so the fixture stays ~2 MiB.
_SRC_FILES = [
    *(f"data/{g}/_{k}_cache.parquet"
      for k in ("closes", "high", "low")
      for g in ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth")),
    "data/yahoo/SPY.parquet",
    "data/us_board_ledger/snapshots.jsonl",
    "data/us_board_ledger/retro_grades.parquet",
    LEDGER_REL,
]


def _ledger_ref() -> str:
    """The commit that last wrote the shipped ledger — where ledger and caches agree."""
    out = subprocess.run(
        ["git", "-C", str(ROOT), "log", "-1", "--format=%H", "--", LEDGER_REL],
        capture_output=True, text=True, check=True).stdout.strip()
    if not out:
        raise SystemExit(f"no commit found for {LEDGER_REL}")
    return out


def _materialise(ref: str, dest: Path) -> None:
    """Check the source files out of `ref` into a scratch root."""
    for rel in _SRC_FILES:
        p = subprocess.run(["git", "-C", str(ROOT), "show", f"{ref}:{rel}"],
                           capture_output=True)
        if p.returncode != 0:          # absent at that ref — the loaders tolerate it
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(p.stdout)


def _distil_snapshots(src: Path, dest: Path) -> int:
    """Keep only the fields load_board_days reads: as_of, buy[].ticker, buy[].hold.

    The real file is ~17 MiB of full board payloads. The provenance counters it feeds
    (`n_days_snapshots`, `n_days_before_definition`) are incremented PER LINE, so the
    line count and each line's as_of are preserved exactly — a distillation that
    collapsed duplicate days would move the counts the report prints.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with dest.open("w") as fh:
        for line in src.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not d.get("as_of"):
                continue
            buy = []
            for r in d.get("buy") or []:
                if not isinstance(r, dict) or not r.get("ticker"):
                    continue
                row: dict = {"ticker": r["ticker"]}
                hold = r.get("hold")
                if isinstance(hold, dict) and hold.get("invalidation") is not None:
                    row["hold"] = {"invalidation": hold["invalidation"]}
                buy.append(row)
            fh.write(json.dumps({"as_of": d["as_of"], "buy": buy}) + "\n")
            n += 1
    return n


def build(ref: str, *, verify: bool = True) -> dict:
    scratch = Path(tempfile.mkdtemp(prefix="exit-policy-vintage-"))
    try:
        _materialise(ref, scratch)
        closes, highs, lows, bench = load_prices(scratch)
        board_days, _inv, prov = load_board_days(scratch)
        if closes.empty or not board_days:
            raise SystemExit(f"ref {ref[:12]} carries no usable panel/boards")

        from engine import track_scoring as ts
        need = sorted({ep["ticker"] for ep in ts.build_episodes(dict(board_days))})

        if FIXTURE.exists():
            shutil.rmtree(FIXTURE)
        (FIXTURE / "data" / "breadth").mkdir(parents=True, exist_ok=True)
        (FIXTURE / "data" / "yahoo").mkdir(parents=True, exist_ok=True)

        # One merged panel per field: _panel() concatenates the groups first-hit-wins,
        # so the already-merged frame IS what the study reads. Writing it back as a
        # single group keeps `closes[tk]` byte-identical and drops three empty reads.
        for name, df in (("closes", closes), ("high", highs), ("low", lows)):
            cols = [c for c in need if c in df.columns]
            df[cols].to_parquet(FIXTURE / "data" / "breadth" / f"_{name}_cache.parquet",
                                compression="snappy")
        if bench is not None:
            bench.to_frame("close").to_parquet(FIXTURE / "data" / "yahoo" / "SPY.parquet",
                                               compression="snappy")

        n_lines = _distil_snapshots(scratch / "data" / "us_board_ledger" / "snapshots.jsonl",
                                    FIXTURE / "data" / "us_board_ledger" / "snapshots.jsonl")
        retro_src = scratch / "data" / "us_board_ledger" / "retro_grades.parquet"
        if retro_src.exists():
            rg = pd.read_parquet(retro_src, columns=["as_of", "lane", "ticker"])
            rg[rg["as_of"].astype(str) >= LEDGER_HISTORY_FROM].to_parquet(
                FIXTURE / "data" / "us_board_ledger" / "retro_grades.parquet",
                compression="snappy", index=False)

        led = json.loads((scratch / LEDGER_REL).read_text())
        price_asof = str(closes.index.max().date())

        # BACKFILL the frontier stamp on pre-2026-08-06 artifacts. Not an inference: this
        # script checked the caches out of the SAME ref that wrote this ledger, so the
        # frontier is observed provenance, not something fitted to the numbers. (Solving
        # for the frontier that reproduces the counts would be circular — a real drift
        # would just refit and vanish — which is why coupling reports `unknown` at runtime
        # instead.) Recorded as backfilled in the manifest either way.
        meta = dict(led.get("meta") or {})
        backfilled = "priced_through" not in meta
        meta.setdefault("priced_through", price_asof)

        out_led = FIXTURE / LEDGER_REL
        out_led.parent.mkdir(parents=True, exist_ok=True)
        # summary + meta only: `rows` is 120 KiB of per-episode display payload that the
        # calibration never reads. Nothing here may be hand-edited — see the manifest.
        out_led.write_text(json.dumps(
            {"as_of": led.get("as_of"), "summary": led.get("summary"),
             "meta": meta}, indent=1) + "\n")
        manifest = {
            "source_ref": ref,
            "source_ref_short": ref[:12],
            "ledger_as_of": led.get("as_of"),   # last BOARD date — NOT the price frontier
            "priced_through": price_asof,
            "priced_through_backfilled": backfilled,
            "n_tickers": len(need),
            "n_sessions": int(len(closes.index)),
            "n_board_days": len(board_days),
            "n_snapshot_lines": n_lines,
            "provenance": prov,
            "regenerate_with": "python3 scripts/build_exit_policy_vintage_fixture.py",
            "why": ("Reconstruction fidelity is pinned to a FROZEN INPUT SLICE because "
                    "collect re-adjusts historical closes in place, so no date clip can "
                    "restore like-for-like against a live cache. See the module docstring."),
        }
        (FIXTURE / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")

        if verify:
            _verify(manifest)
        return manifest
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _verify(manifest: dict) -> None:
    """Refuse to ship a slice that does not reproduce BOTH committed artifacts."""
    res = run_study(FIXTURE)
    cal = res["calibration"]
    bad = {k: v for k, v in cal["deltas"].items() if v not in (0, 0.0)}
    if bad or not cal["exact_match"]:
        raise SystemExit(f"fixture does NOT reproduce the ledger — deltas {bad}")
    if res["price_asof"] != manifest["priced_through"]:
        raise SystemExit(f"price_asof {res['price_asof']} != manifest "
                         f"{manifest['priced_through']}")
    strip = lambda ls: [l for l in ls if "**Study date:**" not in l]  # noqa: E731
    if REPORT_PATH.exists():
        fresh = strip(render_report(res).splitlines())
        disk = strip(REPORT_PATH.read_text().splitlines())
        if fresh != disk:
            n = sum(1 for a, b in zip(fresh, disk) if a != b) + abs(len(fresh) - len(disk))
            raise SystemExit(
                f"fixture render differs from the committed report on {n} line(s). "
                "Either the ref predates the committed report or render_report changed; "
                "regenerate the report at this ref before pinning it.")
    print(f"[vintage-fixture] verified: ledger exact, report byte-identical at "
          f"{manifest['source_ref_short']} (priced_through={manifest['priced_through']}, "
          f"{manifest['n_tickers']} tickers x {manifest['n_sessions']} sessions)",
          flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ref", default=None,
                    help="git ref to freeze (default: last commit that wrote the ledger)")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip the reproduce-both-artifacts check (diagnostics only)")
    args = ap.parse_args(argv)
    ref = args.ref or _ledger_ref()
    m = build(ref, verify=not args.no_verify)
    print(f"[vintage-fixture] wrote {FIXTURE.relative_to(ROOT)} from {m['source_ref_short']}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
