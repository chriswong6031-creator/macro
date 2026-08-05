"""Prophet W3 — shadow candidate DOORS: **T (theme-relay)** and **R (re-arm)**.

Program: `research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §5 W3.
Pre-registration (FROZEN before first accrual): `research/PROPHET_DOORS_PREREG.md`.

WHAT THIS IS
------------
Two new candidate ORIGINATION doors, shipped as **shadow-accrual lanes**: they append
forward-graded flags to their own ledger and nothing else. The masterplan's §2 audit found
the incumbent fresh-cross family sights most eventual winners but holds them for a median of
3 sessions, and that hot-theme members sit veto-blocked by construction (44 of the top-50
21d movers are stoch_ob-family vetoed). §2.5 measured the naive remedy — "unblock the
leaders" — and it FAILED (leader pullback-reset −2.12% per-name median excess), while the
laggard-cross cell was the one positive (+1.44% per-name). So neither door loosens a veto:

  **Door T (theme-relay).** The VALIDATED incumbent trigger, UNMODIFIED (`signal_gate`
  eligible ∧ :func:`engine.signal_gate.is_buyable`, tiers T1/T2/T3), fired on a member of a
  top-5 heating theme. The only new thing is candidacy ROUTING — theme heat conditions WHICH
  validated fires get recorded, never WHETHER a fire is a fire. Theme state is a
  cross-sectional context, so this claims nothing per-name (DNR:KILL-ONSET-FINGERPRINTS / DNR:KILL-VOLUME-FINGERPRINTS).

  **Door R (re-arm).** The MSFT/PLTR-class re-entry: a name whose trend is intact
  (above200 ∧ weekly_bull) but whose master cross has gone stale (3-15 ticks) and is
  therefore NOT eligible today, whose 2D leg has just re-crossed up on a COMPLETED bucket
  while the 3D StochRSI stays constructive (K ≥ D). Keys on trend-intactness + reset, never
  on washout DEPTH (#1747 Amendment-3).

ZERO AUTHORITY (the whole point)
--------------------------------
Nothing in the pick chain imports this module. No board membership, no plan origination, no
rank / gate / size influence, no user-facing surface. It is a display/shadow tier lane, which
under house epistemics ships freely — a null never blocks accrual. Promotion to any authority
requires the pre-registered gate in PROPHET_DOORS_PREREG.md §4, and a PASS there buys only a
REVIEW (an operator-ratified adjudication), never automatic authority.
`tests/test_prophet_doors.py::test_no_authority_*` pins the import fence.

PROSPECTIVE ONLY
----------------
There is NO historical backfill. The ledger starts accruing the night this merges, mirroring
the PSS prospective-accrual charters. Every row is a real forward call made without hindsight.

RECORDED FEATURES ARE NOT FIRE CONDITIONS
-----------------------------------------
Each flag carries an analysis-only feature block (relay position, admission-day turnover,
Foresight Desk stage — :data:`FEATURE_KEYS`, prereg §9 addendum 2026-08-04). They exist so the
promotion read can test the CN-measured relay hypothesis on US forward data from day one.
**They have ZERO effect on fire / cap / dedupe / grading**: :class:`_RecordedFeatures` is
queried only AFTER a night's kept rows are already decided, and it degrades to nulls on any
failure. `tests/test_prophet_doors.py::TestFireInvariance` pins that the fire set is identical
with features on and off.

NIGHTLY IS THE SOLE ADVANCER
----------------------------
House law (CLAUDE.md §Ledgers). :func:`append_flags` refuses off-lane via
`engine.ledger_lane.nightly_advance_enabled` (COLLECT_LANE=nightly), so re-renders and
intraday lanes compute the same flags and discard them. :func:`emit` also takes
``dry_run=True`` for a no-write preview.

Run (nightly / DAG):   python -m scripts.emit_prophet_doors --nightly
Run (safe preview):    python -m scripts.emit_prophet_doors --dry-run
"""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from engine import confluence_tiers as ct
from engine import signal_gate
# Reuse the VALIDATED tier math — never reimplement it here (masterplan P1: rewire before
# invent). These are the same helpers `cascade()` and the §2 audit instruments run on.
from engine.confluence_tiers import _rsi_macd, _stoch_rsi_kd, _tf_bars, _xup
from engine.ledger_lane import nightly_advance_enabled as _ledger_advance_enabled

log = logging.getLogger("prophet_doors")

ROOT = Path(__file__).resolve().parents[1]

SCHEMA = "prophet_doors/v1"

# --------------------------------------------------------------------------- #
# FROZEN construction constants — changing any of these changes the door, which
# is a prereg amendment (PROPHET_DOORS_PREREG.md §7), not a refactor.
# --------------------------------------------------------------------------- #
TOP_K_THEMES = 5                 # Door T: theme is "hot" iff top-K by emerging_score
REARM_TICKS_MIN = 3              # Door R: master cross is STALE (past the FRESH_TICKS=2 window)
REARM_TICKS_MAX = 15             # Door R: ...but not ancient (a 45d-old cross is a new thesis)
MAX_FLAGS_PER_DOOR = 25          # per door, per night; overflow COUNTED and announced
DEDUPE_SESSIONS = 21             # same ticker, same door: suppressed while a prior flag is younger
THEME_MAX_AGE_DAYS = 7           # Door T fails soft + discloses when the theme artifact is older
RS_LOOKBACK = 63                 # RS percentile lookback (sessions), matches the §2.5 study
MIN_HISTORY = ct.MIN_HISTORY     # 200 — the production gate's own history floor

UNIVERSE_GROUPS = ("breadth", "midcap_breadth", "smallcap_breadth")
THEME_ARTIFACT = ("site", "marketdata", "subsector_rotation.json")
SECTOR_PARQUET = ("data", "breadth", "ticker_sectors.parquet")

DOOR_T = "T"
DOOR_R = "R"
DOORS = (DOOR_T, DOOR_R)

# --------------------------------------------------------------------------- #
# RECORDED-FEATURE constants — ANALYSIS ONLY (prereg §9 addendum, 2026-08-04).
#
# These are NOT frozen construction constants. Nothing below is read by a fire
# condition, the priority sort, the cap, the dedupe, or the grader, so changing
# one changes what an analyst can measure — never which flags exist. The frozen
# door constants are the block above; this block is deliberately separate so the
# two can never be confused.
# --------------------------------------------------------------------------- #
RELAY_HIGH_LOOKBACK = 63     # a "fresh high" = close > the max of the PRIOR 63 closes
RELAY_RECENT_SESSIONS = 3    # relay_count_3d: trailing sessions (inclusive of the flag bar)
RELAY_POSITION_WINDOW = 21   # relay_position: trailing sessions the ordering is read over
RELAY_MIN_MEMBERS = 4        # relay_position is null below this covered-member count
TURNOVER_WINDOW_MAX = 60     # turnover_pctile: window = min(60, sessions actually available)
CLOSES_CACHE_NAME = "_closes_cache.parquet"
VOLUME_CACHE_NAME = "_volume_cache.parquet"
FORESIGHT_ARTIFACT = ("site", "basketdata", "foresight_cascade.json")

#: Every recorded-feature key. Present on EVERY flag row (null when uncomputable) so a null is
#: always a disclosed null and never an absent field.
FEATURE_KEYS = (
    "relay_count_3d",
    "relay_position",
    "relay_members_covered",
    "turnover_pctile",
    "turnover_window",
    "foresight_stage",
    "foresight_covered",
)


def null_features() -> dict[str, Any]:
    """The all-null feature block. Every failure path returns exactly this shape."""
    out: dict[str, Any] = {k: None for k in FEATURE_KEYS}
    out["foresight_covered"] = False
    return out


# --------------------------------------------------------------------------- #
# paths
# --------------------------------------------------------------------------- #
def ledger_dir(root: Path | None = None) -> Path:
    return Path(root or ROOT) / "data" / "prophet_doors"


def flags_path(root: Path | None = None) -> Path:
    return ledger_dir(root) / "flags.jsonl"


def status_path(root: Path | None = None) -> Path:
    return ledger_dir(root) / "status.json"


# --------------------------------------------------------------------------- #
# ledger I/O — append-only JSONL
# --------------------------------------------------------------------------- #
def load_flags(root: Path | None = None) -> list[dict]:
    """Every ledger row, oldest first. [] when the file is absent (first night)."""
    p = flags_path(root)
    if not p.exists():
        return []
    out: list[dict] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError as e:
        log.warning("prophet_doors: flags read failed (%s)", e)
    return out


def append_flags(rows: list[dict], root: Path | None = None) -> int:
    """Append flag rows to the forward ledger. Returns the count written.

    NIGHTLY-ONLY (house law: nightly is the sole advancer of forward ledgers). Off-lane this
    is a no-op returning 0 — the caller still computed the flags, they are simply discarded,
    which is exactly what a re-render or an intraday probe must do.

    Plain append (never a read-modify-rewrite): this ledger only ever GROWS, and a
    full-rewrite writer would silently drop any line a future reader cannot parse. Rows are
    already deduped by :func:`emit`.
    """
    if not _ledger_advance_enabled():
        log.debug("prophet_doors.append_flags: skipped (COLLECT_LANE != nightly)")
        return 0
    if not rows:
        return 0
    p = flags_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return len(rows)


def write_status(doc: dict, root: Path | None = None) -> bool:
    """Atomically write the nightly run-status/disclosure artifact. Nightly-gated like the
    ledger itself — an off-lane run must leave no trace in data/."""
    if not _ledger_advance_enabled():
        log.debug("prophet_doors.write_status: skipped (COLLECT_LANE != nightly)")
        return False
    p = status_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=".status.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return True


# --------------------------------------------------------------------------- #
# inputs
# --------------------------------------------------------------------------- #
def load_universe(root: Path | None = None) -> pd.DataFrame:
    """Wide close matrix over the US cache universe (same three breadth caches the §2 audit
    and `engine.equity_factors._closes("broad")` read). Columns = tickers, index = sessions."""
    wide = _concat_group_caches(root, CLOSES_CACHE_NAME)
    if wide.empty:
        return wide
    # universe floor = the production gate's own history requirement
    return wide.loc[:, wide.notna().sum() >= MIN_HISTORY]


def _concat_group_caches(root: Path | None, name: str) -> pd.DataFrame:
    """Wide frame concatenated across the three breadth caches, deduped columns, datetime index."""
    r = Path(root or ROOT)
    frames = []
    for grp in UNIVERSE_GROUPS:
        p = r / "data" / grp / name
        if p.exists():
            frames.append(pd.read_parquet(p))
    if not frames:
        return pd.DataFrame()
    wide = pd.concat(frames, axis=1)
    wide = wide.loc[:, ~wide.columns.duplicated()].sort_index()
    wide.index = pd.to_datetime(wide.index)
    return wide


def load_volumes(root: Path | None = None) -> pd.DataFrame:
    """Wide share-volume matrix over the same three breadth caches.

    NO history floor, deliberately. These caches were backfilled 2026-05-19 and the MEDIAN
    column carries ~51 non-null sessions, so a `MIN_HISTORY`-style floor would empty the frame.
    :meth:`_RecordedFeatures._turnover` records the window length it actually used
    (``turnover_window``) rather than claiming a 60-session read it cannot support — the US
    Superintelligence Roadmap §4.1 names this cache depth as known debt.
    """
    return _concat_group_caches(root, VOLUME_CACHE_NAME)


def _norm_theme(s: Any) -> str:
    """Casefold + strip every non-alphanumeric. Join key between the rotation artifact's theme
    NAMES and the Foresight Desk's theme slugs/names. Exact-after-normalisation only: a fuzzy
    match would fabricate desk coverage the desk never claimed."""
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def load_foresight_stages(root: Path | None = None) -> tuple[dict[str, str], dict]:
    """({normalised theme key: STAGE}, disclosure) from the Thematic Foresight Desk artifact.

    READ-ONLY join (`scripts/build_foresight.py` owns the artifact; this lane never triggers,
    modifies, or reorders the desk). Both the desk's ``theme`` slug and its display ``name``
    are indexed, because the rotation artifact names themes in display form.

    The two taxonomies were built independently, so coverage is PARTIAL by construction and
    that is the honest state: a theme the desk does not cover records
    ``foresight_stage: null`` + ``foresight_covered: false``, never a guessed stage.
    """
    p = Path(root or ROOT).joinpath(*FORESIGHT_ARTIFACT)
    disc: dict[str, Any] = {"source": "/".join(FORESIGHT_ARTIFACT), "ok": False,
                            "asof": None, "n_themes": 0, "reason": None}
    if not p.exists():
        disc["reason"] = "foresight artifact absent — foresight_stage null on every flag"
        return {}, disc
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        disc["reason"] = (f"foresight artifact unreadable ({type(e).__name__}) — "
                          f"foresight_stage null on every flag")
        return {}, disc
    disc["asof"] = doc.get("asof")
    out: dict[str, str] = {}
    n_staged = 0
    for t in (doc.get("themes") or []):
        stage = t.get("stage")
        if stage is None or str(stage) == "":
            continue
        n_staged += 1
        for key in (t.get("theme"), t.get("name")):
            nk = _norm_theme(key)
            if nk:
                out.setdefault(nk, str(stage))
    disc["ok"] = True
    disc["n_themes"] = n_staged                      # desk themes carrying a STAGE
    disc["n_keys"] = len(out)                        # join keys (slug + display name per theme)
    if not out:
        disc["reason"] = "foresight artifact carries no staged themes"
    return out, disc


def theme_member_index(members: dict[str, dict]) -> dict[str, list[str]]:
    """{theme: sorted member tickers}, inverted from :func:`theme_membership`'s ticker map.

    Inverts on each record's ``themes_hit`` (EVERY hot theme the ticker belongs to), not on the
    single best theme: a ticker whose best theme is A but which also sits in B is a genuine B
    member and must count toward B's relay denominator. Inverting on ``theme`` alone would
    under-count exactly the multi-theme names a relay read cares most about.
    """
    out: dict[str, set[str]] = {}
    for tk, rec in (members or {}).items():
        hits = rec.get("themes_hit") or ([rec.get("theme")] if rec.get("theme") else [])
        for th in hits:
            if th:
                out.setdefault(str(th), set()).add(str(tk))
    return {th: sorted(v) for th, v in out.items()}


def load_sectors(root: Path | None = None) -> dict[str, str]:
    """{ticker: GICS sector}. {} when the map is missing (a null sector is recorded, not fatal)."""
    p = Path(root or ROOT).joinpath(*SECTOR_PARQUET)
    if not p.exists():
        return {}
    try:
        df = pd.read_parquet(p)
        return dict(zip(df["ticker"], df["sector"]))
    except Exception as e:  # noqa: BLE001 — a broken sector map must not kill the doors
        log.warning("prophet_doors: sector map read failed (%s)", e)
        return {}


def theme_membership(root: Path | None = None, *, asof: pd.Timestamp | None = None,
                     k: int = TOP_K_THEMES) -> tuple[dict[str, dict], dict]:
    """({ticker: hottest-theme record}, disclosure).

    Membership source is `site/marketdata/subsector_rotation.json`: themes are ranked by
    ``emerging_score`` desc, the top-k are taken, and a ticker belongs to a theme when it
    appears in the ``members`` list of ANY subsector carrying that theme (the artifact holds
    member lists per SUBSECTOR, not per theme). A ticker in several hot themes is recorded
    under its BEST-RANKED one, with the full hit list kept for the receipt.

    FAIL-SOFT + DISCLOSED (masterplan G0.1 / house epistemics): a missing, unreadable, or
    stale (> THEME_MAX_AGE_DAYS older than the tape) artifact yields ({}, disclosure) — Door T
    then emits NOTHING that night and the reason is printed in the status artifact rather than
    silently degrading into an unconditioned door.
    """
    p = Path(root or ROOT).joinpath(*THEME_ARTIFACT)
    disc: dict[str, Any] = {"source": "/".join(THEME_ARTIFACT), "ok": False,
                            "asof": None, "age_days": None, "reason": None,
                            "top_themes": [], "n_members": 0}
    if not p.exists():
        disc["reason"] = "theme artifact absent — Door T emitted nothing tonight"
        return {}, disc
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        disc["reason"] = f"theme artifact unreadable ({type(e).__name__}) — Door T emitted nothing tonight"
        return {}, disc

    disc["asof"] = doc.get("asof")
    if asof is not None and doc.get("asof"):
        try:
            age = int((pd.Timestamp(asof).normalize() - pd.Timestamp(doc["asof"]).normalize()).days)
            disc["age_days"] = age
            if age > THEME_MAX_AGE_DAYS:
                disc["reason"] = (f"theme artifact stale ({age}d older than the tape, limit "
                                  f"{THEME_MAX_AGE_DAYS}d) — Door T emitted nothing tonight")
                return {}, disc
        except (TypeError, ValueError):
            disc["reason"] = "theme artifact asof unparseable — Door T emitted nothing tonight"
            return {}, disc

    themes = [t for t in (doc.get("themes") or []) if t.get("emerging_score") is not None]
    if not themes:
        disc["reason"] = "theme artifact carries no scored themes — Door T emitted nothing tonight"
        return {}, disc
    themes.sort(key=lambda t: (-float(t["emerging_score"]), str(t.get("theme") or "")))
    top = themes[:k]
    rank_of = {str(t.get("theme")): i + 1 for i, t in enumerate(top)}
    score_of = {str(t.get("theme")): float(t["emerging_score"]) for t in top}
    disc["top_themes"] = [{"theme": str(t.get("theme")), "rank": i + 1,
                           "emerging_score": float(t["emerging_score"])}
                          for i, t in enumerate(top)]

    hits: dict[str, list[dict]] = {}
    for sub in (doc.get("subsectors") or []):
        th = str(sub.get("theme") or "")
        if th not in rank_of:
            continue
        for m in (sub.get("members") or []):
            tk = (m.get("t") if isinstance(m, dict) else m)
            if not tk:
                continue
            hits.setdefault(str(tk), []).append(
                {"theme": th, "theme_rank": rank_of[th], "theme_score": score_of[th],
                 "subsector": str(sub.get("key") or ""),
                 "subsector_rank": sub.get("rank")})

    out: dict[str, dict] = {}
    for tk, lst in hits.items():
        lst.sort(key=lambda r: (r["theme_rank"], r["subsector"]))
        best = dict(lst[0])
        best["subsectors"] = sorted({r["subsector"] for r in lst})
        best["themes_hit"] = sorted({r["theme"] for r in lst})
        out[tk] = best
    disc["ok"] = True
    disc["n_members"] = len(out)
    return out, disc


# --------------------------------------------------------------------------- #
# completed-bucket helper (PIT: never fire off the in-progress resample tail)
# --------------------------------------------------------------------------- #
def completed_tf(c: pd.Series, n: int) -> tuple[pd.Series, pd.Series]:
    """``confluence_tiers._tf_bars(c, n)`` with the IN-PROGRESS tail bucket dropped.

    `_tf_bars` resamples on an ``{n}B`` grid whose bins are labelled by bin START, so the
    right-label truncation `confluence_tiers._completed_resample` uses for W-FRI / 2W-FRI
    (labelled by period END) does not transfer. A bin is provably CLOSED whenever a LATER bin
    already holds data, so only the FINAL bin needs a test: it closed once the tape printed
    through its last business day (label + n-1 business days). A holiday inside that bin makes
    the test conservative — the bin is held open one extra session rather than fired early,
    which is the correct direction for a point-in-time gate.

    This is the guard behind `cascade()`'s ``provisional`` flag (T3 repaints at a measured
    23.8% US because it IS read off the incomplete tail). Door R refuses to repaint.
    """
    s, known = _tf_bars(c, n)
    if len(s) == 0:
        return s, known
    last_obs = c.index.max()
    tail_close = s.index[-1] + pd.tseries.offsets.BDay(n - 1)
    if last_obs < tail_close:
        return s.iloc[:-1], known.iloc[:-1]
    return s, known


# --------------------------------------------------------------------------- #
# door fire conditions
# --------------------------------------------------------------------------- #
def door_t_fires(v: dict | None) -> bool:
    """Door T trigger leg: the incumbent VALIDATED construction, byte-unmodified.

    `is_buyable` already requires ``eligible``; both are asserted so the contract reads
    explicitly and a future change to either one cannot silently widen the door.
    """
    return bool(v) and bool(v.get("eligible")) and signal_gate.is_buyable(v)


def door_r_legs(v: dict | None, close: pd.Series) -> dict:
    """Every Door R leg, evaluated independently, plus ``fires`` = their conjunction.

    Legs (all five must hold):
      1. ``not eligible``      — the incumbent gate is NOT offering this name today.
      2. ticks ∈ [3, 15]       — the master cross is stale (past FRESH_TICKS=2) but recent.
      3. ``above200 is True``  — trend intact. ``is True`` is deliberate: an unanalysed
      4. ``weekly_bull is True``  None must never read as an intact trend (build_stock_library
                                  leaders-lane convention).
      5. re-arm confluence     — 2D RSI-MACD crossed up on the latest COMPLETED 2D bucket
                                 AND 3D StochRSI K ≥ D on the latest COMPLETED 3D bucket.

    Returns a dict of the leg booleans + the recorded features, so the tests (and the prereg)
    can pin each leg's positive and negative case separately.
    """
    out: dict[str, Any] = {
        "not_eligible": False, "ticks_in_window": False, "above200": False,
        "weekly_bull": False, "x2d_completed": False, "stoch3d_kd": False,
        "fires": False, "ticks": None, "k3": None, "d3": None,
    }
    if not v:
        return out
    ticks = v.get("ticks")
    out["not_eligible"] = (v.get("eligible") is not True)
    out["ticks"] = ticks
    out["ticks_in_window"] = bool(
        isinstance(ticks, (int, float)) and not isinstance(ticks, bool)
        and REARM_TICKS_MIN <= int(ticks) <= REARM_TICKS_MAX
    )
    out["above200"] = (v.get("above200") is True)
    out["weekly_bull"] = (v.get("weekly_bull") is True)
    # The structural legs are cheap; only pay for the resample math when they all hold.
    if not (out["not_eligible"] and out["ticks_in_window"]
            and out["above200"] and out["weekly_bull"]):
        return out
    try:
        c = close.dropna()
        if not isinstance(c.index, pd.DatetimeIndex):
            c = c.copy()
            c.index = pd.to_datetime(c.index)
        if len(c) < MIN_HISTORY:
            return out
        sm, _smk = completed_tf(c, 2)
        m2, s2 = _rsi_macd(sm)
        x2 = _xup(m2, s2)
        out["x2d_completed"] = bool(len(x2) and bool(x2.iloc[-1]))

        ss3, _sk3 = completed_tf(c, 3)
        k3, d3 = _stoch_rsi_kd(ss3)
        if len(k3):
            kv, dv = float(k3.iloc[-1]), float(d3.iloc[-1])
            if kv == kv and dv == dv:                      # NaN warmup -> leg stays False
                out["k3"], out["d3"] = round(kv, 2), round(dv, 2)
                out["stoch3d_kd"] = kv >= dv
    except Exception as e:  # noqa: BLE001 — one bad series must never kill the nightly door
        log.debug("prophet_doors: door R legs failed (%s)", e)
        return out
    out["fires"] = bool(out["x2d_completed"] and out["stoch3d_kd"])
    return out


# --------------------------------------------------------------------------- #
# dedupe
# --------------------------------------------------------------------------- #
def _sessions_since(index: pd.DatetimeIndex, prior_date: Any, asof: pd.Timestamp) -> int | None:
    """Trading sessions on the cache calendar in (prior_date, asof]. None if undatable."""
    try:
        p = pd.Timestamp(prior_date)
    except (TypeError, ValueError):
        return None
    return int(((index > p) & (index <= pd.Timestamp(asof))).sum())


def recent_by_door(rows: list[dict], index: pd.DatetimeIndex,
                   asof: pd.Timestamp) -> dict[tuple[str, str], int]:
    """{(door, ticker): sessions since the most recent prior flag} for rows inside the
    dedupe window. Only the freshest prior flag per (door, ticker) matters."""
    best: dict[tuple[str, str], int] = {}
    for r in rows:
        door, tk, d = r.get("door"), r.get("ticker"), r.get("date")
        if not (door and tk and d):
            continue
        n = _sessions_since(index, d, asof)
        if n is None:
            continue
        key = (str(door), str(tk))
        if key not in best or n < best[key]:
            best[key] = n
    return best


# --------------------------------------------------------------------------- #
# recorded features — ANALYSIS ONLY (prereg §9 addendum, 2026-08-04)
# --------------------------------------------------------------------------- #
class _RecordedFeatures:
    """Per-flag analysis features. Built once per :func:`emit`, queried per KEPT row.

    ZERO EFFECT ON THE DOORS, structurally. :func:`emit` decides a night's fire set — every
    fire condition, the priority sort, the cap and the dedupe — and only THEN calls
    :meth:`compute` on the rows it already kept. Nothing here can add, drop, or reorder a flag,
    and :meth:`compute` swallows its own failures into :func:`null_features` so a broken input
    cannot change a flag set either.

    RUNTIME. Bounded by construction: at most ``2 * MAX_FLAGS_PER_DOOR`` (50) queries a night,
    and the one vectorised pass is over the trailing
    ``RELAY_HIGH_LOOKBACK + RELAY_POSITION_WINDOW`` (84) sessions of the HOT-THEME MEMBER
    columns of the universe frame already in memory — never a second full-universe sweep. Every
    input is loaded lazily, so a night with no flags pays nothing.

    The features
    ------------
    ``relay_count_3d`` / ``relay_position`` / ``relay_members_covered``
        Where in its theme's relay the name is firing. A "fresh high" is
        ``close > max(prior RELAY_HIGH_LOOKBACK closes)`` — the session a NEW 63-session
        closing high printed, not merely a session sitting at one.
    ``turnover_pctile`` / ``turnover_window``
        Admission-day share volume against the name's OWN recent history.
    ``foresight_stage`` / ``foresight_covered``
        The Thematic Foresight Desk's stage for the flag's theme, when the desk covers it.
    """

    def __init__(self, root: Path, px: pd.DataFrame, members: dict[str, dict],
                 *, enabled: bool = True) -> None:
        self._root = root
        self._px = px
        self._enabled = bool(enabled)
        self._by_theme = theme_member_index(members) if self._enabled else {}
        self._breakout: pd.DataFrame | None = None
        self._vol: pd.DataFrame | None = None
        self._stages: dict[str, str] | None = None
        self._relay_disc: dict[str, Any] = {"consulted": False}
        self._vol_disc: dict[str, Any] = {"consulted": False}
        self._fs_disc: dict[str, Any] = {"consulted": False}

    # ---- inputs (lazy) ---------------------------------------------------- #
    def _breakouts(self) -> pd.DataFrame:
        """Boolean frame (trailing ``RELAY_POSITION_WINDOW`` sessions × covered hot-theme
        members): True where that session printed a NEW ``RELAY_HIGH_LOOKBACK``-session high.

        ``rolling(63).max().shift(1)`` compares the close against the max of the PRIOR 63
        closes, so the flag bar itself is never inside its own comparison window. A tail of
        ``63 + 21`` rows makes exactly the last 21 rows valid, which is the window relay
        position is read over.

        COVERAGE IS STRICT. A member is covered only when its closes are complete across the
        whole 84-session tail. A hole would make ``close > NaN`` evaluate False, i.e. would
        silently record "did not break out" for a name nobody could measure; requiring
        completeness turns that into an honest exclusion from ``relay_members_covered``.
        """
        if self._breakout is not None:
            return self._breakout
        need = RELAY_HIGH_LOOKBACK + RELAY_POSITION_WINDOW
        wanted = {t for lst in self._by_theme.values() for t in lst}
        cols = [c for c in self._px.columns if str(c) in wanted]
        disc: dict[str, Any] = {"consulted": True, "members_indexed": len(wanted),
                                "n_covered": 0, "window_sessions": RELAY_POSITION_WINDOW,
                                "high_lookback": RELAY_HIGH_LOOKBACK, "reason": None}
        if not cols:
            disc["reason"] = "no hot-theme member is present in the close cache"
            self._relay_disc = disc
            self._breakout = pd.DataFrame(dtype=bool)
            return self._breakout
        tail = self._px.loc[:, cols].tail(need)
        tail.columns = [str(c) for c in tail.columns]
        if len(tail) < need:
            disc["reason"] = (f"close cache holds {len(tail)} sessions, "
                              f"{need} needed for a {RELAY_POSITION_WINDOW}-session relay read")
            self._relay_disc = disc
            self._breakout = pd.DataFrame(dtype=bool)
            return self._breakout
        covered = tail.columns[tail.notna().all(axis=0)]
        tail = tail.loc[:, covered]
        bo = (tail > tail.rolling(RELAY_HIGH_LOOKBACK).max().shift(1)).tail(RELAY_POSITION_WINDOW)
        disc["n_covered"] = int(bo.shape[1])
        self._relay_disc = disc
        self._breakout = bo
        return self._breakout

    def _volumes(self) -> pd.DataFrame:
        if self._vol is None:
            v = load_volumes(self._root)
            if not v.empty:
                v.columns = [str(c) for c in v.columns]
            self._vol = v
            self._vol_disc = {
                "consulted": True,
                "source": f"data/{{{','.join(UNIVERSE_GROUPS)}}}/{VOLUME_CACHE_NAME}",
                "ok": not v.empty, "n_tickers": int(v.shape[1]) if not v.empty else 0,
                "last_session": str(v.index.max().date()) if not v.empty else None,
                "window_max": TURNOVER_WINDOW_MAX,
                "reason": None if not v.empty else
                          "volume cache absent or empty — turnover_pctile null on every flag",
            }
        return self._vol

    def _foresight(self) -> dict[str, str]:
        if self._stages is None:
            self._stages, disc = load_foresight_stages(self._root)
            self._fs_disc = {"consulted": True} | disc
        return self._stages

    # ---- features --------------------------------------------------------- #
    def _relay(self, ticker: str, theme: Any) -> dict[str, Any]:
        """Relay count / position for ``ticker`` inside ``theme``.

        ``relay_count_3d`` — OTHER covered members of the theme that printed a fresh high in
        the trailing ``RELAY_RECENT_SESSIONS`` sessions, the flag bar included.

        ``relay_position`` — OTHER covered members whose fresh high printed STRICTLY BEFORE the
        flag bar inside the ``RELAY_POSITION_WINDOW``, over the theme's covered-member count.
        0 = first mover; → 1 = late relay. Simultaneous is not earlier: a peer printing on the
        flag bar itself counts toward the COUNT but not the POSITION.

        The denominator is the theme's whole covered-member set, so it is identical for every
        flag in that theme on that night and the positions are comparable to each other. The
        numerator excludes the flag's own name. A flag that is ITSELF covered is therefore
        bounded at ``(n−1)/n``; a flag the coverage rule excluded (a hole in its own tail, or a
        name outside the doors' universe) still reads its theme's relay, against all ``n``
        covered peers. Null below ``RELAY_MIN_MEMBERS`` covered members — a "position" among
        two names is an artefact of the denominator, not a relay reading. ``n`` is always
        disclosed as ``relay_members_covered``.
        """
        out: dict[str, Any] = {"relay_count_3d": None, "relay_position": None,
                               "relay_members_covered": None}
        if not theme:
            return out                     # Door R on a name in no hot theme — a disclosed null
        bo = self._breakouts()
        if bo.empty:
            return out
        mem = [m for m in self._by_theme.get(str(theme), ()) if m in bo.columns]
        out["relay_members_covered"] = len(mem)
        if not mem:
            return out
        others = [m for m in mem if m != str(ticker)]
        sub = bo.loc[:, others] if others else None
        out["relay_count_3d"] = (0 if sub is None
                                 else int(sub.tail(RELAY_RECENT_SESSIONS).any(axis=0).sum()))
        if len(mem) >= RELAY_MIN_MEMBERS:
            earlier = 0 if sub is None else int(sub.iloc[:-1].any(axis=0).sum())
            out["relay_position"] = round(earlier / len(mem), 4)
        return out

    def _turnover(self, ticker: str) -> dict[str, Any]:
        """Admission-day share volume as a percentile of the name's OWN trailing window.

        Window = the last ``min(TURNOVER_WINDOW_MAX, available)`` non-null sessions ending ON
        the flag bar; ``turnover_window`` records the length actually used. The percentile is
        the share of that window at or below the flag-bar volume (1.0 = the window's highest).

        NEVER IMPUTED. If the cache carries no observation ON the flag bar there is no
        admission-day volume, so both fields are null — reading a stale session's volume as
        "admission day" would fabricate the feature. A single-observation window is likewise
        null: its percentile is definitionally 1.0 and carries no information.
        """
        out: dict[str, Any] = {"turnover_pctile": None, "turnover_window": None}
        vol = self._volumes()
        if vol.empty or str(ticker) not in vol.columns:
            return out
        asof = self._px.index[-1]
        s = vol[str(ticker)]
        s = s.loc[s.index <= asof].dropna()
        if s.empty or s.index[-1] != asof:
            return out
        w = s.iloc[-min(TURNOVER_WINDOW_MAX, len(s)):]
        out["turnover_window"] = int(len(w))
        if len(w) >= 2:
            out["turnover_pctile"] = round(float((w <= float(w.iloc[-1])).mean()), 4)
        return out

    def _stage(self, theme: Any) -> dict[str, Any]:
        """Foresight Desk stage for the flag's theme, or a disclosed non-coverage."""
        out: dict[str, Any] = {"foresight_stage": None, "foresight_covered": False}
        if not theme:
            return out
        stage = self._foresight().get(_norm_theme(theme))
        if stage:
            out["foresight_stage"] = str(stage)
            out["foresight_covered"] = True
        return out

    def compute(self, ticker: str, theme: Any) -> dict[str, Any]:
        """The full feature block for one KEPT flag. ``{}`` when features are disabled."""
        if not self._enabled:
            return {}
        try:
            return {**self._relay(ticker, theme), **self._turnover(ticker), **self._stage(theme)}
        except Exception as e:  # noqa: BLE001 — an analysis feature may never break the lane
            log.warning("prophet_doors: recorded features failed for %s (%s)", ticker, e)
            return null_features()

    def disclosure(self) -> dict[str, Any]:
        """What each feature source actually offered tonight — the "nulls printed" receipt."""
        return {"enabled": self._enabled, "keys": list(FEATURE_KEYS),
                "relay": dict(self._relay_disc), "turnover": dict(self._vol_disc),
                "foresight": dict(self._fs_disc)}


# --------------------------------------------------------------------------- #
# the nightly run
# --------------------------------------------------------------------------- #
def emit(root: Path | None = None, *, dry_run: bool = False,
         universe: pd.DataFrame | None = None, features: bool = True) -> dict:
    """Evaluate both doors on the committed caches and (unless ``dry_run``) accrue the flags.

    Returns the run document: per-door flag rows, overflow counts, dedupe counts, the theme
    disclosure, and timing. ``dry_run=True`` writes NOTHING anywhere — it is the PR-receipt
    and local-preview path. On the nightly lane the ledger append is additionally gated by
    :func:`append_flags`, so an off-lane nightly invocation is also a no-op.

    ``features=False`` records no analysis feature block. It exists so the fire set can be
    compared with features on and off (``TestFireInvariance``); the two MUST be identical,
    because the feature computer only ever sees rows the doors already kept. Production always
    runs with features on.
    """
    t0 = time.time()
    root = Path(root or ROOT)
    px = load_universe(root) if universe is None else universe
    run = {
        "schema": SCHEMA,
        "run_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "asof": None, "n_universe": 0,
        "flags": {DOOR_T: [], DOOR_R: []},
        "overflow": {DOOR_T: 0, DOOR_R: 0},
        "deduped": {DOOR_T: 0, DOOR_R: 0},
        "candidates": {DOOR_T: 0, DOOR_R: 0},
        "theme_source": {}, "feature_source": {}, "appended": 0, "dry_run": bool(dry_run),
        "runtime_s": None,
    }
    if px is None or px.empty:
        run["note"] = "universe cache empty — both doors emitted nothing"
        print("::warning title=prophet_doors::universe cache empty; no doors evaluated", flush=True)
        run["runtime_s"] = round(time.time() - t0, 1)
        return run

    di = px.index
    asof = di[-1]
    run["asof"] = str(asof.date())
    run["n_universe"] = int(px.shape[1])

    members, theme_disc = theme_membership(root, asof=asof)
    run["theme_source"] = theme_disc
    if not theme_disc.get("ok"):
        print(f"::warning title=prophet_doors_theme::{theme_disc.get('reason')}", flush=True)

    sectors = load_sectors(root)
    # RS percentile over the cache universe at the signal bar (the §2.5 study's construction).
    rs_pct = (px / px.shift(RS_LOOKBACK) - 1.0).rank(axis=1, pct=True).iloc[-1]

    def _rs(t: str) -> float | None:
        v = rs_pct.get(t)
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        return round(f, 4) if f == f else None

    t_cand: list[tuple] = []
    r_cand: list[tuple] = []
    for tk in px.columns:
        c = px[tk].dropna()
        if len(c) < MIN_HISTORY:
            continue
        try:
            v = signal_gate.gate(str(tk), c)
        except Exception as e:  # noqa: BLE001 — the gate is documented never-raises; belt+braces
            log.debug("prophet_doors: gate failed for %s (%s)", tk, e)
            continue

        if members and str(tk) in members and door_t_fires(v):
            m = members[str(tk)]
            t_cand.append((
                int(m["theme_rank"]), signal_gate.tier_rank(v), str(tk),
                {
                    "theme": m["theme"], "theme_rank": int(m["theme_rank"]),
                    "theme_score": round(float(m["theme_score"]), 4),
                    "subsector": m["subsector"], "subsectors": m["subsectors"],
                    "themes_hit": m["themes_hit"],
                    "tier": v.get("tier_cascade"), "tier_sub": v.get("tier_sub"),
                    "ticks": v.get("ticks"), "rs63_pctile": _rs(str(tk)),
                    "sector": sectors.get(str(tk)),
                    "hist_d2": v.get("hist_d2"), "hist_d3": v.get("hist_d3"),
                },
            ))

        legs = door_r_legs(v, c)
        if legs["fires"]:
            m = members.get(str(tk)) or {}
            r_cand.append((
                int(legs["ticks"]), str(tk),
                {
                    "ticks_since_master": int(legs["ticks"]),
                    "hist_d2": v.get("hist_d2"), "hist_d3": v.get("hist_d3"),
                    "k3": legs["k3"], "d3": legs["d3"],
                    "rs63_pctile": _rs(str(tk)), "sector": sectors.get(str(tk)),
                    "theme": m.get("theme"), "theme_rank": m.get("theme_rank"),
                    "theme_score": (round(float(m["theme_score"]), 4)
                                    if m.get("theme_score") is not None else None),
                    "above200": True, "weekly_bull": True,
                },
            ))

    run["candidates"][DOOR_T] = len(t_cand)
    run["candidates"][DOOR_R] = len(r_cand)

    # Deterministic priority BEFORE the cap, frozen in the prereg:
    #   Door T — hottest theme first, then the cascade's own entry-quality rank, then ticker.
    #   Door R — freshest re-arm (fewest ticks since the master cross) first, then ticker.
    t_cand.sort(key=lambda x: (x[0], x[1], x[2]))
    r_cand.sort(key=lambda x: (x[0], x[1]))

    prior = recent_by_door(load_flags(root), di, asof)
    asof_str = str(asof.date())
    rows_by_door: dict[str, list[dict]] = {DOOR_T: [], DOOR_R: []}
    fx = _RecordedFeatures(root, px, members, enabled=features)

    for door, cands in ((DOOR_T, t_cand), (DOOR_R, r_cand)):
        kept: list[dict] = []
        for cand in cands:
            tk, feats = cand[-2], cand[-1]
            n_since = prior.get((door, tk))
            if n_since is not None and n_since < DEDUPE_SESSIONS:
                run["deduped"][door] += 1
                continue
            if len(kept) >= MAX_FLAGS_PER_DOOR:
                run["overflow"][door] += 1
                continue
            kept.append({"schema": SCHEMA, "date": asof_str, "door": door,
                         "ticker": tk, "features": feats})
        # Recorded features are attached HERE — after every fire decision, the priority sort,
        # the cap and the dedupe are already settled, and only to rows that survived them
        # (≤ MAX_FLAGS_PER_DOOR per door). Nothing above this line can read them, which is what
        # makes "features change no flag" structural rather than a promise (prereg §9).
        for row in kept:
            row["features"].update(fx.compute(row["ticker"], row["features"].get("theme")))
        rows_by_door[door] = kept
        run["flags"][door] = kept
        if run["overflow"][door]:
            # No silent caps: the count of dropped candidates is announced, not swallowed.
            print(f"::warning title=prophet_doors_cap::door {door} capped at "
                  f"{MAX_FLAGS_PER_DOOR}; {run['overflow'][door]} candidate(s) dropped "
                  f"(asof {asof_str})", flush=True)

    all_rows = rows_by_door[DOOR_T] + rows_by_door[DOOR_R]
    run["feature_source"] = fx.disclosure()
    run["runtime_s"] = round(time.time() - t0, 1)
    if not dry_run:
        run["appended"] = append_flags(all_rows, root)
        write_status({k: v for k, v in run.items() if k != "flags"} |
                     {"flag_tickers": {d: [r["ticker"] for r in rows_by_door[d]] for d in DOORS}},
                     root)
    log.info("prophet_doors: asof=%s doorT=%d doorR=%d (overflow %d/%d, deduped %d/%d) %.1fs",
             asof_str, len(rows_by_door[DOOR_T]), len(rows_by_door[DOOR_R]),
             run["overflow"][DOOR_T], run["overflow"][DOOR_R],
             run["deduped"][DOOR_T], run["deduped"][DOOR_R], run["runtime_s"])
    return run
