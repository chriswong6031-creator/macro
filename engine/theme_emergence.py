"""Theme emergence — fundamental bottleneck DISCOVERY for the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md §6).

THE IDEA. The desk's 18 themes are hand-curated, so the cascade can only CONFIRM themes we
already named — it is blind to the next one forming. The price-based discovery engines
(theme_discovery / narrative_emergence) find co-MOVING non-basket clusters, which is
coincident (the stocks are already moving together). This engine finds the FUNDAMENTAL
bottleneck signature instead: a cluster of *un-tracked* companies in the same SIC industry
independently reporting physical scarcity ("sold out", "on allocation", "lead times
extending") in their filings — the pre-13D state, before price or estimates confirm.

We read collectors/edgar_emergence.py's universe-AGNOSTIC scarcity hits (already SIC-tagged),
drop the tickers already in a tracked theme, group the rest by SIC industry, and surface
industries where >=MIN_NEW_FILERS distinct UNTRACKED filers are flagging scarcity and they
are the MAJORITY of that industry's scarcity-talkers (NEW_SHARE_MIN) — i.e. a bottleneck
forming somewhere we are not looking. DISPLAY-ONLY, a candidate GENERATOR on probation: a
candidate is never a buy and never auto-promoted; it earns a tracked-theme slot only when a
physical correlate later fires. Forward-graded (did the cluster's basket outperform?).
Returns None on shortfall.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

RECENT_DAYS = 180          # the "now" window for a forming cluster
BASELINE_DAYS = 400        # recent + prior baseline span (matches the collector lookback)
MIN_NEW_FILERS = 3         # >= this many distinct UNTRACKED filers in an industry (no single-name)
NEW_SHARE_MIN = 0.5        # untracked filers must be the majority of the industry's scarcity-talkers
MAX_CANDIDATES = 12

# PRECISION lever 1 — drop polysemy-prone SIC domains where "supply constrained" / "sold out"
# means real-estate INVENTORY or a retail SKU, not a manufacturing bottleneck. The desk's
# thesis is physical-INPUT scarcity that leads SUPPLIER re-ratings, which lives in
# manufacturing / materials / industrials / tech / energy — never in REITs, financials, or
# retail trade. Tunable.
EXCLUDED_SIC_PREFIXES = (
    "60", "61", "62", "63", "64",                      # finance & insurance
    "65", "66", "67",                                  # real estate / REIT / holding & investment
    "52", "53", "54", "55", "56", "57", "58", "59",    # retail trade ("sold out" = a SKU)
)
# PRECISION lever 2 — a cluster must contain at least one of these manufacturing-SPECIFIC
# phrases (which rarely mean anything other than a real supply/capacity bottleneck), not only
# the polysemous "sold out" / "supply constrained".
SPECIFIC_PHRASES = {
    "on allocation", "allocate supply", "extended lead times", "longer lead times",
    "double ordering", "expedite fees", "record backlog", "capacity constrained",
    "constrained capacity",
}


def _excluded_sic(sic: str) -> bool:
    return any(str(sic).startswith(pre) for pre in EXCLUDED_SIC_PREFIXES)


def _known_tickers() -> set[str]:
    themes = (config.load() or {}).get("themes") or {}
    out: set[str] = set()
    for spec in themes.values():
        out.update(spec.get("tickers") or [])
    return out


def _hits() -> pd.DataFrame | None:
    p = config.data_dir() / "edgar" / "emergence_hits.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("emergence_hits unreadable: %s", e)
        return None
    need = {"ticker", "sic", "file_date", "phrase"}
    if df is None or df.empty or not need.issubset(df.columns):
        return None
    return df


def _candidates_from(df: pd.DataFrame, known: set[str],
                     ref: date) -> list[dict]:
    """Pure clustering: SIC industries with a majority-untracked scarcity cluster.
    `ref` is the as-of reference date (recent window = [ref-RECENT_DAYS, ref])."""
    d = df.copy()
    d["file_date"] = pd.to_datetime(d["file_date"], errors="coerce")
    # dropna MUST precede any .astype(str) on sic — else a missing SIC becomes the string
    # "nan"/"None" and lumps unrelated un-enriched filers into one phantom cluster.
    d = d.dropna(subset=["file_date", "sic"])
    d = d[d["sic"].astype(str).str.strip().ne("")]
    if d.empty:
        return []
    ref_ts = pd.Timestamp(ref)
    recent_lo = ref_ts - pd.Timedelta(days=RECENT_DAYS)
    base_lo = ref_ts - pd.Timedelta(days=BASELINE_DAYS)
    d = d[d["file_date"] >= base_lo]
    d["new"] = ~d["ticker"].isin(known)
    # count distinct ISSUERS (CIK), not tickers, so multi-class (GOOG/GOOGL) or unit+warrant
    # listings don't inflate a cluster past the MIN_NEW_FILERS / majority gates. Fall back to
    # ticker when a CIK is missing.
    if "cik" in d.columns:
        cik_str = d["cik"].astype(str)
        d["issuer"] = cik_str.mask(d["cik"].isna() | cik_str.isin(["None", "nan", ""]),
                                   d["ticker"].astype(str))
    else:
        d["issuer"] = d["ticker"].astype(str)
    recent = d[d["file_date"] >= recent_lo]
    baseline = d[d["file_date"] < recent_lo]

    out = []
    for sic, grp in recent.groupby(recent["sic"].astype(str)):
        if _excluded_sic(sic):
            continue                                  # polysemy-prone domain (REIT/finance/retail)
        new_grp = grp[grp["new"]]
        n_filers = grp["issuer"].nunique()
        n_new = new_grp["issuer"].nunique()
        new_filers = sorted(new_grp["ticker"].astype(str).unique())
        if n_new < MIN_NEW_FILERS or n_filers == 0:
            continue
        if n_new / n_filers < NEW_SHARE_MIN:
            continue                                  # mostly already-tracked -> not a NEW theme
        phrases = sorted(grp["phrase"].astype(str).unique())
        if not any(p in SPECIFIC_PHRASES for p in phrases):
            continue                                  # only polysemous language -> not a real bottleneck
        base_new = baseline.loc[(baseline["sic"].astype(str) == sic) & baseline["new"],
                                "issuer"].nunique()
        velocity = n_new - int(base_new)              # UNTRACKED-issuer growth vs the prior window
        sic_desc = next((s for s in grp["sic_desc"].dropna().astype(str)), None) \
            if "sic_desc" in grp.columns else None
        quotes = []
        for _, r in grp.sort_values("file_date", ascending=False).head(5).iterrows():
            quotes.append({"ticker": str(r["ticker"]), "phrase": str(r["phrase"]),
                           "file_date": r["file_date"].date().isoformat()})
        out.append({
            "sic": str(sic),
            "sic_desc": sic_desc or f"SIC {sic}",
            "n_filers": n_filers,
            "n_new_filers": n_new,
            "n_known_filers": n_filers - n_new,
            "velocity": velocity,
            "new_filers": new_filers[:12],
            "phrases": phrases,
            "sample_quotes": quotes,
            "asof": grp["file_date"].max().date().isoformat(),
        })
    # most untracked filers first, then sharpest velocity
    out.sort(key=lambda c: (-c["n_new_filers"], -c["velocity"]))
    return out[:MAX_CANDIDATES]


def compute_theme_emergence(write_ledger: bool = True,
                            hits: pd.DataFrame | None = None,
                            asof_date: date | None = None) -> dict | None:
    """Surface candidate emerging bottleneck industries (majority-untracked scarcity
    clusters). DISPLAY-ONLY. Returns None when the emergence cache is absent."""
    df = _hits() if hits is None else hits
    if df is None or df.empty:
        return None
    known = _known_tickers()
    ref = asof_date or date.today()
    try:
        candidates = _candidates_from(df, known, ref)
    except Exception as e:  # noqa: BLE001 — discovery is additive, never fatal
        log.warning("theme_emergence clustering failed: %s", e)
        return None
    if not candidates:
        return None
    payload = {
        "asof": max((c["asof"] for c in candidates), default=None),
        "n_candidates": len(candidates),
        "candidates": candidates,
        "note": ("display-only; CANDIDATE emerging bottlenecks — industries where a majority "
                 "of un-tracked companies are independently reporting physical scarcity. A "
                 "candidate is on PROBATION: never a buy, never auto-added; it earns a tracked "
                 "slot only when a physical correlate fires. The pre-13D discovery layer."),
    }
    if write_ledger:
        try:
            _append_ledger(payload)
        except Exception as e:  # noqa: BLE001
            log.warning("theme_emergence ledger append failed: %s", e)
    return payload


def _append_ledger(payload: dict) -> None:
    """Append-only forward-grading ledger: one row per (sic, asof) candidate cluster —
    graded forward (did the untracked-filer basket outperform SPY / eventually re-rate?)."""
    d = config.data_dir() / "theme_emergence"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "log.jsonl"
    seen = set()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
                seen.add((e.get("sic"), e.get("asof")))
            except Exception:  # noqa: BLE001
                continue
    ts = datetime.now(timezone.utc).isoformat()
    lines = []
    for c in payload["candidates"]:
        key = (c["sic"], c["asof"])
        if key in seen:
            continue
        lines.append(json.dumps({
            "sic": c["sic"], "sic_desc": c["sic_desc"], "asof": c["asof"], "ts": ts,
            "n_new_filers": c["n_new_filers"], "velocity": c["velocity"],
            "new_filers": c["new_filers"],
        }, separators=(",", ":")))
    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
