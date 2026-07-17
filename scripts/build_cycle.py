"""Render the Cycle Intelligence flagship page — the ENGINE-BACKED builder (D3-W3.2).

Before W3.2 this was a shell-copier: every plotted number came from the hand-typed
``site/cycle_data.js`` (audit finding A-1 — opinion wearing the visual authority of the
sibling engines).  W3.2 collapses that schism: **every MEASURED band's position, turns
and projection now come from the engine** (``sector_cycles.record_series`` over the proxy
registry's tapes), while the curated turning-point history + causal prose survive as FRAME
timelines and dated OPINION overlays.

Two-tier taxonomy (ruling A3 — exactly two user-facing words, MEASURED / FRAME):

  MEASURED band  → run ``record_series`` on the registry tape (per its kernel_params);
                   emit the engine record (rebased price / detrended osc / confirmed turns /
                   median-half-cycle projection with lo/hi band + overdue state from W1.6).
                   proxy/monthly/basis/epoch/fitness are HOVER-line details, not tiers.
  FRAME band     → emit the curated ``turns[]`` from the seed store + period stats + the
                   A8 leg-length list ("last major turn {t} ({N}y ago); prior up-legs ran
                   {list}").  NOTHING resolves to a scalar position — no oscillator, no
                   cone, no dial (ruling A8).
  DUAL card      → a MEASURED intermediate band + a thin FRAME secular strip (gold / dollar /
                   japan / bitcoin, + the memory/uranium proxy cards which carry a hand-turn
                   frame overlay).

Data flow (all script-tag data — NEVER fetch, ruling A11):
  data/cycle_ontology/proxy_registry.json     (W3.1 registry, tier per band)
  data/cycle_ontology/registry_health.json    (W3.1 per-band tape freshness)
  data/cycle_ontology/proxy_fitness.json       (W3.1 proxy timing verdicts)
  site/cycle_data.js                            (curated-turn SEED + OPINION prose)
        │
        ▼  this builder
  site/cycledata/cycle_engine.js                (window.CYCLE_ENGINE = {cid:{bands:[…]}})
  site/cycle.html                               (template shell)

Build-time discipline:
  • TOLERANCE ASSERTION (doctrine #1): where a hand-typed ``now.pos`` exists for a MEASURED
    band, the |hand − engine| gap is LOGGED (warn) and carried onto the card as a visible
    delta note.  The build FAILS only on STRUCTURAL errors (a MEASURED tape entirely
    missing / unresolvable) — never on an opinion-vs-engine gap.
  • STALENESS degrades PER-BAND, never the page (house law: a null never blocks building).
    ``registry_report(strict=True)`` raises only on structural errors; a stale tape marks
    its own band (``rec["stale"]``) and the card renders from the last data with a visible
    plain-word stale chip while every other card renders fresh.  One late G.17 release
    must never again freeze all 24 cards (the 2026-07-16/17 INDPRO freeze).

Respecting the ~67-min render budget: the tapes are tiny (~20 measured series × ~56 ms +
parquet I/O), so this stays in the seconds-to-low-minutes range; the wall-time is reported.
"""
from __future__ import annotations

import json
import logging
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402
from scripts._cycle_seed import load_seed  # noqa: E402

log = logging.getLogger("build_cycle")

# committed shell assets (kept in site/); cycle_data.js REMAINS the curated seed store
# (its curated turns[] + OPINION prose feed FRAME bands + the analyst-note overlay).
PAGE_ASSETS = ("cycle.css", "mm_charts.js", "cycle_data.js", "cycle_app.js", "cycle_i18n.js")

# where the engine artifact lands (script-tag data, loaded by the page shell)
_ENGINE_JS = "cycledata/cycle_engine.js"

# tolerance-assertion warn threshold: a hand-vs-engine |Δpos| beyond this logs LOUDER
# (still non-fatal — it renders as the card's visible delta note).
_TOL_LOUD = 20.0

# hero calendar window lead-in: the chart's xDomain starts at 2004, but a few deep-history
# tapes (INDPRO 1919→, Nikkei 1965→) carry a century of points that never plot.  Trim the
# emitted price/osc lines to xDomain[0] − this many years so the payload stays lean while the
# earliest visible history + a small off-screen lead-in for the line entry survive.  Turns are
# NEVER trimmed (a confirmed 1970s pivot still anchors the projection + hazard stats).
_PLOT_LEAD_YEARS = 2.0

# left edge of the hero calendar window (seed META.xDomain[0]); set once in compute() and
# read by _measured_record for the plot-line trim above.  None → no trim (deep history kept).
_XDOMAIN0: float | None = None


# ── engine record for one MEASURED band ──────────────────────────────────────
def _measured_record(cid: str, band: dict) -> dict | None:
    """Run ``record_series`` on the band's registry tape and return a JSON-safe record
    (price line / detrended oscillator / confirmed turns / projection / hazard features /
    basis + freq + proxy flags).  Returns None if the tape is too short for the kernel."""
    from engine import cycle_proxies as cp
    from engine import sector_cycles as sc

    s = cp.load_series(band)
    kernel = band.get("kernel") or {}
    zz_pct = kernel.get("zz_pct")
    zz_abs = kernel.get("zz_abs")
    if zz_pct is None and zz_abs is None:                    # vol-scaled default
        zz_pct = sc._zz_pct_for(s) if band["freq"] == "D" else sc._zz_pct_for_monthly(s)
    rec = sc.record_series(
        s, win_start=s.index.min(), last_ts=s.index[-1],
        freq=band["freq"], invert=band["invert"],
        zz_pct=zz_pct, zz_abs=zz_abs,
        zz_standardize=bool(kernel.get("zz_standardize")),
        trend_span=kernel.get("trend_span"), stoch_win=kernel.get("stoch_win"),
        basis_label=band["basis"], family="flagship",
        series_id=f"{cid}:{band['band']}",
    )
    if rec is None:
        return None
    now = rec.get("now") or {}
    # trim the plotted lines to the hero calendar window (+ a small lead-in) so a century of
    # off-screen INDPRO/Nikkei points never bloat the payload.  Turns/proj/hazard are untouched.
    x0 = (_XDOMAIN0 - _PLOT_LEAD_YEARS) if _XDOMAIN0 is not None else None
    price_pts = rec.get("price") or []
    osc_pts = rec.get("osc") or []
    if x0 is not None:
        price_pts = [p for p in price_pts if (p.get("x") or 0) >= x0]
        osc_pts = [p for p in osc_pts if (p.get("x") or 0) >= x0]
    # W4.3: score the hazard (P(turn ≤ 1m/3m/6m)) — additive, never fatal.
    hz = None
    hf = now.get("hazard_features")
    if hf:
        try:
            from engine.hazard_score import score as _hz_score, _UP_PHASES
            direction = "up" if (now.get("phase") or "") in _UP_PHASES else "down"
            hz = _hz_score(hf, direction, family="flagship")
        except Exception as _hz_exc:  # noqa: BLE001
            log.debug("build_cycle: hazard score failed for %s: %s", cid, _hz_exc)

    return {
        "band": band["band"],
        "tier": "measured",
        "proxy": bool(band.get("proxy")),
        "position_gauge": bool(band.get("position_gauge", True)),
        "freq": band["freq"],
        "basis": band["basis"],
        "invert": bool(band.get("invert")),
        "ref": s.attrs.get("ref"),
        "series_first": str(s.index.min().date()),
        "series_last": str(s.index.max().date()),
        "n_rows": int(len(s)),
        "price": price_pts,
        "osc": osc_pts,
        "turns": rec.get("turns"),
        "proj": rec.get("proj"),
        "record_basis": rec.get("basis"),
        "now": {
            "pos": now.get("pos"),
            "phase": now.get("phase"),
            "phaseLabel": now.get("phaseLabel"),
            "phase_v2": now.get("phase_v2"),
            "pos_v2": now.get("pos_v2"),
            "osc_slope": now.get("osc_slope"),
            "signal": now.get("signal"),
            "stance": now.get("stance"),
            "tone": now.get("tone"),
            "divergence": now.get("divergence"),
            "lastPeak": now.get("lastPeak"),
            "lastTrough": now.get("lastTrough"),
            "freq": now.get("freq") or band["freq"],
            "hazard_features": now.get("hazard_features"),
            "hazard": hz,               # W4.3: P(turn ≤ 1m/3m/6m) or None
        },
        "n_turns_all": rec.get("n_turns_all"),
    }


# ── frame band from the curated seed (A8: timeline + leg lengths, no scalar) ──
def _leg_lengths(turns: list[dict]) -> dict:
    """Prior up-legs (trough→peak) and down-legs (peak→trough), in years, from the curated
    turns[].  The A8 pattern lists prior UP-leg lengths; we compute both for the tooltip."""
    def _yf(t: str) -> float:
        y, m = (t.split("-") + ["6"])[:2]
        return int(y) + ((int(m) or 6) - 0.5) / 12.0

    ups: list[float] = []
    downs: list[float] = []
    for i in range(1, len(turns)):
        a, b = turns[i - 1], turns[i]
        dt = round(_yf(b["t"]) - _yf(a["t"]), 1)
        if dt <= 0:
            continue
        if a["k"] == "trough" and b["k"] == "peak":
            ups.append(dt)
        elif a["k"] == "peak" and b["k"] == "trough":
            downs.append(dt)
    return {"ups": ups, "downs": downs}


def _frame_record(cid: str, band: dict, seed_c: dict, today_x: float) -> dict:
    """Emit a FRAME band: the curated turns[] + period stats + the A8 leg-length list +
    "last major turn {t} ({N}y ago)".  NO oscillator, NO position scalar, NO cone (A8).
    A reserved ``tripwire`` slot is left for W3.3 (empty here)."""
    def _yf(t: str) -> float:
        y, m = (t.split("-") + ["6"])[:2]
        return int(y) + ((int(m) or 6) - 0.5) / 12.0

    turns = seed_c.get("turns") or []
    period = seed_c.get("period") or {}
    legs = _leg_lengths(turns)
    last = turns[-1] if turns else None
    last_x = _yf(last["t"]) if last else None
    yrs_since = round(today_x - last_x, 1) if last_x is not None else None
    return {
        "band": band["band"],
        "tier": "frame",
        "proxy": False,
        "position_gauge": False,          # A8: nothing on a frame resolves to a scalar
        "freq": None,
        "basis": None,
        "monitors": band.get("monitors") or [],
        "turns": turns,                   # curated crown-jewel history (the plotted timeline)
        "period": period,                 # {central, low, high} — window width, not a forecast
        "leg_lengths": legs,              # A8: prior up/down leg lengths (years)
        "last_turn": ({"t": last["t"], "k": last["k"], "e": last.get("e"),
                       "v": last.get("v")} if last else None),
        "years_since_last": yrs_since,    # A8 "N years ago" — pure arithmetic on wall-clock
        "typical_window": (               # a WINDOW (not a central date): last + [low, high]
            {"lo": round(last_x + (period.get("low") or 0), 3),
             "hi": round(last_x + (period.get("high") or 0), 3),
             "next": ("trough" if last["k"] == "peak" else "peak")}
            if last_x is not None and period.get("low") is not None else None),
        "tripwire": None,                 # W3.3: filled by compute() after evaluate_and_persist()
    }


# ── opinion / analyst-note overlay (dated, TTL-lensed) ───────────────────────
def _opinion(seed_c: dict, meta: dict) -> dict:
    """The curated prose, clearly labelled OPINION with its as-of.  The hand ``now.pos`` /
    ``proj`` are DEAD for plotting on MEASURED bands (the engine owns those) — they survive
    only as this dated note + the tolerance-delta comparison."""
    now = seed_c.get("now") or {}
    proj = seed_c.get("proj") or {}
    return {
        "as_of": meta.get("asOf"),
        "archetype": seed_c.get("archetype"),
        "read": now.get("read"),
        "falsifier": proj.get("falsifier"),
        "regimeNote": seed_c.get("regimeNote"),
        "drivers": proj.get("drivers") or [],
        "proxy": seed_c.get("proxy"),
        # the hand read is retained ONLY for the tolerance delta + transparency; never plotted
        "hand_pos": now.get("pos"),
        "hand_phase": now.get("phase"),
        "hand_phaseLabel": now.get("phaseLabel"),
        "hand_next": proj.get("nextTurn"),
        "hand_central": proj.get("central"),
        "hand_tilt": proj.get("tilt"),
        "confidence": now.get("confidence"),
    }


def _fmt(v):
    """JSON-safe: numpy scalars → python; NaN → None."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    return v


def _regime_disagreement(meta: dict, by_id: dict) -> dict | None:
    """W4.5 — compare curated ``regime_claim`` fields against the live engine quad.

    Builds the narrative list (every curated cycle + the META regime block as a synthetic
    "meta" narrative) and defers to ``regime_prior.disagreement_block``.  Returns None (no
    banner) when the prior is unavailable, no claim contradicts, or anything raises — this
    is a display-only reconciliation that must never fail the render (doctrine #7)."""
    try:
        from engine.regime_prior import disagreement_block, regime_prior
        meta_regime = meta.get("regime") or {}
        # each curated cycle is already a narrative dict (it carries id + optional regime_claim)
        narratives: list[dict] = list(by_id.values())
        # + the page's headline premise as the "meta" narrative
        narratives.append({"id": "meta", "regime_claim": meta_regime.get("regime_claim")})
        prior = regime_prior()
        return disagreement_block(narratives, prior=prior)
    except Exception as exc:  # noqa: BLE001
        log.warning("build_cycle: regime disagreement check failed (non-fatal): %s", exc)
        return None


def compute(root: Path) -> dict:
    """Build the whole ``window.CYCLE_ENGINE`` payload + a tolerance ledger.

    STRUCTURAL errors (a MEASURED tape entirely missing / unresolvable) propagate as
    exceptions (the build FAILS — doctrine #7).  A STALE tape degrades only its own band:
    the record is still computed from the last data and carries ``rec["stale"]`` for the
    card chip (house law: a null never blocks building).  Opinion-vs-engine gaps do NOT
    fail the build — they are logged + carried onto the card (doctrine #1)."""
    from engine import cycle_proxies as cp

    # 1 · structural gate — raises ONLY on a missing/unresolvable MEASURED tape.
    #     Stale tapes come back in health["stale"] and degrade per-band below.
    health = cp.registry_report(strict=True)
    for _stale_msg in health.get("stale") or []:
        log.warning("build_cycle: %s — rendering band from last data", _stale_msg)

    # 2 · fitness verdicts (proxy timing) — read the W3.1 artifact if present, else recompute.
    fit_path = root / "data" / "cycle_ontology" / "proxy_fitness.json"
    fitness = (json.loads(fit_path.read_text(encoding="utf-8")).get("verdicts", {})
               if fit_path.exists() else cp.run_fitness(root).get("verdicts", {}))

    # 2b · W3.3 — falsifier tripwire evaluation + latch persistence (non-fatal) ──────────────
    #   evaluate_and_persist is a cheap series-read pass (no kernel runs).  It is additive:
    #   if falsifiers.json is absent the call returns empty lists and the build continues.
    tripwire_by_cycle: dict = {}
    try:
        from engine import falsifier_tripwires as ft
        _tw_results, _tw_newly = ft.evaluate_and_persist(dispatch=True)
        tripwire_by_cycle = ft.results_summary(_tw_results)
        log.info("tripwires: %d evaluated, %d newly fired", len(_tw_results), len(_tw_newly))
    except Exception as _tw_exc:
        log.warning("tripwire evaluation failed (non-fatal): %s", _tw_exc)

    # 3 · the curated seed (turns + OPINION prose) — the frame-timeline + note source.
    seed = load_seed(root / "site" / "cycle_data.js")
    meta, by_id = seed["meta"], seed["by_id"]
    today_x = _now_x()
    global _XDOMAIN0
    xdom = meta.get("xDomain") or []
    _XDOMAIN0 = float(xdom[0]) if xdom else None

    engine: dict = {}
    tol_ledger: list[dict] = []
    order: list[str] = []
    for cid, spec in cp.REGISTRY.items():
        if cid == "spx":
            continue                       # markets.html flagship (W3.5), not a cycle.html card
        seed_c = by_id.get(cid) or {}
        bands_out: list[dict] = []
        card_tier = "frame"
        for band in spec["bands"]:
            if band["tier"] == "measured":
                rec = _measured_record(cid, band)
                if rec is None:
                    log.warning("cycle.%s.%s: record_series returned None (tape too short) — "
                                "skipping band", cid, band["band"])
                    continue
                # attach the fitness verdict (hover 'how computed') for proxy bands
                if band.get("proxy") and cid in fitness:
                    rec["fitness"] = fitness[cid]
                # attach the W3.1 health row (rows / first / last / stale_days)
                hrow = (health.get("bands") or {}).get(f"{cid}.{band['band']}")
                rec["health"] = hrow
                # stale tape → degrade THIS band only: keep the last-data record and
                # flag it for the card's plain-word stale chip (EN/ZH in cycle_app.js).
                if hrow and hrow.get("found") and not hrow.get("ok"):
                    rec["stale"] = {"days": hrow.get("stale_days"),
                                    "limit": hrow.get("stale_limit"),
                                    "last": hrow.get("last")}
                bands_out.append(rec)
                card_tier = "measured"
                # tolerance assertion (doctrine #1) — hand vs engine position gap
                hand_pos = (seed_c.get("now") or {}).get("pos")
                eng_pos = (rec.get("now") or {}).get("pos")
                if (hand_pos is not None and eng_pos is not None
                        and rec.get("position_gauge", True)):
                    delta = round(float(eng_pos) - float(hand_pos), 1)
                    lvl = logging.WARNING if abs(delta) >= _TOL_LOUD else logging.INFO
                    log.log(lvl, "tolerance %s.%s: hand pos=%.0f  engine pos=%.1f  Δ=%+.1f",
                            cid, band["band"], hand_pos, eng_pos, delta)
                    rec["tolerance"] = {"hand_pos": hand_pos, "engine_pos": eng_pos,
                                        "delta": delta, "loud": bool(abs(delta) >= _TOL_LOUD)}
                    tol_ledger.append({"cycle": cid, "band": band["band"],
                                       "hand_pos": hand_pos, "engine_pos": eng_pos,
                                       "delta": delta})
            else:
                bands_out.append(_frame_record(cid, band, seed_c, today_x))
        if not bands_out:
            log.warning("cycle.%s: no bands emitted — dropping card", cid)
            continue
        # W3.3: attach tripwire states for this cycle (if evaluated)
        tw_states = tripwire_by_cycle.get(cid) or []

        engine[cid] = {
            "id": cid,
            "name": spec["name"],
            "short": seed_c.get("short") or spec["name"],
            "group": seed_c.get("group"),
            "accent": seed_c.get("accent"),
            "card_tier": card_tier,        # 'measured' if any measured band, else 'frame'
            "dual": bool(len(bands_out) > 1),
            "bands": bands_out,
            "opinion": _opinion(seed_c, meta),
            "tripwires": tw_states,        # W3.3: per-tripwire states for the UI strip
        }
        order.append(cid)

    # W4.5 — reconcile curated regime_claim fields against the live engine quad.
    #   narratives = every curated cycle (id + optional regime_claim) + the META regime
    #   block as a synthetic "meta" narrative (the page's headline premise).  The check is
    #   additive + non-fatal: a missing/broken prior yields no banner, never a build failure.
    regime_disagreement = _regime_disagreement(meta, by_id)

    payload = {
        "version": 1,
        "wave": "W4.5",
        "as_of": meta.get("asOf"),
        "xDomain": meta.get("xDomain"),
        "regime": meta.get("regime"),
        "regime_disagreement": regime_disagreement,
        "order": order,
        "cycles": engine,
        "census": {"cards": len(engine),
                   "measured_cards": sum(1 for c in engine.values() if c["card_tier"] == "measured"),
                   "frame_cards": sum(1 for c in engine.values() if c["card_tier"] == "frame"),
                   "dual_cards": sum(1 for c in engine.values() if c["dual"]),
                   "stale_bands": sum(
                       sum(1 for b in c["bands"] if b.get("stale")) for c in engine.values()),
                   "tripwires_total": sum(len(c.get("tripwires") or []) for c in engine.values()),
                   "tripwires_fired": sum(
                       sum(1 for tw in (c.get("tripwires") or []) if tw.get("state") == "FIRED")
                       for c in engine.values())},
        "tolerance_ledger": tol_ledger,
    }
    return payload


def _now_x() -> float:
    """Wall-clock decimal year (matches cycle_app.js yfNow / the engine's _yf)."""
    now = pd.Timestamp.now()
    start = pd.Timestamp(now.year, 1, 1)
    end = pd.Timestamp(now.year + 1, 1, 1)
    return now.year + (now - start) / (end - start)


def _write_engine_js(site: Path, payload: dict) -> None:
    (site / "cycledata").mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, default=_fmt, separators=(",", ":"))
    js = ("/* cycle_engine.js — GENERATED by scripts/build_cycle.py (D3-W3.2).\n"
          "   window.CYCLE_ENGINE: engine-computed MEASURED bands + curated FRAME timelines.\n"
          "   Do not edit by hand — regenerate via `python -m scripts.build_cycle`. */\n"
          "window.CYCLE_ENGINE = " + body + ";\n")
    (site / _ENGINE_JS).write_text(js, encoding="utf-8")


def main() -> int:
    t0 = time.time()
    root = config.ROOT
    site = root / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)

    # 1a · emit the shared regime prior artifact (W4.5 — additive, cheap, never fatal) ──
    try:
        from scripts.build_regime_prior import emit as _emit_prior
        from lib import config as _cfg
        _emit_prior(data_dir=_cfg.data_dir(), site_dir=site)
    except Exception as _rp_exc:  # noqa: BLE001
        log.warning("build_cycle: regime_prior emit failed (non-fatal): %s", _rp_exc)

    # 1b · compute the engine payload (raises on structural / staleness errors) ──
    payload = compute(root)
    _write_engine_js(site, payload)
    log.info("cycle_engine.js: %d cards (%d measured, %d frame, %d dual); "
             "%d stale bands (degraded, not fatal); %d tolerance gaps",
             payload["census"]["cards"], payload["census"]["measured_cards"],
             payload["census"]["frame_cards"], payload["census"]["dual_cards"],
             payload["census"]["stale_bands"], len(payload["tolerance_ledger"]))
    rd = payload.get("regime_disagreement")
    if rd:
        log.warning("regime disagreement: %s (%d claims, %s)",
                    rd.get("banner_en"), rd.get("n"),
                    "provisional/soft" if rd.get("provisional") else "firm")

    # 2 · render the page shell ────────────────────────────────────────────────
    env = Environment(
        loader=FileSystemLoader(str(root / "templates")),
        autoescape=False,  # macro pages emit raw HTML; _navlinks uses |safe
    )
    try:                                       # _navlinks references t()/td()/tr() i18n globals
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001 — degrade to English-only rather than crash the build
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    html = env.get_template("cycle.html.j2").render()
    write_page(site / "cycle.html", html, encoding="utf-8")

    # 3 · copy the committed shell assets (cycle_data.js stays the curated seed) ─
    for asset in PAGE_ASSETS:
        src = root / "templates" / asset
        if src.exists():
            shutil.copy2(src, site / asset)

    log.info("built site/cycle.html (%d-cycle engine-backed dashboard) in %.1fs",
             payload["census"]["cards"], time.time() - t0)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
