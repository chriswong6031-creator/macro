"""Bounded XBRL debt-maturity ingestion producer (packet B-F09-3).

Ledger rows MO-PAID-059 / MO-DELTA-018 sequence this as "first a NEW bounded
XBRL debt-maturity ingestion producer" -- a self-contained module, separate
from the general capital-structure companyfacts governance system
(collectors/sec_capital_structure_companyfacts.py), which is a receipt/
coverage-shaped store that deliberately exposes no raw Company Facts bytes
(engine/capital_structure/companyfacts_authenticated_read.py is a metadata-
only read facade by design, not a source of parseable XBRL facts).

Responsibilities, and only these:

  1. Resolve a ticker to its canonical SEC CIK using the two resolvers that
     already exist and are already committed (GATE 0 finding B2) --
     data/edgar/ticker_cik_ledger.json first, falling back to the
     issuer_master reference parquet's own cik column.
  2. Read (and, online, refresh) a small per-issuer cache of exactly the six
     debt-maturity XBRL tags this feature needs, in the real SEC XBRL
     companyfacts shape engine/debt_maturity.py already expects:
     ``{"cik": <int>, "facts": {"us-gaap": {<tag>: {"units": {"USD": [...]}}}}}``.
     The cache lives under its own bounded path
     (``data/debt_maturity/cache/CIK<10-digit>.json``) -- this is a NEW
     producer-owned artifact, not an assertion about the shape of the
     existing companyfacts store.

No network call is required for the pure engine or for tests: a missing or
unreadable cache degrades to ``facts=None`` (the caller renders "no SEC
filings available"), it never raises out of this module, and it never
invents a name/theme-matched identity.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Only these six tags are ever requested -- the "bounded" half of "bounded
# ingestion producer": this module has no path to any other XBRL concept.
from engine.debt_maturity import BUCKETS as _BUCKETS  # noqa: E402

_TAGS = tuple(tag for _key, tag, _en, _zh in _BUCKETS)

_SEC_COMPANYCONCEPT_URL = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
)


def _cik_ledger_path() -> Path:
    from lib import config as _cfg  # noqa: PLC0415

    return _cfg.data_dir() / "edgar" / "ticker_cik_ledger.json"


def _issuer_master_path() -> Path:
    from lib import config as _cfg  # noqa: PLC0415

    return _cfg.data_dir() / "reference" / "issuer_master.parquet"


def _cache_dir() -> Path:
    from lib import config as _cfg  # noqa: PLC0415

    return _cfg.data_dir() / "debt_maturity" / "cache"


def resolve_cik(ticker: str) -> str | None:
    """Resolve `ticker` -> canonical 10-digit CIK, or None if unresolvable.

    Tries the committed ticker->CIK ledger first (a flat ``{ticker: cik}`` or
    ``{ticker: {"cik": ...}}`` JSON map), then falls back to the
    issuer_master reference parquet's own ticker/cik columns. Never matches
    on company name.
    """
    ticker = (ticker or "").strip().upper()
    if not ticker:
        return None

    ledger_path = _cik_ledger_path()
    if ledger_path.exists():
        try:
            ledger = json.loads(ledger_path.read_text())
        except Exception:  # noqa: BLE001 -- a corrupt ledger falls through to the parquet
            ledger = None
        if isinstance(ledger, dict):
            entry = ledger.get(ticker)
            cik_val: Any = entry.get("cik") if isinstance(entry, dict) else entry
            if cik_val:
                try:
                    return _canon(cik_val)
                except ValueError:
                    pass

    im_path = _issuer_master_path()
    if im_path.exists():
        try:
            import pandas as pd  # noqa: PLC0415

            issuer_master = pd.read_parquet(im_path)
        except Exception:  # noqa: BLE001
            return None
        ticker_col = next((c for c in ("ticker", "symbol") if c in issuer_master.columns), None)
        if ticker_col is None or "cik" not in issuer_master.columns:
            return None
        rows = issuer_master[issuer_master[ticker_col].astype(str).str.upper() == ticker]
        if rows.empty:
            return None
        raw_cik = rows.iloc[0].get("cik")
        # a float64 parquet column (e.g. 320193.0) must round-trip cleanly --
        # never string()-and-strip a float repr, which leaves a trailing ".0".
        try:
            if raw_cik is None:
                return None
            cik_int = int(float(raw_cik))
            return _canon(cik_int)
        except (TypeError, ValueError):
            return None
    return None


def _canon(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    if not raw.isdigit() or int(raw) == 0 or len(raw) > 10:
        raise ValueError(f"invalid CIK: {value!r}")
    return raw.zfill(10)


def load_cached_facts(cik: str) -> dict[str, Any] | None:
    """Read the bounded per-issuer cache produced by `refresh_cache_for_cik`.

    Returns None on any absence/parse failure -- the caller renders the
    distinct "no SEC filings available" null state, never a fabricated one.
    """
    path = _cache_dir() / f"CIK{cik}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def refresh_cache_for_cik(cik: str, *, session: Any = None, timeout: float = 10.0) -> bool:
    """Fetch the six bounded debt-maturity tags from SEC's public
    companyconcept API (one small per-tag document each -- the "bounded"
    half of this producer's network footprint) and write the merged cache.

    Best-effort: any network/parse failure leaves the existing cache (if any)
    untouched and returns False. Never raises. Off the render path by design
    -- this is meant to run from a standalone refresh job, not from the
    nightly stock-library build itself.
    """
    try:
        import requests  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return False
    sess = session or requests
    merged: dict[str, Any] = {"cik": int(cik), "facts": {"us-gaap": {}}}
    got_any = False
    for tag in _TAGS:
        url = _SEC_COMPANYCONCEPT_URL.format(cik=cik, tag=tag)
        try:
            resp = sess.get(url, timeout=timeout, headers={"User-Agent": "mastermind-x debt-maturity/1.0"})
            if resp.status_code != 200:
                continue
            payload = resp.json()
        except Exception:  # noqa: BLE001
            continue
        units = payload.get("units") if isinstance(payload, dict) else None
        if not units:
            continue
        merged["facts"]["us-gaap"][tag] = {"units": units}
        got_any = True
    if not got_any:
        return False
    cache_dir = _cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_dir / f".CIK{cik}.json.tmp"
    tmp.write_text(json.dumps(merged))
    tmp.replace(cache_dir / f"CIK{cik}.json")
    return True


def load_debt_maturity_facts(ticker: str) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve `ticker` and return (cik, facts_or_None).

    ``cik`` is None only when the ticker has no CIK resolution at all (an
    identity gap, distinct from "resolved issuer, no filings cached" --
    callers must render the two differently per acceptance #2)."""
    cik = resolve_cik(ticker)
    if cik is None:
        return None, None
    return cik, load_cached_facts(cik)
