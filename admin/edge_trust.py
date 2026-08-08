"""Did this request reach us THROUGH the CDN edge, or direct-to-origin?

Everything in the admin console that treats an IP as an identity — the per-client
login lockout in ``auth.password_ok``, the site-gate self-allow list — depends on
being able to answer that question, and it stopped being answerable when
admin.mastermind-x.com moved behind the TencentEdgeOne edge.

WHY THIS EXISTS (measured 2026-08-07, not theoretical). ``app/deploy/Caddyfile``
injects ``X-Admin-Client-IP {remote_host}`` — the verified TCP peer, with
``header_up`` REPLACING any caller-supplied value so it cannot be spoofed. That is
still exactly right and this module does not change it. What changed is what the
peer MEANS: admin is edge-proxied (CNAME -> admin.mastermind-x.com.eo.dnse3.com),
so for every visitor arriving through the edge the peer is an EdgeOne origin-pull
address, not the visitor. All edge-borne traffic therefore shared ONE lockout
bucket, which inverted ``auth.py``'s stated property — "one attacker can only lock
out *themselves*" — into an anonymous operator-lockout DoS: five wrong passwords
from anywhere on the internet locked the operator out of their own console.

WHAT THE EDGE ACTUALLY SETS, and why only one header is usable. Probing the live
host through the edge with every real-client header forged (2026-08-07, headers
captured off the loopback hop to :8787 with tcpdump):

    sent through the edge        arrived at the origin as
    EO-Connecting-IP: 203.0.113.77   ->  104.36.50.44   (OVERWRITTEN — true client)
    EO-Client-IP:     203.0.113.99   ->  203.0.113.99   (passed through — FORGED)
    True-Client-IP:   203.0.113.66   ->  203.0.113.66   (passed through — FORGED)
    X-Real-IP:        203.0.113.55   ->  203.0.113.55   (passed through — FORGED)
    CF-Connecting-IP: 203.0.113.44   ->  203.0.113.44   (passed through — FORGED)
    X-Forwarded-For:  198.51.100.7   ->  <dropped by the edge; Caddy re-set to peer>

So ``EO-Connecting-IP`` is the ONLY header the edge rewrites, and it is the only
one this module will ever read. A clean edge request carries no ``EO-Client-IP`` at
all — the EdgeOne "Client IP Header" rule that ``app/main.py`` expects is not
active on this zone — so reading that header would have handed a brute-forcer a
free bucket-rotation knob. Do not add it here.

THE PEER CHECK IS THE WHOLE SECURITY PROPERTY. ufw permits 80,443/tcp from
Anywhere, so anyone can reach the origin directly and send whatever
``EO-Connecting-IP`` they like. A forwarded header is worth reading only once the
TCP PEER has been established as an edge address by something the caller does not
control. That is what this module decides, and it fails safe: when it cannot
attest the peer, callers keep using the verified peer as the identity, which is
the pre-existing behaviour and gives up nothing that worked before.

TWO INDEPENDENT ATTESTATIONS, EITHER SUFFICIENT, BOTH OFF BY DEFAULT:

  1. ``ADMIN_EDGE_SECRET`` — a shared secret the EdgeOne console injects on
     origin-pull as ``X-MM-Edge-Auth`` (Rules Engine -> "modify origin-pull request
     header"). Compared in constant time. This is the CIDR-FREE path and the one to
     prefer: it needs no IP list, so it cannot rot, and it is unaffected by the
     edge adding nodes. A direct-to-origin caller cannot produce the header without
     the secret. Runbook: ``app/deploy/README.md`` § "Admin per-client identity".

  2. ``ADMIN_EDGE_ORIGIN_CIDRS`` (or ``config/edgeone_origin_ranges.json``) — the
     EdgeOne origin-pull ranges, for an operator who has pulled them from the
     console's Origin Protection page / the ``DescribeOriginProtection`` API.

BOTH DEFAULT TO EMPTY ON PURPOSE, and mechanism 2 has no shipped list, because as of
2026-08-07 there is NO usable authoritative EdgeOne origin-pull range list:

  * ``https://api.edgeone.ai/ips`` was the credential-free published list. It is
    DEPRECATED — fetched 2026-08-07 it answers 200 with, in full:
        # [DEPRECATION NOTICE] This interface stopped serving on 2026-07-31 and
        # will be officially offline on 2026-08-31. Please migrate in time.
        0.0.0.0/0
        ::/0
    Read that twice. The dead endpoint serves a DEFAULT ROUTE as its payload, so any
    refresh job that ingests it without rejecting blanket ranges silently produces a
    trust-EVERYTHING allowlist. For a firewall that is merely useless; here it would
    be catastrophic, because every direct-to-origin caller would become "the edge"
    and could forge its own identity at will. ``_safe_network`` below refuses such
    entries unconditionally, and that refusal is not configurable.
  * The successor, ``DescribeOriginACL`` (teo 2022-09-01, replacing the deprecated
    ``DescribeOriginProtection``), needs Tencent Cloud SecretId/SecretKey. This
    infrastructure holds no such credential (no TENCENT/EDGEONE/QCLOUD key in any
    /etc/macro-*.env, no tccli on the VPS), so it cannot be pulled here today.

A GUESSED range is worse than no range. Too NARROW merely degrades to the old
peer-keyed behaviour; too BROAD is exploitable — the observed origin-pull addresses
sit in Tencent /16s under AS139341 that also host rentable Tencent Cloud VMs, and
none of the 378 observed peers has a PTR record to distinguish an edge node from a
neighbour. Under-trusting costs availability; over-trusting costs the throttle.
This module refuses to guess. Mechanism 1 is the one to actually turn on.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import os
import sys
import threading
from pathlib import Path

# The ranges file ships WITH THE CODE, so resolve it against the package's repo and
# never against paths.ROOT (which MACRO_ADMIN_ROOT can redirect at a seeded data dir).
_RANGES_FILE = Path(__file__).resolve().parent.parent / "config" / "edgeone_origin_ranges.json"

EDGE_SECRET_HEADER = "X-MM-Edge-Auth"
EDGE_CLIENT_HEADER = "EO-Connecting-IP"

# Widest range that may ever be trusted as "the edge". Deliberately TIGHTER than the
# aggregates this edge is observed in: the origin-pull peers sit in 42 distinct /24s,
# but the /16s those roll up to (43.175.0.0/16, 43.174.0.0/16, 101.33.0.0/16 …) also
# carry rentable Tencent Cloud instances, so accepting a /16 would let anyone who rents
# a VM in one satisfy the peer check and forge their own identity — the exact hazard
# this module's header argues against. A /16 floor would have accepted precisely that
# shape, which is why these are /20 and /40 instead. They still admit any plausible
# authoritative list, whose entries are small blocks.
#
# If a published range is genuinely broader than this, split it into the sub-blocks
# actually used for origin-pull rather than lowering the floor. Deliberately NOT
# env-tunable: a security floor that a config file can lower is not a floor.
_MIN_PREFIX = {4: 20, 6: 40}

_RANGES_CACHE_LOCK = threading.Lock()
_ranges_cache: tuple = ()          # (mtime, size, parsed) or ()


def _warn(msg: str) -> None:
    """Refusals must be visible. A silently dropped range is an allowlist that quietly
    does nothing, and this module is the one place where 'nothing' looks like 'fine'.
    Plain stderr, not a ::warning annotation — this never runs inside an Actions step.
    """
    print(f"admin.edge_trust: {msg}", file=sys.stderr, flush=True)


def _env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _safe_network(net) -> bool:
    """Refuse blanket, private, and non-routable entries however they got into the list.

    This is the last line of defence between a poisoned or misread range source and a
    trust-everything allowlist, so it re-checks properties the caller may believe are
    already guaranteed. Cheap, and the failure it prevents is total.
    """
    if net.prefixlen < _MIN_PREFIX.get(net.version, 128):
        return False
    return not (net.is_private or net.is_loopback or net.is_link_local
                or net.is_multicast or net.is_reserved or net.is_unspecified)


def _parse_networks(values) -> tuple:
    """Parse CIDRs / bare IPs, dropping anything malformed or unsafe rather than raising.

    A bad entry must never take the console down and must never widen trust: an
    unparseable or over-broad range is simply absent, which fails safe to peer keying.
    Every drop is announced, so a list that silently attests nothing is diagnosable.
    """
    nets = []
    for raw in values:
        text = str(raw).strip()
        if not text or text.startswith("#"):
            continue
        try:
            net = ipaddress.ip_network(text, strict=False)
        except ValueError:
            _warn(f"REFUSED unparseable edge range {text!r}")
            continue
        if _safe_network(net):
            nets.append(net)
        else:
            _warn(f"REFUSED unsafe edge range {net} — blanket, private or broader than "
                  f"/{_MIN_PREFIX.get(net.version)}; it attests nothing")
    return tuple(nets)


def _file_ranges() -> tuple:
    """Ranges from the checked-in file, re-parsed only when the file actually changes.

    Cached on (mtime, size) rather than read per request: this sits on the pre-auth
    login path. The operator still needs no restart to widen the list — editing the
    file changes its stat and the next request re-reads it.
    """
    global _ranges_cache
    try:
        st = _RANGES_FILE.stat()
        stamp = (st.st_mtime_ns, st.st_size)
    except OSError:
        return ()
    with _RANGES_CACHE_LOCK:
        if _ranges_cache and _ranges_cache[0] == stamp:
            return _ranges_cache[1]
    try:
        blob = json.loads(_RANGES_FILE.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — a broken list means "no attestation"
        _warn(f"could not read {_RANGES_FILE.name} ({exc}); no ranges will attest")
        return ()
    if isinstance(blob, dict):
        blob = blob.get("ranges") or []
    parsed = _parse_networks(blob) if isinstance(blob, list) else ()
    with _RANGES_CACHE_LOCK:
        _ranges_cache = (stamp, parsed)
    return parsed


def edge_origin_networks() -> tuple:
    """Configured EdgeOne origin-pull ranges. Env wins; empty tuple means unconfigured."""
    raw = _env("ADMIN_EDGE_ORIGIN_CIDRS")
    if raw:
        return _parse_networks(raw.replace(";", ",").split(","))
    return _file_ranges()


def _header_values(headers, name: str) -> list:
    """EVERY value sent for a header, in wire order.

    Duplicates matter here. `HTTPMessage.get()` returns the FIRST occurrence, which is
    the attacker's copy whenever an upstream appends rather than replaces — the same
    first-hop trap `_verified_peer` already avoids for X-Forwarded-For. Callers below
    pick deliberately; nothing reads element 0 by accident.
    """
    if headers is None:
        return []
    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        try:
            vals = get_all(name)
        except Exception:  # noqa: BLE001
            vals = None
        return [str(v).strip() for v in (vals or [])]
    getter = getattr(headers, "get", None)
    if getter is None:
        return []
    val = getter(name)
    if val is None:  # plain dicts are case-SENSITIVE; HTTPMessage is not
        lowered = name.lower()
        for k, v in (headers.items() if hasattr(headers, "items") else []):
            if str(k).lower() == lowered:
                val = v
                break
    return [str(val).strip()] if val is not None else []


def _secret_ok(headers) -> bool:
    """Constant-time match against ANY copy of the header the caller sent.

    Checking every occurrence rather than the first is safe — a match still requires
    knowing the secret — and it stops an attacker from DISABLING attestation by
    prepending a junk copy, which would silently drop us back to the shared bucket.
    """
    secret = _env("ADMIN_EDGE_SECRET")
    if not secret:
        return False
    # http.server decodes headers as latin-1, so a non-ASCII secret can never match what
    # arrives on the wire. Refuse loudly instead of failing shut forever in silence.
    try:
        want = secret.encode("ascii")
    except UnicodeEncodeError:
        _warn("ADMIN_EDGE_SECRET is not ASCII; it can never match a wire header — "
              "attestation is DISABLED until it is replaced with an ASCII token")
        return False
    return any(hmac.compare_digest(v.encode("latin-1", "replace"), want)
               for v in _header_values(headers, EDGE_SECRET_HEADER))


def _peer_in_ranges(peer: str) -> bool:
    nets = edge_origin_networks()
    if not nets:
        return False
    try:
        addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(addr in net for net in nets)


def from_edge(peer: str, headers) -> bool:
    """True only when the request is ATTESTED to have come through the CDN edge.

    ``peer`` must be the verified TCP peer (Caddy's ``X-Admin-Client-IP``), never a
    value the caller supplied — attesting a caller-controlled address would let a
    direct-to-origin client nominate itself as the edge.
    """
    if _secret_ok(headers):
        return True
    return bool(peer) and _peer_in_ranges(peer)


def edge_client_ip(headers) -> str | None:
    """The edge's own attestation of the visitor's address, or None.

    Only meaningful once ``from_edge`` has said yes. Anything that is not a
    syntactically valid IP is discarded, so a junk header degrades to peer keying
    rather than minting an attacker-chosen bucket name.

    TAKE THE LAST VALUE, AND ITS LAST ELEMENT. Probing the live edge on 2026-08-07
    showed it REPLACES this header (a forged copy did not survive; exactly one
    EO-Connecting-IP reached the origin, carrying the true client), under which last
    and first are the same thing. But Tencent documents the replace behaviour nowhere,
    and documents the sibling X-Forwarded-For as APPEND-only — so if this header ever
    behaves the same way, the edge's value is the LAST one and the attacker's is
    first. Last is correct under both behaviours; first is correct under only one and
    hands out unlimited bucket rotation under the other.
    """
    values = _header_values(headers, EDGE_CLIENT_HEADER)
    for raw in reversed(values):
        for part in reversed(raw.split(",")):
            part = part.strip()
            if not part:
                continue
            try:
                return str(ipaddress.ip_address(part))
            except ValueError:
                return None      # a malformed trailing value is not a licence to
                                 # fall back to an earlier, attacker-supplied one
    return None


def resolve_client_id(peer: str, headers) -> str:
    """Per-client identity for throttling: the edge-attested visitor, else the peer."""
    if from_edge(peer, headers):
        attested = edge_client_ip(headers)
        if attested:
            return attested
    return peer
