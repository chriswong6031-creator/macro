"""engine.marketing.accounts — Account liveness model (enabled / status).

The single place that answers "which desk accounts actually exist tonight?".

Config (config/marketing.yml ``desk_network.accounts``) carries the *intent*
per account: ``enabled: true`` on desks with a real X account, ``enabled: false``
on desks that are still just a beat + tilt with no account behind them yet.
Backward-compat: an account with neither ``enabled`` nor ``disabled`` defaults
to enabled (the pre-existing shape), and a legacy ``disabled: true`` still means
not enabled (sentinel's per-account kill-switch).

An optional operator override file — ``data/marketing/account_overrides.json``
— lets the operator flip a single account on/off between config edits without a
deploy. Shape::

    {"flagship": {"enabled": false, "note": "paused for X policy review",
                  "at": "2026-07-23T18:00:00Z"}}

Absent file → no overrides.  Malformed JSON or a non-dict body → ignored
(fail-soft; the config intent stands).  An override's ``enabled`` wins over
config; a malformed single entry is skipped, not fatal.

``account_status`` layers the publish.channels map on top of ``enabled`` to
give the admin a three-state read: ``live`` (enabled + a channel id wired),
``ready`` (enabled but no channel yet), ``planned`` (not enabled).

Pure except for one optional read of the override file — never raises.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

_OVERRIDES_REL = Path("data/marketing/account_overrides.json")


def _root_path(root: Path | str | None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _config_enabled(acct: dict) -> bool:
    """Resolve an account's enabled state from config alone (no overrides).

    Precedence: explicit ``enabled`` key wins; else a legacy ``disabled: true``
    means not enabled; else default True (the pre-existing bare shape).
    """
    if "enabled" in acct:
        return bool(acct.get("enabled"))
    if acct.get("disabled"):
        return False
    return True


def load_overrides(root: Path | str | None = None) -> dict[str, dict]:
    """Read data/marketing/account_overrides.json → {account_id: override}.

    Absent file → {}.  Malformed JSON, a non-dict top level, or a non-dict
    entry → that content is dropped; we never raise.
    """
    path = _root_path(root) / _OVERRIDES_REL
    try:
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — fail-soft: a bad file must not break the plan
        log.warning("account_overrides.json unreadable (%s) — ignoring overrides", exc)
        return {}
    if not isinstance(raw, dict):
        log.warning("account_overrides.json is not an object — ignoring overrides")
        return {}
    out: dict[str, dict] = {}
    for acc_id, ov in raw.items():
        if isinstance(ov, dict):
            out[str(acc_id)] = ov
    return out


def effective_accounts(cfg: dict | None, root: Path | str | None = None) -> list[dict]:
    """Return the config account dicts, each carrying a resolved ``enabled``.

    ``enabled`` = config intent (``enabled`` key, default True; legacy
    ``disabled: true`` = off) unless the operator override file supplies an
    ``enabled`` for that id, in which case the override wins.  The original
    config fields are preserved; ``enabled`` is (re)stamped on a shallow copy so
    callers never mutate the parsed cfg.
    """
    dn_cfg = (cfg or {}).get("desk_network", {}) or {}
    raw_accounts = dn_cfg.get("accounts", []) or []
    overrides = load_overrides(root)

    out: list[dict] = []
    for acct in raw_accounts:
        if not isinstance(acct, dict):
            continue
        resolved = dict(acct)
        enabled = _config_enabled(acct)
        ov = overrides.get(str(acct.get("id", "")))
        if ov is not None and "enabled" in ov:
            enabled = bool(ov.get("enabled"))
        resolved["enabled"] = enabled
        out.append(resolved)
    return out


def account_status(acc: dict, channels_cfg: dict | None) -> str:
    """Three-state liveness for the admin desk-network view.

    ``live``    — enabled AND a non-empty channel id wired in publish.channels.
    ``ready``   — enabled but no channel id yet (real account will exist, unwired).
    ``planned`` — not enabled (beat + tilt only; no real X account behind it).

    ``acc`` should carry a resolved ``enabled`` (see effective_accounts); if it
    only carries config keys we fall back to the config resolution so a bare
    account dict still classifies sensibly.
    """
    enabled = bool(acc["enabled"]) if "enabled" in acc else _config_enabled(acc)
    if not enabled:
        return "planned"
    channel_id = str((channels_cfg or {}).get(acc.get("id", ""), "") or "").strip()
    return "live" if channel_id else "ready"
