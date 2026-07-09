"""Oracle nightly pipeline — incremental append to all oracle artifacts.

Runs AFTER massive_stock_day in the nightly workflow.  Each step is wrapped in
the P1a loud-error pattern: ::error:: annotation + deferred nonzero exit on any
failure, but LATER STEPS STILL ATTEMPT so a single bad step cannot block the
rest of the pipeline.

Steps (in order):
  1. Panel update  — re-run build_oracle_panel (Tier S only for speed; M is
                     weekly or on-demand).  ~3 min for Tier S.
  2. Graph update  — re-run build_oracle_graph.  ~2 min.
  3. Episodes      — re-run build_oracle_episodes.  ~15 s.
  3b. Personality  — B1 per-node personality classification.  ~5 s.
  4. Memory        — write rotation_directive.json and memory_base_rates.json.
  5. Time Machine  — re-run build_oracle_timemachine (export feed).  ~30 s.
  6. Oracle state  — build oracle_state.json (the bus payload, includes A3
                     rotation_tag and B1 personality per node/complex).
  7. Alerts        — diff vs prior state, append to oracle_alerts.jsonl;
                     fires oracle_regime_tag on A3 tag transitions.
  8. Directive     — write data/oracle/rotation_directive.json.
  9. Ledger        — append new detections to data/oracle/forward_ledger.jsonl
                     (keep-FIRST, PIT-stamped).
  10. Banner       — additive oracle entry into site/wh_banner.json when a
                     complex reaches confirmed tier with breadth >= floor.
  11. Compound live accrual (W-B3) — evaluate every exploratory/screened/accruing
                     compound on the LATEST panel date only; new fires → PIT keep-first
                     rows in data/oracle/compounds/live_ledger.jsonl; mature outcomes
                     auto-graded; registry live_n/live_effect updated;
                     status screened→accruing on first live fire.
  12. Promotion scan (W-B1) — flags compounds meeting the economic floor into
                     data/oracle/promotion_queue.json (loud-error pattern;
                     never auto-promotes).
  13. Sentinels (W-B4) — health + decay checks; loud-error; first run seeds silently.
  14. Hypothesis inbox (P9) — four collectors: analogue_surprise, detection_miss,
                     screen_live_divergence, sentinel_mirror; append-only to
                     data/oracle/hypothesis_inbox.jsonl; first run seeds silently.
  15. Rotation Turn Desk (W6) — DISPLAY-ONLY panel: armed A15 windows,
                     member cascade fires, base rates, promotion clock.
                     Artifact: site/basketdata/oracle_turn_desk.json.
                     Forward ledger: data/oracle/turn_desk_ledger.jsonl.
  19. TAPE-ONSET (FTR W7) — DISPLAY-ONLY unconfirmed flag per node: raw
                     accel_z >= 1.0 AND vel_1w > vel_3m AND no active same-direction
                     episode.  Printed rates from data.  Additive fields on
                     oracle_turn_desk.json + sidecar oracle_tape_onset.json.
                     Trial ledger: data/oracle/tape_onset_ledger.jsonl.
                     Registration: research/ORACLE_TAPE_ONSET_TIER_REGISTRATION.md.

Usage
-----
  python scripts/oracle_nightly.py [--data-dir PATH] [--site-dir PATH]
                                   [--skip-panel] [--skip-graph] [--skip-episodes]
                                   [--skip-personality] [--skip-timemachine]

  --skip-panel        skip the panel rebuild (use committed parquets)
  --skip-graph        skip the graph rebuild (use committed graph_s.json)
  --skip-episodes     skip the episode rebuild (use committed episodes)
  --skip-personality  skip the B1 personality step (use committed personality.json)
  --skip-timemachine  skip the Time Machine feed export (render path; the dedicated
                      oracle_offrender job owns the panel-dependent feed rebuild)
  --dry-run           run everything but write no files (for timing + smoke tests)

R4 BINDING (ORACLE_GAUNTLET_P3_ADJUDICATION.md):
  - Nothing here ships a predictive claim.
  - Alerts embed the false-start rate from the gauntlet results.
  - Banner is gated on confirmed + breadth floor.
  - Tilt stays config-gated OFF.
  - Personality classifications are DESCRIPTIVE/DISPLAY tier — statistical labels
    from trailing history, never fed to scores, sizes, or gates.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("oracle_nightly")

# Banner floor (D7 binding): confirmed + breadth ≥ this to emit a banner entry.
_BANNER_BREADTH_FLOOR = 0.65
# Banner expiry days (episode exhaustion is preferred; this is the fallback cap).
_BANNER_EXPIRY_DAYS = 5


def _read_json(p: Path) -> dict | list | None:
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _write_json(p: Path, data: dict | list, *, dry_run: bool = False) -> None:
    if dry_run:
        log.info("DRY-RUN: would write %s", p)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, separators=(",", ":"), default=str))


def _annotation(msg: str) -> None:
    """GitHub Actions ::error:: annotation + plain log."""
    print(f"::error::{msg}", flush=True)
    log.error(msg)


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------

def _delegate(step_name: str, module: str, data_dir: Path, dry_run: bool,
              extra: list[str] | None = None) -> bool:
    """Run a build CLI as a subprocess — the CLIs are the tested, canonical
    entry points; re-imagining their internals here is how the original
    step_panel/step_graph shipped calls against nonexistent signatures and
    step_episodes silently dropped Tier M (the alert tier)."""
    import subprocess
    t0 = time.time()
    cmd = [sys.executable, "-m", module, "--data-dir", str(data_dir)] + (extra or [])
    if dry_run:
        log.info("DRY-RUN: would run %s", " ".join(cmd))
        return True
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    if result.returncode != 0:
        _annotation(f"oracle_nightly: {step_name} FAILED (rc={result.returncode}): "
                    f"{(result.stderr or result.stdout)[-400:]}")
        return False
    log.info("%s done in %.1fs", step_name, time.time() - t0)
    return True


def _step_panel(data_dir: Path, dry_run: bool) -> bool:
    """Rebuild BOTH panel tiers via the canonical CLI (Tier M is the alert
    layer — a Tier-S-only nightly would run every subsector alert on stale
    data as the massive store advances)."""
    log.info("=== Step 1: Panel update (Tier S + M) ===")
    return _delegate("panel", "scripts.build_oracle_panel", data_dir, dry_run,
                     ["--tier", "all"])


def _step_graph(data_dir: Path, dry_run: bool) -> bool:
    """Rebuild BOTH graphs via the canonical CLI (graph_m carries the routing
    matrix and complex edges the display surfaces read)."""
    log.info("=== Step 2: Graph update (Tier S + M) ===")
    return _delegate("graph", "scripts.build_oracle_graph", data_dir, dry_run,
                     ["--tier", "all"])


def _step_episodes(data_dir: Path, dry_run: bool) -> bool:
    """Rebuild BOTH episode catalogs via the canonical CLI."""
    log.info("=== Step 3: Episodes rebuild (Tier S + M) ===")
    return _delegate("episodes", "scripts.build_oracle_episodes", data_dir, dry_run,
                     ["--tier", "all"])


def _step_personality(data_dir: Path, dry_run: bool) -> bool:
    """B1 — Per-node personality classification (descriptive/display tier).

    Reads panel_s (falls back to panel_m), computes trend_persistence,
    reversion_strength, rate_beta, idiosyncrasy per node, classifies each
    into {mean_reverter, trender, rate_proxy, idiosyncratic, mixed}, and writes
    data/oracle/personality.json.

    This step runs AFTER episodes (step 3) and BEFORE oracle state (step 6) so
    the personality map is ready to be folded into oracle_state.json.

    Loud-error pattern: prints ::error:: and returns False on failure so the
    pipeline continues; a personality failure is non-fatal (oracle state degrades
    to personality=null for all nodes).
    """
    log.info("=== Step 3b: Personality (B1) ===")
    try:
        from engine.oracle.personality import build_personality, write_personality
        payload = build_personality(data_dir=data_dir)
        n_nodes = len(payload.get("nodes") or {})
        if not dry_run:
            write_personality(payload, data_dir=data_dir)
        # Sample log: show a few representative nodes
        nodes = payload.get("nodes") or {}
        samples = [(n, v["personality"]) for n, v in list(nodes.items())[:6]]
        log.info(
            "personality: classified %d nodes. samples=%s",
            n_nodes,
            samples,
        )
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: personality FAILED: {e}")
        return False


def _step_memory_base_rates(data_dir: Path, dry_run: bool) -> bool:
    """Write memory_base_rates.json from gauntlet p3_results."""
    log.info("=== Step 4a: Memory base rates ===")
    try:
        p3 = _read_json(data_dir / "oracle" / "gauntlet" / "p3_results.json")
        if not isinstance(p3, dict):
            log.info("memory_base_rates: p3_results not found, skipping")
            return True
        er = p3.get("s3_error_rates") or {}
        # Build a simple node-agnostic base rate dict keyed by direction+tier
        base_rates = {
            "out_onset": {
                "false_start_rate": er.get("false_start_rate_out_5d"),
                "onset_to_confirmed": er.get("onset_to_confirmed_rate_out"),
                "source": "gauntlet/p3_results.json s3_error_rates",
                "note": "Descriptive — measured on Tier-S 1998-2026 episodes.",
            },
            "in_onset": {
                "false_start_rate": er.get("false_start_rate_in_5d"),
                "onset_to_confirmed": er.get("onset_to_confirmed_rate_in"),
                "source": "gauntlet/p3_results.json s3_error_rates",
                "note": "Descriptive — measured on Tier-S 1998-2026 episodes.",
            },
        }
        if not dry_run:
            _write_json(data_dir / "oracle" / "memory_base_rates.json", base_rates)
        log.info("memory_base_rates.json written")
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: memory_base_rates FAILED: {e}")
        return False


def _step_timemachine(data_dir: Path, site_dir: Path, dry_run: bool) -> bool:
    """Re-run build_oracle_timemachine export."""
    t0 = time.time()
    log.info("=== Step 5: Time Machine export ===")
    try:
        # Delegate to the existing script (it handles its own output paths)
        import subprocess
        cmd = [
            sys.executable, "-m", "scripts.build_oracle_timemachine",
            "--data-dir", str(data_dir),
        ]
        if dry_run:
            log.info("DRY-RUN: would run %s", " ".join(cmd))
            return True
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        if result.returncode != 0:
            _annotation(f"oracle_nightly: timemachine export FAILED (rc={result.returncode}): {result.stderr[:400]}")
            return False
        log.info("Time Machine exported in %.1fs", time.time() - t0)
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: timemachine export FAILED: {e}")
        return False


def _step_oracle_state(data_dir: Path, site_dir: Path, dry_run: bool) -> dict | None:
    """Build oracle_state.json (the bus payload).

    Runs validate_payload() IMMEDIATELY BEFORE writing.  A failing payload is
    NEVER written (loud ::error:: annotations, prior file preserved, failure
    recorded so main() returns nonzero exit).
    """
    log.info("=== Step 6: Oracle state ===")
    try:
        from engine.oracle.live import build_oracle_state, write_oracle_state
        from engine.oracle.contract import validate_payload
        state = build_oracle_state(data_dir=data_dir)

        # --- Red Queen contract validation (IMMEDIATELY BEFORE WRITE) ---
        ok, errs = validate_payload(state)
        if not ok:
            for err in errs:
                _annotation(f"oracle_nightly: PAYLOAD_INVALID — {err}")
            _annotation(
                f"oracle_nightly: oracle_state REJECTED by contract validator "
                f"({len(errs)} error(s)); prior file preserved, NOT overwriting."
            )
            # Return None so the failure is recorded and triggers nonzero exit.
            return None

        if not dry_run:
            write_oracle_state(state, out_dir=site_dir / "basketdata")
        log.info(
            "oracle_state.json: asof=%s, %d active_episodes, %d watchlist, %d active_complexes, "
            "payload_version=%s",
            state.get("asof"),
            len(state.get("active_episodes") or []),
            len(state.get("onset_watchlist") or []),
            (state.get("regime") or {}).get("n_active_complexes", 0),
            state.get("payload_version", "unstamped"),
        )
        return state
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: oracle_state FAILED: {e}")
        return None


def _step_alerts(oracle_state: dict, dry_run: bool) -> int:
    """Diff vs prior state, append+dedup events. Returns count of NEW events."""
    log.info("=== Step 7: Alerts ===")
    try:
        from engine.oracle import alerts as OA
        if dry_run:
            prior = OA.load_state()
            new_evs = OA.compute_events(oracle_state, prior)
            log.info("DRY-RUN: would emit %d new alert event(s)", len(new_evs))
            return len(new_evs)
        new_evs = OA.rebuild(oracle_state)
        log.info("oracle_alerts: %d new event(s) fired this run", len(new_evs))
        for e in new_evs:
            log.info("  [%s] %s — %s", e.get("type"), e.get("asset"), e.get("headline"))
        return len(new_evs)
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: alerts FAILED: {e}")
        return 0


def _step_directive(oracle_state: dict, data_dir: Path, dry_run: bool) -> bool:
    """Write data/oracle/rotation_directive.json for Mastermind context."""
    log.info("=== Step 8: Directive ===")
    try:
        regime = oracle_state.get("regime") or {}
        active_eps = oracle_state.get("active_episodes") or []
        complexes = oracle_state.get("complexes") or []
        error_rates = (oracle_state.get("disclaimers") or {}).get("error_rates") or {}

        # Rolling-over leaders: confirmed+ OUT episodes
        rolling_over = []
        for ep in active_eps:
            if ep.get("direction") == "out" and ep.get("tier") in ("confirmed", "undeniable"):
                rolling_over.append({
                    "node": ep.get("node"),
                    "tier": ep.get("tier"),
                    "onset_date": ep.get("onset_date"),
                    "n": None,   # analogue n would come from memory_active_analogues
                    "error_rate": error_rates.get("false_start_rate"),
                })

        # Strengthening complexes: active_in at any tier
        strengthening = []
        for c in complexes:
            if c.get("state") in ("active_in", "active_two_sided") and c.get("n_members_active", 0) > 0:
                strengthening.append({
                    "complex_id": c.get("id"),
                    "name": c.get("name"),
                    "name_zh": c.get("name_zh"),
                    "tier": c.get("tier"),
                    "n_members_active": c.get("n_members_active"),
                })

        directive = {
            "schema": "rotation_directive.v1",
            "asof": oracle_state.get("asof"),
            "regime_aggregate": {
                "n_active_complexes": regime.get("n_active_complexes"),
                "breadth": regime.get("breadth"),
                "vix_regime": regime.get("vix_regime"),
            },
            "rolling_over_leaders": rolling_over,
            "strengthening_complexes": strengthening,
            "error_rates": {
                "onset_to_confirmed_conversion": error_rates.get("onset_to_confirmed_conversion"),
                "false_start_rate": error_rates.get("false_start_rate"),
            },
            "instruction": (
                "Context for tempering conviction and raising cash on rolling-over leaders; "
                "NOT a directional buy signal. Primaries NULL per P3 gauntlet. "
                "Onset secondaries DISPLAY-WITH-EDGE only. Never size into this."
            ),
        }
        if not dry_run:
            _write_json(data_dir / "oracle" / "rotation_directive.json", directive)
        log.info(
            "rotation_directive.json: %d rolling-over leaders, %d strengthening complexes",
            len(rolling_over), len(strengthening),
        )
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: directive FAILED: {e}")
        return False


def _step_ledger(oracle_state: dict, data_dir: Path, dry_run: bool) -> int:
    """Append new detections to forward_ledger.jsonl (keep-FIRST, PIT-stamped)."""
    log.info("=== Step 9: Forward ledger ===")
    try:
        ledger_path = data_dir / "oracle" / "forward_ledger.jsonl"
        asof = oracle_state.get("asof") or ""

        # Load existing — build set of existing episode_ids
        existing_ids: set[str] = set()
        if ledger_path.exists():
            for line in ledger_path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    eid = row.get("episode_id")
                    if eid:
                        existing_ids.add(eid)
                except json.JSONDecodeError:
                    continue

        # P3 cell tags for ledger
        _CELL_TAGS = {
            "onset": {"entry_onset_21d": True},
            "confirmed": {},
        }

        new_rows = []
        for ep in (oracle_state.get("active_episodes") or []):
            eid = f"{ep.get('node','')}::{ep.get('direction','')}::{ep.get('onset_date','')}"
            if eid in existing_ids:
                continue
            tier = ep.get("tier", "onset")
            cell_tags = _CELL_TAGS.get(tier, {})
            # exit_onset_5d cell for out-direction episodes
            if ep.get("direction") == "out" and tier == "onset":
                cell_tags = {"exit_onset_5d": True}
            row = {
                "episode_id": eid,
                "node": ep.get("node"),
                "direction": ep.get("direction"),
                "tier": tier,
                "onset_date": ep.get("onset_date"),
                "confirmed_date": ep.get("confirmed_date"),
                "two_sided": ep.get("two_sided", False),
                "survivorship_flagged": ep.get("survivorship_flagged", False),
                "pit_stamp": asof,
                "registered_at": datetime.now(timezone.utc).isoformat(),
                "cell_tags": cell_tags,
            }
            new_rows.append(row)

        if new_rows and not dry_run:
            with open(ledger_path, "a") as fh:
                for r in new_rows:
                    fh.write(json.dumps(r, default=str) + "\n")

        log.info("forward_ledger: %d new entries (keep-FIRST)", len(new_rows))
        return len(new_rows)
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: ledger FAILED: {e}")
        return 0


def _step_banner(oracle_state: dict, site_dir: Path, dry_run: bool) -> bool:
    """Additive oracle entry into site/wh_banner.json.

    Emits AT MOST ONE deterministic oracle banner entry when:
      - a complex reaches confirmed tier
      - breadth >= _BANNER_BREADTH_FLOOR

    If no banner entry is needed, existing wh_banner.json is untouched.
    Falls back gracefully if the file is absent or malformed.

    Banner language is DESCRIPTIVE ONLY (R4):
    "Sector rotation underway: money rotating out of X / into Y — descriptive read,
     see the Time Machine"
    NO LLM anywhere in this path.
    """
    log.info("=== Step 10: Banner ===")
    try:
        regime = oracle_state.get("regime") or {}
        breadth = regime.get("breadth") or 0.0
        complexes = oracle_state.get("complexes") or []
        asof = oracle_state.get("asof") or ""

        # Only emit when breadth floor is met
        if float(breadth) < _BANNER_BREADTH_FLOOR:
            log.info("banner: breadth %.2f < floor %.2f — no oracle banner entry", breadth, _BANNER_BREADTH_FLOOR)
            return True

        # Find confirmed+ out and in complexes
        out_complexes = [c for c in complexes
                         if c.get("direction") == "out"
                         and c.get("tier") in ("confirmed", "undeniable")]
        in_complexes = [c for c in complexes
                        if c.get("direction") == "in"
                        and c.get("tier") in ("confirmed", "undeniable")]

        if not out_complexes and not in_complexes:
            log.info("banner: no confirmed-tier complex found — no oracle banner entry")
            return True

        # Build bilingual banner entry
        out_names = ", ".join(c.get("name", c.get("id", "?")) for c in out_complexes[:2])
        in_names = ", ".join(c.get("name", c.get("id", "?")) for c in in_complexes[:2])
        out_names_zh = ", ".join(c.get("name_zh") or c.get("name", "?") for c in out_complexes[:2])
        in_names_zh = ", ".join(c.get("name_zh") or c.get("name", "?") for c in in_complexes[:2])

        if out_names and in_names:
            title = f"Sector rotation underway: money rotating out of {out_names} / into {in_names} — descriptive read, see the Time Machine"
            title_zh = f"行业轮动进行中：资金从 {out_names_zh} 流出 / 流入 {in_names_zh} — 描述性读数，查看时光机"
        elif out_names:
            title = f"Sector rotation: outflow from {out_names} confirmed — descriptive, see the Time Machine"
            title_zh = f"行业轮动：{out_names_zh} 资金流出已确认 — 描述性读数，查看时光机"
        else:
            title = f"Sector rotation: inflow into {in_names} confirmed — descriptive, see the Time Machine"
            title_zh = f"行业轮动：{in_names_zh} 资金流入已确认 — 描述性读数，查看时光机"

        from datetime import timedelta
        import datetime as _dt
        asof_dt = _dt.datetime.strptime(asof, "%Y-%m-%d") if asof else _dt.datetime.utcnow()
        expires_at = (asof_dt + timedelta(days=_BANNER_EXPIRY_DAYS)).isoformat() + "Z"

        oracle_entry = {
            "id": f"oracle:rotation:{asof}",
            "title": title,
            "title_zh": title_zh,
            "href": "subsector_rotation.html",
            "importance": 50,
            "tone": "mixed",
            "published_at": asof,
            "expires_at": expires_at,
            "tickers": [],
        }

        # Read existing wh_banner.json and inject (additive, idempotent)
        banner_path = site_dir / "wh_banner.json"
        banner = _read_json(banner_path) or {"schema": "wh_banner.v1", "alerts": []}
        if not isinstance(banner, dict):
            banner = {"schema": "wh_banner.v1", "alerts": []}
        alerts = [a for a in (banner.get("alerts") or [])
                  if not (a.get("id") or "").startswith("oracle:rotation:")]
        alerts.append(oracle_entry)
        banner["alerts"] = alerts

        if not dry_run:
            banner_path.parent.mkdir(parents=True, exist_ok=True)
            banner_path.write_text(json.dumps(banner, separators=(",", ":"), default=str))
        log.info("banner: oracle entry written (id=%s)", oracle_entry["id"])
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: banner FAILED: {e}")
        return False


# ---------------------------------------------------------------------------
# W-B3 Compound live accrual (Step 11)
# ---------------------------------------------------------------------------

def _step_compound_live_accrual(data_dir: Path, dry_run: bool) -> bool:
    """W-B3: evaluate all exploratory/screened/accruing compounds on latest panel date.

    New fires → PIT keep-first rows in live_ledger.jsonl.
    Mature outcomes auto-graded on subsequent nights.
    Registry live_n/live_effect updated.
    status screened→accruing on first live fire.
    """
    log.info("=== Step 11: Compound live accrual (W-B3) ===")
    try:
        from engine.oracle.compounds import (
            load_registry, update_compound_status,
            get_entry_dates, augment_panel_with_derived,
            STATUS_ACCRUING, GRAMMAR_VERSION,
        )

        compounds_dir = data_dir / "oracle" / "compounds"
        registry = load_registry(compounds_dir)

        import json as _json
        active_statuses = {"exploratory", "screened", "accruing"}
        active_compounds = [c for c in registry if c.get("status") in active_statuses]
        if not active_compounds:
            log.info("compound_live_accrual: no active compounds to evaluate")
            return True

        live_ledger_path = compounds_dir / "live_ledger.jsonl"

        # Load existing live_ledger to build seen keys (keep-first).
        # The key now includes GRAMMAR_VERSION so that an evaluator semantics
        # change forces new rows rather than being silently suppressed.
        existing_fire_keys: set[str] = set()
        if live_ledger_path.exists():
            for line in live_ledger_path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    r = _json.loads(line)
                    k = f"{r.get('compound_id')}::{r.get('node')}::{r.get('fire_date')}::grammar={r.get('grammar_version', '1.0.0')}"
                    existing_fire_keys.add(k)
                except Exception:  # noqa: BLE001
                    pass

        # Load panels for each tier needed
        panels: dict[str, "pd.DataFrame"] = {}
        episodes: dict[str, "pd.DataFrame"] = {}
        rotation_groups: dict | None = None

        _rg_path = data_dir / "oracle" / "rotation_groups.json"
        rotation_groups = _json.loads(_rg_path.read_text()) if _rg_path.exists() else {"complexes": []}

        def _get_panel(tier: str) -> "pd.DataFrame | None":
            if tier not in panels:
                p = data_dir / "oracle" / f"panel_{tier}.parquet"
                if not p.exists():
                    return None
                import pandas as _pd
                panels[tier] = _pd.read_parquet(p)
            return panels[tier]

        def _get_episodes(tier: str) -> "pd.DataFrame | None":
            if tier not in episodes:
                p = data_dir / "oracle" / f"episodes_{tier}.parquet"
                if not p.exists():
                    return None
                import pandas as _pd
                episodes[tier] = _pd.read_parquet(p)
            return episodes[tier]

        import pandas as pd
        import numpy as np
        from datetime import datetime, timezone

        n_fired = 0
        n_graded = 0

        # Load SPY for outcome grading (tier s)
        spy_path = data_dir / "yahoo" / "SPY.parquet"
        spy = pd.read_parquet(spy_path)["close"] if spy_path.exists() else None

        for compound in active_compounds:
            cid = compound.get("id", "?")
            tier = compound.get("universe", {}).get("tier", "s")
            horizons = compound.get("horizons", [21, 63])

            panel = _get_panel(tier)
            eps = _get_episodes(tier)
            if panel is None or eps is None:
                log.debug("compound_live_accrual: missing panel/episodes for tier %s — skip %s", tier, cid)
                continue

            # Augment panel with derived columns
            panel_aug = augment_panel_with_derived(panel.copy())

            # Get the LATEST panel date only
            all_dates = panel_aug.index.get_level_values("date").unique().sort_values()
            if all_dates.empty:
                continue
            latest_date = all_dates[-1]

            # Evaluate entry rule on full panel (we only care about latest date fires)
            try:
                entry_dates = get_entry_dates(compound, panel_aug, eps, rotation_groups)
            except ValueError as e:
                log.warning("compound_live_accrual: %s rule error: %s", cid, e)
                continue

            if "__blocked__" in entry_dates:
                continue

            # Check if latest_date fired for any node
            new_fires = []
            for node, dates in entry_dates.items():
                if latest_date in dates:
                    fire_key = f"{cid}::{node}::{latest_date.isoformat()}::grammar={GRAMMAR_VERSION}"
                    if fire_key not in existing_fire_keys:
                        new_fires.append({
                            "compound_id": cid,
                            "node": node,
                            "fire_date": latest_date.isoformat(),
                            "grammar_version": GRAMMAR_VERSION,
                            "registered_at": datetime.now(timezone.utc).isoformat(),
                            "outcome_mature": False,
                            "excess_21d": None,
                            "excess_63d": None,
                        })
                        existing_fire_keys.add(fire_key)

            if new_fires and not dry_run:
                live_ledger_path.parent.mkdir(parents=True, exist_ok=True)
                with open(live_ledger_path, "a") as fh:
                    for row in new_fires:
                        fh.write(_json.dumps(row, separators=(",", ":"), default=str) + "\n")
                n_fired += len(new_fires)
                log.info("compound_live_accrual: %s fired %d new times on %s",
                         cid, len(new_fires), latest_date.isoformat())

                # Flip screened → accruing on first live fire
                if compound.get("status") == "screened":
                    update_compound_status(compounds_dir, cid, STATUS_ACCRUING)
                    log.info("compound_live_accrual: %s screened → accruing", cid)

        # Outcome grading pass: re-read live_ledger, grade mature rows
        if not dry_run and live_ledger_path.exists():
            raw_lines = live_ledger_path.read_text().splitlines()
            updated_lines = []
            for line in raw_lines:
                line_s = line.strip()
                if not line_s:
                    updated_lines.append(line)
                    continue
                try:
                    row = _json.loads(line_s)
                except Exception:  # noqa: BLE001
                    updated_lines.append(line)
                    continue

                if row.get("outcome_mature") is True:
                    updated_lines.append(line)
                    continue

                fire_date = pd.Timestamp(row["fire_date"])
                cid = row["compound_id"]
                node = row["node"]
                comp = next((c for c in registry if c["id"] == cid), None)
                if comp is None:
                    updated_lines.append(line)
                    continue

                tier = comp.get("universe", {}).get("tier", "s")
                horizons = comp.get("horizons", [21, 63])

                panel_t = _get_panel(tier)
                if panel_t is None:
                    updated_lines.append(line)
                    continue

                try:
                    node_panel = panel_t.xs(node, level="node")
                except KeyError:
                    updated_lines.append(line)
                    continue

                ret_series = node_panel["ret"].sort_index()
                all_panel_dates = ret_series.index

                # Entry executed at next close after fire_date
                future = all_panel_dates[all_panel_dates > fire_date]
                if len(future) == 0:
                    updated_lines.append(line)
                    continue
                exec_date = future[0]

                graded = False
                price_level = (1 + ret_series.fillna(0)).cumprod()

                for h in horizons:
                    col = f"excess_{h}d"
                    if row.get(col) is not None:
                        continue
                    exec_pos = all_panel_dates.searchsorted(exec_date)
                    exit_pos = exec_pos + h
                    if exit_pos >= len(all_panel_dates):
                        continue
                    exit_date = all_panel_dates[exit_pos]
                    exec_price = price_level.get(exec_date, np.nan)
                    exit_price = price_level.get(exit_date, np.nan)
                    if np.isnan(exec_price) or np.isnan(exit_price) or exec_price == 0:
                        continue

                    node_ret = exit_price / exec_price - 1

                    if tier == "s" and spy is not None:
                        spy_l = (1 + spy.pct_change(fill_method=None).fillna(0)).cumprod()
                        s_exec = spy_l.get(exec_date, np.nan)
                        s_exit = spy_l.get(exit_date, np.nan)
                        bench_ret = (s_exit / s_exec - 1) if not (np.isnan(s_exec) or np.isnan(s_exit) or s_exec == 0) else np.nan
                    else:
                        # tier m: use rs series
                        if "rs" in node_panel.columns:
                            rs_s = node_panel["rs"].sort_index()
                            rs_level = (1 + rs_s.fillna(0)).cumprod()
                            r_exec = rs_level.get(exec_date, np.nan)
                            r_exit = rs_level.get(exit_date, np.nan)
                            node_ret = (r_exit / r_exec - 1) if not (np.isnan(r_exec) or np.isnan(r_exit) or r_exec == 0) else np.nan
                        bench_ret = 0.0

                    excess = node_ret - bench_ret if not np.isnan(bench_ret) else np.nan
                    if not np.isnan(excess):
                        row[col] = float(excess)
                        graded = True

                # Mark mature only when ALL horizon windows have been graded
                all_graded = all(row.get(f"excess_{h}d") is not None for h in horizons)
                if all_graded:
                    row["outcome_mature"] = True
                    n_graded += 1

                updated_lines.append(_json.dumps(row, separators=(",", ":"), default=str))

            live_ledger_path.write_text("\n".join(updated_lines) + "\n")

        # Update registry live_n / live_effect per compound
        if not dry_run and live_ledger_path.exists():
            live_rows = []
            for line in live_ledger_path.read_text().splitlines():
                line_s = line.strip()
                if line_s:
                    try:
                        live_rows.append(_json.loads(line_s))
                    except Exception:  # noqa: BLE001
                        pass

            registry_updated = load_registry(compounds_dir)
            for compound in registry_updated:
                cid = compound["id"]
                mature = [r for r in live_rows
                          if r.get("compound_id") == cid and r.get("outcome_mature") is True]
                compound["live_n"] = len([r for r in live_rows if r.get("compound_id") == cid])
                if mature:
                    excesses = [r.get("excess_63d") for r in mature if r.get("excess_63d") is not None]
                    compound["live_effect"] = float(np.mean(excesses)) if excesses else None

            from engine.oracle.compounds import save_registry
            save_registry(compounds_dir, registry_updated)

        log.info("compound_live_accrual: %d new fires, %d rows graded this run",
                 n_fired, n_graded)
        return True

    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: compound_live_accrual FAILED: {e}")
        return False


def _step_reversion_forward_ledger(data_dir: Path, dry_run: bool) -> bool:
    """P0: Reversion forward ledger — nightly single-writer (Step 11b).

    For each registry compound with a ``reversion`` block (gauntlet PASS),
    evaluates its entry rule on the latest panel date, appends new fires to
    ``data/oracle/reversion_forward/<compound_id>.jsonl`` (idempotent), and
    grades rows whose exit_date <= latest date.

    Non-fatal: failure prints a warning but never blocks subsequent steps.
    Outputs land under data/ which is covered by 'git add data/' (sentinel-gap law).
    """
    log.info("=== Step 11b: Reversion forward ledger (P0) ===")
    try:
        from scripts.oracle_reversion_forward_ledger import run_reversion_forward_ledger
        summary = run_reversion_forward_ledger(data_dir, dry_run=dry_run)
        log.info(
            "reversion_forward_ledger: n_compounds=%d fired=%d graded=%d skipped=%d",
            summary.get("n_compounds", 0),
            summary.get("total_fired", 0),
            summary.get("total_graded", 0),
            summary.get("n_skipped", 0),
        )
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: reversion_forward_ledger FAILED: {e}")
        return False


def _step_reversion_state(data_dir: Path, site_dir: Path, dry_run: bool) -> bool:
    """P1: Oracle reversion state sidecar writer (Step 11c, display tier only).

    Writes ``site/basketdata/oracle_reversion_state.json`` (schema
    oracle_reversion_state.v1).  Display tier only — no authority granted,
    no ranking surface touched (Article 2).

    Non-fatal: failure never blocks subsequent steps.
    Output lands under site/ which is covered by 'git add site/' (sentinel-gap law).
    """
    log.info("=== Step 11c: Reversion state sidecar (P1, display tier) ===")
    try:
        from scripts.oracle_reversion_state import build_reversion_state
        payload = build_reversion_state(data_dir, site_dir, dry_run=dry_run)
        n = payload.get("n_signals", 0)
        fired = sum(len(s.get("fired_today", [])) for s in payload.get("signals", []))
        log.info("reversion_state: n_signals=%d fired_today_total=%d", n, fired)
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: reversion_state FAILED: {e}")
        return False


def _step_promotion_scan(data_dir: Path, dry_run: bool) -> bool:
    """W-B1: Run promotion scan as the LAST nightly step (loud-error pattern)."""
    log.info("=== Step 12: Promotion scan ===")
    try:
        from scripts.oracle_promotion_scan import run_promotion_scan
        queue = run_promotion_scan(data_dir, dry_run=dry_run)
        log.info("promotion_scan: search_width=%d candidates=%d",
                 queue.get("search_width", 0), queue.get("n_candidates", 0))
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: promotion_scan FAILED: {e}")
        return False


def _step_sentinels(data_dir: Path, dry_run: bool) -> bool:
    """W-B4: Health & decay sentinels — nightly step 13.

    Loud-error pattern: ::error:: annotations on any trip; never blocks other steps.
    First run seeds sentinel_state.json silently (no alarm storm).
    Three checks:
      1. Panel drift   — schema/null-rate/node-count/date-range regression
      2. Edge decay    — live realized stats vs published display_with_edge effects
      3. Ledger integrity — unparseable JSONL lines (P1a torn-line law)
    """
    log.info("=== Step 13: Sentinels (W-B4) ===")
    try:
        from engine.oracle.sentinels import run_sentinels
        ok = run_sentinels(data_dir, dry_run=dry_run)
        if ok:
            log.info("sentinels: all checks clean")
        else:
            # Trips already annotated inside run_sentinels; nonzero exit follows
            _annotation("oracle_nightly: sentinels step 13 detected trip(s) — see sentinel_log.jsonl")
        return ok
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: sentinels FAILED: {e}")
        return False


def _step_hypothesis_inbox(data_dir: Path, dry_run: bool) -> dict[str, int]:
    """P9: Hypothesis inbox collection — nightly step 14.

    Loud-error pattern: ::error:: annotation on any failure; non-blocking (later
    steps not present, but the nightly pipeline continues if this throws).
    First run seeds hypothesis_state.json silently — no rows written.
    Four collectors: analogue_surprise, detection_miss, screen_live_divergence,
    sentinel_mirror.

    Returns counts dict; an empty dict signals failure.
    """
    log.info("=== Step 14: Hypothesis inbox (P9) ===")
    try:
        from engine.oracle.hypothesis_inbox import run_hypothesis_inbox
        counts = run_hypothesis_inbox(data_dir, dry_run=dry_run)
        # (breakdown already logged inside run_hypothesis_inbox — no dup)
        return counts
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: hypothesis_inbox FAILED: {e}")
        return {}


# ---------------------------------------------------------------------------
# Step 15: Rotation Turn Desk (W6)
# ---------------------------------------------------------------------------

# A15 compound spec — not in registry (scout finding: no A15 rows today);
# rule: washout_w > 0 AND ep(out/onset/opposite/within_sessions=20/min_count=2)
_A15_COMPOUND: dict = {
    "id": "A15_WASHOUT_OPP_OUT_2NODE",
    "universe": {"tier": "s"},
    "entry_rule": {
        "all": [
            {"col": "washout_w", "op": "gt", "value": 0},
            {
                "episode_event": {
                    "direction": "out",
                    "tier": "onset",
                    "complex_scope": "opposite",
                    "within_sessions": 20,
                    "min_count": 2,
                }
            },
        ]
    },
    "condition_rule": None,
}

# GICS sector name -> ETF node (for mapping us_standouts sector field).
# Derived from engine/oracle/panel.py::ETF_TO_SECTOR (canonical inverse) plus
# non-canonical aliases emitted by the buy-lane builder (e.g. 'Technology',
# 'Communications').  Aliases added here must NOT appear in ETF_TO_SECTOR so the
# two-way round-trip is preserved; the canonical map is source-of-truth.
def _build_sector_to_etf() -> dict[str, str]:
    from engine.oracle.panel import ETF_TO_SECTOR as _ETS
    _map = {sector: etf for etf, sector in _ETS.items()}
    # Non-canonical aliases emitted by the buy-lane standouts builder.
    # These are intentional additions, not duplicates of canonical names.
    _map.setdefault("Technology", "XLK")          # buy lane alias for XLK
    _map.setdefault("Communications", "XLC")       # buy lane alias for XLC
    return _map


_SECTOR_TO_ETF: dict[str, str] = _build_sector_to_etf()

# Window length in sessions
_A15_WINDOW_SESSIONS = 10
# Maturity horizon for forward ledger grading
_MATURITY_H = 21
# Banned-implication key substrings (Constitution III)
_BANNED_KEY_SUBS = ("forecast", "predicted", "target", "expected_return")


def _step_turn_desk(
    data_dir: Path, site_dir: Path, dry_run: bool
) -> tuple[bool, list[dict], str, list[str]]:
    """W6 Step 15: Rotation Turn Desk — armed windows + member fires + display artifact.

    DISPLAY-ONLY under hard law: this artifact feeds no score, gate, or ordering.
    Forward ledger (data/oracle/turn_desk_ledger.jsonl) is the accrual instrument
    for the registered §5 promotion rule — no peeking logic.

    Returns (ok, armed, panel_asof, all_dates_list) so Step 17 (W7) can stamp
    the same window set without re-running the A15 rule.

    Loud-error pattern: ::error:: + returns (False, [], "", []) ; pipeline continues.
    """
    log.info("=== Step 15: Rotation Turn Desk (W6) ===")
    try:
        import pandas as _pd
        import json as _json
        from datetime import datetime, timezone

        from engine.oracle.compounds import (
            get_entry_dates,
            augment_panel_with_derived,
        )
        from engine.neuralweb.envelope import stamp_if_changed

        # ── 1. Load panel + episodes + rotation_groups ──
        panel_path = data_dir / "oracle" / "panel_s.parquet"
        episodes_path = data_dir / "oracle" / "episodes_s.parquet"
        rg_path = data_dir / "oracle" / "rotation_groups.json"

        if not panel_path.exists():
            _annotation("oracle_nightly: turn_desk — panel_s.parquet missing, skipping")
            return False
        if not episodes_path.exists():
            _annotation("oracle_nightly: turn_desk — episodes_s.parquet missing, skipping")
            return False

        panel_raw = _pd.read_parquet(panel_path)
        episodes_df = _pd.read_parquet(episodes_path)
        rotation_groups = (
            _json.loads(rg_path.read_text()) if rg_path.exists() else {"complexes": []}
        )

        panel_aug = augment_panel_with_derived(panel_raw.copy())

        # ── 2. Recompute A15 entry dates (latest panel) ──
        try:
            entry_dates_raw = get_entry_dates(
                _A15_COMPOUND, panel_aug, episodes_df, rotation_groups
            )
        except ValueError as e:
            _annotation(f"oracle_nightly: turn_desk — A15 rule error: {e}")
            entry_dates_raw = {}

        if "__blocked__" in entry_dates_raw:
            log.warning("turn_desk: A15 blocked (missing column)")
            entry_dates_raw = {}

        # ── 3. Determine panel asof (latest date) ──
        all_dates_idx = panel_aug.index.get_level_values("date").unique().sort_values()
        panel_asof = all_dates_idx[-1].strftime("%Y-%m-%d") if len(all_dates_idx) else ""

        # Convert to sets of string dates for window logic
        entry_dates_str: dict[str, set[str]] = {
            node: {d.strftime("%Y-%m-%d") for d in dates}
            for node, dates in entry_dates_raw.items()
        }

        # ── 4. Build armed windows ──
        # Window = fire → +10 sessions from fire date; merged per node.
        # We need the last N session dates to check recency.
        all_dates_list = [d.strftime("%Y-%m-%d") for d in all_dates_idx]
        date_to_pos: dict[str, int] = {d: i for i, d in enumerate(all_dates_list)}

        armed: list[dict] = []
        for node, fires in entry_dates_str.items():
            if not fires:
                continue
            # Find fires in last _A15_WINDOW_SESSIONS sessions (from panel_asof)
            asof_pos = date_to_pos.get(panel_asof, len(all_dates_list) - 1)
            window_start_pos = max(0, asof_pos - _A15_WINDOW_SESSIONS + 1)
            window_start_date = all_dates_list[window_start_pos]

            recent_fires = sorted(f for f in fires if f >= window_start_date)
            if not recent_fires:
                continue

            latest_fire = recent_fires[-1]
            fire_pos = date_to_pos.get(latest_fire, 0)
            window_end_pos = min(len(all_dates_list) - 1, fire_pos + _A15_WINDOW_SESSIONS - 1)
            window_end = all_dates_list[window_end_pos]
            sessions_remaining = max(0, window_end_pos - asof_pos)

            # ETF nodes → names
            # node is something like XLK, XLV etc.
            from engine.oracle.panel import ETF_TO_SECTOR
            sector_name_en = ETF_TO_SECTOR.get(node, node)

            # ZH name lookup
            _ZH_SECTOR = {
                "XLK": "信息技术", "XLV": "医疗保健", "XLF": "金融",
                "XLY": "可选消费", "XLC": "通信服务", "XLI": "工业",
                "XLP": "必需消费", "XLE": "能源", "XLU": "公用事业",
                "XLRE": "房地产", "XLB": "原材料",
            }
            armed.append({
                "node": node,
                "name_en": sector_name_en,
                "name_zh": _ZH_SECTOR.get(node, node),
                "fire_dates": sorted(fires),
                "window_end": window_end,
                "sessions_remaining": sessions_remaining,
                "member_fires": [],  # filled below
            })

        log.info("turn_desk: %d armed sectors", len(armed))

        # ── 5. Load member fires from us_standouts.json ──
        standouts_path = site_dir / "factordata" / "us_standouts.json"
        # signal_gate.json is declared in dag.yml reads but not consumed yet;
        # variable removed to avoid dead-code confusion (spec §2.2 finding).

        member_fires_asof = ""
        if standouts_path.exists():
            standouts = _read_json(standouts_path) or {}
            member_fires_asof = standouts.get("as_of", "")
            buy_rows = standouts.get("buy", [])
            watch_rows = standouts.get("watch", [])
            all_standout_rows = buy_rows + watch_rows

            # Propagate member_fires_asof to each armed entry so the ledger
            # writer can key member_fire rows on the standouts artifact date
            # (stable for the same event) rather than panel_asof.
            for _ae in armed:
                _ae["_member_fires_asof"] = member_fires_asof

            # Build a quick set of armed nodes
            armed_nodes = {a["node"] for a in armed}

            for row in all_standout_rows:
                sig = row.get("signal", {}) if isinstance(row.get("signal"), dict) else {}
                tc = sig.get("tier_cascade")
                if tc not in ("T1", "T2", "T3"):
                    continue
                # Map sector field to ETF node
                sector_str = row.get("sector", "")
                etf_node = _SECTOR_TO_ETF.get(sector_str)
                if etf_node is None:
                    # Loud annotation so future label drift trips CI rather than
                    # silently dropping T1-T3 fires (spec §2.1 blocker fix).
                    _annotation(
                        f"oracle_nightly: turn_desk — T1-T3 fire sector "
                        f"'{sector_str}' (ticker={row.get('ticker','?')}) "
                        f"not in _SECTOR_TO_ETF — fire dropped; add alias if intentional"
                    )
                    continue
                if etf_node not in armed_nodes:
                    continue
                # Append to armed entry
                for armed_entry in armed:
                    if armed_entry["node"] == etf_node:
                        armed_entry["member_fires"].append({
                            "ticker": row.get("ticker", ""),
                            "tier": tc,
                            "provisional": bool(sig.get("provisional")),
                            "fresh_bars": sig.get("fresh_bars"),
                            "label": row.get("label", ""),
                        })
                        break

        # ── 6. Build base_rates block (CONFIRMED display_with_edge, §W2 lineage) ──
        base_rates = {
            "in_window_wr21": 0.652,
            "outside_window_wr21": 0.536,
            "holdout_delta_pp": 10.7,
            "holdout_ci_lo_pp": 3.8,
            "holdout_ci_hi_pp": 17.9,
            "modern_track_from": "2022-06-30",
            "n_windows": 31,
            "confidence_class": "display_with_edge",
            "lineage": "#1533 W2_FORMAL_RESULTS",
            "note": (
                "IN-window member fires WR21 65.2% vs 53.6% outside "
                "(holdout +10.7pp CI [+3.8, +17.9]); modern track ≥2022-06-30, "
                "31 windows. Growth/cyclical tilt; defensive sectors negative. "
                "NOT a forecast."
            ),
        }

        # ── 7. Promotion clock ──
        turn_desk_ledger_path = data_dir / "oracle" / "turn_desk_ledger.jsonl"
        windows_accrued = 0
        if turn_desk_ledger_path.exists():
            for line in turn_desk_ledger_path.read_text().splitlines():
                if line.strip():
                    try:
                        r = _json.loads(line)
                        if r.get("kind") == "window_open":
                            windows_accrued += 1
                    except Exception:  # noqa: BLE001
                        pass

        promotion_clock = {
            "windows_accrued": windows_accrued,
            "windows_required": 15,
        }

        # ── 7b. Load existing qual_filter stamps for display (W7 additive) ──
        # Read stamps written by previous runs (tonight's stamps are written in
        # Step 17, AFTER this step; this block is display-only and degrades
        # gracefully if the file is absent on first run).
        _stamps_path = data_dir / "oracle" / "qual_filter_stamps.jsonl"
        _stamps_by_window: dict[str, list[str]] = {}  # window_key → [filter_id, ...]
        if _stamps_path.exists():
            for _sl in _stamps_path.read_text().splitlines():
                _sl = _sl.strip()
                if not _sl:
                    continue
                try:
                    _sr = _json.loads(_sl)
                    if _sr.get("value") is True:
                        _wk = _sr.get("window_key", "")
                        _fid = _sr.get("filter_id", "")
                        if _wk and _fid:
                            _stamps_by_window.setdefault(_wk, []).append(_fid)
                except Exception:  # noqa: BLE001
                    pass
        # Annotate each armed entry with its true-stamped filter ids (display only).
        for _ae in armed:
            _node = _ae["node"]
            _ae_qual_true: list[str] = []
            for _fd in _ae.get("fire_dates", []):
                _wk = f"{_node}::a15::{_fd}"
                _ae_qual_true.extend(_stamps_by_window.get(_wk, []))
            _ae["qual_filters_true"] = sorted(set(_ae_qual_true))

        # Compute qual_accrual_note for the payload caveats section.
        _accrual_path = data_dir / "oracle" / "qual_filter_accrual.json"
        _qual_accrual_note = ""
        if _accrual_path.exists():
            try:
                _ac = _json.loads(_accrual_path.read_text())
                _per = _ac.get("per_filter") or {}
                _parts = [
                    f"{fid} n={v.get('filter_true', {}).get('n', 0)}"
                    for fid, v in _per.items()
                ]
                if _parts:
                    _qual_accrual_note = "Qualitative filters accruing: " + "; ".join(_parts)
            except Exception:  # noqa: BLE001
                pass

        # ── 8. Build payload ──
        # n_windows=31 is the full-sample count; holdout arm has n=15.
        # Disclaimer makes both counts explicit to avoid overstating holdout evidence.
        disclaimers = [
            "DISPLAY-WITH-EDGE — desk feeds no score, gate, or ordering surface.",
            "WR21 65.2% vs 53.6% (holdout Δ+10.7pp CI [+3.8, +17.9]) — 31 modern-track windows (holdout n=15), ≥2022-06-30.",
            "Growth/cyclical tilt; defensive sectors (XLV, XLP, XLU) were negative in-window.",
            "T3 fires carry ~23.8% repaint risk — badge shown on each fire.",
            "Not a forecast.",
        ]
        payload: dict = {
            "schema": "oracle_turn_desk.v1",
            "asof": panel_asof,
            "member_fires_asof": member_fires_asof,
            "armed": armed,
            "base_rates": base_rates,
            "promotion_clock": promotion_clock,
            "qual_accrual_note": _qual_accrual_note,
            "disclaimers": disclaimers,
        }

        # Final banned-key sweep — recursive over entire payload tree (dict keys + list items).
        # Enforces Constitution III: no field name containing forecast/predicted/target/expected_return.
        def _check_banned_keys_recursive(obj: object, path: str) -> bool:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    for banned in _BANNED_KEY_SUBS:
                        if banned in k:
                            _annotation(
                                f"oracle_nightly: turn_desk — BANNED key '{k}' at {path}"
                            )
                            return False
                    if not _check_banned_keys_recursive(v, f"{path}.{k}"):
                        return False
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    if not _check_banned_keys_recursive(item, f"{path}[{i}]"):
                        return False
            return True

        if not _check_banned_keys_recursive(payload, "payload"):
            return False

        # ── 9. Stamp + write artifact ──
        artifact_path = site_dir / "basketdata" / "oracle_turn_desk.json"
        prev_payload = _read_json(artifact_path)
        stamped = stamp_if_changed(
            payload, prev_payload, artifact_id="oracle-turn-desk"
        )

        if not dry_run:
            _write_json(artifact_path, stamped)
        log.info(
            "turn_desk: artifact written — armed=%d, member_fires_total=%d, asof=%s",
            len(armed),
            sum(len(a["member_fires"]) for a in armed),
            panel_asof,
        )

        # ── 10. Forward ledger (keep-first) ──
        if not dry_run:
            _write_turn_desk_ledger(
                armed, panel_asof, data_dir, all_dates_list, date_to_pos
            )

        return True, armed, panel_asof, all_dates_list

    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: turn_desk FAILED: {e}")
        return False, [], "", []


def _step_operator_tape_outcomes(data_dir: Path, dry_run: bool) -> bool:
    """PR-A3 Step 18: Operator-tape outcome resolution — append-only nightly join.

    For each tape row not yet resolved:
      - system_state_at_stamp: what Oracle showed for those nodes at pit_stamp
        (from forward_ledger.jsonl episodes; 'unresolvable_pre_capture' if absent)
      - realized_outcome: deterministic 21d forward return (matured only)
      - override_flag: operator direction vs system state (null if unresolvable)

    Appends new/updated rows to data/oracle/operator_tape_outcomes.jsonl.
    Writes display-only scorecard to data/oracle/operator_scorecard.json.

    Loud-error pattern: ::error:: annotation + returns False; does not block
    earlier steps. NEVER mutates operator_tape.jsonl.
    """
    log.info("=== Step 18: Operator-tape outcome resolution (PR-A3) ===")
    try:
        from engine.oracle.tape_outcomes import (
            resolve_tape_outcomes,
            build_operator_scorecard,
            write_operator_scorecard,
        )

        summary = resolve_tape_outcomes(data_dir, dry_run=dry_run)
        log.info(
            "tape_outcomes: n_tape=%d new=%d skipped=%d resolved=%d pending=%d",
            summary.get("n_tape", 0),
            summary.get("n_new", 0),
            summary.get("n_skipped", 0),
            summary.get("n_resolved", 0),
            summary.get("n_pending", 0),
        )

        # Scorecard — always rebuild from outcomes ledger (display-only overwrite)
        scorecard = build_operator_scorecard(data_dir)
        write_operator_scorecard(scorecard, data_dir, dry_run=dry_run)
        log.info(
            "tape_outcomes: scorecard n_resolved=%d n_pending=%d",
            scorecard.get("n_resolved", 0),
            scorecard.get("n_pending", 0),
        )
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: tape_outcomes FAILED: {e}")
        return False


def _step_qual_filter_stamps(
    armed: list[dict],
    panel_asof: str,
    data_dir: Path,
    all_dates_list: list[str],
    dry_run: bool,
) -> bool:
    """W7 Step 17: Qualitative filter PIT stamping + accrual report.

    Writes:
      data/oracle/qual_filter_stamps.jsonl  (keep-first, PIT stamps)
      data/oracle/qual_filter_accrual.json  (conditional WR21 on matured windows)

    Loud-error pattern: ::error:: annotation + returns False; does not block
    earlier steps.  Runs AFTER the turn desk (Step 15) so window_open keys exist.

    Law: no retro-stamping of pre-existing windows — this step stamps only the
    windows passed in `armed` (current night's armed set), which is always a
    subset of the window_open rows just written to turn_desk_ledger.jsonl.
    """
    log.info("=== Step 17: Qualitative filter stamps + accrual (W7) ===")
    try:
        from engine.oracle.qual_filters import (
            stamp_window_open, build_accrual_report, write_accrual_report
        )

        n_new = stamp_window_open(
            armed, panel_asof, data_dir, all_dates_list, dry_run=dry_run
        )
        log.info("qual_filter_stamps: %d new stamp rows", n_new)

        # Accrual report — runs even when no new stamps (updates as windows mature)
        accrual = build_accrual_report(data_dir)
        write_accrual_report(accrual, data_dir, dry_run=dry_run)
        log.info(
            "qual_filter_accrual: n_graded_windows=%d n_filters=%d",
            accrual.get("n_graded_windows", 0),
            len(accrual.get("per_filter") or {}),
        )
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: qual_filter_stamps FAILED: {e}")
        return False


def _step_reversion_promotion_scan(
    data_dir: Path,
    site_dir: Path,
    dry_run: bool,
) -> bool:
    """W4.a Step 16: Reversion promotion scan (P2, armed-not-fired).

    Reads registry reversion-block compounds + P0 forward ledger (matured rows
    only); calls grant_authority VERBATIM; writes
    data/oracle/reversion_promotion_queue.json + data/oracle/reversion_authority.json
    (only for human-ratified rows) + data/neuralweb/governance.jsonl events.

    NEVER auto-promotes: all promotions require human ratified_by in queue row.

    Additive nightly step placed at END per W4_SPEC.md §W4.a:
    'Nightly step appended at END (after the current last step)'.

    Loud-error pattern: ::error:: annotation + returns False; does not block
    earlier steps.
    """
    log.info("=== Step 16: Reversion promotion scan (W4.a P2) ===")
    try:
        from scripts.oracle_reversion_promotion_scan import run_promotion_scan
        summary = run_promotion_scan(data_dir, site_dir, dry_run=dry_run)
        log.info(
            "reversion_promotion_scan: n_compounds=%d candidates=%d lapses=%d accruing=%d",
            summary.get("n_compounds", 0),
            summary.get("n_candidates", 0),
            summary.get("n_lapses", 0),
            summary.get("n_accruing", 0),
        )
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: reversion_promotion_scan FAILED: {e}")
        return False


def _step_tape_onset(
    data_dir: "Path", site_dir: "Path", dry_run: bool
) -> bool:
    """Step 19: TAPE-ONSET (unconfirmed) display tier — registration §2/§3/§5.

    Constitution §V additive-only law: appended at END of oracle nightly step order.
    Loud-error pattern: ::error:: annotation + returns False; later steps still attempt.
    Payload validated before write; prior payload kept on failure.

    Reads: data/oracle/panel_s.parquet, data/oracle/episodes_s.parquet
    Writes (additive fields on existing turn_desk artifact):
        tape_onset_nodes — dict per-node tape_onset_unconfirmed + tape_onset_stats
    Writes (new artifact):
        data/oracle/tape_onset_ledger.jsonl — trial ledger, keep-first, PIT-stamped

    Registration: research/ORACLE_TAPE_ONSET_TIER_REGISTRATION.md
    Verdict vocabulary: NULL / DISPLAY-WITH-EDGE (secondary tier cap per Constitution §I.4)
    Evaluation clock: 2026-10-09
    """
    log.info("=== Step 19: TAPE-ONSET (unconfirmed) display tier (FTR W7) ===")
    try:
        import pandas as _pd
        import json as _json
        from engine.oracle.tape_onset import (
            compute_tape_onset_payload,
            append_tape_onset_ledger,
            check_banned_keys,
        )
        from engine.neuralweb.envelope import stamp_if_changed

        # ── 1. Load panel + episodes ──
        panel_path = data_dir / "oracle" / "panel_s.parquet"
        episodes_path = data_dir / "oracle" / "episodes_s.parquet"

        if not panel_path.exists():
            _annotation("oracle_nightly: tape_onset — panel_s.parquet missing, skipping")
            return False

        panel = _pd.read_parquet(panel_path)

        episodes_df: "_pd.DataFrame | None" = None
        if episodes_path.exists():
            episodes_df = _pd.read_parquet(episodes_path)
        else:
            log.warning("tape_onset: episodes_s.parquet missing — episode-suppression unavailable; flag may over-fire")

        # ── 2. Compute per-node payload ──
        tape_onset_payload = compute_tape_onset_payload(panel, episodes_df)
        n_nodes = len(tape_onset_payload)
        n_flagged = sum(1 for v in tape_onset_payload.values() if v.get("tape_onset_unconfirmed"))
        log.info("tape_onset: computed %d nodes, %d flagged", n_nodes, n_flagged)

        # ── 3. Banned-key check on full payload before write ──
        banned_errs = check_banned_keys(tape_onset_payload, "tape_onset_payload")
        if banned_errs:
            for err in banned_errs:
                _annotation(f"oracle_nightly: tape_onset — {err}")
            _annotation("oracle_nightly: tape_onset — BANNED KEYS found; prior artifact preserved")
            return False

        # ── 4. Additive fields on existing turn_desk artifact ──
        # The turn_desk artifact carries armed sector windows; we add a
        # `tape_onset_nodes` top-level field (additive, tolerant-reader).
        turn_desk_path = site_dir / "basketdata" / "oracle_turn_desk.json"
        prev_turn_desk = _read_json(turn_desk_path) or {}

        if not isinstance(prev_turn_desk, dict):
            prev_turn_desk = {}

        # Augment with tape_onset_nodes (additive: never overwrite unrelated keys)
        augmented = {**prev_turn_desk, "tape_onset_nodes": tape_onset_payload}

        # ── 5. Write tape_onset artifact (separate from turn_desk for clarity) ──
        # The Constitution additive-only law says additive *fields* on existing artifacts.
        # We write them back onto oracle_turn_desk.json AND emit a separate sidecar
        # so the display layer can load it independently without re-parsing the full desk.
        asof = ""
        if isinstance(panel.index, _pd.MultiIndex):
            dates = panel.index.get_level_values("date")
            if len(dates):
                asof = dates.max().strftime("%Y-%m-%d")

        tape_onset_sidecar: dict = {
            "schema": "oracle_tape_onset.v1",
            "asof": asof,
            "registration": "research/ORACLE_TAPE_ONSET_TIER_REGISTRATION.md",
            "confidence_class": "descriptive",
            "display_tier": "TAPE-ONSET (unconfirmed)",
            "authority": {
                "may_rank": False,
                "may_gate": False,
                "may_size": False,
                "may_escalate": False,
            },
            "evaluation_clock": "2026-10-09",
            "disclaimers": {
                "display_only": True,
                "unconfirmed_qualifier": True,
                "note_en": (
                    "TAPE-ONSET (unconfirmed): raw accel_z >= 1.0 with no active episode. "
                    "Historical rates printed from data; descriptive only. "
                    "Not a forecast. Evaluation clock 2026-10-09."
                ),
                "note_zh": (
                    "TAPE-ONSET（未确认）：原始加速度z值>=1.0且无活跃情节。"
                    "历史发生率来自数据计算；仅供描述性参考。"
                    "非预测信号。评估时钟：2026-10-09。"
                ),
            },
            "nodes": tape_onset_payload,
        }

        # Banned-key sweep on sidecar
        sidecar_banned = check_banned_keys(tape_onset_sidecar, "sidecar")
        if sidecar_banned:
            for err in sidecar_banned:
                _annotation(f"oracle_nightly: tape_onset — sidecar banned key: {err}")
            return False

        sidecar_path = site_dir / "basketdata" / "oracle_tape_onset.json"
        prev_sidecar = _read_json(sidecar_path)
        stamped_sidecar = stamp_if_changed(
            tape_onset_sidecar, prev_sidecar, artifact_id="oracle-tape-onset"
        )

        if not dry_run:
            _write_json(sidecar_path, stamped_sidecar)
            # Also update turn_desk with the additive tape_onset_nodes field
            _write_json(turn_desk_path, augmented)

        log.info(
            "tape_onset: sidecar written asof=%s nodes=%d flagged=%d",
            asof, n_nodes, n_flagged,
        )

        # ── 6. Trial ledger append (registration §4) ──
        ledger_path = data_dir / "oracle" / "tape_onset_ledger.jsonl"
        n_new = append_tape_onset_ledger(
            tape_onset_payload, asof, ledger_path, dry_run=dry_run
        )
        log.info("tape_onset_ledger: %d new flag rows appended (keep-first)", n_new)

        return True

    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: tape_onset FAILED: {e}")
        return False


def _write_turn_desk_ledger(
    armed: list[dict],
    panel_asof: str,
    data_dir: Path,
    all_dates_list: list[str],
    date_to_pos: dict[str, int],
) -> None:
    """Append keep-first rows to data/oracle/turn_desk_ledger.jsonl.

    Kinds:
      window_open  — key node::a15::fire_date (one per A15 fire)
      member_fire  — key window_key::ticker::fire_date (today's cascade fires in-window)

    Nightly is the sole advancer; keep-first = once written, never overwritten.
    """
    import json as _json
    from datetime import datetime, timezone

    ledger_path = data_dir / "oracle" / "turn_desk_ledger.jsonl"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing keys
    existing_keys: set[str] = set()
    if ledger_path.exists():
        for line in ledger_path.read_text().splitlines():
            if line.strip():
                try:
                    r = _json.loads(line)
                    if r.get("key"):
                        existing_keys.add(r["key"])
                except Exception:  # noqa: BLE001
                    pass

    new_rows: list[dict] = []
    now_utc = datetime.now(timezone.utc).isoformat()

    for armed_entry in armed:
        node = armed_entry["node"]
        for fire_date in armed_entry.get("fire_dates", []):
            wkey = f"{node}::a15::{fire_date}"
            if wkey not in existing_keys:
                new_rows.append({
                    "kind": "window_open",
                    "key": wkey,
                    "node": node,
                    "fire_date": fire_date,
                    "pit_stamp": panel_asof,
                    "registered_at": now_utc,
                    # h=21 maturity fields (graded on subsequent nights)
                    "fwd_ret_21": None,
                    "outcome_mature": False,
                })
                existing_keys.add(wkey)

        # member fires inside this window.
        # Key on the member's OWN first cascade fire_date (member_fires_asof
        # from the standouts artifact, falling back to panel_asof) rather than
        # panel_asof, so cross-night re-observations of the same economic event
        # are deduped and don't inflate the grading population (spec §4 fix).
        member_fires_asof_for_key = armed_entry.get("_member_fires_asof", panel_asof)
        for mf in armed_entry.get("member_fires", []):
            ticker = mf.get("ticker", "")
            wkey = f"{node}::a15::{armed_entry.get('fire_dates', [''])[0] if armed_entry.get('fire_dates') else ''}"
            # Key on the asof of the standouts artifact (stable for the same
            # cascade event across re-runs on the same night), not panel_asof.
            mkey = f"{wkey}::{ticker}::{member_fires_asof_for_key}"
            if mkey not in existing_keys:
                new_rows.append({
                    "kind": "member_fire",
                    "key": mkey,
                    "node": node,
                    "ticker": ticker,
                    "tier": mf.get("tier"),
                    "provisional": mf.get("provisional"),
                    "fire_date": member_fires_asof_for_key,
                    "pit_stamp": panel_asof,
                    "registered_at": now_utc,
                    "fwd_ret_21": None,
                    "outcome_mature": False,
                })
                existing_keys.add(mkey)

    # Maturity grading pass for existing ungraded rows
    _grade_turn_desk_ledger(ledger_path, data_dir, all_dates_list, date_to_pos)

    if new_rows:
        with open(ledger_path, "a") as fh:
            for row in new_rows:
                fh.write(_json.dumps(row, separators=(",", ":"), default=str) + "\n")
        log.info("turn_desk_ledger: %d new rows appended", len(new_rows))


def _grade_turn_desk_ledger(
    ledger_path: Path,
    data_dir: Path,
    all_dates_list: list[str],
    date_to_pos: dict[str, int],
) -> None:
    """Grade mature rows (h=21) using massive_stock_day closes (absolute return)."""
    import json as _json
    import pandas as _pd

    if not ledger_path.exists():
        return

    massive_dir = data_dir / "massive_stock_day"
    if not massive_dir.exists():
        return

    raw_lines = ledger_path.read_text().splitlines()
    updated_lines: list[str] = []
    changed = False

    for line in raw_lines:
        line_s = line.strip()
        if not line_s:
            updated_lines.append(line)
            continue
        try:
            row = _json.loads(line_s)
        except Exception:  # noqa: BLE001
            updated_lines.append(line)
            continue

        if row.get("outcome_mature") is True or row.get("fwd_ret_21") is not None:
            updated_lines.append(line)
            continue

        fire_date = row.get("fire_date", "")
        ticker = row.get("ticker") if row.get("kind") == "member_fire" else None
        if not ticker or not fire_date:
            updated_lines.append(line)
            continue

        ticker_path = massive_dir / f"{ticker}.parquet"
        if not ticker_path.exists():
            updated_lines.append(line)
            continue

        try:
            closes = _pd.read_parquet(ticker_path)["close"]
            fire_pos = date_to_pos.get(fire_date)
            if fire_pos is None:
                updated_lines.append(line)
                continue
            exit_pos = fire_pos + _MATURITY_H
            if exit_pos >= len(all_dates_list):
                updated_lines.append(line)
                continue
            exit_date = all_dates_list[exit_pos]
            # Entry = close at fire_date (executed at next close → fire_date+1)
            entry_date_str = all_dates_list[min(fire_pos + 1, len(all_dates_list) - 1)]
            entry_date = _pd.Timestamp(entry_date_str)
            exit_date_ts = _pd.Timestamp(exit_date)
            closes_sorted = closes.sort_index()
            entry_prices = closes_sorted[closes_sorted.index <= entry_date]
            exit_prices = closes_sorted[closes_sorted.index <= exit_date_ts]
            if entry_prices.empty or exit_prices.empty:
                updated_lines.append(line)
                continue
            entry_close = float(entry_prices.iloc[-1])
            exit_close = float(exit_prices.iloc[-1])
            if entry_close == 0:
                updated_lines.append(line)
                continue
            fwd_ret_21 = round((exit_close / entry_close - 1), 6)
            row["fwd_ret_21"] = fwd_ret_21
            row["outcome_mature"] = True
            updated_lines.append(_json.dumps(row, separators=(",", ":"), default=str))
            changed = True
        except Exception:  # noqa: BLE001
            updated_lines.append(line)
            continue

    if changed:
        ledger_path.write_text("\n".join(updated_lines) + "\n")
        log.info("turn_desk_ledger: graded mature rows")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Oracle nightly pipeline")
    p.add_argument("--data-dir", type=Path, default=None)
    p.add_argument("--site-dir", type=Path, default=None)
    p.add_argument("--skip-panel", action="store_true")
    p.add_argument("--skip-graph", action="store_true")
    p.add_argument("--skip-episodes", action="store_true")
    p.add_argument("--skip-personality", action="store_true",
                   help="Skip B1 personality step (use committed personality.json)")
    p.add_argument("--skip-timemachine", action="store_true",
                   help="Skip the Time Machine feed export. Use on the RENDER path: "
                        "the export needs the panel+episode parquets, which are built "
                        "OFF-render (build_oracle_panel forbids render-path use), so the "
                        "dedicated oracle_offrender CI job owns the feed rebuild+commit.")
    p.add_argument("--dry-run", action="store_true", help="Run all steps but write no files")
    args = p.parse_args()

    from lib import config as _cfg
    data_dir = args.data_dir or _cfg.data_dir()
    site_dir = args.site_dir or (_cfg.ROOT / "site")

    log.info("oracle_nightly: data_dir=%s site_dir=%s dry_run=%s", data_dir, site_dir, args.dry_run)

    failures: list[str] = []
    t_total = time.time()

    # --- Step 1: Panel ---
    if not args.skip_panel:
        if not _step_panel(data_dir, args.dry_run):
            failures.append("panel")
        else:
            # --- Step 1b: Publish oracle panels to R2 (PR-C1 RUL-7) ---
            # Named single-writer: only the Mac-side oracle ops lane runs this.
            # No-op when R2 creds absent; never blocks subsequent steps on failure.
            log.info("=== Step 1b: Publish oracle panels to R2 (PR-C1) ===")
            try:
                from scripts.publish_oracle_panels import publish as _publish_panels
                rc = _publish_panels(data_dir=data_dir, dry_run=args.dry_run)
                if rc != 0:
                    _annotation("oracle_nightly: publish_oracle_panels returned non-zero (non-fatal)")
                else:
                    log.info("publish_oracle_panels: done")
            except Exception as _e:  # noqa: BLE001
                _annotation(f"oracle_nightly: publish_oracle_panels FAILED: {_e} (non-fatal)")
    else:
        log.info("=== Step 1: Panel SKIPPED (--skip-panel) ===")

    # --- Step 2: Graph ---
    if not args.skip_graph:
        if not _step_graph(data_dir, args.dry_run):
            failures.append("graph")
    else:
        log.info("=== Step 2: Graph SKIPPED (--skip-graph) ===")

    # --- Step 3: Episodes ---
    if not args.skip_episodes:
        if not _step_episodes(data_dir, args.dry_run):
            failures.append("episodes")
    else:
        log.info("=== Step 3: Episodes SKIPPED (--skip-episodes) ===")

    # --- Step 3b: Personality (B1) — AFTER episodes, BEFORE state ---
    if not args.skip_personality:
        if not _step_personality(data_dir, args.dry_run):
            failures.append("personality")
    else:
        log.info("=== Step 3b: Personality SKIPPED (--skip-personality) ===")

    # --- Step 4: Memory ---
    if not _step_memory_base_rates(data_dir, args.dry_run):
        failures.append("memory_base_rates")

    # --- Step 5: Time Machine ---
    if not args.skip_timemachine:
        if not _step_timemachine(data_dir, site_dir, args.dry_run):
            failures.append("timemachine")
    else:
        log.info("=== Step 5: Time Machine SKIPPED (--skip-timemachine) ===")

    # --- Step 6: Oracle state ---
    oracle_state = _step_oracle_state(data_dir, site_dir, args.dry_run)
    if oracle_state is None:
        failures.append("oracle_state")
        oracle_state = {}

    # --- Step 7: Alerts ---
    n_alerts = _step_alerts(oracle_state, args.dry_run)

    # --- Step 8: Directive ---
    if not _step_directive(oracle_state, data_dir, args.dry_run):
        failures.append("directive")

    # --- Step 9: Forward ledger ---
    n_ledger = _step_ledger(oracle_state, data_dir, args.dry_run)

    # --- Step 10: Banner ---
    if not _step_banner(oracle_state, site_dir, args.dry_run):
        failures.append("banner")

    # --- Step 11: Compound live accrual (W-B3) ---
    if not _step_compound_live_accrual(data_dir, args.dry_run):
        failures.append("compound_live_accrual")

    # --- Step 11b: Reversion forward ledger (P0) ---
    if not _step_reversion_forward_ledger(data_dir, args.dry_run):
        failures.append("reversion_forward_ledger")

    # --- Step 11c: Reversion state sidecar (P1, display tier) ---
    if not _step_reversion_state(data_dir, site_dir, args.dry_run):
        failures.append("reversion_state")

    # --- Step 12: Promotion scan (W-B1) ---
    if not _step_promotion_scan(data_dir, args.dry_run):
        failures.append("promotion_scan")

    # --- Step 13: Sentinels (W-B4) — append-only at END per additive-only law ---
    if not _step_sentinels(data_dir, args.dry_run):
        failures.append("sentinels")

    # --- Step 14: Hypothesis inbox (P9) — append-only at END per additive-only law ---
    inbox_counts = _step_hypothesis_inbox(data_dir, args.dry_run)
    if not inbox_counts:  # empty dict = failure sentinel (review major: old guard was dead logic)
        # An empty dict means failure was caught inside _step_hypothesis_inbox
        failures.append("hypothesis_inbox")

    # --- Step 15: Rotation Turn Desk (W6) — DISPLAY-ONLY, additive at END ---
    td_ok, td_armed, td_panel_asof, td_all_dates = _step_turn_desk(
        data_dir, site_dir, args.dry_run
    )
    if not td_ok:
        failures.append("turn_desk")

    # --- Step 16: Reversion promotion scan (W4.a P2) — additive at END ---
    # W4_SPEC.md: 'Nightly step appended at END (after the current last step)'
    # NEVER auto-promotes; loud-error pattern; runs AFTER P0 ledger (11b) + P1
    # sidecar (11c) so it has the freshest base_rate and matured rows.
    if not _step_reversion_promotion_scan(data_dir, site_dir, args.dry_run):
        failures.append("reversion_promotion_scan")

    # --- Step 17: Qualitative filter stamps + accrual (W7) — additive at END ---
    # Runs AFTER turn_desk (Step 15) so the window_open keys exist in the ledger.
    # Seam: Step 15 returns armed + all_dates_list for PIT reuse without re-running A15.
    if not _step_qual_filter_stamps(
        td_armed, td_panel_asof, data_dir, td_all_dates, args.dry_run
    ):
        failures.append("qual_filter_stamps")

    # --- Step 18: Operator-tape outcome resolution (PR-A3) — additive at END ---
    # Appends to data/oracle/operator_tape_outcomes.jsonl + display-only scorecard.
    # Never mutates operator_tape.jsonl. Loud-error pattern.
    if not _step_operator_tape_outcomes(data_dir, args.dry_run):
        failures.append("tape_outcomes")

    # --- Step 19: TAPE-ONSET (unconfirmed) display tier (FTR W7) — additive at END ---
    # Registration: research/ORACLE_TAPE_ONSET_TIER_REGISTRATION.md (merged before this build).
    # Additive fields on oracle_turn_desk.json + sidecar site/basketdata/oracle_tape_onset.json
    # + trial ledger data/oracle/tape_onset_ledger.jsonl. DISPLAY-ONLY, no authority granted.
    # Loud-error pattern: ::error:: annotation + pipeline continues on failure.
    n_tape_onset_ledger = 0
    if not _step_tape_onset(data_dir, site_dir, args.dry_run):
        failures.append("tape_onset")

    elapsed = time.time() - t_total
    log.info(
        "oracle_nightly: DONE in %.1fs — %d new alerts, %d ledger entries, failures=%s",
        elapsed, n_alerts, n_ledger, failures or "none",
    )

    # Summary
    print(f"\n=== oracle_nightly summary ===")
    print(f"  asof:          {oracle_state.get('asof')}")
    print(f"  active_eps:    {len(oracle_state.get('active_episodes') or [])}")
    print(f"  watchlist:     {len(oracle_state.get('onset_watchlist') or [])}")
    print(f"  n_complexes:   {(oracle_state.get('regime') or {}).get('n_active_complexes', 0)}")
    print(f"  new_alerts:    {n_alerts}  (first run = 0, silent seed)")
    print(f"  ledger_new:    {n_ledger}")
    print(f"  inbox_rows:    {(inbox_counts or {}).get('total', 0)}  "
          f"(as={inbox_counts.get('analogue_surprise',0) if inbox_counts else 0}, "
          f"dm={inbox_counts.get('detection_miss',0) if inbox_counts else 0}, "
          f"sld={inbox_counts.get('screen_live_divergence',0) if inbox_counts else 0}, "
          f"sent={inbox_counts.get('sentinel',0) if inbox_counts else 0})")
    print(f"  tape_onset_ledger_new: {n_tape_onset_ledger}")
    print(f"  elapsed_s:     {elapsed:.1f}")
    if failures:
        print(f"  FAILURES:      {failures}")

    # Nonzero exit on any failure (GitHub Actions sees the ::error:: annotations above)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
