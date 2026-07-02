#!/usr/bin/env python3
"""Cross-page cycle-consistency gate (masterplan R3-M3, wave W3.6).

The same instrument is rendered on several cycle surfaces:

  * ``site/cycledata/cycle_engine.js``       — cycle.html flagship MEASURED bands
  * ``site/countrycyclesdata/country_cycles.json`` — country_cycles.html
  * ``site/sectordata/sector_cycles.json``   — sector_cycles.html (US)
  * ``site/chinasectordata/sector_cycles.json`` — sector_cycles_china.html
  * ``site/marketsdata/markets_engine.js``   — markets.html (pulled from country_cycles)

R3-M3 asserts: **the same instrument must show the same ``pos_v2`` / ``phase_v2``
across every page that renders it — within tolerance — OR carry a declared basis
label that explains the difference.**  Two surfaces backing the *same conceptual*
instrument on *different tapes* (e.g. cycle.html's Japan on the local-currency
Nikkei ``^N225`` vs country_cycles' Japan on the USD ETF ``EWJ``) are allowed to
differ, but the difference must be DECLARED — each record must carry an explicit
``basis`` / ``ref`` label.  A same-tape mismatch (same ticker, same basis, different
number) is a real bug — a page recomputed or froze a stale value — and fails RED.

This is the anti-drift twin of ``check_nav_mega`` for the cycle vocabulary: it runs
as a pre-merge PR gate (ci.yml) and a pre-deploy gate, and it writes a full report to
``research/cycle_masterplan/W36_CONSISTENCY_REPORT.md`` for the audit trail.

Usage:
    python -m scripts.check_cycle_consistency [SITE_DIR] [--report PATH]
Exit codes: 0 = consistent (all same-tape agree; all cross-tape declared) · 1 = violation.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict

# pos_v2 is a 0-100 CDF gauge; a small numeric wobble between two builds of the same
# tape (e.g. one page rebuilt an hour later on one more bar) is tolerable.  A genuine
# same-tape divergence (a page recomputing with different math, or a frozen stale value)
# is many points.  2.0 pts separates the two populations comfortably.
POS_TOL = 2.0


def _load_json(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_js_object(path: str, var_name: str):
    """Extract the single ``window.<var_name> = {...};`` object literal from a generated JS file."""
    txt = open(path, encoding="utf-8").read()
    m = re.search(r"window\." + re.escape(var_name) + r"\s*=\s*(\{.*\});", txt, re.S)
    if not m:
        raise ValueError(f"{path}: could not find window.{var_name} object literal")
    return json.loads(m.group(1))


def _records_from_json(data) -> list:
    """Every dict carrying a 'now' block, from a nested cycle JSON."""
    out = []
    if isinstance(data, dict):
        if "now" in data and isinstance(data["now"], dict):
            out.append(data)
        for v in data.values():
            out.extend(_records_from_json(v))
    elif isinstance(data, list):
        for v in data:
            out.extend(_records_from_json(v))
    return out


class Reading:
    """One page's reading of one instrument."""

    __slots__ = ("page", "label", "ticker", "basis", "pos_v2", "phase_v2", "ref")

    def __init__(self, page, label, ticker, basis, pos_v2, phase_v2, ref=None):
        self.page = page
        self.label = label
        if isinstance(ticker, (list, tuple)):
            ticker = ticker[0] if ticker else ""
        self.ticker = str(ticker or "").upper()
        self.basis = basis or ""
        self.pos_v2 = pos_v2
        self.phase_v2 = phase_v2
        self.ref = ref

    @property
    def tape_key(self):
        """The (ticker, basis) identity — readings sharing it MUST agree."""
        return (self.ticker, self.basis)


def _collect(site_dir: str) -> list:
    readings: list = []

    # 1. country_cycles.json — ETF ticker + basis
    p = os.path.join(site_dir, "countrycyclesdata", "country_cycles.json")
    if os.path.exists(p):
        for rec in _records_from_json(_load_json(p)):
            now = rec["now"]
            if now.get("pos_v2") is None:
                continue
            readings.append(Reading("country_cycles", rec.get("ticker") or rec.get("id"),
                                    rec.get("ticker"), now.get("basis"),
                                    now.get("pos_v2"), now.get("phase_v2")))

    # 2. sector_cycles.json (US) + china — sector/basket records.
    #    A single-ETF record (kind sector/nasdaq/russell) is computed ON its ETF tape, so
    #    its ticker IS the cross-page tape identity.  A BASKET (kind="basket") is computed on
    #    its OWN constituent index — its `ticker`/`etf_proxy` (SMH, XLK…) is only a DISPLAY
    #    proxy, not the tape — so a basket is keyed by its unique `id` (it shares a tape with
    #    nothing else; keying it by the proxy would fabricate false cross-page collisions).
    for sub, page in (("sectordata", "sector_cycles"), ("chinasectordata", "sector_cycles_china")):
        p = os.path.join(site_dir, sub, "sector_cycles.json")
        if os.path.exists(p):
            for rec in _records_from_json(_load_json(p)):
                now = rec["now"]
                if now.get("pos_v2") is None:
                    continue
                is_basket = rec.get("kind") == "basket" or str(rec.get("id", "")).startswith("b-")
                if is_basket:
                    # own-index tape → key by the basket id; basis includes the id so it never
                    # collides with a sibling basket that merely shares a display proxy ETF.
                    tk = "BASKET:" + str(rec.get("id"))
                    basis = now.get("basis")
                else:
                    tk = rec.get("ticker") or rec.get("id")
                    basis = now.get("basis")
                readings.append(Reading(page, rec.get("id") or tk, tk, basis,
                                        now.get("pos_v2"), now.get("phase_v2")))

    # 3. markets_engine.js — ETF ticker + basis (pulled from country_cycles)
    p = os.path.join(site_dir, "marketsdata", "markets_engine.js")
    if os.path.exists(p):
        me = _load_js_object(p, "MARKETS_ENGINE")
        for mid, v in (me.get("markets") or {}).items():
            if not (v.get("has_engine") and v.get("pos_v2") is not None):
                continue
            readings.append(Reading("markets", mid, v.get("ticker"), v.get("basis"),
                                    v.get("pos_v2"), v.get("phase_v2")))

    # 4. cycle_engine.js — flagship MEASURED bands; keyed by the band's `ref` tape.
    #    record_basis is the declared basis label (etf_tr / index_px / futures_cont / spot …).
    p = os.path.join(site_dir, "cycledata", "cycle_engine.js")
    if os.path.exists(p):
        ce = _load_js_object(p, "CYCLE_ENGINE")
        for cid, cyc in (ce.get("cycles") or {}).items():
            for band in (cyc.get("bands") or []):
                now = band.get("now") or {}
                if now.get("pos_v2") is None:
                    continue
                # cycle.html tapes are indices/futures/spot — the `ref` (yahoo:SOXX,
                # intl:^N225, fred:DCOILWTICO) is the tape id; strip the source prefix
                # to a bare ticker for cross-page matching, and carry record_basis.
                ref = band.get("ref") or ""
                ticker = ref.split(":", 1)[-1] if ref else cid
                readings.append(Reading("cycle", cid, ticker, band.get("record_basis"),
                                        now.get("pos_v2"), now.get("phase_v2"), ref=ref))
    return readings


def check(site_dir: str) -> tuple[list, list, list]:
    """Return (same_tape_violations, cross_tape_declared, same_tape_ok_groups)."""
    readings = _collect(site_dir)
    by_tape: dict = defaultdict(list)
    for r in readings:
        by_tape[r.tape_key].append(r)

    same_tape_violations = []
    same_tape_ok = []
    for key, group in sorted(by_tape.items()):
        if len(group) < 2:
            continue
        # every reading in a same-tape group MUST agree on pos_v2 (within tol) + phase_v2.
        pos_vals = [g.pos_v2 for g in group]
        phases = {g.phase_v2 for g in group}
        pos_spread = max(pos_vals) - min(pos_vals)
        bad = pos_spread > POS_TOL or len(phases) > 1
        if bad:
            same_tape_violations.append((key, group, pos_spread, phases))
        else:
            same_tape_ok.append((key, group, pos_spread))

    # cross-tape DECLARED differences: same bare ticker across DIFFERENT bases.
    by_ticker: dict = defaultdict(set)
    ticker_readings: dict = defaultdict(list)
    for r in readings:
        by_ticker[r.ticker].add(r.basis)
        ticker_readings[r.ticker].append(r)
    cross_tape_declared = []
    for tk, bases in sorted(by_ticker.items()):
        if len(bases) > 1:
            # same conceptual ticker on ≥2 declared bases — allowed, but every reading
            # MUST carry a non-empty basis label (that is what "declared" means).
            group = ticker_readings[tk]
            undeclared = [g for g in group if not g.basis]
            cross_tape_declared.append((tk, sorted(bases), group, undeclared))
    return same_tape_violations, cross_tape_declared, same_tape_ok


def _fmt_reading(r: Reading) -> str:
    b = r.basis or "∅(UNDECLARED)"
    ref = f" ref={r.ref}" if r.ref else ""
    return f"{r.page}:{r.label} [{r.ticker}/{b}]{ref} pos_v2={r.pos_v2} phase_v2={r.phase_v2}"


def write_report(path: str, site_dir: str, same_tape_violations, cross_tape_declared, same_tape_ok) -> None:
    lines = []
    lines.append("# W3.6 — cross-page cycle-consistency report (R3-M3)\n")
    lines.append(f"Generated by `scripts/check_cycle_consistency.py` over `{site_dir}`.  ")
    lines.append(f"Same-tape tolerance: **±{POS_TOL} pts** on pos_v2 (phase_v2 must match exactly).\n")

    status = "PASS ✅" if not same_tape_violations else "FAIL ❌"
    lines.append(f"**Status: {status}** — "
                 f"{len(same_tape_violations)} same-tape violation(s), "
                 f"{len(same_tape_ok)} same-tape group(s) agree, "
                 f"{len(cross_tape_declared)} declared cross-tape difference(s).\n")

    lines.append("## Same-tape agreement (same ticker + same basis → must agree)\n")
    if same_tape_violations:
        lines.append("### ❌ VIOLATIONS\n")
        for key, group, spread, phases in same_tape_violations:
            lines.append(f"- **{key[0]}/{key[1] or '∅'}** — pos spread {spread:.2f}, phases {sorted(phases)}:")
            for g in group:
                lines.append(f"    - {_fmt_reading(g)}")
    else:
        lines.append("No same-tape violations. Every instrument sharing a (ticker, basis) tape "
                     "agrees on pos_v2 (±tol) and phase_v2 across all pages that render it.\n")
    if same_tape_ok:
        lines.append("\n<details><summary>Same-tape groups that agree "
                     f"({len(same_tape_ok)})</summary>\n")
        for key, group, spread in same_tape_ok:
            pages = ", ".join(sorted({g.page for g in group}))
            lines.append(f"- {key[0]}/{key[1] or '∅'} — {pages} — "
                         f"pos≈{group[0].pos_v2} · {group[0].phase_v2} (spread {spread:.2f})")
        lines.append("</details>\n")

    lines.append("\n## Declared cross-tape differences (same instrument, different tape → labeled)\n")
    lines.append("These are the same conceptual instrument computed on *different tapes* "
                 "(e.g. a local-currency index vs its USD ETF, or a futures contract vs an ETF). "
                 "They are allowed to differ, but every reading must carry a declared basis label.\n")
    any_undeclared = False
    for tk, bases, group, undeclared in cross_tape_declared:
        flag = " — ⚠️ UNDECLARED basis on some readings!" if undeclared else ""
        if undeclared:
            any_undeclared = True
        lines.append(f"- **{tk}** across bases {bases}{flag}:")
        for g in group:
            lines.append(f"    - {_fmt_reading(g)}")
    if not cross_tape_declared:
        lines.append("_(none — no instrument appears under more than one basis.)_\n")
    if any_undeclared:
        lines.append("\n> ⚠️ At least one cross-tape reading lacks a basis label. A cross-tape "
                     "difference is only honest if it is *declared* — those readings must stamp a basis.\n")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    report_path = None
    if "--report" in argv:
        i = argv.index("--report")
        report_path = argv[i + 1]
        del argv[i:i + 2]
    site_dir = argv[0] if argv else "site"

    same_tape_violations, cross_tape_declared, same_tape_ok = check(site_dir)

    if report_path:
        os.makedirs(os.path.dirname(report_path) or ".", exist_ok=True)
        write_report(report_path, site_dir, same_tape_violations, cross_tape_declared, same_tape_ok)
        print(f"cycle-consistency report → {report_path}")

    # A cross-tape difference with an UNDECLARED basis is also a failure (the label is
    # the whole point of R3-M3 — an unlabeled cross-tape difference is silent drift).
    undeclared_cross = [c for c in cross_tape_declared if c[3]]

    if same_tape_violations or undeclared_cross:
        print(f"CYCLE-CONSISTENCY: FAIL — {len(same_tape_violations)} same-tape "
              f"violation(s), {len(undeclared_cross)} undeclared cross-tape difference(s).",
              file=sys.stderr)
        for key, group, spread, phases in same_tape_violations:
            print(f"  same-tape {key}: pos spread {spread:.2f}, phases {sorted(phases)}", file=sys.stderr)
            for g in group:
                print(f"      {_fmt_reading(g)}", file=sys.stderr)
        for tk, bases, group, undeclared in undeclared_cross:
            print(f"  undeclared cross-tape {tk} bases={bases}:", file=sys.stderr)
            for g in undeclared:
                print(f"      {_fmt_reading(g)}", file=sys.stderr)
        return 1

    print(f"CYCLE-CONSISTENCY: PASS — {len(same_tape_ok)} same-tape group(s) agree, "
          f"{len(cross_tape_declared)} declared cross-tape difference(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
