"""Authenticated operator console adapter for private Prophet Trade Memory.

The deployed admin already uses a Supabase Management API PAT.  This module uses
that same server-side channel plus ``SUPABASE_OPERATOR_USER_ID``; no credential or
private row reaches the public site.  User text is base64-encoded before it is
embedded in SQL, so it cannot alter the statement.
"""
from __future__ import annotations

import base64
import json
import re
from typing import Any

from . import settings
from engine.neuralweb.trade_memory import normalize_episode

try:
    import requests
except Exception:  # pragma: no cover - shipped admin requirements include requests
    requests = None  # type: ignore

_API = "https://api.supabase.com/v1"
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _owner() -> str | None:
    value = settings.supabase_operator_user_id()
    return value.lower() if value and _UUID_RE.fullmatch(value) else None


def status() -> dict[str, Any]:
    owner = _owner()
    configured = bool(settings.supabase_pat() and owner and requests)
    if configured:
        reason = None
    elif not settings.supabase_pat():
        reason = "SUPABASE_ACCESS_TOKEN is not set"
    elif not owner:
        reason = "SUPABASE_OPERATOR_USER_ID is not set to a UUID"
    else:
        reason = "requests is not installed"
    return {
        "configured": configured,
        "reason": reason,
        "privacy": "Owner-scoped Supabase rows; never committed to git.",
        "learning_boundary": "Autopsies and patterns are research context only.",
    }


def _query(sql: str):
    pat = settings.supabase_pat()
    if not (pat and requests):
        return None
    response = requests.post(
        f"{_API}/projects/{settings.supabase_project_ref()}/database/query",
        headers={"Authorization": f"Bearer {pat}", "Content-Type": "application/json"},
        json={"query": sql},
        timeout=20,
    )
    if not 200 <= response.status_code < 300:
        # Never include the SQL or personal payload in an exception.
        raise RuntimeError(f"Supabase query failed (HTTP {response.status_code})")
    return response.json()


def panel() -> dict[str, Any]:
    state = status()
    owner = _owner()
    if not state["configured"] or not owner:
        return {
            "ok": False,
            **state,
            "summary": {},
            "episodes": [],
            "patterns": [],
        }
    try:
        summary_rows = _query(
            "select "
            "count(*)::int as total, "
            "count(*) filter (where outcome='open')::int as open, "
            "count(*) filter (where outcome='win')::int as wins, "
            "count(*) filter (where outcome='loss')::int as losses, "
            "count(*) filter (where autopsy_state='complete')::int as autopsied, "
            "count(*) filter (where autopsy_state in ('pending','retry'))::int as awaiting_review "
            f"from public.trade_episodes where user_id='{owner}'::uuid"
        )
        episodes = _query(
            "select id, source, ticker, market, side, entry_date, exit_date, outcome, "
            "autopsy_state, autopsy_model, autopsied_at, "
            "coalesce(autopsy->>'summary','') as autopsy_summary, "
            "coalesce(autopsy->>'lesson','') as lesson "
            "from public.trade_episodes "
            f"where user_id='{owner}'::uuid "
            "order by coalesce(exit_date, entry_date) desc, created_at desc limit 30"
        )
        patterns = _query(
            "select feature_key, status, pattern, updated_at "
            "from public.trade_memory_patterns "
            f"where user_id='{owner}'::uuid "
            "order by case when status='ready_for_prereg' then 0 else 1 end, updated_at desc "
            "limit 30"
        )
        return {
            "ok": True,
            **state,
            "summary": (summary_rows or [{}])[0],
            "episodes": episodes or [],
            "patterns": patterns or [],
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            **state,
            "error": str(exc),
            "summary": {},
            "episodes": [],
            "patterns": [],
        }


def record(payload: dict[str, Any]) -> dict[str, Any]:
    state = status()
    owner = _owner()
    if not state["configured"] or not owner:
        return {"ok": False, "error": state["reason"] or "Trade Memory is not configured"}
    try:
        episode = normalize_episode(payload)
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    # jsonb is decoded inside PostgreSQL.  The embedded token contains only base64
    # characters, so even arbitrary operator prose cannot become SQL syntax.
    encoded = base64.b64encode(
        json.dumps(episode, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")
    sql = f"""
with payload as (
  select convert_from(decode('{encoded}','base64'),'UTF8')::jsonb as j
)
insert into public.trade_episodes (
  user_id, schema, source, ticker, market, side, entry_date, exit_date,
  entry_price, exit_price, outcome, thesis_at_entry, observed_result,
  prophet_pick_ref, autopsy_state
)
select
  '{owner}'::uuid,
  j->>'schema', j->>'source', j->>'ticker', j->>'market', j->>'side',
  (j->>'entry_date')::date,
  nullif(j->>'exit_date','')::date,
  nullif(j->>'entry_price','')::numeric,
  nullif(j->>'exit_price','')::numeric,
  j->>'outcome', j->>'thesis_at_entry', j->>'observed_result',
  nullif(j->>'prophet_pick_ref',''),
  case when j->>'outcome'='open' then 'waiting_close' else 'pending' end
from payload
returning id, ticker, outcome, autopsy_state
"""
    try:
        rows = _query(sql) or []
        row = rows[0] if rows else {}
        return {
            "ok": True,
            "id": row.get("id"),
            "ticker": row.get("ticker"),
            "outcome": row.get("outcome"),
            "autopsy_state": row.get("autopsy_state"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
