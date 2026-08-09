#!/usr/bin/env python3
"""One-shot: re-stamp data/polygon_gex from UTC RUN-DATE to NYSE SESSION date.

WHY (measured 2026-08-06).  ``scripts/build_polygon_gex.accrue`` stamped
``datetime.now(timezone.utc).date()`` — the RUN date, not the session the snapshot
describes.  A nightly run that lands at 01:24 UTC carries the PREVIOUS ET session's
closing chain but was filed under the next calendar day, so the whole store sat one
session forward of the market it measures, and the write-side ``is_session`` gate then
REFUSED every Saturday-UTC run — which is a Friday-evening ET accrual.  That is why
Fridays are missing from the store.

The true accrual instant per historical file is recoverable from git
(``git log -1 --format=%cI -- <path>``; the LAST commit produced the current content
because ``.to_parquet()`` overwrites).  Mapping those instants through
``nyse_calendar.expected_last_session`` (17:00 ET settle buffer) reproduces the data:
30 of 42 files verify SPY spot == the yahoo close of the resolved session to the cent.
``session_date()`` is the WRONG helper here — it calls the whole ET calendar day "the
session", so at 02:24 ET Wednesday it returns Wednesday for a chain carrying Tuesday's
close.

VERIFICATION IS ON THE CROSS-SECTION, NOT ON SPY.  For each file, for every underlying
with a local price series, this compares ``abs(close(session) - spot)/spot``.  SPY alone
called the 08-06 file "0.175% — fine" while 59% of its names disagreed: its spot column
is a live pre-market tape, not 08-05 closes.

    Classification: CLEAN iff median error < 0.05% AND within-0.5% rate >= 90%.

Weekend/holiday runs re-snapshot the same closed-market state, so 42 files collapse to
29 sessions.  Collision winner: prefer CLEAN, then lowest median error, then widest
underlying count, then earliest stamp.  Disposition:

  * 24 CLEAN survivors  -> re-date the chains file + the summary rows.  This is the store.
  * 13 collision losers -> removed (pure duplicates of a kept session).
  *  5 MIXED survivors  -> QUARANTINED (removed).  Their spot column is a live
                           intraday/pre-market tape, so every spot-derived GEX field
                           (net_gex_bn, gamma_flip, dist_to_flip_pct, magnets, max_pain)
                           was computed off a price that is not the session's close, and
                           their OI provenance is ambiguous (a pre-market snapshot may
                           predate the OCC OI refresh).

NOTHING IS DESTROYED.  Every removed blob stays in git history; the committed manifest
(docs/polygon_gex_session_stamp_migration.json) records, per file, the original stamp,
the git-recovered accrual instant, the resolved session, the classification, the measured
metrics, the disposition, and the commit SHA where the blob remains recoverable.  The
instants MUST be frozen there because this migration's own commit rewrites the history of
those paths.

FAIL-CLOSED.  Verification runs BEFORE any write.  The measured outcome is checked
against the pinned adjudication below; any deviation aborts non-zero with a diff and
touches nothing.  Re-running after a successful apply is a clean no-op (every stamp is
already a session date).

Usage
-----
    python -m scripts.migrate_polygon_gex_session_stamps            # dry-run (default)
    python -m scripts.migrate_polygon_gex_session_stamps --apply
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from lib import config, nyse_calendar  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GROUP = "polygon_gex"
MANIFEST_PATH = ROOT / "docs" / "polygon_gex_session_stamp_migration.json"

# ── classification thresholds (pinned adjudication 2026-08-06) ───────────────
MEDIAN_ERR_PCT_MAX = 0.05      # median |close(session) - spot| / spot, in PERCENT
WITHIN_RATE_MIN_PCT = 90.0     # share of names inside WITHIN_TOL_PCT, in PERCENT
WITHIN_TOL_PCT = 0.5
# The tiebreak compares medians at the precision the adjudication was stated in
# (4 decimals of a percent).  Without the rounding, float noise below the printed
# precision would decide a tie that the adjudication decides on BREADTH — session
# 2026-06-18 keeps the 345-name file over two 10-name files that are equally exact.
MEDIAN_TIEBREAK_DECIMALS = 4

KEEP, DROP, QUARANTINE = "keep", "drop", "quarantine"

# ── the pinned adjudication (stamp -> session, class, disposition) ───────────
# Measured over the 42 committed chains files on 2026-08-06.  This is the ruling, not
# an implementation detail: a re-run that computes anything else ABORTS rather than
# quietly migrating to a different store.
PINNED_ADJUDICATION: dict[str, tuple[str, str, str]] = {
    "2026-06-15": ("2026-06-15", "CLEAN", KEEP),
    "2026-06-16": ("2026-06-15", "CLEAN", DROP),
    "2026-06-17": ("2026-06-17", "CLEAN", KEEP),
    "2026-06-18": ("2026-06-17", "MIXED", DROP),
    "2026-06-19": ("2026-06-18", "CLEAN", DROP),
    "2026-06-20": ("2026-06-18", "CLEAN", DROP),
    "2026-06-21": ("2026-06-18", "CLEAN", KEEP),
    "2026-06-22": ("2026-06-18", "MIXED", DROP),
    "2026-06-23": ("2026-06-22", "MIXED", QUARANTINE),
    "2026-06-24": ("2026-06-24", "CLEAN", KEEP),
    "2026-06-25": ("2026-06-24", "MIXED", DROP),
    "2026-06-26": ("2026-06-25", "MIXED", QUARANTINE),
    "2026-06-27": ("2026-06-26", "CLEAN", KEEP),
    "2026-06-28": ("2026-06-26", "CLEAN", DROP),
    "2026-06-29": ("2026-06-26", "CLEAN", DROP),
    "2026-06-30": ("2026-06-29", "MIXED", QUARANTINE),
    "2026-07-01": ("2026-06-30", "CLEAN", KEEP),
    "2026-07-02": ("2026-07-01", "CLEAN", KEEP),
    "2026-07-05": ("2026-07-02", "CLEAN", KEEP),
    "2026-07-07": ("2026-07-06", "MIXED", QUARANTINE),
    "2026-07-08": ("2026-07-07", "CLEAN", KEEP),
    "2026-07-09": ("2026-07-08", "CLEAN", KEEP),
    "2026-07-10": ("2026-07-09", "CLEAN", KEEP),
    "2026-07-12": ("2026-07-10", "CLEAN", KEEP),
    "2026-07-13": ("2026-07-10", "MIXED", DROP),
    "2026-07-14": ("2026-07-13", "CLEAN", KEEP),
    "2026-07-16": ("2026-07-15", "CLEAN", KEEP),
    "2026-07-18": ("2026-07-17", "CLEAN", KEEP),
    "2026-07-19": ("2026-07-17", "CLEAN", DROP),
    "2026-07-20": ("2026-07-17", "CLEAN", DROP),
    "2026-07-21": ("2026-07-20", "CLEAN", KEEP),
    "2026-07-22": ("2026-07-21", "CLEAN", KEEP),
    "2026-07-23": ("2026-07-22", "CLEAN", KEEP),
    "2026-07-24": ("2026-07-23", "CLEAN", KEEP),
    "2026-07-25": ("2026-07-24", "CLEAN", KEEP),
    "2026-07-26": ("2026-07-24", "CLEAN", DROP),
    "2026-07-27": ("2026-07-24", "CLEAN", DROP),
    "2026-07-28": ("2026-07-27", "CLEAN", KEEP),
    "2026-07-29": ("2026-07-28", "CLEAN", KEEP),
    "2026-07-30": ("2026-07-29", "CLEAN", KEEP),
    "2026-07-31": ("2026-07-30", "CLEAN", KEEP),
    "2026-08-06": ("2026-08-05", "MIXED", QUARANTINE),
}


# ═══════════════════════════════════════════════════════════════════════════
# provenance
# ═══════════════════════════════════════════════════════════════════════════
def _git(*args: str) -> str:
    out = subprocess.run(("git", *args), cwd=ROOT, capture_output=True, text=True,
                         check=False)
    return out.stdout.strip()


def _git_last_touch(rel_path: str) -> tuple[datetime | None, str]:
    """(commit instant in UTC, commit SHA) of the LAST commit that touched `rel_path`.

    The last write is the one that produced the current content — ``.to_parquet()``
    overwrites, so earlier commits of the same path hold superseded snapshots.  The SHA
    is also the recovery pointer: ``git show <sha>:<path>`` returns the blob after this
    migration removes it from the working tree.
    """
    raw = _git("log", "-1", "--format=%cI%x09%H", "--", rel_path)
    if not raw or "\t" not in raw:
        return None, ""
    iso, sha = raw.split("\t", 1)
    try:
        return datetime.fromisoformat(iso).astimezone(timezone.utc), sha.strip()
    except ValueError:
        return None, sha.strip()


# ═══════════════════════════════════════════════════════════════════════════
# price reference (cross-section verifier)
# ═══════════════════════════════════════════════════════════════════════════
_PRICE_CACHE: dict[str, pd.Series | None] = {}


def _price_series(sym: str) -> pd.Series | None:
    """Local daily close series for `sym`: data/yahoo first, data/stocks as fallback.

    None when neither store carries the name — that is an UNVERIFIABLE underlying, never
    a failure (roughly 84-95 of ~370 chain names have no local series).
    """
    if sym in _PRICE_CACHE:
        return _PRICE_CACHE[sym]
    dd = config.data_dir()
    out: pd.Series | None = None
    for p in (dd / "yahoo" / f"{sym}.parquet", dd / "stocks" / f"{sym}.parquet"):
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p)
        except Exception:  # noqa: BLE001 — a corrupt price file is "unverifiable"
            continue
        if "close" not in df.columns or df.empty:
            continue
        s = pd.to_numeric(df["close"], errors="coerce").dropna()
        if s.empty:
            continue
        s.index = pd.to_datetime(s.index).normalize()
        out = s[~s.index.duplicated(keep="last")]
        break
    _PRICE_CACHE[sym] = out
    return out


@dataclass
class Metrics:
    underlyings: int = 0
    checkable: int = 0
    unverifiable: int = 0
    median_abs_err_pct: float | None = None
    within_0_5pct_rate: float | None = None
    exact_to_the_cent_rate: float | None = None
    worst_abs_err_pct: float | None = None


def _verify_cross_section(chain: pd.DataFrame, session: date) -> Metrics:
    """Per-underlying |close(session) - spot| / spot, in percent, over the whole chain."""
    ts = pd.Timestamp(session)
    spots = (chain.groupby("underlying", observed=True)["spot"].first()
             .astype("float64").dropna())
    m = Metrics(underlyings=int(len(spots)))
    errs: list[float] = []
    exact = 0
    for sym, spot in spots.items():
        sym = str(sym)
        if not spot or spot <= 0:
            m.unverifiable += 1
            continue
        s = _price_series(sym)
        if s is None or ts not in s.index:
            m.unverifiable += 1
            continue
        close = float(s.loc[ts])
        if close <= 0:
            m.unverifiable += 1
            continue
        errs.append(abs(close - spot) / spot * 100.0)
        # float32 storage of the spot costs ~6e-5 on a $700 name, so "to the cent"
        # is a cent plus that representation slack — never a bare equality.
        if abs(close - spot) <= 0.005 + 1e-5 * close:
            exact += 1
    m.checkable = len(errs)
    if errs:
        se = pd.Series(errs)
        m.median_abs_err_pct = round(float(se.median()), 6)
        m.within_0_5pct_rate = round(float((se <= WITHIN_TOL_PCT).mean() * 100.0), 4)
        m.exact_to_the_cent_rate = round(exact / len(errs) * 100.0, 4)
        m.worst_abs_err_pct = round(float(se.max()), 6)
    return m


def _classify(m: Metrics) -> str:
    """CLEAN iff median error < 0.05% AND within-0.5% rate >= 90%. Unverifiable = MIXED."""
    if m.checkable == 0 or m.median_abs_err_pct is None:
        return "MIXED"
    return ("CLEAN" if (m.median_abs_err_pct < MEDIAN_ERR_PCT_MAX
                        and m.within_0_5pct_rate >= WITHIN_RATE_MIN_PCT) else "MIXED")


# ═══════════════════════════════════════════════════════════════════════════
# plan
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class Record:
    original_stamp: str
    original_path: str
    accrual_instant_utc: str | None
    accrual_instant_et: str | None
    resolved_session: str
    classification: str
    metrics: dict
    disposition: str = ""
    new_path: str | None = None
    reason: str = ""
    recovery_sha: str = ""
    collision_group: list[str] = field(default_factory=list)


def _chains_dir() -> Path:
    return config.data_dir() / GROUP / "chains"


def _chain_files() -> list[Path]:
    return sorted(_chains_dir().glob("*.parquet"))


def _summary_files() -> list[Path]:
    return sorted((config.data_dir() / GROUP).glob("summary_*.parquet"))


def _stamp_of(p: Path) -> date | None:
    try:
        return date.fromisoformat(p.stem)
    except ValueError:
        return None


def already_migrated() -> bool:
    """True when every chains stamp AND every summary index date is an NYSE session."""
    for p in _chain_files():
        d = _stamp_of(p)
        if d is None or not nyse_calendar.is_session(d):
            return False
    for p in _summary_files():
        try:
            idx = pd.read_parquet(p).index
        except Exception:  # noqa: BLE001
            return False
        for t in idx:
            if not nyse_calendar.is_session(pd.Timestamp(t).date()):
                return False
    return True


def build_plan() -> list[Record]:
    """Measure every chains file, resolve collisions, assign dispositions."""
    records: list[Record] = []
    for p in _chain_files():
        stamp = _stamp_of(p)
        if stamp is None:
            raise SystemExit(f"unparseable chains filename: {p}")
        rel = str(p.relative_to(ROOT))
        instant, sha = _git_last_touch(rel)
        if instant is None:
            raise SystemExit(
                f"no git history for {rel} — the accrual instant is unrecoverable, so "
                "the session cannot be resolved. Commit the file or remove it, then re-run.")
        session = nyse_calendar.expected_last_session(instant)
        chain = pd.read_parquet(p, columns=["underlying", "spot"])
        m = _verify_cross_section(chain, session)
        records.append(Record(
            original_stamp=stamp.isoformat(),
            original_path=rel,
            accrual_instant_utc=instant.isoformat(),
            accrual_instant_et=instant.astimezone(nyse_calendar.ET).isoformat(),
            resolved_session=session.isoformat(),
            classification=_classify(m),
            metrics=asdict(m),
            recovery_sha=sha,
        ))

    by_session: dict[str, list[Record]] = defaultdict(list)
    for r in records:
        by_session[r.resolved_session].append(r)

    def _rank(r: Record):
        med = r.metrics["median_abs_err_pct"]
        return (
            0 if r.classification == "CLEAN" else 1,
            round(med, MEDIAN_TIEBREAK_DECIMALS) if med is not None else float("inf"),
            -int(r.metrics["underlyings"]),
            r.original_stamp,
        )

    for session, group in sorted(by_session.items()):
        group_stamps = sorted(r.original_stamp for r in group)
        ordered = sorted(group, key=_rank)
        winner = ordered[0]
        for r in group:
            r.collision_group = group_stamps
        for r in ordered[1:]:
            r.disposition = DROP
            r.reason = (f"collision loser for session {session} — duplicate of "
                        f"{winner.original_stamp} (a closed-market re-snapshot of the "
                        "same session state)")
        if winner.classification == "CLEAN":
            winner.disposition = KEEP
            winner.new_path = str(
                (_chains_dir() / f"{session}.parquet").relative_to(ROOT))
            winner.reason = (f"CLEAN survivor — re-dated {winner.original_stamp} -> "
                             f"{session}")
        else:
            winner.disposition = QUARANTINE
            winner.reason = (
                f"MIXED survivor for session {session} — spot is a live intraday/"
                "pre-market tape, so every spot-derived GEX field (net_gex_bn, "
                "gamma_flip, dist_to_flip_pct, magnet_up/down, max_pain) was computed "
                "off a price that is not the session close; OI provenance is also "
                f"ambiguous. Session {session} becomes an honest gap.")
    return records


# ═══════════════════════════════════════════════════════════════════════════
# verification gate — runs BEFORE any write
# ═══════════════════════════════════════════════════════════════════════════
def verify_plan(records: list[Record]) -> list[str]:
    """Every reason the plan must NOT be applied. Empty list = go."""
    problems: list[str] = []
    measured = {r.original_stamp: (r.resolved_session, r.classification, r.disposition)
                for r in records}

    missing = sorted(set(PINNED_ADJUDICATION) - set(measured))
    unexpected = sorted(set(measured) - set(PINNED_ADJUDICATION))
    if missing:
        problems.append(f"pinned stamps absent from the store: {missing}")
    if unexpected:
        problems.append(
            f"chains files the adjudication never ruled on: {unexpected} — re-adjudicate "
            "before migrating (do NOT widen this script to absorb them)")
    for stamp in sorted(set(measured) & set(PINNED_ADJUDICATION)):
        if measured[stamp] != PINNED_ADJUDICATION[stamp]:
            problems.append(
                f"{stamp}: measured (session={measured[stamp][0]}, "
                f"class={measured[stamp][1]}, disp={measured[stamp][2]}) != pinned "
                f"(session={PINNED_ADJUDICATION[stamp][0]}, "
                f"class={PINNED_ADJUDICATION[stamp][1]}, "
                f"disp={PINNED_ADJUDICATION[stamp][2]})")

    for r in records:
        if r.disposition != KEEP:
            continue
        m = r.metrics
        if not nyse_calendar.is_session(date.fromisoformat(r.resolved_session)):
            problems.append(f"{r.original_stamp}: resolved session "
                            f"{r.resolved_session} is not an NYSE session")
        if m["checkable"] == 0:
            problems.append(f"{r.original_stamp}: zero verifiable underlyings — a kept "
                            "file must be verified, never assumed")
            continue
        if m["median_abs_err_pct"] >= MEDIAN_ERR_PCT_MAX:
            problems.append(
                f"{r.original_stamp}: median error {m['median_abs_err_pct']:.4f}% >= "
                f"{MEDIAN_ERR_PCT_MAX}% against session {r.resolved_session}")
        if m["within_0_5pct_rate"] < WITHIN_RATE_MIN_PCT:
            problems.append(
                f"{r.original_stamp}: within-{WITHIN_TOL_PCT}% rate "
                f"{m['within_0_5pct_rate']:.1f}% < {WITHIN_RATE_MIN_PCT}% against "
                f"session {r.resolved_session}")

    keeps = [r for r in records if r.disposition == KEEP]
    sessions = [r.resolved_session for r in keeps]
    if len(set(sessions)) != len(sessions):
        problems.append("two kept files resolve to the same session — collision "
                        "resolution is broken")
    # The one-file-at-a-time rename below is only collision-free while every target
    # session is <= its source stamp (a snapshot never describes a FUTURE session).
    for r in keeps:
        if r.resolved_session > r.original_stamp:
            problems.append(f"{r.original_stamp}: resolves FORWARD to "
                            f"{r.resolved_session} — refusing to rename")
    return problems


# ═══════════════════════════════════════════════════════════════════════════
# reporting
# ═══════════════════════════════════════════════════════════════════════════
def print_table(records: list[Record]) -> None:
    hdr = (f"{'stamp':<11} {'-> session':<12} {'class':<6} {'names':>5} {'chk':>4} "
           f"{'median%':>9} {'w/in .5%':>9} {'exact%':>7}  disposition")
    print(hdr)
    print("-" * len(hdr))
    for r in sorted(records, key=lambda x: x.original_stamp):
        m = r.metrics
        med = "n/a" if m["median_abs_err_pct"] is None else f"{m['median_abs_err_pct']:.4f}"
        win = "n/a" if m["within_0_5pct_rate"] is None else f"{m['within_0_5pct_rate']:.1f}"
        exa = ("n/a" if m["exact_to_the_cent_rate"] is None
               else f"{m['exact_to_the_cent_rate']:.1f}")
        print(f"{r.original_stamp:<11} {r.resolved_session:<12} {r.classification:<6} "
              f"{m['underlyings']:>5} {m['checkable']:>4} {med:>9} {win:>9} {exa:>7}  "
              f"{r.disposition}")
    n = {d: sum(1 for r in records if r.disposition == d)
         for d in (KEEP, DROP, QUARANTINE)}
    print(f"\n{len(records)} files -> "
          f"{len({r.resolved_session for r in records})} sessions -> "
          f"{n[KEEP]} kept ({n[DROP]} collision losers dropped, "
          f"{n[QUARANTINE]} MIXED survivors quarantined)")
    clean = sum(1 for r in records if r.classification == "CLEAN")
    print(f"classification: {clean} CLEAN, {len(records) - clean} MIXED")


def write_manifest(records: list[Record], applied: bool) -> None:
    payload = {
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "applied": applied,
        "what": ("polygon_gex re-stamped from UTC run-date to NYSE session date "
                 "(scripts/migrate_polygon_gex_session_stamps.py)"),
        "session_resolver": "lib.nyse_calendar.expected_last_session (17:00 ET settle buffer)",
        "provenance": ("accrual instants recovered from `git log -1 --format=%cI -- <path>` "
                       "BEFORE this migration rewrote the history of those paths — they are "
                       "not recoverable from git afterwards, which is why they are frozen here"),
        "verification": ("cross-section: per underlying with a local price series "
                         "(data/yahoo/<S>.parquet close, fallback data/stocks/<S>.parquet), "
                         "abs(close(session) - spot) / spot"),
        "classification_rule": {
            "clean_iff": f"median_abs_err_pct < {MEDIAN_ERR_PCT_MAX} AND "
                         f"within_{WITHIN_TOL_PCT}pct_rate >= {WITHIN_RATE_MIN_PCT}",
        },
        "collision_rule": ("prefer CLEAN, then lowest median error, then widest "
                           "underlying count, then earliest stamp"),
        "recovery": ("nothing is destroyed: `git show <recovery_sha>:<original_path>` "
                     "returns any removed blob"),
        "totals": {
            "files": len(records),
            "sessions": len({r.resolved_session for r in records}),
            "clean": sum(1 for r in records if r.classification == "CLEAN"),
            "mixed": sum(1 for r in records if r.classification == "MIXED"),
            "kept": sum(1 for r in records if r.disposition == KEEP),
            "dropped": sum(1 for r in records if r.disposition == DROP),
            "quarantined": sum(1 for r in records if r.disposition == QUARANTINE),
        },
        "files": [asdict(r) for r in sorted(records, key=lambda x: x.original_stamp)],
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"manifest -> {MANIFEST_PATH.relative_to(ROOT)}")


# ═══════════════════════════════════════════════════════════════════════════
# apply
# ═══════════════════════════════════════════════════════════════════════════
def apply_plan(records: list[Record]) -> None:
    chains = _chains_dir()
    removed = [r for r in records if r.disposition in (DROP, QUARANTINE)]
    keeps = sorted((r for r in records if r.disposition == KEEP),
                   key=lambda r: r.original_stamp)

    # 1. Remove losers/quarantines FIRST so the rename pass below cannot collide with
    #    a stamp that is on its way out.
    for r in removed:
        p = ROOT / r.original_path
        if p.exists():
            p.unlink()
    print(f"removed {len(removed)} chains files "
          f"({sum(1 for r in removed if r.disposition == DROP)} losers, "
          f"{sum(1 for r in removed if r.disposition == QUARANTINE)} quarantined)")

    # 2. Re-date the survivors in ascending stamp order. Every target session is <= its
    #    source stamp and all targets are distinct, so at each step the only file that
    #    can occupy the target is the source itself (an identity re-date).
    for r in keeps:
        src = ROOT / r.original_path
        dst = ROOT / r.new_path
        if dst.exists() and dst != src:
            raise SystemExit(f"refusing to overwrite {dst} while re-dating {src}")
        df = pd.read_parquet(src)
        ts = pd.Timestamp(r.resolved_session)
        for col in df.columns:
            if col == "asof":
                df[col] = pd.Series([ts] * len(df), index=df.index).astype("datetime64[ms]")
            elif col != "expiry" and pd.api.types.is_datetime64_any_dtype(df[col]):
                # `expiry` is a contract property, not a stamp — everything else that
                # carries the accrual date must move with the file.
                raise SystemExit(
                    f"{src}: unexpected datetime column {col!r} — it may embed the old "
                    "stamp. Inspect it and extend this migration before re-running.")
        df.to_parquet(dst)
        if dst != src:
            src.unlink()
    print(f"re-dated {len(keeps)} chains files")

    # 3. Summaries: re-index stamp -> session, drop rows whose file left the store.
    remap = {r.original_stamp: r.resolved_session for r in keeps}
    n_written = n_deleted = n_rows_dropped = 0
    for p in _summary_files():
        df = pd.read_parquet(p)
        stamps = [pd.Timestamp(t).strftime("%Y-%m-%d") for t in df.index]
        mask = [s in remap for s in stamps]
        n_rows_dropped += len(df) - sum(mask)
        kept = df[mask]
        if kept.empty:
            p.unlink()
            n_deleted += 1
            continue
        idx = pd.DatetimeIndex(
            [pd.Timestamp(remap[s]) for s, keep in zip(stamps, mask) if keep]
        ).astype("datetime64[ms]")
        kept = kept.set_axis(idx, axis=0).sort_index()
        if kept.index.duplicated().any():
            raise SystemExit(f"{p}: duplicate session index after re-dating — aborting")
        kept.index.name = df.index.name
        kept.to_parquet(p)
        n_written += 1
    print(f"summaries: {n_written} rewritten, {n_deleted} deleted (no surviving rows), "
          f"{n_rows_dropped} rows dropped")


def assert_store_is_session_clean() -> None:
    bad_files = [p.name for p in _chain_files()
                 if (_stamp_of(p) is None or not nyse_calendar.is_session(_stamp_of(p)))]
    bad_rows: list[str] = []
    for p in _summary_files():
        for t in pd.read_parquet(p).index:
            if not nyse_calendar.is_session(pd.Timestamp(t).date()):
                bad_rows.append(f"{p.name}:{pd.Timestamp(t).date()}")
    if bad_files or bad_rows:
        raise SystemExit(f"POST-MIGRATION CHECK FAILED — non-session chains files: "
                         f"{bad_files[:10]}; non-session summary rows: {bad_rows[:10]}")
    print(f"post-check OK: {len(_chain_files())} chains files and every row of "
          f"{len(_summary_files())} summary files are NYSE session dates")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="write the migration (default is a dry run)")
    args = ap.parse_args()

    if already_migrated():
        print("polygon_gex is already session-stamped — nothing to do (idempotent no-op)")
        return 0

    records = build_plan()
    print_table(records)

    problems = verify_plan(records)
    if problems:
        print("\nVERIFICATION FAILED — nothing written:", file=sys.stderr)
        for msg in problems:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    print("\nverification OK: every kept file matches the resolved session's closes and "
          "the plan matches the pinned adjudication")

    if not args.apply:
        print("\n(dry run — pass --apply to write)")
        return 0

    # The manifest is written BEFORE the data mutation so the provenance survives an
    # interrupted apply (the git-recovered instants are gone once this commit lands).
    write_manifest(records, applied=True)
    apply_plan(records)
    assert_store_is_session_clean()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
