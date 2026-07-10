"""Deterministic CIK verification gate for smart_money funds (SM2-R6).

For every fund in config smart_money.funds:
  (a) fetches https://data.sec.gov/submissions/CIK{zero-padded-10}.json
  (b) checks that recent forms include 13F-HR with filingDate within 18 months
      (skipped for funds with status: closed — those only need EVER-filed)
  (c) loose name sanity: at least one significant token of the config name
      appears case-insensitively in the SEC entity name

Output:
  - Markdown report to reports/verify_13f_ciks_2026-07-10.md
  - Exit nonzero if any active (non-closed) fund FAILs

Usage:
  python scripts/verify_13f_ciks.py [--json] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

# ---- path plumbing -------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import config as _cfg_mod  # noqa: E402

SUBMISSIONS = "https://data.sec.gov/submissions/CIK{:010d}.json"
PACING = 0.12           # seconds between requests (SEC fair-access)
RETRIES = 3
RECENCY_MONTHS = 18     # active funds must have filed within this window
REPORT_PATH = ROOT / "reports" / "verify_13f_ciks_2026-07-10.md"

# Tokens that carry NO discriminating information in fund names
STOP_TOKENS = {
    "capital", "management", "partners", "fund", "group", "llc", "lp", "inc",
    "advisors", "asset", "the", "and", "of",
}


def _ua() -> str:
    cfg = _cfg_mod.load()
    return (cfg.get("smart_money", {}) or {}).get("user_agent", "Macro Dashboard research")


def _get_json(url: str) -> dict | None:
    import requests
    headers = {"User-Agent": _ua(), "Accept-Encoding": "gzip, deflate"}
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            if attempt == RETRIES - 1:
                print(f"  WARN GET failed {url}: {exc}", file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def _significant_tokens(name: str) -> list[str]:
    """Extract tokens with len>3 that are not in the stop-token list."""
    tokens = []
    for tok in name.lower().split():
        tok_clean = tok.strip(".,()&-'\"")
        if len(tok_clean) > 3 and tok_clean not in STOP_TOKENS:
            tokens.append(tok_clean)
    return tokens


def verify_fund(slug: str, spec: dict) -> dict:
    """Returns a result dict: {slug, cik, config_name, sec_name, latest_13f_date,
    verdict, note}. Verdict ∈ VERIFIED / FAILED / FLAGGED."""
    cik = int(spec["cik"])
    config_name = spec.get("name", slug)
    is_closed = str(spec.get("status", "")).lower() == "closed"

    url = SUBMISSIONS.format(cik)
    data = _get_json(url)
    time.sleep(PACING)

    if data is None:
        return {
            "slug": slug, "cik": cik, "config_name": config_name,
            "sec_name": "—", "latest_13f_date": "—",
            "verdict": "FAILED", "note": "CIK not found in EDGAR submissions API",
        }

    sec_name = data.get("name", "")

    # Gather 13F-HR filings from the recent block
    recent = (data.get("filings", {}) or {}).get("recent", {}) or {}
    forms = recent.get("form", [])
    fil_dates = recent.get("filingDate", [])

    hr_dates: list[str] = []
    for i, form in enumerate(forms):
        if form == "13F-HR":
            d = fil_dates[i] if i < len(fil_dates) else ""
            if d:
                hr_dates.append(d)

    # (b) recency check
    latest_date = max(hr_dates) if hr_dates else None

    if is_closed:
        # closed funds: only need ever-filed a 13F-HR
        if not hr_dates:
            recency_ok = False
            recency_note = "no 13F-HR ever found (closed fund)"
        else:
            recency_ok = True
            recency_note = f"closed — last 13F-HR: {latest_date}"
    else:
        cutoff = (date.today() - timedelta(days=int(RECENCY_MONTHS * 30.44))).isoformat()
        if not latest_date:
            recency_ok = False
            recency_note = "no 13F-HR found in recent filings"
        elif latest_date < cutoff:
            recency_ok = False
            recency_note = f"most recent 13F-HR {latest_date} is older than {RECENCY_MONTHS}m cutoff {cutoff}"
        else:
            recency_ok = True
            recency_note = ""

    # (c) loose name sanity — FLAG (not FAIL) if no significant token matches
    sig_tokens = _significant_tokens(config_name)
    sec_lower = sec_name.lower()
    name_match = any(tok in sec_lower for tok in sig_tokens) if sig_tokens else True
    name_note = "" if name_match else (
        f"no significant token from config name '{config_name}' found in SEC name '{sec_name}'"
    )

    # Determine verdict
    if not recency_ok:
        verdict = "FAILED"
        note = recency_note
    elif not name_match:
        verdict = "FLAGGED"
        note = name_note
    else:
        verdict = "VERIFIED"
        note = recency_note if is_closed else ""

    return {
        "slug": slug,
        "cik": cik,
        "config_name": config_name,
        "sec_name": sec_name,
        "latest_13f_date": latest_date or "—",
        "verdict": verdict,
        "note": note,
    }


def run_verification(funds: dict) -> list[dict]:
    results = []
    total = len(funds)
    for i, (slug, spec) in enumerate(funds.items(), 1):
        print(f"  [{i}/{total}] {slug} (CIK {spec.get('cik', '?')}) ...", end=" ", flush=True)
        r = verify_fund(slug, spec)
        print(r["verdict"])
        results.append(r)
    return results


def write_report(results: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    verified = [r for r in results if r["verdict"] == "VERIFIED"]
    flagged = [r for r in results if r["verdict"] == "FLAGGED"]
    failed = [r for r in results if r["verdict"] == "FAILED"]

    lines = [
        "# 13F CIK Verification Report — 2026-07-10",
        "",
        f"**Run date:** {date.today()}  ",
        f"**Total funds checked:** {len(results)}  ",
        f"**VERIFIED:** {len(verified)}  **FLAGGED:** {len(flagged)}  "
        f"**FAILED:** {len(failed)}",
        "",
        "Criteria:",
        "- (a) Submissions JSON exists at data.sec.gov",
        "- (b) A 13F-HR filing within 18 months (closed funds: ever-filed)",
        "- (c) Loose name sanity — flag if no significant token from config name "
        "appears in the SEC entity name (FLAG = review, not auto-fail)",
        "",
        "## Results table",
        "",
        "| slug | CIK | config name | SEC entity name | latest 13F-HR | verdict | note |",
        "|------|-----|-------------|-----------------|---------------|---------|------|",
    ]

    for r in sorted(results, key=lambda x: x["slug"]):
        note = r["note"].replace("|", "/") if r["note"] else ""
        lines.append(
            f"| {r['slug']} | {r['cik']} | {r['config_name']} "
            f"| {r['sec_name']} | {r['latest_13f_date']} "
            f"| **{r['verdict']}** | {note} |"
        )

    if flagged:
        lines += [
            "",
            "## FLAGGED — review required",
            "",
            "These funds passed recency check but the name sanity check found no match. "
            "Operator should manually confirm CIK is correct.",
            "",
        ]
        for r in flagged:
            lines.append(f"- **{r['slug']}** (CIK {r['cik']}): {r['note']}")

    if failed:
        lines += [
            "",
            "## FAILED — must fix before ingestion",
            "",
        ]
        for r in failed:
            lines.append(f"- **{r['slug']}** (CIK {r['cik']}): {r['note']}")

    lines += [
        "",
        "---",
        "_Generated by scripts/verify_13f_ciks.py (SM2-R6)_",
    ]

    path.write_text("\n".join(lines) + "\n")
    print(f"\nReport written to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify 13F CIKs against SEC EDGAR")
    parser.add_argument("--json", action="store_true", help="Print JSON results to stdout")
    parser.add_argument("--out", default=str(REPORT_PATH),
                        help="Markdown report output path")
    args = parser.parse_args()

    cfg = _cfg_mod.load()
    funds = (cfg.get("smart_money", {}) or {}).get("funds", {}) or {}
    if not funds:
        print("ERROR: no funds found in config smart_money.funds", file=sys.stderr)
        return 1

    print(f"Verifying {len(funds)} funds against SEC EDGAR submissions API ...")
    results = run_verification(funds)

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        write_report(results, Path(args.out))

    # Exit nonzero if any ACTIVE fund FAILED
    active_failures = [
        r for r in results
        if r["verdict"] == "FAILED"
        # closed funds that FAIL are still a failure (they should have historical filings)
    ]
    if active_failures:
        print(f"\nEXIT 1 — {len(active_failures)} fund(s) FAILED verification:", file=sys.stderr)
        for r in active_failures:
            print(f"  {r['slug']} (CIK {r['cik']}): {r['note']}", file=sys.stderr)
        return 1

    n_flagged = sum(1 for r in results if r["verdict"] == "FLAGGED")
    if n_flagged:
        print(f"\nNote: {n_flagged} fund(s) FLAGGED (name sanity) — review report")

    print(f"\nAll {len(results)} funds passed (VERIFIED or FLAGGED/closed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
