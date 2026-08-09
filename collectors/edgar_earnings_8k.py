"""SEC EDGAR 8-K Item 2.02 earnings-announcement date collector (Entry-Stack W1).

PURPOSE — S-EV anchor build (masterplan §3 F1 / §6 W1).
The existing `data/edgar/eps_quarterly.parquet` carries asof_date = period_end + 60d
(synthetic constant, std=0 — RT blocker finding). S-EV's historical backtest needs a
REAL point-in-time announcement anchor: the SEC filing date of the 8-K that carries
Item 2.02 "Results of Operations and Financial Condition" — the press-release vehicle.

PIT NOTE: filing_date (the date SEC accepted the filing) is the PIT-visible proxy.
The earnings press release is typically issued the same calendar day or one calendar
day before. Use filing_date conservatively: a trade entered T+1 after filing_date is
strictly-after-announcement. acceptance_datetime (UTC, from acceptanceDateTime field)
is stored when available for sub-day precision but is NOT required for the historical
backtest (which only needs calendar-day PIT accuracy).

EXACT-TOKEN MATCHING: items in the submissions JSON are comma-separated tokens such as
"2.02,9.01" or "2.02". Matching is done by splitting on commas and checking membership
of the stripped token "2.02" — NOT substring matching (which would also match "12.02"
or "2.020" if those tokens ever appeared). The tokenize_items / has_item_202 functions
below are unit-tested.

UNIVERSE: tickers/CIKs from data/edgar/eps_quarterly.parquet (~1,317 names). We use the
same company_tickers.json CIK map used by collectors/edgar_eps.py and edgar_8k.py.

OUTPUT STORE: data/edgar/earnings_8k_dates.parquet
  Columns: ticker (str), cik (int), accession (str, canonical dashed), form (str),
           filing_date (date str yyyy-mm-dd), acceptance_datetime (str, ISO-UTC or
           empty), report_date (str, period of report), items (str, raw comma-sep).
  Append-deduped per the canonical filing key (cik, accession) — see
  append_and_dedup. The "older-files" pagination in the submissions JSON is
  followed for full history.

FILING KEY (Wave 1B, contract freeze Q2): accession is captured because without
  it this store shares only `ticker` with engine/marketing/edgar_earnings_wire.py
  and the two EDGAR planes cannot be joined at any level. It is already present
  in the same parallel-array block this collector walks, so capture costs no
  extra request.

RESUMABILITY: a per-CIK manifest (data/edgar/earnings_8k_dates_manifest.json) tracks
which CIKs have been fully fetched (key = str(cik), value = ISO timestamp). Run the
collector again and already-fetched CIKs are skipped. Pass --force to re-fetch all.

SENTINEL STAGING DETERMINATION (one-shot backfill):
  This store is produced by a one-shot backfill (this script). It does NOT need to run
  nightly — earnings 8-K dates are historical facts that do not change once filed.
  A light incremental refresh (new names added to the universe over time) can be wired
  into the nightly via the same resumable manifest; the manifest-based skip ensures
  already-fetched CIKs add no network cost. No sentinel staging entry is required for the
  initial S-EV backtest study. If a future nightly refresh is desired, add a step in
  daily.yml that calls `python -m collectors.edgar_earnings_8k --incremental` and include
  data/edgar/earnings_8k_dates.parquet in the existing `git add data/` step (already
  covered by the daily workflow's blanket `git add data/`).

SEC RATE LIMIT: <=10 req/s (strictly). This collector sleeps PACE_S=0.12 between CIK
requests matching the pattern in edgar.py and edgar_8k.py. For ~1,317 CIKs that requires
~2.6 minutes of API time at full throughput (plus per-CIK pagination calls for older
filings, bounded by the older-files list length). Budget: 6-15 minutes total.

ERRORS: per-CIK exceptions are logged at WARNING level and the CIK is recorded in the
manifest with status="error". The run never silently skips — zero-8K-result CIKs are
explicitly flagged. Coverage verdict is printed at the end.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Bootstrap repo root onto sys.path so `lib.*` imports work
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib import config  # noqa: E402
from engine.earnings_release.filing_key import (  # noqa: E402
    FilingIdentityError,
    normalize_accession,
)

log = logging.getLogger(__name__)

# The store's columns, in order.  ``accession`` and ``report_date`` were added
# by Wave 1B; ``load_existing`` still reads a parquet written before that and
# ``append_and_dedup`` keys such rows the old way (see its docstring).
STORE_COLUMNS = [
    "ticker", "cik", "accession", "form", "filing_date",
    "acceptance_datetime", "report_date", "items",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{:010d}.json"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
PACE_S = 0.12        # SEC fair-access: <=10 req/s
RETRIES = 3
TIMEOUT = 30

# SEC requires a declared User-Agent with a name + email contact.
# Pattern from edgar_8k.py and edgar_eps.py.
_SEC_UA = "macro-dashboard admin@macro-dashboard.example.com"

# Item 2.02 token (exact string after comma-split and strip).
ITEM_202 = "2.02"

# Coverage gate (masterplan §3 F1)
COVERAGE_GATE_NAMES = 800     # minimum names with ≥8y of Item-2.02 history
COVERAGE_GATE_YEARS = 8       # minimum years of history per name


# ---------------------------------------------------------------------------
# Tokenizer (unit-testable, no live API)
# ---------------------------------------------------------------------------

def tokenize_items(raw: str | None) -> list[str]:
    """Split a raw items string from EDGAR submissions JSON into clean tokens.

    EDGAR stores items as a comma-separated string like "2.02,9.01" or " 2.02 ".
    This function strips whitespace from each token and returns a list of non-empty
    tokens. Empty strings and None inputs return [].

    >>> tokenize_items("2.02,9.01")
    ['2.02', '9.01']
    >>> tokenize_items(" 2.02 ")
    ['2.02']
    >>> tokenize_items("12.02,9.01")
    ['12.02', '9.01']
    >>> tokenize_items("")
    []
    >>> tokenize_items(None)
    []
    """
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def has_item_202(raw: str | None) -> bool:
    """Return True iff the raw items string contains the EXACT token "2.02".

    Uses tokenize_items for splitting — never substring matching — so "12.02" and
    "2.020" are NOT matched.

    >>> has_item_202("2.02,9.01")
    True
    >>> has_item_202("12.02,9.01")
    False
    >>> has_item_202("2.02")
    True
    >>> has_item_202("9.01")
    False
    >>> has_item_202(None)
    False
    >>> has_item_202("")
    False
    """
    return ITEM_202 in tokenize_items(raw)


# ---------------------------------------------------------------------------
# HTTP helper (mirrors edgar.py / edgar_8k.py convention)
# ---------------------------------------------------------------------------

def _sec_get_json(url: str) -> dict | None:
    """Fetch a JSON endpoint from data.sec.gov with retries and fair-access pacing."""
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            r = requests.get(
                url,
                headers={"User-Agent": _SEC_UA, "Accept-Encoding": "gzip, deflate"},
                timeout=TIMEOUT,
            )
            if r.status_code == 404:
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                # Transient — back off and retry
                wait = 2.0 * (attempt + 1)
                log.debug("HTTP %d for %s — retry in %.1fs", r.status_code, url, wait)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            if attempt < RETRIES - 1:
                time.sleep(1.5 * (attempt + 1))
    log.warning("edgar_earnings_8k: GET failed %s: %s", url.split("?")[0], last)
    return None


# ---------------------------------------------------------------------------
# CIK mapping (reuses company_tickers.json cache)
# ---------------------------------------------------------------------------

def _load_company_tickers() -> dict | None:
    """Load SEC ticker->CIK JSON from cache or fetch it (shared cache with edgar.py)."""
    cache = config.data_dir() / "edgar" / "company_tickers.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except Exception:  # noqa: BLE001
            pass
    data = _sec_get_json(TICKERS_URL)
    time.sleep(PACE_S)
    if data:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(data))
    return data


def build_cik_map(tickers: list[str]) -> dict[str, int]:
    """Return {ticker: cik} for the provided ticker list using the SEC JSON."""
    data = _load_company_tickers()
    if not data:
        raise RuntimeError("edgar_earnings_8k: could not load company_tickers.json")
    sec: dict[str, int] = {
        row["ticker"].upper(): int(row["cik_str"]) for row in data.values()
    }
    out: dict[str, int] = {}
    for t in tickers:
        u = t.upper()
        for cand in (u, u.replace("-", "."), u.replace(".", "-"),
                     u.split("-")[0], u.split(".")[0]):
            if cand in sec:
                out[t] = sec[cand]
                break
    return out


# ---------------------------------------------------------------------------
# Submissions API: parse all 8-K Item-2.02 filings for one CIK
# ---------------------------------------------------------------------------

def _normalize_accession(raw: object) -> str:
    """Canonical dashed accession, or "" when the payload omits it.

    Delegates to the one place that decides what a filing key is.  An
    unparseable value becomes "" rather than raising: a malformed accession on
    one filing must not abort a CIK's whole history, and a row that carries ""
    is reported as unjoinable downstream instead of silently mis-joining.
    """
    if raw in (None, ""):
        return ""
    try:
        return normalize_accession(raw)
    except FilingIdentityError:
        log.warning("edgar_earnings_8k: unparseable accessionNumber %r — stored empty", raw)
        return ""


def _extract_8k_rows(ticker: str, cik: int, rec: dict) -> list[dict]:
    """Extract Item-2.02 8-K rows from a 'recent' or older-files filing block.

    ``accessionNumber`` is captured alongside the fields this collector already
    read.  It sits in the same parallel-array structure as ``form`` /
    ``filingDate`` / ``acceptanceDateTime`` / ``items``, so the capture costs no
    extra request — and without it this store shares only ``ticker`` with
    ``engine/marketing/edgar_earnings_wire.py`` and the two planes cannot be
    joined at all (contract freeze Q2).
    """
    forms = rec.get("form") or []
    filing_dates = rec.get("filingDate") or []
    acceptance_dts = rec.get("acceptanceDateTime") or []
    accessions = rec.get("accessionNumber") or []
    report_dates = rec.get("reportDate") or []
    items_list = rec.get("items") or []

    def _safe(lst: list, i: int):
        return lst[i] if i < len(lst) else None

    rows = []
    for i, form in enumerate(forms):
        if form not in ("8-K", "8-K/A"):
            continue
        raw_items = _safe(items_list, i) or ""
        if not has_item_202(raw_items):
            continue
        rows.append({
            "ticker": ticker,
            "cik": int(cik),
            "accession": _normalize_accession(_safe(accessions, i)),
            "form": str(form),
            "filing_date": _safe(filing_dates, i) or "",
            "acceptance_datetime": _safe(acceptance_dts, i) or "",
            # The period of report is what re-groups an 8-K/A with the 8-K it
            # amends; without it a correction mints a second event.
            "report_date": _safe(report_dates, i) or "",
            "items": raw_items,
        })
    return rows


def fetch_earnings_8k_for_cik(ticker: str, cik: int) -> tuple[list[dict], int]:
    """Fetch all 8-K Item-2.02 filings for one CIK from the submissions API.

    Follows the older-files pagination referenced in the submissions JSON to
    retrieve full history beyond the most-recent ~1000 filings.

    The older-files "name" entries are bare filenames such as
    "CIK0000320193-submissions-001.json" (no "submissions/" prefix).
    The correct URL is https://data.sec.gov/submissions/{name}.

    Returns a tuple (rows, n_shards_missing) so callers can surface the
    missing-shard count in run summaries and the coverage JSON.
    """
    url = SUBMISSIONS_URL.format(int(cik))
    data = _sec_get_json(url)
    time.sleep(PACE_S)
    if not data:
        return [], 0

    filings = data.get("filings") or {}
    recent = filings.get("recent") or {}
    rows = _extract_8k_rows(ticker, cik, recent)

    # Follow older-files pagination (data.sec.gov returns a list of shard file names).
    # Each entry's "name" field is a bare filename like
    # "CIK0000320193-submissions-001.json" (NO leading "submissions/" prefix).
    # The correct URL is https://data.sec.gov/submissions/<name>.
    older_files = filings.get("files") or []
    n_shards_missing = 0
    for f in older_files:
        fname = f.get("name") if isinstance(f, dict) else str(f)
        if not fname:
            continue
        # Build the correct shard URL: always under /submissions/
        older_url = f"https://data.sec.gov/submissions/{fname}"
        older_data = _sec_get_json(older_url)
        time.sleep(PACE_S)
        if older_data is None:
            n_shards_missing += 1
            log.warning(
                "edgar_earnings_8k: shard fetch FAILED for %s (CIK %s) — url=%s",
                ticker, cik, older_url,
            )
            continue
        rows.extend(_extract_8k_rows(ticker, cik, older_data))

    return rows, n_shards_missing


# ---------------------------------------------------------------------------
# Manifest (resumability)
# ---------------------------------------------------------------------------

def _manifest_path() -> Path:
    return config.data_dir() / "edgar" / "earnings_8k_dates_manifest.json"


def load_manifest() -> dict[str, dict]:
    """Load the per-CIK fetch manifest. Keys are str(cik)."""
    p = _manifest_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}


def save_manifest(manifest: dict[str, dict]) -> None:
    p = _manifest_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, indent=2))


# ---------------------------------------------------------------------------
# Output parquet
# ---------------------------------------------------------------------------

def _store_path() -> Path:
    return config.data_dir() / "edgar" / "earnings_8k_dates.parquet"


def _coverage_json_path() -> Path:
    return config.data_dir() / "edgar" / "earnings_8k_dates_coverage.json"


def load_existing() -> pd.DataFrame:
    p = _store_path()
    if not p.exists():
        return pd.DataFrame(columns=STORE_COLUMNS)
    return pd.read_parquet(p)


def append_and_dedup(existing: pd.DataFrame, new_rows: list[dict]) -> pd.DataFrame:
    """Append new rows and dedup on the canonical filing key ``(cik, accession)``.

    The key changed in Wave 1B and the reason is not cosmetic.  The old key was
    ``(ticker, filing_date)``, which **destroys amendments**: an 8-K/A filed on
    the same calendar day as the 8-K it corrects collapsed into it and the
    correction became invisible.  ``(cik, accession)`` is the frozen canonical
    filing key (contract freeze Q2) and keeps them two filings; re-grouping them
    into one *event* is
    ``engine.earnings_release.binding.collapse_release_events``' job, on the
    period of report — never on date proximity.

    Legacy rows written before accession capture are keyed the old way and are
    dropped when a keyed row already covers the same ``(ticker, filing_date)``,
    so re-running the collector upgrades the store in place rather than
    doubling it.  Within either key, the earliest non-empty
    ``acceptance_datetime`` wins.
    """
    if not new_rows:
        return existing
    new_df = pd.DataFrame(new_rows)
    combined = pd.concat([existing, new_df], ignore_index=True)
    for column in STORE_COLUMNS:
        if column not in combined.columns:
            combined[column] = ""
    combined["accession"] = combined["accession"].fillna("").astype(str)

    # Sort so the earliest non-empty acceptance_datetime is first within any
    # key — keep='first' is then deterministic regardless of concat order.
    # Empty strings sort before a real ISO timestamp lexicographically, which
    # would wrongly prefer a row with no precision over one with a known time,
    # so "" is mapped to a high sentinel.
    _SENTINEL = "9999-99-99"
    sort_key = combined["acceptance_datetime"].fillna("").replace("", _SENTINEL)
    combined = combined.iloc[sort_key.argsort(kind="stable")]

    keyed = combined[combined["accession"] != ""]
    legacy = combined[combined["accession"] == ""]
    keyed = keyed.drop_duplicates(subset=["cik", "accession"], keep="first")
    if not legacy.empty:
        legacy = legacy.drop_duplicates(subset=["ticker", "filing_date"], keep="first")
        if not keyed.empty:
            covered = set(zip(keyed["ticker"], keyed["filing_date"]))
            legacy = legacy[[
                (t, d) not in covered
                for t, d in zip(legacy["ticker"], legacy["filing_date"])
            ]]
    combined = pd.concat([keyed, legacy], ignore_index=True)
    combined = combined.sort_values(
        ["ticker", "filing_date", "accession"]
    ).reset_index(drop=True)
    return combined[STORE_COLUMNS]


# ---------------------------------------------------------------------------
# Coverage verdict
# ---------------------------------------------------------------------------

def compute_coverage(df: pd.DataFrame) -> dict:
    """Compute coverage statistics and determine PASS/FAIL against the gate.

    Gate: ≥800 names with ≥8 years of Item-2.02 history.
    Returns a dict suitable for JSON serialization.
    """
    if df.empty:
        return {
            "gate_pass": False,
            "gate_verdict": "FAIL",
            "gate_reason": "empty store",
            "names_total": 0,
            "names_ge8y": 0,
            "gate_names_threshold": COVERAGE_GATE_NAMES,
            "gate_years_threshold": COVERAGE_GATE_YEARS,
            "overall_span": "",
            "total_rows": 0,
            "as_of": datetime.now(timezone.utc).date().isoformat(),
        }
    df2 = df.copy()
    df2["filing_date"] = pd.to_datetime(df2["filing_date"], errors="coerce")
    df2 = df2.dropna(subset=["filing_date"])

    per_name = df2.groupby("ticker").agg(
        min_date=("filing_date", "min"),
        max_date=("filing_date", "max"),
        n_filings=("filing_date", "count"),
    )
    per_name["years_span"] = (
        (per_name["max_date"] - per_name["min_date"]).dt.days / 365.25
    )
    names_ge8y = int((per_name["years_span"] >= COVERAGE_GATE_YEARS).sum())
    names_total = len(per_name)
    gate_pass = names_ge8y >= COVERAGE_GATE_NAMES

    overall_min = df2["filing_date"].min().date().isoformat() if not df2.empty else ""
    overall_max = df2["filing_date"].max().date().isoformat() if not df2.empty else ""

    return {
        "gate_pass": gate_pass,
        "gate_verdict": "PASS" if gate_pass else "FAIL",
        "gate_reason": (
            f"{names_ge8y} names with ≥{COVERAGE_GATE_YEARS}y — "
            + ("meets" if gate_pass else "below")
            + f" threshold of {COVERAGE_GATE_NAMES}"
        ),
        "names_total": names_total,
        "names_ge8y": names_ge8y,
        "gate_names_threshold": COVERAGE_GATE_NAMES,
        "gate_years_threshold": COVERAGE_GATE_YEARS,
        "overall_span": f"{overall_min} .. {overall_max}",
        "total_rows": len(df2),
        "as_of": datetime.now(timezone.utc).date().isoformat(),
    }


# ---------------------------------------------------------------------------
# Main backfill
# ---------------------------------------------------------------------------

def run_backfill(
    *,
    force: bool = False,
    incremental: bool = False,
    max_errors: int = 100,
) -> pd.DataFrame:
    """Full backfill: fetch Item-2.02 8-K history for all eps_quarterly tickers.

    Resumable: already-fetched CIKs (status='ok' in manifest) are skipped unless
    force=True. incremental=True additionally skips CIKs with status='error' from a
    prior run (use for nightly incremental; force=True to retry errors).

    Logs per-CIK errors (never silently skips). Returns the final parquet DataFrame.
    """
    # Load universe from eps_quarterly.parquet
    eps_path = config.data_dir() / "edgar" / "eps_quarterly.parquet"
    if not eps_path.exists():
        raise RuntimeError(f"eps_quarterly.parquet not found at {eps_path}")
    universe_tickers = pd.read_parquet(eps_path)["ticker"].unique().tolist()
    log.info("edgar_earnings_8k: universe = %d tickers from eps_quarterly", len(universe_tickers))

    # Build ticker -> CIK map
    cik_map = build_cik_map(universe_tickers)
    log.info("edgar_earnings_8k: %d/%d tickers mapped to CIKs",
             len(cik_map), len(universe_tickers))
    unmapped = set(universe_tickers) - set(cik_map)
    if unmapped:
        log.warning("edgar_earnings_8k: %d tickers not mapped to CIK: %s ...",
                    len(unmapped), sorted(unmapped)[:10])

    # Load manifest + existing store
    manifest = load_manifest() if not force else {}
    existing_df = load_existing()
    log.info("edgar_earnings_8k: manifest has %d done CIKs; store has %d existing rows",
             len(manifest), len(existing_df))

    all_rows: list[dict] = existing_df.to_dict("records") if not existing_df.empty else []
    n_fetched = 0
    n_skipped = 0
    n_error = 0
    n_shards_missing_total = 0

    for ticker, cik in cik_map.items():
        cik_key = str(cik)
        entry = manifest.get(cik_key, {})

        # Skip logic
        if entry.get("status") == "ok" and not force:
            n_skipped += 1
            continue
        if entry.get("status") == "error" and incremental and not force:
            n_skipped += 1
            continue

        try:
            rows, n_shards_missing = fetch_earnings_8k_for_cik(ticker, cik)
        except Exception as e:  # noqa: BLE001
            n_error += 1
            log.warning("edgar_earnings_8k: CIK %s (%s) failed: %s", cik, ticker, e)
            manifest[cik_key] = {
                "ticker": ticker,
                "status": "error",
                "error": str(e),
                "ts": datetime.now(timezone.utc).isoformat(),
            }
            if n_error >= max_errors:
                log.error("edgar_earnings_8k: max_errors=%d reached — stopping", max_errors)
                save_manifest(manifest)
                break
            continue

        n_shards_missing_total += n_shards_missing
        n_rows = len(rows)
        if n_rows == 0:
            log.debug("edgar_earnings_8k: CIK %s (%s) — 0 Item-2.02 8-Ks found", cik, ticker)
        else:
            all_rows.extend(rows)

        manifest[cik_key] = {
            "ticker": ticker,
            "status": "ok",
            "n_filings": n_rows,
            "n_shards_missing": n_shards_missing,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        n_fetched += 1

        # Checkpoint every 50 CIKs: save manifest + parquet
        if n_fetched % 50 == 0:
            log.info(
                "edgar_earnings_8k: checkpoint — %d fetched, %d skipped, %d errors, %d shards missing",
                n_fetched, n_skipped, n_error, n_shards_missing_total,
            )
            _checkpoint(all_rows, existing_df, manifest)

    # Final save
    final_df = _checkpoint(all_rows, existing_df, manifest)
    log.info(
        "edgar_earnings_8k: done — %d fetched, %d skipped, %d errors, %d shards missing; store=%d rows, %d tickers",
        n_fetched, n_skipped, n_error, n_shards_missing_total,
        len(final_df), final_df["ticker"].nunique() if not final_df.empty else 0,
    )
    if n_shards_missing_total > 0:
        log.warning(
            "edgar_earnings_8k: %d older-filing shard(s) could not be fetched — "
            "history for those CIKs may be incomplete",
            n_shards_missing_total,
        )

    # Coverage verdict
    cov = compute_coverage(final_df)
    cov["n_shards_missing"] = n_shards_missing_total
    cov_path = _coverage_json_path()
    cov_path.parent.mkdir(parents=True, exist_ok=True)
    cov_path.write_text(json.dumps(cov, indent=2))

    print("\n=== EDGAR 8-K Item-2.02 Coverage Verdict ===")
    print(f"  Names with ≥{COVERAGE_GATE_YEARS}y of Item-2.02 history : {cov['names_ge8y']}")
    print(f"  Names total                                  : {cov['names_total']}")
    print(f"  Overall date span                            : {cov['overall_span']}")
    print(f"  Total rows                                   : {cov['total_rows']}")
    print(f"  Older-filing shards missing (fetch failures) : {n_shards_missing_total}")
    print(f"\n  S-EV Gate ({COVERAGE_GATE_NAMES} names × {COVERAGE_GATE_YEARS}y): {cov['gate_verdict']}")
    print(f"  ({cov['gate_reason']})")
    print(f"\n  Coverage JSON: {cov_path}")
    print()

    return final_df


def _checkpoint(
    all_rows: list[dict],
    existing_df: pd.DataFrame,
    manifest: dict,
) -> pd.DataFrame:
    """Merge all_rows with existing, dedup, write parquet + manifest."""
    if all_rows:
        final_df = append_and_dedup(existing_df, all_rows)
    else:
        final_df = existing_df.copy() if not existing_df.empty else pd.DataFrame(
            columns=STORE_COLUMNS
        )
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    final_df.to_parquet(p)
    save_manifest(manifest)
    return final_df


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    p = argparse.ArgumentParser(
        description="Fetch EDGAR 8-K Item-2.02 earnings-announcement dates."
    )
    p.add_argument("--force", action="store_true",
                   help="Re-fetch all CIKs ignoring the manifest cache.")
    p.add_argument("--incremental", action="store_true",
                   help="Skip previously-errored CIKs (for nightly refresh).")
    p.add_argument("--max-errors", type=int, default=100,
                   help="Stop after this many per-CIK errors (default 100).")
    args = p.parse_args(argv)
    run_backfill(
        force=args.force,
        incremental=args.incremental,
        max_errors=args.max_errors,
    )


if __name__ == "__main__":
    main()
