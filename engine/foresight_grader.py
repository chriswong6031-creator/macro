"""Foresight forward-grading — the learning loop of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md Phase 5 + INSTITUTIONAL_UPGRADE.md "PIT-grading rigor").
Makes the desk's own hit-rate measured, public, and HONEST — it must not over-report.

The cascade logs every stage flag at fire time (data/foresight/log.jsonl for ALL stages including
RE-RATING/WATCH — negative calls are testable claims too; data/glut_watch/log.jsonl for GLUT
exit calls). This grader re-opens each MATURED flag at each horizon, computes the theme's realized
equal-weight excess return vs SPY over the horizon, and records hit/miss. A thesis hits on
OUTperformance; a glut call hits on UNDERperformance.

MULTI-HORIZON GRADING (W0a): each ledger row is graded at 30, 60, and 90 days independently.
A row is graded at a horizon once that horizon has matured — shorter horizons yield early reads
while 90d accrues. Per-stage × per-horizon hit-rates + avg excess + Wilson CIs are reported.
The per-theme sign test and Benjamini-Yekutieli FDR gate run on the CANONICAL 90d horizon only
(to avoid multiplying the FDR surface across horizons). `n_pending` counts rows logged but not
yet mature at 90d; per-horizon counts are exposed separately.

THREE RIGOR GUARDS so the published track record cannot lie (the upgrade ask):
  1. SURVIVORSHIP-FREE — a member that DELISTED mid-horizon is NOT dropped (dropping losers
     inflates returns). Its terminal return uses its last traded close (or an imputed -100%
     bankruptcy close from data/edgar/dead_name_prices.parquet when available).
  2. POINT-IN-TIME MEMBERSHIP — grade the basket as it was AT FLAG TIME (the `members` snapshot
     logged in the ledger), not today's config (which may have added winners after the fact).
  3. MULTIPLE-TESTING CORRECTION — across many themes, a high hit-rate can be a multiple-
     comparisons artifact. Report a per-theme sign-test p-value with a Benjamini-Yekutieli FDR
     gate (dependence-robust — BY is more conservative than BH, valid under arbitrary dependence
     from overlapping horizons and a shared SPY benchmark), and a Wilson 95% CI on the pooled
     hit-rate — so a small lucky sample can't read as edge.

HONEST BY CONSTRUCTION: ledgers began accruing from W0a → flags logged but n_graded=0 /
n_pending=N until 30d horizon matures (first reads in ~30 days); no fabricated hit-rate.
Forward-only, no look-ahead. Pure given the stores.
"""
from __future__ import annotations

import json
import logging
import math

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

HORIZONS = [30, 60, 90]    # grade each flag at 30d, 60d, and 90d independently
HORIZON_DAYS = 90          # canonical horizon for the FDR gate + legacy callers
MIN_MEMBERS = 2            # need >=2 priced members to grade a theme
DELISTING_GAP_DAYS = 14    # last close >this before `end` => delisted (use it); else just lagging
FDR_Q = 0.10               # Benjamini-Yekutieli false-discovery rate (dependence-robust)


def _stage_direction(stage: str) -> int | None:
    """Grading role of a stage. THESIS stages are positive calls (hit = outperform SPY,
    +1); EXIT stages are negative calls (hit = underperform, -1); everything else
    (RE-RATING / WATCH / UNKNOWN) is a CONTROL ARM (None) — the desk's own do-not-chase /
    nothing-here reads, graded for forward excess ONLY so the claim can be validated,
    NEVER as a hit-rate: a crowded RE-RATING theme that keeps running is beta, not desk
    skill, and rendering it as a "hit" would publish beta as skill. Prefix-tolerant so
    the text-grade variants ("PRECIPICE (text)") inherit the thesis role."""
    s = (stage or "").upper()
    if s.startswith("PRECIPICE") or s.startswith("BROADENING"):
        return +1
    if "GLUT" in s:
        return -1
    return None


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


def grade_ledger_rows(rows: list[dict], today: pd.Timestamp, themes: dict,
                      spy: pd.Series | None) -> dict:
    """Shared row-grading core: grade stage-carrying ledger rows survivorship-free + PIT at
    each HORIZONS entry independently, returning pooled / by_stage / by_theme / by_horizon
    slices. Used by grade() (live foresight + glut ledgers) and by
    engine.foresight_shadow.grade_shadow() (per-candidate shadow slices) so the live and
    shadow track records grade under ONE set of semantics that cannot drift (W3b review N1).

    Each row needs theme/asof/stage (+ optional PIT `members` snapshot); its grading
    direction comes from the stage's ROLE via _stage_direction (thesis +1 / exit -1 /
    control None). The per-theme sign test and BY-FDR gate run on the canonical
    HORIZON_DAYS horizon only.
    """
    # per-horizon accumulators: by_stage_h[h][stage] and by_theme_h[h][theme]
    by_stage_h: dict[int, dict[str, dict]] = {h: {} for h in HORIZONS}
    by_theme_h: dict[int, dict[str, dict]] = {h: {} for h in HORIZONS}

    # canonical-horizon (90d) theme buckets for the FDR gate + legacy pooled stats
    by_stage: dict[str, dict] = {}
    by_theme: dict[str, dict] = {}

    n_total = n_graded = 0
    # n_pending = rows logged but not yet mature at the canonical 90d horizon
    n_pending = 0
    # per-horizon pending counts (a row pending at 30d is also pending at 60/90d)
    n_pending_h: dict[int, int] = {h: 0 for h in HORIZONS}

    for e in rows:
        theme = e.get("theme")
        asof = e.get("asof")
        stage = e.get("stage") or "UNKNOWN"
        if not theme or not asof or theme not in themes:
            continue
        direction = _stage_direction(stage)
        n_total += 1
        start = pd.Timestamp(asof)

        # POINT-IN-TIME membership: the snapshot logged at flag time, else today's config
        members = e.get("members") or (themes.get(theme) or {}).get("tickers") or []

        mature_at_canonical = False

        for h in HORIZONS:
            end = start + pd.Timedelta(days=h)
            if today < end:
                n_pending_h[h] += 1
                continue   # horizon not yet matured

            excess = _theme_excess(members, start, end, spy)
            if excess is None:
                n_pending_h[h] += 1
                continue   # price data not yet available — keep pending

            # control-arm rows (direction None) carry NO hit — forward excess only
            hit = None if direction is None else (excess * direction) > 0
            sb_h = by_stage_h[h].setdefault(stage, {"n": 0, "n_dir": 0, "hits": 0, "sum_excess": 0.0})
            tb_h = by_theme_h[h].setdefault(theme, {"n": 0, "n_dir": 0, "hits": 0, "sum_excess": 0.0})
            for b in (sb_h, tb_h):
                b["n"] += 1
                b["sum_excess"] += excess
                if hit is not None:
                    b["n_dir"] += 1
                    b["hits"] += 1 if hit else 0

            if h == HORIZON_DAYS:
                mature_at_canonical = True
                # populate canonical buckets (for FDR gate + legacy pooled stats)
                sb = by_stage.setdefault(stage, {"n": 0, "n_dir": 0, "hits": 0, "sum_excess": 0.0})
                tb = by_theme.setdefault(theme, {"n": 0, "n_dir": 0, "hits": 0, "sum_excess": 0.0, "obs": []})
                for b in (sb, tb):
                    b["n"] += 1
                    b["sum_excess"] += excess
                    if hit is not None:
                        b["n_dir"] += 1
                        b["hits"] += 1 if hit else 0
                # sign test / FDR run on DIRECTIONAL obs only — control arms make no
                # skill claim, so they must not enter the significance machinery
                if hit is not None:
                    tb["obs"].append((start, hit))

        # n_graded counts rows mature at the canonical horizon; n_pending counts those that
        # have not yet matured there (regardless of shorter-horizon status) — including rows
        # whose canonical horizon elapsed but whose price data is unavailable
        if mature_at_canonical:
            n_graded += 1
        else:
            n_pending += 1

    def _finalize_bucket(bucket: dict) -> None:
        for b in bucket.values():
            # hit_rate over DIRECTIONAL rows only; control-arm buckets (n_dir=0) get None
            # and report avg_excess_pct alone — never a fabricated skill number
            b["hit_rate"] = round(b["hits"] / b["n_dir"], 3) if b["n_dir"] else None
            b["avg_excess_pct"] = round(100.0 * b["sum_excess"] / b["n"], 2) if b["n"] else None
            b["ci95"] = _wilson(b["hits"], b["n_dir"])
            b.pop("sum_excess", None)

    # per-theme sign test on NON-OVERLAPPING (independent) flags at the canonical 90d horizon —
    # so autocorrelated re-fires can't shrink the p-value and over-report significance. The FDR
    # gate (Benjamini-Yekutieli, dependence-robust) runs only on the canonical horizon to avoid
    # multiplying the FDR surface across the three horizons.
    pvals: dict[str, float] = {}
    for t, b in by_theme.items():
        indep = _non_overlapping(b.pop("obs"), HORIZON_DAYS)
        b["n_independent"] = len(indep)
        pvals[t] = _binom_sf(sum(indep), len(indep))
    sig = _fdr_significant(pvals)
    for t, b in by_theme.items():
        b["p_value"] = round(pvals[t], 4)
        b["significant_fdr"] = t in sig

    _finalize_bucket(by_stage)
    _finalize_bucket(by_theme)
    for h in HORIZONS:
        _finalize_bucket(by_stage_h[h])
        _finalize_bucket(by_theme_h[h])

    # pooled hit stats over DIRECTIONAL rows only (thesis + exit stages); control-arm
    # rows are still counted in n_graded but make no hit claim
    pooled_hits = sum(b["hits"] for b in by_stage.values())
    pooled_n_dir = sum(b["n_dir"] for b in by_stage.values())

    # per-horizon summary slices (stage + theme buckets; no FDR repetition)
    by_horizon = {}
    for h in HORIZONS:
        h_hits = sum(b["hits"] for b in by_stage_h[h].values())
        h_dir = sum(b["n_dir"] for b in by_stage_h[h].values())
        h_total = sum(b["n"] for b in by_stage_h[h].values())
        by_horizon[str(h)] = {
            "horizon_days": h,
            "n_graded": h_total,
            "n_directional": h_dir,
            "n_pending": n_pending_h[h],
            "pooled_hit_rate": round(h_hits / h_dir, 3) if h_dir else None,
            "pooled_ci95": _wilson(h_hits, h_dir),
            "by_stage": by_stage_h[h],
            "by_theme": by_theme_h[h],
        }

    return {
        "n_total": n_total,
        "n_graded": n_graded,
        "n_pending": n_pending,
        "pooled_n_directional": pooled_n_dir,
        "pooled_hit_rate": round(pooled_hits / pooled_n_dir, 3) if pooled_n_dir else None,
        "pooled_ci95": _wilson(pooled_hits, pooled_n_dir),
        "n_significant_fdr": len(sig),
        "by_stage": by_stage,
        "by_theme": by_theme,
        "by_horizon": by_horizon,
    }


def grade(today: pd.Timestamp | None = None, write: bool = True) -> dict:
    """Grade every matured flag survivorship-free + PIT at 30/60/90d horizons independently.

    Each ledger row is graded at each horizon in HORIZONS once that horizon has matured; shorter
    horizons yield early reads while the canonical 90d horizon accrues. The per-theme sign test
    and BY-FDR gate run on the 90d horizon only (canonical) to avoid multiplying the FDR surface.
    Old single-horizon rows (without a `horizons` field) are tolerated — they grade at every
    horizon for which start+horizon < today and price data exists.
    """
    if today is None:
        today = pd.Timestamp.now().normalize()
    themes = (config.load() or {}).get("themes") or {}
    spy = _closes("SPY")

    # per-row direction comes from the stage's ROLE (thesis +1 / exit -1 / control None) —
    # a blanket +1 on the whole foresight ledger would grade a RE-RATING theme that keeps
    # running as a "hit", publishing beta as skill. Glut ledger rows are normalized to the
    # forced "GLUT-EXIT" stage, whose role the shared core resolves to exit (-1).
    rows = _read_ledger("foresight/log.jsonl")
    rows += [dict(e, stage="GLUT-EXIT") for e in _read_ledger("glut_watch/log.jsonl")]

    core = grade_ledger_rows(rows, today, themes, spy)

    summary = {
        "updated": str(today.date()),
        "horizons": HORIZONS,
        "horizon_days": HORIZON_DAYS,    # canonical horizon (legacy + FDR gate)
        "n_total": core["n_total"], "n_graded": core["n_graded"], "n_pending": core["n_pending"],
        "pooled_n_directional": core["pooled_n_directional"],
        "pooled_hit_rate": core["pooled_hit_rate"],
        "pooled_ci95": core["pooled_ci95"],
        "fdr_q": FDR_Q,
        "n_significant_fdr": core["n_significant_fdr"],
        "by_stage": core["by_stage"],       # canonical 90d stage buckets
        "by_theme": core["by_theme"],       # canonical 90d theme buckets + FDR
        "by_horizon": core["by_horizon"],   # per-horizon slices (30/60/90)
        "note": ("forward-only, survivorship-free (delisted members graded at their loss, no "
                 "look-ahead past a small settlement window), point-in-time basket membership. "
                 "Each flag is graded at 30/60/90d independently — shorter horizons yield early "
                 "reads while 90d accrues. HIT-RATES ARE SKILL CLAIMS and exist only for "
                 "directional stages: thesis (PRECIPICE/BROADENING, hit = outperform) and exit "
                 "(GLUT, hit = underperform). RE-RATING/WATCH/UNKNOWN are CONTROL ARMS — their "
                 "forward excess validates the do-not-chase claim but is never a hit-rate (a "
                 "crowded theme continuing to run is beta, not skill) and they are excluded from "
                 "the sign test/FDR. Hit-rates carry a Wilson 95% CI over directional flags; the "
                 "per-theme sign test runs on NON-OVERLAPPING directional flags only and the FDR "
                 "gate is Benjamini-Yekutieli (dependence-robust — valid under arbitrary "
                 "dependence from overlapping horizons + shared SPY benchmark), on the canonical "
                 "90d horizon only (avoids multiplying the FDR surface). Residual hole: a "
                 "delisting within ~2wk of a flag's horizon-end drops to pending. Old "
                 "single-horizon rows are tolerated and graded at each HORIZONS entry. "
                 "n_graded=0 until 30d flags mature — never a fabricated hit-rate."),
    }
    if write:
        try:
            d = config.data_dir() / "foresight"
            d.mkdir(parents=True, exist_ok=True)
            (d / "track_record.json").write_text(json.dumps(summary, separators=(",", ":")))
        except Exception as e:  # noqa: BLE001
            log.warning("track_record write failed: %s", e)
    return summary
