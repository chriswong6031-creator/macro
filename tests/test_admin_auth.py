"""admin.auth + deployed-mode auth gate — session signing, CSRF, login throttle,
and a live round-trip proving protected routes require a session."""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from admin import auth, settings  # noqa: E402
from admin.server import Handler  # noqa: E402


def _set_env(**kw):
    old = {k: os.environ.get(k) for k in kw}
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return old


def _restore(old):
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _reset_throttle():
    auth._attempts.clear()


# ---- unit: session signing ---------------------------------------------------
def test_session_roundtrip_and_tamper():
    old = _set_env(ADMIN_SESSION_SECRET="unit-test-secret")
    try:
        tok = auth.mint_session()
        assert auth.valid_session(tok)
        # tampered body / signature must fail
        body, _, sig = tok.partition(".")
        assert not auth.valid_session(body + ".deadbeef")
        assert not auth.valid_session("x" * 10 + "." + sig)
        assert not auth.valid_session(None) and not auth.valid_session("no-dot")
        # a session signed with a different secret must not validate
        _set_env(ADMIN_SESSION_SECRET="other-secret")
        assert not auth.valid_session(tok)
    finally:
        _restore(old)


def test_session_expiry():
    old = _set_env(ADMIN_SESSION_SECRET="unit-test-secret", ADMIN_SESSION_TTL_HOURS="1")
    try:
        import base64
        # hand-mint an already-expired payload with a valid signature
        payload = base64.urlsafe_b64encode(
            json.dumps({"iat": 0, "exp": int(time.time()) - 5}).encode()).decode().rstrip("=")
        tok = f"{payload}.{auth._sign(payload.encode())}"
        assert not auth.valid_session(tok)
    finally:
        _restore(old)


def test_password_and_lockout():
    old = _set_env(ADMIN_PASSWORD="hunter2")
    _reset_throttle()
    try:
        assert auth.password_ok("hunter2")[0] is True
        _reset_throttle()
        assert auth.password_ok("wrong")[0] is False
        # five failures → locked
        for _ in range(5):
            auth.password_ok("nope")
        ok, err = auth.password_ok("hunter2")   # correct, but locked out
        assert ok is False and "locked" in (err or "")
    finally:
        _reset_throttle()
        _restore(old)


def test_lockout_is_per_client_not_global():
    """An attacker hammering from one IP must NOT lock out the operator's IP."""
    old = _set_env(ADMIN_PASSWORD="hunter2")
    _reset_throttle()
    try:
        for _ in range(8):                       # attacker IP trips its own lockout
            auth.password_ok("nope", client_id="9.9.9.9")
        assert auth.password_ok("hunter2", client_id="9.9.9.9")[0] is False  # attacker locked
        # the operator, on a different IP, is unaffected and logs in fine
        assert auth.password_ok("hunter2", client_id="1.2.3.4")[0] is True
    finally:
        _reset_throttle()
        _restore(old)


def test_client_id_ignores_spoofable_forwarding_headers():
    """SECURITY regression (critical): the per-client lockout only holds if _client_id()
    is a peer IP the caller cannot forge. On the deployed admin host it must trust Caddy's
    injected X-Admin-Client-IP, else the LAST X-Forwarded-For hop (the real peer Caddy
    appends) — NEVER the attacker-controlled FIRST hop, which let a brute-force client
    rotate the header per request to land every guess in a fresh lockout bucket."""
    h = Handler.__new__(Handler)

    def _cid(headers, peer=("127.0.0.1", 1)):
        h.headers, h.client_address = headers, peer
        return h._client_id()

    old = _set_env(ADMIN_DEPLOYED="1")
    try:
        # Caddy-injected trusted header wins over any client-sent X-Forwarded-For
        assert _cid({"X-Admin-Client-IP": "9.9.9.9", "X-Forwarded-For": "1.1.1.1"}) == "9.9.9.9"
        # no trusted header → LAST XFF hop (the real peer Caddy appends), NOT the first
        assert _cid({"X-Forwarded-For": "1.1.1.1, 2.2.2.2, 3.3.3.3"}) == "3.3.3.3"
        # no forwarding headers at all → the real TCP peer
        assert _cid({}, peer=("5.5.5.5", 1)) == "5.5.5.5"
        # site-gate self-allow IP ignores spoofable CDN headers on the non-CDN admin host
        h.headers = {"CF-Connecting-IP": "6.6.6.6", "EO-Connecting-IP": "7.7.7.7",
                     "X-Admin-Client-IP": "9.9.9.9"}
        h.client_address = ("127.0.0.1", 1)
        assert h._real_client_ip() == "9.9.9.9"
    finally:
        _restore(old)
    # local mode (not deployed): forwarding headers ignored, use the real TCP peer
    old = _set_env(ADMIN_DEPLOYED=None)
    try:
        assert _cid({"X-Admin-Client-IP": "9.9.9.9", "X-Forwarded-For": "1.1.1.1"},
                    peer=("10.0.0.5", 1)) == "10.0.0.5"
    finally:
        _restore(old)


# ---- the edge collapse (live defect, measured 2026-08-07) --------------------
# admin.mastermind-x.com is edge-proxied, so Caddy's {remote_host} — and therefore the
# X-Admin-Client-IP the tests above treat as identity — is an EdgeOne origin-pull
# address for every real visitor, NOT the visitor. Keying the login lockout on it put
# all edge-borne traffic in ONE bucket and inverted auth.py's stated property ("one
# attacker can only lock out *themselves*") into an anonymous operator-lockout DoS.
#
# EDGE_PEER / EDGE_RANGE below are a real observed origin-pull address and the /24 it
# sits in. They are FIXTURE VALUES for exercising the attestation logic — they are not
# the shipped allowlist, which is empty by default on purpose
# (config/edgeone_origin_ranges.json; see admin/edge_trust.py's header for why guessing
# a range is worse than shipping none).
EDGE_PEER = "43.175.104.236"
EDGE_RANGE = "43.175.104.0/24"
NOT_EDGE_RANGE = "8.8.8.0/24"        # public, loads for real, and never an edge address.
#   NOT a TEST-NET (192.0.2.0/24 etc): Python reports those is_private, so
#   _safe_network drops them and the "allowlist misses this peer" tests below would
#   silently degrade into re-testing the empty-allowlist path.


def _cid_for(headers, peer=("127.0.0.1", 1)):
    h = Handler.__new__(Handler)
    h.headers, h.client_address = headers, peer
    return h._client_id()


def test_two_visitors_behind_one_edge_node_get_separate_buckets():
    """REGRESSION (the collapse itself): two DIFFERENT people arriving through the same
    EdgeOne node must not share a lockout bucket. Against the pre-fix code both of these
    resolve to the edge address and this assertion fails."""
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_EDGE_ORIGIN_CIDRS=EDGE_RANGE,
                   ADMIN_EDGE_SECRET=None)
    try:
        a = _cid_for({"X-Admin-Client-IP": EDGE_PEER, "EO-Connecting-IP": "104.36.50.44"})
        b = _cid_for({"X-Admin-Client-IP": EDGE_PEER, "EO-Connecting-IP": "198.51.100.7"})
        assert a == "104.36.50.44"
        assert b == "198.51.100.7"
        assert a != b, "both visitors collapsed into one bucket — the DoS is back"
    finally:
        _restore(old)


def test_edge_borne_lockout_does_not_reach_the_operator():
    """The DoS, end to end: an attacker burning its five attempts through the edge must
    not lock out the operator arriving through the SAME edge node."""
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_PASSWORD="hunter2",
                   ADMIN_EDGE_ORIGIN_CIDRS=EDGE_RANGE, ADMIN_EDGE_SECRET=None)
    _reset_throttle()
    try:
        attacker = _cid_for({"X-Admin-Client-IP": EDGE_PEER, "EO-Connecting-IP": "203.0.113.9"})
        operator = _cid_for({"X-Admin-Client-IP": EDGE_PEER, "EO-Connecting-IP": "104.36.50.44"})
        for _ in range(8):
            auth.password_ok("nope", client_id=attacker)
        assert auth.password_ok("hunter2", client_id=attacker)[0] is False   # attacker locked
        assert auth.password_ok("hunter2", client_id=operator)[0] is True    # operator unaffected
    finally:
        _reset_throttle()
        _restore(old)


def test_direct_to_origin_caller_cannot_forge_its_bucket():
    """SECURITY (critical): ufw permits 80,443/tcp from Anywhere, so anyone can reach the
    origin directly and send any forwarding header. When the verified peer is NOT an
    attested edge address, EVERY such header must be ignored and the bucket must stay
    pinned to the peer — otherwise a brute-forcer rotates the header per request and the
    throttle is gone."""
    direct = "198.51.100.77"
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_EDGE_ORIGIN_CIDRS=EDGE_RANGE,
                   ADMIN_EDGE_SECRET=None)
    try:
        for forged in ({"EO-Connecting-IP": "203.0.113.1"},
                       {"EO-Client-IP": "203.0.113.2"},
                       {"True-Client-IP": "203.0.113.3"},
                       {"X-Real-IP": "203.0.113.4"},
                       {"CF-Connecting-IP": "203.0.113.5"},
                       {"X-Forwarded-For": "203.0.113.6"}):
            got = _cid_for({"X-Admin-Client-IP": direct, **forged})
            assert got == direct, f"{forged} escaped the bucket -> {got}"
        # …and rotating the header cannot mint a second bucket either
        keys = {_cid_for({"X-Admin-Client-IP": direct, "EO-Connecting-IP": f"203.0.113.{n}"})
                for n in range(1, 6)}
        assert keys == {direct}
    finally:
        _restore(old)


def test_forged_eo_client_ip_is_ignored_even_behind_the_edge():
    """MEASURED 2026-08-07: the edge OVERWRITES EO-Connecting-IP but passes EO-Client-IP
    (and True-Client-IP / X-Real-IP / CF-Connecting-IP) through untouched — a clean edge
    request carries no EO-Client-IP at all. Honouring any of those would hand a
    brute-forcer a bucket-rotation knob on the edge path too."""
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_EDGE_ORIGIN_CIDRS=EDGE_RANGE,
                   ADMIN_EDGE_SECRET=None)
    try:
        got = _cid_for({"X-Admin-Client-IP": EDGE_PEER,
                        "EO-Connecting-IP": "104.36.50.44",   # edge-written, trustworthy
                        "EO-Client-IP": "203.0.113.99",       # caller-supplied
                        "True-Client-IP": "203.0.113.66",
                        "X-Real-IP": "203.0.113.55",
                        "CF-Connecting-IP": "203.0.113.44"})
        assert got == "104.36.50.44"
    finally:
        _restore(old)


def test_unattested_peer_and_junk_header_fall_back_to_peer():
    """Fail-safe in both directions: an edge node outside the configured ranges, and an
    attested peer whose EO-Connecting-IP is missing or malformed, both degrade to the
    pre-fix peer keying rather than to an attacker-chosen bucket name."""
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_EDGE_ORIGIN_CIDRS=NOT_EDGE_RANGE,
                   ADMIN_EDGE_SECRET=None)
    try:
        # peer is a real edge address but the allowlist does not cover it → old behaviour
        assert _cid_for({"X-Admin-Client-IP": EDGE_PEER,
                         "EO-Connecting-IP": "104.36.50.44"}) == EDGE_PEER
    finally:
        _restore(old)
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_EDGE_ORIGIN_CIDRS=EDGE_RANGE,
                   ADMIN_EDGE_SECRET=None)
    try:
        assert _cid_for({"X-Admin-Client-IP": EDGE_PEER}) == EDGE_PEER          # absent
        assert _cid_for({"X-Admin-Client-IP": EDGE_PEER,
                         "EO-Connecting-IP": "not-an-ip"}) == EDGE_PEER         # malformed
        assert _cid_for({"X-Admin-Client-IP": EDGE_PEER,
                         "EO-Connecting-IP": ""}) == EDGE_PEER                  # empty
    finally:
        _restore(old)


def test_shared_secret_attests_the_edge_without_any_cidr():
    """The CIDR-free path: there is no credential-free published EdgeOne origin-pull
    range list, so the preferred attestation is a secret the edge injects on origin-pull.
    It must work with NO ranges configured, and a wrong/absent secret must not attest."""
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_EDGE_ORIGIN_CIDRS=NOT_EDGE_RANGE,
                   ADMIN_EDGE_SECRET="s3kr1t-edge")
    try:
        assert _cid_for({"X-Admin-Client-IP": EDGE_PEER,
                         "X-MM-Edge-Auth": "s3kr1t-edge",
                         "EO-Connecting-IP": "104.36.50.44"}) == "104.36.50.44"
        # wrong secret / no secret → peer keying, no matter what else is sent
        assert _cid_for({"X-Admin-Client-IP": EDGE_PEER,
                         "X-MM-Edge-Auth": "wrong",
                         "EO-Connecting-IP": "104.36.50.44"}) == EDGE_PEER
        assert _cid_for({"X-Admin-Client-IP": EDGE_PEER,
                         "EO-Connecting-IP": "104.36.50.44"}) == EDGE_PEER
    finally:
        _restore(old)


def test_local_mode_still_ignores_every_forwarding_header():
    """Unchanged contract: outside deployed mode nothing forwarded is honoured, because
    there is no Caddy in front to have verified any of it."""
    old = _set_env(ADMIN_DEPLOYED=None, ADMIN_EDGE_ORIGIN_CIDRS=EDGE_RANGE,
                   ADMIN_EDGE_SECRET="s3kr1t-edge")
    try:
        assert _cid_for({"X-Admin-Client-IP": EDGE_PEER,
                         "X-MM-Edge-Auth": "s3kr1t-edge",
                         "EO-Connecting-IP": "104.36.50.44"},
                        peer=("10.0.0.5", 1)) == "10.0.0.5"
    finally:
        _restore(old)


def test_blanket_range_from_a_poisoned_source_cannot_open_the_door():
    """MEASURED 2026-08-07: https://api.edgeone.ai/ips — the only credential-free EdgeOne
    origin-pull range list — is deprecated and now answers HTTP 200 with a deprecation
    notice followed by the literal payload `0.0.0.0/0` / `::/0`. A refresh job that
    trusted the status code would hand us a trust-everything allowlist, and every
    direct-to-origin caller would become "the edge". The loader must refuse those
    entries no matter how they arrive."""
    direct = "198.51.100.77"
    poison = ("# [DEPRECATION NOTICE] This interface stopped serving on 2026-07-31,"
              "0.0.0.0/0,::/0")
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_EDGE_ORIGIN_CIDRS=poison, ADMIN_EDGE_SECRET=None)
    try:
        assert _cid_for({"X-Admin-Client-IP": direct,
                         "EO-Connecting-IP": "203.0.113.1"}) == direct
        assert _cid_for({"X-Admin-Client-IP": EDGE_PEER,
                         "EO-Connecting-IP": "203.0.113.1"}) == EDGE_PEER
    finally:
        _restore(old)
    # …and the same refusal for private/loopback blocks and anything over-broad
    for bad in ("10.0.0.0/8", "127.0.0.0/8", "192.168.0.0/16", "43.0.0.0/8", "::/0"):
        old = _set_env(ADMIN_DEPLOYED="1", ADMIN_EDGE_ORIGIN_CIDRS=bad, ADMIN_EDGE_SECRET=None)
        try:
            from admin import edge_trust
            assert edge_trust.edge_origin_networks() == (), f"{bad} was accepted"
        finally:
            _restore(old)


def test_a_real_narrow_range_still_loads():
    """The floor must not be so aggressive that a genuine origin-pull list is unusable:
    the observed peers sit in /24s, and a plausible authoritative list is made of blocks
    that size. The v6 entry is a /48, not the /32 RIR allocation — a /32 is 2^96
    addresses and is refused by design (see the predicate test above)."""
    import ipaddress

    from admin import edge_trust

    old = _set_env(ADMIN_EDGE_ORIGIN_CIDRS="43.175.104.0/24, 101.33.21.0/24, 2402:4e00:1::/48")
    try:
        assert len(edge_trust.edge_origin_networks()) == 3
    finally:
        _restore(old)
    # A mixed list keeps the good entries and drops only the over-broad one, so an
    # operator who summarises their /24s up to a /16 loses the summary, not the list.
    old = _set_env(ADMIN_EDGE_ORIGIN_CIDRS="43.175.104.0/24, 43.175.0.0/16")
    try:
        assert edge_trust.edge_origin_networks() == (ipaddress.ip_network("43.175.104.0/24"),)
    finally:
        _restore(old)


def _msg(raw: str):
    """A REAL http.client HTTPMessage, so duplicate headers and header casing behave the
    way they do on the wire. A dict cannot express either, so dict-only tests cannot see
    the first-vs-last-occurrence bug below."""
    from email.parser import Parser

    from http.client import HTTPMessage
    return Parser(_class=HTTPMessage).parsestr(raw)


def test_appended_edge_header_cannot_hand_the_bucket_to_the_attacker():
    """SECURITY: `HTTPMessage.get()` returns the FIRST occurrence, and a comma-list's
    element 0 is likewise the earliest hop — both the attacker's copy if the edge ever
    APPENDS rather than replaces. Measured today it replaces, but Tencent documents that
    nowhere and documents the sibling X-Forwarded-For as append-only, so reading the
    first value would be one upstream behaviour change away from unlimited bucket
    rotation. The edge's value is the LAST one under both behaviours."""
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_EDGE_ORIGIN_CIDRS=EDGE_RANGE,
                   ADMIN_EDGE_SECRET=None)
    try:
        # duplicate header lines: attacker's first, edge's appended after
        dup = _msg(f"X-Admin-Client-IP: {EDGE_PEER}\r\n"
                   "EO-Connecting-IP: 203.0.113.77\r\n"
                   "EO-Connecting-IP: 104.36.50.44\r\n\r\n")
        assert _cid_for(dup) == "104.36.50.44"
        # comma-list form of the same attack
        lst = _msg(f"X-Admin-Client-IP: {EDGE_PEER}\r\n"
                   "EO-Connecting-IP: 203.0.113.77, 104.36.50.44\r\n\r\n")
        assert _cid_for(lst) == "104.36.50.44"
        # header CASE is not a way in either (HTTPMessage is case-insensitive)
        cased = _msg(f"x-admin-client-ip: {EDGE_PEER}\r\n"
                     "eo-connecting-ip: 104.36.50.44\r\n\r\n")
        assert _cid_for(cased) == "104.36.50.44"
    finally:
        _restore(old)


def test_junk_copy_cannot_switch_off_the_secret_attestation():
    """An attacker who prepends a junk X-MM-Edge-Auth must not be able to DISABLE
    attestation and force everyone back into the shared bucket — every copy is checked,
    which is safe because a match still requires the secret."""
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_EDGE_ORIGIN_CIDRS=NOT_EDGE_RANGE,
                   ADMIN_EDGE_SECRET="s3kr1t-edge")
    try:
        m = _msg(f"X-Admin-Client-IP: {EDGE_PEER}\r\n"
                 "X-MM-Edge-Auth: junk-prepended-by-attacker\r\n"
                 "X-MM-Edge-Auth: s3kr1t-edge\r\n"
                 "EO-Connecting-IP: 104.36.50.44\r\n\r\n")
        assert _cid_for(m) == "104.36.50.44"
        # …and a set of copies that are ALL wrong still does not attest
        bad = _msg(f"X-Admin-Client-IP: {EDGE_PEER}\r\n"
                   "X-MM-Edge-Auth: nope\r\n"
                   "X-MM-Edge-Auth: also-nope\r\n"
                   "EO-Connecting-IP: 104.36.50.44\r\n\r\n")
        assert _cid_for(bad) == EDGE_PEER
    finally:
        _restore(old)


def test_non_ascii_secret_disables_attestation_instead_of_failing_silently():
    """http.server decodes headers as latin-1, so a non-ASCII ADMIN_EDGE_SECRET can never
    match what arrives on the wire. That must be a refusal (and a warning), not a
    permanently, silently inert attestation that looks configured."""
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_EDGE_ORIGIN_CIDRS=NOT_EDGE_RANGE,
                   ADMIN_EDGE_SECRET="sécret-with-non-ascii")
    try:
        m = _msg(f"X-Admin-Client-IP: {EDGE_PEER}\r\n"
                 "X-MM-Edge-Auth: sécret-with-non-ascii\r\n"
                 "EO-Connecting-IP: 104.36.50.44\r\n\r\n")
        assert _cid_for(m) == EDGE_PEER
    finally:
        _restore(old)


def test_safe_network_refuses_the_rentable_neighbour_shape():
    """The floor must be TIGHTER than the aggregates this edge is observed in. The
    origin-pull peers sit in /24s, but the /16s they roll up to also carry rentable
    Tencent Cloud instances — so a /16 is exactly the shape that would let an attacker
    rent a VM next door, satisfy the peer check, and forge identity at will. Asserted
    directly on the predicate so it cannot go vacuous when the shipped list is empty."""
    import ipaddress

    from admin import edge_trust

    for bad in ("0.0.0.0/0", "::/0", "43.175.0.0/16", "43.174.0.0/16", "101.33.0.0/16",
                "43.0.0.0/8", "10.0.0.0/8", "127.0.0.0/8", "192.168.0.0/16",
                "2402:4e00::/32", "224.0.0.0/4"):
        assert not edge_trust._safe_network(ipaddress.ip_network(bad)), f"{bad} accepted"
    for ok in ("43.175.104.0/24", "101.33.21.0/24", "8.8.8.8/32", "43.175.96.0/20",
               "2402:4e00:1::/48"):
        assert edge_trust._safe_network(ipaddress.ip_network(ok)), f"{ok} refused"


def test_shipped_edge_ranges_are_never_a_blanket_trust():
    """Whatever the shipped file holds must survive the floor above. Vacuous while the
    list is empty (that is the shipped state) — the predicate test above is the one that
    pins the rule; this one guards the DATA if a future operator populates it."""
    from admin import edge_trust

    old = _set_env(ADMIN_EDGE_ORIGIN_CIDRS=None)
    try:
        for net in edge_trust.edge_origin_networks():
            assert edge_trust._safe_network(net), f"{net} should not have loaded"
    finally:
        _restore(old)


def test_csrf_double_submit():
    assert auth.csrf_ok("abc", "abc") is True
    assert auth.csrf_ok("abc", "xyz") is False
    assert auth.csrf_ok(None, "abc") is False
    assert auth.csrf_ok("abc", None) is False


def test_startup_check_requires_password_when_deployed():
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_PASSWORD=None)
    try:
        raised = False
        try:
            settings.startup_check()
        except SystemExit:
            raised = True
        assert raised, "deployed mode with no password must refuse to start"
    finally:
        _restore(old)


# ---- integration: live deployed-mode gate ------------------------------------
def _server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


def _req(port, path, method="GET", body=None, cookies=None, headers=None):
    h = dict(headers or {})
    if body is not None:
        h["Content-Type"] = "application/json"
    if cookies:
        h["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, headers=h, method=method)
    return urllib.request.urlopen(req, timeout=10)


def _response_cookies(response):
    morsels = []
    for header in response.headers.get_all("Set-Cookie") or []:
        parsed = SimpleCookie()
        parsed.load(header)
        assert len(parsed) == 1
        morsels.append(next(iter(parsed.values())))
    return morsels


def test_session_check_promotes_only_a_valid_deployed_session_to_parent_domain():
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_PASSWORD="s3cret",
                   ADMIN_SESSION_SECRET="it-secret", ADMIN_SESSION_TTL_HOURS="1")
    httpd, port = _server()
    try:
        anonymous = _req(port, "/api/session")
        assert json.loads(anonymous.read())["authenticated"] is False
        assert _response_cookies(anonymous) == []

        invalid = _req(port, "/api/session",
                       cookies={auth.SESSION_COOKIE: "invalid"})
        assert json.loads(invalid.read())["authenticated"] is False
        assert _response_cookies(invalid) == []

        session = auth.mint_session()
        promoted_response = _req(
            port, "/api/session", cookies={auth.SESSION_COOKIE: session}
        )
        assert json.loads(promoted_response.read())["authenticated"] is True
        promoted = _response_cookies(promoted_response)
        assert [(m.key, m["domain"]) for m in promoted] == [
            (auth.SESSION_COOKIE, "mastermind-x.com"),
            (auth.SESSION_COOKIE, ""),
        ]
        shared, legacy = promoted
        if shared.value != session:
            raise AssertionError("session promotion changed the signed value")
        assert shared["path"] == "/"
        assert shared["samesite"] == "Strict"
        assert shared["secure"] is True
        assert shared["httponly"] is True
        assert shared["max-age"] == "3600"
        assert legacy.value == ""
        assert legacy["path"] == "/"
        assert legacy["samesite"] == "Strict"
        assert legacy["secure"] is True
        assert legacy["httponly"] is True
        assert legacy["max-age"] == "0"
        assert all(m.key != auth.CSRF_COOKIE for m in promoted)
    finally:
        httpd.shutdown(); httpd.server_close()
        _restore(old)


def test_logout_clears_host_and_parent_domain_sessions_but_only_host_csrf():
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_PASSWORD="s3cret",
                   ADMIN_SESSION_SECRET="it-secret")
    httpd, port = _server()
    try:
        response = _req(port, "/api/logout", "POST", {}, cookies={
            auth.SESSION_COOKIE: auth.mint_session(),
            auth.CSRF_COOKIE: auth.new_csrf(),
        })
        cleared = _response_cookies(response)
        assert [(m.key, m["domain"]) for m in cleared] == [
            (auth.SESSION_COOKIE, ""),
            (auth.SESSION_COOKIE, "mastermind-x.com"),
            (auth.CSRF_COOKIE, ""),
        ]
        for morsel in cleared:
            assert morsel.value == ""
            assert morsel["path"] == "/"
            assert morsel["samesite"] == "Strict"
            assert morsel["secure"] is True
            assert morsel["max-age"] == "0"
        assert cleared[0]["httponly"] is True
        assert cleared[1]["httponly"] is True
        assert cleared[2]["httponly"] == ""
    finally:
        httpd.shutdown(); httpd.server_close()
        _restore(old)


def test_deployed_mode_requires_session():
    old = _set_env(ADMIN_DEPLOYED="1", ADMIN_PASSWORD="s3cret",
                   ADMIN_SESSION_SECRET="it-secret")
    _reset_throttle()
    httpd, port = _server()
    try:
        # /api/session is public and reports the locked state
        r = _req(port, "/api/session")
        sess = json.loads(r.read())
        assert sess["auth_enabled"] is True and sess["authenticated"] is False
        assert sess["deployed"] is True

        # a protected route is 401 without a session
        try:
            _req(port, "/api/health")
            raise AssertionError("expected 401")
        except urllib.error.HTTPError as e:
            assert e.code == 401
        try:
            _req(port, "/api/auth-check")
            raise AssertionError("expected 401")
        except urllib.error.HTTPError as e:
            assert e.code == 401

        # wrong password → 401
        try:
            _req(port, "/api/login", "POST", {"password": "nope"})
            raise AssertionError("expected 401")
        except urllib.error.HTTPError as e:
            assert e.code == 401

        # correct password → 200 + Set-Cookie (session + csrf)
        r = _req(port, "/api/login", "POST", {"password": "s3cret"})
        setc = r.headers.get_all("Set-Cookie") or []
        jar = {}
        for c in setc:
            k, _, rest = c.partition("=")
            jar[k] = rest.split(";")[0]
        assert auth.SESSION_COOKIE in jar and auth.CSRF_COOKIE in jar
        assert "Secure" in " ".join(setc) and "HttpOnly" in " ".join(setc)
        assert all("Domain=" not in cookie for cookie in setc)

        # with the session cookie, the protected route works
        r = _req(port, "/api/health", cookies={auth.SESSION_COOKIE: jar[auth.SESSION_COOKIE]})
        assert r.status == 200
        r = _req(port, "/api/auth-check",
                 cookies={auth.SESSION_COOKIE: jar[auth.SESSION_COOKIE]})
        assert r.status == 200
        assert json.loads(r.read()) == {"ok": True, "authenticated": True}

        # a write WITHOUT the CSRF header is rejected (403) even with a valid session
        try:
            _req(port, "/api/flags/toggle", "POST", {"path": "x", "value": True},
                 cookies={auth.SESSION_COOKIE: jar[auth.SESSION_COOKIE],
                          auth.CSRF_COOKIE: jar[auth.CSRF_COOKIE]})
            raise AssertionError("expected 403 (missing CSRF header)")
        except urllib.error.HTTPError as e:
            assert e.code == 403 and "CSRF" in json.loads(e.read())["error"]

        # write WITH a matching CSRF header passes auth+csrf (then 400 on unmanaged path)
        try:
            _req(port, "/api/flags/toggle", "POST", {"path": "not.real", "value": True},
                 cookies={auth.SESSION_COOKIE: jar[auth.SESSION_COOKIE],
                          auth.CSRF_COOKIE: jar[auth.CSRF_COOKIE]},
                 headers={auth.CSRF_HEADER: jar[auth.CSRF_COOKIE]})
            raise AssertionError("expected 400 (unmanaged flag, past auth)")
        except urllib.error.HTTPError as e:
            assert e.code == 400 and "unmanaged" in json.loads(e.read())["error"]
    finally:
        httpd.shutdown(); httpd.server_close()
        _reset_throttle(); _restore(old)
