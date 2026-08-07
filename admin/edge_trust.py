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
from pathlib import Path

# The ranges file ships WITH THE CODE, so resolve it against the package's repo and
# never against paths.ROOT (which MACRO_ADMIN_ROOT can redirect at a seeded data dir).
_RANGES_FILE = Path(__file__).resolve().parent.parent / "config" / "edgeone_origin_ranges.json"

EDGE_SECRET_HEADER = "X-MM-Edge-Auth"
EDGE_CLIENT_HEADER = "EO-Connecting-IP"

# Widest range that may ever be trusted as "the edge". A real origin-pull list is made
# of small blocks (the observed peers sit in 42 distinct /24s), so these floors admit
# any plausible authoritative list while refusing the shapes that would hand trust to
# the whole internet — including the literal 0.0.0.0/0 + ::/0 that the deprecated
# api.edgeone.ai/ips endpoint now serves. Deliberately NOT env-tunable: a security
# floor that a config file can lower is not a floor.
_MIN_PREFIX = {4: 16, 6: 32}


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
    """
    nets = []
    for raw in values:
        text = str(raw).strip()
        if not text or text.startswith("#"):
            continue
        try:
            net = ipaddress.ip_network(text, strict=False)
        except ValueError:
            continue
        if _safe_network(net):
            nets.append(net)
    return tuple(nets)


def _file_ranges() -> tuple:
    try:
        blob = json.loads(_RANGES_FILE.read_text())
    except Exception:  # noqa: BLE001 — a missing/broken list means "no attestation"
        return ()
    if isinstance(blob, dict):
        blob = blob.get("ranges") or []
    if not isinstance(blob, list):
        return ()
    return _parse_networks(blob)


def edge_origin_networks() -> tuple:
    """Configured EdgeOne origin-pull ranges. Env wins; empty tuple means unconfigured.

    Read on every call rather than cached: the admin service is a single low-traffic
    process, and a cache would make the operator restart it to widen the list after
    pasting fresh ranges out of the EdgeOne console.
    """
    raw = _env("ADMIN_EDGE_ORIGIN_CIDRS")
    if raw:
        return _parse_networks(raw.replace(";", ",").split(","))
    return _file_ranges()


def _header(headers, name: str) -> str:
    """Case-insensitive header read that works for both a real HTTPMessage and a dict."""
    if headers is None:
        return ""
    getter = getattr(headers, "get", None)
    if getter is None:
        return ""
    val = getter(name)
    if val is None:  # plain dicts are case-SENSITIVE; HTTPMessage is not
        lowered = name.lower()
        for k, v in (headers.items() if hasattr(headers, "items") else []):
            if str(k).lower() == lowered:
                val = v
                break
    return (val or "").strip()


def _secret_ok(headers) -> bool:
    secret = _env("ADMIN_EDGE_SECRET")
    if not secret:
        return False
    # Compare as BYTES: hmac.compare_digest raises TypeError on a str containing any
    # non-ASCII codepoint, and the header is caller-supplied — a 500 on the login route
    # would be a remotely triggerable outage, not a rejection.
    return hmac.compare_digest(_header(headers, EDGE_SECRET_HEADER).encode("utf-8", "replace"),
                               secret.encode("utf-8", "replace"))


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
    """
    raw = _header(headers, EDGE_CLIENT_HEADER)
    if not raw:
        return None
    # EdgeOne sends a single address, but tolerate a list form and take the FIRST
    # element: unlike X-Forwarded-For this header is written by the edge, not
    # appended to by each hop, so element 0 is the edge's own value.
    candidate = raw.split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


def resolve_client_id(peer: str, headers) -> str:
    """Per-client identity for throttling: the edge-attested visitor, else the peer."""
    if from_edge(peer, headers):
        attested = edge_client_ip(headers)
        if attested:
            return attested
    return peer
