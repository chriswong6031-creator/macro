"""Stage Analysis v2 — Industry / sub-industry FLOWS engine (SGA-2, masterplan §2.3).

Breadth-rotation via stage breadth: for every GICS industry (and sub-industry)
counts the Stage-2 vs Stage-4 population, freshness, breadth, RS change, and a
rotation `state`, computed from OUR stage output and calibrated against
EquityDesk's `industry_flows` / `subindustry_flows`
(`data/stage_analysis/backfill/{industry_flows,subindustry_flows}.parquet`).

Per-group output (mirroring their column semantics):
    region, industry_id, industry_name, n,
    stage2_count, stage4_count, stage2_stage4_ratio,
    fresh_stage2_count, fresh_stage2_pct, fresh_stage4_count, fresh_stage4_pct,
    breadth_4w_pct, rs_chg_4w_median, rs_level_median, sata_mean,
    stage2_median_age_wks, state, turn_flag.

Column semantics reproduced against the backfill:
    n                     = all names in the group (any stage).
    stage2/4_count        = names with stage == 2 / 4.
    stage2_stage4_ratio   = s2/s4 (or s2 when s4 == 0).
    fresh_stage2_count    = names flagged is_stage2_start (fresh recapture).
    fresh_*_pct           = fresh_count / n * 100.
    sata_mean             = mean member SATA.
    stage2_median_age_wks = median weeks_in_stage of Stage-2 members.
    breadth_4w_pct        = % of members with a positive 4w RS change.
    rs_chg_4w_median      = median member RS change (4w window).
    rs_level_median       = median member RS LEVEL (mansfield_rs), NOT a change —
                            named honestly (their table has a separate true 1w
                            change we do not reconstruct from a single snapshot).
    state                 = rotation label from breadth + s2/s4 ratio + RS change.
    turn_flag             = bounce/roll transition vs a prior snapshot (None when
                            no prior frame is supplied — matches their ~93% NaN).

Calibration HONESTY (MEASURED on the USA backfill; tests::test_calibration_smoke):
  - counts / sata_mean / stage2_median_age_wks reproduce ~100% exact — but this is
    an AGGREGATION-ARITHMETIC check, NOT a fidelity claim: we feed the SAME per-name
    sata/stage/age inputs the seed carries and verify our groupby math reproduces
    their group aggregates. It confirms the plumbing, not an independent read.
  - `state` label agreement is ~70% vs their labels (5-class; well above chance) —
    an independent classifier boundary fit, the one genuine fidelity metric here.
  - breadth / rs_chg use a true multi-week RS window their engine exposes only as an
    aggregate, so our snapshot approximation correlates ~0.75.

DISPLAY-TIER / CONTEXT-ONLY and fail-open throughout: a missing stage frame or an
empty region yields [] / a blank artifact, never a crash.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_ENGINE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _ENGINE_DIR.parent

# Stage-frame columns this engine needs.
_REQUIRED_COLS = (
    "ticker", "region", "industry_id", "industry_name",
    "sub_industry_id", "sub_industry_name",
    "stage_flag", "weeks_in_stage", "is_stage2_start",
    "mansfield_rs", "mansfield_rs_change", "sata_score",
)
# Sub-set that is genuinely required; sub-industry columns are optional and
# back-filled from the parent industry when absent.
_MIN_COLS = (
    "ticker", "region", "industry_id", "industry_name",
    "stage_flag", "weeks_in_stage",
)

FORMULA_VERSION = "flows_ours_v1"


# ---------------------------------------------------------------------------
# Paths / frame loading
# ---------------------------------------------------------------------------
def _data_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    env = os.environ.get("MACRO_DATA_ROOT")
    if env:
        return Path(env)
    return _REPO_ROOT / "data"


def _seed_stage_frame(dr: Path):
    import pandas as pd

    p = dr / "stage_analysis" / "backfill" / "stage_daily.parquet"
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # noqa: BLE001
        log.warning("stage_flows: seed frame unreadable (%s)", e)
        return None


def _load_gics_map(dr: Path):
    """Ticker -> (region, industry_id, industry_name, sub_industry_id/name) from
    the committed EquityDesk overview yardstick.  Reference identity only (GICS
    taxonomy), never their stage/scores.  Fail-open -> None."""
    import pandas as pd

    p = dr / "stage_analysis" / "backfill" / "equitydesk_overview.parquet"
    if not p.exists():
        return None
    try:
        cols = ["ticker", "region", "gics_industry", "gics_sub_industry"]
        ov = pd.read_parquet(p, columns=[c for c in cols])
    except Exception as e:  # noqa: BLE001
        log.warning("stage_flows: overview GICS map unreadable (%s)", e)
        return None
    if ov.empty or "ticker" not in ov.columns:
        return None
    ov = ov.copy()
    ov["ticker"] = ov["ticker"].astype(str).str.split().str[0].str.upper()
    return ov


def _adapt_live_frame(df, dr: Path):
    """Adapt a LIVE classifier frame (per-name records carrying `stage`, no GICS)
    into the seed schema this engine consumes (`stage_flag` + GICS industry).

    The nightly per-name stage records use `stage` ∈ {1,2,3,4}; the EquityDesk
    seed uses a numeric `stage_flag`.  We map `stage` -> `stage_flag` (identity),
    and join region + GICS industry / sub-industry from the committed overview
    yardstick keyed on ticker.  Fail-open: returns the frame unchanged when it
    already carries `stage_flag` (the seed path), or None if it cannot be made
    to satisfy _MIN_COLS.
    """
    import pandas as pd

    out = df.copy()
    # Map the live `stage` column onto the seed's numeric `stage_flag`.
    if "stage_flag" not in out.columns and "stage" in out.columns:
        out["stage_flag"] = pd.to_numeric(out["stage"], errors="coerce")

    need_gics = any(c not in out.columns for c in ("industry_id", "industry_name"))
    need_region = "region" not in out.columns
    if (need_gics or need_region) and "ticker" in out.columns:
        gics = _load_gics_map(dr)
        if gics is not None:
            key = out["ticker"].astype(str).str.split().str[0].str.upper()
            out = out.assign(_tk=key.values)
            gmap = gics.drop_duplicates(subset=["ticker"], keep="last") \
                       .set_index("ticker")
            if need_region:
                out["region"] = out["_tk"].map(gmap["region"])
            if "industry_id" not in out.columns:
                out["industry_id"] = out["_tk"].map(gmap["gics_industry"])
            if "industry_name" not in out.columns:
                out["industry_name"] = out["_tk"].map(gmap["gics_industry"])
            if "sub_industry_id" not in out.columns:
                out["sub_industry_id"] = out["_tk"].map(gmap["gics_sub_industry"])
            if "sub_industry_name" not in out.columns:
                out["sub_industry_name"] = out["_tk"].map(gmap["gics_sub_industry"])
            out = out.drop(columns=["_tk"])
    return out


def _coerce_frame(stage_frame, dr: Path):
    import pandas as pd

    df = stage_frame
    if df is None:
        df = _seed_stage_frame(dr)
    if df is None:
        return None
    if not isinstance(df, pd.DataFrame):
        try:
            df = pd.DataFrame(df)
        except Exception:  # noqa: BLE001
            return None
    if df.empty:
        return None
    # Adapt a live classifier frame (has `stage`, may lack GICS) to the seed
    # schema BEFORE the required-column gate, so the nightly per-name records
    # feed this engine exactly like the EquityDesk seed does.
    if "stage_flag" not in df.columns and "stage" in df.columns:
        df = _adapt_live_frame(df, dr)
    if any(c not in df.columns for c in _MIN_COLS):
        log.warning("stage_flows: stage frame missing required cols %s",
                    [c for c in _MIN_COLS if c not in df.columns])
        return None
    out = df.copy()
    # optional columns -> safe defaults
    if "sub_industry_id" not in out.columns:
        out["sub_industry_id"] = out["industry_id"]
    if "sub_industry_name" not in out.columns:
        out["sub_industry_name"] = out["industry_name"]
    if "is_stage2_start" not in out.columns:
        out["is_stage2_start"] = False
    if "mansfield_rs" not in out.columns:
        out["mansfield_rs"] = float("nan")
    if "mansfield_rs_change" not in out.columns:
        out["mansfield_rs_change"] = float("nan")
    if "sata_score" not in out.columns:
        out["sata_score"] = float("nan")

    out["industry_id"] = out["industry_id"].astype(str)
    out["sub_industry_id"] = out["sub_industry_id"].astype(str)
    out["stage_flag"] = pd.to_numeric(out["stage_flag"], errors="coerce")
    out["weeks_in_stage"] = pd.to_numeric(out["weeks_in_stage"], errors="coerce")
    for c in ("mansfield_rs", "mansfield_rs_change", "sata_score"):
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out["is_stage2_start"] = out["is_stage2_start"].fillna(False).astype(bool)
    return out


# ---------------------------------------------------------------------------
# State classifier (MEASURED ~70% label agreement vs their labels on the backfill)
# ---------------------------------------------------------------------------
def _classify_state(breadth: float, ratio: float, rs4: float) -> str:
    """Rotation state from breadth + stage2/4 ratio + 4w RS change.

    Boundaries fit on EquityDesk industry_flows (MEASURED label agreement ~70%
    on the USA backfill snapshot — 5-class, well above chance; see
    tests::test_calibration_smoke):
      LEADING      broad + top-heavy Stage-2 + rising RS.
      DISTRIBUTING narrow but Stage-2-dominated (topping out).
      BREAKING     narrow + genuinely falling RS (rolling to Stage 4).
      BASING       broad, not yet leadership.
      NEUTRAL      middling.
    """
    b = 0.0 if breadth is None else float(breadth)
    r = 0.0 if ratio is None else float(ratio)
    rs = 0.0 if rs4 is None else float(rs4)
    if b >= 80 and r >= 2.5 and rs > 0:
        return "LEADING"
    if b <= 35 and r >= 3:
        return "DISTRIBUTING"
    # BREAKING requires RS genuinely falling (rs < 0), not merely soft.
    if b <= 40 and rs < 0:
        return "BREAKING"
    if b >= 60:
        return "BASING"
    return "NEUTRAL"


def _turn_flag(state: str, prev_state: str | None) -> str | None:
    """bounce = re-strengthening off a weak state; roll = weakening off a strong
    state.  None unless a prior snapshot is supplied (matches their sparsity)."""
    if prev_state is None:
        return None
    strong = {"LEADING", "BASING"}
    weak = {"BREAKING", "DISTRIBUTING"}
    if prev_state in weak and state in strong:
        return "bounce"
    if prev_state in strong and state in weak:
        return "roll"
    return None


# ---------------------------------------------------------------------------
# Core aggregation
# ---------------------------------------------------------------------------
def _flow_row(grp, region: str, id_col: str, name_col: str,
              prev_states: dict | None) -> dict:
    import numpy as np

    n = int(len(grp))
    stage = grp["stage_flag"]
    s2 = grp[stage == 2]
    s4 = grp[stage == 4]
    s2_count = int(len(s2))
    s4_count = int(len(s4))
    ratio = (s2_count / s4_count) if s4_count > 0 else float(s2_count)

    fresh2 = int(grp["is_stage2_start"].sum())
    # fresh stage-4: symmetric "fresh breakdown" — a Stage-4 name freshly entered
    # (weeks_in_stage small). We approximate their fresh_stage4 with young Stage-4.
    fresh4 = int((s4["weeks_in_stage"] <= 4).sum()) if s4_count else 0

    msc = grp["mansfield_rs_change"]
    breadth = 100.0 * float((msc > 0).mean()) if msc.notna().any() else 0.0
    rs4_med = float(msc.median()) if msc.notna().any() else 0.0
    rs_level_med = float(grp["mansfield_rs"].median()) if grp["mansfield_rs"].notna().any() else 0.0
    sata_mean = float(grp["sata_score"].mean()) if grp["sata_score"].notna().any() else 0.0
    age = float(s2["weeks_in_stage"].median()) if s2_count else None

    state = _classify_state(breadth, ratio, rs4_med)
    gid = str(grp.iloc[0][id_col])
    prev = (prev_states or {}).get((region, gid))
    turn = _turn_flag(state, prev)

    return {
        "region": region,
        "industry_id": gid,
        "industry_name": str(grp.iloc[0][name_col]),
        "n": n,
        "stage2_count": s2_count,
        "stage4_count": s4_count,
        "stage2_stage4_ratio": round(ratio, 4),
        "fresh_stage2_count": fresh2,
        "fresh_stage2_pct": round(100.0 * fresh2 / n, 4) if n else 0.0,
        "fresh_stage4_count": fresh4,
        "fresh_stage4_pct": round(100.0 * fresh4 / n, 4) if n else 0.0,
        "breadth_4w_pct": round(breadth, 4),
        "rs_chg_4w_median": round(rs4_med, 4),
        "rs_level_median": round(rs_level_med, 4),
        "sata_mean": round(sata_mean, 4),
        "stage2_median_age_wks": None if age is None else round(age, 1),
        "state": state,
        "turn_flag": turn,
        "formula_version": FORMULA_VERSION,
    }


def _flows(df, region: str | None, level: str, prev_states: dict | None) -> list[dict]:
    """level == 'industry' or 'sub_industry'."""
    id_col = "industry_id" if level == "industry" else "sub_industry_id"
    name_col = "industry_name" if level == "industry" else "sub_industry_name"

    if region is not None:
        df = df[df["region"] == region]
        if df.empty:
            return []
        regions = [region]
    else:
        regions = [r for r in df["region"].dropna().unique()]

    rows: list[dict] = []
    for reg in regions:
        members = df[df["region"] == reg]
        if members.empty:
            continue
        for _, grp in members.groupby(id_col):
            if grp.empty:
                continue
            try:
                rows.append(_flow_row(grp, str(reg), id_col, name_col, prev_states))
            except Exception as e:  # noqa: BLE001 — one bad group never breaks the rest
                log.warning("stage_flows: group failed (%s)", e)
    return rows


def flows(region: str | None = None, stage_frame=None, root: Path | None = None,
          prev_states: dict | None = None) -> dict[str, list[dict]]:
    """Per-industry AND per-sub-industry breadth-rotation flows.

    Returns {"industry": [...], "sub_industry": [...]}.  Fail-open -> both [].

    prev_states: optional {(region, industry_id): state} from the previous
    snapshot; enables turn_flag (bounce/roll) detection.
    """
    dr = _data_root(root)
    df = _coerce_frame(stage_frame, dr)
    if df is None:
        return {"industry": [], "sub_industry": []}
    return {
        "industry": _flows(df, region, "industry", prev_states),
        "sub_industry": _flows(df, region, "sub_industry", prev_states),
    }


# ---------------------------------------------------------------------------
# Artifact emission
# ---------------------------------------------------------------------------
def _atomic_write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))
    os.replace(tmp, path)


def _prev_states_from_artifact(dr: Path) -> dict:
    """Read the last emitted flows to seed turn_flag detection. Fail-open."""
    p = dr / "stage_analysis" / "industry_flows.json"
    if not p.exists():
        return {}
    try:
        old = json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return {}
    out: dict = {}
    for reg, rows in (old.get("industry_regions") or {}).items():
        for r in rows:
            out[(reg, str(r.get("industry_id")))] = r.get("state")
    return out


def build(stage_frame=None, root: Path | None = None,
          asof: str | None = None) -> dict:
    """Compute flows for all regions, write the display-tier artifact, return
    the contract.  Fail-open throughout.

    Writes: data/stage_analysis/industry_flows.json
    """
    dr = _data_root(root)
    if asof is None:
        asof = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    built = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    prev_states = _prev_states_from_artifact(dr)
    df = _coerce_frame(stage_frame, dr)
    res = (flows(region=None, stage_frame=df, root=root, prev_states=prev_states)
           if df is not None else {"industry": [], "sub_industry": []})

    ind_by_region: dict[str, list] = {}
    for r in res["industry"]:
        ind_by_region.setdefault(r["region"], []).append(r)
    sub_by_region: dict[str, list] = {}
    for r in res["sub_industry"]:
        sub_by_region.setdefault(r["region"], []).append(r)

    contract = {
        "schema": "stage_industry_flows.v1",
        "asof": asof,
        "built": built,
        "is_context_only": True,
        "display_only": True,
        "disclaimer": ("Context only — industry stage-breadth rotation for "
                       "display, never a signal or sizing input."),
        "calibration": {
            "target": "industry_flows / subindustry_flows (EquityDesk)",
            "note": ("counts/ratios/sata/age are aggregation-arithmetic checks "
                     "(our groupby reproduces their aggregates given the same "
                     "per-name inputs — plumbing, not fidelity); breadth/rs_chg "
                     "use our RS window (corr ~0.75); state label agreement "
                     "~70% (measured, 5-class)"),
        },
        "formula_version": FORMULA_VERSION,
        "industry_regions": ind_by_region,
        "sub_industry_regions": sub_by_region,
        "n_industry": len(res["industry"]),
        "n_sub_industry": len(res["sub_industry"]),
    }
    try:
        _atomic_write_json(dr / "stage_analysis" / "industry_flows.json", contract)
    except Exception as e:  # noqa: BLE001 — write failure never breaks a build
        log.warning("::warning:: stage_flows: failed to write flows (%s)", e)
    return contract
