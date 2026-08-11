"""engine.price_pressure.completion — the §10.1 VIXCLS stamp-completion pass.

Registered contract: ``research/PRICE_PRESSURE_R4_VIX_GRADIENT_PREREG.md`` §3
("Lag completion (§10.1)") and §10 item 1.  The problem it exists for, in the
prereg's own measurement: the VIXCLS store trails the tape by one session at
the 22:30Z harvest (store last observation 2026-08-06 while 2026-08-07 had
already traded), so a forward row typically stamps ``vix_pctile = NULL``
through no property of its own — and under the exclusion rule that preceded
this amendment **both evidence arms would have starved to zero permanently**,
an ungradeable registration by construction.

The repair, implemented here literally:

* a **non-null** stamp is immutable and decides the arm forever — this pass
  never touches one, and never recomputes one;
* a **null-at-harvest** stamp is completed ONCE, null → t0's own close
  percentile under the shipped §3 transform (``context.vix_percentile_of`` on
  ``context.clean_vix_closes`` — the same construction the harvest ranks, not a
  re-typed copy), an exact late-arriving value and never a forward-fill;
* only by the first subsequent **nightly producer** run on which t0 is present
  in the store, and only while that row's ``fwd5`` endpoint is still immature.
  Grading-time code may consume the receipt but is forbidden to complete a
  stamp itself;
* the completing producer appends an immutable receipt binding row identity,
  the completed value, ``observed_at``, and the exact SHA-256 of the VIXCLS
  file bytes the value was computed from;
* a row that misses its window is **left null forever** — counted and logged,
  never repaired.

Two structural properties worth stating because they are the whole safety case:

**Receipts are appended only after the ledger write succeeds.**  ``run`` writes
nothing; it returns the completed frame and the receipts it would file, and the
caller (``pipeline.advance``) appends them only once ``write_ledger`` reports
``written``.  A receipt filed against a write that was skipped — the off-nightly
lane, say — would fence the row out of its own completion window forever, which
is the one way this pass could permanently destroy evidence.

**The pass is O(rows with a null stamp).**  It scans one boolean column and then
loops only the nulls; a 35k-row ledger with three null stamps does three
lookups, not 35,000.
"""
from __future__ import annotations

import hashlib
import io
import json
import logging
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from engine.price_pressure import ENGINE_VERSION
from engine.price_pressure import context as _ctx
from engine.price_pressure import ledger as _ledger

log = logging.getLogger("price_pressure.completion")

RECEIPTS_REL: tuple[str, ...] = ("price_pressure", "completion_receipts.jsonl")

#: The endpoint whose maturity closes the completion window (prereg §3: "before
#: that row's ``fwd5`` endpoint matures").  R4-A's registered horizon.
MATURITY_HORIZON = 5

#: Belt and braces on the same window, measured in SESSIONS from t0 to the run's
#: asof.  ``fwd5`` alone would leave a row whose panel slice is ungradeable
#: (a halted name, a torn store) completable indefinitely; the session distance
#: closes that door on the calendar instead of on the tape.
MAX_COMPLETION_SESSIONS = 5

#: Receipt field order.  Frozen: the file is append-only and immutable, so a
#: reordering would make yesterday's lines and today's lines different shapes.
RECEIPT_FIELDS: tuple[str, ...] = (
    "ticker", "date", "side", "vix_pctile", "observed_at", "vixcls_sha256",
    "engine_version",
)

_COUNTERS: tuple[str, ...] = (
    "candidates", "completed", "skipped_matured", "skipped_no_vix",
    "skipped_receipted",
)


# ---------------------------------------------------------------------------
# receipts (append-only, never rewritten, never reordered)
# ---------------------------------------------------------------------------

def receipts_path(data_root: Path) -> Path:
    return Path(data_root).joinpath(*RECEIPTS_REL)


def read_receipts(data_root: Path) -> list[dict]:
    """Every receipt on file, oldest first.  Never raises.

    A torn line is skipped rather than fatal: the receipts file is evidence, and
    a half-written tail must not take the nightly down with it.  Skipping is
    safe in the direction that matters — a row whose receipt is unreadable still
    carries a non-null stamp in the ledger, so it can never be re-completed.
    """
    p = receipts_path(data_root)
    if not p.exists():
        return []
    out: list[dict] = []
    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("price_pressure: completion receipts unreadable at %s (%s)", p, exc)
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:  # noqa: BLE001 — a torn tail is not a reason to die
            log.debug("price_pressure: skipping unparseable completion receipt line")
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def receipt_keys(receipts: Iterable[dict]) -> set[tuple[str, str, str]]:
    """``{(ticker, date, side)}`` — the row identity a receipt fences off."""
    keys: set[tuple[str, str, str]] = set()
    for r in receipts:
        t, d, s = r.get("ticker"), r.get("date"), r.get("side")
        if t is None or d is None or s is None:
            continue
        keys.add((str(t), str(d), str(s)))
    return keys


def encode_receipt(rec: dict) -> str:
    """One JSONL line: frozen field order, no trailing whitespace."""
    return json.dumps({k: rec[k] for k in RECEIPT_FIELDS}, ensure_ascii=False)


def append_receipts(data_root: Path, receipts: Sequence[dict]) -> int:
    """Append new receipts.  Existing lines are never read back out and rewritten.

    Opened in ``"a"`` mode on purpose — the file is immutable history, so the
    only supported mutation is "one more line at the end".  The one byte this
    may add beyond the new lines is a missing final newline on a hand-edited
    file, without which the append would fuse itself onto the last record.
    """
    if not receipts:
        return 0
    p = receipts_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    prefix = ""
    if p.exists() and p.stat().st_size:
        with p.open("rb") as fh:
            fh.seek(-1, io.SEEK_END)
            if fh.read(1) != b"\n":
                prefix = "\n"
    with p.open("a", encoding="utf-8") as fh:
        fh.write(prefix + "".join(encode_receipt(r) + "\n" for r in receipts))
    return len(receipts)


# ---------------------------------------------------------------------------
# the VIXCLS read — value and hash off the SAME bytes
# ---------------------------------------------------------------------------

def read_vix(data_dir: Path) -> tuple[pd.Series, str | None]:
    """``(percentile series indexed by store date, sha256 of the file bytes)``.

    The bytes are read once and both outputs derive from that one read, so the
    receipt's hash provably identifies the artifact the completed value came
    from rather than whatever the file happened to be a moment later.  A missing
    or unreadable store yields an empty series and ``None`` — every candidate
    then counts as ``skipped_no_vix`` and waits for a later night.
    """
    path = _ctx.vix_store_path(data_dir)
    if not path.exists():
        return pd.Series(dtype="float64", index=pd.DatetimeIndex([])), None
    try:
        raw = path.read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        closes = _ctx.clean_vix_closes(pd.read_parquet(io.BytesIO(raw)))
        if closes.empty:
            return pd.Series(dtype="float64", index=pd.DatetimeIndex([])), sha
        return _ctx.vix_percentile_of(closes), sha
    except Exception as exc:  # noqa: BLE001 — a torn store is a gap, not a crash
        log.warning("price_pressure: VIXCLS unreadable for stamp completion (%s)", exc)
        return pd.Series(dtype="float64", index=pd.DatetimeIndex([])), None


# ---------------------------------------------------------------------------
# the pure planner
# ---------------------------------------------------------------------------

def plan_completions(df: pd.DataFrame, *, vix_pct: pd.Series,
                     sessions: pd.DatetimeIndex, asof: pd.Timestamp | None,
                     receipted: set[tuple[str, str, str]] | None = None,
                     max_sessions: int = MAX_COMPLETION_SESSIONS,
                     maturity_horizon: int = MATURITY_HORIZON,
                     ) -> tuple[list[dict], dict]:
    """Which null stamps may be completed tonight, and with what value.  Pure.

    ``vix_pct`` is the §3 percentile series indexed by the store's OWN cleaned
    dates, so membership in its index is exactly "t0 is present in the VIXCLS
    series" and ``.at[t0]`` is exactly "t0's own close percentile".

    Counters, all four printed by the caller:

    ``candidates``          rows carrying a null stamp (the whole working set).
    ``completed``           rows this run may fill.
    ``skipped_matured``     the window is gone — ``fwd{h}`` already graded, t0
                            more than ``max_sessions`` sessions back, or t0 off
                            the session axis entirely (fail closed).  These are
                            the prereg's "missing forever" rows.
    ``skipped_no_vix``      the window is open but the store cannot answer yet:
                            t0 absent from the series, or present with no
                            percentile (the 60-observation warm-up).  These wait
                            for a later night inside their window.
    ``skipped_receipted``   a receipt already exists for the row.  Belt and
                            braces — a completed row carries a non-null stamp
                            and so is never a candidate in the first place.
    """
    stats = {k: 0 for k in _COUNTERS}
    if df.empty or "vix_pctile" not in df.columns:
        return [], stats

    stamp = pd.to_numeric(df["vix_pctile"], errors="coerce")
    null_pos = np.flatnonzero(stamp.isna().to_numpy())
    stats["candidates"] = int(null_pos.size)
    if not null_pos.size:
        return [], stats

    fwd_col = f"fwd{maturity_horizon}"
    fwd = (pd.to_numeric(df[fwd_col], errors="coerce") if fwd_col in df.columns
           else pd.Series(np.nan, index=df.index, dtype="float64"))
    dates = pd.to_datetime(df["date"]).dt.normalize()
    tickers = df["ticker"].to_numpy()
    sides = df["side"].to_numpy()

    axis = pd.DatetimeIndex(sessions).normalize()
    spos = {d: i for i, d in enumerate(axis)}
    if asof is not None:
        asof_pos = spos.get(pd.Timestamp(asof).normalize())
        if asof_pos is None:
            asof_pos = len(axis) - 1
    else:
        asof_pos = len(axis) - 1

    pct_index = vix_pct.index if len(vix_pct) else pd.DatetimeIndex([])
    receipted = receipted or set()

    out: list[dict] = []
    for pos in null_pos:
        pos = int(pos)
        d0 = pd.Timestamp(dates.iloc[pos])
        key = (str(tickers[pos]), d0.strftime("%Y-%m-%d"), str(sides[pos]))

        if key in receipted:
            stats["skipped_receipted"] += 1
            continue

        i = spos.get(d0)
        if i is None or np.isfinite(fwd.iloc[pos]) or (asof_pos - i) > max_sessions:
            stats["skipped_matured"] += 1
            continue

        if d0 not in pct_index:
            stats["skipped_no_vix"] += 1
            continue
        v = vix_pct.at[d0]
        v = float(v) if pd.notna(v) else float("nan")
        if not np.isfinite(v):
            stats["skipped_no_vix"] += 1
            continue

        out.append({"pos": pos, "ticker": key[0], "date": key[1], "side": key[2],
                    "vix_pctile": v})
        stats["completed"] += 1
    return out, stats


# ---------------------------------------------------------------------------
# the runner seam (still writes nothing — see the module docstring)
# ---------------------------------------------------------------------------

def observed_stamp() -> str:
    """The completing run's UTC wall clock, second resolution, ISO-8601 Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(df: pd.DataFrame, data_root: Path, *, data_dir: Path,
        sessions: pd.DatetimeIndex, asof: pd.Timestamp | None,
        observed_at: str | None = None,
        max_sessions: int = MAX_COMPLETION_SESSIONS,
        maturity_horizon: int = MATURITY_HORIZON) -> dict:
    """Plan the completions and apply them to ``df``.  Persists NOTHING.

    Returns ``{"ledger", "receipts", "stats"}``.  The caller writes the ledger
    first and appends ``receipts`` only if that write actually landed.
    """
    vix_pct, sha = read_vix(data_dir)
    existing = receipt_keys(read_receipts(data_root))
    plan, stats = plan_completions(
        df, vix_pct=vix_pct, sessions=sessions, asof=asof, receipted=existing,
        max_sessions=max_sessions, maturity_horizon=maturity_horizon)

    if plan and sha is None:  # unreachable: an empty series plans nothing
        raise AssertionError("completion: planned a fill with no source hash")

    ledger = _ledger.complete_vix_stamps(df, plan) if plan else df
    stamped = observed_at or observed_stamp()
    receipts = [{"ticker": c["ticker"], "date": c["date"], "side": c["side"],
                 "vix_pctile": c["vix_pctile"], "observed_at": stamped,
                 "vixcls_sha256": sha, "engine_version": ENGINE_VERSION}
                for c in plan]
    stats["receipts"] = len(receipts)
    return {"ledger": ledger, "receipts": receipts, "stats": stats}


def log_line(stats: dict, *, appended: int | None = None) -> str:
    """The one summary line, formatted for the Actions log.

    Printed by the caller with a bare ``print(..., flush=True)`` at the start of
    the line: every builder here logs with a prefixing format, so anything that
    might one day carry a ``::`` prefix must never go through ``log.*``
    (house law, ``tests/test_gh_annotation_line_start.py``).
    """
    return ("price_pressure: vix stamp completion "
            f"candidates={stats.get('candidates', 0)} "
            f"completed={stats.get('completed', 0)} "
            f"skipped_matured={stats.get('skipped_matured', 0)} "
            f"skipped_no_vix={stats.get('skipped_no_vix', 0)} "
            f"receipts_appended={stats.get('receipts', 0) if appended is None else appended}")
