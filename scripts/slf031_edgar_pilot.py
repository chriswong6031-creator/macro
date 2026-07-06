"""SLF-031 Feasibility Spike — EDGAR 10-K lazy-prices pilot.

Fetches the two most-recent 10-K primary documents for 20 diverse S&P 500 tickers,
measures fetch time, doc size, parse time, and computes three text-similarity metrics
between consecutive annual filings:

  1. Cosine on TF-IDF  (scikit-learn is a repo dep — confirmed importable)
  2. Jaccard on 3-gram shingles
  3. Normalized length delta  |len(t2) - len(t1)| / max(len(t1), len(t2))

Item-level split attempted for Item 1A (Risk Factors); falls back to whole-doc.

NO return analysis, NO signal claims, NO trial-ledger writes.
This is a feasibility spike — display-only descriptive statistics.

Usage:
    python3 scripts/slf031_edgar_pilot.py

Rate-limited to <=8 req/s.  Uses proper EDGAR user-agent per SEC guidelines.
"""
from __future__ import annotations

import re
import sys
import time
import math
import json
import urllib.request
import urllib.error
import html
from collections import Counter
from typing import Optional

# scikit-learn is a confirmed repo dep (scikit-learn 1.9.0 installed)
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
UA = "MacroDashboard research longr2512@gmail.com"
EDGAR_BASE = "https://data.sec.gov"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
MIN_DELAY = 1.0 / 8.0   # <=8 req/s

# 20 diverse tickers: mix of sectors, large/mid cap, from S&P 500
TICKERS = [
    # Technology (large)
    ("AAPL",  320193),
    ("MSFT",  789019),
    ("NVDA", 1045810),
    # Technology (mid)
    ("AMAT",   796343),
    # Healthcare (large)
    ("JNJ",   200406),
    ("UNH",   731766),
    # Healthcare (mid)
    ("HOLX",  859737),
    # Financials (large)
    ("JPM",   19617),
    ("BRK-B", 1067983),
    # Financials (mid)
    ("RF",    49196),
    # Consumer Discretionary (large)
    ("AMZN", 1018724),
    ("MCD",   63754),
    # Consumer Staples
    ("PG",    80424),
    ("KO",   21344),
    # Energy
    ("XOM",   34088),
    ("SLB",   87347),
    # Industrials
    ("CAT",   18230),
    ("HON",   773840),
    # Materials
    ("LIN",  1707092),
    # Utilities
    ("NEE",   753308),
]

# ---------------------------------------------------------------------------
# Rate-limit helper
# ---------------------------------------------------------------------------
_last_req_time: float = 0.0

def _throttled_get(url: str, retries: int = 3) -> bytes:
    global _last_req_time
    elapsed = time.time() - _last_req_time
    if elapsed < MIN_DELAY:
        time.sleep(MIN_DELAY - elapsed)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,text/html,*/*"})
    for attempt in range(retries):
        try:
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            _last_req_time = time.time()
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 10 * (attempt + 1)
                print(f"    429 rate-limit on {url[:60]}… waiting {wait}s", flush=True)
                time.sleep(wait)
            else:
                raise
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2)
    raise RuntimeError(f"Failed after {retries} retries: {url}")

# ---------------------------------------------------------------------------
# EDGAR filing lookup
# ---------------------------------------------------------------------------
def get_recent_10k_docs(cik: int, ticker: str, n: int = 2) -> list[dict]:
    """Return up to n most-recent 10-K filing primary document URLs + metadata."""
    url = SUBMISSIONS_URL.format(cik=cik)
    raw = _throttled_get(url)
    data = json.loads(raw)
    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    accnos = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])

    results = []
    for form, date, accno, prim in zip(forms, dates, accnos, primary_docs):
        if form == "10-K" and len(results) < n:
            accno_clean = accno.replace("-", "")
            doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accno_clean}/{prim}"
            results.append({"ticker": ticker, "date": date, "accno": accno, "doc_url": doc_url})
    return results

# ---------------------------------------------------------------------------
# HTML/text extraction
# ---------------------------------------------------------------------------
_TAG_RE = re.compile(r"<[^>]+>", re.DOTALL)
_WS_RE  = re.compile(r"\s+")
_ITEM1A_RE = re.compile(
    r"ITEM\s+1A[\.\s]*RISK\s+FACTORS(.*?)(?:ITEM\s+1B|ITEM\s+2)",
    re.IGNORECASE | re.DOTALL,
)

def extract_text(raw_bytes: bytes, url: str) -> tuple[str, Optional[str]]:
    """
    Returns (whole_doc_text, item1a_text_or_None).
    Handles both HTML and plain-text filings.
    """
    try:
        content = raw_bytes.decode("utf-8", errors="replace")
    except Exception:
        content = raw_bytes.decode("latin-1", errors="replace")

    is_html = "<html" in content[:2000].lower() or "<!doctype" in content[:200].lower()

    if is_html:
        # strip tags
        text = _TAG_RE.sub(" ", content)
        text = html.unescape(text)
    else:
        text = content

    text = _WS_RE.sub(" ", text).strip()

    # Attempt Item 1A extraction
    m = _ITEM1A_RE.search(text)
    item1a: Optional[str] = None
    if m and len(m.group(1).strip()) > 500:
        item1a = _WS_RE.sub(" ", m.group(1)).strip()

    return text, item1a

# ---------------------------------------------------------------------------
# Similarity metrics
# ---------------------------------------------------------------------------

def cosine_tfidf(t1: str, t2: str) -> float:
    """TF-IDF cosine similarity between two documents."""
    vectorizer = TfidfVectorizer(max_features=20000, sublinear_tf=True)
    try:
        mat = vectorizer.fit_transform([t1, t2])
        v1 = mat[0].toarray().flatten()
        v2 = mat[1].toarray().flatten()
        denom = np.linalg.norm(v1) * np.linalg.norm(v2)
        if denom == 0:
            return float("nan")
        return float(np.dot(v1, v2) / denom)
    except Exception:
        return float("nan")


def jaccard_3gram(t1: str, t2: str) -> float:
    """Jaccard similarity on character 3-grams (shingles)."""
    def shingles(text: str) -> set:
        # Use word-level 3-grams (more robust than char for long docs)
        words = text.split()
        if len(words) < 3:
            return set()
        return {(words[i], words[i+1], words[i+2]) for i in range(len(words)-2)}

    s1 = shingles(t1)
    s2 = shingles(t2)
    if not s1 and not s2:
        return float("nan")
    union = len(s1 | s2)
    if union == 0:
        return float("nan")
    return len(s1 & s2) / union


def norm_length_delta(t1: str, t2: str) -> float:
    """Normalized absolute length delta: |len2 - len1| / max(len1, len2)."""
    l1, l2 = len(t1.split()), len(t2.split())
    mx = max(l1, l2)
    if mx == 0:
        return float("nan")
    return abs(l2 - l1) / mx

# ---------------------------------------------------------------------------
# Main pilot
# ---------------------------------------------------------------------------
def run_pilot() -> list[dict]:
    results = []

    for ticker, cik in TICKERS:
        print(f"\n[{ticker}] CIK={cik}", flush=True)
        row: dict = {"ticker": ticker, "cik": cik}

        # Step 1: get filing index
        try:
            t0 = time.time()
            filings = get_recent_10k_docs(cik, ticker, n=2)
            row["filing_index_ms"] = round((time.time() - t0) * 1000)
        except Exception as e:
            print(f"  ERROR fetching submissions: {e}", flush=True)
            row["error"] = f"submissions: {e}"
            results.append(row)
            continue

        if len(filings) < 2:
            print(f"  SKIP — only {len(filings)} 10-K(s) found", flush=True)
            row["error"] = f"only {len(filings)} 10-Ks"
            results.append(row)
            continue

        row["filing_dates"] = [f["date"] for f in filings]
        print(f"  10-K dates: {row['filing_dates']}", flush=True)

        # Step 2: fetch primary docs (2 most recent)
        docs_text: list[tuple[str, Optional[str], int, int, int]] = []
        # Each element: (whole_text, item1a, fetch_ms, doc_bytes, parse_ms)
        for i, filing in enumerate(filings):
            url = filing["doc_url"]
            print(f"  Fetching doc {i+1}: {url[:80]}…", flush=True)
            try:
                t0 = time.time()
                raw = _throttled_get(url)
                fetch_ms = round((time.time() - t0) * 1000)
                doc_bytes = len(raw)

                t1 = time.time()
                whole_text, item1a = extract_text(raw, url)
                parse_ms = round((time.time() - t1) * 1000)

                docs_text.append((whole_text, item1a, fetch_ms, doc_bytes, parse_ms))
                print(f"    fetch={fetch_ms}ms, size={doc_bytes/1024:.0f}KB, parse={parse_ms}ms, "
                      f"words={len(whole_text.split()):,}, "
                      f"item1a={'YES('+str(len(item1a.split()))+'w)' if item1a else 'NO'}", flush=True)
            except Exception as e:
                print(f"    ERROR fetching doc: {e}", flush=True)
                docs_text.append(("", None, 0, 0, 0))

        if len(docs_text) < 2 or not docs_text[0][0] or not docs_text[1][0]:
            row["error"] = "fetch failed for >=1 doc"
            results.append(row)
            continue

        # Step 3: compute similarity metrics
        # docs_text[0] = most recent; docs_text[1] = year before
        t_new_whole, i1a_new, fetch_new, bytes_new, parse_new = docs_text[0]
        t_old_whole, i1a_old, fetch_old, bytes_old, parse_old = docs_text[1]

        row["fetch_ms"] = [fetch_new, fetch_old]
        row["doc_bytes"] = [bytes_new, bytes_old]
        row["parse_ms"] = [parse_new, parse_old]
        row["doc_words"] = [len(t_new_whole.split()), len(t_old_whole.split())]
        row["item1a_available"] = bool(i1a_new and i1a_old)

        print(f"  Computing similarity metrics…", flush=True)
        t_sim0 = time.time()

        # Whole-doc metrics
        row["cosine_whole"] = cosine_tfidf(t_old_whole, t_new_whole)
        row["jaccard_whole"] = jaccard_3gram(t_old_whole, t_new_whole)
        row["len_delta_whole"] = norm_length_delta(t_old_whole, t_new_whole)

        # Item 1A metrics (if available)
        if row["item1a_available"]:
            row["cosine_1a"] = cosine_tfidf(i1a_old, i1a_new)
            row["jaccard_1a"] = jaccard_3gram(i1a_old, i1a_new)
            row["len_delta_1a"] = norm_length_delta(i1a_old, i1a_new)
        else:
            row["cosine_1a"] = None
            row["jaccard_1a"] = None
            row["len_delta_1a"] = None

        row["sim_compute_ms"] = round((time.time() - t_sim0) * 1000)
        print(f"  Metrics: cosine={row['cosine_whole']:.4f}, "
              f"jaccard={row['jaccard_whole']:.4f}, "
              f"len_delta={row['len_delta_whole']:.4f}  [compute={row['sim_compute_ms']}ms]", flush=True)

        results.append(row)

    return results


def print_summary(results: list[dict]) -> None:
    print("\n" + "="*70)
    print("PILOT SUMMARY — SLF-031 EDGAR 10-K Lazy Prices Feasibility")
    print("="*70)

    ok = [r for r in results if "error" not in r]
    err = [r for r in results if "error" in r]

    print(f"\n  Tickers attempted:  {len(results)}")
    print(f"  Completed:          {len(ok)}")
    print(f"  Errors/skipped:     {len(err)}")
    if err:
        for r in err:
            print(f"    {r['ticker']:8s}: {r.get('error','?')}")

    if not ok:
        print("\n  No completed tickers — cannot compute aggregate stats.")
        return

    # Timing stats
    fetches = [r["fetch_ms"][0] + r["fetch_ms"][1] for r in ok]
    parses  = [r["parse_ms"][0] + r["parse_ms"][1] for r in ok]
    bytes_  = [r["doc_bytes"][0] + r["doc_bytes"][1] for r in ok]
    compute = [r["sim_compute_ms"] for r in ok]

    def stats(xs: list[float], label: str) -> None:
        xs = [x for x in xs if not math.isnan(x)]
        if not xs:
            print(f"  {label}: N/A")
            return
        print(f"  {label}: min={min(xs):.0f}  median={sorted(xs)[len(xs)//2]:.0f}  max={max(xs):.0f}  mean={sum(xs)/len(xs):.0f}")

    print("\n--- Timing (ms per ticker, both docs combined) ---")
    stats(fetches, "Fetch ms      ")
    stats(parses,  "Parse ms      ")
    stats(compute, "SimCompute ms ")

    print("\n--- Doc sizes (bytes, both docs combined) ---")
    stats(bytes_,  "Total bytes   ")

    print("\n--- Similarity metric distributions (whole-doc) ---")
    cos_w = [r["cosine_whole"] for r in ok if r.get("cosine_whole") is not None and not math.isnan(r["cosine_whole"])]
    jac_w = [r["jaccard_whole"] for r in ok if r.get("jaccard_whole") is not None and not math.isnan(r["jaccard_whole"])]
    ld_w  = [r["len_delta_whole"] for r in ok if r.get("len_delta_whole") is not None and not math.isnan(r["len_delta_whole"])]
    stats(cos_w, "Cosine TF-IDF  ")
    stats(jac_w, "Jaccard 3-gram ")
    stats(ld_w,  "Len delta      ")

    ok_1a = [r for r in ok if r["item1a_available"]]
    print(f"\n--- Item 1A split: {len(ok_1a)}/{len(ok)} tickers extracted ---")
    if ok_1a:
        cos_1a = [r["cosine_1a"] for r in ok_1a if r.get("cosine_1a") is not None and not math.isnan(r["cosine_1a"])]
        jac_1a = [r["jaccard_1a"] for r in ok_1a if r.get("jaccard_1a") is not None and not math.isnan(r["jaccard_1a"])]
        ld_1a  = [r["len_delta_1a"] for r in ok_1a if r.get("len_delta_1a") is not None and not math.isnan(r["len_delta_1a"])]
        stats(cos_1a, "Cosine (1A)    ")
        stats(jac_1a, "Jaccard (1A)   ")
        stats(ld_1a,  "Len delta (1A) ")

    print("\n--- Per-ticker table ---")
    header = f"{'Ticker':8s} {'Dates':24s} {'FetchMs':>8} {'KB':>8} {'ParseMs':>8} {'SimMs':>7} {'Cos':>7} {'Jac':>7} {'LenD':>7} {'1A?':>4}"
    print(header)
    print("-" * len(header))
    for r in sorted(ok, key=lambda x: x["ticker"]):
        dates_str = " -> ".join(r["filing_dates"])
        kb = (r["doc_bytes"][0] + r["doc_bytes"][1]) / 1024
        print(f"{r['ticker']:8s} {dates_str:24s} "
              f"{r['fetch_ms'][0]+r['fetch_ms'][1]:>8d} {kb:>8.0f} "
              f"{r['parse_ms'][0]+r['parse_ms'][1]:>8d} {r['sim_compute_ms']:>7d} "
              f"{r['cosine_whole']:>7.4f} {r['jaccard_whole']:>7.4f} {r['len_delta_whole']:>7.4f} "
              f"{'YES' if r['item1a_available'] else 'NO':>4}")


if __name__ == "__main__":
    print("SLF-031 EDGAR Pilot — starting", flush=True)
    print(f"Rate limit: <=8 req/s  |  UA: {UA}", flush=True)
    t_total = time.time()
    results = run_pilot()
    total_elapsed = time.time() - t_total
    print(f"\nTotal wall-clock: {total_elapsed:.1f}s", flush=True)
    print_summary(results)

    # Save raw results for design doc
    out_path = "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees/slf-l9-lazy-spike/reports/slf031_pilot_raw.json"
    import os
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"results": results, "total_elapsed_s": total_elapsed}, f, indent=2, default=str)
    print(f"\nRaw results saved to {out_path}", flush=True)
