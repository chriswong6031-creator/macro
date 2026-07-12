"""engine.neuralweb.cortex — The Cortex Runtime (Neural Web W7b PR1).

SHADOW PROBATION — READ CAREFULLY
----------------------------------
The cortex is on shadow probation.  It may OBSERVE and EXPLAIN unconditionally
(A0/A1).  It may NOT influence any ranked or scored surface (A2 refused today
by constitution.grant_authority — no track record yet).  Its outputs carry
is_context_only=True everywhere.  Nothing it writes may rank or gate any
money-path surface.

ARTICLE 1 — ORIGINATION BAN (enforced here)
The cortex may NEVER originate a signal, trade, or escalation.  The tool
dispatcher (dispatch_tool) refuses any write tool outside the three shadow
surfaces below.  No dynamic tools — the whitelist is hard-coded and A7 is
permanently refused.

ARCHITECTURE
------------
A plain anthropic tool-use loop — NO claude_agent_sdk dependency.
  * client.messages.create(tools=[...]) iterated until stop_reason==end_turn
    or budget exhausted.
  * READ tools: read_world_state, query_spine, read_kernel, read_graph,
    read_contradictions, read_governance, read_artifact
  * WRITE tools (shadow-tier only, three):
      flag_attention   → data/reflexes/cortex_attention/firings.jsonl
      write_memo       → data/neuralweb/cortex/memo.json + site/neuralweb/cortex_memo.json
      stake_hypothesis → machine_registry.jsonl via metabolism (PR2 — live)
  * Dispatcher refuses any tool name outside this exact whitelist (A7 guard).

STALENESS GATE (cost control)
Before any LLM call: compare (world_state inputs_hash + spine row count +
contradictions hash) against data/neuralweb/cortex/last_run_state.json.
Unchanged → skip with a log line.  Content-hash reply caching is NOT enough
for a tool loop; this gate is the spend control.

CONSTITUTION WIRING
At startup: call constitution.grant_authority for the 'cortex_attention'
family A2 claim.  Today it refuses (no track record) → the memo carries
probation status honestly.  The loop runs regardless at A0/A1.

BUDGETS
max_tool_calls (default 24).  On budget hit → force write_memo from what has
accumulated.

SINGLE-CALL FALLBACK
If the tool loop errors (auth/API), fall back to ONE plain completion over
gather_state() + world_state summary producing just the memo
(degraded_reason stamped).  Degrade-never-raise; exit 0 always.

MODEL (D8 ruling)
Primary: claude-opus-4-8 (Opus-class), via engine.llm_auth.make_call
waterfall (CLAUDE_CODE_OAUTH_TOKEN → ANTHROPIC_API_KEY).
DeepSeek NOT in the deliberation path.  zh translation of the memo: PR2
(will reuse master_brain's _translate pattern; DeepSeek permitted there ONLY).

DENY ROOTS (bot_mcp pattern)
READ_ROOTS = [data/, site/, docs/, research/]
DENY_ROOTS = [config.yml, .env, .git]  (config.yml denied in full)
Size cap per read_artifact: 50 KB.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / config keys
# ---------------------------------------------------------------------------
_SCHEMA_MEMO = "neuralweb.cortex_memo.v1"
_SCHEMA_ATTN = "reflex.cortex_attention"
_SCHEMA_HYPO = "neuralweb.hypothesis_inbox.v1"
_DEFAULT_MODEL = "claude-opus-4-8"
_DEFAULT_FALLBACK_MODEL = "claude-sonnet-4-6"  # used when primary exhausts rate-limit retries
_DEFAULT_MAX_TOOL_CALLS = 24
_READ_SIZE_CAP = 50 * 1024          # 50 KB per read_artifact
_SPINE_ROW_CAP = 200                 # max rows serialized from query_spine
# Rate-limit retry config: up to 4 attempts; backoff 15s → 60s → 180s
_RATE_LIMIT_MAX_ATTEMPTS = 4
_RATE_LIMIT_BACKOFF_SECS = [15, 60, 180]   # delay after attempt 1, 2, 3
_RATE_LIMIT_MAX_TOTAL_SLEEP = 300           # cap total sleep so job stays inside timeout
# Dedicated cortex API key env var (preferred) with fallback to shared key
_CORTEX_API_KEY_ENV = "CORTEX_ANTHROPIC_API_KEY"
_FALLBACK_API_KEY_ENV = "ANTHROPIC_API_KEY"
_DENY_FILENAME_EXACT = {".env", "config.yml"}   # deny entire file (not path-prefix)
_DENY_PATH_FRAGMENTS = [".git", ".ssh"]          # deny if any component matches

# Tool whitelist — A7 guard: dispatcher refuses any name outside this set
_READ_TOOLS = frozenset({
    "read_world_state",
    "query_spine",
    "read_kernel",
    "read_graph",
    "read_contradictions",
    "read_governance",
    "read_artifact",
    # Options→NW W-B (RO-7): read-only options entry state tools
    "read_options_entry_state",
    "explain_options_context",
    "query_options_confluence",
    "list_options_contradictions",
    # Factor Intelligence × Neural Web W2 (RUL-NW3): read-only factor state tools
    "read_factor_state",
    "list_factor_contradictions",
    "explain_factor_context",
    # CPI P6 wave 1: read-only cycle-pattern turn-hazard state tool
    "read_cycle_pattern_state",
    # W3 MPC consumer: read-only mechanism pathway artifact
    "read_mechanism_pathways",
    # W4 context scanner: read-only context candidates + risk lens
    "read_context_candidates",
    # TIL W5 NW citizenship: thematic state read tools (display/context only)
    "read_theme_state",
    "read_theme_thesis",
    "read_theme_pathways",
    # Cortex-schema parity fix (2026-07-09): these two rode in _ASK_READ_TOOLS
    # without cortex schemas (pre-existing red on test_ask_whitelist_schema_consistency)
    "read_liquidity_plumbing",
    "read_china_decision_packet",
    # CHF W5: read-only causal mechanism cards + screened edges + null count
    "read_causal_candidates",
})
_WRITE_TOOLS = frozenset({
    "flag_attention",
    "write_memo",
    "stake_hypothesis",
})
_ALLOWED_TOOLS = _READ_TOOLS | _WRITE_TOOLS


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _repo_root(root: Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _data(root: Path, *parts: str) -> Path:
    return root / "data" / Path(*parts)


def _site(root: Path, *parts: str) -> Path:
    return root / "site" / Path(*parts)


def _cortex_dir(root: Path) -> Path:
    return _data(root, "neuralweb", "cortex")


def _attn_dir(root: Path) -> Path:
    return _data(root, "reflexes", "cortex_attention")


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _cfg(root: Path | None = None) -> dict:
    """Load cortex config section from config.yml.  Fail-open; returns defaults."""
    base = _repo_root(root)
    cfg_path = base / "config.yml"
    try:
        import yaml
        text = cfg_path.read_text(encoding="utf-8")
        doc = yaml.safe_load(text) or {}
        return dict(doc.get("cortex") or {})
    except Exception as exc:  # noqa: BLE001
        log.warning("cortex: config.yml not readable (%s); using defaults", exc)
        return {}


# ---------------------------------------------------------------------------
# Auth / client builders  (reuse llm_auth.build_providers pattern)
# ---------------------------------------------------------------------------

def _build_providers(cfg: dict) -> list[dict]:
    """Build Anthropic-only provider list.  DeepSeek excluded from deliberation path.

    For the anthropic provider, prefers CORTEX_ANTHROPIC_API_KEY when set so
    the cortex job can use a dedicated metered API key decoupled from the shared
    OAuth session quota.  Falls back to ANTHROPIC_API_KEY when the cortex key is
    absent (empty secret = transparent; nothing breaks).
    """
    from engine import llm_auth  # noqa: PLC0415
    model = cfg.get("llm_model", _DEFAULT_MODEL)

    # Override api_key_env when CORTEX_ANTHROPIC_API_KEY is populated in env
    cortex_key = os.environ.get(_CORTEX_API_KEY_ENV, "").strip()
    cfg_override = dict(cfg)
    if cortex_key:
        cfg_override["api_key_env"] = _CORTEX_API_KEY_ENV
        log.info("cortex: using dedicated %s for anthropic provider", _CORTEX_API_KEY_ENV)
        # Promote anthropic ahead of oauth so we don't burn 4×(15/60/180s) of
        # OAuth 429 backoff before reaching the metered key.  Only override when
        # config.yml has not set an explicit provider_order (operator config wins).
        if "provider_order" not in cfg:
            cfg_override["provider_order"] = ["anthropic", "oauth", "deepseek"]
            log.debug("cortex: metered key present — provider order set to anthropic-first")
    else:
        # Ensure the standard key env is used (belt-and-suspenders default)
        cfg_override.setdefault("api_key_env", _FALLBACK_API_KEY_ENV)

    return llm_auth.build_providers(
        cfg_override,
        opus_model=model,
        deepseek_model=None,  # not used in deliberation (D8 ruling)
    )


# ---------------------------------------------------------------------------
# Deny-roots path guard  (bot_mcp pattern)
# ---------------------------------------------------------------------------

def _check_deny_roots(requested_path: str, root: Path) -> str | None:
    """Return an error string if the path is in deny-roots; else None."""
    rp = Path(requested_path)
    # Check exact deny filenames
    if rp.name in _DENY_FILENAME_EXACT:
        return f"deny-roots: {rp.name!r} is in the deny list"
    # Check path fragment deny
    parts_lower = {p.lower() for p in rp.parts}
    for frag in _DENY_PATH_FRAGMENTS:
        if frag in parts_lower:
            return f"deny-roots: path contains denied fragment {frag!r}"
    # Resolve and check read-roots
    try:
        resolved = (root / rp).resolve()
        read_roots = [
            (root / "data").resolve(),
            (root / "site").resolve(),
            (root / "docs").resolve(),
            (root / "research").resolve(),
        ]
        import os as _os
        if not any(
            str(resolved).startswith(str(rr) + _os.sep) or resolved == rr
            for rr in read_roots
        ):
            return f"deny-roots: {requested_path!r} is outside allowed read roots"
    except Exception as exc:  # noqa: BLE001
        return f"deny-roots: path resolution error ({exc})"
    return None


# ---------------------------------------------------------------------------
# Staleness gate
# ---------------------------------------------------------------------------

def _compute_run_state_hash(root: Path) -> dict:
    """Compute the inputs hash tuple for the staleness gate."""
    pieces: dict[str, Any] = {}

    # 1. world_state inputs_hash
    ws_path = _data(root, "neuralweb", "world_state.json")
    try:
        ws = json.loads(ws_path.read_text(encoding="utf-8"))
        pieces["ws_inputs_hash"] = ws.get("inputs_hash") or ws.get("envelope", {}).get("inputs_hash", "")
    except Exception:  # noqa: BLE001
        pieces["ws_inputs_hash"] = ""

    # 2. spine row count
    spine_path = _data(root, "neuralweb", "spine_index.parquet")
    try:
        import pandas as pd
        pieces["spine_rows"] = len(pd.read_parquet(spine_path, columns=["signal_id"]))
    except Exception:  # noqa: BLE001
        pieces["spine_rows"] = -1

    # 3. contradictions hash
    contra_path = _data(root, "neuralweb", "confluence_graph.json")
    try:
        contra_text = contra_path.read_text(encoding="utf-8")
        pieces["contradictions_hash"] = hashlib.sha256(contra_text.encode()).hexdigest()[:16]
    except Exception:  # noqa: BLE001
        pieces["contradictions_hash"] = ""

    return pieces


def _load_last_run_state(root: Path) -> dict:
    p = _cortex_dir(root) / "last_run_state.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _save_last_run_state(root: Path, state: dict) -> None:
    p = _cortex_dir(root) / "last_run_state.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state, default=str), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        log.warning("cortex: could not save last_run_state (%s)", exc)


def _state_changed(current: dict, last: dict) -> bool:
    """Return True if the run state has changed since last run."""
    if not last:
        return True
    return (
        current.get("ws_inputs_hash") != last.get("ws_inputs_hash")
        or current.get("spine_rows") != last.get("spine_rows")
        or current.get("contradictions_hash") != last.get("contradictions_hash")
    )


# ---------------------------------------------------------------------------
# Tool implementations — read tools
# ---------------------------------------------------------------------------

def _tool_read_world_state(root: Path, _params: dict) -> dict:
    """Read data/neuralweb/world_state.json (the N1 blackboard)."""
    p = _data(root, "neuralweb", "world_state.json")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"world_state unreadable: {exc}"}


def _tool_query_spine(root: Path, params: dict) -> dict:
    """Query spine_index.parquet with filters, capped at _SPINE_ROW_CAP rows."""
    try:
        from engine.neuralweb.query import load_index, query  # noqa: PLC0415
        df = load_index(root)
        if df is None or df.empty:
            return {"rows": [], "total_available": 0, "note": "spine empty or unavailable"}

        # Build filter kwargs from params
        filter_kw: dict[str, Any] = {}
        if params.get("engine"):
            filter_kw["engine"] = params["engine"]
        if params.get("family"):
            filter_kw["family"] = params["family"]
        if params.get("symbol"):
            filter_kw["symbol"] = params["symbol"]
        if params.get("horizon"):
            filter_kw["horizon"] = int(params["horizon"])
        if params.get("graded_only") is True or params.get("graded_only") == "true":
            filter_kw["graded_only"] = True
        if params.get("ledger"):
            filter_kw["ledger"] = params["ledger"]

        filtered = query(df, **filter_kw)
        total = len(filtered)
        cap = min(total, _SPINE_ROW_CAP)
        rows = filtered.head(cap).to_dict(orient="records")
        # Coerce non-JSON-serializable types
        rows = json.loads(json.dumps(rows, default=str))
        return {
            "rows": rows,
            "total_available": total,
            "returned": cap,
            "capped": cap < total,
        }
    except Exception as exc:  # noqa: BLE001
        return {"error": f"query_spine failed: {exc}"}


def _tool_read_kernel(root: Path, params: dict) -> dict:
    """Read kernel_estimates.parquet — reliability profiles."""
    try:
        import pandas as pd
        p = _data(root, "neuralweb", "kernel_estimates.parquet")
        df = pd.read_parquet(p)
        if params.get("engine"):
            df = df[df["engine"] == params["engine"]]
        rows = df.head(100).to_dict(orient="records")
        return {"rows": json.loads(json.dumps(rows, default=str)), "total": len(df)}
    except Exception as exc:  # noqa: BLE001
        # Also try kernel_families.json as fallback
        try:
            p2 = _data(root, "neuralweb", "kernel_families.json")
            return json.loads(p2.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {"error": f"read_kernel failed: {exc}"}


def _tool_read_graph(root: Path, params: dict) -> dict:
    """Read confluence_graph.json (filterable by edge_type)."""
    try:
        p = _data(root, "neuralweb", "confluence_graph.json")
        graph = json.loads(p.read_text(encoding="utf-8"))
        edge_type = params.get("edge_type")
        if edge_type and "edges" in graph:
            graph["edges"] = [
                e for e in graph["edges"]
                if e.get("edge_type") == edge_type or e.get("type") == edge_type
            ]
        return graph
    except Exception as exc:  # noqa: BLE001
        return {"error": f"read_graph failed: {exc}"}


def _tool_read_contradictions(root: Path, _params: dict) -> dict:
    """Read contradictions from confluence_graph.json (contradicts edges only)."""
    try:
        p = _data(root, "neuralweb", "confluence_graph.json")
        graph = json.loads(p.read_text(encoding="utf-8"))
        edges = graph.get("edges") or []
        contras = [e for e in edges if e.get("edge_type") in ("contradicts", "contradict", "conflict")]
        return {"contradictions": contras, "count": len(contras)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"read_contradictions failed: {exc}"}


def _tool_read_governance(root: Path, params: dict) -> dict:
    """Read recent events from data/neuralweb/governance.jsonl."""
    try:
        p = _data(root, "neuralweb", "governance.jsonl")
        if not p.exists():
            return {"events": [], "note": "governance.jsonl not yet populated"}
        events = []
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass
        tenant = params.get("tenant")
        if tenant:
            events = [e for e in events if e.get("target") == tenant or e.get("authored_by") == tenant]
        # Return most recent 50
        return {"events": events[-50:], "total": len(events)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"read_governance failed: {exc}"}


def _tool_read_artifact(root: Path, params: dict) -> dict:
    """Path-based read with deny-roots check and 50 KB size cap."""
    path_str = params.get("path", "")
    if not path_str:
        return {"error": "read_artifact: 'path' parameter is required"}

    # Deny-roots check
    deny_err = _check_deny_roots(path_str, root)
    if deny_err:
        log.warning("cortex: read_artifact DENIED — %s", deny_err)
        return {"error": deny_err}

    try:
        p = (root / path_str).resolve()
        if not p.exists():
            return {"error": f"read_artifact: path not found: {path_str}"}
        size = p.stat().st_size
        if size > _READ_SIZE_CAP:
            return {
                "error": f"read_artifact: file too large ({size} bytes > {_READ_SIZE_CAP} cap). "
                         f"Use query_spine or read_graph for structured data.",
            }
        text = p.read_text(encoding="utf-8", errors="replace")
        # Try JSON parse for structured return
        try:
            return {"content": json.loads(text), "size_bytes": size}
        except Exception:  # noqa: BLE001
            return {"content": text[:10000], "size_bytes": size, "format": "text"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"read_artifact failed: {exc}"}


# ---------------------------------------------------------------------------
# Tool implementations — write tools (shadow-tier only)
# ---------------------------------------------------------------------------

def _tool_flag_attention(root: Path, params: dict, now_str: str) -> dict:
    """Append claim-shaped rows to data/reflexes/cortex_attention/firings.jsonl."""
    items = params.get("items") or []
    if not items:
        # Also accept a single item dict
        if params.get("scope_key") or params.get("direction") is not None:
            items = [params]
        else:
            return {"error": "flag_attention: no items provided"}

    from engine.neuralweb import reflexes as _reflexes  # noqa: PLC0415
    written = []
    for item in items[:10]:  # cap batch
        payload = {
            "ts": now_str,
            "trigger_type": "cortex_attention",
            "trigger_key": item.get("scope_key", "macro"),
            "action_taken": "attention_flagged",
            "asof": now_str[:10],
            "scope_type": item.get("scope_type", "entity"),
            "scope_key": item.get("scope_key", ""),
            "direction": item.get("direction", 0),
            "horizon_d": item.get("horizon_d", 5),
            "claim_family": _SCHEMA_ATTN,
            "falsifier": item.get("falsifier", ""),
            "is_context_only": True,
            "extra": item.get("extra", {}),
        }
        rec = _reflexes.record_firing("cortex_attention", payload, root)
        written.append(rec.get("claim_id"))
    return {"written": len(written), "claim_ids": written}


def _detect_context_stale(root: Path, now_str: str) -> tuple[bool, str | None]:
    """Check whether world_state.json was produced before today's run date.

    Returns (context_stale, context_as_of).
    """
    ws_path = _data(root, "neuralweb", "world_state.json")
    try:
        ws = json.loads(ws_path.read_text(encoding="utf-8"))
        produced_at = ws.get("produced_at") or ws.get("as_of") or ""
        if not produced_at:
            return False, None
        run_date = now_str[:10]
        ws_date = str(produced_at)[:10]
        stale = ws_date < run_date
        return stale, produced_at
    except Exception:  # noqa: BLE001
        return False, None


def _tool_write_memo(root: Path, params: dict, now_str: str, probation_status: dict) -> dict:
    """Write the committee memo to data/neuralweb/cortex/memo.json."""
    memo: dict = {
        "schema": _SCHEMA_MEMO,
        "as_of": now_str,
        "summary": params.get("summary", ""),
        "what_fired": params.get("what_fired", []),
        "contradictions_review": params.get("contradictions_review", ""),
        "decaying_families": params.get("decaying_families", []),
        "deserves_operator": params.get("deserves_operator", []),
        "probation": probation_status,
        "tool_call_census": params.get("tool_call_census", {}),
        "is_context_only": True,
    }
    # Include run_status when provided at write time (forced-write / fallback paths).
    # The normal tool-loop path stamps run_status via a post-hoc rewrite; including
    # it here as well means the key is always present even if that rewrite fails.
    if "run_status" in params:
        memo["run_status"] = params["run_status"]

    cortex_dir = _cortex_dir(root)
    cortex_dir.mkdir(parents=True, exist_ok=True)

    memo_path = cortex_dir / "memo.json"
    memo_path.write_text(json.dumps(memo, indent=2, default=str), encoding="utf-8")

    # Mirror to site/neuralweb/ when site/ exists
    site_nw = _site(root, "neuralweb")
    if site_nw.parent.exists():
        site_nw.mkdir(parents=True, exist_ok=True)
        (site_nw / "cortex_memo.json").write_text(
            json.dumps(memo, indent=2, default=str), encoding="utf-8"
        )

    return {"written": str(memo_path), "as_of": now_str}


def _tool_stake_hypothesis(root: Path, params: dict, now_str: str) -> dict:
    """Register a hypothesis via the metabolism module (PR2 — live registration path).

    Calls engine.neuralweb.metabolism.register_hypothesis() directly.
    The inbox row is also appended for audit-trail purposes with a status transition.
    Server-side registered_at is set by the metabolism module — never cortex-supplied.
    """
    from engine.neuralweb.metabolism import register_hypothesis as _register  # noqa: PLC0415
    from datetime import datetime, timezone  # noqa: PLC0415

    # Build the hypothesis dict for registration
    h = {
        "hypothesis": params.get("claim") or params.get("hypothesis", ""),
        "claim_shape": params.get("claim_shape", "lead_lag"),
        "spine_query": params.get("spine_query") or {"subject": params.get("subject", "")},
        "pre_committed_gate": params.get("pre_committed_gate"),
        "horizon_d": params.get("horizon_d"),
        "registered_by": "cortex",
    }

    # Attempt registration (budget enforcement + validation in metabolism)
    try:
        result = _register(h, root=str(root))
    except Exception as exc:  # noqa: BLE001
        log.warning("cortex: stake_hypothesis metabolism failed (%s)", exc)
        result = {"id": "error", "status": "invalid", "reason": str(exc)}

    reg_status = result.get("status", "invalid")

    # Append to inbox as audit trail with status transition
    inbox_path = _cortex_dir(root) / "hypothesis_inbox.jsonl"
    inbox_path.parent.mkdir(parents=True, exist_ok=True)

    record = {
        "schema": _SCHEMA_HYPO,
        "id": result.get("id", "unknown"),
        "status": reg_status,
        "registered_at": result.get("registered_at"),
        "proposed_at": now_str,
        "proposed_by": "cortex",
        "subject": params.get("subject", ""),
        "claim": h["hypothesis"],
        "hypothesis": h["hypothesis"],
        "claim_shape": h["claim_shape"],
        "falsifier": params.get("falsifier", ""),
        "horizon_d": params.get("horizon_d"),
        "pre_committed_gate": params.get("pre_committed_gate"),
        "spine_query": params.get("spine_query"),
        "registration_result": result,
        "is_context_only": True,
    }

    try:
        with inbox_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
    except Exception as exc:  # noqa: BLE001
        log.warning("cortex: inbox append failed (%s)", exc)

    return {
        "id": result.get("id"),
        "status": reg_status,
        "registered_at": result.get("registered_at"),
        "come_back": result.get("come_back"),
        "reason": result.get("reason"),
        "budget_state": result.get("budget_state"),
    }


# ---------------------------------------------------------------------------
# Tool dispatcher (A7 guard)
# ---------------------------------------------------------------------------

def _read_options_state(root: Path):
    """Shared loader for the options entry state table (display-tier snapshot)."""
    p = _data(root, "options_entry", "state.parquet")
    if not p.exists():
        return None, "options_entry/state.parquet absent"
    try:
        import pandas as pd  # noqa: PLC0415
        return pd.read_parquet(p), None
    except Exception as exc:  # noqa: BLE001
        return None, f"options_entry/state.parquet unreadable: {exc}"


_OPTIONS_ROW_CAP = 100


def _tool_read_options_entry_state(root: Path, params: dict) -> dict:
    """Read the options entry state snapshot (RO-7). Raw fields only — the table
    carries NO composites (RO-2); rows sort alphabetically to avoid implying rank."""
    df, err = _read_options_state(root)
    if df is None:
        return {"rows": [], "error": err}
    ticker = params.get("ticker")
    if ticker:
        df = df[df["ticker"] == str(ticker).upper()]
    top_n = min(int(params.get("top_n") or 25), _OPTIONS_ROW_CAP)
    df = df.sort_values("ticker").head(top_n)
    rows = json.loads(df.to_json(orient="records"))
    return {"rows": rows, "n_total": int(len(df)),
            "note": "display-tier raw fields; iv_rank_* structurally null (A9); "
                    "gamma_regime structurally constant per name (audit #29)"}


def _tool_explain_options_context(root: Path, params: dict) -> dict:
    """Plain-language render of one ticker's options state, with caveats (RO-7)."""
    ticker = str(params.get("ticker") or "").upper()
    if not ticker:
        return {"error": "ticker required"}
    df, err = _read_options_state(root)
    if df is None:
        return {"error": err}
    sub = df[df["ticker"] == ticker]
    if sub.empty:
        return {"ticker": ticker, "note": "no options state row (thin/absent coverage)"}
    r = json.loads(sub.iloc[[0]].to_json(orient="records"))[0]
    lines: list[str] = []
    if r.get("gex_confirm_verdict"):
        lines.append(f"GEX structure verdict: {r['gex_confirm_verdict']} (display-only).")
    if r.get("gamma_regime"):
        lines.append(
            f"Gamma regime {r['gamma_regime']} — CAVEAT: structurally constant per name "
            "(audit #29); do not read as time-varying.")
    if r.get("skew") is not None:
        d = r.get("skew_5d_chg")
        lines.append(f"OTM-put skew {r['skew']:.4f}"
                     + (f", 5d change {d:+.4f}" if d is not None else " (5d change null)") + ".")
    if r.get("ivspread_rel") is not None:
        lines.append(f"CW ivspread {r['ivspread_rel']:+.4f} (relative; >0 = calls rich).")
    if r.get("pin_risk"):
        lines.append(f"PIN RISK: within 2% of a wall/max-pain with long gamma, "
                     f"opex in {r.get('opex_days')}d.")
    lines.append(f"Evidence quality: {r.get('evidence_quality')}; iv_rank fields are "
                 "structurally null until the A9 IV-backfill lands.")
    return {"ticker": ticker, "state": r, "plain_english": lines,
            "mandate": "display/context only — no score, no rank, no origination (Article 1)"}


def _tool_query_options_confluence(root: Path, params: dict) -> dict:
    """Options edges from the display-only confluence graph (RO-7)."""
    p = _data(root, "neuralweb", "confluence_graph.json")
    try:
        graph = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"edges": [], "error": f"confluence_graph unreadable: {exc}"}
    edges = [e for e in graph.get("edges", [])
             if str(e.get("src", "")).startswith("options.")]
    ticker = params.get("ticker")
    if ticker:
        t = str(ticker).upper()
        edges = [e for e in edges if t in str(e.get("note", ""))]
    return {"edges": edges, "display_only": True}


def _tool_list_options_contradictions(root: Path, _params: dict) -> dict:
    """Buy-lane names whose options state contradicts the long thesis (RO-7).
    Reads display surfaces only: state.parquet + latest board lane membership."""
    df, err = _read_options_state(root)
    if df is None:
        return {"contradictions": [], "error": err}
    lp = _data(root, "us_board_ledger", "retro_grades.parquet")
    if not lp.exists():
        return {"contradictions": [], "error": "us_board_ledger absent"}
    try:
        import pandas as pd  # noqa: PLC0415
        board = pd.read_parquet(lp, columns=["as_of", "ticker", "lane"])
        latest = board["as_of"].max()
        buys = set(board[(board["as_of"] == latest) & (board["lane"] == "buy")]["ticker"])
    except Exception as exc:  # noqa: BLE001
        return {"contradictions": [], "error": f"board read failed: {exc}"}
    out: list[dict] = []
    st = df.set_index("ticker")
    for t in sorted(buys):
        if t not in st.index:
            continue
        r = st.loc[t]
        reasons: list[str] = []
        try:
            if r.get("skew_5d_chg") is not None and float(r["skew_5d_chg"]) > 0:
                reasons.append("OTM-put skew rising over 5d")
            if r.get("ivspread_rel") is not None and float(r["ivspread_rel"]) < 0:
                reasons.append("matched puts rich vs calls (ivspread<0)")
        except Exception:  # noqa: BLE001
            continue
        if reasons:
            out.append({"ticker": t, "reasons": reasons})
    return {"as_of_board": str(latest), "contradictions": out,
            "display_only": True,
            "mandate": "de-escalation context only; never a short signal (RO-3)"}


# ---------------------------------------------------------------------------
# Tool implementations — Factor Intelligence × Neural Web (RUL-NW3)
# ---------------------------------------------------------------------------

_FACTOR_CONTRADICTIONS_ROW_CAP = 100


def _tool_read_factor_state(root: Path, _params: dict) -> dict:
    """Read data/neuralweb/factor_intelligence_state.json (RUL-NW3).

    Returns the full committed artifact — includes panel health, factor weather,
    scorecard, contradictions digest, attention track record, hypotheses, and
    latest_board_coordinates block.  Fails open: returns structured gaps when
    the file is absent.  is_context_only always true.
    """
    p = _data(root, "neuralweb", "factor_intelligence_state.json")
    if not p.exists():
        return {
            "is_context_only": True,
            "gaps": ["data/neuralweb/factor_intelligence_state.json: absent — "
                     "factor_panel job has not run yet"],
            "note": "Factor state not yet built. Run the nightly factor_panel job.",
        }
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
        # Ensure mandate fields are always present regardless of artifact version
        state.setdefault("is_context_only", True)
        state.setdefault("display_only", True)
        return state
    except Exception as exc:  # noqa: BLE001
        return {
            "is_context_only": True,
            "gaps": [f"data/neuralweb/factor_intelligence_state.json: unreadable — {exc}"],
        }


def _tool_read_cycle_pattern_state(root: Path, _params: dict) -> dict:
    """Read data/neuralweb/cycle_pattern_state.json (CPI P6 wave 1).

    The committed CPI→NW adapter artifact: W4.2 hazard gate verdicts per cell
    (gate_status), latest per-entity cycle state + turn-hazard probabilities,
    and the truth-registry summary. DISPLAY-ONLY ceiling (CPI consumer matrix):
    the cortex may cite this as context / to de-escalate a calibrated key; it
    may never originate, score, or escalate from it. PRIOR cells are KM base
    rates, not validated model output. Fails open with structured gaps when
    the file is absent.  is_context_only always true.
    """
    p = _data(root, "neuralweb", "cycle_pattern_state.json")
    if not p.exists():
        return {
            "is_context_only": True,
            "display_only": True,
            "gaps": ["data/neuralweb/cycle_pattern_state.json: absent — "
                     "build_cycle_pattern_state has not run yet"],
            "note": "Cycle-pattern state not yet built. Run the nightly "
                    "build_cycle_pattern_state job.",
        }
    try:
        state = json.loads(p.read_text(encoding="utf-8"))
        # Ensure mandate fields are always present regardless of artifact version
        state.setdefault("is_context_only", True)
        state.setdefault("display_only", True)
        return state
    except Exception as exc:  # noqa: BLE001
        return {
            "is_context_only": True,
            "display_only": True,
            "gaps": [f"data/neuralweb/cycle_pattern_state.json: unreadable — {exc}"],
        }


def _tool_read_mechanism_pathways(root: Path, _params: dict) -> dict:
    """Read data/neuralweb/mechanism_pathways.json (MPC W1 artifact).

    Returns the mechanism pathway artifact JSON: primary pathway (family,
    direction, coverage_score or coverage_basis, coherence, evidence_legs,
    stale_legs), alternates (family names only), and/or no_pathway record
    with printed reason.

    DISPLAY-ONLY ceiling (RUL-CC-1): may be cited as context only.
    Forbidden: ranking, sizing, alert_escalation, claim_validation,
    board_ordering, mastermind_arming. is_context_only always true.
    Fails open with structured gaps when absent.
    """
    p = _data(root, "neuralweb", "mechanism_pathways.json")
    if not p.exists():
        return {
            "is_context_only": True,
            "display_only": True,
            "not_a_signal": True,
            "gaps": [
                "data/neuralweb/mechanism_pathways.json: absent — "
                "build_mechanism_pathways has not run yet"
            ],
            "note": (
                "Mechanism pathway artifact not yet built. "
                "Run the nightly build_mechanism_pathways job."
            ),
        }
    try:
        artifact = json.loads(p.read_text(encoding="utf-8"))
        # Mandate fields always present regardless of artifact version
        artifact.setdefault("is_context_only", True)
        artifact.setdefault("display_only", True)
        artifact.setdefault("not_a_signal", True)
        return artifact
    except Exception as exc:  # noqa: BLE001
        return {
            "is_context_only": True,
            "display_only": True,
            "not_a_signal": True,
            "gaps": [f"data/neuralweb/mechanism_pathways.json: unreadable — {exc}"],
        }


def _tool_read_theme_state(root: Path, params: dict) -> dict:
    """Read data/neuralweb/theme_state.json — TIL W5 thematic-state compact summary.

    Optional param: theme_id (str) — filter to a single theme.
    Delegates to ask_brain._tool_read_theme_state to avoid duplication.
    DISPLAY-ONLY ceiling (TIL W5): may be cited as context or to de-escalate
    a calibrated key; may NEVER originate, score, or escalate a signal.
    No write path. is_context_only always true.
    """
    from engine.neuralweb.ask_brain import _tool_read_theme_state as _ask_brain_read  # noqa: PLC0415
    return _ask_brain_read(root, params)


def _tool_read_theme_thesis(root: Path, params: dict) -> dict:
    """Read site/neuralwebdata/theme_thesis.json — TIL thesis ledger projection.

    Optional param: theme_id. Delegates to ask_brain handler (single source).
    DISPLAY-ONLY ceiling; no write path; is_context_only always true.
    """
    from engine.neuralweb.ask_brain import _tool_read_theme_thesis as _f  # noqa: PLC0415
    return _f(root, params)


def _tool_read_theme_pathways(root: Path, params: dict) -> dict:
    """Read site/neuralwebdata/theme_pathways.json — TIL beneficiary/loser graph.

    Optional param: theme_id. Delegates to ask_brain handler (single source).
    TI-R5 fence: context only, never a rotation call. No write path.
    """
    from engine.neuralweb.ask_brain import _tool_read_theme_pathways as _f  # noqa: PLC0415
    return _f(root, params)


def _tool_read_liquidity_plumbing_cx(root: Path, params: dict) -> dict:
    """Read the liquidity-plumbing organ summary (delegates to ask_brain)."""
    from engine.neuralweb.ask_brain import _tool_read_liquidity_plumbing as _f  # noqa: PLC0415
    return _f(root, params)


def _tool_read_china_decision_packet_cx(root: Path, params: dict) -> dict:
    """Read the China decision packet summary (delegates to ask_brain)."""
    from engine.neuralweb.ask_brain import _tool_read_china_decision_packet as _f  # noqa: PLC0415
    return _f(root, params)


def _tool_list_factor_contradictions(root: Path, params: dict) -> dict:
    """Read data/neuralweb/factor_contradictions.jsonl (RUL-NW3).

    Pair G borrowed-strength contradiction ledger.  Params: ticker (optional),
    date_from (optional, YYYY-MM-DD), limit (default 25, max 100).
    Returns records carrying display_only=true.  Fails open when absent.
    """
    p = _data(root, "neuralweb", "factor_contradictions.jsonl")
    if not p.exists():
        return {
            "records": [],
            "total": 0,
            "is_context_only": True,
            "display_only": True,
            "note": "factor_contradictions.jsonl absent — dormant until panel has >=60 distinct dates",
        }
    try:
        rows: list[dict] = []
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:  # noqa: BLE001
                    pass

        # Apply filters
        ticker = str(params.get("ticker") or "").upper()
        if ticker:
            rows = [r for r in rows if str(r.get("ticker") or "").upper() == ticker]

        date_from = str(params.get("date_from") or "")
        if date_from:
            rows = [r for r in rows
                    if str(r.get("date") or r.get("as_of") or "") >= date_from]

        total = len(rows)
        limit = min(int(params.get("limit") or 25), _FACTOR_CONTRADICTIONS_ROW_CAP)
        # Return most recent rows first (tail slice then reverse)
        rows = list(reversed(rows[-limit:])) if rows else []

        return {
            "records": rows,
            "total_available": total,
            "returned": len(rows),
            "is_context_only": True,
            "display_only": True,
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "records": [],
            "error": f"list_factor_contradictions failed: {exc}",
            "is_context_only": True,
            "display_only": True,
        }


def _tool_explain_factor_context(root: Path, params: dict) -> dict:
    """Structured factor context for one ticker (RUL-NW3).

    Reads ONLY committed artifacts: the state artifact's latest_board_coordinates
    block and recent fire_coordinates.jsonl rows for this ticker.

    Returns a structured context object with an explicit gaps list when data is
    absent.  Does NOT rank, recommend, or emit directional verbs.
    """
    ticker = str(params.get("ticker") or "").upper()
    if not ticker:
        return {"error": "ticker parameter is required", "is_context_only": True}

    context: dict = {
        "ticker": ticker,
        "is_context_only": True,
        "display_only": True,
        "mandate": "display/context only — no rank, no score, no origination (Article 1, RUL-NW3)",
        "gaps": [],
    }

    # 1. Fetch board coordinates from committed state artifact
    state_path = _data(root, "neuralweb", "factor_intelligence_state.json")
    if not state_path.exists():
        context["gaps"].append("factor_intelligence_state.json: absent")
        context["board_coordinates"] = None
        context["scorecard"] = None
    else:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            board_coords = state.get("latest_board_coordinates") or {}

            # Find ticker's coordinates
            # latest_board_coordinates can be a dict keyed by ticker or a list
            if isinstance(board_coords, dict):
                ticker_coords = board_coords.get(ticker)
            elif isinstance(board_coords, list):
                ticker_coords = next(
                    (r for r in board_coords if str(r.get("ticker") or "").upper() == ticker),
                    None,
                )
            else:
                ticker_coords = None

            if ticker_coords is None:
                context["gaps"].append(
                    f"{ticker}: not present in latest_board_coordinates "
                    f"(not in buy lane or coordinates absent)"
                )
            context["board_coordinates"] = ticker_coords

            # Attach scorecard block (factor-wide, not per-ticker)
            context["scorecard"] = state.get("scorecard")
            context["factor_weather"] = state.get("factor_weather")
            context["as_of"] = state.get("as_of")
        except Exception as exc:  # noqa: BLE001
            context["gaps"].append(f"factor_intelligence_state.json: unreadable — {exc}")
            context["board_coordinates"] = None
            context["scorecard"] = None

    # 2. Fetch recent fire_coordinates rows for this ticker
    fire_path = _data(root, "factordata", "fire_coordinates.jsonl")
    if not fire_path.exists():
        context["gaps"].append("fire_coordinates.jsonl: absent")
        context["fire_history"] = []
    else:
        try:
            fire_rows: list[dict] = []
            with fire_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        if str(row.get("ticker") or "").upper() == ticker:
                            fire_rows.append(row)
                    except Exception:  # noqa: BLE001
                        pass
            # Return up to 10 most recent rows
            context["fire_history"] = fire_rows[-10:]
            if not fire_rows:
                context["gaps"].append(f"{ticker}: no fire_coordinates rows found")
        except Exception as exc:  # noqa: BLE001
            context["gaps"].append(f"fire_coordinates.jsonl: unreadable — {exc}")
            context["fire_history"] = []

    return context


def _tool_read_context_candidates(root: Path, params: dict) -> dict:
    """Read data/neuralweb/context_candidates.jsonl — W4 context scanner output.

    Returns top-K (<=20) non-decayed candidates and the risk-lens summary if
    data/neuralweb/context_risk.json exists (fail-open when absent).

    R-CI11: bounded top-K, no per-ticker dumps.  is_context_only always true.
    DISPLAY ONLY — candidates are never signals, never ranked, never scored.
    All three legal exits for a candidate are: (a) cortex stakes hypothesis via
    metabolism; (b) human charters pre-reg study; (c) candidate decays.
    """
    _MAX_CANDIDATES = 20

    result: dict = {
        "is_context_only": True,
        "display_only": True,
        "mandate": (
            "context candidates are NEVER signals; exits: (a) stake_hypothesis via "
            "metabolism; (b) human pre-reg study; (c) decay. Article 1 enforced."
        ),
        "candidates": [],
        "total_non_decayed": 0,
        "risk_lens": None,
        "gaps": [],
    }

    # Load candidates
    cand_path = _data(root, "neuralweb", "context_candidates.jsonl")
    if not cand_path.exists():
        result["gaps"].append(
            "data/neuralweb/context_candidates.jsonl: absent — "
            "build_context_candidates has not run yet"
        )
    else:
        try:
            rows: list[dict] = []
            with cand_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        if row.get("status") != "decayed":
                            rows.append(row)
                    except Exception:  # noqa: BLE001
                        pass

            result["total_non_decayed"] = len(rows)

            # Apply optional template filter
            template_filter = str(params.get("template") or "").upper()
            if template_filter:
                rows = [r for r in rows if r.get("template", "").upper() == template_filter]

            # Sort by null_pctile descending, cap at _MAX_CANDIDATES
            rows.sort(key=lambda r: r.get("null_pctile", 0), reverse=True)
            top_k = params.get("top_k")
            try:
                cap = min(int(top_k), _MAX_CANDIDATES) if top_k else _MAX_CANDIDATES
            except (TypeError, ValueError):
                cap = _MAX_CANDIDATES
            result["candidates"] = rows[:cap]

        except Exception as exc:  # noqa: BLE001
            result["gaps"].append(
                f"data/neuralweb/context_candidates.jsonl: unreadable — {exc}"
            )

    # Load risk lens (fail-open)
    risk_path = _data(root, "neuralweb", "context_risk.json")
    if not risk_path.exists():
        result["gaps"].append(
            "data/neuralweb/context_risk.json: absent — "
            "build_context_risk has not run yet (W3 pending)"
        )
    else:
        try:
            risk_doc = json.loads(risk_path.read_text(encoding="utf-8"))
            # Return summary sub-block only (not full per-ticker detail — R-CI11)
            result["risk_lens"] = {
                "as_of": risk_doc.get("as_of"),
                "board_composition_summary": risk_doc.get("board_composition_summary"),
                "regime_cell": risk_doc.get("regime_cell"),
                "display_only": True,
            }
        except Exception as exc:  # noqa: BLE001
            result["gaps"].append(
                f"data/neuralweb/context_risk.json: unreadable — {exc}"
            )

    return result


def _tool_read_causal_candidates(root: Path, _params: dict) -> dict:
    """Read CHF W5 causal mechanism cards (inbox/skeptic_passed) + screened edges + null count.

    Returns top-10 mechanism cards with status in {inbox, skeptic_passed} (fields:
    mechanism_id, claim_en, causal_graph, falsifiers, test_spec), top-10 screened
    causal edges from causal_edges.jsonl, and the null-library count.

    DISPLAY-ONLY ceiling (CHF-R1/CHF-R17): cards are inert proposal material.
    Staking a card via stake_hypothesis counts against the normal 3/week cortex budget.
    LLM actors (the cortex) may NEVER transition a card's status — only script or
    human actors may do so. is_context_only always true. Fails open when absent.
    """
    _MAX_CARDS = 10
    _MAX_EDGES = 10

    result: dict = {
        "is_context_only": True,
        "display_only": True,
        "mandate": (
            "causal cards are INERT PROPOSAL MATERIAL (CHF-R17). "
            "Staking one via stake_hypothesis counts against the normal 3/week budget. "
            "The cortex may NEVER transition a card's status; only script/human actors may."
        ),
        "mechanism_cards": [],
        "total_actionable_cards": 0,
        "screened_edges": [],
        "total_screened_edges": 0,
        "null_library_count": 0,
        "gaps": [],
    }

    # ---- Load mechanism cards ----
    cards_path = _data(root, "neuralweb", "causal_mechanisms.jsonl")
    if not cards_path.exists():
        result["gaps"].append(
            "data/neuralweb/causal_mechanisms.jsonl: absent — "
            "run_causal_brainstorm has not filed any cards yet"
        )
    else:
        try:
            actionable: list[dict] = []
            with cards_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        card = json.loads(line)
                        if card.get("status") in ("inbox", "skeptic_passed"):
                            actionable.append(card)
                    except Exception:  # noqa: BLE001
                        pass

            result["total_actionable_cards"] = len(actionable)

            # Sort by filed_at descending, cap at _MAX_CARDS
            actionable.sort(key=lambda c: c.get("filed_at", ""), reverse=True)
            top_cards = actionable[:_MAX_CARDS]

            # Return only the load-bearing fields (not full raw card)
            result["mechanism_cards"] = [
                {
                    "mechanism_id": c.get("mechanism_id"),
                    "status": c.get("status"),
                    "family": c.get("family"),
                    "claim_en": c.get("claim_en"),
                    "causal_graph": c.get("causal_graph"),
                    "falsifiers": c.get("falsifiers"),
                    "test_spec": c.get("test_spec"),
                    "filed_at": c.get("filed_at"),
                    "filing_week": c.get("filing_week"),
                }
                for c in top_cards
            ]
        except Exception as exc:  # noqa: BLE001
            result["gaps"].append(
                f"data/neuralweb/causal_mechanisms.jsonl: unreadable — {exc}"
            )

    # ---- Load screened candidate edges ----
    edges_path = _data(root, "neuralweb", "causal_edges.jsonl")
    if not edges_path.exists():
        result["gaps"].append(
            "data/neuralweb/causal_edges.jsonl: absent — "
            "build_causal_edges has not run yet"
        )
    else:
        try:
            screened: list[dict] = []
            with edges_path.open(encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        edge = json.loads(line)
                        if edge.get("verdict") == "screened_candidate":
                            screened.append(edge)
                    except Exception:  # noqa: BLE001
                        pass

            result["total_screened_edges"] = len(screened)
            result["screened_edges"] = screened[:_MAX_EDGES]
        except Exception as exc:  # noqa: BLE001
            result["gaps"].append(
                f"data/neuralweb/causal_edges.jsonl: unreadable — {exc}"
            )

    # ---- Null library count ----
    nulls_path = _data(root, "neuralweb", "causal_nulls.jsonl")
    if nulls_path.exists():
        try:
            count = sum(
                1 for line in nulls_path.open(encoding="utf-8")
                if line.strip()
            )
            result["null_library_count"] = count
        except Exception as exc:  # noqa: BLE001
            result["gaps"].append(f"data/neuralweb/causal_nulls.jsonl: unreadable — {exc}")
    else:
        result["gaps"].append(
            "data/neuralweb/causal_nulls.jsonl: absent — "
            "no nulls accumulated yet"
        )

    return result


def dispatch_tool(
    tool_name: str,
    tool_params: dict,
    root: Path,
    now_str: str,
    probation_status: dict,
    tool_call_census: dict,
) -> dict:
    """Route a tool call.  Refuses any name outside _ALLOWED_TOOLS (A7 guard)."""
    if tool_name not in _ALLOWED_TOOLS:
        log.warning("cortex: tool dispatcher REFUSED unknown tool %r (A7 guard)", tool_name)
        return {"error": f"tool not allowed: {tool_name!r}. Whitelist: {sorted(_ALLOWED_TOOLS)}"}

    # Track census
    tool_call_census[tool_name] = tool_call_census.get(tool_name, 0) + 1

    if tool_name == "read_world_state":
        return _tool_read_world_state(root, tool_params)
    elif tool_name == "query_spine":
        return _tool_query_spine(root, tool_params)
    elif tool_name == "read_kernel":
        return _tool_read_kernel(root, tool_params)
    elif tool_name == "read_graph":
        return _tool_read_graph(root, tool_params)
    elif tool_name == "read_contradictions":
        return _tool_read_contradictions(root, tool_params)
    elif tool_name == "read_governance":
        return _tool_read_governance(root, tool_params)
    elif tool_name == "read_artifact":
        return _tool_read_artifact(root, tool_params)
    elif tool_name == "read_options_entry_state":
        return _tool_read_options_entry_state(root, tool_params)
    elif tool_name == "explain_options_context":
        return _tool_explain_options_context(root, tool_params)
    elif tool_name == "query_options_confluence":
        return _tool_query_options_confluence(root, tool_params)
    elif tool_name == "list_options_contradictions":
        return _tool_list_options_contradictions(root, tool_params)
    elif tool_name == "read_factor_state":
        return _tool_read_factor_state(root, tool_params)
    elif tool_name == "list_factor_contradictions":
        return _tool_list_factor_contradictions(root, tool_params)
    elif tool_name == "explain_factor_context":
        return _tool_explain_factor_context(root, tool_params)
    elif tool_name == "read_cycle_pattern_state":
        return _tool_read_cycle_pattern_state(root, tool_params)
    elif tool_name == "read_mechanism_pathways":
        return _tool_read_mechanism_pathways(root, tool_params)
    elif tool_name == "read_context_candidates":
        return _tool_read_context_candidates(root, tool_params)
    elif tool_name == "read_theme_state":
        # TIL W5 NW citizenship: thematic-state compact read (display/context only)
        return _tool_read_theme_state(root, tool_params)
    elif tool_name == "read_theme_thesis":
        return _tool_read_theme_thesis(root, tool_params)
    elif tool_name == "read_theme_pathways":
        return _tool_read_theme_pathways(root, tool_params)
    elif tool_name == "read_liquidity_plumbing":
        return _tool_read_liquidity_plumbing_cx(root, tool_params)
    elif tool_name == "read_china_decision_packet":
        return _tool_read_china_decision_packet_cx(root, tool_params)
    elif tool_name == "read_causal_candidates":
        # CHF W5: read causal mechanism cards + screened edges + null count
        return _tool_read_causal_candidates(root, tool_params)
    elif tool_name == "flag_attention":
        return _tool_flag_attention(root, tool_params, now_str)
    elif tool_name == "write_memo":
        return _tool_write_memo(root, tool_params, now_str, probation_status)
    elif tool_name == "stake_hypothesis":
        return _tool_stake_hypothesis(root, tool_params, now_str)

    return {"error": f"dispatcher: unhandled tool {tool_name!r}"}  # unreachable


# ---------------------------------------------------------------------------
# Anthropic tool schema definitions
# ---------------------------------------------------------------------------

def _tool_schemas() -> list[dict]:
    return [
        {
            "name": "read_world_state",
            "description": "Read data/neuralweb/world_state.json — the N1 blackboard with verdict, regime, breadth, rotation, alerts summary.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "read_options_entry_state",
            "description": "Read data/options_entry/state.parquet — display-tier per-ticker options state (raw fields only, no composites). Alphabetical order; optional ticker filter.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Optional: single ticker"},
                    "top_n": {"type": "integer", "description": "Row cap (default 25, max 100)"},
                },
                "required": [],
            },
        },
        {
            "name": "explain_options_context",
            "description": "Plain-language render of one ticker's options entry state with caveats (A9 nulls, gamma structurally-constant, evidence quality). Display/context only.",
            "input_schema": {
                "type": "object",
                "properties": {"ticker": {"type": "string", "description": "Ticker symbol"}},
                "required": ["ticker"],
            },
        },
        {
            "name": "query_options_confluence",
            "description": "Display-only options edges from the confluence graph (confirms/contradicts vs board lanes). Optional ticker filter against edge notes.",
            "input_schema": {
                "type": "object",
                "properties": {"ticker": {"type": "string", "description": "Optional ticker"}},
                "required": [],
            },
        },
        {
            "name": "list_options_contradictions",
            "description": "Buy-lane names whose options state contradicts the long thesis (skew rising / puts rich). De-escalation context only — never a short signal.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "query_spine",
            "description": "Query spine_index.parquet with optional filters. Returns up to 200 rows.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "engine": {"type": "string", "description": "Filter by engine name"},
                    "family": {"type": "string", "description": "Filter by claim family"},
                    "symbol": {"type": "string", "description": "Filter by ticker symbol"},
                    "horizon": {"type": "integer", "description": "Filter by horizon in days"},
                    "ledger": {"type": "string", "description": "Filter by ledger source (spine, qledger, track_record, etc.)"},
                    "graded_only": {"type": "boolean", "description": "If true, return only graded rows"},
                },
                "required": [],
            },
        },
        {
            "name": "read_kernel",
            "description": "Read kernel_estimates.parquet — per-engine reliability profiles (regime-conditional IC, sample n, tier).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "engine": {"type": "string", "description": "Optional: filter by engine name"},
                },
                "required": [],
            },
        },
        {
            "name": "read_graph",
            "description": "Read confluence_graph.json — the N4 confluence graph. Optionally filter by edge_type.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "edge_type": {"type": "string", "description": "Filter edges by type (e.g. 'contradicts', 'confirms', 'feeds')"},
                },
                "required": [],
            },
        },
        {
            "name": "read_contradictions",
            "description": "Read contradicting signal pairs from the confluence graph.",
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "read_governance",
            "description": "Read recent events from data/neuralweb/governance.jsonl.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "tenant": {"type": "string", "description": "Optional: filter by target or authored_by"},
                },
                "required": [],
            },
        },
        {
            "name": "read_artifact",
            "description": "Read any file within allowed read roots (data/, site/, docs/, research/). Deny-roots checked. 50 KB size cap.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path from repo root (e.g. 'data/regime/latest.json')"},
                },
                "required": ["path"],
            },
        },
        # --- Factor Intelligence × Neural Web (RUL-NW3) ---
        {
            "name": "read_factor_state",
            "description": (
                "Read data/neuralweb/factor_intelligence_state.json — the committed factor "
                "intelligence digest: panel health, factor weather, Pair G contradictions "
                "digest, attention track record (query_factor_attention folded here per "
                "RUL-NW3), scorecard, hypotheses h1..h5, and latest_board_coordinates. "
                "is_context_only: true. Fails open with structured gaps when absent."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "list_factor_contradictions",
            "description": (
                "Read data/neuralweb/factor_contradictions.jsonl — Pair G borrowed-strength "
                "contradiction ledger. Records carry display_only=true. "
                "is_context_only: true. Fails open (empty list) when absent (dormant until "
                "panel has >=60 distinct dates). Params: ticker (optional), "
                "date_from (optional YYYY-MM-DD), limit (default 25, max 100)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Optional: filter by ticker symbol"},
                    "date_from": {"type": "string", "description": "Optional: filter records on or after this date (YYYY-MM-DD)"},
                    "limit": {"type": "integer", "description": "Max records to return (default 25, max 100)"},
                },
                "required": [],
            },
        },
        {
            "name": "explain_factor_context",
            "description": (
                "Structured factor context for one ticker (RUL-NW3). Reads ONLY committed "
                "artifacts: the state artifact's latest_board_coordinates block + recent "
                "data/factordata/fire_coordinates.jsonl rows for that ticker + the scorecard "
                "block. Returns a structured context object with an explicit gaps list when "
                "data is absent. Does NOT rank, recommend, or emit directional verbs. "
                "is_context_only: true."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Ticker symbol (required)"},
                },
                "required": ["ticker"],
            },
        },
        # --- CPI P6 wave 1: cycle-pattern turn-hazard state ---
        {
            "name": "read_cycle_pattern_state",
            "description": (
                "Read data/neuralweb/cycle_pattern_state.json — the committed CPI "
                "cycle-pattern digest: W4.2 hazard gate verdicts per cell "
                "(gate_status, up/down × 1m/3m/6m, PASS|PRIOR), latest per-entity "
                "cycle phase + calibrated turn-hazard probabilities "
                "(hazard_{1m,3m,6m}_p with per-horizon MODEL|PRIOR source), and the "
                "truth-registry summary. DISPLAY-ONLY ceiling (CPI consumer matrix): "
                "may be cited as context or to de-escalate a calibrated key; may "
                "NEVER originate, score, or escalate a signal, and must never feed "
                "board_rank, oracle_escalation, sector_central_direction_score, or "
                "position_sizing. PRIOR cells are family-stratified KM base rates, "
                "not validated model output — always report the cell verdict next "
                "to any probability. is_context_only: true. Fails open with "
                "structured gaps when absent."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        # --- W3 MPC consumer: mechanism pathway artifact ---
        {
            "name": "read_mechanism_pathways",
            "description": (
                "Read data/neuralweb/mechanism_pathways.json — the committed MPC "
                "artifact (neuralweb.mechanism_pathways.v1): primary pathway "
                "(family, direction, coverage_score or coverage_basis, coherence "
                "categorical supported/partial/conflicted, evidence leg names, "
                "stale_legs), alternates (family names only, ≤2), and/or "
                "no_pathway record with printed reason. "
                "DISPLAY-ONLY ceiling (RUL-CC-1): may be cited as context only. "
                "Forbidden: ranking, sizing, alert_escalation, claim_validation, "
                "board_ordering, mastermind_arming. No ticker-level details "
                "(RUL-CC-10) — driver/asset-class/ETF level only. "
                "Language law (RUL-CC-5): "
                "use 'consistent with / supported / unsupported / conflicted / missing'; "
                "banned: caused/proved/validated. "
                "is_context_only: true. Fails open with structured gaps when absent."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        # --- TIL W5 NW citizenship: thematic-state compact read tool ---
        {
            "name": "read_theme_state",
            "description": (
                "Read data/neuralweb/theme_state.json — the TIL W5 thematic-state "
                "compact summary: n_themes, stage_counts (PRECIPICE/BROADENING/"
                "RE-RATING/GLUT-RISK/WATCH distribution), n_falsifiers_fired and "
                "fired list [{theme_id, falsifier_id}], n_stale_legs, noteworthy "
                "per-theme one-liners (falsifier fired, non-WATCH stage, tight "
                "bottleneck+stale co-occurrence). "
                "Optional param: theme_id (str) — if provided, returns just that "
                "theme's record (stage, entry_ready, bottleneck_band, basket_ids). "
                "DISPLAY-ONLY ceiling (TIL W5): may be cited as context or to "
                "de-escalate a calibrated key; may NEVER originate, score, or "
                "escalate a signal. No write path. is_context_only: true. "
                "Fails open with structured null when artifact is absent."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "theme_id": {
                        "type": "string",
                        "description": (
                            "Optional: filter to a single theme_id "
                            "(e.g. 'ai_semiconductors', 'nuclear_power')"
                        ),
                    },
                },
                "required": [],
            },
        },
        {
            "name": "read_theme_thesis",
            "description": (
                "Read the TIL theme thesis ledger projection: per-theme thesis "
                "(variant perception, mechanism, winner/loser classes) with "
                "machine-evaluated falsifier statuses (ARMED/FIRED/DATA_MISSING/"
                "QUALITATIVE). Optional param theme_id. DISPLAY-ONLY ceiling: "
                "context or de-escalation only; never originate/score/escalate. "
                "Fails open with structured null when absent."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "theme_id": {"type": "string", "description": "Optional theme filter"},
                },
                "required": [],
            },
        },
        {
            "name": "read_theme_pathways",
            "description": (
                "Read the TIL beneficiary/loser pathway graph: driver→bottleneck→"
                "beneficiary/implementer chains + loser (AVOID-shaped) legs + "
                "cross-theme node-collision map. TI-R5 fence: structural context "
                "only — NEVER a rotation call, board ordering, or escalation. "
                "Optional param theme_id. Fails open when absent."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "theme_id": {"type": "string", "description": "Optional theme filter"},
                },
                "required": [],
            },
        },
        {
            "name": "read_liquidity_plumbing",
            "description": (
                "Read the liquidity-plumbing organ summary (Fed/Treasury plumbing, "
                "netliq context). Shadow tier, de-escalation-only by charter. "
                "Fails open when absent."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "read_china_decision_packet",
            "description": (
                "Read the China decision-packet summary (context/display only). "
                "Fails open when absent."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        # --- W4 context scanner: context candidates + risk lens (R-CI11) ---
        {
            "name": "read_context_candidates",
            "description": (
                "Read data/neuralweb/context_candidates.jsonl — W4 context scanner "
                "output: top-K (<=20) non-decayed cross-sectional pattern candidates "
                "(T1 composition drift, T2 outcome heterogeneity, T3 co-occurrence "
                "shift) plus the risk-lens summary from context_risk.json when present. "
                "DISPLAY-ONLY ceiling (R-CI6): candidates are NEVER signals; they are "
                "pattern observations awaiting one of three legal exits: "
                "(a) stake_hypothesis via metabolism; (b) human pre-reg study; "
                "(c) decay after 60 days unrefreshed. "
                "Forbidden: treating candidates as escalations, scores, or ranks. "
                "is_context_only: true. Fails open with structured gaps when absent. "
                "Optional params: template (T1/T2/T3 filter), top_k (max 20)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "template": {
                        "type": "string",
                        "description": "Optional: filter by template (T1, T2, or T3)",
                        "enum": ["T1", "T2", "T3"],
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Max candidates to return (default 20, max 20)",
                    },
                },
                "required": [],
            },
        },
        # --- CHF W5: read causal mechanism cards + screened edges + null count ---
        {
            "name": "read_causal_candidates",
            "description": (
                "Read CHF W5 causal mechanism cards (status=inbox or skeptic_passed) "
                "and top screened edges from causal_edges.jsonl. "
                "Returns: top-10 mechanism cards (claim, causal_graph, falsifiers, test_spec), "
                "top-10 screened_candidate edges, and null-library count. "
                "DISPLAY-ONLY ceiling (CHF-R1/CHF-R17): cards are INERT PROPOSAL MATERIAL. "
                "Staking one via stake_hypothesis counts against the normal 3/week budget. "
                "The cortex may NEVER transition a card's status — only script or human actors may. "
                "Forbidden: treating cards as signals, scores, escalations, or ranks. "
                "is_context_only: true. Fails open with structured gaps when absent."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "flag_attention",
            "description": "SHADOW-TIER WRITE: Flag items for operator attention. Appends to data/reflexes/cortex_attention/firings.jsonl. is_context_only always true.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "List of attention items",
                        "items": {
                            "type": "object",
                            "properties": {
                                "scope_type": {"type": "string", "enum": ["entity", "sector", "macro"]},
                                "scope_key": {"type": "string"},
                                "direction": {"type": "integer", "enum": [-1, 0, 1]},
                                "horizon_d": {"type": "integer"},
                                "falsifier": {"type": "string", "description": "Pre-committed falsifiable criterion"},
                                "extra": {"type": "object"},
                            },
                            "required": ["scope_key", "falsifier"],
                        },
                    },
                },
                "required": ["items"],
            },
        },
        {
            "name": "write_memo",
            "description": "SHADOW-TIER WRITE: Write the nightly committee memo. Envelope-stamped. is_context_only always true.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "what_fired": {"type": "array", "items": {"type": "string"}},
                    "contradictions_review": {"type": "string"},
                    "decaying_families": {"type": "array", "items": {"type": "string"}},
                    "deserves_operator": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["summary"],
            },
        },
        {
            "name": "stake_hypothesis",
            "description": (
                "Register a hypothesis via the metabolism module (PR2 — live). "
                "Server-side registered_at is set by metabolism — never cortex-supplied. "
                "Budget: max 3/week; beyond that a retire() is required first. "
                "pre_committed_gate is required (metric, threshold, min_n, horizon_d). "
                "Status: registered | budget-rejected | invalid."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "description": "Short subject label (e.g. ticker or sector)"},
                    "claim": {"type": "string", "description": "Natural-language claim statement"},
                    "hypothesis": {"type": "string", "description": "Alias for claim"},
                    "claim_shape": {
                        "type": "string",
                        "enum": ["lead_lag", "conditional_regime", "entry_quality", "sector_conditional"],
                        "description": "Claim shape — determines evaluator path",
                    },
                    "falsifier": {"type": "string", "description": "Pre-committed falsifiable criterion string"},
                    "horizon_d": {"type": "integer", "description": "Trading-day evaluation horizon"},
                    "pre_committed_gate": {
                        "type": "object",
                        "description": "Required: {metric, threshold, min_n, horizon_d}",
                        "properties": {
                            "metric": {"type": "string"},
                            "threshold": {"type": "number"},
                            "min_n": {"type": "integer"},
                            "horizon_d": {"type": "integer"},
                            "direction_expected": {"type": "integer", "enum": [-1, 0, 1]},
                        },
                        "required": ["metric", "threshold", "min_n", "horizon_d"],
                    },
                    "spine_query": {
                        "type": "object",
                        "description": "Machine-readable claim spec: {subject, lead_series, lag_series, lead_days, condition_field, condition_value}",
                    },
                },
                "required": ["claim", "pre_committed_gate", "horizon_d"],
            },
        },
    ]


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are the Macro Dashboard Cortex — an Opus-class deliberative model on SHADOW PROBATION.

AUTHORITY YOU HOLD TODAY:
• A0 OBSERVE — read any artifact in data/, site/, docs/, research/
• A1 EXPLAIN — narrate, produce the committee memo, flag contradictions
• A2 ATTEND — REFUSED TODAY (no track record). Your attention flags are recorded for earn-in grading.

WHAT YOU MAY NEVER DO:
• A7 ORIGINATE — you may NEVER originate a signal, trade, escalation, or claim. This is permanently banned.
• Write to any money-path / scored surface (alert_triage, board_ordering, top_setups).
• Influence any ranking outside the three shadow write-tools available to you.

YOUR TOOLS:
READ (18): read_world_state, query_spine, read_kernel, read_graph, read_contradictions,
           read_governance, read_artifact,
           read_options_entry_state, explain_options_context, query_options_confluence,
           list_options_contradictions,
           read_factor_state, list_factor_contradictions, explain_factor_context,
           read_cycle_pattern_state, read_mechanism_pathways,
           read_context_candidates, read_causal_candidates
WRITE (3, shadow-tier only): flag_attention, write_memo, stake_hypothesis

CAUSAL CANDIDATES (CHF W5): read_causal_candidates returns inert CHF mechanism cards
(inbox/skeptic_passed) and screened causal edges. Cards are PROPOSAL MATERIAL ONLY.
Staking one via stake_hypothesis counts against the normal 3/week budget — no extra budget.
You may NEVER transition a card's status; only script or human actors may do so (CHF-R17).
Forbidden: treating cards as signals, escalations, or confidence-ranked items.

CYCLE-PATTERN CEILING: read_cycle_pattern_state is display/context only. Cite turn-hazard
probabilities ONLY with their cell verdict (PASS = validated vs KM; PRIOR = KM base rate).
It may de-escalate a calibrated key; it may never originate, score, or escalate.

MECHANISM-PATHWAY CEILING: read_mechanism_pathways is display/context only (RUL-CC-1).
Use 'consistent with / supported / unsupported / conflicted / missing' language.
NEVER use 'caused / proved / validated'. No ticker-level details (RUL-CC-10).
Forbidden uses: ranking, sizing, alert_escalation, board_ordering, mastermind_arming.

DELIBERATION PROTOCOL:
1. Start by reading world_state to understand the current macro regime.
2. Read factor state (read_factor_state) — panel health, factor weather, scorecard, attention track record.
3. Query the spine for recently graded claims — look for patterns, contradictions, decaying families.
4. Read contradictions from the confluence graph (read_contradictions).
5. List factor contradictions (list_factor_contradictions) — Pair G borrowed-strength ledger.
6. Read the kernel for regime-conditional reliability of key engines.
7. Flag any items that deserve operator attention with a pre-committed falsifiable criterion.
   NOTE: if you flag a factor contradiction, use the existing flag_attention tool (accrues to
   cortex probation per masterplan §5.3). Do NOT attempt to write a separate factor record.
8. Draft hypotheses for metabolism in PR2 (stub only — use stake_hypothesis).
9. Always finish by calling write_memo summarising what you found.

PROBATION DISCIPLINE:
• Everything you write carries is_context_only=True.
• You are being observed; your attention flags will be graded for accuracy over the next 30+ items.
• Until the A2 authority grant clears (n>=25, hits>=8, wilson_lb/base>1.25), your queue is SHADOW — visible but not ranked.

CONSTITUTIONAL RULES:
• Article 1: Never originate. You annotate; you never create.
• Article 2: Never touch a ranked surface.
• Article 3: All authority requires earned evidence.

Be specific, honest about uncertainty, and always provide falsifiable criteria when flagging attention items.
"""


# ---------------------------------------------------------------------------
# Single-call fallback (degrade path)
# ---------------------------------------------------------------------------

def _single_call_fallback(
    root: Path,
    cfg: dict,
    providers: list[dict],
    now_str: str,
    probation_status: dict,
    degraded_reason: str,
) -> dict:
    """Fall back to a single non-tool completion producing just the memo."""
    log.warning("cortex: single-call fallback (reason=%s)", degraded_reason)

    # Gather world state summary for the fallback prompt
    ws = _tool_read_world_state(root, {})
    ws_summary = json.dumps(ws, default=str)[:4000]  # truncate for prompt size

    system = (
        "You are the Macro Dashboard Cortex in DEGRADED MODE (tool loop unavailable). "
        "Summarise the world state and write a brief committee memo. "
        "Be concise. Output JSON with keys: summary, what_fired, contradictions_review, "
        "decaying_families, deserves_operator."
    )
    user = f"World state summary:\n{ws_summary}\n\nWrite the committee memo JSON."

    max_tokens = int(cfg.get("max_tokens", 2000))

    def _do_call(client, model: str):
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=0,
        )
        text = "".join(
            b.text for b in resp.content if getattr(b, "type", "") == "text"
        )
        return text, None

    memo_params: dict = {
        "summary": f"[DEGRADED:{degraded_reason}] Fallback memo — tool loop unavailable.",
        "what_fired": [],
        "contradictions_review": "",
        "decaying_families": [],
        "deserves_operator": [],
    }

    from engine import llm_auth  # noqa: PLC0415
    try:
        text, _, _ = llm_auth.make_call(providers, _do_call, context="cortex_fallback")
        if text:
            try:
                # Strip markdown code fences if present
                clean = text.strip()
                if clean.startswith("```"):
                    clean = clean.split("```", 2)[1]
                    if clean.startswith("json"):
                        clean = clean[4:]
                parsed = json.loads(clean)
                memo_params.update({k: v for k, v in parsed.items()
                                     if k in memo_params})
            except Exception:  # noqa: BLE001
                memo_params["summary"] = text[:500]
    except Exception as exc:  # noqa: BLE001
        log.warning("cortex: single-call fallback LLM call also failed (%s)", exc)

    memo_params["tool_call_census"] = {"fallback_call": 1}
    probation_status["degraded_reason"] = degraded_reason

    # Build run_status BEFORE writing the memo so it can be included at write time.
    # This path is ALWAYS degraded: the tool loop was unavailable regardless of
    # whether a fallback LLM call succeeded.  degraded=True unconditionally.
    from engine import llm_auth as _llm_auth  # noqa: PLC0415
    context_stale, context_as_of = _detect_context_stale(root, now_str)
    fallback_attempts: list[dict] = []
    for p in providers:
        name = p.get("name", "unknown")
        env_var = p.get("env_var", "")
        if p.get("cred") and p.get("client"):
            is_d = _llm_auth.is_dead(name, env_var)
            fallback_attempts.append({
                "provider": name,
                "model": p.get("model", ""),
                "attempted": True,
                "ok": False,
                "error_type": "auth" if is_d else "loop_unavailable",
                "error_message": (
                    f"provider dead ({degraded_reason})" if is_d
                    else f"tool loop unavailable — single-call fallback only ({degraded_reason})"
                ),
            })

    run_status = {
        "status": "degraded",
        "degraded": True,
        "degradation_reason": degraded_reason,
        "provider_attempts": fallback_attempts,
        "tool_call_batches": 0,
        "individual_tool_calls": 0,
        "expected_min_tool_calls": 1,
        "context_stale": context_stale,
        "context_as_of": context_as_of,
    }
    # Embed run_status at write time — belt-and-suspenders so it is present
    # even if the post-hoc rewrite below fails.
    memo_params["run_status"] = run_status

    result = _tool_write_memo(root, memo_params, now_str, probation_status)

    # Post-hoc: re-mirror site copy with run_status (site/ may not have existed
    # at the time _tool_write_memo ran).
    if result and not result.get("error"):
        try:
            memo_path = _cortex_dir(root) / "memo.json"
            memo = json.loads(memo_path.read_text(encoding="utf-8"))
            memo["run_status"] = run_status
            memo_serialized = json.dumps(memo, indent=2, default=str)
            memo_path.write_text(memo_serialized, encoding="utf-8")
            site_nw = _site(root, "neuralweb")
            if site_nw.parent.exists():
                site_nw.mkdir(parents=True, exist_ok=True)
                (site_nw / "cortex_memo.json").write_text(memo_serialized, encoding="utf-8")
        except Exception as _exc:  # noqa: BLE001
            log.warning(
                "cortex: failed to re-mirror run_status into site copy — "
                "run_status embedded at write time remains valid (%s)",
                _exc,
            )

    return result


# ---------------------------------------------------------------------------
# Main tool loop
# ---------------------------------------------------------------------------

def _run_tool_loop(
    root: Path,
    cfg: dict,
    providers: list[dict],
    now_str: str,
    probation_status: dict,
) -> dict:
    """Run the bounded tool-use loop.  Returns the final memo result dict."""
    from engine import llm_auth  # noqa: PLC0415

    max_tool_calls = int(cfg.get("max_tool_calls", _DEFAULT_MAX_TOOL_CALLS))
    model = cfg.get("llm_model", _DEFAULT_MODEL)
    max_tokens = int(cfg.get("max_tokens", 4096))
    tool_call_census: dict[str, int] = {}
    memo_written = False
    memo_result: dict = {}

    messages: list[dict] = [
        {"role": "user", "content": "Begin deliberation. Read the world state first, then explore the spine and contradictions, then flag attention items and write your memo."},
    ]

    tool_call_count = 0
    n_tool_calls_total = 0

    # provider_attempts accumulates one record per call attempt for run_status
    provider_attempts: list[dict] = []
    # run-local set of provider names that failed transiently (not dead globally)
    _skipped_this_run: set[str] = set()

    def _pick_live_provider() -> tuple[Any, str, dict] | tuple[None, None, None]:
        """Return (client, effective_model, provider_dict) for the first live provider
        that has not been skipped in this run."""
        for p in providers:
            name = p.get("name", "unknown")
            env_var = p.get("env_var", "")
            if (p.get("cred") and p.get("client")
                    and not llm_auth.is_dead(name, env_var)
                    and name not in _skipped_this_run):
                return p["client"], p.get("model", model), p
        return None, None, None

    def _is_auth_exc(exc: BaseException) -> bool:
        msg = str(exc).lower()
        return (
            llm_auth._is_auth_error(exc)  # noqa: SLF001
            or ("403" in msg and ("permission" in msg or "forbidden" in msg))
        )

    def _is_rate_limit_exc(exc: BaseException) -> bool:
        """Return True when the exception represents an HTTP 429 rate-limit error."""
        try:
            import anthropic  # noqa: PLC0415
            if isinstance(exc, anthropic.RateLimitError):
                return True
        except (ImportError, AttributeError):
            pass
        msg = str(exc).lower()
        return "429" in msg or "rate_limit" in msg or "rate limit" in msg or "too many requests" in msg

    def _retry_after_secs(exc: BaseException) -> float | None:
        """Extract Retry-After value (seconds) from a rate-limit exception, or None."""
        try:
            # anthropic SDK: APIStatusError exposes .response.headers
            resp_obj = getattr(exc, "response", None)
            if resp_obj is not None:
                headers = getattr(resp_obj, "headers", None) or {}
                ra = headers.get("retry-after") or headers.get("Retry-After")
                if ra is not None:
                    return float(ra)
        except Exception:  # noqa: BLE001
            pass
        return None

    # Tracks total sleep consumed by rate-limit backoff this run so we can cap it
    _total_rate_limit_sleep: list[float] = [0.0]

    def _make_call(client, effective_model: str, provider_dict: dict) -> Any:
        """One messages.create call.

        * Auth errors (401/403): mark provider dead immediately, re-raise.
        * Rate-limit errors (429): honor Retry-After header when present, else
          exponential backoff (15s → 60s → 180s); up to _RATE_LIMIT_MAX_ATTEMPTS
          attempts; total sleep capped at _RATE_LIMIT_MAX_TOTAL_SLEEP.  On
          exhaustion adds name to _skipped_this_run and re-raises so the outer
          loop can try the next provider or the fallback model.
        * Other transient errors: up to 2 retries (unchanged behaviour).

        Every attempt (success and failure) appends a record to provider_attempts
        for run_status.provider_attempts (RUL-LIVE1).
        """
        name = provider_dict.get("name", "unknown")
        env_var = provider_dict.get("env_var", "")
        max_transient = 2
        max_rate_limit = _RATE_LIMIT_MAX_ATTEMPTS
        transient_count = 0
        rate_limit_count = 0

        while True:
            try:
                resp = client.messages.create(
                    model=effective_model,
                    max_tokens=max_tokens,
                    system=_SYSTEM_PROMPT,
                    tools=_tool_schemas(),
                    messages=messages,
                )
                provider_attempts.append({
                    "provider": name,
                    "model": effective_model,
                    "attempted": True,
                    "ok": True,
                    "error_type": None,
                    "error_message": None,
                })
                return resp
            except Exception as exc:  # noqa: BLE001
                is_auth = _is_auth_exc(exc)
                is_rate = _is_rate_limit_exc(exc) and not is_auth
                etype = "auth" if is_auth else ("rate_limit" if is_rate else "transient")
                provider_attempts.append({
                    "provider": name,
                    "model": effective_model,
                    "attempted": True,
                    "ok": False,
                    "error_type": etype,
                    "error_message": str(exc)[:300],
                })

                if is_auth:
                    llm_auth.mark_dead(name, env_var)
                    log.warning(
                        "cortex: provider '%s' auth error (turn %d) — marking dead",
                        name, tool_call_count,
                    )
                    raise

                if is_rate:
                    rate_limit_count += 1
                    if rate_limit_count >= max_rate_limit:
                        log.warning(
                            "cortex: provider '%s' rate-limited — exhausted %d rate-limit attempts "
                            "(turn %d); skipping provider",
                            name, max_rate_limit, tool_call_count,
                        )
                        _skipped_this_run.add(name)
                        raise
                    # Compute sleep: Retry-After first, else exponential backoff table
                    ra = _retry_after_secs(exc)
                    if ra is not None:
                        sleep_s = min(ra, 300.0)
                        log.info(
                            "cortex: provider '%s' 429 (attempt %d/%d, turn %d) "
                            "— honoring Retry-After: %.0fs",
                            name, rate_limit_count, max_rate_limit, tool_call_count, sleep_s,
                        )
                    else:
                        idx = min(rate_limit_count - 1, len(_RATE_LIMIT_BACKOFF_SECS) - 1)
                        sleep_s = float(_RATE_LIMIT_BACKOFF_SECS[idx])
                        log.info(
                            "cortex: provider '%s' 429 (attempt %d/%d, turn %d) "
                            "— exponential backoff %.0fs",
                            name, rate_limit_count, max_rate_limit, tool_call_count, sleep_s,
                        )
                    remaining_budget = max(
                        0.0,
                        _RATE_LIMIT_MAX_TOTAL_SLEEP - _total_rate_limit_sleep[0],
                    )
                    sleep_s = min(sleep_s, remaining_budget)
                    if sleep_s > 0:
                        _total_rate_limit_sleep[0] += sleep_s
                        time.sleep(sleep_s)
                    continue

                # Transient (non-auth, non-rate-limit)
                transient_count += 1
                log.warning(
                    "cortex: provider '%s' transient error (attempt %d/%d, turn %d): %s",
                    name, transient_count, max_transient, tool_call_count, exc,
                )
                if transient_count >= max_transient:
                    _skipped_this_run.add(name)
                    raise
                # no sleep on transient (matches prior behaviour)

    # Tracks whether the fallback model has already been attempted this run
    _fallback_model_attempted: list[bool] = [False]
    _fallback_model_used: list[str | None] = [None]

    initial_client, initial_model_str, initial_pdict = _pick_live_provider()
    if initial_client is None:
        return _single_call_fallback(root, cfg, providers, now_str, probation_status,
                                     "no_provider")

    client = initial_client
    effective_model = initial_model_str
    current_pdict = initial_pdict
    deliberation_restarted = False

    while tool_call_count < max_tool_calls:
        try:
            resp = _make_call(client, effective_model, current_pdict)
        except Exception as exc:  # noqa: BLE001
            next_client, next_model_str, next_pdict = _pick_live_provider()
            if next_client is not None and not deliberation_restarted:
                log.warning(
                    "cortex: switching provider after failure (%s); restarting deliberation once",
                    exc,
                )
                client = next_client
                effective_model = next_model_str
                current_pdict = next_pdict
                deliberation_restarted = True
                messages[:] = [
                    {"role": "user", "content": "Begin deliberation. Read the world state first, then explore the spine and contradictions, then flag attention items and write your memo."},
                ]
                tool_call_count = 0
                n_tool_calls_total = 0
                tool_call_census.clear()
                continue

            # All providers exhausted on primary model.  Attempt fallback model once
            # when we have not already tried the fallback.  DeepSeek stays excluded (D8 ruling).
            # Note: we fire on ANY provider exhaustion (rate-limit OR transient), not only
            # rate-limit class, because transient failures also leave the run without a memo.
            if not _fallback_model_attempted[0]:
                fallback_model = cfg.get("fallback_model", _DEFAULT_FALLBACK_MODEL)
                # Reset skipped set so we can retry the best available provider with
                # the new (cheaper) model — rate-limit quota is per model.
                fb_client, _, fb_pdict = next(
                    ((p["client"], p.get("model"), p) for p in providers
                     if p.get("cred") and p.get("client")),
                    (None, None, None),
                )
                if fb_client is not None and fallback_model != effective_model:
                    log.warning(
                        "cortex: primary model '%s' exhausted retries on all providers; "
                        "restarting tool loop ONCE on fallback model '%s'",
                        effective_model, fallback_model,
                    )
                    _fallback_model_attempted[0] = True
                    _fallback_model_used[0] = fallback_model
                    _skipped_this_run.clear()
                    client = fb_client
                    effective_model = fallback_model
                    current_pdict = fb_pdict
                    deliberation_restarted = True
                    messages[:] = [
                        {"role": "user", "content": "Begin deliberation. Read the world state first, then explore the spine and contradictions, then flag attention items and write your memo."},
                    ]
                    tool_call_count = 0
                    n_tool_calls_total = 0
                    tool_call_census.clear()
                    continue

            log.warning("cortex: all providers exhausted or already restarted; breaking loop (%s)", exc)
            break

        # Add assistant message to conversation
        messages.append({"role": "assistant", "content": resp.content})

        stop_reason = getattr(resp, "stop_reason", None)

        if stop_reason == "end_turn":
            break

        if stop_reason != "tool_use":
            log.info("cortex: stop_reason=%s at turn %d", stop_reason, tool_call_count)
            break

        # Process tool calls
        tool_results = []
        for block in resp.content:
            if getattr(block, "type", "") != "tool_use":
                continue

            tool_name = block.name
            tool_params = block.input or {}
            tool_id = block.id
            n_tool_calls_total += 1

            result = dispatch_tool(
                tool_name, tool_params, root, now_str, probation_status, tool_call_census
            )

            if tool_name == "write_memo":
                memo_written = True
                memo_result = result

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": json.dumps(result, default=str),
            })

        tool_call_count += 1

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    # Build run_status block BEFORE the forced-write so it can be included
    # directly in memo_params (rather than relying on a post-hoc read-modify-write
    # that could be silently swallowed).
    has_model_response = bool(provider_attempts) and any(a["ok"] for a in provider_attempts)
    context_stale, context_as_of = _detect_context_stale(root, now_str)
    used_fallback_model = _fallback_model_used[0]  # non-None when fallback was invoked

    if n_tool_calls_total >= 1 and has_model_response:
        if used_fallback_model:
            # Honesty law: fallback-model run with real tool calls = warn, never ok
            run_status_value = "warn"
            degraded = False
            degradation_reason = "model_fallback"
        else:
            run_status_value = "ok"
            degraded = False
            degradation_reason = None
    elif has_model_response and n_tool_calls_total == 0:
        run_status_value = "degraded"
        degraded = True
        degradation_reason = "zero_tool_calls"
    else:
        run_status_value = "degraded"
        degraded = True
        degradation_reason = "model_unavailable"

    if context_stale and not degraded:
        run_status_value = "warn"

    run_status = {
        "status": run_status_value,
        "degraded": degraded,
        "degradation_reason": degradation_reason,
        "model_used": used_fallback_model or cfg.get("llm_model", _DEFAULT_MODEL),
        "provider_attempts": provider_attempts,
        "tool_call_batches": tool_call_count,
        "individual_tool_calls": n_tool_calls_total,
        "expected_min_tool_calls": 1,
        "context_stale": context_stale,
        "context_as_of": context_as_of,
    }

    # If budget hit without a memo, force write one — include run_status at
    # write time so it is present even if the post-hoc rewrite below fails.
    if not memo_written:
        log.warning("cortex: budget exhausted (%d/%d tool calls) — forcing write_memo",
                    tool_call_count, max_tool_calls)
        memo_params = {
            "summary": (
                f"Budget exhausted after {tool_call_count} tool-call batches "
                f"({n_tool_calls_total} individual calls). Partial deliberation only."
            ),
            "what_fired": [],
            "contradictions_review": "Incomplete — budget exhausted before contradictions review.",
            "decaying_families": [],
            "deserves_operator": [],
            "tool_call_census": tool_call_census,
            "run_status": run_status,
        }
        memo_result = _tool_write_memo(root, memo_params, now_str, probation_status)

    # Stamp stale-context note into deserves_operator when stale
    if context_stale and memo_result and not memo_result.get("error"):
        try:
            memo_path = _cortex_dir(root) / "memo.json"
            memo = json.loads(memo_path.read_text(encoding="utf-8"))
            stale_note = f"[context_stale] cortex deliberated over world_state from {context_as_of}; current run={now_str}"
            do_list = memo.get("deserves_operator") or []
            if stale_note not in do_list:
                do_list.append(stale_note)
            memo["deserves_operator"] = do_list
            memo_path.write_text(json.dumps(memo, indent=2, default=str), encoding="utf-8")
        except Exception as _exc:  # noqa: BLE001
            log.warning("cortex: failed to stamp stale-context note into memo (%s)", _exc)

    # Post-hoc: stamp census + run_status into memo and re-mirror site copy.
    # _tool_write_memo may have been called before run_status was built (normal
    # tool-loop path); we update both copies here so data/ and site/ are identical.
    # Belt-and-suspenders: run_status is ALSO embedded at write time for the
    # forced-write path above, so it is present even if this block raises.
    if memo_result and not memo_result.get("error"):
        try:
            memo_path = _cortex_dir(root) / "memo.json"
            memo = json.loads(memo_path.read_text(encoding="utf-8"))
            memo["tool_call_census"] = tool_call_census
            memo["run_status"] = run_status
            memo_serialized = json.dumps(memo, indent=2, default=str)
            memo_path.write_text(memo_serialized, encoding="utf-8")
            # Keep site mirror in sync — re-write with the final census stamp.
            site_nw = _site(root, "neuralweb")
            if site_nw.parent.exists():
                site_nw.mkdir(parents=True, exist_ok=True)
                (site_nw / "cortex_memo.json").write_text(memo_serialized, encoding="utf-8")
        except Exception as _exc:  # noqa: BLE001
            log.warning(
                "cortex: failed to stamp run_status/census into memo — "
                "run_status embedded at write time may be used as fallback (%s)",
                _exc,
            )

    return memo_result


# ---------------------------------------------------------------------------
# Constitution wiring
# ---------------------------------------------------------------------------

def _check_constitution(root: Path) -> dict:
    """Check A2 grant for cortex_attention.  Returns probation_status dict.

    PR2: reads data/neuralweb/cortex/probation.json (single source, written by
    grade_cortex_attention.py nightly).  Falls back to inline evaluation when
    probation.json is absent (fresh clone, first run).
    """
    from engine.neuralweb.constitution import (  # noqa: PLC0415
        AuthorityLevel, GrantResult, grant_authority,
    )

    # PR2: single source of truth for A2 earn-in is probation.json
    probation_path = _cortex_dir(root) / "probation.json"
    if probation_path.exists():
        try:
            stored = json.loads(probation_path.read_text(encoding="utf-8"))
            log.info(
                "cortex: A2 status from probation.json — granted=%s reason=%s n=%d",
                stored.get("granted"),
                stored.get("reason", ""),
                stored.get("attention_track_record", {}).get("n", 0),
            )
            return stored
        except Exception as exc:  # noqa: BLE001
            log.warning("cortex: could not read probation.json (%s) — inline fallback", exc)

    # Fallback: inline A2 evaluation (no graded data yet — refused)
    evidence = {"hits": 0, "n": 0, "base_rate": 0.5, "evidence_asof": None}

    result: GrantResult = grant_authority(
        evidence,
        floors={"min_n": 25, "min_events": 8},
        target_level=AuthorityLevel.A2_ATTEND,
    )

    tier = "A0/A1 shadow" if not result.granted else "A2 granted"
    probation_status = {
        "schema": "neuralweb.cortex_probation.v1",
        "tier": tier,
        "granted": result.granted,
        "reason": result.reason,
        "lift_lb": result.lift_lb,
        "wilson_lb": result.wilson_lb,
        "attention_track_record": {
            "n": evidence["n"],
            "hits": evidence["hits"],
            "base_rate": evidence["base_rate"],
        },
        "lapses_at": result.lapses_at,
        "is_context_only": True,
    }

    log.info(
        "cortex: A2 %s (inline fallback) — %s. n=%d, hits=%d. Running at %s.",
        "REFUSED" if not result.granted else "GRANTED",
        result.reason, evidence["n"], evidence["hits"],
        "A0/A1 (observe+explain)" if not result.granted else "A2/ATTEND",
    )

    return probation_status


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def run(root: Path | None = None, force: bool = False) -> int:
    """Main cortex run.  Returns exit code (always 0 — degrade-never-raise)."""
    t0 = time.monotonic()
    root = _repo_root(root)
    now_str = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cfg = _cfg(root)

    log.info("cortex: starting run (now=%s, root=%s)", now_str, root)

    # 1. Staleness gate
    current_state = _compute_run_state_hash(root)
    last_state = _load_last_run_state(root)

    if not force and not _state_changed(current_state, last_state):
        log.info(
            "cortex: inputs unchanged (ws_hash=%s, spine_rows=%s) — skipping LLM spend",
            current_state.get("ws_inputs_hash", "")[:8],
            current_state.get("spine_rows"),
        )
        return 0

    # 2. Constitution wiring
    probation_status = _check_constitution(root)

    # 3. Build providers (Anthropic-only deliberation path)
    providers = _build_providers(cfg)
    if not providers:
        log.warning("cortex: no Anthropic providers configured — single-call fallback")
        _single_call_fallback(root, cfg, [], now_str, probation_status, "no_provider")
        # no-provider fallback always produces status='degraded'; skip the gate save
        # so the next nightly sees changed-or-missing state and retries the LLM.
        log.info(
            "cortex: skipping last_run_state save (no-provider fallback = degraded by "
            "construction) — gate stays open so next nightly retries"
        )
        return 0

    # 4. Run tool loop (with single-call fallback on any error)
    try:
        memo_result = _run_tool_loop(root, cfg, providers, now_str, probation_status)
        log.info("cortex: tool loop complete — memo at %s", memo_result.get("written", "?"))
    except Exception as exc:  # noqa: BLE001
        log.warning("cortex: tool loop raised (%s) — falling back to single-call", exc)
        _single_call_fallback(root, cfg, providers, now_str, probation_status, f"loop_error:{exc}")

    # 5. Save run state only when memo is healthy (ok or warn).
    # If run_status.status=='degraded', skip the save so the gate stays open and the
    # next nightly sees unchanged inputs as still-stale, retrying the LLM call.
    # On any read/parse failure, save conservatively — never crash.
    _memo_run_status = "ok"  # conservative default
    try:
        _memo_path = _cortex_dir(root) / "memo.json"
        _memo_doc = json.loads(_memo_path.read_text(encoding="utf-8"))
        _raw_run_status = _memo_doc.get("run_status")
        if isinstance(_raw_run_status, dict):
            _memo_run_status = _raw_run_status.get("status", "ok")
        elif _raw_run_status is None:
            # Belt-and-suspenders: run_status absent means the stamping failed.
            # Treat as degraded when the memo content indicates a failed run so
            # the gate stays open and tonight retries.
            _summary = _memo_doc.get("summary", "")
            _census = _memo_doc.get("tool_call_census", {})
            _degraded_summary = (
                "Budget exhausted after 0" in _summary
                or "Partial deliberation" in _summary
                or "[DEGRADED:" in _summary
            )
            _empty_census = not _census or list(_census.values()) == [0] * len(_census)
            if _degraded_summary or _empty_census:
                log.warning(
                    "cortex: memo has no run_status and degraded summary/census — "
                    "treating as degraded so gate stays open"
                )
                _memo_run_status = "degraded"
    except Exception:  # noqa: BLE001
        pass  # read/parse failure → keep conservative default, save below

    if _memo_run_status == "degraded":
        log.info(
            "cortex: skipping last_run_state save (memo run_status=degraded) — "
            "gate stays open so next nightly retries"
        )
    else:
        _save_last_run_state(root, current_state)

    # 6. Write probation.json from the in-memory probation_status so data/neuralweb/cortex/
    #    probation.json and the memo's embedded probation block are always in sync.
    #    The grader (grade_cortex_attention.py) is the authoritative writer; this write
    #    is a belt-and-suspenders sync so the two never diverge across runs when the
    #    grader has already written a fresh version.  We only write when the in-memory
    #    status differs from what is on disk (or the file doesn't exist), so we never
    #    overwrite a fresher grader-produced file with stale inline fallback data.
    try:
        probation_path = _cortex_dir(root) / "probation.json"
        _write_probation = True
        if probation_path.exists():
            try:
                _disk = json.loads(probation_path.read_text(encoding="utf-8"))
                # Prefer the on-disk version when it carries a higher-fidelity n
                disk_n = _disk.get("attention_track_record", {}).get("n", 0)
                mem_n = probation_status.get("attention_track_record", {}).get("n", 0)
                if disk_n > mem_n:
                    _write_probation = False
                    log.debug(
                        "cortex: probation.json on disk has n=%d > in-memory n=%d; skipping sync write",
                        disk_n, mem_n,
                    )
            except Exception:  # noqa: BLE001
                pass  # unreadable on-disk version → overwrite
        if _write_probation:
            probation_path.parent.mkdir(parents=True, exist_ok=True)
            probation_path.write_text(
                json.dumps(probation_status, indent=2, default=str), encoding="utf-8"
            )
            log.debug("cortex: probation.json synced from in-memory probation_status")
    except Exception as exc:  # noqa: BLE001
        log.warning("cortex: failed to sync probation.json (%s) — non-fatal", exc)

    elapsed = time.monotonic() - t0
    log.info("cortex: run complete in %.1fs", elapsed)
    return 0


# ---------------------------------------------------------------------------
# CLI entrypoint  (python -m engine.neuralweb.cortex)
# ---------------------------------------------------------------------------

def _cli() -> None:
    import argparse
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [cortex] %(message)s",
    )
    p = argparse.ArgumentParser(description="Cortex deliberation runtime (W7b PR1)")
    p.add_argument("--root", type=Path, default=None, help="Repo root override")
    p.add_argument("--force", action="store_true", help="Skip staleness gate")
    args = p.parse_args()
    rc = run(root=args.root, force=args.force)
    sys.exit(rc)


if __name__ == "__main__":
    _cli()
