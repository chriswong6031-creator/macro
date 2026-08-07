#!/usr/bin/env python3
"""Freeze the coupled 2026-07-31 vintage the Prophet postmortem's G1 loser cohort names.

WHY A FROZEN SLICE AND NOT A DATE PIN (2026-08-06)
--------------------------------------------------------------------------------------
`tests/test_prophet_postmortem.py::TestLoserCohortFixture` pins `LOSER_COHORT` — the
operator's eleven worst rows from the 2026-07-31 track record (masterplan §0 G1) — and
asserts each one lands in the `loser` cohort of a LIVE recomputation over the committed
ledgers. On 2026-08-06 three of its tests went red with nobody's diff to blame:

    FN@2026-07-21 regraded loser -> neutral

Measured, not guessed. FN was admitted on the 07-21 board and filled 07-22 at 513.67.
At the 07-31 tape its 10-session window had SEVEN sessions on it, so the episode was
`in_flight` and marked to the last close, 435.41 — a -15.24% mark, comfortably inside
the -8% loser gate. `collect` kept committing prices while the grading lane was dark, so
the cache now runs to 08-06; the window closes at 08-05 (522.22) and the episode MATURES
at +1.66%. A 17pp swing in four sessions, with no code change anywhere.

That is not drift and not a regression. It is the arithmetic of the cohort itself:

    FIVE of the eleven names — OLN, AMKR, FN, UNIT, BG — are IN-FLIGHT at 2026-07-31.
    Their `loser` status is a MARK-TO-MARKET, i.e. a statement about one tape date.

A mark moves every session by construction, so any pin that lets prices advance re-rots
on a schedule. FN went first; BG@2026-07-17 is next with 3.84pp of margin to the gate.
Re-pinning LOSER_COHORT to today's recomputation is therefore the trap, not the fix: it
would silently DROP FN from the operator's own §0 G1 list (making the gate weaker than
the thing it exists to enforce) and go red again at the next resolution.

Nor does clipping the grading date work — the same lesson #4763 learned for the exit
policy study, and here there are THREE moving inputs behind one clip:

  * FRONTIER — the price caches advance nightly (the movement above).
  * VINTAGE  — `collect` RE-ADJUSTS historical closes in place on every new ex-date
    (#4763 measured 240 re-adjusted closes across 12 dividend names, 0.56..1.18%).
    Those survive ANY date clip.
  * LEDGER   — `data/us_board_ledger/retro_grades.parquet` is REWRITTEN IN PLACE by the
    regime lane every night (last written 08-06 though its newest board date is 07-28),
    and `snapshots.jsonl` will start appending board days again the moment the dark
    grading lane restores, moving the episode set and `as_of = max(days)`.

So the cohort is pinned against a frozen INPUT SLICE at a COUPLED vintage: commit
d29e4dd44da ("engine: regime update 2026-08-01"), the last commit at which the board
snapshots, the retro ledger, the baskets and the price caches were all written by ONE
nightly run. At that vintage all eleven names grade `loser` and the reconstruction is
reproducible forever, because none of its inputs can move again.

The slice is ROOT-SHAPED, so `load_closes`, `load_snapshots`, `load_retro`,
`close_resolver`, `membership_map` and `build_rows` exercise the real production loaders
unmodified — a fixture that reimplemented the loaders would prove nothing about them.

WHAT THIS SCRIPT REFUSES TO DO
--------------------------------------------------------------------------------------
It rebuilds the full artifact twice — once from the untrimmed vintage checkout, once
from the trimmed slice it just wrote — and REFUSES to leave a slice in place that does
not reproduce the reference artifact key-for-key. That guard is what licenses the
aggressive trimming below (17.6 MiB of board snapshots down to the fields
`engine.postmortem.entry_context` actually reads): a field dropped by mistake changes
the artifact, and a changed artifact fails the write.

Usage::

    python3 scripts/build_prophet_postmortem_vintage_fixture.py          # rebuild
    python3 scripts/build_prophet_postmortem_vintage_fixture.py --check  # verify only
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from scripts import prophet_postmortem as ppm  # noqa: E402

#: The coupled vintage. See the module docstring for why this specific commit.
VINTAGE_REF = "d29e4dd44daa212da89e24541f45e2aa0fb582e3"
VINTAGE_ASOF = "2026-07-31"

FIXTURE_REL = Path("tests/fixtures/prophet_postmortem_vintage")

#: Inputs lifted verbatim from the vintage commit before trimming.
VINTAGE_FILES = [
    "data/breadth/_closes_cache.parquet",
    "data/smallcap_breadth/_closes_cache.parquet",
    "data/midcap_breadth/_closes_cache.parquet",
    "data/russell_breadth/_closes_cache.parquet",
    "data/yahoo/SPY.parquet",
    "data/us_board_ledger/retro_grades.parquet",
    "data/us_board_ledger/snapshots.jsonl",
    "data/baskets/latest.json",
    "data/baskets/membership.json",
    "data/baskets/extras.parquet",
]

#: Files small enough to carry whole. Trimming them would buy kilobytes and cost the
#: ability to say the slice IS the vintage for these inputs.
COPY_WHOLE = [
    "data/us_board_ledger/retro_grades.parquet",
    "data/baskets/membership.json",
]

#: Price panels are cut to sessions from here forward. The first board date is
#: 2026-06-15 and the horizon is ten sessions, so this leaves ~115 sessions of lead-in
#: before any episode opens — far more than the fill bar and path window need, and
#: enough that a name whose store went stale mid-window still presents a NON-empty
#: series (the `U` case: a stale STORE must stay distinguishable from a missing NAME,
#: and an over-tight floor would silently reclassify one as the other). The floor is
#: safe to move only in the direction the reproduction guard accepts.
PRICE_FLOOR = "2026-01-02"

#: The board-snapshot fields `engine.postmortem.entry_context` and
#: `scripts.prophet_postmortem._hold_broken` actually read. Everything else on a lane row
#: — `spark_svg`, `dossier`, `gex_confirm`, `sector_pulse`, ... — is board render payload
#: this study never touches, and is 93% of the file. A nested True keeps the whole
#: sub-tree; a dict recurses. Completeness is PROVEN by the reproduction guard, not by
#: this comment: drop a field that matters and the artifact changes and the write fails.
SNAPSHOT_KEEP: dict = {
    "ticker": True,
    "sector": True,
    "price": True,
    "ext_z": True,
    "off_high": True,
    "alpha": True,
    "align_tier": True,
    "urgency": True,
    "state": True,
    "conviction": {
        "band": True,
        "score": True,
        "composite_z": True,
        "spotlight": {"dir": True, "z": True, "sector": True, "theme": True},
        "alignment": {"overextended": True, "entry_tier": True},
        "risk": {"components": True},
    },
    "entry_signal": {
        "spot": True, "chase_above": True, "status": True, "stop": True, "atr_pct": True,
    },
    "hold": {"invalidation": True, "state": True},
    "signal": {"fresh_bars": True},
}

#: Lane arrays `load_snapshots` walks, plus the date key it buckets on.
SNAPSHOT_LANES = ("buy", "watch", "leaders", "laggards")


# --------------------------------------------------------------------------- #
# vintage checkout
# --------------------------------------------------------------------------- #
def _git(args: list[str], *, binary: bool = False):
    proc = subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                          text=not binary, check=False)
    if proc.returncode != 0:
        return None
    return proc.stdout


def materialise_vintage(dest: Path) -> None:
    """Lay the vintage commit's inputs out as a root, untrimmed."""
    if _git(["cat-file", "-e", f"{VINTAGE_REF}^{{commit}}"]) is None:
        raise SystemExit(
            f"vintage commit {VINTAGE_REF[:12]} is not in this checkout. It is an "
            "ordinary main-line commit; fetch full history (`git fetch --unshallow`) "
            "and re-run."
        )
    for rel in VINTAGE_FILES:
        blob = _git(["show", f"{VINTAGE_REF}:{rel}"], binary=True)
        if blob is None:
            print(f"  · absent at the vintage, skipped: {rel}")
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)

    # Per-ticker OHLCV is the ladder's second rung; only a handful of names ever reach
    # it, but which names is a property of the vintage, so take the whole directory
    # listing and let the slice step keep the ones the run actually opened.
    listing = _git(["ls-tree", "--name-only", VINTAGE_REF,
                    f"{ppm.BASKET_OHLCV_REL}/"]) or ""
    ohlcv = [ln.strip() for ln in listing.splitlines() if ln.strip().endswith(".parquet")]
    print(f"  · {len(ohlcv)} ohlcv files at the vintage")
    for rel in ohlcv:
        blob = _git(["show", f"{VINTAGE_REF}:{rel}"], binary=True)
        if blob is None:
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)


def archaeology_snapshot(dest: Path) -> int:
    """Freeze `basket_history` AS OF the vintage commit into the slice.

    Walked with `git log <VINTAGE_REF> --` rather than plain `git log`, so a basket
    revision committed AFTER the vintage cannot leak into a run that claims to be
    reconstructing 2026-07-31. Mirrors `ppm.basket_history`'s newest-blob-per-as_of rule.
    """
    shas = (_git(["log", "--format=%H", VINTAGE_REF, "--", str(ppm.BASKETS_REL)])
            or "").split()
    by_asof: dict[str, dict] = {}
    for sha in shas:                                   # newest first
        blob = _git(["show", f"{sha}:{ppm.BASKETS_REL}"])
        if not blob:
            continue
        try:
            doc = json.loads(blob)
        except json.JSONDecodeError:
            continue
        asof = str(doc.get("as_of") or "")
        if not asof or asof in by_asof:
            continue
        themes = {str(t.get("id")): t for t in (doc.get("themes") or [])
                  if isinstance(t, dict) and t.get("id")}
        if themes:
            by_asof[asof] = themes
    if not by_asof:
        raise SystemExit("no basket revisions found at the vintage — refusing to write "
                         "a slice whose theme context would be empty.")
    out = dest / ppm.BASKET_HISTORY_SNAPSHOT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"_comment": ("Frozen `scripts.prophet_postmortem.basket_history` output at "
                          f"{VINTAGE_REF[:12]}. Fixture-only — a live data/ tree never "
                          "carries this file. Regenerate with "
                          "scripts/build_prophet_postmortem_vintage_fixture.py."),
             "vintage_ref": VINTAGE_REF,
             "revisions": [{"as_of": a, "themes": t} for a, t in sorted(by_asof.items())]},
            ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8")
    return len(by_asof)


# --------------------------------------------------------------------------- #
# trimming
# --------------------------------------------------------------------------- #
def _prune(node, keep):
    if keep is True or not isinstance(node, dict) or not isinstance(keep, dict):
        return node
    return {k: _prune(v, keep[k]) for k, v in node.items() if k in keep}


def trim_snapshots(src: Path, dst: Path) -> tuple[int, int]:
    """Keep every lane row, but only the fields the study reads.

    Rows are kept for EVERY ticker, not just cohort names: `load_snapshots` buckets all
    four lanes so `thesis_break` can follow a name after it drops out of `buy`, and
    `board_days` derives episode membership from the buy lane. Filtering rows would
    change the episode set; filtering fields does not.
    """
    lines_out, rows_out = [], 0
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        doc = json.loads(line)
        slim = {"as_of": doc.get("as_of")}
        for lane in SNAPSHOT_LANES:
            rows = doc.get(lane)
            if not rows:
                continue
            slim[lane] = [_prune(r, SNAPSHOT_KEEP) for r in rows]
            rows_out += len(slim[lane])
        lines_out.append(json.dumps(slim, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")))
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    return len(lines_out), rows_out


def _clip_rows(frame: pd.DataFrame) -> pd.DataFrame:
    idx = pd.to_datetime(frame.index)
    return frame.loc[idx >= pd.Timestamp(PRICE_FLOOR)]


def trim_closes(src_root: Path, dst_root: Path, tickers: set[str]) -> dict[str, int]:
    """Keep each cache's own columns, intersected with the names the study scores.

    Per-group and never merged: `load_closes` is first-hit-wins across the groups in
    order, so a ticker moved between caches would resolve to a different series here
    than the stock library resolves it to. Keeping each name in the group it actually
    lives in preserves that precedence exactly.
    """
    kept = {}
    for grp in ppm.CLOSE_CACHE_GROUPS:
        rel = f"data/{grp}/_closes_cache.parquet"
        src = src_root / rel
        if not src.exists():
            continue
        frame = pd.read_parquet(src)
        cols = [c for c in frame.columns if str(c) in tickers]
        if not cols:
            continue
        dst = dst_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        _clip_rows(frame[cols]).to_parquet(dst)
        kept[grp] = len(cols)
    return kept


def trim_bench(src_root: Path, dst_root: Path) -> None:
    src = src_root / ppm.BENCH_REL
    if not src.exists():
        return
    dst = dst_root / ppm.BENCH_REL
    dst.parent.mkdir(parents=True, exist_ok=True)
    _clip_rows(pd.read_parquet(src)).to_parquet(dst)


def trim_ohlcv(src_root: Path, dst_root: Path, tickers: set[str]) -> None:
    for tk in sorted(tickers):
        src = src_root / ppm.BASKET_OHLCV_REL / f"{tk}.parquet"
        if not src.exists():
            continue
        dst = dst_root / ppm.BASKET_OHLCV_REL / f"{tk}.parquet"
        dst.parent.mkdir(parents=True, exist_ok=True)
        _clip_rows(pd.read_parquet(src)).to_parquet(dst)


def trim_extras(src_root: Path, dst_root: Path, tickers: set[str]) -> int:
    """The third rung, carried ONLY for names that actually reach it.

    At this vintage nothing does — every episode resolves off a cache or off
    `baskets/ohlcv` — so shipping the panel would be 1.7 MiB of input no code path
    reads. `_from_extras` treats an absent file exactly as it treats a missing column
    (a miss, not a crash), and the reproduction guard proves the omission changes
    nothing. If a future vintage does reach this rung, the names land here.
    """
    src = src_root / ppm.BASKET_EXTRAS_REL
    if not src.exists() or not tickers:
        return 0
    frame = pd.read_parquet(src)
    cols = [c for c in frame.columns if str(c) in tickers]
    if not cols:
        return 0
    dst = dst_root / ppm.BASKET_EXTRAS_REL
    dst.parent.mkdir(parents=True, exist_ok=True)
    _clip_rows(frame[cols]).to_parquet(dst)
    return len(cols)


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def _episode_tickers(doc: dict) -> set[str]:
    return {str(r["ticker"]) for r in doc["episodes"]}


def _rung_tickers(root: Path, doc: dict) -> tuple[set[str], set[str]]:
    """Which names the ladder resolved off each FALLBACK rung, at this vintage."""
    resolve = ppm.close_resolver(root, ppm.load_closes(root))
    ohlcv, extras = set(), set()
    for tk in _episode_tickers(doc):
        _, source = resolve(tk)
        if source == ppm.SOURCE_BASKET_OHLCV:
            ohlcv.add(tk)
        elif source == ppm.SOURCE_BASKET_EXTRAS:
            extras.add(tk)
    return ohlcv, extras


def _dir_bytes(path: Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _first_difference(a, b, trail: str = "") -> str | None:
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                return f"{trail}.{k}: absent in reference, present in slice"
            if k not in b:
                return f"{trail}.{k}: present in reference, absent in slice"
            d = _first_difference(a[k], b[k], f"{trail}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return f"{trail}: {len(a)} entries in reference, {len(b)} in slice"
        for i, (x, y) in enumerate(zip(a, b)):
            d = _first_difference(x, y, f"{trail}[{i}]")
            if d:
                return d
        return None
    if a != b:
        return f"{trail}: reference={a!r} slice={b!r}"
    return None


def build(check_only: bool) -> int:
    fixture = ROOT / FIXTURE_REL
    if check_only and not fixture.exists():
        raise SystemExit(f"{FIXTURE_REL} does not exist — run without --check first.")

    staging = Path(tempfile.mkdtemp(prefix="ppm-vintage-"))
    try:
        if check_only:
            print(f"verifying {FIXTURE_REL} reproduces the vintage artifact")
        else:
            print(f"materialising vintage {VINTAGE_REF[:12]} ({VINTAGE_ASOF})")
        materialise_vintage(staging)
        n_rev = archaeology_snapshot(staging)
        print(f"  · {n_rev} basket revisions frozen")

        print("building the REFERENCE artifact from the untrimmed vintage")
        reference = ppm.build_rows(staging)
        tickers = _episode_tickers(reference)
        ohlcv_names, extras_names = _rung_tickers(staging, reference)
        print(f"  · as_of={reference['as_of']} "
              f"episodes={reference['coverage']['n_episodes']} "
              f"tickers={len(tickers)} "
              f"losers={reference['summary']['cohorts']['n_losers']}")
        print(f"  · ladder rungs: ohlcv={sorted(ohlcv_names)} "
              f"extras={sorted(extras_names)}")

        # ---- assemble the slice ------------------------------------------------
        slice_dir = Path(tempfile.mkdtemp(prefix="ppm-slice-"))
        for rel in COPY_WHOLE:
            src = staging / rel
            if src.exists():
                (slice_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, slice_dir / rel)
        shutil.copy2(staging / ppm.BASKET_HISTORY_SNAPSHOT_REL,
                     _mk(slice_dir / ppm.BASKET_HISTORY_SNAPSHOT_REL))
        n_lines, n_rows = trim_snapshots(
            staging / ppm.SNAPSHOTS_REL, slice_dir / ppm.SNAPSHOTS_REL)
        kept_cols = trim_closes(staging, slice_dir, tickers)
        trim_bench(staging, slice_dir)
        trim_ohlcv(staging, slice_dir, ohlcv_names)
        n_extras = trim_extras(staging, slice_dir, extras_names)
        print(f"  · snapshots {n_lines} board nights / {n_rows} lane rows")
        print(f"  · closes {kept_cols}, extras cols {n_extras}, "
              f"ohlcv files {len(ohlcv_names)}, sessions from {PRICE_FLOOR}")

        # ---- the guard ---------------------------------------------------------
        print("rebuilding from the SLICE through the production loaders")
        rebuilt = ppm.build_rows(slice_dir)
        diff = _first_difference(reference, rebuilt)
        if diff is not None:
            raise SystemExit(
                "REFUSING to write the slice: it does not reproduce the vintage "
                f"artifact.\n  first difference: {diff}\n"
                "A trimmed input the study actually reads is the usual cause — widen "
                "SNAPSHOT_KEEP / the column filters rather than relaxing this check.")
        print("  · slice reproduces the reference artifact key-for-key")

        manifest = {
            "source_ref": VINTAGE_REF,
            "source_ref_short": VINTAGE_REF[:12],
            "vintage_as_of": VINTAGE_ASOF,
            "artifact_as_of": reference["as_of"],
            "priced_through": str(ppm.load_closes(slice_dir).index.max().date()),
            "board_dates": reference["coverage"]["board_dates"],
            "n_episodes": reference["coverage"]["n_episodes"],
            "n_tickers": len(tickers),
            "n_matured": reference["summary"]["n_matured"],
            "n_losers": reference["summary"]["cohorts"]["n_losers"],
            "n_winners": reference["summary"]["cohorts"]["n_winners"],
            "basket_revisions": reference["coverage"]["basket_revisions"],
            "snapshot_lane_rows": n_rows,
            "closes_columns": kept_cols,
            "ohlcv_fallback": sorted(ohlcv_names),
            "extras_fallback": sorted(extras_names),
            "regenerate_with": (
                "python3 scripts/build_prophet_postmortem_vintage_fixture.py"),
            "why": (
                "Five of the eleven G1 cohort names are IN-FLIGHT at 2026-07-31, so their "
                "`loser` status is a mark-to-market — a statement about one tape date. "
                "Any pin that lets prices advance re-rots by construction (FN did: "
                "-15.24% mark -> +1.66% matured in four sessions). Frozen at a COUPLED "
                "commit where snapshots, retro ledger, baskets and caches were all "
                "written by one nightly run. See the regenerator's module docstring."),
        }
        (slice_dir / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")

        if check_only:
            print(f"OK — {FIXTURE_REL} is reproducible ({_dir_bytes(slice_dir):,} bytes "
                  "rebuilt); nothing written.")
            return 0

        if fixture.exists():
            shutil.rmtree(fixture)
        shutil.copytree(slice_dir, fixture)
        print(f"wrote {FIXTURE_REL} ({_dir_bytes(fixture):,} bytes)")
        return 0
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _mk(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="rebuild and verify reproduction without writing the fixture")
    args = ap.parse_args()
    return build(args.check)


if __name__ == "__main__":
    raise SystemExit(main())
