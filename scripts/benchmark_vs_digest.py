"""Self-sufficiency scorecard: our EDGAR pipeline vs the digest's curation.

Measures whether our own deterministic EDGAR detector independently surfaces the
situations the digest editors curated — i.e. how close we are to not needing them.

CONFIRMATION RATE (recall proxy): of the latest digest issue's US situations, what
fraction did our EDGAR pipeline also flag (matched by ticker)? Reported per category.
EDGAR-EXTRA: our flagged US situations whose ticker is in NO digest issue — either
fresh detections (ahead of the next digest) or false positives to tune in P1.5+.

Honest scope: our backfill window must overlap the issue's filing week (this script
widens it via collector.backfill_range). Digest issues also re-report ongoing
situations whose original filing predates our window — those will read as "missed"
here even though they are simply outside our lookback, so confirmation is a LOWER
BOUND on true recall. Run: python -m scripts.benchmark_vs_digest
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from lib import config
from engine import special_situations as sse


def _norm(t) -> str | None:
    if not t or (isinstance(t, float) and pd.isna(t)):
        return None
    return str(t).upper().split(".")[0].strip() or None


def run(widen: bool = True) -> None:
    if widen:
        from collectors import special_situations as col
        # widen our EDGAR window to cover the latest digest issue's filing week
        col.backfill_range(date(2026, 6, 8), date(2026, 6, 11))

    digest = pd.read_parquet(config.data_dir() / "special_situations" / "digest_db.parquet")
    edf = sse.build_situations()
    edf = edf[edf.status == "ok"] if not edf.empty else edf

    our_tickers = {_norm(t) for t in edf.ticker.dropna()} - {None}
    all_digest_tickers = {_norm(t) for t in digest.ticker.dropna()} - {None}

    latest = digest[(digest.issue == digest.issue.max()) & (digest.country == "US")].copy()
    latest["nt"] = latest.ticker.map(_norm)

    rows = []
    for cat, g in latest.groupby("category"):
        tickers = {t for t in g.nt if t}
        confirmed = tickers & our_tickers
        rows.append({"category": cat, "digest_US": len(tickers),
                     "confirmed": len(confirmed),
                     "rate%": round(100 * len(confirmed) / len(tickers)) if tickers else 0})
    res = pd.DataFrame(rows).sort_values("digest_US", ascending=False)

    tot_d = res.digest_US.sum()
    tot_c = res.confirmed.sum()
    # EDGAR-extra: our US situations whose ticker is in no digest issue at all
    edf2 = edf.copy()
    edf2["nt"] = edf2.ticker.map(_norm)
    extra = edf2[edf2.nt.notna() & ~edf2.nt.isin(all_digest_tickers)]

    print(f"Issue #{int(digest.issue.max())} US situations: {tot_d} · "
          f"our EDGAR confirmed: {tot_c} ({100*tot_c/tot_d:.0f}% — lower bound)\n")
    print(res.to_string(index=False))
    print(f"\nEDGAR-extra (our US flags in NO digest issue): {edf2.nt.notna().sum()} flagged, "
          f"{len(extra)} not in any digest issue")
    print(extra.category.value_counts().head(8).to_string())
    print("\n[honest] confirmation is a LOWER BOUND — the digest re-reports ongoing situations "
          "whose original filing predates our backfill window. A multi-quarter EDGAR backfill "
          "would raise it. EDGAR-extras are fresh detections OR false positives to tune.")


def main() -> int:
    run(widen=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
