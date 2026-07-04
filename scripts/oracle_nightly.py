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
  4. Memory        — write rotation_directive.json and memory_base_rates.json.
  5. Time Machine  — re-run build_oracle_timemachine (export feed).  ~30 s.
  6. Oracle state  — build oracle_state.json (the bus payload).
  7. Alerts        — diff vs prior state, append to oracle_alerts.jsonl.
  8. Directive     — write data/oracle/rotation_directive.json.
  9. Ledger        — append new detections to data/oracle/forward_ledger.jsonl
                     (keep-FIRST, PIT-stamped).
  10. Banner       — additive oracle entry into site/wh_banner.json when a
                     complex reaches confirmed tier with breadth >= floor.

Usage
-----
  python scripts/oracle_nightly.py [--data-dir PATH] [--site-dir PATH]
                                   [--skip-panel] [--skip-graph] [--skip-episodes]

  --skip-panel     skip the panel rebuild (use committed parquets)
  --skip-graph     skip the graph rebuild (use committed graph_s.json)
  --skip-episodes  skip the episode rebuild (use committed episodes)
  --dry-run        run everything but write no files (for timing + smoke tests)

R4 BINDING (ORACLE_GAUNTLET_P3_ADJUDICATION.md):
  - Nothing here ships a predictive claim.
  - Alerts embed the false-start rate from the gauntlet results.
  - Banner is gated on confirmed + breadth floor.
  - Tilt stays config-gated OFF.
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

def _step_panel(data_dir: Path, dry_run: bool) -> bool:
    """Re-run build_oracle_panel (Tier S only for nightly speed)."""
    t0 = time.time()
    log.info("=== Step 1: Panel update (Tier S) ===")
    try:
        from engine.oracle.panel import build_panel_s
        if not dry_run:
            panel_s = build_panel_s(data_dir=data_dir)
            panel_s.to_parquet(data_dir / "oracle" / "panel_s.parquet")
        log.info("Panel S built in %.1fs", time.time() - t0)
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: panel_s rebuild FAILED: {e}")
        return False


def _step_graph(data_dir: Path, dry_run: bool) -> bool:
    """Re-run build_oracle_graph."""
    t0 = time.time()
    log.info("=== Step 2: Graph update ===")
    try:
        from engine.oracle.graph import build_graph
        import pandas as pd
        panel_path = data_dir / "oracle" / "panel_s.parquet"
        if not panel_path.exists():
            log.warning("oracle_nightly: panel_s.parquet not found — skipping graph")
            return False
        panel = pd.read_parquet(panel_path)
        rg = _read_json(data_dir / "oracle" / "rotation_groups.json") or {}
        backbone = rg.get("complexes") or []
        graph = build_graph(panel, backbone)
        if not dry_run:
            (data_dir / "oracle" / "graph_s.json").write_text(
                json.dumps(graph, separators=(",", ":"), default=str)
            )
        log.info("Graph built in %.1fs", time.time() - t0)
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: graph rebuild FAILED: {e}")
        return False


def _step_episodes(data_dir: Path, dry_run: bool) -> bool:
    """Re-run build_oracle_episodes."""
    t0 = time.time()
    log.info("=== Step 3: Episodes rebuild ===")
    try:
        from engine.oracle.episodes import build_episodes
        import pandas as pd
        panel_path = data_dir / "oracle" / "panel_s.parquet"
        if not panel_path.exists():
            log.warning("oracle_nightly: panel_s.parquet not found — skipping episodes")
            return False
        panel = pd.read_parquet(panel_path)
        rg = _read_json(data_dir / "oracle" / "rotation_groups.json")
        ep = build_episodes(panel, rotation_groups=rg)
        if not dry_run:
            ep.to_parquet(data_dir / "oracle" / "episodes_s.parquet")
        log.info("Episodes built: %d rows in %.1fs", len(ep), time.time() - t0)
        return True
    except Exception as e:  # noqa: BLE001
        _annotation(f"oracle_nightly: episodes rebuild FAILED: {e}")
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
    """Build oracle_state.json (the bus payload)."""
    log.info("=== Step 6: Oracle state ===")
    try:
        from engine.oracle.live import build_oracle_state, write_oracle_state
        state = build_oracle_state(data_dir=data_dir)
        if not dry_run:
            write_oracle_state(state, out_dir=site_dir / "basketdata")
        log.info(
            "oracle_state.json: asof=%s, %d active_episodes, %d watchlist, %d active_complexes",
            state.get("asof"),
            len(state.get("active_episodes") or []),
            len(state.get("onset_watchlist") or []),
            (state.get("regime") or {}).get("n_active_complexes", 0),
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
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Oracle nightly pipeline")
    p.add_argument("--data-dir", type=Path, default=None)
    p.add_argument("--site-dir", type=Path, default=None)
    p.add_argument("--skip-panel", action="store_true")
    p.add_argument("--skip-graph", action="store_true")
    p.add_argument("--skip-episodes", action="store_true")
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
    print(f"  elapsed_s:     {elapsed:.1f}")
    if failures:
        print(f"  FAILURES:      {failures}")

    # Nonzero exit on any failure (GitHub Actions sees the ::error:: annotations above)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
