"""Deterministic DE-ESCALATION-ONLY signal governor for the Intelligence Hub.

Closes the measure→act loop the hub half-built. Every desk track record in this repo is,
by long-standing doctrine, *"CONTEXT-ONLY — never fed into a score/size/allocation."* That
left a hole: `data/radar/radar_ic.json` appeared to measure the radar leading signal as
inverted (pooled IC ≈ −0.33 over ~2k matured obs — later shown by the 2026-08-05 forensic
audit to be mostly unsigned-pooling + overlap + era artifacts; the signed, overlap-robust
read is null), yet the hub keeps ranking on it. Acting only on the rigorous HAC path below
is exactly what protected this governor from that artifact. This module is the authorized,
scoped exception (operator 2026-07-21, "arm live, de-escalation-only, gated"):

  * DE-ESCALATION ONLY — every signal's ``trust`` ∈ [TRUST_FLOOR, 1.0]. The hub applies it as a
    DOWNWARD scale on that signal's contribution to ``opportunity``. The governor can only
    REMOVE influence from a proven-mis-firing signal; it can never originate or boost one.
    ``load_trust`` re-clamps to ≤ 1.0 on read, so even a tampered file cannot produce a boost.
  * GATED / pre-registered / arm-by-evidence — a signal is demoted only when
    ``n_matured ≥ MIN_N`` AND a RIGOROUS daily-HAC t (Newey-West lag=horizon — the overlap-robust
    path, NEVER the naive pooled Spearman that ignores the h-day window autocorrelation) is
    significant (|t| ≥ T_SIG) with the WRONG sign (IC ≤ IC_DEAD). Until then trust = 1.0.
  * AUDITED — every decision → data/hub/signal_governor.json with the evidence behind it.
  * DEGRADE-NEVER-RAISE — missing/corrupt track record ⇒ trust 1.0 (identity); the hub is then
    byte-identical to ungoverned. An absent governor file is a valid, expected state.

Nothing here sizes a position. It only de-escalates a proven-bad signal's rank influence.

Run:  python -m engine.signal_governor            # recompute + persist the trust map
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)

SCHEMA = "signal_governor.v1"

# Per-region track-record paths (the governor engine + gate are shared; only the paths differ).
# A region with no matured track record ⇒ all trust 1.0 (dormant, degrade-safe). CN mirrors the
# US structure — its radar_ic accrues once china_radar_ledger matures; until then CN is dormant.
_REGIONS = {
    "us": {"radar": ("data", "radar", "radar_ic.json"),
           # the copy the PAGE actually ships. engine-render commits site/ but not data/, so the
           # data/ copy can lag the published one by days; read BOTH, act on the freshest (D2).
           "radar_site": ("site", "basketdata", "radar_ic.json"),
           "hub":   ("data", "hub", "track_record.json"),
           "out":   ("data", "hub", "signal_governor.json")},
    "cn": {"radar": ("data", "china_hub", "radar_ic.json"),
           # no published CN radar_ic copy exists yet — one path, same freshness contract.
           "hub":   ("data", "china_hub", "track_record.json"),
           "out":   ("data", "china_hub", "signal_governor.json")},
}
# Back-compat module-level aliases (US) — some tests/consumers reference these directly.
_OUT = _REGIONS["us"]["out"]
_RADAR_IC = _REGIONS["us"]["radar"]
_RADAR_IC_SITE = _REGIONS["us"]["radar_site"]
_HUB_TRACK = _REGIONS["us"]["hub"]

# Age (calendar days) at which the governor's radar input is called STALE and annotated. The
# governor degrades-never-raises, so a stale or missing input silently leaves every trust at
# 1.0 — indistinguishable from "measured healthy". That silence is the defect: the read must
# fail LOUD (line-start ::warning) while still refusing to disarm anything.
STALE_INPUT_DAYS = 2

# ── PRE-REGISTERED GATE (committed constants = the pre-registration) ───────────────────────
MIN_N = 150            # matured observations a signal needs before it can be demoted at all
T_SIG = 2.0            # |Newey-West HAC t| significance bar
IC_DEAD = -0.03        # signed daily-HAC IC must be at least this negative (wrong sign) to demote
TRUST_FLOOR = 0.25     # floor — de-escalate influence, never delete a signal outright
SLOPE = 1.5            # severity: trust = clamp(1 + SLOPE·ic, FLOOR, 1) for ic < 0
MIN_HAC_DAYS = 6       # ic_summary needs ≥6 dated cross-sectional ICs for a valid HAC t-stat

# Signals this governor can currently read a matured track record for. Others join as their
# per-signal track records accrue (hub_track_record forward-grades each feeder going forward).
_SIGNALS = ("radar", "hub")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _trust_from_ic(ic: float | None) -> float:
    """De-escalation-only trust from a signed daily-HAC IC. ic ≥ 0 (right sign / healthy) ⇒ 1.0;
    ic < 0 ⇒ a floored downward scale proportional to how inverted the signal is."""
    if ic is None or ic >= 0:
        return 1.0
    return round(_clamp(1.0 + SLOPE * ic, TRUST_FLOOR, 1.0), 3)


def _read_json(root: Path, parts) -> dict | None:
    try:
        return json.loads(root.joinpath(*parts).read_text())
    except Exception:  # noqa: BLE001 — absent/corrupt ⇒ no reading (identity downstream)
        return None


def _hz_int(h) -> int:
    try:
        return int(h)
    except (TypeError, ValueError):
        return 0


def _needed_days(horizon: int) -> int:
    """A per-date IC series with an h-step forward window overlaps for ~h steps, so ic_summary
    sets the Newey-West lag to h. A HAC t with lag ≥ n_days is DEGENERATE (the long-run variance
    can't be estimated) and its significance is an artifact. Require n_days ≥ the lag (=horizon)
    — never fewer — so we only ever act on a valid, non-degenerate HAC."""
    return max(MIN_HAC_DAYS, horizon)


def _pick_reading(by_horizon: dict, ic_block_key: str) -> dict | None:
    """Gate on the LONGEST horizon that carries a VALID, non-degenerate rigorous HAC IC —
    i.e. n_days ≥ _needed_days(horizon). This is the decision-relevant horizon AND it refuses
    the trap that just bit on live data: radar's 21d HAC reads t≈−8 but has only 11 daily ICs
    against a lag-21 window (lag > n ⇒ degenerate/overstated), while its clean 10d HAC (19 ICs,
    lag 10) reads t≈−0.9, NOT significant. Acting on the degenerate 21d would be curve-fitting
    ~1.5 independent overlapping windows. Picking one horizon deterministically also avoids
    multiple-testing. ``ic_block_key`` names the per-horizon HAC sub-dict {mean_ic, t_hac, n}
    (radar: 'ic_daily_hac'; hub: 'opportunity_ic_daily'). n_matured ≥ MIN_N is left to ``_gate``."""
    best = None
    for h, blk in (by_horizon or {}).items():
        if not isinstance(blk, dict):
            continue
        hac = blk.get(ic_block_key) or {}
        t, ic = hac.get("t_hac"), hac.get("mean_ic")
        n_days = hac.get("n", hac.get("n_days", 0)) or 0
        n_matured = blk.get("n_matured")
        if t is None or ic is None or n_matured is None or n_days < _needed_days(_hz_int(h)):
            continue
        cand = {"n_matured": int(n_matured), "ic": float(ic), "t_hac": float(t),
                "horizon": str(h), "n_days": int(n_days)}
        if best is None or _hz_int(h) > _hz_int(best["horizon"]):
            best = cand
    return best


def _coverage(by_horizon: dict, ic_block_key: str) -> dict | None:
    """The most-matured horizon and its distance-to-a-valid-HAC — for an honest 'measuring'
    note when no horizon is gradeable yet (e.g. radar 21d: have 11 daily ICs, need ≥21)."""
    best = None
    for h, blk in (by_horizon or {}).items():
        if not isinstance(blk, dict):
            continue
        n_matured = blk.get("n_matured") or 0
        n_days = ((blk.get(ic_block_key) or {}).get("n")
                  or (blk.get(ic_block_key) or {}).get("n_days") or 0)
        if best is None or n_matured > best["n_matured"]:
            best = {"horizon": str(h), "n_matured": int(n_matured), "n_days": int(n_days),
                    "need_days": _needed_days(_hz_int(h))}
    return best


def _as_of_date(payload: dict | None) -> date | None:
    """The artifact's own as_of, as a date. None ⇒ unparseable/absent (age unknown)."""
    raw = (payload or {}).get("as_of") or (payload or {}).get("asof")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)[:10]).date()
    except Exception:  # noqa: BLE001
        return None


def _freshest(root: Path, region: str, today: date) -> dict:
    """Read EVERY published copy of a region's radar_ic and return the one with the newest
    as_of — the artifact the page ships is often days fresher than the data/ copy, because
    engine-render commits site/ only (D2). Emits a line-start ``::warning`` when the winner is
    older than STALE_INPUT_DAYS or when no copy is readable at all: a governor that
    degrades-never-raises would otherwise report identity trust for a dead input, which reads
    exactly like 'measured healthy'. NEVER disarms anything — the trust semantics are
    untouched, only the silence is."""
    cfg = _REGIONS[region]
    parts_list = [p for p in (cfg.get("radar"), cfg.get("radar_site")) if p]
    found = []
    for i, parts in enumerate(parts_list):
        payload = _read_json(root, parts)
        if isinstance(payload, dict):
            found.append({"path": "/".join(parts), "payload": payload,
                          "as_of": _as_of_date(payload), "pref": i})
    if not found:
        print(f"::warning title=signal-governor-stale::radar_ic input unreadable for region "
              f"{region} — tried {', '.join('/'.join(p) for p in parts_list)}; the governor is "
              f"running BLIND at identity trust 1.0 (nothing de-escalated, nothing measured)",
              flush=True)
        log.warning("signal_governor: no readable radar_ic for region %s (tried %s)",
                    region, [("/".join(p)) for p in parts_list])
        return {"payload": None, "source": None, "as_of": None, "age_days": None, "stale": True}
    # newest as_of wins; an un-dated copy sorts last (age unverifiable, never preferred). Ties
    # break toward the LAST candidate, i.e. the published site copy — the page's own truth.
    best = max(found, key=lambda f: (f["as_of"] is not None, f["as_of"] or date.min, f["pref"]))
    age = (today - best["as_of"]).days if best["as_of"] else None
    stale = age is not None and age > STALE_INPUT_DAYS
    if stale:
        print(f"::warning title=signal-governor-stale::radar_ic as_of {best['as_of']} is {age}d "
              f"old (>{STALE_INPUT_DAYS}d) at {best['path']} — the de-escalation gate is grading "
              f"a stale track record; trust stays ≥ its measured value, nothing is disarmed",
              flush=True)
        log.warning("signal_governor: stale radar_ic (%sd) at %s", age, best["path"])
    return {"payload": best["payload"], "source": best["path"], "as_of": best["as_of"],
            "age_days": age, "stale": bool(stale)}


def _radar_reading(root: Path, region: str = "us", today: date | None = None) -> dict:
    fresh = _freshest(root, region, today or date.today())
    bh = (fresh.get("payload") or {}).get("by_horizon") or {}
    return {"reading": _pick_reading(bh, "ic_daily_hac"), "coverage": _coverage(bh, "ic_daily_hac"),
            "input": {"source": fresh.get("source"),
                      "as_of": fresh["as_of"].isoformat() if fresh.get("as_of") else None,
                      "age_days": fresh.get("age_days"), "stale": fresh.get("stale")}}


def _hub_reading(root: Path, region: str = "us", today: date | None = None) -> dict:
    """No staleness sentinel here on purpose: build_intel_hub RE-PERSISTS data/hub/
    track_record.json in-run (scripts/build_intel_hub.py:259) immediately before
    signal_governor.compute reads it, so this input cannot lag the way radar_ic does.
    ``today`` is accepted only so both readers share one call signature."""
    bh = (_read_json(root, _REGIONS[region]["hub"]) or {}).get("horizons") or {}
    return {"reading": _pick_reading(bh, "opportunity_ic_daily"),
            "coverage": _coverage(bh, "opportunity_ic_daily")}


_READERS = {"radar": _radar_reading, "hub": _hub_reading}


def _gate(signal: str, reading: dict | None, coverage: dict | None = None) -> dict:
    """Apply the pre-registered gate to one signal's reading → its trust + full audit trail."""
    if not reading:
        if coverage and coverage.get("n_matured"):
            reason = (f"measuring: no VALID-HAC horizon yet — best is {coverage['horizon']}d with "
                      f"{coverage['n_days']} daily ICs (need ≥{coverage['need_days']} for a "
                      f"non-degenerate lag-{coverage['horizon']} HAC) — trust 1.0 (shadow)")
        else:
            reason = "no matured track record — measuring, trust 1.0 (identity)"
        return {"signal": signal, "n_matured": (coverage or {}).get("n_matured"),
                "ic": None, "t_hac": None, "horizon": None, "demoted": False, "trust": 1.0,
                "reason": reason}
    n, ic, t = reading["n_matured"], reading["ic"], reading["t_hac"]
    demoted = (n >= MIN_N and t is not None and abs(t) >= T_SIG and ic is not None and ic <= IC_DEAD)
    trust = _trust_from_ic(ic) if demoted else 1.0
    if demoted:
        reason = (f"DEMOTED: rigorous {reading['horizon']}d daily-HAC IC={ic:+.3f} (t={t:+.2f}) "
                  f"wrong-sign over {n} matured obs → trust {trust} (de-escalation only)")
    elif n < MIN_N:
        reason = f"measuring: only {n} matured obs (need ≥{MIN_N}) — trust 1.0"
    elif ic is not None and ic > IC_DEAD:
        reason = f"healthy: {reading['horizon']}d IC={ic:+.3f} not wrong-sign — trust 1.0"
    else:
        reason = f"not significant: {reading['horizon']}d t={t} (need |t|≥{T_SIG}) — trust 1.0"
    return {"signal": signal, "n_matured": n, "ic": round(ic, 4) if ic is not None else None,
            "t_hac": round(t, 3) if t is not None else None, "horizon": reading["horizon"],
            "demoted": bool(demoted), "trust": trust, "reason": reason}


def compute(root: Path | None = None, today: date | str | None = None,
            persist: bool = True, region: str = "us") -> dict:
    """Read every governable signal's matured track record, apply the pre-registered
    de-escalation gate, and emit the per-signal trust map + audit. Never raises.
    ``region`` ∈ _REGIONS ('us' | 'cn') selects the track-record + output paths — one shared
    gate engine, per-region wiring."""
    try:
        root = Path(root) if root else config.ROOT
        if region not in _REGIONS:
            region = "us"
        today_str = today.isoformat() if hasattr(today, "isoformat") else str(today or date.today())
        try:
            today_dt = datetime.fromisoformat(today_str[:10]).date()
        except Exception:  # noqa: BLE001
            today_dt = date.today()
        signals = {}
        inputs = {}
        for name in _SIGNALS:
            rd = _READERS[name](root, region, today_dt)
            signals[name] = _gate(name, rd.get("reading"), rd.get("coverage"))
            if rd.get("input"):                       # which copy was read + how old it was
                signals[name]["input"] = rd["input"]
                inputs[name] = rd["input"]
        trust = {k: v["trust"] for k, v in signals.items()}
        n_demoted = sum(1 for v in signals.values() if v["demoted"])
        demoted_names = [k for k, v in signals.items() if v["demoted"]]
        note = (f"{n_demoted} signal(s) de-escalated by evidence: {', '.join(demoted_names)}."
                if n_demoted else
                "No signal has cleared the de-escalation gate yet — all trust 1.0 (shadow/measuring).")
        out = {
            "schema": SCHEMA, "as_of": today_str, "generated_at": _now_iso(), "region": region,
            "gate": {"min_n": MIN_N, "t_sig": T_SIG, "ic_dead": IC_DEAD, "trust_floor": TRUST_FLOOR,
                     "method": "rigorous daily-HAC signed IC (Newey-West lag=horizon), never pooled Spearman"},
            "trust": trust, "signals": signals, "n_demoted": n_demoted, "note": note,
            "inputs": inputs,          # per-signal provenance: which copy, its as_of, its age
            "stale_inputs": sorted(k for k, v in inputs.items() if v.get("stale")),
            "disclaimer": ("De-escalation-only signal governor. A signal is demoted ONLY once its "
                           "matured, overlap-robust track record proves it mis-firing; trust never "
                           "exceeds 1.0 and never sizes a position. Absent ⇒ hub is ungoverned."),
        }
        if persist:
            p = root.joinpath(*_REGIONS[region]["out"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(out, indent=2, default=str))
        return out
    except Exception as e:  # noqa: BLE001 — additive, never fatal to the build
        log.warning("signal_governor.compute failed (returning identity): %s", e)
        return {"schema": SCHEMA, "as_of": str(today or date.today()), "generated_at": _now_iso(),
                "gate": {"min_n": MIN_N, "t_sig": T_SIG, "ic_dead": IC_DEAD, "trust_floor": TRUST_FLOOR},
                "trust": {}, "signals": {}, "n_demoted": 0,
                "note": f"error ({e}) — identity (all trust 1.0), degrade-safe."}


def load_trust(root: Path | None = None, region: str = "us") -> dict:
    """Read the persisted per-signal trust map for a region's hub to apply. SAFETY: every value is
    re-clamped to [TRUST_FLOOR, 1.0] on read, so the governor can NEVER hand the ranker a boost
    (>1.0), even if the file is hand-edited or corrupted. Absent/corrupt ⇒ {} (identity)."""
    try:
        root = Path(root) if root else config.ROOT
        out = _REGIONS.get(region, _REGIONS["us"])["out"]
        d = json.loads(root.joinpath(*out).read_text())
        raw = d.get("trust") or {}
        return {str(k): _clamp(float(v), TRUST_FLOOR, 1.0)
                for k, v in raw.items() if v is not None}
    except Exception:  # noqa: BLE001 — no governor ⇒ ungoverned
        return {}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="print the full governor payload")
    ap.add_argument("--region", default="us", choices=sorted(_REGIONS), help="region to govern")
    args = ap.parse_args()
    out = compute(persist=True, region=args.region)
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        print(f"[{args.region}] as_of {out['as_of']} · {out['n_demoted']} demoted · {out['note']}")
        for name, s in out.get("signals", {}).items():
            print(f"  {name:8s} trust={s['trust']:<5} | {s['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
