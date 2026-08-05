"""China Prophet loser + miss telemetry — OPS-TELEMETRY tier, **ZERO AUTHORITY**.

WHAT THIS IS
------------
A nightly read-only forensic pass over the board ledger that answers three questions the
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
  3. **Is the SCORE ITSELF any good — on every dimension, not just the one that is
     easy to count?** ``rank_effectiveness`` grades the ordering nightly: a rank-IC
     ladder across every realized outcome the ledger carries, top-6 oracle regret per
     admission date, a risk/time profile per score tercile, and a per-component
     attribution. The multi-metric shape is deliberate and is the whole point (see
     §RANK EFFECTIVENESS below): a shortlist can be *right* in a way an immediate-win
     count cannot see.

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

RANK EFFECTIVENESS — how the score grades itself
------------------------------------------------
A track record that counts only "did the pick go up within 10 sessions" will condemn a
ranker that is in fact doing its job on a dimension that record cannot see. A top-ranked
name can carry a shallower drawdown, a bigger 21/63-session excursion, or a slower
path to its high than a mid-ranked one, and a single immediate-win number scores all of
that as a miss. So the ordering is graded on EVERY outcome the ledger already carries,
and each is published whether it flatters the score or not:

  * **The rank-IC ladder** — Spearman IC of the ordering against ``excess`` at the forced
    H=10 verdict (the incumbent number), the MAE proxy (worst forward close vs the fill),
    the maturation spine's ``fwd_mfe_{5,10,21,63}``, the catastrophic flag (abs P&L
    ≤ −15%), the rotational CLEAN_LIFTOFF partition, and post-cushion breach.
  * **Top-6 oracle regret** — per admission date, what the top-6-by-score actually earned
    against what the best-6-in-hindsight from the SAME date's pool earned. This is the
    only number that asks "did we highlight the best of the shortlist we ourselves drew",
    which is a different question from "did the shortlist go up".
  * **Risk/time profile by score tercile** — loser rate, median excess, median MAE,
    catastrophic rate, CLEAN_LIFTOFF share, median 21-session MFE, and median day-of-max.
    "Maybe the top-ranked picks are lower-risk, or slower but bigger" stops being a
    speculation here and becomes a measured row.
  * **Per-component attribution** — each stored score leg gets its own IC, so which leg
    earns its weight is visible nightly rather than assumed (glass-box law).

ORIENTATION (stated once, because a sign error here inverts every reading)
    Every IC is emitted in ONE canonical orientation: the ordering key is built so that
    a LOWER key is the board's OWN claim of a better pick. ``board_rank`` is used as-is
    (rank 1 = best); ``prophet_score`` and every component are NEGATED (higher score =
    better pick). So for an outcome where higher is better — excess, MFE, CLEAN_LIFTOFF —
    a well-ordered board scores a NEGATIVE IC, and a POSITIVE IC is the V1 failure
    (measured legacy baseline: board_rank IC vs excess = **+0.073**, anti-predictive).
    For a COST outcome — catastrophic, post-cushion breach — the signs flip, so every
    metric ships its own ``good_sign`` and a ``wrong_sign`` boolean rather than leaving
    the reader to work it out. IC method is the per-date Spearman then the MEAN across
    dates, gated at 5 distinct ordering values per date — the same convention
    ``china_standout_track.grade`` publishes ``board_rank_ic`` with, and the one that
    reproduces the audited +0.073. The pooled cross-date IC ships alongside it.

BUDGET
------
Render budget is law. The whole pass is designed to stay well inside the ~90s allotted
to it on the asia lane: per-ticker price frames are memoised across every episode, the
runner universe is scanned with ``columns=['close']`` only, and no per-name recompute of
any production signal happens at all. ``rank_effectiveness`` adds NO store reads at all —
it is pure arithmetic over the episode records section 1 already built, and carries its
own ``elapsed_seconds``. Measured ``elapsed_seconds`` ships in the artifact so a
regression is visible the night it lands.
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

# ── rank effectiveness ─────────────────────────────────────────────────────────
# Floors, not knobs. RANK_EFF_MIN_ROWS mirrors china_standout_track._MIN_GRADED (8) —
# the same "publish nothing below this" line the CN ledger already draws.
RANK_EFF_MIN_ROWS = 8
# Distinct ordering values a single date needs before it contributes an IC. Below 5 a
# per-date Spearman is arithmetic on noise; this is grade()'s own gate.
RANK_EFF_MIN_PER_DATE = 5
ORACLE_K = 6                      # the shortlist depth the oracle regret judges
# Absolute (NOT benchmark-relative) P&L in PERCENT. track_scoring.score_from_fill returns
# pnl/excess/mfe/mae already multiplied by 100, and this threshold is compared to that
# scale — masterplan §8 M5 counts "≤ −15% abs" and reproduces 47/407 on the legacy era.
CATASTROPHIC_PNL_PCT = -15.0
# An anti-predictive ordering is only alarmed once the sample can carry the claim.
WRONG_SIGN_MIN_EPISODES = 60
N_TERCILES = 3
CLEAN_LIFTOFF = "CLEAN_LIFTOFF"   # engine.grading.TerminalState.CLEAN_LIFTOFF

# Stored per-component score legs (china_standout_track.append_board).
# ``prophet_theme_timing`` is the R2 leg from china_board_rank's V3 SCORE_WEIGHTS: it is
# listed here so the attribution lights up automatically the night append_board starts
# storing it, and reports a disclosed null until then. A missing column is a printed
# null, never a silent gap and never a blocker (CLAUDE.md §Epistemics).
PROPHET_COMPONENT_COLS = (
    "prophet_signal",
    "prophet_entry",
    "prophet_runway",
    "prophet_bottom_quality",
    "prophet_reversal_member",
    "prophet_theme_timing",
)

# Maturation-spine outcome columns carried on the board row itself. These are written
# back by china_standout_track.grade(); build_china_library calls THIS module BEFORE
# grade(), so the spine a given night reads is last night's write-back and the newest
# rows are legitimately null. That staleness is reported (``spine_source``,
# ``n_spine_null``) rather than papered over.
SPINE_MFE_COLS = ("fwd_mfe_5", "fwd_mfe_10", "fwd_mfe_21", "fwd_mfe_63")
SPINE_STATE_COLS = ("terminal_state_clean8_21", "post_cushion_breach")

# The outcome ladder. ``higher_better`` states which direction of the OUTCOME is good;
# combined with the canonical low-key-is-better ordering it fixes the expected IC sign.
RANK_EFF_METRICS: tuple[tuple[str, bool, str], ...] = (
    ("excess_h10", True,
     "CSI300-relative excess at the forced H=10 verdict — the incumbent number"),
    ("mae_proxy_10", True,
     ("worst forward close vs the T+1 fill inside H=10 (score_from_fill's own 'mae'); "
      "less negative is better, so it reads as a higher-is-better outcome")),
    ("fwd_mfe_5", True, "max favourable excursion, 5 sessions (ledger spine)"),
    ("fwd_mfe_10", True, "max favourable excursion, 10 sessions (ledger spine)"),
    ("fwd_mfe_21", True, "max favourable excursion, 21 sessions — the longer-duration lens"),
    ("fwd_mfe_63", True, "max favourable excursion, 63 sessions — the longest lens"),
    ("catastrophic", False,
     (f"1 when absolute P&L <= {CATASTROPHIC_PNL_PCT:.0f}% (masterplan §8 M5) — a COST, "
      "so the good sign is inverted")),
    ("clean_liftoff_21", True,
     "1 when terminal_state_clean8_21 == CLEAN_LIFTOFF (rotational partition)"),
    ("post_cushion_breach", False,
     "1 when a cushioned position fell back through its fill — a COST, sign inverted"),
)

ORDER_SOURCE_RANK = "board_rank"
ORDER_SOURCE_SCORE = "prophet_score"


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


_NULLISH = frozenset({"", "nan", "none", "nat", "<na>"})


def _tri_bool(value: Any) -> bool | None:
    """True / False / None from a nullable stored bool — NEVER collapsing None to False.

    ``post_cushion_breach`` is genuinely three-valued: True (cushioned then breached),
    False (cushioned and held), None (never cushioned at all — the question does not
    apply). Round-tripped through parquet the null arrives as ``None`` on an object
    column or as ``NaN`` on a float one, and ``bool(NaN)`` is True, which would score
    every never-cushioned episode as a breach.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip().lower()
    if text in _NULLISH:
        return None
    if text in ("true", "1", "1.0"):
        return True
    if text in ("false", "0", "0.0"):
        return False
    return None


def _text_or_none(value: Any) -> str | None:
    """A stored string cell, with every null spelling normalised to ``None``."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return None if text.lower() in _NULLISH else text


def _day_of_max(closes: pd.Series, fill_date: Any, horizon: int) -> int | None:
    """1-based session of the highest close inside the H-session window from the fill.

    Day 1 IS the T+1 fill bar, matching ``score_from_fill(..., include_fill_bar=True)``
    — the CN fill is the T+1 open (or its (H+L)/2 proxy), so that session's own close is
    already a legitimate exit and must be a candidate for the max. This deliberately does
    NOT reuse ``china_standout_track._cn_fwd_mfe``'s window (T+2 .. T+1+H), which excludes
    the fill bar: mixing the two would put day-of-max and MFE on different clocks.

    None until the full window has printed — a truncated window would report an early
    day-of-max for the arithmetic reason that no later bar exists yet.
    """
    try:
        fwd = closes[closes.index >= fill_date].iloc[:horizon]
    except Exception:  # noqa: BLE001 — a malformed index is a null, not a crash
        return None
    if len(fwd) < horizon:
        return None
    vals = pd.to_numeric(fwd, errors="coerce")
    if not int(vals.notna().sum()):
        return None
    return int(vals.argmax()) + 1


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

    Admission metadata (rank / tier / lane / entry_status / narr_level, plus the stored
    ``prophet_*`` score and its component legs) is read from the episode's OWN admission
    row — the ``(entry_date, ticker)`` key — never from a last-row-wins map over the
    whole frame, which attributes a repeat ticker's later appearance to its first
    episode. The maturation-spine outcome columns ride along the same key so the rank
    grader in section 3 needs no second pass over the board frame.
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
            # the score the board ordered by, and the legs that built it (v2+/v3 rows;
            # legacy rows carry board_rank only — grade what exists, null what does not)
            "prophet_score": _f(brow.get("prophet_score")),
            **{c: _f(brow.get(c)) for c in PROPHET_COMPONENT_COLS},
            # maturation spine, as written back by china_standout_track.grade()
            **{c: _f(brow.get(c)) for c in SPINE_MFE_COLS},
            "terminal_state_clean8_21": _text_or_none(brow.get("terminal_state_clean8_21")),
            "post_cushion_breach": _tri_bool(brow.get("post_cushion_breach")),
        })

    meta_keys = (
        "board_rank", "tier", "lane", "entry_status", "narr_level", "prophet_score",
        *PROPHET_COMPONENT_COLS, *SPINE_MFE_COLS, *SPINE_STATE_COLS,
    )

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
            # section-3 inputs: the worst forward close vs the fill, and how long the
            # position took to reach its high. Null until the window matures.
            "mae_proxy_10": None, "day_of_max_10": None, "day_of_max_21": None,
            **{k: meta.get(k) for k in meta_keys},
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
            # MAE proxy = the scorer's OWN 'mae' (worst close in the same H=10 forced
            # window, measured from the same T+1 fill). Taking it from score_from_fill
            # rather than re-walking the close path is deliberate: a second walk would
            # be a second, incomparable drawdown convention living beside the first.
            rec["mae_proxy_10"] = _round(_f(sc.get("mae")), 6)
            rec["day_of_max_10"] = _day_of_max(closes, after[0], HORIZON)
            rec["day_of_max_21"] = _day_of_max(closes, after[0], 21)
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
# 3. rank effectiveness — the score grades itself
#
# Read §RANK EFFECTIVENESS in the module docstring before touching anything here; the
# orientation convention is stated there once and every function below assumes it.
# ZERO AUTHORITY, exactly like sections 1-2: nothing here scores, ranks, gates or sizes
# anything. It reports on an ordering that was already fixed months ago and cannot
# change it.
# ---------------------------------------------------------------------------
def _order_key(rec: dict, source: str) -> float | None:
    """The canonical ordering key — LOWER = the board's own claim of a better pick.

    ``board_rank`` is already oriented that way (rank 1 = best). ``prophet_score`` and
    every component leg run the other way (higher = better), so they are NEGATED here.
    Negating in ONE place is the point: every IC downstream then shares a single sign
    convention and a metric's ``good_sign`` alone decides how to read it.
    """
    if source == ORDER_SOURCE_RANK:
        return _f(rec.get("board_rank"))
    value = _f(rec.get(source))
    return None if value is None else -value


def _natural_value(source: str, key: float) -> float:
    """Undo ``_order_key``'s negation, for reporting a range in the source's own units."""
    return key if source == ORDER_SOURCE_RANK else -key


def _outcome(rec: dict, metric: str) -> float | None:
    """One realized outcome for one episode, or None when the ledger cannot answer.

    A null is a null: it drops that episode from THAT metric's IC and from nothing else.
    No metric is ever imputed, and no null blocks another metric from being published.
    """
    if metric == "excess_h10":
        return _f(rec.get("excess"))
    if metric == "mae_proxy_10":
        return _f(rec.get("mae_proxy_10"))
    if metric in SPINE_MFE_COLS:
        return _f(rec.get(metric))
    if metric == "catastrophic":
        pnl = _f(rec.get("pnl"))
        return None if pnl is None else float(pnl <= CATASTROPHIC_PNL_PCT)
    if metric == "clean_liftoff_21":
        state = _text_or_none(rec.get("terminal_state_clean8_21"))
        return None if state is None else float(state == CLEAN_LIFTOFF)
    if metric == "post_cushion_breach":
        flag = _tri_bool(rec.get("post_cushion_breach"))
        return None if flag is None else float(flag)
    return None


def _spearman_ic(triples: list[tuple[str, float, float]]) -> dict:
    """Per-date Spearman IC, then the MEAN across dates. Pooled IC alongside it.

    ``triples`` = ``(admission_date, ordering_key, outcome)``.

    Per-date-then-mean is not a stylistic choice. Pooling ranks across dates folds the
    market's own day-to-day return into the correlation: on a day the whole board rose,
    every name looks like a win regardless of where the score put it. Averaging
    within-date ICs asks the only question the score is responsible for — given the
    names admitted THAT day, did it put the better ones first. It is also the convention
    ``china_standout_track.grade`` already publishes ``board_rank_ic`` with, and the one
    that reproduces the audited legacy +0.073.

    A date contributes only with ≥5 distinct ordering values and ≥2 distinct outcomes;
    below either, the correlation is undefined or is arithmetic on noise. The pooled
    figure ships too, so a reader can see when the two disagree.
    """
    out: dict[str, Any] = {
        "ic": None, "n": len(triples), "n_dates": 0, "pooled_ic": None, "note": None,
    }
    if len(triples) < RANK_EFF_MIN_ROWS:
        out["note"] = (f"n={len(triples)} below the {RANK_EFF_MIN_ROWS}-row floor — "
                       "accruing, not absent")
        return out
    frame = pd.DataFrame(triples, columns=["date", "key", "outcome"])
    # A constant column has no rank order, so its correlation is undefined — check
    # before asking rather than after, or scipy answers NaN and warns on every leg that
    # the ledger happens to store as a single value (prophet_reversal_member today).
    if frame["key"].nunique() < 2 or frame["outcome"].nunique() < 2:
        out["note"] = ("the ordering key or the outcome is constant across all "
                       f"{len(triples)} episodes — correlation undefined, which is a "
                       "fact about the sample rather than a missing number")
        return out
    pooled = frame["key"].corr(frame["outcome"], method="spearman")
    out["pooled_ic"] = _round(float(pooled), 4) if pd.notna(pooled) else None

    ics: list[float] = []
    for _d, sub in frame.groupby("date"):
        if sub["key"].nunique() < RANK_EFF_MIN_PER_DATE or sub["outcome"].nunique() < 2:
            continue
        corr = sub["key"].corr(sub["outcome"], method="spearman")
        if pd.notna(corr):
            ics.append(float(corr))
    out["n_dates"] = len(ics)
    if ics:
        out["ic"] = _round(float(pd.Series(ics).mean()), 4)
    else:
        out["note"] = (f"no admission date carried {RANK_EFF_MIN_PER_DATE} distinct "
                       "ordering values AND 2 distinct outcomes — per-date IC undefined; "
                       "the pooled figure is still printed")
    return out


def _ic_ladder(recs: list[dict], source: str) -> dict:
    """The full outcome ladder for ONE ordering source on ONE definition's episodes."""
    ladder: dict[str, Any] = {}
    for metric, higher_better, metric_note in RANK_EFF_METRICS:
        triples: list[tuple[str, float, float]] = []
        for r in recs:
            key = _order_key(r, source)
            value = _outcome(r, metric)
            if key is None or value is None:
                continue
            triples.append((str(r.get("entry_date")), key, value))
        cell = _spearman_ic(triples)
        # A LOWER key is the board's better pick, so an outcome that is better when
        # HIGHER must correlate NEGATIVELY with the key on a well-ordered board.
        cell["good_sign"] = "negative" if higher_better else "positive"
        cell["higher_outcome_is_better"] = bool(higher_better)
        cell["metric_note"] = metric_note
        ic = cell["ic"]
        cell["wrong_sign"] = (
            None if ic is None else bool(ic > 0 if higher_better else ic < 0)
        )
        ladder[metric] = cell
    return ladder


def _mid(values: list[float | None], nd: int = 4) -> float | None:
    """Median over the non-null members, or None when there are none."""
    clean = [v for v in values if v is not None]
    return _round(float(pd.Series(clean).median()), nd) if clean else None


def _oracle_regret(recs: list[dict], source: str) -> dict:
    """Top-K oracle regret per admission date — "did we highlight the best of OUR list".

    For each admission date with at least ``ORACLE_K`` matured, excess-bearing episodes:
    the mean excess of the K the score put first, against the mean excess of the K that
    actually did best from the SAME date's pool. ``regret = oracle − achieved`` (never
    negative by construction) and ``capture@K`` is how many of the hindsight-best K the
    score actually named.

    DEGENERACY IS REPORTED, NOT HIDDEN. When a date's pool is exactly K, the top-K by
    score and the top-K by hindsight are the same K names: regret is 0 and capture is
    1.0 for the arithmetic reason that no selection was possible. Those dates would drag
    the rolling mean toward a flattering zero, so the ``*_with_choice`` pair — computed
    over pools strictly larger than K — ships beside the headline and the degenerate
    count is printed.
    """
    out: dict[str, Any] = {
        "k": ORACLE_K, "n_dates": 0, "n_dates_with_choice": 0, "n_dates_degenerate": 0,
        "regret6": None, "capture6": None,
        "regret6_with_choice": None, "capture6_with_choice": None,
        "by_date": [], "note": None,
    }
    pools: dict[str, list[tuple[float, float, str]]] = {}
    for r in recs:
        key = _order_key(r, source)
        excess = _f(r.get("excess"))
        if key is None or excess is None:
            continue
        pools.setdefault(str(r.get("entry_date")), []).append(
            (key, excess, str(r.get("ticker")))
        )

    rows: list[dict] = []
    for date_s in sorted(pools):
        pool = pools[date_s]
        if len(pool) < ORACLE_K:
            continue
        # Ties broken on ticker so the same pool always yields the same K names.
        by_score = sorted(pool, key=lambda t: (t[0], t[2]))[:ORACLE_K]
        by_real = sorted(pool, key=lambda t: (-t[1], t[2]))[:ORACLE_K]
        achieved = sum(t[1] for t in by_score) / ORACLE_K
        oracle = sum(t[1] for t in by_real) / ORACLE_K
        captured = len({t[2] for t in by_score} & {t[2] for t in by_real})
        rows.append({
            "date": date_s,
            "n_pool": len(pool),
            "has_choice": bool(len(pool) > ORACLE_K),
            "achieved_mean_excess": _round(achieved, 4),
            "oracle_mean_excess": _round(oracle, 4),
            "regret": _round(oracle - achieved, 4),
            "capture": _round(captured / ORACLE_K, 4),
        })
    if not rows:
        out["note"] = (f"no admission date has {ORACLE_K} matured excess-bearing "
                       "episodes yet — accruing")
        return out

    chosen = [r for r in rows if r["has_choice"]]
    out["by_date"] = rows
    out["n_dates"] = len(rows)
    out["n_dates_with_choice"] = len(chosen)
    out["n_dates_degenerate"] = len(rows) - len(chosen)
    out["regret6"] = _round(sum(r["regret"] for r in rows) / len(rows), 4)
    out["capture6"] = _round(sum(r["capture"] for r in rows) / len(rows), 4)
    if chosen:
        out["regret6_with_choice"] = _round(
            sum(r["regret"] for r in chosen) / len(chosen), 4)
        out["capture6_with_choice"] = _round(
            sum(r["capture"] for r in chosen) / len(chosen), 4)
    if out["n_dates_degenerate"]:
        out["note"] = (f"{out['n_dates_degenerate']} of {len(rows)} dates had a pool of "
                       f"exactly {ORACLE_K} — no selection was possible, so their regret "
                       "is 0 and capture 1.0 by construction; read the *_with_choice pair")
    return out


def _tercile_profile(recs: list[dict], source: str) -> dict:
    """Risk + time-to-payoff profile per ordering tercile — the longer-duration lens.

    The operator's standing caution is that a top-ranked pick may be *better* in a way an
    immediate-win count cannot see: lower risk, or a bigger move that takes longer to
    arrive. This is where that stops being a hypothesis. Each tercile reports its loser
    rate AND its median drawdown, catastrophic rate, CLEAN_LIFTOFF share, 21-session MFE
    and median day-of-max, so "T1 wins less often but bleeds less and pays later and
    bigger" is a readable row rather than an argument.

    The split is positional over a TOTAL order — sorted on ``(key, entry_date, ticker)``
    and cut at ``pos * 3 // n``. Quantile cuts on this data are not reproducible: legacy
    ordering keys are integer ranks 1-60 repeated across 18 dates, so the bin edges land
    on massive ties and a tie-handling change silently moves episodes between buckets.
    T1 is the best-ordered third.
    """
    graded: list[tuple[float, str, str, dict]] = []
    for r in recs:
        key = _order_key(r, source)
        if key is None or _f(r.get("excess")) is None:
            continue
        graded.append((key, str(r.get("entry_date")), str(r.get("ticker")), r))

    out: dict[str, Any] = {
        "n": len(graded), "n_terciles": N_TERCILES, "terciles": [], "note": None,
        "split": "positional over (ordering_key, entry_date, ticker); T1 = best-ordered",
    }
    if len(graded) < RANK_EFF_MIN_ROWS:
        out["note"] = (f"n={len(graded)} below the {RANK_EFF_MIN_ROWS}-row floor — "
                       "accruing, not absent")
        return out

    graded.sort(key=lambda t: (t[0], t[1], t[2]))
    n = len(graded)
    buckets: list[list[tuple[float, str, str, dict]]] = [[] for _ in range(N_TERCILES)]
    for pos, item in enumerate(graded):
        buckets[min(N_TERCILES - 1, pos * N_TERCILES // n)].append(item)

    for i, bucket in enumerate(buckets):
        rows = [item[3] for item in bucket]
        keys = [item[0] for item in bucket]
        excess = [_f(r.get("excess")) for r in rows]
        losers = sum(1 for v in excess if v is not None and v <= 0)
        pnls = [_f(r.get("pnl")) for r in rows if _f(r.get("pnl")) is not None]
        states = [_text_or_none(r.get("terminal_state_clean8_21")) for r in rows]
        graded_states = [s for s in states if s is not None]
        breaches = [_tri_bool(r.get("post_cushion_breach")) for r in rows]
        graded_breach = [b for b in breaches if b is not None]
        natural = sorted(_natural_value(source, k) for k in keys)
        out["terciles"].append({
            "tercile": f"T{i + 1}",
            "n": len(rows),
            "ordering_source": source,
            "ordering_value_range": [_round(natural[0], 4), _round(natural[-1], 4)],
            # the incumbent lens
            "loser_rate": _rate(losers, len(rows)),
            "median_excess": _mid(excess),
            # the risk lens — is the top third simply safer?
            "median_mae_proxy_10": _mid([_f(r.get("mae_proxy_10")) for r in rows]),
            "catastrophic_rate": _rate(
                sum(1 for p in pnls if p <= CATASTROPHIC_PNL_PCT), len(pnls)),
            "n_pnl_graded": len(pnls),
            # the duration lens — does the top third pay later, and bigger?
            "clean_liftoff_share": _rate(
                sum(1 for s in graded_states if s == CLEAN_LIFTOFF), len(graded_states)),
            "n_terminal_graded": len(graded_states),
            "post_cushion_breach_rate": _rate(
                sum(1 for b in graded_breach if b), len(graded_breach)),
            "n_breach_graded": len(graded_breach),
            "median_fwd_mfe_21": _mid([_f(r.get("fwd_mfe_21")) for r in rows], 6),
            "median_fwd_mfe_63": _mid([_f(r.get("fwd_mfe_63")) for r in rows], 6),
            "median_day_of_max_10": _mid([_f(r.get("day_of_max_10")) for r in rows], 2),
            "median_day_of_max_21": _mid([_f(r.get("day_of_max_21")) for r in rows], 2),
        })
    return out


def _component_attribution(recs: list[dict]) -> dict:
    """Per-leg IC — which component of the score actually earns its weight (glass-box).

    Every leg in ``PROPHET_COMPONENT_COLS`` is graded against ``excess_h10`` and against
    ``fwd_mfe_21``, in the same low-key-is-better orientation as the score itself (the
    legs run higher-is-better, so ``_order_key`` negates them). Two disclosed nulls are
    possible and both are printed rather than dropped:

      * the column is absent from the ledger entirely (legacy rows carry no components,
        and ``prophet_theme_timing`` is not stored by ``append_board`` yet), and
      * the column is present but CONSTANT across the sample, which makes its IC
        undefined — a real finding about the leg, not a missing number.
    """
    out: dict[str, Any] = {}
    for col in PROPHET_COMPONENT_COLS:
        values = [_f(r.get(col)) for r in recs]
        present = [v for v in values if v is not None]
        cell: dict[str, Any] = {
            "available": bool(present), "n": len(present),
            "n_distinct_values": len({round(v, 6) for v in present}),
            "ic": {},
            "note": None,
        }
        if not present:
            cell["note"] = (f"'{col}' is null on every matured episode of this "
                            "definition — the ledger does not store it (yet)")
            out[col] = cell
            continue
        if cell["n_distinct_values"] < 2:
            cell["note"] = (f"'{col}' is constant ({present[0]}) across all "
                            f"{len(present)} matured episodes — its IC is undefined, "
                            "which is a fact about the leg, not a missing number")
        for metric in ("excess_h10", "fwd_mfe_21"):
            triples = []
            for r in recs:
                key = _order_key(r, col)
                value = _outcome(r, metric)
                if key is None or value is None:
                    continue
                triples.append((str(r.get("entry_date")), key, value))
            entry = _spearman_ic(triples)
            entry["good_sign"] = "negative"   # both metrics are higher-is-better
            ic = entry["ic"]
            entry["wrong_sign"] = None if ic is None else bool(ic > 0)
            cell["ic"][metric] = entry
        out[col] = cell
    return out


def _rank_eff_block(blk: dict) -> dict:
    """The rank-effectiveness block for ONE board definition. Definitions never pool."""
    episodes = blk.get("episodes") or []
    matured = [r for r in episodes if r.get("matured")]
    with_excess = [r for r in matured if _f(r.get("excess")) is not None]
    # Two different dates, and conflating them would misreport an era's life: the era's
    # last ADMISSION says whether it is still running, while its last MATURED admission
    # is only as recent as the forced horizon allows.
    all_dates = sorted({str(r.get("entry_date")) for r in episodes})
    matured_dates = sorted({str(r.get("entry_date")) for r in matured})

    out: dict[str, Any] = {
        "board_definition": blk.get("board_definition"),
        "available": False,
        "n_matured": len(matured),
        "n_matured_with_excess": len(with_excess),
        "first_admission": all_dates[0] if all_dates else None,
        "last_admission": all_dates[-1] if all_dates else None,
        "last_matured_admission": matured_dates[-1] if matured_dates else None,
        "orderings": {},
        "primary_ordering": None,
        "oracle_regret": None,
        "risk_by_tercile": None,
        "components": None,
        "headline": None,
        "note": None,
    }
    if len(matured) < RANK_EFF_MIN_ROWS:
        out["note"] = (f"{len(matured)} matured episode(s), below the "
                       f"{RANK_EFF_MIN_ROWS}-row floor — the ordering is not gradeable "
                       "yet. Accruing; this blocks nothing.")
        return out

    has_score = any(_f(r.get("prophet_score")) is not None for r in matured)
    has_rank = any(_f(r.get("board_rank")) is not None for r in matured)
    # The SCORE is the instrument under test wherever the ledger stored it; board_rank is
    # the legacy era's only ordering and stays graded beside it wherever both exist.
    primary = ORDER_SOURCE_SCORE if has_score else ORDER_SOURCE_RANK

    unavailable_reason = {
        ORDER_SOURCE_SCORE: ("pre-v2 board rows carry board_rank only — the score did "
                             "not exist when this era was admitted"),
        ORDER_SOURCE_RANK: "the ledger stored no board_rank for this era",
    }
    for source, present in ((ORDER_SOURCE_SCORE, has_score), (ORDER_SOURCE_RANK, has_rank)):
        if not present:
            out["orderings"][source] = {
                "available": False, "n": 0, "ic": {},
                "note": (f"'{source}' is null on every matured episode of this "
                         f"definition — {unavailable_reason[source]}"),
            }
            continue
        n_present = sum(1 for r in matured if _order_key(r, source) is not None)
        out["orderings"][source] = {
            "available": True,
            "n": n_present,
            "is_primary": bool(source == primary),
            "orientation": (
                "used as stored (rank 1 = best, so lower = better)"
                if source == ORDER_SOURCE_RANK
                else "NEGATED (higher score = better, so lower key = better)"
            ),
            "ic": _ic_ladder(matured, source),
        }

    out["available"] = True
    out["primary_ordering"] = primary
    out["oracle_regret"] = _oracle_regret(matured, primary)
    out["risk_by_tercile"] = _tercile_profile(matured, primary)
    out["components"] = _component_attribution(matured)
    # Spine coverage is printed because build_china_library calls this module BEFORE
    # china_standout_track.grade(), so the newest rows legitimately carry a null spine.
    out["spine_coverage"] = {
        "source": ("china_standout_track.grade() write-back on the board row — read "
                   "one nightly BEFORE this run's grade(), so the newest admissions "
                   "are null until tomorrow"),
        **{c: sum(1 for r in matured if _f(r.get(c)) is not None)
           for c in SPINE_MFE_COLS},
        "terminal_state_clean8_21": sum(
            1 for r in matured
            if _text_or_none(r.get("terminal_state_clean8_21")) is not None),
        "post_cushion_breach": sum(
            1 for r in matured if _tri_bool(r.get("post_cushion_breach")) is not None),
    }

    primary_ic = (out["orderings"].get(primary) or {}).get("ic") or {}
    top = (out["risk_by_tercile"].get("terciles") or [{}])[0]
    out["headline"] = {
        "ordering_source": primary,
        "ic_excess_h10": (primary_ic.get("excess_h10") or {}).get("ic"),
        "ic_mfe_21": (primary_ic.get("fwd_mfe_21") or {}).get("ic"),
        "regret6": out["oracle_regret"].get("regret6"),
        "capture6": out["oracle_regret"].get("capture6"),
        "top_tercile_loser_rate": top.get("loser_rate"),
    }
    return out


def _warn_wrong_sign(block: dict) -> None:
    """Alarm an ANTI-PREDICTIVE ordering — the V1 failure, restated as a nightly gate.

    Fires when the primary ordering's ``ic_excess_h10`` is POSITIVE over at least
    ``WRONG_SIGN_MIN_EPISODES`` matured episodes: on the canonical orientation a
    positive IC means the board put the WORSE names first.

    No era is exempt, deliberately. The legacy block trips this every night at +0.073 —
    that firing is the standing proof the detector can see the defect the program already
    measured, and a suppression list for "known" eras is exactly the kind of quiet branch
    that would let the next one through. The message carries the era's last admission
    date so a closed era reads as a closed era.
    """
    head = block.get("headline") or {}
    ic = head.get("ic_excess_h10")
    n = int(block.get("n_matured") or 0)
    if ic is None or ic <= 0 or n < WRONG_SIGN_MIN_EPISODES:
        return
    definition = block.get("board_definition")
    print(f"::warning title=cn-prophet-rank-anti-predictive::"
          f"cn_prophet_audit: board_definition '{definition}' orders ANTI-PREDICTIVELY — "
          f"{head.get('ordering_source')} rank-IC vs H=10 excess is {ic:+.4f} over {n} "
          f"matured episodes (a well-ordered board scores NEGATIVE here). Last admission "
          f"{block.get('last_admission')}, last matured "
          f"{block.get('last_matured_admission')}. Full ladder in "
          f"data/cn_prophet_audit/latest.json -> rank_effectiveness.", flush=True)


def rank_effectiveness(definitions: list[dict]) -> dict:
    """Grade the ORDERING itself, per board definition. Never pooled, zero authority.

    ``definitions`` is ``loser_telemetry(...)['definitions']`` — this function adds no
    store read of its own and is pure arithmetic over the episode records section 1 has
    already built, which is what keeps it inside budget.
    """
    t0 = time.perf_counter()
    blocks = [_rank_eff_block(blk) for blk in definitions]
    for block in blocks:
        try:
            _warn_wrong_sign(block)
        except Exception as exc:  # noqa: BLE001 — an alarm must never break the artifact
            log.debug("cn_prophet_audit: wrong-sign check skipped (%s)", exc)
    elapsed = round(time.perf_counter() - t0, 2)
    log.info("cn_prophet_audit: rank_effectiveness over %d definition(s) in %.2fs",
             len(blocks), elapsed)
    return {
        "tier": TIER,
        "authority": "none — this grades an ordering it cannot change",
        "orientation": (
            "Every IC uses one key convention: LOWER ordering key = the board's own "
            "claim of a better pick. board_rank is used as stored (rank 1 = best); "
            "prophet_score and every component are NEGATED. So for a higher-is-better "
            "outcome a well-ordered board scores a NEGATIVE ic and a POSITIVE ic is "
            "anti-predictive (measured legacy baseline: +0.073 vs H=10 excess). Cost "
            "outcomes invert — read each metric's own 'good_sign'/'wrong_sign'."
        ),
        "ic_method": (
            f"per-admission-date Spearman, then the MEAN across dates; a date "
            f"contributes with >= {RANK_EFF_MIN_PER_DATE} distinct ordering values and "
            f">= 2 distinct outcomes. Same convention as "
            f"china_standout_track.grade()'s board_rank_ic. 'pooled_ic' is the "
            f"cross-date figure, printed for comparison."
        ),
        "min_rows": RANK_EFF_MIN_ROWS,
        "oracle_k": ORACLE_K,
        "catastrophic_pnl_pct": CATASTROPHIC_PNL_PCT,
        "wrong_sign_min_episodes": WRONG_SIGN_MIN_EPISODES,
        "definitions": blocks,
        "elapsed_seconds": elapsed,
    }


# ---------------------------------------------------------------------------
# 4. write path
# ---------------------------------------------------------------------------
def _forward_log_rows(definitions: list[dict], asof: str,
                      rank_eff: dict | None = None) -> list[dict]:
    """One headline row per (run date × board_definition) for the append-only log.

    The rank-effectiveness headline columns are ADDITIVE — they join by
    ``board_definition`` and are null for a definition that has not accrued enough
    matured episodes to be gradeable. ``append_forward_log``'s column union means rows
    written before these columns existed keep reading fine, and keep-FIRST still means a
    published headline is never rewritten.
    """
    rank_by_def: dict[str, dict] = {}
    for blk in (rank_eff or {}).get("definitions") or []:
        rank_by_def[str(blk.get("board_definition"))] = blk.get("headline") or {}

    rows = []
    for blk in definitions:
        chase = blk.get("chase") or {}
        head = rank_by_def.get(str(blk["board_definition"])) or {}
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
            # ── rank effectiveness, appended AFTER the pre-existing columns so the
            # log's own identity columns keep leading the parquet ──────────────────
            "rank_ordering_source": head.get("ordering_source"),
            "ic_excess_h10": head.get("ic_excess_h10"),
            "ic_mfe_21": head.get("ic_mfe_21"),
            "regret6": head.get("regret6"),
            "capture6": head.get("capture6"),
            "top_tercile_loser_rate": head.get("top_tercile_loser_rate"),
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
        # Pure arithmetic over the episode records just built — no store read, so it
        # runs before the memo is dropped only for locality, not because it needs it.
        ranking = rank_effectiveness(losers["definitions"])
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
            "rank_effectiveness": ranking,
            "miss_funnel": funnel,
            "elapsed_seconds": elapsed,
        }
        written = _write_latest(doc)
        n_log = append_forward_log(
            _forward_log_rows(losers["definitions"], str(asof or ""), ranking)
        ) if asof else 0
        return {
            "written": bool(written),
            "elapsed_seconds": elapsed,
            "n_definitions": len(losers["definitions"]),
            "rank_effectiveness_seconds": ranking.get("elapsed_seconds"),
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
