"""Which forwarded header actually carries the visitor, on the PUBLIC (www) zone.

The app keys per-visitor throttles and stamps analytics rows on "the client IP".
Every one of those decisions is only as good as the header it reads, and the four
headers this module refuses are attacker-suppliable — so the refusals are the
security property, not a style preference.

WHY THIS EXISTS (measured 2026-08-07 on www.mastermind-x.com, not theoretical).
``app/main.py`` resolved the visitor from the first non-empty of
``EO-Client-IP`` -> ``EO-Connecting-IP`` -> ``CF-Connecting-IP`` ->
``True-Client-IP`` -> ``X-Forwarded-For``[0] -> ``X-Real-IP``. Five of those six
are forwarded verbatim from whatever the caller sent, and ufw permits 80,443/tcp
from Anywhere — so any direct-to-origin client could nominate its own identity and
rotate it per request, minting a fresh rate-limit bucket every time.

WHAT THE EDGE ACTUALLY DOES, PER ZONE. Probing the live hosts with every
real-client header forged, headers captured off the loopback hop with tcpdump:

    header               www (this module)          admin (admin/edge_trust.py)
    EO-Connecting-IP     REPLACED — true client     REPLACED — true client
    EO-Client-IP         REPLACED — true client     passed through — FORGED
    True-Client-IP       passed through — FORGED    passed through — FORGED
    X-Real-IP            passed through — FORGED    passed through — FORGED
    CF-Connecting-IP     passed through — FORGED    passed through — FORGED
    X-Forwarded-For      dropped by the edge; Caddy re-sets it to the TCP peer

THE TWO ZONES DISAGREE, so read the row for the host you are on. The EdgeOne
"Client IP Header" rule IS active on www — a clean www request carries
``EO-Client-IP``, and a forged one arrives overwritten — and it is NOT active on
admin, where a clean request carries no ``EO-Client-IP`` at all and a forged one
sails through. ``admin/edge_trust.py``'s header (written from the admin probe
alone) is right about admin and must not be read as a statement about www.

``EO-Connecting-IP`` is the ONLY header edge-overwritten on BOTH zones, which is
why it is the only forwarded header this module will read. That intersection is
the point: a resolver that trusted ``EO-Client-IP`` would be correct on www today
and silently forgeable the moment a surface moves to a zone without that console
rule — which is exactly the difference that produced this bug.

WHAT THIS DOES AND DOES NOT BUY. Through the edge the resolved identity is now
UNFORGEABLE: the edge replaces (never appends) ``EO-Connecting-IP``, so a caller
cannot displace it or rotate it. Direct-to-origin it remains caller-chosen — that
is unfixable by header reading alone, and this module does not pretend otherwise.
It is bounded instead by the OTHER half of the dual-key design: a direct-to-origin
caller's ``X-MM-Peer`` is their own address, so ``app/support.py::_rate_ok`` and
``app/company_intelligence.py`` still hold them to the trusted-peer budget. The
claimed key stops being free to rotate for edge traffic, which is where the real
traffic is; the peer key keeps bounding everyone else.

NO CIDR GUESSING, AND NO ATTESTATION REQUIRED HERE. ``admin/edge_trust.py`` needs
an attested peer because on admin the edge sets no per-visitor header at all, so
the choice there is "attested visitor or shared peer bucket". www has no such
dilemma: the edge writes a true per-visitor value into ``EO-Connecting-IP`` for
every edge request, so reading it needs no allowlist to be safe against a caller
behind the edge. Gating it on attestation would be strictly WORSE here — with no
attestation configured (there is none, and edge_trust documents why a range list
cannot be pulled today) every edge visitor would collapse into one shared bucket
and 5 wrong support tickets from anywhere would lock out every CN visitor at once.
That is precisely the operator-lockout DoS #4922 fixed for admin, re-created on
the public site. Do not "harden" this by routing it through ``from_edge``.

FALLBACK ORDER, and why each rung is where it is:

  1. ``EO-Connecting-IP`` — edge-written, forge-proof through the edge (above).
  2. ``X-MM-Peer`` — Caddy's ``header_up X-MM-Peer {remote_host}``, the verified TCP
     peer with any inbound copy REPLACED, so a caller cannot set it. Coarse behind
     the edge (it is the edge node), exact for a direct-to-origin caller — which is
     the direction that matters, because that is the caller who has no honest
     ``EO-Connecting-IP``.
  3. ``X-Forwarded-For``, LAST element — measured equal to (2) in production: the
     edge drops the inbound chain and Caddy re-sets it to the peer, because the
     edge arrives from public addresses and ``trusted_proxies static private_ranges``
     therefore does not trust it. Kept as a rung because ``/ws/tape`` predates the
     ``header_up`` and any route added without one still needs a floor. LAST, never
     first: if Caddy is ever configured to trust the edge it will APPEND rather than
     replace, and under append the trustworthy value is the last one while the
     attacker's is the first. Last is right under both behaviours; first is right
     under one and hands out unlimited bucket rotation under the other.

Everything else is refused outright. ``EO-Client-IP``, ``True-Client-IP``,
``X-Real-IP`` and ``CF-Connecting-IP`` are measured pass-through on at least one
live zone and are set by nothing in this estate, so a value in one is evidence of a
caller, not of a visitor. Do not re-add them.
"""
from __future__ import annotations

import ipaddress
from typing import Any

# The one forwarded header the edge overwrites on BOTH measured zones.
EDGE_CLIENT_HEADER = "eo-connecting-ip"

# Caddy's header_up in app/deploy/Caddyfile — the verified TCP peer, unspoofable.
TRUSTED_PEER_HEADER = "x-mm-peer"

FORWARDED_FOR_HEADER = "x-forwarded-for"

# Country. MEASURED on www 2026-08-07: the edge sets a country header whose name
# arrives at the origin with NO `EO` prefix — literally `-Client-IPCountry` — and it
# REPLACES a forged copy of that name with the true country. It does NOT set
# `EO-Client-IPCountry`, the name app/gate.py has always asked for, so that header
# arrives carrying whatever the caller sent even THROUGH the edge. The missing prefix
# looks like a console-rule quirk and may be corrected upstream at any time, so
# app/gate.py checks this name FIRST and the configured name immediately after: the
# order is correct both before and after such a fix, and neither ordering can be
# displaced by a forgery.
EDGE_COUNTRY_HEADER = "-client-ipcountry"

UNKNOWN = "unknown"


def _get(headers: Any, name: str) -> str:
    """One header value, case-insensitively, from a Request/WebSocket/dict.

    Starlette lowercases header names, but the unit tests (and any plain dict a
    caller passes) are case-SENSITIVE, so fall back to a scan rather than silently
    reading nothing — a resolver that returns "" for the header it was given is a
    resolver that quietly degrades to the peer.
    """
    if headers is None:
        return ""
    getter = getattr(headers, "get", None)
    if getter is None:
        return ""
    val = getter(name)
    if val is None:
        try:
            items = headers.items()
        except Exception:  # noqa: BLE001
            return ""
        for k, v in items:
            if str(k).lower() == name:
                val = v
                break
    return str(val).strip() if val is not None else ""


def _as_ip(raw: str) -> str | None:
    """Canonical form of a syntactically valid IP, else None.

    CANONICALISING IS PART OF THE THROTTLE. ``1.2.3.4``, ``::ffff:1.2.3.4`` and
    ``0:0:0:0:0:ffff:1.2.3.4`` are one host spelled three ways, as are ``1:db8::1``
    and ``0001:0db8:0000::0001``; keying on the raw string would let a direct-to-origin
    caller rotate buckets without ever changing address. ``ipaddress`` already collapses
    the v6 spellings, but it renders an IPv4-mapped address as ``::ffff:102:304`` rather
    than as the v4 address, so that one alias is unmapped here by hand. Rejecting
    non-IPs matters for the same reason — junk must degrade to the peer, never mint a
    bucket named after whatever the caller typed.
    """
    if not raw:
        return None
    try:
        addr = ipaddress.ip_address(raw)
    except ValueError:
        return None
    mapped = getattr(addr, "ipv4_mapped", None)
    return str(mapped or addr)


def _last_element(value: str) -> str | None:
    """The LAST comma-separated element of a forwarded-header value.

    A malformed trailing element returns None rather than scanning leftwards: under
    append semantics the elements to the left are exactly the caller-supplied ones,
    so "the last value is junk" is a reason to fall through to the next rung, never
    a licence to honour an earlier one.
    """
    if not value:
        return None
    return _as_ip(value.rsplit(",", 1)[-1].strip())


def client_ip(headers: Any) -> str:
    """The visitor's address for throttling and analytics, or ``"unknown"``.

    Never raises and never returns a caller-chosen value when a trustworthy one is
    available. See the module header for why the order is what it is.
    """
    edge = _last_element(_get(headers, EDGE_CLIENT_HEADER))
    if edge:
        return edge
    peer = _as_ip(_get(headers, TRUSTED_PEER_HEADER))
    if peer:
        return peer
    xff = _last_element(_get(headers, FORWARDED_FOR_HEADER))
    if xff:
        return xff
    return UNKNOWN


def trusted_peer(headers: Any) -> str:
    """The verified TCP peer (Caddy ``X-MM-Peer``), or ``""`` when absent.

    Deliberately NOT falling back to ``X-Forwarded-For``: callers use this as the
    unspoofable half of a dual-key limit, and a rung that is only usually trustworthy
    does not belong under a key whose whole job is to be trustworthy always.
    """
    return _get(headers, TRUSTED_PEER_HEADER)[:64]
