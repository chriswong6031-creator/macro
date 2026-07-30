# Paywall / regwall exposure via the public git mirror and the public R2 base

**Status:** ADJUDICATION — operator decision required. Nothing in this document has been
implemented.
**Opened:** 2026-07-30, during Prophet Live P0.
**Builds on (do not re-litigate):** #3391 (operator ruling "don't show the real board free"
→ landing shows 2-week-delayed winners), #3393 (regwalled `/factordata/*` + `/labdata/*` at
Caddy), CXI-R23 Amendment 2 (`research/DO_NOT_REBUILD.md` row 58, operator ruling 2026-07-20).

---

## §0 RECOMMENDATION (read this first)

**The repo being public is not the finding.** The operator already accepted that
(CXI-R23 Amendment 2, 2026-07-20 — "repo public for mirror + live-quotes"). The finding is
that the acceptance was **scoped to source visibility**, and the build pipeline silently
extended it to **287.6 MB / 6,597 gated product payloads**, including the graded Prophet
board that #3391 and #3393 exist to keep off the free tier. That same ruling already draws
the line this violates, in its own words: source-visibility acceptance "does NOT extend to
serving internals through product surfaces."

Recommended disposition, in priority order:

| # | Action | Class | Why now |
|---|---|---|---|
| **R1** | **Move the Prophet Live armed pack + `prophet_live.json` off the publicly-bound R2 bucket.** Operator must create/bind a private bucket + secrets; then a small config change routes them there. | **P0 — imminent** | The pack has **never been written yet** (verified 404 today). The first night it publishes, per-name trigger/fade **levels** become anonymously readable. Fixing it *before* first publish costs nothing and leaks nothing. After, it is a leak with a history. |
| **R2** | Adopt **option (iii)** — keep git public, stop committing *ranked/graded* payloads; publish degraded or delayed copies to git and serve the full payload from a private store. | P1 — structural | Generalizes the #3391 delayed-winners pattern the operator already ruled for. Preserves the mirror + live-quotes acceptance R1 and CXI-R23 depend on. |
| **R3** | Do **not** make the repo private (option i). | — | It breaks `live.js`'s keyless quote fallback and contradicts a standing operator acceptance. See §4(i). |

**R1 is the only time-sensitive item, and I did not implement it** — see §5 for why it is not
"unambiguously safe and reversible" in the sense the brief authorized, and for the exact
arming steps that need the operator.

---

## §1 The finding, verified

Every claim below was re-verified in this session on 2026-07-30 — not inherited from the
P0 report.

```
$ gh repo view --json visibility
chriswong6031-creator/macro → PUBLIC
```

Because the repo is public, **"committed to git" is identical to "anonymously readable via
`raw.githubusercontent.com`"**. Sampled proof across every gate class (HTTP status / bytes,
no auth, no token):

| Path (`…/macro/main/site/`) | Policy class | Result |
|---|---|---|
| `factordata/us_standouts.json` | INSIDER default-deny | **200** — 1,911,301 B |
| `premiumdata/special_situations.json` | PREMIUM enforced-early | **200** — 7,013,537 B |
| `allocationdata/special_situations.json` | PREMIUM enforced-early | **200** — 5,922,425 B |
| `chinaspecialdata/special.json` | PREMIUM enforced-early | **200** — 21,220 B |
| `labdata/pick_lab.json` | INSIDER default-deny | **200** — 365,999 B |
| `factordata/china_standouts.json` | INSIDER default-deny | **200** — 3,398,439 B |
| `marketdata/subsector_confluence_china.json` | INSIDER default-deny | **200** — 6,625,266 B |
| `intelligence/by_ticker.json` | INSIDER default-deny | **200** — 2,621,091 B |
| `neuralwebdata/bottom_sensors.json` | INSIDER default-deny | **200** — 3,014,101 B |

All three `enforced_early` premium payloads — the paths whose gate is live *ahead* of the
site-wide paywall switch — are anonymously downloadable in full.

`live-data` branch (`…/macro/live-data/quotes.json`) → **200**, 371,710 B. This one is
**intentional** and load-bearing; see §3(a).

### The half-enforcement, precisely

`app/deploy/Caddyfile` `@reg_asset` is a correct, default-deny **serving** boundary, and
`@reg_html` gates pages beside it. Both control `www.mastermind-x.com` only. The identical
bytes reach the public mirror through a completely separate path: the render commits them
into `site/`, and `app/deploy/update.sh` does `fetch + reset + rsync` of `site/` to serve
them. **Git is simultaneously the delivery transport for the site and a public mirror.**
#3393 closed the served path; the git path was never in its scope.

---

## §2 Census — every tracked `site/` artifact, classified against `config/site_access.yml`

Method: parse the policy file, classify all 9,237 git-tracked paths under `site/` by the
same precedence Caddy applies (`deny` → `premium.enforced_early` → `public` → `free_registered`
→ insider default); the classifier reproduces the `@reg_asset` list exactly. "Readable from git"
is not sampled per-row because it is entailed by repo visibility — the sample in §1 proves the
class.

| Policy class | Files | Size | Gated when served? | Readable from git? | Readable from R2 base? |
|---|---:|---:|---|---|---|
| **PREMIUM enforced-early** | **5** | **12.3 MB** | Yes — paid entitlement, enforced today | **YES** | partial¹ |
| **INSIDER default-deny** | **6,571** | **274.0 MB** | Yes — account + `site_full` | **YES** | partial¹ |
| **free_registered** | **21** | **2.1 MB** | Yes — account required | **YES** | partial¹ |
| deny (404 to everyone) | 4 | 1.9 MB | Yes — 404 even to entitled users | **YES** | no |
| public | 2,636 | 258.8 MB | No — intentionally public | yes (intended) | yes (intended) |
| **Gated-when-served, yet public in git** | **6,597** | **287.6 MB** | — | — | — |

¹ The R2 public base mirrors the *data plane* (`live_flow/`, `stockdata/`, etc.), not the
rendered `site/` tree. Spot-checked: `factordata/us_standouts.json` → **404** on the R2 base.
The R2 exposure is a distinct, narrower set — §3(c).

### Largest gated artifacts on the public mirror

| Size | Class | Path |
|---:|---|---|
| 6.85 MB | INSIDER | `/factordata/tech_screener.json` |
| 6.69 MB | **PREMIUM** | `/premiumdata/special_situations.json` |
| 6.32 MB | INSIDER | `/marketdata/subsector_confluence_china.json` |
| 5.65 MB | **PREMIUM** | `/allocationdata/special_situations.json` |
| 3.24 MB | INSIDER | `/factordata/china_setups.json` |
| 3.24 MB | INSIDER | `/factordata/china_standouts.json` |
| **1.82 MB** | INSIDER | **`/factordata/us_standouts.json`** ← the graded Prophet board |
| 1.33 MB | INSIDER | `/factordata/smartmoney.json` |
| 0.35 MB | INSIDER | `/labdata/pick_lab.json` |
| 0.02 MB | **PREMIUM** | `/chinaspecialdata/special.json` |

83 gated artifacts sit under the five product prefixes the operator has ruled on
(`factordata`, `labdata`, `premiumdata`, `allocationdata`, `chinaspecialdata`).

---

## §3 Materiality by class

### (a) Intentionally public — no action

`live-data/quotes.json` is **deliberate and load-bearing**. `.github/workflows/live-quotes.yml`
force-pushes an orphan single commit to `live-data`; `templates/live.js` reads it as
`window.LIVE_SNAPSHOT_URL`, the "keyless ~15-min delayed quotes with NO Worker deploy"
fallback, relying on raw.githubusercontent's `CORS *`. The workflow header records three
consumers. Display-tier delayed market context — not a product artifact.

Also fine: the `/stocks/` SEO estate (195.9 MB), `/research/` teasers, `/assets/`,
`/factordata/tech_events/*` and `/factordata/tech_lab.json` (explicit Terminal-ingest
carve-outs), fonts, vendor JS. These are `public` by policy and public in git — consistent.

**This class is why option (i) is expensive.** Both pillars of the operator's 2026-07-20
acceptance — "mirror + live-quotes" — live here.

### (b) Product artifacts the operator has ruled should not be free — the P1 leak

`us_standouts.json` is the graded board. #3391 ruled the real board is not shown free, and the
landing therefore ships 2-week-**delayed** winners; #3393 regwalled `/factordata/*` because the
board was directly fetchable. Both controls hold on the served path and are bypassed by a
`curl` to raw.githubusercontent. The same applies to `pick_lab.json`, the three
`enforced_early` premium payloads, and the ranked China boards.

Materiality: this is the **paid product**, in machine-readable form, at full fidelity, with no
account, no rate limit, and no attribution. It is also *more* useful to a competitor than to a
subscriber — a subscriber gets the UI; a scraper gets the whole ranked universe as JSON. The
history compounds it: every nightly commit is a dated snapshot, so the mirror is not just
today's board but a **free point-in-time archive of the board's entire history**, which is
precisely the asset the track-record and calibration work exists to build.

I flag one honest counterweight: this exposure has existed for as long as the render has
committed `site/`, so the marginal harm of one more night is small. That argues for a
considered fix, not an emergency one — and it does **not** apply to (c).

### (c) Pipeline internals that leak more than the product — the P0

This is the one that is not yet true and can still be prevented.

**Verified today** against `https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev`:

| Key | Result |
|---|---|
| `live_flow/prophet_marks.json` | **200** — option marks |
| `live_flow/prophet_live.json` | **200** — currently `{"status":"dark","reason":"no_pack"}` |
| `live_flow/prophet_live_armed.json` | **404** — *not yet written* |

The chain, read from source:

- `engine/prophet_live/r2io.py:32` → `PACK_KEY = "live_flow/prophet_live_armed.json"`
- `r2io.bucket()` → `os.environ.get("R2_BUCKET", "mastermindx")`
- `r2io.put_json()` → `cl.put_object(Bucket=bucket(), Key=key, …)`
- `scripts/build_prophet_live_pack.py:430` → `r2io.put_json(r2io.PACK_KEY, payload)`

Bucket `mastermindx` **is** the bucket behind that public base — proven by `live_flow/prophet_live.json`,
written by the same `put_json` to the same bucket, answering 200 anonymously. Therefore the
armed pack's 404 means *"the nightly has not written it yet"*, **not** *"it is private."* On the
first night it publishes it becomes an anonymous public download.

What that pack contains (`engine/prophet_live/armed_pack.py`): per-name `state`,
`center_buyable`, `as_of_close`, `bar_date`, `tier`, `tier_cascade`, `probed`, and for probed
names **the swept trigger/fade threshold levels themselves**, plus pack-level `band_pct`,
`grid_points`, `bisect_iters` and coverage meta. It is built by the nightly and consumed by the
`*/5` evaluator, so it exists **before** anything publishes to users.

**The sharpest point.** `config/site_access.yml` already reasons about exactly this risk and
reaches the opposite conclusion about where safety lies:

> `/live/prophet_live.json` … **MUST NOT** join it. It names which tickers are armed and which
> are forming today — pre-publication board membership, which is what the "don't show the real
> board free" ruling (#3391 …) is about. **(The armed trigger LEVELS are not in it; they stay in
> the R2 pack.)**

The parenthetical treats "they stay in the R2 pack" as the *mitigation* — the levels are
withheld from the gated file because the R2 pack is assumed to be the safer place. **The R2 pack
is in a publicly-bound bucket, so the mitigation is void, and the levels are the more sensitive
half.** The policy file's stated intent and the runtime's actual behavior are in direct
contradiction.

And the second leak is already live: `/live/prophet_live.json` is the artifact that file says
MUST NOT be public. Caddy honors that (it is deliberately left undeclared so it takes
`premium.default_tier`, pinned by `tests/test_prophet_live_vps_lane.py`). The R2 copy serves it
to anyone. It is empty today only because there is no pack; it populates the moment R1's window
closes.

Severity ordering, and why (c) outranks (b) despite being smaller: (b) leaks the **published**
board; (c) leaks **tonight's board membership and its levels before publication**, which is
tradeable ahead of the customers who paid for it.

---

## §4 Options, with costs

### (i) Make the repo private

**Breaks, concretely:**
- **`live.js`'s keyless quote fallback.** `LIVE_SNAPSHOT_URL` fetches `live-data/quotes.json`
  cross-origin from raw.githubusercontent; private repos serve raw only with a token, and no
  token can ship in a browser. Every page's no-Worker fallback dies. The brief forbids this,
  and correctly.
- **A standing operator acceptance.** CXI-R23 Amendment 2 names "repo public for mirror +
  live-quotes" as accepted state. Reversing it is an operator decision, not a fix.
- Unknown external inbound links to raw URLs; any unauthenticated CI/consumer of raw paths.

**Does not fix:** the R2 exposure in §3(c) at all — different system. **Not recommended.**

### (ii) Stop committing gated payloads; serve them only from a private store

**Cost is much higher than it looks**, because git is not only the mirror — it is the
**delivery transport**. `app/deploy/update.sh` fetches and rsyncs `site/` onto the VPS. Removing
287.6 MB of payload from git means building a new transport for it (R2 sync to the VPS, or
authenticated pull), plus reworking the render lane's publish step and the `?v=` stamping that
the Caddyfile `immutable` list depends on. That is a multi-PR infrastructure program, not a
narrowing.

**The private store exists as a proven pattern**, though not one that is drop-in here:
`mastermindx-research` (`research/RESEARCH_VAULT_MASTERPLAN.md:70`) is a private bucket with **no
public/r2.dev binding**, reached by `R2_RESEARCH_*` env vars, delivered through authenticated
FastAPI routes (`/api/research/view`, `/api/research/download`). Note it is documented as a
**separate Cloudflare account** (`tests/test_research_vault.py:1081` — distinct endpoint and
credentials), so the render/prophet lanes' existing `R2_*` credentials will **not** authenticate
against it. Using it means new secrets on every lane that publishes.

Right answer for the **narrow, high-value** case (R1). Wrong tool for all 287 MB.

### (iii) Keep git public; publish only degraded/delayed copies there

Generalizes the pattern the operator **already chose** in #3391: the landing shows 2-week-delayed
winners precisely so the real board is not free. Applied to the mirror: the render writes a
degraded artifact (delayed, truncated, or rank-suppressed) to `site/` for git, and the full
payload is delivered by the private path — or, cheaper, the *ranked/graded* fields are stripped
from the committed copy while display-tier context stays.

**Costs:** per-artifact judgment about what "degraded" means (not mechanical); a real risk of
the two copies drifting; and it needs the same private-delivery transport as (ii) for the full
payload, so it is (ii) plus a compatibility shim — but it can be done **incrementally, worst
artifacts first**, which (ii) cannot.

**Recommended as the structural direction (R2).**

### (iv) Accept and document, narrowing only the worst leaks

Cheapest, and defensible for (b) given the exposure's age. **Not defensible for (c):** accepting
a pre-publication leak of trigger levels is accepting that a scraper trades tonight's board
before the paying customer sees it. Acceptable **only** if paired with R1.

---

## §5 What I did NOT implement, and why

The brief authorized me to ship one narrowing if it were "unambiguously safe and reversible —
e.g. moving Prophet Live's armed pack off a public prefix to a private store without changing
behavior." **I judged it does not currently meet that bar, so I did not ship it.** The blockers
are infrastructure facts I cannot verify or create from here:

1. **No verified private destination exists in the right account.** Bucket-level public access on
   R2 is a Cloudflare binding, not a repo setting — I cannot change it, and I cannot enumerate
   buckets without credentials. `mastermindx-research` is a *different account*, so the prophet
   lane's `R2_ACCESS_KEY_ID` would not authenticate against it.
2. **A misconfigured move takes Prophet Live dark — the exact P0 just shipped.** `put_json`
   returns `False` (never raises) when credentials are absent or wrong, and `get_json` falls back
   to the public base and then returns `None`. A pack published to a bucket the evaluator cannot
   read reproduces today's `{"status":"dark","reason":"no_pack"}` silently, every 5 minutes,
   with no exception anywhere.
3. **`R2_BUCKET` is a single shared secret.** Repointing it moves *every* R2 consumer on the
   lane, not just the pack. A correct fix needs a *separate* destination variable, which is a
   change inside `engine/prophet_live/r2io.py` — the module the brief scopes out.

None of this is a reason to leave it. It is a reason the first step belongs to the operator.

### R1 arming steps (operator)

1. Create an R2 bucket in the **same Cloudflare account** as `mastermindx`, with **no public
   r2.dev binding** (e.g. `mastermindx-live`). Same-account means the existing `R2_ACCESS_KEY_ID`
   / `R2_SECRET_ACCESS_KEY` already authenticate — no new credentials.
2. Confirm which is true, so the fix can be scoped:
   - the whole `live_flow/` prefix should move (simplest — one destination variable), or
   - only `prophet_live_armed.json` + `prophet_live.json` move, and `prophet_marks.json` stays.
3. Then a follow-up PR adds a `PROPHET_LIVE_R2_BUCKET`-style override read by `r2io.bucket()`,
   defaulting to today's value so the change is inert until the secret is set, with tests
   covering: publish-to-private, evaluator read-back, and **a fail-loud** (line-start
   `::warning`) when the pack is unreadable — so blockers 2 and 3 above become visible instead of
   silent. Reversible by unsetting one secret.

**Timing:** the pack has not been written yet. Doing this before its first publish means nothing
ever leaks. That window closes on the next nightly that builds a pack.

---

## §6 Collision check

- `research/DO_NOT_REBUILD.md` — no kill covers this topic. Row 58 (CXI-R23 Amendment 2) is the
  governing operator ruling and is **built on**, not re-litigated: it accepts source visibility
  and explicitly declines to extend that acceptance to product surfaces.
- `docs/ACTIVE_BUILD_MAP.md` — no open lane touches `site_access.yml`, the Caddyfile boundary, or
  the R2 publish targets. Nearest prior work is closed: #3474 (boundary drift → CI), #3418/#3419
  (Caddy access routes), #3393 (the gate this documents the other half of).
- No `engine/prophet_live/*` behavior was changed. No boundary file was edited. This PR is
  documentation only.
