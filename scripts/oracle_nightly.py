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

Usage
-----
  python scripts/oracle_nightly.py [--data-dir PATH] [--site-dir PATH]
                                   [--skip-panel] [--skip-graph] [--skip-episodes]
                                   [--skip-personality]

  --skip-panel        skip the panel rebuild (use committed parquets)
  --skip-graph        skip the graph rebuild (use committed graph_s.json)
  --skip-episodes     skip the episode rebuild (use committed episodes)
  --skip-personality  skip the B1 personality step (use committed personality.json)
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
        log.info(
            "hypothesis_inbox: total=%d (analogue_surprise=%d, detection_miss=%d, "
            "screen_live_divergence=%d, sentinel=%d)",
            counts["total"],
            counts["analogue_surprise"],
            counts["detection_miss"],
            counts["screen_live_divergence"],
            counts["sentinel"],
        )
        return counts
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: hypothesis_inbox FAILED: {e}")
        return {}


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
    if not _step_timemachine(data_dir, site_dir, args.dry_run):
        failures.append("timemachine")

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

    # --- Step 12: Promotion scan (W-B1) ---
    if not _step_promotion_scan(data_dir, args.dry_run):
        failures.append("promotion_scan")

    # --- Step 13: Sentinels (W-B4) — append-only at END per additive-only law ---
    if not _step_sentinels(data_dir, args.dry_run):
        failures.append("sentinels")

    # --- Step 14: Hypothesis inbox (P9) — append-only at END per additive-only law ---
    inbox_counts = _step_hypothesis_inbox(data_dir, args.dry_run)
    if not inbox_counts and inbox_counts != {}:
        # An empty dict means failure was caught inside _step_hypothesis_inbox
        failures.append("hypothesis_inbox")

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
    print(f"  elapsed_s:     {elapsed:.1f}")
    if failures:
        print(f"  FAILURES:      {failures}")

    # Nonzero exit on any failure (GitHub Actions sees the ::error:: annotations above)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
