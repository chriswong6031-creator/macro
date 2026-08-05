"""China Prophet loser + miss telemetry — OPS-TELEMETRY tier, **ZERO AUTHORITY**.

WHAT THIS IS
------------
A nightly read-only forensic pass over the board ledger that answers two questions the
board itself cannot answer about itself:

  1. **Which of our own picks lost, and did they share a shape?** Per matured episode
     it recomputes the "chase" shape — did we buy a name that had already gone (closed
     at its own high on a limit-move day, gapped away from us overnight, or arrived
     after a 21-session run) — and reports the loser/winner split inside that cohort
     against the cohort outside it.
  2. **Which real runners did we never surface, and where did they stop?** Rolling
     top-150 trailing-63-session runners are joined against the point-in-time candidate
     ledger, so a name we missed is attributed to the exact funnel stage that dropped
     it (``featured`` / ``more_actionable`` / ``late_or_unfillable`` / ``forming`` /
     ``not_raw_eligible`` / ``absent``) rather than to a vague "we missed it".

WHAT THIS IS NOT — the authority boundary
-----------------------------------------
This module has **zero authority**. It never scores, ranks, gates, sizes, vetoes, or
orders anything. It writes to its own store (``data/cn_prophet_audit/``) and to nothing
else; no production artifact, template, or lane reads from it. Its outputs are
operator-facing telemetry for deciding what to *investigate*, and every number in them
is display-tier until it is separately promoted through the gauntlet (CLAUDE.md
§Epistemics: the gauntlet is a PROMOTION gate, never a build gate — a null here blocks
nothing and the accrual continues regardless).

CONVENTIONS THAT ARE LOAD-BEARING
---------------------------------
* **Never pooled across ``board_definition``.** The legacy cascade/setup board and the
  selective ``cn_prophet_v2`` shelf are different instruments; a union measures neither
  (the same law ``china_standout_track._latest_definition_frame`` enforces). Every
  aggregate in this module is keyed by definition and the definitions are never summed.
* **The ledger's own scorer.** Episodes come from ``track_scoring.build_episodes`` over
  ``{date → tickers}``; grading is the forced H=10 verdict via ``score_from_fill`` with
  the CN T+1 fill from ``china_standout_track._t1_fill`` (locked-limit rows excluded —
  unfillable is unfillable) and CSI300-relative excess off ``_bench_close``. Re-deriving
  a second scoring path here would produce a second, incomparable win rate.
* **PIT only for the miss funnel.** A name's funnel state on a session is the lane the
  candidate ledger *recorded that day*. ``gate()`` is never replayed and history is
  never backfilled — both are far too heavy for the asia lane, and a replayed gate is
  not point-in-time anyway. Coverage therefore starts at the candidate store's birth
  (2026-07-30) and ``coverage_start`` is printed in every artifact.
* **Write discipline.** Best-effort, never raises. Writes are gated to the asia
  collection lane (``lane in (None, 'asia')`` — ``None`` is the legacy call convention)
  and refused on a mid-session partial panel via the SAME
  ``china_standout_track.session_status`` check ``append_board`` uses. The forward log
  is append-only, keep-first per ``(date, board_definition)``.

BUDGET
------
Render budget is law. The whole pass is designed to stay well inside the ~90s allotted
to it on the asia lane: per-ticker price frames are memoised across every episode, the
runner universe is scanned with ``columns=['close']`` only, and no per-name recompute of
any production signal happens at all. Measured ``elapsed_seconds`` ships in the artifact
so a regression is visible the night it lands.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

STORE_DIR = "cn_prophet_audit"
LATEST_FILE = "latest.json"
FORWARD_LOG_FILE = "forward_log.parquet"
SCHEMA = "cn_prophet_audit/v1"
TIER = "ops-telemetry"

# Grading conventions — deliberately the SAME constants the CN ledger publishes with.
HORIZON = 10                      # sessions; forced verdict (track_scoring.DEFAULT_HORIZON)
METRIC = "excess"                 # CSI300-relative; in A-shares beta dominates absolute P&L

# ── chase shape ────────────────────────────────────────────────────────────────
# A-share daily price limits: ChiNext (300*) and STAR (688*) trade a ±20% band, the
# main boards ±10%. The stored closes are dividend-adjusted, so an exact ±limit print
# is not reliably reproducible from them — hence the 0.95 tolerance band below, which
# is what "the name went limit-ish today" has to mean on adjusted data.
LIMIT_WIDE_PREFIXES = ("300", "688")
LIMIT_WIDE = 0.185
LIMIT_STD = 0.095
LIMIT_NEAR_FRACTION = 0.95
CHASE_T1_GAP = 0.03               # T+1 fill printed ≥3% above the close we logged
CHASE_TRAIL_21 = 0.25             # the name had already run ≥25% into the board date
TRAIL_WINDOW = 21

# ── miss funnel ────────────────────────────────────────────────────────────────
RUNNER_TOP_N = 150
RUNNER_LOOKBACK = 63              # trailing sessions (~3 months)
RUNNER_MIN_BARS = 200             # a name with less history has no comparable trail
RUNNER_GROUP = "china_stocks"
CANDIDATE_DIR = "china_prophet_rank"
CANDIDATE_FILE = "candidates.parquet"
FUNNEL_ABSENT = "absent"          # not in the candidate ledger that session at all
FUNNEL_LANES = (
    "featured",
    "more_actionable",
    "late_or_unfillable",
    "forming",
    "not_raw_eligible",
    FUNNEL_ABSENT,
)

_MEMBERS = ("china_search", "members.parquet")


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------
def _store_dir():
    return config.data_dir() / STORE_DIR


def latest_path():
    return _store_dir() / LATEST_FILE


def forward_log_path():
    return _store_dir() / FORWARD_LOG_FILE


def _candidates_path():
    return config.data_dir() / CANDIDATE_DIR / CANDIDATE_FILE


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def limit_for(ticker: str) -> float:
    """Daily price-limit band for an A-share ticker (0.185 wide-band, else 0.095).

    ChiNext (300xxx) and STAR (688xxx) run a ±20% band; every other board ±10%. The
    constants are the tolerance-adjusted forms — see LIMIT_NEAR_FRACTION.
    """
    core = str(ticker).split(".")[0]
    return LIMIT_WIDE if core.startswith(LIMIT_WIDE_PREFIXES) else LIMIT_STD


def _f(value: Any) -> float | None:
    """float() that returns None rather than raising or propagating NaN."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if pd.notna(out) else None


def _round(value: float | None, nd: int) -> float | None:
    return None if value is None else round(float(value), nd)


def _rate(numer: int, denom: int) -> float | None:
    return None if not denom else round(numer / denom, 4)


_LEGACY_STAMPS = frozenset({"", "nan", "none", "nat", "legacy", "<na>"})


def norm_definition(value: Any) -> str:
    """Normalise a stored ``board_definition`` to the era name the ledger publishes.

    Every pre-version spelling (null / NaN / '' / 'None' / '<NA>' / 'legacy') IS the
    legacy era — the same reading ``build_china_library._cn_is_legacy_stamp`` takes.
    Without this a null stamp would open its own phantom 'nan' definition block and
    split one era's sample in two.
    """
    text = "" if value is None else str(value).strip()
    return "legacy" if text.lower() in _LEGACY_STAMPS else text


def _sector_lookup() -> dict[str, str | None]:
    """ticker → sector from the curated search universe. Empty dict when absent."""
    out: dict[str, str | None] = {}
    try:
        p = config.data_dir() / _MEMBERS[0] / _MEMBERS[1]
        if not p.exists():
            return out
        mem = pd.read_parquet(p)
        if "sector" not in mem.columns:
            return out
        for tk, sec in mem["sector"].items():
            out[str(tk)] = str(sec) if pd.notna(sec) else None
    except Exception as exc:  # noqa: BLE001 — enrichment only, null is fine
        log.debug("cn_prophet_audit: sector lookup skipped (%s)", exc)
    return out


# ---------------------------------------------------------------------------
# 1. loser telemetry
# ---------------------------------------------------------------------------
def chase_fields(pdf: pd.DataFrame, closes: pd.Series, d0: pd.Timestamp,
                 ticker: str, fill: float | None) -> dict:
    """The per-episode CHASE shape measured on the board date and its T+1 fill.

    Four independently-null legs, then the composite:

      ``day0_at_high``  the board-date bar closed AT its own high — the price the user
                        was shown was the top tick of the session, untradeable in size.
      ``day0_ret``      that bar's own return (vs the prior close).
      ``limit_move``    ``day0_ret`` reached ~the board's daily limit band.
      ``t1_gap``        the T+1 fill vs the close we logged — how far the entry ran away
                        overnight from the number the board published.
      ``trail_21``      the 21-session run INTO the board date — arriving after the move.

    ``chase_composite`` = (``day0_at_high`` AND ``limit_move``) OR ``t1_gap`` ≥ 3%
    OR ``trail_21`` ≥ 25%. The pin-and-limit leg is deliberately a conjunction: a close
    at the high on a quiet day is noise, and a limit move the user could still have
    entered under is not a chase — it is the pair that says "gone".

    Every leg is None when its inputs are unavailable, and a None leg simply does not
    fire (it never blocks the composite from firing on another leg).
    """
    out: dict[str, Any] = {
        "day0_at_high": None, "day0_ret": None, "limit_move": None,
        "t1_gap": None, "trail_21": None, "chase_composite": False,
        "limit_band": limit_for(ticker),
    }
    if d0 in pdf.index:
        row = pdf.loc[d0]
        hi, cl = _f(row.get("high")), _f(row.get("close"))
        if hi is not None and cl is not None:
            out["day0_at_high"] = bool(hi == cl)
    board_close = _f(closes.get(d0)) if d0 in closes.index else None

    prior = closes[closes.index < d0]
    if len(prior) and board_close is not None:
        prev = _f(prior.iloc[-1])
        if prev:
            out["day0_ret"] = board_close / prev - 1.0

    if out["day0_ret"] is not None:
        out["limit_move"] = bool(
            out["day0_ret"] >= LIMIT_NEAR_FRACTION * out["limit_band"]
        )

    if fill is not None and board_close:
        out["t1_gap"] = float(fill) / board_close - 1.0

    upto = closes[closes.index <= d0]
    if len(upto) >= TRAIL_WINDOW + 1:
        base = _f(upto.iloc[-(TRAIL_WINDOW + 1)])
        last = _f(upto.iloc[-1])
        if base and last is not None:
            out["trail_21"] = last / base - 1.0

    out["chase_composite"] = bool(
        (bool(out["day0_at_high"]) and bool(out["limit_move"]))
        or (out["t1_gap"] is not None and out["t1_gap"] >= CHASE_T1_GAP)
        or (out["trail_21"] is not None and out["trail_21"] >= CHASE_TRAIL_21)
    )
    # Round AFTER the composite so the artifact stays small without any rounded
    # value ever deciding a threshold comparison.
    for k in ("day0_ret", "t1_gap", "trail_21"):
        out[k] = _round(out[k], 6)
    return out


def episode_telemetry(bdf: pd.DataFrame, bench: pd.Series | None,
                      price_of, sectors: dict | None = None) -> list[dict]:
    """Per-episode telemetry rows for ONE board definition's slice of the ledger.

    ``bdf`` must already be filtered to a single ``board_definition`` — this function
    does not filter, and pooling two definitions into one call would silently
    manufacture episodes that span a definition change.

    Admission metadata (rank / tier / lane / entry_status / narr_level) is read from
    the episode's OWN admission row — the ``(entry_date, ticker)`` key — never from a
    last-row-wins map over the whole frame, which attributes a repeat ticker's later
    appearance to its first episode.
    """
    from engine import track_scoring as _ts  # noqa: PLC0415 — off module load

    sectors = sectors or {}
    board_days: dict[str, set[str]] = {}
    admission: dict[tuple[str, str], dict] = {}
    for _i, brow in bdf.iterrows():
        tk = str(brow.get("ticker") or "")
        d0s = str(brow.get("date") or "")
        if not tk or not d0s:
            continue
        board_days.setdefault(d0s, set()).add(tk)
        # keep-FIRST, mirroring the store's own (date, ticker, definition) rule.
        admission.setdefault((d0s, tk), {
            "board_rank": _f(brow.get("board_rank")),
            "tier": (str(brow["tier"]) if pd.notna(brow.get("tier")) else None),
            "lane": (str(brow["lane"]) if pd.notna(brow.get("lane")) else None),
            "entry_status": (str(brow["entry_status"])
                             if pd.notna(brow.get("entry_status")) else None),
            "narr_level": (str(brow["narr_level"])
                           if pd.notna(brow.get("narr_level")) else None),
        })

    rows: list[dict] = []
    for ep in _ts.build_episodes(board_days):
        tk, d0s = ep["ticker"], ep["entry_date"]
        try:
            d0 = pd.Timestamp(d0s)
        except Exception as exc:  # noqa: BLE001 — a bad stored date is not fatal
            log.debug("cn_prophet_audit: unparseable board date %r (%s)", d0s, exc)
            continue
        meta = admission.get((d0s, tk), {})
        rec: dict[str, Any] = {
            "ticker": tk, "entry_date": d0s, "exit_date": ep.get("exit_date"),
            "sector": sectors.get(tk),
            "state": "no_price", "matured": False, "locked": False,
            "excess": None, "pnl": None, "held": None, "exit_reason": None,
            "day0_at_high": None, "day0_ret": None, "limit_move": None,
            "t1_gap": None, "trail_21": None, "chase_composite": False,
            "limit_band": limit_for(tk),
            **{k: meta.get(k) for k in
               ("board_rank", "tier", "lane", "entry_status", "narr_level")},
        }

        pdf = price_of(tk)
        if pdf is None or "close" not in pdf:
            rows.append(rec)
            continue
        closes = pd.to_numeric(pdf["close"], errors="coerce").dropna()
        if closes.empty:
            rows.append(rec)
            continue

        fill, locked, _pinned = _cst_t1_fill(pdf, d0)
        rec["locked"] = bool(locked)
        rec.update(chase_fields(pdf, closes, d0, tk, fill))

        after = closes.index[closes.index > d0]
        sc = None
        if fill is not None and len(after):
            # include_fill_bar: the CN fill is the T+1 open (or its (H+L)/2 proxy), so
            # that same session's close is already a legitimate day-one exit.
            sc = _ts.score_from_fill(closes, after[0], float(fill), HORIZON,
                                     bench_close=bench, include_fill_bar=True)
        if sc is None:
            rec["state"] = "awaiting_t1"
            rows.append(rec)
            continue

        if locked:
            rec["state"] = "locked_excluded"
        elif sc.get("matured"):
            rec["state"] = "matured"
            rec["matured"] = True
            # 6 dp on a PERCENT quantity: far below anything that could flip a
            # win/loss sign, and it keeps the artifact readable.
            rec["excess"] = _round(_f(sc.get("excess")), 6)
            rec["pnl"] = _round(_f(sc.get("pnl")), 6)
            rec["held"] = sc.get("held")
            rec["exit_reason"] = sc.get("exit_reason")
        else:
            rec["state"] = "inflight"
        rows.append(rec)
    return rows


def _cst_t1_fill(pdf: pd.DataFrame, d0: pd.Timestamp):
    """Indirection over ``china_standout_track._t1_fill`` so a test can patch either."""
    from engine import china_standout_track as _cst  # noqa: PLC0415

    return _cst._t1_fill(pdf, d0)  # noqa: SLF001 — the ledger's own fill convention


def _cohort_stats(recs: list[dict]) -> dict:
    """win/loss arithmetic over matured, excess-bearing episodes.

    A win is ``excess > 0`` with NO dead band — the same rule ``track_scoring.summarize``
    applies, for the same reason: a band that drops flats from the denominator is the
    least defensible knob on a track record.
    """
    vals = [r["excess"] for r in recs if r.get("matured") and r.get("excess") is not None]
    n = len(vals)
    losers = sum(1 for v in vals if v <= 0)
    return {
        "n": n,
        "n_winners": n - losers,
        "n_losers": losers,
        "win_rate": _rate(n - losers, n),
        "loser_rate": _rate(losers, n),
        "median_excess": _round(float(pd.Series(vals).median()), 4) if n else None,
    }


def _by_entry_status(recs: list[dict]) -> list[dict]:
    """win/loss split per admission ``entry_status``, newest-largest first."""
    buckets: dict[str, list[dict]] = {}
    for r in recs:
        if not (r.get("matured") and r.get("excess") is not None):
            continue
        buckets.setdefault(str(r.get("entry_status")), []).append(r)
    out = [{"entry_status": (None if k == "None" else k), **_cohort_stats(v)}
           for k, v in buckets.items()]
    out.sort(key=lambda d: (-d["n"], str(d["entry_status"])))
    return out


def _featured_vs_rest(recs: list[dict], definition: str) -> dict:
    """Running featured-vs-rest comparison, for the v2 shelf only.

    NULL until the shelf actually has matured rows on both sides — and a null here
    blocks nothing (CLAUDE.md §Epistemics). The note names the reason so the null is
    disclosed rather than hidden.
    """
    featured = [r for r in recs if str(r.get("lane")) == "featured"]
    rest = [r for r in recs if str(r.get("lane")) != "featured"]
    f_stats, r_stats = _cohort_stats(featured), _cohort_stats(rest)
    note = None
    if not f_stats["n"] and not r_stats["n"]:
        note = (f"no matured episodes on '{definition}' yet — the shelf is younger "
                f"than the {HORIZON}-session forced horizon")
    elif not r_stats["n"]:
        note = (f"'{definition}' board rows carry only lane='featured' in the ledger "
                "(the non-featured lanes are logged to the candidate store, not the "
                "board store) — no comparison leg exists")
    elif not f_stats["n"]:
        note = f"no matured lane='featured' episodes on '{definition}' yet"
    return {
        "featured": f_stats,
        "rest": r_stats,
        "excess_gap": (
            None if (f_stats["median_excess"] is None or r_stats["median_excess"] is None)
            else _round(f_stats["median_excess"] - r_stats["median_excess"], 4)
        ),
        "note": note,
    }


def loser_telemetry(board: pd.DataFrame, bench: pd.Series | None,
                    price_of, sectors: dict | None = None) -> dict:
    """Per-definition loser telemetry. Definitions are NEVER pooled.

    Returns ``{definitions: [ {board_definition, ...aggregates, episodes: [...] } ]}``,
    one block per stamp found in the store, ordered by first board date.
    """
    out: list[dict] = []
    if board is None or board.empty:
        return {"definitions": out}
    stamps = (board["board_definition"].map(norm_definition)
              if "board_definition" in board.columns
              else pd.Series("legacy", index=board.index))
    for definition in sorted(stamps.unique()):
        slice_ = board[stamps == definition]
        recs = episode_telemetry(slice_, bench, price_of, sectors)
        matured = [r for r in recs if r.get("matured") and r.get("excess") is not None]
        chase = [r for r in matured if r.get("chase_composite")]
        clean = [r for r in matured if not r.get("chase_composite")]
        head = _cohort_stats(matured)
        out.append({
            "board_definition": definition,
            "dates": sorted(slice_["date"].astype(str).unique().tolist()),
            "n_board_rows": len(slice_),
            "n_episodes": len(recs),
            "n_matured": head["n"],
            "n_winners": head["n_winners"],
            "n_losers": head["n_losers"],
            "win_rate": head["win_rate"],
            "loser_rate": head["loser_rate"],
            "median_excess": head["median_excess"],
            "n_locked_excluded": sum(1 for r in recs if r.get("locked")),
            "n_inflight": sum(1 for r in recs if r.get("state") == "inflight"),
            "n_awaiting_t1": sum(1 for r in recs if r.get("state") == "awaiting_t1"),
            "n_no_price": sum(1 for r in recs if r.get("state") == "no_price"),
            "chase": {
                "definition": (f"(day0_at_high AND limit_move) OR "
                               f"t1_gap>={CHASE_T1_GAP:.2f} OR "
                               f"trail_21>={CHASE_TRAIL_21:.2f}"),
                "n_flagged": len(chase),
                "share_of_matured": _rate(len(chase), head["n"]),
                **{f"chase_{k}": v for k, v in _cohort_stats(chase).items()},
                **{f"clean_{k}": v for k, v in _cohort_stats(clean).items()},
                "legs": {
                    "day0_at_high_and_limit": sum(
                        1 for r in matured
                        if bool(r.get("day0_at_high")) and bool(r.get("limit_move"))),
                    "t1_gap": sum(1 for r in matured
                                  if (r.get("t1_gap") or -1) >= CHASE_T1_GAP),
                    "trail_21": sum(1 for r in matured
                                    if (r.get("trail_21") or -1) >= CHASE_TRAIL_21),
                },
            },
            "by_entry_status": _by_entry_status(recs),
            "featured_vs_rest": _featured_vs_rest(recs, definition),
            "episodes": recs,
        })
    out.sort(key=lambda d: (d["dates"][0] if d["dates"] else ""))
    return {"definitions": out}


# ---------------------------------------------------------------------------
# 2. miss funnel
# ---------------------------------------------------------------------------
def _runner_universe() -> tuple[dict[str, pd.Series], dict]:
    """Every china_stocks close series with ≥ RUNNER_MIN_BARS bars.

    Reads ONLY the ``close`` column (``pd.read_parquet(path, columns=['close'])``) —
    the whole scan is the single largest thing this module does and the OHLC columns
    are dead weight for a trailing-return rank. Nothing is truncated silently: the
    counts of files scanned, short-history files skipped, and unreadable files are all
    returned and printed into the artifact.
    """
    d = config.data_dir() / RUNNER_GROUP
    stats = {"n_files": 0, "n_scanned": 0, "n_short_history": 0, "n_unreadable": 0,
             "min_bars": RUNNER_MIN_BARS}
    series: dict[str, pd.Series] = {}
    if not d.exists():
        return series, stats
    for p in sorted(d.glob("*.parquet")):
        stats["n_files"] += 1
        try:
            frame = pd.read_parquet(p, columns=["close"])
        except Exception:  # noqa: BLE001 — one bad file must not end the scan
            stats["n_unreadable"] += 1
            continue
        s = pd.to_numeric(frame["close"], errors="coerce").dropna()
        if len(s) < RUNNER_MIN_BARS:
            stats["n_short_history"] += 1
            continue
        if not isinstance(s.index, pd.DatetimeIndex):
            try:
                s.index = pd.to_datetime(s.index)
            except Exception:  # noqa: BLE001
                stats["n_unreadable"] += 1
                continue
        series[p.stem] = s.sort_index()
        stats["n_scanned"] += 1
    return series, stats


def _runners_for_date(series: dict[str, pd.Series], d: pd.Timestamp) -> list[tuple[str, float]]:
    """Top-N names by trailing-``RUNNER_LOOKBACK``-session return as of ``d``.

    A name must have PRINTED a bar on ``d`` to qualify. Reading a stale last close for
    a halted or delisted name would let a name that could not trade that session enter
    the runner list, which is exactly the kind of survivor-flavoured leak this whole
    audit exists to catch.
    """
    scored: list[tuple[str, float]] = []
    for tk, s in series.items():
        upto = s[s.index <= d]
        if len(upto) < RUNNER_LOOKBACK + 1 or upto.index[-1] != d:
            continue
        base = _f(upto.iloc[-(RUNNER_LOOKBACK + 1)])
        last = _f(upto.iloc[-1])
        if not base or last is None:
            continue
        scored.append((tk, last / base - 1.0))
    scored.sort(key=lambda kv: -kv[1])
    return scored[:RUNNER_TOP_N]


def miss_funnel() -> dict:
    """Rolling top-150 runners × the PIT lane the candidate ledger recorded that day.

    Coverage starts at ``candidates.parquet``'s birth and there is deliberately NO
    backfill: the lane a name would have been given on an earlier date can only be
    recovered by replaying ``gate()``, which is both too heavy for this lane and no
    longer point-in-time once replayed. ``coverage_start`` therefore ships in the
    artifact and every reader sees the window the numbers cover.
    """
    out: dict[str, Any] = {
        "available": False, "coverage_start": None, "coverage_dates": [],
        "top_n": RUNNER_TOP_N, "lookback_sessions": RUNNER_LOOKBACK,
        "universe": {}, "by_date": [], "pooled": None,
        "note": ("PIT lane as recorded in data/china_prophet_rank/candidates.parquet. "
                 "Never backfilled and gate() is never replayed — coverage starts at "
                 "the candidate store's birth."),
    }
    p = _candidates_path()
    if not p.exists():
        out["note"] = "candidate store absent — miss funnel unavailable"
        return out
    try:
        cand = pd.read_parquet(p, columns=["stamp_date", "ticker", "lane"])
    except Exception as exc:  # noqa: BLE001
        out["note"] = f"candidate store unreadable: {exc}"
        return out
    if cand.empty:
        out["note"] = "candidate store empty"
        return out

    dates = sorted(cand["stamp_date"].astype(str).unique().tolist())
    out["coverage_start"] = dates[0]
    out["coverage_dates"] = dates

    series, stats = _runner_universe()
    out["universe"] = stats
    if not series:
        out["note"] = "china_stocks universe empty — miss funnel unavailable"
        return out

    lane_by_key: dict[tuple[str, str], str] = {}
    for _i, row in cand.iterrows():
        key = (str(row["stamp_date"])[:10], str(row["ticker"]))
        lane_by_key.setdefault(key, str(row["lane"]) if pd.notna(row["lane"]) else FUNNEL_ABSENT)

    pooled: dict[str, int] = {lane: 0 for lane in FUNNEL_LANES}
    n_total = 0
    for ds in dates:
        try:
            d = pd.Timestamp(ds)
        except Exception as exc:  # noqa: BLE001 — one bad key never ends the sweep
            log.debug("cn_prophet_audit: unparseable candidate date %r (%s)", ds, exc)
            continue
        runners = _runners_for_date(series, d)
        counts: dict[str, int] = {lane: 0 for lane in FUNNEL_LANES}
        missed: list[dict] = []
        for tk, ret in runners:
            lane = lane_by_key.get((ds, tk), FUNNEL_ABSENT)
            if lane not in counts:
                counts[lane] = 0
                pooled.setdefault(lane, 0)
            counts[lane] += 1
            pooled[lane] += 1
            n_total += 1
            if lane != "featured":
                missed.append({"ticker": tk, "trail_63": _round(ret, 4), "lane": lane})
        missed.sort(key=lambda r: -(r["trail_63"] or 0.0))
        out["by_date"].append({
            "date": ds,
            "n_runners": len(runners),
            "lanes": counts,
            "top_missed": missed[:20],
        })
    out["pooled"] = {
        "n_runner_sessions": n_total,
        "lanes": pooled,
        "shares": {k: _rate(v, n_total) for k, v in pooled.items()},
    }
    out["available"] = bool(out["by_date"])
    return out


# ---------------------------------------------------------------------------
# 3. write path
# ---------------------------------------------------------------------------
def _forward_log_rows(definitions: list[dict], asof: str) -> list[dict]:
    """One headline row per (run date × board_definition) for the append-only log."""
    rows = []
    for blk in definitions:
        chase = blk.get("chase") or {}
        rows.append({
            "date": str(asof),
            "board_definition": blk["board_definition"],
            "n_episodes": int(blk["n_episodes"]),
            "n_matured": int(blk["n_matured"]),
            "n_winners": int(blk["n_winners"]),
            "n_losers": int(blk["n_losers"]),
            "win_rate": blk["win_rate"],
            "loser_rate": blk["loser_rate"],
            "median_excess": blk["median_excess"],
            "n_chase_flagged": int(chase.get("n_flagged") or 0),
            "chase_share_of_matured": chase.get("share_of_matured"),
            "chase_n_losers": int(chase.get("chase_n_losers") or 0),
            "chase_n_winners": int(chase.get("chase_n_winners") or 0),
            "chase_loser_rate": chase.get("chase_loser_rate"),
            "clean_loser_rate": chase.get("clean_loser_rate"),
        })
    return rows


def append_forward_log(rows: list[dict]) -> int:
    """Append-only, keep-FIRST per ``(date, board_definition)``. Never raises.

    Keep-first is the same leak-free rule the board store uses: once a night's headline
    is logged it is never rewritten, so a re-run cannot quietly move a number a reader
    already saw. Returns the row count after the merge, or 0 on failure.
    """
    if not rows:
        return 0
    try:
        p = forward_log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        new = pd.DataFrame(rows)
        if p.exists():
            prior = pd.read_parquet(p)
            cols = list(dict.fromkeys([*new.columns, *prior.columns]))
            combined = pd.concat(
                [prior.reindex(columns=cols), new.reindex(columns=cols)],
                ignore_index=True,
            ).drop_duplicates(subset=["date", "board_definition"], keep="first")
        else:
            combined = new
        combined.to_parquet(p, index=False)
        return len(combined)
    except Exception as exc:  # noqa: BLE001 — telemetry write is never fatal
        log.warning("cn_prophet_audit: forward-log append failed: %s", exc)
        print("::warning title=cn-prophet-audit-forward-log::"
              f"cn_prophet_audit could not append its forward log ({exc}) — the "
              "nightly headline row for this date is missing from "
              "data/cn_prophet_audit/forward_log.parquet.", flush=True)
        return 0


def run(asof: str | None = None, lane: str | None = None) -> dict:
    """Nightly entry point. Best-effort, NEVER raises, ZERO authority.

    Gates (identical to ``china_standout_track.append_board`` — one discipline, not two):
      * asia-lane only. ``lane=None`` is the legacy call convention and is allowed;
        any other lane refuses without writing (render lanes discard data/ writes).
      * a mid-session partial China panel refuses via ``session_status``.

    Returns a small status dict; the full artifact lands in
    ``data/cn_prophet_audit/latest.json`` and the headline row in
    ``forward_log.parquet``.
    """
    t0 = time.perf_counter()
    try:
        from engine import china_standout_track as _cst  # noqa: PLC0415

        if lane is not None and lane != "asia":
            log.info("cn_prophet_audit: skipped (lane=%s, not asia)", lane)
            return {"written": False, "reason": f"lane={lane} (not asia)",
                    "elapsed_seconds": round(time.perf_counter() - t0, 2)}
        sess = _cst.session_status(asof)
        if sess.get("partial_session"):
            log.warning("cn_prophet_audit: REFUSING write — %s", sess.get("reason"))
            return {"written": False, "reason": str(sess.get("reason")),
                    "elapsed_seconds": round(time.perf_counter() - t0, 2)}

        board_path = _cst._store_path()  # noqa: SLF001 — read-only path accessor
        if not board_path.exists():
            return {"written": False, "reason": "board store absent",
                    "elapsed_seconds": round(time.perf_counter() - t0, 2)}
        board = pd.read_parquet(board_path)

        bench = _cst._bench_close()  # noqa: SLF001 — the ledger's own benchmark
        if bench is None:
            print("::warning title=cn-prophet-audit-benchmark::"
                  "cn_prophet_audit: CSI300 benchmark 510300.SS is unavailable — every "
                  "excess-based aggregate in data/cn_prophet_audit/latest.json is null "
                  "for this run.", flush=True)
            log.warning("cn_prophet_audit: bench 510300.SS unavailable")

        memo: dict[str, pd.DataFrame | None] = {}

        def price_of(tk: str):
            if tk not in memo:
                memo[tk] = _cst._price_frame(tk)  # noqa: SLF001
            return memo[tk]

        losers = loser_telemetry(board, bench, price_of, _sector_lookup())
        memo.clear()
        funnel = miss_funnel()

        elapsed = round(time.perf_counter() - t0, 2)
        doc = {
            "schema": SCHEMA,
            "tier": TIER,
            "authority": "none — ops telemetry; never scores, ranks, gates or sizes",
            "as_of": str(asof) if asof else None,
            "generated_utc": pd.Timestamp.now("UTC").isoformat(),
            "horizon_sessions": HORIZON,
            "metric": METRIC,
            "benchmark": "510300.SS",
            "benchmark_available": bench is not None,
            "coverage_start": funnel.get("coverage_start"),
            "loser_telemetry": losers,
            "miss_funnel": funnel,
            "elapsed_seconds": elapsed,
        }
        written = _write_latest(doc)
        n_log = append_forward_log(
            _forward_log_rows(losers["definitions"], str(asof or ""))
        ) if asof else 0
        return {
            "written": bool(written),
            "elapsed_seconds": elapsed,
            "n_definitions": len(losers["definitions"]),
            "forward_log_rows": n_log,
        }
    except Exception as exc:  # telemetry NEVER breaks the nightly board
        log.warning("cn_prophet_audit run failed: %s", exc, exc_info=True)
        print("::warning title=cn-prophet-audit::"
              f"cn_prophet_audit failed ({exc}) — loser/miss telemetry is missing for "
              "this run. The China board itself is unaffected (this module has no "
              "authority over scoring, lanes or ranks).", flush=True)
        return {"written": False, "reason": f"error: {exc}",
                "elapsed_seconds": round(time.perf_counter() - t0, 2)}


def _write_latest(doc: dict) -> bool:
    """Atomic-ish write of latest.json. Never raises."""
    try:
        from engine import track_ledger as _tl  # noqa: PLC0415 — pyify only

        p = latest_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_tl.pyify(doc), ensure_ascii=False), encoding="utf-8")
        tmp.replace(p)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("cn_prophet_audit: latest.json write failed: %s", exc)
        print("::warning title=cn-prophet-audit-write::"
              f"cn_prophet_audit could not write data/cn_prophet_audit/latest.json "
              f"({exc}) — loser/miss telemetry is missing for this run.", flush=True)
        return False
