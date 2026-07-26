"""TXI-W5 Loop-C proposal-lane runner (gated, weekly) — pack generation + CHF-reply ingest.

This is the WIRING that lets NEW transmission chains be proposed (semi-)autonomously through
the EXISTING CHF brainstorm lane and land as hypothesis-tier chains. It builds NO second LLM
loop (TXI §4 CHF-R1/R2): the LLM proposing happens inside run_causal_brainstorm.py. This
runner only orchestrates the two DETERMINISTIC ends —

    (1) emit the proposal PACK (scripts.propose_transmission_chains) to the CHF lane's drop
        location, so the CHF generator has a transmission-chain-shaped prompt; and
    (2) ingest the CHF lane's chain-shaped REPLIES (scripts.ingest_transmission_chains) into
        hypothesis-tier knowledge/transmission/proposed/ YAMLs.

THE GATE (does NOT flip on by building this — the lane sub-flag ships OFF):
    A scheduled run acts ONLY when BOTH are true (ANDed in _gate_state):
        config/causal_llm.yml         : auto_loop        (CHF's EXISTING operator gate; CHF-R8)
        config/transmission_proposals.yml : enabled      (this lane's OWN sub-flag; ships FALSE)
    HONEST STATE: CHF `auto_loop` DEFAULTS false per CHF-R8 but the operator already flipped it
    TRUE in this repo (ruling 2026-07-09). So `enabled` (default FALSE) is the SOLE remaining
    lock in the current repo — this is NOT two independent operator flips. It ships OFF so
    wiring the lane into weekly.yml can never auto-activate it; the operator flips `enabled`
    on in a one-line PR. When EITHER gate is off, the runner NO-OPS (prints the reason, writes
    nothing, exits 0). Inputs absent → also a no-op.

Proposals are DISPLAY-TIER and behind promotion: W1 auto-compiles their state + W3
auto-backtests them (the loader globs proposed/), but they stay `hypothesis` and never arm /
gain authority until a human PR promotes them out of proposed/ (TXI-R5).

No Date.now on chains: the pack meta carries proposed_at (from --asof); the ingest stamps it.

Usage (weekly.yml passes --trigger scheduled — this lane runs WEEKLY only, not nightly):
    python -m scripts.run_transmission_proposals --trigger scheduled [--asof YYYY-MM-DD]
    python -m scripts.run_transmission_proposals --status-only     # ad-hoc gate-state probe
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import ingest_transmission_chains as ingest_mod  # noqa: E402
from scripts import propose_transmission_chains as pack_mod  # noqa: E402

_CHF_CONFIG = ROOT / "config" / "causal_llm.yml"
_LANE_CONFIG = ROOT / "config" / "transmission_proposals.yml"
_RUN_LOG = ROOT / "data" / "transmission" / "proposal_runs.jsonl"


def _load_yaml(path: Path) -> dict:
    """Fail-open config load (mirrors run_causal_brainstorm._load_config)."""
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def _resolve_asof(cli_asof: str | None) -> str:
    """Data date for the pack metadata → the chains' proposed_at. Prefer the explicit arg,
    else the nightly transmission artifact's asof (a real data date, not a fresh clock)."""
    if cli_asof:
        return cli_asof
    latest = ROOT / "data" / "transmission" / "latest.json"
    if latest.exists():
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("asof"):
                return str(data["asof"])
        except (json.JSONDecodeError, OSError):
            pass
    # Last resort only (no data date available): today's date, logged by the caller.
    return datetime.now(timezone.utc).date().isoformat()


def _gate_state() -> tuple[bool, bool, str]:
    """Return (auto_loop, lane_enabled, reason_if_blocked)."""
    chf = _load_yaml(_CHF_CONFIG)
    lane = _load_yaml(_LANE_CONFIG)
    auto_loop = bool(chf.get("auto_loop", False))
    lane_enabled = bool(lane.get("enabled", False))
    if not auto_loop:
        return auto_loop, lane_enabled, "CHF auto_loop is OFF (config/causal_llm.yml) — proposal lane no-op"
    if not lane_enabled:
        return auto_loop, lane_enabled, "transmission_proposals.enabled is OFF (config/transmission_proposals.yml) — proposal lane no-op"
    return auto_loop, lane_enabled, ""


def _write_run_log(row: dict) -> None:
    _RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _RUN_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def run(trigger: str, *, asof: str | None = None, status_only: bool = False,
        write: bool = True) -> int:
    """Gate → (optionally) emit pack + ingest replies. Always returns 0 (non-fatal lane)."""
    lane = _load_yaml(_LANE_CONFIG)
    auto_loop, lane_enabled, blocked = _gate_state()

    if status_only:
        print(f"[run_transmission_proposals] status-only: auto_loop={auto_loop} "
              f"lane_enabled={lane_enabled} (no action)")
        return 0

    if blocked:
        print(f"[run_transmission_proposals] {blocked}")
        return 0

    # ---- gates open: emit the pack to the CHF lane's drop location ----
    n_requested = int(lane.get("n_requested", 12))
    asof = _resolve_asof(asof)
    generated_at = datetime.now(timezone.utc).isoformat()

    # The pack + meta go to a handoff dir (temp by default — the CHF lane, or an operator,
    # picks the pack up; this is NOT a committed data path). This mirrors how the CHF runner
    # writes its pack to tempfile.gettempdir().
    handoff = Path(tempfile.gettempdir()) / f"txi_proposal_pack_{asof}"
    handoff.mkdir(parents=True, exist_ok=True)
    pack_path = handoff / "pack.txt"
    meta_path = handoff / "pack.meta.json"
    pack_path.write_text(pack_mod.build_pack(n_requested=n_requested, asof=asof) + "\n",
                         encoding="utf-8")
    meta = pack_mod.build_meta(n_requested, asof, generated_at)
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"[run_transmission_proposals] pack → {pack_path} (asof={asof}, n={n_requested})")

    # ---- ingest the CHF lane's replies IF a reply inbox is configured + present ----
    reply_inbox = lane.get("reply_inbox")
    ingest_stats = None
    if reply_inbox:
        inbox = Path(reply_inbox)
        if not inbox.is_absolute():
            inbox = ROOT / inbox
        if inbox.exists():
            ingest_stats = ingest_mod.ingest(
                inbox,
                proposed_at=meta["proposed_at"],
                write=write,
                ingested_at=generated_at,
            )
            print(f"[run_transmission_proposals] ingest: parsed={ingest_stats['parsed']} "
                  f"accepted={ingest_stats['accepted']} rejected={ingest_stats['rejected']} "
                  f"(dup={ingest_stats['dup']}) dry_run={ingest_stats['dry_run']}")
        else:
            print(f"[run_transmission_proposals] reply_inbox {inbox} absent — pack emitted, "
                  "no replies to ingest (no-op ingest)")
    else:
        print("[run_transmission_proposals] no reply_inbox configured — pack emitted only "
              "(the CHF lane / operator ingests separately)")

    # ---- run log (only in write mode, and only when the lane actually acted) ----
    if write:
        _write_run_log({
            "schema": "txi.proposal_run.v1",
            "ts": generated_at,
            "trigger": trigger,
            "asof": asof,
            "pack_id": meta["pack_id"],
            "gate": {"auto_loop": auto_loop, "lane_enabled": lane_enabled},
            "ingest": (
                {k: ingest_stats[k] for k in ("parsed", "accepted", "rejected", "dup", "dry_run")}
                if ingest_stats else None
            ),
        })
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trigger", choices=["operator", "scheduled"], default="operator")
    ap.add_argument("--asof", type=str, default=None, metavar="YYYY-MM-DD",
                    help="Data date for the pack metadata → chains' proposed_at (no clock call).")
    ap.add_argument("--status-only", action="store_true", default=False,
                    help="Print gate state and exit (nightly non-Tuesday probe).")
    ap.add_argument("--dry-run", action="store_true", default=False,
                    help="Emit the pack but do not write ingested YAMLs / run log.")
    args = ap.parse_args(argv)
    return run(args.trigger, asof=args.asof, status_only=args.status_only,
               write=not args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
