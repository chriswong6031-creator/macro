"""Heavy backlog burn-down for the Special Situations desk (roadmap Tier-2.2).

The daily build deliberately processes only a bounded slice of the ~23k-deferred backlog
(so it can never stall the engine job). This runs the same enrichment lanes with HIGH,
env-overridable per-run limits to chew through the historical backlog faster, then leaves
the rest to converge daily. Progress persists in events.parquet (committed by the workflow).

Triggered by .github/workflows/special-sits-backfill.yml (manual dispatch or weekly cron);
no-op for the LLM lanes without DEEPSEEK_API_KEY. Run priors regen + desk render as
separate workflow steps after this.
"""
from __future__ import annotations

import logging
import os


def _lim(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    from collectors import special_situations as col
    col.fetch_events()                                       # make sure the store is current
    col.enrich_text(limit=_lim("SS_TEXT_LIMIT", 6000))      # keyword pre-filter (cheap, SEC-paced)
    col.enrich_filers(limit=_lim("SS_FILER_LIMIT", 3000))   # P3.2 13D cover-page reporting person
    col.enrich_classify(limit=_lim("SS_CLASSIFY_LIMIT", 1500))  # P1.1 LLM verify (gated; no-op w/o key)
    col.enrich_summaries(limit=_lim("SS_SUMMARY_LIMIT", 1000))  # P1.3 LLM summary (gated; no-op w/o key)
    print("[special-sits-backfill] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
