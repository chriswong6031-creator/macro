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
unreadable cache degrades to ``facts=None`` and a distinct "not loaded yet"
caller-facing status (never "no SEC filings available" -- that is a positive
claim this producer must have actually earned), it never raises out of this
module, and it never invents a name/theme-matched identity.

Three distinct null states (META-CEO ruling round 2, packet B-F09-3 B2)
------------------------------------------------------------------------
A cache MISS (this producer has never reached this CIK, or its last attempt
was a transient network failure) is not the same claim as a cache HIT that
positively confirms the issuer has no SEC filings at all -- conflating the two
would render "No SEC filings available" for a listing this producer simply
has not gotten to yet, which is a fabricated negative. ``refresh_cache_for_cik``
therefore always WRITES a cache file once it has genuinely completed a fetch
cycle (even when that cycle found nothing), and marks a confirmed-empty result
with ``confirmed_no_filings: true`` so a caller can tell the two apart:

  * no cache file on disk               -> caller renders "not loaded yet"
  * cache file, ``confirmed_no_filings`` -> caller passes ``companyfacts=None``
    to ``extract_maturity_ladder`` -> engine's own ``no_filings`` status
  * cache file, real (possibly empty per-tag) facts -> caller passes the
    facts through -> engine's own ``no_maturity_facts`` / ``reported`` status

``refresh_cache_for_cik`` has two call modes. Standalone (``full_companyfacts``
omitted) fetches the six bounded tags itself from SEC's companyconcept API --
used by backfill/ad-hoc tooling. Wired (``full_companyfacts`` supplied by a
caller that already fetched the filer's full companyfacts document in the SAME
nightly step -- ``collectors/edgar_facts.py``'s per-issuer companyfacts fetch,
which this producer is wired into) reuses that payload instead of six more
network round trips; passing ``full_companyfacts=None`` there means the
caller's own fetch positively confirmed (an HTTP 404 on the full companyfacts
document, not a timeout) that this CIK carries no SEC filings at all.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

log = logging.getLogger(__name__)

# Sentinel distinguishing "full_companyfacts not supplied at all" (standalone
# mode: fetch it myself) from "supplied and is None" (wired mode: the caller's
# own fetch already ran and positively found nothing for this CIK).
_UNSET: Any = object()

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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_cached_facts(cik: str) -> dict[str, Any] | None:
    """Read the bounded per-issuer cache produced by `refresh_cache_for_cik`.

    Returns None on any absence/parse failure -- the caller must NOT treat
    this as "confirmed no SEC filings" (that positive claim is only earned by
    a cache file that carries ``confirmed_no_filings: true`` -- see
    `load_debt_maturity_facts`); an absent/unreadable cache is "not loaded
    yet", never a fabricated negative.
    """
    path = _cache_dir() / f"CIK{cik}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) else None


def _write_cache_from_full_companyfacts(cik: str, full_companyfacts: Mapping[str, Any] | None) -> bool:
    """Wired-mode cache write: slim the six bounded tags out of an
    already-fetched full companyfacts document (no network call here at all).

    ``full_companyfacts=None`` means the caller's own fetch positively
    confirmed (an HTTP 404 on the full companyfacts document -- not a timeout
    or a transient failure, which the caller must never pass through here)
    that this CIK has no SEC filings; that is recorded as
    ``confirmed_no_filings`` so ``load_debt_maturity_facts`` can render the
    genuine "no SEC filings available" state instead of a blanket "not
    reported" or a fabricated "not loaded yet".
    """
    try:
        cache_dir = _cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        now = _utc_now_iso()
        if not full_companyfacts:
            merged: dict[str, Any] = {
                "cik": int(cik), "facts": {"us-gaap": {}},
                "fetched_at": now, "confirmed_no_filings": True,
            }
        else:
            usgaap = ((full_companyfacts or {}).get("facts") or {}).get("us-gaap") or {}
            slim: dict[str, Any] = {}
            for tag in _TAGS:
                node = usgaap.get(tag)
                if node and node.get("units"):
                    slim[tag] = {"units": node["units"]}
            merged = {"cik": int(cik), "facts": {"us-gaap": slim}, "fetched_at": now}
        tmp = cache_dir / f".CIK{cik}.json.tmp"
        tmp.write_text(json.dumps(merged))
        tmp.replace(cache_dir / f"CIK{cik}.json")
        return True
    except Exception:  # noqa: BLE001 -- never fatal to the caller's own build/collector
        return False


def refresh_cache_for_cik(
    cik: str, *, session: Any = None, timeout: float = 10.0, full_companyfacts: Any = _UNSET,
) -> bool:
    """Warm the bounded per-issuer debt-maturity cache for `cik`.

    Two modes (see module docstring):

    * Wired (``full_companyfacts`` explicitly supplied, even as ``None``):
      reuses a companyfacts document a caller already fetched in the SAME
      nightly step -- no network call happens here. This is the mode
      ``collectors/edgar_facts.py`` calls for every issuer its own build
      already companyfacts-fetches (packet B-F09-3 B1 wiring).
    * Standalone (``full_companyfacts`` omitted): fetches the six bounded
      debt-maturity tags itself from SEC's public companyconcept API (one
      small per-tag document each) -- used by ad-hoc/backfill tooling, never
      by the render path. Best-effort: a total network failure across every
      tag leaves the existing cache (if any) untouched and returns False; a
      completed round trip (even one that found nothing) always writes,
      distinguishing "asked and got nothing" from "never asked".
    """
    if full_companyfacts is not _UNSET:
        return _write_cache_from_full_companyfacts(cik, full_companyfacts)
    try:
        import requests  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return False
    sess = session or requests
    merged: dict[str, Any] = {"cik": int(cik), "facts": {"us-gaap": {}}}
    got_any = False
    any_clean_response = False
    for tag in _TAGS:
        url = _SEC_COMPANYCONCEPT_URL.format(cik=cik, tag=tag)
        try:
            resp = sess.get(url, timeout=timeout, headers={"User-Agent": "mastermind-x debt-maturity/1.0"})
        except Exception:  # noqa: BLE001 -- a transient failure never overwrites the existing cache
            continue
        # Any HTTP response at all (200, 404, ...) means the round trip to SEC
        # completed -- this is what lets "asked every tag and found nothing"
        # be told apart from "every single tag request failed" (network down),
        # which must leave the existing cache untouched, not confirm a false
        # negative.
        any_clean_response = True
        if resp.status_code != 200:
            continue
        try:
            payload = resp.json()
        except Exception:  # noqa: BLE001
            continue
        units = payload.get("units") if isinstance(payload, dict) else None
        if not units:
            continue
        merged["facts"]["us-gaap"][tag] = {"units": units}
        got_any = True
    if not any_clean_response:
        return False
    merged["fetched_at"] = _utc_now_iso()
    if not got_any:
        merged["confirmed_no_filings"] = True
    cache_dir = _cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = cache_dir / f".CIK{cik}.json.tmp"
    tmp.write_text(json.dumps(merged))
    tmp.replace(cache_dir / f"CIK{cik}.json")
    return True


def load_debt_maturity_facts(ticker: str) -> tuple[str | None, dict[str, Any] | None, str]:
    """Resolve `ticker` and return (cik, facts_or_None, cache_state).

    ``cache_state`` is one of:

      * ``"unresolved"`` -- the ticker has no CIK resolution at all yet (an
        identity gap, not a positive claim about SEC filings).
      * ``"not_loaded"`` -- the CIK resolved, but this producer has never
        completed a fetch cycle for it (cache file absent). Renders "Debt
        schedule not loaded yet.", never "no SEC filings available".
      * ``"confirmed_no_filings"`` -- a completed fetch cycle positively found
        no SEC filings for this CIK at all.
      * ``"loaded"`` -- a completed fetch cycle produced real (possibly
        empty-per-tag) companyfacts; pass `facts` to
        ``engine.debt_maturity.extract_maturity_ladder``, whose own
        ``no_maturity_facts``/``reported``/``identity_mismatch`` statuses
        already distinguish "has filings, no maturity breakdown" from
        "reported"."""
    cik = resolve_cik(ticker)
    if cik is None:
        return None, None, "unresolved"
    cached = load_cached_facts(cik)
    if cached is None:
        return cik, None, "not_loaded"
    if cached.get("confirmed_no_filings"):
        return cik, None, "confirmed_no_filings"
    return cik, cached, "loaded"
