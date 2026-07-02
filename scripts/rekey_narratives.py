"""THE turn-epoch re-key migrator — Cycle Intelligence Masterplan W2.1 (D1-owned).

One migrator, one re-key scheme (ruling A5): given an engine's OLD turn set + OLD epoch
and its NEW turn set + NEW epoch, re-key every narrative / cycle_dna leg binding via
`engine.cycle_ontology.match_turns` (half-cycle-scaled tolerance) and write
`data/<engine>/narratives.<new_epoch>.json` (+ `cycle_dna.<new_epoch>.json` where a DNA
file exists) with, per leg:

    - a `status` ∈ {exact, shifted, orphaned, new},
    - a `prev_key` chain back to the hand-researched original,
    - the narrative body carried verbatim on exact/shifted, retained-but-detached on
      orphaned (moved to a top-level `"orphaned": {...}` section — NEVER plotted),
    - `new` turns get an empty research slot.

The migrator is:
    * idempotent — re-running against the same (old, new) turn sets reproduces the file;
    * `--dry-run`-able — computes + prints the report, writes nothing;
    * self-refusing — aborts if new_epoch == old_epoch (nothing to migrate).

The JS-consumable leg KEY FORM is preserved (the shared templates/sector_cycles.js looks
up `nmap[turn.date] || nmap[turn.t]`) — legs stay keyed by the NEW turn's raw date/month
so the page finds them with zero JS change.  The canonical month-quantized `turn_id`
(series:kind:YYYY-MM) + prev_key travel *inside* each leg as metadata.

Ruling-A5 note: D1 §3.3 says `narratives.<epoch>.json` keyed by turn_id; D4 §3.3 said
`narratives.v2.json` keyed by `ticker__kind__date` with a prev_key chain.  A5 arbitrates:
D1 owns identity (turn_id = series:kind:YYYY-MM, ONE turn_epoch, file `narratives.<epoch>.json`).
This migrator follows A5's file/id scheme; it keeps the D4 prev_key-chain + orphan-quarantine
CONCEPT but expresses keys in the A5 form.  The JS-lookup key form is a third, orthogonal
concern (the site reads raw dates) — preserved independently so loading is byte-identical
today (W2.1 acceptance).

Usage (synthetic / real):
    python -m scripts.rekey_narratives --engine sector_cycles \\
        --old-epoch tr_v0 --new-epoch price_1a2b3c4d [--dry-run]

    # or drive it programmatically with explicit turn sets (see rekey_engine()).

Additive & never-fatal at *build* time — this script is a one-time migration tool, not a
render-path step; the builders' loaders (extended in this same wave) resolve the epoch file
if present and fall back to the legacy file otherwise.
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import cycle_ontology as onto  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("rekey_narratives")

# ─────────────────────────────────────────────────────────────────────────────
# Engine registry — where each engine's narratives / dna / data live, and the
# CURRENT (legacy) epoch parameters used to reproduce its OLD turn set.
# ─────────────────────────────────────────────────────────────────────────────
ENGINES: dict[str, dict] = {
    "sector_cycles": {
        "dir":       "sector_cycles",
        "has_dna":   True,
        "basis":     "close_tr",
        "zz_pct":    14.0,
    },
    "country_cycles": {
        "dir":       "country_cycles",
        "has_dna":   True,
        "basis":     "close_tr",
        "zz_pct":    14.0,
    },
    "china_sector_cycles": {
        "dir":       "china_sector_cycles",
        "has_dna":   True,
        "basis":     "close_price",   # Shenwan L1 already price-basis (D4-N1) — but the
                                      # re-key machinery is engine-agnostic; a threshold
                                      # review still bumps the epoch.
        "zz_pct":    18.0,
    },
}

# Half-cycle-scaled tolerance: a slow (housing-scale) turn tolerates a wider date match
# than a 2-week whipsaw.  We scale a base tolerance by the series' median half-cycle in
# years, clamped to a sane band.  (D4 §3.3 asks for exactly this; D1 §3.3 fixes the base
# at 60d.)
_BASE_TOL_DAYS = 60
_MIN_TOL_DAYS = 30
_MAX_TOL_DAYS = 210
_EXACT_MONTH = True  # "exact" == same YYYY-MM (month-quantized turn_id equality)


# ─────────────────────────────────────────────────────────────────────────────
# Tolerance
# ─────────────────────────────────────────────────────────────────────────────
def half_cycle_tol_days(new_turns: list[dict], base: int = _BASE_TOL_DAYS) -> int:
    """Half-cycle-scaled match tolerance in calendar days.

    tol = clamp( base * median_half_cycle_years , MIN, MAX ).
    A 6-month intermediate cycle → ~base; an 18-year housing frame → widened toward MAX.
    Falls back to `base` when there aren't enough confirmed turns to estimate spacing.
    """
    xs = sorted(t.get("x") for t in new_turns
                if not t.get("provisional") and isinstance(t.get("x"), (int, float)))
    if len(xs) < 3:
        return base
    halves = [xs[i] - xs[i - 1] for i in range(1, len(xs))]
    halves = [h for h in halves if h > 0]
    if not halves:
        return base
    halves.sort()
    med = halves[len(halves) // 2]
    tol = int(round(base * max(1.0, med / 0.5)))   # 0.5yr half-cycle == base
    return max(_MIN_TOL_DAYS, min(_MAX_TOL_DAYS, tol))


# ─────────────────────────────────────────────────────────────────────────────
# Turn helpers
# ─────────────────────────────────────────────────────────────────────────────
def _turn_by_id(new_turns: list[dict]) -> dict[str, dict]:
    return {t["turn_id"]: t for t in new_turns if "turn_id" in t}


def _doc_has_turn_legs(doc: dict) -> bool:
    """True iff any series in the doc carries a non-empty turn-keyed `legs` dict.

    narratives.json → True (legs keyed by turn date).  cycle_dna.json → False (it is a
    per-series profile: summary/drivers/analog, NO legs) → epoch-invariant."""
    for section in ("sectors", "baskets"):
        for srec in (doc.get(section, {}) or {}).values():
            if isinstance(srec, dict) and isinstance(srec.get("legs"), dict) and srec["legs"]:
                return True
    return False


def _leg_key_for_turn(t: dict) -> str:
    """The JS-consumable leg key for a NEW turn — the raw date the site looks up
    (`nmap[a.date] || nmap[a.t]`).  We key by full date when present, else month."""
    return t.get("date") or t.get("t") or t["turn_id"].rsplit(":", 1)[-1]


def _month_of_key(k: str) -> str | None:
    """YYYY-MM of a leg key ('YYYY-MM-DD' | 'YYYY-MM' | 'series:kind:YYYY-MM')."""
    try:
        if len(k) >= 7 and k[4] == "-" and k[:4].isdigit():
            return k[:7]
        parts = k.rsplit(":", 1)
        if len(parts) == 2 and len(parts[1]) >= 7 and parts[1][4] == "-":
            return parts[1][:7]
    except (IndexError, ValueError):
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Core: re-key ONE series' leg dict
# ─────────────────────────────────────────────────────────────────────────────
def rekey_series_legs(
    old_legs: dict[str, Any],
    new_turns: list[dict],
    *,
    series_id: str,
    tol_days: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict]]:
    """Re-key one series' `legs` dict from old turn-keys to new turn-keys.

    Returns (new_legs, orphaned_legs, per_leg_report).

    new_legs   : {new_leg_key: {<narrative fields>, "status", "turn_id", "prev_key",
                                "rekey_shift_days"?}}  — plotted.
    orphaned   : {old_key: {<narrative fields>, "status":"orphaned", "prev_key", "reason"}}
                 — retained but NEVER plotted (not returned to the page's legs map).
    report     : list of {old_key, new_key, turn_id, status, delta_days}.
    """
    match = onto.match_turns(old_legs, new_turns, tol_days=tol_days)
    by_id = _turn_by_id(new_turns)

    new_legs: dict[str, Any] = {}
    orphaned: dict[str, Any] = {}
    report: list[dict] = []

    for old_key, body in old_legs.items():
        m = match.get(old_key, {"status": "orphaned", "new_turn_id": None, "delta_days": None})
        status = m["status"]
        new_id = m.get("new_turn_id")

        if status in ("exact", "shifted") and new_id and new_id in by_id:
            turn = by_id[new_id]
            new_key = _leg_key_for_turn(turn)
            # Ruling A5: "exact" == same month-quantized turn (YYYY-MM equal).  match_turns
            # reports string-equality of turn_id vs old_key; because legacy keys are raw
            # dates (never turn_ids), we re-derive exact-vs-shifted on MONTH equality here.
            old_month = _month_of_key(old_key)
            new_month = _month_of_key(turn.get("t") or turn.get("date") or new_key)
            status = "exact" if (old_month and old_month == new_month) else "shifted"
            carried = copy.deepcopy(body) if isinstance(body, dict) else {"body": body}
            carried["status"] = status
            carried["turn_id"] = new_id
            carried["prev_key"] = old_key
            # prev_key chain: preserve any inherited chain from a prior epoch
            prior_chain = body.get("prev_key_chain") if isinstance(body, dict) else None
            chain = list(prior_chain) if isinstance(prior_chain, list) else []
            chain.append(old_key)
            carried["prev_key_chain"] = chain
            if status == "shifted":
                carried["rekey_shift_days"] = m.get("delta_days")
            # collision: two old keys land on one new turn → keep first, orphan the rest
            if new_key in new_legs:
                orphaned[old_key] = _mk_orphan(body, old_key,
                                               reason=f"collided onto {new_key} (already bound)")
                report.append({"old_key": old_key, "new_key": None, "turn_id": new_id,
                               "status": "orphaned", "delta_days": m.get("delta_days")})
                continue
            new_legs[new_key] = carried
            report.append({"old_key": old_key, "new_key": new_key, "turn_id": new_id,
                           "status": status, "delta_days": m.get("delta_days")})
        else:
            # orphaned — retained, detached, never plotted
            orphaned[old_key] = _mk_orphan(body, old_key, reason=m.get("reason", "no match within tolerance"))
            report.append({"old_key": old_key, "new_key": None, "turn_id": None,
                           "status": "orphaned", "delta_days": None})

    # NEW turns with no prior binding → empty research slot (plotted key exists, no prose)
    bound_ids = {v.get("turn_id") for v in new_legs.values()}
    for turn in new_turns:
        if turn.get("provisional"):
            continue
        tid = turn.get("turn_id")
        if tid in bound_ids:
            continue
        new_key = _leg_key_for_turn(turn)
        if new_key in new_legs:
            continue
        new_legs[new_key] = {"status": "new", "turn_id": tid, "prev_key": None,
                             "prev_key_chain": []}
        report.append({"old_key": None, "new_key": new_key, "turn_id": tid,
                       "status": "new", "delta_days": 0})

    return new_legs, orphaned, report


def _mk_orphan(body: Any, old_key: str, *, reason: str) -> dict:
    o = copy.deepcopy(body) if isinstance(body, dict) else {"body": body}
    o["status"] = "orphaned"
    o["prev_key"] = old_key
    prior_chain = body.get("prev_key_chain") if isinstance(body, dict) else None
    chain = list(prior_chain) if isinstance(prior_chain, list) else []
    chain.append(old_key)
    o["prev_key_chain"] = chain
    o["reason"] = reason
    return o


# ─────────────────────────────────────────────────────────────────────────────
# Core: re-key a whole narratives document (sectors + baskets)
# ─────────────────────────────────────────────────────────────────────────────
def rekey_document(
    doc: dict,
    new_turns_by_series: dict[str, list[dict]],
    *,
    old_epoch: str,
    new_epoch: str,
    base_tol_days: int = _BASE_TOL_DAYS,
) -> tuple[dict, dict]:
    """Re-key an entire narratives/cycle_dna document.

    `new_turns_by_series` maps the document's series id (sector ticker.lower(), Shenwan
    code, or basket "b-"+key WITHOUT the "b-" — see note) to that series' fresh turn list.

    NOTE on basket keying: the document nests baskets under `doc["baskets"][key]`; the
    caller supplies turns under the same `key` (no "b-" prefix — that prefix is a builder
    concern, not a data-file one).

    Returns (new_doc, orphaned_doc).

    A doc WITHOUT turn-keyed legs (e.g. cycle_dna.json is a per-series *profile* —
    summary/drivers/analog, NO `legs` dict) is epoch-invariant: it carries verbatim into
    the new epoch (only the epoch stamp changes).  Re-keying it by turn would fabricate
    meaningless "new" slots, so we short-circuit.
    """
    new_doc: dict = {
        "epoch":            new_epoch,
        "prev_epoch":       old_epoch,
        "detector_version": onto.DETECTOR_VERSION,
        "rekeyed_from":     doc.get("version"),
        "note":             doc.get("note", ""),
        "sectors":          {},
        "baskets":          {},
    }
    orphaned_doc: dict = {"epoch": new_epoch, "prev_epoch": old_epoch,
                          "sectors": {}, "baskets": {}}
    stats = {"exact": 0, "shifted": 0, "orphaned": 0, "new": 0,
             "series": 0, "worst_shifts": [], "legless_carried": 0}

    # Epoch-invariant (no turn-keyed legs) → carry verbatim, re-stamp only.
    if not _doc_has_turn_legs(doc):
        for section in ("sectors", "baskets"):
            for sid, srec in (doc.get(section, {}) or {}).items():
                new_doc[section][sid] = copy.deepcopy(srec)
                stats["series"] += 1
                stats["legless_carried"] += 1
        new_doc["_rekey_stats"] = {k: v for k, v in stats.items() if k != "worst_shifts"}
        new_doc["_rekey_stats"]["worst_shifts"] = []
        new_doc["_rekey_stats"]["turn_keyed"] = False
        return new_doc, orphaned_doc

    for section in ("sectors", "baskets"):
        for sid, srec in (doc.get(section, {}) or {}).items():
            new_turns = new_turns_by_series.get(sid, [])
            new_srec = copy.deepcopy(srec) if isinstance(srec, dict) else {}
            old_legs = (srec or {}).get("legs", {}) if isinstance(srec, dict) else {}
            tol = half_cycle_tol_days(new_turns, base=base_tol_days)
            new_legs, orphaned, report = rekey_series_legs(
                old_legs, new_turns, series_id=sid, tol_days=tol)

            new_srec["legs"] = new_legs
            new_doc[section][sid] = new_srec
            if orphaned:
                orphaned_doc[section][sid] = {"legs": orphaned}

            stats["series"] += 1
            for r in report:
                stats[r["status"]] = stats.get(r["status"], 0) + 1
                if r["status"] == "shifted" and r.get("delta_days") is not None:
                    stats["worst_shifts"].append((abs(r["delta_days"]), sid, r["old_key"], r["new_key"]))

    stats["worst_shifts"].sort(reverse=True)
    stats["worst_shifts"] = stats["worst_shifts"][:10]
    new_doc["_rekey_stats"] = {k: v for k, v in stats.items() if k != "worst_shifts"}
    new_doc["_rekey_stats"]["worst_shifts"] = [
        {"delta_days": d, "series": s, "old_key": ok, "new_key": nk}
        for (d, s, ok, nk) in stats["worst_shifts"]
    ]
    new_doc["_rekey_stats"]["turn_keyed"] = True
    return new_doc, orphaned_doc


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────
def format_report(engine: str, old_epoch: str, new_epoch: str,
                  narr_stats: dict, dna_stats: dict | None) -> str:
    lines = [
        "═" * 72,
        f"  REKEY REPORT — {engine}   {old_epoch}  →  {new_epoch}",
        "═" * 72,
    ]
    for label, stats in [("narratives", narr_stats), ("cycle_dna", dna_stats)]:
        if stats is None:
            continue
        if stats.get("turn_keyed") is False:
            lines.append(f"  [{label}]  {stats.get('series', 0)} series — "
                         f"epoch-invariant profile (no turn legs), carried verbatim")
            continue
        lines.append(f"  [{label}]  {stats.get('series', 0)} series")
        for st in ("exact", "shifted", "orphaned", "new"):
            lines.append(f"      {st:<9} {stats.get(st, 0):>5}")
        ws = stats.get("worst_shifts", [])
        if ws:
            lines.append("      worst shifts (days):")
            for w in ws[:5]:
                lines.append(f"         {w['delta_days']:>4}d  {w['series']}  {w['old_key']} → {w['new_key']}")
    lines.append("═" * 72)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────
def rekey_engine(
    engine: str,
    new_turns_by_series: dict[str, list[dict]],
    *,
    old_epoch: str,
    new_epoch: str,
    dna_new_turns_by_series: dict[str, list[dict]] | None = None,
    root: Path | None = None,
    dry_run: bool = False,
    base_tol_days: int = _BASE_TOL_DAYS,
) -> dict:
    """Re-key one engine's narratives (+ cycle_dna) into the new epoch.

    Refuses to run if new_epoch == old_epoch.  Returns a result dict:
        {engine, old_epoch, new_epoch, narratives_path, dna_path, report(str),
         narr_stats, dna_stats, wrote(bool)}.

    Idempotency: the write is a pure function of (source doc, new turn sets, epochs).
    Re-running with the same inputs re-produces byte-identical output.
    """
    if new_epoch == old_epoch:
        raise ValueError(
            f"rekey_narratives: new_epoch == old_epoch ({new_epoch!r}); nothing to migrate. "
            "An epoch bump requires a change in basis, ZigZag params, or detector version.")

    if engine not in ENGINES:
        raise ValueError(f"rekey_narratives: unknown engine {engine!r}; expected one of {list(ENGINES)}")
    spec = ENGINES[engine]
    root = root or config.ROOT
    ddir = root / "data" / spec["dir"]

    result: dict = {"engine": engine, "old_epoch": old_epoch, "new_epoch": new_epoch,
                    "wrote": False, "narratives_path": None, "dna_path": None,
                    "narr_stats": None, "dna_stats": None}

    # ── narratives ──────────────────────────────────────────────────────────
    narr_src = ddir / "narratives.json"
    if narr_src.exists():
        doc = json.loads(narr_src.read_text(encoding="utf-8"))
        new_doc, orphaned_doc = rekey_document(
            doc, new_turns_by_series, old_epoch=old_epoch, new_epoch=new_epoch,
            base_tol_days=base_tol_days)
        result["narr_stats"] = new_doc["_rekey_stats"]
        out = ddir / f"narratives.{new_epoch}.json"
        orph = ddir / f"narratives.{new_epoch}.orphans.json"
        result["narratives_path"] = str(out)
        if not dry_run:
            out.write_text(json.dumps(new_doc, ensure_ascii=False, indent=2, sort_keys=True),
                           encoding="utf-8")
            orphaned_doc["_note"] = "Orphaned narrative legs — retained for review, NEVER plotted."
            orph.write_text(json.dumps(orphaned_doc, ensure_ascii=False, indent=2, sort_keys=True),
                            encoding="utf-8")
            result["wrote"] = True
    else:
        log.warning("%s: no narratives.json — nothing to re-key", engine)

    # ── cycle_dna (same re-key machinery; DNA legs keyed the same way) ───────
    if spec.get("has_dna"):
        dna_src = ddir / "cycle_dna.json"
        if dna_src.exists():
            dna_doc = json.loads(dna_src.read_text(encoding="utf-8"))
            dna_turns = dna_new_turns_by_series or new_turns_by_series
            new_dna, orph_dna = rekey_document(
                dna_doc, dna_turns, old_epoch=old_epoch, new_epoch=new_epoch,
                base_tol_days=base_tol_days)
            result["dna_stats"] = new_dna["_rekey_stats"]
            out = ddir / f"cycle_dna.{new_epoch}.json"
            orph = ddir / f"cycle_dna.{new_epoch}.orphans.json"
            result["dna_path"] = str(out)
            if not dry_run:
                out.write_text(json.dumps(new_dna, ensure_ascii=False, indent=2, sort_keys=True),
                               encoding="utf-8")
                orph_dna["_note"] = "Orphaned cycle_dna legs — retained for review, NEVER plotted."
                orph.write_text(json.dumps(orph_dna, ensure_ascii=False, indent=2, sort_keys=True),
                                encoding="utf-8")

    result["report"] = format_report(engine, old_epoch, new_epoch,
                                     result["narr_stats"] or {}, result["dna_stats"])
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Real-turn-set computation (compute NEW turns from the live engine at the new epoch)
# ─────────────────────────────────────────────────────────────────────────────
def compute_new_turns(engine: str, basis: str, zz_pct: float,
                     root: Path | None = None) -> dict[str, list[dict]]:
    """Compute the NEW turn set for every series in an engine, at the given basis+pct.

    Reads the engine's current `compute()` output and re-runs the ontology detector on
    each series' price panel.  Best-effort: a series that can't be recomputed yields an
    empty turn list (its legs will all orphan, warned in the report) — the never-fatal
    house pattern.  For W2.1 the migrator is proven on SYNTHETIC turn sets (tests); this
    path exists so W2.2 can drive a real basis flip through the same code.
    """
    # NOTE: the actual per-series price panels live behind each engine's private loaders.
    # W2.1 does not perform a real flip (that is W2.2); this helper is intentionally thin
    # and delegates to the engine's own turn output when available.
    out: dict[str, list[dict]] = {}
    try:
        if engine == "sector_cycles":
            from engine import sector_cycles as eng
        elif engine == "country_cycles":
            from engine import country_cycles as eng
        elif engine == "china_sector_cycles":
            from engine import china_sector_cycles as eng
        else:
            return out
        data = eng.compute()
    except Exception as e:  # noqa: BLE001
        log.warning("%s: compute() failed (%s) — no new turns; all legs will orphan", engine, e)
        return out
    if not data:
        return out

    def _emit(sid: str, rec: dict) -> None:
        if not isinstance(rec, dict):
            return
        turns = rec.get("turns") or []
        cleaned = []
        for t in turns:
            if not isinstance(t, dict) or not t.get("date"):
                continue
            tid = t.get("turn_id")
            if not tid:
                # engine record predates turn_id stamping (kernel-integration wave) —
                # synthesize the canonical month-quantized id: series:kind:YYYY-MM.
                kind = t.get("k") or "peak"
                ym = t.get("t") or str(t["date"])[:7]
                tid = f"{sid}:{kind}:{ym}"
            cleaned.append({**t, "turn_id": tid})
        if cleaned:
            out[sid] = cleaned

    for section in ("sectors", "baskets"):
        sec = data.get(section)
        # The narratives doc keys baskets WITHOUT the builder's "b-" prefix; the engine
        # records carry it (id="b-ai_infra").  Strip it so turn ids align with the doc.
        strip_bprefix = (section == "baskets")
        if isinstance(sec, dict):
            for sid, rec in sec.items():
                sid = sid[2:] if strip_bprefix and sid.startswith("b-") else sid
                _emit(sid, rec)
        elif isinstance(sec, list):       # engine returns a LIST of records with an "id"
            for rec in sec:
                if isinstance(rec, dict) and rec.get("id"):
                    sid = rec["id"]
                    sid = sid[2:] if strip_bprefix and sid.startswith("b-") else sid
                    _emit(sid, rec)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Turn-epoch narrative re-key migrator (W2.1)")
    ap.add_argument("--engine", required=True, choices=sorted(ENGINES),
                    help="engine whose narratives to re-key")
    ap.add_argument("--old-epoch", default=onto.LEGACY_TR_EPOCH,
                    help=f"epoch tag of the source narratives.json (default {onto.LEGACY_TR_EPOCH})")
    ap.add_argument("--new-epoch", default=None,
                    help="target epoch tag; if omitted, computed from the engine's declared basis+pct")
    ap.add_argument("--dry-run", action="store_true", help="compute + report, write nothing")
    ap.add_argument("--base-tol-days", type=int, default=_BASE_TOL_DAYS)
    args = ap.parse_args(argv)

    spec = ENGINES[args.engine]
    new_epoch = args.new_epoch or onto.turn_epoch(spec["basis"], spec["zz_pct"])

    # Refuse a no-op migration BEFORE running the (slow) engine — same-epoch bumps nothing.
    if new_epoch == args.old_epoch:
        log.error("rekey_narratives: new_epoch == old_epoch (%r); nothing to migrate. "
                  "An epoch bump requires a change in basis, ZigZag params, or detector version.",
                  new_epoch)
        return 2

    new_turns = compute_new_turns(args.engine, spec["basis"], spec["zz_pct"])
    try:
        res = rekey_engine(
            args.engine, new_turns,
            old_epoch=args.old_epoch, new_epoch=new_epoch,
            dry_run=args.dry_run, base_tol_days=args.base_tol_days)
    except ValueError as e:
        log.error("%s", e)
        return 2

    print(res["report"])
    if args.dry_run:
        print("  [DRY RUN] no files written.")
    else:
        print(f"  wrote {res['narratives_path']}")
        if res.get("dna_path"):
            print(f"  wrote {res['dna_path']}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
