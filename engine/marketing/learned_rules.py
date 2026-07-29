"""engine/marketing/learned_rules.py — learning without collapse (XG-W6).

Charter §8, Reversibility: "learned rules (format preferences, timing, reply
families) are versioned config entries with a rollback path — XG-W6 ships the
version log alongside the scorecards; **a rule that cannot be reverted may not
be learned**."

That last clause is enforced HERE, at the store, exactly the way
``reply_queue.validate_critic_stamp`` enforces the critic guarantee: a rule
without a complete, replayable ``revert`` block is REFUSED, so "every learned
rule can be rolled back" is a structural fact about the ledger rather than a
property of whichever proposer happened to write it.

**What a revert block has to say.** Restoring "the old value" is not enough,
because the commonest learned rule sets a key that did not exist before. A
revert therefore carries ``present`` (did the key exist at all) as well as
``value``. Without that flag, rolling back a first-time rule would write an
invented "previous" value and quietly become a second edit rather than an
undo — a rollback path that changes state is not a rollback path.

**Shipping posture: DARK by default.** Applying a learned rule is a PROMOTION
(it changes what gets ranked or emitted), and promotions run the gauntlet
(house epistemics law). So the store, the version log, the shape enforcement,
and the admin surface ship now; consumption is gated behind
``learning.learned_rules.enabled`` (default ``false``). The one wired reader —
``reply_producer`` restricting reply families — checks that flag, so the call
site is real and the behaviour is off until an operator arms it.

**Nothing here edits config/marketing.yml.** A process that rewrites its own
committed config is an unreviewable self-edit; the active set is a data file
that readers consult, and the operator's own YAML always wins on conflict.

Storage (TRACKED, nightly-advanced):
    data/marketing/learning/rules_log.jsonl    append-only version log
    data/marketing/learning/rules_active.json  the currently-applied set

Public API:
    RULE_SCHEMA / KINDS / DEFAULTS
    rules_log_path(root) / rules_active_path(root)
    make_rule(...) -> dict
    validate_rule(rule) -> list[str]        # [] means the SHAPE can be reverted
    apply_rule(rule, *, now, root=None, actor=...) -> dict
        # ...and verifies the declared revert against the ACTUAL active state
    rollback(version_id, *, now, root=None, actor=...) -> dict
    history(root=None) -> list[dict]
    active(root=None) -> dict
    enabled(cfg) -> bool
    active_for(kind, *, account=None, root=None, cfg=None) -> list[dict]
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

RULE_SCHEMA = "marketing.learned_rule/v1"

#: The three rule families the charter names. A closed vocabulary on purpose:
#: an open one is how "learned rule" grows to mean "arbitrary runtime patch".
KINDS: frozenset[str] = frozenset({"format_preference", "timing", "reply_family"})

DEFAULTS: dict[str, Any] = {
    # DARK BY DEFAULT — applying a learned rule is a promotion, and promotions
    # run the gauntlet. Arming lever: learning.learned_rules.enabled: true.
    "enabled": False,
    # A proposal must cite this many labelled observations. Charter §8 experiment
    # law: "No learning promotes from one viral accident."
    "min_evidence_n": 30,
    # ...and the cell it came from must have cleared the labels n-floor.
    "require_cell_verdict_not_seeding": True,
}


def _cfg(cfg: dict | None) -> dict:
    raw = (((cfg or {}).get("learning") or {}).get("learned_rules") or {})
    return {**DEFAULTS, **raw}


def enabled(cfg: dict | None) -> bool:
    """Is the CONSUMPTION of learned rules armed? Default False."""
    return bool(_cfg(cfg).get("enabled"))


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
def _root_path(root: Path | str | None) -> Path:
    if root is None:
        return Path(__file__).resolve().parent.parent.parent
    return Path(root)


def _dir(root: Path | str | None) -> Path:
    return _root_path(root) / "data" / "marketing" / "learning"


def rules_log_path(root: Path | str | None = None) -> Path:
    return _dir(root) / "rules_log.jsonl"


def rules_active_path(root: Path | str | None = None) -> Path:
    return _dir(root) / "rules_active.json"


def _read_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
    except (FileNotFoundError, NotADirectoryError, OSError):
        return []
    return out


def _append_jsonl(path: Path, row: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return True
    except OSError as exc:
        log.warning("learned_rules: cannot append %s: %s", path, exc)
        return False


def _write_json_atomic(path: Path, payload: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".lr-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            os.replace(tmp, path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("learned_rules: cannot write %s: %s", path, exc)
        return False


def _iso(dt: datetime) -> str:
    ts = dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Rule construction + THE reversibility gate
# ---------------------------------------------------------------------------
def make_rule(
    *,
    kind: str,
    path: str,
    value: Any,
    revert_present: bool,
    revert_value: Any = None,
    evidence: dict | None = None,
    account: str | None = None,
    note: str = "",
    now: datetime | None = None,
) -> dict:
    """Build a learned-rule proposal with a complete revert block.

    ``revert_present`` is the load-bearing argument: False means "this key did
    not exist before" and a rollback DELETES it; True means it existed and a
    rollback restores ``revert_value``. Making it a required keyword rather
    than inferring it stops a proposer from silently guessing.
    """
    ts = now or datetime.now(timezone.utc)
    rule: dict[str, Any] = {
        "schema": RULE_SCHEMA,
        "kind": str(kind),
        "account": (str(account) if account else None),
        "path": str(path),
        "value": value,
        "revert": {"present": bool(revert_present), "value": revert_value},
        "evidence": dict(evidence or {}),
        "note": str(note or ""),
        "proposed_at": _iso(ts),
    }
    basis = f"{rule['kind']}|{rule['account']}|{rule['path']}|" \
            f"{json.dumps(value, sort_keys=True, default=str)}|{rule['proposed_at']}"
    rule["version_id"] = "lr-" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]  # noqa: S324
    return rule


def validate_rule(rule: dict, *, cfg: dict | None = None) -> list[str]:
    """Errors in a rule; [] means it is learnable. THE STRUCTURAL GUARANTEE.

    A rule that cannot be reverted may not be learned (charter §8), so the
    revert block is checked here rather than trusted from a proposer. Also
    enforces the experiment law's evidence floor: no learning promotes from one
    viral accident.
    """
    conf = _cfg(cfg)
    errors: list[str] = []
    if not isinstance(rule, dict):
        return ["rule must be a mapping"]
    if rule.get("schema") != RULE_SCHEMA:
        errors.append(f"schema must be {RULE_SCHEMA!r}; got {rule.get('schema')!r}")
    if rule.get("kind") not in KINDS:
        errors.append(f"kind {rule.get('kind')!r} not in {sorted(KINDS)}")
    if not str(rule.get("path") or "").strip():
        errors.append("path must be a non-empty config key path")
    if not str(rule.get("version_id") or "").strip():
        errors.append("version_id must be non-empty — an unversioned rule cannot be rolled back")

    revert = rule.get("revert")
    if not isinstance(revert, dict):
        errors.append(
            "revert must be a mapping {present: bool, value: any} — a rule that "
            "cannot be reverted may not be learned (charter §8)"
        )
    elif not isinstance(revert.get("present"), bool):
        errors.append(
            "revert.present must be a bool: True restores revert.value, False "
            "DELETES the key. Without it a rollback of a first-time rule would "
            "write an invented previous value instead of undoing the change."
        )
    elif revert["present"] and "value" not in revert:
        errors.append("revert.present is True but revert.value is missing — nothing to restore")

    evidence = rule.get("evidence")
    if not isinstance(evidence, dict):
        errors.append("evidence must be a dict (inspectable: charter §8)")
    else:
        n = evidence.get("n")
        floor = int(conf.get("min_evidence_n") or 0)
        if not isinstance(n, int):
            errors.append(f"evidence.n must be an int (declared sample size); got {n!r}")
        elif n < floor:
            errors.append(
                f"evidence.n={n} below min_evidence_n={floor} — no learning promotes "
                "from one viral accident (charter §8 experiment law)"
            )
        if conf.get("require_cell_verdict_not_seeding") and evidence.get("verdict") == "seeding":
            errors.append(
                "evidence cites a cell whose verdict is 'seeding' (below the labels "
                "n-floor) — a seeding cell makes no ranking claim, so it cannot "
                "support one"
            )
    return errors


# ---------------------------------------------------------------------------
# Apply / rollback / read
# ---------------------------------------------------------------------------
def _revert_matches_state(rule: dict, table: dict[str, dict]) -> list[str]:
    """Does the rule's declared revert describe the ACTUAL current state?

    Two ways to be wrong, and both make the rollback path a lie:

      * ``present: False`` ("nothing was here") on a path that IS active — a
        rollback would delete a rule someone else applied.
      * ``present: True`` with a ``value`` that is not what is currently
        active — a rollback would write a value that was never there.
    """
    key = str(rule.get("path") or "")
    revert = rule.get("revert") or {}
    current = table.get(key)
    declared_present = bool(revert.get("present"))

    if current is None:
        if declared_present:
            return [f"revert.present is True but nothing is active at {key!r}"]
        return []
    if not declared_present:
        return [f"revert.present is False but {key!r} is already active "
                f"(version {current.get('version_id')!r})"]
    if revert.get("value") != current.get("value"):
        return [f"revert.value {revert.get('value')!r} does not match the active "
                f"value {current.get('value')!r} at {key!r}"]
    return []


def apply_rule(
    rule: dict,
    *,
    now: datetime | None = None,
    root: Path | str | None = None,
    actor: str = "nightly",
    cfg: dict | None = None,
) -> dict:
    """Record a rule as ACTIVE, appending a version-log row. Returns {ok, ...}.

    Refuses anything ``validate_rule`` rejects — including, and especially, a
    rule with no revert block. Applying supersedes any active rule on the same
    ``path``; the superseded version stays in the log, so the chain back to the
    original value is always walkable.
    """
    errors = validate_rule(rule, cfg=cfg)
    if errors:
        print(
            f"::warning title=learned-rule-refused::rule {rule.get('version_id')!r} "
            f"refused: {errors[0]}",
            flush=True,
        )
        return {"ok": False, "errors": errors, "version_id": rule.get("version_id")}

    ts = now or datetime.now(timezone.utc)
    table = active(root)
    vid = str(rule["version_id"])
    key = str(rule["path"])
    superseded = table.get(key, {}).get("version_id")

    # REVERSIBILITY MUST BE TRUE, NOT WELL-FORMED. `validate_rule` proves the
    # revert block has the right SHAPE; it cannot know whether the value it
    # promises to restore is the value that is actually there. A proposer built
    # against a stale read would declare `revert: {present: false}` on a path
    # something else already set, and rolling it back would DELETE a live rule
    # instead of restoring one — a rollback that changes state is not a
    # rollback. This is the only place with both halves in hand, so it checks.
    errs = _revert_matches_state(rule, table)
    if errs:
        print(
            f"::warning title=learned-rule-stale::rule {vid!r} refused: {errs[0]} "
            "— the declared revert does not describe the CURRENT active state, so "
            "rolling it back would not undo it",
            flush=True,
        )
        return {"ok": False, "errors": errs, "version_id": vid}

    entry = dict(rule)
    entry.update({"applied_at": _iso(ts), "applied_by": actor, "state": "active",
                  "supersedes": superseded})
    table[key] = entry

    if not _write_json_atomic(rules_active_path(root),
                              {"schema": RULE_SCHEMA, "rules": table,
                               "updated_at": _iso(ts)}):
        return {"ok": False, "errors": ["write_failed"], "version_id": vid}
    _append_jsonl(rules_log_path(root), {
        "at": _iso(ts), "action": "apply", "actor": actor, "version_id": vid,
        "kind": rule.get("kind"), "account": rule.get("account"), "path": key,
        "value": rule.get("value"), "revert": rule.get("revert"),
        "evidence": rule.get("evidence"), "supersedes": superseded,
    })
    return {"ok": True, "version_id": vid, "path": key, "supersedes": superseded}


def rollback(
    version_id: str,
    *,
    now: datetime | None = None,
    root: Path | str | None = None,
    actor: str = "operator",
) -> dict:
    """Undo one applied rule. Returns {ok, restored: {...}}.

    ``revert.present == False`` DELETES the key rather than writing a value —
    the difference between "put it back" and "there was nothing there" is the
    whole point of carrying the flag.
    """
    ts = now or datetime.now(timezone.utc)
    table = active(root)
    match = None
    for key, entry in table.items():
        if str(entry.get("version_id")) == str(version_id):
            match = (key, entry)
            break
    if match is None:
        return {"ok": False, "error": "unknown_or_inactive_version", "version_id": version_id}

    key, entry = match
    revert = entry.get("revert") or {}
    if revert.get("present"):
        # Re-apply the previous value AS A RULE so the active set stays a
        # complete description of current state (and remains rollback-able).
        restored = dict(entry)
        restored["value"] = revert.get("value")
        restored["revert"] = {"present": True, "value": entry.get("value")}
        restored["state"] = "active"
        restored["applied_at"] = _iso(ts)
        restored["applied_by"] = actor
        restored["rolled_back_from"] = version_id
        table[key] = restored
        outcome = {"path": key, "action": "restored", "value": revert.get("value")}
    else:
        table.pop(key, None)
        outcome = {"path": key, "action": "deleted", "value": None}

    if not _write_json_atomic(rules_active_path(root),
                              {"schema": RULE_SCHEMA, "rules": table,
                               "updated_at": _iso(ts)}):
        return {"ok": False, "error": "write_failed", "version_id": version_id}
    _append_jsonl(rules_log_path(root), {
        "at": _iso(ts), "action": "rollback", "actor": actor,
        "version_id": version_id, "path": key, "outcome": outcome,
    })
    return {"ok": True, "version_id": version_id, "restored": outcome}


def active(root: Path | str | None = None) -> dict[str, dict]:
    """{config_path: active rule entry}."""
    try:
        blob = json.loads(rules_active_path(root).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    rules = blob.get("rules") if isinstance(blob, dict) else None
    return {str(k): v for k, v in rules.items() if isinstance(v, dict)} if isinstance(rules, dict) else {}


def history(root: Path | str | None = None) -> list[dict]:
    """The append-only version log, oldest first. Shipped ALONGSIDE the
    scorecards (charter §8) — the admin learning panel renders both."""
    return _read_jsonl(rules_log_path(root))


def active_for(
    kind: str,
    *,
    account: str | None = None,
    root: Path | str | None = None,
    cfg: dict | None = None,
) -> list[dict]:
    """Active rules of one kind, for one account (or fleet-wide).

    Returns ``[]`` when consumption is disarmed, which is the default. The
    caller therefore needs no flag check of its own and cannot forget one.
    """
    if not enabled(cfg):
        return []
    out = [
        entry for entry in active(root).values()
        if entry.get("kind") == str(kind)
        and (entry.get("account") in (None, account) if account is not None
             else entry.get("account") is None)
    ]
    return sorted(out, key=lambda e: str(e.get("path")))


__all__ = [
    "RULE_SCHEMA", "KINDS", "DEFAULTS",
    "rules_log_path", "rules_active_path",
    "make_rule", "validate_rule", "apply_rule", "rollback",
    "active", "history", "active_for", "enabled",
]
