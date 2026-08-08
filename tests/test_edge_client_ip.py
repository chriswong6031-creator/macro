"""A forged header must never displace the edge-written one.

These tests are the executable form of a LIVE MEASUREMENT, not a design opinion.
On 2026-08-07 www.mastermind-x.com was probed through the edge with every
real-client header forged, and the origin-side headers were captured off the
loopback hop to :8000 with tcpdump. What came back:

    sent through the edge              arrived at the origin as
    EO-Connecting-IP: 203.0.113.13  -> 104.36.50.44   (OVERWRITTEN — true client)
    EO-Client-IP: 203.0.113.11,.12  -> 104.36.50.44   (OVERWRITTEN — one value)
    True-Client-IP:   203.0.113.66  -> 203.0.113.66   (passed through — FORGED)
    X-Real-IP:        203.0.113.55  -> 203.0.113.55   (passed through — FORGED)
    CF-Connecting-IP: 203.0.113.44  -> 203.0.113.44   (passed through — FORGED)
    X-Forwarded-For: 198.51.100.7   -> 43.175.104.147 (edge dropped it; Caddy
                                                       re-set it to the TCP peer)

and the same probe fired DIRECT to the origin, bypassing the edge entirely
(ufw permits 80,443/tcp from Anywhere), had every one of those arrive exactly as
typed — with X-MM-Peer carrying the caller's own real address.

``_EDGE_CAPTURE`` / ``_DIRECT_CAPTURE`` below are those two captures, verbatim. The
resolver is pinned against the wire, so a future edit that "looks safe" has to
survive what the edge actually does rather than what a comment says it does.
"""
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from app import edge_client

# The four headers measured to arrive carrying whatever a caller sent, on at least
# one live zone. Nothing in this estate sets them. The resolver must ignore all four.
FORGEABLE = ("eo-client-ip", "cf-connecting-ip", "true-client-ip", "x-real-ip")

TRUE_CLIENT = "104.36.50.44"
EDGE_NODE = "43.175.104.147"
ATTACKER = "203.0.113.99"

# Verbatim from the 2026-08-07 capture of an edge-borne request whose every
# real-client header was forged (names lowercased as Starlette delivers them).
_EDGE_CAPTURE = {
    "host": "www.mastermind-x.com",
    "-client-ipcountry": "US",
    "cdn-loop": "TencentEdgeOne; loops=2",
    "cf-connecting-ip": "203.0.113.44",
    "cf-ipcountry": "XX",
    "eo-client-ip": TRUE_CLIENT,
    "eo-client-ipcountry": "XX",
    "eo-connecting-ip": TRUE_CLIENT,
    "true-client-ip": "203.0.113.66",
    "x-forwarded-for": EDGE_NODE,
    "x-mm-peer": EDGE_NODE,
    "x-real-ip": "203.0.113.55",
}

# Verbatim from the same probe fired direct-to-origin. Every forwarded header is the
# caller's; only x-mm-peer (Caddy header_up) tells the truth, and it names the caller.
_DIRECT_CAPTURE = {
    "host": "www.mastermind-x.com",
    "-client-ipcountry": "XX",
    "eo-client-ip": ATTACKER,
    "eo-client-ipcountry": "XX",
    "eo-connecting-ip": "203.0.113.77",
    "x-forwarded-for": TRUE_CLIENT,
    "x-mm-peer": TRUE_CLIENT,
}


# --------------------------------------------------------------------------- #
# The captures themselves
# --------------------------------------------------------------------------- #
def test_edge_capture_resolves_to_the_true_client():
    """The whole point: a real edge request with five forged headers still resolves
    to the visitor the edge attested, not to anything the caller typed."""
    assert edge_client.client_ip(_EDGE_CAPTURE) == TRUE_CLIENT


def test_direct_capture_resolves_to_the_callers_own_peer():
    """Direct-to-origin, the forged EO-Connecting-IP is unmaskable by header reading —
    but it must NOT be honoured over nothing. It is honoured here (there is no way to
    tell it apart), which is exactly why it may only ever be the TIGHT rate-limit key:
    the caller's real address is still pinned in x-mm-peer for the trusted key."""
    assert edge_client.trusted_peer(_DIRECT_CAPTURE) == TRUE_CLIENT


# --------------------------------------------------------------------------- #
# No forged header displaces the edge-written value
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("header", FORGEABLE)
def test_no_forged_header_displaces_the_edge_value(header):
    h = {"eo-connecting-ip": TRUE_CLIENT, header: ATTACKER}
    assert edge_client.client_ip(h) == TRUE_CLIENT


@pytest.mark.parametrize("header", FORGEABLE)
def test_forgeable_header_alone_yields_no_identity(header):
    """Not merely outranked — never read. A request carrying ONLY a forgeable header
    resolves to 'unknown' rather than to the caller's chosen name."""
    assert edge_client.client_ip({header: ATTACKER}) == edge_client.UNKNOWN


def test_all_four_forged_at_once_still_lose_to_the_edge():
    h = {"eo-connecting-ip": TRUE_CLIENT}
    h.update(dict.fromkeys(FORGEABLE, ATTACKER))
    assert edge_client.client_ip(h) == TRUE_CLIENT


def test_forged_headers_cannot_displace_the_trusted_peer_either():
    """With no edge header at all, the Caddy peer wins over every forged header —
    the pre-2026-08-07 order returned the forgery here."""
    h = {"x-mm-peer": EDGE_NODE}
    h.update(dict.fromkeys(FORGEABLE, ATTACKER))
    assert edge_client.client_ip(h) == EDGE_NODE


# --------------------------------------------------------------------------- #
# Bucket rotation — the property the rate limiters actually depend on
# --------------------------------------------------------------------------- #
def test_rotating_forged_headers_cannot_rotate_the_bucket():
    """The attack the old precedence permitted: a fresh EO-Client-IP per request minted
    a fresh rate-limit bucket every time. Behind the edge that must now be impossible."""
    keys = set()
    for n in range(50):
        keys.add(edge_client.client_ip({
            "eo-connecting-ip": TRUE_CLIENT,
            "eo-client-ip": f"203.0.113.{n}",
            "cf-connecting-ip": f"198.51.100.{n}",
            "true-client-ip": f"192.0.2.{n}",
            "x-real-ip": f"203.0.113.{n}",
            "x-forwarded-for": f"198.51.100.{n}",
        }))
    assert keys == {TRUE_CLIENT}


def test_alternate_spellings_of_one_address_share_one_bucket():
    """Canonicalisation is part of the throttle: without it a direct-to-origin caller
    rotates buckets without ever changing host. The IPv4-mapped forms matter most —
    ipaddress renders them '::ffff:102:304' unless they are unmapped by hand, which is
    a free second bucket for the same machine."""
    v4 = ("1.2.3.4", "::ffff:1.2.3.4", "0:0:0:0:0:ffff:1.2.3.4")
    assert {edge_client.client_ip({"eo-connecting-ip": s}) for s in v4} == {"1.2.3.4"}

    v6 = ("0001:0db8:0000::0001", "1:db8::1", "1:0db8:0:0:0:0:0:1")
    assert {edge_client.client_ip({"eo-connecting-ip": s}) for s in v6} == {"1:db8::1"}


def test_leading_zero_ipv4_is_refused_not_reinterpreted():
    """'01.2.3.4' is ambiguous (octal in some parsers) and Python refuses it. Refusal is
    the right outcome: it degrades to the peer rather than minting a second bucket for
    a host that already has one."""
    assert edge_client.client_ip({"eo-connecting-ip": "01.2.3.4",
                                  "x-mm-peer": EDGE_NODE}) == EDGE_NODE


# --------------------------------------------------------------------------- #
# Append semantics — last element, never first
# --------------------------------------------------------------------------- #
def test_edge_header_takes_the_last_value_not_the_first():
    """The edge REPLACES this header today (measured), under which first and last are
    the same. If it ever appends instead, the edge's value is the LAST and the
    attacker's is the first — so last is the only choice correct under both."""
    assert edge_client.client_ip({"eo-connecting-ip": f"{ATTACKER}, {TRUE_CLIENT}"}) == TRUE_CLIENT


def test_xff_takes_the_last_element_not_the_first():
    """Caddy replaces the inbound chain while the peer is untrusted, so today this is a
    single value. Were the edge ever added to trusted_proxies, Caddy would APPEND and
    the first element would be the caller's — which is what the old resolver read."""
    assert edge_client.client_ip({"x-forwarded-for": f"{ATTACKER}, {EDGE_NODE}"}) == EDGE_NODE


def test_prepended_junk_cannot_unseat_the_edge_value():
    assert edge_client.client_ip({"eo-connecting-ip": f"not-an-ip, {TRUE_CLIENT}"}) == TRUE_CLIENT


# --------------------------------------------------------------------------- #
# Degrading safely
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("bad", ["", "   ", "not-an-ip", "1.2.3.4.5", "999.1.1.1",
                                 "1.2.3.4:80", "<script>", "1.2.3.4, evil"])
def test_malformed_edge_header_degrades_to_the_peer(bad):
    """A junk edge value must fall THROUGH to the trusted peer — never mint a bucket
    named after whatever the caller typed, and never scan leftwards to an earlier
    element, which under append semantics is precisely the attacker's."""
    assert edge_client.client_ip({"eo-connecting-ip": bad, "x-mm-peer": EDGE_NODE}) == EDGE_NODE


def test_malformed_edge_header_does_not_fall_back_to_a_forged_one():
    h = {"eo-connecting-ip": "not-an-ip"}
    h.update(dict.fromkeys(FORGEABLE, ATTACKER))
    assert edge_client.client_ip(h) == edge_client.UNKNOWN


def test_no_headers_at_all_is_unknown():
    assert edge_client.client_ip({}) == edge_client.UNKNOWN
    assert edge_client.client_ip(None) == edge_client.UNKNOWN


def test_trusted_peer_never_falls_back_to_xff():
    """The peer key's whole job is to be trustworthy always; a rung that is only
    usually trustworthy does not belong under it."""
    assert edge_client.trusted_peer({"x-forwarded-for": EDGE_NODE}) == ""


def test_header_lookup_is_case_insensitive():
    assert edge_client.client_ip({"EO-Connecting-IP": TRUE_CLIENT}) == TRUE_CLIENT
    assert edge_client.trusted_peer({"X-MM-Peer": EDGE_NODE}) == EDGE_NODE


# --------------------------------------------------------------------------- #
# One resolver — the consumers must not drift apart again
# --------------------------------------------------------------------------- #
def test_every_consumer_resolves_the_capture_identically():
    """app/main.py and app/tape.py each carried their own copy of the header list, and
    app/company_intelligence.py a third, shorter one. They must now agree by
    construction — a per-visitor throttle and the analytics stamp disagreeing about who
    a visitor is was how the forgeable headers survived in two places after one fix."""
    import app.main as main
    import app.tape as tape
    import app.company_intelligence as ci

    class _Req:
        def __init__(self, headers):
            self.headers = headers
            self.client = None

    req = _Req(_EDGE_CAPTURE)
    assert main._mm_client_ip(req) == TRUE_CLIENT
    assert tape._client_ip(req) == TRUE_CLIENT
    assert ci._claimed_client_identity(req) == TRUE_CLIENT


@pytest.mark.parametrize("header", FORGEABLE)
def test_no_consumer_honours_a_forgeable_header(header):
    import app.main as main
    import app.tape as tape
    import app.company_intelligence as ci

    class _Req:
        def __init__(self, headers):
            self.headers = headers
            self.client = None

    req = _Req({header: ATTACKER})
    assert main._mm_client_ip(req) == edge_client.UNKNOWN
    assert tape._client_ip(req) == "unknown"
    assert ci._claimed_client_identity(req) == "unknown"


# --------------------------------------------------------------------------- #
# Country — the same defect, on the gate
# --------------------------------------------------------------------------- #
def test_forged_country_header_cannot_displace_the_edge_country():
    """MEASURED: the edge sets `-Client-IPCountry` (no EO prefix) and overwrites a
    forged copy of it, but never sets `EO-Client-IPCountry` — which the gate asked for
    and which therefore arrived carrying whatever the caller sent. Reading the
    configured name first is what made country blocking bypassable with one header."""
    from app import gate

    country, source = gate._resolve_country_header(_EDGE_CAPTURE)
    assert country == "US"                       # the edge's value, not the forged XX
    assert source == "header:-Client-IPCountry"


def test_gate_country_falls_through_when_the_edge_header_is_absent():
    """If the console rule is ever corrected so the EO-prefixed name is the edge-set
    one, this order still resolves — the quirky name simply goes absent."""
    from app import gate

    country, source = gate._resolve_country_header({"eo-client-ipcountry": "JP"})
    assert (country, source) == ("JP", "header:EO-Client-IPCountry")
