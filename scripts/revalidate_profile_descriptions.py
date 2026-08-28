"""Re-adjudicate the CACHED business descriptions against the current entity
resolver and withdraw the ones that are provably about another company.

Why this exists
---------------
`collectors/equity_profile.py` treats descriptions as near-static and will leave a
non-empty cached row alone for REFRESH_DAYS (120). So hardening the matcher fixes
only FUTURE resolutions: a blurb that already named the wrong company keeps being
published to a public, crawlable dossier for months. Measured on the committed
cache, RWT (Redwood Trust, a mortgage REIT) was serving the description of a
restaurant in Portland, Oregon.

Two mechanisms correct that, and this script is the immediate half:

  * `RESOLVER_VERSION` marks every cached blurb as resolved-by-an-older-rule, so the
    collector re-adjudicates all of them with the FULL evidence set (both issuer
    names plus the live page's Wikidata short description) over its next few
    capped passes. That is the thorough half, and it is automatic.
  * This script runs now, offline, and withdraws the rows that are decidable
    without any network at all — where the SEC's own industry text for the ticker
    and the stored blurb describe incompatible kinds of organisation.

It is deliberately high-precision, not high-recall: see
`equity_profile.adjudicate_cached_row` for why the cache cannot support a
stricter offline test without making false accusations. Anything it does not
withdraw is not thereby declared correct — it is merely left for the collector.

A withdrawal also drops the ticker's cached Chinese translation. The zh cache is
keyed by a hash of the English text and `scripts/translate_profiles.py` already
discards translations whose hash no longer matches, but that rebuild is skipped
entirely when translation is disabled (no API key), which would strand a
translation of the WRONG company beside a now-empty English field.

    python3 scripts/revalidate_profile_descriptions.py            # report only
    python3 scripts/revalidate_profile_descriptions.py --apply    # write
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import equity_profile as EP  # noqa: E402
from lib import config  # noqa: E402

ZH_CACHE_NAME = "descriptions_zh.parquet"


def _profile_dir() -> Path:
    return config.data_dir() / "profile"


def revalidate(df: pd.DataFrame, now: str) -> tuple[pd.DataFrame, list[dict]]:
    """Return (updated frame, withdrawal records). Pure: never touches disk."""
    out = df.copy()
    for col, default in (("desc_strength", None), ("desc_resolver_version", 0),
                         ("desc_first_seen", None), ("desc_superseded_at", None),
                         ("desc_fetched_at", None)):
        if col not in out.columns:
            out[col] = default

    withdrawn: list[dict] = []
    for ticker, row in df.iterrows():
        drop, reason = EP.adjudicate_cached_row(
            row.get("name"), row.get("wiki_title"),
            row.get("description"), row.get("sic_description"))
        if not drop:
            continue
        withdrawn.append({
            "ticker": str(ticker),
            "name": EP._cell(row.get("name")),
            "wiki_title": EP._cell(row.get("wiki_title")),
            "sic_description": EP._cell(row.get("sic_description")),
            "reason": reason,
            "withdrawn_description": EP._cell(row.get("description")),
            "withdrawn_at": now,
        })
        # withdraw the claim, keep the receipt
        out.loc[ticker, "description"] = None
        out.loc[ticker, "wiki_title"] = None       # the title WAS the wrong page
        out.loc[ticker, "desc_strength"] = None
        out.loc[ticker, "desc_superseded_at"] = now
        out.loc[ticker, "desc_resolver_version"] = 0   # re-resolve me
        out.loc[ticker, "desc_tries"] = 0              # with a fresh retry budget
    return out, withdrawn


def purge_zh(zh_path: Path, tickers: set[str]) -> int:
    """Drop cached Chinese translations for tickers whose English was withdrawn."""
    if not tickers or not zh_path.exists():
        return 0
    zh = pd.read_parquet(zh_path)
    hit = zh.index.astype(str).isin(tickers)
    if not hit.any():
        return 0
    zh[~hit].to_parquet(zh_path)
    return int(hit.sum())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="write the corrected cache (default: report only)")
    args = ap.parse_args()

    prof_path = _profile_dir() / "profiles.parquet"
    if not prof_path.exists():
        print(f"no {prof_path} — nothing to revalidate")
        return 0

    df = pd.read_parquet(prof_path)
    has_desc = int(sum(
        1 for _, r in df.iterrows()
        if str(EP._cell(r.get("description")) or "").strip()))
    now = datetime.now(timezone.utc).isoformat()
    out, withdrawn = revalidate(df, now)

    print(f"resolver v{EP.RESOLVER_VERSION} · {len(df)} cached rows · "
          f"{has_desc} with a description")
    print(f"withdrawn as another company: {len(withdrawn)}")
    for w in withdrawn:
        print(f"  {w['ticker']:<7} {str(w['name'])[:30]:<32} "
              f"accepted page: {str(w['wiki_title'])[:30]:<32} [{w['reason']}]")
        print(f"          SEC says: {w['sic_description']}")
        print(f"          page said: {str(w['withdrawn_description'])[:110]}")
    print(f"retained pending collector re-adjudication: {has_desc - len(withdrawn)}")

    if not args.apply:
        print("\n(report only — pass --apply to write)")
        return 0

    out.to_parquet(prof_path)
    n_zh = purge_zh(_profile_dir() / ZH_CACHE_NAME, {w["ticker"] for w in withdrawn})
    print(f"\nwrote {prof_path}")
    print(f"purged {n_zh} stale Chinese translation(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
