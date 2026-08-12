# Cross-repo page registry

`data/product_experience/page_registry.json` is a census of every user-visible
route across the three product repos — `macro` (this static site), `terminal`
(charting-app, Next.js) and `mastermind` (the FastAPI portfolio app). One row per
route, or per route FAMILY where a builder renders thousands of pages from one
template.

It exists so a product question — *what surfaces do we ship, who can reach them,
what renders them, and which ones is nobody looking after* — can be answered from
one file instead of three repo tours.

- Generator: `scripts/build_product_page_registry.py`
- Hand-maintained overlay: `config/product_experience/page_registry_overrides.yml`
- Tests / CI drift guard: `tests/test_build_product_page_registry.py`

## Regenerate

```bash
# full rebuild (needs both sister repos on disk; a few seconds)
python3 scripts/build_product_page_registry.py --as-of 2026-08-11T00:00:00Z

# validate the committed artifact — no sister repos, no network, CI-safe
python3 scripts/build_product_page_registry.py --check

# optional: attach open PRs that touch each row's files (ONE `gh` call)
python3 scripts/build_product_page_registry.py --with-prs
```

Flags: `--output`, `--overrides`, `--terminal-root`, `--terminal-ref`
(default `origin/master`), `--mastermind-root`, `--site-dir`, `--as-of`,
`--with-prs`, `--check`.

Two habits keep diffs honest:

- **Always pass `--as-of`** when regenerating for a PR. Without it `generated_at`
  is "now", and every rebuild churns the file.
- **`--with-prs` is opt-in.** It spends one `gh pr list` call, and the GitHub REST
  pool is shared by every session and hook in the fleet (CLAUDE.md). Never poll it.

The terminal rows are read from a git REF, never from the charting-app working
tree — that checkout is routinely a stale feature branch. The resolved SHA is
recorded in `sources.terminal.sha`.

## Top level

```json
{
  "schema": "mastermind.page_registry.v1",
  "generated_at": "2026-08-11T00:00:00Z",
  "sources": { "macro": {...}, "terminal": {...}, "mastermind": {...} },
  "pages": [ ... ]
}
```

`sources.<repo>` carries the provenance of that repo's rows: the root, the git
ref and SHA the rows were read from, how the page inventory was obtained, and —
for macro — how many `write_page()` call sites resolved and how many did not
(`write_page_unresolved`, with a sample in `unresolved_write_sites`). A repo that
is missing or unreadable gets `{"available": false, "reason": ...}` and
contributes no rows; the build never crashes and never guesses.

Rows are sorted by `(repo, route, page_id)` and every row carries every field in
a fixed order, so a diff of the file is a diff of facts.

## Fields

| Field | Meaning |
|---|---|
| `page_id` | Stable slug, always `<repo>:<slug>` (`macro:us_stocks`, `terminal:options`). Families end in `_family`. This is the override key. |
| `repo` | `macro` \| `terminal` \| `mastermind` |
| `route` | URL path (`/us_stocks.html`, `/options`). Family routes carry a `<param>` segment: `/stocks/<id>.html`. |
| `route_kind` | `page` \| `family` |
| `source_template` | Repo-relative path of what renders the page. For hand-authored macro pages and Next.js page modules the file IS the page. |
| `builder` | Repo-relative builder script paths (macro). `[]` for pages nothing builds; a page can have several. |
| `data_sources` | Reserved for v2 — `[]` in v1. Deriving the data behind a page is separate work. |
| `access_shell` | Who can reach the shell: `anonymous` \| `signed_in` \| `paid` \| `admin` \| `operator` \| `unknown` |
| `payload_tier` | What the DATA behind it costs: `public` \| `public_shell_premium_payload` \| `premium` \| `internal` \| `unknown` |
| `nav_family` | Which link inventory names it (`product_nav.china` from `templates/_navlinks.html.j2`, `public_nav.public` from `templates/_public_nav.html.j2`, `footer.legal` from `templates/_public_footer.html.j2`, `app_nav.rail` from the terminal's `AppNav.tsx`), or `none` when nothing links it. The navs outrank the footer, so a page takes its footer column only when no nav names it. `none` is a finding, not a gap. |
| `archetype` | Overlay only. Default `unclassified`. |
| `primary_user_question` | Overlay only. Default `""`. |
| `owner` | Overlay only. Default `unowned` — and it is `unowned` everywhere in v1 on purpose. |
| `lifecycle` | `live` \| `lab` \| `internal` \| `parked` \| `dev_only` \| `unknown` |
| `priority` | Overlay only: `P0`..`P3` \| `unclassified`. Never derived. |
| `generated` | `true` (a builder renders it), `false` (hand-authored / plain-copy / a page module), or `"unknown"`. |
| `bilingual` | `true` \| `false` \| `"unknown"` |
| `themes` | `["light","dark"]` \| `["dark"]` \| `"unknown"` |
| `locales` | `["en","zh"]` \| `["en"]` \| `"unknown"` |
| `known_contracts` | Rules that govern the page, e.g. `site_access.v1:free_registered`, or the lib/pages.py rule that decides which tickers get a page. |
| `open_prs` | `[]` unless built with `--with-prs`. |
| `source_evidence` | `path` or `path:line` strings backing the derived facts. Every row has at least one. |
| `notes` | Free text: caveats, counts, why a fact is missing. |

### `payload_tier`, precisely

Every macro `*.html` **shell** has been anonymous since 2026-08-04
(`config/site_access.yml` header) — the registration wall that used to 302 member
pages is gone. What the policy still gates is the payload, so for macro:

- `internal` — the route is in the policy's `deny` bucket (404 even for an
  entitled user). `access_shell` is then `unknown`, because "nobody, in
  production" is not one of the access values.
- `public` — the route is in `public`, and its template does not read a
  premium-enforced payload.
- `public_shell_premium_payload` — either a public shell that reads a payload
  under `premium.enforced_early` (or paints a `tier_preview` lock), or a page
  whose payload sits behind `free_registered` / the Insider+ default. The exact
  bucket is recorded in `known_contracts`.
- `premium` — the whole surface needs a paid entitlement. Used for terminal
  `/options` (feature `terminal_live_options`).

## Unknown handling

`"unknown"` is a value, not a hole. A fact the code does not state is recorded as
the literal string `"unknown"` (or `[]` for list fields), never as `null`, never
as a plausible guess. `--check` fails on any `null`.

The main known gaps in v1, all visible in the artifact itself:

- macro pages whose route no `write_page()` call site resolves to (the builder
  takes its output path as a parameter, or builds the path from a data file):
  `source_template` and `builder` stay unknown, with a note saying so.
- directory families whose output directory is chosen at runtime
  (`site / out_name`): the family row has no builder.
- `data_sources` is empty for every row in v1.

Attribution is deliberately conservative. A builder's family write is used to
attribute individual pages only when the pattern carries real constant material
(`/fund_<slug>.html` attributes `fund_berkshire.html`; `/<name>.html` matches the
whole site and attributes nothing).

## The overrides law

`config/product_experience/page_registry_overrides.yml` is the ONLY hand-edited
input. Its own header states the rules; in short:

1. Judgment fields (`priority`, `archetype`, `primary_user_question`, `owner`)
   and access facts a static reader cannot honestly see live there — nowhere else.
2. Each entry should carry `evidence: [paths]`; `note:` is appended to the row's
   notes so the reason travels with the row.
3. An override for a page_id that no longer exists is a **hard error** — the build
   exits non-zero with a `::error` annotation, and `--check` re-checks it against
   the committed artifact. Stale overrides cannot accumulate.
4. Only overridable fields may be set. `route`, `builder`, `source_template`,
   `source_evidence` and friends are derived-only, so the overlay can never
   invent a page the code does not render.

v1 seeds only the P0 set (acquisition, activation, and the paid product itself)
and the terminal/mastermind access + lifecycle facts. P1–P3 assignment is a
separate work item; everything else stays `unclassified`. `owner` is `unowned`
everywhere — the census reports that honestly rather than inventing names.

## Tests

`tests/test_build_product_page_registry.py` has two halves:

- **Schema suite** against the committed JSON — every row has every field, page_ids
  are unique and repo-prefixed, enums are valid, nothing is `null`, every row cites
  evidence, every override resolves. This is the drift guard: regenerate the
  artifact when the census changes, or the suite goes red.
- **Derivation units** on `tmp_path` fixtures with an injected `run_git` callable.
  No test reads a sister repo, shells out to git or `gh`, or touches the network.
