from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def make_charts(events: pd.DataFrame, results: pd.DataFrame, out_dir: str | Path) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if events.empty or results.empty:
        return
    top = results.sort_values("bounce_quality_score", ascending=False).head(5)["signal_name"].tolist()
    keep = events[events["signal_name"].isin(["base"] + top)]
    _hist_by_signal(keep, "ret_20d", out / "forward_return_20d_distribution.png")
    _hist_by_signal(keep, "mfe_20d", out / "mfe_20d_distribution.png")
    _hist_by_signal(keep, "mae_20d", out / "mae_20d_distribution.png")
    _bar(results.sort_values("stopout_rate_5pct").head(20), "signal_name", "stopout_rate_5pct", out / "stopout_rate_top20.png")
    _bar(results.sort_values("new_low_rate_60D").head(20), "signal_name", "new_low_rate_60D", out / "new_low_rate_top20.png")
    _bar(results.sort_values("durable_bottom_60D", ascending=False).head(20), "signal_name", "durable_bottom_60D", out / "durable_bottom_rate_top20.png")
    if "date" in events:
        counts = events.assign(year=pd.to_datetime(events["date"]).dt.year).groupby(["year", "signal_name"]).size().unstack(fill_value=0)
        counts[[c for c in counts.columns if c in ["base"] + top]].plot(figsize=(12, 6))
        plt.title("Signal count by year")
        plt.tight_layout()
        plt.savefig(out / "signal_count_by_year.png", dpi=140)
        plt.close()
        perf = events.assign(year=pd.to_datetime(events["date"]).dt.year).groupby(["year", "signal_name"])["ret_20d"].median().unstack()
        perf[[c for c in perf.columns if c in ["base"] + top]].plot(figsize=(12, 6))
        plt.axhline(0, color="black", linewidth=0.8)
        plt.title("Median 20D return by year")
        plt.tight_layout()
        plt.savefig(out / "performance_by_year.png", dpi=140)
        plt.close()
    if "sector" in events:
        sector = events[events["sector"].notna() & (events["sector"] != "Unmapped")]
        if not sector.empty:
            perf = sector.groupby(["sector", "signal_name"])["ret_20d"].median().unstack()
            cols = [c for c in perf.columns if c in ["base"] + top]
            if cols:
                perf[cols].plot(kind="bar", figsize=(13, 7))
                plt.axhline(0, color="black", linewidth=0.8)
                plt.title("Median 20D return by sector")
                plt.tight_layout()
                plt.savefig(out / "performance_by_sector.png", dpi=140)
                plt.close()
    plt.figure(figsize=(8, 6))
    plt.scatter(results["sample_size"], results["bounce_quality_score"], alpha=0.75)
    plt.xlabel("Sample size")
    plt.ylabel("Bounce Quality Score")
    plt.tight_layout()
    plt.savefig(out / "sample_size_vs_bounce_quality.png", dpi=140)
    plt.close()
    plt.figure(figsize=(8, 6))
    plt.scatter(events["dist_60d_low"], events["ret_20d"], alpha=0.12, s=8)
    plt.xlabel("Distance from 60D low")
    plt.ylabel("20D forward return")
    plt.tight_layout()
    plt.savefig(out / "dist_60d_low_vs_20d_return.png", dpi=140)
    plt.close()
    combo = results[results["signal_name"].str.contains("\\+", regex=True, na=False)].copy()
    if not combo.empty:
        _heatmap(combo.head(50), "median_20D", out / "combo_heatmap_median_20d.png")
        _heatmap(combo.head(50), "MFE_MAE_ratio_20D", out / "combo_heatmap_mfe_mae.png")


def _hist_by_signal(df: pd.DataFrame, col: str, path: Path) -> None:
    plt.figure(figsize=(10, 6))
    for name, sub in df.groupby("signal_name"):
        s = sub[col].dropna().clip(-0.5, 0.8)
        if len(s):
            plt.hist(s, bins=50, alpha=0.35, density=True, label=name)
    plt.legend(fontsize=8)
    plt.title(col)
    plt.tight_layout()
    plt.savefig(path, dpi=140)
    plt.close()


def _bar(df: pd.DataFrame, x: str, y: str, path: Path) -> None:
    plt.figure(figsize=(12, 6))
    plt.bar(df[x].astype(str), df[y])
    plt.xticks(rotation=75, ha="right", fontsize=8)
    plt.title(y)
    plt.tight_layout()
    plt.savefig(path, dpi=140)
    plt.close()


def _heatmap(df: pd.DataFrame, value: str, path: Path) -> None:
    mat = []
    names = []
    for _, row in df.iterrows():
        names.append(row["signal_name"][:45])
        mat.append([row.get(value, 0)])
    plt.figure(figsize=(6, max(6, len(names) * 0.22)))
    plt.imshow(mat, aspect="auto", cmap="RdYlGn")
    plt.yticks(range(len(names)), names, fontsize=7)
    plt.xticks([0], [value])
    plt.colorbar()
    plt.tight_layout()
    plt.savefig(path, dpi=140)
    plt.close()
