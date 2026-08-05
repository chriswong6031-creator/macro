#!/usr/bin/env python3
"""Regenerate the frozen HK G1 board fixture from the committed close panel.

WHAT THIS RE-PINS
-----------------
``tests/fixtures/hk_board_2026_07_31.json`` is the 2026-07-31 HK board panel: the
verdict / meta / trailing-closes slice of ``data/hk_search/closes_deep.parquet``
that ``tests/test_hk_board_rank.py`` replays the G1 gates against.  It is a
MEASUREMENT frozen at an as-of date, not a hand-built board, so it is only
trustworthy while it still matches the panel it was measured from.  Two tests in
``TestG1FixtureIsNotStale`` enforce exactly that:

  * ``test_source_panel_history_is_unchanged`` — every frozen 90-session tail must
    equal the matching historical slice of the live panel, date for date and
    close for close.
  * ``test_witness_verdicts_replay_from_the_live_panel`` — the seven witness
    tickers' verdicts must re-derive from the live panel through the real
    ``engine.signal_gate``.

The panel is append-only in normal operation, and an append does not invalidate a
historical replay.  A REWRITE at or before the as-of date does — and yahoo ships
those routinely as dividend adjustments, which rescale a ticker's entire history
by a constant ratio (PR #4559: 2338.HK's whole tail moved by ~0.9871).  Those
tests then hard-fail on a fixture nobody touched.  This script is the remedy:
it rebuilds the ENTIRE fixture from the panel, with the same slices those tests
check, and refuses to write when the drift does not look like an adjustment.

USAGE
-----
    python3 scripts/regen_hk_g1_fixture.py            # re-pin (writes only on drift)
    python3 scripts/regen_hk_g1_fixture.py --check    # report, never write
    python3 scripts/regen_hk_g1_fixture.py --force    # write through a refusal

Exit codes: 0 = byte no-op or written · 1 = fatal (missing fixture, NaN payload)
· 2 = refused (structural / non-adjustment drift) · 3 = ``--check`` would write.

This script re-pins an EXISTING freeze.  The era parameters (``_as_of``,
``_tail_sessions``, ``_source``) are read from the committed fixture and never
minted here: a new era is a deliberate act that re-pins the paired artifact
``tests/fixtures/hk_standouts_2026_07_31.json`` and ``BOARD_ASOF`` in the same
commit (see the ``prod_board`` docstring in the test module).

THE ERA-STAMPED SHAPE (why each rule is what it is)
---------------------------------------------------
Every rule below was fitted against the committed file and reproduces it exactly.
They are conventions of the 2026-07-31 freeze, not re-derivable preferences, so
they are recorded here rather than left to the next regenerator's judgement.

*Ticker set and order* — ``[c for c in panel.columns if hist[c].dropna().shape[0]
>= 250]``, in PANEL COLUMN order, and the same order in ``verdicts``, ``meta``
and ``closes``.  Reproduces the committed 157 tickers in the committed order.

*The 9-key verdict prune* — the stored verdicts carry only ``eligible``,
``tier_cascade``, ``ticks``, ``fresh_bars``, ``above200``, ``weekly_bull``,
``provisional``, ``asof`` and ``last`` (itself normalised to the four keys
``date``/``type``/``quality``/``reason``, null-filled).  This was never a
historical ``signal_gate.compact()`` schema: ``_VERDICT_KEYS`` already carried
today's 19 keys at the fixture's birth commit c781a4cd483.  The 9 keys are
#4421's deliberate lean prune, and they are exactly the harness READ CLOSURE —
the lane builders in ``engine/hk_board_rank.py`` and ``engine/us_board_rank.py``
read only those fields (plus ``last.{date,type,quality,reason}``), and the
witness replay compares five of them.  Regenerated values are byte-identical to
the stored ones across all 157 tickers under today's engine (verified
2026-08-05, zero drift), so preserving the shape keeps the fixture byte-stable,
keeps the diff on a future re-pin surgical, and avoids the documented NaN hazard
that the full schema's ``state``/``last`` payloads can carry (see
``buy_signal()``'s docstring in ``engine/signal_gate.py``).

*Default ``reclaim_veto``* — the gate is called as
``signal_gate.compact(signal_gate.gate(ticker, series))``, i.e. with the DEFAULT
``reclaim_veto=True``, not the HK-production ``reclaim_veto=False``.  That is
deliberate: the frozen replay's contract is the witness test's own call, and
that test calls the default.  Changing it here would green this script while
reddening the test it exists to satisfy.

*``meta.price``* — ``round(px, 2)`` at or above HK$1, ``round(px, 3)`` below.
Fits 157/157; a plain 2dp rule fails on the two sub-dollar witnesses 3333.HK
(0.163) and 0884.HK (0.039).  The threshold is only bounded by the data to the
half-open interval (0.163, 1.06]; HK$1.00 is chosen as the round number inside
that band.

*``meta.off_high``* — ``round((px / max(last 252 sessions) - 1) * 100, 1)``, with
``-0.0`` normalised to ``0.0``.  The 252-session window is uniquely correct:
252 fits 157/157, while full history fits 52/157, the 90-session tail 40/157,
250 sessions 151/157, 260 sessions 151/157 and a calendar 52-week window
147/157.

*``meta.dir``* — the constant ``"flat"``.  All 157 stored values are ``"flat"``,
and production's ``dir`` is a cycle-ladder field the price panel cannot produce
(``"dir": r.get("cycle_dir") or "flat"`` in ``scripts/build_hk_library.py``), so
the generator stamps the fallback.  The lanes read ``dir`` only as
down / not-down, so the fallback is faithful for the replay.

*The byte contract* — ``json.dumps(obj, indent=1, allow_nan=False)`` encoded
ASCII, no trailing newline, default separators.  ``allow_nan=False`` is the NaN
gate, not a formatting choice: a NaN anywhere in the payload aborts the run
BEFORE any write rather than persisting a value that reloads as a float the
tests cannot compare.

PROVENANCE AND THE NO-OP
------------------------
``_source_sha256_16`` is stamped only on a REAL write.  Step one of the protocol
serialises the candidate carrying the COMMITTED sha and compares bytes, so an
append-only panel advance — which moves the panel's sha but not one byte of the
frozen payload — is a byte-level no-op: nothing is written, and the recorded sha
keeps pointing at the panel image of the last genuine freeze.

DRIFT PROTOCOL
--------------
When the bytes do differ the candidate is classified, not blindly written:

  * provenance-only (``_note`` / sha alone) — benign, written;
  * adjustment drift — every drifted ticker must keep its dates AND satisfy a
    constant-ratio signature; each one prints an ``ADJUSTMENT-SIGNATURE`` receipt
    line so the regeneration commit carries proof the rewrite was an adjustment;
  * anything else — ticker set changes, calendar surgery, non-constant close
    drift, or verdict/meta drift on a ticker whose closes did NOT move — is
    REFUSED with a receipt.  ``--force`` writes through, after diagnosis.

The constant-ratio tolerance is 0.0025 in price units: the closes are stored at
3dp, so both sides of the comparison carry a rounding of up to 0.0005 and the
implied per-session ratio wobbles accordingly (#4559 measured a 0.987044-0.987071
spread from exactly this noise, on a genuinely constant adjustment).

The signature also needs at least TWO changed sessions to mean anything.  With one,
the median ratio is that session's own ratio and the residual is zero by
construction — a test that cannot fail is not a test, so a lone re-printed close is
refused rather than waved through as an "adjustment".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:                       # run as `python3 scripts/...`
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np                                       # noqa: E402
import pandas as pd                                      # noqa: E402

from engine import signal_gate                           # noqa: E402


DEFAULT_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "hk_board_2026_07_31.json"

# Era-stamped conventions — see the module docstring for the receipt behind each.
MIN_HISTORY_SESSIONS = 250
OFF_HIGH_WINDOW = 252
PRICE_3DP_BELOW = 1.0
STORED_VERDICT_KEYS = ("eligible", "tier_cascade", "ticks", "fresh_bars",
                       "above200", "weekly_bull", "provisional", "asof", "last")
MARKER_KEYS = ("date", "type", "quality", "reason")
CLOSE_DECIMALS = 3

# Two 3dp roundings (0.0005 each) plus slack, in price units.
RATIO_TOLERANCE = 0.0025

NOTE = ("GENERATED by scripts/regen_hk_g1_fixture.py (byte-idempotent; prints "
        "ADJUSTMENT-SIGNATURE receipts on drift). See "
        "tests/test_hk_board_rank.py::regenerate_g1_fixture.")

EXIT_OK = 0
EXIT_FATAL = 1
EXIT_REFUSED = 2
EXIT_WOULD_WRITE = 3


def say(message: str) -> None:
    """Every line this script emits.  Plain stdout — no logger, no annotations."""
    print(message, flush=True)


# --------------------------------------------------------------------------- #
# payload derivation
# --------------------------------------------------------------------------- #
def _scalar(value):
    """numpy scalars -> python scalars (byte-neutral; defensive against dtype leaks)."""
    if isinstance(value, np.generic):
        return value.item()
    return value


def prune_verdict(ticker: str, full: dict) -> dict:
    """The era-stamped 9-key verdict, in the committed insertion order.

    ``last`` is normalised to the four marker keys with explicit None fill — live
    sell/cut markers omit ``quality``/``reason``, and the fixture stores all four
    on all 157.  A marker carrying keys OUTSIDE the four means the upstream shape
    widened and this prune is dropping data, so it is announced loudly.
    """
    out: dict = {}
    for key in STORED_VERDICT_KEYS:
        if key != "last":
            out[key] = _scalar(full.get(key))
            continue
        marker = full.get("last")
        if not marker:
            out["last"] = None
            continue
        extra = [k for k in marker if k not in MARKER_KEYS]
        if extra:
            say(f"WARNING {ticker}: marker carries keys outside the stored four "
                f"{sorted(extra)} — the upstream marker shape widened and this "
                f"prune is dropping them; proceeding with the era-stamped shape")
        out["last"] = {k: _scalar(marker.get(k)) for k in MARKER_KEYS}
    return out


def build_payload(panel: "pd.DataFrame", as_of: str, tail_sessions: int) -> dict:
    """verdicts / meta / closes for every ticker with enough history, in panel order."""
    hist = panel.loc[:as_of]
    tickers = [c for c in panel.columns
               if hist[c].dropna().shape[0] >= MIN_HISTORY_SESSIONS]

    verdicts: dict = {}
    meta: dict = {}
    closes: dict = {}
    for ticker in tickers:
        series = hist[ticker].dropna()

        # The witness replay's exact call — DEFAULT reclaim_veto, same slice.
        full = signal_gate.compact(
            signal_gate.gate(ticker, panel[ticker].loc[:as_of].dropna()))
        verdicts[ticker] = prune_verdict(ticker, full)

        last_px = float(series.iloc[-1])
        price = (round(last_px, 2) if last_px >= PRICE_3DP_BELOW
                 else round(last_px, 3))
        high = float(series.tail(OFF_HIGH_WINDOW).max())
        off_high = round((last_px / high - 1) * 100, 1)
        if off_high == 0.0:                      # -0.0 is not a reading, it is a sign
            off_high = 0.0
        meta[ticker] = {"name": ticker, "price": price, "off_high": off_high,
                        "dir": "flat"}

        tail = series.tail(tail_sessions)
        closes[ticker] = {
            "dates": [str(index.date()) for index in tail.index],
            "closes": [round(float(value), CLOSE_DECIMALS) for value in tail.tolist()],
        }

    return {"verdicts": verdicts, "meta": meta, "closes": closes}


def assemble(committed: dict, payload: dict, sha16: str) -> dict:
    """The full fixture object in the committed top-level insertion order."""
    return {
        "_note": NOTE,
        "_source": committed["_source"],
        "_source_sha256_16": sha16,
        "_as_of": committed["_as_of"],
        "_tail_sessions": committed["_tail_sessions"],
        "verdicts": payload["verdicts"],
        "meta": payload["meta"],
        "closes": payload["closes"],
    }


def serialize(obj: dict) -> bytes:
    """The byte contract.  ``allow_nan=False`` aborts on a NaN before any write."""
    return json.dumps(obj, indent=1, allow_nan=False).encode("ascii")


# --------------------------------------------------------------------------- #
# drift classification
# --------------------------------------------------------------------------- #
def _ratio_signature(old_closes: list, new_closes: list) -> dict:
    """Constant-ratio test over the sessions whose close moved.

    A dividend adjustment rescales a whole history by one factor, so every changed
    session must sit on the SAME ratio once 3dp rounding is allowed for.  Returns
    the receipt numbers plus the sessions that fail it.

    A SINGLE changed session is refused before the ratio is even consulted: the
    median of one ratio is that ratio, so the residual is identically zero and the
    test would pass any value at all — it is arithmetically incapable of failing.
    One re-printed close is a correction or a corruption, not a rescaled history,
    and it earns the same human look (``--force`` after diagnosis).
    """
    changed = [(i, o, n) for i, (o, n) in enumerate(zip(old_closes, new_closes))
               if o != n]
    nonpositive = [(i, o, n) for i, o, n in changed if o <= 0]
    if nonpositive:
        return {"changed": changed, "passed": False, "ratios": [],
                "r_med": None, "violations": nonpositive[:5], "resid": None,
                "why": "a changed session has a non-positive old close — no ratio"}

    ratios = [n / o for _, o, n in changed]
    r_med = statistics.median(ratios) if ratios else None
    resid = max((abs(n - r_med * o) for _, o, n in changed), default=0.0)

    if len(changed) < 2:
        return {"changed": changed, "passed": False, "ratios": ratios,
                "r_med": r_med, "violations": changed[:5], "resid": resid,
                "why": "a single changed session carries no ratio signature "
                       "(the one-point residual is zero by construction)"}

    violations = [(i, o, n) for i, o, n in changed
                  if abs(n - r_med * o) > RATIO_TOLERANCE]
    return {"changed": changed, "passed": not violations, "ratios": ratios,
            "r_med": r_med, "violations": violations[:5], "resid": resid,
            "why": "" if not violations else "non-constant ratio"}


def classify(committed: dict, candidate: dict) -> dict:
    """Compare the committed payload against the freshly derived one.

    Returns ``{"refusals": [...], "adjusted": [...], "downstream": [...],
    "sections": [...], "lines": [...]}`` — ``lines`` is the receipt text to print
    in order, ``refusals`` empty means the write is allowed without ``--force``.
    """
    lines: list[str] = []
    refusals: list[str] = []
    adjusted: list[str] = []
    downstream: list[str] = []

    old_closes_all = committed.get("closes") or {}
    new_closes_all = candidate["closes"]
    old_tickers = list(old_closes_all)
    new_tickers = list(new_closes_all)

    added = [t for t in new_tickers if t not in set(old_tickers)]
    removed = [t for t in old_tickers if t not in set(new_tickers)]
    if added or removed:
        refusals.append("ticker set changed")
        lines.append(f"REFUSE ticker set changed: +{len(added)} -{len(removed)} "
                     f"(committed {len(old_tickers)} -> candidate {len(new_tickers)})")
        if added:
            lines.append(f"  added:   {', '.join(added[:20])}"
                         + (" ..." if len(added) > 20 else ""))
        if removed:
            lines.append(f"  removed: {', '.join(removed[:20])}"
                         + (" ..." if len(removed) > 20 else ""))
    elif old_tickers != new_tickers:
        # Same set, different order: dict equality would call this benign, and the
        # fixture's insertion order IS part of its byte contract.
        first = next(i for i, (a, b) in enumerate(zip(old_tickers, new_tickers))
                     if a != b)
        refusals.append("ticker order changed")
        lines.append(f"REFUSE ticker order changed at position {first}: committed "
                     f"{old_tickers[first]} -> candidate {new_tickers[first]} "
                     f"(panel column order moved; the fixture's order is its contract)")

    shared = [t for t in new_tickers if t in set(old_tickers)]

    closes_moved: set = set()
    for ticker in shared:
        old = old_closes_all[ticker]
        new = new_closes_all[ticker]
        if old == new:
            continue
        closes_moved.add(ticker)

        old_dates = old.get("dates") or []
        new_dates = new.get("dates") or []
        if old_dates != new_dates:
            gained = [d for d in new_dates if d not in set(old_dates)]
            lost = [d for d in old_dates if d not in set(new_dates)]
            refusals.append(f"{ticker}: calendar surgery")
            lines.append(
                f"REFUSE {ticker}: session dates changed — the 90-session tail is a "
                f"different calendar, not a re-priced one "
                f"(+{len(gained)} -{len(lost)} dates)")
            if gained:
                lines.append(f"  added dates:   {', '.join(gained[:5])}"
                             + (" ..." if len(gained) > 5 else ""))
            if lost:
                lines.append(f"  removed dates: {', '.join(lost[:5])}"
                             + (" ..." if len(lost) > 5 else ""))
            continue

        sig = _ratio_signature(old["closes"], new["closes"])
        changed = sig["changed"]
        total = len(new["closes"])
        ratios = sig["ratios"]
        rmin = min(ratios) if ratios else float("nan")
        rmax = max(ratios) if ratios else float("nan")
        span_first = new_dates[changed[0][0]] if changed else "-"
        span_last = new_dates[changed[-1][0]] if changed else "-"
        resid = sig["resid"] if sig["resid"] is not None else float("nan")
        lines.append(
            f"ADJUSTMENT-SIGNATURE {ticker}: changed={len(changed)}/{total} sessions, "
            f"ratio min={rmin:.6f} max={rmax:.6f}, dates_equal=True, "
            f"span={span_first}..{span_last}, max|new-r*old|={resid:.4f}")

        if sig["passed"]:
            adjusted.append(ticker)
            continue

        refusals.append(f"{ticker}: {sig['why'] or 'non-constant drift'}")
        lines.append(f"REFUSE {ticker}: {sig['why'] or 'non-constant drift'} — "
                     f"the session(s) the signature cannot account for:")
        for index, old_value, new_value in sig["violations"]:
            ratio = (new_value / old_value) if old_value else float("nan")
            lines.append(f"    {new_dates[index]}  old={old_value}  new={new_value}  "
                         f"ratio={ratio:.6f}")
        lines.append("    ^ this needs human eyes: a dividend adjustment rescales a "
                     "whole history by ONE ratio measured over MANY sessions, so drift "
                     "that is not constant — or too thin to test — is corruption or a "
                     "partial rewrite, not an adjustment signature. Diagnose the panel "
                     "diff before re-pinning, then re-run with --force to write "
                     "through.")

    old_verdicts = committed.get("verdicts") or {}
    new_verdicts = candidate["verdicts"]
    old_meta = committed.get("meta") or {}
    new_meta = candidate["meta"]
    for ticker in shared:
        derived_changed = []
        for label, old_map, new_map in (("verdict", old_verdicts, new_verdicts),
                                        ("meta", old_meta, new_meta)):
            old = old_map.get(ticker)
            new = new_map.get(ticker)
            if old == new:
                continue
            keys = sorted(set(old or {}) | set(new or {}))
            for key in keys:
                before = (old or {}).get(key)
                after = (new or {}).get(key)
                if before != after:
                    derived_changed.append((label, key, before, after))
        if not derived_changed:
            continue
        if ticker in closes_moved:
            downstream.append(ticker)
            continue
        refusals.append(f"{ticker}: derived drift with unchanged closes")
        lines.append(
            f"REFUSE {ticker}: verdict/meta changed while its stored closes did NOT — "
            f"either the panel was rewritten OUTSIDE the {len(new_closes_all[ticker]['dates'])}"
            f"-session tail this fixture can see, or the engine's own output moved:")
        for label, key, before, after in derived_changed[:8]:
            lines.append(f"    {label}.{key}: {before!r} -> {after!r}")
        if len(derived_changed) > 8:
            lines.append(f"    ... and {len(derived_changed) - 8} more")
        lines.append("    ^ an engine-change PR knows itself and re-pins with --force; "
                     "unexplained movement here needs human eyes on the panel first.")

    sections = []
    if closes_moved or added or removed:
        sections.append("closes")
    if any(old_verdicts.get(t) != new_verdicts.get(t) for t in shared) or added or removed:
        sections.append("verdicts")
    if any(old_meta.get(t) != new_meta.get(t) for t in shared) or added or removed:
        sections.append("meta")

    return {"lines": lines, "refusals": refusals, "adjusted": adjusted,
            "downstream": downstream, "sections": sections,
            "added": added, "removed": removed, "closes_moved": sorted(closes_moved)}


# --------------------------------------------------------------------------- #
# entry point
# --------------------------------------------------------------------------- #
def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Regenerate the frozen HK G1 board fixture from the close panel.")
    parser.add_argument("--check", action="store_true",
                        help="report what would happen; never write "
                             "(exit 0 no-op / 3 would write / 2 would refuse)")
    parser.add_argument("--force", action="store_true",
                        help="write through a refusal, AFTER diagnosing it")
    parser.add_argument("--fixture", default=None,
                        help=f"fixture path (default {DEFAULT_FIXTURE})")
    parser.add_argument("--panel", default=None,
                        help="close panel path (default: the fixture's own _source, "
                             "resolved against the repo root)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    fixture_path = Path(args.fixture) if args.fixture else DEFAULT_FIXTURE
    if not fixture_path.exists():
        say(f"FATAL missing fixture {fixture_path}")
        say("This script RE-PINS an existing freeze — it does not mint new eras. The "
            "era parameters (_as_of, _tail_sessions, _source) live in the committed "
            "fixture, and a new era re-pins the paired board artifact and BOARD_ASOF "
            "in the same commit. Restore the fixture from git first.")
        return EXIT_FATAL

    committed_bytes = fixture_path.read_bytes()
    committed = json.loads(committed_bytes)

    as_of = str(committed["_as_of"])
    tail_sessions = int(committed["_tail_sessions"])
    source = str(committed["_source"])

    if args.panel:
        panel_path = Path(args.panel)
    else:
        candidate_path = Path(source)
        panel_path = (candidate_path if candidate_path.is_absolute()
                      else REPO_ROOT / candidate_path)
    if not panel_path.exists():
        say(f"FATAL missing close panel {panel_path}")
        return EXIT_FATAL

    say(f"fixture {fixture_path}")
    say(f"panel   {panel_path}")
    say(f"era     as_of={as_of} tail_sessions={tail_sessions} source={source}")

    panel = pd.read_parquet(panel_path)
    payload = build_payload(panel, as_of, tail_sessions)
    say(f"derived {len(payload['closes'])} tickers with >= {MIN_HISTORY_SESSIONS} "
        f"closes through {as_of}")

    old_sha = str(committed.get("_source_sha256_16") or "")
    new_sha = hashlib.sha256(panel_path.read_bytes()).hexdigest()[:16]

    # Step 1 — the no-op test carries the COMMITTED sha, so an append-only panel
    # advance (new sha, identical frozen payload) never churns the file.
    try:
        held_bytes = serialize(assemble(committed, payload, old_sha))
    except ValueError as exc:
        say(f"FATAL refusing to write a non-finite value into the fixture: {exc}")
        say("A NaN in the payload would reload as a float the replays cannot compare. "
            "Nothing was written.")
        return EXIT_FATAL

    if held_bytes == committed_bytes:
        say(f"NO-OP fixture already matches the panel byte for byte "
            f"({len(payload['closes'])} tickers, sha16 {old_sha} unchanged); "
            f"nothing written")
        return EXIT_OK

    verdict = classify(committed, payload)
    for line in verdict["lines"]:
        say(line)

    refusals = verdict["refusals"]
    payload_moved = bool(verdict["sections"])

    if refusals and not args.force:
        say(f"REFUSED {len(refusals)} blocking finding(s): "
            f"{'; '.join(refusals[:6])}"
            + (" ..." if len(refusals) > 6 else ""))
        say("Nothing was written. Diagnose the panel, then re-run with --force to "
            "write through.")
        return EXIT_REFUSED

    if args.check:
        if refusals:
            say("WOULD WRITE THROUGH (--force) past the refusals above; --check wrote "
                "nothing")
        elif payload_moved:
            say(f"WOULD WRITE payload drift in {', '.join(verdict['sections'])} "
                f"(adjusted={len(verdict['adjusted'])} "
                f"downstream={len(verdict['downstream'])}); --check wrote nothing")
        else:
            say("WOULD WRITE provenance only (_note / _source_sha256_16); the payload "
                "is byte-identical; --check wrote nothing")
        return EXIT_WOULD_WRITE

    try:
        final_bytes = serialize(assemble(committed, payload, new_sha))
    except ValueError as exc:
        say(f"FATAL refusing to write a non-finite value into the fixture: {exc}")
        return EXIT_FATAL

    fixture_path.write_bytes(final_bytes)

    if refusals:
        say(f"FORCED past {len(refusals)} refusal(s) — the receipts above are the "
            f"record of what was written through")
    if payload_moved:
        say(f"WROTE payload drift in {', '.join(verdict['sections'])}: "
            f"{len(verdict['adjusted'])} ticker(s) re-priced on a constant-ratio "
            f"signature, {len(verdict['downstream'])} with verdict/meta moved "
            f"downstream of their own re-pricing, "
            f"+{len(verdict['added'])}/-{len(verdict['removed'])} tickers")
    else:
        say("WROTE provenance only (_note / _source_sha256_16); the payload is "
            "byte-identical to the committed one")
    say(f"WROTE {fixture_path} — {len(payload['closes'])} tickers, "
        f"sha16 {old_sha or '(none)'} -> {new_sha}, {len(final_bytes)} bytes")
    return EXIT_OK


if __name__ == "__main__":                                # pragma: no cover
    sys.exit(main())
