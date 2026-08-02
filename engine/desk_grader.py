"""UNIFIED FORWARD DESK GRADER — one falsifiable scorecard across three research desks.

The Intelligence Hub, the Alt-Data desk and the Congress desk each SURFACE a ranked set of
names every day. Those rankings are CLAIMS about the future. This harness records the surfaced
set daily and, once a horizon elapses, grades each claim against realized forward returns — so
each page can show whether its desk actually beats the market, and so the engines behind them
can be IMPROVED as rolling data accrues (the owner's explicit ask).

Generalizes engine/hub_track_record.py from ONE desk to THREE, and adds four things the
single-desk grader lacks:

  1. LEAVE TRACKING (owner-explicit). Each snapshot day we diff today's surfaced set against
     the most recent on-desk set; names that dropped get a departure marker. Grading then
     CONTINUES for departed names from their historical snapshot dates, and the scorecard
     SPLITS every result: on-desk vs after-leaving. This answers "did we exit winners too
     early?" and "were the drops correct (did dropped names keep falling)?".

  2. OWNER HORIZONS. 5 / 10 / 20 / 30 / 60 / 90 TRADING days (not the hub's 5/10/21/63),
     absolute AND SPY-relative. Maturation counts real trading rows in the price index, so a
     weekend/holiday never shortens a window.

  3. SCORE-VELOCITY as a SECOND axis (owner's hypothesis). Where a name has >=5 prior snapshots
     we compute score_vel (delta score over the last 5 snapshot dates) and grade it beside the
     LEVEL — the owner suspects velocity-of-score predicts better than level. Both ICs, per
     horizon, side by side.

  4. AUTO-FINDINGS + NOTES loop. Each run derives plain-language findings from the stats
     (stage inversions, negative proven ICs, drops-are-correct) and renders them beside a
     human notes ledger, so the improvement loop starts populated and keeps growing.

PRICE LAYER — yahoo-only, DELIBERATELY. The shared engine.ai_desk._close_series falls back to
data/breadth/_closes_cache.parquet, which is SPLIT-CORRUPTED (see notes.jsonl). This grader
reads ONLY data/yahoo/<T>.parquet `close` (dividend-adjusted). A name absent from yahoo is a
COVERAGE SKIP (counted, reported honestly), never a silently-wrong forward return.

INTEL-HUB is NOT double-snapshotted: an ADAPTER reads the existing 63k-row
data/hub/signal_snapshots.jsonl as the hub's history (instant backfill, engine_version-
segmented where the stamp exists), leaving engine/hub_track_record.py untouched and accruing.

CONTEXT-ONLY · DEGRADE-NEVER-RAISE — no matured data => a valid 'accruing' payload, never an
exception. Honest gate: "proven" needs n>=40 + significant HAC-t + right sign; a proven
NEGATIVE IC renders as "alarm", loudly.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

from engine import validation as V
from lib import config

log = logging.getLogger(__name__)

SCHEMA = "desk_grader.v1"
DESKS = ("intel_hub", "alt_data", "congress")
HORIZONS = (5, 10, 20, 30, 60, 90)          # owner's TRADING-day horizons
BENCH = "SPY"
MIN_PROVEN_N = 40                            # matured obs before a signal can be called "proven"
MIN_DATES_IC = 6                             # per-date ICs needed for a HAC summary
VEL_MIN_SNAPS = 5                            # prior snapshots needed to compute score-velocity
_GRADER_DIR = ("data", "desk_grader")
_HUB_SNAP = ("data", "hub", "signal_snapshots.jsonl")   # the adapter source (untouched)

# Per-desk stage/tier bullish sets — for hit-rate direction. Names on these desks are LONG
# theses (lean +1) unless the desk marks them broken/rolling-over.
_HUB_BULLISH = {"emerging", "early", "discovery"}
_HUB_BEARISH = {"exhausted", "distribution"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dir(root: Path) -> Path:
    return root.joinpath(*_GRADER_DIR)


def _snap_path(root: Path, desk: str) -> Path:
    return _dir(root) / f"{desk}_snapshots.jsonl"


def _notes_path(root: Path) -> Path:
    return _dir(root) / "notes.jsonl"


# --------------------------------------------------------------------------- #
# jsonl io — corruption-resilient (skip bad lines, never raise)
# --------------------------------------------------------------------------- #
def _load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    try:
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001 — one bad line never voids the ledger
                continue
    except Exception as e:  # noqa: BLE001
        log.warning("desk_grader load %s failed: %s", p, e)
    return out


def _append_jsonl(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")


# --------------------------------------------------------------------------- #
# yahoo-only price layer — NEVER the split-corrupted breadth cache
# --------------------------------------------------------------------------- #
_PX_MEMO: dict[str, pd.Series | None] = {}


def _yahoo_series(ticker: str, root: Path) -> pd.Series | None:
    """Adjusted closes from data/yahoo/<T>.parquet ONLY. Memoized. None if absent —
    deliberately NO breadth-cache fallback (that cache is split-corrupted)."""
    key = f"{root}|{ticker}"
    if key in _PX_MEMO:
        return _PX_MEMO[key]
    val: pd.Series | None = None
    try:
        df = pd.read_parquet(Path(root) / "data" / "yahoo" / f"{ticker}.parquet")
        s = df["close"].dropna()
        s.index = pd.to_datetime(s.index)
        val = s.sort_index() if len(s) else None
    except Exception:  # noqa: BLE001
        val = None
    _PX_MEMO[key] = val
    return val


def _reset_px_cache() -> None:
    """Test hook — drop the memoized price series (fixtures write fresh parquets)."""
    _PX_MEMO.clear()


def _fwd_ret_trading(ticker: str, root: Path, start: str, n_td: int) -> tuple[float | None, bool]:
    """Absolute forward return over n_td TRADING days after `start`.

    Returns (ret, covered). `covered` is True when the price series extends far enough that the
    +n_td-th trading bar EXISTS (so the horizon has truly elapsed for this name); a name that
    simply isn't in yahoo, or hasn't traded long enough yet, returns (None, False) — a coverage
    skip, never a wrong number. The start level is the last close ON OR BEFORE `start` (matching
    the snapshot's information set); the end level is exactly n_td trading bars later.
    """
    s = _yahoo_series(ticker, root)
    if s is None or s.empty:
        return None, False
    try:
        ts = pd.Timestamp(start)
        prior = s[s.index <= ts]
        if prior.empty:
            return None, False
        start_pos = len(prior) - 1                      # index of the start bar in `s`
        end_pos = start_pos + n_td
        if end_pos >= len(s):                           # horizon has not elapsed for this name
            return None, False
        p0 = float(s.iloc[start_pos])
        p1 = float(s.iloc[end_pos])
        if p0 == 0:
            return None, False
        return (p1 / p0 - 1.0), True
    except Exception:  # noqa: BLE001
        return None, False


def _fwd_rel(ticker: str, root: Path, start: str, n_td: int) -> tuple[float | None, str]:
    """SPY-relative forward return + a coverage reason.

    reason ∈ {"ok", "no_price", "immature", "no_bench"}:
      no_price  — the name is not in yahoo (or has no bar at/after start)
      immature  — in yahoo but the +n_td trading bar does not exist yet (horizon not elapsed)
      no_bench  — SPY itself lacks the +n_td bar (only near the very right edge)
    Only "ok" yields a number. Leakage-safe: the end bar is strictly AFTER the start bar.
    """
    e_ret, e_cov = _fwd_ret_trading(ticker, root, start, n_td)
    if not e_cov:
        s = _yahoo_series(ticker, root)
        return None, ("no_price" if s is None or s.empty else "immature")
    b_ret, b_cov = _fwd_ret_trading(BENCH, root, start, n_td)
    if not b_cov:
        return None, "no_bench"
    return float(e_ret - b_ret), "ok"


# --------------------------------------------------------------------------- #
# 1. SNAPSHOT LAYER (+ leave tracking)
# --------------------------------------------------------------------------- #
def _norm_row(desk: str, r: dict, today_str: str) -> dict | None:
    """Normalize one surfaced row into the desk's snapshot schema. Returns None for junk
    (missing/placeholder ticker). Desk-specific context is preserved for by-slice breakdowns."""
    t = (r.get("ticker") or r.get("t") or "").upper().strip()
    if not t or t in ("N/A", "NA", "NONE", "?"):
        return None
    row: dict = {"date": today_str, "ticker": t,
                 "rank": r.get("rank"), "score": r.get("score"),
                 "lean": r.get("lean", 1)}
    for k in ("stage", "entry_tier", "gate_tier", "broken", "engine_version",
              "covered", "unconfirmed"):
        if r.get(k) is not None:
            row[k] = r.get(k)
    return row


def _last_on_desk(rows: list[dict]) -> tuple[str | None, set[str]]:
    """The most recent snapshot DATE that carried live (non-departure) rows, and the set of
    tickers surfaced on that date. Departure marker rows (departed=True) are ignored."""
    live = [r for r in rows if not r.get("departed")]
    if not live:
        return None, set()
    last_date = max(r["date"] for r in live)
    return last_date, {r["ticker"] for r in live if r["date"] == last_date}


def snapshot_desk(desk: str, rows: list[dict] | None, today: date | str | None = None,
                  engine_version: str | None = None, root: Path | None = None) -> dict:
    """Append today's surfaced set for `desk`. Idempotent by (date, ticker). Diffs against the
    previous on-desk set and writes DEPARTURE markers for names that dropped. Never raises.

    `rows` = that desk's surfaced names, each a dict with at least {ticker}; optionally
    {rank, score, lean, stage, entry_tier, gate_tier, broken, covered, ...}. Returns a small
    report {n_new, n_departed, n_total}.
    """
    try:
        if desk not in DESKS:
            raise ValueError(f"unknown desk {desk!r}")
        # intel_hub is served by the adapter, never double-snapshotted here.
        if desk == "intel_hub":
            return {"n_new": 0, "n_departed": 0, "adapter": True,
                    "n_total": len(_load_hub_adapter(Path(root) if root else config.ROOT))}
        root = Path(root) if root else config.ROOT
        today_str = today.isoformat() if hasattr(today, "isoformat") else str(today or date.today())
        path = _snap_path(root, desk)
        existing_rows = _load_jsonl(path)
        seen = {f"{r.get('date')}|{r.get('ticker')}"
                for r in existing_rows if not r.get("departed")}
        prev_date, prev_set = _last_on_desk(existing_rows)

        new_rows, today_set = [], set()
        for r in (rows or []):
            nr = _norm_row(desk, r, today_str)
            if nr is None:
                continue
            today_set.add(nr["ticker"])
            key = f"{today_str}|{nr['ticker']}"
            if key in seen:
                continue
            if engine_version and "engine_version" not in nr:
                nr["engine_version"] = engine_version
            new_rows.append(nr)
            seen.add(key)

        # DEPARTURES — names on the previous on-desk set that are absent today. Only when today
        # actually surfaced something (an empty-desk day must not mass-evict the whole board),
        # and only when today is a NEW date (re-running the same day is a no-op).
        departures = []
        if today_set and prev_set and prev_date != today_str:
            # last-known rank/score per departed ticker (from its most recent live snapshot)
            last_seen: dict[str, dict] = {}
            for r in existing_rows:
                if not r.get("departed") and r.get("ticker") in prev_set:
                    last_seen[r["ticker"]] = r          # rows are append-order → last wins
            for tk in sorted(prev_set - today_set):
                dep_key = f"{today_str}|{tk}|dep"
                if dep_key in seen:
                    continue
                ls = last_seen.get(tk, {})
                departures.append({"date": today_str, "ticker": tk, "departed": True,
                                   "left_desk": today_str, "last_rank": ls.get("rank"),
                                   "last_score": ls.get("score")})
                seen.add(dep_key)

        to_write = new_rows + departures
        if to_write:
            _append_jsonl(path, to_write)
        return {"n_new": len(new_rows), "n_departed": len(departures),
                "n_total": len(existing_rows) + len(to_write)}
    except Exception as e:  # noqa: BLE001
        log.warning("desk_grader snapshot(%s) failed: %s", desk, e)
        return {"n_new": 0, "n_departed": 0, "n_total": 0, "error": str(e)}


# --------------------------------------------------------------------------- #
# intel-hub ADAPTER — read the existing hub ledger AS desk snapshots (no double write)
# --------------------------------------------------------------------------- #
def _load_hub_adapter(root: Path) -> list[dict]:
    """Read data/hub/signal_snapshots.jsonl and reshape each row into the desk-grader snapshot
    schema. The hub logs the WHOLE ranking each day (not just the top), so the cross-sectional
    IC sees the full cross-section. score = opportunity (opp); stage/lean/engine_version carried.
    Departures are derived on the fly (the hub ledger has no markers) so on-desk/off-desk split
    still works. Never raises."""
    raw = _load_jsonl(root.joinpath(*_HUB_SNAP))
    out: list[dict] = []
    for r in raw:
        t = (r.get("t") or "").upper().strip()
        if not t or t in ("N/A", "NA", "NONE", "?"):
            continue
        row = {"date": r.get("date"), "ticker": t, "score": r.get("opp"),
               "rank": None, "lean": r.get("lean", 1), "stage": r.get("stage"),
               "edge": r.get("edge")}
        if r.get("engine_version"):
            row["engine_version"] = r["engine_version"]
        if row["date"]:
            out.append(row)
    return _mark_departures(out)


def _mark_departures(rows: list[dict]) -> list[dict]:
    """Derive departure markers for a ledger that has none (the hub adapter): a name present on
    date D-1's board but absent on date D 'left the desk' on D. Adds departed=True rows so the
    on-desk / after-leaving split is available for the adapter too. Pure; returns rows+markers."""
    if not rows:
        return rows
    by_date: dict[str, set] = {}
    last_row: dict[str, dict] = {}
    for r in rows:
        by_date.setdefault(r["date"], set()).add(r["ticker"])
    dates = sorted(by_date)
    markers = []
    for i in range(1, len(dates)):
        prev, cur = dates[i - 1], dates[i]
        gone = by_date[prev] - by_date[cur]
        for tk in gone:
            # find last live row for tk on/before prev
            ls = None
            for r in rows:
                if r["ticker"] == tk and r["date"] <= prev and not r.get("departed"):
                    ls = r
            markers.append({"date": cur, "ticker": tk, "departed": True,
                            "left_desk": cur, "last_rank": (ls or {}).get("rank"),
                            "last_score": (ls or {}).get("score")})
    return rows + markers


def _load_desk(desk: str, root: Path) -> list[dict]:
    if desk == "intel_hub":
        return _load_hub_adapter(root)
    return _load_jsonl(_snap_path(root, desk))


# --------------------------------------------------------------------------- #
# 2/3. GRADING LAYER — maturation, on-desk vs departed split, level + velocity IC
# --------------------------------------------------------------------------- #
def _departed_since(rows: list[dict]) -> dict[str, str]:
    """ticker -> the date it left the desk (earliest departure marker). Used to tag each matured
    live snapshot as on-desk (snapshot date < departure) or after-leaving (>= departure)."""
    out: dict[str, str] = {}
    for r in rows:
        if r.get("departed"):
            tk, d = r["ticker"], r.get("left_desk") or r["date"]
            if tk not in out or d < out[tk]:
                out[tk] = d
    return out


def _velocity(rows: list[dict]) -> dict[tuple[str, str], float]:
    """(ticker, date) -> score velocity = (score_now - score_5_snaps_ago) for names with >=5
    prior snapshots. Uses only PAST snapshots (<= this date) so it is leakage-free. The owner's
    second axis: does the CHANGE in a desk's own score predict better than its LEVEL?"""
    live = [r for r in rows if not r.get("departed") and r.get("score") is not None]
    by_t: dict[str, list] = {}
    for r in sorted(live, key=lambda x: x["date"]):
        by_t.setdefault(r["ticker"], []).append(r)
    out: dict[tuple[str, str], float] = {}
    for tk, seq in by_t.items():
        for i in range(len(seq)):
            if i >= VEL_MIN_SNAPS:                      # need >=5 PRIOR snapshots
                cur = float(seq[i]["score"])
                past = float(seq[i - VEL_MIN_SNAPS]["score"])
                out[(tk, seq[i]["date"])] = cur - past
    return out


def _matured(rows: list[dict], root: Path, n_td: int, today: date,
             vel: dict) -> tuple[list[dict], dict]:
    """Mature every LIVE snapshot old enough that its n_td-trading-day forward window has
    elapsed AND is price-covered. Attaches fwd (SPY-relative), on_desk flag, and score_vel.
    Returns (matured_rows, coverage_counters). Departure markers are not graded directly (the
    live snapshots carry the returns); they only tag on-desk vs after-leaving."""
    departed = _departed_since(rows)
    cov = {"eligible": 0, "ok": 0, "no_price": 0, "immature": 0, "no_bench": 0}
    out = []
    today_ts = pd.Timestamp(today)
    for r in rows:
        if r.get("departed") or not r.get("date"):
            continue
        try:
            # cheap calendar pre-filter: n_td trading days is at least n_td calendar days
            if (today_ts - pd.Timestamp(r["date"])).days < n_td:
                continue
        except Exception:  # noqa: BLE001
            continue
        cov["eligible"] += 1
        fwd, reason = _fwd_rel(r["ticker"], root, r["date"], n_td)
        cov[reason] = cov.get(reason, 0) + 1
        if fwd is None:
            continue
        dep_date = departed.get(r["ticker"])
        on_desk = not (dep_date is not None and r["date"] >= dep_date)
        row = {**r, "fwd": fwd, "on_desk": on_desk}
        v = vel.get((r["ticker"], r["date"]))
        if v is not None:
            row["score_vel"] = v
        out.append(row)
    cov["coverage_pct"] = round(100.0 * cov["ok"] / cov["eligible"], 1) if cov["eligible"] else None
    return out, cov


def _signed(v, lean) -> float | None:
    if v is None or not lean:
        return None
    return float(v) * (1 if lean > 0 else -1)


def _daily_ic(rows: list[dict], field: str, n_td: int) -> dict:
    """Per-DATE cross-sectional rank-ICs of `field` (signed by lean) vs fwd, summarized with a
    horizon-aware Newey-West HAC t (periods_per_year=2*n_td => NW lag = n_td). The lag MUST equal
    the horizon: daily snapshots with an n_td-day forward window overlap ~n_td days, so the IC
    series autocorrelates at lag n_td; a fixed small lag under-corrects and lets noise clear the
    bar at the long horizons. (Preserves the fix already made in hub_track_record.)"""
    by_date: dict[str, list] = {}
    for r in rows:
        by_date.setdefault(r["date"], []).append(r)
    ics = []
    for _, day in sorted(by_date.items()):
        xs, fwd = [], []
        for r in day:
            sx = _signed(r.get(field), r.get("lean"))
            if sx is None:
                continue
            xs.append(sx)
            fwd.append(r["fwd"])
        if len(xs) < 10 or len(set(xs)) < 2 or len(set(fwd)) < 2:
            continue
        ic = V.rank_ic(xs, fwd)
        if ic == ic:                                    # not NaN
            ics.append(ic)
    return V.ic_summary(ics, periods_per_year=2 * n_td) if len(ics) >= MIN_DATES_IC else {"n_days": len(ics)}


def _pooled_ic(rows: list[dict], field: str) -> float | None:
    xs, ys = [], []
    for r in rows:
        sx = _signed(r.get(field), r.get("lean"))
        if sx is None:
            continue
        xs.append(sx)
        ys.append(r["fwd"])
    if len(xs) < 10:
        return None
    s = pd.concat([pd.Series(xs).rename("s"), pd.Series(ys).rename("f")], axis=1).dropna()
    if len(s) < 10 or s["s"].nunique() < 2 or s["f"].nunique() < 2:
        return None
    return round(float(s["s"].rank().corr(s["f"].rank())), 4)


def _summary_stats(rows: list[dict]) -> dict:
    """mean SPY-relative fwd return + hit-rate (realized in the lean's expected direction)."""
    if not rows:
        return {"n": 0, "mean_fwd_rel": None, "hit_rate": None}
    fwds = [r["fwd"] for r in rows]
    n = len(fwds)
    mean = sum(fwds) / n
    hits = sum(1 for r in rows if (r["fwd"] > 0) == ((r.get("lean") or 1) > 0))
    return {"n": n, "mean_fwd_rel": round(mean, 4), "hit_rate": round(hits / n, 3)}


def _by_key(rows: list[dict], key: str, bull: set | None = None,
            bear: set | None = None) -> dict:
    """mean fwd + hit-rate grouped by a desk-specific key (stage / entry_tier / gate_tier)."""
    by: dict[str, list] = {}
    for r in rows:
        v = r.get(key)
        if v is None or v == "":
            continue
        by.setdefault(str(v), []).append(r)
    out = {}
    for k, grp in by.items():
        fwds = [r["fwd"] for r in grp]
        n = len(fwds)
        mean = sum(fwds) / n if n else 0.0
        if bull and k in bull:
            hit = sum(1 for f in fwds if f > 0) / n
        elif bear and k in bear:
            hit = sum(1 for f in fwds if f < 0) / n
        else:
            hit = sum(1 for r in grp if (r["fwd"] > 0) == ((r.get("lean") or 1) > 0)) / n
        out[k] = {"n": n, "mean_fwd_rel": round(mean, 4), "hit_rate": round(hit, 3)}
    return out


def _engine_versions(rows: list[dict]) -> dict:
    """engine_version -> summary + level IC, so a pre/post overhaul A/B is a first-class read.
    Only versions with >=1 matured row appear; empty when the ledger carries no stamp yet."""
    by: dict[str, list] = {}
    for r in rows:
        ev = r.get("engine_version")
        if ev:
            by.setdefault(ev, []).append(r)
    return {ev: {**_summary_stats(grp),
                 "ic_pooled": _pooled_ic(grp, "score")} for ev, grp in by.items()}


def _proven_status(ic_daily: dict, n_matured: int, level_or_vel_ic) -> str:
    """proven / measuring / alarm. proven needs n>=40 + |HAC-t|>=2 + POSITIVE IC; a SIGNIFICANT
    NEGATIVE IC (the desk is anti-predictive) is 'alarm', shown loudly; else 'measuring'."""
    t = (ic_daily or {}).get("t_hac")
    mic = (ic_daily or {}).get("mean_ic")
    if n_matured >= MIN_PROVEN_N and t is not None and abs(t) >= 2.0 and mic is not None:
        if mic > 0:
            return "proven"
        return "alarm"                                  # significant + NEGATIVE = anti-predictive
    return "measuring"


def compute(desk: str, today: date | str | None = None, root: Path | None = None,
            horizons=HORIZONS) -> dict:
    """Grade every matured snapshot for `desk` across all owner horizons. Per horizon: level IC
    (daily HAC + pooled) AND velocity IC side by side, mean/hit split on-desk vs departed,
    by-stage / by-tier breakdowns, engine_version A/B, coverage %. Auto-findings + notes attached.
    Never raises; degrades to an 'accruing' payload."""
    try:
        if desk not in DESKS:
            raise ValueError(f"unknown desk {desk!r}")
        root = Path(root) if root else config.ROOT
        today_dt = pd.Timestamp(today).date() if today else date.today()
        rows = _load_desk(desk, root)
        vel = _velocity(rows)
        n_live = sum(1 for r in rows if not r.get("departed"))
        n_dep = sum(1 for r in rows if r.get("departed"))

        bull = _HUB_BULLISH if desk == "intel_hub" else None
        bear = _HUB_BEARISH if desk == "intel_hub" else None
        by_key = "stage" if desk == "intel_hub" else ("entry_tier" if desk == "alt_data" else "gate_tier")

        out_h: dict[str, dict] = {}
        peak_ic, lead_time = None, None
        for h in horizons:
            mat, cov = _matured(rows, root, h, today_dt, vel)
            on_desk = [r for r in mat if r.get("on_desk")]
            departed = [r for r in mat if not r.get("on_desk")]
            has_vel = [r for r in mat if "score_vel" in r]

            level_daily = _daily_ic(mat, "score", h)
            vel_daily = _daily_ic(has_vel, "score_vel", h) if has_vel else {"n_days": 0}
            level_ic = level_daily.get("mean_ic")
            vel_ic = vel_daily.get("mean_ic")
            status = _proven_status(level_daily, len(mat), level_ic)

            out_h[str(h)] = {
                "n_matured": len(mat),
                "coverage": cov,
                # LEVEL axis
                "level_ic": level_ic,
                "level_ic_pooled": _pooled_ic(mat, "score"),
                "level_ic_daily": level_daily,
                # VELOCITY axis (owner's hypothesis)
                "velocity_ic": vel_ic,
                "velocity_ic_pooled": _pooled_ic(has_vel, "score_vel") if has_vel else None,
                "velocity_ic_daily": vel_daily,
                "velocity_n": len(has_vel),
                # split: on-desk vs after leaving
                "overall": _summary_stats(mat),
                "on_desk": _summary_stats(on_desk),
                "departed": _summary_stats(departed),
                # desk-specific breakdown
                "by_slice_key": by_key,
                "by_slice": _by_key(mat, by_key, bull, bear),
                "by_stage": _by_key(mat, "stage", bull, bear) if desk == "intel_hub" else {},
                # engine_version A/B
                "engine_versions": _engine_versions(mat),
                "status": status,
            }
            t = level_daily.get("t_hac")
            if status == "proven" and level_ic and (peak_ic is None or level_ic > peak_ic):
                peak_ic, lead_time = level_ic, h

        any_matured = any(e["n_matured"] > 0 for e in out_h.values())
        any_alarm = any(e["status"] == "alarm" for e in out_h.values())
        any_proven = any(e["status"] == "proven" for e in out_h.values())
        findings = _auto_findings(desk, out_h)
        notes = _load_notes(root, desk)

        if not any_matured:
            note = ("Accruing — the desk records its surfaced set daily and grades each name at "
                    "5/10/20/30/60/90 trading days. First 5d grades ~ once the horizon elapses.")
        elif any_alarm:
            note = "ALARM — a matured horizon shows a SIGNIFICANT NEGATIVE IC: this desk is anti-predictive there."
        elif any_proven:
            note = f"Measured edge — level IC peaks at the {lead_time}d horizon. Context-only."
        else:
            note = "Measuring — matured observations accruing; no horizon has cleared the significance bar yet."

        return {
            "schema": SCHEMA, "desk": desk, "as_of": today_dt.isoformat(),
            "generated_at": _now_iso(), "is_context_only": True,
            "n_snapshots_live": n_live, "n_departures": n_dep,
            "horizons": out_h, "lead_time_d": lead_time, "peak_level_ic": peak_ic,
            "any_matured": any_matured, "any_alarm": any_alarm, "any_proven": any_proven,
            "auto_findings": findings, "notes": notes, "note": note,
            "disclaimer": (
                "An accountable scorecard of this desk's own surfaced names — its ranking score "
                "(level AND velocity) graded against realized SPY-relative forward returns at "
                "5/10/20/30/60/90 trading days, split on-desk vs after-leaving. A signal is "
                "'proven' only past n>=40 with a significant Newey-West t of the right sign; a "
                "significant negative IC is an 'alarm'. Context-only — nothing here sizes a position."),
        }
    except Exception as e:  # noqa: BLE001
        log.warning("desk_grader compute(%s) failed: %s", desk, e)
        return {"schema": SCHEMA, "desk": desk, "as_of": str(today or date.today()),
                "generated_at": _now_iso(), "is_context_only": True, "n_snapshots_live": 0,
                "n_departures": 0, "horizons": {}, "lead_time_d": None, "peak_level_ic": None,
                "any_matured": False, "any_alarm": False, "any_proven": False,
                "auto_findings": [], "notes": [], "note": f"compute error ({e}) — accruing, degrade-safe."}


# --------------------------------------------------------------------------- #
# 5. NOTES + AUTO-FINDINGS
# --------------------------------------------------------------------------- #
def _load_notes(root: Path, desk: str | None = None) -> list[dict]:
    notes = _load_jsonl(_notes_path(root))
    if desk:
        notes = [n for n in notes if n.get("desk") in (desk, "all", None)]
    return sorted(notes, key=lambda n: n.get("date", ""), reverse=True)


def add_note(desk: str, note: str, author: str = "human",
             today: date | str | None = None, root: Path | None = None) -> bool:
    """Append a lesson to data/desk_grader/notes.jsonl (the improvement loop). Never raises."""
    try:
        root = Path(root) if root else config.ROOT
        today_str = today.isoformat() if hasattr(today, "isoformat") else str(today or date.today())
        _append_jsonl(_notes_path(root), [{"date": today_str, "desk": desk,
                                           "note": note, "author": author}])
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("desk_grader add_note failed: %s", e)
        return False


def _auto_findings(desk: str, out_h: dict) -> list[dict]:
    """Derive plain-language findings from the stats each run — the automated half of the
    improvement loop. Each finding: {horizon, severity, text}. Empty until data matures."""
    out = []
    for h, e in out_h.items():
        if not e.get("n_matured"):
            continue
        # negative proven IC at any horizon = loud alarm
        if e["status"] == "alarm":
            out.append({"horizon": h, "severity": "alarm",
                        "text": f"{h}d level IC is significantly NEGATIVE ({e['level_ic']:+.3f}, "
                                f"n={e['n_matured']}) — the desk's ranking is anti-predictive here; "
                                f"consider inverting or gating the score."})
        # velocity beats level (owner's hypothesis) — flag when both exist and velocity is larger + right sign
        lic, vic = e.get("level_ic"), e.get("velocity_ic")
        if lic is not None and vic is not None and vic > 0 and vic > lic + 0.02:
            out.append({"horizon": h, "severity": "insight",
                        "text": f"{h}d: score VELOCITY IC ({vic:+.3f}) exceeds LEVEL IC ({lic:+.3f}) "
                                f"— the change in the desk's score ranks winners better than its level."})
        # departed names vs on-desk — were the drops correct?
        od, dep = e.get("on_desk", {}), e.get("departed", {})
        if od.get("n", 0) >= 10 and dep.get("n", 0) >= 10:
            odm, depm = od.get("mean_fwd_rel"), dep.get("mean_fwd_rel")
            if odm is not None and depm is not None:
                if depm < odm - 0.005:
                    out.append({"horizon": h, "severity": "insight",
                                "text": f"{h}d: departed names ({depm*100:+.1f}% avg) underperform on-desk "
                                        f"names ({odm*100:+.1f}%) — DROPS ARE CORRECT; the desk sheds "
                                        f"names before they lag."})
                elif depm > odm + 0.005:
                    out.append({"horizon": h, "severity": "warn",
                                "text": f"{h}d: departed names ({depm*100:+.1f}% avg) OUTPERFORM on-desk "
                                        f"names ({odm*100:+.1f}%) — the desk may be exiting winners too early."})
        # stage inversion (intel_hub) — do 'exhausted' names beat 'emerging'?
        if desk == "intel_hub":
            bs = e.get("by_stage", {})
            em, ex = bs.get("emerging"), bs.get("exhausted")
            if em and ex and em.get("n", 0) >= 8 and ex.get("n", 0) >= 8:
                if ex["mean_fwd_rel"] > em["mean_fwd_rel"] + 0.005:
                    out.append({"horizon": h, "severity": "warn",
                                "text": f"{h}d: 'exhausted' ({ex['mean_fwd_rel']*100:+.1f}%) outperforms "
                                        f"'emerging' ({em['mean_fwd_rel']*100:+.1f}%) — possible residual "
                                        f"inversion in the lifecycle staging."})
    return out


# --------------------------------------------------------------------------- #
# seed notes — start the improvement loop populated with what we already learned
# --------------------------------------------------------------------------- #
_SEED_NOTES = [
    {"date": "2026-07-04", "desk": "intel_hub", "author": "wave2",
     "note": "2026-07-04 inversion finding: the OLD hub engine was anti-predictive — pooled "
             "opportunity IC ~-0.09 @5d, and 'exhausted' names (+1.84% avg fwd) BEAT 'emerging' "
             "(-0.77%). The hub-v3-trajectory overhaul is the fix under test; this grader's "
             "engine_version A/B is the experiment that proves whether it worked."},
    {"date": "2026-07-04", "desk": "all", "author": "wave2",
     "note": "PRICE LESSON: grade off data/yahoo/<T>.parquet adjusted closes ONLY. The S&P-1500 "
             "breadth close cache (data/breadth/_closes_cache.parquet) is SPLIT-CORRUPTED — using "
             "it silently poisons every RS / forward-return number. A name missing from yahoo is a "
             "coverage skip here, never a wrong return."},
    {"date": "2026-07-04", "desk": "congress", "author": "wave2",
     "note": "CONGRESS LESSON: disclosure lags the trade by up to 45 days, so grade forward "
             "returns from the REPORT date (when the desk surfaces the name), not the trade date — "
             "the desk's edge, if any, is decay-on-report-date, not the politician's original entry."},
    {"date": "2026-07-04", "desk": "intel_hub", "author": "wave2",
     "note": "NOTE on the engine_version A/B: the historical hub ledger carries NO engine_version "
             "stamp (all ~63k rows pre-date the stamp), so the pre/post-overhaul split only begins "
             "accruing from 2026-07-04 forward. Until enough hub-v3-trajectory rows mature, the A/B "
             "reads one-sided; that is expected, not a bug."},
]


def seed_notes(root: Path | None = None) -> int:
    """Write the seed lessons if notes.jsonl is empty. Idempotent. Returns rows written."""
    try:
        root = Path(root) if root else config.ROOT
        p = _notes_path(root)
        if p.exists() and _load_jsonl(p):
            return 0
        _append_jsonl(p, _SEED_NOTES)
        return len(_SEED_NOTES)
    except Exception as e:  # noqa: BLE001
        log.warning("desk_grader seed_notes failed: %s", e)
        return 0
