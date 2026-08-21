#!/usr/bin/env python3
"""Production Caddy topology guard for ``GET /api/hub/prophet`` (Sol Day-6
AMENDMENT clause F, DEC:B1-PROPHET-PUBLIC-SPLIT).

``app/prophet_lab.py::_hub_prophet_authorized`` denies ``/api/hub/prophet``
unless BOTH:

  1. the TCP peer is loopback (127.0.0.1 / ::1), AND
  2. the request carries NO ``X-MM-Peer`` header.

That guard's whole trust model rests on a fact that used to live only in
prose comments: Caddy's ``reverse_proxy /api/* 127.0.0.1:8000`` block REPLACES
any inbound ``X-MM-Peer`` with ``header_up X-MM-Peer {remote_host}``, so a
request that arrives through the public edge ALWAYS carries the header by the
time uvicorn sees it — even though its TCP peer also reads 127.0.0.1 (Caddy
sits in front of every request). A direct same-box call bypassing Caddy
carries no such header. If a FUTURE Caddyfile edit ever adds a new
``reverse_proxy ... 127.0.0.1:8000`` block that does NOT stamp that header and
does NOT rewrite the caller's path to something fixed and non-hub, an
attacker who can reach that block from off-box gets a headerless,
loopback-peer request into uvicorn — indistinguishable, from
``_hub_prophet_authorized``'s point of view, from a legitimate direct call —
and ``/api/hub/prophet`` (which carries no auth of its own) becomes reachable
from the public internet. This module makes that topology fact mechanical
instead of prose: it parses the shipped Caddyfile, finds every proxy block
whose upstream is the macro-api backend on port 8000, and classifies it.

CLASSIFICATION (see ``classify_backend_proxies``)
    SAFE_PEER_STAMPED  — the block contains
        ``header_up X-MM-Peer {remote_host}``. Caddy replaces any inbound
        value, so every request through this proxy is stamped and
        ``_hub_prophet_authorized`` denies it regardless of path.
    SAFE_FIXED_REWRITE — the block contains a ``rewrite <path>`` to a
        CONSTANT path that is not under ``/api/hub/``. The caller's own
        request path can therefore never select the hub route through this
        proxy, no matter what it sends.
    UNSAFE — anything else: a proxy that forwards the client's path to
        :8000 with no peer stamp and no fixed rewrite is a headerless,
        loopback-looking path into uvicorn — exactly the shape
        ``_hub_prophet_authorized`` cannot distinguish from a legitimate
        direct call. Also UNSAFE, unconditionally, regardless of the header
        stamp: a block whose ``rewrite`` target is itself under
        ``/api/hub/`` — see ``main()``'s exit code.

RESIDUAL — what this guard does NOT cover
    * A change made directly on the box to the deployed
      ``/etc/caddy/Caddyfile`` that never lands in this repo's
      ``app/deploy/Caddyfile`` — this guard only ever sees the committed
      source, never live production config.
    * Any OTHER listener bound to :8000 outside Caddy's control (a rogue
      process, a second reverse proxy, a container port mapping) — Caddy
      being correctly configured says nothing about who else might be
      listening on that port.
    * A Caddyfile directive this parser does not model (e.g. an
      ``import``ed snippet file, or a non-``reverse_proxy`` mechanism that
      reaches :8000) — ``main()`` treats zero discovered backend proxies as
      a failure specifically so a silently-dropped or silently-restructured
      block cannot pass vacuously (see clause F: "a future generic
      reverse_proxy :8000 block cannot silently bypass the hub guard").
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CADDYFILE = REPO_ROOT / "app" / "deploy" / "Caddyfile"

_BACKEND_HOST_RE = r"(?:127\.0\.0\.1|localhost|\[::1\])"
_BACKEND_TARGET_RE = re.compile(rf"{_BACKEND_HOST_RE}\s*:\s*8000\b")
_REVERSE_PROXY_RE = re.compile(r"\breverse_proxy\b")
_HEADER_UP_PEER_RE = re.compile(r"header_up\s+X-MM-Peer\s+\{remote_host\}")
_REWRITE_RE = re.compile(r"\brewrite\s+(\S+)")

SAFE_PEER_STAMPED = "SAFE_PEER_STAMPED"
SAFE_FIXED_REWRITE = "SAFE_FIXED_REWRITE"
UNSAFE = "UNSAFE"


@dataclass(frozen=True)
class ProxyBlock:
    line: int
    upstream: str
    has_header_up_peer: bool
    rewrite_targets: tuple[str, ...]
    classification: str
    reasons: tuple[str, ...]


def _strip_comment(line: str) -> str:
    """Drop a trailing ``# ...`` comment token. Caddyfile comments in this
    repo always begin at a token boundary (start of line or after
    whitespace), so this intentionally does not try to parse quoted strings
    — matching this file's own style is enough to keep brace-counting sane.
    """
    return re.sub(r"(^|\s)#.*$", "", line)


def classify_backend_proxies(text: str) -> list[ProxyBlock]:
    """Find every ``reverse_proxy`` directive targeting the macro-api
    backend (127.0.0.1 / localhost / [::1] on :8000) and classify it.

    Pure text/line parsing — no file I/O — so tests can feed it synthetic
    Caddyfile snippets directly.
    """
    lines = text.splitlines()
    n = len(lines)
    results: list[ProxyBlock] = []
    i = 0
    while i < n:
        code_line = _strip_comment(lines[i])
        if _REVERSE_PROXY_RE.search(code_line) and _BACKEND_TARGET_RE.search(code_line):
            start_line_no = i + 1
            host_match = _BACKEND_TARGET_RE.search(code_line)
            upstream = re.sub(r"\s+", "", host_match.group(0)) if host_match else "unknown:8000"

            block_lines: list[str] = []
            if code_line.rstrip().endswith("{"):
                depth = 1
                j = i + 1
                while j < n and depth > 0:
                    cl = _strip_comment(lines[j])
                    depth += cl.count("{") - cl.count("}")
                    if depth > 0:
                        block_lines.append(lines[j])
                    j += 1
                i = j
            else:
                # Bare single-line directive — no block at all.
                i += 1

            block_text = "\n".join(block_lines)
            has_peer = bool(_HEADER_UP_PEER_RE.search(block_text))
            rewrite_targets = tuple(_REWRITE_RE.findall(block_text))
            hub_rewrites = tuple(t for t in rewrite_targets if t.startswith("/api/hub/"))

            # A rewrite only makes the block safe when its target is a CONSTANT
            # path. `rewrite {http.request.uri}` / `rewrite {path}` re-emit the
            # caller's own path, so the caller still chooses the upstream route —
            # exactly the pass-through this guard exists to reject. Treat any
            # placeholder-bearing or non-absolute target as no rewrite at all.
            non_constant = tuple(
                t for t in rewrite_targets if "{" in t or not t.startswith("/")
            )
            constant_rewrites = tuple(
                t for t in rewrite_targets if t not in non_constant
            )

            reasons: tuple[str, ...]
            if hub_rewrites:
                classification = UNSAFE
                reasons = (
                    f"rewrite target under /api/hub/ inside a :8000 proxy block: {', '.join(hub_rewrites)}",
                )
            elif non_constant and not has_peer:
                classification = UNSAFE
                reasons = (
                    "rewrite target is not a constant path "
                    f"({', '.join(non_constant)}) — the caller's own path still "
                    "selects the upstream route, so /api/hub/* stays reachable",
                )
            elif has_peer:
                classification = SAFE_PEER_STAMPED
                reasons = ()
            elif constant_rewrites:
                classification = SAFE_FIXED_REWRITE
                reasons = ()
            else:
                classification = UNSAFE
                reasons = (
                    "no 'header_up X-MM-Peer {remote_host}' stamp and no fixed 'rewrite' target — "
                    "the caller's own path/headers pass through to :8000 unmarked",
                )

            results.append(
                ProxyBlock(
                    line=start_line_no,
                    upstream=upstream,
                    has_header_up_peer=has_peer,
                    rewrite_targets=rewrite_targets,
                    classification=classification,
                    reasons=reasons,
                )
            )
            continue
        i += 1
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="Repository root (used to locate app/deploy/Caddyfile unless --caddyfile is given).",
    )
    parser.add_argument(
        "--caddyfile",
        default=None,
        help="Explicit path to the Caddyfile to check (default: <root>/app/deploy/Caddyfile).",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    caddyfile = Path(args.caddyfile).resolve() if args.caddyfile else (root / "app" / "deploy" / "Caddyfile")

    if not caddyfile.is_file():
        print(f"::error title=caddy-hub-boundary::Caddyfile not found at {caddyfile}", flush=True)
        return 1

    text = caddyfile.read_text(encoding="utf-8")
    proxies = classify_backend_proxies(text)

    for p in proxies:
        print(
            f"::notice title=caddy-hub-boundary::{caddyfile}:{p.line} {p.upstream} -> {p.classification}",
            flush=True,
        )

    unsafe = [p for p in proxies if p.classification == UNSAFE]
    for p in unsafe:
        reason = "; ".join(p.reasons)
        print(
            f"::error title=caddy-hub-boundary::{caddyfile}:{p.line} {p.upstream} classified UNSAFE "
            f"— {reason} — this is a headerless, loopback-looking path into uvicorn that "
            f"_hub_prophet_authorized (app/prophet_lab.py) cannot distinguish from a legitimate "
            f"direct same-box call.",
            flush=True,
        )

    if not proxies:
        print(
            "::error title=caddy-hub-boundary::found ZERO :8000 backend reverse_proxy blocks in "
            f"{caddyfile} — a guard that cannot see any topology cannot vouch for it (silently-dropped "
            "or silently-restructured directive would otherwise pass vacuously)",
            flush=True,
        )
        return 1

    if unsafe:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
