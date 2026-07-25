"""Empirical null base rate for the desks' `hit` endpoint. DETERMINISTIC · NEVER-RAISES.

WHY THIS EXISTS
---------------
`hit` is a NOT-FALSIFIED metric, not a directional one. A desk thesis logs a falsifier —
"XLY underperforms SPY by more than 5% over 20 sessions" — and `hit` simply means that
condition did NOT occur (engine/desk_scorer.py:140). Its null is therefore nowhere near
0.5: for a typical rel_return falsifier (op '<', threshold −0.05) a coin-flip lean is
*not falsified* roughly 80–85% of the time, because most 20-day windows simply don't drop
5% versus the benchmark. The `level` (fade-fear) endpoint runs the other way — "never made
a new high above entry" is HARSH, with a null well below 0.5.

This is the same error the L6 Phase-0 report flagged for its own floored favorable-excursion
endpoint (base rate ~88%; `research/macro_tx/L6_PHASE0_REPORT.md` "In plain English",
adjudication condition C1: *any future masterplan must treat this endpoint as what it is*).
Comparing a not-falsified rate to 0.5 and calling 0.5 the "coin-flip" null manufactures an
edge out of the endpoint's leniency.

WHAT WE MEASURE
---------------
For every decided thesis we re-evaluate ITS OWN predicate — same instrument, same benchmark,
same window length, same operator and threshold — at EVERY historical entry date in the price
cache. The fraction of those placebo entries that come back not-falsified is that thesis's
null hit-rate p_i: what a no-skill lean on that exact instrument and horizon would score.
The desk's null is the mix-matched mean of its own p_i, so a desk cannot look good merely by
writing lenient falsifiers or by favouring the lenient endpoint kind.

The same sweep yields the null for `dir_accuracy` (q_i) — which is genuinely near 0.5 for a
rel_return lean, but is measured rather than assumed.

Exhaustive over history, so there is no RNG: same inputs → same numbers, every run.

Verified against the live ai_desk ledger: replaying these sweeps at each thesis's ACTUAL
entry date reproduces engine.desk_scorer's recorded hit/miss on 13 of 13, and the `level`
realized values to 4 decimals — so the null describes the same endpoint that was graded. The
one deliberate difference is `start_level`: the scorer prefers the entry close captured at
log time, while a placebo entry at an arbitrary historical date has no such capture and must
use the cached close throughout. That moves realized values by <0.005 and flipped no outcome.

WHAT IT DOES NOT DO
-------------------
Display-tier accrual is untouched. This module computes a promotion statistic and nothing
else — it never writes a score, a size, or an allocation, and a null never stops a desk from
continuing to log and grade theses.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA = "desk_placebo.v1"

# A placebo rate is only meaningful with enough historical windows behind it.
_MIN_PLACEBO_WINDOWS = 60

_MACHINE_KINDS = ("rel_return", "level")


# --------------------------------------------------------------------------- #
# price access (lazy imports — keep this module cheap to import)
# --------------------------------------------------------------------------- #
def _series_cache(root):
    """Per-call ticker → close-series cache. _close_series re-reads parquet each time and a
    desk re-uses the same benchmark on every thesis, so caching turns O(theses) parquet
    reads into O(distinct tickers)."""
    from engine import ai_desk as _desk

    cache: dict = {}

    def get(ticker):
        if not ticker:
            return None
        if ticker not in cache:
            try:
                cache[ticker] = _desk._close_series(ticker, root)
            except Exception:  # noqa: BLE001
                cache[ticker] = None
        return cache[ticker]

    return get


def _window_len(s, asof, check_by) -> int:
    """Trading-day span the scorer actually graded: last bar <= asof → last bar <= check_by."""
    import pandas as pd

    i0 = s.index.searchsorted(pd.Timestamp(asof), side="right") - 1
    i1 = s.index.searchsorted(pd.Timestamp(check_by), side="right") - 1
    return int(i1 - i0)


# --------------------------------------------------------------------------- #
# the per-thesis placebo sweeps — mirror engine.desk_scorer's evaluators exactly
# --------------------------------------------------------------------------- #
def placebo_rel_return(get, check: dict, asof, check_by) -> dict | None:
    """Null for eval_rel_return: realized = subject excess vs benchmark over W sessions;
    falsified iff op(realized, threshold). Swept over every historical entry date."""
    import pandas as pd

    sub, vs = check.get("subject_ticker"), check.get("vs")
    a = get(sub)
    if a is None or getattr(a, "empty", True):
        return None
    if vs:
        b = get(vs)
        if b is None or b.empty:
            return None
        joined = pd.concat({"a": a, "b": b}, axis=1, sort=True).dropna()
        a, b = joined["a"], joined["b"]
    else:
        b = None
    w = _window_len(a, asof, check_by)
    if w < 1:
        return None
    realized = a.shift(-w) / a - 1.0
    if b is not None:
        realized = realized - (b.shift(-w) / b - 1.0)
    realized = realized.dropna()
    if len(realized) < _MIN_PLACEBO_WINDOWS:
        return None
    op, thr = check.get("op"), float(check.get("threshold", 0.0))
    falsified = (realized < thr) if op == "<" else (realized > thr)
    dir_ok = (realized > 0) if op == "<" else (realized < 0)
    return {"p_hit": float((~falsified).mean()), "p_dir": float(dir_ok.mean()),
            "window_bd": w, "n_windows": int(len(realized))}


def placebo_level(get, check: dict, asof, check_by) -> dict | None:
    """Null for eval_level (fade-fear): falsified iff the level makes ANY new high above
    entry within the window. Swept over every historical entry date."""
    import pandas as pd

    a = get(check.get("subject_ticker"))
    if a is None or getattr(a, "empty", True):
        return None
    w = _window_len(a, asof, check_by)
    if w < 1:
        return None
    # max close over (t, t+w] — matches desk_scorer.max_close_between's exclusive start.
    fwd_max = a.shift(-1).rolling(w, min_periods=w).max().shift(-(w - 1))
    frame = pd.concat({"e0": a, "mx": fwd_max, "final": a.shift(-w)}, axis=1, sort=True).dropna()
    if len(frame) < _MIN_PLACEBO_WINDOWS:
        return None
    return {"p_hit": float((frame["mx"] <= frame["e0"]).mean()),
            "p_dir": float((frame["final"] < frame["e0"]).mean()),
            "window_bd": w, "n_windows": int(len(frame))}


_PLACEBOS = {"rel_return": placebo_rel_return, "level": placebo_level}


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #
def poisson_binomial_sf(ps: list, k: int) -> float:
    """P(X >= k) where X = sum of independent Bernoulli(p_i) — exact, by DP convolution.

    Each thesis has its OWN null p_i (different instrument, horizon, threshold), so the
    aggregate null is Poisson-binomial, not binomial. Exact beats a normal approximation at
    the sample sizes here (n ~ 10-50).

    INDEPENDENCE CAVEAT: this assumes the theses are independent draws. They are not — a
    desk logs many theses within days of each other with overlapping forward windows, so the
    true variance is larger and this p-value is ANTICONSERVATIVE. That is precisely why
    promotion additionally requires a floor on non-overlapping window blocks
    (`independent_blocks`) rather than trusting this number alone.
    """
    if not ps:
        return 1.0
    k = max(0, int(k))
    dist = [1.0]
    for p in ps:
        p = min(max(float(p), 0.0), 1.0)
        nxt = [0.0] * (len(dist) + 1)
        for i, v in enumerate(dist):
            nxt[i] += v * (1.0 - p)
            nxt[i + 1] += v * p
        dist = nxt
    if k >= len(dist):
        return 0.0
    return float(sum(dist[k:]))


def independent_blocks(spans: list) -> int:
    """Greedy count of NON-OVERLAPPING (asof, check_by) windows — the desk's effective
    number of independent looks at the tape.

    A desk that logs 45 theses across three weeks, each graded over the following 20
    sessions, has not taken 45 independent samples: every window covers substantially the
    same market. Sort by window end, then walk taking each window that starts at or after
    the last taken window's end (classic interval scheduling — the maximum such set).
    """
    clean = [(a, b) for a, b in spans if a and b and str(a) <= str(b)]
    if not clean:
        return 0
    clean.sort(key=lambda ab: str(ab[1]))
    taken, last_end = 0, ""
    for start, end in clean:
        if str(start) >= last_end:
            taken += 1
            last_end = str(end)
    return taken


def holm_adjust(pvals: dict) -> dict:
    """Holm-Bonferroni step-down over the desks tested in one run. Promotion is a family of
    simultaneous tests (one per desk, every night); an unadjusted alpha would promote a desk
    on multiplicity alone. Returns {key: adjusted_p} (monotone, capped at 1.0)."""
    items = sorted(((k, v) for k, v in pvals.items() if v is not None), key=lambda kv: kv[1])
    m, out, running = len(items), {}, 0.0
    for i, (k, p) in enumerate(items):
        running = max(running, min(1.0, (m - i) * p))
        out[k] = running
    for k, v in pvals.items():
        if v is None:
            out[k] = None
    return out


# --------------------------------------------------------------------------- #
# reconstructing the decided predicate mix
# --------------------------------------------------------------------------- #
def _load_jsonl(path) -> list:
    try:
        return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    except Exception:  # noqa: BLE001
        return []


def _decided_mix(root: Path, slug: str, today) -> tuple[list, str, int]:
    """The theses whose outcomes make up the track record → [(ledger_row, outcome_row|None)].

    Preferred source is data/<slug>/scored.jsonl joined to theses.jsonl by id (exact, and
    carries per-thesis outcomes). That file is untracked for some desks, so we fall back to
    the ledger's machine-checkable theses whose check_by has elapsed — the same population
    the scorer grades. The fallback carries no per-thesis outcome, so the caller must take
    observed counts from the aggregate track record and may only do so when the counts line
    up exactly.
    """
    ledger = {}
    for row in _load_jsonl(root / "data" / slug / "theses.jsonl"):
        if row.get("id"):
            ledger[row["id"]] = row
    if not ledger:
        return [], "none", 0

    scored_rows = _load_jsonl(root / "data" / slug / "scored.jsonl")
    decided = [r for r in scored_rows if r.get("outcome") in ("hit", "miss")]
    if decided:
        pairs, orphans = [], 0
        for r in decided:
            led = ledger.get(r.get("id"))
            if led is None:
                orphans += 1
                continue
            pairs.append((led, r))
        return pairs, "scored", orphans

    cutoff = str(today)
    pairs = [
        (row, None) for row in ledger.values()
        if str(row.get("check_by") or "") <= cutoff
        and ((row.get("falsifier") or {}).get("check") or {}).get("kind") in _MACHINE_KINDS
    ]
    return pairs, ("ledger_elapsed" if pairs else "none"), 0


# --------------------------------------------------------------------------- #
# public entry point
# --------------------------------------------------------------------------- #
def null_baseline(root, slug: str, track: dict, today) -> dict:
    """Measure the empirical null for one desk's realized predicate mix.

    Returns a plain dict, always — `available` False with a `reason` when the null could not
    be established. Never raises: an unmeasurable null must leave the desk unpromoted, never
    break the nightly.
    """
    out = {
        "schema": SCHEMA, "available": False, "reason": "not computed",
        "mix_source": "none", "n": 0, "n_decided": 0, "coverage": None,
        "unreconstructable": 0,
        "null_hit_rate": None, "null_dir_rate": None,
        "observed_hit_rate": None, "observed_dir_rate": None,
        "p_hit": None, "p_dir": None,
        "independent_blocks": 0, "by_kind": {},
    }
    try:
        root = Path(root)
        overall = (track or {}).get("overall") or {}
        n_decided = int(overall.get("n") or 0)
        out["n_decided"] = n_decided
        if not n_decided:
            out["reason"] = "no decided outcomes yet"
            return out

        pairs, source, orphans = _decided_mix(root, slug, today)
        out["mix_source"] = source
        out["unreconstructable"] = orphans
        if not pairs:
            out["reason"] = "no thesis ledger to reconstruct the graded predicates from"
            return out

        get = _series_cache(root)
        ps, qs, spans, kinds = [], [], [], {}
        hits = dirs = 0
        no_null = 0
        for led, scored in pairs:
            check = ((led.get("falsifier") or {}).get("check") or {})
            kind = check.get("kind")
            fn = _PLACEBOS.get(kind)
            asof, check_by = led.get("state_asof"), led.get("check_by")
            res = fn(get, check, asof, check_by) if (fn and asof and check_by) else None
            if res is None:
                no_null += 1
                continue
            ps.append(res["p_hit"])
            qs.append(res["p_dir"])
            spans.append((asof, check_by))
            k = kinds.setdefault(kind, {"n": 0, "null_hit_sum": 0.0, "null_dir_sum": 0.0})
            k["n"] += 1
            k["null_hit_sum"] += res["p_hit"]
            k["null_dir_sum"] += res["p_dir"]
            if scored is not None:
                hits += 1 if scored.get("outcome") == "hit" else 0
                dirs += 1 if scored.get("directionally_correct") else 0

        out["unreconstructable"] = orphans + no_null
        n = len(ps)
        out["n"] = n
        if not n:
            out["reason"] = "no graded predicate had enough price history for a placebo sweep"
            return out

        # Display-tier from here: the measured null is reported even when it covers only part
        # of the graded set (a partial null is real information about the endpoint). Only the
        # promotion TEST below requires exact pairing.
        out["null_hit_rate"] = round(sum(ps) / n, 4)
        out["null_dir_rate"] = round(sum(qs) / n, 4)
        out["coverage"] = round(n / n_decided, 4) if n_decided else None
        out["independent_blocks"] = independent_blocks(spans)
        out["by_kind"] = {
            k: {"n": v["n"], "null_hit_rate": round(v["null_hit_sum"] / v["n"], 4),
                "null_dir_rate": round(v["null_dir_sum"] / v["n"], 4)}
            for k, v in sorted(kinds.items())
        }

        # Observed counts: per-thesis when scored.jsonl gave them, else the aggregate track
        # record — but only when the reconstructed mix matches it exactly, so we never test
        # one population's hits against another population's null.
        if source == "scored" and n == n_decided:
            obs_hits, obs_dirs = hits, dirs
        elif n == n_decided and overall.get("hits") is not None:
            obs_hits = int(overall.get("hits") or 0)
            dir_acc = overall.get("dir_accuracy")
            obs_dirs = int(round(float(dir_acc) * n)) if dir_acc is not None else None
        else:
            out["reason"] = (f"reconstructed {n} graded predicates but the track record has "
                             f"{n_decided} — cannot pair observed outcomes to their nulls")
            return out

        out["observed_hit_rate"] = round(obs_hits / n, 4)
        out["p_hit"] = round(poisson_binomial_sf(ps, obs_hits), 5)
        if obs_dirs is not None:
            out["observed_dir_rate"] = round(obs_dirs / n, 4)
            out["p_dir"] = round(poisson_binomial_sf(qs, obs_dirs), 5)
        out["available"] = True
        out["reason"] = ""
        return out
    except Exception as e:  # noqa: BLE001 — a broken placebo must not break the nightly
        log.warning("desk_placebo(%s) failed: %s", slug, e)
        out["reason"] = f"placebo sweep failed: {e}"
        return out
