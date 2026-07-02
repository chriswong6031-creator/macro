"""SEC EDGAR full-text search → bottleneck-language hits (leg 6 of engine/bottleneck.py;
research/THEMATIC_FORESIGHT_DESK.md T1).

WHY. The highest-signal, lowest-cost leg of the 13D HBM pattern is the firm itself saying
the words — "sold out," "capacity constrained," "on allocation," "longer lead times." SEC
EDGAR full-text search is keyless (UA header, <10 req/s, 2001→present) and surfaces the
exact sentence at the filer level. We sweep a phrase dictionary across 10-K/10-Q/8-K,
keep only hits whose ticker is in our curated theme universe (config `themes:`), and store
them so the engine can read mention FREQUENCY + ACCELERATION per theme.

SNIPPET PROBE RESULT (2026-07-02): the EDGAR search-index endpoint returns ONLY metadata
in _source (ciks, display_names, file_date, root_forms, adsh, …) — there is NO
highlight/excerpt/snippet field in the JSON response. Fallback (b) from spec §P0-B is
therefore in effect: polarity column = null for all rows, and the ≥2-distinct-filers gate
carries the noise burden until a per-filing document fetcher lands (that is L-effort,
out of scope for W1a/b). The polarity column is auditable — once a doc-fetcher lands
it can populate affirmative/negated retroactively without schema changes.

Bounded + drip + cached (mirrors collectors/edgar_rpo): refreshes only when the cache is
stale, caps pages per phrase, reuses collectors.edgar_facts._get_json for the fair-access
UA/pacing.

Outputs:
  data/edgar/bottleneck_hits.parquet  (phrase, form, file_date, cik, ticker, display_name,
                                       fetched, polarity[null])
  data/edgar/glut_hits.parquet        (same schema; §3.6 glut text tier)
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from collectors.edgar_facts import _get_json
from lib import config

log = logging.getLogger("edgar_fts")

FTS_URL = "https://efts.sec.gov/LATEST/search-index"
FORMS = "10-K,10-Q,8-K"

# ── Bottleneck (scarcity) phrase dictionary ──────────────────────────────────
PHRASES = [
    "sold out", "capacity constrained", "supply constrained", "on allocation",
    "longer lead times", "extended lead times", "record backlog",
    "unable to meet demand", "demand exceeds supply", "tight supply",
]

# ── Glut (capacity-adds) phrase dictionary  §3.6 ─────────────────────────────
GLUT_PHRASES = [
    "capacity expansion", "new fab", "adding capacity", "additional capacity",
    "capacity coming online", "increased supply", "inventory normalization",
    "excess inventory", "capacity ramp",
]

MAX_PAGES = 5              # 10 hits/page -> up to 50 most-recent hits per phrase
LOOKBACK_DAYS = 400        # window swept (covers the engine's 240d accel window + margin)
STALE_DAYS = 7             # skip refresh if the cache's newest fetch is younger than this

# EDGAR display_names come in two shapes, both handled below:
#   legacy   "COMPANY  (TICK, CIK 0001234567)"          — ticker + CIK in ONE paren
#   current  "COMPANY  (TICK)  (CIK 0001234567)"        — ticker and CIK in SEPARATE parens
#            "COMPANY  (TICK, TICK-WT)  (CIK ...)"       — multiple share classes / warrants
#            "Boeing Co (The)  (BA)  (CIK 0000012927)"  — a name-paren BEFORE the ticker paren
# The old regex only matched the legacy single-paren form, so every current-format hit
# parsed to None (silently dropping the entire EDGAR-language leg). The ticker paren is the
# LAST ticker-shaped paren immediately preceding the CIK paren — so an issuer-name paren like
# "(The)" (Boeing/Coca-Cola/Disney/Carlyle) is overwritten by the real "(BA)" paren rather
# than mistaken for the ticker.
_PAREN_RE = re.compile(r"\(([^)]*)\)")
_TICKER_TOK = re.compile(r"^[A-Z][A-Z.\-]{0,6}$")
# common issuer-name-paren tokens that are ticker-SHAPED but are not tickers
_NOT_TICKER = {"THE", "INC", "CO", "CORP", "LP", "LLP", "LLC", "LTD", "PLC", "SA", "AG",
               "NV", "SE", "AB", "NEW", "OLD", "CLASS", "OF", "GROUP", "HLDG", "HLDGS"}


def _tickers_from_display(name: str) -> list[str]:
    """Tickers from the paren immediately preceding the CIK paren (the ticker paren).

    Returns [] when no ticker-shaped token precedes the CIK. Handles the legacy single-paren
    '(TICK, CIK ..)', the current two-paren '(TICK) (CIK ..)', multi-class '(TICK, TICK-WT)',
    and a leading issuer-name paren like '(The)' (which gets overwritten by the real paren)."""
    last: list[str] = []
    for grp in _PAREN_RE.findall(name or ""):
        g = grp.strip()
        if g.upper().startswith("CIK"):
            return last                         # the ticker paren is the one just before CIK
        toks = []
        for tok in g.split(","):
            tok = tok.strip().upper()
            if tok and tok not in _NOT_TICKER and tok != "CIK" and _TICKER_TOK.match(tok):
                toks.append(tok)
        if toks:
            last = toks                         # overwrite earlier name-parens like (The)
    return last                                 # legacy form (CIK lives inside the ticker paren)


def _parse_hit(h: dict) -> dict | None:
    src = h.get("_source") or {}
    names = src.get("display_names") or []
    if not names:
        return None
    cand = _tickers_from_display(names[0])
    if not cand:
        return None
    ticker = cand[0]
    ciks = src.get("ciks") or []
    return {
        "id": h.get("_id"),
        "ticker": ticker,
        "cik": str(ciks[0]) if ciks else None,
        "form": (src.get("root_forms") or [src.get("file_type")] or [None])[0],
        "file_date": src.get("file_date"),
        "display_name": names[0],
        # polarity: null — EDGAR FTS returns no snippet/highlight field (probe 2026-07-02).
        # Fallback (b): the ≥2-distinct-filers gate carries the noise burden.
        # A per-filing doc-fetcher (L-effort) can populate this retroactively in a later wave.
        "polarity": None,
    }


def _is_stale(p: Path) -> bool:
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


def _theme_universe() -> set[str]:
    themes = (config.load() or {}).get("themes") or {}
    out: set[str] = set()
    for spec in themes.values():
        out.update(spec.get("tickers") or [])
    return out


def _sweep_phrases(
    phrases: list[str],
    universe: set[str],
    cache_path: Path,
    force: bool = False,
) -> pd.DataFrame | None:
    """Core sweep helper — shared by bottleneck and glut sweeps.

    Queries EDGAR FTS for each phrase, filters to theme-universe tickers, upserts
    the cache parquet at `cache_path`, and returns the result frame.

    Returns None only on a total network failure on the very first request; otherwise
    returns the (possibly cached) frame.
    """
    if not force and not _is_stale(cache_path):
        log.info("edgar_fts cache fresh (%s); skipping refresh", cache_path.name)
        return pd.read_parquet(cache_path) if cache_path.exists() else None

    enddt = date.today()
    startdt = enddt - timedelta(days=LOOKBACK_DAYS)
    rows: list[dict] = []
    first_request = True

    for phrase in phrases:
        for page in range(MAX_PAGES):
            url = (f'{FTS_URL}?q="{phrase.replace(" ", "+")}"&forms={FORMS}'
                   f"&startdt={startdt}&enddt={enddt}&from={page * 10}")
            data = _get_json(url, retries=1 if first_request else 3)
            # network down / endpoint unreachable on the very first call -> abort the whole
            # sweep (don't grind through dozens of 40s timeouts) and keep any existing cache.
            if data is None and first_request:
                log.warning("edgar_fts: EDGAR unreachable; keeping existing cache (%s)",
                            cache_path.name)
                return pd.read_parquet(cache_path) if cache_path.exists() else None
            first_request = False
            hits = ((data or {}).get("hits") or {}).get("hits") or []
            if not hits:
                break
            for h in hits:
                rec = _parse_hit(h)
                if rec and rec["ticker"] in universe:
                    rec["phrase"] = phrase
                    rows.append(rec)
            time.sleep(0.15)               # fair-access pacing (<10 req/s)
            if len(hits) < 10:
                break

    today = date.today().isoformat()
    if not rows:
        log.info("edgar_fts: no in-universe hits this sweep (%s)", cache_path.name)
        # still stamp a fetch so we don't re-sweep every build on an empty window
        if cache_path.exists():
            return pd.read_parquet(cache_path)
        return None

    new = pd.DataFrame(rows)
    new["fetched"] = today

    if cache_path.exists():
        try:
            old = pd.read_parquet(cache_path)
            new = pd.concat([old, new], ignore_index=True)
        except Exception:  # noqa: BLE001
            pass

    # Ensure polarity column is always present (may not exist in old rows pre-W1a)
    if "polarity" not in new.columns:
        new["polarity"] = None

    new = new.drop_duplicates(subset=["id", "phrase"]).reset_index(drop=True)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    new.to_parquet(cache_path, index=False)
    log.info("edgar_fts: %d hits cached -> %s", len(new), cache_path)
    return new


# ── Public fetch functions ────────────────────────────────────────────────────

def _bottleneck_cache_path() -> Path:
    p = config.data_dir() / "edgar" / "bottleneck_hits.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _glut_cache_path() -> Path:
    p = config.data_dir() / "edgar" / "glut_hits.parquet"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def fetch_bottleneck_hits(force: bool = False,
                          phrases: list[str] | None = None) -> pd.DataFrame | None:
    """Sweep the bottleneck phrase dictionary, filter to the theme universe, upsert the cache.
    Returns the (filtered) frame, or the existing cache when fresh / on total failure."""
    universe = _theme_universe()
    if not universe:
        return None
    return _sweep_phrases(
        phrases=(phrases or PHRASES),
        universe=universe,
        cache_path=_bottleneck_cache_path(),
        force=force,
    )


def fetch_glut_hits(force: bool = False,
                    phrases: list[str] | None = None) -> pd.DataFrame | None:
    """Sweep the glut (capacity-adds) phrase dictionary (§3.6). Same polarity-null
    fallback as the bottleneck sweep — no snippet available from the FTS endpoint."""
    universe = _theme_universe()
    if not universe:
        return None
    return _sweep_phrases(
        phrases=(phrases or GLUT_PHRASES),
        universe=universe,
        cache_path=_glut_cache_path(),
        force=force,
    )


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    df_bn = fetch_bottleneck_hits(force=True)
    df_gl = fetch_glut_hits(force=True)
    print(f"bottleneck rows: {0 if df_bn is None else len(df_bn)}")
    print(f"glut rows:       {0 if df_gl is None else len(df_gl)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
