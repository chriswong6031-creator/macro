"""scripts.measure_massive_close_parity — does the vendor's close AGREE with ours?

THE QUESTION THIS ANSWERS, AND WHY IT IS NOT THE SAME AS "DOES IT FETCH".
``engine.close_pass.massive_close`` closes a coverage hole by splicing a vendor
close onto a store history. Coverage is trivially measurable and by itself proves
nothing: a wrong price is indistinguishable from a right one on a board. What
makes the splice legal is the BASIS ARGUMENT — a store history is re-based
retrospectively at each ex-date, so for a name with no same-session corporate
action today's raw close IS today's adjusted close — and an argument is not
evidence. This script is the evidence: it joins the names whose store ALREADY
carried the session's bar against the vendor's close for the same session and
reports how far apart they are, on the real universe.

Those names are the control group. We do not need the vendor for them; that is
exactly why they can grade it. If the two agree to the cent across the whole
overlap, the same construction on the names the store had NOT yet reached is the
same construction.

MEASURED 2026-08-13 (committed store, live API): overlap 1,741 names, 1,741
agreeing within $0.005, max abs diff 0.000117 — float32 parquet storage, not a
price difference. Fifteen of those 1,741 had a same-session EX-DIVIDEND and still
agreed to the cent, which is the basis law confirming itself from the inside: the
re-basing applies to the bars BEHIND the ex-date, never to the ex-date's own
close.

THIS BATTERY ALSO FOUND A REAL DEFECT, which is the point of running it rather
than reasoning about it. Its first run reported ONE disagreement — TPC, store
94.67 against vendor 16.98 — because the matcher upper-cased the vendor's ticker
and the vendor's ticker space is case-SENSITIVE (``TpC`` is a different security
from ``TPC``; ``BCpC`` is Brunswick notes, not Balchem's ``BCPC``). See
``massive_close.universe_ticker``.

THREE NUMBERS, and the third is the one to argue with:
  AGREEMENT     overlap names, count within a cent, max abs diff, worst names.
  COVERAGE      names with no store bar that the vendor DOES cover — the gain,
                measured rather than assumed.
  DARKED        the same-session split/ex-dividend names the guard refuses (58
                of the 2026-08-14 gain). A darked name may well have a correct
                store bar already — the guard refuses the SPLICE, not the name,
                and it refuses it without needing to know which case it is in.
                BYND split 30:1 that session and IS in the guard's set, but it is
                not in this repo's 1,763-name universe, so it never reaches the
                darked list: the guard is upstream of membership.

READ-ONLY. Opens the price store, calls the vendor, prints. Writes no ``data/``
path, no ``site/`` path and no artifact of any kind; ``--json`` goes to stdout so
a caller can redirect it if it wants a file. Needs a FULL checkout — it reads the
real store — which is why it is a script and not a test.

Usage:
  python -m scripts.measure_massive_close_parity                     # last session
  python -m scripts.measure_massive_close_parity --session 2026-08-14
  python -m scripts.measure_massive_close_parity --session 2026-08-14 --json
  python -m scripts.measure_massive_close_parity --simulate-collect  # evaluated_n
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.close_pass import massive_close as MC  # noqa: E402

#: "Agrees" means the two closes round to the same cent. Not an epsilon chosen to
#: pass: a board renders `$%.2f`, so a difference below this is a difference no
#: reader and no gate can see, and anything above it is a real disagreement.
CENT = 0.005


def last_session() -> str:
    """The newest completed NYSE session, from the repo's own calendar."""
    from datetime import datetime, timezone  # noqa: PLC0415
    from lib.nyse_calendar import ET, is_session  # noqa: PLC0415
    from datetime import timedelta  # noqa: PLC0415

    day = datetime.now(timezone.utc).astimezone(ET).date()
    for _ in range(10):
        if is_session(day):
            return day.isoformat()
        day -= timedelta(days=1)
    return day.isoformat()


def store_closes(session: str) -> tuple[dict[str, float], list[str], int]:
    """``({ticker: store close for session}, names with no session bar, universe)``.

    One pass over the real universe. A name whose newest bar IS the session is a
    control-group member; every other name is a coverage candidate — which is the
    same split ``close_pass_publish.collect`` makes, made here without the gate.
    """
    from scripts.build_stock_library import universe  # noqa: PLC0415
    import pandas as pd  # noqa: PLC0415

    have: dict[str, float] = {}
    missing: list[str] = []
    uni = universe()
    for ticker, close, _high, _name, _sector in uni:
        if close is None or getattr(close, "empty", True):
            missing.append(ticker)
            continue
        last = close.index[-1]
        through = (last.date() if hasattr(last, "date") else last).isoformat()
        price = close.iloc[-1]
        if through == session and not pd.isna(price):
            have[ticker] = float(price)
        else:
            missing.append(ticker)
    return have, missing, len(uni)


def parity(session: str) -> dict:
    """The whole battery. Returns a plain dict so ``--json`` is the same object."""
    have, missing, universe_n = store_closes(session)
    wanted = sorted(set(have) | set(missing))

    fetched = MC.fetch_session_closes(session, wanted)
    vendor = dict(fetched.closes)
    guard = MC.corp_action_tickers(session) if fetched.ok else MC.CorpActions(session)

    overlap = sorted(set(have) & set(vendor))
    diffs = sorted(((abs(have[t] - vendor[t]), t) for t in overlap), reverse=True)
    agree = sum(1 for d, _ in diffs if d < CENT)
    gained = sorted(t for t in missing if t in vendor)
    darked = sorted(t for t in gained if t in guard.tickers)

    return {
        "session": session,
        "universe_n": universe_n,
        "source": fetched.source,
        "finalized": fetched.finalized,
        "basis": fetched.basis,
        "observed_at": fetched.observed_at,
        "reason": fetched.reason,
        "vendor_rows": fetched.vendor_rows,
        "vendor_matched": fetched.matched_n,
        "store_has_session_bar": len(have),
        "store_missing_session_bar": len(missing),
        "overlap_n": len(overlap),
        "agree_within_cent": agree,
        "disagree_n": len(overlap) - agree,
        "max_abs_diff": round(diffs[0][0], 6) if diffs else None,
        "worst": [{"ticker": t, "store": round(have[t], 4),
                   "massive": round(vendor[t], 4), "diff": round(d, 4)}
                  for d, t in diffs[:12]],
        "coverage_gain_n": len(gained),
        "coverage_after": len(have) + len(gained) - len(darked),
        "corp_actions": {
            "complete": guard.complete,
            "splits_n": guard.splits_n,
            "dividends_n": guard.dividends_n,
            "reason": guard.reason,
            "darked_in_gain": darked,
            "darked_in_overlap": sorted(t for t in overlap if t in guard.tickers),
        },
    }


def simulate_collect(session: str) -> dict:
    """Run the REAL ``collect()`` and report the coverage line it produces.

    The measured claim in the PR body, not an estimate: this is the same function
    the workflow calls, over the same store, with the vendor live. It runs the
    gate over the whole universe, so it costs what the pass costs.
    """
    from scripts import close_pass_publish as P  # noqa: PLC0415

    out = P.collect(session)
    meta = dict(out.get("close_meta") or {})
    return {
        "session": session,
        "universe_n": out["universe_n"],
        "evaluated_n": len(out["verdicts"]),
        "skipped": dict(out["skipped"]),
        **meta,
    }


def _print(report: dict) -> None:
    ca = report["corp_actions"]
    print(f"session {report['session']}  universe {report['universe_n']}  "
          f"source={report['source']} finalized={report['finalized']} "
          f"basis={report['basis']}")
    if report["reason"]:
        print(f"  vendor degraded: {report['reason']}")
    print(f"  vendor rows {report['vendor_rows']}, matched {report['vendor_matched']} "
          f"of {report['universe_n']} universe names")
    print("\nAGREEMENT (store's own session bar vs Massive, the control group)")
    print(f"  overlap            {report['overlap_n']}")
    print(f"  agree within $0.005 {report['agree_within_cent']}  "
          f"({report['disagree_n']} disagree)")
    print(f"  max abs diff       {report['max_abs_diff']}")
    for row in report["worst"][:8]:
        print(f"    {row['ticker']:<8} store {row['store']:>12}  "
              f"massive {row['massive']:>12}  diff {row['diff']}")
    print("\nCOVERAGE")
    print(f"  store had the session bar   {report['store_has_session_bar']}")
    print(f"  store did NOT               {report['store_missing_session_bar']}")
    print(f"  of those, Massive covers    {report['coverage_gain_n']}  <- the gain")
    print(f"  darked by the corp guard    {len(ca['darked_in_gain'])} "
          f"{ca['darked_in_gain']}")
    print(f"  names with a session close  {report['coverage_after']}")
    print(f"\nCORP ACTIONS  complete={ca['complete']} splits={ca['splits_n']} "
          f"dividends={ca['dividends_n']}")
    if ca["darked_in_overlap"]:
        print(f"  also in the overlap (store already had a bar): "
              f"{ca['darked_in_overlap'][:20]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--session", default=None, help="YYYY-MM-DD (default: last)")
    ap.add_argument("--json", action="store_true", help="machine-readable to stdout")
    ap.add_argument("--simulate-collect", action="store_true",
                    help="run the real collect() and report evaluated_n")
    args = ap.parse_args(argv)

    session = args.session or last_session()
    report = (simulate_collect(session) if args.simulate_collect
              else parity(session))
    if args.json or args.simulate_collect:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        _print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
