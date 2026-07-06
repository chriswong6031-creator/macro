"""The Outcome Spine — the one shared signal-id → outcome substrate (Masterplan §W4, audit #13).

The audit's core finding (#13): the suite is full of accountability ledgers whose grades
are "computed, logged, and discarded from every downstream arithmetic step". The loop only
ever closed inside the LLM context window. #13 says the missing piece is *"a shared
signal-id/outcome contract that exists nowhere in either codebase"*. This module IS that
contract.

WHAT A SPINE ROW IS
-------------------
Every decision-facing signal writes ONE prediction row when it fires::

    {signal_id, engine, version, family, as_of, symbol, universe, horizon,
     score, size_binding, direction, meta}

  * ``signal_id``   — stable id for THIS prediction (``{engine}:{as_of}:{symbol}:{horizon}``).
  * ``engine``      — the emitter ("us_board", "altdata_conv", "desk:ai_desk", …).
  * ``version``     — ``engine@version`` so a re-tuned engine's rows are separable.
  * ``family``      — the POOLING family this row shrinks toward (see engine.pooling): the
                      lane / channel / desk group. n=5 in a family of 6 moves a little
                      instead of nothing.
  * ``as_of``       — the decision date (the bar the signal fired on).
  * ``symbol`` / ``universe`` — the graded name (or a universe tag for aggregate theses).
  * ``horizon``     — trading-day horizon the prediction is about.
  * ``score``       — the emitter's own conviction/rank score (signed if directional).
  * ``size_binding``— True iff this row actually *sized real (paper) money* (a hard filter
                      so the loop can weight the rows that mattered, not display-only noise).
  * ``direction``   — +1 long / -1 short / 0 neutral-context (drives sign-safe grading).

MATURATION — one grader, never a second convention
---------------------------------------------------
Rows do NOT carry an outcome at emission. They MATURE through engine.grading (the W1c
survivorship-aware next-bar grader) exactly like every other track record — so the spine
never re-derives a subtly-different (flattering) fill/return convention. ``graded_rows``
joins predictions to matured forward returns and returns the outcome panel the pooling
engine and the IC-aware alert severity read.

ADAPTERS, NOT DUPLICATES
------------------------
The FIRST emitters already keep rich ledgers. Rather than double-log, this module ADAPTS
their existing artifacts into spine rows:
  * ``adapt_us_board``   — the US board retro/forward ledger (scripts/grade_us_board.py,
    data/us_board_ledger/retro_grades.parquet) → per (as_of, lane, ticker, horizon) rows,
    already next-bar-filled and excess-vs-SPY graded. Both lanes (buy + watch/laggard).
  * ``adapt_altdata``    — the alt-data convergence ledger (engine.altdata_ledger,
    data/altdata/{theses,scored}.jsonl) → per-thesis rows carrying the co-firing channel
    set so engine.altdata_signals can estimate the same-event penalty (#23).
  * ``adapt_desk_scorer``— every Phase-C desk's scored.jsonl (engine.desk_scorer) → per-thesis
    rows keyed by ``family="desk:{name}"`` so engine.desk_scorer can pool desk weights (#13).

Design: pure pandas/pyarrow, degrade-never-raise (a missing ledger yields an empty frame
with the canonical columns, never a crash), append-only + idempotent on ``signal_id``. This
is a LIBRARY — callers pass their own root; it reads config only for the default path.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

__all__ = [
    "SpinePrediction",
    "COLUMNS",
    "spine_path",
    "emit",
    "load",
    "graded_rows",
    "measured_ic",
    "adapt_us_board",
    "adapt_altdata",
    "adapt_desk_scorer",
    "adapt_subsector_sponsorship",
    "write_subsector_sponsorship",
    "rebuild_from_adapters",
]

SCHEMA = "spine.predictions.v2"

# The canonical row contract. Every adapter and every direct emitter yields exactly these.
# W1 adds: is_sizing, is_veto, is_alpha, is_timing, is_context, falsifier, half_life
# appended at the END to preserve positional compatibility with any legacy reader.
COLUMNS = [
    "signal_id", "engine", "version", "family", "as_of", "symbol", "universe",
    "horizon", "score", "size_binding", "direction", "event_key", "outcome_excess",
    "outcome_graded", "graded_at", "meta",
    # W1 Spine v2 — descriptive role flags (additive; no consumer uses them to gate money)
    "is_sizing",    # True iff this row sized real (paper) money  (= size_binding)
    "is_veto",      # True iff this is a short/avoid lane (direction < 0 and not size_binding)
    "is_alpha",     # True iff directional long conviction that was sized (size_binding and direction > 0)
    "is_timing",    # Left False this wave — no mechanical source; see open questions
    "is_context",   # Catch-all default: True when none of the above apply
    "falsifier",    # Human-facing falsifier text (nullable str); machine `check` stays in meta
    "half_life",    # Decay half-life in trading days (nullable float); filled by W2
]

# Conservative defaults for the 5 flag columns on read (old parquet backfill).
# is_context must be True for old rows (they were context before the flag existed).
_FLAG_DEFAULTS: dict[str, object] = {
    "is_sizing":  False,
    "is_veto":    False,
    "is_alpha":   False,
    "is_timing":  False,
    "is_context": True,
}


def _derive_role_flags(size_binding: bool, direction: int) -> dict:
    """Derive the 5 descriptive role flags from mechanical spine fields.

    Derivation (R8 conservative):
      is_sizing  = size_binding
      is_veto    = (direction < 0) and not size_binding
      is_alpha   = size_binding and (direction > 0)
      is_timing  = False  (no mechanical source this wave — open question)
      is_context = not (is_sizing or is_veto or is_alpha)  # catch-all default

    Badge precedence for one-badge display: veto > alpha > sizing > timing > context.
    Flags are non-exclusive (buy rows have is_sizing AND is_alpha both True).
    """
    is_sizing  = bool(size_binding)
    is_veto    = bool((direction < 0) and not size_binding)
    is_alpha   = bool(is_sizing and (direction > 0))
    is_timing  = False
    is_context = not (is_sizing or is_veto or is_alpha)
    return {
        "is_sizing":  is_sizing,
        "is_veto":    is_veto,
        "is_alpha":   is_alpha,
        "is_timing":  is_timing,
        "is_context": is_context,
    }


@dataclass
class SpinePrediction:
    """One decision-facing prediction. ``outcome_*`` stay None until maturation."""
    signal_id: str
    engine: str
    family: str
    as_of: str
    symbol: str
    horizon: int
    score: float
    direction: int = 1
    size_binding: bool = False
    version: str = "v1"
    universe: str = ""
    # ``event_key`` groups predictions that share ONE underlying event (e.g. every alt-data
    # channel lit by the same 8-K). The pooling / convergence layers collapse a shared
    # event_key to ONE effective observation (#23 co-firing penalty). Defaults to the row's
    # own (symbol, as_of) — i.e. "one event per name per day" unless the emitter knows better.
    event_key: str = ""
    outcome_excess: float | None = None      # matured excess-vs-benchmark forward return
    outcome_graded: bool = False
    graded_at: str | None = None
    meta: dict = field(default_factory=dict)
    # W1 Spine v2 — descriptive role flags (descriptive-only; never gate a money path)
    is_sizing:  bool = False    # derived from size_binding
    is_veto:    bool = False    # derived from direction < 0 and not size_binding
    is_alpha:   bool = False    # derived from size_binding and direction > 0
    is_timing:  bool = False    # always False this wave (no mechanical source)
    is_context: bool = True     # catch-all default
    falsifier:  str | None = None   # human-facing falsifier text (nullable)
    half_life:  float | None = None  # decay half-life in trading days; filled by W2

    def __post_init__(self):
        if not self.event_key:
            self.event_key = f"{self.symbol}:{self.as_of}"
        # Auto-derive role flags from size_binding / direction if caller left them at defaults.
        # Flags are derivation-cached: if the caller explicitly set them we respect that.
        # Conservative guard: only overwrite if all 5 are at factory defaults (all False / is_context True).
        _all_default = (
            not self.is_sizing and not self.is_veto and not self.is_alpha
            and not self.is_timing and self.is_context
        )
        if _all_default:
            flags = _derive_role_flags(self.size_binding, self.direction)
            self.is_sizing  = flags["is_sizing"]
            self.is_veto    = flags["is_veto"]
            self.is_alpha   = flags["is_alpha"]
            self.is_timing  = flags["is_timing"]
            self.is_context = flags["is_context"]

    def as_row(self) -> dict:
        d = asdict(self)
        d["meta"] = json.dumps(d.get("meta") or {}, default=str)
        # Ensure flag values are native Python bool (guard against np.bool_ poisoning json)
        for flag in ("is_sizing", "is_veto", "is_alpha", "is_timing", "is_context"):
            d[flag] = bool(d[flag])
        # half_life must be Python float or None (not np.float64)
        hl = d.get("half_life")
        d["half_life"] = float(hl) if hl is not None else None
        return d


# --------------------------------------------------------------------------- #
# io — append-only parquet, idempotent on signal_id
# --------------------------------------------------------------------------- #
def spine_path(root=None) -> Path:
    from lib import config
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "spine" / "predictions.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _empty() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype="object") for c in COLUMNS})
    return df


def load(root=None) -> pd.DataFrame:
    """The full predictions frame (canonical columns), or an empty frame. Never raises.

    W1 R8 backfill: old 16-col parquet loads with conservative flag defaults so
    is_context=True (not null) for pre-W1 rows.  falsifier=None, half_life=NaN.
    """
    p = spine_path(root)
    if not p.exists():
        return _empty()
    try:
        df = pd.read_parquet(p)
        for c in COLUMNS:
            if c not in df.columns:
                # Apply R8 conservative defaults (not None) for the 5 role flags
                default = _FLAG_DEFAULTS.get(c, None)
                df[c] = default
        df = df[COLUMNS]
        # Backfill flag columns for rows where they are None/NaN (old parquet rows).
        for flag, default_val in _FLAG_DEFAULTS.items():
            if flag in df.columns:
                df[flag] = df[flag].fillna(default_val)
        # Cast flag columns to Python bool (nullable object → bool-safe)
        for flag in _FLAG_DEFAULTS:
            if flag in df.columns:
                df[flag] = df[flag].astype(bool)
        return df
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("spine.load failed: %s", e)
        return _empty()


def emit(rows: Iterable[SpinePrediction | dict], root=None) -> int:
    """Append prediction rows, de-duped on ``signal_id`` (last-wins). Returns rows written.

    Idempotent: re-emitting the same signal_id updates it (so a maturation pass can rewrite
    the row with its outcome without duplicating). Degrade-never-raise."""
    try:
        new = [r.as_row() if isinstance(r, SpinePrediction) else dict(r) for r in rows]
        if not new:
            return 0
        nf = pd.DataFrame(new)
        for c in COLUMNS:
            if c not in nf.columns:
                nf[c] = None
        nf = nf[COLUMNS]
        cur = load(root)
        merged = pd.concat([cur, nf], ignore_index=True)
        # last write wins per signal_id (keeps the most recently-graded copy)
        merged = merged.drop_duplicates(subset=["signal_id"], keep="last").reset_index(drop=True)
        merged.to_parquet(spine_path(root), index=False)
        return len(new)
    except Exception as e:  # noqa: BLE001
        log.warning("spine.emit failed: %s", e)
        return 0


# --------------------------------------------------------------------------- #
# maturation / measured IC — reads matured rows; never grades a second way
# --------------------------------------------------------------------------- #
def graded_rows(root=None, *, size_binding_only: bool = False) -> pd.DataFrame:
    """Matured rows only (outcome_graded True and a finite outcome_excess). This is the
    single panel the pooling engine and IC-aware alert severity consume."""
    df = load(root)
    if df.empty:
        return df
    g = df[df["outcome_graded"].fillna(False).astype(bool)].copy()
    g["outcome_excess"] = pd.to_numeric(g["outcome_excess"], errors="coerce")
    g = g[np.isfinite(g["outcome_excess"])]
    if size_binding_only:
        g = g[g["size_binding"].fillna(False).astype(bool)]
    return g.reset_index(drop=True)


def _signed_outcome(g: pd.DataFrame) -> pd.Series:
    """The direction-aware realized excess: a SHORT/veto (direction -1) that avoided a loser
    earns POSITIVE credit (sign-inverted) — so attribution and calibration agree in sign
    (audit #17). direction 0 (context) keeps the raw excess (no directional claim)."""
    d = pd.to_numeric(g["direction"], errors="coerce").fillna(1)
    signed = g["outcome_excess"].where(d == 0, g["outcome_excess"] * np.sign(d.replace(0, 1)))
    return signed


def _effective_n(g: pd.DataFrame) -> int:
    """Distinct-event count: rows sharing an ``event_key`` count as ONE observation. This is
    the co-firing collapse (#23) — N same-event channels are one, not N, pieces of evidence."""
    if g.empty:
        return 0
    return int(g["event_key"].nunique())


def measured_ic(root=None, *, engine=None, family=None, horizon=None,
                size_binding_only: bool = False) -> dict:
    """Measured forward edge for a slice of the spine. Returns::

        {"n": <rows>, "n_eff": <distinct events>, "hit_rate": .., "mean_excess": ..,
         "ic": <sign-aware mean signed excess>, "wrong_sign": <bool>}

    ``ic`` here is the direction-aware MEAN signed excess (a simple, robust edge proxy — the
    pooling engine consumes the raw signed outcomes, this is the human-facing summary). n_eff
    is the co-firing-collapsed effective sample. Empty slice → n=0 cold-start dict (never a
    crash, never a fabricated number)."""
    g = graded_rows(root, size_binding_only=size_binding_only)
    if engine is not None:
        g = g[g["engine"] == engine]
    if family is not None:
        g = g[g["family"] == family]
    if horizon is not None:
        g = g[pd.to_numeric(g["horizon"], errors="coerce") == int(horizon)]
    g = g.reset_index(drop=True)
    n = len(g)
    if n == 0:
        return {"n": 0, "n_eff": 0, "hit_rate": None, "mean_excess": None,
                "ic": None, "wrong_sign": False}
    signed = _signed_outcome(g)
    mean_signed = float(signed.mean())
    return {
        "n": n,
        "n_eff": _effective_n(g),
        "hit_rate": round(float((signed > 0).mean()), 4),
        "mean_excess": round(float(g["outcome_excess"].mean()), 5),
        "ic": round(mean_signed, 5),
        "wrong_sign": bool(mean_signed < 0),
    }


# --------------------------------------------------------------------------- #
# ADAPTERS — read the existing ledgers into spine rows (no duplicate logging)
# --------------------------------------------------------------------------- #
def adapt_us_board(root=None) -> list[SpinePrediction]:
    """US board ledger → spine rows. Reads data/us_board_ledger/retro_grades.parquet (already
    next-bar-filled and excess-vs-SPY graded by scripts/grade_us_board.py). BOTH lanes: the
    ``buy`` lane is size-binding (direction +1), ``watch``/``laggards`` are context (0) so
    they still accrue IC but never claim to have sized money.

    W1: role flags derived mechanically; falsifier=None for all us_board rows (retro_grades.parquet
    carries no falsifier field — correct null story, not a gap to fill).
    """
    from lib import config
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "us_board_ledger" / "retro_grades.parquet"
    if not p.exists():
        return []
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("adapt_us_board read failed: %s", e)
        return []
    out: list[SpinePrediction] = []
    for _, r in df.iterrows():
        lane = str(r.get("lane", ""))
        ex = r.get("excess_spy")
        as_of = str(r.get("as_of", ""))
        tk = str(r.get("ticker", ""))
        h = r.get("horizon")
        if not as_of or not tk or h is None:
            continue
        # laggards is a SHORT-lean lane (we expect it to underperform) → direction -1 so a
        # correctly-avoided loser earns positive credit; buy/watch are long-lean.
        direction = -1 if lane in ("laggards", "laggard") else 1
        sb = (lane == "buy")
        flags = _derive_role_flags(sb, direction)
        out.append(SpinePrediction(
            signal_id=f"us_board:{as_of}:{tk}:{lane}:{int(h)}",
            engine="us_board", family=f"us_board:{('laggards' if direction < 0 else lane)}",
            as_of=as_of, symbol=tk, horizon=int(h),
            score=float(r["composite_z"]) if pd.notna(r.get("composite_z")) else 0.0,
            direction=direction,
            size_binding=sb,
            universe="us_1500",
            outcome_excess=float(ex) if pd.notna(ex) else None,
            outcome_graded=pd.notna(ex),
            meta={"lane": lane, "position": _num(r.get("position"))},
            # W1 Spine v2 flags — descriptive-only, never gate a money path
            is_sizing=flags["is_sizing"],
            is_veto=flags["is_veto"],
            is_alpha=flags["is_alpha"],
            is_timing=flags["is_timing"],
            is_context=flags["is_context"],
            falsifier=None,  # retro_grades.parquet carries no falsifier — correct null story
            half_life=None,  # filled by W2
        ))
    return out


def adapt_altdata(root=None) -> list[SpinePrediction]:
    """Alt-data convergence ledger → spine rows carrying the co-firing channel set. Reads the
    theses (channels, entry) and the matured outcomes (scored.jsonl). ``event_key`` is the
    THESIS id — every channel that co-fired on the same name/day is one event, so downstream
    can penalise same-event correlation (#23) instead of counting channels as independent.

    W1: falsifier text mapped from thesis["falsifier"]["text"] (available on all 134 rows).
    Role flags: altdata is always context-only (size_binding=False, direction=1).
    """
    from engine.altdata_ledger import _LEDGER, _SCORED, _p
    from engine.desk_scorer import load_jsonl, dedupe_by_id
    from lib import config
    r = Path(root) if root else config.ROOT
    theses = dedupe_by_id(load_jsonl(_p(r, _LEDGER)))
    scored = dedupe_by_id(load_jsonl(_p(r, _SCORED)))
    # altdata: size_binding=False, direction=1 → always is_context=True per R8
    _flags = _derive_role_flags(False, 1)
    out: list[SpinePrediction] = []
    for tid, th in theses.items():
        sc = scored.get(tid) or {}
        outcome = sc.get("outcome")
        realized = sc.get("realized")
        graded = outcome in ("hit", "miss") and realized is not None
        chans = th.get("channels") or []
        tk = th.get("ticker") or ""
        as_of = th.get("state_asof") or ""
        score = float(th.get("convergence_score") or len(chans))
        # Extract falsifier text (the machine check dict stays in meta)
        falsifier_obj = th.get("falsifier") or {}
        falsifier_text: str | None = falsifier_obj.get("text") if isinstance(falsifier_obj, dict) else None
        # For a convergence thesis the realized number is the rel_return vs SPY; 'miss' means
        # it UNDERperformed. outcome_excess carries the signed realized excess directly.
        out.append(SpinePrediction(
            signal_id=f"altdata_conv:{tid}",
            engine="altdata_conv", family="altdata:convergence",
            as_of=as_of, symbol=tk, horizon=th.get("horizon_d") or 63,
            score=score, direction=1, size_binding=False, universe="us_altdata",
            event_key=tid,   # the co-firing collapse key: one thesis = one event
            outcome_excess=float(realized) if graded else None,
            outcome_graded=bool(graded),
            meta={"channels": list(chans), "trump_linked": bool(th.get("trump_linked")),
                  "convergence_score": int(score),
                  "falsifier_check": falsifier_obj.get("check") if isinstance(falsifier_obj, dict) else None},
            # W1 Spine v2 flags
            is_sizing=_flags["is_sizing"],
            is_veto=_flags["is_veto"],
            is_alpha=_flags["is_alpha"],
            is_timing=_flags["is_timing"],
            is_context=_flags["is_context"],
            falsifier=falsifier_text,
            half_life=None,
        ))
    return out


# Desk scored.jsonl locations, keyed by desk name → its family. Mirrors master_brain._DESK_TRACKS
# but points at the per-thesis scored rows (richer than the aggregate track_record.json).
_DESK_SCORED = {
    "ai_desk":       ("data", "ai_desk", "scored.jsonl"),
    "policy_intent": ("data", "policy_intent", "scored.jsonl"),
    "radar":         ("data", "radar", "scored.jsonl"),
    "stock_desk":    ("data", "stock_desk", "scored.jsonl"),
    "demand_chain":  ("data", "demand_chain", "scored.jsonl"),
    "narrative_brain": ("data", "narrative_brain", "scored.jsonl"),
    "thematic_desk": ("data", "thematic_desk", "scored.jsonl"),
}


def adapt_desk_scorer(root=None, desks: dict | None = None) -> list[SpinePrediction]:
    """Every Phase-C desk's scored.jsonl → spine rows keyed ``family="desk:{name}"``. The
    desk 'family' is what engine.desk_scorer pools toward the cross-desk mean so a cold desk
    (n=5) shrinks to the family prior instead of keeping full equal-weight (#13/#19). The
    realized rel_return becomes outcome_excess; a 'miss' is a negative-signed outcome so a
    reliably-wrong desk's pooled weight can go NEGATIVE (sign-safety).

    W1: falsifier text joined from sibling theses.jsonl (same dir as scored.jsonl) keyed by id.
    scored.jsonl does NOT carry falsifier — theses.jsonl does.  Join is nullable: rows whose
    id is absent from theses.jsonl get falsifier=None.
    Role flags: desks are always context-only (size_binding=False, direction=1).
    """
    from lib import config
    from engine.desk_scorer import load_jsonl
    r = Path(root) if root else config.ROOT
    desks = desks or _DESK_SCORED
    # Desks are context-only: size_binding=False, direction=1 → is_context=True
    _flags = _derive_role_flags(False, 1)
    out: list[SpinePrediction] = []
    for name, parts in desks.items():
        scored_path = Path(r).joinpath(*parts)
        rows = load_jsonl(scored_path)
        # Load theses.jsonl for falsifier join (sibling file at same dir as scored.jsonl)
        theses_path = scored_path.parent / "theses.jsonl"
        theses_by_id: dict[str, dict] = {}
        if theses_path.exists():
            try:
                for th in load_jsonl(theses_path):
                    tid = th.get("id")
                    if tid:
                        theses_by_id[str(tid)] = th
            except Exception as e:  # noqa: BLE001
                log.debug("adapt_desk_scorer: theses.jsonl read failed for %s: %s", name, e)
        for sr in rows:
            outcome = sr.get("outcome")
            if outcome not in ("hit", "miss"):
                continue           # unscored/expired/open carry no outcome
            realized = sr.get("realized")
            sid = sr.get("id")
            if sid is None:
                continue
            # 'hit'/'miss' is the falsifier verdict; realized is the signed rel_return where
            # available. When realized is absent, encode the verdict as ±1 so the sign still
            # flows (a hit is a correct call → positive; a miss → negative).
            if realized is None:
                excess = 1.0 if outcome == "hit" else -1.0
            else:
                excess = float(realized) if outcome == "hit" else -abs(float(realized))
            # Falsifier join: look up thesis by id; extract text only (machine check stays in meta)
            thesis = theses_by_id.get(str(sid))
            falsifier_obj = (thesis or {}).get("falsifier") or {}
            falsifier_text: str | None = (
                falsifier_obj.get("text") if isinstance(falsifier_obj, dict) else None
            )
            out.append(SpinePrediction(
                signal_id=f"desk:{name}:{sid}",
                engine=f"desk:{name}", family=f"desk:{name}",
                as_of=str(sr.get("check_by") or ""), symbol=str(sr.get("subject") or name),
                horizon=63, score=1.0, direction=1, size_binding=False,
                universe="desks",
                outcome_excess=excess, outcome_graded=True,
                meta={"conviction": sr.get("conviction"), "lean": sr.get("lean"),
                      "kind": sr.get("kind"), "outcome": outcome,
                      "dir_ok": sr.get("directionally_correct")},
                # W1 Spine v2 flags
                is_sizing=_flags["is_sizing"],
                is_veto=_flags["is_veto"],
                is_alpha=_flags["is_alpha"],
                is_timing=_flags["is_timing"],
                is_context=_flags["is_context"],
                falsifier=falsifier_text,
                half_life=None,
            ))
    return out


# --------------------------------------------------------------------------- #
# SRSS Phase 2 — subsector sponsorship adapter (shadow tier, display-only)
# --------------------------------------------------------------------------- #
# "Today's live gate fires" source: data/us_board_ledger/snapshots.jsonl, the
# SAME append-only forward ledger scripts/grade_us_board.py --nightly accrues
# (retro_grades.parquet, read by adapt_us_board() above, is the MATURED/graded
# view of this same stream — it only carries a row once a full grading pass has
# run). snapshots.jsonl carries the as-fired board the instant it is committed,
# which is what "live" means here — reading it directly (not retro_grades)
# avoids waiting on maturation for a purely descriptive annotation that is
# never itself graded (see below).
_SPONSORSHIP_BOARD = ("data", "us_board_ledger", "snapshots.jsonl")

# House convention (mirrors adapt_us_board's lane->direction mapping exactly):
# buy/watch lanes are long-lean, laggards is the short-lean lane. This is read
# FROM the source event's own lane, never invented.
_LANE_DIRECTION = {"buy": 1, "watch": 1, "laggards": -1, "laggard": -1}


def _load_latest_board_fires(root=None) -> list[dict]:
    """Flatten the MOST RECENT snapshot in data/us_board_ledger/snapshots.jsonl
    into one dict per (as_of, ticker, lane) fire — the "today's live gate
    fires" input to ``adapt_subsector_sponsorship``. Fail-open: returns []
    if the ledger is absent/unreadable/empty."""
    from lib import config
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "us_board_ledger" / "snapshots.jsonl"
    if not p.exists():
        return []
    try:
        lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
    except Exception as e:  # noqa: BLE001
        log.warning("adapt_subsector_sponsorship: snapshots.jsonl read failed: %s", e)
        return []
    if not lines:
        return []
    try:
        latest = json.loads(lines[-1])
    except Exception as e:  # noqa: BLE001
        log.warning("adapt_subsector_sponsorship: latest snapshot line unparsable: %s", e)
        return []
    as_of = latest.get("as_of")
    if not as_of:
        return []
    out: list[dict] = []
    for lane in ("buy", "watch", "laggards"):
        for row in latest.get(lane) or []:
            tk = row.get("ticker")
            if not tk:
                continue
            out.append({
                "ticker": tk,
                "as_of": as_of,
                "lane": lane,
                "direction": _LANE_DIRECTION.get(lane, 0),
            })
    return out


def adapt_subsector_sponsorship(root=None, fires: list[dict] | None = None) -> list[SpinePrediction]:
    """Subsector-rotation sponsorship annotation → spine rows (SRSS Phase 2).

    Joins today's live per-stock gate fires (``fires``, defaulting to
    ``_load_latest_board_fires`` — see above) to the latest PIT subsector
    rotation snapshot (``data/subsector_rotation/snapshots.jsonl``) via the
    SAME nearest-prior-date, leak-safe join Phase 0 built and validated
    (``engine.subsector_sponsorship.RotationIndex`` / ``classify_sponsorship``
    — imported, not re-derived).

    ARTICLE-1 / DISPLAY-ONLY CONTRACT (hard):
      * ``direction`` is INHERITED from the source fire's own lane/direction
        field only — never invented. A fire with no direction information at
        all yields ``direction=0`` (context), not a fabricated lean.
      * ``score`` is always 0.0 — this row NEVER carries an originating
        conviction/rank score. The rotation ledger's own display score is
        carried through under ``meta["sponsorship_score"]`` for DISPLAY ONLY
        (confluence.py copies it to an edge attribute; nothing sums it into
        any weighted aggregate — see engine/neuralweb/confluence.py).
      * ``size_binding`` is always False (never sizes money).
      * ``outcome_excess``/``outcome_graded`` are always None/False — this is
        a descriptive annotation, never graded, so it can never enter
        ``graded_rows()``/``measured_ic()`` and cannot move any pooled score.
      * ``meta["display_only"] = True`` — the same display-only convention
        confluence.py stamps on every edge (see confluence.py's ``_edge()``
        helper and its module docstring hard law).

    This is a SHADOW-tier artifact: it is NOT written into the shared
    data/spine/predictions.parquet (unlike the other three adapters here) —
    see ``write_subsector_sponsorship`` — to avoid mixing a
    never-graded, zero-score context stream into the one ledger every pooling
    /kernel/half-life consumer iterates over engine-by-engine.

    Returns [] fail-open (bare root, absent ledgers, or no matches).
    """
    root_path = root
    from lib import config
    r = Path(root_path) if root_path else config.ROOT

    if fires is None:
        fires = _load_latest_board_fires(root_path)
    if not fires:
        return []

    from engine.subsector_sponsorship import (
        RotationIndex,
        classify_sponsorship,
        confidence_tier,
        is_stale,
        load_snapshots,
    )

    snapshots = load_snapshots(r)
    if not snapshots:
        return []
    ridx = RotationIndex(snapshots)

    out: list[SpinePrediction] = []
    for fire in fires:
        ticker = fire.get("ticker")
        as_of = fire.get("as_of")
        if not ticker or not as_of:
            continue
        try:
            event_date = pd.Timestamp(as_of)
        except Exception:  # noqa: BLE001
            continue

        # direction: inherit ONLY from the source fire. No "direction" key at
        # all (and no lane) means direction=0 — never fabricate a lean.
        raw_dir = fire.get("direction")
        if raw_dir is None:
            lane = fire.get("lane")
            raw_dir = _LANE_DIRECTION.get(lane, 0) if lane else 0
        elif isinstance(raw_dir, str):
            raw_dir = {"long": 1, "short": -1}.get(raw_dir.lower(), 0)
        try:
            direction = int(raw_dir)
        except (TypeError, ValueError):
            direction = 0

        match = ridx.lookup(ticker, event_date)
        if match is None:
            continue  # no-match: not silently guessed, simply no row emitted

        rotation_date = pd.Timestamp(match.get("date"))
        n_members = len(match.get("members") or [])
        stale = is_stale(rotation_date, event_date)
        state = classify_sponsorship(
            match.get("quadrant"), match.get("rs_mom"), match.get("accel"),
            match.get("score"), n_members, stale,
        )
        tier = confidence_tier(n_members)

        out.append(SpinePrediction(
            signal_id=f"subsector_sponsorship:{as_of}:{ticker}:{fire.get('lane', 'na')}",
            engine="subsector_sponsorship",
            family=f"subsector_sponsorship:{state.lower()}",
            as_of=str(as_of),
            symbol=str(ticker),
            horizon=21,          # nominal context horizon; never graded (see docstring)
            score=0.0,           # never an originating score — see docstring
            direction=direction,  # inherited only, never invented
            size_binding=False,   # never sizes money
            universe="us_1500",
            outcome_excess=None,
            outcome_graded=False,
            meta={
                "display_only": True,
                "sponsorship_state": state,
                "confidence_tier": tier,
                "sponsorship_score": _num(match.get("score")),
                "rotation_key": match.get("key"),
                "rotation_asof": str(rotation_date.date()),
                "n_members": n_members,
                "stale": bool(stale),
                "source_lane": fire.get("lane"),
            },
            falsifier=None,
            half_life=None,
        ))
    return out


def write_subsector_sponsorship(root=None, fires: list[dict] | None = None) -> dict:
    """Build ``adapt_subsector_sponsorship`` rows and write them to their OWN
    shadow-tier parquet (data/spine/subsector_sponsorship.parquet) — kept
    OUT of data/spine/predictions.parquet on purpose (see adapter docstring).
    Idempotent on signal_id (last-wins), same convention as ``emit``.
    Degrade-never-raise. Returns {"rows_in": n, "path": str, "total_rows": n}."""
    from lib import config
    base = config.data_dir() if root is None else (Path(root) / "data")
    out_path = base / "spine" / "subsector_sponsorship.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        rows = adapt_subsector_sponsorship(root=root, fires=fires)
        new = [p.as_row() for p in rows]
        nf = pd.DataFrame(new) if new else _empty()
        if out_path.exists():
            try:
                cur = pd.read_parquet(out_path)
            except Exception:  # noqa: BLE001
                cur = _empty()
        else:
            cur = _empty()
        for c in COLUMNS:
            if c not in nf.columns:
                nf[c] = None
            if c not in cur.columns:
                cur[c] = None
        merged = pd.concat([cur[COLUMNS], nf[COLUMNS]], ignore_index=True) if len(nf) else cur[COLUMNS]
        merged = merged.drop_duplicates(subset=["signal_id"], keep="last").reset_index(drop=True)
        merged.to_parquet(out_path, index=False)
        return {"rows_in": len(new), "path": str(out_path), "total_rows": int(len(merged))}
    except Exception as e:  # noqa: BLE001
        log.warning("write_subsector_sponsorship failed: %s", e)
        return {"rows_in": 0, "path": str(out_path), "total_rows": 0}


def rebuild_from_adapters(root=None) -> dict:
    """Run every adapter and emit their rows into the spine. Idempotent (signal_id de-dupe).
    Returns a per-emitter count report. This is the single call a build step makes to keep the
    spine current from the existing ledgers — an adapter, not a second logger."""
    report: dict[str, int] = {}
    for name, fn in (("us_board", adapt_us_board),
                     ("altdata_conv", adapt_altdata),
                     ("desk_scorer", adapt_desk_scorer)):
        try:
            rows = fn(root=root)
            report[name] = emit(rows, root=root)
        except Exception as e:  # noqa: BLE001
            log.warning("spine adapter %s failed: %s", name, e)
            report[name] = 0
    report["total_rows"] = int(load(root).shape[0])
    report["graded_rows"] = int(graded_rows(root).shape[0])
    return report


def _num(x):
    try:
        v = float(x)
        return v if np.isfinite(v) else None
    except (TypeError, ValueError):
        return None
