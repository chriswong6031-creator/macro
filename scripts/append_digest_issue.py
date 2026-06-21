"""Append a new Special Situations Digest issue into the curated answer-key parquet.

The original archive (issues #1–19) was a ONE-TIME bulk normalization from a raw
browser capture under research/_recon_raw/ (see scripts/ingest_digest_db.py). That
raw capture is gitignored and no longer on disk, so a new issue cannot be added by
re-running the bulk ingest — instead this APPENDS the new issue's situations onto the
existing data/special_situations/digest_db.parquet, reusing the exact same field
parsers so the column contract stays byte-compatible with the bulk ingest.

Input: a single file you provide for the new issue. Accepted formats:
  * JSON: a list of objects, or {"items": [...]}, or {"situations": [...]}.
  * CSV.
Each record may use the terse capture keys (c,t,co,cat,i,hk,mc,ev,sec,m,px,u,ind,biz,s)
or friendly keys (company, ticker, country, category, issue, headline, market_cap, ev,
sector, metrics, price, source_url, industry, business_desc, summary). Pre-parsed
numeric columns (market_cap_musd, ev_musd, price, ev_sales, ev_gp, fwd_pe, ev_ebitda)
are used directly when present.

Deterministic — no network, no LLM. The existing parquet is backed up before write.
Run: python -m scripts.append_digest_issue --issue 20 path/to/issue20.{json,csv}
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import timedelta
from pathlib import Path

import pandas as pd

from lib import config
from scripts.ingest_digest_db import (
    ISSUE1_DATE,
    OUT,
    _bucket,
    _parse_metrics,
    _parse_price,
    _parse_usd_m,
)

# Final column order — MUST match scripts/ingest_digest_db.ingest() exactly.
COLUMNS = [
    "id", "company", "ticker", "country", "category", "issue", "issue_date",
    "headline", "market_cap_musd", "mc_raw", "ev_musd", "ev_raw", "price",
    "price_ccy", "sector", "industry", "ev_sales", "ev_gp", "fwd_pe", "ev_ebitda",
    "business_desc", "summary", "source_url", "source_domain", "source_bucket",
]

# Friendly/alternate keys -> the terse capture key the parsers below expect.
_ALIASES = {
    "company": "c", "name": "c",
    "ticker": "t", "symbol": "t",
    "country": "co",
    "category": "cat",
    "issue": "i",
    "headline": "hk", "hl": "hk",
    "market_cap": "mc", "marketcap": "mc", "market_cap_raw": "mc",
    "enterprise_value": "ev", "ev_raw": "ev",
    "sector": "sec",
    "metrics": "m", "multiples": "m",
    "price": "px", "price_raw": "px", "last": "px",
    "source_url": "u", "url": "u", "link": "u",
    "industry": "ind",
    "business_desc": "biz", "description": "biz", "business": "biz", "context": "biz",
    "summary": "s",
}


def _g(rec: dict, *keys):
    """First non-empty value among keys (terse first), else None."""
    for k in keys:
        if k in rec and rec[k] not in (None, "", float("nan")):
            v = rec[k]
            if isinstance(v, float) and pd.isna(v):
                continue
            return v
    return None


def _canon(rec: dict) -> dict:
    """Fold friendly aliases onto terse keys without clobbering an explicit terse key."""
    out = dict(rec)
    for friendly, terse in _ALIASES.items():
        if friendly in out and terse not in out:
            out[terse] = out[friendly]
    return out


def _num(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if pd.isna(f) else f
    except (TypeError, ValueError):
        return None


# The publisher's structured export tags EV multiples with a period qualifier
# (Fwd/LTM/NTM/TTM EV/Sales, LTM EV/GP, ...) that the shared _parse_metrics key-map
# does not recognize. Strip the qualifier *only* before "EV/" so they fold onto the
# canonical EV/* columns; "Fwd P/E" is left intact (it IS a recognized key). When both
# Fwd and LTM variants of the same EV multiple are present, the first (Fwd) wins via
# _parse_metrics' setdefault, matching the forward-looking convention of issues #1–19.
_MULT_QUALIFIER = re.compile(r"\b(?:fwd|ltm|ntm|ttm)\s+(ev/)", re.IGNORECASE)


def _norm_mult_labels(m):
    if not m or not isinstance(m, str):
        return m
    return _MULT_QUALIFIER.sub(r"\1", m)


def _load(path: Path) -> tuple[list[dict], dict]:
    """Return (situation records, file-level meta). Accepts the publisher's nested
    {categories:[{name,count,items:[...]}]} export, a flat list / {items|situations|rows},
    or CSV."""
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path).to_dict(orient="records"), {}
    data = json.loads(path.read_text())
    if isinstance(data, list):
        return data, {}
    if not isinstance(data, dict):
        raise ValueError(f"could not find a list of situations in {path}")
    meta = {k: data[k] for k in ("issue", "total_situations", "title", "publisher") if k in data}
    cats = data.get("categories")
    if isinstance(cats, list) and cats and isinstance(cats[0], dict) and "items" in cats[0]:
        records = []
        for c in cats:
            name = c.get("name") or c.get("category")
            for it in (c.get("items") or []):
                rec = dict(it)
                rec.setdefault("category", name)   # lift the group label onto each item
                records.append(rec)
        return records, meta
    records = data.get("items") or data.get("situations") or data.get("rows") or []
    if not isinstance(records, list):
        raise ValueError(f"could not find a list of situations in {path}")
    return records, meta


def normalize(records: list[dict], issue: int, start_id: int) -> pd.DataFrame:
    rows = []
    next_id = start_id
    idate = (ISSUE1_DATE + timedelta(days=(issue - 1) * 7)).isoformat()
    for raw in records:
        r = _canon(raw)
        mets = _parse_metrics(_norm_mult_labels(_g(r, "m")))
        px_v = _g(r, "px")
        px, ccy = _parse_price(px_v)              # handles "$5.20" / "CAD 31.76" strings
        if px is None and px_v is not None:
            px = _num(px_v)                        # bare numeric price
        if px is not None and not ccy and _g(r, "price_ccy"):
            ccy = str(_g(r, "price_ccy")).upper()
        mc_v = _g(r, "mc")
        mc_musd = (_parse_usd_m(mc_v) if isinstance(mc_v, str)
                   else _num(mc_v) if mc_v is not None else _num(_g(r, "market_cap_musd")))
        ev_v = _g(r, "ev")
        ev_musd = (_parse_usd_m(ev_v) if isinstance(ev_v, str)
                   else _num(ev_v) if ev_v is not None else _num(_g(r, "ev_musd")))
        url = _g(r, "u")
        bucket, host = _bucket(url)
        rid = _g(r, "id")
        try:
            rid = int(rid) if rid is not None else None
        except (TypeError, ValueError):
            rid = None
        if rid is None:
            rid, next_id = next_id, next_id + 1
        rows.append({
            "id": rid, "company": _g(r, "c"), "ticker": _g(r, "t"),
            "country": _g(r, "co"), "category": _g(r, "cat"),
            "issue": issue, "issue_date": _g(r, "issue_date") or idate,
            "headline": _g(r, "hk"),
            "market_cap_musd": mc_musd,
            "mc_raw": mc_v if isinstance(mc_v, str) else None,
            "ev_musd": ev_musd,
            "ev_raw": ev_v if isinstance(ev_v, str) else None,
            "price": px, "price_ccy": ccy,
            "sector": _g(r, "sec") or _g(r, "ind"), "industry": _g(r, "ind"),
            "ev_sales": mets.get("ev_sales", _num(_g(r, "ev_sales"))),
            "ev_gp": mets.get("ev_gp", _num(_g(r, "ev_gp"))),
            "fwd_pe": mets.get("fwd_pe", _num(_g(r, "fwd_pe"))),
            "ev_ebitda": mets.get("ev_ebitda", _num(_g(r, "ev_ebitda"))),
            "business_desc": _g(r, "biz"), "summary": _g(r, "s"),
            "source_url": url, "source_domain": host, "source_bucket": bucket,
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path, help="JSON/CSV file of the new issue's situations")
    ap.add_argument("--issue", type=int, default=None,
                    help="issue number (e.g. 20); inferred from the file if it declares one")
    ap.add_argument("--dry-run", action="store_true", help="parse + report, do not write")
    args = ap.parse_args()

    if not args.path.exists():
        print(f"input not found: {args.path}")
        return 1
    if not OUT.exists():
        print(f"existing parquet not found: {OUT} — nothing to append onto")
        return 1

    records, meta = _load(args.path)
    file_issue = meta.get("issue")
    issue = args.issue if args.issue is not None else (int(file_issue) if file_issue is not None else None)
    if issue is None:
        print("issue number not given and not declared in the file — pass --issue N")
        return 1
    if file_issue is not None and int(file_issue) != issue:
        print(f"--issue {issue} disagrees with the file's declared issue {file_issue} — aborting")
        return 1
    declared = meta.get("total_situations")
    if declared is not None and int(declared) != len(records):
        print(f"WARNING: file declares total_situations={declared} but {len(records)} records parsed")

    existing = pd.read_parquet(OUT)
    if issue in set(existing.issue.dropna().astype(int).tolist()):
        print(f"issue #{issue} is ALREADY in the parquet "
              f"({(existing.issue == issue).sum()} rows) — refusing to double-add. "
              f"Remove it first if you intend to replace it.")
        return 1

    start_id = int(existing.id.max()) + 1
    new = normalize(records, issue, start_id)

    # de-dup any ids that collide with existing rows (provided ids reused upstream)
    clash = set(new.id) & set(existing.id)
    if clash:
        nxt = max(int(existing.id.max()), int(new.id.max())) + 1
        remap = {}
        for cid in sorted(clash):
            remap[cid], nxt = nxt, nxt + 1
        new["id"] = new["id"].map(lambda x: remap.get(x, x))
        print(f"  remapped {len(clash)} colliding id(s) to fresh values")

    combined = pd.concat([existing, new], ignore_index=True)

    print(f"[parsed] issue #{issue}: {len(new)} situations")
    cov = {c: f"{new[c].notna().mean()*100:.0f}%" for c in
           ["ticker", "market_cap_musd", "price", "ev_sales", "ev_gp", "fwd_pe", "ev_ebitda",
            "summary", "country", "category"]}
    print(f"  coverage: {cov}")
    print(f"  US: {(new.country=='US').sum()} · with ticker: {new[new.country=='US'].ticker.notna().sum()}")
    print(f"  issue_date: {new.issue_date.dropna().unique().tolist()}")
    miss_cat = int(new.category.isna().sum())
    miss_co = int(new.country.isna().sum())
    if miss_cat or miss_co:
        print(f"  WARNING: {miss_cat} rows missing category, {miss_co} missing country")
    print(f"  total after append: {len(combined)} rows · issues {int(combined.issue.min())}–{int(combined.issue.max())}")

    if args.dry_run:
        print("[dry-run] not written")
        return 0

    backup = OUT.with_suffix(".parquet.bak")
    shutil.copy2(OUT, backup)
    combined.to_parquet(OUT, index=False)
    print(f"[written] {OUT}  (backup: {backup})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
