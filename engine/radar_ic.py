"""Radar IC (Information Coefficient) validation harness — Phase 0 accountability, v2.

Proves (or disproves) whether the Divergence Radar's `edge_score` (0-100) has
predictive power over forward horizons. Mirrors the falsifiable-ledger pattern
of engine/demand_ledger.py + engine/ai_desk_scorer.py.

v2 (2026-08-05 forensic audit) — the v1 scoreboard indicted claims the radar
never made. Five construction defects, each now fixed while keeping every v1
field byte-compatible for existing consumers (signal_governor reads
by_horizon[h].ic_daily_hac + n_matured; experiments_registry reads by_horizon):

  1. SIGNED grading. `edge_score` is a salience magnitude (how far activity and
     price disagree) — direction lives in `state`. v1's headline pooled IC
     correlated the UNSIGNED score with signed returns, so a high-edge bearish
     flag that correctly preceded a fall scored as a MISS. v1 ic_all stays (as
     the legacy field) but v2 adds ic_all_signed + a claims-only HAC series.
  2. CLAIMS vs DIAGONAL. engine/radar.py's own doctrine: the radar "is SILENT
     on the diagonal — CONFIRMED means corroborated and already priced, no
     edge". v1 graded CONFIRMED_UP as a bullish call (it was 28% of all rows
     and the single worst cohort in the July-2026 AI-infra unwind). v2 grades
     divergence states as the radar's claims and reports CONFIRMED_* separately
     as context. BROKEN_LAGGARD (an explicit non-claim) leaves directional
     denominators entirely.
  3. BASE RATE. Over Jun-Aug 2026 only ~39% of tracked subjects beat SPY at
     21d — every naive hit-rate read against an implied 0.5 was mostly era.
     v2 prints the unconditional base rate per horizon and each cohort's
     excess vs the matching directional base.
  4. EPISODES. Daily snapshots of a persisting flag are the SAME call repeated
     (~6 rows per contiguous (subject,state) run; weekend runs re-stamped
     Friday's close under a new date). v2 groups contiguous runs into episodes
     and reports entry-day episode stats next to the row-level (row-weighted)
     legacy numbers. New snapshots are keyed to the SESSION (radar.json as_of),
     not the wall clock, so weekend duplicates stop accruing (#4568 family).
  5. HORIZON UNITS. radar.py seeds hypotheses at 63 TRADING days (~91 calendar)
     but v1 graded at 21/63 CALENDAR days and starved stamped rows out of the
     21d panel. v2 grades every row at every horizon descriptively (the stamp
     is metadata; the seeded PROMISE is graded by engine/radar_scorer.py at
     check_by) and adds the 91-calendar-day block that matches the promise.

A machine-readable `verdict` block applies pre-registered evidence gates
(V_MIN_EPISODES matured claim episodes + a valid, non-degenerate claims HAC
|t| >= V_T_SIG) so the front-end copy can only claim "worked"/"hasn't" when the
evidence clears the bar — otherwise it must say "measuring" or "no evidence
either way". Constants are committed here; changing them is a new pre-reg.

Price helper: reuses engine.ai_desk._close_series / ai_desk_scorer._close_at
(data/yahoo/<T>.parquet). SPY = benchmark. All public functions never raise.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from engine.ai_desk import _close_series               # price loader — do NOT reinvent
from engine import validation as V                      # HAC t-stat machinery — do NOT reinvent
from lib import config

log = logging.getLogger(__name__)

SCHEMA = "radar_ic.v2"
_SNAPSHOTS_FILE = ("data", "radar", "edge_snapshots.jsonl")
# Default IC grading horizon.  The 21d horizon remains the legacy default so that
# existing consumers of radar_ic.json top-level fields (ic_all, n_matured, etc.)
# are unaffected.
_HORIZON_D = 21        # default ~1 trading month (kept as legacy default)
_ROLLING_N = 90        # rolling window (obs count, not calendar days)
_BENCH = "SPY"
# 91 calendar days ≈ radar.SEED_HORIZON_D (63 trading days) — the horizon the
# radar actually promises when it seeds a watch-hypothesis.
_SEED_CAL_D = 91
_HORIZONS_DEFAULT = [21, 63, _SEED_CAL_D]

# Edge-score buckets: (label, lo_inclusive, hi_exclusive)
_BUCKETS = [("0-40", 0, 40), ("40-70", 40, 70), ("70-100", 70, 101)]

# The radar's CLAIMS are its off-diagonal states (engine/radar.py: "the radar is
# SILENT on the diagonal — when sources agree there is no edge").
_CLAIM_STATES = {"POSITIVE_DIVERGENCE", "NEGATIVE_DIVERGENCE"}
# The diagonal: corroborated / already priced — context the radar explicitly
# does NOT claim an edge on. Graded separately, never folded into the verdict.
_DIAGONAL_STATES = {"CONFIRMED_UP", "CONFIRMED_DOWN"}

# States whose implied direction is POSITIVE (we expect positive fwd rel-return)
_BULLISH_STATES = {"POSITIVE_DIVERGENCE", "CONFIRMED_UP"}
# States whose implied direction is NEGATIVE
_BEARISH_STATES = {"NEGATIVE_DIVERGENCE", "CONFIRMED_DOWN"}

_STATE_DIR = {"POSITIVE_DIVERGENCE": 1, "CONFIRMED_UP": 1,
              "NEGATIVE_DIVERGENCE": -1, "CONFIRMED_DOWN": -1}

# ── PRE-REGISTERED VERDICT GATES (committed constants = the pre-registration) ──
# The page may only claim the radar "led" or "lagged" when BOTH clear:
V_MIN_EPISODES = 60    # matured CLAIM episodes at the verdict horizon
V_T_SIG = 2.0          # |HAC t| on the claims-only daily IC series (non-degenerate)

# Episode segmentation: a subject re-flagging after this many calendar days of
# absence starts a NEW episode (same-state runs interrupted by a quiet spell are
# separate calls, not one long one).
_EPISODE_GAP_D = 7

# Era ledger — construction breaks that make cross-era pooling suspect.
# Era 1: wall-clock-dated snapshots, pre-dock edge scores (2026-06-20..2026-08-04).
# Era 2: session-keyed snapshots + diagonal/extension edge docking (radar_plus v2).
_CURRENT_ERA = 2
_ERA_BREAKS = [
    {"era": 2, "date": "2026-08-05",
     "note": ("scoring construction v2 — session-keyed snapshots, diagonal edge "
              "docking (radar_plus), source-stamped ticker rows. Rows before this "
              "date are era 1; pooled cross-era stats carry both constructions.")},
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Per-process close-series memo. v1 re-read the parquet on EVERY price lookup
# (4 lookups/row/horizon × ~9k rows × horizons ≈ 50k+ parquet reads per nightly
# run); v2 loads each ticker once per compute (≈660 reads) and slices in memory.
# Cleared at the top of compute_ic() so a long-lived process never serves a
# stale series to a later invocation.
_SERIES_MEMO: dict[tuple[str, str], object] = {}


def _series(ticker: str, root: Path):
    key = (str(root), ticker)
    if key not in _SERIES_MEMO:
        try:
            _SERIES_MEMO[key] = _close_series(ticker, root)
        except Exception:  # noqa: BLE001
            _SERIES_MEMO[key] = None
    return _SERIES_MEMO[key]


def _asof_close(ticker: str, root: Path, on_date) -> float | None:
    """Last close ON or BEFORE on_date (mirrors desk_scorer.close_at semantics)."""
    s = _series(ticker, root)
    if s is None or getattr(s, "empty", True):
        return None
    try:
        s = s[s.index <= pd.Timestamp(on_date)]
        return round(float(s.iloc[-1]), 4) if len(s) else None
    except Exception:  # noqa: BLE001
        return None


def _covers(ticker: str, root: Path, check_by) -> bool:
    """True once the store holds a trading day ON OR AFTER check_by (window
    elapsed) — desk_scorer.covers semantics on the memoized series."""
    s = _series(ticker, root)
    try:
        return s is not None and not s.empty and s.index.max() >= pd.Timestamp(check_by)
    except Exception:  # noqa: BLE001
        return False


def _fwd_rel_return(ticker: str, root: Path, start_date: str, horizon_d: int
                    ) -> float | None:
    """Total return of `ticker` minus SPY over `horizon_d` calendar days from
    `start_date`. Uses close ON or BEFORE start_date as entry, and close ON or
    BEFORE (start_date + horizon_d) as exit. Returns None if price unavailable."""
    try:
        end_ts = (pd.Timestamp(start_date) + pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
        e0 = _asof_close(ticker, root, start_date)
        e1 = _asof_close(ticker, root, end_ts)
        b0 = _asof_close(_BENCH, root, start_date)
        b1 = _asof_close(_BENCH, root, end_ts)
        if None in (e0, e1, b0, b1) or e0 == 0 or b0 == 0:
            return None
        return round((e1 / e0 - 1.0) - (b1 / b0 - 1.0), 6)
    except Exception as e:  # noqa: BLE001
        log.debug("_fwd_rel_return(%s, %s): %s", ticker, start_date, e)
        return None


def _is_matured(row: dict, root: Path, horizon_d: int, today: date) -> bool:
    """True when the snapshot is old enough AND price data covers the horizon."""
    try:
        snap_date = pd.Timestamp(row["date"])
        # must be at least horizon_d calendar days old
        if (pd.Timestamp(today) - snap_date).days < horizon_d:
            return False
        end_ts = (snap_date + pd.Timedelta(days=horizon_d)).strftime("%Y-%m-%d")
        ticker = row["ticker"]
        return bool(
            _covers(ticker, root, end_ts)
            and _covers(_BENCH, root, end_ts)
        )
    except Exception:  # noqa: BLE001
        return False


def _daily_hac_signed_ic(enriched: list[dict], horizon_d: int,
                         states: set[str] | None = None) -> dict:
    """RIGOROUS, overlap-robust signal quality: per-DATE cross-sectional Spearman IC of
    (edge_score signed by the state's implied direction) vs fwd_rel_return, summarized with a
    Newey-West HAC t-stat at lag=horizon. The pooled ``ic_all`` above OVERSTATES significance
    because daily snapshots with an h-day forward window overlap for ~h days (the IC series
    autocorrelates at lag h). This is the number the signal governor gates de-escalation on —
    never the pooled Spearman. Needs ≥10 names/date and ≥6 dates; else returns {n_days:…}.

    ``states``: optional restriction (e.g. _CLAIM_STATES for the claims-only series the
    verdict gates on). Default None = every directional state (the governor's series —
    unchanged from v1 so its gate keeps reading the same number)."""
    by_date: dict[str, list] = {}
    for r in enriched:
        if states is not None and r.get("state") not in states:
            continue
        d = _STATE_DIR.get(r.get("state"), 0)
        if not d:                                   # no directional claim ⇒ excluded
            continue
        by_date.setdefault(r["date"], []).append((r["edge_score"] * d, r["fwd_rel_return"]))
    ics: list[float] = []
    for _, pairs in sorted(by_date.items()):
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        if len(xs) < 10 or len(set(xs)) < 2 or len(set(ys)) < 2:   # need spread for a rank corr
            continue
        ic = V.rank_ic(xs, ys)
        if ic == ic:                                # not NaN
            ics.append(ic)
    # periods_per_year=2*h ⇒ ic_summary sets the NW lag to h (its lag = periods_per_year//2)
    return V.ic_summary(ics, periods_per_year=2 * horizon_d) if len(ics) >= 6 else {"n_days": len(ics)}


def _spearman_ic(xs: list[float], ys: list[float]) -> float | None:
    """Spearman rank correlation between xs and ys. Returns None if n < 3."""
    n = len(xs)
    if n < 3:
        return None
    try:
        # rank ties broken by average (standard Spearman)
        def ranks(v: list[float]) -> list[float]:
            indexed = sorted(enumerate(v), key=lambda t: t[1])
            r: list[float] = [0.0] * len(v)
            i = 0
            while i < len(indexed):
                j = i
                while j < len(indexed) - 1 and indexed[j + 1][1] == indexed[j][1]:
                    j += 1
                avg_rank = (i + j) / 2 + 1  # 1-based
                for k in range(i, j + 1):
                    r[indexed[k][0]] = avg_rank
                i = j + 1
            return r

        rx, ry = ranks(xs), ranks(ys)
        mx = sum(rx) / n
        my = sum(ry) / n
        num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
        den = math.sqrt(
            sum((rx[i] - mx) ** 2 for i in range(n))
            * sum((ry[i] - my) ** 2 for i in range(n))
        )
        return round(num / den, 4) if den > 0 else None
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# snapshot accrual
# ---------------------------------------------------------------------------

def _load_snapshots(root: Path) -> list[dict]:
    p = root.joinpath(*_SNAPSHOTS_FILE)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _snapshot_key(row: dict) -> str:
    return f"{row['date']}|{row['subject']}"


def snapshot(today: date | str | None = None, root: Path | None = None) -> int:
    """Append today's edge readings to data/radar/edge_snapshots.jsonl.

    Rows are keyed to the SESSION: the stamped `date` is radar.json's `as_of`
    (the market session the flags were computed from), falling back to
    radar_ticker.json's `as_of`, then to the `today` argument. v1 stamped the
    wall-clock date, so weekend/holiday runs re-recorded Friday's readings —
    and Friday's entry close — under fresh dates (calendar-vs-session ledger
    trap, #4568 family). Idempotent by (date, subject). Returns count of
    newly-appended rows."""
    try:
        root = Path(root) if root else config.ROOT
        today_str = (today.isoformat() if hasattr(today, "isoformat") else str(today or date.today()))

        # Load current snapshots to find existing keys
        existing = {_snapshot_key(r) for r in _load_snapshots(root)}

        new_rows: list[dict] = []

        # -- per-basket: hypotheses from radar.json; edge_score from radar_enriched.json --
        # Single-writer fix (neural-web W0 PR5): build_radar_plus now writes edge_score to
        # radar_enriched.json, not radar.json.  Fallback to radar.json edge_score for one
        # cycle of backward compatibility (legacy runs where radar_enriched.json is absent).
        radar_p = root / "site" / "basketdata" / "radar.json"
        enriched_p = root / "site" / "basketdata" / "radar_enriched.json"
        ticker_p = root / "site" / "basketdata" / "radar_ticker.json"

        # Session key: prefer the data's own as_of over the wall clock.
        session = None
        rd: dict = {}
        td: dict = {}
        if radar_p.exists():
            try:
                rd = json.loads(radar_p.read_text())
                session = rd.get("as_of") or None
            except Exception as e:  # noqa: BLE001
                log.warning("snapshot: radar.json parse error: %s", e)
                rd = {}
        if ticker_p.exists():
            try:
                td = json.loads(ticker_p.read_text())
                if not session:
                    session = td.get("as_of") or None
            except Exception as e:  # noqa: BLE001
                log.warning("snapshot: radar_ticker.json parse error: %s", e)
                td = {}
        session = str(session or today_str)[:10]

        if rd:
            try:
                mem = _load_membership(root)
                # Build basket→horizon_d map from hypotheses (stamped by radar.py at seed
                # time, in TRADING days). Metadata only in v2 — the descriptive IC grades
                # every row at every horizon; the seeded promise itself is graded by
                # engine/radar_scorer.py at each hypothesis's check_by.
                hyp_horizon: dict[str, int] = {
                    h["subject"]: int(h["horizon_d"])
                    for h in rd.get("hypotheses", [])
                    if h.get("horizon_d") and h.get("subject")
                }
                # Build basket→edge_score from radar_enriched.json (canonical post W0 PR5);
                # fall back to radar.json flag.edge_score for pre-fix runs.
                enriched_edge: dict[str, int] = {}
                if enriched_p.exists():
                    try:
                        ed = json.loads(enriched_p.read_text())
                        for ef in ed.get("flags", []):
                            bid = ef.get("basket", "")
                            es = ef.get("edge_score")
                            if bid and es is not None:
                                enriched_edge[bid] = int(es)
                    except Exception as _ee:  # noqa: BLE001
                        log.debug("snapshot: radar_enriched.json parse error: %s", _ee)
                for flag in rd.get("flags", []):
                    state = flag.get("state", "")
                    if state == "QUIET":
                        continue
                    basket_id = flag.get("basket", "")
                    # Prefer enriched edge_score; fall back to inline (legacy/first-run).
                    es = enriched_edge.get(basket_id) if enriched_edge else flag.get("edge_score")
                    if es is None:
                        continue
                    proxy = _proxy_for(basket_id, mem)
                    if not proxy:
                        continue
                    row: dict[str, Any] = {
                        "date": session,
                        "kind": "basket",
                        "subject": basket_id,
                        "ticker": proxy,
                        "edge_score": int(es),
                        "state": state,
                        "era": _CURRENT_ERA,
                    }
                    # Stamp the seeded horizon (trading days) as metadata.
                    if basket_id in hyp_horizon:
                        row["horizon_d"] = hyp_horizon[basket_id]
                    key = _snapshot_key(row)
                    if key not in existing:
                        new_rows.append(row)
                        existing.add(key)
            except Exception as e:  # noqa: BLE001
                log.warning("snapshot: radar.json processing error: %s", e)

        # -- per-ticker from radar_ticker.json --
        if td:
            try:
                for t in td.get("tickers", []):
                    state = t.get("state", "")
                    if state == "QUIET":
                        continue
                    es = t.get("edge_score")
                    ticker = t.get("ticker", "")
                    if es is None or not ticker:
                        continue
                    row = {
                        "date": session,
                        "kind": "ticker",
                        "subject": ticker,
                        "ticker": ticker,
                        "edge_score": int(es),
                        "state": state,
                        "era": _CURRENT_ERA,
                    }
                    # Provenance: 'signal' (direct alt-signal read) vs 'basket_attributed'
                    # (a basket flag attributed down to a member). Separable cohorts at
                    # grading time — the buy-the-laggard construction gets its own grade.
                    if t.get("source"):
                        row["source"] = t["source"]
                    key = _snapshot_key(row)
                    if key not in existing:
                        new_rows.append(row)
                        existing.add(key)
            except Exception as e:  # noqa: BLE001
                log.warning("snapshot: radar_ticker.json processing error: %s", e)

        if not new_rows:
            log.info("snapshot: nothing new to append (already snapshotted or no data)")
            return 0

        p = root.joinpath(*_SNAPSHOTS_FILE)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as fh:
            for r in new_rows:
                fh.write(json.dumps(r, separators=(",", ":")) + "\n")

        log.info("snapshot: appended %d rows for session %s", len(new_rows), session)
        return len(new_rows)

    except Exception as e:  # noqa: BLE001
        log.warning("snapshot failed: %s", e)
        return 0


# ---------------------------------------------------------------------------
# membership / proxy helpers (mirrors radar.py, self-contained here)
# ---------------------------------------------------------------------------

def _load_membership(root: Path) -> dict:
    try:
        p = root / "data" / "baskets" / "membership.json"
        return json.loads(p.read_text()).get("baskets", {})
    except Exception:  # noqa: BLE001
        return {}


def _proxy_for(basket_id: str, mem: dict) -> str | None:
    b = mem.get(basket_id) or {}
    px = b.get("etf_proxy")
    if isinstance(px, list):
        px = px[0] if px else None
    if isinstance(px, str) and px.strip():
        return px.strip().split()[0]
    return None


# ---------------------------------------------------------------------------
# episode segmentation
# ---------------------------------------------------------------------------

def _episode_entries(rows: list[dict]) -> list[dict]:
    """Collapse the snapshot panel into EPISODES: contiguous same-(subject,state)
    runs, split when the subject skips more than _EPISODE_GAP_D calendar days.
    Returns the ENTRY row of each episode with `episode_len` (row count) added.

    Rationale: a flag that persists for three weeks is one call observed daily,
    not twenty-one independent calls. Row-level (v1) stats duration-weight every
    episode; episode-level stats grade each call once, at its entry."""
    by_subject: dict[str, list[dict]] = {}
    for r in rows:
        if not r.get("subject") or not r.get("date"):
            continue
        by_subject.setdefault(r["subject"], []).append(r)
    entries: list[dict] = []
    for _, subj_rows in by_subject.items():
        subj_rows.sort(key=lambda r: r["date"])
        cur: dict | None = None
        prev_date: pd.Timestamp | None = None
        prev_state: str | None = None
        for r in subj_rows:
            try:
                d = pd.Timestamp(r["date"])
            except Exception:  # noqa: BLE001
                continue
            new_run = (
                cur is None
                or r.get("state") != prev_state
                or (prev_date is not None and (d - prev_date).days > _EPISODE_GAP_D)
            )
            if new_run:
                if cur is not None:
                    entries.append(cur)
                cur = {**r, "episode_len": 1}
            else:
                cur["episode_len"] = cur.get("episode_len", 1) + 1
            prev_date, prev_state = d, r.get("state")
        if cur is not None:
            entries.append(cur)
    entries.sort(key=lambda r: (r["date"], r.get("subject", "")))
    return entries


# ---------------------------------------------------------------------------
# IC computation
# ---------------------------------------------------------------------------

def _dir_hit(state: str, fwd: float) -> bool | None:
    """True/False for a directional state's call vs the realized sign; None when the
    state makes no directional claim (BROKEN_LAGGARD etc.) — excluded from hit math."""
    d = _STATE_DIR.get(state, 0)
    if d == 0:
        return None
    return fwd > 0 if d > 0 else fwd < 0


def _cohort_stats(rows: list[dict]) -> dict:
    """Directional accuracy + mean forward return for a cohort of enriched rows.
    Non-directional rows are counted (n_nonclaim) but excluded from accuracy."""
    n = len(rows)
    hits = misses = 0
    for r in rows:
        h = _dir_hit(r.get("state", ""), r["fwd_rel_return"])
        if h is True:
            hits += 1
        elif h is False:
            misses += 1
    n_dir = hits + misses
    return {
        "n": n,
        "n_directional": n_dir,
        "n_nonclaim": n - n_dir,
        "dir_accuracy": round(hits / n_dir, 3) if n_dir else None,
        "mean_fwd_ret": round(sum(r["fwd_rel_return"] for r in rows) / n, 4) if n else None,
    }


def _base_rate(enriched: list[dict]) -> dict:
    """The era's unconditional cross-section at this horizon: what a dart would
    have scored. Every cohort accuracy must be read against p_up (bullish calls)
    or 1 - p_up (bearish calls) — NOT against 0.5."""
    n = len(enriched)
    if not n:
        return {"n": 0, "p_up": None, "mean_fwd_ret": None, "median_fwd_ret": None}
    fwds = sorted(r["fwd_rel_return"] for r in enriched)
    ups = sum(1 for f in fwds if f > 0)
    mid = n // 2
    median = fwds[mid] if n % 2 else (fwds[mid - 1] + fwds[mid]) / 2
    return {
        "n": n,
        "p_up": round(ups / n, 3),
        "mean_fwd_ret": round(sum(fwds) / n, 4),
        "median_fwd_ret": round(median, 4),
    }


def _excess_vs_base(state: str, dir_accuracy: float | None, p_up: float | None
                    ) -> float | None:
    """Cohort skill net of the era: accuracy minus the matching directional base
    rate (p_up for bullish states, 1-p_up for bearish)."""
    if dir_accuracy is None or p_up is None:
        return None
    d = _STATE_DIR.get(state, 0)
    if d == 0:
        return None
    base = p_up if d > 0 else 1.0 - p_up
    return round(dir_accuracy - base, 3)


def _dart_baseline(rows: list[dict], p_up: float | None) -> float | None:
    """Direction-weighted dart accuracy for a MIXED-direction cohort: the accuracy
    a dart throwing the same mix of bullish/bearish calls would have scored in
    this era — mean over directional rows of (p_up if bullish else 1-p_up)."""
    if p_up is None:
        return None
    dirs = [_STATE_DIR.get(r.get("state"), 0) for r in rows]
    dirs = [d for d in dirs if d]
    if not dirs:
        return None
    return round(sum(p_up if d > 0 else 1.0 - p_up for d in dirs) / len(dirs), 3)


def _compute_ic_for_horizon(
    rows: list[dict], root: Path, horizon_d: int, today_dt: date,
) -> dict:
    """Inner helper: compute IC stats for a single horizon.

    v2: EVERY row is graded at every horizon (descriptive lead/lag measurement).
    v1 restricted `horizon_d`-stamped rows to their stamped horizon, which was
    starving the panels — every POSITIVE_DIVERGENCE basket row left the 21d
    block while the 63d block (calendar days, mismatching the trading-day
    promise) had nothing matured. The stamp is provenance metadata; the seeded
    PROMISE is graded by engine/radar_scorer.py at each hypothesis's check_by.

    Returns a dict with the v1 keys (n_matured, ic_all, ic_rolling, by_bucket,
    by_state, ic_daily_hac, note) plus v2 additions (base_rate, ic_all_signed,
    claims, diagonal, episodes, by_kind). Never raises.
    """
    matured = [r for r in rows if _is_matured(r, root, horizon_d, today_dt)]

    enriched: list[dict] = []
    for r in matured:
        fwd = _fwd_rel_return(r["ticker"], root, r["date"], horizon_d)
        if fwd is None:
            continue
        enriched.append({**r, "fwd_rel_return": fwd})

    n_matured = len(enriched)

    if n_matured < 3:
        accruing_note = (
            f"Accruing — {n_matured} matured observations so far "
            f"(need ≥3 for IC; grows as the {horizon_d}d horizon elapses)."
        )
        return {
            "n_matured": n_matured,
            "ic_all": None,
            "ic_all_signed": None,
            f"ic_rolling_{_ROLLING_N}": None,
            "ic_daily_hac": {"n_days": 0},
            "ic_daily_hac_claims": {"n_days": 0},
            "base_rate": _base_rate(enriched),
            "by_bucket": {label: {"n": 0, "hit_rate": None, "mean_fwd_ret": None}
                          for label, *_ in _BUCKETS},
            "by_state": {},
            "by_kind": {},
            "claims": _cohort_stats([]),
            "diagonal": _cohort_stats([]),
            "episodes": {"n_matured": 0, "claims": _cohort_stats([]),
                         "diagonal": _cohort_stats([]), "ic_signed": None},
            "note": accruing_note,
        }

    scores = [r["edge_score"] for r in enriched]
    returns = [r["fwd_rel_return"] for r in enriched]
    # Legacy headline (v1): UNSIGNED pooled Spearman. Kept for continuity but it
    # conflates direction with salience — read ic_all_signed / the HAC blocks.
    ic_all = _spearman_ic(scores, returns)
    directional = [r for r in enriched if _STATE_DIR.get(r.get("state"), 0)]
    ic_all_signed = _spearman_ic(
        [r["edge_score"] * _STATE_DIR[r["state"]] for r in directional],
        [r["fwd_rel_return"] for r in directional],
    ) if directional else None

    # Rolling IC over last _ROLLING_N obs (by append order)
    if n_matured >= _ROLLING_N:
        recent = enriched[-_ROLLING_N:]
        ic_rolling = _spearman_ic(
            [r["edge_score"] for r in recent],
            [r["fwd_rel_return"] for r in recent],
        )
    else:
        ic_rolling = ic_all  # use all when fewer than the window

    base = _base_rate(enriched)

    # Hit-rate by edge bucket. v2 fix: non-directional states (BROKEN_LAGGARD)
    # no longer sit in the denominator as guaranteed misses.
    by_bucket: dict[str, dict] = {}
    for label, lo, hi in _BUCKETS:
        bucket_rows = [r for r in enriched if lo <= r["edge_score"] < hi]
        stats = _cohort_stats(bucket_rows)
        by_bucket[label] = {
            "n": stats["n"],
            "n_directional": stats["n_directional"],
            "hit_rate": stats["dir_accuracy"],
            "mean_fwd_ret": stats["mean_fwd_ret"],
        }

    # Directional accuracy by state (+ skill net of the era's base rate)
    by_state: dict[str, dict] = {}
    for state in (*_BULLISH_STATES, *_BEARISH_STATES):
        state_rows = [r for r in enriched if r.get("state") == state]
        if not state_rows:
            continue
        stats = _cohort_stats(state_rows)
        by_state[state] = {
            "n": stats["n"],
            "dir_accuracy": stats["dir_accuracy"],
            "excess_vs_base": _excess_vs_base(state, stats["dir_accuracy"], base["p_up"]),
            "mean_fwd_ret": stats["mean_fwd_ret"],
        }

    # Population split: the page is about THEME flags, but ticker rows dominate
    # the ledger ~9:1. Report kinds separately so neither masquerades as the other.
    by_kind: dict[str, dict] = {}
    for kind in ("basket", "ticker"):
        kind_rows = [r for r in enriched if r.get("kind") == kind]
        if kind_rows:
            by_kind[kind] = _cohort_stats(kind_rows)

    # Claims (divergence states — what the radar actually asserts) vs the
    # diagonal (CONFIRMED_* — "already priced", explicitly not a call).
    claim_rows = [r for r in enriched if r.get("state") in _CLAIM_STATES]
    diag_rows = [r for r in enriched if r.get("state") in _DIAGONAL_STATES]
    claims = _cohort_stats(claim_rows)
    claims["base_dart"] = _dart_baseline(claim_rows, base["p_up"])
    claims["excess_vs_base"] = (
        round(claims["dir_accuracy"] - claims["base_dart"], 3)
        if claims["dir_accuracy"] is not None and claims["base_dart"] is not None else None
    )
    diagonal = _cohort_stats(diag_rows)
    diagonal["base_dart"] = _dart_baseline(diag_rows, base["p_up"])
    diagonal["excess_vs_base"] = (
        round(diagonal["dir_accuracy"] - diagonal["base_dart"], 3)
        if diagonal["dir_accuracy"] is not None and diagonal["base_dart"] is not None else None
    )

    # Episode-level: one grade per contiguous flag run, at its entry day.
    entries = _episode_entries(rows)
    ep_matured = [e for e in entries if _is_matured(e, root, horizon_d, today_dt)]
    ep_enriched = []
    for e in ep_matured:
        fwd = _fwd_rel_return(e["ticker"], root, e["date"], horizon_d)
        if fwd is None:
            continue
        ep_enriched.append({**e, "fwd_rel_return": fwd})
    ep_claims = [e for e in ep_enriched if e.get("state") in _CLAIM_STATES]
    ep_diag = [e for e in ep_enriched if e.get("state") in _DIAGONAL_STATES]
    ep_dir = [e for e in ep_enriched if _STATE_DIR.get(e.get("state"), 0)]
    ep_base = _base_rate(ep_enriched)
    ep_claims_stats = _cohort_stats(ep_claims)
    ep_claims_stats["base_dart"] = _dart_baseline(ep_claims, ep_base["p_up"])
    ep_claims_stats["excess_vs_base"] = (
        round(ep_claims_stats["dir_accuracy"] - ep_claims_stats["base_dart"], 3)
        if ep_claims_stats["dir_accuracy"] is not None
        and ep_claims_stats["base_dart"] is not None else None
    )
    episodes = {
        "n_matured": len(ep_enriched),
        "base_rate": ep_base,
        "claims": ep_claims_stats,
        "diagonal": _cohort_stats(ep_diag),
        "ic_signed": _spearman_ic(
            [e["edge_score"] * _STATE_DIR[e["state"]] for e in ep_dir],
            [e["fwd_rel_return"] for e in ep_dir],
        ) if ep_dir else None,
    }

    note = (
        f"{n_matured} matured row-observations (horizon={horizon_d}d; "
        f"{episodes['n_matured']} distinct episodes). "
        f"Base rate P(beat {_BENCH})={base['p_up']}. "
        f"IC_all={ic_all} (unsigned legacy), IC_signed={ic_all_signed}. "
        "CONTEXT-ONLY — never fed into a score/size/allocation."
    ) if n_matured >= 10 else (
        f"ACCRUING — only {n_matured} matured obs (need ~30+ for reliable IC). "
        "Treat these early numbers as provisional. "
        "Context-only, never a trade signal."
    )

    return {
        "n_matured": n_matured,
        "ic_all": ic_all,
        "ic_all_signed": ic_all_signed,
        f"ic_rolling_{_ROLLING_N}": ic_rolling,
        # Governor contract (signal_governor._pick_reading): all directional
        # states, signed — unchanged from v1.
        "ic_daily_hac": _daily_hac_signed_ic(enriched, horizon_d),
        # Verdict series: the radar's CLAIMS only (divergence states).
        "ic_daily_hac_claims": _daily_hac_signed_ic(enriched, horizon_d, states=_CLAIM_STATES),
        "base_rate": base,
        "by_bucket": by_bucket,
        "by_state": by_state,
        "by_kind": by_kind,
        "claims": claims,
        "diagonal": diagonal,
        "episodes": episodes,
        "note": note,
    }


def _verdict(by_horizon: dict[str, dict]) -> dict:
    """Machine-readable, pre-registered verdict over the CLAIMS cohort.

    Picks the LONGEST horizon whose claims HAC is valid and non-degenerate
    (n_days ≥ lag=horizon — same rule as signal_governor._needed_days), then:

      status = 'insufficient'  — matured claim episodes < V_MIN_EPISODES, or no
                                  valid claims HAC at any horizon yet
               'null'          — evidence gates met, |t| < V_T_SIG: measured,
                                  no evidence of lead OR lag either way
               'lagging'       — t ≤ -V_T_SIG on the claims series (wrong sign)
               'leading'       — t ≥ +V_T_SIG (right sign)

    The front-end copy keys off `status` — it may not claim worked/failed
    from any other field. Gates are committed constants (a pre-registration);
    the diagonal (CONFIRMED_*) cohort never enters this verdict."""
    best = None
    best_h = 0
    max_ep = 0
    for h_str, blk in (by_horizon or {}).items():
        try:
            h = int(h_str)
        except (TypeError, ValueError):
            continue
        ep = ((blk.get("episodes") or {}).get("claims") or {}).get("n_directional") or 0
        max_ep = max(max_ep, ep)
        hac = blk.get("ic_daily_hac_claims") or {}
        t = hac.get("t_hac")
        n_days = hac.get("n", hac.get("n_days", 0)) or 0
        if t is None or n_days < max(6, h):        # degenerate/absent HAC ⇒ not usable
            continue
        if h > best_h:
            best_h = h
            best = {"horizon": h, "t_hac": round(float(t), 3),
                    "mean_ic": hac.get("mean_ic"), "n_days": int(n_days),
                    "n_claim_episodes": ep}
    gates = {"min_claim_episodes": V_MIN_EPISODES, "t_sig": V_T_SIG,
             "hac_valid_rule": "n_days >= lag (=horizon)"}
    if best is None:
        return {"status": "insufficient", "basis": None, "gates": gates,
                "n_claim_episodes": max_ep,
                "note": ("No horizon carries a valid, non-degenerate claims HAC yet "
                         "(need >= horizon daily cross-sections against the "
                         "horizon-length overlap) — measuring, no performance "
                         "statement possible.")}
    if max_ep < V_MIN_EPISODES:
        return {"status": "insufficient", "basis": best, "gates": gates,
                "n_claim_episodes": max_ep,
                "note": ("Not enough matured, independent claim episodes for any "
                         "performance statement — measuring.")}
    if best["n_claim_episodes"] < V_MIN_EPISODES:
        return {"status": "insufficient", "basis": best, "gates": gates,
                "n_claim_episodes": best["n_claim_episodes"],
                "note": "Valid HAC exists but claim episodes below the pre-registered floor."}
    t = best["t_hac"]
    if t <= -V_T_SIG:
        status = "lagging"
    elif t >= V_T_SIG:
        status = "leading"
    else:
        status = "null"
    return {"status": status, "basis": best, "gates": gates,
            "n_claim_episodes": best["n_claim_episodes"],
            "note": {"lagging": "Claims HAC significantly wrong-signed at the verdict horizon.",
                     "leading": "Claims HAC significantly right-signed at the verdict horizon.",
                     "null": "Evidence gates met; no significant lead or lag either way."}[status]}


def compute_ic(today: date | str | None = None, horizon_d: int = _HORIZON_D,
               horizons: list[int] | None = None,
               root: Path | None = None) -> dict:
    """Compute Spearman IC + hit-rate across all matured snapshots.

    Horizon-parametric: default `horizons=[21, 63, 91]` — 21d legacy early read,
    63d legacy calendar block, 91 calendar days ≈ the 63-TRADING-day horizon
    radar.py actually promises at seed time. Legacy top-level fields (n_matured,
    ic_all, ic_rolling_90, by_bucket, by_state, note) always reflect the 21d
    horizon so existing consumers of radar_ic.json are unaffected.

    `horizon_d` (single int, legacy) is still accepted; when passed alone it sets
    the primary horizon only — `horizons` takes precedence when given.

    Degrades safely: if no snapshots or none matured yet, returns a valid dict
    with n_matured:0 and an "accruing" note. Never raises.
    """
    if horizons is None:
        horizons = list(_HORIZONS_DEFAULT)
    # Ensure the legacy primary horizon is always computed (backward compat)
    if horizon_d not in horizons:
        horizons = [horizon_d] + list(horizons)

    try:
        root = Path(root) if root else config.ROOT
        today_dt = (pd.Timestamp(today).date() if today else date.today())
        today_str = today_dt.isoformat()

        _SERIES_MEMO.clear()   # fresh prices per invocation; reused across horizons
        rows = _load_snapshots(root)
        n_total = len(rows)

        # Compute per-horizon blocks
        by_horizon: dict[str, dict] = {}
        for h in horizons:
            by_horizon[str(h)] = _compute_ic_for_horizon(rows, root, h, today_dt)

        # Legacy primary horizon block (horizon_d, default 21d)
        primary = by_horizon[str(horizon_d)]
        n_matured = primary["n_matured"]
        ic_all = primary["ic_all"]
        ic_rolling = primary[f"ic_rolling_{_ROLLING_N}"]

        return {
            "schema": SCHEMA,
            "as_of": today_str,
            "generated_at": _now_iso(),
            "horizon_d": horizon_d,            # legacy primary horizon
            "horizons": horizons,              # all computed horizons
            "seed_horizon_cal_d": _SEED_CAL_D,  # the block matching the seeded promise
            "n_snapshots": n_total,
            # Legacy top-level fields = primary (21d) horizon — consumers unaffected
            "n_matured": n_matured,
            "ic_all": ic_all,
            "ic_all_signed": primary.get("ic_all_signed"),
            f"ic_rolling_{_ROLLING_N}": ic_rolling,
            "by_bucket": primary["by_bucket"],
            "by_state": primary["by_state"],
            "base_rate": primary.get("base_rate"),
            "note": primary["note"],
            # Per-horizon detail blocks (W1 scoreboard + signal governor read here)
            "by_horizon": by_horizon,
            # Pre-registered honest verdict — the ONLY field front-end copy may
            # base a worked/failed claim on.
            "verdict": _verdict(by_horizon),
            "era_breaks": _ERA_BREAKS,
        }

    except Exception as e:  # noqa: BLE001
        log.warning("compute_ic failed: %s", e)
        as_of_str = (today.isoformat() if hasattr(today, "isoformat")
                     else str(today or date.today()))
        return _empty_result(
            as_of_str, 0, 0, horizon_d,
            f"compute_ic error: {e} — accruing, degrade-safe.",
        )


def _empty_horizon_block(horizon_d: int, note: str) -> dict:
    return {
        "n_matured": 0,
        "ic_all": None,
        "ic_all_signed": None,
        f"ic_rolling_{_ROLLING_N}": None,
        "ic_daily_hac": {"n_days": 0},
        "ic_daily_hac_claims": {"n_days": 0},
        "base_rate": {"n": 0, "p_up": None, "mean_fwd_ret": None, "median_fwd_ret": None},
        "by_bucket": {label: {"n": 0, "hit_rate": None, "mean_fwd_ret": None}
                      for label, *_ in _BUCKETS},
        "by_state": {},
        "by_kind": {},
        "claims": _cohort_stats([]),
        "diagonal": _cohort_stats([]),
        "episodes": {"n_matured": 0, "claims": _cohort_stats([]),
                     "diagonal": _cohort_stats([]), "ic_signed": None},
        "note": note,
    }


def _empty_result(as_of: str, n_snapshots: int, n_matured: int,
                  horizon_d: int, note: str) -> dict:
    horizons = list(_HORIZONS_DEFAULT)
    if horizon_d not in horizons:
        horizons = [horizon_d] + horizons
    return {
        "schema": SCHEMA,
        "as_of": as_of,
        "generated_at": _now_iso(),
        "horizon_d": horizon_d,
        "horizons": horizons,
        "seed_horizon_cal_d": _SEED_CAL_D,
        "n_snapshots": n_snapshots,
        "n_matured": n_matured,
        "ic_all": None,
        "ic_all_signed": None,
        f"ic_rolling_{_ROLLING_N}": None,
        "by_bucket": {label: {"n": 0, "hit_rate": None, "mean_fwd_ret": None}
                      for label, *_ in _BUCKETS},
        "by_state": {},
        "base_rate": {"n": 0, "p_up": None, "mean_fwd_ret": None, "median_fwd_ret": None},
        "note": note,
        "by_horizon": {str(h): _empty_horizon_block(h, note) for h in horizons},
        "verdict": {"status": "insufficient", "basis": None,
                    "gates": {"min_claim_episodes": V_MIN_EPISODES, "t_sig": V_T_SIG,
                              "hac_valid_rule": "n_days >= lag (=horizon)"},
                    "n_claim_episodes": 0, "note": note},
        "era_breaks": _ERA_BREAKS,
    }
