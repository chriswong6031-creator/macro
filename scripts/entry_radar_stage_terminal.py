"""Stage and run the A5.6-pinned Terminal emitter — the G0/C5 replay population.

WHAT THIS IS FOR (prereg §3, gate §14 G-5)
-------------------------------------------
G0's replay population is NOT a Macro reimplementation of the grey dot.  It is the
Terminal repo's own ``signal_layer`` at the pinned commit
``prereg.TERMINAL_PIN``, exported with ``git archive`` into a run workspace and
executed per name on the panel's close series (the W2 F6-probe precedent).  No
Terminal file is modified and nothing is re-derived here — running the pinned
original is what discharges §3.2's "seeded from origin/master only" law.

The G-5 gate then demands EVIDENCE that the staged emitter is the emitter the W2
fixtures were cut from: :func:`fixture_fidelity` re-runs it on the fixture names
and compares, and ``engine.entry_radar.replay.gates.check_staging_fidelity``
refuses the whole run on any mismatch.

THE ONE SUBTLETY IN THE FIXTURE COMPARISON (measured, not assumed)
------------------------------------------------------------------
The artifact field ``indicator.early_dots`` is NOT the dot population.  At the
pin, ``confluence_v2.build_v2`` computes (``confluence_v2.py:1171-1178, 1201`` @
82cb8cbf)::

    promoted_dot_dates  = {w.ts for w in bottom_watches if w.kind == "early_dot"}
    unpromoted_early_dots = [ts for ts in early_dots(sig, close)
                             if ts not in promoted_dot_dates]
    ...  "early_dots": unpromoted_early_dots[-SIDE_CHANNEL_CAP:]   # cap = 40

and ``contracts.indicator_contract`` caps once more at ``[-40:]``.  So the field
is the last 40 of the dots that were NOT promoted into a bottom-watch — a DISPLAY
side channel, deliberately de-duplicated against the amber watch markers.

The REPLAY population is the other object: ``g0_adapter``'s §3.1 union,
``early_dots ∪ {w.ts for w in bottom_watches if subtype == "early_dot"}``, which
is exactly the uncapped module-level ``early_dots(sig, close)``.  Measured on
2026-08-15 over ``data/stocks``: NVDA 136 uncapped dots vs the fixture's 40;
last-40-of-uncapped ``!=`` the fixture on all three names, while the emitter's own
side channel matches all three exactly.  :func:`run_name` therefore returns BOTH —
``dots`` (uncapped, the population every outcome attaches to) and
``dots_side_channel`` (the emitter's own capped list) — and G-5 compares the
side channel, because that is the field the fixture actually froze.

NO NETWORK, NO REPO WRITES.  ``git archive`` reads the Terminal repo; the export
lands wherever the caller points ``dest`` (the runner passes a scratchpad path).
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
# UNCONDITIONAL, position 0 — the house strong-pin idiom
# (tests/test_check_script_import_pinning.py); `python3 scripts/…` otherwise runs
# with scripts/ on sys.path and no repo root at all.
sys.path.insert(0, str(REPO_ROOT))

from engine.entry_radar.replay import prereg  # noqa: E402

#: Where the Terminal repo lives when the environment does not say otherwise.
DEFAULT_TERMINAL_REPO = "/Users/chriswong/Documents/Cluade/charting-app"

#: The one subtree staged.  Narrow on purpose: the emitter is what is pinned, and
#: exporting the whole repo would invite a second Terminal import surface.
STAGED_SUBTREE = "signal_layer"

#: The W2 fixture names G-5 grades against (tests/fixtures/entry_radar/<T>.slice.json).
FIXTURE_NAMES = ("NVDA", "NFLX", "TSLA")


class StagingError(RuntimeError):
    """The pin is unreachable, the export failed, or the staged tree is wrong."""


def terminal_repo_path(terminal_repo: str | Path | None = None) -> Path:
    """``MACRO_TERMINAL_REPO`` > the house default.  Read lazily, never at import."""
    if terminal_repo:
        return Path(terminal_repo)
    return Path(os.environ.get("MACRO_TERMINAL_REPO") or DEFAULT_TERMINAL_REPO)


# --------------------------------------------------------------------------- #
# staging
# --------------------------------------------------------------------------- #
def stage(pin: str = prereg.TERMINAL_PIN, *,
          terminal_repo: str | Path | None = None,
          dest: str | Path) -> Path:
    """``git -C <repo> archive <pin> signal_layer | tar -x -C dest``.

    Refuses (rather than falling back to HEAD, or to a nearby tag) when the pin is
    not a reachable commit in the Terminal repo: a G0 population emitted by an
    unpinned emitter is not the population §1 registered a spec hash for.

    Returns the directory that CONTAINS ``signal_layer`` — i.e. what goes on
    ``sys.path``.
    """
    repo = terminal_repo_path(terminal_repo)
    if not (repo / ".git").exists() and not repo.is_dir():
        raise StagingError(f"terminal repo {repo} does not exist "
                           f"(set MACRO_TERMINAL_REPO)")
    probe = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{pin}^{{commit}}"],
                           capture_output=True, text=True)
    if probe.returncode != 0:
        raise StagingError(
            f"pin {pin} is not a reachable commit in {repo} "
            f"({(probe.stderr or '').strip()}); the A5.6 emitter cannot be staged")

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    archive = subprocess.run(["git", "-C", str(repo), "archive", pin, STAGED_SUBTREE],
                             capture_output=True)
    if archive.returncode != 0:
        raise StagingError(f"git archive {pin} {STAGED_SUBTREE} failed: "
                           f"{archive.stderr.decode('utf-8', 'replace').strip()}")
    extract = subprocess.run(["tar", "-x", "-C", str(dest)], input=archive.stdout,
                             capture_output=True)
    if extract.returncode != 0:
        raise StagingError(f"tar -x into {dest} failed: "
                           f"{extract.stderr.decode('utf-8', 'replace').strip()}")
    init = dest / STAGED_SUBTREE / "__init__.py"
    if not init.exists():
        raise StagingError(f"staged tree {dest} carries no {STAGED_SUBTREE}/__init__.py")
    return dest


@contextmanager
def staged_signal_layer(staged_dir: str | Path) -> Iterator[tuple[Any, Any]]:
    """Import the STAGED ``signal_layer`` in isolation, then put ``sys`` back.

    Three things happen in order, and all three matter:

    1. Any ``signal_layer*`` already in ``sys.modules`` is set aside — otherwise a
       second call in the same process would silently reuse the first import and
       a fidelity report could be produced by a tree nobody staged.
    2. The staged directory goes on ``sys.path[0]`` and the modules are imported.
       Their ``__file__`` is then CHECKED to be under ``staged_dir``: an import
       that resolved elsewhere is a staging failure, not a warning.
    3. The path entry and the module table are restored in a ``finally``, so a
       raising body cannot leave the interpreter pointing at the export.
    """
    staged = Path(staged_dir).resolve()
    saved = {k: v for k, v in sys.modules.items()
             if k == STAGED_SUBTREE or k.startswith(STAGED_SUBTREE + ".")}
    for key in saved:
        del sys.modules[key]
    sys.path.insert(0, str(staged))
    try:
        importlib.invalidate_caches()
        confluence = importlib.import_module(f"{STAGED_SUBTREE}.confluence")
        confluence_v2 = importlib.import_module(f"{STAGED_SUBTREE}.confluence_v2")
        for module in (confluence, confluence_v2):
            where = Path(getattr(module, "__file__", "") or "").resolve()
            if staged not in where.parents:
                raise StagingError(
                    f"{module.__name__} imported from {where}, not from the staged "
                    f"tree {staged}; the emitter under test is not the pinned one")
        yield confluence, confluence_v2
    finally:
        for key in [k for k in list(sys.modules)
                    if k == STAGED_SUBTREE or k.startswith(STAGED_SUBTREE + ".")]:
            del sys.modules[key]
        sys.modules.update(saved)
        try:
            sys.path.remove(str(staged))
        except ValueError:  # pragma: no cover — another actor cleaned it
            pass


# --------------------------------------------------------------------------- #
# running one name
# --------------------------------------------------------------------------- #
def _aligned(series: pd.Series | None, index: pd.Index) -> pd.Series | None:
    if series is None:
        return None
    out = pd.Series(pd.to_numeric(pd.Series(series).to_numpy(), errors="coerce"),
                    index=index, dtype=float)
    return out


def run_name(staged_dir: str | Path, ticker: str, close: pd.Series, *,
             high: pd.Series | None = None, low: pd.Series | None = None,
             volume: pd.Series | None = None) -> dict[str, Any]:
    """Run the staged emitter on one name's daily close series.

    Returns::

        {"dots": [{"ts", "known_ts"}, ...],   # UNCAPPED §3.1 population
         "dots_side_channel": [ts, ...],      # build_v2's own capped display list
         "watches": [<bottom_watch>, ...],    # verbatim: ts/known_ts/kind/quality/...
         "n_sessions": int,
         "score_basis": "full"|"partial"}

    ``dots`` carries ``known_ts`` because the G0 decision clock is ``known_ts``,
    never ``ts`` (§3): ``ts`` is the 3D bar's OPEN date and the value only became
    observable at the bar's last session.  The join is by 3D-bar-open date against
    ``sig["known_ts"]``, which is the column ``compute_signals`` builds for exactly
    this question (``confluence.py:240-250`` @ the pin).

    ``watches`` is passed through UNTOUCHED.  Those dicts already carry
    ``ts/known_ts/kind/quality/price/scored/washout_ctx/...``; re-shaping them here
    would put a second definition of a C5 event in Macro, which §3 forbids.
    """
    close = pd.Series(pd.to_numeric(pd.Series(close).to_numpy(), errors="coerce"),
                      index=pd.DatetimeIndex(pd.Series(close).index), dtype=float)
    close = close.dropna().sort_index()
    high = _aligned(high, close.index) if high is not None else None
    low = _aligned(low, close.index) if low is not None else None
    volume = _aligned(volume, close.index) if volume is not None else None

    with staged_signal_layer(staged_dir) as (confluence, confluence_v2):
        sig = confluence.compute_signals(close)
        dot_dates: Sequence[str] = confluence_v2.early_dots(sig, close)
        known = _known_ts_lookup(sig)
        dots = [{"ts": ts, "known_ts": known.get(ts)} for ts in dot_dates]
        v2 = confluence_v2.build_v2(sig, close, high=high, low=low, volume=volume,
                                    symbol=ticker)
    return {
        "ticker": ticker,
        "dots": dots,
        "dots_side_channel": list(v2.get("early_dots") or []),
        "watches": list(v2.get("bottom_watches") or []),
        "n_sessions": int(len(close)),
        "score_basis": str(v2.get("score_basis") or ""),
    }


def _known_ts_lookup(sig: pd.DataFrame) -> dict[str, str | None]:
    """3D-bar-open date -> its ``known_ts`` date, both as ``YYYY-MM-DD``.

    A frame with no ``known_ts`` column (a legacy emitter) maps every bar to its
    own open date, which is the fallback ``contracts._extract_signals`` uses at the
    pin — stated rather than silently returning None, because a None known_ts is
    a REFUSAL downstream (§3: a watch/dot with no decision clock is counted as a
    refusal, never dated from ``ts``).
    """
    if sig is None or not len(sig):
        return {}
    index = pd.DatetimeIndex(sig.index)
    if "known_ts" not in sig.columns:
        return {d.strftime("%Y-%m-%d"): d.strftime("%Y-%m-%d") for d in index}
    out: dict[str, str | None] = {}
    for when, value in zip(index, sig["known_ts"]):
        key = when.strftime("%Y-%m-%d")
        out[key] = (None if value is None or pd.isna(value)
                    else pd.Timestamp(value).strftime("%Y-%m-%d"))
    return out


# --------------------------------------------------------------------------- #
# G-5 evidence
# --------------------------------------------------------------------------- #
def _curated_frame(root: Path, ticker: str) -> pd.DataFrame:
    path = root / "data" / "stocks" / f"{ticker}.parquet"
    if not path.exists():
        raise StagingError(f"fixture name {ticker} has no curated store at {path}")
    frame = pd.read_parquet(path)
    frame.index = pd.DatetimeIndex(frame.index).normalize()
    return frame.sort_index()


def fixture_fidelity(staged_dir: str | Path, *, root: str | Path | None = None,
                     pin: str = prereg.TERMINAL_PIN,
                     names: Sequence[str] = FIXTURE_NAMES) -> dict[str, Any]:
    """§14 G-5 evidence: does the staged emitter reproduce the W2 fixtures?

    Per name, on the curated ``data/stocks/<T>.parquet`` closes (+high/low/volume):

    * (a) the emitter's ``early_dots`` side channel must equal the fixture's
      ``indicator.early_dots`` list EXACTLY (order included) — see the module
      docstring for why the operand is the side channel and not the last 40 of the
      uncapped population;
    * (b) the ``(ts, kind)`` set of ``bottom_watches`` must equal the fixture's
      ``(ts, subtype)`` set over ``indicator.signals`` rows of type
      ``BOTTOM_WATCH`` — ``kind`` on the emitter side is what ``contracts`` stamps
      as ``subtype`` on the artifact side (``contracts.py`` @ the pin).

    The returned shape is what ``gates.check_staging_fidelity`` consumes:
    ``{"terminal_pin": <sha>, "fixtures": {<name>: {"match": bool, ...counts}}}``.
    """
    root = Path(root) if root is not None else REPO_ROOT
    fixtures_dir = root / "tests" / "fixtures" / "entry_radar"
    report: dict[str, Any] = {"terminal_pin": pin, "fixtures": {}}
    for ticker in names:
        fixture_path = fixtures_dir / f"{ticker}.slice.json"
        if not fixture_path.exists():
            report["fixtures"][ticker] = {"match": False,
                                          "reason": f"missing fixture {fixture_path}"}
            continue
        doc = json.loads(fixture_path.read_text(encoding="utf-8")).get("indicator") or {}
        want_dots = list(doc.get("early_dots") or [])
        want_watches = {(str(s.get("ts")), str(s.get("subtype")))
                        for s in (doc.get("signals") or [])
                        if s.get("type") == "BOTTOM_WATCH"}

        frame = _curated_frame(root, ticker)
        out = run_name(staged_dir, ticker, frame["close"],
                       high=frame.get("high"), low=frame.get("low"),
                       volume=frame.get("volume"))
        got_dots = list(out["dots_side_channel"])
        got_watches = {(str(w.get("ts")), str(w.get("kind"))) for w in out["watches"]}

        dots_match = got_dots == want_dots
        watch_match = got_watches == want_watches
        report["fixtures"][ticker] = {
            "match": bool(dots_match and watch_match),
            "dots_match": bool(dots_match),
            "watches_match": bool(watch_match),
            "dots_expected": len(want_dots),
            "dots_got": len(got_dots),
            "dots_population_uncapped": len(out["dots"]),
            "watches_expected": len(want_watches),
            "watches_got": len(got_watches),
            "n_sessions": out["n_sessions"],
            "dots_only_in_run": sorted(set(got_dots) - set(want_dots))[:5],
            "dots_only_in_fixture": sorted(set(want_dots) - set(got_dots))[:5],
            "watches_only_in_run": sorted(got_watches - want_watches)[:5],
            "watches_only_in_fixture": sorted(want_watches - got_watches)[:5],
        }
    return report


# --------------------------------------------------------------------------- #
# panel-scale table emission (the replay's G0/C5 population source)
# --------------------------------------------------------------------------- #
def _emit_one(job: tuple[str, str, str, str]) -> tuple[str, str]:
    """Worker: run the staged emitter on one name's cached closes -> JSON table.

    Returns (ticker, status).  The vendor plane's ``c`` column is the §3/§4
    substrate for Panel-B (basis-variant, radar_derived, disclosed); a missing
    or short cache file is a recorded refusal, never a fabricated table.
    """
    staged_dir, ticker, cache_dir, out_dir = job
    import pandas as pd  # noqa: PLC0415 — worker process import

    src = Path(cache_dir) / "vendor_daily" / f"{ticker}.parquet"
    if not src.exists():
        return ticker, "refused:no_daily_cache"
    try:
        frame = pd.read_parquet(src)
        close = frame["c"].dropna()
        if len(close) < 120:
            return ticker, "refused:history_short"
        table = run_name(staged_dir, ticker, close,
                         high=frame.get("h"), low=frame.get("l"),
                         volume=frame.get("v"))
        payload = {
            "ticker": ticker, "terminal_pin": prereg.TERMINAL_PIN,
            "price_basis": "vendor_adjusted_split_only",
            "n_sessions": int(table.get("n_sessions") or len(close)),
            "dots": table.get("dots") or [],
            "watches": table.get("watches") or [],
        }
        out = Path(out_dir) / f"{ticker}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload), encoding="utf-8")
        return ticker, "ok"
    except Exception as exc:  # noqa: BLE001 — one bad name never sinks the panel
        return ticker, f"refused:{type(exc).__name__}"


def emit_tables(staged_dir: str | Path, names: Sequence[str], *,
                cache_dir: str | Path, workers: int = 6) -> dict[str, str]:
    """Run the staged emitter across ``names`` -> ``<cache>/staged_tables/*.json``.

    A manifest (``_manifest.json``) records the pin, per-name status, and counts
    so the §13 row-14 census can name every non-emitted table.  Already-emitted
    tables are kept (idempotent resume).
    """
    from concurrent.futures import ProcessPoolExecutor  # noqa: PLC0415

    out_dir = Path(cache_dir) / "staged_tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    todo, statuses = [], {}
    for t in names:
        if (out_dir / f"{t}.json").exists():
            statuses[t] = "cached"
            continue
        todo.append((str(staged_dir), t, str(cache_dir), str(out_dir)))
    if todo:
        with ProcessPoolExecutor(max_workers=max(1, workers)) as ex:
            for ticker, status in ex.map(_emit_one, todo):
                statuses[ticker] = status
    counts: dict[str, int] = {}
    for s in statuses.values():
        counts[s.split(":")[0]] = counts.get(s.split(":")[0], 0) + 1
    (out_dir / "_manifest.json").write_text(json.dumps({
        "terminal_pin": prereg.TERMINAL_PIN, "n": len(statuses),
        "counts": counts, "statuses": statuses}), encoding="utf-8")
    return statuses


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fidelity", action="store_true",
                        help="stage the pin and print the §14 G-5 fidelity report")
    parser.add_argument("--emit-tables", action="store_true",
                        help="run the staged emitter across a panel into the cache")
    parser.add_argument("--cache-dir", default=None,
                        help="vendor cache dir (required with --emit-tables)")
    parser.add_argument("--names-file", default=None,
                        help="one ticker per line; default = data/universe/membership.parquet")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--pin", default=prereg.TERMINAL_PIN)
    parser.add_argument("--terminal-repo", default=None)
    parser.add_argument("--dest", default=None,
                        help="staging directory (default: a temp dir, removed after)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    if args.emit_tables:
        if not args.cache_dir:
            parser.error("--emit-tables requires --cache-dir")
        if args.names_file:
            names = [ln.strip() for ln in Path(args.names_file).read_text().splitlines()
                     if ln.strip()]
        else:
            import pandas as pd  # noqa: PLC0415
            mem = pd.read_parquet(REPO_ROOT / "data/universe/membership.parquet")
            names = sorted(set(mem["ticker"].astype(str)))
        tmp2: tempfile.TemporaryDirectory | None = None
        if args.dest:
            dest2 = Path(args.dest)
        else:
            tmp2 = tempfile.TemporaryDirectory(prefix="entry_radar_stage_")
            dest2 = Path(tmp2.name)
        try:
            staged = stage(args.pin, terminal_repo=args.terminal_repo, dest=dest2)
            statuses = emit_tables(staged, names, cache_dir=args.cache_dir,
                                   workers=args.workers)
        finally:
            if tmp2 is not None:
                tmp2.cleanup()
        ok = sum(1 for s in statuses.values() if s in ("ok", "cached"))
        print(f"emit-tables: {ok}/{len(statuses)} tables present "
              f"({len(statuses) - ok} refused; see staged_tables/_manifest.json)",
              flush=True)
        return 0

    if not args.fidelity:
        parser.error("nothing to do — pass --fidelity or --emit-tables")

    tmp: tempfile.TemporaryDirectory | None = None
    if args.dest:
        dest = Path(args.dest)
    else:
        tmp = tempfile.TemporaryDirectory(prefix="entry_radar_stage_")
        dest = Path(tmp.name)
    try:
        staged = stage(args.pin, terminal_repo=args.terminal_repo, dest=dest)
        report = fixture_fidelity(staged, pin=args.pin)
    finally:
        if tmp is not None:
            tmp.cleanup()

    ok = all(bool(r.get("match")) for r in report["fixtures"].values())
    if args.json:
        # PURE JSON on stdout — the replay runner parses this file/stream, and a
        # trailing human summary line would corrupt it (measured: "Extra data").
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if ok else 1
    print(f"G-5 staging fidelity — terminal_pin {report['terminal_pin']}")
    for name, row in report["fixtures"].items():
        print(f"  {name:<6} match={str(row.get('match')).lower():<5} "
              f"dots {row.get('dots_got')}/{row.get('dots_expected')} "
              f"(population {row.get('dots_population_uncapped')}) "
              f"watches {row.get('watches_got')}/{row.get('watches_expected')} "
              f"sessions {row.get('n_sessions')}")
    print(f"G-5: {'PASS' if ok else 'REFUSE'} "
          f"({sum(1 for r in report['fixtures'].values() if r.get('match'))}"
          f"/{len(report['fixtures'])} fixtures)")
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
