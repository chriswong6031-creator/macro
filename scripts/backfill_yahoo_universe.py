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
8.3%, 746/747 tip at exactly 1.0 — the sole exception is IBIT). Constant-ratio
segments are the DIVIDEND ADJUSTMENT WORKING, not a defect, which is why an
anomaly here annotates and accrues instead of parking a name.

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
1. ``scripts/run_us_scan_tier.py:90`` treats "has a data/yahoo parquet" as a proxy
   for "is in the curated roster" and EXCLUDES those names from the scan tier.
   That proxy stops holding the moment this lane runs: a parquet now means "the
   hub ledger mentioned it". Measured 2026-08-08, a fully drained queue would
   newly exclude 4,601 names from the scan tier (6,217 queued minus the 2,840
   already covered by data/stocks + the four breadth constituent lists). The
   affordance for fixing it lives in this lane's state file — ``state["done"]``
   is the exact provenance set to subtract from that glob — but the repair
   belongs to that lane, not this one. UNRESOLVED as of this commit.
2. Nothing MAINTAINS a backfilled parquet. ``collectors/yahoo.py``'s fetch list is
   the config universe, so a name this lane creates has a frozen tip from the
   night it landed. That is enough for a backward-looking grade of an already-
   matured horizon, and NOT enough to grade a signal fired after the backfill
   date. Closing that needs the maintenance half (either these names join the
   collector's fetch list or this lane grows a refresh leg) — deliberately out of
   scope here, because the coverage gap has to close before maintaining it means
   anything. The yahoo store-tip audit does NOT fire on these files
   (``audit_store_freshness`` iterates ``maintained_tickers()``, not a directory
   glob — verified), so their staleness is silent today.

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

    Reported, never enforced: IBIT is a live counterexample to both the tip and
    the <=1 rule, and parking it would be parking a name over a vendor quirk in a
    column no grader reads."""
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


def _mark_attempt(state: dict, ticker: str, error: str, max_attempts: int) -> bool:
    """Record one failed attempt; park the ticker once it has spent them all.

    ``fetch_failed`` is a statement about a REQUEST. A name can leave an index,
    move to a symbol nobody told us about, or be a listing this lane cannot
    reach — all of them 404 identically from here, and none of them means the
    security stopped existing. Nothing here touches lib/delisted_symbols.
    Returns True when this attempt parked the name."""
    pending = state.setdefault("pending", {})
    entry = pending.get(ticker) or {"attempts": 0}
    entry["attempts"] = int(entry.get("attempts", 0)) + 1
    entry["error"] = error[:300]
    entry["last_attempt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if entry["attempts"] >= max_attempts:
        pending.pop(ticker, None)
        state.setdefault("parked", {})[ticker] = {
            "reason": "fetch_failed",
            "note": "no data returned for the requested symbol; NOT a delisting or "
                    "death claim — this lane cannot distinguish a 404 from a renamed, "
                    "non-US, or otherwise unreachable listing",
            "attempts": entry["attempts"],
            "error": entry["error"],
            "parked_utc": entry["last_attempt"],
        }
        return True
    pending[ticker] = entry
    return False


def run(cap: int = 400, batch_size: int = 20, sleep_s: float = 1.5,
        budget_s: float = 480.0, period: str = "max", max_attempts: int = 3,
        recent_days: int = 90, dry_run: bool = False,
        today: date | None = None) -> dict:
    """One bounded slice of the backfill. Returns the run report."""
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
        "census": census,
    }
    if dry_run:
        report["plan_sample"] = [t for t, _ in plan[:20]]
        report["elapsed_s"] = round(time.monotonic() - t0, 1)
        # Nothing was written, so nothing came off the queue.
        report["remaining"] = census["queue"]
        _emit(report)
        return report

    adapter = YahooAdapter()
    no_adj_close: list[str] = []
    schema_rejects: list[str] = []
    anomalies: dict[str, list[str]] = {}

    for i in range(0, len(plan), max(1, batch_size)):
        if time.monotonic() - t0 > budget_s:
            report["budget_exhausted"] = True
            log.info("backfill: wall-clock budget %.0fs spent — stopping before batch %d",
                     budget_s, i // max(1, batch_size) + 1)
            break
        batch = [t for t, _ in plan[i:i + max(1, batch_size)]]
        symbols = {t: vendor_symbol(t) for t in batch}
        try:
            df = download_batch(sorted(set(symbols.values())), period)
        except Exception as e:  # noqa: BLE001 — a transport failure is not symbol evidence
            report["batch_errors"] += 1
            log.warning("backfill: batch of %d failed (%s) — no attempt charged to those "
                        "names; they lead the queue again next run", len(batch), e)
            time.sleep(sleep_s)
            continue

        for ticker in batch:
            report["attempted"] += 1
            sub = None if df is None else slice_symbol(df, symbols[ticker])
            if sub is None:
                report["no_data"] += 1
                if _mark_attempt(state, ticker,
                                 f"no data returned for vendor symbol {symbols[ticker]!r}",
                                 max_attempts):
                    report["parked"] += 1
                continue
            try:
                frame = extract_store_frame(sub, ticker, no_adj_close=no_adj_close)
                frame = None if frame is None else adapter.validate(ticker, frame)
            except Exception as e:  # noqa: BLE001 — one malformed response is not the run
                report["no_data"] += 1
                if _mark_attempt(state, ticker, f"extract/validate failed: {e}",
                                 max_attempts):
                    report["parked"] += 1
                continue
            violation = schema_violation(frame)
            if violation:
                # NEVER written. A frame that diverges from the collector's schema
                # is worse than a missing file: it reads as coverage and grades wrong.
                report["schema_rejected"] += 1
                schema_rejects.append(f"{ticker}: {violation}")
                if _mark_attempt(state, ticker, f"schema gate: {violation}", max_attempts):
                    report["parked"] += 1
                continue
            diag = ratio_report(frame)
            if diag["anomalies"]:
                report["ratio_anomalies"] += 1
                anomalies[ticker] = diag["anomalies"]
            store.upsert("yahoo", ticker, frame)
            state.setdefault("done", {})[ticker] = {
                "backfilled": datetime.now(timezone.utc).date().isoformat(),
                "rows": int(len(frame)),
                "last_obs": frame.index.max().date().isoformat(),
            }
            state.get("pending", {}).pop(ticker, None)
            report["written"] += 1
            if len(frame) < SHORT_HISTORY_ROWS:
                report["short_history"] += 1
        time.sleep(sleep_s)

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
    print(f"::notice title=yahoo-backfill::backfilled {report['written']}, "
          f"parked {report['parked']}, remaining {report['remaining']}", flush=True)
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
    ap.add_argument("--dry-run", action="store_true",
                    help="compute and print the plan; no network, no writes")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    run(cap=a.cap, batch_size=a.batch_size, sleep_s=a.sleep, budget_s=a.budget_s,
        period=a.period, max_attempts=a.max_attempts, recent_days=a.recent_days,
        dry_run=a.dry_run)
    # Always 0: this is an additive, non-fatal lane. A backfill that got nothing
    # tonight must never red the night's collect job — the ::notice/::warning
    # lines above carry the outcome.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
