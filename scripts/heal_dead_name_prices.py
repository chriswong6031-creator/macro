"""Heal identity splices in the dead-name PRICE registry.

WHAT WENT WRONG. `scripts/research/fetch_dead_name_prices_polygon.py` asks Polygon
for [ANCHOR_DATE=2021-07-06, index_removal_date] by BARE TICKER STRING. ANCHOR_DATE
is one global constant, so for any name whose S&P tenure began after it the request
reaches back before that registrant held the string — and the vendor answers for
whoever held it then. Two registrants land under one key with no seam marker:

  FI    Frank's International ($15-19, 63 bars, ends 2021) welded to Fiserv
        ($110-238, from 2023-06-07) across a completely empty 2022.
  ALTM  Altus Midstream (161 bars, ends 2021) welded to Arcadium Lithium
        (from 2024-01-04) across an empty 2022-2023.

WHAT DID **NOT** GO WRONG. The 126 names the reused-ticker tripwire files as
`registry_mismatch` are NOT contaminated. `dead_universe()` selects on a CLOSED
S&P membership (`end_date.notna()`), which is an INDEX EXIT, not a death — 172 of
the 1,083 "dead" names still trade today. Those names correlate ~1.0 with their live
store because they ARE that company, and their registry rows stop at the fetch bound
(101/126 land on the index-removal date itself, 25/126 on removal + 60d), not at any
death. Capping them at a "death date" would delete genuine market data, so this heal
does not touch them; the universe-basis caveat is stamped instead.

Detection is `collectors.edgar_deadname_prices.split_identity_seam` — a segment is
foreign only when it lies ENTIRELY before the name's tenure AND sits behind a hole of
>= 45 days. A gap INSIDE the tenure is a corporate event, never a swap (EBIX/ENDP →
OTC after Ch.11), and that price->0 tail is the anti-survivorship data the panel
exists to capture, so it is preserved.

Quarantine, never delete: refused rows are written to
data/quarantine/dead_name_prices_spliced.parquet with a JSON manifest, so the call
stays auditable and reversible.

Usage:
    python -m scripts.heal_dead_name_prices --dry-run     # report only (default)
    python -m scripts.heal_dead_name_prices --apply       # quarantine + rewrite
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from collectors.edgar_deadname_prices import (  # noqa: E402
    SPLICE_GAP_DAYS,
    split_identity_seam,
    tenure_bounds,
)
from lib import config  # noqa: E402

log = logging.getLogger(__name__)

LIVE_STORES = ("baskets/ohlcv", "stocks")
CORR_SAME_INSTRUMENT = 0.35   # mirrors scripts/audit_reused_tickers.py


def _prices_path() -> Path:
    return config.data_dir() / "edgar" / "dead_name_prices.parquet"


def _quarantine_dir() -> Path:
    p = config.data_dir() / "quarantine"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _membership() -> pd.DataFrame:
    return pd.read_parquet(config.data_dir() / "breadth" / "sp1500_pit_membership.parquet")


def _live_close(ticker: str) -> pd.Series:
    """Latest close series for `ticker` from whichever live store carries it."""
    for store in LIVE_STORES:
        p = config.data_dir() / store / f"{ticker}.parquet"
        if not p.exists():
            continue
        try:
            df = pd.read_parquet(p, columns=["close"])
            s = df["close"]
            s.index = pd.to_datetime(s.index)
            return s.sort_index()
        except Exception:  # noqa: BLE001 — corruption is audit_prices' beat
            continue
    return pd.Series(dtype=float)


def _overlap_corr(a: pd.Series, b: pd.Series) -> tuple[int, float | None]:
    """(n_overlap, daily-return correlation) between two close series."""
    idx = a.index.intersection(b.index)
    if len(idx) < 20:
        return len(idx), None
    ra, rb = a.reindex(idx).pct_change(), b.reindex(idx).pct_change()
    joined = pd.concat([ra, rb], axis=1).dropna()
    if len(joined) < 20 or joined.iloc[:, 0].std() == 0 or joined.iloc[:, 1].std() == 0:
        return len(idx), None
    return len(idx), float(joined.iloc[:, 0].corr(joined.iloc[:, 1]))


def scan(prices: pd.DataFrame, mem: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Return (foreign_rows, per-name findings) for every spliced registry name."""
    foreign_frames: list[pd.DataFrame] = []
    findings: list[dict] = []
    for ticker, grp in prices.groupby("ticker", sort=True):
        s = grp.set_index("date")["close"].sort_index()
        bounds = tenure_bounds(ticker, mem)
        kept, foreign = split_identity_seam(s, bounds[0] if bounds else None)
        if len(foreign) == 0:
            continue
        rows = grp[grp["date"].isin(foreign.index)].copy()
        rows["quarantine_reason"] = "pre_tenure_identity_splice"
        rows["tenure_start"] = bounds[0]
        foreign_frames.append(rows)
        findings.append({
            "ticker": ticker,
            "tenure_start": str(bounds[0].date()),
            "n_rows_total": int(len(s)),
            "n_quarantined": int(len(foreign)),
            "n_retained": int(len(kept)),
            "foreign_span": [str(foreign.index.min().date()), str(foreign.index.max().date())],
            "foreign_close_range": [round(float(foreign.min()), 4), round(float(foreign.max()), 4)],
            "retained_span": ([str(kept.index.min().date()), str(kept.index.max().date())]
                              if len(kept) else None),
            "retained_close_range": ([round(float(kept.min()), 4), round(float(kept.max()), 4)]
                                     if len(kept) else None),
            "seam_gap_days": int((kept.index.min() - foreign.index.max()).days) if len(kept) else None,
        })
    foreign = (pd.concat(foreign_frames, ignore_index=True) if foreign_frames
               else pd.DataFrame(columns=[*prices.columns, "quarantine_reason", "tenure_start"]))
    return foreign, findings


def verify(prices: pd.DataFrame, findings: list[dict]) -> list[dict]:
    """Post-heal overlap check of each healed name against its LIVE store.

    A healed series must now read as ONE instrument: either it no longer overlaps a
    live store at all (the registrant is genuinely gone) or the overlap correlates
    like the same instrument. The pre-heal splice could do neither.
    """
    out = []
    for f in findings:
        t = f["ticker"]
        reg = prices[prices["ticker"] == t].set_index("date")["close"].sort_index()
        live = _live_close(t)
        n_ovl, corr = _overlap_corr(reg, live) if len(live) else (0, None)
        out.append({
            "ticker": t,
            "n_overlap_with_live_store": n_ovl,
            "ret_corr_vs_live": round(corr, 4) if corr is not None else None,
            "verdict": ("no_live_overlap" if n_ovl < 20 else
                        "same_instrument" if corr is not None and corr >= CORR_SAME_INSTRUMENT
                        else "still_divergent"),
        })
    return out


def heal(apply: bool = False) -> dict:
    path = _prices_path()
    if not path.exists():
        log.warning("heal_dead_name_prices: %s absent — nothing to heal", path)
        return {"error": "no_registry", "n_quarantined": 0}

    prices = pd.read_parquet(path)
    prices["date"] = pd.to_datetime(prices["date"])
    mem = _membership()

    foreign, findings = scan(prices, mem)
    n_rows = int(len(foreign))
    now = datetime.now(timezone.utc).isoformat()

    healed = prices
    if n_rows:
        keys = set(zip(foreign["ticker"], foreign["date"]))
        mask = [k not in keys for k in zip(prices["ticker"], prices["date"])]
        healed = prices[mask].reset_index(drop=True)

    checks = verify(healed, findings)

    manifest = {
        "schema": "dead_name_prices_splice_quarantine.v1",
        "generated_utc": now,
        "applied": bool(apply and n_rows),
        "splice_gap_days": SPLICE_GAP_DAYS,
        "detector": "collectors.edgar_deadname_prices.split_identity_seam",
        "n_registry_names_before": int(prices["ticker"].nunique()),
        "n_registry_rows_before": int(len(prices)),
        "n_names_spliced": len(findings),
        "n_rows_quarantined": n_rows,
        "n_registry_rows_after": int(len(healed)),
        "findings": findings,
        "post_heal_overlap_checks": checks,
        "not_contamination_note": (
            "The reused-ticker tripwire's 126 `registry_mismatch` names are NOT healed "
            "here and are NOT contaminated: dead_universe() selects on a CLOSED S&P "
            "membership (an INDEX EXIT, not a death), so those names are still-listed "
            "companies whose registry rows are their own genuine prices, truncated at "
            "the fetch bound. Trimming them to a 'death date' would delete real market "
            "data. The universe-basis caveat is stamped on _dead_name_price_coverage "
            "instead."),
    }

    if apply and n_rows:
        qdir = _quarantine_dir()
        foreign.to_parquet(qdir / "dead_name_prices_spliced.parquet", index=False)
        (qdir / "dead_name_prices_spliced.json").write_text(json.dumps(manifest, indent=1))
        healed.sort_values(["ticker", "date"]).reset_index(drop=True).to_parquet(path, index=False)
        log.info("heal: quarantined %d rows across %d names → %s", n_rows, len(findings), qdir)

    for f in findings:
        print(f"::warning title=dead-name-splice::{f['ticker']}: quarantined "
              f"{f['n_quarantined']} pre-tenure bar(s) "
              f"{f['foreign_span'][0]}..{f['foreign_span'][1]} "
              f"(close {f['foreign_close_range'][0]}-{f['foreign_close_range'][1]}) — "
              f"another registrant held the string before {f['tenure_start']}", flush=True)
    bad = [c for c in checks if c["verdict"] == "still_divergent"]
    if bad:
        print(f"::warning title=dead-name-splice-residual::{len(bad)} healed name(s) still "
              f"diverge from their live store: {[c['ticker'] for c in bad]}", flush=True)
    print(f"dead-name splice heal: names={len(findings)} rows_quarantined={n_rows} "
          f"applied={manifest['applied']}", flush=True)
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Quarantine identity splices in the dead-name price registry.")
    ap.add_argument("--apply", action="store_true", help="write the quarantine + rewrite the registry")
    ap.add_argument("--dry-run", action="store_true", help="report only (default)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    out = heal(apply=args.apply and not args.dry_run)
    print(json.dumps({k: v for k, v in out.items() if k != "findings"}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
