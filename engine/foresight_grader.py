"""Foresight forward-grading — the learning loop of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md Phase 5 + INSTITUTIONAL_UPGRADE.md "PIT-grading rigor").
Makes the desk's own hit-rate measured, public, and HONEST — it must not over-report.

The cascade logs every actionable flag at fire time (data/foresight/log.jsonl for PRECIPICE/
BROADENING theses; data/glut_watch/log.jsonl for GLUT exit calls). This grader re-opens each
MATURED flag (asof + horizon in the past), computes the theme's realized equal-weight excess
return vs SPY over the horizon, and records hit/miss. A thesis hits on OUTperformance; a glut
call hits on UNDERperformance.

THREE RIGOR GUARDS so the published track record cannot lie (the upgrade ask):
  1. SURVIVORSHIP-FREE — a member that DELISTED mid-horizon is NOT dropped (dropping losers
     inflates returns). Its terminal return uses its last traded close (or an imputed -100%
     bankruptcy close from data/edgar/dead_name_prices.parquet when available).
  2. POINT-IN-TIME MEMBERSHIP — grade the basket as it was AT FLAG TIME (the `members` snapshot
     logged in the ledger), not today's config (which may have added winners after the fact).
  3. MULTIPLE-TESTING CORRECTION — across many themes, a high hit-rate can be a multiple-
     comparisons artifact. Report a per-theme sign-test p-value with a Benjamini-Hochberg FDR
     gate, and a Wilson 95% CI on the pooled hit-rate — so a small lucky sample can't read as edge.

HONEST BY CONSTRUCTION: ledgers only began accruing recently -> n_graded=0 / n_pending=N until
flags mature; no fabricated hit-rate. Forward-only, no look-ahead. Pure given the stores.
"""
from __future__ import annotations

import json
import logging
import math

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

HORIZON_DAYS = 90          # ~63 trading days — the revision-momentum / PEAD horizon
MIN_MEMBERS = 2            # need >=2 priced members to grade a theme
DELISTING_GAP_DAYS = 14    # last close >this before `end` => delisted (use it); else just lagging
FDR_Q = 0.10               # Benjamini-Hochberg false-discovery rate


# --------------------------------------------------------------------------- price access
_DEAD = {"path": None, "by_ticker": {}}


def _closes(ticker: str) -> pd.Series | None:
    p = config.data_dir() / "yahoo" / f"{ticker}.parquet"
    if not p.exists():
        return _dead_closes(ticker)
    try:
        df = pd.read_parquet(p)
    except Exception:  # noqa: BLE001
        return _dead_closes(ticker)
    if "close" not in df.columns:
        return _dead_closes(ticker)
    s = df["close"].dropna()
    if not len(s):
        return _dead_closes(ticker)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _dead_closes(ticker: str) -> pd.Series | None:
    """Last-resort price series for a DELISTED name from data/edgar/dead_name_prices.parquet
    (long table ticker/date/close/source, incl. imputed_bankruptcy -100% terminals). Degrades
    to None when the store is absent (CI-collected) — survivorship is then handled by last-close."""
    p = config.data_dir() / "edgar" / "dead_name_prices.parquet"
    if _DEAD["path"] != str(p):                          # re-key on path (test isolation; new store)
        _DEAD["path"] = str(p)
        _DEAD["by_ticker"] = {}
        try:
            if p.exists():
                df = pd.read_parquet(p)
                if {"ticker", "date", "close"}.issubset(df.columns):
                    for tk, g in df.groupby(df["ticker"].astype(str)):
                        s = pd.Series(g["close"].values, index=pd.to_datetime(g["date"]))
                        # keep >=0 so an imputed 0.0 bankruptcy terminal survives as a -100% loss
                        _DEAD["by_ticker"][tk] = s[s >= 0].dropna().sort_index()
        except Exception as e:  # noqa: BLE001
            log.warning("dead_name_prices load failed: %s", e)
    return _DEAD["by_ticker"].get(str(ticker))


def _ret(s: pd.Series | None, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    """SURVIVORSHIP-FREE total return start->end, NO look-ahead. Terminal = the first close in
    [end, end+gap] (a small settlement window for weekends/holidays); a name with NO close in
    that window but a last trade well before `end` is treated as DELISTED and graded at that last
    close (the loss is NOT dropped). None when there is no anchor at start, or the series merely
    lags (last close within `gap` of `end`) i.e. not yet matured. Residual hole (disclosed): a
    name that delists WITHIN `gap` of `end` drops to pending rather than being graded at its loss."""
    if s is None or s.empty:
        return None
    a = s[s.index >= start]
    if a.empty:
        return None                                     # never priced at start — cannot grade
    p0 = float(a.iloc[0])
    if p0 <= 0:
        return None
    win = s[(s.index >= end) & (s.index <= end + pd.Timedelta(days=DELISTING_GAP_DAYS))]
    if not win.empty:
        p1 = float(win.iloc[0])                         # close at/near `end` — no look-ahead past +gap
    else:
        before = s[s.index < end]
        if before.empty or (end - before.index[-1]).days < DELISTING_GAP_DAYS:
            return None                                 # data merely lagging -> pending, not a delisting
        p1 = float(before.iloc[-1])                     # delisted: terminal = last traded close
    return p1 / p0 - 1.0


def _theme_excess(members: list[str], start: pd.Timestamp, end: pd.Timestamp,
                  spy: pd.Series | None) -> float | None:
    """Equal-weight theme excess vs SPY. Survivorship-free: delisted members are graded at
    their loss (via _ret), not silently excluded."""
    spy_ret = _ret(spy, start, end)
    if spy_ret is None:
        return None
    rets = [r for r in (_ret(_closes(m), start, end) for m in (members or [])) if r is not None]
    if len(rets) < MIN_MEMBERS:
        return None
    return (sum(rets) / len(rets)) - spy_ret


# --------------------------------------------------------------------------- statistics
def _binom_sf(k: int, n: int, p: float = 0.5) -> float:
    """P(X >= k) for X ~ Binom(n, p). Exact, stdlib only (no scipy dependency)."""
    if n <= 0:
        return 1.0
    k = max(0, int(k))
    return float(sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def _fdr_significant(pvals: dict[str, float], q: float = FDR_Q) -> set[str]:
    """Benjamini-YEKUTIELI FDR (BH with the threshold scaled by 1/H_m) — valid under ARBITRARY
    dependence. The themes' tests are NOT independent (overlapping 90d horizons, shared SPY
    benchmark), so the dependence-robust, conservative variant is the honest choice: it under-
    reports significance rather than over-reporting it."""
    items = sorted(((k, v) for k, v in pvals.items() if v is not None), key=lambda kv: kv[1])
    m = len(items)
    if m == 0:
        return set()
    h_m = sum(1.0 / i for i in range(1, m + 1))          # harmonic number — the BY correction
    passing = 0
    for rank, (_, p) in enumerate(items, 1):
        if p <= q * rank / (m * h_m):
            passing = rank
    return {items[i][0] for i in range(passing)}


def _non_overlapping(obs: list[tuple], horizon_days: int) -> list[int]:
    """One observation per NON-OVERLAPPING horizon (greedy by date) — independent flags for the
    sign test. A theme re-fires monthly with overlapping 90d horizons; counting every fire as an
    independent Bernoulli inflates n and shrinks the p-value (anti-conservative). obs=[(ts,hit)]."""
    kept, last = [], None
    for ts, hit in sorted(obs, key=lambda x: x[0]):
        if last is None or (ts - last).days >= horizon_days:
            kept.append(hit)
            last = ts
    return kept


def _wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """Wilson score 95% CI for a hit-rate k/n — honest bounds on a small sample."""
    if not n:
        return None
    phat = k / n
    d = 1 + z * z / n
    c = (phat + z * z / (2 * n)) / d
    h = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


# --------------------------------------------------------------------------- ledger + grade
def _read_ledger(rel: str) -> list[dict]:
    p = config.data_dir() / rel
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def grade(today: pd.Timestamp | None = None, write: bool = True) -> dict:
    """Grade every matured flag survivorship-free + PIT, with an FDR gate and Wilson CIs."""
    if today is None:
        today = pd.Timestamp.now().normalize()
    themes = (config.load() or {}).get("themes") or {}
    spy = _closes("SPY")

    sources = [("foresight/log.jsonl", None, +1), ("glut_watch/log.jsonl", "GLUT-EXIT", -1)]
    by_stage: dict[str, dict] = {}
    by_theme: dict[str, dict] = {}
    n_total = n_graded = n_pending = 0

    for rel, force_stage, direction in sources:
        for e in _read_ledger(rel):
            theme = e.get("theme")
            asof = e.get("asof")
            stage = force_stage or e.get("stage") or "UNKNOWN"
            if not theme or not asof or theme not in themes:
                continue
            n_total += 1
            start = pd.Timestamp(asof)
            end = start + pd.Timedelta(days=HORIZON_DAYS)
            if today < end:
                n_pending += 1
                continue
            # POINT-IN-TIME membership: the snapshot logged at flag time, else today's config
            members = e.get("members") or (themes.get(theme) or {}).get("tickers") or []
            excess = _theme_excess(members, start, end, spy)
            if excess is None:
                n_pending += 1
                continue
            hit = (excess * direction) > 0
            sb = by_stage.setdefault(stage, {"n": 0, "hits": 0, "sum_excess": 0.0})
            tb = by_theme.setdefault(theme, {"n": 0, "hits": 0, "sum_excess": 0.0, "obs": []})
            for b in (sb, tb):
                b["n"] += 1
                b["hits"] += 1 if hit else 0
                b["sum_excess"] += excess
            tb["obs"].append((start, hit))
            n_graded += 1

    def _finalize(bucket):
        for b in bucket.values():
            b["hit_rate"] = round(b["hits"] / b["n"], 3) if b["n"] else None
            b["avg_excess_pct"] = round(100.0 * b["sum_excess"] / b["n"], 2) if b["n"] else None
            b["ci95"] = _wilson(b["hits"], b["n"])
            b.pop("sum_excess", None)

    # per-theme sign test on NON-OVERLAPPING (independent) flags only, then a dependence-robust
    # FDR gate — so autocorrelated re-fires can't shrink the p-value and over-report significance.
    pvals = {}
    for t, b in by_theme.items():
        indep = _non_overlapping(b.pop("obs"), HORIZON_DAYS)
        b["n_independent"] = len(indep)
        pvals[t] = _binom_sf(sum(indep), len(indep))
    sig = _fdr_significant(pvals)
    for t, b in by_theme.items():
        b["p_value"] = round(pvals[t], 4)
        b["significant_fdr"] = t in sig
    _finalize(by_stage)
    _finalize(by_theme)

    pooled_hits = sum(b["hits"] for b in by_stage.values())
    summary = {
        "updated": str(today.date()),
        "horizon_days": HORIZON_DAYS,
        "n_total": n_total, "n_graded": n_graded, "n_pending": n_pending,
        "pooled_hit_rate": round(pooled_hits / n_graded, 3) if n_graded else None,
        "pooled_ci95": _wilson(pooled_hits, n_graded),
        "fdr_q": FDR_Q,
        "n_significant_fdr": len(sig),
        "by_stage": by_stage,
        "by_theme": by_theme,
        "note": ("forward-only, survivorship-free (delisted members graded at their loss, no "
                 "look-ahead past a small settlement window), point-in-time basket membership. "
                 "Hit-rates carry a Wilson 95% CI; the per-theme sign test runs on NON-OVERLAPPING "
                 "flags only and the FDR gate is Benjamini-Yekutieli (dependence-robust), so "
                 "autocorrelated re-fires + a shared benchmark can't read as edge. Residual hole: "
                 "a delisting within ~2wk of a flag's horizon-end drops to pending. n_graded=0 "
                 "until flags mature — never a fabricated hit-rate."),
    }
    if write:
        try:
            d = config.data_dir() / "foresight"
            d.mkdir(parents=True, exist_ok=True)
            (d / "track_record.json").write_text(json.dumps(summary, separators=(",", ":")))
        except Exception as e:  # noqa: BLE001
            log.warning("track_record write failed: %s", e)
    return summary
