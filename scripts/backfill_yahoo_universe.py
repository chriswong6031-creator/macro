"""Off-render, incremental backfill of data/yahoo/<T>.parquet for the ledger universe.

THE GAP THIS CLOSES
-------------------
Every Intelligence Hub grader prices names from ``data/yahoo/<T>.parquet`` and
NOTHING else — deliberately, because the S&P-1500 breadth cache is
split-UNADJUSTED and silently poisons forward returns (engine/desk_grader.py:31,
engine/trajectory.py:11). But the yahoo store is populated by
``collectors/yahoo.py``, whose fetch list is the CONFIG universe (index/ETF/FX
groups + stock_search extras + theme members) — not the hub's signal ledger. So
the graders can only grade the intersection. Measured 2026-08-08 on this tree:
603 of 7,711 distinct ledger tickers had a parquet, desk_grader's 20d coverage
was 6.2%, and 7 of that night's 30 Command names (ECHO, BRK.B, PSKY, CNVS, TSLX,
AMRZ, HLNE) could not be priced at all. A scorecard that grades 6% of its own
universe is not a ruler.

This lane closes the gap from the OTHER side: it takes the names the ledger
actually carries and fetches their history once, off the render path, a bounded
slice per night. Masterplan: research/INTEL_HUB_LOBE_AUDIT_AND_UPGRADE_MASTERPLAN_BY_FABLE.md
§4 item 2(b).

SCHEMA PARITY IS THE HARD GATE
------------------------------
A second writer into data/yahoo is the silent-poison shape. ``close`` is
total-return (split+dividend) adjusted and ``close_price`` is split-only; a
backfilled frame that swaps them, drops one, reorders the columns, or lands a
tz-aware index reads as coverage and grades wrong, with no error anywhere. So
this script does NOT re-derive the rename: it calls the collector's own seam
(``collectors.yahoo.extract_store_frame`` -> ``YahooAdapter._extract``), the
collector's own validator (``Adapter.validate``) and the collector's own writer
(``lib.store.upsert``), then re-checks the result against
``collectors.yahoo.STORE_COLUMNS`` before it is allowed to stay. A frame that
fails that check is never written. tests/test_yahoo_universe_backfill.py pins it.

The dual-basis ratio ``close/close_price`` is reported, never enforced: it is
piecewise-constant with an upward step at each ex-dividend date and 1.0 at the
tip (measured across all 747 stored parquets: median 0.55% of bars step, max
8.3%, 746/747 tip at exactly 1.0). Constant-ratio segments are the DIVIDEND
ADJUSTMENT WORKING, not a defect, which is why an anomaly here annotates and
accrues instead of parking a name.

The one measured exception proves the point. Stored IBIT had tip ratio 1.002385
(total return BELOW split-only, which should be impossible) — and a full
period='max' re-pull of the same name returns tip 1.0 with zero anomalies. So the
anomaly was an artifact of the collector's WINDOWED upsert leaving pre-window rows
on a stale basis, not a property of the security or the vendor. A hard gate would
have refused a real name over a repairable store artifact; the refresh phase below
heals it instead, because a full re-pull IS the basis heal (lib.store.basis_shifted
documents why a short window cannot be).

NEVER A DEATH CLAIM
-------------------
A symbol this lane cannot fetch is parked as ``fetch_failed`` with the vendor's
error text. That is a statement about a request, not about a security: a name can
leave an index, be served under a renamed symbol, or be a non-US listing this
lane simply cannot reach, and every one of those looks identical to a 404 from
here. Nothing in this script writes ``lib/delisted_symbols`` or any other
lifecycle ledger, and a parked name keeps every row it already has.

KNOWN COUPLINGS THIS LANE CREATES (read before raising the cap)
---------------------------------------------------------------
1. ``scripts/run_us_scan_tier.py`` treats "has a data/yahoo parquet" as a proxy for
   "is in the curated roster" and EXCLUDES those names from the scan tier. That
   proxy stops holding the moment this lane runs: a parquet now means "the hub
   ledger mentioned it". Measured 2026-08-08, a fully drained queue would otherwise
   newly exclude 4,601 names from the scan tier (6,217 queued minus the 2,840
   already covered by data/stocks + the four breadth constituent lists). RESOLVED
   in the same PR: ``curated_universe`` now subtracts the names this lane created,
   reading ``state["done"]`` from ``data/yahoo_backfill_state.json``. That makes
   ``done`` a CONSUMED CONTRACT, not just provenance — its keys are ledger tickers
   and its ``backfilled`` date is set once, on creation, and never moved by a
   refresh.
2. Nothing else MAINTAINS a backfilled parquet, which is why this lane has a
   second phase (below). ``collectors/yahoo.py``'s fetch list is the config
   universe, so a name this lane creates would otherwise keep a frozen tip from
   the night it landed. The yahoo store-tip audit does NOT fire on these files
   either (``audit_store_freshness`` iterates ``maintained_tickers()``, not a
   directory glob — verified), so the staleness would be silent.

THE REFRESH PHASE, AND THE 7-DAY BOUND IT IS SIZED AGAINST
----------------------------------------------------------
Once the backfill queue under-fills ``--cap``, the remaining cap and budget go to
re-pulling the parquets nothing else advances: files whose stem is not in the
collector's maintained set, oldest tip first.

The cadence target comes from the house bar-lag convention:
``engine/name_score_grader.py:96 _MAX_BAR_LAG_DAYS = 7`` — "calendar days a name's
own last bar may lag the ledger stamp; beyond 7 the call is an echo of a dead or
stale feed" — already mirrored by ``collectors/yahoo.py:440 _STALE_CAL_DAYS``. A
tip more than ~7 calendar days old therefore buys nothing: the name reads as
uncovered again. So a full pass must complete in UNDER 7 days, and
``REFRESH_TARGET_CADENCE_D = 6`` keeps a day of slack for a vendor-slow night.

    per_run  = clip(ceil(n_refreshable / 6), 400, 1500)
    cadence  = n_refreshable / per_run          (printed in the run notice)

Dynamic rather than a fixed number so the cadence holds as the store grows instead
of silently lengthening past the bound. At the measured 181 ms/symbol:

    n_refreshable ~4.5k (expected steady state)  -> 750/night, 6.0d, ~192 s
    n_refreshable  6.2k (whole addressable set)  -> 1037/night, 6.0d, ~265 s
    clamp ceiling 1500                           -> ~383 s, inside --budget-s 480

A fixed 400/night over 6.2k names would be a ~16-day cadence — past the bound for
most of the rotation, i.e. a refresh phase that runs every night and fixes nothing.
That is the failure this arithmetic exists to prevent, and the notice prints the
achieved cadence so it cannot regress quietly (plus a ``::warning`` when it drifts
past the target).

NOTE on the citation: the brief for this phase named
``engine/ai_desk.py MAX_ASOF_STALE_DAYS=7``. No such constant exists anywhere in
the tree (checked 2026-08-08) — the real bound is ``_MAX_BAR_LAG_DAYS`` above.
``ai_desk._level_asof`` (:236) and ``desk_scorer.close_at`` (:96) are still
UNBOUNDED ``asof``-or-before lookups, which is masterplan §4 item 2(a) and a
separate lane. The 6-day target is therefore the right number for the wrong-cited
reason: it is what the house convention already implies, and it is what item 2(a)
will enforce when it lands.

INCREMENTAL AND RESUMABLE
-------------------------
The needed set is recomputed from DISK every run (ledger ∪ hub universe MINUS
the parquets that exist), so resumption is correct even if the state file is
deleted — the state file adds attempt counts, park decisions and provenance, not
correctness. Per-run work is bounded twice: ``--cap`` tickers and ``--budget-s``
wall-clock seconds, both printed.

Usage
-----
    python -m scripts.backfill_yahoo_universe                 # nightly shape
    python -m scripts.backfill_yahoo_universe --dry-run       # plan only, no network
    python -m scripts.backfill_yahoo_universe --cap 5         # live smoke
    python -m scripts.backfill_yahoo_universe --cap 800 --budget-s 900
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

# Make the repo root importable when run as a plain script (python scripts/...).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.yahoo import STORE_COLUMNS, YahooAdapter, extract_store_frame  # noqa: E402
from lib import config, store  # noqa: E402
from lib.ticker_aliases import fetch_symbol  # noqa: E402

log = logging.getLogger(__name__)

STATE_FILE = "yahoo_backfill_state.json"
STATE_SCHEMA = "yahoo_backfill_state/1"

#: The hub signal ledger. NOTE the masterplan and the brief both say
#: "data/hub/track_record.json ledger" — track_record.json is the computed
#: SUMMARY (schema/as_of/horizons/ic; verified 2026-08-08, no per-ticker rows).
#: The ledger it summarises is this jsonl, one {date,t,opp,edge,stage,lean} row
#: per (date, ticker) — the same constant engine/hub_track_record.py:44 uses.
LEDGER = ("hub", "signal_snapshots.jsonl")
HUB_JSON = ("intel_hub", "hub.json")

#: hub.json lists whose names are the CURRENT surface — priority 1.
CURRENT_LISTS = ("command", "emerging", "discovery")
#: hub.json lists that also name real universe members (they join the needed set
#: but rank by ledger recency like everything else).
OTHER_LISTS = ("exhausted", "catalysts")

#: A symbol this lane can plausibly ask Yahoo for: a US-shaped root, optionally
#: with a one-to-three character class/series suffix. The ledger carries plenty
#: that is not (measured 886 of the 7,108 missing on 2026-08-08): China/HK
#: numeric board codes (000100, 002070) that belong to the china/hk planes, and
#: parse artifacts ('()', 'N/A', 'ASX:PEX', 'CONSECUTIVE'). Requesting those
#: spends nightly budget to learn nothing. They are recorded as
#: ``unsupported_symbol`` — again a statement about THIS lane's reach, not about
#: the security.
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9]{0,8}([.\-][A-Z0-9]{1,3})?$")

#: US class shares are served by Yahoo with a dash: BRK.B -> BRK-B. This is a
#: punctuation convention, not a rename, so it does NOT belong in
#: lib/ticker_aliases (that map is for genuine vendor/membership disagreements
#: and each entry there must be verified by a live pull). Verified live on
#: BRK.B during this lane's smoke run.
CLASS_SHARE_RE = re.compile(r"^[A-Z]{1,4}\.[A-Z]{1,2}$")

#: Below this many bars nothing downstream can read the file (trajectory needs
#: ~30, a 20d horizon needs 21) — it is still written, because a real short
#: history is honest coverage, but the count is reported so a run that produced
#: only stubs cannot look like a run that produced stores.
SHORT_HISTORY_ROWS = 30

#: Refresh-phase cadence target, in CALENDAR days. Must stay strictly under the
#: house 7-day bar-lag bound (see the module docstring), with a day of slack for a
#: vendor-slow night that truncates a pass.
REFRESH_TARGET_CADENCE_D = 6
#: Clamp on the computed per-night refresh size. The floor keeps a small store
#: moving; the ceiling keeps one pass inside the step's wall-clock budget
#: (1,500 x 181 ms + 75 batch sleeps ~= 383 s, under the 480 s default).
REFRESH_CAP_MIN = 400
REFRESH_CAP_MAX = 1500

#: Ratio diagnostics (soft). Tolerances from the measured store, see the
#: module docstring.
RATIO_TOL = 1e-6
RATIO_STEP_FRACTION_MAX = 0.15
RATIO_MIN_ROWS = 60


# ---------------------------------------------------------------------------
# universe
# ---------------------------------------------------------------------------
def ledger_last_seen(data_dir: Path | None = None) -> dict[str, str]:
    """{ticker: latest ISO date it appears in the hub signal ledger}.

    Streamed line by line: the ledger is ~19 MB / 170k rows on 2026-08-08 and
    grows ~2.9k rows a night, so json.load of the whole thing is the
    unbounded-scan shape this repo keeps stubbing its toe on."""
    p = (data_dir or config.data_dir()).joinpath(*LEDGER)
    out: dict[str, str] = {}
    if not p.exists():
        log.warning("hub signal ledger absent at %s — universe falls back to hub.json", p)
        return out
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            t, d = row.get("t"), row.get("date")
            if not t or not d:
                continue
            if t not in out or d > out[t]:
                out[t] = d
    return out


def hub_universe(site_dir: Path | None = None) -> tuple[set[str], set[str]]:
    """(current-surface tickers, every ticker hub.json names).

    The current surface is priority 1: those are the names a reader is looking at
    tonight, and the ones whose missing parquet shows up as a blank cell."""
    p = (site_dir or config.site_dir()).joinpath(*HUB_JSON)
    if not p.exists():
        log.warning("hub.json absent at %s — universe is the ledger alone", p)
        return set(), set()
    with open(p) as f:
        hub = json.load(f)
    current: set[str] = set()
    every: set[str] = set()
    for key in CURRENT_LISTS + OTHER_LISTS:
        for row in hub.get(key) or []:
            if not isinstance(row, dict):
                continue
            t = row.get("ticker") or row.get("t")
            if not t:
                continue
            every.add(t)
            if key in CURRENT_LISTS:
                current.add(t)
    return current, every


def stored_tickers(data_dir: Path | None = None) -> set[str]:
    """Every ticker that already has a data/yahoo parquet — the done marker.

    Read from disk, not from the state file: the parquet's existence is what the
    graders actually test, so it is what must decide the needed set."""
    d = (data_dir or config.data_dir()) / "yahoo"
    if not d.exists():
        return set()
    return {p.stem for p in d.glob("*.parquet")}


def addressable(ticker: str) -> bool:
    """True when this lane can plausibly ask Yahoo for the symbol (SYMBOL_RE)."""
    return bool(SYMBOL_RE.match(ticker))


def store_stem(name: str) -> str:
    """The parquet stem ``lib.store`` writes ``name`` under.

    Derived from ``store._path`` rather than re-implementing its character map,
    because a second copy of that map is exactly how the two drift. It matters
    here: the collector maintains ``CL=F`` / ``USDJPY=X`` / ``^GSPC``, whose files
    are ``CL_F`` / ``USDJPY_X`` / ``_GSPC``. Comparing a directory stem against
    the raw config ticker misses all of them — measured 2026-08-08, a naive
    compare called 38 collector-maintained FX/commodity series "non-maintained",
    which would have had the refresh phase re-pulling them nightly under a symbol
    yfinance 404s and parking all 38."""
    return store._path("yahoo", name).stem


def maintained_stems() -> set[str] | None:
    """Parquet stems the NIGHTLY COLLECTOR owns — the set a refresh must not touch.

    ``maintained_tickers()`` (not ``all_tickers()``) so a delisted name whose store
    the collector still carries is also left alone.

    Returns None — NOT an empty set — when the set cannot be resolved. An empty set
    would read as "nothing is maintained", making every parquet in the directory a
    refresh candidate: fail-OPEN, in the one direction that trespasses on the
    collector's own series. The caller treats None as "skip the refresh phase"."""
    try:
        return {store_stem(t) for t in YahooAdapter().maintained_tickers()}
    except Exception as e:  # noqa: BLE001 — fail CLOSED (see above)
        log.warning("refresh: could not resolve the collector's maintained set (%s) — "
                    "refresh phase skipped this run", e)
        return None


def vendor_symbol(ticker: str) -> str:
    """The string that goes to yfinance for a ledger ticker.

    House alias table first (a genuine vendor/membership rename), then the US
    class-share dot->dash convention. Fetched under this, STORED under the
    ledger ticker — the ledger key is the join key for every downstream reader."""
    sym = fetch_symbol(ticker)
    if sym != ticker:
        return sym
    if CLASS_SHARE_RE.match(ticker):
        return ticker.replace(".", "-")
    return ticker


def needed_queue(state: dict, today: date | None = None, recent_days: int = 90,
                 data_dir: Path | None = None,
                 site_dir: Path | None = None) -> tuple[list[tuple[str, int]], dict]:
    """The ordered work queue plus a census of how it was derived.

    Needed = (ledger tickers ∪ hub.json universe) MINUS tickers that already have
    a parquet. Priority buckets, in order:

      1. the current hub surface (command / emerging / discovery)
      2. anything the ledger saw within ``recent_days``
      3. the rest of the ledger

    Within a bucket: fewest attempts first, then alphabetical — so a name that
    has already burned a retry never crowds out a name that has never been asked,
    and the order is deterministic across runs (resumability).

    Parked names and symbols this lane cannot address are excluded entirely."""
    today = today or datetime.now(timezone.utc).date()
    last_seen = ledger_last_seen(data_dir)
    current, hub_every = hub_universe(site_dir)
    have = stored_tickers(data_dir)
    parked = state.get("parked") or {}
    pending = state.get("pending") or {}

    universe = set(last_seen) | hub_every
    missing = {t for t in universe if t not in have}
    unsupported = sorted(t for t in missing if not addressable(t))
    workable = sorted(t for t in missing if addressable(t))

    cutoff = (today - timedelta(days=recent_days)).isoformat()
    buckets: dict[str, int] = {}
    for t in workable:
        if t in current:
            buckets[t] = 1
        elif last_seen.get(t, "") >= cutoff:
            buckets[t] = 2
        else:
            buckets[t] = 3

    queue = [(t, buckets[t]) for t in workable if t not in parked]
    queue.sort(key=lambda tb: (tb[1], int((pending.get(tb[0]) or {}).get("attempts", 0)), tb[0]))

    census = {
        "ledger_tickers": len(last_seen),
        "hub_universe": len(hub_every),
        "hub_current_surface": len(current),
        "union_needed": len(universe),
        "already_stored": len(have),
        "missing": len(missing),
        "unsupported_symbols": len(unsupported),
        "unsupported_sample": unsupported[:12],
        "parked": len(parked),
        "queue": len(queue),
        "bucket_1_current": sum(1 for _, b in queue if b == 1),
        "bucket_2_recent": sum(1 for _, b in queue if b == 2),
        "bucket_3_rest": sum(1 for _, b in queue if b == 3),
    }
    return queue, census


# ---------------------------------------------------------------------------
# gates
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# refresh phase (post-drain)
# ---------------------------------------------------------------------------
def refresh_cap_for(n_refreshable: int) -> int:
    """How many names to refresh tonight to hold the target cadence.

    ceil(n / REFRESH_TARGET_CADENCE_D), clamped to [REFRESH_CAP_MIN,
    REFRESH_CAP_MAX]. Dynamic rather than a fixed number so the cadence holds as
    the store grows instead of silently lengthening past the staleness bound —
    the whole point of the phase. See the module docstring for the arithmetic and
    the measured runtime at each end of the clamp."""
    if n_refreshable <= 0:
        return 0
    want = -(-n_refreshable // REFRESH_TARGET_CADENCE_D)   # ceil
    return max(REFRESH_CAP_MIN, min(REFRESH_CAP_MAX, want))


def cadence_days(n_refreshable: int, per_run: int) -> float:
    """Calendar days for one full pass over the refreshable set at ``per_run``/night.

    Printed in the run notice because it is the number that decides whether this
    phase is doing its job: past the ~7-day bar-lag bound a refreshed name is no
    better than an unrefreshed one."""
    if n_refreshable <= 0 or per_run <= 0:
        return 0.0
    # Floored at 0.1 so a small population reads as "well inside a day" rather than
    # "0.0d", which would look like the phase did not run. 0.0 stays reserved for
    # "nothing is refreshable".
    return max(0.1, round(n_refreshable / per_run, 1))


def refresh_candidates(state: dict, data_dir: Path | None = None) -> tuple[list[str], int]:
    """(tonight's refresh order, total refreshable) — oldest tip first.

    Refreshable = a data/yahoo parquet whose stem is NOT in the collector's
    maintained set and is not parked. Those are precisely the files nothing else
    advances: the collector's fetch list is the config universe, so a name this
    lane created has a frozen tip from the night it landed.

    Ordering key is the stored tip. For a name this lane wrote, that is
    ``state["done"][t]["last_obs"]`` — free, and accurate because a non-maintained
    file has no other writer and this lane rewrites the entry on every touch. Only
    names with no such entry are read off disk (measured 1.3 ms/file, so ~9 s if
    the whole 6.8k store ever needed reading, versus ~0 s in the steady state).
    Order alone rides on it: the refresh re-pulls period='max' either way, so a
    stale ordering key costs at most a suboptimal pick, never correctness."""
    d = (data_dir or config.data_dir()) / "yahoo"
    if not d.exists():
        return [], 0
    maintained = maintained_stems()
    if maintained is None:
        return [], 0
    done = state.get("done") or {}
    parked = state.get("parked") or {}
    tips: list[tuple[str, str]] = []
    for p in sorted(d.glob("*.parquet")):
        stem = p.stem
        if stem.startswith("_") or stem in maintained or stem in parked:
            continue
        entry = done.get(stem) or {}
        tip = entry.get("last_obs")
        if not tip:
            try:
                tip = str(pd.read_parquet(p).index.max().date())
            except Exception:  # noqa: BLE001 — an unreadable file is not a refresh target
                continue
        tips.append((stem, str(tip)))
    tips.sort(key=lambda st: (st[1], st[0]))       # oldest tip first, then alphabetical
    return [t for t, _ in tips], len(tips)


def schema_violation(frame: pd.DataFrame | None) -> str | None:
    """HARD gate. The reason this frame must not be written, or None.

    Everything here is a contract with readers that never call this module:
    engine/trajectory.py and engine/desk_grader.py open the parquet and index
    ``close`` directly, and the hub ledger joins on a naive daily index."""
    if frame is None or len(frame) == 0:
        return "empty frame"
    cols = tuple(frame.columns)
    if cols != STORE_COLUMNS:
        return f"columns {cols} != collector schema {STORE_COLUMNS}"
    # close / close_price must be float — they are prices and every reader does
    # float math on them. volume is deliberately looser: the collector's OWN store
    # carries both dtypes (measured 2026-08-08: 667 files float64, 74 int64),
    # because yfinance returns int64 for a homogeneous batch and float64 once
    # NaN-padding kicks in on a heterogeneous one. Neither is "the" schema, so
    # this lane accepts what the vendor sends and coerces nothing — a cast here
    # would make backfilled files differ from 74 collector-produced ones in the
    # other direction.
    bad_price = [c for c in ("close", "close_price") if frame[c].dtype.kind != "f"]
    if bad_price:
        return f"non-float price columns {bad_price}"
    if frame["volume"].dtype.kind not in "fiu":
        return f"non-numeric volume dtype {frame['volume'].dtype}"
    if not isinstance(frame.index, pd.DatetimeIndex):
        return f"index is {type(frame.index).__name__}, not DatetimeIndex"
    if frame.index.tz is not None:
        return f"tz-aware index ({frame.index.tz}) — the store is tz-naive daily"
    if frame.index.has_duplicates:
        return "duplicate index dates"
    if not frame.index.is_monotonic_increasing:
        return "index is not sorted ascending"
    if frame["close"].isna().any():
        return "NaN in close (the column every grader reads)"
    if float(frame["close"].min()) <= 0:
        return f"non-positive close (min {float(frame['close'].min()):.6g})"
    if len(frame) < 2:
        return f"{len(frame)} row(s) — a one-bar stub, not a series"
    return None


def ratio_report(frame: pd.DataFrame) -> dict:
    """SOFT dual-basis diagnostics for close/close_price.

    Expected shape (measured over the whole stored store, see module docstring):
    piecewise-constant with an upward step at each ex-dividend date, <= 1.0
    throughout, and exactly 1.0 at the tip. A CONSTANT-RATIO SEGMENT IS THE
    DIVIDEND ADJUSTMENT WORKING — flagging it would be flagging the feature. What
    is worth naming is the opposite: a ratio that moves on nearly every bar (the
    two bases are not the two bases), a ratio above 1 (total return below
    split-only), or a tip off 1.0.

    Reported, never enforced. Measured counterexample: stored IBIT breaks both the
    tip and the <=1 rule (1.002385), and a full re-pull of the same name comes back
    at exactly 1.0 — so the anomaly was a stale-basis STORE artifact, not a property
    of the security. Parking on it would have cost a real name over something the
    refresh phase repairs, in a column no grader reads."""
    ratio = (frame["close"] / frame["close_price"]).replace(
        [float("inf"), float("-inf")], pd.NA).dropna().astype(float)
    out: dict = {"rows": int(len(frame)), "ratio_rows": int(len(ratio)), "anomalies": []}
    if ratio.empty:
        out["anomalies"].append("no comparable close/close_price rows")
        return out
    tip = float(ratio.iloc[-1])
    top = float(ratio.max())
    out["tip_ratio"] = round(tip, 9)
    out["max_ratio"] = round(top, 9)
    if abs(tip - 1.0) > RATIO_TOL:
        out["anomalies"].append(f"tip ratio {tip:.6f} != 1.0")
    if top > 1.0 + RATIO_TOL:
        out["anomalies"].append(f"max ratio {top:.6f} > 1.0 (TR below split-only)")
    if len(ratio) >= RATIO_MIN_ROWS:
        rel = (ratio.diff() / ratio.shift()).dropna().abs()
        frac = float((rel > RATIO_TOL).mean()) if len(rel) else 0.0
        out["step_fraction"] = round(frac, 6)
        if frac > RATIO_STEP_FRACTION_MAX:
            out["anomalies"].append(
                f"{frac:.1%} of bars step (> {RATIO_STEP_FRACTION_MAX:.0%}) — the two "
                f"bases do not look like TR vs split-only")
    return out


# ---------------------------------------------------------------------------
# state
# ---------------------------------------------------------------------------
def state_path(data_dir: Path | None = None) -> Path:
    return (data_dir or config.data_dir()) / STATE_FILE


def load_state(data_dir: Path | None = None) -> dict:
    p = state_path(data_dir)
    if not p.exists():
        return {"schema": STATE_SCHEMA, "done": {}, "parked": {}, "pending": {}}
    try:
        with open(p) as f:
            s = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        # A corrupt state file must not stop the lane: the needed set comes from
        # disk, so the worst a reset costs is a repeated attempt count.
        print(f"::warning title=yahoo-backfill::state file unreadable ({e}) — starting "
              f"from a fresh one; the needed set is recomputed from disk so no "
              f"coverage is lost, only attempt counts", flush=True)
        return {"schema": STATE_SCHEMA, "done": {}, "parked": {}, "pending": {}}
    for key in ("done", "parked", "pending"):
        s.setdefault(key, {})
    s["schema"] = STATE_SCHEMA
    return s


def save_state(state: dict, data_dir: Path | None = None) -> Path:
    p = state_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    state["updated_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(p, "w") as f:
        json.dump(state, f, indent=1, sort_keys=True)
    return p


# ---------------------------------------------------------------------------
# fetch
# ---------------------------------------------------------------------------
def download_batch(symbols: list[str], period: str) -> pd.DataFrame | None:
    """One yfinance batch, with the collector's request shape.

    ``auto_adjust=False`` is load-bearing: it is what returns BOTH Close
    (split-adjusted, dividend-UNadjusted) and Adj Close (total return), which is
    the dual basis the store carries. Raises on a transport/vendor failure;
    returns None when the response came back empty (every symbol in the batch
    returned nothing — evidence about the SYMBOLS, not about the network, which is
    why the caller attributes it per ticker)."""
    df = yf.download(symbols, period=period, auto_adjust=False,
                     progress=False, group_by="ticker", threads=True)
    if df is None or df.empty:
        return None
    return df


def slice_symbol(df: pd.DataFrame, symbol: str) -> pd.DataFrame | None:
    """The flat single-symbol frame for ``symbol`` out of a batch response.

    Returned FLAT so ``extract_store_frame`` never re-slices by the alias-table
    symbol: this lane may have requested a symbol the alias table does not carry
    (BRK.B -> BRK-B), and the store key must stay the ledger ticker."""
    if isinstance(df.columns, pd.MultiIndex):
        if symbol not in df.columns.get_level_values(0):
            return None
        sub = df[symbol]
    else:
        sub = df
    sub = sub.dropna(how="all")
    return None if sub.empty else sub


#: What a park MEANS, per phase. Both are statements about a REQUEST.
_PARK_NOTE = {
    "backfill": "no data returned for the requested symbol; NOT a delisting or "
                "death claim — this lane cannot distinguish a 404 from a renamed, "
                "non-US, or otherwise unreachable listing",
    "refresh": "the stored series could not be re-pulled; the EXISTING parquet is "
               "KEPT UNTOUCHED (stale-but-present beats absent — the ~7d bar-lag "
               "bound reports its staleness honestly downstream). NOT a delisting "
               "or death claim, and not a coverage loss",
}


def _mark_attempt(state: dict, ticker: str, error: str, max_attempts: int,
                  phase: str = "backfill") -> bool:
    """Record one failed attempt; park the ticker once it has spent them all.

    ``fetch_failed`` / ``refresh_failed`` is a statement about a REQUEST. A name can
    leave an index, move to a symbol nobody told us about, or be a listing this lane
    cannot reach — all of them 404 identically from here, and none of them means the
    security stopped existing. Nothing here touches lib/delisted_symbols, and nothing
    here deletes, truncates or invalidates a parquet: a park removes a name from the
    fetch queue and does nothing else. Returns True when this attempt parked it."""
    pending = state.setdefault("pending", {})
    entry = pending.get(ticker) or {"attempts": 0}
    entry["attempts"] = int(entry.get("attempts", 0)) + 1
    entry["error"] = f"[{phase}] {error}"[:300]
    entry["last_attempt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if entry["attempts"] >= max_attempts:
        pending.pop(ticker, None)
        state.setdefault("parked", {})[ticker] = {
            "reason": "refresh_failed" if phase == "refresh" else "fetch_failed",
            "note": _PARK_NOTE.get(phase, _PARK_NOTE["backfill"]),
            "attempts": entry["attempts"],
            "error": entry["error"],
            "parked_utc": entry["last_attempt"],
        }
        return True
    pending[ticker] = entry
    return False


def run(cap: int = 400, batch_size: int = 20, sleep_s: float = 1.5,
        budget_s: float = 480.0, period: str = "max", max_attempts: int = 3,
        recent_days: int = 90, refresh_cap: int = 0, dry_run: bool = False,
        today: date | None = None) -> dict:
    """One bounded slice of the lane: the backfill phase, then the refresh phase.

    The refresh phase only starts when the backfill queue UNDER-FILLED the cap, so
    during the ~16 drain nights it never competes for the budget; once the queue is
    empty it inherits the whole allowance. Both phases share one wall clock."""
    t0 = time.monotonic()
    state = load_state()
    queue, census = needed_queue(state, today=today, recent_days=recent_days)
    plan = queue[:max(0, cap)]

    report: dict = {
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "cap": cap, "period": period, "batch_size": batch_size,
        "budget_s": budget_s, "dry_run": bool(dry_run),
        "planned": len(plan), "written": 0, "short_history": 0,
        "attempted": 0, "no_data": 0, "parked": 0, "schema_rejected": 0,
        "ratio_anomalies": 0, "batch_errors": 0, "budget_exhausted": False,
        "refresh_planned": 0, "refreshed": 0, "refreshable": 0,
        "refresh_cap": 0, "refresh_cadence_d": 0.0, "refresh_ran": False,
        "census": census,
    }

    # The refresh plan is resolved BEFORE any fetch so --dry-run can print it and
    # so the cadence number in the notice describes tonight's actual intent.
    refresh_plan: list[str] = []
    if len(plan) < cap:
        candidates, n_refreshable = refresh_candidates(state)
        chosen = refresh_cap if refresh_cap > 0 else refresh_cap_for(n_refreshable)
        refresh_plan = candidates[:max(0, chosen)]
        report["refreshable"] = n_refreshable
        report["refresh_cap"] = chosen
        report["refresh_planned"] = len(refresh_plan)
        report["refresh_cadence_d"] = cadence_days(n_refreshable, chosen)
        report["refresh_ran"] = bool(refresh_plan)

    if dry_run:
        report["plan_sample"] = [t for t, _ in plan[:20]]
        report["refresh_sample"] = refresh_plan[:20]
        report["elapsed_s"] = round(time.monotonic() - t0, 1)
        # Nothing was written, so nothing came off the queue.
        report["remaining"] = census["queue"]
        _emit(report)
        return report

    adapter = YahooAdapter()
    no_adj_close: list[str] = []
    schema_rejects: list[str] = []
    anomalies: dict[str, list[str]] = {}

    def _work(tickers: list[str], phase: str) -> None:
        """Fetch, gate and store one phase's names. Identical path for both phases —
        the refresh re-pulls period='max' exactly as the backfill does, which is also
        what makes it the adjustment-basis heal (a full re-pull rebases the whole
        series; see lib.store.basis_shifted for why a short window cannot)."""
        for i in range(0, len(tickers), max(1, batch_size)):
            if time.monotonic() - t0 > budget_s:
                report["budget_exhausted"] = True
                log.info("%s: wall-clock budget %.0fs spent — stopping before batch %d",
                         phase, budget_s, i // max(1, batch_size) + 1)
                return
            batch = tickers[i:i + max(1, batch_size)]
            symbols = {t: vendor_symbol(t) for t in batch}
            try:
                df = download_batch(sorted(set(symbols.values())), period)
            except Exception as e:  # noqa: BLE001 — transport failure is not symbol evidence
                report["batch_errors"] += 1
                log.warning("%s: batch of %d failed (%s) — no attempt charged to those "
                            "names; they lead the queue again next run", phase, len(batch), e)
                time.sleep(sleep_s)
                continue

            for ticker in batch:
                report["attempted"] += 1
                sub = None if df is None else slice_symbol(df, symbols[ticker])
                if sub is None:
                    report["no_data"] += 1
                    if _mark_attempt(state, ticker,
                                     f"no data returned for vendor symbol "
                                     f"{symbols[ticker]!r}", max_attempts, phase=phase):
                        report["parked"] += 1
                    continue
                try:
                    frame = extract_store_frame(sub, ticker, no_adj_close=no_adj_close)
                    frame = None if frame is None else adapter.validate(ticker, frame)
                except Exception as e:  # noqa: BLE001 — one bad response is not the run
                    report["no_data"] += 1
                    if _mark_attempt(state, ticker, f"extract/validate failed: {e}",
                                     max_attempts, phase=phase):
                        report["parked"] += 1
                    continue
                violation = schema_violation(frame)
                if violation:
                    # NEVER written. A frame that diverges from the collector's schema
                    # is worse than a missing file: it reads as coverage and grades wrong.
                    # On a REFRESH that also means the existing parquet is left exactly
                    # as it was — a refusal never degrades what is already on disk.
                    report["schema_rejected"] += 1
                    schema_rejects.append(f"{ticker}: {violation}")
                    if _mark_attempt(state, ticker, f"schema gate: {violation}",
                                     max_attempts, phase=phase):
                        report["parked"] += 1
                    continue
                diag = ratio_report(frame)
                if diag["anomalies"]:
                    report["ratio_anomalies"] += 1
                    anomalies[ticker] = diag["anomalies"]
                store.upsert("yahoo", ticker, frame)
                entry = state.setdefault("done", {}).get(ticker) or {}
                entry.update({
                    "rows": int(len(frame)),
                    "last_obs": frame.index.max().date().isoformat(),
                })
                # `backfilled` is the provenance date the scan-tier exclusion reads —
                # set once, on the night the file was CREATED, and never moved by a
                # refresh. `refreshed` carries the cadence evidence separately.
                today_iso = datetime.now(timezone.utc).date().isoformat()
                entry.setdefault("backfilled", today_iso)
                if phase == "refresh":
                    entry["refreshed"] = today_iso
                    report["refreshed"] += 1
                else:
                    report["written"] += 1
                state["done"][ticker] = entry
                state.get("pending", {}).pop(ticker, None)
                if len(frame) < SHORT_HISTORY_ROWS:
                    report["short_history"] += 1
            time.sleep(sleep_s)

    _work([t for t, _ in plan], "backfill")
    if refresh_plan and not report["budget_exhausted"]:
        _work(refresh_plan, "refresh")

    if no_adj_close:
        log.info("backfill: %d name(s) had no Adj Close (close_price=close, no "
                 "dividends): %s", len(no_adj_close), no_adj_close[:20])
    if schema_rejects:
        # Loud: the hard gate firing means a writer and its readers disagree.
        print(f"::warning title=yahoo-backfill-schema::{len(schema_rejects)} frame(s) "
              f"REFUSED by the store-schema gate and not written: "
              f"{'; '.join(schema_rejects[:5])}", flush=True)
    if anomalies:
        print(f"::warning title=yahoo-backfill-basis::{len(anomalies)} backfilled "
              f"name(s) have unexpected close/close_price structure (written anyway — "
              f"constant-ratio segments are the dividend adjustment working, these are "
              f"not that): "
              f"{'; '.join(f'{t} {v[0]}' for t, v in list(anomalies.items())[:5])}",
              flush=True)

    report["elapsed_s"] = round(time.monotonic() - t0, 1)
    report["remaining"] = max(0, census["queue"] - report["written"])
    report["ratio_anomaly_names"] = {t: v for t, v in list(anomalies.items())[:40]}
    state["last_run"] = {k: v for k, v in report.items() if k != "census"}
    state["last_run"]["census"] = census
    save_state(state)
    _emit(report)
    return report


def _emit(report: dict) -> None:
    """The one line a nightly reader sees.

    BARE print, never through the logger: every builder here logs with a
    prefixing format, so ``log.info("::notice ...")`` emits ``INFO ::notice ...``
    and GitHub silently drops it — the annotation reviews as an alarm, runs clean,
    and produces nothing. ``flush`` because stdout is block-buffered when piped
    in CI. See tests/test_gh_annotation_line_start.py."""
    tail = ""
    if report.get("refresh_ran"):
        # The cadence is the number that decides whether the refresh phase is doing
        # its job at all: past the ~7d bar-lag bound a refreshed name grades no
        # better than an unrefreshed one, so it belongs in the one line a nightly
        # reader sees, not only in the state file.
        tail = (f", refreshed {report['refreshed']} of {report['refreshable']}, "
                f"refresh cadence ~{report['refresh_cadence_d']}d")
    print(f"::notice title=yahoo-backfill::backfilled {report['written']}, "
          f"parked {report['parked']}, remaining {report['remaining']}{tail}", flush=True)
    if report.get("refresh_ran") and report["refresh_cadence_d"] > REFRESH_TARGET_CADENCE_D:
        print(f"::warning title=yahoo-backfill-cadence::refresh cadence is "
              f"~{report['refresh_cadence_d']}d over {report['refreshable']} "
              f"non-maintained series, past the {REFRESH_TARGET_CADENCE_D}d target — "
              f"names near the tail of the rotation will read as stale to the graders. "
              f"Raise --refresh-cap or REFRESH_CAP_MAX", flush=True)
    log.info("yahoo backfill run: %s", json.dumps(
        {k: v for k, v in report.items() if k not in ("census", "ratio_anomaly_names")},
        default=str))
    c = report["census"]
    log.info("universe census: %d ledger tickers, %d missing a parquet, %d queue "
             "(%d current / %d recent / %d rest), %d unsupported symbols, %d parked",
             c["ledger_tickers"], c["missing"], c["queue"], c["bucket_1_current"],
             c["bucket_2_recent"], c["bucket_3_rest"], c["unsupported_symbols"],
             c["parked"])
    if report.get("budget_exhausted"):
        log.info("budget: stopped at %.0fs of a %.0fs allowance with %d of %d planned "
                 "names attempted", report["elapsed_s"], report["budget_s"],
                 report["attempted"], report["planned"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__ and __doc__.splitlines()[0])
    ap.add_argument("--cap", type=int, default=400,
                    help="max tickers to attempt this run (default 400)")
    ap.add_argument("--batch-size", type=int, default=20,
                    help="symbols per yfinance request (default 20)")
    ap.add_argument("--sleep", type=float, default=1.5,
                    help="seconds between batches (default 1.5)")
    ap.add_argument("--budget-s", type=float, default=480.0,
                    help="wall-clock seconds after which no new batch starts (default 480)")
    ap.add_argument("--period", default="max",
                    help="yfinance period for the first pull (default max)")
    ap.add_argument("--max-attempts", type=int, default=3,
                    help="failed fetches before a name is parked as fetch_failed "
                         "(default 3 — a park is never a death claim)")
    ap.add_argument("--recent-days", type=int, default=90,
                    help="ledger recency window for priority bucket 2 (default 90)")
    ap.add_argument("--refresh-cap", type=int, default=0,
                    help="names to refresh once the backfill queue under-fills --cap; "
                         "0 (default) computes it from the cadence target — "
                         f"ceil(n/{REFRESH_TARGET_CADENCE_D}) clamped to "
                         f"[{REFRESH_CAP_MIN}, {REFRESH_CAP_MAX}]")
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print both plans; no network, no writes")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    run(cap=a.cap, batch_size=a.batch_size, sleep_s=a.sleep, budget_s=a.budget_s,
        period=a.period, max_attempts=a.max_attempts, recent_days=a.recent_days,
        refresh_cap=a.refresh_cap, dry_run=a.dry_run)
    # Always 0: this is an additive, non-fatal lane. A backfill that got nothing
    # tonight must never red the night's collect job — the ::notice/::warning
    # lines above carry the outcome.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
