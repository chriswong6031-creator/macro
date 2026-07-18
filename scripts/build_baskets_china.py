"""Build the China thematic-baskets page -> site/baskets_china.html (+ chinabasketdata/baskets.json).

The A-share analogue of scripts/build_baskets.py. Reads data/baskets_china/membership.json +
the china_search close cache + the CSI 300 ETF via engine.baskets_china.compute_china_baskets()
and renders the same FactorWatch-style baskets view (sortable performance table, interactive
overlay chart, per-category cards + member drill), benchmarked to the CSI 300 (沪深300).
Additive — any failure logs and returns 0 so it can never break the rest of the site.

Usage: python -m scripts.build_baskets_china
"""
from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_baskets_china")

# Version string bumped when the cascade logic changes; invalidates the member-signal cache.
_MEMBER_SIGNAL_VERSION = "v1"
# Max age in days before the member-signal cache is forced stale.
_MEMBER_SIGNAL_MAX_AGE_D = 3


def _attach_basket_intel(data: dict) -> None:
    """Attach per-basket intel from theme_intel + basket_turn_cn onto each basket row.

    Fields added to each basket dict (None-safe; missing intel → fields absent or None):
      score, label, label_zh, reco, reco_zh, clean_entry_q, rollover_risk_band
    turn_state is already attached by the china_basket_turn organ after this runs, so
    this function only reads existing turn_state if present.

    Called ONCE after theme_intel is resolved and BEFORE the JSON write.
    """
    try:
        ti = data.get("theme_intel") or {}
        themes = ti.get("themes") or []
        theme_by_id: dict = {}
        for t in themes:
            bid = t.get("id")
            if bid:
                theme_by_id[bid] = t

        for b in data.get("baskets") or []:
            bid = b.get("id")
            if not bid:
                continue
            t = theme_by_id.get(bid)
            if t is None:
                continue
            b["score"] = t.get("score")
            b["label"] = t.get("label")
            b["label_zh"] = t.get("label_zh")
            b["reco"] = t.get("reco")
            b["reco_zh"] = t.get("reco_zh")
            tx = t.get("textures") or {}
            ce = tx.get("clean_entry") or {}
            rr = tx.get("rollover_risk") or {}
            b["clean_entry_q"] = ce.get("quality")
            # rollover_risk band deliberately NOT attached — no consumer yet (review 07-18)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("_attach_basket_intel failed: %s", e)


def _compute_member_signals(data: dict, site: Path) -> None:
    """Compute per-member entry-signal chips for curated baskets.

    For each curated basket member with >=120 bars in data/china_search/closes.parquet,
    runs engine.signal_gate.gate() and attaches to the member dict:
      sig_tier: "T1"|"T2"|"T3"|None  (T4 or None -> None)
      sig_fresh: bool
      ret_5d: float|None

    Content-gated cache (site/chinabasketdata/member_signals.json) keyed on
    (closes max date, member set hash, cascade version) — reused when fingerprint matches.
    Wrapped in try/except: never breaks the build.
    """
    _CACHE_PATH = site / "chinabasketdata" / "member_signals.json"
    BUYABLE = {"T1", "T2", "T3"}

    try:
        import pandas as pd
        from engine.signal_gate import gate as _sg_gate

        closes_p = config.ROOT / "data" / "china_search" / "closes.parquet"
        if not closes_p.exists():
            log.warning("member_signals: closes.parquet not found — skipping")
            return

        closes_df = pd.read_parquet(closes_p)
        max_date = str(closes_df.index.max().date() if hasattr(closes_df.index.max(), "date") else closes_df.index.max())

        # Build member set fingerprint from all curated basket member symbols.
        all_symbols: list[str] = []
        for b in (data.get("baskets") or []):
            for m in (b.get("members") or []):
                sym = m.get("symbol")
                if sym:
                    all_symbols.append(sym)
        all_symbols.sort()
        fp_src = f"{max_date}|{'|'.join(all_symbols)}|{_MEMBER_SIGNAL_VERSION}"
        fingerprint = hashlib.sha1(fp_src.encode()).hexdigest()[:16]

        # Load cache if fingerprint matches and age is acceptable.
        cached_signals: dict = {}
        cache_hit = False
        try:
            if _CACHE_PATH.exists():
                _prev = json.loads(_CACHE_PATH.read_text())
                _pm = _prev.get("meta") or {}
                _age_ok = False
                if _pm.get("computed_at"):
                    _age_d = (datetime.now(timezone.utc)
                              - datetime.fromisoformat(_pm["computed_at"])).days
                    _age_ok = 0 <= _age_d <= _MEMBER_SIGNAL_MAX_AGE_D
                if _pm.get("fingerprint") == fingerprint and _age_ok:
                    cached_signals = _prev.get("signals") or {}
                    cache_hit = True
                    log.info("member_signals: cache HIT (fp=%s)", fingerprint)
        except Exception:  # noqa: BLE001
            pass

        if not cache_hit:
            log.info("member_signals: computing for %d symbols...", len(set(all_symbols)))
            import time as _t
            _t0 = _t.time()
            computed: dict = {}
            unique_symbols = list(dict.fromkeys(all_symbols))
            for sym in unique_symbols:
                if sym not in closes_df.columns:
                    computed[sym] = {"sig_tier": None, "sig_fresh": False}
                    continue
                series = closes_df[sym].dropna()
                if len(series) < 120:
                    computed[sym] = {"sig_tier": None, "sig_fresh": False}
                    continue
                try:
                    v = _sg_gate(sym, series)
                    tc = v.get("tier_cascade")
                    tier = tc if tc in BUYABLE else None
                    # fresh = True when the tier is active and recently crossed
                    fresh = tier is not None and (
                        v.get("fresh_bars") is not None and v.get("fresh_bars", 999) <= 10
                    )
                    computed[sym] = {"sig_tier": tier, "sig_fresh": bool(fresh)}
                except Exception as _e:  # noqa: BLE001
                    log.debug("member_signals: gate(%s) failed: %s", sym, _e)
                    computed[sym] = {"sig_tier": None, "sig_fresh": False}

            elapsed = _t.time() - _t0
            log.info("member_signals: computed %d symbols in %.1fs", len(computed), elapsed)
            cached_signals = computed

            # Persist cache.
            try:
                _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                _CACHE_PATH.write_text(json.dumps({
                    "meta": {
                        "fingerprint": fingerprint,
                        "computed_at": datetime.now(timezone.utc).isoformat(),
                        "max_date": max_date,
                        "version": _MEMBER_SIGNAL_VERSION,
                    },
                    "signals": cached_signals,
                }, separators=(",", ":")))
            except Exception as _e:  # noqa: BLE001
                log.warning("member_signals: cache write failed: %s", _e)

        # Attach signals to member rows; also compute ret_5d from closes.
        # ret_5d: last close / close[−6] − 1 (5 trading days), None if insufficient.
        _last_5d: dict = {}
        for sym in set(all_symbols):
            if sym in closes_df.columns:
                series = closes_df[sym].dropna()
                if len(series) >= 6:
                    _last_5d[sym] = float(series.iloc[-1] / series.iloc[-6] - 1)

        for b in (data.get("baskets") or []):
            for m in (b.get("members") or []):
                sym = m.get("symbol")
                if not sym:
                    continue
                sig = cached_signals.get(sym) or {}
                m["sig_tier"] = sig.get("sig_tier")
                m["sig_fresh"] = sig.get("sig_fresh", False)
                m["ret_5d"] = _last_5d.get(sym)

    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("_compute_member_signals failed: %s", e)


def _compute_basket_overlaps(data: dict) -> None:
    """Compute pairwise member overlap (Jaccard) among curated baskets.

    Attaches top_overlaps: [{id, name, name_zh, n_shared, jaccard}] (top 3, n_shared>=2)
    to each basket dict. Cheap: 22×22 pairwise.
    """
    try:
        baskets = data.get("baskets") or []
        member_sets: dict = {}
        for b in baskets:
            bid = b.get("id")
            if bid:
                member_sets[bid] = {m.get("symbol") for m in (b.get("members") or []) if m.get("symbol")}

        basket_meta: dict = {}
        for b in baskets:
            bid = b.get("id")
            if bid:
                basket_meta[bid] = {"name": b.get("name", ""), "name_zh": b.get("name_zh")}

        for b in baskets:
            bid = b.get("id")
            if not bid:
                continue
            a_set = member_sets.get(bid) or set()
            overlaps = []
            for b2 in baskets:
                bid2 = b2.get("id")
                if not bid2 or bid2 == bid:
                    continue
                b_set = member_sets.get(bid2) or set()
                inter = len(a_set & b_set)
                if inter < 2:
                    continue
                union = len(a_set | b_set)
                jaccard = inter / union if union > 0 else 0.0
                overlaps.append({
                    "id": bid2,
                    "name": basket_meta[bid2]["name"],
                    "name_zh": basket_meta[bid2]["name_zh"],
                    "n_shared": inter,
                    "jaccard": round(jaccard, 3),
                })
            overlaps.sort(key=lambda x: (-x["n_shared"], -x["jaccard"]))
            b["top_overlaps"] = overlaps[:3]
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("_compute_basket_overlaps failed: %s", e)


def main() -> int:
    site = config.ROOT / "site"
    try:
        from engine.baskets_china import compute_china_baskets
        data = compute_china_baskets()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china baskets engine failed: %s", e)
        return 0
    if not data:
        log.warning("no china baskets (need data/baskets_china/membership.json + china_search cache) — skipping")
        return 0

    # THEME ROTATION DESK (regionalized) — score/label/recommend + 5-day rotation + act-now +
    # concentration, rides inside baskets_json; region alerts feed the page bell. Additive.
    theme_alerts_recent = []
    try:
        from engine.theme_scoring import compute_theme_intel
        ti = compute_theme_intel("china")
        if ti:
            data["theme_intel"] = ti
            from engine import theme_alerts
            theme_alerts.rebuild(ti, "china")
            theme_alerts_recent = theme_alerts.recent(30, as_of=ti.get("as_of"), region="china")
            # Attach score/label/reco/clean_entry_q/rollover_risk_band onto each basket row
            # so the page can sort by score and show the desk findings without a second round-trip.
            _attach_basket_intel(data)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china theme desk failed: %s", e)

    # THEME CONTEXT (leadership health hero) — reads allocation_china.json + theme_intel,
    # produces site/basketdata/theme_context_cn.json and the theme_context Jinja var.
    # MUST run after _attach_basket_intel so theme_intel is populated.
    # Fail-open: absent alloc or engine failure → theme_context=None (page renders plain header).
    theme_context = None
    try:
        from engine.theme_context import compute_theme_context, write_context as _write_tc
        _alloc_cn_path = site / "allocationdata" / "allocation_china.json"
        if _alloc_cn_path.exists():
            _alloc_cn = json.loads(_alloc_cn_path.read_text())
            _ti_for_tc = data.get("theme_intel") or {}
            theme_context = compute_theme_context(_alloc_cn, _ti_for_tc, region="china")
            if theme_context:
                _write_tc(theme_context)
                log.info("theme_context[china]: wrote theme_context_cn.json (state=%s)",
                         (theme_context.get("leadership") or {}).get("state"))
        else:
            log.debug("theme_context[china]: allocation_china.json absent — skipping")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("theme_context[china] failed: %s", e)

    # 🔥 FORMING NARRATIVES (engine.narrative_emergence) — coherent, TIGHTENING A-share
    # groups not yet in a basket, with clean-entry recommended tickers. emergence_alerts
    # diffs vs prior + fires a "narrative_forming" event. Display-only, additive, noisy.
    emergence = None
    try:
        from engine.narrative_emergence import compute_emergence
        emergence = compute_emergence("china")
        if emergence:
            from engine import emergence_alerts
            emergence_alerts.rebuild(emergence, "china")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china narrative emergence failed: %s", e)

    # Validated sleeve-size chip (W6-CN Fix 1) — thread risk_radar_intl gross_factor into the
    # baskets JSON header as a DISPLAY chip. Regime sizes sleeves, never vetoes names.
    try:
        from engine.risk_radar_intl import cn_sleeve_chip
        data["sleeve_chip"] = cn_sleeve_chip()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china baskets: sleeve chip failed (%s)", e)

    # attach each basket's cycle record (engine.china_sector_cycles, written by
    # scripts.build_china_sector_cycles) so BOTH the overview payload (baskets.json + the
    # rendered page, e.g. the Leadership Health "contested" read) AND the per-theme detail
    # pages can see it. MUST run BEFORE the JSON write / overview render below — it used to
    # sit after them, so only detail pages ever saw cycle data (the stale-label problem).
    # Optional + ordering-safe: absent map (cycles not built yet) simply omits the record.
    try:
        cyc_map_p = site / "chinasectordata" / "sector_cycles_basket_map.json"
        if cyc_map_p.exists():
            cyc_map = json.loads(cyc_map_p.read_text())
            for b in data.get("baskets", []):
                cyc = cyc_map.get(b.get("id"))
                if cyc:
                    b["cycle"] = cyc
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("china baskets cycle-map attach failed: %s", e)

    fdir = site / "chinabasketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "baskets.json").write_text(json.dumps(data, separators=(",", ":"), default=str))
    # SECTOR PULSE — compact per-theme rotation data product. Also merges velocity/heat keys
    # into theme_intel for the rotation-scorecard page enhancements. Additive — never breaks build.
    try:
        if data.get("theme_intel"):
            from engine import sector_pulse as _sp
            _sp.write_pulse(data["theme_intel"], "china", fdir)
            _sp.merge_pulse_into_theme_intel(data["theme_intel"], "china")
            _sp.write_score_snapshot(data["theme_intel"], "china")   # accrues the baskets_china velocity stream
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sector_pulse china hook failed: %s", e)
    if emergence:
        (fdir / "narrative_emergence.json").write_text(
            json.dumps(emergence, separators=(",", ":"), ensure_ascii=False, default=str))

    # split the dense CHART (level matrix, for the interactive chart + live σ/sort table)
    # from the BASKETS metadata (thesis/members/rationale/perf/changelog/reference).
    chart = data.pop("chart")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # W5-B: load the sleeve summary stats for the strategy card (additive, best-effort).
    # Reads the committed sleeve JSON if it exists; falling back to None just hides the card stats.
    # Also reads rederive_stats.primary.full for Sharpe + n (replaces hardcoded ~0.57 / 349).
    sleeve_stats = None
    try:
        _sleeve_json = site / "factordata" / "cn_reversal_sleeve.json"
        if _sleeve_json.exists():
            _sd = json.loads(_sleeve_json.read_text())
            _sf = (_sd.get("sizing") or {}).get("sleeve_factor")
            _nm = _sd.get("n_members")
            if _sf is not None and _nm is not None:
                sleeve_stats = {"n_members": int(_nm), "sleeve_factor": float(_sf)}
                # Pull re-derived Sharpe + n from rederive_stats.primary.full (source-of-truth).
                _rd = (_sd.get("rederive_stats") or {}).get("primary") or {}
                _full = _rd.get("full") or {}
                _sh = _full.get("sharpe")
                _nr = _full.get("n")
                if _sh is not None:
                    sleeve_stats["sharpe"] = float(_sh)
                if _nr is not None:
                    sleeve_stats["n_rebalances"] = int(_nr)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.debug("baskets_china: sleeve stats load skipped (%s)", e)

    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)

    def _render_page(payload: dict) -> None:
        """Render + write baskets_china.html for the given basket payload.

        Called twice: once here (pre-turn-organ, so an organ failure still ships
        a page), and once after the china_basket_turn organ + signal/overlap
        merge — the organ runs post-write by dependency (it reads the
        just-written level series), so without the re-render the INLINED page
        payload would lack turn_state and the lifecycle chips / Entry Radar
        would silently never fire from turn states (us_stocks one-build-lag
        class, cf. #2829).

        #2886 double-render contract: theme_context= must be passed to EVERY
        render call so the final page retains the hero. Both calls use the same
        theme_context dict (computed once above, before the first render)."""
        _html = env.get_template("baskets_china.html.j2").render(
            baskets_json=json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
            chart_json=json.dumps(chart, separators=(",", ":")),
            theme_alerts_json=json.dumps(theme_alerts_recent, separators=(",", ":")),
            bench_en="CSI 300", bench_zh="沪深300",
            generated_utc=built,
            sleeve_stats=sleeve_stats,
            theme_context=theme_context)
        write_page(site / "baskets_china.html", _html)
        return len(_html)

    _page_kb = (_render_page(data) or 0) // 1024

    # per-theme detail pages (site/basket_china/<id>.html) + the shared desk renderer
    # (basket cycle records were attached above, before the JSON write, so the detail
    # builder still sees b["cycle"] exactly as before)
    try:
        from scripts.build_theme_detail import build_detail_pages
        build_detail_pages(data, site, env, "china")
        deskjs = config.ROOT / "templates" / "baskets_desk.js"
        if deskjs.exists():
            (site / "baskets_desk.js").write_text(deskjs.read_text())
        ne = config.ROOT / "templates" / "forming_narratives.js"
        if ne.exists():
            (site / "forming_narratives.js").write_text(ne.read_text())
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china theme detail pages failed: %s", e)
    # ship the TradingView Lightweight Charts runtime (Apache-2.0) used by the page
    lwc = config.ROOT / "templates" / "lightweight-charts.js"
    if lwc.exists():
        (site / "lightweight-charts.js").write_text(lwc.read_text())
    log.info("wrote %s/baskets_china.html (%d baskets, %d categories, %d KB)",
             site, len(data["baskets"]), len(data.get("categories", [])), _page_kb)

    # W3.8 — FREEZE China (curated) basket levels + membership hashes (append-only, PIT).
    # chart was popped from data above and is still in scope.
    try:
        from engine.basket_freeze import freeze_domain, FreezeSkipped
        from engine.baskets_china import _membership as _cn_mem, _closes as _cn_closes
        _cn_mem_data = _cn_mem()
        try:
            _cn_cl = _cn_closes()
        except Exception:  # noqa: BLE001
            _cn_cl = None
        _freeze_result = freeze_domain("china", {"chart": chart}, _cn_cl, _cn_mem_data)
        log.info("basket_freeze[china]: %s", _freeze_result)
    except FreezeSkipped as e:
        log.error("basket_freeze[china]: SKIPPED (churn guard): %s", e)
    except Exception as e:  # noqa: BLE001
        log.error("basket_freeze[china]: failed: %s", e)

    # W8-R5 — CN basket turn-watch organ (display-tier, expected-NULL forward meter).
    # Runs AFTER baskets.json is committed so compute_all() reads the just-written
    # level series. Annotates each basket with its turn state and writes
    # site/chinabasketdata/basket_turn_cn.json + appends ledger (CN_LANE=asia gate).
    # Additive — never fatal.
    try:
        import time as _t
        _t0 = _t.time()
        from engine.china_basket_turn import run as _cn_turn_run
        _turn_art = _cn_turn_run(data_root=config.ROOT, site_root=site)
        _turn_elapsed = _t.time() - _t0
        _turn_states = _turn_art.get("baskets", {})
        _turn_dist = {}
        for _s in _turn_states.values():
            _st = _s.get("state", "NONE")
            _turn_dist[_st] = _turn_dist.get(_st, 0) + 1
        log.info("china_basket_turn: %d baskets in %.2fs — dist: %s",
                 len(_turn_states), _turn_elapsed, _turn_dist)
        # Annotate each curated basket row in the serialized payload for UI chips.
        # Re-write baskets.json with turn_state attached to each basket.
        try:
            _bj_path = fdir / "baskets.json"
            _bj = json.loads(_bj_path.read_text())
            for _b in (_bj.get("baskets") or []):
                _bid = _b.get("id")
                if _bid and _bid in _turn_states:
                    _b["turn_state"] = _turn_states[_bid].get("state", "NONE")
                    _b["turn_dd_252"] = _turn_states[_bid].get("dd_252")
                    _b["turn_hist_d"] = _turn_states[_bid].get("hist_d")
                    _b["turn_slope_20d"] = _turn_states[_bid].get("slope_20d")
                    _b["turn_evidence"] = _turn_states[_bid].get("evidence", [])
            _bj_path.write_text(json.dumps(_bj, separators=(",", ":"), default=str))
        except Exception as _ae:  # noqa: BLE001 — additive
            log.warning("china_basket_turn: baskets.json annotation failed: %s", _ae)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("china_basket_turn organ failed: %s", e)

    # Member conviction signals + cross-basket overlap — computed after turn annotation so
    # turn_state is already on each basket row in `data`. These are additive display features.
    _compute_member_signals(data, site)
    _compute_basket_overlaps(data)

    # Re-write baskets.json to include the newly attached intel + member signals + overlaps.
    # (The turn annotation above already did a re-write from the disk copy; we write on top
    # of `data` in memory which includes member signals and overlaps added since that write.)
    try:
        _bj_path2 = fdir / "baskets.json"
        _bj2 = json.loads(_bj_path2.read_text())
        # Build a lookup from the in-memory data (has sig_tier, ret_5d, top_overlaps, etc.)
        _mem_lookup: dict = {}
        for _b in (data.get("baskets") or []):
            _bid = _b.get("id")
            if _bid:
                _mem_lookup[_bid] = _b
        for _b2 in (_bj2.get("baskets") or []):
            _bid2 = _b2.get("id")
            if not _bid2 or _bid2 not in _mem_lookup:
                continue
            _src = _mem_lookup[_bid2]
            # Copy intel fields
            for _fld in ("score", "label", "label_zh", "reco", "reco_zh",
                         "clean_entry_q", "top_overlaps"):
                if _fld in _src:
                    _b2[_fld] = _src[_fld]
            # Copy member-level signal fields
            _mem_by_sym = {m.get("symbol"): m for m in (_src.get("members") or []) if m.get("symbol")}
            for _m2 in (_b2.get("members") or []):
                _s2 = _m2.get("symbol")
                if _s2 and _s2 in _mem_by_sym:
                    _msrc = _mem_by_sym[_s2]
                    _m2["sig_tier"] = _msrc.get("sig_tier")
                    _m2["sig_fresh"] = _msrc.get("sig_fresh", False)
                    _m2["ret_5d"] = _msrc.get("ret_5d")
        _bj_path2.write_text(json.dumps(_bj2, separators=(",", ":"), default=str))
        log.info("baskets.json: re-wrote with member signals + overlaps")

        # RE-RENDER the page with the fully-merged payload (turn_state + intel +
        # signals + overlaps). The initial render happened before the turn organ
        # by dependency; this second render makes the INLINED payload match the
        # final baskets.json so lifecycle chips + Entry Radar fire (#2829 class).
        try:
            _bj2_render = dict(_bj2)
            # baskets.json still carries the chart subtree (written pre-pop); the page
            # inlines chart separately as CHART — re-inlining it in BASKETS is 235KB
            # of dead payload (review 07-18).
            _bj2_render.pop("chart", None)
            _kb2 = (_render_page(_bj2_render) or 0) // 1024
            log.info("baskets_china.html: re-rendered with turn_state-merged payload (%d KB shipped)", _kb2)
        except Exception as _re:  # noqa: BLE001 — additive; first render already shipped
            log.warning("baskets_china.html re-render failed (first render stands): %s", _re)
    except Exception as _we:  # noqa: BLE001 — additive
        log.warning("baskets.json final re-write failed: %s", _we)

    return 0


if __name__ == "__main__":
    sys.exit(main())
