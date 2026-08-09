"""Limit-up pool (涨停板) — the A-share momentum / retail-froth plane.

Eastmoney publishes a per-name 涨停板 (daily-limit-up) pool: every name that hit
its +10%/+20% price ceiling on a given trading date, with how many consecutive
boards it has strung together (连板数), how much capital sealed the board (封板资金),
how many times the seal broke during the session (炸板次数), the day's turnover
(换手率) and the listed sector (所属行业).

  stock_zt_pool_em(date=YYYYMMDD) -> the whole limit-up pool for one trading date.

We walk back over OBSERVED Shanghai Composite sessions to the most recent
populated trading date and bake a flat per-name snapshot under
data/china_zt_pool/pool.parquet, refreshed once per UTC day.  Eastmoney may
replay the previous session when asked for a weekend/holiday, so a non-empty
payload is never accepted as proof of the requested session.

DISPLAY-ONLY context. A limit-up pool is the loudest LAGGING retail-momentum read
there is — 连板 leaders (龙头) and consecutive-board chains are a froth / crowding
tell, never a validated buy ranking. Consumed downstream by engine/china_extras
(zt_pool / zt_sector_breadth) for momentum tiers + sector breadth.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import logging
import os
import stat
import tempfile
from pathlib import Path

import pandas as pd

from lib import config
from lib import cn_calendar
from collectors import _drip
from collectors.china_analyst import to_ticker, _num

log = logging.getLogger("china_zt_pool")

OUT = config.data_dir() / "china_zt_pool" / "pool.parquet"
SESSION_REF = config.data_dir() / "china" / "000001.SS.parquet"
WALK_BACK_DAYS = 10        # calendar-day envelope over observed sessions

# One explicit, auditable repair for the bad rows already committed before the observed-session
# gate existed.  Both weekend dates map to the real Friday payload they repeat.  The repair CLI
# validates off-session identity AND an exact semantic fingerprint before deleting a row; dates
# outside this manifest are reported and retained for a separately reviewed migration.
KNOWN_OFF_SESSION_CLONES: dict[str, str] = {
    "2026-07-04": "2026-07-03",
    "2026-07-05": "2026-07-03",
    "2026-07-11": "2026-07-10",
    "2026-07-12": "2026-07-10",
    "2026-07-18": "2026-07-17",
    "2026-07-19": "2026-07-17",
    "2026-07-25": "2026-07-24",
    "2026-07-26": "2026-07-24",
    "2026-08-01": "2026-07-31",
    "2026-08-02": "2026-07-31",
    "2026-08-08": "2026-08-07",
}

_SEMANTIC_COLUMNS = (
    "ticker", "name", "consec_boards", "seal_fund_yi", "failed_seals",
    "turnover_pct", "sector",
)


class SessionReferenceError(RuntimeError):
    """The observed A-share session reference cannot safely authorize a write."""


def _col(cols: list[str], *needles: str) -> str | None:
    """First column whose name CONTAINS any needle (akshare names drift by version)."""
    for c in cols:
        s = str(c)
        if any(n in s for n in needles):
            return c
    return None


def _pool_for(date: str) -> pd.DataFrame | None:
    """The raw limit-up pool for one YYYYMMDD date. None on failure / empty."""
    import akshare as ak
    try:
        df = ak.stock_zt_pool_em(date=date)
    except Exception as e:  # noqa: BLE001 — one broken scrape must never break the build
        log.debug("china zt pool: %s failed (%s)", date, e)
        return None
    return df if df is not None and not df.empty else None


def _parse(date: str, df: pd.DataFrame, asof: str) -> list[dict]:
    """Flatten one day's pool into our schema rows (substring column matching)."""
    cols = list(df.columns)
    code_c = _col(cols, "代码")
    name_c = _col(cols, "名称")
    consec_c = _col(cols, "连板数", "连板")
    seal_c = _col(cols, "封板资金", "封单资金")
    fail_c = _col(cols, "炸板次数")
    turn_c = _col(cols, "换手率")
    sector_c = _col(cols, "所属行业", "行业")
    if not code_c:
        return []
    iso = pd.to_datetime(date).strftime("%Y-%m-%d")
    rows: list[dict] = []
    for _, r in df.iterrows():
        t = to_ticker(r.get(code_c))
        if not t:
            continue
        seal = _num(r.get(seal_c)) if seal_c else None
        rows.append({
            "ticker": t,
            "name": str(r.get(name_c) or "") if name_c else "",
            "consec_boards": int(_num(r.get(consec_c)) or 1) if consec_c else 1,
            # 封板资金 is in yuan; store as 亿 (1e8) for readability
            "seal_fund_yi": round(seal / 1e8, 4) if seal is not None else None,
            "failed_seals": int(_num(r.get(fail_c)) or 0) if fail_c else 0,
            "turnover_pct": _num(r.get(turn_c)) if turn_c else None,
            "sector": str(r.get(sector_c) or "") if sector_c else "",
            "date": iso,
            "asof": asof,
        })
    return rows


def _load_observed_sessions(required_through: _dt.date | None = None) -> pd.DatetimeIndex:
    """Load the exact observed SSE session index, failing closed when absent or stale.

    The Shanghai Composite is an index and therefore cannot be suspended name-by-name.  Its
    tracked price index is the repository's observed mainland-session authority.  The rule-based
    ``cn_calendar`` is deliberately conservative/incomplete and is used only to say how fresh the
    observed reference must be; it is never used to invent a session for this collector.
    """
    if not SESSION_REF.exists():
        raise SessionReferenceError(f"observed session reference missing: {SESSION_REF}")
    try:
        frame = pd.read_parquet(SESSION_REF)
    except Exception as exc:  # noqa: BLE001 — caller turns this into a no-write collector miss
        raise SessionReferenceError(
            f"observed session reference unreadable: {SESSION_REF} ({exc})"
        ) from exc
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise SessionReferenceError(
            f"observed session reference is not date-indexed: {SESSION_REF}"
        )
    idx = frame.index
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    idx = idx.normalize().unique().sort_values()
    if idx.empty:
        raise SessionReferenceError(f"observed session reference is empty: {SESSION_REF}")
    if bool((idx.dayofweek >= 5).any()):
        raise SessionReferenceError(
            f"observed session reference contains weekend rows: {SESSION_REF}"
        )
    if required_through is not None and idx[-1].date() < required_through:
        raise SessionReferenceError(
            "observed session reference stale: "
            f"latest={idx[-1].date().isoformat()} required={required_through.isoformat()}"
        )
    return idx


def _observed_session_strings(
    start: _dt.date,
    end: _dt.date,
    *,
    required_through: _dt.date,
    newest_first: bool,
) -> list[str]:
    """Observed session dates inside ``[start, end]`` as YYYYMMDD strings."""
    idx = _load_observed_sessions(required_through=required_through)
    keep = idx[(idx.date >= start) & (idx.date <= end)]
    if newest_first:
        keep = keep[::-1]
    return [d.strftime("%Y%m%d") for d in keep]


def _history_frame() -> pd.DataFrame:
    """Read the current pool history; an unreadable existing store is a no-write failure."""
    if not OUT.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(OUT)
    except Exception as exc:  # noqa: BLE001
        raise SessionReferenceError(f"zt pool history unreadable: {OUT} ({exc})") from exc


def _semantic_fingerprint(rows: list[dict] | pd.DataFrame) -> str:
    """Stable hash of one session's economic payload, excluding collection/date stamps."""
    frame = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    missing = [c for c in _SEMANTIC_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"zt pool semantic columns missing: {missing}")
    frame = frame.loc[:, list(_SEMANTIC_COLUMNS)].sort_values(
        ["ticker", "name"], kind="mergesort", na_position="first"
    )
    canonical: list[dict] = []
    integer_cols = {"consec_boards", "failed_seals"}
    float_cols = {"seal_fund_yi", "turnover_pct"}
    for record in frame.to_dict(orient="records"):
        out: dict[str, object] = {}
        for col in _SEMANTIC_COLUMNS:
            value = record[col]
            if value is None or pd.isna(value):
                out[col] = None
            elif col in integer_cols:
                out[col] = int(value)
            elif col in float_cols:
                out[col] = float(value)
            else:
                out[col] = str(value)
        canonical.append(out)
    payload = json.dumps(
        canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _exact_prior_clone(
    candidate_date: str,
    rows: list[dict] | pd.DataFrame,
    history: pd.DataFrame,
) -> str | None:
    """Return the immediately prior stored session when ``rows`` exactly replay it."""
    if history.empty or "date" not in history.columns:
        return None
    dates = history["date"].astype(str)
    prior_dates = sorted(d for d in dates.unique() if d < candidate_date)
    if not prior_dates:
        return None
    prior_date = prior_dates[-1]
    prior = history.loc[dates == prior_date]
    same = _semantic_fingerprint(rows) == _semantic_fingerprint(prior)
    return prior_date if same else None


def _atomic_write_parquet(path: Path, frame: pd.DataFrame) -> None:
    """Write one parquet replacement in the target directory, then atomically rename it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    prior_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    handle = tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    )
    tmp = Path(handle.name)
    handle.close()
    try:
        frame.to_parquet(tmp, index=False)
        os.chmod(tmp, prior_mode)
        with tmp.open("rb") as saved:
            os.fsync(saved.fileno())
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def repair_off_session_clones() -> int:
    """Explicitly remove only the 11 manifest-pinned, exact off-session clones.

    This migration is never called by ``refresh`` or ``backfill``.  Every present candidate must
    be absent from the observed session index and byte-equivalent at the semantic-record level to
    its pinned real Friday source.  Any mismatch aborts before the single atomic replacement.
    Unexpected off-session dates are reported and retained for separate adjudication.
    """
    history = _history_frame()
    if history.empty:
        return 0
    if "date" not in history.columns:
        raise SessionReferenceError("zt pool history has no date column")
    parsed = pd.to_datetime(history["date"].astype(str), errors="coerce")
    if parsed.isna().any():
        raise SessionReferenceError("zt pool history contains an unparseable date")
    max_stamped = parsed.max().date()
    required = cn_calendar.last_session_on_or_before(max_stamped)
    observed_idx = _load_observed_sessions(required_through=required)
    observed = {d.strftime("%Y-%m-%d") for d in observed_idx}
    stamped = set(history["date"].astype(str))
    unexpected = sorted(stamped - observed - set(KNOWN_OFF_SESSION_CLONES))
    if unexpected:
        log.warning(
            "china zt pool repair: retaining %d unmanifested off-session date(s): %s",
            len(unexpected), ",".join(unexpected),
        )

    remove: list[str] = []
    for bad_date, source_date in KNOWN_OFF_SESSION_CLONES.items():
        if bad_date not in stamped:
            continue
        if bad_date in observed:
            raise SessionReferenceError(
                f"repair manifest date is now an observed session: {bad_date}"
            )
        if source_date not in observed or source_date not in stamped:
            raise SessionReferenceError(
                f"repair source missing/not observed: {bad_date} -> {source_date}"
            )
        bad = history.loc[history["date"].astype(str) == bad_date]
        source = history.loc[history["date"].astype(str) == source_date]
        if _semantic_fingerprint(bad) != _semantic_fingerprint(source):
            raise SessionReferenceError(
                f"repair fingerprint mismatch: {bad_date} != {source_date}"
            )
        remove.append(bad_date)

    if not remove:
        return 0
    doomed = history["date"].astype(str).isin(remove)
    removed_rows = int(doomed.sum())
    repaired = history.loc[~doomed].copy()
    _atomic_write_parquet(OUT, repaired)
    log.info(
        "china zt pool repair: atomically removed %d rows across %d pinned dates: %s",
        removed_rows, len(remove), ",".join(remove),
    )
    return removed_rows


def _stored_sessions() -> set[str]:
    """The set of session `date`s already on disk (append-only PIT history)."""
    try:
        history = _history_frame()
        if history.empty or "date" not in history.columns:
            return set()
        return set(history["date"].astype(str).unique())
    except Exception:  # noqa: BLE001
        return set()


def refresh(now: _dt.datetime | None = None) -> int:
    """Bake the most recent populated limit-up pool and APPEND it to the point-in-time history
    (keep-last per session `date`, so a same-session re-collect corrects). Best-effort; returns
    names written for the latest session (0 on failure / already-stored session)."""
    if now is None:
        now = _dt.datetime.now(_dt.timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    asof = now.astimezone(_dt.timezone.utc).date().isoformat()
    expected = cn_calendar.expected_last_session(now)
    try:
        dates = _observed_session_strings(
            expected - _dt.timedelta(days=WALK_BACK_DAYS), expected,
            required_through=expected, newest_first=True,
        )
        history = _history_frame()
    except SessionReferenceError as exc:
        log.warning("china zt pool: refusing refresh (%s)", exc)
        return 0
    if not dates:
        log.warning("china zt pool: no observed session in last %d days", WALK_BACK_DAYS)
        return 0

    have = (set(history["date"].astype(str).unique())
            if not history.empty and "date" in history.columns else set())
    for pop_date in dates:
        iso = pd.to_datetime(pop_date).strftime("%Y-%m-%d")
        if iso in have:                                  # newest eligible session already stored
            log.info("china zt pool: session %s already stored", iso)
            return 0
        df = _pool_for(pop_date)
        if df is None:
            continue
        rows = _parse(pop_date, df, asof)
        if not rows:
            continue
        try:
            clone_of = _exact_prior_clone(iso, rows, history)
        except ValueError as exc:
            log.warning("china zt pool: refusing refresh; clone guard unavailable (%s)", exc)
            return 0
        if clone_of is not None:
            log.warning(
                "china zt pool: refusing exact cross-session replay %s == %s",
                iso, clone_of,
            )
            continue
        n = _drip.append_snapshot(OUT, rows, date_col="date")
        log.info("china zt pool: appended %s (%d names, session %s, asof %s)",
                 OUT, n, pop_date, asof)
        return n
    log.warning("china zt pool: no acceptable populated observed session in lookback")
    return 0


def backfill(start: str, end: str) -> int:
    """Range-backfill the limit-up pool PIT history: append every populated trading session in
    [start, end] (YYYY-MM-DD). akshare serves stock_zt_pool_em per-date, so history is fetchable.
    Skips sessions already stored. Returns the number of NEW sessions appended."""
    asof = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
    try:
        start_date = _dt.date.fromisoformat(start)
        end_date = _dt.date.fromisoformat(end)
    except ValueError:
        log.warning("china zt pool backfill: invalid ISO range [%s..%s]", start, end)
        return 0
    if end_date < start_date:
        log.warning("china zt pool backfill: end precedes start [%s..%s]", start, end)
        return 0
    required = cn_calendar.last_session_on_or_before(end_date)
    try:
        dates = _observed_session_strings(
            start_date, end_date, required_through=required, newest_first=False,
        )
        history = _history_frame()
    except SessionReferenceError as exc:
        log.warning("china zt pool backfill: refusing write (%s)", exc)
        return 0
    have = (set(history["date"].astype(str).unique())
            if not history.empty and "date" in history.columns else set())
    added = 0
    for date_str in dates:
        iso = pd.to_datetime(date_str).strftime("%Y-%m-%d")
        if iso in have:
            continue
        df = _pool_for(date_str)
        if df is None:
            continue
        rows = _parse(date_str, df, asof)
        if rows:
            try:
                clone_of = _exact_prior_clone(iso, rows, history)
            except ValueError as exc:
                log.warning(
                    "china zt pool backfill: refusing further writes; clone guard unavailable (%s)",
                    exc,
                )
                return added
            if clone_of is not None:
                log.warning(
                    "china zt pool backfill: refusing exact cross-session replay %s == %s",
                    iso, clone_of,
                )
                continue
            if _drip.append_snapshot(OUT, rows, date_col="date") <= 0:
                continue
            added += 1
            have.add(iso)
            history = pd.concat([history, pd.DataFrame(rows)], ignore_index=True)
            log.info("china zt pool backfill: appended session %s (%d names)", iso, len(rows))
    log.info("china zt pool backfill: %d new sessions [%s..%s]", added, start, end)
    return added


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", nargs=2, metavar=("START", "END"),
                    help="range-backfill PIT history for [START END] (YYYY-MM-DD)")
    ap.add_argument(
        "--repair-off-session-clones", action="store_true",
        help="explicitly remove only the manifest-pinned exact weekend clones",
    )
    a = ap.parse_args()
    if a.backfill and a.repair_off_session_clones:
        ap.error("--backfill and --repair-off-session-clones are mutually exclusive")
    if a.repair_off_session_clones:
        try:
            repair_off_session_clones()
        except (SessionReferenceError, ValueError) as exc:
            log.error("china zt pool repair refused: %s", exc)
            return 2
        return 0
    if a.backfill:
        return 0 if backfill(a.backfill[0], a.backfill[1]) else 0
    return 0 if refresh() else 1


if __name__ == "__main__":
    raise SystemExit(main())
