from __future__ import annotations

from unittest.mock import patch

from admin import trade_memory

OWNER = "123e4567-e89b-42d3-a456-426614174000"


def _configured():
    return patch.multiple(
        "admin.settings",
        supabase_pat=lambda: "sbp_test",
        supabase_project_ref=lambda: "project",
        supabase_operator_user_id=lambda: OWNER,
    )


def test_status_requires_pat_and_operator_uuid():
    with patch("admin.settings.supabase_pat", return_value=None), \
         patch("admin.settings.supabase_operator_user_id", return_value=OWNER):
        assert trade_memory.status()["configured"] is False

    with patch("admin.settings.supabase_pat", return_value="sbp_test"), \
         patch("admin.settings.supabase_operator_user_id", return_value="not-a-uuid"):
        assert trade_memory.status()["configured"] is False


def test_panel_is_owner_scoped_and_shapes_private_rows():
    calls = []

    def fake_query(sql):
        calls.append(sql)
        if "count(*)" in sql:
            return [{"total": 2, "wins": 1, "losses": 1, "autopsied": 1, "awaiting_review": 1}]
        if "from public.trade_episodes" in sql:
            return [{"id": "e1", "ticker": "JNJ", "outcome": "win"}]
        return [{"feature_key": "rotation", "status": "accruing", "pattern": {}}]

    with _configured(), patch("admin.trade_memory._query", side_effect=fake_query):
        result = trade_memory.panel()
    assert result["ok"] is True
    assert result["summary"]["total"] == 2
    assert result["episodes"][0]["ticker"] == "JNJ"
    assert result["patterns"][0]["feature_key"] == "rotation"
    assert calls and all(f"user_id='{OWNER}'::uuid" in sql for sql in calls)


def test_record_encodes_free_text_and_rejects_position_size():
    payload = {
        "source": "operator",
        "ticker": "JNJ",
        "market": "us",
        "side": "long",
        "entry_date": "2026-06-10",
        "exit_date": "2026-07-20",
        "outcome": "win",
        "thesis_at_entry": "rotation'); drop table trade_episodes; --",
        "observed_result": "healthcare outperformed",
    }
    sql_seen = []

    def fake_query(sql):
        sql_seen.append(sql)
        return [{"id": "e1", "ticker": "JNJ", "outcome": "win", "autopsy_state": "pending"}]

    with _configured(), patch("admin.trade_memory._query", side_effect=fake_query):
        result = trade_memory.record(payload)
    assert result["ok"] is True
    assert "drop table" not in sql_seen[0]
    assert "decode('" in sql_seen[0]

    payload["position_size"] = 100_000
    with _configured(), patch("admin.trade_memory._query") as query:
        refused = trade_memory.record(payload)
    assert refused["ok"] is False
    assert "does not store" in refused["error"]
    query.assert_not_called()
