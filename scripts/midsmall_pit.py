"""Point-in-time S&P 400 (mid) + 600 (small) membership — the GO-blocker data for
the insider-buying factor (research/INSIDER_FACTOR.md §4).

The insider signal's edge is academically concentrated in small/mid-caps, but our
only PIT membership was S&P 500 (large-cap), so the de-biased Phase-0 test was run
where the signal does NOT live. This reconstructs mid- and small-cap membership
the same way the fja05680 S&P 500 CSV is built — from each Wikipedia page's CURRENT
constituents plus its "changes" log, walked BACKWARD into (ticker, start, end)
intervals — then unions all three into one S&P 1500 PIT membership.

Honest coverage ceiling (the changes logs only go so far back):
  * S&P 400 changes from ~2012  → mid-cap PIT reliable 2012→
  * S&P 600 changes from ~2019  → small-cap PIT reliable ~2020→
Names present before their log began get start = the log's first date (member "at
least since"); we cannot recover earlier membership from this free source — the
same irreducible gap as the delisted-price recovery.

Writes:
  data/breadth/sp1500_pit_membership.parquet     (ticker, start_date, end_date, src)
  data/breadth/_closes_delisted_1500.parquet      best-effort prices for members that
                                                   have since left and aren't in the deep matrix

Run once, offline:  .venv/bin/python -m scripts.midsmall_pit
"""
from __future__ import annotations

import io
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.breadth import BreadthAdapter  # noqa: E402
from engine.equity_factors import _closes  # noqa: E402
from lib import config  # noqa: E402

HDR = {"User-Agent": "Mozilla/5.0 (macro-dashboard research)"}
INDICES = {
    "sp400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
    "sp600": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
}


def _norm(sym) -> str:
    return str(sym).replace(".", "-").strip()


def reconstruct(label: str, url: str) -> pd.DataFrame:
    """Walk the Wikipedia changes log backward from today's constituents into
    membership intervals. Guarantees the reconstructed open intervals reconcile
    exactly to the current constituent list."""
    html = urllib.request.urlopen(urllib.request.Request(url, headers=HDR), timeout=60).read().decode()
    tabs = pd.read_html(io.StringIO(html))
    current = {_norm(s) for s in tabs[0]["Symbol"]}
    ch = tabs[1].copy()
    ch.columns = ["_".join(c).strip() if isinstance(c, tuple) else str(c) for c in ch.columns]
    ch["date"] = pd.to_datetime(ch[[c for c in ch.columns if "Date" in c][0]], errors="coerce")
    addc = [c for c in ch.columns if c.startswith("Added") and "Ticker" in c][0]
    remc = [c for c in ch.columns if c.startswith("Removed") and "Ticker" in c][0]
    ch["add"] = ch[addc].map(_norm).replace("nan", "")
    ch["rem"] = ch[remc].map(_norm).replace("nan", "")
    ch = ch.dropna(subset=["date"]).sort_values("date", ascending=False)

    cset = set(current)
    intervals: dict[str, list] = defaultdict(list)
    for t in current:
        intervals[t].append([None, pd.NaT])          # open spell, start unknown
    orphan = 0
    for _, r in ch.iterrows():
        D = r["date"]
        if r["add"]:                                   # entered at D -> close its open spell's start
            iv = intervals[r["add"]]
            if r["add"] in cset and iv and iv[-1][0] is None:
                iv[-1][0] = D
                cset.discard(r["add"])                 # not a member just before D
            else:
                orphan += 1                            # add we can't place (M&A/rename) — skip, conservative
        if r["rem"]:                                   # left at D -> member until D, older start unknown
            intervals[r["rem"]].append([None, D])
            cset.add(r["rem"])
    floor = ch["date"].min()

    rows = [(t, s if s is not None else floor, e) for t, ivs in intervals.items() for s, e in ivs]
    m = pd.DataFrame(rows, columns=["ticker", "start_date", "end_date"])
    m["src"] = label
    opens = set(m.loc[m["end_date"].isna(), "ticker"])
    assert opens == current, f"{label}: open intervals do not reconcile to current constituents"
    print(f"[{label}] {len(m)} intervals · {m['ticker'].nunique()} tickers · "
          f"changes {floor.date()}→{ch['date'].max().date()} · {orphan} orphan adds skipped", flush=True)
    return m


def build_membership() -> pd.DataFrame:
    parts = [reconstruct(lbl, url) for lbl, url in INDICES.items()]
    sp500 = config.data_dir() / "breadth" / "sp500_pit_membership.parquet"
    if sp500.exists():
        s = pd.read_parquet(sp500)
        s["src"] = "sp500"
        parts.append(s[["ticker", "start_date", "end_date", "src"]])
        print(f"[sp500] {len(s)} intervals folded in", flush=True)
    allm = pd.concat(parts, ignore_index=True)
    # A ticker can legitimately appear in more than one index over time (promotions
    # 600→400→500); keep every interval, just de-dup exact repeats.
    allm = allm.drop_duplicates(subset=["ticker", "start_date", "end_date"]).reset_index(drop=True)
    out = config.data_dir() / "breadth" / "sp1500_pit_membership.parquet"
    allm.to_parquet(out)
    print(f"[sp1500] {len(allm)} intervals · {allm['ticker'].nunique()} unique tickers · "
          f"by src {allm['src'].value_counts().to_dict()} -> {out}", flush=True)
    return allm


def fetch_delisted(members: pd.DataFrame) -> None:
    """Best-effort prices for PIT members that have since left and aren't already in
    the deep close matrix. Mirrors scripts.residual_alpha_pit.fetch_delisted but over
    the full 1500 member set; written to a SEPARATE file so the residual-alpha
    delisted cache is left untouched."""
    pit = set(members["ticker"])
    have = set(_closes().columns)        # deep matrix shares these 1506 columns
    missing = sorted(pit - have)
    print(f"[delisted] {len(pit)} historical members · already priced {len(pit & have)} "
          f"({100 * len(pit & have) // max(len(pit),1)}%) · fetching {len(missing)} missing "
          f"(best-effort, many won't resolve) …", flush=True)
    if not missing:
        return
    closes = BreadthAdapter()._download_closes(missing, "max")
    closes = closes.loc[:, ~closes.columns.duplicated()].dropna(axis=1, how="all").sort_index()
    got = [t for t in missing if t in closes.columns]
    closes = closes[got]
    out = config.data_dir() / "breadth" / "_closes_delisted_1500.parquet"
    closes.to_parquet(out)
    recovered = len(pit & have) + len(got)
    print(f"[delisted] resolved {len(got)}/{len(missing)} ({100 * len(got) // max(len(missing),1)}%) "
          f"-> {out} {closes.shape}", flush=True)
    print(f"[coverage] PIT price coverage now {recovered}/{len(pit)} "
          f"({100 * recovered // max(len(pit),1)}%) — the rest is the irreducible free-data gap.",
          flush=True)


def main() -> int:
    fetch_delisted(build_membership())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
