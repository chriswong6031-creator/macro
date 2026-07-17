"""Build the International comparative dashboard -> site/intl.html (macro) +
site/intl_stocks.html (stocks) + site/intl_stock.html (per-stock search shell).

Standalone like scripts/build_canada.py — shares only the parquet store. Recomputes
the per-country regimes (live == backtest), assembles the cross-country comparison,
the pooled standouts and the flagged sector-rotation board, and renders the dark,
bilingual templates/intl.html.j2 (rendered twice via a `mode` flag). Returns 0 on
ANY engine error so it can never break the macro / vector site builds.

Usage: python -m scripts.build_intl   (run after build_site, before build_vector)
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, site_assets  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_intl")

ASSETS = ("theme.css", "theme.js", "mtf.js", "chart_i18n.js", "charts.js",
          "tablesort.js", "stockdata.js", "stockview.js")

# quad colour keys (match the .q-Qn CSS) — uniform with the other verticals
QUAD_MEANING = {
    "Goldilocks": ("growth ↑ inflation ↓ — risk-on, duration & quality favoured",
                   "增长 ↑ 通胀 ↓ — 偏好风险、久期与质量"),
    "Reflation": ("growth ↑ inflation ↑ — cyclicals, value & commodities favoured",
                  "增长 ↑ 通胀 ↑ — 偏好周期、价值与大宗"),
    "Stagflation": ("growth ↓ inflation ↑ — defensives, energy & real assets",
                    "增长 ↓ 通胀 ↑ — 偏好防御、能源与实物资产"),
    "Growth-scare": ("growth ↓ inflation ↓ — bonds & defensives over equities",
                     "增长 ↓ 通胀 ↓ — 债券与防御优于股票"),
}

# ---- IRD-R8 display shim: iso3 → name/flag for the fragility-map panel --------
# (same idiom as the IRD-W3 _TRANSMITTER_NAMES shim; covers engine.intl_risk._IMF_COUNTRIES)
_VULN_COUNTRY_NAMES: dict[str, dict[str, str]] = {
    "AUS": {"en": "Australia",      "zh": "澳大利亚",   "flag": "🇦🇺"},
    "BRA": {"en": "Brazil",         "zh": "巴西",       "flag": "🇧🇷"},
    "CAN": {"en": "Canada",         "zh": "加拿大",     "flag": "🇨🇦"},
    "CHL": {"en": "Chile",          "zh": "智利",       "flag": "🇨🇱"},
    "CHN": {"en": "China",          "zh": "中国",       "flag": "🇨🇳"},
    "COL": {"en": "Colombia",       "zh": "哥伦比亚",   "flag": "🇨🇴"},
    "DEU": {"en": "Germany",        "zh": "德国",       "flag": "🇩🇪"},
    "EGY": {"en": "Egypt",          "zh": "埃及",       "flag": "🇪🇬"},
    "ESP": {"en": "Spain",          "zh": "西班牙",     "flag": "🇪🇸"},
    "FRA": {"en": "France",         "zh": "法国",       "flag": "🇫🇷"},
    "GBR": {"en": "United Kingdom", "zh": "英国",       "flag": "🇬🇧"},
    "HUN": {"en": "Hungary",        "zh": "匈牙利",     "flag": "🇭🇺"},
    "IDN": {"en": "Indonesia",      "zh": "印尼",       "flag": "🇮🇩"},
    "IND": {"en": "India",          "zh": "印度",       "flag": "🇮🇳"},
    "ITA": {"en": "Italy",          "zh": "意大利",     "flag": "🇮🇹"},
    "JPN": {"en": "Japan",          "zh": "日本",       "flag": "🇯🇵"},
    "KOR": {"en": "South Korea",    "zh": "韩国",       "flag": "🇰🇷"},
    "MEX": {"en": "Mexico",         "zh": "墨西哥",     "flag": "🇲🇽"},
    "MYS": {"en": "Malaysia",       "zh": "马来西亚",   "flag": "🇲🇾"},
    "PHL": {"en": "Philippines",    "zh": "菲律宾",     "flag": "🇵🇭"},
    "POL": {"en": "Poland",         "zh": "波兰",       "flag": "🇵🇱"},
    "THA": {"en": "Thailand",       "zh": "泰国",       "flag": "🇹🇭"},
    "TUR": {"en": "Turkey",         "zh": "土耳其",     "flag": "🇹🇷"},
    "USA": {"en": "United States",  "zh": "美国",       "flag": "🇺🇸"},
    "ZAF": {"en": "South Africa",   "zh": "南非",       "flag": "🇿🇦"},
}


def _enrich_vulnerability(vuln: dict | None) -> dict | None:
    """Annotate vulnerability_table() rows with the display fields the fragility-map
    panel reads (flag emoji, EN/ZH names, plain-word chip tags, one-line desc).

    Analytic keys (iso3, values, raw flag slugs, fragile) are preserved for the
    Tier-2 receipt; enrichment is additive and fail-open per row. Raw engine slugs
    like 'debt>70.0%_rising' never reach the glance tier (Design Doctrine Law 2).
    """
    if not vuln or not vuln.get("countries"):
        return vuln
    for row in vuln["countries"]:
        try:
            iso3 = row.get("iso3", "")
            info = _VULN_COUNTRY_NAMES.get(iso3, {})
            row["cc"] = iso3
            row["flag"] = info.get("flag", "🌐")
            row["name_en"] = info.get("en", iso3)
            row["name_zh"] = info.get("zh", iso3)
            tags: list[dict[str, str]] = []
            for f in row.get("flags") or []:
                if f.startswith("debt>") and row.get("debt_gdp") is not None:
                    tags.append({"en": f"Debt {row['debt_gdp']:.0f}% of GDP & rising",
                                 "zh": f"债务占GDP {row['debt_gdp']:.0f}% 且上升"})
                elif f.startswith("CA<") and row.get("current_account") is not None:
                    tags.append({"en": f"Current account {row['current_account']:+.1f}% of GDP",
                                 "zh": f"经常账户 {row['current_account']:+.1f}% GDP"})
                elif f.startswith("fiscal<") and row.get("fiscal_balance") is not None:
                    tags.append({"en": f"Fiscal balance {row['fiscal_balance']:+.1f}% of GDP",
                                 "zh": f"财政余额 {row['fiscal_balance']:+.1f}% GDP"})
                elif f.startswith("credit_gap>") and row.get("bis_credit_gap") is not None:
                    tags.append({"en": f"Credit gap {row['bis_credit_gap']:.1f}pp above trend",
                                 "zh": f"信用缺口高于趋势 {row['bis_credit_gap']:.1f}pp"})
                else:
                    # future engine flag with no mapping yet — plain words, never the raw slug
                    tags.append({"en": "Structural warning", "zh": "结构性预警"})
            row["tags"] = tags
            n_flags = len(row.get("flags") or [])
            if n_flags:
                row["desc_en"] = f"{n_flags} of 4 structural warnings concurrent"
                row["desc_zh"] = f"4项结构性预警中{n_flags}项并发"
            else:
                row["desc_en"] = "No structural warnings"
                row["desc_zh"] = "无结构性预警"
        except Exception:  # noqa: BLE001 — display shim never blocks the artifact
            continue
    return vuln


def _cgl_compact_summary(artifact: dict | None) -> dict | None:
    """Build compact contagion_links summary for data/intl_risk/latest.json (additive key).

    Returns {as_of, pressure: {mkt: {pct, level}}, top_stressed: [up to 3 mkts by pct]}
    or None when artifact unavailable. CGL-R10 additive-only.
    """
    if not artifact:
        return None
    pressure = artifact.get("pressure") or {}
    pct_map = {}
    for mkt, p in pressure.items():
        pct = p.get("pct")
        if pct is not None:
            pct_map[mkt] = {"pct": pct, "level": p.get("level", "low")}
    top_stressed = sorted(pct_map, key=lambda m: -(pct_map[m]["pct"] or 0.0))[:3]
    return {
        "as_of":       artifact.get("built", "")[:10],
        "pressure":    pct_map,
        "top_stressed": top_stressed,
    }


def main() -> int:
    try:
        from engine.intl_run import run
        latest = run()
    except Exception as e:  # noqa: BLE001 — never break the site build
        log.error("intl engine failed (%s); skipping intl page", e)
        return 0

    # ---- cross-market performance / rotation / rates desks (display-only) ------
    try:                                                # inline SVG sparkline renderer
        from scripts.build_intl_library import _spark_svg
    except Exception:  # noqa: BLE001 — sparklines are decorative; never break the build
        def _spark_svg(*_a, **_k):
            return ""
    perf, rates = None, None
    try:
        from engine import intl_performance
        perf = intl_performance.performance_panel(records=latest["records"])
        for b in (perf.get("leaderboard") or []):
            h = next((b["returns"][k] for k in ("12m", "6m", "3m", "ytd", "1m")
                      if k in b["returns"]), None)
            col = ("var(--up)" if (h and h["usd"] >= 0) else "var(--down)")
            b["spark_svg"] = _spark_svg(b.get("spark") or [], color=col, w=200, h=40)
    except Exception as e:  # noqa: BLE001 — additive, never break the build
        log.error("intl performance panel failed (%s)", e)
    try:
        from engine import intl_rates
        rates = intl_rates.rates_desk(latest["records"])
        for r in (rates.get("rows") or []):
            # neutral accent — the spark plots the 10y *yield* path (not a price
            # direction), so up/down semantics would misread (a rising yield line
            # tinted "down")
            r["spark_svg"] = _spark_svg(r.get("spark") or [], color="var(--link)", w=130, h=34)
        an = rates.get("anchor") or {}
        an["spark_svg"] = _spark_svg(an.get("spark") or [], color="var(--link)", w=200, h=40)
        liq = rates.get("liquidity")
        if liq:
            liq["spark_svg"] = _spark_svg(liq.get("spark") or [],
                                          color=("var(--down)" if liq.get("draining") else "var(--up)"),
                                          w=200, h=40)
    except Exception as e:  # noqa: BLE001
        log.error("intl rates desk failed (%s)", e)

    # ---- IRD-W2: intl_risk composite desk (fail-open per leg) -------------------
    # HOISTED above the page-render try so a template failure does NOT kill the
    # artifact write.  vm['risk_desk'] then just references the computed dict.
    _ird_t0 = time.time()
    em_stress_result = None
    contagion_state = None
    try:
        from engine.intl_risk import em_stress as _em_stress
        em_stress_result = _em_stress()
    except Exception as _e:
        log.error("intl_risk em_stress failed (%s)", _e)

    # IRD-R8 slow fragility map — annual IMF WEO/BIS data, cheap store reads (<1s)
    vulnerability_result = None
    try:
        from engine.intl_risk import vulnerability_table as _vulnerability_table
        vulnerability_result = _enrich_vulnerability(_vulnerability_table())
    except Exception as _e:
        log.error("intl_risk vulnerability_table failed (%s)", _e)

    spillover_result = None
    try:
        from engine.contagion import spillover as _spillover
        spillover_result = _spillover()
    except Exception as _e:
        log.error("contagion spillover failed (%s)", _e)

    corr_result = None
    try:
        from engine.contagion import corr_tightening as _corr_tightening
        corr_result = _corr_tightening()
    except Exception as _e:
        log.error("contagion corr_tightening failed (%s)", _e)

    two_tier_result = None
    try:
        from engine.contagion import two_tier_read as _two_tier_read
        _em_state = (em_stress_result or {}).get("state")
        two_tier_result = _two_tier_read(em_stress_state=_em_state)
        contagion_state = (two_tier_result or {}).get("state")
    except Exception as _e:
        log.error("contagion two_tier_read failed (%s)", _e)

    # CGL W1: contagion_links directed-pressure artifact (fail-open per CGL-R7)
    # Must run AFTER intl_run.run() (radar states available) and on the nightly lane
    # (CGL-R6: ledger_lane_armed() guards history/shadow appends internally).
    # The artifact's per-market pressure blocks are attached to each intl record
    # (rec["contagion"]) and passed to the template as CGL context var.
    _cgl_artifact: dict | None = None
    try:
        from engine import contagion_links as _cgl
        _cgl_artifact = _cgl.snapshot()
        # Attach per-market contagion block to each record
        _cgl_pressure = (_cgl_artifact or {}).get("pressure") or {}
        for _rec in latest.get("records") or []:
            _cc_mkt = _rec.get("cc", "")
            if _cc_mkt in _cgl_pressure:
                _rec["contagion"] = _cgl_pressure[_cc_mkt]
    except Exception as _cgl_e:
        log.warning("contagion_links snapshot failed (fail-open): %s", _cgl_e)

    cb_desk_result = None
    try:
        from engine.cb_desk import snapshot as _cb_snapshot
        cb_desk_result = _cb_snapshot()
    except Exception as _e:
        log.error("cb_desk snapshot failed (%s)", _e)

    inversion_result = None
    try:
        from engine.intl_bonds import inversion_board as _inversion_board
        inversion_result = _inversion_board()
    except Exception as _e:
        log.error("intl_bonds inversion_board failed (%s)", _e)

    # Read smile_decomp from forex/latest.json if fresh (asof today/yesterday).
    # Freshness is judged from the embedded `asof` date, NEVER file mtime — on CI
    # runners a checkout rewrites files with mtime = checkout time, so a frozen
    # forex lane would silently pass an mtime gate forever (the polygon-universe
    # frozen-cache class, #2690). Missing/unparsable asof ⇒ treated stale (skip).
    smile_result = None
    try:
        _forex_path = config.data_dir() / "forex" / "latest.json"
        if _forex_path.exists():
            _forex_raw = json.loads(_forex_path.read_text(encoding="utf-8"))
            _forex_asof = _forex_raw.get("asof")
            try:
                _forex_age_d = (date.today() - date.fromisoformat(str(_forex_asof))).days
            except Exception:  # noqa: BLE001
                _forex_age_d = None
            if _forex_age_d is not None and _forex_age_d <= 1:      # ≈ the old <36h window
                smile_result = (_forex_raw.get("dollar_desk") or {}).get("smile_decomp")
            else:
                log.warning("smile_decomp skipped: forex latest.json asof=%r stale/missing",
                            _forex_asof)
    except Exception as _e:
        log.error("smile_decomp read from forex/latest.json failed (%s)", _e)

    # Read SWPT (Fed swap lines) from FRED store: $M → $bn (same as build_bonds)
    _swap_lines_bn: float | None = None
    try:
        from lib import store as _ird_store
        _swpt_df = _ird_store.read("fred", "SWPT")
        if _swpt_df is not None and not _swpt_df.empty:
            _swpt_val = _swpt_df.iloc[:, 0].dropna()
            if not _swpt_val.empty:
                _swap_lines_bn = round(float(_swpt_val.iloc[-1]) / 1000.0, 1)  # $M → $bn
    except Exception as _e:
        log.error("swap_lines_bn (SWPT) read failed (%s)", _e)

    _ird_elapsed = time.time() - _ird_t0
    print(f"[timing] build_intl intl_risk block: {_ird_elapsed:.2f}s")
    log.info("[timing] build_intl intl_risk block: %.2fs", _ird_elapsed)

    # Assemble intl_risk payload and write to data/intl_risk/latest.json.
    # Written BEFORE the page-render try so template failures cannot kill this artifact.
    _ird_dir = config.data_dir() / "intl_risk"
    _ird_dir.mkdir(parents=True, exist_ok=True)

    # ---- IRD-W3 shim: transmitter display names (ticker→country name EN+ZH) ------
    _TRANSMITTER_NAMES: dict[str, dict[str, str]] = {
        "EWA": {"en": "Australia",     "zh": "澳大利亚", "flag": "🇦🇺"},
        "EWL": {"en": "Switzerland",   "zh": "瑞士",     "flag": "🇨🇭"},
        "EZA": {"en": "South Africa",  "zh": "南非",     "flag": "🇿🇦"},
        "EWJ": {"en": "Japan",         "zh": "日本",     "flag": "🇯🇵"},
        "EWG": {"en": "Germany",       "zh": "德国",     "flag": "🇩🇪"},
        "EWU": {"en": "United Kingdom","zh": "英国",     "flag": "🇬🇧"},
        "EWC": {"en": "Canada",        "zh": "加拿大",   "flag": "🇨🇦"},
        "EWZ": {"en": "Brazil",        "zh": "巴西",     "flag": "🇧🇷"},
        "EWW": {"en": "Mexico",        "zh": "墨西哥",   "flag": "🇲🇽"},
        "INDA": {"en": "India",        "zh": "印度",     "flag": "🇮🇳"},
        "EIDO": {"en": "Indonesia",    "zh": "印尼",     "flag": "🇮🇩"},
        "EWY": {"en": "South Korea",   "zh": "韩国",     "flag": "🇰🇷"},
        "EWT": {"en": "Taiwan",        "zh": "台湾",     "flag": "🇹🇼"},
        "EEM": {"en": "EM Broad",      "zh": "新兴市场",  "flag": "🌏"},
        "SPY": {"en": "United States", "zh": "美国",     "flag": "🇺🇸"},
    }

    # ---- IRD-W3 shim: EMB/IEF ratio spark from emb_ief leg history ----------------
    # emb_ief leg value in em_stress is a ratio; history comes from spillover.
    # We compute a 120d EMB/IEF ratio from the yahoo store (fail-open).
    _emb_ief_spark_svg: str = ""
    try:
        from scripts.build_intl_library import _spark_svg as _w3_spark
        from lib import store as _w3_store
        _emb_df = _w3_store.read("yahoo", "EMB")
        _ief_df = _w3_store.read("yahoo", "IEF")
        if _emb_df is not None and _ief_df is not None and not _emb_df.empty and not _ief_df.empty:
            _emb_s = _emb_df.iloc[:, 0].dropna()
            _ief_s = _ief_df.iloc[:, 0].dropna()
            _ratio = _emb_s.div(_ief_s).dropna().tail(120)
            if len(_ratio) >= 10:
                _emb_ief_spark_svg = _w3_spark(
                    list(_ratio.values), color="var(--info)", w=220, h=38
                )
    except Exception as _w3_e:
        log.warning("IRD-W3 emb_ief spark failed (fail-open): %s", _w3_e)

    # ---- IRD-W3 shim: spillover history spark (total connectedness weekly) --------
    _spillover_spark_svg: str = ""
    try:
        from scripts.build_intl_library import _spark_svg as _w3_spark2
        _sp_hist = (spillover_result or {}).get("history_weekly") or []
        _sp_vals = [row.get("total") for row in _sp_hist[-52:] if row.get("total") is not None]
        if len(_sp_vals) >= 4:
            _spillover_spark_svg = _w3_spark2(
                _sp_vals, color="var(--warn)", w=200, h=34
            )
    except Exception as _w3_e2:
        log.warning("IRD-W3 spillover spark failed (fail-open): %s", _w3_e2)

    # ---- Annotate top_transmitters with display names ---------------------------
    _annotated_transmitters: list[dict] = []
    try:
        for _tx in (spillover_result or {}).get("top_transmitters") or []:
            _tk = _tx.get("ticker", "")
            _info = _TRANSMITTER_NAMES.get(_tk, {})
            _annotated_transmitters.append({
                "ticker": _tk,
                "to_others_pct": _tx.get("to_others_pct"),
                "name_en": _info.get("en", _tk),
                "name_zh": _info.get("zh", _tk),
                "flag": _info.get("flag", ""),
            })
    except Exception as _w3_e3:
        log.warning("IRD-W3 transmitter annotation failed (fail-open): %s", _w3_e3)

    _intl_risk_payload = {
        "built": datetime.now(timezone.utc).isoformat(),
        "timing_sec": round(_ird_elapsed, 2),
        "em_stress": em_stress_result,
        "vulnerability": vulnerability_result,   # IRD-R8 fragility map (display-enriched rows)
        "spillover": spillover_result,
        "corr_tightening": corr_result,
        "two_tier": two_tier_result,
        "cb_desk": cb_desk_result,
        "smile": smile_result,
        "inversion_board": inversion_result,
        # IRD-W2 fix #6: swap_lines_bn at top level so _compose_intl_risk can read it
        "swap_lines_bn": _swap_lines_bn,
        # IRD-W3 shims: display-enriched data for the template surface
        "top_transmitters_display": _annotated_transmitters,
        "emb_ief_spark_svg": _emb_ief_spark_svg,
        "spillover_spark_svg": _spillover_spark_svg,
        # CGL W1: contagion_links compact summary (additive; CGL-R10)
        "contagion_links": _cgl_compact_summary(_cgl_artifact),
    }
    try:
        (_ird_dir / "latest.json").write_text(
            json.dumps(_intl_risk_payload, indent=2, default=str, ensure_ascii=False)
        )
        log.info("wrote data/intl_risk/latest.json (em_stress=%s, contagion=%s, vuln_fragile=%s)",
                 (em_stress_result or {}).get("state"), contagion_state,
                 (vulnerability_result or {}).get("n_fragile"))
    except Exception as _e:
        log.error("failed to write intl_risk/latest.json (%s)", _e)

    # ---- CBF W2: Cross-Border Flow Regime organ (fail-open) ----------------
    # compose() is pure; writes nothing itself.  We write latest.json + advance
    # history.parquet here.  Any exception is logged (NOT swallowed silently —
    # #2316 lesson) and execution continues so this never blocks the render.
    #
    # CBF_INTRADAY=1 is set by sentinel.yml when this runs as part of a flash-
    # state-change intraday rebuild.  In that context we still run compose() and
    # write latest.json (cross-refs are useful), but we SKIP history.parquet
    # accrual — advancing a forward ledger intraday violates CLAUDE.md law
    # ("nightly is the sole advancer of forward ledgers; intraday lanes discard
    # data/ writes").  The sentinel's git-add is already scoped to data/vector/
    # etc and would delete the intraday-written parquet before push anyway, but
    # the run-time mutation and PIT-inconsistent row are still prohibited.
    import os as _os
    _cbf_intraday = _os.environ.get("CBF_INTRADAY", "").strip() not in ("", "0")
    _cbf_dir = config.data_dir() / "flow_regime"
    _cbf_dir.mkdir(parents=True, exist_ok=True)
    try:
        from engine.flow_regime import compose as _cbf_compose, accrue_history as _cbf_accrue
        _cbf_payload = _cbf_compose(repo_root=config.ROOT)
        (_cbf_dir / "latest.json").write_text(
            json.dumps(_cbf_payload, indent=2, default=str, ensure_ascii=False)
        )
        log.info(
            "wrote data/flow_regime/latest.json (regime=%s, disc=%s)",
            (_cbf_payload.get("regime") or {}).get("state"),
            (_cbf_payload.get("discriminator") or {}).get("state"),
        )
        if _cbf_intraday:
            # Intraday context (sentinel flash rebuild): skip forward-ledger advance.
            log.info("flow_regime history accrual SKIPPED (CBF_INTRADAY=1 — nightly only)")
        else:
            # Nightly context: advance history.parquet (CBF-R10).
            # compose() already ran classify_history internally — re-run here is safe
            # because compose() is deterministic and idempotent.  This keeps history
            # accrual decoupled from compose()'s internal history_df.
            try:
                from engine.flow_regime import (
                    load_inputs_from_store as _cbf_load,
                    build_broad_dollar as _cbf_broad,
                    build_emfx_basket as _cbf_emfx,
                    build_row_composite as _cbf_row,
                    classify_history as _cbf_classify,
                )
                _cbf_inputs = _cbf_load()
                _cbf_spy    = _cbf_inputs["spy_close"]
                _cbf_idx    = _cbf_spy.dropna().index
                _cbf_dollar = _cbf_broad(_cbf_inputs.get("dtwexbgs"), _cbf_inputs.get("dxy"), _cbf_idx)
                _cbf_emfx_s = _cbf_emfx(_cbf_inputs.get("fx_series") or {}, _cbf_idx, negate=True)
                _cbf_row_ret = _cbf_row(_cbf_inputs.get("row_etf_closes") or {}, _cbf_idx)
                _cbf_row_lvl = (1 + _cbf_row_ret.fillna(0.0)).cumprod() * 100.0
                _cbf_hist_df = _cbf_classify(
                    spy_close=_cbf_spy,
                    row_composite_level=_cbf_row_lvl,
                    broad_dollar_level=_cbf_dollar,
                    emfx_basket_daily_ret=_cbf_emfx_s,
                    vix_close=_cbf_inputs.get("vix_close"),
                )
                _cbf_accrue(repo_root=config.ROOT, history_df=_cbf_hist_df)
            except Exception as _cbf_hist_exc:
                log.exception("flow_regime history accrual failed (non-fatal): %s", _cbf_hist_exc)
    except Exception as _cbf_exc:
        log.exception("flow_regime compose/write failed (non-fatal): %s", _cbf_exc)

    # ---- ITR W1: turn board + rotation ranks (fail-open, hoisted pre-render) -------
    # Computed BEFORE the page-render try so a turn-engine error never kills the
    # page render (mirrors the IRD-W3 shim pattern above).
    turn_board: list | None = None
    turn_events: list = []
    rotation_ranks: list = []
    bench_note: str | None = None

    try:
        from engine import intl_inputs as _itr_inputs
        _itr_closes_raw = _itr_inputs._intl_closes()
        _itr_countries = _itr_inputs.countries()

        # Build a cc->Series dict (primary index only) for the rotation engine
        _itr_closes: dict[str, "pd.Series"] = {}
        for _cc, _c in _itr_countries.items():
            _idx_col = _c["index"]
            if _idx_col in _itr_closes_raw:
                _s = _itr_closes_raw[_idx_col].dropna()
                if not _s.empty:
                    _itr_closes[_cc] = _s

        # Fetch a fresh benchmark via the ITR-R6 helper in intl_performance
        _itr_bench: "pd.Series | None" = None
        if perf is not None:
            _itr_bench = perf.get("bench")
            bench_note = perf.get("bench_note")
        else:
            try:
                from engine.intl_performance import _bench_series_fresh as _itr_bf
                _itr_bench, bench_note = _itr_bf(intl_closes=_itr_closes_raw)
            except Exception as _e:
                log.warning("ITR bench freshness helper failed (fail-open): %s", _e)

        # Compute per-market turn states
        _itr_states: dict[str, dict] = {}
        try:
            from engine.intl_market_state import market_states as _itr_ms
            _itr_states = _itr_ms(_itr_closes, bench=_itr_bench)
        except Exception as _e:
            log.warning("intl_market_state.market_states failed (fail-open): %s", _e)

        # Compute rotation ranks
        try:
            from engine.intl_rotation import rank as _itr_rank
            _raw_ranks = _itr_rank(_itr_closes, _itr_bench, _itr_states)
            # Enrich with name/name_zh/flag from countries config
            for _rr in _raw_ranks:
                _cc2 = _rr.get("cc", "")
                _meta = _itr_countries.get(_cc2, {})
                _rr["name"]     = _meta.get("name", _cc2)
                _rr["name_zh"]  = _meta.get("name_zh", _cc2)
                _rr["flag"]     = _meta.get("flag", "")
            rotation_ranks = _raw_ranks
        except Exception as _e:
            log.warning("intl_rotation.rank failed (fail-open): %s", _e)

        # Leading-risk radar (#2684, schema risk_radar_intl.v1) joined onto its turn
        # tile by cc — display-only context; never feeds urgency sort or rank.
        _radar_by_cc = {
            (_r.get("cc") or ""): _r.get("risk_radar")
            for _r in (latest.get("records") or [])
            if isinstance(_r.get("risk_radar"), dict)
        }

        # Build turn_board: urgency-sorted (desc), ties by dd_pct ascending
        if _itr_states:
            _tb_rows = []
            for _cc3, _st in _itr_states.items():
                _meta3 = _itr_countries.get(_cc3, {})
                _row = dict(_st)
                _row["cc"]       = _cc3
                _row["name"]     = _meta3.get("name", _cc3)
                _row["name_zh"]  = _meta3.get("name_zh", _cc3)
                _row["flag"]     = _meta3.get("flag", "")
                _row["risk_radar"] = _radar_by_cc.get(_cc3)
                _tb_rows.append(_row)
            turn_board = sorted(
                _tb_rows,
                key=lambda r: (-r.get("urgency", 0), r.get("dd_pct", 0) or 0),
            )

        # Build turn_events: top 10 newest cross-market events
        _all_events = []
        for _cc4, _st4 in _itr_states.items():
            _meta4 = _itr_countries.get(_cc4, {})
            for _ev in (_st4.get("events") or []):
                _all_events.append({
                    "date":     _ev.get("date"),
                    "cc":       _cc4,
                    "flag":     _meta4.get("flag", ""),
                    "name":     _meta4.get("name", _cc4),
                    "name_zh":  _meta4.get("name_zh", _cc4),
                    "en":       _ev.get("en", ""),
                    "zh":       _ev.get("zh", ""),
                    "code":     _ev.get("code", ""),
                })
        # Dedup by (date, cc, code) then sort newest first and take top 10
        _seen_evkeys: set = set()
        _dedup_events = []
        for _ev2 in _all_events:
            _evkey = (_ev2.get("date") or "", _ev2.get("cc", ""), _ev2.get("code", ""))
            if _evkey not in _seen_evkeys:
                _seen_evkeys.add(_evkey)
                _dedup_events.append(_ev2)
        _dedup_events.sort(key=lambda e: e.get("date") or "", reverse=True)
        turn_events = _dedup_events[:10]

        # Attach record['turn'] = per-country market_states dict for each country record
        for _rec in latest.get("records") or []:
            _cc5 = _rec.get("cc", "")
            if _cc5 in _itr_states:
                _rec["turn"] = _itr_states[_cc5]

        # Attach turn state to each leaderboard row too: the template hero KPI
        # (bestr.get('turn')) and the leaderboard JS (turnLookup / stateChip)
        # read `turn` off perf.leaderboard rows, not off latest.records.
        if perf is not None:
            for _lb_row in (perf.get("leaderboard") or []):
                _cc6 = _lb_row.get("cc", "")
                if _cc6 in _itr_states:
                    _lb_row["turn"] = _itr_states[_cc6]

        log.info(
            "ITR turn engine: %d states, %d events, bench_note=%s",
            len(_itr_states), len(turn_events), bench_note,
        )
    except Exception as _itr_exc:
        log.error("ITR turn engine block failed (fail-open): %s", _itr_exc)

    try:
        from engine import intl_stocks
        closes, members = intl_stocks.panel()
        alpha = None
        try:
            alpha = intl_stocks.compute_intl_alpha(closes, members)
        except Exception as e:  # noqa: BLE001 — additive
            log.error("intl alpha failed (%s)", e)
        board = []
        try:
            board = intl_stocks.sector_board()
        except Exception as e:  # noqa: BLE001
            log.error("intl sector board failed (%s)", e)

        # per-stock library + pooled standouts shortlist
        setups = None
        try:
            from scripts import build_intl_library
            setups = build_intl_library.main(alpha=alpha)
        except Exception as e:  # noqa: BLE001 — additive
            log.error("intl stock library failed (%s)", e)

        for r in latest["records"]:
            r["quad_meaning"] = QUAD_MEANING.get(r.get("quad_name"))

        # the raw benchmark Series is engine-internal — it must never reach the
        # template ({{ perf | tojson }} cannot serialize a pd.Series)
        if isinstance(perf, dict):
            perf.pop("bench", None)

        vm = {
            "latest": latest,
            "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "records": latest["records"],
            "summary": latest["summary"],
            "rankings": latest.get("rankings", {}),
            "heatmap": latest.get("heatmap", []),
            "periphery": latest.get("periphery"),
            "sector_board": board,
            "setups": setups,
            "perf": perf,
            "rates": rates,
            # risk_desk available to template (None-safe: may be partial on engine error)
            "risk_desk": _intl_risk_payload,
            # CGL W1: full artifact for the directed contagion table (templates guard {% if CGL %})
            "CGL": _cgl_artifact,
            # ITR W1: turn engine keys (None/[] when engine errors)
            "turn_board":     turn_board,
            "turn_events":    turn_events,
            "rotation_ranks": rotation_ranks,
            "bench_note":     bench_note,
        }

        site = Path(config.load()["storage"]["site_dir"])
        site.mkdir(parents=True, exist_ok=True)
        env = Environment(loader=FileSystemLoader(
            str(Path(__file__).resolve().parent.parent / "templates")), autoescape=False)
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)

        tmpl = env.get_template("intl.html.j2")
        write_page(site / "intl.html", tmpl.render(**vm, mode="macro"))
        write_page(site / "intl_stocks.html", tmpl.render(**vm, mode="stocks"))
        log.info("wrote intl.html + intl_stocks.html (%d economies, %d standouts)",
                 vm["summary"]["n"], len((setups or {}).get("buy") or []))

        # per-stock search shell
        try:
            from engine.cycles import STATE_DISPLAY
            shell = env.get_template("intl_stock.html.j2").render(
                state_display_json=json.dumps(STATE_DISPLAY, default=str), generated_utc=vm["built"])
            write_page(site / "intl_stock.html", shell)
        except Exception as e:  # noqa: BLE001 — search additive
            log.error("intl stock shell render failed (%s)", e)

        for a in ASSETS:
            src = Path(config.ROOT) / "templates" / a
            if src.exists():
                site_assets.copy_asset(a, src, site)

        # landing-hub card stat (presence-gated by the .html existing)
        s = vm["summary"]
        idir = config.data_dir() / "intl"
        idir.mkdir(parents=True, exist_ok=True)
        _hub_payload = {
            "date": latest.get("date", ""),
            "label": f"{s['n']} economies · {s['dominant_quad']}",
            "recession_watch": s.get("recession_watch", 0),
            # IRD-W2 additive keys for hub.json
            "em_stress_state": (em_stress_result or {}).get("state"),
            "contagion_state": contagion_state,
        }
        (idir / "hub.json").write_text(json.dumps(_hub_payload, indent=2))
    except Exception as e:  # noqa: BLE001
        log.error("intl page render failed (%s); skipping", e)
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
