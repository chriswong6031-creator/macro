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

STRUCTURE REFRESH CONTRACT (added 2026-08-14, GMI Theme Graph W3A plan §3):
``--refresh-tree`` is a STRUCTURE-ONLY mode — it re-traces the source, diffs,
receipts, promotes-or-refuses, and EXITS. It never touches the perf feeds, and
the nightly never passes it (cadence is manual/receipted-on-demand: the rights
review is unresolved and the structure has been empirically frozen since June,
so an unattended mutation cadence on an undocumented vendor route buys nothing).
DETECTION is automated instead: every normal perf run compares the subsector keys
``map_perf`` returns against the committed tree's keys and emits an advisory
line-start ``::warning`` on any symmetric difference — a source restructure goes
loud within one night while mutation stays a human-triggered, receipted act.
Exit codes: 0 promoted (or a clean ``--dry-run``), 3 refused by an interlock,
4 fetch/parse failure. A refusal is receipted too — the refusals ARE the audit
trail, and a run that leaves no receipt is indistinguishable from a run that
never happened.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

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
TREE_REFRESH_RECEIPTS_DIR = OUT_DIR / "tree_refresh_receipts"
# The probation queue is a data-plane sidecar shared with the theme graph
# (plan §4). This module only ever APPENDS `kind=key_rename` rows to it and
# never reads the graph — nothing in engine/theme_graph is imported here, so a
# refresh stays runnable with the graph layer absent or mid-build.
PROBATION_PROPOSALS_PATH = ROOT / "data" / "theme_graph" / "probation" / "proposals.jsonl"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Finviz subtype code -> our timeframe key (matches the sp500 heatmap contract).
ST_TO_TF: dict[str, str] = {
    "d1": "1D", "w1": "1W", "w4": "1M", "mtd": "MTD",
    "w13": "3M", "w26": "6M", "w52": "1Y", "ytd": "YTD",
}

# --------------------------------------------------------------------------- #
# Structure refresh contract — preregistered constants
#
# Every number below is pinned in research/theme_graph/W3A_LOCAL_THEME_PLANE_PLAN.md
# §3 and lives HERE rather than at its call site so that loosening a wall is a
# one-line reviewable diff instead of a buried literal.
# --------------------------------------------------------------------------- #

#: Stamped into every receipt. Bump when the trace or the normalisation changes
#: shape — a receipt must never be readable against the wrong extraction contract.
PARSER_VERSION = "finviz_tree_refresh.v1"

MAP_PAGE_URL = "https://finviz.com/map?t=themes"
FINVIZ_ORIGIN = "https://finviz.com"

#: Refuse promotion when more than this FRACTION of the PRIOR memberships
#: disappears in one pull. Observed genuine churn is 1.1% per SEVEN WEEKS
#: (26 removals of 2,356, 2026-06-27 → 2026-08-14, every one dispositioned as
#: dead-at-vendor), so 25% is >=20x any drift the source has ever shown — while
#: still tripping the 40-45% "parser ate half the chunk" catastrophe (test B).
#: Overridable ONLY with --allow-shrink, which is an operator's signed act.
MAX_MEMBERSHIP_REMOVAL_FRAC = 0.25

#: Refuse promotion on more than this fractional shrink in the subtheme count.
#: The structure is empirically FROZEN (zero themes/subthemes/keys/names/
#: descriptions changed in seven weeks), so a structural shrink is presumptively
#: a partial parse rather than a source edit. Overridable ONLY with --allow-shrink.
MAX_SUBTHEME_SHRINK_FRAC = 0.05

#: ANY decrease in the theme count refuses — deliberately not a fraction. The 40
#: top-level themes are the coarsest possible evidence that the walk finished;
#: losing even one is the signature of a truncated chunk, not of curation.
MAX_THEME_SHRINK = 0

#: A removed subtheme key and an added subtheme key whose member sets overlap at
#: Jaccard >= this are the same concept under a new key. That REFUSES promotion
#: with NO flag override: auto-promoting would silently break every graph node id
#: bound to the old key (a fake identity break), and auto-merging would silently
#: rewrite identity. The run files a `key_rename` probation proposal instead and
#: a human ratifies (G0.6) — neither failure mode can happen quietly.
RENAME_JACCARD_MIN = 0.80

#: Politeness floor between requests on an undocumented vendor route; the
#: receipted 2026-08-14 extraction used the same gap and drew no bot-wall.
MIN_FETCH_GAP_S = 0.5

#: Exit codes. A caller (or an operator's shell) must be able to tell "the source
#: MOVED in a way a human has to look at" from "I could not READ the source"
#: without parsing stdout — the two demand completely different responses.
EXIT_PROMOTED = 0
EXIT_REFUSED = 3
EXIT_FETCH_PARSE = 4


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


# --------------------------------------------------------------------------- #
# Nightly key-drift tripwire (advisory; runs on EVERY normal perf fetch)
#
# The structure refresh is a manual, receipted act (see the module docstring), so
# nothing would otherwise notice a source restructure until someone thought to
# look. map_perf already returns the source's OWN current subsector key set on
# every nightly run — comparing it against the committed tree costs one set
# difference and turns "we find out whenever" into "we find out tonight".
# Deliberately non-fatal and non-mutating: the nightly's job is the perf board,
# and a tripwire that could red the nightly would be a worse failure than the
# drift it reports.
# --------------------------------------------------------------------------- #

#: How many keys per side the annotation names before it truncates. An Actions
#: annotation is one line in a summary; a 268-key dump there is unreadable and
#: the receipted refresh is where the full list belongs.
DRIFT_KEYS_SHOWN = 5


def key_drift(tree_keys: Iterable[str], perf_keys: Iterable[str]) -> dict | None:
    """Symmetric difference between the committed tree and what map_perf returned.

    Returns ``None`` when the two key sets agree (the steady state), else a dict
    naming both sides. Pure — no I/O, no printing — so the comparison is unit
    testable without capturing stdout.
    """
    tree = set(tree_keys)
    perf = set(perf_keys)
    tree_only = sorted(tree - perf)
    perf_only = sorted(perf - tree)
    if not tree_only and not perf_only:
        return None
    return {
        "tree_key_count": len(tree),
        "perf_key_count": len(perf),
        "tree_only": tree_only,
        "perf_only": perf_only,
    }


def _sample(keys: list[str]) -> str:
    shown = ", ".join(keys[:DRIFT_KEYS_SHOWN]) or "-"
    extra = len(keys) - DRIFT_KEYS_SHOWN
    return f"{shown} (+{extra} more)" if extra > 0 else shown


def emit_key_drift_warning(drift: dict | None) -> bool:
    """Print the advisory annotation for ``drift``; return True if one was emitted.

    A BARE ``print`` on purpose, never a logger: every builder here configures a
    prefixing log format, so ``log.warning("::warning …")`` emits
    ``WARNING ::warning …`` and GitHub silently drops it — the annotation reviews
    as an alarm, runs clean, and produces nothing (tests/test_gh_annotation_line_start.py).
    ``flush=True`` is load-bearing because stdout is block-buffered when piped in CI.
    """
    if not drift:
        return False
    print(
        "::warning title=finviz-tree-drift::Finviz map_perf key set no longer matches the "
        f"committed themes_tree.json: {len(drift['tree_only'])} tree-only, "
        f"{len(drift['perf_only'])} perf-only "
        f"(tree {drift['tree_key_count']}, map_perf {drift['perf_key_count']}). "
        f"tree-only: {_sample(drift['tree_only'])}. perf-only: {_sample(drift['perf_only'])}. "
        "Advisory only — the board is unaffected; re-pull the structure with "
        "`python scripts/fetch_finviz_themes.py --refresh-tree` after a look.",
        flush=True,
    )
    return True


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
# --refresh-tree: paths, fetch layer
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class _RefreshPaths:
    """Every file the refresh may read or write, in one injectable bundle.

    Defaults are the production paths, so callers and the CLI need not know this
    type exists; tests point the whole bundle at ``tmp_path`` and prove the
    byte-identity/append contracts against a real filesystem instead of a mock.
    Same motivation as ``append_subsector_perf_history(path=…)`` above.
    """
    tree: Path = TREE_PATH
    tree_history: Path = TREE_HISTORY_PATH
    receipts_dir: Path = TREE_REFRESH_RECEIPTS_DIR
    proposals: Path = PROBATION_PROPOSALS_PATH


#: ``fetch(url, referer=…, rows=…) -> bytes``; appends one receipt row to ``rows``
#: on BOTH success and failure, then returns the body or raises.
FetchFn = Callable[..., bytes]

_LAST_TREE_FETCH = [0.0]


def _fetch_bytes(url: str, *, referer: str | None = None,
                 rows: list[dict] | None = None) -> bytes:
    """GET ``url`` once, receipt the attempt into ``rows``, return the raw body.

    ONE attempt per URL, deliberately — the retry loop in ``_get`` exists because
    a perf feed hiccup costs a night's board, but the structure refresh is a
    manual act on an undocumented vendor route where a non-200 is EVIDENCE (a bot
    wall, a moved asset, a deploy in flight) that an operator must read, not a
    transient to hammer through. The failed attempt is receipted before the raise
    so the refusal receipt names the exact url and status.
    """
    gap = time.time() - _LAST_TREE_FETCH[0]
    if gap < MIN_FETCH_GAP_S:
        time.sleep(MIN_FETCH_GAP_S - gap)

    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _row(**kw) -> None:
        if rows is not None:
            rows.append({"url": url, "retrieved_at_utc": retrieved_at, **kw})

    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            body = r.read()
            status, ctype = r.status, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        body = e.read() or b""
        _row(http_status=e.code, byte_size=len(body),
             sha256=hashlib.sha256(body).hexdigest(),
             content_type=(e.headers.get("Content-Type", "") if e.headers else ""), ok=False)
        raise RuntimeError(f"GET failed: {url} (HTTP {e.code}, {len(body)}B body)") from e
    except Exception as e:  # noqa: BLE001 — DNS/TLS/timeout: same complete-or-fail posture
        _row(http_status=f"ERROR:{type(e).__name__}", byte_size=0, sha256=None,
             error=repr(e), ok=False)
        raise RuntimeError(f"GET failed: {url} ({e!r})") from e
    finally:
        _LAST_TREE_FETCH[0] = time.time()

    if status != 200:
        _row(http_status=status, byte_size=len(body),
             sha256=hashlib.sha256(body).hexdigest(), content_type=ctype, ok=False)
        raise RuntimeError(f"GET failed: {url} (HTTP {status})")
    _row(http_status=status, byte_size=len(body),
         sha256=hashlib.sha256(body).hexdigest(), content_type=ctype, ok=True)
    return body


# --------------------------------------------------------------------------- #
# --refresh-tree: strict JS object-literal reader (no eval, ever)
# --------------------------------------------------------------------------- #

class JsParseError(ValueError):
    """The chunk did not parse as the narrow literal grammar we accept."""


class TreeIntegrityError(ValueError):
    """The parsed tree is structurally incomplete — a partial tree never promotes."""


_IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUM = re.compile(r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?")
_ESCAPES = {'"': '"', "\\": "\\", "/": "/", "b": "\b", "f": "\f",
            "n": "\n", "r": "\r", "t": "\t", "'": "'", "\n": ""}


def parse_js_object(src: str, pos: int = 0):
    """Parse ONE JS literal value at ``src[pos]``; return ``(value, end_pos)``.

    The Finviz module export is a MINIFIED JS OBJECT LITERAL, not JSON: bare
    identifier keys and ``!0``/``!1`` booleans. ``eval``/``json.loads`` are both
    out — one executes vendor code we do not control, the other cannot read it.

    Deliberately narrow: objects, arrays, single/double-quoted strings, numbers,
    ``true``/``false``/``null`` and the minifier's ``!0``/``!1``. Anything else —
    a function, a variable reference, a template literal, a trailing operator —
    RAISES, so a structural change upstream surfaces as a loud parse error
    instead of a quietly half-read tree.
    """
    def ws(i: int) -> int:
        while i < len(src) and src[i] in " \t\r\n":
            i += 1
        return i

    def value(i: int):
        i = ws(i)
        if i >= len(src):
            raise JsParseError(f"unexpected end of input at {i}")
        c = src[i]
        if c == "{":
            return obj(i)
        if c == "[":
            return arr(i)
        if c in "\"'":
            return string(i)
        if c == "!":  # minified booleans: !0 -> true, !1 -> false
            if src[i + 1:i + 2] == "0":
                return True, i + 2
            if src[i + 1:i + 2] == "1":
                return False, i + 2
            raise JsParseError(f"unsupported ! expression at {i}: {src[i:i + 8]!r}")
        for lit, val in (("true", True), ("false", False), ("null", None)):
            if src.startswith(lit, i):
                return val, i + len(lit)
        m = _NUM.match(src, i)
        if m:
            txt = m.group(0)
            return (float(txt) if any(ch in txt for ch in ".eE") else int(txt)), m.end()
        raise JsParseError(f"unparseable value at {i}: {src[i:i + 40]!r}")

    def string(i: int):
        quote = src[i]
        i += 1
        out: list[str] = []
        while i < len(src):
            c = src[i]
            if c == "\\":
                nxt = src[i + 1]
                if nxt == "u":
                    out.append(chr(int(src[i + 2:i + 6], 16)))
                    i += 6
                    continue
                if nxt == "x":
                    out.append(chr(int(src[i + 2:i + 4], 16)))
                    i += 4
                    continue
                if nxt not in _ESCAPES:
                    raise JsParseError(f"unsupported escape \\{nxt} at {i}")
                out.append(_ESCAPES[nxt])
                i += 2
                continue
            if c == quote:
                return "".join(out), i + 1
            out.append(c)
            i += 1
        raise JsParseError(f"unterminated string from {i}")

    def key(i: int):
        i = ws(i)
        if src[i] in "\"'":
            return string(i)
        m = _IDENT.match(src, i)
        if not m:
            raise JsParseError(f"unparseable object key at {i}: {src[i:i + 40]!r}")
        return m.group(0), m.end()

    def obj(i: int):
        out: dict = {}
        i = ws(i + 1)
        if src[i] == "}":
            return out, i + 1
        while True:
            k, i = key(i)
            i = ws(i)
            if src[i] != ":":
                raise JsParseError(f"expected ':' after key {k!r} at {i}")
            v, i = value(i + 1)
            if k in out:
                raise JsParseError(f"duplicate key {k!r} at {i}")
            out[k] = v
            i = ws(i)
            if src[i] == ",":
                i = ws(i + 1)
                if src[i] == "}":  # tolerate a trailing comma
                    return out, i + 1
                continue
            if src[i] == "}":
                return out, i + 1
            raise JsParseError(f"expected ',' or '}}' at {i}: {src[i:i + 40]!r}")

    def arr(i: int):
        out: list = []
        i = ws(i + 1)
        if src[i] == "]":
            return out, i + 1
        while True:
            v, i = value(i)
            out.append(v)
            i = ws(i)
            if src[i] == ",":
                i = ws(i + 1)
                if src[i] == "]":
                    return out, i + 1
                continue
            if src[i] == "]":
                return out, i + 1
            raise JsParseError(f"expected ',' or ']' at {i}: {src[i:i + 40]!r}")

    return value(pos)


def _slice_balanced(src: str, start: int) -> str:
    """The brace-balanced object literal beginning at ``src[start] == '{'``.

    String-aware: a brace inside a description or a ticker CSV must not move the
    depth counter, or the slice ends in the middle of the data.
    """
    if src[start:start + 1] != "{":
        raise JsParseError(f"expected '{{' at {start}, got {src[start:start + 1]!r}")
    depth, i, in_str, quote = 0, start, False, ""
    while i < len(src):
        c = src[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                in_str = False
        elif c in "\"'":
            in_str, quote = True, c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    raise JsParseError("unbalanced braces: object literal never closed")


# --------------------------------------------------------------------------- #
# --refresh-tree: the 4-hop trace (nothing hardcoded — every id re-derived)
# --------------------------------------------------------------------------- #

def _trace_tree(fetch: FetchFn) -> dict:
    """Walk map page → map.v1 → runtime.v1 → data chunk; return the trace + root.

    NOTHING is hardcoded, not even the module and chunk ids that have held since
    2026-06-27: every file hash rotates on a vendor redeploy, and a hardcoded id
    would fetch a stale or absent asset and call the result "the current source".
    Each hop is re-derived and recorded in the receipt so a later reader can
    replay exactly what this run read. Ambiguity is a refusal, not a guess: two
    candidate ``map.v1`` scripts means the page shape changed.
    """
    html = fetch(MAP_PAGE_URL).decode("utf-8", "replace")

    def one(pattern: str, what: str) -> str:
        hits = sorted(set(re.findall(pattern, html)))
        if not hits:
            raise RuntimeError(f"trace broke: no {what} in the map page ({len(html)}B)")
        if len(hits) > 1:
            raise RuntimeError(f"trace ambiguous: {len(hits)} {what} candidates: {hits}")
        return hits[0]

    map_js = one(r"/assets/dist/map\.v1\.[0-9a-f]+\.js", "map.v1 script")
    runtime_js = one(r"/assets/dist/runtime\.v1\.[0-9a-f]+\.js", "runtime.v1 script")

    map_src = fetch(FINVIZ_ORIGIN + map_js, referer=MAP_PAGE_URL).decode("utf-8", "replace")
    # The map-type switch: `case <ns>.<enum>.Themes: return <wrap>(r.e(<CHUNK>)
    # .then(r.t.bind(r,<MODULE>,23)))` — this is where the Themes lazy chunk and
    # its module id are DECLARED by the source, so we read them rather than
    # remember them.
    m = re.search(
        r"case\s+\w+\.\w+\.Themes\s*:\s*return\s+\w+\(\s*\w+\.e\((\d+)\)\.then\(\s*\w+\.t\.bind\(\s*\w+\s*,\s*(\d+)",
        map_src,
    )
    if not m:
        raise RuntimeError(
            "trace broke: no `case *.Themes: return *(r.e(<chunk>).then(r.t.bind(r,<module>` in "
            f"{map_js} ({len(map_src)}B); the map-type switch changed shape"
        )
    chunk_id, module_id = m.group(1), m.group(2)

    rt_src = fetch(FINVIZ_ORIGIN + runtime_js, referer=MAP_PAGE_URL).decode("utf-8", "replace")
    hm = re.search(rf"\b{chunk_id}\s*:\s*\"([0-9a-f]+)\"", rt_src)
    if not hm:
        raise RuntimeError(
            f"trace broke: chunk {chunk_id} absent from the runtime chunk-hash table ({runtime_js})"
        )
    chunk_hash = hm.group(1)

    chunk_url = f"{FINVIZ_ORIGIN}/assets/dist/{chunk_id}.v1.{chunk_hash}.js"
    chunk_src = fetch(chunk_url, referer=MAP_PAGE_URL).decode("utf-8", "replace")

    mm = re.search(rf"\b{module_id}\s*\(\s*\w+\s*\)\s*\{{\s*\w+\.exports\s*=\s*", chunk_src)
    if not mm:
        raise RuntimeError(
            f"trace broke: module {module_id} has no `e.exports=` in chunk {chunk_id} "
            f"({len(chunk_src)}B)"
        )
    literal = _slice_balanced(chunk_src, mm.end())
    root, end = parse_js_object(literal)
    if end != len(literal):
        raise JsParseError(f"trailing bytes after the module literal: {literal[end:end + 60]!r}")

    return {
        "map_page_url": MAP_PAGE_URL,
        "map_js_url": FINVIZ_ORIGIN + map_js,
        "runtime_js_url": FINVIZ_ORIGIN + runtime_js,
        "chunk_url": chunk_url,
        "chunk_id": chunk_id,
        "module_id": module_id,
        "chunk_hash": chunk_hash,
        "literal_bytes": len(literal),
        "root": root,
    }


# --------------------------------------------------------------------------- #
# --refresh-tree: normalisation + completeness (pure; no network)
# --------------------------------------------------------------------------- #

_ROOT_FIELDS = {"name", "children"}
_SUB_FIELDS = {"name", "displayName", "description", "extra", "value"}


def _normalise_tree(root: dict) -> tuple[list[dict], list[str], list[dict]]:
    """Source root → the committed ``[{theme,key,subsectors:[…]}]`` shape.

    Returns ``(tree, notes, groups)``. Source ordering is preserved end to end.

    ``groups`` keeps the LEVEL-1 SUPERGROUP layer the committed schema flattens:
    Finviz nests the 40 themes under six unlabelled buckets ("1".."6"). Flattening
    in group order reproduces the committed ordering exactly — but the grouping is
    real upstream structure, so it is RECORDED in the receipt rather than
    discarded (it becomes ``source_meta.supergroup_index`` in the graph; hierarchy
    itself stays out of the tree until W4 owns it).

    Unknown fields RAISE rather than get noted. Every node in the live source has
    exactly the field set below, verified against the committed 2026-08-14 chunk
    receipt; a new field could carry membership-relevant data, and silently
    dropping it is precisely the invisible loss complete-or-fail exists to stop.
    """
    notes: list[str] = []

    def _check_fields(node: dict, allowed: set[str], what: str) -> None:
        extra = set(node) - allowed
        if extra:
            raise TreeIntegrityError(
                f"{what} {node.get('name')!r} carries unknown field(s) {sorted(extra)} — "
                "the source node shape changed; extend the parser deliberately"
            )

    if not isinstance(root, dict) or root.get("name") != "Root":
        raise TreeIntegrityError(
            f"expected a Root node, got name={root.get('name')!r}" if isinstance(root, dict)
            else f"expected a Root object, got {type(root).__name__}"
        )
    _check_fields(root, _ROOT_FIELDS, "root")
    lvl1 = root.get("children") or []
    if not lvl1:
        raise TreeIntegrityError("root has no children — empty tree")

    groups: list[dict] = []
    for grp in lvl1:
        _check_fields(grp, _ROOT_FIELDS, "supergroup")
        groups.append({"group": grp.get("name"),
                       "themes": [t.get("name") for t in (grp.get("children") or [])]})
    shape = ", ".join(f"{g['group']}={len(g['themes'])}" for g in groups)
    notes.append(f"level-1 supergroup layer: {len(lvl1)} groups ({shape}) "
                 "— flattened in group order to match the committed schema")

    tree: list[dict] = []
    for grp in lvl1:
        for tnode in grp.get("children") or []:
            _check_fields(tnode, _ROOT_FIELDS, "theme")
            tname = tnode.get("name")
            if not isinstance(tname, str) or not tname:
                raise TreeIntegrityError(f"theme with no usable name: {tnode!r}")
            subs: list[dict] = []
            for snode in tnode.get("children") or []:
                _check_fields(snode, _SUB_FIELDS, "subsector")
                skey = snode.get("name")
                if not isinstance(skey, str) or not skey:
                    raise TreeIntegrityError(f"subsector with no key under theme {tname!r}")
                raw = snode.get("extra")
                if raw is None:
                    raise TreeIntegrityError(
                        f"subsector {skey!r} has NO 'extra' member CSV — partial chunk")
                parts = [p.strip() for p in str(raw).split(",")]
                members = [p for p in parts if p]
                if len(members) != len(parts):
                    notes.append(f"subsector {skey!r}: dropped "
                                 f"{len(parts) - len(members)} blank CSV field(s)")
                if len(set(members)) != len(members):
                    dupes = sorted({m for m in members if members.count(m) > 1})
                    notes.append(f"subsector {skey!r}: duplicate members {dupes} (kept as-is)")
                subs.append({
                    "key": skey,
                    "name": snode.get("displayName"),
                    "description": snode.get("description"),
                    "members": members,
                })
            tree.append({"theme": tname, "key": tname, "subsectors": subs})
    return tree, notes, groups


def assert_complete_tree(tree: list[dict]) -> None:
    """Raise ``TreeIntegrityError`` unless every completeness precondition holds.

    Complete-or-fail (plan §3): a theme with zero subthemes or a subtheme with an
    empty member list means the walk did not finish, and a partial tree that
    promotes is worse than no refresh at all — the shrink interlocks downstream
    would then be measuring a truncation against itself. Globally unique subtheme
    keys are checked here too because the graph's node id grammar
    (``ltheme:finviz:<subtheme_key>``) binds identity to that key: a duplicate
    would silently collapse two concepts into one node.
    """
    if not tree:
        raise TreeIntegrityError("empty tree: zero themes parsed")
    seen: dict[str, str] = {}
    for t in tree:
        if not t.get("subsectors"):
            raise TreeIntegrityError(f"theme {t.get('theme')!r} has ZERO subthemes")
        for s in t["subsectors"]:
            if not s.get("members"):
                raise TreeIntegrityError(
                    f"subtheme {s.get('key')!r} (theme {t.get('theme')!r}) has an EMPTY member CSV")
            prior = seen.get(s["key"])
            if prior is not None:
                raise TreeIntegrityError(
                    f"subtheme key {s['key']!r} appears under both {prior!r} and "
                    f"{t.get('theme')!r} — keys must be globally unique (graph node id grammar)")
            seen[s["key"]] = t.get("theme")


def _tree_counts(tree: list[dict]) -> dict[str, int]:
    subs = [s for t in tree for s in t["subsectors"]]
    members = [m for s in subs for m in s["members"]]
    return {
        "themes": len(tree),
        "subthemes": len(subs),
        "memberships": len(members),
        "unique_tickers": len(set(members)),
    }


def _subtheme_index(tree: list[dict]) -> dict[str, dict]:
    """``{subtheme_key: {theme, name, description, members:set}}`` for diffing."""
    out: dict[str, dict] = {}
    for t in tree:
        for s in t.get("subsectors") or []:
            out[s["key"]] = {
                "theme": t.get("theme"),
                "name": s.get("name"),
                "description": s.get("description"),
                "members": set(s.get("members") or []),
            }
    return out


# --------------------------------------------------------------------------- #
# --refresh-tree: diff, identity, interlocks (all pure — unit tested directly)
# --------------------------------------------------------------------------- #

def diff_trees(prev: list[dict], new: list[dict]) -> dict:
    """Structural + membership diff of two trees. Pure; no thresholds applied here.

    Memberships are diffed as ``(subtheme_key, ticker)`` PAIRS, not as ticker
    sets: a ticker that merely moves between subthemes is one removal and one
    addition, and a subtheme that vanishes removes all of its pairs — which is
    exactly what the shrink wall must see. A ticker-set diff would have scored a
    catastrophic subtheme loss as "nothing removed" whenever the tickers survived
    elsewhere.
    """
    p_idx, n_idx = _subtheme_index(prev), _subtheme_index(new)
    p_themes = [t.get("theme") for t in prev]
    n_themes = [t.get("theme") for t in new]

    def pairs(idx: dict[str, dict]) -> set[tuple[str, str]]:
        return {(k, m) for k, v in idx.items() for m in v["members"]}

    p_pairs, n_pairs = pairs(p_idx), pairs(n_idx)
    removed_pairs, added_pairs = p_pairs - n_pairs, n_pairs - p_pairs
    p_tick = {m for _, m in p_pairs}
    n_tick = {m for _, m in n_pairs}

    shared = sorted(set(p_idx) & set(n_idx))
    name_changes = [
        {"key": k, "prev": p_idx[k]["name"], "new": n_idx[k]["name"]}
        for k in shared if p_idx[k]["name"] != n_idx[k]["name"]
    ]
    # Descriptions are long free text; the receipt carries only WHICH subthemes
    # moved (the before/after prose is recoverable from the PIT tape's two rows).
    desc_changed = [k for k in shared if p_idx[k]["description"] != n_idx[k]["description"]]
    moved = [
        {"key": k, "prev_theme": p_idx[k]["theme"], "new_theme": n_idx[k]["theme"]}
        for k in shared if p_idx[k]["theme"] != n_idx[k]["theme"]
    ]

    return {
        "themes": {
            "prev": len(p_themes), "new": len(n_themes),
            "added": sorted(set(n_themes) - set(p_themes)),
            "removed": sorted(set(p_themes) - set(n_themes)),
        },
        "subthemes": {
            "prev": len(p_idx), "new": len(n_idx),
            "added": sorted(set(n_idx) - set(p_idx)),
            "removed": sorted(set(p_idx) - set(n_idx)),
            "name_changes": name_changes,
            "description_changes": desc_changed,
            "moved_between_themes": moved,
        },
        "memberships": {
            "prev": len(p_pairs), "new": len(n_pairs),
            "added": len(added_pairs), "removed": len(removed_pairs),
            "added_sample": [f"{k}:{m}" for k, m in sorted(added_pairs)[:20]],
            "removed_sample": [f"{k}:{m}" for k, m in sorted(removed_pairs)[:20]],
        },
        "tickers": {
            "prev": len(p_tick), "new": len(n_tick),
            "added": len(n_tick - p_tick), "removed": len(p_tick - n_tick),
        },
    }


def detect_key_renames(prev: list[dict], new: list[dict],
                       *, threshold: float = RENAME_JACCARD_MIN) -> list[dict]:
    """Removed-key × added-key pairs whose members overlap at Jaccard >= threshold.

    A subtheme whose KEY changes while its MEMBERS stay put is one concept under
    a new label, and the two ways of handling it automatically are both wrong:
    treat it as a break and every graph node bound to the old key dies for a
    reason that never happened; treat it as a merge and identity is rewritten with
    no record. So this only FLAGS — the caller refuses promotion and files a
    probation proposal for a human (plan §4).
    """
    p_idx, n_idx = _subtheme_index(prev), _subtheme_index(new)
    removed = sorted(set(p_idx) - set(n_idx))
    added = sorted(set(n_idx) - set(p_idx))
    out: list[dict] = []
    for r in removed:
        a_members = p_idx[r]["members"]
        for a in added:
            b_members = n_idx[a]["members"]
            union = a_members | b_members
            if not union:
                continue
            shared = a_members & b_members
            j = len(shared) / len(union)
            if j >= threshold:
                out.append({
                    "old_key": r, "new_key": a,
                    "jaccard": round(j, 4),
                    "old_theme": p_idx[r]["theme"], "new_theme": n_idx[a]["theme"],
                    "old_name": p_idx[r]["name"], "new_name": n_idx[a]["name"],
                    "old_member_count": len(a_members), "new_member_count": len(b_members),
                    "shared_member_count": len(shared),
                })
    out.sort(key=lambda d: (-d["jaccard"], d["old_key"], d["new_key"]))
    return out


def shrink_stats(diff: dict) -> dict:
    """The three shrink measurements plus the thresholds they are read against.

    Thresholds travel WITH the numbers into the receipt: a receipt that records
    "0.31 removed" without recording the wall it was judged against cannot be
    re-adjudicated later if the wall moves.
    """
    p_mem = diff["memberships"]["prev"]
    p_sub = diff["subthemes"]["prev"]
    return {
        "membership_removals": diff["memberships"]["removed"],
        "prior_memberships": p_mem,
        "membership_removal_frac": round(diff["memberships"]["removed"] / p_mem, 6) if p_mem else 0.0,
        "max_membership_removal_frac": MAX_MEMBERSHIP_REMOVAL_FRAC,
        "theme_delta": diff["themes"]["new"] - diff["themes"]["prev"],
        "max_theme_shrink": MAX_THEME_SHRINK,
        "subtheme_delta": diff["subthemes"]["new"] - p_sub,
        "subtheme_shrink_frac": round(max(0, p_sub - diff["subthemes"]["new"]) / p_sub, 6) if p_sub else 0.0,
        "max_subtheme_shrink_frac": MAX_SUBTHEME_SHRINK_FRAC,
    }


def evaluate_interlocks(diff: dict, *, allow_shrink: bool = False) -> list[str]:
    """Preregistered refusal reasons for this diff (empty list ⇒ nothing blocking).

    Bootstrap case: with no prior tree there is nothing to shrink FROM, so the
    walls are skipped rather than dividing by zero — the completeness checks in
    ``assert_complete_tree`` are what guard a first materialisation.
    """
    st = shrink_stats(diff)
    out: list[str] = []
    if diff["themes"]["prev"] and st["theme_delta"] < -MAX_THEME_SHRINK:
        out.append(
            f"theme_count_decrease: {diff['themes']['prev']} → {diff['themes']['new']} "
            f"({st['theme_delta']}); ANY theme loss is presumptively a truncated chunk")
    if diff["subthemes"]["prev"] and st["subtheme_shrink_frac"] > MAX_SUBTHEME_SHRINK_FRAC:
        out.append(
            f"subtheme_shrink: {diff['subthemes']['prev']} → {diff['subthemes']['new']} "
            f"({st['subtheme_shrink_frac']:.1%} > {MAX_SUBTHEME_SHRINK_FRAC:.0%})")
    if st["prior_memberships"] and st["membership_removal_frac"] > MAX_MEMBERSHIP_REMOVAL_FRAC:
        out.append(
            f"membership_shrink: {st['membership_removals']} of {st['prior_memberships']} "
            f"memberships removed ({st['membership_removal_frac']:.1%} > "
            f"{MAX_MEMBERSHIP_REMOVAL_FRAC:.0%})")
    if allow_shrink:
        # --allow-shrink is the operator's signed acknowledgement of a REAL source
        # contraction; it clears the three walls above and nothing else.
        out = []
    return out


# --------------------------------------------------------------------------- #
# --refresh-tree: probation proposals, receipts, atomic promotion
# --------------------------------------------------------------------------- #

def _rel_to_root(p: Path) -> str:
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def _proposal_id(rename: dict, new_tree_sha: str) -> str:
    """Deterministic id: the same suspected rename re-proposed by a re-run is the
    SAME proposal, not a second one (an operator investigating a refusal will run
    it more than once, and a queue that grows a row per attempt is unreadable)."""
    return f"key_rename:{rename['old_key']}->{rename['new_key']}:{new_tree_sha[:12]}"


def append_probation_proposal(path: Path, row: dict) -> bool:
    """Append one proposal row; return False if that ``proposal_id`` is already queued.

    Append-only by contract (plan §4) — nothing here ever rewrites or ratifies a
    row, and the graph build ignores anything not ``status=ratified``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                if json.loads(line).get("proposal_id") == row["proposal_id"]:
                    return False
            except Exception:  # noqa: BLE001 — torn line: treat as absent, like _last_asof
                continue
    _append_jsonl_line(path, row)
    return True


def _tree_json_bytes(tree: list[dict]) -> bytes:
    """Serialise exactly the way the committed themes_tree.json is serialised.

    ``json.dumps(indent=2)`` with NO trailing newline reproduces the committed
    file byte-for-byte (verified against data/themes_heatmap/themes_tree.json).
    Any other formatting would render every refresh — including one that changed
    nothing — as a whole-file diff, and a reviewer could no longer see the real
    delta a promotion carries.
    """
    return json.dumps(tree, indent=2).encode()


def _promote_tree(tree: list[dict], *, paths: _RefreshPaths, asof: str) -> dict:
    """tmp+rename the tree, then append the PIT history line. Rolls back on failure.

    ``os.replace`` is atomic within a filesystem, so a reader never observes a
    half-written tree. If the history append then fails, the tree is restored to
    its previous bytes and the error propagates: the invariant tests A/B assert —
    a failed refresh leaves ``themes_tree.json`` byte-identical — must hold for a
    failure at ANY step, not just an early one.
    """
    prev_bytes = paths.tree.read_bytes() if paths.tree.exists() else None
    paths.tree.parent.mkdir(parents=True, exist_ok=True)
    tmp = paths.tree.parent / (paths.tree.name + ".tmp")
    tmp.write_bytes(_tree_json_bytes(tree))
    os.replace(tmp, paths.tree)
    try:
        history_written = append_tree_history(asof, tree, path=paths.tree_history)
    except Exception:
        if prev_bytes is None:
            paths.tree.unlink(missing_ok=True)
        else:
            paths.tree.write_bytes(prev_bytes)
        raise
    return {"history_appended": history_written}


def _write_refresh_receipt(receipts_dir: Path, stamp: str, receipt: dict) -> Path:
    receipts_dir.mkdir(parents=True, exist_ok=True)
    path = receipts_dir / f"{stamp}.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    return path


# --------------------------------------------------------------------------- #
# --refresh-tree: the orchestrator
# --------------------------------------------------------------------------- #

def refresh_tree(
    *,
    allow_shrink: bool = False,
    dry_run: bool = False,
    paths: _RefreshPaths | None = None,
    fetch: FetchFn | None = None,
    asof: str | None = None,
    now_utc: datetime | None = None,
) -> int:
    """Re-pull the Finviz structure, diff it, and promote-or-refuse. Returns an exit code.

    STRUCTURE ONLY — this never touches the perf feeds or ``perf_snapshot.json``.
    Write order on success is tree → history → receipt, so the receipt is the last
    thing written and its existence means the promotion completed; on refusal only
    the receipt is written, and the committed tree is byte-identical either way.
    """
    paths = paths or _RefreshPaths()
    fetch = fetch or _fetch_bytes
    now = now_utc or datetime.now(timezone.utc)
    # ISO-8601 BASIC format: colon-free so the filename is portable, still
    # lexicographically sortable, still unambiguous UTC.
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    asof = asof or _asof_stamp(now)

    prev_tree = json.loads(paths.tree.read_text()) if paths.tree.exists() else []
    prev_hash = _tree_hash(prev_tree) if prev_tree else None

    rows: list[dict] = []

    def _fetch(url: str, *, referer: str | None = None) -> bytes:
        return fetch(url, referer=referer, rows=rows)

    receipt: dict = {
        "parser_version": PARSER_VERSION,
        "refreshed_at_utc": now.isoformat(timespec="seconds"),
        "asof": asof,
        "mode": "dry_run" if dry_run else "refresh",
        "allow_shrink": allow_shrink,
        "tree_path": _rel_to_root(paths.tree),
        "tree_history_path": _rel_to_root(paths.tree_history),
        "prev_tree_sha256": prev_hash,
        "promoted": False,
        "reason": None,
        "refusal_reasons": [],
        "error": None,
        "fetches": rows,
    }

    # ---- fetch + parse (complete-or-fail) --------------------------------- #
    try:
        traced = _trace_tree(_fetch)
        tree, notes, groups = _normalise_tree(traced.pop("root"))
        assert_complete_tree(tree)
    except Exception as e:  # noqa: BLE001 — every failure here is a REFUSAL with evidence
        receipt["reason"] = "fetch_or_parse_failure"
        receipt["error"] = f"{type(e).__name__}: {e}"
        rp = _write_refresh_receipt(paths.receipts_dir, stamp, receipt)
        print(f"REFUSED (fetch/parse): {type(e).__name__}: {e}", file=sys.stderr)
        print(f"receipt: {rp}", file=sys.stderr)
        return EXIT_FETCH_PARSE

    new_hash = _tree_hash(tree)
    diff = diff_trees(prev_tree, tree)
    renames = detect_key_renames(prev_tree, tree)
    refusals = evaluate_interlocks(diff, allow_shrink=allow_shrink)

    receipt.update({
        "trace": traced,
        "counts": _tree_counts(tree),
        "new_tree_sha256": new_hash,
        "tree_changed": new_hash != prev_hash,
        "diff": diff,
        "shrink": shrink_stats(diff),
        "supergroups": groups,
        "parse_notes": notes,
        "identity_report": {
            "threshold_jaccard": RENAME_JACCARD_MIN,
            "renames": renames,
            "proposal_ids": [],
        },
    })

    # ---- identity: a suspected rename refuses with NO flag override -------- #
    if renames:
        refusals.append(
            f"suspected_key_rename: {len(renames)} removed/added subtheme key pair(s) overlap at "
            f"Jaccard >= {RENAME_JACCARD_MIN} (" +
            ", ".join(f"{r['old_key']}→{r['new_key']} j={r['jaccard']}" for r in renames[:5]) +
            ") — curation required; --allow-shrink does NOT override this")
        receipt_path_hint = _rel_to_root(paths.receipts_dir / f"{stamp}.json")
        for r in renames:
            row = {
                "proposal_id": _proposal_id(r, new_hash),
                "kind": "key_rename",
                "evidence_refs": [receipt_path_hint],
                "evidence": {
                    "source_family": "finviz_themes",
                    "old_key": r["old_key"], "new_key": r["new_key"],
                    "jaccard": r["jaccard"],
                    "old_theme": r["old_theme"], "new_theme": r["new_theme"],
                    "old_name": r["old_name"], "new_name": r["new_name"],
                    "old_member_count": r["old_member_count"],
                    "new_member_count": r["new_member_count"],
                    "shared_member_count": r["shared_member_count"],
                    "prev_tree_sha256": prev_hash,
                    "candidate_tree_sha256": new_hash,
                },
                "proposed_by": "refresh_identity",
                "created": now.isoformat(timespec="seconds"),
                "status": "proposed",
                "ratified_by": None,
            }
            if not dry_run:
                append_probation_proposal(paths.proposals, row)
            receipt["identity_report"]["proposal_ids"].append(row["proposal_id"])
        receipt["identity_report"]["proposals_path"] = _rel_to_root(paths.proposals)

    receipt["refusal_reasons"] = refusals

    # ---- dry run: everything above, zero mutation ------------------------- #
    if dry_run:
        receipt["reason"] = "dry_run"
        rp = _write_refresh_receipt(paths.receipts_dir, stamp, receipt)
        for r in refusals:
            print(f"WOULD REFUSE: {r}", file=sys.stderr)
        print(f"dry run: {receipt['counts']} tree_changed={receipt['tree_changed']}")
        print(f"receipt: {rp}")
        return EXIT_REFUSED if refusals else EXIT_PROMOTED

    if refusals:
        receipt["reason"] = "refused_by_interlock"
        rp = _write_refresh_receipt(paths.receipts_dir, stamp, receipt)
        for r in refusals:
            print(f"REFUSED: {r}", file=sys.stderr)
        print(f"receipt: {rp}", file=sys.stderr)
        return EXIT_REFUSED

    # ---- promotion: tree → history → receipt ------------------------------ #
    try:
        promoted = _promote_tree(tree, paths=paths, asof=asof)
    except Exception as e:  # noqa: BLE001 — tree already rolled back by _promote_tree
        receipt["reason"] = "promotion_failed"
        receipt["error"] = f"{type(e).__name__}: {e}"
        rp = _write_refresh_receipt(paths.receipts_dir, stamp, receipt)
        print(f"REFUSED (promotion failed, tree rolled back): {type(e).__name__}: {e}",
              file=sys.stderr)
        print(f"receipt: {rp}", file=sys.stderr)
        return EXIT_FETCH_PARSE

    receipt["promoted"] = True
    receipt["reason"] = "promoted"
    receipt["history_appended"] = promoted["history_appended"]
    rp = _write_refresh_receipt(paths.receipts_dir, stamp, receipt)
    c = receipt["counts"]
    print(f"promoted: {c['themes']} themes, {c['subthemes']} subthemes, "
          f"{c['memberships']} memberships, {c['unique_tickers']} tickers "
          f"(sha {new_hash[:12]}, history {'appended' if promoted['history_appended'] else 'unchanged'})")
    print(f"receipt: {rp}")
    return EXIT_PROMOTED


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch Finviz themes snapshot")
    ap.add_argument("--refresh-tree", action="store_true",
                    help="STRUCTURE ONLY: re-trace the theme→subsector→member structure, "
                         "diff it against the committed tree, promote or refuse, then EXIT "
                         "(does NOT fetch perf; the nightly never passes this)")
    ap.add_argument("--allow-shrink", action="store_true",
                    help="with --refresh-tree: acknowledge a REAL source contraction and clear "
                         "the theme/subtheme/membership shrink walls. Never clears a suspected "
                         "key rename — that one has no override by design.")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --refresh-tree: fetch, diff and receipt, but mutate NOTHING")
    args = ap.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.refresh_tree:
        # Structure-only mode: refresh and exit. It must NEVER fall through into
        # the perf fetch — a refresh is a manual act on the structure, while the
        # perf path is the nightly's board, and mixing them would make an
        # operator's structural investigation silently rewrite tonight's snapshot.
        raise SystemExit(refresh_tree(allow_shrink=args.allow_shrink, dry_run=args.dry_run))
    if args.allow_shrink or args.dry_run:
        raise SystemExit(
            "--allow-shrink/--dry-run apply only to --refresh-tree; the perf path never "
            "mutates the tree, so silently accepting them would be a false promise")

    if not TREE_PATH.exists():
        # The structure is a hash-rotated webpack data chunk and the committed
        # themes_tree.json is the source of record — fail loudly if it is gone
        # rather than silently shipping an empty map.
        raise SystemExit(f"missing structure seed {TREE_PATH}; cannot proceed")

    tree = json.loads(TREE_PATH.read_text())
    members = sorted({m for t in tree for s in t["subsectors"] for m in s["members"]})
    print(f"tree: {len(tree)} themes, "
          f"{sum(len(t['subsectors']) for t in tree)} subsectors, {len(members)} members")

    print("fetching subsector perf …")
    sub_perf = fetch_subsector_perf()
    print(f"  {len(sub_perf)} subsectors × {len(ST_TO_TF)} timeframes")

    # Advisory key-drift tripwire (plan §3): map_perf just told us the source's
    # own CURRENT subsector key set, so compare it against the committed tree for
    # free. Non-fatal and non-mutating — it reports, the operator decides, and
    # `--refresh-tree` is the only thing that ever moves the structure.
    emit_key_drift_warning(key_drift(
        {s["key"] for t in tree for s in t["subsectors"]}, sub_perf.keys()))

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
