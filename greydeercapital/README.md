# Grey Deer Capital — website

A hand-built, production-quality static site for **Grey Deer Capital LLC** — an active
investment firm centered on signal-based AI quantitative research, AI-assisted qualitative
confirmation, and cycle / regime / rotation analysis.

No build step. No framework. No runtime dependencies beyond three vendored libraries for the
globe. Deploys as plain static files to any web server (the VPS behind `greydeercapital.com`).

---

## Design direction

**Thesis — the deer as the regime-sensor.** A deer is alert and still, sensing change before it
is visible; the firm reads the market's turn before the herd. The antler is branching geometry —
the same shape as a river delta, a capital-rotation network, and a signal tree — so the mark *is*
the thesis, not decoration.

- **Color** — a duotone that maps to the firm's two halves: warm **Fawn `#C7B299`** (the steward /
  human confirmation / deer) meeting cool **Glacial `#63B4AC`** (the signal / flow / AI), on a
  green-undertoned **Graphite `#0E1214`**. Their convergence is the brand.
- **Type** — **Newsreader** (editorial serif → voice), **Hanken Grotesk** (humanist body → clarity),
  **Geist Mono** (utility/data → the quant identity). Loaded from Google Fonts.
- **Signature** — the **antler-delta globe**: an atmospheric d3-orthographic planet whose
  capital-flow arcs travel warm→cool and converge at glowing signal-nodes.
- **Motion** — reveal-on-scroll, an ambient "capital as water" flow field, a cyclical process orbit,
  hover micro-interactions. All gated behind `prefers-reduced-motion`.

---

## Structure

```
greydeercapital/
├── index.html            Flagship homepage (hero globe, offerings, process orbit, ecosystem, CTA)
├── approach.html         Philosophy / how the firm thinks
├── capabilities.html     The six disciplines, in depth (deep-linked from the footer)
├── research.html         Research & insights (filterable note cards — placeholder content)
├── about.html            Firm identity, the name, what makes it different
├── contact.html          Inquiry form for private & institutional prospects
├── legal.html            Disclosures, privacy, terms, Form ADV (placeholder, pending counsel)
├── 404.html              Branded not-found page
├── robots.txt · sitemap.xml · site.webmanifest
└── assets/
    ├── css/  tokens.css · base.css · components.css   (design system, in that cascade order)
    ├── js/   main.js (nav+footer components, reveal, orbit, filter, form)
    │          globe.js (homepage signature)  ·  flowfield.js (ambient current lines)
    ├── vendor/  d3-array · d3-geo · topojson-client · world-110m.json   (globe only)
    └── brand/  mark.svg · mark-mono.svg · favicon.svg · og.svg
```

**Single source of truth for chrome:** the nav and footer are injected by `main.js` into
`#nav-root` / `#footer-root` on every page, so they can never drift out of sync. Each page only
declares its own `<main>` content and sets `<body data-page="…">` to light the active nav link.

**Only three CSS files, in cascade order:** `tokens.css` (variables) → `base.css` (reset,
typography, atmosphere) → `components.css` (every component class). No page defines its own
`<style>` block; all pages assemble from the same component kit.

---

## Local preview

```bash
cd greydeercapital
python3 -m http.server 8777
# open http://localhost:8777
```

A server is required (the globe fetches `world-110m.json`, and the nav/footer are injected by JS).

## Deploy

Copy the contents of `greydeercapital/` to the web root that serves `greydeercapital.com`
(e.g. `rsync -a greydeercapital/ vps:/var/www/greydeercapital/`). Everything is relative-pathed,
so it works from any root. Configure the server to serve `404.html` for not-found responses.

### Production to-dos (noted where relevant in the code)
- Rasterize `assets/brand/og.svg` → `og.png` (1200×630) for the widest social-preview support,
  and update the `og:image` / `twitter:image` URLs.
- Wire the contact form (`main.js` → `initForm`) to a real intake endpoint or CRM; it currently
  validates and shows a success state client-side without sending.
- Have counsel review and finalize `legal.html`.
- `admin.greydeercapital.com` and `client.greydeercapital.com` are separate applications; this
  repository contains the public brand site only.

---

*Not investment advice. © Grey Deer Capital LLC.*
