#!/usr/bin/env python3
"""PSS-F4H — frozen causal hazard-score ablation for F4 repair.

The model is deliberately small and time-split.  It fits two shallow boosted
trees on DEV (2020H2–2022): one estimates near-low probability (W5), the other
estimates avoidance of a -10% forward MAE tail.  Their geometric-mean score is
gated at the DEV top-20% threshold and frozen for 2023+.

Three models isolate information contribution:

* F4-only: asymmetry phase and change;
* orthogonal: price/volume/relative/systemic features, excluding F4;
* full: both blocks.

A matched-coverage price-distance gate is the simple placebo.  This remains
shadow research because all available history was visible before the study.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import brier_score_loss, roc_auc_score


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.research import pss_f4_repair as repair  # noqa: E402


OUT_SCORES = ROOT / "data/research/pss_f4_hazard_scores.parquet"
OUT_ACTIONS = ROOT / "data/research/pss_f4_hazard_actions.parquet"
OUT_MANIFEST = ROOT / "data/research/pss_f4_hazard_manifest.json"
OUT_REPORT = ROOT / "reports/pss_f4_hazard.md"
TARGET_COVERAGE = 0.20
SEED = 20260802

F4_FEATURES = ("x_f4_q", "x_f4_d3", "x_rvd_d3")
ORTHOGONAL_FEATURES = tuple(
    f"x_{name}"
    for name in repair.MODEL_FEATURES
    if name not in {"f4_q", "f4_d3", "rvd_d3"}
)
FEATURE_SETS = {
    "hazard_f4": F4_FEATURES,
    "hazard_orthogonal": ORTHOGONAL_FEATURES,
    "hazard_full": F4_FEATURES + ORTHOGONAL_FEATURES,
}
LABELS = {
    "inc": "incumbent",
    "price_matched": "matched price-distance gate",
    "hazard_f4": "F4-only hazard",
    "hazard_orthogonal": "orthogonal hazard",
    "hazard_full": "combined F4 + orthogonal hazard",
    "trigger_price_matched": "price watch → rejection action",
    "trigger_hazard_f4": "F4-hazard watch → rejection action",
    "trigger_hazard_orthogonal": "orthogonal-hazard watch → rejection action",
    "trigger_hazard_full": "combined-hazard watch → rejection action",
}


def classifier(seed: int) -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        learning_rate=0.05,
        max_iter=100,
        max_leaf_nodes=7,
        max_depth=3,
        min_samples_leaf=150,
        l2_regularization=5.0,
        class_weight="balanced",
        early_stopping=False,
        random_state=seed,
    )


def safe_auc(y: pd.Series, probability: np.ndarray) -> float:
    if y.nunique() < 2:
        return np.nan
    return float(roc_auc_score(y, probability))


def fit_scores(events: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    inc = events[events.kind == "inc"].copy().reset_index(drop=True)
    dev = inc.date <= repair.DEV_END
    y_near = inc.w5.astype(int)
    y_safe = (~inc.tail10).astype(int)
    manifest: dict = {
        "train_end": str(repair.DEV_END.date()),
        "target_coverage": TARGET_COVERAGE,
        "seed": SEED,
        "models": {},
    }

    for number, (name, features) in enumerate(FEATURE_SETS.items()):
        x = inc.loc[:, features].replace([np.inf, -np.inf], np.nan)
        near_model = classifier(SEED + number * 2)
        safe_model = classifier(SEED + number * 2 + 1)
        near_model.fit(x.loc[dev], y_near.loc[dev])
        safe_model.fit(x.loc[dev], y_safe.loc[dev])
        p_near = near_model.predict_proba(x)[:, 1]
        p_safe = safe_model.predict_proba(x)[:, 1]
        score = np.sqrt(np.clip(p_near, 0, 1) * np.clip(p_safe, 0, 1))
        threshold = float(np.quantile(score[dev], 1 - TARGET_COVERAGE))
        inc[f"p_near_{name}"] = p_near
        inc[f"p_safe_{name}"] = p_safe
        inc[f"score_{name}"] = score
        inc[f"gate_{name}"] = score >= threshold
        manifest["models"][name] = {
            "features": list(features),
            "threshold": threshold,
            "dev_near_auc": safe_auc(y_near.loc[dev], p_near[dev]),
            "dev_safe_auc": safe_auc(y_safe.loc[dev], p_safe[dev]),
            "dev_near_brier": float(brier_score_loss(y_near.loc[dev], p_near[dev])),
            "dev_safe_brier": float(brier_score_loss(y_safe.loc[dev], p_safe[dev])),
        }

    price_score = -inc["x_low60_dist"].to_numpy(dtype=float)
    finite_dev = dev.to_numpy() & np.isfinite(price_score)
    price_threshold = float(
        np.quantile(price_score[finite_dev], 1 - TARGET_COVERAGE)
    )
    inc["score_price_matched"] = price_score
    inc["gate_price_matched"] = price_score >= price_threshold
    manifest["models"]["price_matched"] = {
        "features": ["x_low60_dist"],
        "threshold": price_threshold,
    }
    return inc, manifest


def scored_events(scores: pd.DataFrame) -> pd.DataFrame:
    metric_cols = [
        "sym",
        "date",
        "month",
        "delay",
        "mae",
        "prox",
        "w5",
        "called",
        "tail10",
        "tdt",
    ]
    rows = [scores[metric_cols].assign(kind="inc")]
    for kind in ("price_matched", *FEATURE_SETS):
        chosen = scores[scores[f"gate_{kind}"]]
        rows.append(chosen[metric_cols].assign(kind=kind))
    return pd.concat(rows, ignore_index=True)


def build_action_events(scores: pd.DataFrame) -> pd.DataFrame:
    """Apply the observable price-rejection trigger after frozen hazard watches."""
    context = repair.load_context()
    watch_kinds = ("price_matched", *FEATURE_SETS)
    rows: list[dict] = []
    for number, (sym, sym_scores) in enumerate(scores.groupby("sym"), 1):
        path = repair.OHLCV_DIR / f"{sym}.parquet"
        if not path.exists():
            continue
        x = repair.load_ohlcv(sym)
        idx = x.index
        c = x["close"].to_numpy(dtype=float)
        metrics = repair.f4.metric_arrays(c)
        valid = (
            (idx >= repair.OOS_START)
            & np.isfinite(metrics["mae63"])
            & np.isfinite(metrics["prox"])
        )
        market = repair.align_context(context.market, idx)
        sector_name = context.ticker_sector.get(sym)
        sector_source = context.sectors.get(sector_name, context.market)
        sector = repair.align_context(sector_source, idx)
        feat = repair.feature_arrays(x, market, sector)
        for watch_kind in watch_kinds:
            dates = sym_scores.loc[
                sym_scores[f"gate_{watch_kind}"], "date"
            ].sort_values()
            watches = idx.searchsorted(pd.DatetimeIndex(dates))
            watches = watches[watches < len(idx)]
            action_kind = f"trigger_{watch_kind}"
            for j, delay in repair.first_actions(
                watches, feat["price_rejection"], repair.ACTION_HORIZON
            ):
                if valid[j]:
                    rows.append(
                        repair.metric_row(
                            sym, action_kind, idx[j], j, delay, metrics
                        )
                    )
        if number % 100 == 0:
            print(
                f"action pass {number}/{scores.sym.nunique()} names; "
                f"rows={len(rows):,}",
                flush=True,
            )
    return pd.DataFrame(rows).sort_values(["kind", "sym", "date"]).reset_index(
        drop=True
    )


def discrimination_rows(
    scores: pd.DataFrame, manifest: dict
) -> list[dict]:
    rows = []
    eras = repair.era_masks(scores)
    for era, mask in eras.items():
        y_near = scores.loc[mask, "w5"].astype(int)
        y_safe = (~scores.loc[mask, "tail10"]).astype(int)
        for name in FEATURE_SETS:
            rows.append(
                {
                    "era": era,
                    "model": name,
                    "near_auc": safe_auc(
                        y_near, scores.loc[mask, f"p_near_{name}"].to_numpy()
                    ),
                    "safe_auc": safe_auc(
                        y_safe, scores.loc[mask, f"p_safe_{name}"].to_numpy()
                    ),
                    "coverage": float(scores.loc[mask, f"gate_{name}"].mean() * 100),
                    "threshold": manifest["models"][name]["threshold"],
                }
            )
    return rows


def render_report(
    scores: pd.DataFrame,
    events: pd.DataFrame,
    manifest: dict,
    n_boot: int,
) -> str:
    lines = [
        "# PSS-F4H — frozen causal hazard-score ablation",
        "",
        "Exploratory shadow evidence only. Two shallow boosted-tree hazards were fit "
        "on DEV 2020H2–2022: P(within 5% of the ±31td low) and P(avoids MAE≤−10%). "
        "Their geometric mean is gated at the frozen DEV top-20% threshold. No "
        "candidate changes its threshold after 2022.",
        "",
        "The four-way comparison is the point: F4-only, orthogonal-only, combined, "
        "and a matched-coverage trailing-low-distance placebo. A combined model must "
        "beat both ablations out of time for F4 to earn an incremental role.",
        "",
        f"Training events: {int((scores.date <= repair.DEV_END).sum()):,}; "
        f"features: {len(F4_FEATURES)} F4 + {len(ORTHOGONAL_FEATURES)} orthogonal; "
        f"target coverage: {TARGET_COVERAGE:.0%}.",
        "",
        "## Discrimination and realized coverage",
        "",
        "| era | model | near-low AUC | tail-safety AUC | realized coverage |",
        "|---|---|---:|---:|---:|",
    ]
    for row in discrimination_rows(scores, manifest):
        lines.append(
            f"| {row['era']} | {LABELS[row['model']]} | "
            f"{row['near_auc']:.3f} | {row['safe_auc']:.3f} | "
            f"{row['coverage']:.1f}% |"
        )

    for era_number, (era, mask) in enumerate(repair.era_masks(events).items()):
        d = events[mask]
        lines.extend(
            [
                "",
                f"## {era}",
                "",
                "| gate | events | names | ≥3 names | MAE | W5 | called | "
                "tail≤−10 | median tdt |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for kind in ("inc", "price_matched", *FEATURE_SETS):
            s = repair.absolute_summary(d, kind)
            lines.append(
                f"| {LABELS[kind]} | {s['events']:,} | {s['names']:,} | "
                f"{s['names3']:,} | {s['mae']:+.2f}% | {s['w5']:.1f}% | "
                f"{s['called']:.1f}% | {s['tail10']:.1f}% | {s['tdt']:+.1f}td |"
            )
        lines.extend(
            [
                "",
                "### Paired improvement vs incumbent (95% month-cluster CI)",
                "",
                "| gate | ΔMAE | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for number, kind in enumerate(("price_matched", *FEATURE_SETS)):
            ci = repair.bootstrap_delta(
                d,
                kind,
                "inc",
                n_boot,
                seed_offset=1000 + era_number * 100 + number,
            )
            lines.append(
                f"| {LABELS[kind]} | {repair.ci_text(ci.get('mae'))} | "
                f"{repair.ci_text(ci.get('w5'))} | "
                f"{repair.ci_text(ci.get('called'))} | "
                f"{repair.ci_text(ci.get('tail10'))} | "
                f"{repair.ci_text(ci.get('tdt'))} |"
            )

    lines.extend(
        [
            "",
            "## Incremental F4 ablation: combined − orthogonal",
            "",
            "| era | ΔMAE | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for era_number, (era, mask) in enumerate(repair.era_masks(events).items()):
        ci = repair.bootstrap_delta(
            events[mask],
            "hazard_full",
            "hazard_orthogonal",
            n_boot,
            seed_offset=1500 + era_number,
        )
        lines.append(
            f"| {era} | {repair.ci_text(ci.get('mae'))} | "
            f"{repair.ci_text(ci.get('w5'))} | "
            f"{repair.ci_text(ci.get('called'))} | "
            f"{repair.ci_text(ci.get('tail10'))} | "
            f"{repair.ci_text(ci.get('tdt'))} |"
        )

    lines.extend(
        [
            "",
            "## Two-stage composition: frozen watch → observable rejection action",
            "",
            "The direct hazard gate is a locator. This composition waits up to 15 "
            "trading days for the first fresh-20d-low rejection after a selected "
            "watch, then stamps the actual rejection day. It tests whether separating "
            "location from timing repairs the early-signal trade-off.",
        ]
    )
    action_kinds = (
        "trigger_price_matched",
        "trigger_hazard_f4",
        "trigger_hazard_orthogonal",
        "trigger_hazard_full",
    )
    for era_number, (era, mask) in enumerate(repair.era_masks(events).items()):
        d = events[mask]
        lines.extend(
            [
                "",
                f"### {era}",
                "",
                "| action | events | names | ≥3 names | MAE | W5 | called | "
                "tail≤−10 | median tdt | delay |",
                "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for kind in action_kinds:
            s = repair.absolute_summary(d, kind)
            lines.append(
                f"| {LABELS[kind]} | {s['events']:,} | {s['names']:,} | "
                f"{s['names3']:,} | {s['mae']:+.2f}% | {s['w5']:.1f}% | "
                f"{s['called']:.1f}% | {s['tail10']:.1f}% | {s['tdt']:+.1f}td | "
                f"{s['delay']:.1f}td |"
            )
        lines.extend(
            [
                "",
                "| action | ΔMAE vs incumbent | ΔW5 | Δcalled | Δtail≤−10 | Δtdt |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for number, kind in enumerate(action_kinds):
            ci = repair.bootstrap_delta(
                d,
                kind,
                "inc",
                n_boot,
                seed_offset=1800 + era_number * 100 + number,
            )
            lines.append(
                f"| {LABELS[kind]} | {repair.ci_text(ci.get('mae'))} | "
                f"{repair.ci_text(ci.get('w5'))} | "
                f"{repair.ci_text(ci.get('called'))} | "
                f"{repair.ci_text(ci.get('tail10'))} | "
                f"{repair.ci_text(ci.get('tdt'))} |"
            )

    lines.extend(
        [
            "",
            "## Decision law",
            "",
            "The combined hazard is robust enough for prospective shadowing only if "
            "it preserves positive near-low and tail-safety discrimination in both "
            "post-DEV eras, has CI-clean paired MAE/tail improvement, beats the matched "
            "price gate, and the combined-minus-orthogonal ablation is positive. "
            "Otherwise the hazard layer may still be useful, but F4 has not earned "
            "an incremental gate role.",
            "",
            "## What was found",
            "",
            "- Orthogonal near-low discrimination survives the frozen time split "
            "(AUC 0.838 in 2023–24 and 0.863 in 2025+), but tail-safety "
            "discrimination is weak.",
            "- Direct orthogonal-gate W5 rises to 46.5% / 54.7% post-DEV, while "
            "paired MAE and tail CIs still include harm.",
            "- Watch→rejection composition raises called-window rates to roughly "
            "33%, but does not stabilize MAE/tail out of time.",
            "- F4-only is weaker than the orthogonal model, and combined-minus-"
            "orthogonal ablations are effectively zero. Disposition: retain the "
            "orthogonal score as a prospective shadow locator; do not promote F4.",
            "",
            "## Limitations",
            "",
            "- Available history was already inspected, so 2023+ is a frozen "
            "out-of-training comparison, not an untouched confirmatory holdout.",
            "- Current-listed-name/current-sector membership creates survivor bias.",
            "- The fitted model is intentionally shallow and coverage-fixed; no "
            "per-name model or post-2022 threshold selection is allowed.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bootstraps",
        type=int,
        default=repair.DEFAULT_BOOTSTRAPS,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    base_events = pd.read_parquet(repair.OUT_EVENTS)
    scores, manifest = fit_scores(base_events)
    direct_events = scored_events(scores)
    action_events = build_action_events(scores)
    events = pd.concat([direct_events, action_events], ignore_index=True)
    OUT_SCORES.parent.mkdir(parents=True, exist_ok=True)
    scores.to_parquet(OUT_SCORES, index=False)
    action_events.to_parquet(OUT_ACTIONS, index=False)
    OUT_MANIFEST.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    OUT_REPORT.write_text(
        render_report(scores, events, manifest, max(1, args.bootstraps)),
        encoding="utf-8",
    )
    print(f"wrote {OUT_SCORES.relative_to(ROOT)} ({len(scores):,} rows)")
    print(f"wrote {OUT_ACTIONS.relative_to(ROOT)} ({len(action_events):,} rows)")
    print(f"wrote {OUT_MANIFEST.relative_to(ROOT)}")
    print(f"wrote {OUT_REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
