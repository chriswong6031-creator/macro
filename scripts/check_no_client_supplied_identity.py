#!/usr/bin/env python3
"""AST guard: route handlers must not take user identity from the client.

Rationale
---------
``_pg()`` authenticates to PostgREST with ``SUPABASE_SERVICE_ROLE_KEY``, which
bypasses Row Level Security entirely. Service-role access is safe in this
codebase only because every ``user_id`` (and equivalent identity) is derived
from the Supabase-verified token record (``user.get("id")`` via
``require_user`` / ``Depends``), never from a request body, query parameter, or
path segment. A single handler that accepts client-supplied identity becomes a
full cross-tenant read/write. This is the isolation invariant the 2026-08-12
auth/billing audit named as the most important one in the API
(``research/MASTERMIND_SECURITY_AUTH_BILLING_AUDIT.md`` §2.1; WS-9 / GATE-6).

What it flags (inside a FastAPI/Starlette route handler only)
-------------------------------------------------------------
1. A handler parameter named ``user_id`` / equivalent whose default is not
   ``Depends`` / ``Header`` / ``Cookie``.
2. ``Query`` / ``Path`` / ``Body`` / ``Form`` whose ``alias`` is an identity key.
3. A route path template containing ``{user_id}`` (or equivalent).
4. Reading an identity key off a request-sourced object (``body.get("user_id")``,
   ``payload["user_id"]``, ``body.user_id``, ``request.query_params.get(...)``,
   ``request.path_params[...]``).
5. A same-module Pydantic/body model field named as identity, used as a
   handler body parameter.

Helpers that take ``user_id`` as an ordinary argument are invisible — they are
not route handlers. Resource ids (``run_id``, ``thread_id``, ``doc_id``,
``ticker``) are not identity. Operator admin tools are out of scope (different
trust boundary).

Usage
-----
    python3 scripts/check_no_client_supplied_identity.py
    python3 scripts/check_no_client_supplied_identity.py --root /path/to/repo
    python3 scripts/check_no_client_supplied_identity.py --selftest

Exit codes: 0 = clean / selftest passed · 1 = finding(s) / selftest failed.
"""
from __future__ import annotations

import argparse
import ast
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCAN_ROOTS: tuple[str, ...] = ("app",)

HTTP_METHODS = frozenset({
    "get", "post", "put", "patch", "delete", "head", "options", "trace",
    "websocket", "api_route",
})

# Handler *parameter* names that are identity. ``uid`` is included here
# (a ``uid: str`` query/path param is the same bug) but is NOT a body-key
# name — too many legitimate locals (``uid = user.get("id")``).
IDENTITY_PARAM_NAMES = frozenset({
    "user_id",
    "userid",
    "userId",
    "account_id",
    "accountid",
    "owner_id",
    "ownerid",
    "auth_user_id",
    "auth_uid",
    "supabase_uid",
    "supabase_user_id",
    "uid",
})

# Keys read from a request container / path template. No bare ``uid`` / ``id``.
IDENTITY_KEYS = frozenset({
    "user_id",
    "userid",
    "userId",
    "account_id",
    "owner_id",
    "auth_user_id",
    "auth_uid",
    "supabase_uid",
    "supabase_user_id",
})

_INJECTED_DEFAULTS = frozenset({"Depends", "Header", "Cookie"})
_INJECTED_ANNOTATIONS = frozenset({
    "Request", "Response", "BackgroundTasks", "WebSocket",
})
_CLIENT_DEFAULTS = frozenset({
    "Query", "Path", "Body", "Form", "File", "ApiPath",
})
_REQUEST_BODY_NAMES = frozenset({
    "body", "payload", "data", "json", "form", "fields",
    "req_body", "request_body", "content",
})
_SIMPLE_TYPES = frozenset({
    "str", "int", "float", "bool", "bytes", "None", "NoneType",
})
_SKIP_DIRS = frozenset({".git", "__pycache__", ".venv", "node_modules"})


@dataclass(frozen=True)
class Finding:
    path: str
    lineno: int
    kind: str
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.lineno}: [{self.kind}] {self.detail}"


def _const_str(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_name(node: ast.AST | None) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _ann_names(node: ast.AST | None) -> set[str]:
    names: set[str] = set()
    if node is None:
        return names
    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, ast.Attribute):
        names.add(node.attr)
        names |= _ann_names(node.value)
    elif isinstance(node, ast.Subscript):
        names |= _ann_names(node.value)
        names |= _ann_names(node.slice)
    elif isinstance(node, ast.BinOp):
        names |= _ann_names(node.left)
        names |= _ann_names(node.right)
    elif isinstance(node, ast.Tuple):
        for elt in node.elts:
            names |= _ann_names(elt)
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        token = node.value.replace(" ", "")
        for part in token.replace("[", ",").replace("]", ",").split("|"):
            piece = part.split(",")[0].split(".")[-1]
            if piece:
                names.add(piece)
    return names


def _primary_ann_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return _primary_ann_name(node.value)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value.split("[")[0].split("|")[0].strip().split(".")[-1]
    return None


def _is_route_decorator(node: ast.AST) -> ast.Call | None:
    call = node if isinstance(node, ast.Call) else None
    func = call.func if call is not None else node
    if isinstance(func, ast.Attribute) and func.attr in HTTP_METHODS:
        return call
    return None


def _decorator_path(call: ast.Call | None) -> str | None:
    if call is None:
        return None
    if call.args:
        value = _const_str(call.args[0])
        if value is not None:
            return value
    for kw in call.keywords:
        if kw.arg == "path":
            return _const_str(kw.value)
    return None


def _path_identity_segment(path: str) -> str | None:
    for key in IDENTITY_KEYS:
        needle = "{" + key + "}"
        if needle in path:
            return key
    return None


def _kw_alias(call: ast.Call | None) -> str | None:
    if call is None:
        return None
    for kw in call.keywords:
        if kw.arg == "alias":
            return _const_str(kw.value)
    return None


def _is_injected(arg: ast.arg, default: ast.AST | None) -> bool:
    if _call_name(default) in _INJECTED_DEFAULTS:
        return True
    if _ann_names(arg.annotation) & _INJECTED_ANNOTATIONS:
        return True
    return False


def _model_identity_fields(classdef: ast.ClassDef) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for stmt in classdef.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            name = stmt.target.id
            if name in IDENTITY_PARAM_NAMES:
                hits.append((stmt.lineno, name))
    return hits


def _expr_name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


def _is_request_name(node: ast.AST | None) -> bool:
    return isinstance(node, ast.Name) and node.id == "request"


def _params_attr(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Attribute) and node.attr in ("query_params", "path_params"):
        if _is_request_name(node.value):
            return node.attr
    return None


def _unwrap_await(node: ast.AST) -> ast.AST:
    return node.value if isinstance(node, ast.Await) else node


def _is_request_payload_call(node: ast.AST) -> bool:
    node = _unwrap_await(node)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr in {"json", "body"} and _is_request_name(node.func.value):
            return True
    return False


class _TaintCollector(ast.NodeVisitor):
    """Collect names assigned from request body / query / path containers."""

    def __init__(self, seed: set[str]) -> None:
        self.tainted = set(seed)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._rhs_tainted(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.tainted.add(target.id)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None and self._rhs_tainted(node.value):
            if isinstance(node.target, ast.Name):
                self.tainted.add(node.target.id)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        if self._rhs_tainted(node.value) and isinstance(node.target, ast.Name):
            self.tainted.add(node.target.id)
        self.generic_visit(node)

    def _rhs_tainted(self, node: ast.AST) -> bool:
        node = _unwrap_await(node)
        if _is_request_payload_call(node):
            return True
        if _params_attr(node) is not None:
            return True
        if isinstance(node, ast.Name) and node.id in self.tainted:
            return True
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if name == "loads" and node.args:
                arg = _unwrap_await(node.args[0])
                if _is_request_payload_call(arg):
                    return True
                if isinstance(arg, ast.Name) and arg.id in self.tainted:
                    return True
            if name == "dict" and node.args:
                inner = node.args[0]
                if isinstance(inner, ast.Name) and inner.id in self.tainted:
                    return True
        return False


class _IdentityReadVisitor(ast.NodeVisitor):
    def __init__(self, tainted: set[str], relpath: str) -> None:
        self.tainted = tainted
        self.relpath = relpath
        self.findings: list[Finding] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "get" and node.args:
            key = _const_str(node.args[0])
            if key in IDENTITY_KEYS:
                source = _params_attr(func.value)
                if source is not None:
                    self.findings.append(Finding(
                        self.relpath, node.lineno, "request_container",
                        f"request.{source}.get({key!r}) — identity from "
                        f"{'query' if source == 'query_params' else 'path'} params",
                    ))
                elif self._is_tainted(func.value):
                    self.findings.append(Finding(
                        self.relpath, node.lineno, "body_key",
                        f"request-sourced .get({key!r}) — identity from request body",
                    ))
        if _call_name(node) == "getattr" and len(node.args) >= 2:
            key = _const_str(node.args[1])
            if key in IDENTITY_KEYS and self._is_tainted(node.args[0]):
                self.findings.append(Finding(
                    self.relpath, node.lineno, "body_key",
                    f"getattr(..., {key!r}) on a request-sourced object",
                ))
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        key = _const_str(node.slice)
        if key in IDENTITY_KEYS:
            source = _params_attr(node.value)
            if source is not None:
                self.findings.append(Finding(
                    self.relpath, node.lineno, "request_container",
                    f"request.{source}[{key!r}] — identity from "
                    f"{'query' if source == 'query_params' else 'path'} params",
                ))
            elif self._is_tainted(node.value):
                self.findings.append(Finding(
                    self.relpath, node.lineno, "body_key",
                    f"request-sourced [{key!r}] — identity from request body",
                ))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in IDENTITY_KEYS and self._is_tainted(node.value):
            self.findings.append(Finding(
                self.relpath, node.lineno, "body_key",
                f"request-sourced .{node.attr} — identity from request body",
            ))
        self.generic_visit(node)

    def _is_tainted(self, node: ast.AST) -> bool:
        name = _expr_name(node)
        return name is not None and name in self.tainted


def _iter_args(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[ast.arg, ast.AST | None]]:
    args = list(func.args.args) + list(func.args.kwonlyargs)
    defaults = list(func.args.defaults)
    kw_defaults = list(func.args.kw_defaults)
    positional = args[: len(func.args.args)]
    pad = [None] * (len(positional) - len(defaults))
    pos_defaults = pad + defaults
    out: list[tuple[ast.arg, ast.AST | None]] = []
    for arg, default in zip(positional, pos_defaults):
        out.append((arg, default))
    for arg, default in zip(func.args.kwonlyargs, kw_defaults):
        out.append((arg, default))
    if func.args.vararg is not None:
        out.append((func.args.vararg, None))
    if func.args.kwarg is not None:
        out.append((func.args.kwarg, None))
    return out


def _scan_handler(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    route_call: ast.Call | None,
    relpath: str,
    classes: dict[str, ast.ClassDef],
) -> list[Finding]:
    findings: list[Finding] = []
    path = _decorator_path(route_call)
    if path:
        segment = _path_identity_segment(path)
        if segment is not None:
            findings.append(Finding(
                relpath, func.lineno, "route_path",
                f"route path {path!r} binds {{{segment}}} as a path parameter",
            ))

    seed: set[str] = set()
    for arg, default in _iter_args(func):
        if arg.arg in {"self", "cls"}:
            continue
        injected = _is_injected(arg, default)
        default_name = _call_name(default)
        alias = _kw_alias(default) if default_name in _CLIENT_DEFAULTS else None

        if not injected and arg.arg in IDENTITY_PARAM_NAMES:
            findings.append(Finding(
                relpath, arg.lineno, "handler_param",
                f"handler parameter {arg.arg!r} is client-supplied identity "
                f"(path, query, or body) — derive it from the verified token",
            ))
        if alias in IDENTITY_KEYS:
            findings.append(Finding(
                relpath, arg.lineno, "query_or_path_alias",
                f"handler parameter {arg.arg!r} aliases client identity {alias!r}",
            ))

        if injected:
            continue
        if arg.arg in _REQUEST_BODY_NAMES:
            seed.add(arg.arg)
        if default_name == "Body":
            seed.add(arg.arg)
        ann = _primary_ann_name(arg.annotation)
        if ann and ann not in _SIMPLE_TYPES and ann not in _INJECTED_ANNOTATIONS:
            if ann in {"dict", "Dict", "Mapping", "list", "List"}:
                seed.add(arg.arg)
            classdef = classes.get(ann)
            if classdef is not None:
                seed.add(arg.arg)
                for lineno, field in _model_identity_fields(classdef):
                    findings.append(Finding(
                        relpath, lineno, "model_field",
                        f"body model {ann}.{field} accepts client-supplied identity "
                        f"(used by handler {func.name!r})",
                    ))

    taint = _TaintCollector(seed)
    taint.visit(func)
    reader = _IdentityReadVisitor(taint.tainted, relpath)
    reader.visit(func)
    findings.extend(reader.findings)
    return findings


def _scan_tree(tree: ast.AST, relpath: str) -> list[Finding]:
    classes = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    findings: list[Finding] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        route_call = None
        for dec in node.decorator_list:
            route_call = _is_route_decorator(dec)
            if route_call is not None or (
                isinstance(dec, ast.Attribute) and dec.attr in HTTP_METHODS
            ):
                if route_call is None and isinstance(dec, ast.Call):
                    route_call = dec
                findings.extend(_scan_handler(node, route_call, relpath, classes))
                break
    return findings


def scan_file(path: Path, relpath: str) -> list[Finding]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [Finding(relpath, 1, "parse_error", f"unreadable: {exc}")]
    try:
        tree = ast.parse(source, filename=relpath)
    except SyntaxError as exc:
        return [Finding(relpath, exc.lineno or 1, "parse_error", f"unparseable: {exc.msg}")]
    return _scan_tree(tree, relpath)


def scan(root: Path | None = None) -> list[Finding]:
    base = Path(root) if root is not None else ROOT
    findings: list[Finding] = []
    for sub in SCAN_ROOTS:
        folder = base / sub
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.py")):
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            relpath = path.relative_to(base).as_posix()
            findings.extend(scan_file(path, relpath))
    findings.sort(key=lambda f: (f.path, f.lineno, f.kind, f.detail))
    return findings


# ── Selftest (synthetic mutation proof) ──────────────────────────────────────

_CLEAN = textwrap.dedent(
    """\
    from fastapi import APIRouter, Depends, Header, Query, Request
    from pydantic import BaseModel

    router = APIRouter()

    class Ticket(BaseModel):
        subject: str
        email: str

    def _helper(user_id: str) -> str:
        return user_id

    @router.get("/api/me")
    def me(user: dict = Depends(require_user)):
        user_id = user.get("id") or user.get("email") or ""
        return {"id": user_id}

    @router.get("/api/brain/runs/{run_id}")
    def run_detail(run_id: str, user: dict = Depends(require_user)):
        uid = user.get("id")
        return {"run_id": run_id, "uid": uid}

    @router.get("/api/search")
    def search(q: str = Query(""), authorization: str | None = Header(default=None)):
        return {"q": q}

    @router.post("/api/support")
    def support(body: Ticket, request: Request, user: dict = Depends(require_user)):
        user_id = (user or {}).get("id")
        row = {"user_id": user_id, "subject": body.subject}
        return row
    """
)

_BAD_PARAM = textwrap.dedent(
    """\
    from fastapi import APIRouter
    router = APIRouter()

    @router.get("/api/whoami")
    def whoami(user_id: str):
        return {"user_id": user_id}
    """
)

_BAD_PATH = textwrap.dedent(
    """\
    from fastapi import APIRouter
    router = APIRouter()

    @router.get("/api/users/{user_id}")
    def get_user(name: str):
        return {"name": name}
    """
)

_BAD_QUERY_ALIAS = textwrap.dedent(
    """\
    from fastapi import APIRouter, Query
    router = APIRouter()

    @router.get("/api/who")
    def who(ident: str = Query(..., alias="user_id")):
        return {"ident": ident}
    """
)

_BAD_BODY_GET = textwrap.dedent(
    """\
    from fastapi import APIRouter, Body
    router = APIRouter()

    @router.post("/api/act")
    def act(payload: dict = Body(default=None)):
        user_id = payload.get("user_id")
        return {"user_id": user_id}
    """
)

_BAD_QUERY_PARAMS = textwrap.dedent(
    """\
    from fastapi import APIRouter, Request
    router = APIRouter()

    @router.get("/api/act")
    def act(request: Request):
        user_id = request.query_params.get("user_id")
        return {"user_id": user_id}
    """
)

_BAD_JSON_BODY = textwrap.dedent(
    """\
    from fastapi import APIRouter, Request
    import json
    router = APIRouter()

    @router.post("/api/act")
    async def act(request: Request):
        data = json.loads(await request.body())
        user_id = data["user_id"]
        return {"user_id": user_id}
    """
)

_BAD_MODEL = textwrap.dedent(
    """\
    from fastapi import APIRouter
    from pydantic import BaseModel
    router = APIRouter()

    class Hack(BaseModel):
        user_id: str
        note: str

    @router.post("/api/hack")
    def hack(body: Hack):
        return {"note": body.note}
    """
)

_BAD_ACCOUNT = textwrap.dedent(
    """\
    from fastapi import APIRouter
    router = APIRouter()

    @router.get("/api/acct")
    def acct(account_id: str):
        return {"account_id": account_id}
    """
)


def selftest() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="no_client_id_") as tmp:
        root = Path(tmp)
        app = root / "app"
        app.mkdir()
        (app / "__init__.py").write_text("", encoding="utf-8")
        (app / "clean.py").write_text(_CLEAN, encoding="utf-8")

        clean = [f for f in scan(root) if f.path.endswith("clean.py")]
        if clean:
            failures.append(f"clean fixture flagged: {clean}")
        else:
            print("  [PASS] token-derived identity + resource path + helper param are clean")

        cases = (
            ("bad_param.py", _BAD_PARAM, "handler_param"),
            ("bad_path.py", _BAD_PATH, "route_path"),
            ("bad_alias.py", _BAD_QUERY_ALIAS, "query_or_path_alias"),
            ("bad_body.py", _BAD_BODY_GET, "body_key"),
            ("bad_query.py", _BAD_QUERY_PARAMS, "request_container"),
            ("bad_json.py", _BAD_JSON_BODY, "body_key"),
            ("bad_model.py", _BAD_MODEL, "model_field"),
            ("bad_account.py", _BAD_ACCOUNT, "handler_param"),
        )
        for name, source, kind in cases:
            (app / name).write_text(source, encoding="utf-8")
            hits = [f for f in scan(root) if f.path.endswith(name)]
            if any(f.kind == kind for f in hits):
                print(f"  [PASS] {name} → {kind}")
            else:
                failures.append(f"{name} did not produce {kind}: {hits}")

    live = scan(ROOT)
    if live:
        failures.append(
            "live tree is not clean (selftest refuses to bless a red guard): "
            + "; ".join(f.render() for f in live[:8])
        )
    else:
        print("  [PASS] live app/ tree is clean")

    if failures:
        print("\nSELFTEST FAILED:")
        for item in failures:
            print(f"  - {item}")
        return 1
    print("selftest OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help="Repo root (default: parent of scripts/)",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Plant synthetic violations and prove the guard goes red, then green",
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    findings = scan(args.root.resolve())
    if not findings:
        print(
            "check_no_client_supplied_identity: OK — no route handler derives "
            "user identity from request body, query, or path."
        )
        return 0

    for finding in findings:
        print(finding.render(), file=sys.stderr)
    print(
        f"::error title=no-client-supplied-identity::"
        f"{len(findings)} handler(s) derive user identity from the client. "
        f"_pg() uses SUPABASE_SERVICE_ROLE_KEY (bypasses RLS); identity must "
        f"come from the verified token only.",
        flush=True,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
