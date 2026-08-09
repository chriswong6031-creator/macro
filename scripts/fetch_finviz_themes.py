"""Fetch the Finviz *themes* map snapshot (structure + per-timeframe performance).

Finviz's themes treemap (https://finviz.com/map?t=themes) is a curated
narrative-basket hierarchy: **theme → subsector → member tickers**. None of it
is a documented API, so this collector pulls the two feeds the page itself uses
and freezes them into a committed snapshot so the *build* (and CI) stays fully
offline:

* **Structure** — ``data/themes_heatmap/themes_tree.json`` (theme → subsector →
  members + descriptions). Lives in the repo; refreshed here only with
  ``--refresh-tree`` (it changes rarely and the source is a hash-rotated webpack
  chunk; see [[finviz-themes-map-extraction]]).
* **Performance** — ``/api/map_perf`` gives every subsector's % move for a given
  timeframe (the colour of each tile); ``/api/map_perf_screener`` gives the same
  per *member* ticker (the colour of each row in the hover popup). Both are
  pulled for all eight daily-group timeframes and written to
  ``data/themes_heatmap/perf_snapshot.json``.

The pure assembly (snapshot → the JSON the frontend reads) lives in
``engine/themes_heatmap.py``; the build wrapper is
``scripts/build_themes_heatmap.py``. This module is the only one that touches the
network.

PIT ARCHIVAL (added 2026-07-04, append-only, zero breaking changes):
* ``data/themes_heatmap/member_perf_history.jsonl`` — one line per NYSE **session**,
  compact JSON: {"asof": "YYYY-MM-DD", "subsectors": {...}, "members": {...}}.
  Idempotent: if the asof date already exists in the file the append is skipped.
  It used to be one line per CALENDAR day, which is not the same thing: daily.yml
  fires ~22:30 UTC every night INCLUDING weekends, and Finviz themes perf is EOD,
  so a Saturday and a Sunday run each re-fetched Friday's unchanged board and
  stamped it under a fresh weekend date. Stamping the SESSION (see ``_asof_stamp``)
  makes those re-fetches dedupe upstream — every downstream consumer of
  ``asof`` inherits the fix. It is also self-healing in the other direction: a
  Saturday fetch that follows a FAILED Friday fetch archives Friday's board under
  Friday, so the recovered day lands on the session it actually describes.
* ``data/themes_heatmap/tree_history.jsonl`` — one line per *change* in the tree,
  keyed by sha256(sort_keys JSON); appended only when the tree hash changes (or
  the file is empty). Format: {"asof": "YYYY-MM-DD", "sha256": "...", "tree": [...]}.

Staging note: daily.yml stages ``data/`` broadly (``git add data/``), so the two
new .jsonl files are picked up automatically — no workflow change needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# daily.yml runs this in FILE mode (``python scripts/fetch_finviz_themes.py``), so
# sys.path[0] is scripts/, NOT the repo root — and this module was stdlib-only until
# the session stamp below. Put ROOT on the path before the first ``lib`` import or
# the nightly dies on ImportError at collection time.
sys.path.insert(0, str(ROOT))

from lib import nyse_calendar  # noqa: E402 — must follow the sys.path bootstrap above

OUT_DIR = ROOT / "data" / "themes_heatmap"
TREE_PATH = OUT_DIR / "themes_tree.json"
PERF_PATH = OUT_DIR / "perf_snapshot.json"
SUBSECTOR_PERF_HISTORY_PATH = OUT_DIR / "subsector_perf_history.jsonl"
TREE_HISTORY_PATH = OUT_DIR / "tree_history.jsonl"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Finviz subtype code -> our timeframe key (matches the sp500 heatmap contract).
ST_TO_TF: dict[str, str] = {
    "d1": "1D", "w1": "1W", "w4": "1M", "mtd": "MTD",
    "w13": "3M", "w26": "6M", "w52": "1Y", "ytd": "YTD",
}


def _get(url: str, retries: int = 3, pause: float = 0.8) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    last = None
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001 - network is best-effort
            last = e
            time.sleep(pause * (i + 1))
    raise RuntimeError(f"GET failed after {retries}: {url} ({last})")


def fetch_subsector_perf() -> dict[str, dict[str, float]]:
    """{subsector_key: {tf: pct}} for every subsector, all timeframes."""
    out: dict[str, dict[str, float]] = {}
    for st, tf in ST_TO_TF.items():
        d = _get(f"https://finviz.com/api/map_perf?t=themes&st={st}")
        if d.get("subtype") != st:  # Finviz falls back to d1 on a bad code
            raise RuntimeError(f"subtype mismatch for {st!r}: got {d.get('subtype')!r}")
        for k, v in (d.get("nodes") or {}).items():
            out.setdefault(k, {})[tf] = round(float(v), 2)
        time.sleep(0.4)
    return out


def fetch_member_perf(tickers: list[str], chunk: int = 120) -> dict[str, dict[str, float]]:
    """{ticker: {tf: pct}} via the screener perf feed, batched by ticker."""
    out: dict[str, dict[str, float]] = {}
    uniq = sorted(set(tickers))
    batches = [uniq[i:i + chunk] for i in range(0, len(uniq), chunk)]
    for st, tf in ST_TO_TF.items():
        for batch in batches:
            q = urllib.parse.urlencode({"st": st, "t": ",".join(batch)})
            d = _get(f"https://finviz.com/api/map_perf_screener?{q}")
            for k, v in (d.get("nodes") or {}).items():
                if v is None:
                    continue
                out.setdefault(k, {})[tf] = round(float(v), 2)
            time.sleep(0.25)
    return out


def _asof_stamp(now_utc: datetime | None = None) -> str:
    """The NYSE SESSION this EOD board describes, as ``YYYY-MM-DD``.

    NOT the calendar day the fetch ran. daily.yml fires ~22:30 UTC every night
    including weekends and holidays, and Finviz themes perf is end-of-day, so a
    Saturday or Sunday run re-fetches Friday's UNCHANGED board. Stamped from the
    clock, each of those nights minted a fresh ``asof`` that no downstream dedup
    could recognise as a duplicate — ``build_subsector_rotation`` reads this field
    and hands it to ``engine.subsector_track_record.snapshot()``, whose (date,key)
    idempotency then saw a brand-new day and appended a full 269-row set, so
    ``compute()`` graded one Friday's calls as up to THREE independent IC days.

    ``session_date`` maps the instant to its ET-calendar session: a post-close
    weekday run stamps that weekday, a weekend/holiday run stamps the last
    completed session, and it is UTC-midnight-rollover safe (TS-R2).
    """
    return nyse_calendar.session_date(now_utc).isoformat()


# --------------------------------------------------------------------------- #
# PIT archival helpers (append-only; zero coupling to existing perf_snapshot)
# --------------------------------------------------------------------------- #

def _last_asof(path: Path) -> str | None:
    """asof of the LAST parseable non-empty line, or None.

    Dedup reads only the last line: the file is append-only with one line per
    day, so the newest asof is always last. A torn/partial trailing line (runner
    killed mid-append, disk-full) parses as garbage → None → the caller
    re-appends, so a torn line can never silently block a day's archival (it
    would be the exact permanent PIT loss this file exists to prevent). Readers
    of this file must skip unparseable lines for the same reason."""
    if not path.exists():
        return None
    last = None
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                last = line
    if last is None:
        return None
    try:
        return json.loads(last).get("asof")
    except Exception:  # noqa: BLE001 — torn line: treat the day as unarchived
        return None


def _last_line_hash(path: Path) -> str | None:
    """Return the sha256 field from the last non-empty line, or None."""
    if not path.exists():
        return None
    last = None
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                last = line
    if last is None:
        return None
    try:
        return json.loads(last).get("sha256")
    except Exception:  # noqa: BLE001
        return None


def _tree_hash(tree: list) -> str:
    return hashlib.sha256(json.dumps(tree, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _append_jsonl_line(p: Path, row: dict) -> None:
    """Append one JSON line, first terminating any torn trailing line.

    If a prior run died mid-append the file ends without a newline; appending
    directly would GLUE the new record onto the fragment and corrupt it too.
    Prepending a newline in that case seals the fragment as one bad (skippable)
    line and keeps every subsequent record parseable."""
    prefix = ""
    if p.exists() and p.stat().st_size > 0:
        with p.open("rb") as fh:
            fh.seek(-1, 2)
            if fh.read(1) != b"\n":
                prefix = "\n"
    with p.open("a") as fh:
        fh.write(prefix + json.dumps(row, separators=(",", ":")) + "\n")


def append_subsector_perf_history(
    asof: str,
    sub_perf: dict,
    path: Path | None = None,
) -> bool:
    """Append one line of Finviz SUBSECTOR-level perf to subsector_perf_history.jsonl.
    Returns True if written, False if skipped (asof already archived).

    Deliberately subsector-only (~15-20 KB/day, snapshots.jsonl-class): Finviz's
    subsector aggregates ride Finviz's FULL universe and cannot be rebuilt later —
    they are the irreplaceable PIT layer, together with the tree (below). The
    per-MEMBER perf is NOT archived: member horizons are trailing returns fully
    reconstructable from the accumulating whole-market massive_stock_day store
    (nightly, R2-published), and ~100 KB/day of duplicated member JSON in git
    history forever fails the repo's heavy-store discipline (r2 data plane)."""
    p = path if path is not None else SUBSECTOR_PERF_HISTORY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    if _last_asof(p) == asof:
        return False
    _append_jsonl_line(p, {"asof": asof, "subsectors": sub_perf})
    return True


def append_tree_history(
    asof: str,
    tree: list,
    path: Path | None = None,
) -> bool:
    """Append to tree_history.jsonl only when the tree content changed. Returns True if written."""
    p = path if path is not None else TREE_HISTORY_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    h = _tree_hash(tree)
    if _last_line_hash(p) == h:
        return False
    _append_jsonl_line(p, {"asof": asof, "sha256": h, "tree": tree})
    return True


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch Finviz themes snapshot")
    ap.add_argument("--refresh-tree", action="store_true",
                    help="(reserved) re-pull the theme→subsector→member structure")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.refresh_tree or not TREE_PATH.exists():
        # The structure is a hash-rotated webpack data chunk; refreshing it is a
        # manual, traced extraction (see the memory note). The committed
        # themes_tree.json is the source of record — fail loudly if it is gone
        # rather than silently shipping an empty map.
        if not TREE_PATH.exists():
            raise SystemExit(f"missing structure seed {TREE_PATH}; cannot proceed")

    tree = json.loads(TREE_PATH.read_text())
    members = sorted({m for t in tree for s in t["subsectors"] for m in s["members"]})
    print(f"tree: {len(tree)} themes, "
          f"{sum(len(t['subsectors']) for t in tree)} subsectors, {len(members)} members")

    print("fetching subsector perf …")
    sub_perf = fetch_subsector_perf()
    print(f"  {len(sub_perf)} subsectors × {len(ST_TO_TF)} timeframes")

    print("fetching member perf …")
    mem_perf = fetch_member_perf(members)
    print(f"  {len(mem_perf)}/{len(members)} members covered")

    asof = _asof_stamp()
    snap = {
        "source": "finviz-themes",
        # Finviz themes perf is end-of-day; stamp the NYSE SESSION the board
        # describes — never the calendar day of the fetch — so the rotation build
        # and its forward track-record date each call by the true data day
        # (build_subsector_rotation reads snap["asof"]). See _asof_stamp: the
        # weekend runs of a 7-nights-a-week schedule re-describe Friday's board,
        # and a clock stamp made every one of them look like a new session.
        "asof": asof,
        "timeframes": list(ST_TO_TF.values()),
        "subsector_perf": sub_perf,
        "member_perf": mem_perf,
    }
    PERF_PATH.write_text(json.dumps(snap, separators=(",", ":")))
    print(f"wrote {PERF_PATH} ({PERF_PATH.stat().st_size // 1024} KB)")

    # --- PIT archival (additive; non-fatal to the snapshot, LOUD on failure) ---
    # perf_snapshot.json is already written above, so an archival failure must
    # never look like a normal skip: a lost day is unrecoverable. Each append is
    # isolated; any failure prints a ::error:: annotation (visible in the Actions
    # UI even though daily.yml runs this step with `|| echo`) and the process
    # exits non-zero so the loss is observable, not laundered into a green run.
    archival_ok = True
    try:
        written = append_subsector_perf_history(asof, sub_perf)
        print(f"subsector_perf_history.jsonl: {'appended' if written else 'skipped (asof exists)'}")
    except Exception as e:  # noqa: BLE001
        archival_ok = False
        print(f"::error::PIT archival FAILED (subsector perf, asof={asof}): {e!r} — "
              "this day's Finviz subsector aggregates are NOT archived", file=sys.stderr)
    try:
        tree_written = append_tree_history(asof, tree)
        print(f"tree_history.jsonl: {'appended (tree changed)' if tree_written else 'skipped (tree unchanged)'}")
    except Exception as e:  # noqa: BLE001
        archival_ok = False
        print(f"::error::PIT archival FAILED (tree, asof={asof}): {e!r} — "
              "membership history is NOT archived for this day", file=sys.stderr)
    if not archival_ok:
        sys.exit(2)


if __name__ == "__main__":
    main()
