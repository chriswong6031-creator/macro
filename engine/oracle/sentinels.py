"""Oracle W-B4 Health & Decay Sentinels.

Three sentinel checks run each nightly as step 13 (loud-error pattern;
never blocks other steps).

1. PANEL DRIFT
   Compare tonight's panel manifest vs the prior run's snapshot persisted
   in data/oracle/sentinel_state.json (keep-prior pattern — if the file is
   absent this is the first run; seed silently, no alarm storm).
   Trips on:
     - schema column-set change
     - per-column null-rate jump > 0.15 absolute
     - node-count drop > 10%
     - date-range regression (max date moving BACKWARD)
   Any trip → ::error:: annotation + a row in data/oracle/sentinel_log.jsonl.

2. EDGE DECAY
   For every display_with_edge item (the 2 onset cells + 6 routing cells —
   read the lineage list from engine.oracle.contract, NOT a hardcoded copy),
   compute the live realized stat from the forward/live ledgers where matured
   rows exist.
   Degrades silently if n_live < 10 (insufficient data — decay monitoring
   needs data, not noise).
   Fires "decay_watch" + ::error:: when:
     - the live estimate's sign flips vs the published stat, OR
     - |live − published| > 2× |published| with n_live ≥ 30.
   NEVER auto-demotes — flags for Fable adjudication only.

3. LEDGER INTEGRITY
   Parse trial_ledger.jsonl and live_ledger.jsonl line-by-line (skip-tolerant
   per tolerant-reader pattern (oracle_screen._load_trial_ledger)).  Count unparseable lines.  Any > 0 → sentinel row.

Constitution bindings:
  - First run seeds sentinel_state.json silently (no alarm storm).
  - Annotations are bilingual (en + zh) in sentinel_log.jsonl.
  - Nothing auto-promotes or auto-demotes.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Loud-error helper (GitHub Actions annotation + log)
# ---------------------------------------------------------------------------

def _annotation(msg: str) -> None:
    """Emit a GitHub Actions ::error:: annotation + log.error."""
    print(f"::error::{msg}", flush=True)
    log.error(msg)


# ---------------------------------------------------------------------------
# Sentinel log writer (append-only bilingual JSONL)
# ---------------------------------------------------------------------------

def _append_sentinel_log(
    log_path: Path,
    check: str,
    level: str,
    detail_en: str,
    detail_zh: str,
    extra: dict | None = None,
) -> None:
    """Append one row to sentinel_log.jsonl."""
    row: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "check": check,
        "level": level,
        "detail_en": detail_en,
        "detail_zh": detail_zh,
    }
    if extra:
        row.update(extra)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


# ---------------------------------------------------------------------------
# 1. PANEL DRIFT
# ---------------------------------------------------------------------------

def _load_manifest(data_dir: Path) -> dict | None:
    """Load data/oracle/manifest.json; return None if absent or corrupt."""
    p = data_dir / "oracle" / "manifest.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("sentinels: could not read manifest.json: %s", e)
        return None


def _extract_manifest_snapshot(manifest: dict) -> dict:
    """Pull the comparable fields from manifest.json into a flat snapshot dict.

    Covers tier_s and tier_m where present.
    Returns a dict suitable for persistence and comparison.
    """
    snap: dict[str, Any] = {}
    for tier_key in ("tier_s", "tier_m"):
        td = manifest.get(tier_key)
        if not isinstance(td, dict):
            continue
        snap[f"{tier_key}.node_count"] = td.get("node_count")
        snap[f"{tier_key}.date_range"] = td.get("date_range")
        snap[f"{tier_key}.columns"] = sorted(td.get("column_schema") or
                                              manifest.get("column_schema") or [])
        # Per-column null rates
        null_rates = td.get("null_rates") or {}
        for col, rate in null_rates.items():
            snap[f"{tier_key}.null_rate.{col}"] = rate
    # Also pick up the top-level column_schema if tiers don't embed it
    if "column_schema" in manifest:
        for tier_key in ("tier_s", "tier_m"):
            key = f"{tier_key}.columns"
            if key not in snap:
                snap[key] = sorted(manifest["column_schema"])
    return snap


_NULL_RATE_JUMP_THRESHOLD = 0.15
_NODE_COUNT_DROP_FRACTION = 0.10


def check_panel_drift(
    data_dir: Path,
    state_path: Path,
    log_path: Path,
) -> list[str]:
    """Run the panel drift sentinel.

    Returns a list of trip messages (empty = clean).
    Seeds sentinel_state.json silently on first run (no alarm).
    """
    manifest = _load_manifest(data_dir)
    if manifest is None:
        log.info("sentinels.panel_drift: manifest.json absent — skip")
        return []

    tonight = _extract_manifest_snapshot(manifest)

    # Load prior snapshot
    prior: dict = {}
    if state_path.exists():
        try:
            stored = json.loads(state_path.read_text())
            prior = stored.get("panel_snapshot") or {}
        except Exception as e:  # noqa: BLE001
            log.warning("sentinels: could not read sentinel_state.json: %s", e)

    trips: list[str] = []

    if not prior:
        # First run — seed silently.
        log.info("sentinels.panel_drift: first run, seeding sentinel_state.json silently")
    else:
        # 1a. Schema column-set change per tier
        for tier_key in ("tier_s", "tier_m"):
            col_key = f"{tier_key}.columns"
            prior_cols = set(prior.get(col_key) or [])
            tonight_cols = set(tonight.get(col_key) or [])
            if prior_cols and tonight_cols and prior_cols != tonight_cols:
                added = tonight_cols - prior_cols
                removed = prior_cols - tonight_cols
                msg = (
                    f"panel_drift: {tier_key} schema changed — "
                    f"added={sorted(added)} removed={sorted(removed)}"
                )
                trips.append(msg)
                _annotation(f"oracle_sentinels: {msg}")
                _append_sentinel_log(
                    log_path, "panel_drift", "error",
                    detail_en=msg,
                    detail_zh=(
                        f"面板漂移：{tier_key} 列结构变化 — "
                        f"新增={sorted(added)} 删除={sorted(removed)}"
                    ),
                    extra={"tier": tier_key, "added": sorted(added), "removed": sorted(removed)},
                )

        # 1b. Per-column null-rate jump > 0.15 absolute
        for key, tonight_val in tonight.items():
            if ".null_rate." not in key:
                continue
            prior_val = prior.get(key)
            if prior_val is None or tonight_val is None:
                continue
            try:
                delta = float(tonight_val) - float(prior_val)
            except (TypeError, ValueError):
                continue
            if delta > _NULL_RATE_JUMP_THRESHOLD:
                col = key.split(".null_rate.", 1)[1]
                tier = key.split(".")[0]
                msg = (
                    f"panel_drift: {tier} column '{col}' null-rate jumped "
                    f"{prior_val:.3f} → {tonight_val:.3f} "
                    f"(Δ={delta:+.3f}, threshold={_NULL_RATE_JUMP_THRESHOLD})"
                )
                trips.append(msg)
                _annotation(f"oracle_sentinels: {msg}")
                _append_sentinel_log(
                    log_path, "panel_drift", "error",
                    detail_en=msg,
                    detail_zh=(
                        f"面板漂移：{tier} 列 '{col}' 空值率跳升 "
                        f"{prior_val:.3f} → {tonight_val:.3f} "
                        f"（变化={delta:+.3f}，阈值={_NULL_RATE_JUMP_THRESHOLD}）"
                    ),
                    extra={"tier": tier, "col": col,
                           "prior_null_rate": prior_val, "tonight_null_rate": tonight_val,
                           "delta": delta},
                )

        # 1c. Node-count drop > 10%
        for tier_key in ("tier_s", "tier_m"):
            nc_key = f"{tier_key}.node_count"
            prior_nc = prior.get(nc_key)
            tonight_nc = tonight.get(nc_key)
            if prior_nc is None or tonight_nc is None:
                continue
            try:
                drop = (int(prior_nc) - int(tonight_nc)) / max(int(prior_nc), 1)
            except (TypeError, ValueError):
                continue
            if drop > _NODE_COUNT_DROP_FRACTION:
                msg = (
                    f"panel_drift: {tier_key} node count dropped "
                    f"{prior_nc} → {tonight_nc} "
                    f"({drop:.1%} > {_NODE_COUNT_DROP_FRACTION:.0%} threshold)"
                )
                trips.append(msg)
                _annotation(f"oracle_sentinels: {msg}")
                _append_sentinel_log(
                    log_path, "panel_drift", "error",
                    detail_en=msg,
                    detail_zh=(
                        f"面板漂移：{tier_key} 节点数下降 "
                        f"{prior_nc} → {tonight_nc} "
                        f"（{drop:.1%} > {_NODE_COUNT_DROP_FRACTION:.0%} 阈值）"
                    ),
                    extra={"tier": tier_key,
                           "prior_node_count": prior_nc,
                           "tonight_node_count": tonight_nc, "drop_fraction": drop},
                )

        # 1d. Date-range regression (max date moving backward)
        for tier_key in ("tier_s", "tier_m"):
            dr_key = f"{tier_key}.date_range"
            prior_dr = prior.get(dr_key)
            tonight_dr = tonight.get(dr_key)
            if not (prior_dr and tonight_dr):
                continue
            try:
                # date_range is a list [start, end]
                prior_max = str(prior_dr[1] if isinstance(prior_dr, list) else prior_dr)
                tonight_max = str(tonight_dr[1] if isinstance(tonight_dr, list) else tonight_dr)
            except (IndexError, TypeError):
                continue
            if tonight_max < prior_max:
                msg = (
                    f"panel_drift: {tier_key} max date regressed "
                    f"'{prior_max}' → '{tonight_max}'"
                )
                trips.append(msg)
                _annotation(f"oracle_sentinels: {msg}")
                _append_sentinel_log(
                    log_path, "panel_drift", "error",
                    detail_en=msg,
                    detail_zh=(
                        f"面板漂移：{tier_key} 最大日期回退 "
                        f"'{prior_max}' → '{tonight_max}'"
                    ),
                    extra={"tier": tier_key,
                           "prior_max_date": prior_max,
                           "tonight_max_date": tonight_max},
                )

    # Persist tonight's snapshot (whether first run or update)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        current_state: dict = {}
        if state_path.exists():
            try:
                current_state = json.loads(state_path.read_text())
            except Exception:  # noqa: BLE001
                pass
        current_state["panel_snapshot"] = tonight
        current_state["panel_snapshot_updated_at"] = datetime.now(timezone.utc).isoformat()
        state_path.write_text(json.dumps(current_state, default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("sentinels: could not write sentinel_state.json: %s", e)

    return trips


# ---------------------------------------------------------------------------
# 2. EDGE DECAY
# ---------------------------------------------------------------------------

def _read_json_tolerant(path: Path) -> dict | None:
    """Read a JSON file; None on absence or corruption (sentinels never crash)."""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("sentinels: could not read %s: %s", path.name, e)
        return None


def _load_jsonl_skip_tolerant(path: Path) -> tuple[list[dict], int]:
    """Parse a JSONL file line-by-line; return (rows, n_unparseable).

    tolerant-reader pattern (oracle_screen._load_trial_ledger): skip unparseable lines, count them.
    """
    if not path.exists():
        return [], 0
    rows: list[dict] = []
    n_bad = 0
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            n_bad += 1
    return rows, n_bad


def _get_display_with_edge_compounds() -> frozenset[str]:
    """Read the display_with_edge compound ids from engine.oracle.contract.

    This is the SINGLE SOURCE OF TRUTH — not a hardcoded copy here.
    If the import fails, degrade gracefully (log warning, return empty set).
    """
    try:
        from engine.oracle.contract import _DISPLAY_WITH_EDGE_COMPOUNDS  # type: ignore[attr-defined]
        return frozenset(_DISPLAY_WITH_EDGE_COMPOUNDS)
    except Exception as e:  # noqa: BLE001
        log.warning(
            "sentinels.edge_decay: could not import _DISPLAY_WITH_EDGE_COMPOUNDS "
            "from engine.oracle.contract: %s — skipping edge-decay check", e
        )
        return frozenset()


def check_edge_decay(
    data_dir: Path,
    log_path: Path,
) -> list[str]:
    """Run the edge-decay sentinel.

    For every display_with_edge compound, compute the live realized stat
    from matured rows in forward_ledger.jsonl and live_ledger.jsonl.
    Degrade silently if n_live < 10.
    Flag "decay_watch" if sign flips or |live - published| > 2×|published|
    with n_live >= 30.

    Returns a list of trip messages (empty = clean or insufficient data).
    """
    display_compounds = _get_display_with_edge_compounds()
    if not display_compounds:
        log.info("sentinels.edge_decay: no display_with_edge compounds found — skip")
        return []

    published_stats = _load_published_stats(data_dir)

    trips: list[str] = []

    # MONITOR-INERT TRIPWIRE (the meta-fix for the #1290 review major: the
    # first decay monitor read invented schemas and reported green with zero
    # coverage forever). If a monitored id has NO published stat, the monitor
    # is inert for it — that is itself a sentinel trip, never a silent skip.
    missing_pub = sorted(c for c in display_compounds if c not in published_stats)
    if missing_pub:
        msg = (f"monitor_inert: no published stat loaded for "
               f"{len(missing_pub)}/{len(display_compounds)} monitored cells: "
               f"{', '.join(missing_pub[:4])}{'…' if len(missing_pub) > 4 else ''}")
        trips.append(msg)
        _annotation(f"oracle_sentinels: {msg}")
        _append_sentinel_log(
            log_path, "edge_decay", "monitor_inert",
            detail_en=(f"Decay monitor has NO published baseline for: "
                       f"{', '.join(missing_pub)} — schema drift between the "
                       f"gauntlet artifacts and the sentinel reader. The monitor "
                       f"is blind for these cells until fixed."),
            detail_zh=(f"衰减监视器缺少已发布基准：{', '.join(missing_pub)} — "
                       f"哨兵读取器与回测产物的结构漂移，修复前对这些单元失明。"),
        )

    for compound_id in sorted(display_compounds):
        matured = _get_matured_rows(compound_id, data_dir)
        if matured is None:
            # Declared gap (routing cells: aggregates only, no per-event live
            # source yet) or unreadable store — recorded, not silently green.
            log.info("sentinels.edge_decay: %s live_source=none (declared gap)", compound_id)
            continue
        n_live = len(matured)

        if n_live < 10:
            # Insufficient accrual — degrade silently (needs data, not noise)
            log.debug("sentinels.edge_decay: %s n_live=%d < 10 — skip", compound_id, n_live)
            continue

        # matured is a list of direction-adjusted floats (episodes-parquet source)
        import numpy as np  # local import; numpy already a dep
        live_mean = float(np.mean(matured))

        pub = published_stats.get(compound_id)
        if pub is None:
            log.debug("sentinels.edge_decay: no published stat for %s — skip", compound_id)
            continue

        published_mean = float(pub)

        # Decay check: sign flip OR |live - published| > 2×|published| with n>=30
        sign_flip = (live_mean * published_mean < 0)  # opposite signs
        magnitude_decay = (
            n_live >= 30
            and abs(published_mean) > 0
            and abs(live_mean - published_mean) > 2 * abs(published_mean)
        )

        if sign_flip or magnitude_decay:
            reason = "sign_flip" if sign_flip else "magnitude_decay"
            msg = (
                f"edge_decay [{reason}]: {compound_id} — "
                f"published={published_mean:+.4f} live={live_mean:+.4f} "
                f"n_live={n_live}"
            )
            trips.append(msg)
            _annotation(f"oracle_sentinels: {msg}")
            _append_sentinel_log(
                log_path, "edge_decay", "decay_watch",
                detail_en=(
                    f"Decay watch [{reason}]: {compound_id} — "
                    f"published effect {published_mean:+.4f}, "
                    f"live realized {live_mean:+.4f} (n={n_live}). "
                    f"Flag for Fable adjudication — NEVER auto-demotes."
                ),
                detail_zh=(
                    f"衰减监视 [{reason}]：{compound_id} — "
                    f"已发布效应 {published_mean:+.4f}，"
                    f"实盘实现 {live_mean:+.4f}（n={n_live}）。"
                    f"标记供 Fable 裁定 — 绝不自动降级。"
                ),
                extra={
                    "compound_id": compound_id,
                    "published_stat": published_mean,
                    "live_stat": live_mean,
                    "n_live": n_live,
                    "reason": reason,
                },
            )

    return trips


def _load_published_stats(data_dir: Path) -> dict[str, float]:
    """compound_id → published effect, aligned to the REAL gauntlet schemas
    (review major on #1290: the first version read invented keys —
    p3['timing'][..]['mean_excess'] — and was inert against production data
    while its fixtures passed. Shapes verified against the real files
    2026-07-04):

      p3_results.json:   episodes.<cell_id>.direction_adjusted_mean
                         (fallback raw_mean)
      p3b_routing_placebo.json: cells['routing_<src>/<dest>/<regime>_<N>d']
                         with fields src/dest/horizon_d/real_mean —
                         reverse-mapped to the contract ids '<src>__<dest>__<N>d'.

    NOTE the alias: the Constitution prose calls the onset cells
    entry_onset_21d / exit_onset_5d; the code ids (contract.py, here) are
    ep_in_onset_21d / ep_out_onset_5d. Same cells."""
    stats: dict[str, float] = {}
    g = data_dir / "oracle" / "gauntlet"

    p3 = _read_json_tolerant(g / "p3_results.json")
    episodes = (p3 or {}).get("episodes") or {}
    for cell_id, row in episodes.items():
        if not isinstance(row, dict):
            continue
        v = row.get("direction_adjusted_mean")
        if v is None:
            v = row.get("raw_mean")
        if isinstance(v, (int, float)):
            stats[str(cell_id)] = float(v)

    p3b = _read_json_tolerant(g / "p3b_routing_placebo.json")
    cells = (p3b or {}).get("cells") or {}
    for _key, cell in cells.items():
        if not isinstance(cell, dict):
            continue
        src, dest, h = cell.get("src"), cell.get("dest"), cell.get("horizon_d")
        v = cell.get("real_mean")
        if src and dest and h and isinstance(v, (int, float)):
            stats[f"{src}__{dest}__{int(h)}d"] = float(v)
    return stats


#: The live-evidence adjudication boundary: only episodes with onset AFTER the
#: P3 adjudication date count as uncontaminated forward evidence for the
#: display_with_edge onset cells.
_ADJUDICATION_DATE = pd.Timestamp("2026-07-04")


def _get_matured_rows(
    compound_id: str,
    data_dir: Path,
) -> list[float] | None:
    """Direction-adjusted matured live outcomes for a display_with_edge cell.

    Onset cells (ep_in_onset_21d / ep_out_onset_5d): read from the nightly-
    regenerated episodes_s.parquet — rows with onset_date > the adjudication
    date and a matured outcome at the cell's horizon are exactly the accruing
    forward evidence (PIT: the detector never sees its outcome).

    Routing cells: **no per-event live source exists yet** — the routing
    matrix stores aggregates only. Returns None with the gap DECLARED (the
    caller records live_source='none' in the snapshot rather than silently
    reporting zero rows as monitored-and-healthy).
    """
    if compound_id.startswith("ep_"):
        try:
            direction = "in" if compound_id.startswith("ep_in") else "out"
            horizon = int(compound_id.rsplit("_", 1)[-1].rstrip("d"))
            eps = pd.read_parquet(data_dir / "oracle" / "episodes_s.parquet")
        except Exception:  # noqa: BLE001 — degrade, sentinel never crashes the night
            return None
        sub = eps[(eps["direction"] == direction)
                  & (pd.to_datetime(eps["onset_date"]) > _ADJUDICATION_DATE)]
        vcol, mcol = f"outcome_rs_{horizon}d", f"outcome_mature_{horizon}d"
        if vcol not in sub.columns or mcol not in sub.columns:
            return None
        sub = sub[(sub[mcol] == True) & sub[vcol].notna()]  # noqa: E712
        sign = 1.0 if direction == "in" else -1.0
        return [sign * float(v) for v in sub[vcol].tolist()]
    # routing cells: aggregates only — declared gap
    return None


def check_ledger_integrity(
    data_dir: Path,
    log_path: Path,
) -> list[str]:
    """Parse trial_ledger.jsonl and live_ledger.jsonl line-by-line.

    Count unparseable lines.  Any > 0 → sentinel row.
    Returns a list of trip messages (empty = clean).
    """
    ledger_specs = [
        ("trial_ledger", data_dir / "oracle" / "compounds" / "trial_ledger.jsonl"),
        ("live_ledger", data_dir / "oracle" / "compounds" / "live_ledger.jsonl"),
        ("forward_ledger", data_dir / "oracle" / "forward_ledger.jsonl"),
    ]

    trips: list[str] = []

    for ledger_name, ledger_path in ledger_specs:
        if not ledger_path.exists():
            log.debug("sentinels.ledger_integrity: %s not found — skip", ledger_name)
            continue

        _, n_bad = _load_jsonl_skip_tolerant(ledger_path)
        if n_bad > 0:
            msg = (
                f"ledger_integrity: {ledger_name} has {n_bad} unparseable line(s)"
            )
            trips.append(msg)
            _annotation(f"oracle_sentinels: {msg}")
            _append_sentinel_log(
                log_path, "ledger_integrity", "error",
                detail_en=(
                    f"Ledger integrity: {ledger_name} has {n_bad} unparseable line(s). "
                    f"Lines were skipped (tolerant-reader pattern (oracle_screen._load_trial_ledger)). Investigate for truncation."
                ),
                detail_zh=(
                    f"账本完整性：{ledger_name} 有 {n_bad} 行无法解析。"
                    f"已按 P1a 撕裂行规则跳过。请排查是否存在截断。"
                ),
                extra={"ledger": ledger_name, "n_unparseable": n_bad,
                       "path": str(ledger_path)},
            )

    return trips


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_sentinels(data_dir: Path, dry_run: bool = False) -> bool:
    """Run all three sentinels.  Returns True if no trips; False if any trip.

    dry_run=True: compute all checks, print findings, but do NOT write
    sentinel_state.json or sentinel_log.jsonl.

    Loud-error pattern: each check is wrapped independently; a crash in one
    check does not block the others.
    """
    state_path = data_dir / "oracle" / "sentinel_state.json"
    log_path = data_dir / "oracle" / "sentinel_log.jsonl"

    all_trips: list[str] = []
    ok = True

    # --- Check 1: Panel drift ---
    try:
        if dry_run:
            # In dry-run, pass a temp path so we don't persist
            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
                tmp_state = Path(tf.name)
            try:
                trips = check_panel_drift(data_dir, tmp_state, log_path)
            finally:
                try:
                    os.unlink(tmp_state)
                except Exception:
                    pass
        else:
            trips = check_panel_drift(data_dir, state_path, log_path)
        all_trips.extend(trips)
        if trips:
            ok = False
        log.info("sentinels.panel_drift: %d trip(s)", len(trips))
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_sentinels: panel_drift check CRASHED: {e}")
        ok = False

    # --- Check 2: Edge decay ---
    try:
        trips = check_edge_decay(data_dir, log_path if not dry_run else Path("/dev/null"))
        all_trips.extend(trips)
        if trips:
            ok = False
        log.info("sentinels.edge_decay: %d trip(s)", len(trips))
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_sentinels: edge_decay check CRASHED: {e}")
        ok = False

    # --- Check 3: Ledger integrity ---
    try:
        trips = check_ledger_integrity(data_dir, log_path if not dry_run else Path("/dev/null"))
        all_trips.extend(trips)
        if trips:
            ok = False
        log.info("sentinels.ledger_integrity: %d trip(s)", len(trips))
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_sentinels: ledger_integrity check CRASHED: {e}")
        ok = False

    if all_trips:
        log.warning("sentinels: %d total trip(s): %s", len(all_trips), all_trips)
    else:
        log.info("sentinels: all checks clean")

    return ok
