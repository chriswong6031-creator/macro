"""Tests for scripts/check_no_client_supplied_identity.py.

Covers the three client-identity surfaces the audit named (body / query / path),
the token-derived happy path the live API already uses, and the --selftest
mutation proof the house-law suite requires.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_no_client_supplied_identity.py"

sys.path.insert(0, str(ROOT))
from scripts.check_no_client_supplied_identity import (  # noqa: E402
    Finding,
    scan,
    scan_file,
)


def _write_app(tmp_path: Path, name: str, source: str) -> Path:
    app = tmp_path / "app"
    app.mkdir(exist_ok=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    path = app / name
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def _kinds(findings: list[Finding], name: str) -> set[str]:
    return {f.kind for f in findings if f.path.endswith(name)}


class TestLiveTree:
    def test_current_app_is_clean(self) -> None:
        findings = scan(ROOT)
        assert findings == [], [f.render() for f in findings]


class TestCleanHandlers:
    def test_token_derived_user_id_is_clean(self, tmp_path: Path) -> None:
        _write_app(
            tmp_path,
            "ok.py",
            """
            from fastapi import APIRouter, Depends, Request
            router = APIRouter()

            @router.get("/api/me")
            def me(user: dict = Depends(require_user), request: Request = None):
                user_id = user.get("id") or user.get("email") or ""
                row = {"user_id": user_id}
                return row
            """,
        )
        assert scan(tmp_path) == []

    def test_resource_path_and_helper_param_are_clean(self, tmp_path: Path) -> None:
        _write_app(
            tmp_path,
            "ok.py",
            """
            from fastapi import APIRouter, Depends
            router = APIRouter()

            def load(user_id: str) -> dict:
                return {"user_id": user_id}

            @router.get("/api/brain/runs/{run_id}")
            def detail(run_id: str, user: dict = Depends(require_user)):
                uid = user.get("id")
                return load(uid)
            """,
        )
        assert scan(tmp_path) == []


class TestViolations:
    def test_handler_param_user_id(self, tmp_path: Path) -> None:
        _write_app(
            tmp_path,
            "bad.py",
            """
            from fastapi import APIRouter
            router = APIRouter()

            @router.get("/api/whoami")
            def whoami(user_id: str):
                return user_id
            """,
        )
        assert "handler_param" in _kinds(scan(tmp_path), "bad.py")

    def test_path_template_user_id(self, tmp_path: Path) -> None:
        _write_app(
            tmp_path,
            "bad.py",
            """
            from fastapi import APIRouter
            router = APIRouter()

            @router.get("/api/users/{user_id}")
            def get_user():
                return {}
            """,
        )
        assert "route_path" in _kinds(scan(tmp_path), "bad.py")

    def test_query_alias_user_id(self, tmp_path: Path) -> None:
        _write_app(
            tmp_path,
            "bad.py",
            """
            from fastapi import APIRouter, Query
            router = APIRouter()

            @router.get("/api/who")
            def who(ident: str = Query(..., alias="user_id")):
                return ident
            """,
        )
        assert "query_or_path_alias" in _kinds(scan(tmp_path), "bad.py")

    def test_body_get_user_id(self, tmp_path: Path) -> None:
        _write_app(
            tmp_path,
            "bad.py",
            """
            from fastapi import APIRouter, Body
            router = APIRouter()

            @router.post("/api/act")
            def act(payload: dict = Body(default=None)):
                return payload.get("user_id")
            """,
        )
        assert "body_key" in _kinds(scan(tmp_path), "bad.py")

    def test_query_params_get_user_id(self, tmp_path: Path) -> None:
        _write_app(
            tmp_path,
            "bad.py",
            """
            from fastapi import APIRouter, Request
            router = APIRouter()

            @router.get("/api/act")
            def act(request: Request):
                return request.query_params.get("user_id")
            """,
        )
        assert "request_container" in _kinds(scan(tmp_path), "bad.py")

    def test_path_params_subscript(self, tmp_path: Path) -> None:
        _write_app(
            tmp_path,
            "bad.py",
            """
            from fastapi import APIRouter, Request
            router = APIRouter()

            @router.get("/api/act")
            def act(request: Request):
                return request.path_params["account_id"]
            """,
        )
        assert "request_container" in _kinds(scan(tmp_path), "bad.py")

    def test_json_body_user_id(self, tmp_path: Path) -> None:
        _write_app(
            tmp_path,
            "bad.py",
            """
            from fastapi import APIRouter, Request
            import json
            router = APIRouter()

            @router.post("/api/act")
            async def act(request: Request):
                data = json.loads(await request.body())
                return data["user_id"]
            """,
        )
        assert "body_key" in _kinds(scan(tmp_path), "bad.py")

    def test_pydantic_model_field(self, tmp_path: Path) -> None:
        _write_app(
            tmp_path,
            "bad.py",
            """
            from fastapi import APIRouter
            from pydantic import BaseModel
            router = APIRouter()

            class Hack(BaseModel):
                user_id: str

            @router.post("/api/hack")
            def hack(body: Hack):
                return body
            """,
        )
        assert "model_field" in _kinds(scan(tmp_path), "bad.py")

    def test_account_id_param(self, tmp_path: Path) -> None:
        _write_app(
            tmp_path,
            "bad.py",
            """
            from fastapi import APIRouter
            router = APIRouter()

            @router.post("/api/acct")
            def acct(account_id: str):
                return account_id
            """,
        )
        assert "handler_param" in _kinds(scan(tmp_path), "bad.py")

    def test_unparseable_file_is_a_finding(self, tmp_path: Path) -> None:
        path = _write_app(tmp_path, "broken.py", "def (\n")
        findings = scan_file(path, "app/broken.py")
        assert findings and findings[0].kind == "parse_error"


class TestSelftestAndCli:
    def test_selftest_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--selftest"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "selftest OK" in result.stdout

    def test_live_cli_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "check_no_client_supplied_identity: OK" in result.stdout
