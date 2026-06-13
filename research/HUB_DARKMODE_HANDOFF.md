# Home page (hub) — dark mode + toggles + i18n fix — handoff spec

**For the session that owns the hub / i18n (`_hub_html` in `scripts/build_vector.py`).**
User wants the home page (`index.html`) to get the same treatment as the rest of
the site: a **dark theme**, an **animated dark/light switch**, an **EN/中文 toggle**,
all **remembered across pages** (localStorage, same-origin — no cookies needed).

All edits are in `_hub_html()` in `scripts/build_vector.py`. It's an f-string, so
**every literal CSS brace must be doubled** (`{{ }}`), and `{C['x']}` interpolations
stay as-is.

---

## 🔴 URGENT (pre-existing bug, not part of dark mode)
The live hub currently renders **both languages at once** — `<h1>` shows
"Market Intelligence市场情报". `engine.i18n.t()` was switched to dual-emit
`<span class="l-en">…</span><span class="l-zh">…</span>`, but the hub's `<style>`
has **no visibility CSS** and the `<head>` has **no lang init**, so nothing hides
the inactive language. Fix first:

1. In `<head>` (before `</head>`), add the no-flash init (reads both theme + lang):
```html
<script>try{{var t=localStorage.getItem('theme');if(t)document.documentElement.setAttribute('data-theme',t);var l=localStorage.getItem('lang');if(l)document.documentElement.setAttribute('data-lang',l);}}catch(e){{}}</script>
```
2. In `<style>`, add the dual-emit visibility rules (same as every other page):
```css
html:not([data-lang="zh"]) .l-zh{{display:none}}
html[data-lang="zh"] .l-en{{display:none}}
html[data-lang="zh"] body{{font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans CJK SC",Inter,sans-serif}}
```

That alone makes the hub correctly monolingual + lang-aware (and the lang choice
already carries over from other pages via localStorage).

---

## Dark mode (additive override — no rewrite of the existing light rules)
The hub interpolates `{C['x']}` light literals, so the cleanest low-risk path is an
additive `html[data-theme="dark"]` block appended to `<style>` that overrides the
surfaces/text (everything else stays light by default):
```css
html[data-theme="dark"] body{{background:#0f1115;color:#d7dce3}}
html[data-theme="dark"] .h h1,html[data-theme="dark"] .c h2,html[data-theme="dark"] .feed-h h3,html[data-theme="dark"] .ha-head,html[data-theme="dark"] .ha-edge,html[data-theme="dark"] .site-footer .made{{color:#e8edf4}}
html[data-theme="dark"] .h p,html[data-theme="dark"] .feed-h .n,html[data-theme="dark"] .c p,html[data-theme="dark"] .ha-what,html[data-theme="dark"] .ha-edge b,html[data-theme="dark"] .site-footer .dev{{color:#8b93a1}}
html[data-theme="dark"] .c,html[data-theme="dark"] .feed-card{{background:#181b21;border-color:#2a2f3a}}
html[data-theme="dark"] .c:hover{{box-shadow:0 12px 30px rgba(0,0,0,.5)}}
html[data-theme="dark"] .ha-item,html[data-theme="dark"] .ha-what,html[data-theme="dark"] .site-footer{{border-color:#2a2f3a}}
html[data-theme="dark"] .ha-detail{{color:#d7dce3}}
html[data-theme="dark"] .stat{{background:#222732;color:#d7dce3}}
html[data-theme="dark"] .ha-src.s-macro{{background:#2a2550}}
html[data-theme="dark"] .ha-src.s-vector{{background:#1d2c52}}
html[data-theme="dark"] .ha-src.s-commodity{{background:#3a2f17}}
```
(Light stays the hub's default; if you'd rather flip the whole site to dark-by-
default for first-time visitors, that's a separate call — the macro dashboard
defaults dark, the Vector pages default light, so there's already a mismatch.)

## The toggles (animated, shared mechanism)
`theme.js` is already loaded by the hub and already wires `.theme-switch` →
`toggleTheme` and `.lang-toggle .opt` → `setLang` (pure-CSS visuals off
`data-theme`/`data-lang`). So just add the markup + CSS.

CSS (append to `<style>`):
```css
.hub-ctrls{{position:absolute;top:20px;right:22px;display:flex;align-items:center;gap:10px}}
.theme-switch{{width:56px;height:27px;border-radius:999px;background:#eef1f6;border:1px solid {C['grid']};position:relative;cursor:pointer;padding:0}}
html[data-theme="dark"] .theme-switch{{background:#222732;border-color:#2a2f3a}}
.theme-switch .ic{{position:absolute;top:50%;transform:translateY(-50%);font-size:10.5px;opacity:.5}}
.theme-switch .ic.sun{{left:8px}} .theme-switch .ic.moon{{right:8px}}
.theme-switch .knob{{position:absolute;top:2px;left:2px;width:22px;height:22px;border-radius:50%;background:{C['blue']};display:flex;align-items:center;justify-content:center;font-size:11px;box-shadow:0 2px 5px rgba(0,0,0,.3);transform:translateX(29px);transition:transform .34s cubic-bezier(.34,1.45,.5,1),background .3s}}
.theme-switch .knob::before{{content:"\\2600\\FE0F"}}
html[data-theme="dark"] .theme-switch .knob{{transform:translateX(0);background:#e8c15a}}
html[data-theme="dark"] .theme-switch .knob::before{{content:"\\1F319"}}
.lang-toggle{{display:inline-flex;position:relative;background:#eef1f6;border:1px solid {C['grid']};border-radius:999px;padding:3px;cursor:pointer}}
html[data-theme="dark"] .lang-toggle{{background:#222732;border-color:#2a2f3a}}
.lang-toggle .pill{{position:absolute;top:3px;left:3px;width:calc(50% - 3px);height:calc(100% - 6px);border-radius:999px;background:{C['blue']};transition:transform .34s cubic-bezier(.34,1.4,.5,1)}}
html[data-lang="zh"] .lang-toggle .pill{{transform:translateX(100%)}}
.lang-toggle .opt{{position:relative;z-index:1;min-width:28px;text-align:center;padding:3px 9px;font-size:11.5px;font-weight:600;color:{C['muted']};transition:color .25s;user-select:none}}
html:not([data-lang="zh"]) .lang-toggle .en-opt{{color:#fff}}
html[data-lang="zh"] .lang-toggle .zh-opt{{color:#fff}}
```
The hub body is `display:flex;flex-direction:column;align-items:center` — give it
`position:relative` and drop the control cluster in right after `<body>`:
```html
<div class="hub-ctrls">
  <button class="theme-switch" aria-label="Toggle dark / light mode"><span class="ic sun">☀️</span><span class="ic moon">🌙</span><span class="knob"></span></button>
  <div class="lang-toggle" role="group" aria-label="Language"><span class="pill"></span><span class="opt en-opt" data-l="en">EN</span><span class="opt zh-opt" data-l="zh">中文</span></div>
</div>
```
Add `position:relative;` to the `body{{…}}` rule so `.hub-ctrls` anchors top-right.

## Cross-over
Already handled by `localStorage` (same-origin, shared by all pages). With the
`<head>` init above, the hub honors a theme/lang set on any other dashboard, and
its own toggles persist for the next page. No cookies.

## Reference — this is consistent with the rest of the site
The Vector pages (`templates/vector.html.j2`, `templates/commodities.html.j2`) just
got the identical dark palette (`#0f1115`/`#181b21`/`#2a2f3a`/`#e8edf4`/`#d7dce3`/
`#8b93a1`) + the same `.theme-switch` / `.lang-toggle`. Match those values so the
whole site reads as one dark theme. The macro family uses the same palette via
`theme.css`'s dark `:root`.
