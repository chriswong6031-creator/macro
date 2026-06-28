"""SEC EDGAR full-text search → guidance-change language hits (T3 of the Thematic
Foresight Desk; research/THEMATIC_FORESIGHT_DESK.md + research/THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md).

WHY (the T3 leg). T3 is the *guidance-gap* tier — the days-to-one-quarter window where
management pre-signals versus the bar the market set. The clean version needs a paywalled
expectation series (Visible Alpha / Estimize whisper) for the numeric gap, but the
LANGUAGE side is fully free: a company front-running its own print files an 8-K that
literally says "raising our guidance" / "lowering our outlook". That sentence hits the
wire FIRST; the consensus estimate revision (T4) is the lagged response over the following
days-to-weeks — so a guidance-language event mechanically LEADS T4 breadth (Hsu et al.,
bundled-guidance 8-Ks pull faster, larger revisions).

This collector mirrors collectors/edgar_fts.py exactly (keyless efts.sec.gov, UA header,
<10 req/s, drip + cached, abort-on-first-failure) but sweeps two DIRECTIONAL lexicons over
**8-K only** (where pre-announcements live) and tags each hit raise/cut. We keep only hits
whose ticker is in the curated theme universe (config `themes:`) and store them so
engine/guidance_gap.py can roll a per-theme RAISE/CUT tilt band up from the filers.

Writes data/edgar/guidance_hits.parquet (phrase, direction, form, file_date, cik, ticker,
display_name), deduped by document id + phrase. Network failure is non-fatal — the engine's
T3 leg simply stays None (the cascade runs unchanged on T1×T2×T4).

LIMITS (honest). Phrase matching has no sentence-level negation handling ("not raising
guidance" would match); the ≥2-distinct-filer guard in engine/guidance_gap.py mitigates a
single false positive, and the LLM extractor layer (blueprint §5) is where negation gets
resolved. This is a coarse directional BAND, never a numeric beat/miss.
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import pandas as pd

from collectors.edgar_facts import _get_json
from collectors.edgar_fts import _parse_hit, _theme_universe
from lib import config

log = logging.getLogger("edgar_guidance")

FTS_URL = "https://efts.sec.gov/LATEST/search-index"
FORMS = "8-K"              # pre-announcements / guidance updates file as 8-K (Item 2.02/7.01)

# Directional lexicons — high-precision exact phrases (efts does quoted phrase match).
# Ambiguous stems ("now expects", "now anticipates") are deliberately excluded — they carry
# no direction without the surrounding clause, which FTS does not return.
RAISE_PHRASES = [
    "raising our guidance", "raised its guidance", "raising full-year guidance",
    "raising our full-year guidance", "increasing our guidance", "increasing our outlook",
    "raising our outlook", "above the high end", "better than previously expected",
    "raising guidance", "raises guidance", "increased its guidance",
]
CUT_PHRASES = [
    "lowering our guidance", "lowered its guidance", "lowering full-year guidance",
    "reducing our guidance", "reducing our outlook", "lowering our outlook",
    "below our prior", "lowering guidance", "lowered guidance", "cuts guidance",
    "reducing full-year guidance",
]
_DIRECTION = {**{p: "raise" for p in RAISE_PHRASES}, **{p: "cut" for p in CUT_PHRASES}}

MAX_PAGES = 5              # 10 hits/page -> up to 50 most-recent hits per phrase
LOOKBACK_DAYS = 120        # ~2 quarters of pre-announcements (T3 is a days-to-1q window)
STALE_DAYS = 3             # guidance is time-sensitive — refresh more often than bottleneck (7)


def _cache_path():
    p = config.data_dir() / "edgar" / "guidance_hits.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _is_stale(p) -> bool:
    if not p.exists():
        return True
    try:
        df = pd.read_parquet(p)
        if df.empty or "fetched" not in df.columns:
            return True
        newest = pd.to_datetime(df["fetched"]).max().date()
        return (date.today() - newest).days >= STALE_DAYS
    except Exception:  # noqa: BLE001
        return True


def fetch_guidance_hits(force: bool = False,
                        phrases: list[str] | None = None) -> pd.DataFrame | None:
    """Sweep the directional lexicons over 8-K, filter to the theme universe, upsert the
    cache. Returns the (filtered) frame, or the existing cache when fresh / on total
    failure. Mirrors collectors/edgar_fts.fetch_bottleneck_hits."""
    p = _cache_path()
    if not force and not _is_stale(p):
        log.info("edgar_guidance cache fresh; skipping refresh")
        return pd.read_parquet(p) if p.exists() else None

    universe = _theme_universe()
    if not universe:
        return None
    enddt = date.today()
    startdt = enddt - timedelta(days=LOOKBACK_DAYS)
    rows: list[dict] = []
    first_request = True
    for phrase in (phrases or (RAISE_PHRASES + CUT_PHRASES)):
        direction = _DIRECTION.get(phrase)
        if direction is None:                   # unknown phrase (only via a custom phrases= arg)
            continue
        for page in range(MAX_PAGES):
            url = (f'{FTS_URL}?q="{phrase.replace(" ", "+")}"&forms={FORMS}'
                   f"&startdt={startdt}&enddt={enddt}&from={page * 10}")
            data = _get_json(url, retries=1 if first_request else 3)
            # network down on the very first call -> abort the whole sweep, keep any cache
            if data is None and first_request:
                log.warning("edgar_guidance: EDGAR unreachable; keeping existing cache")
                return pd.read_parquet(p) if p.exists() else None
            first_request = False
            hits = ((data or {}).get("hits") or {}).get("hits") or []
            if not hits:
                break
            for h in hits:
                rec = _parse_hit(h)
                if rec and rec["ticker"] in universe:
                    rec["phrase"] = phrase
                    rec["direction"] = direction
                    rows.append(rec)
            time.sleep(0.15)               # fair-access pacing (<10 req/s)
            if len(hits) < 10:
                break

    today = date.today().isoformat()
    if not rows:
        log.info("edgar_guidance: no in-universe guidance-language hits this sweep")
        if p.exists():
            return pd.read_parquet(p)
        return None
    new = pd.DataFrame(rows)
    new["fetched"] = today
    if p.exists():
        try:
            old = pd.read_parquet(p)
            new = pd.concat([old, new], ignore_index=True)
        except Exception:  # noqa: BLE001
            pass
    new = new.drop_duplicates(subset=["id", "phrase"]).reset_index(drop=True)
    new.to_parquet(p, index=False)
    log.info("edgar_guidance: %d guidance-language hits cached -> %s", len(new), p)
    return new


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    df = fetch_guidance_hits(force=True)
    print(f"rows: {0 if df is None else len(df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
