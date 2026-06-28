"""Signal-sanity invariants — a CORRECTNESS tripwire over the engine's published boards.

The dead-man's switch (``scripts/healthcheck.py``) is a *liveness* probe: it fires when the
pipeline STOPS or a broad swath of *collectors* break. It is structurally blind to the more
dangerous failure — a signal that runs to completion but emits **confidently wrong numbers**.
That class (a ``top_n`` cut that drops 800 names to 16; a lens that silently goes constant; a
builder that freezes while siblings advance) sails straight through a liveness check, and —
because the Flagship book and the Autonomous Brain both select from these same boards — a
single such break propagates to BOTH books at once with no independent check left.

This module is the missing correctness layer. It asserts cheap, **ground-truth-free** invariants
on the per-ticker boards that feed the books — no "right answer" required, just the fingerprints
of a broken signal:

  * COVERAGE   — a board that should carry ~N names suddenly carries far fewer  → break.
  * DEGENERACY — a score column that should vary is all-null or all-one-value   → break.
  * FREEZE     — ``as_of`` advanced to a new date but the signal values are byte-identical to
                 the prior vintage (the builder didn't actually recompute)       → break.
  * STALENESS  — a board lags the freshest sibling (or now) by too many days     → warn.
  * DRIFT      — a board's score distribution jumped far beyond its prior vintage → warn.

It is pure (no I/O beyond the optional ``load_payloads`` reader) and **stdlib-only**, so it runs
both in the daily build (``scripts/signal_sanity.py``, blocking) and folded into the no-pip
heartbeat (``scripts/healthcheck.py``). Degrade-never-raise: a malformed board degrades to a
reported failure, never an exception that takes the check down with it.

The boards + the specific fields that carry their signal were mapped against the consumer,
``Mastermind/brain/intake.py`` — see ``SURFACES`` for the per-board rationale (which constant
columns are by-design and deliberately NOT flagged).
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable

# Tunable defaults (overridable via the config.yml ``signal_sanity:`` block).
DEFAULTS = {
    "stale_days": 5,        # board as_of older than now by this many days → warn (absolute)
    "rel_stale_days": 2,    # board lags the freshest sibling by this many days → warn (relative)
    "max_drift_pct": 0.5,   # primary-score mean moved > this fraction vs prior vintage → warn
    "min_pop": 8,           # need at least this many records in a subset to judge degeneracy
    "require_all": True,    # a missing REQUIRED board is a hard failure
}


# ---------------------------------------------------------------------------
# board specs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScoreField:
    """A numeric column expected to VARY across names — a degeneracy/drift sentinel."""
    name: str
    get: Callable[[dict], "float | None"]
    subset: "Callable[[dict], bool] | None" = None   # restrict to the rows that should carry it
    primary: bool = False                            # the field used for drift
    check_degeneracy: bool = True                    # False = naturally-uniform column (count/context-only)
    min_pop: "int | None" = None                     # per-field override of the global degeneracy floor


@dataclass(frozen=True)
class Surface:
    key: str
    path: str                                # site-relative path
    as_of_key: str                           # top-level date field ('as_of' — news uses 'asof')
    extract: Callable[[dict], list]          # doc -> list of per-ticker record dicts
    ticker: Callable[[dict], "str | None"]
    coverage: Callable[[list], int]          # how to count "live" names (news: those with news)
    coverage_floor: int
    scores: tuple                            # tuple[ScoreField, ...]
    label: str
    required: bool = True
    rel_stale_exempt: bool = False           # skip the cross-surface relative-staleness warn (different as_of basis)


def _num(v) -> "float | None":
    """Coerce to float, excluding bools and NaN; everything else → None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f if math.isfinite(f) else None  # drop NaN AND ±inf (a div-by-zero builder emits inf)
    return None


def _dotted(rec: dict, *path):
    cur = rec
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _non_quiet(r: dict) -> bool:
    return r.get("state") not in (None, "QUIET")


def _has_news(r: dict) -> bool:
    n = _num(r.get("n_recent"))
    return n is not None and n >= 1


# The six per-ticker boards both books select from. Score fields are chosen to AVOID the
# by-design constants (briefing divergences.lean≡1, hub falsifier_penalty≡1, the compressed
# conviction.score in the top slice) so a healthy build never false-trips.
SURFACES: tuple = (
    Surface(
        key="standouts", path="factordata/us_standouts.json", as_of_key="as_of",
        extract=lambda d: list(d.get("buy") or d.get("standouts") or []),
        ticker=lambda r: r.get("ticker"),
        coverage=len, coverage_floor=40,
        scores=(
            # conviction.composite_z is the granular sentinel; conviction.score is naturally
            # compressed (85-100) in the top slice and is NOT a degeneracy signal.
            ScoreField("conviction.composite_z", lambda r: _num(_dotted(r, "conviction", "composite_z")), primary=True),
            ScoreField("alpha", lambda r: _num(r.get("alpha"))),
        ),
        label="engine buy-board",
        # standouts stamps as_of with the last TRADING day (from alpha.json); the other five stamp
        # the build/calendar date — so it structurally lags by 1-3d every weekend. Its absolute
        # staleness check still catches a genuinely frozen board; exempt it from the relative one.
        rel_stale_exempt=True,
    ),
    Surface(
        key="briefing", path="intelligence/briefing.json", as_of_key="as_of",
        extract=lambda d: list(d.get("priority_queue") or []),
        ticker=lambda r: r.get("ticker"),
        coverage=len, coverage_floor=8,
        scores=(
            ScoreField("priority", lambda r: _num(r.get("priority")), primary=True),
            ScoreField("strength", lambda r: _num(r.get("strength"))),
        ),
        label="Phase-5 priority queue",
    ),
    Surface(
        key="radar", path="basketdata/radar_ticker.json", as_of_key="as_of",
        extract=lambda d: list(d.get("tickers") or []),
        ticker=lambda r: r.get("ticker"),
        coverage=len, coverage_floor=40,
        scores=(
            # edge_score is populated on every row but only the non-QUIET subset is consumed; judge
            # degeneracy there. It is a coarse 0-100 INTEGER, so on a legitimately low-divergence day
            # a small non-QUIET set can share one value — require a larger population before judging
            # (min_pop=20) so a quiet regime can't false-trip the zero-variance check.
            ScoreField("edge_score", lambda r: _num(r.get("edge_score")), subset=_non_quiet, primary=True, min_pop=20),
        ),
        label="divergence radar",
    ),
    Surface(
        key="altdata", path="altdata/mastermind.json", as_of_key="as_of",
        extract=lambda d: list(d.get("signals") or []),
        ticker=lambda r: r.get("ticker"),
        coverage=len, coverage_floor=8,
        scores=(
            ScoreField("signal_score", lambda r: _num(r.get("signal_score")), primary=True),
            ScoreField("weighted_score", lambda r: _num(r.get("weighted_score"))),
        ),
        label="alt-data desk",
    ),
    Surface(
        key="news", path="news/by_ticker.json", as_of_key="asof",   # NB: 'asof', no underscore
        extract=lambda d: [{"ticker": k, **(v or {})} for k, v in (d.get("tickers") or {}).items()],
        ticker=lambda r: r.get("ticker"),
        # ~48% of tickers legitimately have n_recent==0; "coverage" = names carrying >=1 story.
        coverage=lambda recs: sum(1 for r in recs if _has_news(r)),
        coverage_floor=100,
        scores=(
            # Both columns are naturally uniform in valid states, so they are NOT degeneracy-judged
            # (the coverage floor already proves the news pipeline ran): n_recent is a tiny headline
            # COUNT that legitimately goes all-1 on a quiet day, and sentiment_score is Polygon-only
            # enrichment that legitimately goes all-0 on a Polygon outage while RSS headlines flow.
            ScoreField("n_recent", lambda r: _num(r.get("n_recent")), subset=_has_news, primary=True,
                       check_degeneracy=False),
            ScoreField("sentiment_score", lambda r: _num(r.get("sentiment_score")), subset=_has_news,
                       check_degeneracy=False),
        ),
        label="news flow",
    ),
    Surface(
        key="intel_hub", path="intel_hub/hub.json", as_of_key="as_of",
        extract=lambda d: list(d.get("command") or []),
        ticker=lambda r: r.get("ticker"),
        coverage=len, coverage_floor=8,
        scores=(
            ScoreField("composite_conviction", lambda r: _num(r.get("composite_conviction")), primary=True),
            ScoreField("opportunity_score", lambda r: _num(r.get("opportunity_score"))),
            ScoreField("edge_remaining", lambda r: _num(r.get("edge_remaining"))),
        ),
        label="5-desk command",
    ),
)

_BY_KEY = {s.key: s for s in SURFACES}


# ---------------------------------------------------------------------------
# evaluation (pure)
# ---------------------------------------------------------------------------

def _parse_date(s) -> "date | None":
    if not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _fingerprint(s: Surface, recs: list) -> str:
    """A hash of the SIGNAL VALUES only (ticker + score fields), sorted by ticker — robust to
    presentational churn (e.g. spark_svg), so a true content-freeze is detectable."""
    rows = []
    for r in recs:
        if not isinstance(r, dict):
            continue
        rows.append([str(s.ticker(r)), [[f.name, f.get(r)] for f in s.scores]])
    # sort on the FULL row (ticker + values), not ticker alone — so duplicate/None tickers can't
    # leave the order (and thus the hash) dependent on the builder's iteration order.
    rows.sort(key=lambda x: (x[0], json.dumps(x[1], sort_keys=True, default=str)))
    blob = json.dumps(rows, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _cfg(cfg: dict, key: str):
    return (cfg or {}).get(key, DEFAULTS[key])


def evaluate_surface(s: Surface, doc, prior, *, now: datetime, cfg: dict) -> dict:
    """Evaluate one board. Returns {key,label,ok,fails,warns,as_of,n,coverage,row}. Never raises."""
    res = {"key": s.key, "label": s.label, "ok": True, "fails": [], "warns": [],
           "as_of": None, "n": 0, "coverage": 0, "row": None}

    if doc is None:
        if s.required and _cfg(cfg, "require_all"):
            res["ok"] = False
            res["fails"].append(f"{s.key}: board missing/unreadable ({s.path})")
        else:
            res["warns"].append(f"{s.key}: board absent ({s.path})")
        return res

    try:
        recs = [r for r in (s.extract(doc) or []) if isinstance(r, dict)]
    except Exception as e:  # noqa: BLE001 — a malformed board is a failure, not a crash
        res["ok"] = False
        res["fails"].append(f"{s.key}: could not parse records ({e!r})")
        return res

    as_of = doc.get(s.as_of_key)
    res["as_of"] = as_of
    res["n"] = len(recs)
    cov = int(s.coverage(recs)) if recs else 0
    res["coverage"] = cov
    _floors = (cfg or {}).get("floors")
    floor = int((_floors if isinstance(_floors, dict) else {}).get(s.key, s.coverage_floor))
    min_pop = int(_cfg(cfg, "min_pop"))

    # 1. coverage / structure
    if not recs:
        res["ok"] = False
        res["fails"].append(f"{s.key}: no records ({s.path} container empty)")
    elif cov < floor:
        res["ok"] = False
        res["fails"].append(f"{s.key}: coverage {cov} < floor {floor} ({s.label})")

    # 2. degeneracy — every signal column flagged check_degeneracy should vary
    score_stats: dict = {}
    for f in s.scores:
        subset = [r for r in recs if (f.subset is None or f.subset(r))]
        nonnull = [v for v in (f.get(r) for r in subset) if v is not None]
        uniq = len({round(v, 6) for v in nonnull})
        score_stats[f.name] = {
            "n_sub": len(subset), "pop": len(nonnull), "uniq": uniq,
            "mean": statistics.fmean(nonnull) if nonnull else None,
            "std": statistics.pstdev(nonnull) if len(nonnull) > 1 else (0.0 if nonnull else None),
        }
        if not f.check_degeneracy:                       # count/context-only column — never a fail
            continue
        fmp = int(f.min_pop if f.min_pop is not None else min_pop)
        if len(subset) >= fmp:
            if not nonnull:
                res["ok"] = False
                res["fails"].append(f"{s.key}.{f.name}: all {len(subset)} values null (signal column dead)")
            elif uniq <= 1:
                res["ok"] = False
                res["fails"].append(f"{s.key}.{f.name}: all {len(nonnull)} values identical (={nonnull[0]!r}) — zero-variance signal")
        elif f.subset is not None and recs:
            # the CONSUMED subset shrank below the bar to judge it — itself a possible break, so
            # surface it (a warn) rather than silently disabling the degeneracy check.
            res["warns"].append(
                f"{s.key}.{f.name}: consumed subset only {len(subset)} rows (< {fmp}) — degeneracy not judged")

    fp = _fingerprint(s, recs)

    # 3. absolute staleness
    d = _parse_date(as_of)
    stale_days = float(_cfg(cfg, "stale_days"))
    if d is not None:
        age = (now.date() - d).days
        if age > stale_days:
            res["warns"].append(f"{s.key}: as_of {as_of} is {age}d old (> {stale_days:.0f}d)")
    elif as_of is not None:
        res["warns"].append(f"{s.key}: unparseable as_of {as_of!r}")

    # 4. freeze + drift vs the previous DISTINCT vintage
    if prior and prior.get("as_of") and as_of and prior.get("as_of") != as_of:
        if prior.get("fingerprint") == fp:
            res["ok"] = False
            res["fails"].append(
                f"{s.key}: CONTENT FROZEN — as_of advanced {prior['as_of']}→{as_of} but signal "
                f"values are byte-identical to the prior vintage (builder did not recompute)")
        prim = next((f for f in s.scores if f.primary), s.scores[0] if s.scores else None)
        if prim:
            mt = score_stats.get(prim.name, {}).get("mean")
            prior_prim = (prior.get("scores") or {}).get(prim.name) or {}
            pm = prior_prim.get("mean")
            if mt is not None and pm is not None:
                # scale-aware denominator: a near-zero prior mean must not explode the % via 1e-9.
                denom = max(abs(pm), prior_prim.get("std") or 0.0, 1e-6)
                drift = abs(mt - pm) / denom
                if drift > float(_cfg(cfg, "max_drift_pct")):
                    res["warns"].append(
                        f"{s.key}.{prim.name}: mean drifted {drift * 100:.0f}% "
                        f"({pm:.3g}→{mt:.3g}) vs {prior['as_of']}")

    res["row"] = {"run_date": now.date().isoformat(), "surface": s.key, "as_of": as_of,
                  "n_records": len(recs), "coverage": cov, "fingerprint": fp, "scores": score_stats}
    return res


def evaluate_all(payloads: dict, prior_by_surface: "dict | None" = None, *,
                 now: "datetime | None" = None, cfg: "dict | None" = None) -> dict:
    """Evaluate every board. ``payloads`` maps surface-key → loaded JSON (or None if absent).
    ``prior_by_surface`` maps surface-key → its previous baseline row (or None). Returns a report
    with the SAME {ok, fail_reasons, warnings} shape as healthcheck.check_health, plus per-surface
    detail and the new baseline rows to persist."""
    cfg = cfg or {}
    now = now or datetime.now()
    prior_by_surface = prior_by_surface or {}

    surfaces: dict = {}
    fails: list = []
    warns: list = []
    missing: list = []
    present_dates: dict = {}

    for s in SURFACES:
        doc = payloads.get(s.key)
        if doc is None:
            missing.append(s.key)
        try:
            r = evaluate_surface(s, doc, prior_by_surface.get(s.key), now=now, cfg=cfg)
        except Exception as e:  # noqa: BLE001 — one bad board degrades to a fail, never a crash
            r = {"key": s.key, "label": s.label, "ok": False, "as_of": None, "n": 0, "coverage": 0,
                 "fails": [f"{s.key}: evaluator error ({e!r})"], "warns": [], "row": None}
        surfaces[s.key] = r
        fails += r["fails"]
        warns += r["warns"]
        d = _parse_date(r.get("as_of"))
        if d is not None:
            present_dates[s.key] = d

    # cross-surface relative staleness — one builder lagging its siblings (exempt boards whose
    # as_of uses a different basis, e.g. standouts' last-trading-day stamp).
    if len(present_dates) >= 2:
        freshest = max(present_dates.values())
        rel = float(_cfg(cfg, "rel_stale_days"))
        for k, d in present_dates.items():
            if _BY_KEY[k].rel_stale_exempt:
                continue
            lag = (freshest - d).days
            if lag > rel:
                msg = f"{k}: lags the freshest board by {lag}d (as_of {d.isoformat()} vs {freshest.isoformat()})"
                warns.append(msg)
                surfaces[k]["warns"].append(msg)

    return {
        "ok": not fails,
        "fail_reasons": fails,
        "warnings": warns,
        "surfaces": surfaces,
        "checked": [s.key for s in SURFACES],
        "missing": missing,
        "evaluated_at": now.isoformat(),
    }


def baseline_rows(report: dict) -> list:
    """The per-surface stat rows to append to the rolling baseline (one per present board)."""
    return [r["row"] for r in report.get("surfaces", {}).values() if r.get("row")]


def summary_line(report: dict) -> str:
    s = report.get("surfaces", {})
    cov = " ".join(f"{k}={v.get('coverage')}" for k, v in s.items())
    return (f"{'OK' if report.get('ok') else 'FAIL'} | "
            f"{len(report.get('fail_reasons') or [])} fail / {len(report.get('warnings') or [])} warn "
            f"| coverage: {cov}")


# ---------------------------------------------------------------------------
# thin reader (the only I/O — used by both the runner and the heartbeat)
# ---------------------------------------------------------------------------

def load_payloads(site_dir) -> dict:
    """Read each board's published JSON from ``site_dir`` (stdlib-only; absent/unreadable → None)."""
    out: dict = {}
    base = Path(site_dir)
    for s in SURFACES:
        p = base / s.path
        try:
            out[s.key] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
        except Exception:  # noqa: BLE001 — a corrupt board degrades to None, surfaced as a failure
            out[s.key] = None
    return out
