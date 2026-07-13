"""scripts/run_signal_foundry_brainstorm.py — Signal Foundry LLM brainstorm runner.

Mirrors run_causal_brainstorm.py architecture exactly (provider waterfall,
run_status dict, never-raise contract, exit 0 always except unexpected crash).

SF-R5 gates (fail-closed):
  (i)  SIGNAL_FOUNDRY_PAUSED env must be the exact string 'false' (unset or
       anything else → paused; never raises, just degrades to pack-only).
  (ii) config auto_loop: true
  (iii) trigger == 'scheduled' → OAuth-ONLY provider (ANTHROPIC_API_KEY and
        deepseek are explicitly excluded from the scheduled path).

Without any gate: pack-only mode: always builds the brainstorm pack and writes it
to /tmp/signal_foundry_pack_<isoweek>.txt, then writes lane_status.json.

SF-R7 two-key: every compiled spec goes through engine.signal_foundry.screen.
screen_candidate; only admitted specs are appended to data/signal_foundry/candidates.jsonl
with status='proposed'; rejected specs are appended with status='screen_rejected'.

ISO-week idempotency (SF-R6): counts this week's filed rows; if >= filed_per_week, no-op.
Governance row goes to data/signal_foundry/governance.jsonl (SF-R10 write fence).

Usage:
    python -m scripts.run_signal_foundry_brainstorm [--root PATH] [--trigger operator|scheduled] [--dry-run]

Outputs (non-fatal on any individual failure):
  /tmp/signal_foundry_pack_<isoweek>.txt         — brainstorm pack (always rebuilt fresh)
  data/signal_foundry/candidates.jsonl           — specs filed (append)
  data/signal_foundry/lane_status.json           — lane status (write)
  data/signal_foundry/governance.jsonl           — governance events (append)
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Module-level imports so tests can patch them
from engine.signal_foundry.screen import screen_candidate  # noqa: E402
from engine.signal_foundry.spec import stamp_gates_hash  # noqa: E402

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_CONFIG_PATH = ROOT / "config" / "signal_foundry.yml"
_CANDIDATES_PATH = ROOT / "data" / "signal_foundry" / "candidates.jsonl"
_LANE_STATUS_PATH = ROOT / "data" / "signal_foundry" / "lane_status.json"
_GOVERNANCE_PATH = ROOT / "data" / "signal_foundry" / "governance.jsonl"


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load config/signal_foundry.yml; fail-open with defaults."""
    try:
        import yaml
        return yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # noqa: BLE001
        log.warning("run_signal_foundry_brainstorm: could not load signal_foundry.yml (%s); using defaults", exc)
        return {}


# ---------------------------------------------------------------------------
# ISO week helpers (idempotency — SF-R6)
# ---------------------------------------------------------------------------

def _current_iso_week() -> str:
    now = datetime.now(timezone.utc)
    year, week, _ = now.isocalendar()
    return f"{year}-W{week:02d}"


def _count_filed_this_week(candidates_path: Path, iso_week: str) -> int:
    """Count rows in candidates.jsonl that were filed this ISO week."""
    count = 0
    if not candidates_path.exists():
        return count
    try:
        with candidates_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if row.get("iso_week") == iso_week and row.get("status") in {
                        "proposed", "registered", "tested"
                    }:
                        count += 1
                except Exception:
                    continue
    except OSError:
        pass
    return count


# ---------------------------------------------------------------------------
# SF-R5 GATE 1: SIGNAL_FOUNDRY_PAUSED env check (fail-closed)
# ---------------------------------------------------------------------------

def _is_paused() -> bool:
    """Return True if the foundry is paused (fail-closed).

    The foundry runs ONLY when SIGNAL_FOUNDRY_PAUSED is exactly the string
    'false'. Any other value (including unset, 'true', '0', empty) → paused.
    This mirrors scripts/metabolism_guard.py is_paused() exactly.
    """
    val = os.environ.get("SIGNAL_FOUNDRY_PAUSED", "")
    return val.strip().lower() != "false"


# ---------------------------------------------------------------------------
# Lane status file
# ---------------------------------------------------------------------------

def _write_lane_status(
    status: str,
    reason: str,
    root: Path | None = None,
) -> None:
    """Write data/signal_foundry/lane_status.json.

    Statuses (mirror causal):
      full                — full LLM run completed
      degraded_pack_only  — no auth or gate closed; pack written, no LLM
      awaiting_arming     — paused (SIGNAL_FOUNDRY_PAUSED not 'false')
      paused              — auto_loop false with no operator trigger
    """
    base = root or ROOT
    lane_path = base / "data" / "signal_foundry" / "lane_status.json"
    try:
        lane_path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "status": status,
            "asof": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "reason": reason,
        }
        lane_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("run_signal_foundry_brainstorm: could not write lane status (%s)", exc)


# ---------------------------------------------------------------------------
# Provider builders (mirror run_causal_brainstorm.py exactly)
# ---------------------------------------------------------------------------

def _build_scheduled_providers(cfg: dict) -> list[dict]:
    """For scheduled trigger: ONLY the CLAUDE_CODE_OAUTH_TOKEN (oauth) provider.

    SF-R5 mirror of CHF-R8: ANTHROPIC_API_KEY and deepseek are explicitly
    excluded from the scheduled path.
    """
    from engine import llm_auth  # noqa: PLC0415

    model = cfg.get("models", {}).get("generator", "claude-sonnet-4-6")
    try:
        providers = llm_auth.build_providers(cfg, opus_model=model)
    except Exception as exc:  # noqa: BLE001
        log.warning("run_signal_foundry_brainstorm: provider build failed (%s)", exc)
        return []
    return [p for p in providers if p.get("name") == "oauth"]


def _build_operator_providers(cfg: dict, model_override: str | None = None) -> list[dict]:
    """For operator trigger: full waterfall (oauth → anthropic → deepseek)."""
    from engine import llm_auth  # noqa: PLC0415
    model = model_override or cfg.get("models", {}).get("generator", "claude-sonnet-4-6")
    return llm_auth.build_providers(cfg, opus_model=model)


def _build_providers_for_model(
    cfg: dict,
    trigger: str,
    model_role: str,
) -> list[dict]:
    """Build providers selecting the right model from models config section."""
    model = cfg.get("models", {}).get(model_role)
    if trigger == "scheduled":
        providers = _build_scheduled_providers(cfg)
        if providers and model:
            for p in providers:
                p["model"] = model
        return providers
    else:
        return _build_operator_providers(cfg, model_override=model)


# ---------------------------------------------------------------------------
# Numeric field rejection (RF-16 / SF-R12 — mirrors run_causal_brainstorm.py)
# ---------------------------------------------------------------------------

_NUMERIC_FIELD_NAMES = frozenset({
    "confidence", "confidence_score", "probability", "prob",
    "score", "weight", "numeric_confidence", "confidence_pct",
})


def _has_numeric_confidence(obj: Any, depth: int = 0) -> bool:
    """Return True if obj contains a numeric confidence-like field (RF-16)."""
    if depth > 8:
        return False
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in _NUMERIC_FIELD_NAMES and isinstance(v, (int, float)):
                return True
            if _has_numeric_confidence(v, depth + 1):
                return True
    elif isinstance(obj, list):
        for item in obj:
            if _has_numeric_confidence(item, depth + 1):
                return True
    return False


def _validate_skeptic_findings(findings: list[dict]) -> tuple[list[dict], list[str]]:
    """Validate skeptic output: reject any finding with numeric confidence (RF-16).

    Returns (valid_findings, rejection_reasons).
    """
    valid: list[dict] = []
    rejected: list[str] = []
    for i, f in enumerate(findings):
        if _has_numeric_confidence(f):
            spec_id = f.get("spec_id", f.get("id", f"finding[{i}]"))
            rejected.append(
                f"{spec_id}: contains numeric confidence field "
                "(RF-16/SF-R12 violation — skeptic must be categorical only)"
            )
        else:
            valid.append(f)
    return valid, rejected


# ---------------------------------------------------------------------------
# LLM call helper (mirrors run_causal_brainstorm.py)
# ---------------------------------------------------------------------------

def _llm_call(
    providers: list[dict],
    system: str,
    user: str,
    max_tokens: int,
    context: str,
) -> tuple[str | None, str | None, str | None, dict]:
    """Make one LLM call via the provider waterfall.

    Returns (text, degraded_reason, provider_used, token_counts_dict).
    """
    from engine import llm_auth  # noqa: PLC0415

    token_counts: dict = {}

    def _call_fn(client, model: str) -> tuple[str | None, str | None]:
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            # temperature removed — rejected (400) on opus-4.7+ per Anthropic API
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        )
        usage = getattr(resp, "usage", None)
        if usage is not None:
            token_counts["input_tokens"] = getattr(usage, "input_tokens", None)
            token_counts["output_tokens"] = getattr(usage, "output_tokens", None)
        return text, None

    text, reason, provider = llm_auth.make_call(providers, _call_fn, context=context)
    return text, reason, provider, token_counts


# ---------------------------------------------------------------------------
# JSON array parser (mirrors run_causal_brainstorm.py)
# ---------------------------------------------------------------------------

def _parse_json_array(text: str) -> list[dict]:
    """Parse LLM output that should be a JSON array. Tries multiple strategies."""
    import json as _json

    text = text.strip()

    # Direct parse
    try:
        obj = _json.loads(text)
        if isinstance(obj, list):
            return [c for c in obj if isinstance(c, dict)]
    except _json.JSONDecodeError:
        pass

    # Strip markdown code fences
    for fence in ("```json", "```"):
        if fence in text:
            start = text.find(fence) + len(fence)
            end = text.rfind("```")
            if end > start:
                inner = text[start:end].strip()
                try:
                    obj = _json.loads(inner)
                    if isinstance(obj, list):
                        return [c for c in obj if isinstance(c, dict)]
                except _json.JSONDecodeError:
                    pass

    # Find first '[' and last ']'
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            obj = _json.loads(text[start:end + 1])
            if isinstance(obj, list):
                return [c for c in obj if isinstance(c, dict)]
        except _json.JSONDecodeError:
            pass

    raise ValueError(f"could not parse JSON array from text of length {len(text)}")


# ---------------------------------------------------------------------------
# Data inventory helper (pack contents)
# ---------------------------------------------------------------------------

_INVENTORY_DIRS = [
    "data/fred",
    "data/cboe",
    "data/cot",
    "data/sentiment",
    "data/coinmetrics",
    "data/checkonchain",
    "data/yahoo",
]


def _build_data_inventory(root: Path) -> str:
    """Build a short inventory of tracked data stores for the brainstorm pack."""
    lines: list[str] = ["DATA INVENTORY (tracked stores):"]
    for rel_dir in _INVENTORY_DIRS:
        dir_path = root / rel_dir
        if not dir_path.exists():
            lines.append(f"  {rel_dir}: absent")
            continue
        files = sorted(dir_path.rglob("*.parquet")) + sorted(dir_path.rglob("*.csv"))
        if not files:
            lines.append(f"  {rel_dir}: empty")
            continue
        # Sample first few files + count
        sample = [str(f.relative_to(root)) for f in files[:5]]
        more = len(files) - 5
        summary = ", ".join(sample)
        if more > 0:
            summary += f" ... (+{more} more)"
        lines.append(f"  {rel_dir}: {len(files)} file(s) — {summary}")
    return "\n".join(lines)


def _build_existing_registry_summary(root: Path) -> str:
    """List existing REGISTRY row names + existing SF candidate ids."""
    lines: list[str] = ["EXISTING REGISTRY (do not duplicate):"]

    # Signal lab registry
    try:
        import importlib.util
        sl_path = root / "engine" / "signal_lab.py"
        if sl_path.exists():
            spec_obj = importlib.util.spec_from_file_location("_sl_tmp", sl_path)
            if spec_obj is not None:
                mod = importlib.util.module_from_spec(spec_obj)
                spec_obj.loader.exec_module(mod)  # type: ignore[union-attr]
                registry = getattr(mod, "REGISTRY", [])
                for row in registry:
                    n = row.get("name", "")
                    tier = row.get("tier", "")
                    if n:
                        lines.append(f"  REGISTRY: {n} (tier={tier})")
    except Exception:
        lines.append("  REGISTRY: (could not load)")

    # Existing SF candidates
    cands_path = root / "data" / "signal_foundry" / "candidates.jsonl"
    if cands_path.exists():
        try:
            with cands_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        sid = row.get("id") or row.get("spec_id") or ""
                        name = row.get("name", "")
                        status = row.get("status", "")
                        if sid or name:
                            lines.append(f"  SF: {sid} {name} (status={status})")
                    except Exception:
                        continue
        except OSError:
            pass

    return "\n".join(lines)


def _build_blocklist_summary(root: Path) -> str:
    """Summarize blocklist themes from config/signal_foundry_blocklist.yml."""
    lines: list[str] = ["BLOCKLIST THEMES (forbidden — never propose these):"]
    bl_path = root / "config" / "signal_foundry_blocklist.yml"
    if not bl_path.exists():
        lines.append("  (blocklist absent)")
        return "\n".join(lines)
    try:
        import yaml
        with bl_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        for entry in data.get("entries", []):
            reason = entry.get("reason", "")
            source = entry.get("source", "")
            patterns = entry.get("match", {}).get("any_of", [])
            lines.append(f"  [{source}] {reason} (patterns: {patterns[:3]})")
    except Exception as exc:
        lines.append(f"  (could not load blocklist: {exc})")
    return "\n".join(lines)


def _spec_schema_hint() -> str:
    """Return the spec JSON schema + whitelisted transforms for the pack."""
    return """\
SPEC JSON SCHEMA (compiler must emit this structure):
{
  "id": "SF-NNNN",
  "name": "short english name",
  "name_zh": "chinese name",
  "market": "US macro",
  "thesis": "one sentence causal thesis",
  "mechanism": "mechanism description",
  "seed_provenance": {"source": "<source file>", "ref": "<edge id or name>"},
  "data": [{"path": "data/<store>/<file>.parquet", "column": "<col>", "pit": "proxy|lagged|release_lag|clean"}],
  "feature": {"pipeline": [["<transform>", {"<param>": <value>}], ...]},
  "target": {"path": "data/yahoo/SPY.parquet", "kind": "excess_return|absolute_return|drawdown_onset|forward_vol", "horizon_d": 5|10|21|63|126},
  "universe": "single_series",
  "baseline": "buy_and_hold|sma_200|flat",
  "gates": {"min_t_hac": 2.0, "fdr_q": 0.10, "dsr": 0.90},
  "horizon_role": "swing",
  "orthogonality_note": "what makes this distinct from existing signals",
  "evidence_note": "literature or empirical basis"
}

WHITELISTED TRANSFORM VOCABULARY (only these are allowed in feature.pipeline):
zscore, pctile_rank, diff, pct_change, sma, ema, ratio, spread, lag, sign, clip,
rolling_corr, rolling_vol, drawdown

FORBIDDEN in output:
- No numeric confidence scores (e.g., confidence: 0.8 is FORBIDDEN — RF-16/SF-R12)
- No "validated" claims
- No paths to gitignored/untracked stores (only tracked data/* files)
- No changes to engine/, config/, or any harness code
"""


# ---------------------------------------------------------------------------
# Pack builder
# ---------------------------------------------------------------------------

def _build_sf_pack(root: Path, n_candidates: int = 5) -> str:
    """Build a fresh Signal Foundry brainstorm pack.

    Always rebuilt fresh (never reuse a persisted pack).
    """
    from engine.signal_foundry.seeds import harvest_seeds  # noqa: PLC0415

    seeds = harvest_seeds(root)
    seed_lines = []
    for s in seeds[:40]:  # cap at 40 seeds in pack
        kind = s.get("kind", "unknown")
        ref = s.get("ref", "")
        summary = s.get("summary", "")
        data_hint = s.get("data_hint", "")
        seed_lines.append(f"  [{kind}] {ref}: {summary}" + (f" (data: {data_hint})" if data_hint else ""))

    inventory = _build_data_inventory(root)
    registry_summary = _build_existing_registry_summary(root)
    blocklist_summary = _build_blocklist_summary(root)
    schema_hint = _spec_schema_hint()

    pack = f"""\
=== SIGNAL FOUNDRY BRAINSTORM PACK ===
ISO Date: {datetime.now(timezone.utc).date().isoformat()}

MISSION: Propose {n_candidates} novel Signal Foundry candidate specs.
Each spec must:
  1. Propose a construct that could predict forward returns (or vol, drawdown onset).
  2. Use ONLY tracked data paths listed in the DATA INVENTORY.
  3. Use ONLY the whitelisted transform vocabulary in feature.pipeline.
  4. NOT duplicate any entry in the EXISTING REGISTRY or prior SF specs.
  5. NOT match any BLOCKLIST theme.
  6. Include orthogonality_note (what makes it distinct) and evidence_note (basis).
  7. Include a PIT plan per data[] entry (proxy, lagged, release_lag, or clean).
  8. MUST NOT contain numeric confidence scores (RF-16/SF-R12 — categorical outputs only).

{schema_hint}

=== SEEDS (brainstorm from these — mechanism edges, frontier candidates, killed constructions) ===
{chr(10).join(seed_lines) if seed_lines else '  (no seeds available)'}

=== {inventory} ===

=== {registry_summary} ===

=== {blocklist_summary} ===

INSTRUCTIONS:
  - Generator: produce exactly {n_candidates} candidate pre-spec dicts as a JSON array.
    Each should have: name, thesis, mechanism, seed_provenance, data (with path, column, pit),
    feature.pipeline, target, universe, baseline, gates, orthogonality_note, evidence_note.
  - Skeptic: for each candidate emit ADVISORY_DROP or ADVISORY_KEEP with categorical blockers[].
    ABSOLUTELY NO numeric confidence fields. recommendation must be exactly 'ADVISORY_DROP' or 'ADVISORY_KEEP'.
  - Compiler: for surviving candidates, emit strict spec JSON matching the schema above exactly.
    Assign sequential ids starting from the next available SF-NNNN (check existing SF specs).
    Add registered_at: "{datetime.now(timezone.utc).date().isoformat()}".
"""
    return pack


# ---------------------------------------------------------------------------
# Pack-only mode
# ---------------------------------------------------------------------------

def _run_pack_only_mode(
    cfg: dict,
    reason: str,
    iso_week: str,
    root: Path,
    lane_status: str = "degraded_pack_only",
) -> int:
    """Build fresh pack, write to /tmp, update lane status. Always returns 0."""
    print(f"[run_signal_foundry_brainstorm] {reason}")
    print("[run_signal_foundry_brainstorm] Entering pack-only mode.")

    n_cands = int((cfg.get("budgets") or {}).get("filed_per_week", 5))
    try:
        pack_text = _build_sf_pack(root, n_candidates=n_cands)
        pack_path = Path(tempfile.gettempdir()) / f"signal_foundry_pack_{iso_week}.txt"
        pack_path.write_text(pack_text, encoding="utf-8")
        print(f"[run_signal_foundry_brainstorm] Pack written to: {pack_path}")
    except Exception as exc:  # noqa: BLE001
        print(f"[run_signal_foundry_brainstorm] WARNING: pack build failed ({exc}); continuing")

    _write_lane_status(lane_status, reason, root=root)
    return 0


# ---------------------------------------------------------------------------
# Candidate filing (SF-R7 two-key screen + append to candidates.jsonl)
# ---------------------------------------------------------------------------

def _next_sf_id(candidates_path: Path) -> str:
    """Determine the next SF-NNNN id by scanning existing candidates."""
    max_n = 0
    if candidates_path.exists():
        try:
            with candidates_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        sid = str(row.get("id") or row.get("spec_id") or "")
                        if sid.startswith("SF-") and sid[3:].isdigit():
                            n = int(sid[3:])
                            if n > max_n:
                                max_n = n
                    except Exception:
                        continue
        except OSError:
            pass
    return f"SF-{max_n + 1:04d}"


def _file_specs(
    specs: list[dict],
    candidates_path: Path,
    root: Path,
    iso_week: str,
    dry_run: bool,
) -> tuple[int, int]:
    """Apply two-key screen (SF-R7) and file admitted specs.

    Returns (n_admitted, n_rejected).
    """
    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    n_admitted = 0
    n_rejected = 0
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # Determine starting id from existing candidates
    next_id_n = 0
    if candidates_path.exists():
        try:
            with candidates_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        sid = str(row.get("id") or row.get("spec_id") or "")
                        if sid.startswith("SF-") and sid[3:].isdigit():
                            n = int(sid[3:])
                            if n > next_id_n:
                                next_id_n = n
                    except Exception:
                        continue
        except OSError:
            pass

    for spec in specs:
        # Assign id if missing or placeholder
        sid = str(spec.get("id") or "")
        if not sid or not sid.startswith("SF-") or not sid[3:].isdigit():
            next_id_n += 1
            sid = f"SF-{next_id_n:04d}"
            spec = dict(spec, id=sid)

        # Ensure registered_at is set
        if not spec.get("registered_at"):
            spec = dict(spec, registered_at=datetime.now(timezone.utc).date().isoformat())

        # SF-R7 two-key: deterministic screen must independently admit
        screen_result = screen_candidate(spec, repo_root=root)
        if screen_result.get("admit"):
            # Stamp gates hash (SF-R4 gate-freeze)
            spec_stamped = stamp_gates_hash(spec)
            row: dict = {
                **spec_stamped,
                "status": "proposed",
                "proposed_at": ts,
                "iso_week": iso_week,
                "screen_result": {
                    "verdict": screen_result.get("verdict"),
                    "gates_passed": screen_result.get("gates_passed", []),
                    "gates_failed": screen_result.get("gates_failed", []),
                },
            }
            print(f"[run_signal_foundry_brainstorm] ADMITTED: {sid} '{spec.get('name', '')}'")
            if not dry_run:
                with candidates_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
            n_admitted += 1
        else:
            # Filed as screen_rejected (honest funnel — SF-R7)
            row = {
                "id": sid,
                "name": spec.get("name", ""),
                "status": "screen_rejected",
                "proposed_at": ts,
                "iso_week": iso_week,
                "screen_result": {
                    "verdict": screen_result.get("verdict"),
                    "reasons": screen_result.get("reasons", []),
                    "gates_passed": screen_result.get("gates_passed", []),
                    "gates_failed": screen_result.get("gates_failed", []),
                },
            }
            print(f"[run_signal_foundry_brainstorm] SCREEN_REJECTED: {sid} "
                  f"'{spec.get('name', '')}' reasons={screen_result.get('reasons', [])}")
            if not dry_run:
                with candidates_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
            n_rejected += 1

    return n_admitted, n_rejected


# ---------------------------------------------------------------------------
# Governance event writer (data/signal_foundry/governance.jsonl — SF-R10)
# ---------------------------------------------------------------------------

def _append_governance_event(
    event_type: str,
    evidence: dict,
    root: Path,
) -> None:
    """Append a governance event to data/signal_foundry/governance.jsonl.

    NEVER writes to data/neuralweb/governance.jsonl (SF-R10 write fence).
    """
    gov_path = root / "data" / "signal_foundry" / "governance.jsonl"
    try:
        gov_path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "event": event_type,
            "authored_by": "run_signal_foundry_brainstorm",
            "evidence": evidence,
        }
        with gov_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001
        print(f"[run_signal_foundry_brainstorm] WARNING: governance event write failed ({exc}); non-fatal")


# ---------------------------------------------------------------------------
# Run log writer
# ---------------------------------------------------------------------------

def _write_run_log(
    run_status: dict,
    root: Path,
    pack_id: str | None = None,
    raw_replies: dict | None = None,
) -> None:
    """Append one row to data/signal_foundry/governance.jsonl (run log)."""
    _append_governance_event(
        "sf_brainstorm_run",
        {
            "pack_id": pack_id,
            "run_status": run_status,
            "raw_replies_truncated": {
                k: (v[:1000] + "... [truncated]" if v and len(v) > 1000 else v)
                for k, v in (raw_replies or {}).items()
            },
        },
        root=root,
    )


# ---------------------------------------------------------------------------
# Full mode: generator → skeptic → compiler → two-key screen → file
# ---------------------------------------------------------------------------

def _run_full_mode(
    cfg: dict,
    trigger: str,
    iso_week: str,
    dry_run: bool,
    root: Path,
) -> int:
    """Run the full LLM chain: generator → skeptic → compiler → screen → file.

    Returns 0 always (non-fatal pattern).
    """
    run_status: dict[str, Any] = {
        "trigger": trigger,
        "iso_week": iso_week,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "full",
        "dry_run": dry_run,
        "stages": {},
    }

    budgets = cfg.get("budgets") or {}
    n_candidates = int(budgets.get("filed_per_week", 5))
    models_cfg = cfg.get("models") or {}
    generator_model = models_cfg.get("generator", "claude-sonnet-4-6")
    skeptic_model = models_cfg.get("skeptic", "claude-opus-4-8")
    compiler_model = models_cfg.get("compiler", "claude-haiku-4-5-20251001")

    # ---- Step 1: Build fresh pack ----
    print("[run_signal_foundry_brainstorm] Building fresh brainstorm pack...")
    try:
        pack_text = _build_sf_pack(root, n_candidates=n_candidates)
        pack_path = Path(tempfile.gettempdir()) / f"signal_foundry_pack_{iso_week}.txt"
        pack_path.write_text(pack_text, encoding="utf-8")
        print(f"[run_signal_foundry_brainstorm] Pack written to: {pack_path}")
        run_status["stages"]["pack"] = "ok"
    except Exception as exc:  # noqa: BLE001
        print(f"[run_signal_foundry_brainstorm] ERROR: pack build failed ({exc}); aborting full mode")
        run_status["stages"]["pack"] = f"error: {exc}"
        _write_run_log(run_status, root=root)
        _write_lane_status("degraded_pack_only", f"pack build failed: {exc}", root=root)
        return 0

    # ---- Step 2: GENERATOR — pack → JSON array of candidate pre-specs ----
    print(f"[run_signal_foundry_brainstorm] Stage: GENERATOR (model={generator_model})")
    gen_providers = _build_providers_for_model(cfg, trigger, "generator")
    gen_system = (
        "You are the Signal Foundry brainstorm generator. Read the BRAINSTORM PACK carefully. "
        "Produce EXACTLY the requested number of candidate signal specs as a JSON array. "
        "Obey all forbidden-output constraints in the pack. "
        "CRITICAL: do NOT include any numeric confidence score fields. "
        "Return JSON array ONLY — no prose, no markdown fences."
    )

    gen_text, gen_reason, gen_provider, gen_tokens = _llm_call(
        gen_providers, gen_system, pack_text,
        max_tokens=6000, context="sf_generator",
    )

    run_status["stages"]["generator"] = {
        "model": generator_model,
        "provider": gen_provider,
        "degraded_reason": gen_reason,
        "token_counts": gen_tokens,
    }

    if gen_text is None:
        print(f"[run_signal_foundry_brainstorm] WARNING: generator failed (reason={gen_reason}); falling to pack-only")
        _write_run_log(run_status, root=root)
        _write_lane_status("degraded_pack_only", f"generator failed: {gen_reason}", root=root)
        return 0

    # Parse generator output
    try:
        candidate_specs = _parse_json_array(gen_text)
    except Exception as exc:  # noqa: BLE001
        print(f"[run_signal_foundry_brainstorm] WARNING: could not parse generator output ({exc}); falling to pack-only")
        run_status["stages"]["generator"]["parse_error"] = str(exc)
        _write_run_log(run_status, root=root)
        _write_lane_status("degraded_pack_only", f"generator parse error: {exc}", root=root)
        return 0

    print(f"[run_signal_foundry_brainstorm] Generator produced {len(candidate_specs)} spec(s)")
    run_status["stages"]["generator"]["n_specs_raw"] = len(candidate_specs)

    # ---- Step 3: SKEPTIC — specs → per-spec ADVISORY findings (categorical only) ----
    print(f"[run_signal_foundry_brainstorm] Stage: SKEPTIC (model={skeptic_model})")
    skeptic_providers = _build_providers_for_model(cfg, trigger, "skeptic")

    skeptic_system = (
        "You are the Signal Foundry adversarial skeptic. Review proposed signal specs for "
        "identification failures, look-ahead bias, data confounds, reverse causation, "
        "and PIT gaps.\n\n"
        "RULES:\n"
        "- Produce ONLY categorical findings per spec: NO numeric confidence scores, "
        "probabilities, weights, or any numeric field that represents confidence.\n"
        "- recommendation MUST be exactly one of: ADVISORY_DROP or ADVISORY_KEEP.\n"
        "- blockers[] must be a list of strings describing specific methodological problems.\n"
        "- Return a JSON array where each element has: "
        "{spec_id: str, recommendation: 'ADVISORY_DROP'|'ADVISORY_KEEP', blockers: [str]}.\n"
        "- ADVISORY_DROP if: circular definition, known look-ahead, insufficient PIT plan, "
        "trivial reverse causation, or no plausible mechanism.\n"
        "- This is ADVISORY-ONLY — your output never directly transitions a spec's status."
    )
    skeptic_user = (
        f"Review these {len(candidate_specs)} candidate signal specs. Return JSON array only.\n\n"
        f"SPECS:\n{json.dumps(candidate_specs, indent=2, ensure_ascii=False)}"
    )

    skep_text, skep_reason, skep_provider, skep_tokens = _llm_call(
        skeptic_providers, skeptic_system, skeptic_user,
        max_tokens=3000, context="sf_skeptic",
    )

    run_status["stages"]["skeptic"] = {
        "model": skeptic_model,
        "provider": skep_provider,
        "degraded_reason": skep_reason,
        "token_counts": skep_tokens,
    }

    # Mechanically apply skeptic findings
    surviving_specs = candidate_specs
    if skep_text is not None:
        try:
            findings_raw = _parse_json_array(skep_text)
            # RF-16/SF-R12: reject numeric confidence fields
            valid_findings, rf16_rejections = _validate_skeptic_findings(findings_raw)
            if rf16_rejections:
                print(f"[run_signal_foundry_brainstorm] WARNING: skeptic RF-16 violations: {rf16_rejections}")
                run_status["stages"]["skeptic"]["rf16_rejections"] = rf16_rejections

            drop_ids: set[str] = set()
            for f in valid_findings:
                if f.get("recommendation") == "ADVISORY_DROP":
                    sid = str(f.get("spec_id", f.get("id", "")))
                    if sid:
                        drop_ids.add(sid)
                        blockers = f.get("blockers", [])
                        print(f"[run_signal_foundry_brainstorm] ADVISORY_DROP: spec_id={sid!r} blockers={blockers}")

            surviving_specs = [
                s for s in candidate_specs
                if str(s.get("id", s.get("name", ""))) not in drop_ids
            ]
            n_dropped = len(candidate_specs) - len(surviving_specs)
            print(f"[run_signal_foundry_brainstorm] Skeptic: {n_dropped} spec(s) dropped, "
                  f"{len(surviving_specs)} surviving")
            run_status["stages"]["skeptic"]["n_dropped"] = n_dropped
            run_status["stages"]["skeptic"]["n_surviving"] = len(surviving_specs)
        except Exception as exc:  # noqa: BLE001
            print(f"[run_signal_foundry_brainstorm] WARNING: skeptic parse failed ({exc}); proceeding with all specs")
            run_status["stages"]["skeptic"]["parse_error"] = str(exc)
    else:
        print(f"[run_signal_foundry_brainstorm] WARNING: skeptic unavailable (reason={skep_reason}); all specs survive")

    if not surviving_specs:
        print("[run_signal_foundry_brainstorm] All specs dropped by skeptic; nothing to file")
        _write_run_log(run_status, root=root)
        _write_lane_status("full", "all specs dropped by skeptic; no filing this week", root=root)
        return 0

    # ---- Step 4: COMPILER — surviving specs → strict schema JSON ----
    print(f"[run_signal_foundry_brainstorm] Stage: COMPILER (model={compiler_model})")
    compiler_providers = _build_providers_for_model(cfg, trigger, "compiler")

    compiler_system = (
        "You are the Signal Foundry schema compiler. Convert the given candidate signal specs "
        "to strictly conform to the Signal Foundry spec schema. "
        "Fix any missing required fields by inference from context. "
        "Assign sequential ids starting from the id specified in the pack (SF-NNNN format). "
        "Do NOT change the mechanism, data paths, feature pipeline, or target. "
        "Return a JSON array only — no prose, no markdown fences. "
        "CRITICAL: do NOT include any numeric confidence score fields in the output."
    )
    compiler_user = (
        f"Compile these {len(surviving_specs)} surviving specs to strict SF schema. "
        f"Return JSON array only.\n\n"
        f"SPECS:\n{json.dumps(surviving_specs, indent=2, ensure_ascii=False)}"
    )

    comp_text, comp_reason, comp_provider, comp_tokens = _llm_call(
        compiler_providers, compiler_system, compiler_user,
        max_tokens=5000, context="sf_compiler",
    )

    run_status["stages"]["compiler"] = {
        "model": compiler_model,
        "provider": comp_provider,
        "degraded_reason": comp_reason,
        "token_counts": comp_tokens,
    }

    final_specs = surviving_specs  # default: use pre-compiler specs
    if comp_text is not None:
        try:
            compiled = _parse_json_array(comp_text)
            if compiled and len(compiled) >= len(surviving_specs) * 0.5:
                final_specs = compiled
                run_status["stages"]["compiler"]["n_compiled"] = len(compiled)
                print(f"[run_signal_foundry_brainstorm] Compiler produced {len(compiled)} compiled spec(s)")
            else:
                print("[run_signal_foundry_brainstorm] WARNING: compiler output too short; using pre-compiler specs")
        except Exception as exc:  # noqa: BLE001
            print(f"[run_signal_foundry_brainstorm] WARNING: compiler parse failed ({exc}); using pre-compiler specs")
            run_status["stages"]["compiler"]["parse_error"] = str(exc)
    else:
        print(f"[run_signal_foundry_brainstorm] NOTE: compiler unavailable (reason={comp_reason}); using pre-compiler specs")

    # ---- Step 5: Two-key screen + file (SF-R7) ----
    candidates_path = root / "data" / "signal_foundry" / "candidates.jsonl"
    # SF-R6 HARD cap: a single run may not file past the weekly budget, even
    # when the LLM chain returns more admitted specs than the remaining
    # allowance (the pre-run GATE 3 only blocks the NEXT run).
    filed_per_week = int((cfg.get("budgets") or {}).get("filed_per_week", 5))
    already_filed = 0 if dry_run else _count_filed_this_week(candidates_path, iso_week)
    remaining = max(0, filed_per_week - already_filed)
    if len(final_specs) > remaining:
        print(f"[run_signal_foundry_brainstorm] SF-R6 hard cap: truncating "
              f"{len(final_specs)} specs to remaining weekly budget {remaining} "
              f"({already_filed}/{filed_per_week} already filed, {iso_week})")
        final_specs = final_specs[:remaining]
    n_admitted, n_rejected = _file_specs(
        final_specs,
        candidates_path=candidates_path,
        root=root,
        iso_week=iso_week,
        dry_run=dry_run,
    )
    run_status["stages"]["screen"] = {
        "n_admitted": n_admitted,
        "n_screen_rejected": n_rejected,
    }
    print(f"[run_signal_foundry_brainstorm] Screen: {n_admitted} admitted, {n_rejected} screen_rejected")

    # ---- Step 6: Write raw LLM replies to run log (governance.jsonl) ----
    pack_id = f"sf-{iso_week}-{trigger}"
    _write_run_log(
        run_status,
        root=root,
        pack_id=pack_id,
        raw_replies={
            "generator": gen_text,
            "skeptic": skep_text,
            "compiler": comp_text,
        },
    )

    # ---- Step 7: Governance event ----
    _append_governance_event(
        "sf_llm_proposed",
        {
            "pack_id": pack_id,
            "iso_week": iso_week,
            "trigger": trigger,
            "n_admitted": n_admitted,
            "n_screen_rejected": n_rejected,
            "models": {
                "generator": generator_model,
                "skeptic": skeptic_model,
                "compiler": compiler_model,
            },
            "dry_run": dry_run,
        },
        root=root,
    )
    print(f"[run_signal_foundry_brainstorm] Governance event appended (sf_llm_proposed, n_admitted={n_admitted})")

    _write_lane_status(
        "full",
        f"full run completed; {n_admitted} admitted, {n_rejected} screen_rejected",
        root=root,
    )
    return 0


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Main entrypoint. Always returns 0 except unexpected crash."""
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=None,
                    help="Repo root (default: inferred from script location)")
    ap.add_argument("--trigger", choices=["operator", "scheduled"], default="operator",
                    help="Trigger mode (default: operator)")
    ap.add_argument("--dry-run", action="store_true", default=False,
                    help="Dry-run: build pack + run LLM chain but do not write specs to disk")
    args = ap.parse_args(argv)

    root = Path(args.root) if args.root else ROOT
    trigger = args.trigger
    dry_run = args.dry_run
    iso_week = _current_iso_week()

    print(f"[run_signal_foundry_brainstorm] trigger={trigger}, iso_week={iso_week}, dry_run={dry_run}")

    # Load config
    cfg = _load_config()

    # ---- GATE 1: SIGNAL_FOUNDRY_PAUSED fail-closed (SF-R5) ----
    if trigger == "scheduled" and _is_paused():
        return _run_pack_only_mode(
            cfg,
            reason="SIGNAL_FOUNDRY_PAUSED is not 'false' — paused (SF-R5 fail-closed)",
            iso_week=iso_week,
            root=root,
            lane_status="awaiting_arming",
        )

    # ---- GATE 2: auto_loop check (SF-R5) ----
    if trigger == "scheduled":
        auto_loop = cfg.get("auto_loop", False)
        if not auto_loop:
            return _run_pack_only_mode(
                cfg,
                reason="auto_loop disabled in config/signal_foundry.yml — paused (SF-R5)",
                iso_week=iso_week,
                root=root,
                lane_status="paused",
            )

    # ---- GATE 3: ISO-week idempotency (SF-R6) ----
    filed_per_week = int((cfg.get("budgets") or {}).get("filed_per_week", 5))
    candidates_path = root / "data" / "signal_foundry" / "candidates.jsonl"
    if not dry_run:
        already_filed = _count_filed_this_week(candidates_path, iso_week)
        if already_filed >= filed_per_week:
            print(f"[run_signal_foundry_brainstorm] ISO-week lock: already filed "
                  f"{already_filed}/{filed_per_week} this week ({iso_week}); skip, exit 0")
            _write_lane_status(
                "full",
                f"already filed {already_filed}/{filed_per_week} this week ({iso_week}); idempotent skip",
                root=root,
            )
            return 0

    # ---- GATE 4: Auth availability check ----
    if trigger == "scheduled":
        # SF-R5: OAuth-ONLY on scheduled path (ANTHROPIC_API_KEY excluded)
        providers = _build_scheduled_providers(cfg)
        if not providers:
            return _run_pack_only_mode(
                cfg,
                reason="scheduled trigger requires CLAUDE_CODE_OAUTH_TOKEN (oauth) — not available; pack-only (SF-R5)",
                iso_week=iso_week,
                root=root,
                lane_status="degraded_pack_only",
            )
    else:
        # Operator can use any provider (full waterfall)
        providers = _build_operator_providers(cfg)
        if not providers:
            return _run_pack_only_mode(
                cfg,
                reason="no LLM auth available (operator trigger); pack-only mode",
                iso_week=iso_week,
                root=root,
                lane_status="degraded_pack_only",
            )

    # ---- FULL MODE ----
    print("[run_signal_foundry_brainstorm] Auth available; running full LLM chain")
    return _run_full_mode(
        cfg=cfg,
        trigger=trigger,
        iso_week=iso_week,
        dry_run=dry_run,
        root=root,
    )


if __name__ == "__main__":
    sys.exit(main())
