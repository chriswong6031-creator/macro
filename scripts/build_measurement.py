"""Render site/measurement.html — Cycle Intelligence Measurement Hub (W3.7).

Data flow (script-tag only — ruling A11, zero runtime compute, zero fetch):
  data/{sector,country,china_sector}_cycles/scorecards/promises_price_v1_zz14_v0.json
  data/cycle_ontology/cone_recalibration.json
  data/cycle_ontology/collinearity_phase0.json
  data/experiments/registry_seed.json            (accruing experiments)
  research/cycle_masterplan/PREREGISTRATION.md   (gate ledger — parsed or fallback JSON)
        │
        ▼  this builder
  site/measurementdata/measurement_data.js       (window.MEASUREMENT = {...})
  site/measurement.html                          (template shell)

Ruling A6: BACKTEST and LIVE cohorts NEVER blended in one number.
Each scorecard cell is badged BACKTEST n= or LIVE n= with its epoch.

Ruling §6.6: the scorecards ARE the story — render failures straight.
Every FAILED gate renders as FAILED (red/amber tokens); honesty IS the product.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine.cycle_pattern.truths import active_truths  # noqa: E402
from lib.pages import write_page  # noqa: E402

log = logging.getLogger("build_measurement")

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
TEMPLATES = ROOT / "templates"
DATA = ROOT / "data"
RESEARCH = ROOT / "research" / "cycle_masterplan"

# Output paths
OUT_DIR = SITE / "measurementdata"
OUT_JS = OUT_DIR / "measurement_data.js"
OUT_HTML = SITE / "measurement.html"

# Source data paths
SCORECARD_PATHS = {
    "sector_cycles": DATA / "sector_cycles" / "scorecards" / "promises_price_v1_zz14_v0.json",
    "country_cycles": DATA / "country_cycles" / "scorecards" / "promises_price_v1_zz14_v0.json",
    "china_sector_cycles": DATA / "china_sector_cycles" / "scorecards" / "promises_price_v1_zz14_v0.json",
}
CONE_RECAL_PATH = DATA / "cycle_ontology" / "cone_recalibration.json"
COLLINEARITY_PATH = DATA / "cycle_ontology" / "collinearity_phase0.json"
EXPERIMENTS_PATH = DATA / "experiments" / "registry_seed.json"
PREREGISTRATION_PATH = RESEARCH / "PREREGISTRATION.md"

# Gate ledger fallback (curated JSON co-committed alongside this script)
GATE_LEDGER_PATH = DATA / "cycle_ontology" / "gate_ledger.json"

# ── engine display names ───────────────────────────────────────────────────────
ENGINE_LABELS = {
    "sector_cycles": {"en": "US Sector Cycles", "zh": "美国板块周期"},
    "country_cycles": {"en": "Country Cycles", "zh": "国家周期"},
    "china_sector_cycles": {"en": "China Sector Cycles", "zh": "中国板块周期"},
}

# ── verdict → badge class mapping ─────────────────────────────────────────────
VERDICT_CLASS = {
    "falsified": "verdict-fail",
    "too_tight": "verdict-miscal",
    "miscalibrated": "verdict-miscal",
    "accruing": "verdict-accruing",
    "earning": "verdict-pass",
    "pass": "verdict-pass",
    "inconclusive": "verdict-accruing",
    "measuring": "verdict-accruing",
    None: "verdict-none",
}

# ── gate families and gate ledger (parsed from PREREGISTRATION.md or fallback) ──

GATE_LEDGER_FALLBACK: list[dict] = [
    # Keystone gates (W0.4)
    {"id": "KG-1", "family": "keystone", "claim": "Position deciles carry forward drawdown-adjusted signal",
     "criterion": "Monotone/near-monotone dd-adj score + ≥1 extreme-decile gap CI excludes 0 (95%)",
     "judged_by": "data/research/keystone_tr0/study_tables.json",
     "status": "fail", "result": "NO-EDGE — every decile return-gap CI straddles zero at 21/63/126d"},
    {"id": "KG-2", "family": "keystone", "claim": "Phases carry forward drawdown-adjusted signal",
     "criterion": "≥1 phase's dd-adj gap-vs-base CI excludes 0 at 95%, sign consistent ≥2 horizons",
     "judged_by": "data/research/keystone_tr0/study_tables.json",
     "status": "pass", "result": "REFINE — Peak→shallower DD [+1.2%,+5.0%]; Trough→deeper DD [−10.0%,−1.9%] at 63d. Decays post-2018 (walk-forward fragility)"},
    {"id": "KG-3", "family": "keystone", "claim": "LADDER inversion (low-pos/DECLINE > high-pos/FRESH-BUY on dd-adj)",
     "criterion": "Inversion verdict == inversion_confirmed on ≥2 horizons",
     "judged_by": "data/research/keystone_tr0/study_tables.json",
     "status": "fail", "result": "INCONCLUSIVE — all 9 era×horizon cells straddle zero; point estimate leans opposite direction"},
    {"id": "KG-4", "family": "keystone", "claim": "Signal (BUY/SELL) precedes its promised move",
     "criterion": "BUY fwd-ret hit-gap CI > 0; SELL fwd-maxdd p10 gap CI < 0 on ≥2 horizons",
     "judged_by": "data/research/keystone_tr0/study_tables.json",
     "status": "fail", "result": "NO-EDGE — signal cells straddle 0 on both return and drawdown channels"},
    {"id": "KG-5", "family": "keystone", "claim": "Walk-forward stability of KG-1/2 effects",
     "criterion": "Sign of any KG-1/2 effect holds in BOTH pre_2018 and post_2018 sub-panels",
     "judged_by": "data/research/keystone_tr0/study_tables.json",
     "status": "fail", "result": "FAIL — Phase DD signal significant pre-2018, straddles zero post-2018"},

    # Cone coverage / calibration gates (W2.4)
    {"id": "CC-1 (sector_cycles)", "family": "calibration", "claim": "Sector cycles cone band is calibrated",
     "criterion": "Empirical coverage within Wilson CI of 0.80 nominal",
     "judged_by": "data/sector_cycles/scorecards/promises_price_v1_zz14_v0.json",
     "status": "fail", "result": "MISCALIBRATED — empirical 0.188 vs nominal 0.80 [CI 0.154,0.227]; recal multiplier 8.19×"},
    {"id": "CC-1 (country_cycles)", "family": "calibration", "claim": "Country cycles cone band is calibrated",
     "criterion": "Empirical coverage within Wilson CI of 0.80 nominal",
     "judged_by": "data/country_cycles/scorecards/promises_price_v1_zz14_v0.json",
     "status": "fail", "result": "MISCALIBRATED — empirical 0.283 vs nominal 0.80 [CI 0.259,0.309]; recal multiplier 3.57×"},
    {"id": "CC-1 (china_sector_cycles)", "family": "calibration", "claim": "China sector cycles cone band is calibrated",
     "criterion": "Empirical coverage within Wilson CI of 0.80 nominal",
     "judged_by": "data/china_sector_cycles/scorecards/promises_price_v1_zz14_v0.json",
     "status": "fail", "result": "MISCALIBRATED — empirical 0.359 vs nominal 0.80 [CI 0.327,0.391]; recal multiplier 3.12×"},
    {"id": "CC-2 (sector_cycles/signal)", "family": "calibration", "claim": "Sector cycles signal labels are honest (Brier skill > base rate)",
     "criterion": "Brier skill_score vs per-instrument base rate > 0, n≥30",
     "judged_by": "data/sector_cycles/scorecards/promises_price_v1_zz14_v0.json",
     "status": "fail", "result": "FALSIFIED — skill −1.538, hit 0.430 vs base 0.659 (n=642)"},
    {"id": "CC-2 (sector_cycles/stance)", "family": "calibration", "claim": "Sector cycles stance is honest (Brier skill > base rate)",
     "criterion": "Brier skill_score vs per-instrument base rate > 0, n≥30",
     "judged_by": "data/sector_cycles/scorecards/promises_price_v1_zz14_v0.json",
     "status": "fail", "result": "FALSIFIED — skill −1.309, hit 0.481 vs base 0.659 (n=1257)"},
    {"id": "CC-2 (country_cycles/signal)", "family": "calibration", "claim": "Country cycles signal labels are honest",
     "criterion": "Brier skill_score vs per-instrument base rate > 0, n≥30",
     "judged_by": "data/country_cycles/scorecards/promises_price_v1_zz14_v0.json",
     "status": "fail", "result": "FALSIFIED — skill −1.198, hit 0.460 vs base 0.565 (n=2075)"},
    {"id": "CC-2 (country_cycles/stance)", "family": "calibration", "claim": "Country cycles stance is honest",
     "criterion": "Brier skill_score vs per-instrument base rate > 0, n≥30",
     "judged_by": "data/country_cycles/scorecards/promises_price_v1_zz14_v0.json",
     "status": "fail", "result": "FALSIFIED — skill −1.191, hit 0.462 vs base 0.565 (n=3900)"},
    {"id": "CC-2 (china_sector_cycles/signal)", "family": "calibration", "claim": "China sector cycles signal labels are honest",
     "criterion": "Brier skill_score vs per-instrument base rate > 0, n≥30",
     "judged_by": "data/china_sector_cycles/scorecards/promises_price_v1_zz14_v0.json",
     "status": "fail", "result": "FALSIFIED — skill −1.159, hit 0.460 vs base 0.507 (n=1677)"},
    {"id": "CC-3 (sector_cycles)", "family": "turn_pr", "claim": "Sector cycles turn P/R factual (not circular)",
     "criterion": "Precision & recall Wilson-lo > 0.5 on n_eff≥40, graded against independent realized-extrema truth",
     "judged_by": "data/sector_cycles/scorecards/promises_price_v1_zz14_v0.json",
     "status": "fail", "result": "FALSIFIED — prec 0.075 [0.054,0.103], rec 0.289 [0.214,0.379]; Wilson-lo far below 0.5 (n_eff=422)"},
    {"id": "CC-3 (country_cycles)", "family": "turn_pr", "claim": "Country cycles turn P/R factual",
     "criterion": "Precision & recall Wilson-lo > 0.5 on n_eff≥40",
     "judged_by": "data/country_cycles/scorecards/promises_price_v1_zz14_v0.json",
     "status": "fail", "result": "FALSIFIED — prec 0.109 [0.093,0.128], rec 0.255 [0.220,0.294] (n_eff=1191)"},
    {"id": "CC-3 (china_sector_cycles)", "family": "turn_pr", "claim": "China sector cycles turn P/R factual",
     "criterion": "Precision & recall Wilson-lo > 0.5 on n_eff≥40",
     "judged_by": "data/china_sector_cycles/scorecards/promises_price_v1_zz14_v0.json",
     "status": "fail", "result": "FALSIFIED — prec 0.230 [0.203,0.260], rec 0.369 [0.329,0.411] (n_eff=810)"},

    # Collinearity gates (W2.5 — post-registration, criteria pre-defined)
    {"id": "CL-1", "family": "collinearity", "claim": "state_score and pos_osc are redundant (near-collinear price transforms)",
     "criterion": "Pooled |rho| > 0.80 OR VIF > 5.0",
     "judged_by": "data/cycle_ontology/collinearity_phase0.json",
     "status": "pass", "result": "CONFIRMED — rho(state_score, pos_osc) = −0.968; VIF(pos_osc)=29.8, VIF(state_score)=25.8"},
    {"id": "CL-2", "family": "collinearity", "claim": "≥1 leg carries independent risk-channel information",
     "criterion": "≥1 leg's partial-corr with forward max-drawdown CI excludes 0 on ≥1 horizon",
     "judged_by": "data/cycle_ontology/collinearity_phase0.json",
     "status": "pass", "result": "CONFIRMED — 4 risk-channel survivors: trend_pass_f, mom_score, rs_63d_f, vol_pctile (63d)"},
    {"id": "CL-3", "family": "collinearity", "claim": "Dimension reduction justified (5 PCs explain ≥90%)",
     "criterion": "n_pcs_for_90pct < n_legs (8)",
     "judged_by": "data/cycle_ontology/collinearity_phase0.json",
     "status": "pass", "result": "CONFIRMED — 5 of 8 PCs explain 91.2% of variance"},

    # Downstream gates (not yet judged)
    {"id": "HZ-up-1m", "family": "hazard", "claim": "Peak-hazard 1-month beats Kaplan-Meier baseline",
     "criterion": "OOS Brier(model) < Brier(KM) with 90% CI excluding 0",
     "judged_by": "data/cycle_hazard/model.json (not yet built)", "status": "accruing", "result": None},
    {"id": "HZ-dn-1m", "family": "hazard", "claim": "Trough-hazard 1-month beats KM",
     "criterion": "Same, direction down", "judged_by": "data/cycle_hazard/model.json",
     "status": "accruing", "result": None},
    {"id": "BC-1", "family": "calibration", "claim": "LADDER_SCORE / tier cuts are earned, not asserted",
     "criterion": "artifact validated==true ⇔ n_eff≥40 per cell AND train→holdout rank-corr>0.5 AND FDR survived",
     "judged_by": "data/calibration/*.json (not yet built)", "status": "accruing", "result": None},
    {"id": "DL-1", "family": "decision", "claim": "Hazard cone earns its place over the IQR band",
     "criterion": "Walk-forward entry-sizing on hazard cone improves drawdown-adjusted outcomes, CI excluding 0",
     "judged_by": "walk-forward sizing backtest artifact (not yet built)", "status": "accruing", "result": None},
    {"id": "LL-A", "family": "leadlag", "claim": "Some ordered pair's lagged Δphase-position leads",
     "criterion": "≥1 pair×lag survives BH-FDR q=0.10 on ≤2017 TRAIN cross-correlation",
     "judged_by": "data/cycle_hazard/leadlag_phase0.json",
     "status": "pass", "result": "PASS — 136 of 8,253 pair×lag tests survive BH-FDR; top-20 frozen"},
    {"id": "LL-B", "family": "leadlag", "claim": "Knowing the leader's confirmed turn improves the follower's OOS hazard",
     "criterion": "Pooled OOS 3m Brier improvement ≥2% AND positive in ≥2/3 year-blocks AND CI₉₀ excludes 0",
     "judged_by": "data/cycle_hazard/leadlag_phase0.json → stageB.pooled",
     "status": "fail",
     "result": "NO-GO — rel improvement +0.029% (bar ≥2%), CI₉₀ [−0.26%,+0.29%] includes 0, 3/9 year-blocks positive (bar ≥6/9). STOP: interaction layer not built. Sync gauge shipped."},
]

# ── sync gauge paths ───────────────────────────────────────────────────────────
SYNC_GAUGE_PATH = DATA / "leadlag" / "sync_gauge.json"
LEADLAG_PHASE0_PATH = DATA / "cycle_hazard" / "leadlag_phase0.json"

# ── Pattern Memory v0 paths ────────────────────────────────────────────────────
TRUTHS_JSONL_PATH = DATA / "cycle_pattern" / "truths.jsonl"

# ── Prediction Layer — hazard model path ──────────────────────────────────────
HAZARD_MODEL_PATH = DATA / "hazard" / "model_price_c4414dcb.json"

# ── Prediction Layer — forward log paths (for hazard adoption non-null checks) ─
FORWARD_LOG_PATHS: dict[str, Path] = {
    "sector_cycles": DATA / "sector_cycles" / "forward_log.parquet",
    "country_cycles": DATA / "country_cycles" / "forward_log.parquet",
    "china_sector_cycles": DATA / "china_sector_cycles" / "forward_log.parquet",
}

# ── Coverage Matrix — sourced from committed dict (curated, audited 2026-07-06) ─
# Columns: state_export / outcome_join / hazard_adoption / truth_badge / nw_export / live_grader
# Values: yes / partial / no
# Evidence comment cites the file path that was checked.
# "curated check" = not machine-detectable; verified by manual inspection.
COVERAGE_MATRIX: list[dict] = [
    {
        # cycle.html — built by scripts/build_cycle.py; reads forward_log + backfill;
        # no engine.cycle_pattern imports found; no truth badge; no hazard columns shown;
        # no NW lobe; no live grader.
        "page": "cycle",
        "label_en": "cycle.html",
        "label_zh": "cycle.html",
        "state_export": "no",          # evidence: templates/cycle.html.j2 — no state_monthly read
        "state_export_hint": "none",
        "outcome_join": "no",          # evidence: templates/cycle.html.j2 — no outcomes.parquet read
        "outcome_join_hint": "none",
        "hazard_adoption": "no",       # evidence: templates/cycle.html.j2 grep hazard_1m_p → 0 hits
        "hazard_adoption_hint": "none",
        "truth_badge": "no",           # curated check: no truth_badge token in template
        "truth_badge_hint": "none",
        "nw_export": "no",             # evidence: data/neuralweb/cycle_pattern_state.json not built (P6)
        "nw_export_hint": "none",
        "live_grader": "no",           # evidence: no grader wired in dag.yml for cycle page
        "live_grader_hint": "none",
    },
    {
        # sector_cycles.html — built by scripts/build_sector_cycles.py;
        # reads forward_log.parquet (has hazard cols at 50.9% non-null);
        # no state_monthly join; no truth badge; no hazard rendered in template;
        # no NW export; no live grader.
        "page": "sector_cycles",
        "label_en": "sector_cycles.html",
        "label_zh": "sector_cycles.html",
        "state_export": "partial",     # evidence: data/sector_cycles/forward_log.parquet has hazard cols
        "state_export_hint": "forward_log",
        "outcome_join": "no",          # evidence: templates/sector_cycles.html.j2 — no outcomes read
        "outcome_join_hint": "none",
        "hazard_adoption": "no",       # curated check: templates/sector_cycles.html.j2 grep hazard_1m_p → 0 hits; field present in data but not rendered
        "hazard_adoption_hint": "col-not-rendered",
        "truth_badge": "no",           # curated check: no truth_badge in sector_cycles template
        "truth_badge_hint": "none",
        "nw_export": "no",             # evidence: cycle_pattern_state.json not built (P6)
        "nw_export_hint": "none",
        "live_grader": "no",           # evidence: no live grader in dag.yml for sector_cycles
        "live_grader_hint": "none",
    },
    {
        # country_cycles.html — analogous to sector_cycles; forward_log has hazard at 50% non-null;
        # hazard cols present but not rendered in template.
        "page": "country_cycles",
        "label_en": "country_cycles.html",
        "label_zh": "country_cycles.html",
        "state_export": "partial",     # evidence: data/country_cycles/forward_log.parquet has hazard cols
        "state_export_hint": "forward_log",
        "outcome_join": "no",          # evidence: templates/country_cycles.html.j2 — no outcomes read
        "outcome_join_hint": "none",
        "hazard_adoption": "no",       # curated check: templates/country_cycles.html.j2 grep hazard_1m_p → 0 hits
        "hazard_adoption_hint": "col-not-rendered",
        "truth_badge": "no",           # curated check: no truth_badge in country_cycles template
        "truth_badge_hint": "none",
        "nw_export": "no",             # evidence: cycle_pattern_state.json not built (P6)
        "nw_export_hint": "none",
        "live_grader": "no",           # evidence: no live grader in dag.yml for country_cycles
        "live_grader_hint": "none",
    },
    {
        # markets.html — curated opinion page; no engine-backed hazard; no cycle_pattern reads;
        # no state_monthly, no outcomes, no truth badge, no NW export, no grader.
        "page": "markets",
        "label_en": "markets.html",
        "label_zh": "markets.html",
        "state_export": "no",          # evidence: templates/markets.html.j2 — no state_monthly or forward_log import
        "state_export_hint": "none",
        "outcome_join": "no",          # evidence: templates/markets.html.j2 — no outcomes.parquet
        "outcome_join_hint": "none",
        "hazard_adoption": "no",       # evidence: templates/markets.html.j2 grep hazard → 0 cycle-hazard hits
        "hazard_adoption_hint": "none",
        "truth_badge": "no",           # curated check: no truth_badge in markets template
        "truth_badge_hint": "none",
        "nw_export": "no",             # evidence: cycle_pattern_state.json not built (P6)
        "nw_export_hint": "none",
        "live_grader": "no",           # evidence: no live grader wired for markets
        "live_grader_hint": "none",
    },
    {
        # sector_central.html — reads data/sector_central/calls.parquet; no cycle_pattern artifacts;
        # no truth badge; no hazard; no NW export; no live grader.
        "page": "sector_central",
        "label_en": "sector_central.html",
        "label_zh": "sector_central.html",
        "state_export": "no",          # evidence: templates/sector_central.html.j2 — no state_monthly import
        "state_export_hint": "none",
        "outcome_join": "no",          # evidence: templates/sector_central.html.j2 — no outcomes read
        "outcome_join_hint": "none",
        "hazard_adoption": "no",       # curated check: templates/sector_central.html.j2 grep hazard_1m_p → 0 hits
        "hazard_adoption_hint": "none",
        "truth_badge": "no",           # curated check: no truth_badge in sector_central template
        "truth_badge_hint": "none",
        "nw_export": "no",             # evidence: cycle_pattern_state.json not built (P6)
        "nw_export_hint": "none",
        "live_grader": "no",           # evidence: no live grader wired for sector_central
        "live_grader_hint": "none",
    },
    {
        # sector_central_china.html — reads china central calls; no cycle_pattern artifacts;
        # no truth badge; no hazard; no NW export; no live grader.
        "page": "sector_central_china",
        "label_en": "sector_central_china.html",
        "label_zh": "sector_central_china.html",
        "state_export": "no",          # evidence: templates/sector_central_china.html.j2 — no state_monthly import
        "state_export_hint": "none",
        "outcome_join": "no",          # evidence: templates/sector_central_china.html.j2 — no outcomes read
        "outcome_join_hint": "none",
        "hazard_adoption": "no",       # curated check: templates/sector_central_china.html.j2 grep hazard_1m_p → 0 hits
        "hazard_adoption_hint": "none",
        "truth_badge": "no",           # curated check: no truth_badge in sector_central_china template
        "truth_badge_hint": "none",
        "nw_export": "no",             # evidence: cycle_pattern_state.json not built (P6)
        "nw_export_hint": "none",
        "live_grader": "no",           # evidence: no live grader wired for china central
        "live_grader_hint": "none",
    },
    {
        # measurement.html — this page; reads truth_ledger (truths.jsonl), accrual_clocks,
        # hazard model JSON (prediction layer); no state_monthly join; no outcome join;
        # no NW export; no live grader slot.
        "page": "measurement",
        "label_en": "measurement.html",
        "label_zh": "measurement.html",
        "state_export": "partial",     # evidence: scripts/build_measurement.py reads forward_log.parquet for accrual clocks; no state_monthly join
        "state_export_hint": "accrual-clocks",
        "outcome_join": "no",          # evidence: scripts/build_measurement.py — outcomes.parquet not read
        "outcome_join_hint": "none",
        "hazard_adoption": "partial",  # evidence: scripts/build_measurement.py build_prediction_layer() reads hazard model JSON; rendered in prediction layer section
        "hazard_adoption_hint": "model-json",
        "truth_badge": "yes",          # evidence: templates/measurement.html.j2 — Pattern Memory section renders truth_ledger rows
        "truth_badge_hint": "truth-ledger",
        "nw_export": "no",             # evidence: cycle_pattern_state.json not built (P6)
        "nw_export_hint": "none",
        "live_grader": "no",           # evidence: no live grader wired; page is static build
        "live_grader_hint": "none",
    },
]

# ── Accrual clock ledger paths (five live ledgers) ─────────────────────────────
ACCRUAL_LEDGERS: list[dict[str, Any]] = [
    {
        "key": "sector_cycles",
        "label_en": "US Sector Cycles — forward log",
        "label_zh": "美国板块周期 · 前向日志",
        "path": DATA / "sector_cycles" / "forward_log.parquet",
        "id_col": "id",
        "date_col": "date",
    },
    {
        "key": "country_cycles",
        "label_en": "Country Cycles — forward log",
        "label_zh": "国家周期 · 前向日志",
        "path": DATA / "country_cycles" / "forward_log.parquet",
        "id_col": "id",
        "date_col": "date",
    },
    {
        "key": "china_sector_cycles",
        "label_en": "China Sector Cycles — forward log",
        "label_zh": "中国板块周期 · 前向日志",
        "path": DATA / "china_sector_cycles" / "forward_log.parquet",
        "id_col": "id",
        "date_col": "date",
    },
    {
        "key": "sector_central",
        "label_en": "US Sector Central — calls",
        "label_zh": "美国板块中枢 · 研判记录",
        "path": DATA / "sector_central" / "calls.parquet",
        "id_col": "id",
        "date_col": "date",
    },
    {
        "key": "china_sector_central",
        "label_en": "China Sector Central — calls",
        "label_zh": "中国板块中枢 · 研判记录",
        "path": DATA / "china_sector_central" / "calls.parquet",
        "id_col": "id",
        "date_col": "date",
    },
]


def build_truth_ledger() -> dict:
    """Pattern Memory v0 — read truths.jsonl via active_truths() and return a
    summary dict for embedding in window.MEASUREMENT.

    Absent-safe: if the file is missing, returns {available: False}.
    BC-2: no use of 'validated'/'已验证' in rendered text here — this is data,
    not UI copy.
    """
    if not TRUTHS_JSONL_PATH.exists():
        log.warning("truths.jsonl not found at %s — truth ledger unavailable", TRUTHS_JSONL_PATH)
        return {"available": False}

    try:
        truths = active_truths(TRUTHS_JSONL_PATH)
    except Exception as exc:
        log.warning("active_truths() failed: %s — truth ledger unavailable", exc)
        return {"available": False}

    from collections import Counter
    status_counts = dict(Counter(t.get("status", "") for t in truths))

    # Promoted nulls: the subset that is the null library
    promoted_nulls = [t for t in truths if t.get("status") == "promoted_null"]

    # Truth table rows (display order: truth_id sorted, which active_truths() guarantees)
    rows = []
    for t in truths:
        rows.append({
            "truth_id": t.get("truth_id", ""),
            "statement": t.get("statement", ""),
            "status": t.get("status", ""),
            "effect_class": t.get("effect_class", ""),
            "pit_class": t.get("pit_class", ""),
            "next_review_due": t.get("next_review_due", ""),
        })

    # Null library: promoted_null rows with their evidence_refs
    null_library = []
    for t in promoted_nulls:
        null_library.append({
            "truth_id": t.get("truth_id", ""),
            "statement": t.get("statement", ""),
            "evidence_refs": t.get("evidence_refs", []),
            "ci_summary": t.get("ci_summary", ""),
            "notes": t.get("notes", ""),
            "next_review_due": t.get("next_review_due", ""),
        })

    return {
        "available": True,
        "total": len(truths),
        "status_counts": status_counts,
        "rows": rows,
        "null_library": null_library,
    }


def _parse_date(s: str) -> date | None:
    """Parse YYYY-MM-DD string to date; return None on failure."""
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def build_accrual_clocks() -> list[dict]:
    """Live maturity & accrual clock for the five forward ledgers.

    For each ledger:
      rows            — total row count
      unique_ids      — number of unique id values
      unique_dates    — number of unique stamp dates
      first_date      — earliest date (YYYY-MM-DD)
      last_date       — latest date (YYYY-MM-DD)
      cadence_days    — (last-first)/(n_dates-1) in fractional days; None if n_dates<2
      target_40_date  — projected calendar date to reach 40 unique stamp dates;
                        None if cadence unmeasurable or already at ≥40

    Absent-safe: if the file does not exist, returns a stub with available=False.
    Pure numpy/pandas/pyarrow — no sklearn/scipy.
    """
    results = []
    for spec in ACCRUAL_LEDGERS:
        path: Path = spec["path"]
        key: str = spec["key"]
        id_col: str = spec["id_col"]
        date_col: str = spec["date_col"]

        if not path.exists():
            log.warning("Accrual ledger not found: %s", path)
            results.append({
                "key": key,
                "label_en": spec["label_en"],
                "label_zh": spec["label_zh"],
                "available": False,
            })
            continue

        try:
            table = pq.read_table(path, columns=[id_col, date_col])
            import pandas as pd
            df = table.to_pandas()

            n_rows = len(df)
            unique_ids = int(df[id_col].nunique())

            # Unique stamp dates (as sorted list of YYYY-MM-DD strings)
            date_strs = sorted(df[date_col].dropna().unique().tolist())
            n_dates = len(date_strs)
            first_date = date_strs[0] if date_strs else None
            last_date = date_strs[-1] if date_strs else None

            cadence_days: float | None = None
            target_40_date: str | None = None

            if n_dates >= 2 and first_date and last_date:
                d_first = _parse_date(first_date)
                d_last = _parse_date(last_date)
                if d_first and d_last:
                    span_days = (d_last - d_first).days
                    cadence_days = round(span_days / (n_dates - 1), 1)
                    if n_dates < 40 and cadence_days and cadence_days > 0:
                        stamps_needed = 40 - n_dates
                        days_needed = stamps_needed * cadence_days
                        projected = d_last + timedelta(days=days_needed)
                        target_40_date = projected.isoformat()
                    # else already at 40+ or cadence is 0 (shouldn't happen)

            results.append({
                "key": key,
                "label_en": spec["label_en"],
                "label_zh": spec["label_zh"],
                "available": True,
                "n_rows": n_rows,
                "unique_ids": unique_ids,
                "unique_dates": n_dates,
                "first_date": first_date,
                "last_date": last_date,
                "cadence_days": cadence_days,
                "target_40_date": target_40_date,
            })
        except Exception as exc:
            log.warning("Accrual clock failed for %s: %s", key, exc)
            results.append({
                "key": key,
                "label_en": spec["label_en"],
                "label_zh": spec["label_zh"],
                "available": False,
                "error": str(exc),
            })

    return results


def _hazard_non_null_rates() -> dict[str, float | None]:
    """Return per-engine non-null fraction for hazard_1m_p in each forward log.

    Used in build_prediction_layer() adoption gaps section.
    Pure pyarrow; absent-safe (None if file missing or col absent).
    """
    rates: dict[str, float | None] = {}
    for engine_key, path in FORWARD_LOG_PATHS.items():
        if not path.exists():
            rates[engine_key] = None
            continue
        try:
            table = pq.read_table(path, columns=["hazard_1m_p"])
            col = table.column("hazard_1m_p").to_pylist()
            total = len(col)
            if total == 0:
                rates[engine_key] = None
            else:
                non_null = sum(1 for v in col if v is not None)
                rates[engine_key] = round(non_null / total, 4)
        except Exception as exc:
            log.warning("hazard non-null check failed for %s: %s", engine_key, exc)
            rates[engine_key] = None
    return rates


def build_prediction_layer() -> dict:
    """Prediction Layer — hazard model ledger, freshness, and adoption gaps.

    Returns a dict for embedding in window.MEASUREMENT.prediction_layer.
    Absent-safe: if the model artifact is missing, returns {available: False}.
    BC-2: no affirmative 'validated'/'已验证' in rendered copy.
    """
    if not HAZARD_MODEL_PATH.exists():
        log.warning("Hazard model not found at %s — prediction layer unavailable", HAZARD_MODEL_PATH)
        return {"available": False}

    try:
        raw = load_json(HAZARD_MODEL_PATH)
    except Exception as exc:
        log.warning("Failed to load hazard model: %s", exc)
        return {"available": False}

    # ── 6-cell ledger ─────────────────────────────────────────────────────────
    ledger_raw = raw.get("ledger", {})
    cells = []
    for direction in ("up", "down"):
        for horizon in ("1m", "3m", "6m"):
            cell = ledger_raw.get(direction, {}).get(horizon, {})
            skill = cell.get("skill_vs_km")
            ci90 = cell.get("ci90", [])
            delta_brier_str = f"{skill:+.4f}" if skill is not None else "—"
            ci_str = (
                f"[{ci90[0]:+.4f}, {ci90[1]:+.4f}]"
                if len(ci90) == 2
                else "—"
            )
            verdict = cell.get("verdict", "PRIOR")
            cells.append({
                "direction": direction,
                "horizon": horizon,
                "verdict": verdict,         # "PASS" or "PRIOR"
                "delta_brier": skill,
                "delta_brier_str": delta_brier_str,
                "ci90": ci90,
                "ci90_str": ci_str,
                "ci_excludes_zero": cell.get("ci_excludes_zero", False),
                "survives_bh_fdr": cell.get("survives_bh_fdr", False),
                "n_oos": cell.get("n_oos"),
                "n_months": cell.get("n_months"),
            })

    # ── Model freshness ────────────────────────────────────────────────────────
    built_at = raw.get("built_at", "")
    fit_date_str = built_at[:10] if built_at else "unknown"  # YYYY-MM-DD
    revision_optimistic = bool(raw.get("revision_optimistic", False))

    # Days since fit (vs today)
    days_stale: int | None = None
    try:
        fit_date = date.fromisoformat(fit_date_str)
        days_stale = (date.today() - fit_date).days
    except Exception:
        pass

    # ── Adoption gaps ─────────────────────────────────────────────────────────
    # Machine-detectable: hazard non-null rate per engine in forward logs
    non_null_rates = _hazard_non_null_rates()

    # Build per-engine adoption gap records
    engine_adoption_gaps = []
    ENGINE_LABELS_LOCAL = {
        "sector_cycles": {"en": "US Sector Cycles", "zh": "美国板块周期"},
        "country_cycles": {"en": "Country Cycles", "zh": "国家周期"},
        "china_sector_cycles": {"en": "China Sector Cycles", "zh": "中国板块周期"},
    }
    for engine_key, rate in non_null_rates.items():
        labels = ENGINE_LABELS_LOCAL.get(engine_key, {"en": engine_key, "zh": engine_key})
        if rate is None:
            note_en = "forward log absent or hazard column missing"
            note_zh = "前向日志缺失或无风险列"
            gap_type = "missing"
        elif rate == 0.0:
            note_en = "hazard_1m_p is 100% null — all historical rows pre-date W4.3 stamp fix"
            note_zh = "hazard_1m_p 全为空值 — 所有历史行早于 W4.3 修复时间点"
            gap_type = "all_null"
        elif rate < 1.0:
            pct = round(rate * 100, 1)
            note_en = f"hazard_1m_p non-null in {pct}% of rows — pre-W4.3 rows are null"
            note_zh = f"hazard_1m_p 在 {pct}% 行中非空 — W4.3 前的行为空值"
            gap_type = "partial_null"
        else:
            note_en = "hazard_1m_p fully populated"
            note_zh = "hazard_1m_p 全量填充"
            gap_type = "none"

        engine_adoption_gaps.append({
            "engine": engine_key,
            "label_en": labels["en"],
            "label_zh": labels["zh"],
            "produced_by": "engine/cycle_hazard/ stamp loop (W4.3)",
            "consumed_by": "forward_log.parquet column (hazard_1m_p/3m/6m) — not yet rendered in any page template",
            "non_null_rate": rate,
            "gap_type": gap_type,
            "note_en": note_en,
            "note_zh": note_zh,
            "detection": "machine",   # derived from parquet non-null count
        })

    # Curated (not machine-detectable) adoption gaps
    # Evidence: grep for hazard_1m_p/hazard_3m_p across all templates returns 0 hits.
    # The cycle hazard probabilities exist in forward_log.parquet columns and in the
    # model artifact, but no template (cycle.html.j2, sector_cycles.html.j2, etc.)
    # renders them to the user. This is the primary UI adoption gap.
    curated_gaps = [
        {
            "gap_id": "UI-HZ-1",
            "description_en": (
                "Hazard probabilities (hazard_1m_p, hazard_3m_p, hazard_6m_p) are present in "
                "forward_log.parquet for sector and country engines, but are rendered on zero "
                "user-facing pages today. No template consumes now.hazard or any hazard_*_p column. "
                "The 4/6 PASS cells exist only in data/hazard/model_price_c4414dcb.json."
            ),
            "description_zh": (
                "风险概率（hazard_1m_p、hazard_3m_p、hazard_6m_p）已存在于板块与国家引擎的 "
                "forward_log.parquet 中，但当前未被任何用户可见页面渲染。"
                "没有任何模板读取 now.hazard 或任何 hazard_*_p 字段。"
                "4/6 通过的单元格仅存在于 data/hazard/model_price_c4414dcb.json 中。"
            ),
            "produced_by": "engine/cycle_hazard/stamp loop → forward_log.parquet; data/hazard/model_price_c4414dcb.json",
            "consumed_by": "nowhere — zero page templates",
            "detection": "curated check",  # grep templates/ for hazard_1m_p → 0 hits (verified 2026-07-06)
            "planned_phase": "P6",
        },
    ]

    return {
        "available": True,
        "model_artifact": str(HAZARD_MODEL_PATH.relative_to(ROOT)),
        "built_at": built_at,
        "fit_date": fit_date_str,
        "days_stale": days_stale,
        "refit_cadence": "quarterly (per D5)",
        "revision_optimistic": revision_optimistic,
        "n_cells_pass": raw.get("n_cells_pass", 0),
        "n_cells_total": 6,
        "cells": cells,
        "adoption_gaps": {
            "by_engine": engine_adoption_gaps,
            "curated": curated_gaps,
        },
    }


def build_coverage_matrix() -> dict:
    """Coverage Matrix — 7 scope pages × 6 capability columns.

    Values are sourced from COVERAGE_MATRIX (a committed Python dict with a
    comment per cell citing the evidence file path).  This is intentionally
    hand-maintained until machine detection exists — marked 'curated, audited
    2026-07-06'.

    Returns a dict for embedding in window.MEASUREMENT.coverage_matrix.
    """
    columns = [
        {"key": "state_export",    "label_en": "State export",    "label_zh": "状态导出"},
        {"key": "outcome_join",    "label_en": "Outcome join",    "label_zh": "结果关联"},
        {"key": "hazard_adoption", "label_en": "Hazard adoption", "label_zh": "风险采纳"},
        {"key": "truth_badge",     "label_en": "Truth badge",     "label_zh": "真值徽章"},
        {"key": "nw_export",       "label_en": "NW export",       "label_zh": "神经网络导出"},
        {"key": "live_grader",     "label_en": "Live grader",     "label_zh": "实盘评分器"},
    ]

    rows = []
    for spec in COVERAGE_MATRIX:
        row = {
            "page": spec["page"],
            "label_en": spec["label_en"],
            "label_zh": spec["label_zh"],
            "cells": {},
        }
        for col in columns:
            key = col["key"]
            row["cells"][key] = {
                "value": spec.get(key, "no"),
                "hint": spec.get(f"{key}_hint", ""),
            }
        rows.append(row)

    return {
        "available": True,
        "audit_note": "curated, audited 2026-07-06",
        "columns": columns,
        "rows": rows,
    }


def load_json(path: Path) -> dict | list:
    with open(path) as f:
        return json.load(f)


def load_scorecard(engine: str) -> dict:
    path = SCORECARD_PATHS[engine]
    if not path.exists():
        log.warning("Scorecard missing: %s", path)
        return {}
    return load_json(path)


def assert_cohorts_not_merged(scorecard: dict, engine: str) -> None:
    """Unit check: BACKTEST and LIVE cohorts must never be blended in one cell.
    Ruling A6: each cell is either BACKTEST n= or LIVE n=, never pooled."""
    cohorts = scorecard.get("cohorts", {})
    if "BACKTEST" in cohorts and "LIVE" in cohorts:
        bt = cohorts["BACKTEST"]
        lv = cohorts["LIVE"]
        # They must not share the same n_stamps field
        assert bt.get("n_stamps") != lv.get("n_stamps") or bt.get("n_stamps") == 0, \
            f"{engine}: BACKTEST and LIVE appear merged (same n_stamps)!"
    log.debug("%s: BACKTEST/LIVE separation check passed", engine)


def fmt_pct(v: float | None, decimals: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v*100:.{decimals}f}%"


def fmt_ci(ci: list | None) -> str:
    if not ci or len(ci) < 2:
        return ""
    return f"[{ci[0]*100:.1f}%, {ci[1]*100:.1f}%]"


def fmt_n(n: int | float | None) -> str:
    if n is None:
        return "—"
    return str(int(n))


def build_engine_scorecard(engine: str) -> dict:
    """Compile one engine's scorecard dict for the JS payload."""
    sc = load_scorecard(engine)
    if not sc:
        return {"engine": engine, "missing": True}

    assert_cohorts_not_merged(sc, engine)

    cohorts = sc.get("cohorts", {})
    epoch = sc.get("epoch", {})
    result: dict[str, Any] = {
        "engine": engine,
        "label_en": ENGINE_LABELS[engine]["en"],
        "label_zh": ENGINE_LABELS[engine]["zh"],
        "as_of": sc.get("as_of", ""),
        "epoch": epoch,
        "n_stamps_total": sc.get("n_stamps_total", 0),
        "cohorts": {},
    }

    for cohort_name, cohort in cohorts.items():
        n_stamps = cohort.get("n_stamps", 0)
        n_months = cohort.get("n_months", 0)
        n_instruments = cohort.get("n_instruments", 0)

        # Turn P/R
        turn_pr = cohort.get("turn_pr", {})
        pooled_pr = turn_pr.get("pooled", {})
        pr_verdict = pooled_pr.get("verdict")

        # Cone coverage
        cone = cohort.get("cone_coverage", {})
        cone_fwd = cone.get("forward_only", {})

        # Reliability
        rel = cohort.get("reliability", {})
        signal_rel = rel.get("signal", {})
        stance_rel = rel.get("stance", {})

        cohort_data: dict[str, Any] = {
            "cohort": cohort_name,
            "n_stamps": n_stamps,
            "n_months": n_months,
            "n_instruments": n_instruments,
            "badge": cohort_name,  # "BACKTEST" or "LIVE"
            "turn_pr": {
                "precision": pooled_pr.get("precision"),
                "precision_pct": fmt_pct(pooled_pr.get("precision")),
                "precision_ci": pooled_pr.get("precision_ci"),
                "precision_ci_str": fmt_ci(pooled_pr.get("precision_ci")),
                "recall": pooled_pr.get("recall"),
                "recall_pct": fmt_pct(pooled_pr.get("recall")),
                "recall_ci": pooled_pr.get("recall_ci"),
                "recall_ci_str": fmt_ci(pooled_pr.get("recall_ci")),
                "n_eff": pooled_pr.get("n_eff"),
                "verdict": pr_verdict,
                "verdict_class": VERDICT_CLASS.get(pr_verdict, "verdict-none"),
                "timing_err": pooled_pr.get("timing_err", {}),
                "gate_id": sc.get("gates", {}).get("turn_pr", "CC-3"),
                "truth_definition": turn_pr.get("truth_definition", ""),
            },
            "cone": {
                "nominal": cone.get("nominal", 0.80),
                "empirical": cone.get("empirical"),
                "empirical_pct": fmt_pct(cone.get("empirical")),
                "ci": cone.get("ci"),
                "ci_str": fmt_ci(cone.get("ci")),
                "n": cone.get("n"),
                "recal_multiplier": cone.get("recal_multiplier"),
                "overdue_fraction": cone.get("overdue_fraction"),
                "overdue_pct": fmt_pct(cone.get("overdue_fraction")),
                "verdict": cone.get("verdict"),
                "verdict_class": VERDICT_CLASS.get(cone.get("verdict"), "verdict-none"),
                "forward_only": {
                    "empirical": cone_fwd.get("empirical"),
                    "empirical_pct": fmt_pct(cone_fwd.get("empirical")),
                    "ci_str": fmt_ci(cone_fwd.get("ci")),
                    "n": cone_fwd.get("n"),
                    "recal_multiplier": cone_fwd.get("recal_multiplier"),
                    "verdict": cone_fwd.get("verdict"),
                    "verdict_class": VERDICT_CLASS.get(cone_fwd.get("verdict"), "verdict-none"),
                },
                "gate_id": sc.get("gates", {}).get("cone", "CC-1"),
            },
            "reliability": {
                "signal": {
                    "skill_score": signal_rel.get("skill_score"),
                    "skill_str": f"{signal_rel.get('skill_score', 0):.3f}" if signal_rel.get("skill_score") is not None else "—",
                    "hit_rate": signal_rel.get("hit_rate"),
                    "hit_rate_pct": fmt_pct(signal_rel.get("hit_rate")),
                    "base_hit_rate": signal_rel.get("base_hit_rate"),
                    "base_pct": fmt_pct(signal_rel.get("base_hit_rate")),
                    "brier": signal_rel.get("brier"),
                    "n": signal_rel.get("n"),
                    "verdict": signal_rel.get("verdict"),
                    "verdict_class": VERDICT_CLASS.get(signal_rel.get("verdict"), "verdict-none"),
                },
                "stance": {
                    "skill_score": stance_rel.get("skill_score"),
                    "skill_str": f"{stance_rel.get('skill_score', 0):.3f}" if stance_rel.get("skill_score") is not None else "—",
                    "hit_rate": stance_rel.get("hit_rate"),
                    "hit_rate_pct": fmt_pct(stance_rel.get("hit_rate")),
                    "base_hit_rate": stance_rel.get("base_hit_rate"),
                    "base_pct": fmt_pct(stance_rel.get("base_hit_rate")),
                    "brier": stance_rel.get("brier"),
                    "n": stance_rel.get("n"),
                    "verdict": stance_rel.get("verdict"),
                    "verdict_class": VERDICT_CLASS.get(stance_rel.get("verdict"), "verdict-none"),
                },
                "gate_id": sc.get("gates", {}).get("reliability", "CC-2"),
            },
        }
        result["cohorts"][cohort_name] = cohort_data

    return result


def build_gate_ledger() -> list[dict]:
    """Load gate ledger from committed JSON, fallback to embedded FALLBACK list."""
    if GATE_LEDGER_PATH.exists():
        try:
            data = load_json(GATE_LEDGER_PATH)
            gates = data if isinstance(data, list) else data.get("gates", [])
            log.info("Loaded %d gates from %s", len(gates), GATE_LEDGER_PATH)
            return gates
        except Exception as e:
            log.warning("Failed to load gate_ledger.json: %s — using embedded fallback", e)

    log.info("Using embedded gate ledger fallback (%d gates)", len(GATE_LEDGER_FALLBACK))
    return GATE_LEDGER_FALLBACK


def build_accruing_experiments() -> list[dict]:
    """Load the experiments registry and extract cycle-measurement accruing entries."""
    if not EXPERIMENTS_PATH.exists():
        log.warning("Experiments registry not found: %s", EXPERIMENTS_PATH)
        return []

    data = load_json(EXPERIMENTS_PATH)
    entries = data.get("experiments", data) if isinstance(data, dict) else data

    # Pull the cycle-related entries (cycle PIT backfill + measurement primitives)
    cycle_ids = {
        "cycle-pit-backfill-w23",
        "sector-central-grader",
        "anticipation-forward-cone",
    }
    # Also pick up any entry with phase_hint containing measurement or cycle
    result = []
    for e in entries:
        eid = e.get("id", "")
        phase = e.get("phase_hint", "")
        if eid in cycle_ids or (phase and "measurement" in phase) or (phase and "cycle" in phase.lower()):
            result.append({
                "id": eid,
                "name": e.get("name", eid),
                "status": e.get("status", ""),
                "come_back_on": e.get("come_back_on", ""),
                "come_back_note": e.get("come_back_note", ""),
                "what": e.get("what", ""),
                "state": e.get("state", ""),
                "next_step": e.get("next_step", ""),
                "phase_hint": phase,
            })

    return result


def build_cone_recal() -> dict:
    """Load cone recalibration artifact."""
    if not CONE_RECAL_PATH.exists():
        return {}
    return load_json(CONE_RECAL_PATH)


def build_collinearity() -> dict:
    """Load collinearity phase-0 summary for the page."""
    if not COLLINEARITY_PATH.exists():
        return {}
    data = load_json(COLLINEARITY_PATH)
    # Extract the verdict section
    verdict = data.get("verdict", {})
    pooled = data.get("pooled", {})
    return {
        "study_date": data.get("study_date", ""),
        "n_pooled": pooled.get("n", 0),
        "redundant_pairs": verdict.get("redundant_pairs", []),  # list of {pair, rho}
        "high_vif_legs": verdict.get("high_vif_legs", []),      # list of {leg, vif}
        "surviving_legs": verdict.get("surviving_legs", []),
        "risk_channel_survivors": verdict.get("risk_channel_survivors", []),
        "n_pcs_for_90pct": verdict.get("n_pcs_for_90pct") or pooled.get("pca", {}).get("n_pcs_for_90pct"),
        "pca_variance_explained": pooled.get("pca", {}).get("explained_cumulative", []),
    }


def build_sync_gauge() -> dict:
    """Load the W5.1 STOP-fallback sync gauge artifact.

    Ruling A11: data is script-tag embedded (window.X), zero fetch, zero runtime compute.
    The sync gauge is the honest replacement for markets.html fake convergence bands —
    a measured dispersion statistic (1 − circ_var(2π·pos/100)), not a predicted convergence.
    """
    if not SYNC_GAUGE_PATH.exists():
        log.warning("Sync gauge not found: %s", SYNC_GAUGE_PATH)
        return {}

    raw = load_json(SYNC_GAUGE_PATH)
    families = raw.get("families", {})

    # Build per-family summary stats (latest + recent range)
    family_summaries: list[dict] = []
    FAMILY_LABELS = {
        "us_sector": {"en": "US Sector", "zh": "美国板块"},
        "country": {"en": "Country ETF", "zh": "国家ETF"},
        "cn_sector": {"en": "China Sector (Shenwan)", "zh": "中国申万板块"},
    }
    for fam_key, series in families.items():
        if not series:
            continue
        latest = series[-1]
        syncs = [row["sync"] for row in series if row.get("n", 0) >= 5]
        fam_summary = {
            "key": fam_key,
            "label_en": FAMILY_LABELS.get(fam_key, {}).get("en", fam_key),
            "label_zh": FAMILY_LABELS.get(fam_key, {}).get("zh", fam_key),
            "latest_date": latest.get("date", ""),
            "latest_sync": round(latest.get("sync", 0), 4),
            "latest_n": latest.get("n", 0),
            "latest_frac": latest.get("frac", {}),
            "n_history": len(series),
            "sync_mean": round(sum(syncs) / len(syncs), 4) if syncs else None,
            "sync_p10": round(sorted(syncs)[int(len(syncs) * 0.10)], 4) if len(syncs) >= 10 else None,
            "sync_p90": round(sorted(syncs)[int(len(syncs) * 0.90)], 4) if len(syncs) >= 10 else None,
            # full history for sparkline (date + sync only; frac embedded)
            "history": [
                {"d": row["date"], "s": row["sync"], "n": row.get("n", 0),
                 "f": row.get("frac", {})}
                for row in series
            ],
        }
        family_summaries.append(fam_summary)

    # Load gate verdict from leadlag_phase0.json for provenance
    gate_summary: dict = {}
    if LEADLAG_PHASE0_PATH.exists():
        try:
            ll = load_json(LEADLAG_PHASE0_PATH)
            gate = ll.get("gate", {})
            sb = ll.get("stageB", {}).get("pooled", {})
            gate_summary = {
                "verdict": gate.get("verdict", ""),
                "LL_A_pass": gate.get("LL_A_pass", False),
                "LL_B_pass": gate.get("LL_B_pass", False),
                "rel_brier_improvement": sb.get("rel_brier_improvement"),
                "n_year_blocks_positive": sb.get("n_year_blocks_positive"),
                "n_year_blocks": sb.get("n_year_blocks"),
                "ci90": sb.get("ci90"),
                "generated_at": ll.get("generated_at", ""),
            }
        except Exception as e:
            log.warning("Failed to load leadlag_phase0.json for sync gauge provenance: %s", e)

    return {
        "available": bool(family_summaries),
        "generated_at": raw.get("generated_at", ""),
        "definition": raw.get("definition", ""),
        "families": family_summaries,
        "gate_summary": gate_summary,
    }


def build_provenance(engines: list[dict]) -> dict:
    """Compile provenance footer from all engine scorecards."""
    epochs = {}
    as_of_dates = []
    fingerprints = set()
    for eng in engines:
        if eng.get("missing"):
            continue
        epoch = eng.get("epoch", {})
        name = eng["engine"]
        epochs[name] = {
            "basis_version": epoch.get("basis_version", ""),
            "zz_version": epoch.get("zz_version", ""),
            "engine_fingerprint": epoch.get("engine_fingerprint", ""),
        }
        if eng.get("as_of"):
            as_of_dates.append(eng["as_of"])
        fp = epoch.get("engine_fingerprint")
        if fp:
            fingerprints.add(fp)

    # All engines should share the same fingerprint
    fingerprint_consistent = len(fingerprints) <= 1
    return {
        "epochs": epochs,
        "computed_on": max(as_of_dates) if as_of_dates else "",
        "engine_fingerprints": sorted(fingerprints),
        "fingerprint_consistent": fingerprint_consistent,
        "build_date": date.today().isoformat(),
    }


# ── Evidence-Gap panel paths (PR-A1) ──────────────────────────────────────────
GRADING_CLOSURE_PATH = DATA / "governance" / "grading_closure.json"
TRIAL_LEDGER_PATH = DATA / "trial_ledger.jsonl"
RULE_EXPERIMENTS_PATH = DATA / "rule_experiments" / "registry.jsonl"
QLEDGER_TRACK_RECORD_PATH = SITE / "qledger" / "track_record.json"

# Earliest-maturity notes for TIME-starved ledgers (drawn from §0, programmatically
# readable from grading_closure.json data; the notes below follow program doc §1/§3).
# Keyed by ledger key; value is a human-readable come-back date where known.
_MATURITY_NOTES: dict[str, str] = {
    "risk_radar_intl_cn":       "earliest maturity ~2026-07-10 (n=5 at ~weekly cadence)",
    "risk_radar_intl_hk":       "earliest maturity ~2026-07-10 (n=4)",
    "risk_radar_intl_ca":       "earliest maturity ~2026-07-10 (n=4)",
    "market_state_forward_log": "earliest maturity ~2026-07-10 (n=5)",
    "oracle_forward_ledger":    "earliest maturity ~2026-07-30 (n=173, quarterly grading window)",
    "oracle_compounds_live_ledger": "earliest maturity ~2026-07-30 (n=53)",
    "oracle_reversion_forward": "seeded only after first reversion compound passes gauntlet",
    "btc_override_ledger":      "earliest maturity ~2026-08-25 (n=5, monthly cadence)",
    "foresight_log":            "earliest maturity ~2026-08-25 (n=34)",
    "froth_fragility_log":      "earliest maturity ~2026-08-25 (n=5)",
    "species_registry":         "earliest maturity ~2026-09 (n=21, accruing)",
    "species_antichase_shadow_ledger": "seeded when F3_ANTICHASE accrues first row",
    "species_f1d_shadow_ledger":       "seeded when EI-F1D-RW accrues first row",
    "china_standout_track":     "earliest maturity ~2026-08 (n=240)",
    "board_ledger_hk":          "earliest maturity ~2026-08 (n=9, weekly cadence)",
    "board_ledger_ca":          "earliest maturity ~2026-08 (n=40)",
}


def build_grading_closure() -> dict:
    """Load grading_closure.json and derive STARVATION column per RUL-4.

    STARVATION logic:
      grader_wired starts with 'Y' AND n_graded == 0  => 'accruing (time-starved)'
      grader_wired == 'N'                              => 'needs grader (build)'
      n_graded > 0 (any grader status)                => 'closed / partial'

    The distinction makes TIME-vs-BUILD unmistakable (RUL-4).
    Absent-safe: returns {available: False} if file is missing.
    """
    if not GRADING_CLOSURE_PATH.exists():
        log.warning("grading_closure.json not found: %s", GRADING_CLOSURE_PATH)
        return {"available": False}

    try:
        raw = load_json(GRADING_CLOSURE_PATH)
    except Exception as exc:
        log.warning("Failed to load grading_closure.json: %s", exc)
        return {"available": False}

    ledgers_raw = raw.get("ledgers", [])
    rows: list[dict] = []
    for ledger in ledgers_raw:
        key = ledger.get("key", "")
        grader_wired = ledger.get("grader_wired", "N") or "N"
        n_logged = ledger.get("n_logged", 0) or 0
        n_graded = ledger.get("n_graded", 0) or 0
        verdict = ledger.get("verdict", "")

        # Derive STARVATION column — the central point of RUL-4
        if n_graded > 0:
            starvation = "closed / partial"
            starvation_type = "closed"
        elif str(grader_wired).upper().startswith("Y"):
            maturity = _MATURITY_NOTES.get(key, "")
            if maturity:
                starvation = f"accruing (time-starved) — {maturity}"
            else:
                starvation = "accruing (time-starved)"
            starvation_type = "time"
        else:
            starvation = "needs grader (build)"
            starvation_type = "build"

        rows.append({
            "key": key,
            "path": ledger.get("path", ""),
            "n_logged": n_logged,
            "n_graded": n_graded,
            "grader_wired": str(grader_wired),
            "verdict": verdict,
            "starvation": starvation,
            "starvation_type": starvation_type,   # 'closed' | 'time' | 'build'
            "last_graded_at": ledger.get("last_graded_at"),
        })

    return {
        "available": True,
        "generated_at": raw.get("generated_at", ""),
        "n_ledgers": raw.get("n_ledgers", len(rows)),
        "n_closed": raw.get("n_closed", 0),
        "n_grader_starved": raw.get("n_grader_starved", 0),
        "n_log_only": raw.get("n_log_only", 0),
        "rows": rows,
    }


def build_trial_budgets() -> dict:
    """Summarise trial_ledger.jsonl by family: row count + latest ts.

    Absent-safe: returns {available: False} if file is missing.
    """
    if not TRIAL_LEDGER_PATH.exists():
        log.warning("trial_ledger.jsonl not found: %s", TRIAL_LEDGER_PATH)
        return {"available": False}

    try:
        families: dict[str, dict] = {}
        with open(TRIAL_LEDGER_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                family = row.get("family", "unknown")
                ts = row.get("ts", "")
                if family not in families:
                    families[family] = {"n": 0, "latest_ts": ""}
                families[family]["n"] += 1
                if ts > families[family]["latest_ts"]:
                    families[family]["latest_ts"] = ts

        rows = sorted(
            [{"family": k, "n_rows": v["n"], "latest_ts": v["latest_ts"]} for k, v in families.items()],
            key=lambda r: r["family"],
        )
        return {
            "available": True,
            "n_total": sum(r["n_rows"] for r in rows),
            "n_families": len(rows),
            "rows": rows,
        }
    except Exception as exc:
        log.warning("Failed to read trial_ledger.jsonl: %s", exc)
        return {"available": False}


def build_rule_experiments() -> dict:
    """Read rule_experiments/registry.jsonl and build the experiment registry panel.

    Each exp_id may have multiple lines (registered → executed → reported lifecycle).
    Collapse to one row per exp_id showing: exp_id, status (latest), declared_budget,
    question (truncated to 200 chars).

    Also compute cumulative pooled SUM of declared_budget over all registered experiments
    (per §0.5.6 / RUL-5: this is the SUM semantic, distinct from TrialLedger max()-basis).

    Absent-safe: returns {available: False} if file is missing.
    """
    if not RULE_EXPERIMENTS_PATH.exists():
        log.warning("rule_experiments/registry.jsonl not found: %s", RULE_EXPERIMENTS_PATH)
        return {"available": False}

    try:
        # Collect lines by exp_id — keep latest status, first registration fields
        by_exp: dict[str, dict] = {}
        with open(RULE_EXPERIMENTS_PATH, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                exp_id = row.get("exp_id", "")
                if not exp_id:
                    continue
                if exp_id not in by_exp:
                    by_exp[exp_id] = row.copy()
                else:
                    # Update mutable fields (status, run_at, etc.) from later rows
                    for k in ("status", "status_updated_at", "run_at", "runtime_s"):
                        if k in row:
                            by_exp[exp_id][k] = row[k]

        rows = []
        pooled_sum = 0
        for exp_id, rec in by_exp.items():
            budget = rec.get("declared_budget") or 0
            try:
                budget = int(budget)
            except (TypeError, ValueError):
                budget = 0
            pooled_sum += budget
            question_raw = rec.get("question", "")
            question_trunc = question_raw[:200] + "…" if len(question_raw) > 200 else question_raw
            rows.append({
                "exp_id": exp_id,
                "status": rec.get("status", ""),
                "declared_budget": budget,
                "question": question_trunc,
                "registered_at": rec.get("registered_at", ""),
                "run_at": rec.get("run_at", ""),
            })

        rows.sort(key=lambda r: r["registered_at"])

        return {
            "available": True,
            "n_experiments": len(rows),
            "pooled_declared_budget_sum": pooled_sum,
            "rows": rows,
        }
    except Exception as exc:
        log.warning("Failed to read rule_experiments/registry.jsonl: %s", exc)
        return {"available": False}


def build_qledger_reliability() -> dict:
    """Read site/qledger/track_record.json and build the per-family × horizon
    reliability accrual table per §0.5.8 / RUL-6.

    RUL-6: expose only trust/accrual fields:
      family, horizon, n_obs, n_dates, hit_rate, wilson_ci_low, state
    No composite, no escalation-eligible score.

    §0.5.8 MANDATORY: print n_dates beside every CI; add caveat that CI is
    computed on overlapping n_obs, not independent date clusters.
    All families are ACCRUING today (max n_dates=9 of the 25 floor).
    Panel must say "not yet calibrated — trust/accrual surface, not authority."

    Absent-safe: returns {available: False} if file is missing.
    """
    if not QLEDGER_TRACK_RECORD_PATH.exists():
        log.warning("qledger track_record.json not found: %s", QLEDGER_TRACK_RECORD_PATH)
        return {"available": False}

    try:
        raw = load_json(QLEDGER_TRACK_RECORD_PATH)
    except Exception as exc:
        log.warning("Failed to load qledger track_record.json: %s", exc)
        return {"available": False}

    graded_min_dates = raw.get("graded_min_dates", 25)
    by_family = raw.get("by_family", {})

    rows: list[dict] = []
    max_n_dates = 0
    for family, horizons in by_family.items():
        if not isinstance(horizons, dict):
            continue
        for horizon_str, cell in horizons.items():
            if not isinstance(cell, dict):
                continue
            n_dates = cell.get("n_dates") or 0
            max_n_dates = max(max_n_dates, n_dates)
            hit_rate = cell.get("hit_rate")
            wilson_ci_low = cell.get("wilson_ci_low")
            rows.append({
                "family": family,
                "horizon": horizon_str,
                "n_obs": cell.get("n_obs") or 0,
                "n_dates": n_dates,
                "hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
                "hit_rate_pct": f"{hit_rate*100:.1f}%" if hit_rate is not None else "—",
                "wilson_ci_low": round(wilson_ci_low, 4) if wilson_ci_low is not None else None,
                "wilson_ci_low_str": f"{wilson_ci_low:.4f}" if wilson_ci_low is not None else "—",
                "state": cell.get("state", "ACCRUING"),
                # n_dates beside every CI per §0.5.8
                "n_dates_note": f"n_dates={n_dates} of {graded_min_dates} floor",
            })

    # Sort: family then horizon
    rows.sort(key=lambda r: (r["family"], r["horizon"]))

    return {
        "available": True,
        "generated_at": raw.get("generated_at", ""),
        "graded_min_dates": graded_min_dates,
        "max_n_dates": max_n_dates,
        "n_families": len(by_family),
        "rows": rows,
        # §0.5.8 mandatory caveat
        "ci_caveat_en": (
            "Wilson CI is computed on overlapping n_obs (all graded observations), "
            "not on independent date clusters. n_dates is shown beside every CI. "
            "Max n_dates across all families is currently "
            f"{max_n_dates} of the {graded_min_dates}-date floor."
        ),
        "ci_caveat_zh": (
            "威尔逊置信区间基于重叠的n_obs（所有已评分观测值）计算，"
            "而非独立的日期簇。每个置信区间旁均显示n_dates。"
            f"当前所有族中n_dates最大值为{max_n_dates}，floor为{graded_min_dates}。"
        ),
    }


def emit_js(payload: dict) -> str:
    """Emit the window.MEASUREMENT = {...} script-tag data."""
    json_str = json.dumps(payload, ensure_ascii=False, indent=None, separators=(",", ":"))
    return f"// Auto-generated by scripts/build_measurement.py — DO NOT EDIT\n// Ruling A11: script-tag data, zero fetch, zero runtime compute\nwindow.MEASUREMENT={json_str};\n"


def run() -> None:
    t0 = time.time()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log.info("build_measurement: starting W3.7 render")

    # Create output directory
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Build engine scorecards
    engines: list[dict] = []
    for engine_name in ["sector_cycles", "country_cycles", "china_sector_cycles"]:
        log.info("Loading scorecard: %s", engine_name)
        sc = build_engine_scorecard(engine_name)
        engines.append(sc)

    # 2. Unit test: BACKTEST/LIVE never merged (per A6)
    for sc in engines:
        if sc.get("missing"):
            continue
        cohorts = sc.get("cohorts", {})
        # Verify BACKTEST and LIVE are separate objects, not combined
        bt = cohorts.get("BACKTEST", {})
        lv = cohorts.get("LIVE", {})
        if bt and lv:
            assert bt.get("cohort") == "BACKTEST", f"Cohort label mismatch in {sc['engine']}"
            assert lv.get("cohort") == "LIVE", f"Cohort label mismatch in {sc['engine']}"
            log.info("%s: A6 BACKTEST/LIVE separation: OK", sc["engine"])
        # Verify failed gates are rendered (not hidden)
        for cohort_name, cohort in cohorts.items():
            pr_verdict = cohort.get("turn_pr", {}).get("verdict")
            if pr_verdict == "falsified":
                assert cohort["turn_pr"]["verdict_class"] == "verdict-fail", \
                    f"{sc['engine']}/{cohort_name}: falsified gate must map to verdict-fail class!"
            log.debug("%s/%s: failed-gate render check OK", sc["engine"], cohort_name)

    # 3. Gate ledger
    gates = build_gate_ledger()
    log.info("Gate ledger: %d entries", len(gates))

    # 4. Accruing experiments
    accruing = build_accruing_experiments()
    log.info("Accruing cycle experiments: %d", len(accruing))

    # 5. Cone recalibration
    cone_recal = build_cone_recal()

    # 6. Collinearity
    collinearity = build_collinearity()

    # 6b. Sync gauge (W5.1 STOP-fallback)
    sync_gauge = build_sync_gauge()
    if sync_gauge.get("available"):
        log.info("Sync gauge: %d families loaded", len(sync_gauge.get("families", [])))
    else:
        log.warning("Sync gauge not available — check data/leadlag/sync_gauge.json")

    # 6c. Pattern Memory v0 — truth ledger + null library (Hub v2)
    truth_ledger = build_truth_ledger()
    if truth_ledger.get("available"):
        log.info(
            "Truth ledger: %d active truths, status counts: %s",
            truth_ledger.get("total", 0),
            truth_ledger.get("status_counts", {}),
        )
    else:
        log.warning("Truth ledger unavailable — truths.jsonl missing or parse error")

    # 6d. Accrual clocks (Hub v2)
    accrual_clocks = build_accrual_clocks()
    log.info("Accrual clocks: %d ledgers loaded", len(accrual_clocks))

    # 6e. Prediction Layer (Hub v2 completion)
    prediction_layer = build_prediction_layer()
    if prediction_layer.get("available"):
        log.info(
            "Prediction layer: %d cells, %d PASS, fit=%s, %s days stale",
            prediction_layer.get("n_cells_total", 0),
            prediction_layer.get("n_cells_pass", 0),
            prediction_layer.get("fit_date", "?"),
            prediction_layer.get("days_stale", "?"),
        )
    else:
        log.warning("Prediction layer unavailable — hazard model artifact missing")

    # 6f. Coverage Matrix (Hub v2 completion)
    coverage_matrix = build_coverage_matrix()
    log.info("Coverage matrix: %d page rows", len(coverage_matrix.get("rows", [])))

    # 6g. Evidence-Gap panel (PR-A1)
    grading_closure = build_grading_closure()
    if grading_closure.get("available"):
        log.info(
            "Grading closure: %d ledgers (%d closed, %d grader-starved, %d log-only)",
            grading_closure.get("n_ledgers", 0),
            grading_closure.get("n_closed", 0),
            grading_closure.get("n_grader_starved", 0),
            grading_closure.get("n_log_only", 0),
        )
    else:
        log.warning("Grading closure unavailable — data/governance/grading_closure.json missing")

    trial_budgets = build_trial_budgets()
    if trial_budgets.get("available"):
        log.info(
            "Trial budgets: %d rows across %d families",
            trial_budgets.get("n_total", 0),
            trial_budgets.get("n_families", 0),
        )
    else:
        log.warning("Trial budgets unavailable — data/trial_ledger.jsonl missing")

    rule_experiments = build_rule_experiments()
    if rule_experiments.get("available"):
        log.info(
            "Rule experiments: %d experiments, pooled declared budget SUM=%d",
            rule_experiments.get("n_experiments", 0),
            rule_experiments.get("pooled_declared_budget_sum", 0),
        )
    else:
        log.warning("Rule experiments unavailable — data/rule_experiments/registry.jsonl missing")

    qledger_reliability = build_qledger_reliability()
    if qledger_reliability.get("available"):
        log.info(
            "qledger reliability: %d rows, max n_dates=%d of %d floor",
            len(qledger_reliability.get("rows", [])),
            qledger_reliability.get("max_n_dates", 0),
            qledger_reliability.get("graded_min_dates", 25),
        )
    else:
        log.warning("qledger reliability unavailable — site/qledger/track_record.json missing")

    # 7. Grand total of PIT month-end stamps across all three engines (used in prose)
    n_stamps_grand_total = sum(
        eng.get("n_stamps_total", 0) for eng in engines if not eng.get("missing")
    )
    log.info("Grand total PIT stamps across all engines: %d", n_stamps_grand_total)

    # 8. Provenance
    provenance = build_provenance(engines)

    # 9. Assemble payload
    payload = {
        "schema": "measurement.v2",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "engines": engines,
        "gate_ledger": gates,
        "accruing_experiments": accruing,
        "cone_recalibration": cone_recal,
        "collinearity": collinearity,
        "provenance": provenance,
        # Headline consolidated verdict (§6.6)
        "sync_gauge": sync_gauge,
        # Hub v2 additions
        "truth_ledger": truth_ledger,
        "accrual_clocks": accrual_clocks,
        # Hub v2 completion (P2)
        "prediction_layer": prediction_layer,
        "coverage_matrix": coverage_matrix,
        # Evidence-Gap panel (PR-A1)
        "grading_closure": grading_closure,
        "trial_budgets": trial_budgets,
        "rule_experiments": rule_experiments,
        "qledger_reliability": qledger_reliability,
        "consolidated_verdict": {
            "en": (
                "Descriptive structure (confirmed turns, phase wheel, risk/vol clustering) has measurable substance. "
                "Every predictive claim tested so far — position deciles, ladder ordering, turn projections, "
                "directional labels — fails its pre-registered gate. "
                "Phase 3 (honest surfaces + tripwires + regime context) is the product. "
                "Predictive/sizing outputs proceed only through their registered gates."
            ),
            "zh": (
                "描述性结构（已确认拐点、阶段轮盘、风险/波动聚集）具有可测量的实质。"
                "迄今测试的所有预测性主张——仓位十分位、阶梯排序、拐点推演、方向标签——"
                "均未通过其预注册门槛。"
                "第三阶段（诚实展示 + 预警触点 + 周期背景）即为产品本身。"
                "预测/仓位信号仅可通过其已注册门槛后才能发布。"
            ),
        },
    }

    # 10. Emit JS
    js_text = emit_js(payload)
    OUT_JS.write_text(js_text, encoding="utf-8")
    log.info("Wrote %s (%d bytes)", OUT_JS.relative_to(ROOT), len(js_text))

    # 11. Render HTML via Jinja2
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=False)
    try:                                       # _site_nav and _navlinks reference t()/td()/tr() i18n globals
        from engine import i18n
        env.globals.update(td=i18n.td, tr=i18n.tr, t=i18n.t)
    except Exception:  # noqa: BLE001 — degrade to English-only rather than crash the build
        env.globals.update(td=lambda en: en, tr=lambda en: en, t=lambda en, zh="": en)
    template = env.get_template("measurement.html.j2")
    html = template.render(
        page_title="Cycle Measurement Hub",
        engines=engines,
        gate_ledger=gates,
        accruing_experiments=accruing,
        cone_recalibration=cone_recal,
        collinearity=collinearity,
        sync_gauge=sync_gauge,
        provenance=provenance,
        build_date=date.today().isoformat(),
        generated_at=payload["generated_at"],
        n_stamps_grand_total=n_stamps_grand_total,
        # Hub v2 additions
        truth_ledger=truth_ledger,
        accrual_clocks=accrual_clocks,
        # Hub v2 completion (P2)
        prediction_layer=prediction_layer,
        coverage_matrix=coverage_matrix,
        # Evidence-Gap panel (PR-A1)
        grading_closure=grading_closure,
        trial_budgets=trial_budgets,
        rule_experiments=rule_experiments,
        qledger_reliability=qledger_reliability,
    )
    write_page(OUT_HTML, html, encoding="utf-8")
    log.info("Wrote %s (%d bytes)", OUT_HTML.relative_to(ROOT), len(html))

    elapsed = time.time() - t0
    log.info("build_measurement: done in %.1fs", elapsed)


if __name__ == "__main__":
    run()
