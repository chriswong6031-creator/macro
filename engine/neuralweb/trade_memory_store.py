"""Private Supabase adapter for Prophet Trade Memory.

The adapter is intentionally operator-scoped even though it uses a service-role
credential.  ``SUPABASE_OPERATOR_USER_ID`` is mandatory and every read/write carries
that UUID.  It never enumerates other users and never logs tickers, notes, prices, or
autopsy text.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from urllib.parse import quote

log = logging.getLogger("neuralweb.trade_memory_store")

try:
    import requests
except Exception:  # pragma: no cover - production requirements include requests
    requests = None  # type: ignore

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class SupabaseTradeMemoryStore:
    """Small PostgREST client with an explicit single-owner boundary."""

    def __init__(
        self,
        base_url: str,
        service_key: str,
        operator_user_id: str,
        session: Any = None,
    ):
        self.base_url = str(base_url or "").rstrip("/")
        self.service_key = str(service_key or "")
        self.operator_user_id = str(operator_user_id or "").lower()
        self.session = session or requests

    @property
    def available(self) -> bool:
        return bool(
            self.base_url
            and self.service_key
            and _UUID_RE.fullmatch(self.operator_user_id)
            and self.session is not None
        )

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _url(self, table: str) -> str:
        return f"{self.base_url}/rest/v1/{table}"

    def fetch_pending(self, limit: int = 8) -> list[dict[str, Any]]:
        if not self.available:
            return []
        params = {
            "select": "*",
            "user_id": f"eq.{self.operator_user_id}",
            "outcome": "in.(win,loss,flat)",
            "autopsy_state": "in.(pending,retry)",
            "order": "created_at.asc",
            "limit": str(max(1, min(25, int(limit)))),
        }
        try:
            response = self.session.get(
                self._url("trade_episodes"),
                headers=self._headers,
                params=params,
                timeout=25,
            )
            if response.status_code != 200:
                log.warning("trade_memory_store: pending read HTTP %s", response.status_code)
                return []
            rows = response.json()
            return rows if isinstance(rows, list) else []
        except Exception as exc:  # noqa: BLE001
            log.warning("trade_memory_store: pending read failed (%s)", type(exc).__name__)
            return []

    def fetch_autopsied(self, limit: int = 500) -> list[dict[str, Any]]:
        if not self.available:
            return []
        params = {
            "select": "id,entry_date,outcome,autopsy",
            "user_id": f"eq.{self.operator_user_id}",
            "autopsy_state": "eq.complete",
            "autopsy": "not.is.null",
            "order": "entry_date.desc",
            "limit": str(max(1, min(2_000, int(limit)))),
        }
        try:
            response = self.session.get(
                self._url("trade_episodes"),
                headers=self._headers,
                params=params,
                timeout=25,
            )
            if response.status_code != 200:
                log.warning("trade_memory_store: autopsy read HTTP %s", response.status_code)
                return []
            rows = response.json()
            return rows if isinstance(rows, list) else []
        except Exception as exc:  # noqa: BLE001
            log.warning("trade_memory_store: autopsy read failed (%s)", type(exc).__name__)
            return []

    def update_episode(self, episode_id: str, patch: dict[str, Any]) -> bool:
        if not self.available or not _UUID_RE.fullmatch(str(episode_id or "")):
            return False
        # Whitelist prevents a caller from moving a row to another owner or changing
        # the trade facts during the autopsy pass.
        allowed = {
            "evidence_packet",
            "autopsy",
            "autopsy_state",
            "autopsy_model",
            "autopsied_at",
            "autopsy_error",
            "updated_at",
        }
        body = {k: v for k, v in patch.items() if k in allowed}
        if not body:
            return False
        headers = {**self._headers, "Prefer": "return=minimal"}
        params = {
            "id": f"eq.{episode_id}",
            "user_id": f"eq.{self.operator_user_id}",
        }
        try:
            response = self.session.patch(
                self._url("trade_episodes"),
                headers=headers,
                params=params,
                data=json.dumps(body, ensure_ascii=False, default=str),
                timeout=25,
            )
            return response.status_code in (200, 204)
        except Exception as exc:  # noqa: BLE001
            log.warning("trade_memory_store: episode update failed (%s)", type(exc).__name__)
            return False

    def replace_patterns(self, patterns: list[dict[str, Any]]) -> bool:
        """Replace the operator's derived pattern view (rebuildable from episodes)."""
        if not self.available:
            return False
        owner = quote(self.operator_user_id, safe="")
        try:
            deleted = self.session.delete(
                self._url("trade_memory_patterns"),
                headers={**self._headers, "Prefer": "return=minimal"},
                params={"user_id": f"eq.{owner}"},
                timeout=25,
            )
            if deleted.status_code not in (200, 204):
                log.warning("trade_memory_store: pattern reset HTTP %s", deleted.status_code)
                return False
            if not patterns:
                return True
            rows = [
                {
                    "user_id": self.operator_user_id,
                    "feature_key": p.get("feature_key"),
                    "pattern": p,
                    "status": p.get("status") or "accruing",
                }
                for p in patterns
            ]
            inserted = self.session.post(
                self._url("trade_memory_patterns"),
                headers={**self._headers, "Prefer": "return=minimal"},
                data=json.dumps(rows, ensure_ascii=False, default=str),
                timeout=25,
            )
            return inserted.status_code in (200, 201, 204)
        except Exception as exc:  # noqa: BLE001
            log.warning("trade_memory_store: pattern replace failed (%s)", type(exc).__name__)
            return False


def build_store() -> SupabaseTradeMemoryStore | None:
    """Build the production store from the existing operator bridge secrets."""
    base_url = os.environ.get("SUPABASE_URL", "").strip()
    if not base_url:
        try:
            from lib import config  # noqa: PLC0415
            base_url = str(
                ((config.load().get("watchlist") or {}).get("supabase") or {}).get("url") or ""
            )
        except Exception:  # noqa: BLE001
            base_url = ""
    key = (
        os.environ.get("SUPABASE_SERVICE_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    )
    owner = os.environ.get("SUPABASE_OPERATOR_USER_ID") or ""
    store = SupabaseTradeMemoryStore(base_url, key, owner)
    return store if store.available else None
