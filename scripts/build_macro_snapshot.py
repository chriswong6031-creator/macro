"""scripts/build_macro_snapshot.py — Macro Snapshot Registry (R5 PR-C §6.1).

SINGLE-WRITER: this script is the ONLY producer for all three outputs.
  data/macro_snapshots/latest.json    — frozen label composite (display-only)
  data/macro_snapshots/ledger.parquet — one row per (asof, domain, field, value)
  data/macro_snapshots/transitions.jsonl — label flips vs prior ledger asof

PIT DISCIPLINE
--------------
asof = MAX of present source asofs. No spine row dated before the newest source
component can bind to this snapshot without a forward-look risk. oldest_component_asof
= MIN — staleness diagnostic only.

SAME-ASOF REPLACE (IDEMPOTENCY)
---------------------------------
Re-running on the same date replaces ledger rows and transitions for today.
This is a BLOCKING requirement (§0.5 item 2): a nightly retry must be a no-op.

LABEL VOCABULARY v1 (FROZEN — extending bumps schema minor)
------------------------------------------------------------
All values are verbatim strings from sources. NO derived numerics, NO banding.
recession_risk ingests transmission's categorical yield_curve.recession.risk verbatim.

RUL-M5: single-writer declaration satisfies RUL-P10 (not gitignored; not R2).

Never use the word "validated" in any output.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _repo_root() -> Path:
    """Resolve repo root from script location."""
    return Path(__file__).resolve().parent.parent


def _data_dir(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root) / "data"
    try:
        from lib import config  # noqa: PLC0415
        return config.data_dir()
    except Exception:  # noqa: BLE001
        return _repo_root() / "data"


def _out_dir(root: Path | None = None) -> Path:
    p = _data_dir(root) / "macro_snapshots"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Date normalizer — private until engine/neuralweb/_dates.py is available
# ---------------------------------------------------------------------------

def _to_iso(s: Any) -> str | None:
    """Best-effort ISO date from various formats.

    Handles: ISO date/datetime ("2026-07-05", "2026-07-05T..."),
    display strings ("Jul 05, 2026"), None. Returns "YYYY-MM-DD" or None.
    Note: engine/neuralweb/_dates.py may supply to_iso() in PR-B; until then
    this private copy handles the same cases. Deduplicate when PR-B lands.
    """
    if s is None:
        return None
    s = str(s).strip()
    if not s or s.lower() in ("none", "nan", ""):
        return None
    # ISO passthrough (YYYY-MM-DD or YYYY-MM-DDTHH:...)
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    # Display string: "Jul 05, 2026" or "Jan 1, 2026"
    import datetime  # noqa: PLC0415
    for fmt in ("%b %d, %Y", "%b %d %Y", "%B %d, %Y", "%B %d %Y"):
        try:
            return datetime.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    # Last resort: pandas
    try:
        return str(pd.Timestamp(s).date())
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Canonical JSON for stable hashing
# ---------------------------------------------------------------------------

def _canonical_json(obj: Any) -> str:
    """Deterministic JSON for hashing — sort_keys, ensure_ascii, no spacing."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _context_id(labels: dict) -> str:
    """sha256(canonical_json(labels))[:16]."""
    h = hashlib.sha256(_canonical_json(labels).encode("utf-8")).hexdigest()
    return h[:16]


# ---------------------------------------------------------------------------
# Source readers (all fail-open — missing/corrupt = gap)
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> tuple[dict, str | None]:
    """Read a JSON file; returns (data, gap_note). data={} on any failure."""
    if not path.exists():
        return {}, f"absent: {path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except Exception as e:  # noqa: BLE001
        return {}, f"read error ({e}): {path}"


def _safe(d: Any, *keys: str, default: Any = None) -> Any:
    """Safe nested dict get."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, default)
        if d is None:
            return default
    return d


# ---------------------------------------------------------------------------
# Label extractors — domain keyed
# ---------------------------------------------------------------------------

def _extract_us(regime_latest: dict) -> tuple[dict, str | None]:
    """Extract US quad/regime labels from data/regime/latest.json."""
    gaps = []
    rv = regime_latest.get("regime_vector") or {}
    qv = regime_latest.get("quad_vector") or {}
    cac = regime_latest.get("cross_asset_confirm") or {}
    vr = regime_latest.get("vol_regime") or {}
    rr = regime_latest.get("risk_radar") or {}

    labels: dict[str, Any] = {
        "us_quad": regime_latest.get("quad"),
        "us_transition_state": regime_latest.get("transition_state"),
        "us_fused_risk": rv.get("fused_risk_label"),
        "us_vol_regime": rv.get("vol_regime") or (vr.get("regime") if vr else None),
        "us_risk_radar": rv.get("risk_radar_state") or (rr.get("state") if rr else None),
        "us_rate_pressure": rv.get("rate_pressure"),
    }

    # cross_asset_confirm → to_brain.verdict → market_state_verdict proxy
    # market_state_verdict: use cross_asset_confirm.verdict as top-level
    cac_verdict = cac.get("verdict")
    labels["cross_asset_verdict"] = cac_verdict

    # asof from regime_vector or top-level
    asof = rv.get("asof") or regime_latest.get("asof") or regime_latest.get("date")
    asof_iso = _to_iso(asof)

    if not any(v is not None for v in labels.values()):
        gaps.append("us: all regime labels null")

    return {"us": {k: str(v) if v is not None else None for k, v in labels.items()}}, asof_iso, gaps


def _extract_market_state(market_state: dict) -> tuple[dict, str | None]:
    """Extract market_state verdict from data/market_state/latest.json."""
    verdict = market_state.get("verdict")
    asof = _to_iso(market_state.get("asof") or market_state.get("date"))
    return {"market": {"market_state_verdict": str(verdict) if verdict is not None else None}}, asof


def _extract_transmission(transmission: dict) -> tuple[dict, str | None]:
    """Extract yield_curve labels from data/transmission/latest.json.

    recession_risk: uses transmission's categorical yield_curve.recession.risk VERBATIM.
    No re-banding, no thresholds. §0.5 item 6.
    """
    yc = transmission.get("yield_curve") or {}
    regime_block = yc.get("regime") or {}
    recession_block = yc.get("recession") or {}
    shape_block = yc.get("shape") or {}

    labels: dict[str, Any] = {
        # yield_curve regime key (string token) verbatim
        "yield_curve_regime": regime_block.get("key"),
        # recession.risk categorical VERBATIM — no banding
        "recession_risk": recession_block.get("risk"),
    }
    asof = _to_iso(transmission.get("asof"))
    return {"transmission": {k: str(v) if v is not None else None for k, v in labels.items()}}, asof


def _extract_forex(forex: dict) -> tuple[dict, str | None]:
    """Extract FX/dollar labels from data/forex/latest.json."""
    dd = forex.get("dollar_desk") or {}
    labels: dict[str, Any] = {
        "usd_trend": dd.get("trend"),
        "usd_regime": forex.get("regime"),
        "fx_risk": forex.get("risk"),
        "real_rate_regime": dd.get("real_rate_regime"),
        "fx_liquidity_dir": dd.get("liquidity_dir"),
    }
    # forex uses display date "Jul 05, 2026" — normalise
    asof = _to_iso(forex.get("date") or forex.get("asof"))
    return {"fx": {k: str(v) if v is not None else None for k, v in labels.items()}}, asof


def _extract_bonds(bonds: dict) -> tuple[dict, str | None]:
    """Extract bond/credit labels from data/bonds/bond_health.json."""
    labels: dict[str, Any] = {
        "bond_health_label": bonds.get("health_label"),
        "bond_cycle_phase": bonds.get("cycle_phase"),
    }
    asof = _to_iso(bonds.get("as_of") or bonds.get("asof"))
    return {"bonds": {k: str(v) if v is not None else None for k, v in labels.items()}}, asof


def _extract_commodity(commodity: dict) -> tuple[dict, str | None]:
    """Extract commodity labels from data/commodity/latest.json."""
    labels: dict[str, Any] = {
        "commodity_regime": commodity.get("regime"),
        "commodity_favored": commodity.get("favored"),
    }
    asof = _to_iso(commodity.get("date") or commodity.get("asof"))
    return {"commodity": {k: str(v) if v is not None else None for k, v in labels.items()}}, asof


def _extract_china(china: dict) -> tuple[dict, str | None]:
    """Extract China quad label from data/china_regime/latest.json."""
    labels: dict[str, Any] = {
        "china_quad": china.get("quad"),
    }
    asof = _to_iso(china.get("date") or china.get("asof"))
    return {"china": {k: str(v) if v is not None else None for k, v in labels.items()}}, asof


def _extract_hk(hk: dict) -> tuple[dict, str | None]:
    """Extract HK quad/risk labels from data/hk_regime/latest.json."""
    labels: dict[str, Any] = {
        "hk_quad": hk.get("quad"),
        "hk_risk_state": hk.get("risk_state"),
    }
    asof = _to_iso(hk.get("date") or hk.get("asof"))
    return {"hk": {k: str(v) if v is not None else None for k, v in labels.items()}}, asof


def _extract_canada(canada: dict) -> tuple[dict, str | None]:
    """Extract Canada quad label from data/canada_regime/latest.json."""
    labels: dict[str, Any] = {
        "canada_quad": canada.get("quad"),
    }
    asof = _to_iso(canada.get("date") or canada.get("asof"))
    return {"canada": {k: str(v) if v is not None else None for k, v in labels.items()}}, asof


def _extract_dispersion(dispersion: dict) -> tuple[dict, str | None]:
    """Extract dispersion state from data/dispersion/regime.json."""
    labels: dict[str, Any] = {
        "dispersion_state": dispersion.get("state") or dispersion.get("label"),
    }
    asof = _to_iso(dispersion.get("as_of") or dispersion.get("asof"))
    return {"dispersion": {k: str(v) if v is not None else None for k, v in labels.items()}}, asof


# ---------------------------------------------------------------------------
# Main snapshot builder
# ---------------------------------------------------------------------------

def build_snapshot(root: Path | None = None) -> dict:
    """Build the macro snapshot dict without writing anything.

    Returns a snapshot dict or raises on unrecoverable failure.
    The snapshot is the canonical v1 representation.
    """
    data = _data_dir(root)
    gaps: list[str] = []
    sources: dict[str, str | None] = {}
    labels: dict[str, dict] = {}
    source_asofs: list[str] = []

    # -----------------------------------------------------------------------
    # 1. regime/latest.json (us quad, regime_vector, cross_asset)
    # -----------------------------------------------------------------------
    regime_raw, g = _read_json(data / "regime" / "latest.json")
    if g:
        gaps.append(f"regime: {g}")
    else:
        try:
            us_labels, us_asof, us_gaps = _extract_us(regime_raw)
            labels.update(us_labels)
            sources["data/regime/latest.json"] = us_asof
            if us_asof:
                source_asofs.append(us_asof)
            gaps.extend(us_gaps or [])
        except Exception as e:  # noqa: BLE001
            gaps.append(f"regime extraction failed: {e}")

    # -----------------------------------------------------------------------
    # 2. market_state/latest.json
    # -----------------------------------------------------------------------
    ms_raw, g = _read_json(data / "market_state" / "latest.json")
    if g:
        gaps.append(f"market_state: {g}")
    else:
        try:
            ms_labels, ms_asof = _extract_market_state(ms_raw)
            labels.update(ms_labels)
            sources["data/market_state/latest.json"] = ms_asof
            if ms_asof:
                source_asofs.append(ms_asof)
        except Exception as e:  # noqa: BLE001
            gaps.append(f"market_state extraction failed: {e}")

    # -----------------------------------------------------------------------
    # 3. transmission/latest.json
    # -----------------------------------------------------------------------
    tx_raw, g = _read_json(data / "transmission" / "latest.json")
    if g:
        gaps.append(f"transmission: {g}")
    else:
        try:
            tx_labels, tx_asof = _extract_transmission(tx_raw)
            labels.update(tx_labels)
            sources["data/transmission/latest.json"] = tx_asof
            if tx_asof:
                source_asofs.append(tx_asof)
        except Exception as e:  # noqa: BLE001
            gaps.append(f"transmission extraction failed: {e}")

    # -----------------------------------------------------------------------
    # 4. forex/latest.json
    # -----------------------------------------------------------------------
    fx_raw, g = _read_json(data / "forex" / "latest.json")
    if g:
        gaps.append(f"forex: {g}")
    else:
        try:
            fx_labels, fx_asof = _extract_forex(fx_raw)
            labels.update(fx_labels)
            sources["data/forex/latest.json"] = fx_asof
            if fx_asof:
                source_asofs.append(fx_asof)
        except Exception as e:  # noqa: BLE001
            gaps.append(f"forex extraction failed: {e}")

    # -----------------------------------------------------------------------
    # 5. bonds/bond_health.json
    # -----------------------------------------------------------------------
    bd_raw, g = _read_json(data / "bonds" / "bond_health.json")
    if g:
        gaps.append(f"bonds: {g}")
    else:
        try:
            bd_labels, bd_asof = _extract_bonds(bd_raw)
            labels.update(bd_labels)
            sources["data/bonds/bond_health.json"] = bd_asof
            if bd_asof:
                source_asofs.append(bd_asof)
        except Exception as e:  # noqa: BLE001
            gaps.append(f"bonds extraction failed: {e}")

    # -----------------------------------------------------------------------
    # 6. commodity/latest.json
    # -----------------------------------------------------------------------
    cm_raw, g = _read_json(data / "commodity" / "latest.json")
    if g:
        gaps.append(f"commodity: {g}")
    else:
        try:
            cm_labels, cm_asof = _extract_commodity(cm_raw)
            labels.update(cm_labels)
            sources["data/commodity/latest.json"] = cm_asof
            if cm_asof:
                source_asofs.append(cm_asof)
        except Exception as e:  # noqa: BLE001
            gaps.append(f"commodity extraction failed: {e}")

    # -----------------------------------------------------------------------
    # 7. china_regime/latest.json
    # -----------------------------------------------------------------------
    cn_raw, g = _read_json(data / "china_regime" / "latest.json")
    if g:
        gaps.append(f"china_regime: {g}")
    else:
        try:
            cn_labels, cn_asof = _extract_china(cn_raw)
            labels.update(cn_labels)
            sources["data/china_regime/latest.json"] = cn_asof
            if cn_asof:
                source_asofs.append(cn_asof)
        except Exception as e:  # noqa: BLE001
            gaps.append(f"china_regime extraction failed: {e}")

    # -----------------------------------------------------------------------
    # 8. hk_regime/latest.json
    # -----------------------------------------------------------------------
    hk_raw, g = _read_json(data / "hk_regime" / "latest.json")
    if g:
        gaps.append(f"hk_regime: {g}")
    else:
        try:
            hk_labels, hk_asof = _extract_hk(hk_raw)
            labels.update(hk_labels)
            sources["data/hk_regime/latest.json"] = hk_asof
            if hk_asof:
                source_asofs.append(hk_asof)
        except Exception as e:  # noqa: BLE001
            gaps.append(f"hk_regime extraction failed: {e}")

    # -----------------------------------------------------------------------
    # 9. canada_regime/latest.json
    # -----------------------------------------------------------------------
    ca_raw, g = _read_json(data / "canada_regime" / "latest.json")
    if g:
        gaps.append(f"canada_regime: {g}")
    else:
        try:
            ca_labels, ca_asof = _extract_canada(ca_raw)
            labels.update(ca_labels)
            sources["data/canada_regime/latest.json"] = ca_asof
            if ca_asof:
                source_asofs.append(ca_asof)
        except Exception as e:  # noqa: BLE001
            gaps.append(f"canada_regime extraction failed: {e}")

    # -----------------------------------------------------------------------
    # 10. dispersion/regime.json
    # -----------------------------------------------------------------------
    disp_raw, g = _read_json(data / "dispersion" / "regime.json")
    if g:
        gaps.append(f"dispersion: {g}")
    else:
        try:
            disp_labels, disp_asof = _extract_dispersion(disp_raw)
            labels.update(disp_labels)
            sources["data/dispersion/regime.json"] = disp_asof
            if disp_asof:
                source_asofs.append(disp_asof)
        except Exception as e:  # noqa: BLE001
            gaps.append(f"dispersion extraction failed: {e}")

    # -----------------------------------------------------------------------
    # PIT join key: MAX of present source asofs (§0.5 item 5)
    # oldest_component_asof: MIN (staleness diagnostic)
    # -----------------------------------------------------------------------
    valid_asofs = [a for a in source_asofs if a]
    if valid_asofs:
        asof = max(valid_asofs)
        oldest_component_asof = min(valid_asofs)
    else:
        import datetime  # noqa: PLC0415
        asof = str(datetime.date.today())
        oldest_component_asof = asof
        gaps.append("no source asofs found; using today as fallback")

    macro_context_id = _context_id(labels)

    snapshot: dict[str, Any] = {
        "schema": "macro_snapshot.v1",
        "asof": asof,
        "oldest_component_asof": oldest_component_asof,
        "macro_context_id": macro_context_id,
        "labels": labels,
        "sources": sources,
        "gaps": gaps,
        "display_only": True,
    }
    return snapshot


# ---------------------------------------------------------------------------
# Ledger writer (same-asof replace — idempotent)
# ---------------------------------------------------------------------------

def _ledger_rows(snapshot: dict) -> list[dict]:
    """Flatten snapshot labels into ledger rows.

    One row per (asof, domain, field, value, source_asof, macro_context_id).
    """
    asof = snapshot["asof"]
    macro_context_id = snapshot["macro_context_id"]
    labels = snapshot["labels"]
    sources = snapshot["sources"]

    # Build domain → source_asof map
    domain_source_asof: dict[str, str | None] = {}
    _domain_to_path_fragment: dict[str, str] = {
        "us": "regime",
        "market": "market_state",
        "transmission": "transmission",
        "fx": "forex",
        "bonds": "bonds",
        "commodity": "commodity",
        "china": "china_regime",
        "hk": "hk_regime",
        "canada": "canada_regime",
        "dispersion": "dispersion",
    }
    for domain, fragment in _domain_to_path_fragment.items():
        for src_path, src_asof in sources.items():
            if fragment in src_path:
                domain_source_asof[domain] = src_asof
                break

    rows: list[dict] = []
    for domain, field_map in labels.items():
        src_asof = domain_source_asof.get(domain)
        for field, value in field_map.items():
            rows.append({
                "asof": asof,
                "domain": domain,
                "field": field,
                "value": value,
                "source_asof": src_asof,
                "macro_context_id": macro_context_id,
            })
    return rows


def write_ledger(snapshot: dict, out_dir: Path) -> pd.DataFrame:
    """Write (or update) ledger.parquet with same-asof replace semantics.

    Idempotency: existing rows for today's asof are dropped before re-inserting.
    """
    ledger_path = out_dir / "ledger.parquet"
    today_asof = snapshot["asof"]
    new_rows = pd.DataFrame(_ledger_rows(snapshot))

    if ledger_path.exists():
        try:
            existing = pd.read_parquet(ledger_path)
            # Drop today's rows (same-asof replace)
            existing = existing[existing["asof"] != today_asof]
        except Exception as e:  # noqa: BLE001
            log.warning("ledger.parquet unreadable (%s) — overwriting", e)
            existing = pd.DataFrame()
    else:
        existing = pd.DataFrame()

    if not existing.empty:
        combined = pd.concat([existing, new_rows], ignore_index=True)
    else:
        combined = new_rows

    ledger_tmp = ledger_path.with_name(ledger_path.name + ".tmp")
    combined.to_parquet(ledger_tmp, index=False)
    os.replace(ledger_tmp, ledger_path)
    return combined


# ---------------------------------------------------------------------------
# Transitions writer (same-asof replace — idempotent)
# ---------------------------------------------------------------------------

def _prior_ledger_asof(full_ledger: pd.DataFrame, today_asof: str) -> str | None:
    """Find the most recent asof strictly before today in the full ledger."""
    if full_ledger.empty or "asof" not in full_ledger.columns:
        return None
    prior_asofs = sorted(a for a in full_ledger["asof"].unique() if a < today_asof)
    return prior_asofs[-1] if prior_asofs else None


def write_transitions(snapshot: dict, full_ledger: pd.DataFrame, out_dir: Path) -> None:
    """Write transitions.jsonl — label flips vs the prior ledger asof.

    Same-asof replace: drop today's existing transitions before re-deriving.
    First run (no prior asof): emits nothing, prints a note.
    """
    transitions_path = out_dir / "transitions.jsonl"
    today_asof = snapshot["asof"]

    # Drop existing today rows (idempotency — §0.5 item 2)
    existing_lines: list[str] = []
    if transitions_path.exists():
        try:
            for line in transitions_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if obj.get("asof") != today_asof:
                        existing_lines.append(line)
                except Exception:  # noqa: BLE001
                    existing_lines.append(line)  # keep unparseable lines
        except Exception as e:  # noqa: BLE001
            log.warning("transitions.jsonl unreadable (%s) — overwriting", e)
            existing_lines = []

    prior_asof = _prior_ledger_asof(full_ledger, today_asof)
    if prior_asof is None:
        print("transitions: no prior ledger asof found — first run, no transitions emitted")
        # Write back (unchanged) existing lines (atomic)
        transitions_tmp = transitions_path.with_name(transitions_path.name + ".tmp")
        transitions_tmp.write_text(
            "\n".join(existing_lines) + ("\n" if existing_lines else ""),
            encoding="utf-8",
        )
        os.replace(transitions_tmp, transitions_path)
        return

    # Build domain.field → value maps for prior and today
    prior_rows = full_ledger[full_ledger["asof"] == prior_asof]
    today_rows = full_ledger[full_ledger["asof"] == today_asof]

    prior_map: dict[tuple, str | None] = {}
    for _, r in prior_rows.iterrows():
        prior_map[(r["domain"], r["field"])] = r["value"]

    def _norm(v: Any) -> Any:
        """Normalise NaN / 'nan' / 'None' to None for stable comparison."""
        if v is None:
            return None
        if isinstance(v, float) and v != v:  # NaN check (NaN != NaN)
            return None
        s = str(v)
        if s.lower() in ("nan", "none", ""):
            return None
        return s

    new_transitions: list[str] = []
    for _, r in today_rows.iterrows():
        key = (r["domain"], r["field"])
        prior_val = _norm(prior_map.get(key))
        curr_val = _norm(r["value"])
        if prior_val != curr_val:
            flip = {
                "asof": today_asof,
                "domain": r["domain"],
                "field": r["field"],
                "from_value": prior_val,
                "to_value": curr_val,
                "macro_context_id": r["macro_context_id"],
            }
            new_transitions.append(json.dumps(flip, ensure_ascii=True))

    all_lines = existing_lines + new_transitions
    transitions_tmp = transitions_path.with_name(transitions_path.name + ".tmp")
    transitions_tmp.write_text(
        "\n".join(all_lines) + ("\n" if all_lines else ""),
        encoding="utf-8",
    )
    os.replace(transitions_tmp, transitions_path)
    if new_transitions:
        print(f"transitions: {len(new_transitions)} flip(s) detected vs {prior_asof}")
    else:
        print(f"transitions: 0 flips vs {prior_asof} (labels unchanged)")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main(root: Path | None = None) -> int:
    """Build macro snapshot, update ledger and transitions. Returns exit code."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if root is None:
        root = _repo_root()

    print("build_macro_snapshot: starting")

    try:
        snapshot = build_snapshot(root=root)
    except Exception as e:  # noqa: BLE001
        log.error("build_snapshot failed: %s", e)
        return 1

    asof = snapshot["asof"]
    ctx_id = snapshot["macro_context_id"]
    gaps = snapshot.get("gaps", [])
    n_labels = sum(len(v) for v in snapshot["labels"].values())

    print(f"build_macro_snapshot: asof={asof}, macro_context_id={ctx_id}, "
          f"labels={n_labels}, gaps={len(gaps)}")
    if gaps:
        for g in gaps:
            print(f"  gap: {g}")

    out = _out_dir(root)

    # Write latest.json (atomic: write .tmp then os.replace)
    latest_path = out / "latest.json"
    try:
        latest_tmp = latest_path.with_name(latest_path.name + ".tmp")
        latest_tmp.write_text(
            json.dumps(snapshot, indent=2, ensure_ascii=True),
            encoding="utf-8",
        )
        os.replace(latest_tmp, latest_path)
        print(f"build_macro_snapshot: wrote {latest_path}")
    except Exception as e:  # noqa: BLE001
        log.error("write latest.json failed: %s", e)
        return 1

    # Write/update ledger.parquet (same-asof replace)
    try:
        full_ledger = write_ledger(snapshot, out)
        print(f"build_macro_snapshot: ledger.parquet updated ({len(full_ledger)} rows total)")
    except Exception as e:  # noqa: BLE001
        log.error("write ledger.parquet failed: %s", e)
        return 1

    # Write/update transitions.jsonl (same-asof replace)
    try:
        write_transitions(snapshot, full_ledger, out)
    except Exception as e:  # noqa: BLE001
        log.error("write transitions.jsonl failed: %s", e)
        return 1

    # Verify hash stability: re-compute and compare
    snapshot2 = build_snapshot(root=root)
    if snapshot2["macro_context_id"] != ctx_id:
        log.warning(
            "hash instability: first_run=%s second_run=%s (sources may have changed)",
            ctx_id, snapshot2["macro_context_id"],
        )
    else:
        print(f"build_macro_snapshot: hash stable ({ctx_id})")

    print("build_macro_snapshot: done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
